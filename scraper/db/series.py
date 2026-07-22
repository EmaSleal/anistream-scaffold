"""Supabase query functions for the series table.

All functions return raw dicts from the DB (snake_case). Callers are
responsible for passing them through domain/series.map_series_row().
"""
import logging

import storage

logger = logging.getLogger(__name__)

# Columns fetched for catalog/browse endpoints (consolidated=True).
# Excludes streaming config (principal_slug, fallback_slug, animeflv_*) and
# operational metadata (broadcast_*, aired_from, kitsu_status, last_simulcast_check)
# that catalog callers never read, cutting raw row size in Python memory.
_CATALOG_SELECT = (
    "id, mal_id, title, slug, description, thumbnail_url, banner_url, "
    "rating, genres, audio_formats, season_count, episode_count, year, "
    "is_simulcast, is_featured, score, "
    "franchise_id, season_order, franchise_relation, media_type"
)


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
    has_banner: bool = False,
) -> list[dict]:
    """Return a list of series rows.

    Args:
        limit: Maximum rows to return.
        sort: "score" (default, descending) or "title" (ascending).
        featured: If True, filter to is_featured=true.
        franchise_id: If set, filter to a specific franchise UUID.
        consolidated: If True, fetch enough rows for consolidation upstream.
            Uses _CATALOG_SELECT projection; limit is bypassed so the domain
            layer has sufficient material to consolidate and trim.
        simulcast: If True, filter to is_simulcast=true.
        genre: If set, filter to series containing this genre (case-sensitive).
        year: If set (and non-zero), filter to series with this release year.
        search: If set, filter by ILIKE title match.
        has_banner: If True, filter to series where banner_url IS NOT NULL.
    """
    client = storage.get_client()
    select_expr = _CATALOG_SELECT if consolidated else "*"
    query = client.table("series").select(select_expr)

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

    if has_banner:
        query = query.not_.is_("banner_url", "null")

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
    """Return streaming config fields for the given series.

    Includes audio_formats so the stream-url route can gate the DUB probe.
    """
    client = storage.get_client()
    result = (
        client.table("series")
        .select("animeflv_disabled, fallback_slug, principal_slug, audio_formats")
        .eq("id", series_id)
        .maybe_single()
        .execute()
    )
    return result.data if result else None


def update_stream_source(
    series_id: str,
    fallback_slug: str,
    animeflv_disabled: bool = False,
    principal_slug: str | None = None,
) -> bool:
    """Set stream source fields for a series.

    Args:
        series_id: UUID of the series row.
        fallback_slug: JKAnime slug for fallback playback.
        animeflv_disabled: Whether to skip the AnimeFlv source. Defaults to False.
        principal_slug: AnimeAV1 slug for primary HLS playback. When None, the
            column is left unchanged (not included in the update payload).

    Returns True if a row was updated, False if series_id not found.
    """
    client = storage.get_client()
    payload: dict = {
        "fallback_slug": fallback_slug,
        "animeflv_disabled": animeflv_disabled,
    }
    if principal_slug is not None:
        payload["principal_slug"] = principal_slug
    result = (
        client.table("series")
        .update(payload)
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
    fetch fails. The stub will have principal_slug=None (no playable source yet).
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


def get_recommended_mal_ids_batch(
    mal_ids: list[int],
) -> dict[int, list[int] | None]:
    """Return a dict mapping each mal_id to its recommended_mal_ids, in one query.

    Tri-state per entry (mirrors get_recommended_mal_ids):
      None  — column IS NULL (never fetched from Jikan).
      []    — fetched; genuinely empty.
      [ids] — fetched; list of recommended MAL IDs.

    Keys absent from the DB are absent from the returned dict (not padded).
    Returns {} on empty input or on any DB error (fail-open).
    """
    if not mal_ids:
        return {}
    try:
        client = storage.get_client()
        result = (
            client.table("series")
            .select("mal_id, recommended_mal_ids")
            .in_("mal_id", mal_ids)
            .execute()
        )
        return {
            row["mal_id"]: row["recommended_mal_ids"]
            for row in result.data or []
        }
    except Exception as exc:
        logger.warning("get_recommended_mal_ids_batch failed: %s", exc)
        return {}


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


def get_random_series_mal_ids_by_genre(
    genre: str,
    exclude_mal_id: int,
    limit: int = 5,
) -> list[int]:
    """Return up to `limit` random mal_ids for series in `genre`, excluding `exclude_mal_id`."""
    import random
    result = (
        storage.get_client()
        .table("series")
        .select("mal_id")
        .contains("genres", [genre])
        .not_.is_("mal_id", "null")
        .neq("mal_id", exclude_mal_id)
        .limit(30)
        .execute()
    )
    candidates = [row["mal_id"] for row in result.data or [] if row.get("mal_id")]
    return random.sample(candidates, min(limit, len(candidates)))


def warm_recommendations(mal_ids: list[int]) -> tuple[int, int]:
    """For each mal_id fetch related anime from MAL API v2 and persist.

    Falls back to random same-genre series from the catalog when MAL returns
    no related anime for a series.

    Returns (saved, skipped) where saved = rows written, skipped = API errors.
    """
    import logging
    import time
    from fetcher import fetch_related_anime
    saved = 0
    skipped = 0
    for mid in mal_ids:
        try:
            related_ids, genres = fetch_related_anime(mid)
            if related_ids is None:
                skipped += 1
                continue
            if not related_ids and genres:
                for genre in genres[:2]:
                    fallback = get_random_series_mal_ids_by_genre(genre, mid, limit=5)
                    if fallback:
                        related_ids = fallback
                        break
            save_recommended_mal_ids(mid, related_ids)
            saved += 1
        except Exception:
            logging.exception("warm_recommendations failed for mal_id=%s", mid)
            skipped += 1
        finally:
            time.sleep(0.3)
    return saved, skipped
