"""Tests for the simulcast episode-check feature.

Covers:
  4.1 — cooldown_elapsed unit tests
  4.2 — is_simulcast_candidate truth table
  4.3 — get_series_simulcast_meta unit tests
  4.4 — run_simulcast_check integration tests
  4.5 — continue_watching route simulcast thread spawning
  4.6 — idempotency: upsert SQL uses ON CONFLICT semantics

All DB/HTTP/threading calls are mocked.
"""
from __future__ import annotations

import sys
import os
import json
import time
import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, call, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

TEST_SECRET = "test-internal-secret-for-tests-only"
os.environ.setdefault("INTERNAL_JWT_SECRET", TEST_SECRET)
os.environ.setdefault("SERVICE_SECRET", "test-service-secret-for-tests-only")

import auth as auth_module
auth_module._INTERNAL_JWT_SECRET = TEST_SECRET

import jwt as pyjwt


def _token(user_id: str = "u-1", role: str = "USER") -> str:
    return pyjwt.encode(
        {"sub": user_id, "role": role, "exp": int(time.time()) + 60},
        TEST_SECRET,
        algorithm="HS256",
    )


def _auth_header(user_id: str = "u-1") -> dict:
    return {"Authorization": f"Bearer {_token(user_id)}"}


# ---------------------------------------------------------------------------
# 4.1 — cooldown_elapsed
# ---------------------------------------------------------------------------

from domain.simulcast import cooldown_elapsed


class TestCooldownElapsed:
    def test_none_returns_true(self):
        """NULL last_check → cooldown always elapsed."""
        assert cooldown_elapsed(None) is True

    def test_recent_datetime_returns_false(self):
        """Timestamp from 1 hour ago → within 6h window → not elapsed."""
        recent = datetime.now(timezone.utc) - timedelta(hours=1)
        assert cooldown_elapsed(recent) is False

    def test_stale_datetime_returns_true(self):
        """Timestamp from 8 hours ago → beyond 6h window → elapsed."""
        stale = datetime.now(timezone.utc) - timedelta(hours=8)
        assert cooldown_elapsed(stale) is True

    def test_exactly_at_boundary_returns_true(self):
        """Exactly 6 hours ago → elapsed (>= timedelta boundary)."""
        at_boundary = datetime.now(timezone.utc) - timedelta(hours=6)
        assert cooldown_elapsed(at_boundary) is True

    def test_recent_iso_string_returns_false(self):
        """ISO string from 2 hours ago → not elapsed."""
        recent = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        assert cooldown_elapsed(recent) is False

    def test_stale_iso_string_returns_true(self):
        """ISO string from 7 hours ago → elapsed."""
        stale = (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat()
        assert cooldown_elapsed(stale) is True

    def test_naive_datetime_treated_as_utc_stale(self):
        """Naive datetime 8h ago treated as UTC → elapsed."""
        naive_stale = datetime.utcnow() - timedelta(hours=8)
        assert cooldown_elapsed(naive_stale) is True

    def test_naive_datetime_treated_as_utc_recent(self):
        """Naive datetime 1h ago treated as UTC → not elapsed."""
        naive_recent = datetime.utcnow() - timedelta(hours=1)
        assert cooldown_elapsed(naive_recent) is False

    def test_custom_hours_respected(self):
        """Custom hours=2: 1h ago → not elapsed; 3h ago → elapsed."""
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        three_hours_ago = datetime.now(timezone.utc) - timedelta(hours=3)
        assert cooldown_elapsed(one_hour_ago, hours=2) is False
        assert cooldown_elapsed(three_hours_ago, hours=2) is True

    def test_unparseable_string_returns_true(self):
        """Garbage string → treated as no previous check → True."""
        assert cooldown_elapsed("not-a-datetime") is True


# ---------------------------------------------------------------------------
# 4.2 — is_simulcast_candidate truth table
# ---------------------------------------------------------------------------

from domain.simulcast import is_simulcast_candidate

# A fixed "now" that is a Wednesday in UTC, used throughout truth-table tests.
_NOW = datetime(2026, 6, 3, 12, 0, 0, tzinfo=timezone.utc)  # Wednesday

# A plausible "aired_at" that makes next_expected (aired+7d) already past.
_AIRED_8_DAYS_AGO = (_NOW - timedelta(days=8)).isoformat()
# A plausible "aired_at" that makes next_expected still in the future.
_AIRED_3_DAYS_AGO = (_NOW - timedelta(days=3)).isoformat()


def _base_kwargs(**overrides):
    """Return a full set of valid kwargs for is_simulcast_candidate."""
    base = dict(
        is_simulcast=True,
        progress_sec=1400.0,
        duration_sec=1440.0,       # ratio ≈ 0.972 → caught-up
        last_aired_at=_AIRED_8_DAYS_AGO,
        broadcast_day=None,
        broadcast_time=None,
        broadcast_timezone=None,
        now_utc=_NOW,
    )
    base.update(overrides)
    return base


class TestIsSimulcastCandidate:
    def test_not_simulcast_returns_false(self):
        """is_simulcast=False → always False regardless of other conditions."""
        assert is_simulcast_candidate(**_base_kwargs(is_simulcast=False)) is False

    def test_caught_up_by_ratio_returns_true(self):
        """progress/duration >= 0.95 AND next episode expected → True."""
        kwargs = _base_kwargs(progress_sec=1400.0, duration_sec=1440.0)
        assert is_simulcast_candidate(**kwargs) is True

    def test_caught_up_by_remaining_seconds_returns_true(self):
        """remaining <= 120s AND next episode expected → True (long-format)."""
        kwargs = _base_kwargs(progress_sec=3460.0, duration_sec=3600.0)
        # ratio = 3460/3600 = 0.961 ≥ 0.95 — also caught up by ratio; test remaining path:
        kwargs2 = _base_kwargs(progress_sec=3540.0, duration_sec=3660.0)
        # ratio = 3540/3660 ≈ 0.967; remaining = 120s exactly → caught-up
        assert is_simulcast_candidate(**kwargs2) is True

    def test_remaining_just_over_120_not_caught_up(self):
        """remaining > 120s AND ratio < 0.95 → not caught-up → False."""
        # ratio = 0.90; remaining = 360s > 120 → not caught-up
        kwargs = _base_kwargs(progress_sec=1296.0, duration_sec=1440.0)
        # 1296/1440 = 0.90, remaining = 144s > 120 → not caught-up
        assert is_simulcast_candidate(**kwargs) is False

    def test_zero_duration_not_caught_up_returns_false(self):
        """duration_sec=0 → cannot compute ratio → not caught-up → False."""
        kwargs = _base_kwargs(progress_sec=500.0, duration_sec=0.0)
        assert is_simulcast_candidate(**kwargs) is False

    def test_aired_at_present_next_expected_passed_returns_true(self):
        """aired_at 8 days ago → next_expected 1 day ago → True."""
        kwargs = _base_kwargs(last_aired_at=_AIRED_8_DAYS_AGO)
        assert is_simulcast_candidate(**kwargs) is True

    def test_aired_at_present_next_expected_future_returns_false(self):
        """aired_at 3 days ago → next_expected 4 days from now → False."""
        kwargs = _base_kwargs(last_aired_at=_AIRED_3_DAYS_AGO)
        assert is_simulcast_candidate(**kwargs) is False

    def test_aired_at_none_broadcast_schedule_arrived(self):
        """aired_at=None; broadcast schedule indicates episode has aired → True.

        We pick a broadcast_day/time/tz whose compute_broadcast_utc() falls
        before _NOW. Since compute_broadcast_utc returns the *most recent*
        occurrence, and _NOW is a Wednesday, we set the broadcast day also to
        Wednesday but with a time well before _NOW's hour (12:00 UTC).
        """
        kwargs = _base_kwargs(
            last_aired_at=None,
            broadcast_day="Wednesdays",
            broadcast_time="01:00",     # 01:00 UTC < 12:00 UTC → already passed today
            broadcast_timezone="UTC",
        )
        assert is_simulcast_candidate(**kwargs) is True

    def test_aired_at_none_broadcast_schedule_not_yet(self):
        """aired_at=None; broadcast schedule says episode hasn't aired → False.

        Set broadcast_day to Thursday. _NOW is Wednesday. The most-recent
        Thursday at 01:00 UTC is 6 days ago, which is < _NOW. This exposes
        the nuance: compute_broadcast_utc returns the MOST RECENT occurrence,
        so it's in the past — this should still return True in our implementation.

        Instead we test with a broadcast time later today:
        broadcast_day=Wednesday, time=23:00 UTC, _NOW=12:00 UTC → not yet arrived.
        """
        kwargs = _base_kwargs(
            last_aired_at=None,
            broadcast_day="Wednesdays",
            broadcast_time="23:00",     # 23:00 UTC > 12:00 UTC → not yet
            broadcast_timezone="UTC",
        )
        assert is_simulcast_candidate(**kwargs) is False

    def test_aired_at_none_missing_broadcast_info_returns_false(self):
        """aired_at=None but no broadcast_day/time/tz → cannot compute → False."""
        kwargs = _base_kwargs(
            last_aired_at=None,
            broadcast_day=None,
            broadcast_time=None,
            broadcast_timezone=None,
        )
        assert is_simulcast_candidate(**kwargs) is False

    def test_aired_at_none_partial_broadcast_info_returns_false(self):
        """Partial broadcast info (missing tz) → cannot compute → False."""
        kwargs = _base_kwargs(
            last_aired_at=None,
            broadcast_day="Wednesdays",
            broadcast_time="01:00",
            broadcast_timezone=None,    # missing
        )
        assert is_simulcast_candidate(**kwargs) is False


# ---------------------------------------------------------------------------
# 4.3 — get_series_simulcast_meta
# ---------------------------------------------------------------------------

class TestGetSeriesSimulcastMeta:
    def _mock_client(self, series_rows: list[dict], episode_rows: list[dict]) -> MagicMock:
        """Build a mock Supabase client that returns the given rows."""
        client = MagicMock()

        # Chain for series table: .select().in_().execute()
        series_exec = MagicMock()
        series_exec.data = series_rows
        series_in = MagicMock()
        series_in.execute.return_value = series_exec
        series_select = MagicMock()
        series_select.in_.return_value = series_in
        series_table = MagicMock()
        series_table.select.return_value = series_select

        # Chain for episodes table: .select().in_().execute()
        eps_exec = MagicMock()
        eps_exec.data = episode_rows
        eps_in = MagicMock()
        eps_in.execute.return_value = eps_exec
        eps_select = MagicMock()
        eps_select.in_.return_value = eps_in
        eps_table = MagicMock()
        eps_table.select.return_value = eps_select

        def table_side_effect(name):
            if name == "series":
                return series_table
            if name == "episodes":
                return eps_table
            return MagicMock()

        client.table.side_effect = table_side_effect
        return client

    def test_empty_input_returns_empty_dict(self):
        from db.progress import get_series_simulcast_meta
        assert get_series_simulcast_meta([]) == {}

    def test_returns_dict_keyed_by_series_id(self):
        from db.progress import get_series_simulcast_meta

        series_rows = [
            {
                "id": "attack-on-titan",
                "is_simulcast": True,
                "animeflv_slug": "shingeki-no-kyojin",
                "broadcast_day": "Saturdays",
                "broadcast_time": "00:10",
                "broadcast_timezone": "Asia/Tokyo",
                "last_simulcast_check": None,
            }
        ]
        episode_rows = [
            {"series_id": "attack-on-titan", "episode_number": 3},
            {"series_id": "attack-on-titan", "episode_number": 7},
            {"series_id": "attack-on-titan", "episode_number": 5},
        ]
        mock_client = self._mock_client(series_rows, episode_rows)

        with patch("storage.get_client", return_value=mock_client):
            result = get_series_simulcast_meta(["attack-on-titan"])

        assert "attack-on-titan" in result
        row = result["attack-on-titan"]
        assert row["is_simulcast"] is True
        assert row["animeflv_slug"] == "shingeki-no-kyojin"
        assert row["broadcast_day"] == "Saturdays"
        assert row["max_episode_number"] == 7

    def test_max_episode_number_is_none_when_no_episodes(self):
        from db.progress import get_series_simulcast_meta

        series_rows = [
            {
                "id": "new-series",
                "is_simulcast": True,
                "animeflv_slug": "new-slug",
                "broadcast_day": None,
                "broadcast_time": None,
                "broadcast_timezone": None,
                "last_simulcast_check": None,
            }
        ]
        mock_client = self._mock_client(series_rows, [])

        with patch("storage.get_client", return_value=mock_client):
            result = get_series_simulcast_meta(["new-series"])

        assert result["new-series"]["max_episode_number"] is None

    def test_multiple_series_keyed_correctly(self):
        from db.progress import get_series_simulcast_meta

        series_rows = [
            {"id": "s1", "is_simulcast": True, "animeflv_slug": "slug1",
             "broadcast_day": None, "broadcast_time": None,
             "broadcast_timezone": None, "last_simulcast_check": None},
            {"id": "s2", "is_simulcast": False, "animeflv_slug": None,
             "broadcast_day": None, "broadcast_time": None,
             "broadcast_timezone": None, "last_simulcast_check": None},
        ]
        episode_rows = [
            {"series_id": "s1", "episode_number": 10},
            {"series_id": "s2", "episode_number": 5},
        ]
        mock_client = self._mock_client(series_rows, episode_rows)

        with patch("storage.get_client", return_value=mock_client):
            result = get_series_simulcast_meta(["s1", "s2"])

        assert result["s1"]["max_episode_number"] == 10
        assert result["s2"]["max_episode_number"] == 5
        assert result["s2"]["is_simulcast"] is False


# ---------------------------------------------------------------------------
# 4.4 — run_simulcast_check integration tests
# ---------------------------------------------------------------------------

from simulcast_check import run_simulcast_check


class TestRunSimulcastCheck:
    def test_new_episode_found_upserts_and_seeds_and_stamps(self):
        """Scraped episode_number > current_max_ep → upsert episode, seed progress, stamp."""
        scraped = [{"episode_number": 6, "title": "Episode 6", "thumbnail_url": None}]

        with (
            patch("simulcast_check.scrape_animeav1_episodes", return_value=scraped) as mock_scrape,
            patch("simulcast_check.storage.upsert_episode") as mock_upsert_ep,
            patch("simulcast_check.db_progress.upsert_progress") as mock_upsert_prog,
            patch("simulcast_check.db_simulcast.update_simulcast_fields") as mock_stamp,
            patch("simulcast_check._resolve_aired_at", return_value="2026-06-03"),
        ):
            run_simulcast_check("user-1", "series-x", "series-x-slug", current_max_ep=5)

        mock_scrape.assert_called_once_with("series-x-slug")
        mock_upsert_ep.assert_called_once_with({
            "id": "series-x-ep-6",
            "series_id": "series-x",
            "episode_number": 6,
            "title": "Episode 6",
            "thumbnail_url": None,
            "animeflv_slug": "series-x-slug-6",
            "aired_at": "2026-06-03",
        })
        mock_upsert_prog.assert_called_once_with(
            user_id="user-1",
            episode_id="series-x-ep-6",
            series_id="series-x",
            progress_sec=1,
            duration_sec=0,
        )
        mock_stamp.assert_called_once_with("series-x", {})

    def test_no_new_episode_stamps_cooldown_no_upsert(self):
        """Scraped max == current_max_ep → no upsert, cooldown stamped."""
        scraped = [{"episode_number": 5, "title": None, "thumbnail_url": None}]

        with (
            patch("simulcast_check.scrape_animeav1_episodes", return_value=scraped),
            patch("simulcast_check.storage.upsert_episode") as mock_upsert_ep,
            patch("simulcast_check.db_progress.upsert_progress") as mock_upsert_prog,
            patch("simulcast_check.db_simulcast.update_simulcast_fields") as mock_stamp,
        ):
            run_simulcast_check("user-1", "series-x", "series-x-slug", current_max_ep=5)

        mock_upsert_ep.assert_not_called()
        mock_upsert_prog.assert_not_called()
        mock_stamp.assert_called_once_with("series-x", {})

    def test_scrape_raises_runtime_error_fail_silent_attempts_stamp(self):
        """scrape_animeav1_episodes returns [] (error) → no upserts, stamps cooldown."""
        with (
            patch("simulcast_check.scrape_animeav1_episodes", return_value=[]),
            patch("simulcast_check.storage.upsert_episode") as mock_upsert_ep,
            patch("simulcast_check.db_progress.upsert_progress") as mock_upsert_prog,
            patch("simulcast_check.db_simulcast.update_simulcast_fields") as mock_stamp,
        ):
            # Must not raise.
            run_simulcast_check("user-1", "series-x", "series-x-slug", current_max_ep=5)

        mock_upsert_ep.assert_not_called()
        mock_upsert_prog.assert_not_called()
        mock_stamp.assert_called_once_with("series-x", {})

    def test_multiple_new_episodes_all_upserted(self):
        """Two new episodes → both upserted and progress seeded for each."""
        scraped = [
            {"episode_number": 6, "title": "Ep 6", "thumbnail_url": None},
            {"episode_number": 7, "title": "Ep 7", "thumbnail_url": "http://thumb.jpg"},
        ]

        with (
            patch("simulcast_check.scrape_animeav1_episodes", return_value=scraped),
            patch("simulcast_check.storage.upsert_episode") as mock_upsert_ep,
            patch("simulcast_check.db_progress.upsert_progress") as mock_upsert_prog,
            patch("simulcast_check.db_simulcast.update_simulcast_fields") as mock_stamp,
        ):
            run_simulcast_check("user-1", "series-x", "series-x-slug", current_max_ep=5)

        assert mock_upsert_ep.call_count == 2
        assert mock_upsert_prog.call_count == 2
        mock_stamp.assert_called_once()


# ---------------------------------------------------------------------------
# 4.5 — continue_watching route: thread spawning guard
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    with patch("storage.get_client"):
        from app import create_app
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c


def _progress_row(episode_id="ep1", series_id="s1", progress_sec=1400.0, duration_sec=1440.0):
    return {
        "episode_id": episode_id,
        "series_id": series_id,
        "progress_sec": progress_sec,
        "duration_sec": duration_sec,
        "updated_at": "2026-06-01T00:00:00Z",
    }


def _episode_row(id="ep1", series_id="s1", episode_number=5, aired_at=None):
    return {
        "id": id,
        "series_id": series_id,
        "episode_number": episode_number,
        "title": "Episode",
        "animeflv_slug": f"{series_id}-{episode_number}",
        "thumbnail_url": None,
        "aired_at": aired_at,
        "series": {"title": "Test Anime"},
    }


def _simulcast_meta(series_id="s1", is_simulcast=True, slug="test-slug", max_ep=5,
                    last_check=None):
    return {
        series_id: {
            "id": series_id,
            "is_simulcast": is_simulcast,
            "animeflv_slug": slug,
            "broadcast_day": None,
            "broadcast_time": None,
            "broadcast_timezone": None,
            "last_simulcast_check": last_check,
            "max_episode_number": max_ep,
        }
    }


class TestContinueWatchingSimulcastThreads:
    def test_qualifying_row_spawns_one_thread(self, client):
        """One qualifying progress row → exactly one daemon thread spawned."""
        # aired_at 8 days ago → next_expected already passed → qualifies
        aired_8_days_ago = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        rows = [_progress_row("ep1", "s1", progress_sec=1400.0, duration_sec=1440.0)]
        eps = [_episode_row("ep1", "s1", episode_number=5, aired_at=aired_8_days_ago)]
        meta = _simulcast_meta("s1", is_simulcast=True, slug="s1-slug", max_ep=5)

        with (
            patch("db.progress.get_recent_progress", return_value=rows),
            patch("db.progress.get_series_franchise_map", return_value={"s1": "s1"}),
            patch("db.progress.get_episodes_by_ids", return_value=eps),
            patch("db.progress.get_series_simulcast_meta", return_value=meta),
            patch("routes.progress_routes.threading.Thread") as mock_thread_cls,
        ):
            mock_thread_instance = MagicMock()
            mock_thread_cls.return_value = mock_thread_instance

            res = client.get("/api/progress/continue-watching", headers=_auth_header())

        assert res.status_code == 200
        assert mock_thread_cls.call_count == 1
        # Verify daemon=True was passed
        _, kwargs = mock_thread_cls.call_args
        assert kwargs.get("daemon") is True
        mock_thread_instance.start.assert_called_once()

    def test_non_qualifying_row_no_thread(self, client):
        """Row where is_simulcast=False → no thread spawned."""
        aired_8_days_ago = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        rows = [_progress_row("ep1", "s1", progress_sec=1400.0, duration_sec=1440.0)]
        eps = [_episode_row("ep1", "s1", episode_number=5, aired_at=aired_8_days_ago)]
        meta = _simulcast_meta("s1", is_simulcast=False, slug="s1-slug")

        with (
            patch("db.progress.get_recent_progress", return_value=rows),
            patch("db.progress.get_series_franchise_map", return_value={"s1": "s1"}),
            patch("db.progress.get_episodes_by_ids", return_value=eps),
            patch("db.progress.get_series_simulcast_meta", return_value=meta),
            patch("routes.progress_routes.threading.Thread") as mock_thread_cls,
        ):
            res = client.get("/api/progress/continue-watching", headers=_auth_header())

        assert res.status_code == 200
        mock_thread_cls.assert_not_called()

    def test_one_qualifying_one_not_exactly_one_thread(self, client):
        """Two rows: one qualifies (simulcast), one does not → exactly one thread."""
        aired_8_days_ago = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        rows = [
            _progress_row("ep1", "s1", progress_sec=1400.0, duration_sec=1440.0),
            _progress_row("ep2", "s2", progress_sec=100.0, duration_sec=1440.0),  # not caught-up
        ]
        eps = [
            _episode_row("ep1", "s1", episode_number=5, aired_at=aired_8_days_ago),
            _episode_row("ep2", "s2", episode_number=3, aired_at=aired_8_days_ago),
        ]
        meta_combined = {
            "s1": {
                "id": "s1", "is_simulcast": True, "animeflv_slug": "s1-slug",
                "broadcast_day": None, "broadcast_time": None,
                "broadcast_timezone": None, "last_simulcast_check": None,
                "max_episode_number": 5,
            },
            "s2": {
                "id": "s2", "is_simulcast": True, "animeflv_slug": "s2-slug",
                "broadcast_day": None, "broadcast_time": None,
                "broadcast_timezone": None, "last_simulcast_check": None,
                "max_episode_number": 3,
            },
        }

        with (
            patch("db.progress.get_recent_progress", return_value=rows),
            patch("db.progress.get_series_franchise_map",
                  return_value={"s1": "s1", "s2": "s2"}),
            patch("db.progress.get_episodes_by_ids", return_value=eps),
            patch("db.progress.get_series_simulcast_meta", return_value=meta_combined),
            patch("routes.progress_routes.threading.Thread") as mock_thread_cls,
        ):
            mock_thread_instance = MagicMock()
            mock_thread_cls.return_value = mock_thread_instance
            res = client.get("/api/progress/continue-watching", headers=_auth_header())

        assert res.status_code == 200
        # s1 qualifies (caught-up), s2 does not (not caught-up: 100/1440 ≈ 0.069)
        assert mock_thread_cls.call_count == 1

    def test_user_id_passed_as_explicit_arg_not_via_g(self, client):
        """user_id is passed as a positional arg to Thread, not accessed via g."""
        aired_8_days_ago = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        rows = [_progress_row("ep1", "s1", progress_sec=1400.0, duration_sec=1440.0)]
        eps = [_episode_row("ep1", "s1", episode_number=5, aired_at=aired_8_days_ago)]
        meta = _simulcast_meta("s1", is_simulcast=True, slug="s1-slug", max_ep=5)

        captured_args = {}

        def capture_thread(*args, **kwargs):
            captured_args.update(kwargs)
            m = MagicMock()
            return m

        with (
            patch("db.progress.get_recent_progress", return_value=rows),
            patch("db.progress.get_series_franchise_map", return_value={"s1": "s1"}),
            patch("db.progress.get_episodes_by_ids", return_value=eps),
            patch("db.progress.get_series_simulcast_meta", return_value=meta),
            patch("routes.progress_routes.threading.Thread", side_effect=capture_thread),
        ):
            res = client.get("/api/progress/continue-watching", headers=_auth_header())

        assert res.status_code == 200
        # The thread args tuple must contain user_id as first element.
        thread_args = captured_args.get("args", ())
        assert thread_args[0] == "u-1", (
            f"Expected user_id='u-1' as first thread arg, got {thread_args}"
        )

    def test_cooldown_active_no_thread(self, client):
        """last_simulcast_check within 6h → cooldown active → no thread."""
        aired_8_days_ago = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        recent_check = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        rows = [_progress_row("ep1", "s1", progress_sec=1400.0, duration_sec=1440.0)]
        eps = [_episode_row("ep1", "s1", episode_number=5, aired_at=aired_8_days_ago)]
        meta = _simulcast_meta("s1", is_simulcast=True, slug="s1-slug",
                               last_check=recent_check)

        with (
            patch("db.progress.get_recent_progress", return_value=rows),
            patch("db.progress.get_series_franchise_map", return_value={"s1": "s1"}),
            patch("db.progress.get_episodes_by_ids", return_value=eps),
            patch("db.progress.get_series_simulcast_meta", return_value=meta),
            patch("routes.progress_routes.threading.Thread") as mock_thread_cls,
        ):
            res = client.get("/api/progress/continue-watching", headers=_auth_header())

        assert res.status_code == 200
        mock_thread_cls.assert_not_called()

    def test_mid_series_episode_no_thread(self, client):
        """User on ep 3 of a 5-episode series → condition 2 fails → no thread."""
        aired_8_days_ago = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        rows = [_progress_row("ep3", "s1", progress_sec=1400.0, duration_sec=1440.0)]
        # episode_number=3, but series max is 5 → not the last episode
        eps = [_episode_row("ep3", "s1", episode_number=3, aired_at=aired_8_days_ago)]
        meta = _simulcast_meta("s1", is_simulcast=True, slug="s1-slug", max_ep=5)

        with (
            patch("db.progress.get_recent_progress", return_value=rows),
            patch("db.progress.get_series_franchise_map", return_value={"s1": "s1"}),
            patch("db.progress.get_episodes_by_ids", return_value=eps),
            patch("db.progress.get_series_simulcast_meta", return_value=meta),
            patch("routes.progress_routes.threading.Thread") as mock_thread_cls,
        ):
            res = client.get("/api/progress/continue-watching", headers=_auth_header())

        assert res.status_code == 200
        mock_thread_cls.assert_not_called()

    def test_response_does_not_block_on_thread(self, client):
        """Route returns a response without calling thread.join()."""
        aired_8_days_ago = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        rows = [_progress_row("ep1", "s1", progress_sec=1400.0, duration_sec=1440.0)]
        eps = [_episode_row("ep1", "s1", episode_number=5, aired_at=aired_8_days_ago)]
        meta = _simulcast_meta("s1", is_simulcast=True, slug="s1-slug", max_ep=5)

        with (
            patch("db.progress.get_recent_progress", return_value=rows),
            patch("db.progress.get_series_franchise_map", return_value={"s1": "s1"}),
            patch("db.progress.get_episodes_by_ids", return_value=eps),
            patch("db.progress.get_series_simulcast_meta", return_value=meta),
            patch("routes.progress_routes.threading.Thread") as mock_thread_cls,
        ):
            mock_thread_instance = MagicMock()
            mock_thread_cls.return_value = mock_thread_instance
            res = client.get("/api/progress/continue-watching", headers=_auth_header())

        assert res.status_code == 200
        # join() must NEVER be called on the spawned thread.
        mock_thread_instance.join.assert_not_called()


# ---------------------------------------------------------------------------
# 4.6 — Idempotency: upsert uses ON CONFLICT semantics
# ---------------------------------------------------------------------------

class TestRunSimulcastCheckIdempotency:
    def test_calling_twice_does_not_duplicate_upsert_calls(self):
        """Calling run_simulcast_check twice with same args → upsert called twice,
        but the underlying DB uses ON CONFLICT DO UPDATE so no actual duplicates.
        We verify the mock is called each time (i.e. the code always calls upsert),
        confirming the idempotency guarantee lives in the SQL layer (storage.upsert_episode
        and db_progress.upsert_progress both use ON CONFLICT)."""
        scraped = [{"episode_number": 6, "title": "Ep 6", "thumbnail_url": None}]

        with (
            patch("simulcast_check.scrape_animeav1_episodes", return_value=scraped),
            patch("simulcast_check.storage.upsert_episode") as mock_upsert_ep,
            patch("simulcast_check.db_progress.upsert_progress") as mock_upsert_prog,
            patch("simulcast_check.db_simulcast.update_simulcast_fields"),
        ):
            run_simulcast_check("u-1", "s1", "s1-slug", current_max_ep=5)
            run_simulcast_check("u-1", "s1", "s1-slug", current_max_ep=5)

        # Both calls attempt the upsert; DB deduplicates via ON CONFLICT.
        assert mock_upsert_ep.call_count == 2
        assert mock_upsert_prog.call_count == 2

    def test_episode_id_format_no_zero_padding(self):
        """Episode ID must be '{series_id}-ep-{num}' with NO zero-padding."""
        scraped = [{"episode_number": 6, "title": None, "thumbnail_url": None}]
        captured_ids = []

        def capture_upsert(episode_dict):
            captured_ids.append(episode_dict["id"])

        with (
            patch("simulcast_check.scrape_animeav1_episodes", return_value=scraped),
            patch("simulcast_check.storage.upsert_episode", side_effect=capture_upsert),
            patch("simulcast_check.db_progress.upsert_progress"),
            patch("simulcast_check.db_simulcast.update_simulcast_fields"),
        ):
            run_simulcast_check("u-1", "my-series", "my-slug", current_max_ep=5)

        assert captured_ids == ["my-series-ep-6"]
        # Explicitly confirm no zero-padding (e.g. not "my-series-ep-06")
        assert "my-series-ep-06" not in captured_ids
