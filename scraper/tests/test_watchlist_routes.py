"""Integration tests for watchlist routes via Flask test client.

The DB layer is mocked so no real Supabase connection is needed.
Auth decorators are bypassed by patching auth._INTERNAL_JWT_SECRET and
minting valid test tokens with PyJWT.
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
from unittest.mock import patch, MagicMock

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


def _series_row(id: str = "s1", title: str = "Naruto") -> dict:
    return {
        "id": id,
        "mal_id": 20,
        "title": title,
        "slug": id,
        "description": "",
        "thumbnail_url": "http://img.com/thumb.jpg",
        "banner_url": "",
        "rating": "14+",
        "genres": ["Action"],
        "audio_formats": ["sub"],
        "season_count": 1,
        "episode_count": 10,
        "year": 2002,
        "media_type": "tv",
        "is_simulcast": False,
        "is_featured": False,
        "score": 8.0,
        "franchise_id": None,
        "season_order": 1,
        "franchise_relation": None,
        "animeflv_slug": id,
        "fallback_slug": None,
        "animeflv_disabled": False,
    }


@pytest.fixture
def client():
    """Flask test client with storage mocked."""
    with patch("storage.get_client"):
        from app import create_app
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c


# ---------------------------------------------------------------------------
# GET /api/watchlist
# ---------------------------------------------------------------------------

class TestGetWatchlist:
    def test_empty_watchlist_returns_200_empty_array(self, client):
        with patch("db.watchlist.get_watchlist", return_value=[]):
            res = client.get("/api/watchlist", headers=_auth_header())
        assert res.status_code == 200
        assert json.loads(res.data) == []

    def test_watchlist_returns_series_objects(self, client):
        rows = [_series_row("s1", "Naruto"), _series_row("s2", "Bleach")]
        with patch("db.watchlist.get_watchlist", return_value=rows):
            res = client.get("/api/watchlist", headers=_auth_header())
        data = json.loads(res.data)
        assert res.status_code == 200
        assert len(data) == 2
        assert data[0]["id"] == "s1"
        # Response is camelCase-mapped
        assert "thumbnailUrl" in data[0]

    def test_unauthenticated_returns_401(self, client):
        res = client.get("/api/watchlist")
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/watchlist
# ---------------------------------------------------------------------------

class TestAddToWatchlist:
    def test_add_series_returns_201(self, client):
        with patch("db.watchlist.add_to_watchlist") as mock_add:
            res = client.post(
                "/api/watchlist",
                headers=_auth_header(),
                data=json.dumps({"series_id": "s1"}),
                content_type="application/json",
            )
        assert res.status_code == 201
        mock_add.assert_called_once_with("u-1", "s1")

    def test_add_again_idempotent_returns_201(self, client):
        # add_to_watchlist is an upsert — calling twice should not raise
        with patch("db.watchlist.add_to_watchlist"):
            res1 = client.post(
                "/api/watchlist",
                headers=_auth_header(),
                data=json.dumps({"series_id": "s1"}),
                content_type="application/json",
            )
            res2 = client.post(
                "/api/watchlist",
                headers=_auth_header(),
                data=json.dumps({"series_id": "s1"}),
                content_type="application/json",
            )
        assert res1.status_code == 201
        assert res2.status_code == 201

    def test_missing_series_id_returns_400(self, client):
        res = client.post(
            "/api/watchlist",
            headers=_auth_header(),
            data=json.dumps({}),
            content_type="application/json",
        )
        assert res.status_code == 400

    def test_unauthenticated_returns_401(self, client):
        res = client.post(
            "/api/watchlist",
            data=json.dumps({"series_id": "s1"}),
            content_type="application/json",
        )
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/watchlist/<series_id>
# ---------------------------------------------------------------------------

class TestRemoveFromWatchlist:
    def test_delete_existing_returns_204(self, client):
        with patch("db.watchlist.remove_from_watchlist") as mock_del:
            res = client.delete("/api/watchlist/s1", headers=_auth_header())
        assert res.status_code == 204
        mock_del.assert_called_once_with("u-1", "s1")

    def test_delete_absent_returns_204_idempotent(self, client):
        # remove_from_watchlist never raises — DELETE is always 204
        with patch("db.watchlist.remove_from_watchlist"):
            res = client.delete("/api/watchlist/nonexistent", headers=_auth_header())
        assert res.status_code == 204

    def test_unauthenticated_returns_401(self, client):
        res = client.delete("/api/watchlist/s1")
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# Full round-trip smoke test
# ---------------------------------------------------------------------------

class TestWatchlistRoundTrip:
    def test_add_then_get_then_delete(self, client):
        series = [_series_row("s1")]

        with patch("db.watchlist.add_to_watchlist"):
            res = client.post(
                "/api/watchlist",
                headers=_auth_header(),
                data=json.dumps({"series_id": "s1"}),
                content_type="application/json",
            )
        assert res.status_code == 201

        with patch("db.watchlist.get_watchlist", return_value=series):
            res = client.get("/api/watchlist", headers=_auth_header())
        data = json.loads(res.data)
        assert len(data) == 1

        with patch("db.watchlist.remove_from_watchlist"):
            res = client.delete("/api/watchlist/s1", headers=_auth_header())
        assert res.status_code == 204
