"""Flask test client integration tests for /api/episodes routes."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import pytest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _episode_row(
    id="ep1",
    series_id="s1",
    episode_number=1,
    animeflv_slug="naruto-1",
):
    return {
        "id": id,
        "series_id": series_id,
        "episode_number": episode_number,
        "title": f"Episode {episode_number}",
        "animeflv_slug": animeflv_slug,
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
# GET /api/episodes/watch/<id>
# ---------------------------------------------------------------------------

class TestWatchEpisode:
    def test_resolve_by_slug_200(self, client):
        row = _episode_row(animeflv_slug="naruto-1")
        with patch("db.episodes.get_episode_for_watch", return_value=row):
            res = client.get("/api/episodes/watch/naruto-1")
        assert res.status_code == 200
        data = json.loads(res.data)
        assert "episode" in data
        assert "animeflvSlug" in data
        assert data["animeflvSlug"] == "naruto-1"

    def test_resolve_by_uuid_fallback_200(self, client):
        row = _episode_row(id="uuid-abc", animeflv_slug="naruto-1")
        with patch("db.episodes.get_episode_for_watch", return_value=row):
            res = client.get("/api/episodes/watch/uuid-abc")
        assert res.status_code == 200

    def test_no_match_returns_404(self, client):
        with patch("db.episodes.get_episode_for_watch", return_value=None):
            res = client.get("/api/episodes/watch/nonexistent")
        assert res.status_code == 404

    def test_episode_shape_is_camel_case(self, client):
        row = _episode_row()
        with patch("db.episodes.get_episode_for_watch", return_value=row):
            res = client.get("/api/episodes/watch/ep1")
        data = json.loads(res.data)
        ep = data["episode"]
        assert "seriesId" in ep
        assert "series_id" not in ep


# ---------------------------------------------------------------------------
# GET /api/episodes/<series_id>/adjacent
# ---------------------------------------------------------------------------

class TestAdjacentEpisodes:
    def test_adjacent_happy_path(self, client):
        prev_row = _episode_row(id="ep0", episode_number=0)
        next_row = _episode_row(id="ep2", episode_number=2)
        with patch("db.episodes.get_adjacent_episodes", return_value={"prev": prev_row, "next": next_row}):
            res = client.get("/api/episodes/s1/adjacent?episode_number=1")
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data["prev"] is not None
        assert data["next"] is not None
        assert data["prev"]["episode"] == 0
        assert data["next"]["episode"] == 2

    def test_adjacent_missing_episode_number_returns_400(self, client):
        res = client.get("/api/episodes/s1/adjacent")
        assert res.status_code == 400

    def test_adjacent_invalid_episode_number_returns_400(self, client):
        res = client.get("/api/episodes/s1/adjacent?episode_number=abc")
        assert res.status_code == 400

    def test_adjacent_at_boundary_returns_null(self, client):
        with patch("db.episodes.get_adjacent_episodes", return_value={"prev": None, "next": None}):
            res = client.get("/api/episodes/s1/adjacent?episode_number=999")
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data["prev"] is None
        assert data["next"] is None
