"""Supabase query functions for the watch_progress table.

The watch_progress table schema:
  (id, user_id, episode_id, series_id, progress_sec, duration_sec, updated_at)
  UNIQUE constraint on (user_id, episode_id).
"""
import logging
from datetime import datetime, timezone

import storage
from domain.series import map_episode_row

logger = logging.getLogger(__name__)


def _resolve_franchise_key(series_id: str) -> str:
    """Return franchise_id for series_id, or series_id as fallback. Never raises."""
    try:
        client = storage.get_client()
        result = (
            client.table("series")
            .select("franchise_id")
            .eq("id", series_id)
            .maybe_single()
            .execute()
        )
        if result and result.data and result.data.get("franchise_id"):
            return result.data["franchise_id"]
        return series_id
    except Exception:
        return series_id


def _resolve_next_episode_id(episode_id: str, series_id: str) -> str | None:
    """Return the ID of the next episode after episode_id in series_id, or None."""
    try:
        # Parse episode number from "{series_id}-ep-{N}" convention
        parts = episode_id.split("-ep-")
        if len(parts) >= 2:
            ep_num = int(parts[-1])
        else:
            # Fallback: query current episode's episode_number
            client = storage.get_client()
            cur_result = (
                client.table("episodes")
                .select("episode_number")
                .eq("id", episode_id)
                .maybe_single()
                .execute()
            )
            if not cur_result or not cur_result.data:
                return None
            ep_num = cur_result.data["episode_number"]

        client = storage.get_client()
        next_result = (
            client.table("episodes")
            .select("id")
            .eq("series_id", series_id)
            .eq("episode_number", ep_num + 1)
            .maybe_single()
            .execute()
        )
        if next_result and next_result.data:
            return next_result.data["id"]
        return None
    except Exception:
        return None


def _upsert_continue_watching(
    user_id: str,
    franchise_key: str,
    series_id: str,
    episode_id: str,
    progress_sec: int,
    next_episode_id: str | None,
    duration_sec: int = 0,
) -> None:
    """Best-effort upsert into user_continue_watching. Never raises."""
    try:
        client = storage.get_client()
        payload = {
            "user_id": user_id,
            "franchise_key": franchise_key,
            "series_id": series_id,
            "episode_id": episode_id,
            "progress_sec": int(progress_sec),
            "duration_sec": int(duration_sec),
            "next_episode_id": next_episode_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        client.table("user_continue_watching").upsert(
            payload, on_conflict="user_id,franchise_key"
        ).execute()
    except Exception:
        logger.warning("_upsert_continue_watching failed", exc_info=True)


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

    franchise_key = _resolve_franchise_key(series_id)
    next_ep_id = _resolve_next_episode_id(episode_id, series_id)
    _upsert_continue_watching(user_id, franchise_key, series_id, episode_id, int(progress_sec), next_ep_id, int(duration_sec))


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
    if next_ep_id is not None:
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
        franchise_key = _resolve_franchise_key(next_series_id or current_series_id)
        next_next_ep_id = _resolve_next_episode_id(next_ep_id, next_series_id or current_series_id)
        _upsert_continue_watching(user_id, franchise_key, next_series_id or current_series_id, next_ep_id, 0, next_next_ep_id, 0)


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
          ``id``, ``is_simulcast``, ``principal_slug``, ``broadcast_day``,
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
            "id, is_simulcast, principal_slug, broadcast_day, broadcast_time, "
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
            "principal_slug": row.get("principal_slug"),
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


def get_continue_watching(user_id: str, limit: int = 10) -> list[dict]:
    """Return a continue-watching list for the user from user_continue_watching.

    Fetches up to limit*2 rows (pre-filter budget), batch-fetches episode details,
    applies the 0.95 completion filter in Python, and returns at most limit items
    ordered by updated_at DESC.

    Returns [] on any error or when no rows exist.
    """
    try:
        client = storage.get_client()
        ucw_result = (
            client.table("user_continue_watching")
            .select("*")
            .eq("user_id", user_id)
            .order("updated_at", desc=True)
            .limit(limit * 2)
            .execute()
        )
        ucw_rows = ucw_result.data or []
    except Exception:
        logger.warning("get_continue_watching: failed to fetch UCW rows", exc_info=True)
        return []

    if not ucw_rows:
        return []

    episode_ids = [row["episode_id"] for row in ucw_rows if row.get("episode_id")]
    episode_rows = get_episodes_by_ids(episode_ids)
    episode_by_id = {ep["id"]: ep for ep in episode_rows}

    result: list[dict] = []
    for row in ucw_rows:
        ep = episode_by_id.get(row.get("episode_id"))
        if ep is None:
            continue
        # Exclude completed episodes (>= 0.95 of duration).
        # UCW duration_sec is authoritative (captured at watch time); fall back
        # to the episodes table value when the column is 0 or absent.
        duration_sec = row.get("duration_sec") or ep.get("duration_sec") or 0
        progress_sec = row.get("progress_sec", 0)
        if duration_sec > 0 and progress_sec / duration_sec >= 0.95:
            continue
        episode = map_episode_row(ep)
        if duration_sec > 0:
            episode["duration"] = duration_sec
        result.append({
            "episode": episode,
            "progressSeconds": progress_sec,
            "seriesId": row["series_id"],
        })
        if len(result) >= limit:
            break

    return result


def refresh_simulcast_next_episodes(
    series_id: str,
    prev_episode_id: str,
    new_episode_id: str,
) -> None:
    """Update next_episode_id for UCW rows where episode_id=prev and next_episode_id IS NULL.

    Called after a new simulcast episode is upserted so that users sitting on the
    previous last episode get their look-ahead pointer filled in. Never raises.
    """
    try:
        client = storage.get_client()
        client.table("user_continue_watching").update(
            {"next_episode_id": new_episode_id}
        ).eq("series_id", series_id).eq(
            "episode_id", prev_episode_id
        ).is_("next_episode_id", "null").execute()
    except Exception:
        logger.warning(
            "refresh_simulcast_next_episodes failed for series=%r prev=%r new=%r",
            series_id, prev_episode_id, new_episode_id,
            exc_info=True,
        )
