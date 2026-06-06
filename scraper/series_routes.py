"""Flask Blueprint for public series endpoints."""
import logging
import threading
from flask import Blueprint, request, jsonify, g
from db import series as db_series
from db import episodes as db_episodes
from db import progress as db_progress
from domain.series import (
    map_series_row,
    consolidate_franchises,
    build_seasons,
)
from auth import require_admin, require_auth
from fetcher import fetch_recommendations, fetch_jikan_by_genre, search_animeflv

series_bp = Blueprint("series", __name__, url_prefix="/api/series")

_SEASON_MONTHS: dict[str, tuple[int, int]] = {
    "winter": (1, 3),
    "spring": (4, 6),
    "summer": (7, 9),
    "fall": (10, 12),
}


def _season_months(season: str) -> tuple[int, int] | None:
    """Return the (start_month, end_month) range for a season name, or None if unknown."""
    return _SEASON_MONTHS.get(season.lower())


@series_bp.get("")
def list_series():
    """GET /api/series — list series with optional filters."""
    try:
        limit = int(request.args.get("limit", 20))
    except (TypeError, ValueError):
        limit = 20

    sort = request.args.get("sort", "score")
    featured_param = request.args.get("featured")
    franchise_id = request.args.get("franchise_id")
    consolidated_param = request.args.get("consolidated")
    simulcast_param = request.args.get("simulcast")
    genre = request.args.get("genre")
    year = request.args.get("year", type=int)
    season = request.args.get("season")

    featured = featured_param is not None and featured_param.lower() not in ("false", "0", "")
    consolidated = consolidated_param is not None and consolidated_param.lower() not in ("false", "0", "")
    simulcast = simulcast_param is not None and simulcast_param.lower() not in ("false", "0", "")

    rows = db_series.get_series_list(
        limit=limit,
        sort=sort,
        featured=featured if featured else None,
        franchise_id=franchise_id,
        consolidated=consolidated,
        simulcast=simulcast,
        genre=genre,
        year=year,
    )
    mapped = [map_series_row(r) for r in rows]

    if season:
        month_range = _season_months(season)
        if month_range:
            start_month, end_month = month_range
            filtered_by_season = []
            for s in mapped:
                aired_from = s.get("airedFrom")
                if not aired_from:
                    continue
                try:
                    month = int(aired_from[5:7])
                except (TypeError, ValueError, IndexError):
                    continue
                if start_month <= month <= end_month:
                    filtered_by_season.append(s)
            mapped = filtered_by_season

    if consolidated:
        mapped = consolidate_franchises(mapped)
        mapped = mapped[:limit]

    return jsonify(mapped)


@series_bp.get("/search")
def search_series():
    """GET /api/series/search?q=&limit= — title search."""
    q = request.args.get("q")
    if not q:
        return jsonify({"error": "Missing required parameter: q"}), 400

    try:
        limit = int(request.args.get("limit", 8))
    except (TypeError, ValueError):
        limit = 8

    rows = db_series.search_series(q, limit=limit)
    # Return minimal projection: malId, title, slug
    result = [
        {
            "malId": r.get("mal_id"),
            "title": r.get("title"),
            "slug": r.get("slug"),
        }
        for r in rows
    ]
    return jsonify(result)


@series_bp.get("/search-animeflv")
@require_admin
def search_animeflv_results():
    """GET /api/series/search-animeflv?q= — search AnimeFlv for slugs.

    Returns list of {title, slug, animeflv_url} from AnimeFlv search.
    """
    q = request.args.get("q")
    if not q:
        return jsonify({"error": "Missing required parameter: q"}), 400

    try:
        limit = int(request.args.get("limit", 10))
    except (TypeError, ValueError):
        limit = 10

    results = search_animeflv(q, limit=limit)
    return jsonify(results)


@series_bp.get("/recommendations")
@require_auth
def series_recommendations():
    """GET /api/series/recommendations — personalized recommendations for the authenticated user.

    Pipeline:
    1. Fetch the 5 most-recent progress entries (progress_sec > 0 enforced by query).
    2. Resolve mal_id for each seed series; skip seeds without one.
    3. Call Jikan recommendations for each seed (top 3 each, fail-open).
    4. Deduplicate candidates by mal_id; remove already-watched mal_ids.
    5. Batch-query the series table for matched candidates.
    6. Spawn daemon threads to ingest unmatched candidates as stubs.
    7. Fallback: if no seeds resolved, return top-scored series from DB.
    """
    user_id = g.user_id

    # Step 1 — seed series from watch history
    progress_rows = db_progress.get_recent_progress(user_id, limit=5)
    series_ids = list({row["series_id"] for row in progress_rows})

    # Step 2 — resolve mal_ids; empty result triggers fallback
    mal_id_map = db_progress.get_mal_ids_for_series(series_ids) if series_ids else {}

    if not mal_id_map:
        # Fallback: no history or no seeds with mal_id
        rows = db_series.get_series_list(limit=10, sort="score")
        return jsonify([map_series_row(r) for r in rows])

    # Build the watched mal_id set for filtering
    all_progress = db_progress.get_recent_progress(user_id, limit=500)
    watched_series_ids = {row["series_id"] for row in all_progress}
    watched_mal_ids = set(db_progress.get_mal_ids_for_series(list(watched_series_ids)).values())

    # Step 3 — fetch recommendations for each seed (fail-open, top 3)
    candidates: dict[int, dict] = {}
    for mal_id in mal_id_map.values():
        entries = fetch_recommendations(mal_id)
        for entry in entries:
            anime_entry = entry.get("entry", {})
            candidate_mal_id = anime_entry.get("mal_id")
            if candidate_mal_id and candidate_mal_id not in candidates:
                candidates[candidate_mal_id] = anime_entry

    # Step 4 — filter out already-watched candidates
    filtered_mal_ids = [
        mid for mid in candidates
        if mid not in watched_mal_ids
    ]

    if not filtered_mal_ids:
        rows = db_series.get_series_list(limit=10, sort="score")
        return jsonify([map_series_row(r) for r in rows])

    # Step 5 — cross-reference against series table
    matched = db_series.get_series_by_mal_ids(filtered_mal_ids)
    matched_mal_ids = {s["malId"] for s in matched if s.get("malId")}

    # Step 6 — spawn daemon threads for unmatched candidates
    unmatched_mal_ids = [mid for mid in filtered_mal_ids if mid not in matched_mal_ids]
    for unmatched_mal_id in unmatched_mal_ids:
        try:
            t = threading.Thread(
                target=db_series.upsert_series_stub,
                args=(unmatched_mal_id,),
                daemon=True,
            )
            t.start()
        except Exception:
            logging.exception(
                "Failed to spawn stub ingest thread for mal_id=%s", unmatched_mal_id
            )

    return jsonify(matched)


@series_bp.get("/<series_id>")
def series_detail(series_id: str):
    """GET /api/series/<id> — single series detail."""
    row = db_series.get_series_by_id(series_id)
    if not row:
        return jsonify({"error": "Series not found"}), 404
    return jsonify(map_series_row(row))


@series_bp.get("/<series_id>/seasons")
def series_seasons(series_id: str):
    """GET /api/series/<id>/seasons — part-merged, labelled season list."""
    # Look up the series to get its franchise_id
    row = db_series.get_series_by_id(series_id)
    if not row:
        return jsonify({"error": "Series not found"}), 404

    franchise_id = row.get("franchise_id")
    if franchise_id:
        members_raw = db_series.get_series_by_franchise(franchise_id)
    else:
        members_raw = [row]

    members = [map_series_row(r) for r in members_raw]

    # Fetch episodes for each member
    episodes_by_series: dict[str, list[dict]] = {}
    for member in members:
        sid = member["id"]
        eps_raw = db_episodes.get_episodes_by_series(sid)
        from domain.series import map_episode_row
        episodes_by_series[sid] = [map_episode_row(e) for e in eps_raw]

    # For simulcast franchise members with elapsed cooldown, discover new episodes
    # in the background so they appear on the next page load.
    from domain.simulcast import cooldown_elapsed
    from simulcast_check import run_simulcast_update

    for member in members:
        if not member.get("isSimulcast") or not member.get("animeflvSlug"):
            continue
        if not cooldown_elapsed(member.get("lastSimulcastCheck")):
            continue
        sid = member["id"]
        eps = episodes_by_series.get(sid, [])
        current_max_ep = max((e.get("episode", 0) for e in eps), default=0)
        threading.Thread(
            target=run_simulcast_update,
            args=(sid, member["animeflvSlug"], current_max_ep),
            daemon=True,
        ).start()

    payload = build_seasons(members, episodes_by_series, requested_series_id=series_id)
    return jsonify(payload)


@series_bp.get("/<series_id>/episodes")
def series_episodes(series_id: str):
    """GET /api/series/<id>/episodes — episodes ordered by episode_number."""
    from domain.series import map_episode_row
    from domain.simulcast import cooldown_elapsed
    from simulcast_check import run_simulcast_update

    rows = db_episodes.get_episodes_by_series(series_id)

    # If this is a simulcast series and conditions are met, discover new episodes
    # in the background — works even when the user has no watch_progress.
    series_row = db_series.get_series_by_id(series_id)
    if series_row and series_row.get("is_simulcast") and series_row.get("animeflv_slug"):
        if cooldown_elapsed(series_row.get("last_simulcast_check")):
            current_max_ep = max((r["episode_number"] for r in rows), default=0)
            threading.Thread(
                target=run_simulcast_update,
                args=(series_id, series_row["animeflv_slug"], current_max_ep),
                daemon=True,
            ).start()

    return jsonify([map_episode_row(r) for r in rows])


@series_bp.patch("/<series_id>/stream-source")
@require_admin
def update_stream_source(series_id: str):
    """PATCH /api/series/<id>/stream-source — set animeav1 slug and disable animeflv."""
    body = request.get_json(silent=True) or {}
    animeav1_slug = body.get("animeav1_slug")
    if not animeav1_slug:
        return jsonify({"error": "animeav1_slug is required"}), 400

    updated = db_series.update_stream_source(series_id, animeav1_slug)
    if not updated:
        return jsonify({"error": "Series not found"}), 404

    return jsonify({
        "id": series_id,
        "animeav1Slug": animeav1_slug,
        "animeflv_disabled": True,
    }), 200


@series_bp.get("/<series_id>/stream-config")
def series_stream_config(series_id: str):
    """GET /api/series/<id>/stream-config — streaming flags."""
    config = db_series.get_stream_config(series_id)
    if not config:
        return jsonify({"error": "Series not found"}), 404
    return jsonify({
        "animeflvDisabled": config.get("animeflv_disabled", False),
        "animeav1Slug": config.get("animeav1_slug"),
    })


# Genre name → Jikan genre ID (MAL genre IDs via Jikan v4)
_JIKAN_GENRE_IDS: dict[str, int] = {
    "Action": 1, "Adventure": 2, "Comedy": 4, "Drama": 8,
    "Fantasy": 10, "Horror": 14, "Mystery": 7, "Romance": 22,
    "Sci-Fi": 24, "Slice of Life": 36, "Sports": 30,
    "Supernatural": 37, "Thriller": 41, "Isekai": 62,
    "Mecha": 18, "Psychological": 40, "Shounen": 27, "Shoujo": 25,
}


@series_bp.get("/discover")
def discover_series():
    """GET /api/series/discover — genre discovery feed with background Jikan enrichment.

    Returns shuffled catalog series matching the top 3 genres in the DB.
    Spawns a daemon thread that fetches Jikan top series for those genres
    and upserts new ones as stubs — catalog grows on each visit.
    """
    import random
    from collections import Counter
    from normalizer import normalize
    from storage import upsert_many
    import storage

    # 1. Aggregate genres and mal_ids from existing catalog
    rows = storage.get_client().table("series").select("genres, mal_id").limit(500).execute().data or []
    counter: Counter = Counter()
    known_mal_ids: set[int] = set()
    for row in rows:
        for g in (row.get("genres") or []):
            counter[g] += 1
        if row.get("mal_id"):
            known_mal_ids.add(int(row["mal_id"]))

    top_genres = [g for g, _ in counter.most_common(3)]

    # 2. Return shuffled DB series matching top genres
    all_series = db_series.get_series_list(limit=200, sort="score")
    filtered = [s for s in all_series if any(g in (s.get("genres") or []) for g in top_genres)]
    random.shuffle(filtered)
    mapped = [map_series_row(s) for s in filtered[:50]]

    # 3. Background: fetch Jikan for top genres, upsert new series as stubs
    def _enrich_catalog(genres: list[str], known: set[int]) -> None:
        import time as _time
        for genre in genres:
            genre_id = _JIKAN_GENRE_IDS.get(genre)
            if not genre_id:
                continue
            try:
                jikan_results = fetch_jikan_by_genre(genre_id, limit=15)
                new_entries = []
                for raw in jikan_results:
                    mal_id = raw.get("mal_id")
                    if mal_id and int(mal_id) not in known:
                        entry = normalize(raw)
                        if entry:
                            new_entries.append(entry)
                if new_entries:
                    upsert_many(new_entries)
            except Exception as exc:
                logging.warning("[discover] genre=%s enrich error: %s", genre, exc)
            _time.sleep(0.5)

    threading.Thread(target=_enrich_catalog, args=(top_genres, known_mal_ids), daemon=True).start()

    return jsonify(mapped), 200
