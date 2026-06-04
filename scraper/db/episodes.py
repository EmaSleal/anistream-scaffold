"""Supabase query functions for the episodes table.

All functions return raw dicts from the DB (snake_case). Callers pass them
through domain/series.map_episode_row().
"""
import storage


def get_episodes_by_series(series_id: str) -> list[dict]:
    """Return all episodes for a series, ordered by episode_number ASC."""
    client = storage.get_client()
    result = (
        client.table("episodes")
        .select("*, series:series_id(title)")
        .eq("series_id", series_id)
        .order("episode_number", desc=False)
        .execute()
    )
    return result.data or []


def get_episode_for_watch(watch_id: str) -> dict | None:
    """Dual-lookup: try animeflv_slug first, then UUID.

    Returns the episode row with the series title joined, or None.
    """
    client = storage.get_client()

    # Attempt 1: animeflv_slug match
    result = (
        client.table("episodes")
        .select("*, series:series_id(title)")
        .eq("animeflv_slug", watch_id)
        .maybe_single()
        .execute()
    )
    if result and result.data:
        return result.data

    # Attempt 2: UUID match
    result = (
        client.table("episodes")
        .select("*, series:series_id(title)")
        .eq("id", watch_id)
        .maybe_single()
        .execute()
    )
    return result.data if result else None


def get_adjacent_episodes(series_id: str, episode_number: int) -> dict:
    """Return prev and next episode rows (or None) around episode_number."""
    client = storage.get_client()

    prev_result = (
        client.table("episodes")
        .select("*, series:series_id(title)")
        .eq("series_id", series_id)
        .eq("episode_number", episode_number - 1)
        .maybe_single()
        .execute()
    )

    next_result = (
        client.table("episodes")
        .select("*, series:series_id(title)")
        .eq("series_id", series_id)
        .eq("episode_number", episode_number + 1)
        .maybe_single()
        .execute()
    )

    return {
        "prev": prev_result.data if prev_result else None,
        "next": next_result.data if next_result else None,
    }
