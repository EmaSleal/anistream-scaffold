"""Integration tests for progress routes and build_continue_watching domain function.

The DB layer is mocked. Auth is bypassed via patched INTERNAL_JWT_SECRET and PyJWT tokens.
"""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

TEST_SECRET = "test-internal-secret-for-tests-only"
os.environ.setdefault("INTERNAL_JWT_SECRET", TEST_SECRET)
os.environ.setdefault("SERVICE_SECRET", "test-service-secret-for-tests-only")

import json
import pytest
import jwt as pyjwt
from unittest.mock import patch

import auth as auth_module
auth_module._INTERNAL_JWT_SECRET = TEST_SECRET


def _token(user_id: str = "u-1", role: str = "USER") -> str:
    return pyjwt.encode(
        {"sub": user_id, "role": role, "exp": int(time.time()) + 60},
        TEST_SECRET,
        algorithm="HS256",
    )


def _auth_header(user_id: str = "u-1") -> dict:
    return {"Authorization": f"Bearer {_token(user_id)}"}


def _progress_row(
    episode_id: str = "ep1",
    series_id: str = "s1",
    progress_sec: float = 100.0,
    duration_sec: float = 1440.0,
    updated_at: str = "2026-01-01T00:00:00Z",
) -> dict:
    return {
        "episode_id": episode_id,
        "series_id": series_id,
        "progress_sec": progress_sec,
        "duration_sec": duration_sec,
        "updated_at": updated_at,
    }


def _episode_row(id: str = "ep1", series_id: str = "s1") -> dict:
    return {
        "id": id,
        "series_id": series_id,
        "episode_number": 1,
        "title": "Episode 1",
        "animeflv_slug": f"{series_id}-1",
        "thumbnail_url": None,
        "aired_at": None,
        "series": {"title": "Naruto"},
    }


@pytest.fixture
def client():
    with patch("storage.get_client"):
        from app import create_app
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c


# ---------------------------------------------------------------------------
# POST /api/progress
# ---------------------------------------------------------------------------

class TestUpsertProgress:
    def test_creates_row_returns_200(self, client):
        with patch("db.progress.upsert_progress") as mock_up:
            res = client.post(
                "/api/progress",
                headers=_auth_header(),
                data=json.dumps({
                    "episode_id": "ep1",
                    "series_id": "s1",
                    "progress_sec": 120,
                    "duration_sec": 1440,
                }),
                content_type="application/json",
            )
        assert res.status_code == 200
        mock_up.assert_called_once()

    def test_update_same_episode_returns_200(self, client):
        with patch("db.progress.upsert_progress"):
            res1 = client.post(
                "/api/progress",
                headers=_auth_header(),
                data=json.dumps({"episode_id": "ep1", "series_id": "s1", "progress_sec": 100}),
                content_type="application/json",
            )
            res2 = client.post(
                "/api/progress",
                headers=_auth_header(),
                data=json.dumps({"episode_id": "ep1", "series_id": "s1", "progress_sec": 500}),
                content_type="application/json",
            )
        assert res1.status_code == 200
        assert res2.status_code == 200

    def test_missing_episode_id_returns_400(self, client):
        res = client.post(
            "/api/progress",
            headers=_auth_header(),
            data=json.dumps({"series_id": "s1", "progress_sec": 100}),
            content_type="application/json",
        )
        assert res.status_code == 400

    def test_missing_series_id_returns_400(self, client):
        res = client.post(
            "/api/progress",
            headers=_auth_header(),
            data=json.dumps({"episode_id": "ep1", "progress_sec": 100}),
            content_type="application/json",
        )
        assert res.status_code == 400

    def test_missing_progress_sec_returns_400(self, client):
        res = client.post(
            "/api/progress",
            headers=_auth_header(),
            data=json.dumps({"episode_id": "ep1", "series_id": "s1"}),
            content_type="application/json",
        )
        assert res.status_code == 400

    def test_missing_duration_sec_does_not_return_400(self, client):
        """duration_sec is nullable — default to 0, NEVER return 400."""
        with patch("db.progress.upsert_progress") as mock_up:
            res = client.post(
                "/api/progress",
                headers=_auth_header(),
                data=json.dumps({"episode_id": "ep1", "series_id": "s1", "progress_sec": 100}),
                content_type="application/json",
            )
        assert res.status_code == 200
        # Verify duration_sec defaulted to 0
        call_kwargs = mock_up.call_args
        assert call_kwargs.kwargs.get("duration_sec") == 0.0

    def test_unauthenticated_returns_401(self, client):
        res = client.post(
            "/api/progress",
            data=json.dumps({"episode_id": "ep1", "series_id": "s1", "progress_sec": 100}),
            content_type="application/json",
        )
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/progress/<episode_id>
# ---------------------------------------------------------------------------

class TestGetEpisodeProgress:
    def test_existing_row_returns_progress_sec(self, client):
        with patch("db.progress.get_episode_progress", return_value=350.0):
            res = client.get("/api/progress/ep1", headers=_auth_header())
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data["progress_sec"] == 350.0

    def test_no_row_returns_zero(self, client):
        with patch("db.progress.get_episode_progress", return_value=0):
            res = client.get("/api/progress/ep99", headers=_auth_header())
        assert res.status_code == 200
        assert json.loads(res.data)["progress_sec"] == 0

    def test_unauthenticated_returns_401(self, client):
        res = client.get("/api/progress/ep1")
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/progress/continue-watching
# ---------------------------------------------------------------------------

class TestContinueWatching:
    def test_empty_progress_returns_empty_array(self, client):
        with patch("db.progress.get_recent_progress", return_value=[]):
            res = client.get("/api/progress/continue-watching", headers=_auth_header())
        assert res.status_code == 200
        assert json.loads(res.data) == []

    def test_returns_enriched_episodes(self, client):
        rows = [_progress_row("ep1", "s1", 100, 1440)]
        eps = [_episode_row("ep1", "s1")]
        with (
            patch("db.progress.get_recent_progress", return_value=rows),
            patch("db.progress.get_series_franchise_map", return_value={"s1": "f1"}),
            patch("db.progress.get_episodes_by_ids", return_value=eps),
        ):
            res = client.get("/api/progress/continue-watching", headers=_auth_header())
        data = json.loads(res.data)
        assert res.status_code == 200
        assert len(data) == 1
        assert "episode" in data[0]
        assert data[0]["progressSeconds"] == 100

    def test_unauthenticated_returns_401(self, client):
        res = client.get("/api/progress/continue-watching")
        assert res.status_code == 401

    def test_continue_watching_route_not_matched_as_episode_id(self, client):
        """Ensure 'continue-watching' is NOT treated as an episode_id param."""
        # If routing were wrong, it would call get_episode_progress("continue-watching")
        with patch("db.progress.get_recent_progress", return_value=[]):
            res = client.get("/api/progress/continue-watching", headers=_auth_header())
        # Should hit continue_watching route (200), not episode progress route
        assert res.status_code == 200
        assert isinstance(json.loads(res.data), list)


# ---------------------------------------------------------------------------
# POST /api/progress/advance
# ---------------------------------------------------------------------------

class TestAdvanceEpisode:
    def test_advance_200(self, client):
        """Authenticated POST with all required fields returns 200 {"advanced": true}."""
        with patch("db.progress.advance_episode") as mock_advance:
            res = client.post(
                "/api/progress/advance",
                headers=_auth_header(),
                data=json.dumps({
                    "current_episode_id": "ep1",
                    "current_series_id": "s1",
                    "duration_sec": 1440,
                    "next_episode_id": "ep2",
                    "next_series_id": "s1",
                }),
                content_type="application/json",
            )
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data == {"advanced": True}
        mock_advance.assert_called_once_with(
            user_id="u-1",
            current_ep_id="ep1",
            current_series_id="s1",
            duration_sec=1440.0,
            next_ep_id="ep2",
            next_series_id="s1",
        )

    def test_advance_400_missing_next_episode_id(self, client):
        """Authenticated POST without next_episode_id returns 400."""
        res = client.post(
            "/api/progress/advance",
            headers=_auth_header(),
            data=json.dumps({
                "current_episode_id": "ep1",
                "current_series_id": "s1",
                "duration_sec": 1440,
            }),
            content_type="application/json",
        )
        assert res.status_code == 400
        data = json.loads(res.data)
        assert "error" in data

    def test_advance_401_unauthenticated(self, client):
        """POST without auth token returns 401."""
        res = client.post(
            "/api/progress/advance",
            data=json.dumps({
                "current_episode_id": "ep1",
                "current_series_id": "s1",
                "duration_sec": 1440,
                "next_episode_id": "ep2",
                "next_series_id": "s1",
            }),
            content_type="application/json",
        )
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# Unit tests: build_continue_watching (domain/progress.py)
# ---------------------------------------------------------------------------

from domain.progress import build_continue_watching


class TestBuildContinueWatching:
    def test_empty_input_returns_empty_list(self):
        result = build_continue_watching([], {}, [])
        assert result == []

    def test_franchise_dedup_keeps_most_recent(self):
        """Two series in the same franchise — only keep the first (most recent)."""
        rows = [
            _progress_row("ep1", "s1", 100, 1440, "2026-01-02T00:00:00Z"),
            _progress_row("ep2", "s2", 200, 1440, "2026-01-01T00:00:00Z"),
        ]
        franchise_map = {"s1": "franchise-A", "s2": "franchise-A"}
        eps = [_episode_row("ep1", "s1"), _episode_row("ep2", "s2")]

        result = build_continue_watching(rows, franchise_map, eps)
        assert len(result) == 1
        assert result[0]["episode"]["id"] == "ep1"

    def test_different_franchises_both_included(self):
        rows = [
            _progress_row("ep1", "s1", 100, 1440),
            _progress_row("ep2", "s2", 200, 1440),
        ]
        franchise_map = {"s1": "f1", "s2": "f2"}
        eps = [_episode_row("ep1", "s1"), _episode_row("ep2", "s2")]

        result = build_continue_watching(rows, franchise_map, eps)
        assert len(result) == 2

    def test_near_complete_episode_filtered_out(self):
        """progress_sec / duration_sec >= 0.95 → episode filtered."""
        rows = [_progress_row("ep1", "s1", progress_sec=1400, duration_sec=1440)]
        # 1400/1440 = 0.972 >= 0.95 → filtered
        franchise_map = {"s1": "f1"}
        eps = [_episode_row("ep1", "s1")]

        result = build_continue_watching(rows, franchise_map, eps)
        assert result == []

    def test_exactly_95_percent_filtered_out(self):
        rows = [_progress_row("ep1", "s1", progress_sec=1368, duration_sec=1440)]
        # 1368/1440 = 0.95 → filtered
        franchise_map = {"s1": "f1"}
        eps = [_episode_row("ep1", "s1")]

        result = build_continue_watching(rows, franchise_map, eps)
        assert result == []

    def test_below_95_percent_included(self):
        rows = [_progress_row("ep1", "s1", progress_sec=1300, duration_sec=1440)]
        # 1300/1440 = 0.903 < 0.95 → included
        franchise_map = {"s1": "f1"}
        eps = [_episode_row("ep1", "s1")]

        result = build_continue_watching(rows, franchise_map, eps)
        assert len(result) == 1

    def test_zero_duration_not_filtered(self):
        """When duration_sec == 0, we cannot compute pct — do NOT filter."""
        rows = [_progress_row("ep1", "s1", progress_sec=500, duration_sec=0)]
        franchise_map = {"s1": "f1"}
        eps = [_episode_row("ep1", "s1")]

        result = build_continue_watching(rows, franchise_map, eps)
        assert len(result) == 1

    def test_caps_at_10_items(self):
        """Output is capped at 10 regardless of input size."""
        rows = [_progress_row(f"ep{i}", f"s{i}", 100, 1440) for i in range(20)]
        franchise_map = {f"s{i}": f"f{i}" for i in range(20)}
        eps = [_episode_row(f"ep{i}", f"s{i}") for i in range(20)]

        result = build_continue_watching(rows, franchise_map, eps)
        assert len(result) == 10

    def test_episode_not_found_is_skipped(self):
        """If an episode ID has no matching row in episode_rows, skip it."""
        rows = [_progress_row("ep-missing", "s1", 100, 1440)]
        franchise_map = {"s1": "f1"}
        eps = []  # No episode data returned

        result = build_continue_watching(rows, franchise_map, eps)
        assert result == []

    def test_result_structure(self):
        """Each item has episode (camelCase), progressSeconds, seriesId."""
        rows = [_progress_row("ep1", "s1", 250, 1440)]
        franchise_map = {"s1": "f1"}
        eps = [_episode_row("ep1", "s1")]

        result = build_continue_watching(rows, franchise_map, eps)
        assert len(result) == 1
        item = result[0]
        assert "episode" in item
        assert "progressSeconds" in item
        assert "seriesId" in item
        assert item["progressSeconds"] == 250
        assert item["seriesId"] == "s1"
        # Episode is camelCase-mapped
        assert "seriesId" in item["episode"]
