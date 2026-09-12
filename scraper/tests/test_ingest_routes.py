"""Tests for scraper/routes/ingest_routes.py::backfill_episodes_from_metadata."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("INTERNAL_JWT_SECRET", "test-internal-secret-for-tests-only")
os.environ.setdefault("SERVICE_SECRET", "test-service-secret")

from unittest.mock import patch

from routes.ingest_routes import backfill_episodes_from_metadata


_SERIES_ROW = {"id": "s1", "kitsu_id": "kitsu-1", "mal_id": 21, "media_type": "tv"}
_KITSU_EPS = {1: {"title": "Pilot", "aired_at": "2020-01-01"}}
_JIKAN_TITLES = {1: {"title": "Pilot (Jikan)"}}


class TestBackfillEpisodesFromMetadata:
    def test_noop_when_episodes_already_exist(self):
        with patch("routes.ingest_routes.get_episode_count", return_value=5), \
             patch("routes.ingest_routes.get_series_by_id") as mock_get_series:
            result = backfill_episodes_from_metadata("s1")
        assert result == 0
        mock_get_series.assert_not_called()

    def test_noop_when_series_not_found(self):
        with patch("routes.ingest_routes.get_episode_count", return_value=0), \
             patch("routes.ingest_routes.get_series_by_id", return_value=None), \
             patch("routes.ingest_routes.upsert_episodes") as mock_upsert:
            result = backfill_episodes_from_metadata("missing")
        assert result == 0
        mock_upsert.assert_not_called()

    def test_creates_episodes_from_kitsu_and_jikan(self):
        with patch("routes.ingest_routes.get_episode_count", return_value=0), \
             patch("routes.ingest_routes.get_series_by_id", return_value=_SERIES_ROW), \
             patch("routes.ingest_routes.fetch_kitsu_episodes", return_value=_KITSU_EPS), \
             patch("routes.ingest_routes.fetch_jikan_episodes", return_value=_JIKAN_TITLES), \
             patch("routes.ingest_routes.upsert_episodes", return_value=1) as mock_upsert:
            result = backfill_episodes_from_metadata("s1")

        assert result == 1
        mock_upsert.assert_called_once()
        episodes = mock_upsert.call_args[0][0]
        assert episodes == [{
            "id": "s1-ep-1",
            "series_id": "s1",
            "episode_number": 1,
            "title": "Pilot (Jikan)",
            "description": None,
            "thumbnail_url": None,
            "aired_at": "2020-01-01",
            "duration_sec": None,
            "animeflv_slug": None,
        }]

    def test_skips_kitsu_jikan_fetch_when_ids_absent(self):
        row = {"id": "s1", "kitsu_id": None, "mal_id": None, "media_type": "tv"}
        with patch("routes.ingest_routes.get_episode_count", return_value=0), \
             patch("routes.ingest_routes.get_series_by_id", return_value=row), \
             patch("routes.ingest_routes.fetch_kitsu_episodes") as mock_kitsu, \
             patch("routes.ingest_routes.fetch_jikan_episodes") as mock_jikan:
            result = backfill_episodes_from_metadata("s1")

        assert result == 0
        mock_kitsu.assert_not_called()
        mock_jikan.assert_not_called()

    def test_returns_zero_when_metadata_builder_yields_no_episodes(self):
        """TV series with no Kitsu/Jikan episode data yet — nothing to create."""
        row = {"id": "s1", "kitsu_id": "k1", "mal_id": 21, "media_type": "tv"}
        with patch("routes.ingest_routes.get_episode_count", return_value=0), \
             patch("routes.ingest_routes.get_series_by_id", return_value=row), \
             patch("routes.ingest_routes.fetch_kitsu_episodes", return_value={}), \
             patch("routes.ingest_routes.fetch_jikan_episodes", return_value={}), \
             patch("routes.ingest_routes.upsert_episodes") as mock_upsert:
            result = backfill_episodes_from_metadata("s1")

        assert result == 0
        mock_upsert.assert_not_called()
