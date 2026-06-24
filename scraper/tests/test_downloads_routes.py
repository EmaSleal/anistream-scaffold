"""Integration tests for /api/admin/downloads/* routes.

All external I/O (Supabase, NAS, stream scrapers) is mocked.
"""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("INTERNAL_JWT_SECRET", "test-internal-secret-for-tests-only")
os.environ.setdefault("SERVICE_SECRET", "test-service-secret")

import json
from unittest.mock import patch, MagicMock

import jwt as pyjwt
import pytest

_SECRET = "test-internal-secret-for-tests-only"


def _make_token(role: str = "ADMIN") -> str:
    payload = {"sub": "user-1", "role": role, "exp": int(time.time()) + 60}
    return pyjwt.encode(payload, _SECRET, algorithm="HS256")


def _admin_headers() -> dict:
    return {"Authorization": f"Bearer {_make_token('ADMIN')}"}


def _user_headers() -> dict:
    return {"Authorization": f"Bearer {_make_token('USER')}"}


_STREAM_CONFIG = {"principal_slug": "slug-av1", "fallback_slug": "slug-jk", "animeflv_disabled": True}
_EPISODES = [
    {"episode_number": 1, "title": "Pilot"},
    {"episode_number": 2, "title": "Episode 2"},
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    import auth as auth_module
    auth_module._INTERNAL_JWT_SECRET = _SECRET

    with patch("storage.get_client"):
        from app import create_app
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c


# ---------------------------------------------------------------------------
# Auth guard — all routes return 401/403 without a valid admin token
# ---------------------------------------------------------------------------

class TestAuthGuard:
    def test_episodes_no_token_returns_401(self, client):
        res = client.get("/api/admin/downloads/episodes/series-1")
        assert res.status_code == 401

    def test_episodes_user_role_returns_403(self, client):
        res = client.get("/api/admin/downloads/episodes/series-1", headers=_user_headers())
        assert res.status_code == 403

    def test_sources_no_token_returns_401(self, client):
        res = client.get("/api/admin/downloads/sources/series-1?episode_number=1")
        assert res.status_code == 401

    def test_trigger_no_token_returns_401(self, client):
        res = client.post("/api/admin/downloads/trigger", json={})
        assert res.status_code == 401

    def test_jobs_no_token_returns_401(self, client):
        res = client.get("/api/admin/downloads/jobs/job-1")
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# GET /episodes/<series_id>
# ---------------------------------------------------------------------------

class TestEpisodesRoute:
    def test_happy_path_fan_out(self, client):
        with patch("routes.downloads_routes.db_episodes.get_episodes_by_series", return_value=_EPISODES), \
             patch("routes.downloads_routes.nas_configured", return_value=True), \
             patch("routes.downloads_routes.check_episode_status", return_value="downloaded"):
            res = client.get("/api/admin/downloads/episodes/series-1", headers=_admin_headers())
        assert res.status_code == 200
        data = json.loads(res.data)
        assert len(data["episodes"]) == 2
        assert all(ep["status"] == "downloaded" for ep in data["episodes"])

    def test_returns_unknown_when_nas_not_configured(self, client):
        with patch("routes.downloads_routes.db_episodes.get_episodes_by_series", return_value=_EPISODES), \
             patch("routes.downloads_routes.nas_configured", return_value=False):
            res = client.get("/api/admin/downloads/episodes/series-1", headers=_admin_headers())
        assert res.status_code == 200
        data = json.loads(res.data)
        assert all(ep["status"] == "unknown" for ep in data["episodes"])

    def test_returns_empty_list_for_series_with_no_episodes(self, client):
        with patch("routes.downloads_routes.db_episodes.get_episodes_by_series", return_value=[]):
            res = client.get("/api/admin/downloads/episodes/series-1", headers=_admin_headers())
        assert res.status_code == 200
        assert json.loads(res.data)["episodes"] == []


# ---------------------------------------------------------------------------
# GET /sources/<series_id>
# ---------------------------------------------------------------------------

class TestSourcesRoute:
    def test_happy_path(self, client):
        sources = [{"source": "animeav1", "available": True}]
        with patch("routes.downloads_routes.db_series.get_stream_config", return_value=_STREAM_CONFIG), \
             patch("routes.downloads_routes.probe_sources", return_value=sources):
            res = client.get(
                "/api/admin/downloads/sources/series-1?episode_number=1",
                headers=_admin_headers(),
            )
        assert res.status_code == 200
        assert json.loads(res.data)["sources"] == sources

    def test_400_when_episode_number_missing(self, client):
        res = client.get("/api/admin/downloads/sources/series-1", headers=_admin_headers())
        assert res.status_code == 400

    def test_404_when_series_not_found(self, client):
        with patch("routes.downloads_routes.db_series.get_stream_config", return_value=None):
            res = client.get(
                "/api/admin/downloads/sources/series-1?episode_number=1",
                headers=_admin_headers(),
            )
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# POST /trigger
# ---------------------------------------------------------------------------

class TestTriggerRoute:
    def test_202_on_success(self, client):
        with patch("routes.downloads_routes.db_series.get_stream_config", return_value=_STREAM_CONFIG), \
             patch("routes.downloads_routes.resolve_source", return_value="http://cdn/ep1.m3u8"), \
             patch("routes.downloads_routes.create_download_job", return_value={"jobId": "job-1", "status": "pending"}):
            res = client.post(
                "/api/admin/downloads/trigger",
                json={"series_id": "series-1", "episode_number": 1, "source": "animeav1"},
                headers=_admin_headers(),
            )
        assert res.status_code == 202
        data = json.loads(res.data)
        assert data["jobId"] == "job-1"

    def test_422_when_source_cannot_resolve(self, client):
        with patch("routes.downloads_routes.db_series.get_stream_config", return_value=_STREAM_CONFIG), \
             patch("routes.downloads_routes.resolve_source", return_value=None):
            res = client.post(
                "/api/admin/downloads/trigger",
                json={"series_id": "series-1", "episode_number": 1, "source": "animeav1"},
                headers=_admin_headers(),
            )
        assert res.status_code == 422
        assert json.loads(res.data)["error"] == "no_source"

    def test_503_when_nas_unavailable(self, client):
        from domain.nas_jobs import NasUnavailable
        with patch("routes.downloads_routes.db_series.get_stream_config", return_value=_STREAM_CONFIG), \
             patch("routes.downloads_routes.resolve_source", return_value="http://cdn/ep1.m3u8"), \
             patch("routes.downloads_routes.create_download_job", side_effect=NasUnavailable("down")):
            res = client.post(
                "/api/admin/downloads/trigger",
                json={"series_id": "series-1", "episode_number": 1, "source": "animeav1"},
                headers=_admin_headers(),
            )
        assert res.status_code == 503

    def test_400_when_body_missing_fields(self, client):
        res = client.post(
            "/api/admin/downloads/trigger",
            json={},
            headers=_admin_headers(),
        )
        assert res.status_code == 400

    def test_404_when_series_not_found(self, client):
        with patch("routes.downloads_routes.db_series.get_stream_config", return_value=None):
            res = client.post(
                "/api/admin/downloads/trigger",
                json={"series_id": "series-1", "episode_number": 1, "source": "animeav1"},
                headers=_admin_headers(),
            )
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# GET /jobs/<job_id>
# ---------------------------------------------------------------------------

class TestJobsRoute:
    def test_returns_status_on_success(self, client):
        with patch("routes.downloads_routes.get_job_status", return_value={"status": "done"}):
            res = client.get("/api/admin/downloads/jobs/job-1", headers=_admin_headers())
        assert res.status_code == 200
        assert json.loads(res.data)["status"] == "done"

    def test_returns_unknown_when_nas_unreachable(self, client):
        with patch("routes.downloads_routes.get_job_status", return_value={"status": "unknown"}):
            res = client.get("/api/admin/downloads/jobs/job-1", headers=_admin_headers())
        assert res.status_code == 200
        assert json.loads(res.data)["status"] == "unknown"

    def test_includes_error_field_when_failed(self, client):
        with patch("routes.downloads_routes.get_job_status", return_value={"status": "failed", "error": "disk full"}):
            res = client.get("/api/admin/downloads/jobs/job-1", headers=_admin_headers())
        data = json.loads(res.data)
        assert data["status"] == "failed"
        assert data["error"] == "disk full"
