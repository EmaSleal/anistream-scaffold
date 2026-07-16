"""Supabase query helpers for simulcast-related fields on the series table.

All functions return raw dicts from the DB (snake_case). Callers are
responsible for any domain transformations.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import storage

_CR_TZ = ZoneInfo("America/Costa_Rica")


def get_series_simulcast_data(series_id: str) -> dict | None:
    """Return the simulcast-relevant columns for a series row.

    Fetches: id, kitsu_id, broadcast_day, broadcast_time, broadcast_timezone,
             episode_count, last_simulcast_check, principal_slug.

    Args:
        series_id: The series ``id`` (slug-based primary key).

    Returns:
        A dict with the listed keys, or None if no row matches.
    """
    client = storage.get_client()
    result = (
        client.table("series")
        .select(
            "id, kitsu_id, broadcast_day, broadcast_time, broadcast_timezone, "
            "episode_count, last_simulcast_check, principal_slug"
        )
        .eq("id", series_id)
        .maybe_single()
        .execute()
    )
    return result.data if result else None


def update_simulcast_fields(series_id: str, fields: dict) -> None:
    """PATCH only the provided fields plus last_simulcast_check = now().

    Args:
        series_id: The series ``id`` to update.
        fields:    A dict of column→value pairs to update. Only keys present
                   in this dict are written; ``last_simulcast_check`` is always
                   set to the current UTC timestamp.
    """
    client = storage.get_client()
    payload = {
        **fields,
        "last_simulcast_check": datetime.now(timezone.utc).isoformat(),
    }
    client.table("series").update(payload).eq("id", series_id).execute()


# ---------------------------------------------------------------------------
# Simulcast job helpers
# ---------------------------------------------------------------------------


def _cr_date(iso_str: str) -> date | None:
    """Parse an ISO 8601 string into a calendar date in Costa Rica timezone.

    Args:
        iso_str: An ISO 8601 timestamp string (e.g. ``"2026-06-27T10:00:00+00:00"``).

    Returns:
        The local date in ``America/Costa_Rica``, or None when the string
        cannot be parsed.
    """
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(_CR_TZ).date()
    except Exception:
        return None


def get_due_simulcast_series() -> list[dict]:
    """Return simulcast series not checked within the last 4 hours.

    Fetches all rows where ``is_simulcast=True`` and ``principal_slug IS NOT
    NULL`` (AnimeAV1 integration marker), then applies a Python-side filter
    that excludes any series whose ``last_simulcast_check`` is within the
    4-hour cooldown window. The time-based cooldown (rather than once-per-day)
    lets the job re-check later in the same day when AnimeAV1 hasn't posted
    the episode yet at the time of the first pass.

    A single batched ``episodes`` query resolves ``max_episode_number`` for all
    surviving candidates (same technique as ``db.progress.get_series_simulcast_meta``).

    Returns:
        A list of dicts with keys: ``id``, ``principal_slug``, ``mal_id``,
        ``kitsu_id``, ``max_episode_number`` (int or None).
    """
    client = storage.get_client()

    # Fetch all simulcast series that have a principal_slug (AnimeAV1-integrated).
    result = (
        client.table("series")
        .select("id, principal_slug, mal_id, kitsu_id, last_simulcast_check")
        .eq("is_simulcast", True)
        .not_.is_("principal_slug", "null")
        .execute()
    )
    rows = result.data or []

    # Filter out series checked within the last 4 hours.
    # A time-based cooldown (rather than once-per-day) lets the scheduler
    # re-check later the same day when an episode wasn't on AnimeAV1 yet at
    # the time of the previous check (AnimeAV1 typically lags 2–6 h after
    # the Japanese broadcast).
    now_utc = datetime.now(timezone.utc)
    _cooldown = timedelta(hours=4)
    candidates = []
    for row in rows:
        last_check = row.get("last_simulcast_check")
        if last_check is not None:
            try:
                last_dt = datetime.fromisoformat(last_check)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                if now_utc - last_dt < _cooldown:
                    continue  # checked within cooldown window — skip
            except Exception:
                pass
        candidates.append(row)

    if not candidates:
        return []

    # Resolve max_episode_number per candidate via a single batched episodes query.
    candidate_ids = [c["id"] for c in candidates]
    eps_result = (
        client.table("episodes")
        .select("series_id, episode_number")
        .in_("series_id", candidate_ids)
        .execute()
    )

    max_ep_map: dict[str, int | None] = {cid: None for cid in candidate_ids}
    for ep in eps_result.data or []:
        sid = ep.get("series_id")
        ep_num = ep.get("episode_number")
        if sid in max_ep_map and ep_num is not None:
            current = max_ep_map[sid]
            if current is None or ep_num > current:
                max_ep_map[sid] = ep_num

    return [
        {
            "id": row["id"],
            "principal_slug": row["principal_slug"],
            "mal_id": row.get("mal_id"),
            "kitsu_id": row.get("kitsu_id"),
            "max_episode_number": max_ep_map.get(row["id"]),
        }
        for row in candidates
    ]
