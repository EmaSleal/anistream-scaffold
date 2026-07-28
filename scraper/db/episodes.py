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


def get_recent_simulcast_episodes(limit: int = 20) -> list[dict]:
    """Return recently aired simulcast episodes ordered by effective date DESC.

    Uses two queries to avoid unreliable PostgREST embedded-resource filters:
    1. Fetch all simulcast series IDs.
    2. Fetch episodes for those series, including created_at as a date fallback.

    Sort key: aired_at if set, otherwise created_at[:10]. Episodes with neither
    are excluded. Returns at most `limit` rows.
    """
    client = storage.get_client()

    # Step 1: get simulcast series
    series_result = (
        client.table("series")
        .select("id, title, thumbnail_url")
        .eq("is_simulcast", True)
        .execute()
    )
    series_rows = series_result.data or []
    if not series_rows:
        return []

    series_map = {s["id"]: s for s in series_rows}
    series_ids = list(series_map.keys())

    # Step 2: fetch recent episodes for those series
    # Fetch more than limit to account for Python-side sorting + dedup
    eps_result = (
        client.table("episodes")
        .select("id, series_id, episode_number, title, thumbnail_url, animeflv_slug, created_at")
        .in_("series_id", series_ids)
        .order("created_at", desc=True)
        .limit(limit * 4)
        .execute()
    )
    episodes = eps_result.data or []

    # Attach series data and compute effective_date for sorting
    enriched = []
    for ep in episodes:
        effective = (ep.get("created_at") or "")[:10]
        if not effective:
            continue
        ep["series"] = series_map.get(ep.get("series_id"), {})
        ep["_effective_date"] = effective
        enriched.append(ep)

    enriched.sort(key=lambda e: (e["_effective_date"], e.get("episode_number", 0)), reverse=True)

    # One episode per series — keep the most recent (first after sort)
    seen: set[str] = set()
    deduped = []
    for ep in enriched:
        sid = ep.get("series_id")
        if sid not in seen:
            seen.add(sid)
            deduped.append(ep)

    return deduped[:limit]


def get_adjacent_episodes(series_id: str, episode_number: int) -> dict:
    """Return prev and next episode rows (or None) around episode_number.

    Falls back to the adjacent series in the same franchise when the boundary
    episode (first or last) has no neighbour within the current series.
    """
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

    prev_ep = prev_result.data if prev_result else None
    next_ep = next_result.data if next_result else None

    # Cross-franchise boundary fallback: only query when actually needed
    need_franchise = (next_ep is None) or (prev_ep is None and episode_number <= 1)
    if need_franchise:
        series_row = (
            client.table("series")
            .select("franchise_id, season_order")
            .eq("id", series_id)
            .maybe_single()
            .execute()
        )
        franchise_id = None
        season_order = None
        if series_row and series_row.data:
            franchise_id = series_row.data.get("franchise_id")
            season_order = series_row.data.get("season_order")

        if franchise_id and season_order is not None:
            if next_ep is None:
                next_series = (
                    client.table("series")
                    .select("id")
                    .eq("franchise_id", franchise_id)
                    .eq("season_order", season_order + 1)
                    .maybe_single()
                    .execute()
                )
                if next_series and next_series.data:
                    first_ep = (
                        client.table("episodes")
                        .select("*, series:series_id(title)")
                        .eq("series_id", next_series.data["id"])
                        .order("episode_number", desc=False)
                        .limit(1)
                        .execute()
                    )
                    next_ep = first_ep.data[0] if first_ep and first_ep.data else None

            if prev_ep is None and episode_number <= 1:
                prev_series = (
                    client.table("series")
                    .select("id")
                    .eq("franchise_id", franchise_id)
                    .eq("season_order", season_order - 1)
                    .maybe_single()
                    .execute()
                )
                if prev_series and prev_series.data:
                    last_ep = (
                        client.table("episodes")
                        .select("*, series:series_id(title)")
                        .eq("series_id", prev_series.data["id"])
                        .order("episode_number", desc=True)
                        .limit(1)
                        .execute()
                    )
                    prev_ep = last_ep.data[0] if last_ep and last_ep.data else None

    return {
        "prev": prev_ep,
        "next": next_ep,
    }
