"""Supabase query functions for the watch_progress table.

The watch_progress table schema:
  (id, user_id, episode_id, series_id, progress_sec, duration_sec, updated_at)
  UNIQUE constraint on (user_id, episode_id).
"""
from datetime import datetime, timezone

import storage


def upsert_progress(
    user_id: str,
    episode_id: str,
    series_id: str,
    progress_sec: float,
    duration_sec: float,
) -> None:
    """Insert or replace a watch_progress row on conflict (user_id, episode_id)."""
    client = storage.get_client()
    client.table("watch_progress").upsert(
        {
            "user_id": user_id,
            "episode_id": episode_id,
            "series_id": series_id,
            "progress_sec": int(progress_sec),
            "duration_sec": int(duration_sec),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="user_id,episode_id",
    ).execute()


def advance_episode(
    user_id: str,
    current_ep_id: str,
    current_series_id: str,
    duration_sec: float,
    next_ep_id: str,
    next_series_id: str,
) -> None:
    """Mark current episode as fully watched and seed the next episode at 0.

    Calls upsert_progress twice in sequence:
      1. current episode at progress_sec=duration_sec (fully watched)
      2. next episode at progress_sec=0 (seeds it in Continue Watching)
    """
    upsert_progress(
        user_id=user_id,
        episode_id=current_ep_id,
        series_id=current_series_id,
        progress_sec=float(duration_sec),
        duration_sec=float(duration_sec),
    )
    # Seed next episode at progress_sec=1 (not 0) so get_recent_progress
    # (.gt("progress_sec", 0)) picks it up for the Continue Watching row.
    client = storage.get_client()
    client.table("watch_progress").upsert(
        {
            "user_id": user_id,
            "episode_id": next_ep_id,
            "series_id": next_series_id,
            "progress_sec": 1,
            "duration_sec": 0,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="user_id,episode_id",
    ).execute()


def get_episode_progress(user_id: str, episode_id: str) -> float:
    """Return progress_sec for the (user_id, episode_id) row, or 0 if absent."""
    client = storage.get_client()
    result = (
        client.table("watch_progress")
        .select("progress_sec")
        .eq("user_id", user_id)
        .eq("episode_id", episode_id)
        .maybe_single()
        .execute()
    )
    if result and result.data:
        return result.data.get("progress_sec", 0) or 0
    return 0


def get_recent_progress(user_id: str, limit: int = 30) -> list[dict]:
    """Return the most-recent progress rows where progress_sec > 0.

    Ordered by updated_at DESC, capped at `limit` rows.
    """
    client = storage.get_client()
    result = (
        client.table("watch_progress")
        .select("episode_id, series_id, progress_sec, duration_sec, updated_at")
        .eq("user_id", user_id)
        .gt("progress_sec", 0)
        .order("updated_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


def get_series_franchise_map(series_ids: list[str]) -> dict[str, str]:
    """Return a mapping of series_id -> franchise_id (fallback to series_id).

    Used by the continue-watching domain logic for franchise deduplication.
    """
    if not series_ids:
        return {}
    client = storage.get_client()
    result = (
        client.table("series")
        .select("id, franchise_id")
        .in_("id", series_ids)
        .execute()
    )
    mapping: dict[str, str] = {}
    for row in result.data or []:
        sid = row["id"]
        mapping[sid] = row.get("franchise_id") or sid
    return mapping


def get_mal_ids_for_series(series_ids: list[str]) -> dict[str, int]:
    """Return a mapping of series_id -> mal_id for the given series IDs.

    Skips any series row where mal_id IS NULL.
    Returns an empty dict when series_ids is empty.
    """
    if not series_ids:
        return {}
    client = storage.get_client()
    result = (
        client.table("series")
        .select("id, mal_id")
        .in_("id", series_ids)
        .not_.is_("mal_id", "null")
        .execute()
    )
    return {row["id"]: row["mal_id"] for row in result.data or []}


def get_series_by_ids(series_ids: list[str]) -> list[dict]:
    """Return full series rows for the given IDs (snake_case, for map_series_row)."""
    if not series_ids:
        return []
    client = storage.get_client()
    result = (
        client.table("series")
        .select("*")
        .in_("id", series_ids)
        .execute()
    )
    return result.data or []


def get_episodes_by_ids(episode_ids: list[str]) -> list[dict]:
    """Return episode rows (with series title join) for the given IDs."""
    if not episode_ids:
        return []
    client = storage.get_client()
    result = (
        client.table("episodes")
        .select("*, series:series_id(title)")
        .in_("id", episode_ids)
        .execute()
    )
    return result.data or []


def get_series_simulcast_meta(series_ids: list[str]) -> dict[str, dict]:
    """Return simulcast-relevant metadata for the given series IDs.

    Executes a single batched query against the ``series`` table for all
    requested IDs and also computes the maximum known episode number for
    each series from the ``episodes`` table.

    Args:
        series_ids: List of series ID strings to look up.

    Returns:
        A dict keyed by series_id. Each value contains:
          ``id``, ``is_simulcast``, ``animeflv_slug``, ``broadcast_day``,
          ``broadcast_time``, ``broadcast_timezone``, ``last_simulcast_check``,
          ``max_episode_number`` (int | None — the highest episode_number in DB
          for that series, or None if no episodes exist).
        Returns an empty dict when ``series_ids`` is empty.
    """
    if not series_ids:
        return {}

    client = storage.get_client()

    # Fetch simulcast fields from series table.
    series_result = (
        client.table("series")
        .select(
            "id, is_simulcast, animeflv_slug, broadcast_day, broadcast_time, "
            "broadcast_timezone, last_simulcast_check"
        )
        .in_("id", series_ids)
        .execute()
    )

    meta: dict[str, dict] = {}
    for row in series_result.data or []:
        sid = row["id"]
        meta[sid] = {
            "id": sid,
            "is_simulcast": row.get("is_simulcast") or False,
            "animeflv_slug": row.get("animeflv_slug"),
            "broadcast_day": row.get("broadcast_day"),
            "broadcast_time": row.get("broadcast_time"),
            "broadcast_timezone": row.get("broadcast_timezone"),
            "last_simulcast_check": row.get("last_simulcast_check"),
            "max_episode_number": None,
        }

    if not meta:
        return meta

    # Fetch max episode_number per series in a single query.
    eps_result = (
        client.table("episodes")
        .select("series_id, episode_number")
        .in_("series_id", list(meta.keys()))
        .execute()
    )

    for ep in eps_result.data or []:
        sid = ep.get("series_id")
        ep_num = ep.get("episode_number")
        if sid in meta and ep_num is not None:
            current_max = meta[sid]["max_episode_number"]
            if current_max is None or ep_num > current_max:
                meta[sid]["max_episode_number"] = ep_num

    return meta
