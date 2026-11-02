"""T-009 / ADR-016: admin list / accept / deny endpoints for slug suggestions."""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("INTERNAL_JWT_SECRET", "test-internal-secret-for-tests-only")
os.environ.setdefault("SERVICE_SECRET", "test-service-secret-for-tests-only")

import jwt as pyjwt
import pytest
from unittest.mock import patch

_SECRET = "test-internal-secret-for-tests-only"
M = "routes.slug_suggestions_routes"
BASE = "/api/admin/slug-suggestions"


def _headers(role="ADMIN"):
    tok = pyjwt.encode({"sub": "u", "role": role, "exp": int(time.time()) + 60}, _SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {tok}"}


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


def _sug(source="animeav1", status="pending", slug="shared"):
    return {"id": "sug-1", "series_id": "s2", "source": source, "slug": slug, "status": status}


_ROW = {"id": "s2", "franchise_id": "f1", "season_order": 2, "episode_count": 12,
        "kitsu_id": None, "mal_id": 7}
_PAGE_EPS = [{"episode_number": n, "thumbnail_url": None} for n in range(1, 25)]


class _Env:
    """Patches every collaborator of accept/deny and records writes."""

    def __init__(self, suggestion, row=_ROW, offset=0, page=_PAGE_EPS, jk_info=None, mark_ok=True):
        self.mark_ok = mark_ok
        self.set_slug, self.upsert, self.decided = [], [], []
        self.patches = [
            patch(f"{M}.db.get_suggestion", return_value=suggestion),
            patch(f"{M}.get_series_by_id", return_value=row),
            patch(f"{M}._claimed_episode_offset", return_value=offset),
            patch(f"{M}.fetch_kitsu_episodes", return_value={}),
            patch(f"{M}.fetch_jikan_episodes", return_value={}),
            patch("routes.ingest_routes.scrape_animeav1_episodes", return_value=page),
            patch(f"{M}.fetch_jkanime_series_info", return_value=jk_info),
            patch(f"{M}._detect_av1_dub", return_value=False),
            patch(f"{M}.db.set_series_slug", side_effect=lambda *a, **k: self.set_slug.append(a)),
            patch(f"{M}.upsert_episodes", side_effect=lambda e: self.upsert.append(e) or len(e)),
            patch(f"{M}.db.mark_decided", side_effect=lambda *a: self.decided.append(a) or self.mark_ok),
        ]

    def __enter__(self):
        for p in self.patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in self.patches:
            p.stop()

    @property
    def wrote_nothing(self):
        return not (self.set_slug or self.upsert or self.decided)


class TestAuth:
    @pytest.mark.parametrize("method,path", [("get", ""), ("post", "/accept"), ("post", "/deny")])
    def test_requires_admin(self, client, method, path):
        assert getattr(client, method)(BASE + path).status_code == 401
        assert getattr(client, method)(BASE + path, headers=_headers("USER")).status_code == 403


class TestList:
    def test_defaults_to_pending_and_paginates(self, client):
        with patch(f"{M}.db.list_suggestions", return_value=([_sug()], 41)) as lst:
            res = client.get(BASE + "?page=2&per_page=10", headers=_headers())
        assert res.status_code == 200
        assert lst.call_args[0] == ("pending", 2, 10)
        assert res.get_json() == {"items": [_sug()], "total": 41, "page": 2, "per_page": 10}

    def test_status_filter_and_invalid_status(self, client):
        with patch(f"{M}.db.list_suggestions", return_value=([], 0)) as lst:
            assert client.get(BASE + "?status=denied", headers=_headers()).status_code == 200
            assert lst.call_args[0][0] == "denied"
        res = client.get(BASE + "?status=bogus", headers=_headers())
        assert res.status_code == 400 and res.is_json


class TestAccept:
    def test_animeav1_builds_episodes_with_offset_and_marks_accepted(self, client):
        # Shared page: 24 episodes, 12 claimed by the earlier cour -> own slice 13..24.
        with _Env(_sug(), offset=12) as env:
            res = client.post(BASE + "/accept", json={"id": "sug-1"}, headers=_headers())
        assert res.status_code == 200
        body = res.get_json()
        assert body["episodes_ingested"] == 12 and body["status"] == "accepted"
        assert env.set_slug == [("s2", "principal_slug", "shared", None)]
        nums = [e["episode_number"] for e in env.upsert[0]]
        assert nums == list(range(13, 25))
        assert env.upsert[0][0]["id"] == "s2-ep-13"  # same id as a metadata stub
        assert env.decided == [("sug-1", "accepted")]

    def test_jkanime_persists_fallback_slug(self, client):
        sug = _sug(source="jkanime", slug="jk")
        with _Env(sug, jk_info={"episode_count": 12}) as env:
            res = client.post(BASE + "/accept", json={"id": "sug-1"}, headers=_headers())
        assert res.status_code == 200 and res.get_json()["episodes_ingested"] == 12
        assert env.set_slug == [("s2", "fallback_slug", "jk", None)]

    def test_undeterminable_offset_is_409_and_writes_nothing(self, client):
        with _Env(_sug(), offset=None) as env:
            res = client.post(BASE + "/accept", json={"id": "sug-1"}, headers=_headers())
        assert res.status_code == 409 and res.get_json()["reason"] == "ambiguous_shared_slug_offset"
        assert env.wrote_nothing

    def test_capless_continuation_is_409_and_writes_nothing(self, client):
        with _Env(_sug(), row={**_ROW, "episode_count": 0}, offset=12) as env:
            res = client.post(BASE + "/accept", json={"id": "sug-1"}, headers=_headers())
        assert res.status_code == 409 and res.get_json()["reason"] == "capless_continuation"
        assert env.wrote_nothing

    def test_no_episodes_is_409_and_writes_nothing(self, client):
        with _Env(_sug(), page=[]) as env:
            res = client.post(BASE + "/accept", json={"id": "sug-1"}, headers=_headers())
        assert res.status_code == 409 and res.get_json()["reason"] == "no_episodes"
        assert env.wrote_nothing

    def test_lost_race_returns_409(self, client):
        # Slug/episode writes are idempotent, so the retry after this is safe.
        with _Env(_sug(), mark_ok=False) as env:
            res = client.post(BASE + "/accept", json={"id": "sug-1"}, headers=_headers())
        assert res.status_code == 409 and res.get_json()["reason"] == "already_decided"

    def test_missing_not_pending_and_bad_body(self, client):
        with _Env(None) as env:
            assert client.post(BASE + "/accept", json={"id": "x"}, headers=_headers()).status_code == 404
        with _Env(_sug(status="denied")) as env:
            res = client.post(BASE + "/accept", json={"id": "sug-1"}, headers=_headers())
            assert res.status_code == 409 and env.wrote_nothing
        res = client.post(BASE + "/accept", json={}, headers=_headers())
        assert res.status_code == 400 and res.is_json


class TestDeny:
    def test_marks_denied_and_writes_nothing_else(self, client):
        with _Env(_sug()) as env:
            res = client.post(BASE + "/deny", json={"id": "sug-1"}, headers=_headers())
        assert res.status_code == 200 and res.get_json()["status"] == "denied"
        assert env.decided == [("sug-1", "denied")]
        assert env.set_slug == [] and env.upsert == []

    def test_lost_race_returns_409(self, client):
        with _Env(_sug(), mark_ok=False) as env:
            res = client.post(BASE + "/deny", json={"id": "sug-1"}, headers=_headers())
        assert res.status_code == 409 and res.get_json()["reason"] == "already_decided"
        assert env.set_slug == [] and env.upsert == []

    def test_404_and_409(self, client):
        with _Env(None) as env:
            assert client.post(BASE + "/deny", json={"id": "x"}, headers=_headers()).status_code == 404
        with _Env(_sug(status="accepted")) as env:
            assert client.post(BASE + "/deny", json={"id": "x"}, headers=_headers()).status_code == 409
            assert env.wrote_nothing
