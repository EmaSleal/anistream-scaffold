"""Pure domain functions for simulcast status resolution and broadcast scheduling.

No database or HTTP access here. All functions accept plain values and return
plain values so they remain fully unit-testable in isolation.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

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
    kitsu_status: str | None,
    has_kitsu: bool,
) -> bool:
    """Resolve whether a series is currently simulcasting.

    Rules:
    - When has_kitsu is True:  True iff jikan_airing AND kitsu_status == "current".
    - When has_kitsu is False: returns jikan_airing alone (Kitsu cannot confirm or
      deny; we fall back to the Jikan airing flag as the sole source of truth).

    Args:
        jikan_airing:  The ``airing`` boolean from the Jikan API response.
        kitsu_status:  The ``attributes.status`` string from Kitsu, or None.
        has_kitsu:     True when a kitsu_id is present for this series.

    Returns:
        True if the series is considered actively simulcasting, False otherwise.
    """
    if not has_kitsu:
        return jikan_airing
    return jikan_airing and kitsu_status == "current"


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


def compute_broadcast_utc(day: int, time_str: str, tz_str: str) -> datetime:
    """Convert a weekday + local time into the next matching UTC datetime.

    The function finds the closest upcoming occurrence of ``day`` (0 = Monday)
    from the current moment, combines it with ``time_str``, interprets the
    result in ``tz_str``, then converts to UTC.

    This is used to compute the centre of the ±12-hour broadcast window.

    Args:
        day:      0-based weekday (Monday = 0, Sunday = 6).
        time_str: Time in "HH:MM" format (local to tz_str).
        tz_str:   IANA timezone name, e.g. "Asia/Tokyo".

    Returns:
        A timezone-aware UTC datetime representing the broadcast moment.

    Raises:
        ValueError: If time_str cannot be parsed as "HH:MM".
        zoneinfo.ZoneInfoNotFoundError: If tz_str is not a valid IANA zone.
    """
    tz = ZoneInfo(tz_str)
    now_utc = datetime.now(timezone.utc)
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
