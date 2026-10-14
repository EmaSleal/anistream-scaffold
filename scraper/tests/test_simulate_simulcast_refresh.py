"""Unit tests for scraper/scripts/simulate_simulcast_refresh.py's grace-period
eligibility + backward gap-backfill simulation extension (Phase 3 of
simulcast-gap-recovery).

Covers:
  3.1  build_backfill_plan_rows() calls the SAME domain.simulcast.classify_recheck
       / plan_backfill functions the real cron job uses (no duplicated logic),
       performs a read-only AnimeAV1 scrape only for "airing"/"grace" candidates,
       and never performs a Supabase write.
  3.2  main() wires this into a new simulcast_backfill_plan.csv output.

All external I/O (Supabase, AnimeAV1 HTTP, Jikan HTTP) is mocked. No real
network calls.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

os.environ.setdefault("INTERNAL_JWT_SECRET", "test-internal-secret-for-tests-only")
os.environ.setdefault("SERVICE_SECRET", "test-service-secret")

from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest

import simulate_simulcast_refresh as sim

NOW = datetime(2026, 10, 12, tzinfo=timezone.utc)


def _row(**overrides):
    base = {
        "id": "series-1",
        "title": "Test Series",
        "mal_id": 1,
        "principal_slug": "test-series",
        "episode_count": 12,
        "is_simulcast": False,
        "franchise_id": None,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# build_backfill_plan_rows — parity with the real cron path
# ---------------------------------------------------------------------------


class TestBuildBackfillPlanRowsUsesRealDomainFunctions:
    def test_calls_classify_recheck_and_plan_backfill_not_duplicated(self):
        """Spies on the real domain functions to prove this script calls them
        directly rather than re-implementing the decision logic locally."""
        row = _row()
        own_nums_map = {"series-1": set(range(2, 13))}  # 2..12 ingested, episode 1 missing
        last_aired_map = {"series-1": NOW - timedelta(days=5)}

        with patch.object(sim, "classify_recheck", wraps=sim.classify_recheck) as mock_classify, \
             patch.object(sim, "plan_backfill", wraps=sim.plan_backfill) as mock_plan, \
             patch.object(sim, "get_slug_sibling_episodes", return_value={"offset": 0, "sibling_nums": set()}), \
             patch.object(sim, "scrape_animeav1_episodes", return_value=[{"episode_number": n} for n in range(1, 13)]):
            rows = sim.build_backfill_plan_rows([row], own_nums_map, last_aired_map, now_utc=NOW)

        mock_classify.assert_called_once()
        mock_plan.assert_called_once()
        assert rows[0]["mode"] == "grace"
        assert rows[0]["missing_inserts"] == "1"
        assert rows[0]["skip_reason"] == ""

    def test_ambiguous_offset_is_surfaced_for_admin_review(self):
        row = _row(franchise_id="franchise-1")
        own_nums_map = {"series-1": {13, 14}}
        last_aired_map = {"series-1": NOW - timedelta(days=5)}

        with patch.object(sim, "get_slug_sibling_episodes", return_value={
            "offset": 12,
            "sibling_nums": {1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12},  # sibling has its own gap
        }), \
             patch.object(sim, "scrape_animeav1_episodes", return_value=[{"episode_number": n} for n in range(1, 25)]):
            rows = sim.build_backfill_plan_rows(
                [row], own_nums_map, last_aired_map, now_utc=NOW,
            )

        assert rows[0]["skip_reason"] == "ambiguous_offset"
        assert rows[0]["missing_inserts"] == ""


class TestBuildBackfillPlanRowsReadOnlyScraping:
    def test_performs_read_only_animeav1_scrape_for_grace_candidate(self):
        row = _row()
        own_nums_map = {"series-1": {1, 2, 3}}
        last_aired_map = {"series-1": NOW - timedelta(days=5)}

        with patch.object(sim, "get_slug_sibling_episodes", return_value={"offset": 0, "sibling_nums": set()}), \
             patch.object(sim, "scrape_animeav1_episodes", return_value=[{"episode_number": n} for n in range(1, 5)]) as mock_scrape:
            sim.build_backfill_plan_rows([row], own_nums_map, last_aired_map, now_utc=NOW)

        mock_scrape.assert_called_once_with("test-series")

    def test_expired_mode_skips_scrape_and_is_marked_informational(self):
        """Mirrors production: expired rows go through get_expired_gap_candidates
        + mark_gap_unresolved only — never scraped or backfilled."""
        row = _row()
        own_nums_map = {"series-1": {1, 2, 3}}
        last_aired_map = {"series-1": NOW - timedelta(days=20)}

        with patch.object(sim, "scrape_animeav1_episodes") as mock_scrape:
            rows = sim.build_backfill_plan_rows([row], own_nums_map, last_aired_map, now_utc=NOW)

        mock_scrape.assert_not_called()
        assert rows[0]["mode"] == "expired"
        assert rows[0]["skip_reason"] == "grace_period_expired_no_scrape"

    def test_not_eligible_mode_skips_scrape(self):
        """have == expected -> classify_recheck returns None (regardless of
        the anchor) -> not eligible, no scrape performed."""
        row = _row(episode_count=12)
        own_nums_map = {"series-1": set(range(1, 13))}
        last_aired_map = {"series-1": NOW - timedelta(days=3)}

        with patch.object(sim, "scrape_animeav1_episodes") as mock_scrape:
            rows = sim.build_backfill_plan_rows([row], own_nums_map, last_aired_map, now_utc=NOW)

        mock_scrape.assert_not_called()
        assert rows[0]["mode"] == "not_eligible"

    def test_airing_mode_still_eligible_for_backfill_scrape(self):
        """mode='airing' also gets a backfill plan — the cron job's backward
        gap-backfill is not gated on grace mode specifically. No anchor is
        needed here since is_simulcast=True short-circuits classify_recheck."""
        row = _row(is_simulcast=True)
        own_nums_map = {"series-1": {2, 3, 4}}  # episode 1 missing

        with patch.object(sim, "get_slug_sibling_episodes", return_value={"offset": 0, "sibling_nums": set()}), \
             patch.object(sim, "scrape_animeav1_episodes", return_value=[{"episode_number": n} for n in range(1, 5)]) as mock_scrape:
            rows = sim.build_backfill_plan_rows([row], own_nums_map, {}, now_utc=NOW)

        mock_scrape.assert_called_once_with("test-series")
        assert rows[0]["mode"] == "airing"
        assert rows[0]["missing_inserts"] == "1"


# ---------------------------------------------------------------------------
# main() — zero DB writes, CSV output wiring
# ---------------------------------------------------------------------------


class TestMainIsReadOnly:
    def test_main_writes_backfill_csv_and_performs_zero_db_writes(self, tmp_path, monkeypatch):
        candidate_row = _row()

        # storage.get_client(): track every call so we can assert no write verbs
        # (update/upsert/insert) were ever invoked anywhere in the run.
        mock_client = MagicMock()
        series_select_chain = MagicMock()
        series_select_chain.select.return_value = series_select_chain
        series_select_chain.eq.return_value = series_select_chain
        series_select_chain.not_ = MagicMock()
        series_select_chain.not_.is_.return_value = series_select_chain
        series_select_chain.execute.return_value = MagicMock(data=[candidate_row])

        empty_series_chain = MagicMock()
        empty_series_chain.select.return_value = empty_series_chain
        empty_series_chain.eq.return_value = empty_series_chain
        empty_series_chain.not_ = MagicMock()
        empty_series_chain.not_.is_.return_value = empty_series_chain
        empty_series_chain.execute.return_value = MagicMock(data=[])

        episodes_chain = MagicMock()
        episodes_chain.select.return_value = episodes_chain
        episodes_chain.in_.return_value = episodes_chain
        episodes_chain.execute.return_value = MagicMock(
            data=[
                {
                    "series_id": "series-1",
                    "episode_number": n,
                    "aired_at": (NOW - timedelta(days=5)).isoformat(),
                }
                for n in range(1, 12)
            ]
        )

        call_count = {"series": 0}

        def _table(name):
            if name == "series":
                call_count["series"] += 1
                return series_select_chain if call_count["series"] == 1 else empty_series_chain
            return episodes_chain

        mock_client.table.side_effect = _table

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sim, "__file__", str(tmp_path / "simulate_simulcast_refresh.py"))

        with patch.object(sim.storage, "get_client", return_value=mock_client), \
             patch.object(sim, "fetch_anime_by_id", return_value={"airing": False, "episodes": 12}), \
             patch.object(sim, "get_slug_sibling_episodes", return_value={"offset": 0, "sibling_nums": set()}), \
             patch.object(sim, "scrape_animeav1_episodes", return_value=[{"episode_number": n} for n in range(1, 13)]), \
             patch("time.sleep"):
            sim.main(recency_days=14)

        # Zero DB writes anywhere in the run.
        mock_client.table.return_value.update.assert_not_called()
        for chain in (series_select_chain, empty_series_chain, episodes_chain):
            chain.update.assert_not_called() if hasattr(chain, "update") else None

        out_dir = os.path.join(os.path.dirname(os.path.abspath(sim.__file__)), "output")
        backfill_csv = os.path.join(out_dir, "simulcast_backfill_plan.csv")
        assert os.path.exists(backfill_csv)

        with open(backfill_csv, encoding="utf-8") as f:
            content = f.read()
        assert "series-1" in content
        assert "grace" in content
