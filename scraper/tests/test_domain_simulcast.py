"""Unit tests for scraper/domain/simulcast.py.

All tests use pure values — no database or HTTP access.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import timezone
import pytest
from domain.simulcast import (
    resolve_simulcast_status,
    parse_broadcast_day,
    compute_broadcast_utc,
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

    def test_kitsu_finished_returns_false(self):
        """jikan airing but kitsu finished → False."""
        assert resolve_simulcast_status(
            jikan_airing=True,
            kitsu_status="finished",
            has_kitsu=True,
        ) is False

    def test_kitsu_upcoming_returns_false(self):
        """jikan airing but kitsu upcoming (not 'current') → False."""
        assert resolve_simulcast_status(
            jikan_airing=True,
            kitsu_status="upcoming",
            has_kitsu=True,
        ) is False

    def test_kitsu_none_with_has_kitsu_returns_false(self):
        """kitsu_status is None despite has_kitsu=True (fetch failed) → False."""
        assert resolve_simulcast_status(
            jikan_airing=True,
            kitsu_status=None,
            has_kitsu=True,
        ) is False

    def test_no_kitsu_id_jikan_true_returns_true(self):
        """Confirmed override: no kitsu_id + jikan airing → True (fallback to jikan alone)."""
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

    def test_no_kitsu_id_ignores_kitsu_status(self):
        """When has_kitsu=False, kitsu_status is irrelevant; jikan alone decides."""
        assert resolve_simulcast_status(
            jikan_airing=True,
            kitsu_status="current",  # should be ignored
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
