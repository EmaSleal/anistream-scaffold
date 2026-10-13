"""Unit tests for scraper/db/simulcast.py — Phase 2 (simulcast gap recovery).

Covers:
  2.1/2.2  get_slug_sibling_episodes()
  2.3/2.4  parity with routes.ingest_routes._claimed_episode_offset
  2.5/2.6  mark_gap_unresolved() / get_expired_gap_candidates()
  2.7/2.8  grace-aware get_due_simulcast_series()

All Supabase access is mocked. SIMULCAST_GRACE_ENABLED / SIMULCAST_BACKFILL_MODE
default OFF — the "flag off" tests pin today's exact behavior.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("INTERNAL_JWT_SECRET", "test-internal-secret-for-tests-only")
os.environ.setdefault("SERVICE_SECRET", "test-service-secret")

from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _chain_mock(data):
    """Return a MagicMock chain where every chained call returns itself and
    .execute() returns a result object with .data = data."""
    chain = MagicMock()
    for method in (
        "select", "eq", "not_", "is_", "in_", "order", "limit",
    ):
        getattr(chain, method).return_value = chain
    chain.not_.is_.return_value = chain
    result = MagicMock()
    result.data = data
    chain.execute.return_value = result
    return chain


# ---------------------------------------------------------------------------
# 2.1/2.2 — get_slug_sibling_episodes()
# ---------------------------------------------------------------------------


class TestGetSlugSiblingEpisodes:
    def test_no_franchise_id_returns_zero_offset_empty_nums(self):
        """franchise_id=None → short-circuit, no DB call needed."""
        from db.simulcast import get_slug_sibling_episodes

        with patch("db.simulcast.get_series_by_franchise") as mock_siblings:
            result = get_slug_sibling_episodes(None, "some-slug", "series-a")

        mock_siblings.assert_not_called()
        assert result == {"offset": 0, "sibling_nums": set()}

    def test_sibling_sharing_slug_returns_offset_and_numbers(self):
        """A franchise sibling sharing principal_slug contributes its own
        ingested episode numbers to sibling_nums and its count to offset."""
        from db.simulcast import get_slug_sibling_episodes

        siblings = [
            {"id": "series-a-part1", "principal_slug": "shared-slug", "fallback_slug": None},
            {"id": "series-a-part2", "principal_slug": "other-slug", "fallback_slug": None},
        ]
        ep_rows = [
            {"series_id": "series-a-part1", "episode_number": 1},
            {"series_id": "series-a-part1", "episode_number": 2},
            {"series_id": "series-a-part1", "episode_number": 3},
        ]
        mock_client = MagicMock()
        mock_client.table.return_value = _chain_mock(ep_rows)

        with patch("db.simulcast.get_series_by_franchise", return_value=siblings), \
             patch("storage.get_client", return_value=mock_client):
            result = get_slug_sibling_episodes("fr-1", "shared-slug", "series-a-part2")

        assert result["offset"] == 3
        assert result["sibling_nums"] == {1, 2, 3}

    def test_exclude_id_is_never_counted_as_its_own_sibling(self):
        """The series being evaluated itself must never count toward its own offset."""
        from db.simulcast import get_slug_sibling_episodes

        siblings = [
            {"id": "series-a", "principal_slug": "shared-slug", "fallback_slug": None},
        ]
        mock_client = MagicMock()
        mock_client.table.return_value = _chain_mock([])

        with patch("db.simulcast.get_series_by_franchise", return_value=siblings), \
             patch("storage.get_client", return_value=mock_client):
            result = get_slug_sibling_episodes("fr-1", "shared-slug", "series-a")

        assert result == {"offset": 0, "sibling_nums": set()}

    def test_fallback_slug_match_also_counts(self):
        """A sibling matching via fallback_slug (jkanime) also contributes."""
        from db.simulcast import get_slug_sibling_episodes

        siblings = [
            {"id": "series-b", "principal_slug": None, "fallback_slug": "jk-slug"},
        ]
        ep_rows = [{"series_id": "series-b", "episode_number": 1}]
        mock_client = MagicMock()
        mock_client.table.return_value = _chain_mock(ep_rows)

        with patch("db.simulcast.get_series_by_franchise", return_value=siblings), \
             patch("storage.get_client", return_value=mock_client):
            result = get_slug_sibling_episodes("fr-1", "jk-slug", "series-c")

        assert result["offset"] == 1
        assert result["sibling_nums"] == {1}

    def test_no_matching_sibling_returns_zero(self):
        """No sibling shares this slug → zero offset, empty sibling_nums, no episodes query."""
        from db.simulcast import get_slug_sibling_episodes

        siblings = [
            {"id": "series-b", "principal_slug": "unrelated-slug", "fallback_slug": None},
        ]
        mock_client = MagicMock()

        with patch("db.simulcast.get_series_by_franchise", return_value=siblings), \
             patch("storage.get_client", return_value=mock_client):
            result = get_slug_sibling_episodes("fr-1", "shared-slug", "series-a")

        assert result == {"offset": 0, "sibling_nums": set()}
        mock_client.table.assert_not_called()


# ---------------------------------------------------------------------------
# 2.3/2.4 — parity with routes.ingest_routes._claimed_episode_offset
# ---------------------------------------------------------------------------


class TestOffsetParityWithIngestRoutes:
    """Guards against drift between get_slug_sibling_episodes's offset and
    _claimed_episode_offset — both must select the exact same sibling set
    and sum the exact same episode counts, even though the two live in
    different modules (db layer vs. route layer) by design."""

    def test_offset_matches_claimed_episode_offset_single_sibling(self):
        from db.simulcast import get_slug_sibling_episodes
        from routes.ingest_routes import _claimed_episode_offset

        siblings = [
            {"id": "part1", "principal_slug": "shared", "fallback_slug": None},
            {"id": "part2", "principal_slug": "shared", "fallback_slug": None},
        ]
        ep_rows = [
            {"series_id": "part1", "episode_number": n} for n in range(1, 13)
        ]
        mock_client = MagicMock()
        mock_client.table.return_value = _chain_mock(ep_rows)

        with patch("db.simulcast.get_series_by_franchise", return_value=siblings), \
             patch("routes.ingest_routes.get_series_by_franchise", return_value=siblings), \
             patch("routes.ingest_routes.get_episode_count", return_value=12), \
             patch("storage.get_client", return_value=mock_client):
            db_offset = get_slug_sibling_episodes("fr-1", "shared", "part2")["offset"]
            legacy_offset = _claimed_episode_offset("fr-1", "shared", "part2")

        assert db_offset == legacy_offset == 12

    def test_offset_matches_claimed_episode_offset_no_sibling(self):
        from db.simulcast import get_slug_sibling_episodes
        from routes.ingest_routes import _claimed_episode_offset

        siblings = [
            {"id": "solo", "principal_slug": "own-slug", "fallback_slug": None},
        ]
        mock_client = MagicMock()
        mock_client.table.return_value = _chain_mock([])

        with patch("db.simulcast.get_series_by_franchise", return_value=siblings), \
             patch("routes.ingest_routes.get_series_by_franchise", return_value=siblings), \
             patch("storage.get_client", return_value=mock_client):
            db_offset = get_slug_sibling_episodes("fr-1", "own-slug", "solo")["offset"]
            legacy_offset = _claimed_episode_offset("fr-1", "own-slug", "solo")

        assert db_offset == legacy_offset == 0


# ---------------------------------------------------------------------------
# 2.5/2.6 — mark_gap_unresolved() / get_expired_gap_candidates()
# ---------------------------------------------------------------------------


class TestMarkGapUnresolved:
    def test_sets_gap_unresolved_at_and_missing_episodes(self):
        from db.simulcast import mark_gap_unresolved

        mock_update = MagicMock()
        mock_eq = MagicMock()
        mock_eq.execute.return_value = MagicMock()
        mock_update.eq.return_value = mock_eq
        mock_table = MagicMock()
        mock_table.update.return_value = mock_update
        mock_client = MagicMock()
        mock_client.table.return_value = mock_table

        with patch("storage.get_client", return_value=mock_client):
            mark_gap_unresolved("series-x", [3, 1, 2])

        mock_table.update.assert_called_once()
        payload = mock_table.update.call_args.args[0]
        assert payload["gap_missing_episodes"] == [1, 2, 3]
        assert "gap_unresolved_at" in payload
        mock_update.eq.assert_called_once_with("id", "series-x")


class TestGetExpiredGapCandidates:
    def _mock_client(self, series_rows, episode_rows):
        series_chain = _chain_mock(series_rows)
        eps_chain = _chain_mock(episode_rows)
        mock_client = MagicMock()
        mock_client.table.side_effect = lambda t: series_chain if t == "series" else eps_chain
        return mock_client

    def test_expired_series_with_gap_is_returned(self):
        from db.simulcast import get_expired_gap_candidates

        ended_15_days_ago = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()
        series_rows = [
            {
                "id": "s1",
                "is_simulcast": False,
                "simulcast_ended_at": ended_15_days_ago,
                "episode_count": 12,
            }
        ]
        episode_rows = [
            {"series_id": "s1", "episode_number": n} for n in range(1, 11)
        ]
        mock_client = self._mock_client(series_rows, episode_rows)

        with patch("storage.get_client", return_value=mock_client):
            result = get_expired_gap_candidates()

        assert len(result) == 1
        assert result[0]["id"] == "s1"
        assert result[0]["have"] == 10
        assert result[0]["expected"] == 12
        assert result[0]["own_episode_numbers"] == set(range(1, 11))

    def test_matching_counts_not_expired_excluded(self):
        """have == expected → classify_recheck returns None → excluded."""
        from db.simulcast import get_expired_gap_candidates

        ended_15_days_ago = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()
        series_rows = [
            {
                "id": "s1",
                "is_simulcast": False,
                "simulcast_ended_at": ended_15_days_ago,
                "episode_count": 10,
            }
        ]
        episode_rows = [{"series_id": "s1", "episode_number": n} for n in range(1, 11)]
        mock_client = self._mock_client(series_rows, episode_rows)

        with patch("storage.get_client", return_value=mock_client):
            result = get_expired_gap_candidates()

        assert result == []

    def test_still_within_grace_excluded(self):
        """Finished 5 days ago (within 14d grace) → classify_recheck returns "grace", not "expired"."""
        from db.simulcast import get_expired_gap_candidates

        ended_5_days_ago = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        series_rows = [
            {
                "id": "s1",
                "is_simulcast": False,
                "simulcast_ended_at": ended_5_days_ago,
                "episode_count": 12,
            }
        ]
        episode_rows = [{"series_id": "s1", "episode_number": n} for n in range(1, 11)]
        mock_client = self._mock_client(series_rows, episode_rows)

        with patch("storage.get_client", return_value=mock_client):
            result = get_expired_gap_candidates()

        assert result == []

    def test_no_candidate_rows_returns_empty_list_no_episodes_query(self):
        from db.simulcast import get_expired_gap_candidates

        series_chain = _chain_mock([])
        mock_client = MagicMock()
        mock_client.table.return_value = series_chain

        with patch("storage.get_client", return_value=mock_client):
            result = get_expired_gap_candidates()

        assert result == []


# ---------------------------------------------------------------------------
# 2.7/2.8 — grace-aware get_due_simulcast_series()
# ---------------------------------------------------------------------------


class TestGraceAwareGetDueSimulcastSeries:
    def _mock_client(self, series_rows, episode_rows=None):
        episode_rows = episode_rows or []
        series_chain = _chain_mock(series_rows)
        eps_chain = _chain_mock(episode_rows)
        mock_client = MagicMock()
        mock_client.table.side_effect = lambda t: series_chain if t == "series" else eps_chain
        return mock_client

    def test_flag_off_behavior_unchanged_airing_only(self):
        """No env var set → identical to pre-existing behavior: only
        is_simulcast=True rows, no mode/have/expected/franchise_id keys."""
        from db.simulcast import get_due_simulcast_series

        row = {
            "id": "s1",
            "principal_slug": "slug1",
            "mal_id": 42,
            "kitsu_id": None,
            "last_simulcast_check": None,
        }
        mock_client = self._mock_client([row], [])

        with patch("storage.get_client", return_value=mock_client), \
             patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SIMULCAST_GRACE_ENABLED", None)
            result = get_due_simulcast_series()

        assert len(result) == 1
        item = result[0]
        assert set(item.keys()) == {"id", "principal_slug", "mal_id", "kitsu_id", "max_episode_number"}

    def test_flag_on_includes_grace_eligible_row(self):
        """SIMULCAST_GRACE_ENABLED=1 → a finished series with a real gap
        within the 14-day window is included alongside airing rows."""
        from db.simulcast import get_due_simulcast_series

        ended_5_days_ago = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        airing_row = {
            "id": "s-airing",
            "principal_slug": "slug-airing",
            "mal_id": 1,
            "kitsu_id": None,
            "last_simulcast_check": None,
            "is_simulcast": True,
            "simulcast_ended_at": None,
            "episode_count": 24,
            "franchise_id": None,
        }
        grace_row = {
            "id": "s-grace",
            "principal_slug": "slug-grace",
            "mal_id": 2,
            "kitsu_id": None,
            "last_simulcast_check": None,
            "is_simulcast": False,
            "simulcast_ended_at": ended_5_days_ago,
            "episode_count": 12,
            "franchise_id": "fr-1",
        }
        episode_rows = [
            {"series_id": "s-grace", "episode_number": n} for n in range(1, 11)
        ]
        mock_client = self._mock_client([airing_row, grace_row], episode_rows)

        with patch("storage.get_client", return_value=mock_client), \
             patch.dict(os.environ, {"SIMULCAST_GRACE_ENABLED": "1"}, clear=False):
            result = get_due_simulcast_series()

        ids = {r["id"] for r in result}
        assert ids == {"s-airing", "s-grace"}
        grace_item = next(r for r in result if r["id"] == "s-grace")
        assert grace_item["mode"] == "grace"
        assert grace_item["have"] == 10
        assert grace_item["expected"] == 12
        assert grace_item["franchise_id"] == "fr-1"
        airing_item = next(r for r in result if r["id"] == "s-airing")
        assert airing_item["mode"] == "airing"

    def test_flag_on_excludes_expired_row(self):
        """SIMULCAST_GRACE_ENABLED=1 → a series past the 14-day grace window
        with a real gap is NOT included (classify_recheck returns "expired")."""
        from db.simulcast import get_due_simulcast_series

        ended_20_days_ago = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
        expired_row = {
            "id": "s-expired",
            "principal_slug": "slug-expired",
            "mal_id": 3,
            "kitsu_id": None,
            "last_simulcast_check": None,
            "is_simulcast": False,
            "simulcast_ended_at": ended_20_days_ago,
            "episode_count": 12,
            "franchise_id": None,
        }
        episode_rows = [{"series_id": "s-expired", "episode_number": n} for n in range(1, 11)]
        mock_client = self._mock_client([expired_row], episode_rows)

        with patch("storage.get_client", return_value=mock_client), \
             patch.dict(os.environ, {"SIMULCAST_GRACE_ENABLED": "1"}, clear=False):
            result = get_due_simulcast_series()

        assert result == []

    def test_flag_on_cooldown_still_applies_to_grace_rows(self):
        """Grace row checked 1 hour ago → still within the 4h cooldown → excluded."""
        from db.simulcast import get_due_simulcast_series

        ended_5_days_ago = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        grace_row = {
            "id": "s-grace",
            "principal_slug": "slug-grace",
            "mal_id": 2,
            "kitsu_id": None,
            "last_simulcast_check": one_hour_ago,
            "is_simulcast": False,
            "simulcast_ended_at": ended_5_days_ago,
            "episode_count": 12,
            "franchise_id": None,
        }
        episode_rows = [{"series_id": "s-grace", "episode_number": n} for n in range(1, 11)]
        mock_client = self._mock_client([grace_row], episode_rows)

        with patch("storage.get_client", return_value=mock_client), \
             patch.dict(os.environ, {"SIMULCAST_GRACE_ENABLED": "1"}, clear=False):
            result = get_due_simulcast_series()

        assert result == []
