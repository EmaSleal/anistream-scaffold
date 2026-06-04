"""Flask test client integration tests for /api/series routes.

These tests mock the db layer so no real Supabase connection is needed.
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


def _token(role: str = "ADMIN", user_id: str = "admin-1") -> str:
    """Mint a short-lived HS256 JWT for test usage."""
    return pyjwt.encode(
        {"sub": user_id, "role": role, "exp": int(time.time()) + 60},
        TEST_SECRET,
        algorithm="HS256",
    )


def _auth_header(role: str = "ADMIN") -> dict:
    return {"Authorization": f"Bearer {_token(role=role)}"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _series_row(
    id="s1",
    title="Naruto",
    score=8.0,
    is_featured=False,
    franchise_id=None,
    media_type="tv",
    season_order=1,
):
    return {
        "id": id,
        "mal_id": 20,
        "title": title,
        "slug": id,
        "description": "A ninja story.",
        "thumbnail_url": "http://img.com/naruto.jpg",
        "banner_url": "",
        "rating": "14+",
        "genres": ["Action"],
        "audio_formats": ["sub"],
        "season_count": 1,
        "episode_count": 220,
        "year": 2002,
        "media_type": media_type,
        "is_simulcast": False,
        "is_featured": is_featured,
        "score": score,
        "franchise_id": franchise_id,
        "season_order": season_order,
        "franchise_relation": None,
        "animeflv_slug": "naruto",
        "animeav1_slug": None,
        "animeflv_disabled": False,
    }


def _episode_row(id="ep1", series_id="s1", episode_number=1):
    return {
        "id": id,
        "series_id": series_id,
        "episode_number": episode_number,
        "title": f"Episode {episode_number}",
        "animeflv_slug": f"naruto-{episode_number}",
        "thumbnail_url": None,
        "aired_at": None,
        "series": {"title": "Naruto"},
    }


@pytest.fixture
def client():
    """Return a Flask test client with storage mocked out."""
    with patch("storage.get_client"):
        from app import create_app
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c


# ---------------------------------------------------------------------------
# GET /api/series — list
# ---------------------------------------------------------------------------

class TestSeriesList:
    def test_default_list_returns_array(self, client):
        rows = [_series_row(id=f"s{i}", score=float(10 - i)) for i in range(5)]
        with patch("db.series.get_series_list", return_value=rows):
            res = client.get("/api/series")
        assert res.status_code == 200
        data = json.loads(res.data)
        assert isinstance(data, list)
        assert len(data) == 5

    def test_response_is_camel_case(self, client):
        with patch("db.series.get_series_list", return_value=[_series_row()]):
            res = client.get("/api/series")
        data = json.loads(res.data)
        assert "thumbnailUrl" in data[0]
        assert "thumbnail_url" not in data[0]

    def test_featured_filter(self, client):
        featured = [_series_row(id="f1", is_featured=True)]
        with patch("db.series.get_series_list", return_value=featured) as mock_fn:
            res = client.get("/api/series?featured=true")
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data[0]["isFeatured"] is True

    def test_consolidated_returns_one_per_franchise(self, client):
        rows = [
            _series_row(id="tv1", media_type="tv", franchise_id="fid", season_order=1),
            _series_row(id="ova1", media_type="ova", franchise_id="fid", season_order=2),
        ]
        with patch("db.series.get_series_list", return_value=rows):
            res = client.get("/api/series?consolidated=true")
        data = json.loads(res.data)
        assert len(data) == 1

    def test_default_limit_passed(self, client):
        with patch("db.series.get_series_list", return_value=[]) as mock_fn:
            client.get("/api/series")
        mock_fn.assert_called_once()
        kwargs = mock_fn.call_args
        assert kwargs[1].get("limit", kwargs[0][0] if kwargs[0] else 20) == 20

    def test_simulcast_filter_returns_only_simulcast_rows(self, client):
        simulcast_row = {**_series_row(id="sim1"), "is_simulcast": True}
        with patch("series_routes.db_series.get_series_list", return_value=[simulcast_row]) as mock_fn:
            res = client.get("/api/series?simulcast=true")
        assert res.status_code == 200
        data = json.loads(res.data)
        assert len(data) == 1
        assert data[0]["isSimulcast"] is True
        mock_fn.assert_called_once()
        assert mock_fn.call_args[1].get("simulcast") is True

    def test_no_simulcast_param_does_not_apply_filter(self, client):
        rows = [_series_row(id=f"s{i}") for i in range(3)]
        with patch("series_routes.db_series.get_series_list", return_value=rows) as mock_fn:
            res = client.get("/api/series")
        assert res.status_code == 200
        data = json.loads(res.data)
        assert len(data) == 3
        assert mock_fn.call_args[1].get("simulcast") is False


# ---------------------------------------------------------------------------
# GET /api/series/search
# ---------------------------------------------------------------------------

class TestSeriesSearch:
    def test_search_match_returns_results(self, client):
        rows = [{"id": "s1", "mal_id": 20, "title": "Naruto", "slug": "naruto"}]
        with patch("db.series.search_series", return_value=rows):
            res = client.get("/api/series/search?q=naruto")
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data[0]["title"] == "Naruto"
        assert "malId" in data[0]

    def test_search_empty_returns_empty_array(self, client):
        with patch("db.series.search_series", return_value=[]):
            res = client.get("/api/series/search?q=xyznotfound")
        assert res.status_code == 200
        assert json.loads(res.data) == []

    def test_search_missing_q_returns_400(self, client):
        res = client.get("/api/series/search")
        assert res.status_code == 400

    def test_search_projection_fields(self, client):
        rows = [{"id": "s1", "mal_id": 20, "title": "Naruto", "slug": "naruto"}]
        with patch("db.series.search_series", return_value=rows):
            res = client.get("/api/series/search?q=naruto")
        data = json.loads(res.data)
        keys = set(data[0].keys())
        assert keys == {"malId", "title", "slug"}


# ---------------------------------------------------------------------------
# GET /api/series/<id>
# ---------------------------------------------------------------------------

class TestSeriesDetail:
    def test_found_returns_200(self, client):
        with patch("db.series.get_series_by_id", return_value=_series_row()):
            res = client.get("/api/series/s1")
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data["id"] == "s1"

    def test_not_found_returns_404(self, client):
        with patch("db.series.get_series_by_id", return_value=None):
            res = client.get("/api/series/nonexistent")
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/series/<id>/episodes
# ---------------------------------------------------------------------------

class TestSeriesEpisodes:
    def test_episodes_returned_in_order(self, client):
        rows = [_episode_row(id=f"ep{i}", episode_number=i) for i in range(1, 5)]
        with patch("db.episodes.get_episodes_by_series", return_value=rows):
            res = client.get("/api/series/s1/episodes")
        assert res.status_code == 200
        data = json.loads(res.data)
        assert len(data) == 4
        episodes = [d["episode"] for d in data]
        assert episodes == sorted(episodes)


# ---------------------------------------------------------------------------
# GET /api/series/<id>/stream-config
# ---------------------------------------------------------------------------

class TestStreamConfig:
    def test_returns_config(self, client):
        config = {"animeflv_disabled": False, "animeav1_slug": "naruto-av1"}
        with patch("db.series.get_stream_config", return_value=config):
            res = client.get("/api/series/s1/stream-config")
        assert res.status_code == 200
        data = json.loads(res.data)
        assert "animeflvDisabled" in data
        assert "animeav1Slug" in data

    def test_not_found_returns_404(self, client):
        with patch("db.series.get_stream_config", return_value=None):
            res = client.get("/api/series/bad/stream-config")
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/series/<id>/stream-source
# ---------------------------------------------------------------------------

class TestPatchStreamSource:
    def test_valid_admin_token_and_body_returns_200(self, client):
        with patch("db.series.update_stream_source", return_value=True):
            res = client.patch(
                "/api/series/s1/stream-source",
                headers=_auth_header(role="ADMIN"),
                data=json.dumps({"animeav1_slug": "naruto-av1"}),
                content_type="application/json",
            )
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data["id"] == "s1"
        assert data["animeav1Slug"] == "naruto-av1"
        assert data["animeflv_disabled"] is True

    def test_missing_animeav1_slug_returns_400(self, client):
        res = client.patch(
            "/api/series/s1/stream-source",
            headers=_auth_header(role="ADMIN"),
            data=json.dumps({}),
            content_type="application/json",
        )
        assert res.status_code == 400

    def test_no_body_returns_400(self, client):
        res = client.patch(
            "/api/series/s1/stream-source",
            headers=_auth_header(role="ADMIN"),
        )
        assert res.status_code == 400

    def test_non_admin_role_returns_403(self, client):
        res = client.patch(
            "/api/series/s1/stream-source",
            headers=_auth_header(role="USER"),
            data=json.dumps({"animeav1_slug": "naruto-av1"}),
            content_type="application/json",
        )
        assert res.status_code == 403

    def test_no_token_returns_401(self, client):
        res = client.patch(
            "/api/series/s1/stream-source",
            data=json.dumps({"animeav1_slug": "naruto-av1"}),
            content_type="application/json",
        )
        assert res.status_code == 401

    def test_series_not_found_returns_404(self, client):
        with patch("db.series.update_stream_source", return_value=False):
            res = client.patch(
                "/api/series/nonexistent/stream-source",
                headers=_auth_header(role="ADMIN"),
                data=json.dumps({"animeav1_slug": "naruto-av1"}),
                content_type="application/json",
            )
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# Unit tests for db.series.update_stream_source
# ---------------------------------------------------------------------------

class TestRecommendationsEndpoint:
    """Integration tests for GET /api/series/recommendations."""

    def _rec_entry(self, mal_id: int) -> dict:
        """Build a Jikan recommendations data entry."""
        return {
            "entry": {
                "mal_id": mal_id,
                "title": f"Rec Anime {mal_id}",
                "images": {"jpg": {"image_url": f"http://img/{mal_id}.jpg"}},
            },
            "votes": 5,
        }

    def _series_row_with_mal(self, id="s1", mal_id=100, title="Naruto", score=8.0):
        return {
            "id": id,
            "mal_id": mal_id,
            "title": title,
            "slug": id,
            "description": "desc",
            "thumbnail_url": "http://img.com/x.jpg",
            "banner_url": "",
            "rating": "14+",
            "genres": ["Action"],
            "audio_formats": ["sub"],
            "season_count": 1,
            "episode_count": 12,
            "year": 2020,
            "media_type": "tv",
            "is_simulcast": False,
            "is_featured": False,
            "score": score,
            "franchise_id": None,
            "season_order": 1,
            "franchise_relation": None,
            "animeflv_slug": "naruto",
            "animeav1_slug": None,
            "animeflv_disabled": False,
        }

    def test_unauthenticated_returns_401(self, client):
        res = client.get("/api/series/recommendations")
        assert res.status_code == 401

    def test_returns_fallback_for_user_with_empty_history(self, client):
        top_rows = [self._series_row_with_mal(id=f"s{i}", mal_id=i, score=float(10-i)) for i in range(1, 4)]
        with (
            patch("series_routes.db_progress.get_recent_progress", return_value=[]),
            patch("series_routes.db_series.get_series_list", return_value=top_rows),
        ):
            res = client.get("/api/series/recommendations", headers=_auth_header())
        assert res.status_code == 200
        data = json.loads(res.data)
        assert isinstance(data, list)
        assert len(data) == 3

    def test_returns_deduped_and_watched_filtered_results(self, client):
        """User has history, recommendations are fetched, watched ones are removed."""
        progress_rows = [
            {"series_id": "s1", "progress_sec": 100, "updated_at": "2026-01-01T00:00:00Z"},
        ]
        # s1 has mal_id=10; the seed gives back recommendations for mal_id 20, 30
        # mal_id 10 is already watched and should be excluded
        rec_entries = [self._rec_entry(20), self._rec_entry(30), self._rec_entry(10)]
        matched_rows = [self._series_row_with_mal(id="s20", mal_id=20, title="Anime 20")]

        with (
            patch("series_routes.db_progress.get_recent_progress", side_effect=[
                progress_rows,   # first call: limit=5 seeds
                progress_rows,   # second call: limit=500 watched set
            ]),
            patch("series_routes.db_progress.get_mal_ids_for_series", side_effect=[
                {"s1": 10},       # seed mal_ids
                {"s1": 10},       # watched mal_ids
            ]),
            patch("series_routes.fetch_recommendations", return_value=rec_entries),
            patch("series_routes.db_series.get_series_by_mal_ids", return_value=matched_rows),
            patch("series_routes.db_series.upsert_series_stub"),
            patch("threading.Thread") as mock_thread,
        ):
            res = client.get("/api/series/recommendations", headers=_auth_header())

        assert res.status_code == 200
        data = json.loads(res.data)
        assert isinstance(data, list)
        # mal_id=10 (already watched) must be excluded
        mal_ids_in_response = [item.get("malId") for item in data]
        assert 10 not in mal_ids_in_response

    def test_returns_fallback_when_seeds_have_no_mal_ids(self, client):
        """Seeds exist but none have mal_id — fallback to top-scored."""
        progress_rows = [
            {"series_id": "s-no-mal", "progress_sec": 100, "updated_at": "2026-01-01T00:00:00Z"},
        ]
        top_rows = [self._series_row_with_mal(id="top1", mal_id=99)]
        with (
            patch("series_routes.db_progress.get_recent_progress", return_value=progress_rows),
            patch("series_routes.db_progress.get_mal_ids_for_series", return_value={}),
            patch("series_routes.db_series.get_series_list", return_value=top_rows),
        ):
            res = client.get("/api/series/recommendations", headers=_auth_header())
        assert res.status_code == 200
        data = json.loads(res.data)
        assert len(data) == 1

    def test_skips_failed_jikan_seed_fail_open(self, client):
        """If fetch_recommendations returns [] for a seed, continue without error."""
        progress_rows = [
            {"series_id": "s1", "progress_sec": 100, "updated_at": "2026-01-01T00:00:00Z"},
        ]
        with (
            patch("series_routes.db_progress.get_recent_progress", side_effect=[
                progress_rows,
                progress_rows,
            ]),
            patch("series_routes.db_progress.get_mal_ids_for_series", side_effect=[
                {"s1": 10},
                {"s1": 10},
            ]),
            patch("series_routes.fetch_recommendations", return_value=[]),
            patch("series_routes.db_series.get_series_list", return_value=[self._series_row_with_mal()]) as mock_fallback,
        ):
            res = client.get("/api/series/recommendations", headers=_auth_header())
        assert res.status_code == 200

    def test_spawns_daemon_thread_for_unmatched_candidates(self, client):
        """Unmatched candidates trigger daemon thread spawn; response is not blocked."""
        progress_rows = [
            {"series_id": "s1", "progress_sec": 100, "updated_at": "2026-01-01T00:00:00Z"},
        ]
        rec_entries = [self._rec_entry(200)]  # mal_id=200, not in DB
        with (
            patch("series_routes.db_progress.get_recent_progress", side_effect=[
                progress_rows,
                progress_rows,
            ]),
            patch("series_routes.db_progress.get_mal_ids_for_series", side_effect=[
                {"s1": 10},
                {"s1": 10},
            ]),
            patch("series_routes.fetch_recommendations", return_value=rec_entries),
            patch("series_routes.db_series.get_series_by_mal_ids", return_value=[]),
            patch("series_routes.threading") as mock_threading,
        ):
            mock_thread_instance = MagicMock()
            mock_threading.Thread.return_value = mock_thread_instance

            res = client.get("/api/series/recommendations", headers=_auth_header())

        assert res.status_code == 200
        # Thread must have been created with daemon=True and started
        mock_threading.Thread.assert_called_once_with(
            target=mock_threading.Thread.call_args[1]["target"],
            args=(200,),
            daemon=True,
        )
        mock_thread_instance.start.assert_called_once()


class TestUpdateStreamSource:
    def test_updates_correct_fields_and_returns_true(self):
        """update_stream_source calls UPDATE with animeav1_slug + animeflv_disabled=True."""
        mock_result = MagicMock()
        mock_result.data = [{"id": "s1"}]

        mock_table = MagicMock()
        mock_table.update.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = mock_result

        mock_client = MagicMock()
        mock_client.table.return_value = mock_table

        with patch("storage.get_client", return_value=mock_client):
            import importlib
            import db.series as db_series_mod
            result = db_series_mod.update_stream_source("s1", "naruto-av1")

        assert result is True
        mock_table.update.assert_called_once_with(
            {"animeav1_slug": "naruto-av1", "animeflv_disabled": True}
        )
        mock_table.eq.assert_called_once_with("id", "s1")

    def test_returns_false_when_no_row_matched(self):
        """update_stream_source returns False when Supabase returns no data."""
        mock_result = MagicMock()
        mock_result.data = []

        mock_table = MagicMock()
        mock_table.update.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = mock_result

        mock_client = MagicMock()
        mock_client.table.return_value = mock_table

        with patch("storage.get_client", return_value=mock_client):
            import db.series as db_series_mod
            result = db_series_mod.update_stream_source("nonexistent", "some-slug")

        assert result is False
