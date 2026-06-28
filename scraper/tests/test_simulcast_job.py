"""Unit tests for the simulcast background job module.

Covers:
  4.1  jobs.simulcast_job._within_cr_window()
  4.2  db.simulcast.get_due_simulcast_series()
  4.3  jobs.simulcast_job.run_simulcast_daily_check()
  4.4  scheduler.init_scheduler()

All external I/O (Supabase, APScheduler, Jikan) is mocked.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("INTERNAL_JWT_SECRET", "test-internal-secret-for-tests-only")
os.environ.setdefault("SERVICE_SECRET", "test-service-secret")

from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_simulcast_client(series_rows: list, episode_rows: list | None = None) -> MagicMock:
    """Return a chain-mockable Supabase client for get_due_simulcast_series.

    The mock handles two distinct table queries:
      - "series"   → returns series_rows
      - "episodes" → returns episode_rows
    """
    episode_rows = episode_rows or []

    # Series table chain
    series_chain = MagicMock()
    series_chain.select.return_value = series_chain
    series_chain.eq.return_value = series_chain
    series_chain.not_ = MagicMock()
    series_chain.not_.is_.return_value = series_chain
    series_result = MagicMock()
    series_result.data = series_rows
    series_chain.execute.return_value = series_result

    # Episodes table chain
    eps_chain = MagicMock()
    eps_chain.select.return_value = eps_chain
    eps_chain.in_.return_value = eps_chain
    eps_result = MagicMock()
    eps_result.data = episode_rows
    eps_chain.execute.return_value = eps_result

    mock_client = MagicMock()
    mock_client.table.side_effect = lambda t: series_chain if t == "series" else eps_chain
    return mock_client


# ---------------------------------------------------------------------------
# Task C1 — refresh_series_from_jikan persists episode_count
# ---------------------------------------------------------------------------


class TestRefreshSeriesFromJikanEpisodeCount:
    """Unit tests for domain.jikan_refresh.refresh_series_from_jikan().

    Guards that episode_count is written to the DB when Jikan returns a
    non-None episode count and is absent when Jikan returns None.
    """

    def _make_jikan_data(self, episodes: int | None) -> dict:
        return {
            "airing": True,
            "episodes": episodes,
            "broadcast": {},
            "aired": {},
        }

    def test_episode_count_in_fields_when_jikan_returns_value(self):
        """Jikan returns episodes=24 → update_simulcast_fields called with episode_count=24."""
        from domain.jikan_refresh import refresh_series_from_jikan

        jikan_data = self._make_jikan_data(24)
        with patch("domain.jikan_refresh.fetch_anime_by_id", return_value=jikan_data), \
             patch("domain.jikan_refresh.fetch_kitsu_series_status", return_value=None), \
             patch("domain.jikan_refresh.update_simulcast_fields") as mock_update:
            refresh_series_from_jikan("series-1", mal_id=123, kitsu_id=None)

        mock_update.assert_called_once()
        _, fields = mock_update.call_args.args
        assert "episode_count" in fields, "episode_count must be in fields_to_update when Jikan returns a value"
        assert fields["episode_count"] == 24

    def test_episode_count_absent_when_jikan_returns_none(self):
        """Jikan returns episodes=None → episode_count NOT in fields_to_update."""
        from domain.jikan_refresh import refresh_series_from_jikan

        jikan_data = self._make_jikan_data(None)
        with patch("domain.jikan_refresh.fetch_anime_by_id", return_value=jikan_data), \
             patch("domain.jikan_refresh.fetch_kitsu_series_status", return_value=None), \
             patch("domain.jikan_refresh.update_simulcast_fields") as mock_update:
            refresh_series_from_jikan("series-1", mal_id=123, kitsu_id=None)

        mock_update.assert_called_once()
        _, fields = mock_update.call_args.args
        assert "episode_count" not in fields, "episode_count must NOT be in fields_to_update when Jikan returns None"

    def test_episode_count_absent_when_jikan_fetch_fails(self):
        """Jikan fetch raises → episode_count NOT in fields_to_update (fail-open)."""
        from domain.jikan_refresh import refresh_series_from_jikan

        with patch("domain.jikan_refresh.fetch_anime_by_id", side_effect=RuntimeError("timeout")), \
             patch("domain.jikan_refresh.fetch_kitsu_series_status", return_value=None), \
             patch("domain.jikan_refresh.update_simulcast_fields") as mock_update:
            refresh_series_from_jikan("series-1", mal_id=123, kitsu_id=None)

        mock_update.assert_called_once()
        _, fields = mock_update.call_args.args
        assert "episode_count" not in fields


# ---------------------------------------------------------------------------
# Task 4.1 — _within_cr_window()
# ---------------------------------------------------------------------------


class TestWithinCrWindow:
    """Unit tests for jobs.simulcast_job._within_cr_window().

    America/Costa_Rica = UTC-6 (no DST).
    Window: 07:00 <= CR local hour < 19:00.

    UTC/CR offset reference:
      12:59 UTC → 06:59 CR   (before window)
      13:00 UTC → 07:00 CR   (start of window, inclusive)
      00:59 UTC → 18:59 CR   (last minute still inside window)
      01:00 UTC → 19:00 CR   (end of window, exclusive)
    """

    def test_false_before_window_at_0659_cr(self):
        """12:59 UTC (06:59 CR) → outside window → False."""
        from jobs.simulcast_job import _within_cr_window

        now = datetime(2026, 1, 15, 12, 59, tzinfo=timezone.utc)
        assert _within_cr_window(now=now) is False

    def test_true_at_window_start_0700_cr(self):
        """13:00 UTC (07:00 CR) → start of window, inclusive → True."""
        from jobs.simulcast_job import _within_cr_window

        now = datetime(2026, 1, 15, 13, 0, tzinfo=timezone.utc)
        assert _within_cr_window(now=now) is True

    def test_true_at_1859_cr(self):
        """00:59 UTC next day (18:59 CR) → last minute inside window → True."""
        from jobs.simulcast_job import _within_cr_window

        now = datetime(2026, 1, 16, 0, 59, tzinfo=timezone.utc)
        assert _within_cr_window(now=now) is True

    def test_false_at_window_end_1900_cr(self):
        """01:00 UTC next day (19:00 CR) → end of window, exclusive → False."""
        from jobs.simulcast_job import _within_cr_window

        now = datetime(2026, 1, 16, 1, 0, tzinfo=timezone.utc)
        assert _within_cr_window(now=now) is False


# ---------------------------------------------------------------------------
# Task 4.2 — get_due_simulcast_series()
# ---------------------------------------------------------------------------


class TestGetDueSimulcastSeries:
    """Unit tests for db.simulcast.get_due_simulcast_series()."""

    def test_null_last_check_row_is_included(self):
        """Row with last_simulcast_check=None → not skipped → appears in result."""
        from db.simulcast import get_due_simulcast_series

        row = {
            "id": "s1",
            "animeflv_slug": "slug1",
            "mal_id": 42,
            "kitsu_id": None,
            "last_simulcast_check": None,
        }
        mock_client = _make_simulcast_client([row], [])
        with patch("storage.get_client", return_value=mock_client):
            result = get_due_simulcast_series()

        assert len(result) == 1
        assert result[0]["id"] == "s1"

    def test_already_checked_today_cr_is_excluded(self):
        """Row with last_simulcast_check = today in CR tz → already done → excluded."""
        from db.simulcast import get_due_simulcast_series
        from zoneinfo import ZoneInfo

        # Build a timestamp that falls on today's date in CR timezone
        today_cr = datetime.now(timezone.utc).astimezone(ZoneInfo("America/Costa_Rica"))
        today_noon_cr = today_cr.replace(hour=12, minute=0, second=0, microsecond=0)
        row = {
            "id": "s1",
            "animeflv_slug": "slug1",
            "mal_id": 42,
            "kitsu_id": None,
            "last_simulcast_check": today_noon_cr.isoformat(),
        }
        mock_client = _make_simulcast_client([row], [])
        with patch("storage.get_client", return_value=mock_client):
            result = get_due_simulcast_series()

        assert result == []

    def test_return_shape_has_required_keys(self):
        """Result dicts include id, animeflv_slug, mal_id, kitsu_id, max_episode_number."""
        from db.simulcast import get_due_simulcast_series

        row = {
            "id": "s1",
            "animeflv_slug": "slug1",
            "mal_id": 42,
            "kitsu_id": "k1",
            "last_simulcast_check": None,
        }
        mock_client = _make_simulcast_client([row], [])
        with patch("storage.get_client", return_value=mock_client):
            result = get_due_simulcast_series()

        assert len(result) == 1
        item = result[0]
        for key in ("id", "animeflv_slug", "mal_id", "kitsu_id", "max_episode_number"):
            assert key in item, f"Result dict is missing key '{key}'"

    def test_max_episode_number_from_batched_episodes_query(self):
        """max_episode_number equals the highest episode_number returned by the batched query."""
        from db.simulcast import get_due_simulcast_series

        row = {
            "id": "s1",
            "animeflv_slug": "slug1",
            "mal_id": None,
            "kitsu_id": None,
            "last_simulcast_check": None,
        }
        ep_rows = [
            {"series_id": "s1", "episode_number": 5},
            {"series_id": "s1", "episode_number": 12},
            {"series_id": "s1", "episode_number": 3},
        ]
        mock_client = _make_simulcast_client([row], ep_rows)
        with patch("storage.get_client", return_value=mock_client):
            result = get_due_simulcast_series()

        assert result[0]["max_episode_number"] == 12

    def test_no_series_rows_returns_empty_list(self):
        """Empty series result → returns [] immediately."""
        from db.simulcast import get_due_simulcast_series

        mock_client = _make_simulcast_client([], [])
        with patch("storage.get_client", return_value=mock_client):
            result = get_due_simulcast_series()

        assert result == []


# ---------------------------------------------------------------------------
# Task 4.3 — run_simulcast_daily_check()
# ---------------------------------------------------------------------------


class TestRunSimulcastDailyCheck:
    """Unit tests for jobs.simulcast_job.run_simulcast_daily_check()."""

    def test_outside_window_returns_early_no_db_call(self):
        """_within_cr_window() = False → early return, DB never queried."""
        from jobs.simulcast_job import run_simulcast_daily_check

        with patch("jobs.simulcast_job._within_cr_window", return_value=False), \
             patch("db.simulcast.get_due_simulcast_series") as mock_db:
            run_simulcast_daily_check()

        mock_db.assert_not_called()

    def test_per_series_exception_continues_loop(self):
        """Exception raised for first series → loop continues, second series is attempted."""
        from jobs.simulcast_job import run_simulcast_daily_check

        candidates = [
            {"id": "s1", "animeflv_slug": "a", "mal_id": 1, "kitsu_id": None, "max_episode_number": 3},
            {"id": "s2", "animeflv_slug": "b", "mal_id": 2, "kitsu_id": None, "max_episode_number": 5},
        ]
        with patch("jobs.simulcast_job._within_cr_window", return_value=True), \
             patch("db.simulcast.get_due_simulcast_series", return_value=candidates), \
             patch("jobs.simulcast_job.refresh_series_from_jikan", side_effect=RuntimeError("jikan down")) as mock_refresh, \
             patch("jobs.simulcast_job.run_simulcast_update") as mock_update:
            run_simulcast_daily_check()

        # refresh attempted for both series despite the first one raising
        assert mock_refresh.call_count == 2
        # run_simulcast_update never reached because refresh raised before it on both series
        mock_update.assert_not_called()

    def test_refresh_and_update_called_per_candidate(self):
        """refresh_series_from_jikan and run_simulcast_update each called once per candidate."""
        from jobs.simulcast_job import run_simulcast_daily_check

        candidates = [
            {"id": "s1", "animeflv_slug": "a-slug", "mal_id": 10, "kitsu_id": "k1", "max_episode_number": 5},
        ]
        with patch("jobs.simulcast_job._within_cr_window", return_value=True), \
             patch("db.simulcast.get_due_simulcast_series", return_value=candidates), \
             patch("jobs.simulcast_job.refresh_series_from_jikan") as mock_refresh, \
             patch("jobs.simulcast_job.run_simulcast_update") as mock_update:
            run_simulcast_daily_check()

        mock_refresh.assert_called_once_with("s1", 10, "k1")
        mock_update.assert_called_once_with("s1", "a-slug", 5)

    def test_no_mal_id_skips_jikan_refresh_but_calls_update(self):
        """Candidate without mal_id → refresh_series_from_jikan skipped; run_simulcast_update called."""
        from jobs.simulcast_job import run_simulcast_daily_check

        candidates = [
            {"id": "s1", "animeflv_slug": "a-slug", "mal_id": None, "kitsu_id": None, "max_episode_number": None},
        ]
        with patch("jobs.simulcast_job._within_cr_window", return_value=True), \
             patch("db.simulcast.get_due_simulcast_series", return_value=candidates), \
             patch("jobs.simulcast_job.refresh_series_from_jikan") as mock_refresh, \
             patch("jobs.simulcast_job.run_simulcast_update") as mock_update:
            run_simulcast_daily_check()

        # No MAL ID → Jikan refresh skipped
        mock_refresh.assert_not_called()
        # AnimeFlv scrape still runs; max_episode_number=None resolves to 0
        mock_update.assert_called_once_with("s1", "a-slug", 0)


# ---------------------------------------------------------------------------
# Task 4.4 — init_scheduler()
# ---------------------------------------------------------------------------


class TestInitScheduler:
    """Unit tests for scheduler.init_scheduler().

    Guards (tested in order):
      1. app.config["TESTING"] = True  → returns None
      2. SIMULCAST_JOB_ENABLED != "1"  → returns None
      3. debug=True + WERKZEUG_RUN_MAIN != "true" → returns None
      4. All guards pass → BackgroundScheduler created, started, returned
    """

    def _make_flask_app(self, testing: bool = False, debug: bool = False):
        from flask import Flask

        app = Flask(__name__)
        app.config["TESTING"] = testing
        app.debug = debug
        return app

    def test_testing_flag_returns_none(self):
        """Guard 1: TESTING=True → None returned immediately."""
        from scheduler import init_scheduler

        app = self._make_flask_app(testing=True)
        result = init_scheduler(app)
        assert result is None

    def test_job_env_disabled_returns_none(self):
        """Guard 2: SIMULCAST_JOB_ENABLED != '1' → None returned."""
        from scheduler import init_scheduler

        app = self._make_flask_app(testing=False)
        with patch.dict(os.environ, {"SIMULCAST_JOB_ENABLED": "0"}, clear=False):
            result = init_scheduler(app)

        assert result is None

    def test_werkzeug_reloader_parent_process_returns_none(self):
        """Guard 3: debug=True and WERKZEUG_RUN_MAIN != 'true' → None returned."""
        from scheduler import init_scheduler

        app = self._make_flask_app(testing=False, debug=True)
        env = {"SIMULCAST_JOB_ENABLED": "1", "WERKZEUG_RUN_MAIN": "false"}
        with patch.dict(os.environ, env, clear=False):
            result = init_scheduler(app)

        assert result is None

    def test_all_guards_pass_returns_started_scheduler(self):
        """TESTING=False, SIMULCAST_JOB_ENABLED=1, not debug → BackgroundScheduler started."""
        from scheduler import init_scheduler

        app = self._make_flask_app(testing=False, debug=False)
        mock_sched = MagicMock()
        env = {"SIMULCAST_JOB_ENABLED": "1"}
        with patch.dict(os.environ, env, clear=False), \
             patch("apscheduler.schedulers.background.BackgroundScheduler", return_value=mock_sched), \
             patch("apscheduler.triggers.interval.IntervalTrigger"):
            result = init_scheduler(app)

        assert result is mock_sched
        mock_sched.add_job.assert_called_once()
        mock_sched.start.assert_called_once()
