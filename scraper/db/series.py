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
    genre: str | None = None,
    year: int | None = None,
    search: str | None = None,
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
        genre: If set, filter to series containing this genre (case-sensitive).
        year: If set (and non-zero), filter to series with this release year.
        search: If set, filter by ILIKE title match.
    """
    client = storage.get_client()
    query = client.table("series").select("*")

    if featured is True:
        query = query.eq("is_featured", True)

    if simulcast is True:
        query = query.eq("is_simulcast", True)

    if franchise_id:
        query = query.eq("franchise_id", franchise_id)

    if genre:
        query = query.contains("genres", [genre])

    if year:
        query = query.eq("year", year)

    if search:
        query = query.ilike("title", f"%{search}%")

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
    """Return animeflv_disabled and fallback_slug for the given series."""
    client = storage.get_client()
    result = (
        client.table("series")
        .select("animeflv_disabled, fallback_slug")
        .eq("id", series_id)
        .maybe_single()
        .execute()
    )
    return result.data if result else None


def update_stream_source(series_id: str, fallback_slug: str, animeflv_disabled: bool = False) -> bool:
    """Set fallback_slug for a series. animeflv_disabled defaults to False.

    Returns True if a row was updated, False if series_id not found.
    """
    client = storage.get_client()
    result = (
        client.table("series")
        .update({"fallback_slug": fallback_slug, "animeflv_disabled": animeflv_disabled})
        .eq("id", series_id)
        .execute()
    )
    return bool(result.data)


def reset_animeflv(series_id: str) -> bool:
    """Re-enable animeflv for a series (set animeflv_disabled=False).

    Returns True if a row was updated, False if series_id not found.
    """
    client = storage.get_client()
    result = (
        client.table("series")
        .update({"animeflv_disabled": False})
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


def upsert_series_stub(mal_id: int, entry: dict | None = None) -> None:
    """Fetch full Jikan data for mal_id and upsert a metadata-only stub series.

    If entry is provided (from seasons/now), use it as a fallback when individual
    fetch fails. The stub will have animeflv_slug=None (no playable source yet).
    Errors are caught and logged; this function never raises.
    """
    import logging
    try:
        from fetcher import fetch_anime_by_id
        from normalizer import normalize
        import storage as storage_module
        raw = None
        try:
            raw = fetch_anime_by_id(mal_id)
        except Exception as e:
            logging.warning("fetch_anime_by_id failed for mal_id=%s, using fallback entry", mal_id)
            raw = entry

        if raw:
            normalized = normalize(raw)
            if normalized:
                storage_module.upsert_many([normalized])
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


def get_recommended_mal_ids(mal_id: int) -> list[int] | None:
    """Return persisted recommendation IDs for the series with this mal_id.

    Tri-state return:
      None  — column IS NULL (never fetched from Jikan).
      []    — fetched; genuinely empty (no recommendations).
      [ids] — fetched; list of recommended MAL IDs.
    Returns None if no series row exists for this mal_id.
    """
    client = storage.get_client()
    result = (
        client.table("series")
        .select("recommended_mal_ids")
        .eq("mal_id", mal_id)
        .maybe_single()
        .execute()
    )
    if not result or not result.data:
        return None
    return result.data.get("recommended_mal_ids")  # None | list[int]


def save_recommended_mal_ids(mal_id: int, mal_ids: list[int]) -> None:
    """Persist recommendation IDs for the series with this mal_id.

    Pass [] to record 'fetched, empty'. Never call with [] on a Jikan failure
    (caller is responsible for distinguishing empty from error).
    Uses UPDATE (not upsert) — the row must already exist.
    """
    client = storage.get_client()
    client.table("series").update(
        {"recommended_mal_ids": mal_ids}
    ).eq("mal_id", mal_id).execute()


def warm_recommendations(mal_ids: list[int]) -> None:
    """For each mal_id whose recommended_mal_ids is NULL, fetch Jikan and persist.

    Designed to run inside a daemon thread. Throttled, fail-open, never raises.
    Skips mal_ids that already have a non-NULL value (including []).
    Uses a local import of fetch_recommendations to avoid circular imports
    (same pattern as upsert_series_stub).
    """
    import logging
    import time
    from fetcher import fetch_recommendations
    for mid in mal_ids:
        try:
            if get_recommended_mal_ids(mid) is not None:
                continue  # already warm or confirmed empty — skip
            entries = fetch_recommendations(mid)
            if not entries:
                continue  # fail-open: leave NULL so next request retries
            rec_ids = [
                e.get("entry", {}).get("mal_id")
                for e in entries
                if e.get("entry", {}).get("mal_id")
            ]
            save_recommended_mal_ids(mid, rec_ids)
        except Exception:
            logging.exception("warm_recommendations failed for mal_id=%s", mid)
        finally:
            time.sleep(0.5)  # Jikan rate-limit courtesy — runs on every iteration
