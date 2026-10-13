"""Pure domain functions for simulcast status resolution and broadcast scheduling.

No database or HTTP access here. All functions accept plain values and return
plain values so they remain fully unit-testable in isolation.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import logging

# Day name → 0-based index (Monday = 0, Sunday = 6)
_DAY_MAP: dict[str, int] = {
    "mondays": 0,
    "tuesdays": 1,
    "wednesdays": 2,
    "thursdays": 3,
    "fridays": 4,
    "saturdays": 5,
    "sundays": 6,
}


def resolve_simulcast_status(
    jikan_airing: bool,
    kitsu_status: str | None = None,  # unused — kept for call-site compatibility
    has_kitsu: bool = False,          # unused — kept for call-site compatibility
) -> bool:
    """Resolve whether a series is currently simulcasting.

    Source of truth: Jikan's ``airing`` field only.

    Kitsu is intentionally excluded because Kitsu assigns franchise-level IDs
    (the same kitsu_id to all seasons of a franchise). As a result,
    ``kitsu_status == "current"`` reflects whether any season of the franchise
    is airing, not the specific season being evaluated — making it an unreliable
    per-season signal.

    Args:
        jikan_airing:  The ``airing`` boolean from the Jikan API response for
                       this specific series (unique mal_id per season).
        kitsu_status:  Ignored. Kept for backward compatibility.
        has_kitsu:     Ignored. Kept for backward compatibility.

    Returns:
        True if Jikan reports the series as currently airing, False otherwise.
    """
    return jikan_airing


def parse_broadcast_day(day_str: str | None) -> int | None:
    """Map a Jikan broadcast day string to a 0-based weekday integer.

    Jikan returns day strings like "Mondays", "Tuesdays", …, "Sundays".
    This function normalises the input (strip, lowercase) and maps it to
    Python's weekday convention: Monday = 0, Sunday = 6.

    Args:
        day_str: The raw day string from Jikan (e.g. "Wednesdays"), or None.

    Returns:
        An integer in [0, 6], or None when the input is unknown or None.
    """
    if not day_str:
        return None
    return _DAY_MAP.get(day_str.strip().lower())


def compute_broadcast_utc(
    day: int,
    time_str: str,
    tz_str: str,
    now: datetime | None = None,
) -> datetime:
    """Convert a weekday + local time into the most recent matching UTC datetime.

    Args:
        day:      0-based weekday (Monday = 0, Sunday = 6).
        time_str: Time in "HH:MM" format (local to tz_str).
        tz_str:   IANA timezone name, e.g. "Asia/Tokyo".
        now:      Reference UTC datetime (defaults to current time). Pass
                  explicitly in tests to avoid real-clock dependency.

    Returns:
        A timezone-aware UTC datetime representing the broadcast moment.

    Raises:
        ValueError: If time_str cannot be parsed as "HH:MM".
        zoneinfo.ZoneInfoNotFoundError: If tz_str is not a valid IANA zone.
    """
    tz = ZoneInfo(tz_str)
    now_utc = now if now is not None else datetime.now(timezone.utc)
    now_local = now_utc.astimezone(tz)

    hour, minute = (int(p) for p in time_str.split(":"))

    # Find the most recent occurrence of the target weekday at the given time.
    # We look back up to 6 days to get the "current week" broadcast slot,
    # then use that as the reference point for the ±12h window check.
    days_back = (now_local.weekday() - day) % 7
    broadcast_local = now_local.replace(
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0,
    ).replace(tzinfo=tz)
    # Subtract the days offset to land on the target weekday
    broadcast_local = broadcast_local - timedelta(days=days_back)

    return broadcast_local.astimezone(timezone.utc)


def cooldown_elapsed(last_check: str | datetime | None, hours: int = 6) -> bool:
    """Return True when the simulcast cooldown window has elapsed.

    The cooldown prevents redundant scrapes for the same series. It elapses
    when ``last_check`` is None (never checked) or when the time since
    ``last_check`` exceeds ``hours``.

    Args:
        last_check: UTC timestamp of the last simulcast check. Accepts:
            - ``None`` → always returns True (no previous check).
            - A timezone-aware or naive ``datetime`` object (treated as UTC
              if naive).
            - An ISO 8601 string (e.g. ``"2026-06-04T10:00:00+00:00"``).
        hours: Cooldown window in hours. Default is 6.

    Returns:
        True if the cooldown has elapsed or no previous check exists,
        False if the last check was within the cooldown window.
    """
    if last_check is None:
        return True

    if isinstance(last_check, str):
        try:
            last_check = datetime.fromisoformat(last_check)
        except ValueError:
            # Unparseable string — treat as no previous check.
            return True

    # Normalise naive datetimes to UTC.
    if last_check.tzinfo is None:
        last_check = last_check.replace(tzinfo=timezone.utc)

    now_utc = datetime.now(timezone.utc)
    return (now_utc - last_check) >= timedelta(hours=hours)


def is_simulcast_candidate(
    *,
    is_simulcast: bool,
    progress_sec: float,
    duration_sec: float,
    last_aired_at: str | None,
    broadcast_day: str | None,
    broadcast_time: str | None,
    broadcast_timezone: str | None,
    now_utc: datetime,
) -> bool:
    """Return True when a CW progress row qualifies for a simulcast episode check.

    Evaluates three compound conditions — all must be true:

    1. **Simulcast flag**: ``is_simulcast`` must be True.
    2. **Caught-up**: the user has consumed at least 95 % of the episode, OR
       the remaining time is at most 120 seconds (for long-format shows where
       95 % may still leave minutes of credits).
    3. **Broadcast window**: the next expected episode should have aired by now.
       - When ``last_aired_at`` is provided, the next expected air time is
         ``aired_at + 7 days`` (weekly cadence assumption).
       - When ``last_aired_at`` is None, the next expected air time is computed
         from ``broadcast_day`` / ``broadcast_time`` / ``broadcast_timezone``
         via ``compute_broadcast_utc``. If any of these are missing or
         unparseable, the condition is treated as False.

    Args:
        is_simulcast:      Whether the series is flagged as currently airing.
        progress_sec:      User's current playback position in seconds.
        duration_sec:      Known total duration of the episode in seconds.
        last_aired_at:     ISO 8601 air date of the *current* (last-known)
                           episode, or None.
        broadcast_day:     Jikan broadcast day string (e.g. ``"Wednesdays"``),
                           or None.
        broadcast_time:    Local broadcast time as ``"HH:MM"``, or None.
        broadcast_timezone: IANA timezone name (e.g. ``"Asia/Tokyo"``), or None.
        now_utc:           Current UTC datetime (passed explicitly for testability).

    Returns:
        True if all conditions are met, False otherwise.
    """
    # Condition 1: simulcast flag.
    if not is_simulcast:
        return False

    # Condition 2: caught-up check.
    caught_up: bool
    if duration_sec > 0:
        ratio = progress_sec / duration_sec
        remaining = duration_sec - progress_sec
        caught_up = ratio >= 0.95 or remaining <= 120
    else:
        # duration unknown — we cannot confirm caught-up; do not trigger.
        caught_up = False

    if not caught_up:
        return False

    # Condition 3: broadcast window — next episode should have aired by now.
    if last_aired_at is not None:
        try:
            aired_dt = datetime.fromisoformat(last_aired_at)
        except ValueError:
            return False
        if aired_dt.tzinfo is None:
            aired_dt = aired_dt.replace(tzinfo=timezone.utc)
        next_expected = aired_dt + timedelta(days=7)
        return now_utc >= next_expected

    # Fallback: derive next expected from broadcast schedule.
    if not (broadcast_day and broadcast_time and broadcast_timezone):
        return False

    day_index = parse_broadcast_day(broadcast_day)
    if day_index is None:
        return False

    try:
        broadcast_utc = compute_broadcast_utc(day_index, broadcast_time, broadcast_timezone, now=now_utc)
    except Exception:
        logging.warning(
            "is_simulcast_candidate: could not compute broadcast UTC "
            "(day=%r, time=%r, tz=%r)",
            broadcast_day, broadcast_time, broadcast_timezone,
            exc_info=True,
        )
        return False

    return now_utc >= broadcast_utc


# ---------------------------------------------------------------------------
# Simulcast gap recovery: grace-period eligibility + backward gap backfill.
#
# Pure decision logic only. The DB layer supplies plain facts (rows, owned
# episode numbers, sibling-claimed episode numbers); the cron job and the
# read-only simulate script both call these same functions so a CSV review
# validates the exact code that will later write.
# ---------------------------------------------------------------------------


def _as_aware_utc(value: datetime | str) -> datetime:
    """Normalise a datetime or ISO string to a timezone-aware UTC datetime."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def _owned_window(offset: int, expected: int) -> set[int]:
    """Return the episode-number window a series owns on a shared source
    listing: ``(offset, offset + expected]`` — exclusive lower bound (the
    sibling's claimed range), inclusive upper bound (own expected count).
    """
    return set(range(offset + 1, offset + expected + 1))


def classify_recheck(
    row: dict,
    have: int,
    now: datetime,
    grace_days: int = 14,
) -> str | None:
    """Classify whether a series is due for a simulcast recheck.

    Returns one of:
        - ``"airing"``:  ``row["is_simulcast"]`` is True. Behaves exactly as
          today — unconditionally eligible.
        - ``"grace"``:   Finished airing within ``grace_days`` and still has
          fewer ingested episodes (``have``) than Jikan expects
          (``row["episode_count"]``).
        - ``"expired"``: The grace window has elapsed and a gap still exists.
          Eligibility stops here; the gap is surfaced for admin review by
          the caller (not by this function).
        - ``None``:      Not eligible — either airing is False with no gap,
          or the inputs needed to establish a gap are missing.

    Args:
        row: Plain dict with ``is_simulcast`` (bool), ``simulcast_ended_at``
            (datetime | ISO str | None — stamped by the DB trigger when
            ``is_simulcast`` flips True -> False), and ``episode_count``
            (int | None — Jikan's expected episode count for this series).
        have: This series' own ingested episode count.
        now: Reference UTC datetime (passed explicitly for testability).
        grace_days: Grace window length in days. Default 14.
    """
    if row.get("is_simulcast"):
        return "airing"

    ended_at = row.get("simulcast_ended_at")
    expected = row.get("episode_count")
    if ended_at is None or expected is None:
        return None

    if have >= expected:
        return None

    ended_at = _as_aware_utc(ended_at)
    elapsed = now - ended_at
    if elapsed <= timedelta(days=grace_days):
        return "grace"
    return "expired"


def plan_backfill(
    own: set[int],
    expected: int,
    offset: int,
    sibling_nums: set[int],
    source_nums: set[int],
    current_max: int,
) -> dict:
    """Plan which missing episode numbers to backfill for a series.

    Computes ``inserts = (window ∩ source_nums) − own − sibling_nums``,
    restricted to numbers below ``current_max`` and capped at
    ``expected − len(own)`` remaining slots, where ``window`` is the
    series' own owned range ``(offset, offset + expected]``.

    Refuses to propose any insert (returning ``skip_reason="ambiguous_offset"``
    instead) when the inputs can't establish a trustworthy boundary:
        - any number in ``own`` falls outside the owned window — the offset
          itself must be wrong, or
        - ``sibling_nums`` is not a clean, contiguous ``1..offset`` prefix —
          the sibling has its own gap, so the offset derived from its
          ingested count can't be trusted as a clean boundary.

    An understated offset would shift the window into a sibling's claimed
    range, which is exactly the failure mode this guards against.

    Args:
        own: This series' own ingested episode numbers (in shared-source
            numbering, i.e. already offset-relative to a cour-split sibling
            if one exists).
        expected: This series' own Jikan-expected episode count.
        offset: Episode numbers claimed by a franchise sibling that shares
            the same source slug (same semantics as
            ``routes/ingest_routes.py::_claimed_episode_offset`` — the
            sibling's own ingested episode count).
        sibling_nums: Episode numbers claimed by that sibling.
        source_nums: Episode numbers currently listed on the shared source
            page.
        current_max: This series' current max known episode number; only
            numbers strictly below this are eligible for backfill (the
            forward-scrape path already owns numbers at/above it).

    Returns:
        ``{"inserts": list[int], "skip_reason": str | None}``. ``inserts``
        is sorted ascending. ``skip_reason`` is ``"ambiguous_offset"`` or
        ``None``.
    """
    own = set(own)
    sibling_nums = set(sibling_nums)
    source_nums = set(source_nums)

    window = _owned_window(offset, expected)

    if any(n not in window for n in own):
        return {"inserts": [], "skip_reason": "ambiguous_offset"}

    if offset > 0 and sibling_nums != set(range(1, offset + 1)):
        return {"inserts": [], "skip_reason": "ambiguous_offset"}

    missing = (window & source_nums) - own - sibling_nums
    missing = {n for n in missing if n < current_max}

    remaining_slots = max(expected - len(own), 0)
    inserts = sorted(missing)[:remaining_slots]

    return {"inserts": inserts, "skip_reason": None}
