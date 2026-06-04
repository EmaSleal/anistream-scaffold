"""Supabase query helpers for simulcast-related fields on the series table.

All functions return raw dicts from the DB (snake_case). Callers are
responsible for any domain transformations.
"""
from __future__ import annotations

from datetime import datetime, timezone
import storage


def get_series_simulcast_data(series_id: str) -> dict | None:
    """Return the simulcast-relevant columns for a series row.

    Fetches: id, kitsu_id, broadcast_day, broadcast_time, broadcast_timezone,
             episode_count, last_simulcast_check, animeflv_slug.

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
            "episode_count, last_simulcast_check, animeflv_slug"
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
