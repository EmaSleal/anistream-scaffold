"""Jikan metadata refresh for simulcast series.

Extracted from simulcast_routes.refresh_simulcast() to enable reuse by the
background scheduler job and to keep the route handler thin.

This module sits at the boundary between HTTP fetching and DB persistence.
It deliberately breaks the "pure domain" convention of domain/simulcast.py
because the refresh operation is inherently a side-effecting orchestration
step — not a pure computation.
"""
from __future__ import annotations

import logging
from typing import Any

from db.simulcast import update_simulcast_fields
from domain.simulcast import resolve_simulcast_status
from fetcher import fetch_anime_by_id, fetch_kitsu_series_status

logger = logging.getLogger(__name__)


def refresh_series_from_jikan(
    series_id: str,
    mal_id: int,
    kitsu_id: str | None,
) -> dict[str, Any]:
    """Refresh Jikan metadata for a series. Returns updated fields dict.

    Fetches airing status, episode count, and broadcast fields from Jikan for
    the given MAL ID. Optionally fetches Kitsu status when kitsu_id is supplied.
    Resolves is_simulcast, persists all updated fields via update_simulcast_fields(),
    and returns a summary dict suitable for logging by the caller.

    Jikan and Kitsu HTTP failures are handled fail-open: the function falls back
    to safe defaults (is_simulcast=False, no broadcast override) and still
    persists the resolved state. This matches the original route behaviour where
    a Jikan outage does not prevent the cooldown timestamp from updating.

    Args:
        series_id: The series DB id (slug-based primary key).
        mal_id:    The MyAnimeList ID used to query Jikan.
        kitsu_id:  Optional Kitsu anime ID; when present, Kitsu status is
                   fetched and stored alongside the Jikan fields.

    Returns:
        A dict with the following keys:
            is_simulcast (bool)            — resolved simulcast flag.
            jikan_episode_count (int|None) — episode count from Jikan, or None
                                             when the Jikan call failed.
            jikan_available (bool)         — True when Jikan data was fetched
                                             successfully.
            fields_updated (dict)          — columns written to the series row
                                             (excluding last_simulcast_check,
                                             which is stamped by the DB helper).

    Raises:
        Exception: propagated from update_simulcast_fields() on DB write failure.
                   The caller is responsible for logging or surfacing the error.
    """
    # Fetch Jikan airing + broadcast data (fail-open).
    jikan_airing = False
    jikan_episode_count: int | None = None
    jikan_broadcast: dict = {}
    jikan_aired_from: str | None = None
    jikan_available = False

    try:
        jikan_data = fetch_anime_by_id(mal_id)
        jikan_airing = bool(jikan_data.get("airing", False))
        ep_count = jikan_data.get("episodes")
        jikan_episode_count = int(ep_count) if ep_count else None
        jikan_broadcast = jikan_data.get("broadcast") or {}
        jikan_aired_from = (jikan_data.get("aired") or {}).get("from")
        jikan_available = True
    except Exception:
        logger.warning(
            "refresh_series_from_jikan: Jikan fetch failed for mal_id=%s — using defaults",
            mal_id,
        )

    # Optionally fetch Kitsu status.  fetch_kitsu_series_status() is itself
    # fail-open and always returns str | None without raising.
    kitsu_status: str | None = None
    if kitsu_id:
        kitsu_status = fetch_kitsu_series_status(kitsu_id)

    # Resolve whether the series is currently simulcasting.
    is_simulcast = resolve_simulcast_status(
        jikan_airing=jikan_airing,
        kitsu_status=kitsu_status,
        has_kitsu=bool(kitsu_id),
    )

    # Build the set of fields to write back.  Broadcast fields are only
    # included when Jikan actually returned them — avoids overwriting existing
    # DB values with None when Jikan is temporarily unavailable.
    fields_to_update: dict[str, Any] = {
        "is_simulcast": is_simulcast,
        "kitsu_status": kitsu_status,
    }
    if jikan_broadcast.get("day") is not None:
        fields_to_update["broadcast_day"] = jikan_broadcast["day"]
    if jikan_broadcast.get("time") is not None:
        fields_to_update["broadcast_time"] = jikan_broadcast["time"]
    if jikan_broadcast.get("timezone") is not None:
        fields_to_update["broadcast_timezone"] = jikan_broadcast["timezone"]
    if jikan_aired_from is not None:
        fields_to_update["aired_from"] = jikan_aired_from
    if jikan_episode_count is not None:
        fields_to_update["episode_count"] = jikan_episode_count

    # Persist — last_simulcast_check is stamped inside update_simulcast_fields.
    # Raises on DB failure; caller decides how to surface or log the error.
    update_simulcast_fields(series_id, fields_to_update)

    return {
        "is_simulcast": is_simulcast,
        "jikan_episode_count": jikan_episode_count,
        "jikan_available": jikan_available,
        "fields_updated": fields_to_update,
    }
