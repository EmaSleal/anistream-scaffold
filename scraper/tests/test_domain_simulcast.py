"""Unit tests for scraper/domain/simulcast.py.

All tests use pure values — no database or HTTP access.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timedelta, timezone
import pytest
from domain.simulcast import (
    resolve_simulcast_status,
    parse_broadcast_day,
    compute_broadcast_utc,
    classify_recheck,
    plan_backfill,
)


# ---------------------------------------------------------------------------
# resolve_simulcast_status — truth table
# ---------------------------------------------------------------------------

class TestResolveSimulcastStatus:
    def test_both_sources_true_returns_true(self):
        """jikan airing + kitsu current → True."""
        assert resolve_simulcast_status(
            jikan_airing=True,
            kitsu_status="current",
            has_kitsu=True,
        ) is True

    def test_jikan_false_returns_false(self):
        """jikan not airing (regardless of kitsu) → False."""
        assert resolve_simulcast_status(
            jikan_airing=False,
            kitsu_status="current",
            has_kitsu=True,
        ) is False

    def test_kitsu_finished_ignored_jikan_decides(self):
        """jikan airing + kitsu finished → True (kitsu is ignored, jikan wins)."""
        assert resolve_simulcast_status(
            jikan_airing=True,
            kitsu_status="finished",
            has_kitsu=True,
        ) is True

    def test_kitsu_upcoming_ignored_jikan_decides(self):
        """jikan airing + kitsu upcoming → True (kitsu is ignored, jikan wins)."""
        assert resolve_simulcast_status(
            jikan_airing=True,
            kitsu_status="upcoming",
            has_kitsu=True,
        ) is True

    def test_kitsu_none_ignored_jikan_decides(self):
        """jikan airing + kitsu_status None → True (kitsu is ignored)."""
        assert resolve_simulcast_status(
            jikan_airing=True,
            kitsu_status=None,
            has_kitsu=True,
        ) is True

    def test_jikan_false_kitsu_current_returns_false(self):
        """jikan not airing + kitsu current → False (jikan is source of truth)."""
        assert resolve_simulcast_status(
            jikan_airing=False,
            kitsu_status="current",
            has_kitsu=True,
        ) is False

    def test_no_kitsu_id_jikan_true_returns_true(self):
        """No kitsu_id + jikan airing → True."""
        assert resolve_simulcast_status(
            jikan_airing=True,
            kitsu_status=None,
            has_kitsu=False,
        ) is True

    def test_no_kitsu_id_jikan_false_returns_false(self):
        """No kitsu_id + jikan not airing → False."""
        assert resolve_simulcast_status(
            jikan_airing=False,
            kitsu_status=None,
            has_kitsu=False,
        ) is False

    def test_kitsu_params_always_ignored(self):
        """kitsu_status and has_kitsu are irrelevant — only jikan_airing matters."""
        assert resolve_simulcast_status(
            jikan_airing=True,
            kitsu_status="current",  # ignored
            has_kitsu=False,
        ) is True


# ---------------------------------------------------------------------------
# parse_broadcast_day
# ---------------------------------------------------------------------------

class TestParseBroadcastDay:
    def test_wednesdays_returns_2(self):
        assert parse_broadcast_day("Wednesdays") == 2

    def test_mondays_returns_0(self):
        assert parse_broadcast_day("Mondays") == 0

    def test_sundays_returns_6(self):
        assert parse_broadcast_day("Sundays") == 6

    def test_tuesdays_returns_1(self):
        assert parse_broadcast_day("Tuesdays") == 1

    def test_thursdays_returns_3(self):
        assert parse_broadcast_day("Thursdays") == 3

    def test_fridays_returns_4(self):
        assert parse_broadcast_day("Fridays") == 4

    def test_saturdays_returns_5(self):
        assert parse_broadcast_day("Saturdays") == 5

    def test_unknown_string_returns_none(self):
        assert parse_broadcast_day("Whenever") is None

    def test_empty_string_returns_none(self):
        assert parse_broadcast_day("") is None

    def test_none_returns_none(self):
        assert parse_broadcast_day(None) is None

    def test_lowercase_works(self):
        """parse_broadcast_day normalises to lowercase before lookup."""
        assert parse_broadcast_day("wednesdays") == 2

    def test_leading_trailing_whitespace_handled(self):
        assert parse_broadcast_day("  Fridays  ") == 4


# ---------------------------------------------------------------------------
# compute_broadcast_utc
# ---------------------------------------------------------------------------

class TestComputeBroadcastUtc:
    def test_wednesday_midnight_jst_is_tuesday_1500_utc(self):
        """Spec anchor: Wednesdays 00:00 Asia/Tokyo → Tuesday 15:00 UTC.

        JST is UTC+9, so 00:00 JST = 15:00 UTC the day before (Tuesday).
        Wednesday index = 2.
        """
        result = compute_broadcast_utc(2, "00:00", "Asia/Tokyo")

        # The result must be UTC-aware
        assert result.tzinfo is not None
        result_utc = result.astimezone(timezone.utc)

        # Weekday: Tuesday = 1 (Python datetime.weekday())
        assert result_utc.weekday() == 1, (
            f"Expected Tuesday (weekday=1), got weekday={result_utc.weekday()} "
            f"({result_utc.strftime('%A %Y-%m-%d %H:%M UTC')})"
        )
        assert result_utc.hour == 15
        assert result_utc.minute == 0

    def test_returns_utc_aware_datetime(self):
        """compute_broadcast_utc always returns a timezone-aware UTC datetime."""
        result = compute_broadcast_utc(0, "12:00", "Asia/Tokyo")
        assert result.tzinfo is not None

    def test_saturday_noon_utc_direct(self):
        """Saturday 12:00 UTC is Saturday 12:00 UTC (UTC±0 timezone)."""
        result = compute_broadcast_utc(5, "12:00", "UTC")
        result_utc = result.astimezone(timezone.utc)
        # Saturday = weekday 5
        assert result_utc.weekday() == 5
        assert result_utc.hour == 12
        assert result_utc.minute == 0


# ---------------------------------------------------------------------------
# classify_recheck — grace-period eligibility (simulcast-gap-recovery)
# ---------------------------------------------------------------------------

class TestClassifyRecheck:
    NOW = datetime(2026, 10, 12, tzinfo=timezone.utc)

    def test_still_airing_returns_airing(self):
        """is_simulcast=True always classifies as 'airing', regardless of have/expected."""
        row = {"is_simulcast": True, "episode_count": 12}
        assert classify_recheck(row, have=5, now=self.NOW, last_episode_aired_at=None) == "airing"

    def test_last_episode_aired_5_days_ago_with_gap_returns_grace(self):
        """Within the 14-day grace window and have < expected → 'grace'."""
        row = {"is_simulcast": False, "episode_count": 12}
        aired_at = self.NOW - timedelta(days=5)
        assert classify_recheck(row, have=11, now=self.NOW, last_episode_aired_at=aired_at) == "grace"

    def test_matching_counts_returns_none(self):
        """have == expected → no gap, not eligible even with a recent anchor."""
        row = {"is_simulcast": False, "episode_count": 12}
        aired_at = self.NOW - timedelta(days=3)
        assert classify_recheck(row, have=12, now=self.NOW, last_episode_aired_at=aired_at) is None

    def test_last_episode_aired_15_days_ago_with_gap_returns_expired(self):
        """Past the 14-day grace window with have < expected → 'expired'."""
        row = {"is_simulcast": False, "episode_count": 12}
        aired_at = self.NOW - timedelta(days=15)
        assert classify_recheck(row, have=10, now=self.NOW, last_episode_aired_at=aired_at) == "expired"

    def test_null_episode_count_excluded_from_grace_rule(self):
        """A null Jikan-expected count can never establish a grace-period gap."""
        row = {"is_simulcast": False, "episode_count": None}
        aired_at = self.NOW - timedelta(days=5)
        assert classify_recheck(row, have=5, now=self.NOW, last_episode_aired_at=aired_at) is None

    def test_null_last_episode_aired_at_excluded(self):
        """No known aired_at for our own episodes means we can't anchor the grace clock — exclude."""
        row = {"is_simulcast": False, "episode_count": 12}
        assert classify_recheck(row, have=5, now=self.NOW, last_episode_aired_at=None) is None

    def test_grace_boundary_at_exactly_14_days_is_still_grace(self):
        row = {"is_simulcast": False, "episode_count": 12}
        aired_at = self.NOW - timedelta(days=14)
        assert classify_recheck(row, have=10, now=self.NOW, last_episode_aired_at=aired_at) == "grace"

    def test_grace_boundary_just_past_14_days_is_expired(self):
        row = {"is_simulcast": False, "episode_count": 12}
        aired_at = self.NOW - timedelta(days=14, hours=1)
        assert classify_recheck(row, have=10, now=self.NOW, last_episode_aired_at=aired_at) == "expired"


# ---------------------------------------------------------------------------
# plan_backfill — backward gap detection within owned range (episode-gap-backfill)
# ---------------------------------------------------------------------------

class TestPlanBackfill:
    def test_leading_gap_daemons_like(self):
        """Episode 1 missing below current_max, no sibling offset involved."""
        own = set(range(2, 13))  # 2..12 ingested, episode 1 missing
        result = plan_backfill(
            own=own,
            expected=12,
            offset=0,
            sibling_nums=set(),
            source_nums=set(range(1, 13)),
            current_max=13,
        )
        assert result == {"inserts": [1], "skip_reason": None}

    def test_internal_gap(self):
        """Episode 3 missing among 1, 2, 4."""
        result = plan_backfill(
            own={1, 2, 4},
            expected=4,
            offset=0,
            sibling_nums=set(),
            source_nums={1, 2, 3, 4},
            current_max=5,
        )
        assert result == {"inserts": [3], "skip_reason": None}

    def test_cour_split_sibling_offset_is_not_a_gap(self):
        """own == expected inside the owned window → no inserts, by design."""
        own = set(range(13, 25))  # Part 2's own 12 episodes, fully ingested
        result = plan_backfill(
            own=own,
            expected=12,
            offset=12,
            sibling_nums=set(range(1, 13)),  # Part 1 cleanly owns 1..12
            source_nums=set(range(1, 25)),
            current_max=25,
        )
        assert result == {"inserts": [], "skip_reason": None}

    def test_ambiguous_sibling_offset_skips_with_no_inserts(self):
        """Sibling itself has a gap, so the offset boundary can't be trusted."""
        result = plan_backfill(
            own={13, 14},
            expected=12,
            offset=12,
            sibling_nums={1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12},  # sibling missing #3
            source_nums=set(range(1, 25)),
            current_max=15,
        )
        assert result == {"inserts": [], "skip_reason": "ambiguous_offset"}

    def test_own_numbers_outside_window_is_ambiguous(self):
        """An own number below the owned window means the offset itself is wrong."""
        result = plan_backfill(
            own={5, 13, 14},
            expected=12,
            offset=12,
            sibling_nums=set(range(1, 13)),
            source_nums=set(range(1, 25)),
            current_max=15,
        )
        assert result == {"inserts": [], "skip_reason": "ambiguous_offset"}

    def test_sibling_held_number_excluded_from_inserts(self):
        """A number already claimed by a sibling is never proposed for insertion."""
        result = plan_backfill(
            own={1, 2, 4},
            expected=4,
            offset=0,
            sibling_nums={3},
            source_nums={1, 2, 3, 4},
            current_max=5,
        )
        assert result == {"inserts": [], "skip_reason": None}

    def test_already_ingested_number_never_duplicated(self):
        """Re-running after the gap was already filled proposes zero inserts."""
        result = plan_backfill(
            own={1, 2, 3, 4},
            expected=4,
            offset=0,
            sibling_nums=set(),
            source_nums={1, 2, 3, 4},
            current_max=5,
        )
        assert result == {"inserts": [], "skip_reason": None}

    def test_restricted_to_numbers_below_current_max(self):
        """A missing number at/above current_max is not proposed for insertion."""
        result = plan_backfill(
            own={1, 2, 3},
            expected=4,
            offset=0,
            sibling_nums=set(),
            source_nums={1, 2, 3, 4},
            current_max=4,
        )
        assert result == {"inserts": [], "skip_reason": None}
