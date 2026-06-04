"""Unit tests for recommendation-related DB helpers.

Covers:
- db.progress.get_mal_ids_for_series
- db.series.upsert_series_stub
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("INTERNAL_JWT_SECRET", "test-internal-secret-for-tests-only")
os.environ.setdefault("SERVICE_SECRET", "test-service-secret-for-tests-only")

import pytest
from unittest.mock import patch, MagicMock, call


# ---------------------------------------------------------------------------
# T6b — get_mal_ids_for_series
# ---------------------------------------------------------------------------

class TestGetMalIdsForSeries:
    def _make_mock_client(self, rows: list[dict]) -> MagicMock:
        """Build a mock Supabase client that returns ``rows`` from execute()."""
        mock_result = MagicMock()
        mock_result.data = rows

        mock_table = MagicMock()
        # All chained filter calls return the same mock_table so chaining works
        mock_table.select.return_value = mock_table
        mock_table.in_.return_value = mock_table
        mock_table.not_ = MagicMock()
        mock_table.not_.is_.return_value = mock_table
        mock_table.execute.return_value = mock_result

        mock_client = MagicMock()
        mock_client.table.return_value = mock_table
        return mock_client

    def test_returns_empty_dict_for_empty_input(self):
        import db.progress as db_progress
        result = db_progress.get_mal_ids_for_series([])
        assert result == {}

    def test_returns_correct_mapping(self):
        import db.progress as db_progress
        rows = [{"id": "s1", "mal_id": 20}, {"id": "s2", "mal_id": 21}]
        mock_client = self._make_mock_client(rows)
        with patch("storage.get_client", return_value=mock_client):
            result = db_progress.get_mal_ids_for_series(["s1", "s2"])
        assert result == {"s1": 20, "s2": 21}

    def test_skips_series_with_null_mal_id(self):
        """Rows with null mal_id are excluded by the NOT IS NULL query filter."""
        import db.progress as db_progress
        # The DB filter already excludes NULLs; simulate by returning only non-null rows
        rows = [{"id": "s1", "mal_id": 20}]
        mock_client = self._make_mock_client(rows)
        with patch("storage.get_client", return_value=mock_client):
            result = db_progress.get_mal_ids_for_series(["s1", "s2"])
        assert "s2" not in result
        assert result == {"s1": 20}

    def test_returns_empty_dict_when_no_rows_returned(self):
        import db.progress as db_progress
        mock_client = self._make_mock_client([])
        with patch("storage.get_client", return_value=mock_client):
            result = db_progress.get_mal_ids_for_series(["s1"])
        assert result == {}

    def test_queries_series_table_with_correct_ids(self):
        import db.progress as db_progress
        mock_client = self._make_mock_client([])
        with patch("storage.get_client", return_value=mock_client):
            db_progress.get_mal_ids_for_series(["s1", "s2", "s3"])
        mock_client.table.assert_called_with("series")
        mock_client.table().select.assert_called_with("id, mal_id")


# ---------------------------------------------------------------------------
# T6c — upsert_series_stub
# ---------------------------------------------------------------------------

class TestUpsertSeriesStub:
    def _normalized_entry(self, mal_id: int = 42) -> dict:
        return {
            "id": "test-anime",
            "mal_id": mal_id,
            "title": "Test Anime",
            "slug": "test-anime",
            "description": "",
            "thumbnail_url": "",
            "banner_url": "",
            "rating": "14+",
            "genres": [],
            "audio_formats": ["sub"],
            "season_count": 1,
            "episode_count": 0,
            "year": 2024,
            "media_type": "tv",
            "is_simulcast": False,
            "is_featured": False,
            "score": None,
            "titles": [],
            "broadcast_day": None,
            "broadcast_time": None,
            "broadcast_timezone": None,
            "aired_from": None,
            "kitsu_id": None,
            "kitsu_status": None,
            # Note: animeflv_slug is NOT in normalize() output — it stays NULL in DB
        }

    def test_calls_upsert_many_with_single_element_list(self):
        import db.series as db_series_mod
        entry = self._normalized_entry()
        with (
            patch("fetcher.fetch_anime_by_id", return_value={"mal_id": 42}),
            patch("normalizer.normalize", return_value=entry),
            patch("storage.upsert_many") as mock_upsert,
        ):
            db_series_mod.upsert_series_stub(42)
            mock_upsert.assert_called_once()
            args = mock_upsert.call_args[0][0]
            assert isinstance(args, list)
            assert len(args) == 1

    def test_entry_has_no_animeflv_slug(self):
        """normalize() does not produce animeflv_slug — the DB column stays NULL."""
        import db.series as db_series_mod
        entry = self._normalized_entry()
        assert "animeflv_slug" not in entry

        with (
            patch("fetcher.fetch_anime_by_id", return_value={"mal_id": 42}),
            patch("normalizer.normalize", return_value=entry),
            patch("storage.upsert_many") as mock_upsert,
        ):
            db_series_mod.upsert_series_stub(42)
            called_entry = mock_upsert.call_args[0][0][0]
            assert "animeflv_slug" not in called_entry

    def test_does_not_raise_when_fetch_fails(self):
        """upsert_series_stub is fail-open — exceptions must NOT propagate."""
        import db.series as db_series_mod
        with patch("fetcher.fetch_anime_by_id", side_effect=Exception("network error")):
            # Should not raise
            db_series_mod.upsert_series_stub(99)

    def test_does_not_raise_when_normalize_returns_none(self):
        """When normalize() returns None, upsert_many must NOT be called."""
        import db.series as db_series_mod
        with (
            patch("fetcher.fetch_anime_by_id", return_value={}),
            patch("normalizer.normalize", return_value=None),
            patch("storage.upsert_many") as mock_upsert,
        ):
            db_series_mod.upsert_series_stub(42)
            mock_upsert.assert_not_called()

    def test_does_not_raise_when_upsert_fails(self):
        """Even if upsert_many throws, the function must swallow the exception."""
        import db.series as db_series_mod
        entry = self._normalized_entry()
        with (
            patch("fetcher.fetch_anime_by_id", return_value={"mal_id": 42}),
            patch("normalizer.normalize", return_value=entry),
            patch("storage.upsert_many", side_effect=RuntimeError("db down")),
        ):
            db_series_mod.upsert_series_stub(42)  # must not raise
