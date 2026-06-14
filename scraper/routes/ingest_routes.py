import time
from flask import Blueprint, request, jsonify
from config import REQUEST_DELAY
from fetcher import (
    fetch_anime_by_id,
    fetch_jikan_episodes,
    fetch_kitsu_series_status,
    search_anime_by_title,
    search_kitsu_anime,
    fetch_kitsu_episodes,
)
from normalizer import normalize
from storage import upsert_series, upsert_episodes, get_series_by_mal_id, get_episode_count
from scraper_animeflv import scrape_episode_list, scrape_related_series

bp = Blueprint("api", __name__)


def _discover_franchise(start_slug: str) -> list[dict]:
    """BFS-discover all related series from animeflv.

    Returns a list of {slug, title, relation, order} sorted by season_order (1-based).
    The start slug is always included with relation="root".
    """
    visited: set[str] = set()
    # queue entries: (slug, relation, order, title)
    queue: list[tuple[str, str, int, str]] = [(start_slug, "root", 0, "")]
    results: list[dict] = []

    while queue:
        slug, relation, order, title = queue.pop(0)
        if slug in visited:
            continue
        visited.add(slug)
        results.append({"slug": slug, "relation": relation, "order": order, "title": title})

        for r in scrape_related_series(slug):
            if r["slug"] in visited:
                continue
            if r["relation"] == "Secuela":
                child_order = order + 1
            elif r["relation"] == "Precuela":
                child_order = order - 1
            else:
                child_order = order
            queue.append((r["slug"], r["relation"], child_order, r["title"]))

        time.sleep(0.5)

    # Normalize to 1-based keeping relative order
    if results:
        min_order = min(r["order"] for r in results)
        for r in results:
            r["order"] = r["order"] - min_order + 1

    return sorted(results, key=lambda x: x["order"])


def _build_episodes_from_metadata(
    canonical_id: str,
    kitsu_eps: dict,
    jikan_titles: dict[int, dict] | None = None,
    media_type: str = "",
) -> list[dict]:
    """Build episode rows from Kitsu/Jikan when AnimeFlv is unavailable.

    animeflv_slug is left NULL — the watch route falls back to episode id lookup.
    For movies and other single-entry types, synthesizes ep 1 when both APIs
    return no episode list.
    """
    ep_numbers = sorted(set(kitsu_eps) | set(jikan_titles or {}))
    if not ep_numbers:
        # Jikan/Kitsu don't enumerate episodes for movies — create a single ep
        ep_numbers = [1]
    episodes = []
    for num in ep_numbers:
        kitsu = kitsu_eps.get(num, {})
        jikan = (jikan_titles.get(num) or {}) if jikan_titles else {}
        episodes.append({
            "id": f"{canonical_id}-ep-{num}",
            "series_id": canonical_id,
            "episode_number": num,
            "title": jikan.get("title") or kitsu.get("title"),
            "description": kitsu.get("description"),
            "thumbnail_url": kitsu.get("thumbnail_url"),
            "aired_at": kitsu.get("aired_at") or jikan.get("aired_at"),
            "duration_sec": kitsu.get("duration_sec") or None,
            "animeflv_slug": None,
        })
    return episodes


def _build_episodes(
    canonical_id: str,
    animeflv_slug: str,
    kitsu_eps: dict,
    jikan_titles: dict[int, dict] | None = None,
) -> list[dict]:
    """Scrape animeflv episodes and merge with Kitsu + Jikan metadata."""
    try:
        raw_episodes = scrape_episode_list(animeflv_slug)
    except RuntimeError:
        return []

    episodes = []
    for ep in raw_episodes:
        num = ep["episode_number"]
        kitsu = kitsu_eps.get(num, {})
        jikan = (jikan_titles.get(num) or {}) if jikan_titles else {}
        title = jikan.get("title") or kitsu.get("title") or ep.get("title")
        # Kitsu aired_at takes priority; fall back to Jikan aired field
        aired_at = kitsu.get("aired_at") or jikan.get("aired_at")
        episodes.append({
            "id": f"{canonical_id}-ep-{num}",
            "series_id": canonical_id,
            "episode_number": num,
            "title": title,
            "description": kitsu.get("description"),
            "thumbnail_url": kitsu.get("thumbnail_url") or ep.get("thumbnail_url"),
            "aired_at": aired_at,
            "duration_sec": kitsu.get("duration_sec") or None,
            "animeflv_slug": f"{animeflv_slug}-{num}",
        })
    return episodes


def _ingest_related(entry: dict, franchise_id: str) -> dict:
    """Ingest a single franchise member discovered via scrape_related_series.

    Searches Jikan by the title scraped from animeflv to get full metadata.
    Returns a status dict with keys: status, episodes_ingested.
    """
    slug = entry["slug"]
    title = entry["title"]
    relation = entry["relation"]
    order = entry["order"]

    try:
        jikan_raw = search_anime_by_title(title)
        if not jikan_raw:
            return {"status": "jikan_not_found", "episodes_ingested": 0}

        series = normalize(jikan_raw)
        if not series:
            return {"status": "normalize_failed", "episodes_ingested": 0}

        mal_id = jikan_raw.get("mal_id")
        existing = get_series_by_mal_id(mal_id) if mal_id else None
        canonical_id = existing["id"] if existing else slug

        series["id"] = canonical_id
        series["slug"] = canonical_id
        series["animeflv_slug"] = slug
        series["franchise_id"] = franchise_id
        series["season_order"] = order
        series["franchise_relation"] = relation

        kitsu_result = search_kitsu_anime(series.get("title", ""))
        kitsu_id = kitsu_result["id"] if kitsu_result else None
        if kitsu_result and kitsu_result.get("cover_url"):
            series["banner_url"] = kitsu_result["cover_url"]
        kitsu_eps = fetch_kitsu_episodes(kitsu_id) if kitsu_id else {}

        # Fetch Kitsu status and re-normalize with simulcast metadata
        kitsu_status = fetch_kitsu_series_status(kitsu_id) if kitsu_id else None
        normalized_with_kitsu = normalize(jikan_raw, kitsu_id=kitsu_id, kitsu_status=kitsu_status)
        if normalized_with_kitsu:
            for field in ("broadcast_day", "broadcast_time", "broadcast_timezone", "aired_from",
                          "kitsu_id", "kitsu_status", "is_simulcast"):
                series[field] = normalized_with_kitsu.get(field)

        upsert_series(series)

        # If this series was already scraped in a previous (partial) run,
        # skip episode scraping — metadata above is already updated.
        if existing:
            ep_count = get_episode_count(canonical_id)
            if ep_count > 0:
                return {"status": "already_scraped", "episodes_ingested": ep_count}

        jikan_titles = fetch_jikan_episodes(mal_id) if mal_id else {}
        episodes = _build_episodes(canonical_id, slug, kitsu_eps, jikan_titles)
        count = upsert_episodes(episodes)

        return {"status": "ok", "episodes_ingested": count}

    except Exception as exc:
        return {"status": f"error: {exc}", "episodes_ingested": 0}


@bp.route("/ingest", methods=["POST"])
def ingest():
    body = request.get_json(force=True) or {}
    mal_id = body.get("mal_id")
    animeflv_slug = body.get("animeflv_slug")
    fallback_slug = body.get("fallback_slug")

    if not mal_id:
        return jsonify({"error": "mal_id is required"}), 422

    try:
        mal_id_int = int(mal_id)
    except (TypeError, ValueError):
        return jsonify({"error": "mal_id must be a number"}), 422

    # Fetch + normalize main series from Jikan
    try:
        raw = fetch_anime_by_id(mal_id_int)
    except ValueError:
        return jsonify({"error": "Anime not found on MAL"}), 404
    except Exception as exc:
        return jsonify({"error": f"Jikan error: {exc}"}), 502

    series = normalize(raw)
    if not series:
        return jsonify({"error": "Could not normalize series data"}), 502

    existing = get_series_by_mal_id(mal_id_int)
    canonical_id = existing["id"] if existing else (animeflv_slug or fallback_slug or f"mal-{mal_id_int}")

    series["id"] = canonical_id
    series["slug"] = canonical_id
    if animeflv_slug:
        series["animeflv_slug"] = animeflv_slug
    if fallback_slug:
        series["fallback_slug"] = fallback_slug

    # Discover full franchise (BFS) — requires animeflv_slug
    if animeflv_slug:
        print(f"  Discovering franchise for {animeflv_slug}...")
        franchise_entries = _discover_franchise(animeflv_slug)
        franchise_id = franchise_entries[0]["slug"] if franchise_entries else animeflv_slug
        main_entry = next((e for e in franchise_entries if e["slug"] == animeflv_slug), None)
        series["season_order"] = main_entry["order"] if main_entry else 1
        series["franchise_relation"] = main_entry["relation"] if main_entry else "root"
    else:
        franchise_entries = []
        franchise_id = canonical_id
        series["season_order"] = 1
        series["franchise_relation"] = "root"

    series["franchise_id"] = franchise_id

    # Fetch Kitsu cover + episode metadata for main series
    kitsu_result = search_kitsu_anime(series.get("title", ""))
    kitsu_id = kitsu_result["id"] if kitsu_result else None
    if kitsu_result and kitsu_result.get("cover_url"):
        series["banner_url"] = kitsu_result["cover_url"]
    kitsu_eps = fetch_kitsu_episodes(kitsu_id) if kitsu_id else {}

    # Fetch Kitsu status and re-normalize with full simulcast metadata
    kitsu_status = fetch_kitsu_series_status(kitsu_id) if kitsu_id else None
    normalized_with_kitsu = normalize(raw, is_featured=series.get("is_featured", False), kitsu_id=kitsu_id, kitsu_status=kitsu_status)
    if normalized_with_kitsu:
        # Merge simulcast fields back into series dict (preserve already-set fields like id, slug, etc.)
        for field in ("broadcast_day", "broadcast_time", "broadcast_timezone", "aired_from",
                      "kitsu_id", "kitsu_status", "is_simulcast"):
            series[field] = normalized_with_kitsu.get(field)

    upsert_series(series)

    # Fetch episode titles from Jikan
    print(f"  Fetching episode titles from Jikan for mal_id={mal_id_int}...")
    jikan_titles = fetch_jikan_episodes(mal_id_int)

    # Scrape episodes for main series
    main_count = 0
    if animeflv_slug:
        try:
            main_episodes = _build_episodes(canonical_id, animeflv_slug, kitsu_eps, jikan_titles)
            if not main_episodes:
                raise RuntimeError(
                    f"'var episodes' not found in animeflv/{animeflv_slug} — "
                    "check the slug or Cloudflare"
                )
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 502
        main_count = upsert_episodes(main_episodes)
    else:
        media_type = raw.get("type", "")
        main_episodes = _build_episodes_from_metadata(canonical_id, kitsu_eps, jikan_titles, media_type)
        main_count = upsert_episodes(main_episodes)

    # Ingest each related franchise member
    franchise_results = []
    for entry in franchise_entries:
        if entry["slug"] == animeflv_slug:
            continue
        print(f"  Ingesting related [{entry['relation']}]: {entry['slug']}")
        result = _ingest_related(entry, franchise_id)
        franchise_results.append({
            "slug": entry["slug"],
            "title": entry["title"],
            "relation": entry["relation"],
            "season_order": entry["order"],
            **result,
        })
        time.sleep(REQUEST_DELAY)

    return jsonify({
        "series_id": canonical_id,
        "series_title": series.get("title", ""),
        "episodes_ingested": main_count,
        "kitsu_id": kitsu_id,
        "kitsu_episodes_matched": len(kitsu_eps),
        "franchise_id": franchise_id,
        "franchise": franchise_results,
    }), 200


