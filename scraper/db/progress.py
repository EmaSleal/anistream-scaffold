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
