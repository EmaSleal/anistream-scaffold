"""Supabase query functions for the series table.

All functions return raw dicts from the DB (snake_case). Callers are
responsible for passing them through domain/series.map_series_row().
"""
import storage


def get_series_list(
    limit: int = 20,
    sort: str = "score",
    featured: bool | None = None,
    franchise_id: str | None = None,
    consolidated: bool = False,
    simulcast: bool = False,
) -> list[dict]:
    """Return a list of series rows.

    Args:
        limit: Maximum rows to return.
        sort: "score" (default, descending) or "title" (ascending).
        featured: If True, filter to is_featured=true.
        franchise_id: If set, filter to a specific franchise UUID.
        consolidated: If True, fetch enough rows for consolidation upstream.
            When consolidating, we bypass the limit and let the domain layer trim.
        simulcast: If True, filter to is_simulcast=true.
    """
    client = storage.get_client()
    query = client.table("series").select("*")

    if featured is True:
        query = query.eq("is_featured", True)

    if simulcast is True:
        query = query.eq("is_simulcast", True)

    if franchise_id:
        query = query.eq("franchise_id", franchise_id)

    if sort == "title":
        query = query.order("title", desc=False)
    else:
        query = query.order("score", desc=True)

    # When consolidated, fetch a larger set so consolidation has material to work with
    effective_limit = 500 if consolidated else limit
    query = query.limit(effective_limit)

    result = query.execute()
    return result.data or []


def get_series_by_id(series_id: str) -> dict | None:
    """Return a single series row by UUID, or None if not found."""
    client = storage.get_client()
    result = (
        client.table("series")
        .select("*")
        .eq("id", series_id)
        .maybe_single()
        .execute()
    )
    return result.data if result else None


def search_series(q: str, limit: int = 8) -> list[dict]:
    """Case-insensitive ILIKE search on the title column.

    Returns minimal projection: id, mal_id, title, slug.
    """
    client = storage.get_client()
    result = (
        client.table("series")
        .select("id, mal_id, title, slug")
        .ilike("title", f"%{q}%")
        .limit(limit)
        .execute()
    )
    return result.data or []


def get_stream_config(series_id: str) -> dict | None:
    """Return animeflv_disabled and animeav1_slug for the given series."""
    client = storage.get_client()
    result = (
        client.table("series")
        .select("animeflv_disabled, animeav1_slug")
        .eq("id", series_id)
        .maybe_single()
        .execute()
    )
    return result.data if result else None


def update_stream_source(series_id: str, animeav1_slug: str) -> bool:
    """Set animeav1_slug and animeflv_disabled=True for a series.

    Returns True if a row was updated, False if series_id not found.
    """
    client = storage.get_client()
    result = (
        client.table("series")
        .update({"animeav1_slug": animeav1_slug, "animeflv_disabled": True})
        .eq("id", series_id)
        .execute()
    )
    return bool(result.data)


def get_series_by_mal_ids(mal_ids: list[int]) -> list[dict]:
    """Return series rows matching the given MAL IDs, mapped to camelCase.

    Returns an empty list when mal_ids is empty.
    """
    if not mal_ids:
        return []
    from domain.series import map_series_row
    client = storage.get_client()
    result = (
        client.table("series")
        .select("*")
        .in_("mal_id", mal_ids)
        .execute()
    )
    return [map_series_row(row) for row in result.data or []]


def upsert_series_stub(mal_id: int) -> None:
    """Fetch full Jikan data for mal_id and upsert a metadata-only stub series.

    The stub will have animeflv_slug=None (no playable source yet).
    Errors are caught and logged; this function never raises.
    """
    import logging
    try:
        from fetcher import fetch_anime_by_id
        from normalizer import normalize
        import storage as storage_module
        raw = fetch_anime_by_id(mal_id)
        entry = normalize(raw)
        if entry:
            storage_module.upsert_many([entry])
    except Exception:
        logging.exception("upsert_series_stub failed for mal_id=%s", mal_id)


def get_series_by_franchise(franchise_id: str) -> list[dict]:
    """Return all members of a franchise ordered by season_order ascending."""
    client = storage.get_client()
    result = (
        client.table("series")
        .select("*")
        .eq("franchise_id", franchise_id)
        .order("season_order", desc=False)
        .execute()
    )
    return result.data or []
