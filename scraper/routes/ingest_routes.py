import time
from flask import Blueprint, request, jsonify
from config import REQUEST_DELAY
from fetcher import (
    fetch_anime_by_id,
    fetch_jikan_episodes,
    fetch_jikan_relations,
    fetch_kitsu_series_status,
    search_kitsu_anime,
    fetch_kitsu_episodes,
)
from normalizer import normalize
from storage import upsert_series, upsert_episodes, get_series_by_mal_id, get_episode_count
from scraper_animeav1 import (
    scrape_animeav1_episodes,
    find_best_animeav1_match,
    animeav1_has_dub,
)
from scraper_jkanime import find_best_jkanime_match, fetch_jkanime_series_info
from db.series import get_series_by_id, get_series_by_franchise

bp = Blueprint("api", __name__)


def _detect_av1_dub(animeav1_slug: str) -> bool:
    """Probe episode 1 of an AnimeAV1 series to detect DUB availability.

    Returns True when a span.ic-dub element is present on the episode 1 page.
    Returns False on any error — never raises.
    """
    try:
        return animeav1_has_dub(animeav1_slug, episode_number=1)
    except Exception:
        return False


_FRANCHISE_RELATIONS = {
    "Sequel", "Prequel", "Side story", "Parent story",
    "Alternative version", "Alternative setting", "Summary", "Full story",
}
# "Other" intentionally excluded — MAL tags unrelated crossover promos/CMs
# (e.g. brand tie-in commercials) with this relation, and following it pulls
# them into the franchise as if they were real entries.


def _discover_franchise_jikan(start_mal_id: int) -> list[dict]:
    """BFS-discover all related series via Jikan relations API.

    Returns a list of {mal_id, title, relation, order} sorted by season_order (1-based).
    The root entry is always included with relation="root".

    Order heuristic: Prequel entries get order - 1, Sequel entries get order + 1,
    all others keep the parent order.  After traversal the list is normalized to
    1-based so callers can use season_order directly.
    """
    visited: set[int] = set()
    # queue entries: (mal_id, relation, order, title)
    queue: list[tuple[int, str, int, str]] = [(start_mal_id, "root", 0, "")]
    results: list[dict] = []

    while queue:
        mal_id, relation, order, title = queue.pop(0)
        if mal_id in visited:
            continue
        visited.add(mal_id)
        results.append({"mal_id": mal_id, "relation": relation, "order": order, "title": title})

        try:
            related = fetch_jikan_relations(mal_id)
        except Exception:
            related = []

        for rel_group in related:
            rel_type = rel_group.get("relation", "")
            if rel_type not in _FRANCHISE_RELATIONS:
                continue
            for entry in rel_group.get("entry", []):
                if entry.get("type") != "anime":
                    continue
                child_mal_id = entry.get("mal_id")
                if not child_mal_id or child_mal_id in visited:
                    continue
                if rel_type == "Sequel":
                    child_order = order + 1
                elif rel_type == "Prequel":
                    child_order = order - 1
                else:
                    child_order = order
                queue.append((child_mal_id, rel_type, child_order, entry.get("name", "")))

        time.sleep(0.4)

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
    """Build episode rows from Kitsu/Jikan when AnimeAV1 is unavailable.

    animeflv_slug is left NULL — the watch route falls back to episode id lookup.
    For movies and other single-entry types, synthesizes ep 1 when both APIs
    return no episode list. TV series with no data yet return [] instead —
    they have no real video source, and a synthesized placeholder would mask
    that from the admin ingest-retry flow (IngestTrigger), which relies on
    episodes_ingested == 0 to prompt for the real AnimeAV1 slug.
    """
    ep_numbers = sorted(set(kitsu_eps) | set(jikan_titles or {}))
    if not ep_numbers:
        if (media_type or "tv").lower() == "tv":
            return []
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


def _build_episodes_from_jkanime(
    canonical_id: str,
    episode_count: int,
    kitsu_eps: dict,
    jikan_titles: dict[int, dict] | None = None,
    max_episodes: int | None = None,
    episode_offset: int = 0,
) -> list[dict]:
    """Build episode rows numbered 1..episode_count from a jkanime match.

    Used when AnimeAV1 has no page for this member — jkanime episodes resolve
    at stream time via fallback_slug (domain/stream.py::resolve_jkanime_stream),
    so this only needs to create the right number of rows, merged with
    whatever Kitsu/Jikan per-episode metadata is available. animeflv_slug is
    left NULL, matching every other non-AnimeFlv source.

    ``max_episodes`` mirrors _build_episodes_from_animeav1's same-named guard:
    when jkanime has no page of its own for a recap/special and the fuzzy
    match falls back onto its parent season's page, jkanime's own episode
    count reflects that season's total, not this specific member's — capping
    to this member's own Jikan-reported episode_count prevents a 1-episode
    special from claiming the whole season's episode count.

    ``episode_offset`` mirrors _build_episodes_from_animeav1's same-named
    param (see _claimed_episode_offset): skips leading episode numbers
    already claimed by a sibling — via either AnimeAV1 or jkanime — on a
    same-named shared page, so a Part 2 sourced here doesn't duplicate a
    Part 1 sourced from AnimeAV1 (confirmed live for Slime Season 4 Part 2).
    """
    if max_episodes:
        episode_count = min(episode_count, max_episodes)
    episodes = []
    for num in range(episode_offset + 1, episode_count + 1):
        rel_num = num - episode_offset
        kitsu = kitsu_eps.get(rel_num, {})
        jikan = (jikan_titles.get(rel_num) or {}) if jikan_titles else {}
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


def _build_episodes_from_animeav1(
    canonical_id: str,
    animeav1_slug: str,
    kitsu_eps: dict,
    jikan_titles: dict[int, dict] | None = None,
    episode_offset: int = 0,
    max_episodes: int | None = None,
) -> list[dict]:
    """Scrape AnimeAV1 episode list and merge with Kitsu + Jikan metadata.

    Sets animeflv_slug to None — episodes sourced from AnimeAV1 do not have
    an AnimeFlv episode slug.  Returns [] on scraper error or empty result.

    ``episode_offset`` and ``max_episodes`` handle the case where AnimeAV1
    doesn't split a MAL cour split ("Part 1"/"Part 2") into separate pages —
    both parts' title search resolve to the same AnimeAV1 slug. When that
    happens, an earlier-ingested sibling already claims the leading episodes
    on that shared page (see ``_claimed_episode_offset``); this member skips
    those (keeping AnimeAV1's native episode_number, required for stream
    resolution) and is capped at its own official MAL episode count so it
    never grabs episodes belonging to a not-yet-ingested later sibling.
    Kitsu/Jikan lookups are rebased to this member's own numbering (which
    restarts at 1 per MAL entry) via ``num - episode_offset``.
    """
    raw_episodes = scrape_animeav1_episodes(animeav1_slug)
    if not raw_episodes:
        return []
    if episode_offset:
        raw_episodes = [ep for ep in raw_episodes if ep["episode_number"] > episode_offset]
    if max_episodes:
        raw_episodes = raw_episodes[:max_episodes]
    if not raw_episodes:
        return []

    episodes = []
    for ep in raw_episodes:
        num = ep["episode_number"]
        rel_num = num - episode_offset
        kitsu = kitsu_eps.get(rel_num, {})
        jikan = (jikan_titles.get(rel_num) or {}) if jikan_titles else {}
        title = jikan.get("title") or kitsu.get("title")
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
            "animeflv_slug": None,
        })
    return episodes


def _claimed_episode_offset(franchise_id: str | None, slug: str, exclude_id: str) -> int:
    """Return how many leading episodes on ``slug`` are already claimed by
    another member of this franchise.

    AnimeAV1/jkanime sometimes don't split a MAL cour split ("Part 1"/
    "Part 2") into separate pages, so both parts' title search resolve to
    the same slug (confirmed against the live site for e.g. Slime Season 4
    Part 2). The sibling ingested first claims the leading episodes on that
    shared page; this offset tells the next one where to continue.

    Checks both ``principal_slug`` (AnimeAV1) and ``fallback_slug``
    (jkanime) — a sibling sourced from either can claim the same slug name,
    e.g. Part 1 resolved via AnimeAV1 and Part 2 via jkanime both landing on
    a page named after the same season (confirmed live: Slime Season 4
    Part 2 duplicated Part 1's episodes this way before this checked both).
    """
    if not franchise_id:
        return 0
    siblings = get_series_by_franchise(franchise_id)
    claimed = 0
    for s in siblings:
        if s.get("id") == exclude_id:
            continue
        if s.get("principal_slug") != slug and s.get("fallback_slug") != slug:
            continue
        claimed += get_episode_count(s["id"])
    return claimed


def _slug_claimed_by_sibling(franchise_id: str, av1_slug: str, mal_id: int) -> bool:
    """True if another franchise member already owns ``av1_slug`` as its id or
    principal_slug.

    AnimeAV1 sometimes doesn't split a MAL cour split ("Part 1"/"Part 2") into
    separate pages, and its title search can also fuzzy-match a recap/special
    with no page of its own onto an unrelated season's page. Letting a second
    member claim the same slug as its own canonical id would collide on
    ``upsert_series(..., on_conflict="id")`` and silently overwrite whichever
    sibling already claimed it — so callers must fall back to a mal_id-based
    id instead when this returns True.
    """
    for s in get_series_by_franchise(franchise_id):
        if s.get("mal_id") == mal_id:
            continue
        if s.get("id") == av1_slug or s.get("principal_slug") == av1_slug:
            return True
    return False


def _kitsu_id_claimed_by_sibling(franchise_id: str, kitsu_id: str, mal_id: int) -> bool:
    """True if another franchise member already stored this same kitsu_id.

    Kitsu sometimes indexes an entire franchise's cours/recaps/specials under
    one shared anime entry (see domain/simulcast.py's resolve_simulcast_status
    docstring — kitsu_status there is franchise-wide, not per-season). When a
    sibling already claims this kitsu_id, treating it as this member's own
    match would persist that sibling's kitsu_status/episode metadata as if it
    were this member's — e.g. a not-yet-aired sequel silently inheriting
    "finished" from the long-completed season it fuzzy-matched onto. The
    periodic simulcast refresh job re-reads the stored kitsu_id later too, so
    this must be caught at ingest time or it keeps re-persisting on its own.
    """
    for s in get_series_by_franchise(franchise_id):
        if s.get("mal_id") == mal_id:
            continue
        if s.get("kitsu_id") == kitsu_id:
            return True
    return False


def backfill_episode_metadata(series_id: str) -> int:
    """Re-scrape AnimeAV1 (+ Kitsu/Jikan) to fill in missing episode metadata.

    Triggered lazily from a series page visit when its first episode has no
    thumbnail_url — this happens when a franchise member's initial ingest fell
    back to Jikan-only metadata (AnimeAV1 title-search miss at ingest time, or
    a principal_slug that was only set afterwards via the admin editor, which
    never rebuilds episodes). Reuses the same Kitsu > AnimeAV1 merge priority
    as ingest and upserts on the existing episode ids — refreshes titles/dates
    too, but never creates or removes episodes.

    Returns the number of episodes upserted, or 0 if nothing could be resolved
    (no principal_slug, or the AnimeAV1 scrape came back empty).
    """
    from db.series import get_series_by_id

    row = get_series_by_id(series_id)
    if not row:
        return 0
    principal_slug = row.get("principal_slug")
    if not principal_slug:
        return 0

    kitsu_id = row.get("kitsu_id")
    mal_id = row.get("mal_id")
    kitsu_eps = fetch_kitsu_episodes(kitsu_id) if kitsu_id else {}
    jikan_titles = fetch_jikan_episodes(mal_id) if mal_id else {}

    episodes = _build_episodes_from_animeav1(series_id, principal_slug, kitsu_eps, jikan_titles)
    if not episodes:
        return 0
    return upsert_episodes(episodes)


def backfill_episodes_from_jkanime(series_id: str, jkanime_slug: str) -> int:
    """Create episode rows from a jkanime episode count for a series that has none.

    Mirrors backfill_episodes_from_metadata, but sources the episode count
    from jkanime itself (fetch_jkanime_series_info) instead of Kitsu/Jikan —
    used when an admin manually assigns a jkanime slug via JkanimeAssignPanel
    (routes/series_routes.py::update_stream_source). Without this, assigning
    fallback_slug to a TV-type stub with no Kitsu/Jikan per-episode listing
    only enabled streaming for episodes that were never created, since
    _build_episodes_from_metadata deliberately returns [] for that case.

    Returns the number of episodes created, or 0 if the series already has
    episodes, doesn't exist, or jkanime has no episode count for this slug.
    """
    if get_episode_count(series_id) > 0:
        return 0

    row = get_series_by_id(series_id)
    if not row:
        return 0

    jkanime_info = fetch_jkanime_series_info(jkanime_slug)
    if not jkanime_info or not jkanime_info.get("episode_count"):
        return 0

    kitsu_id = row.get("kitsu_id")
    mal_id = row.get("mal_id")
    kitsu_eps = fetch_kitsu_episodes(kitsu_id) if kitsu_id else {}
    jikan_titles = fetch_jikan_episodes(mal_id) if mal_id else {}

    episodes = _build_episodes_from_jkanime(
        series_id, jkanime_info["episode_count"], kitsu_eps, jikan_titles,
    )
    if not episodes:
        return 0
    return upsert_episodes(episodes)


def backfill_episodes_from_metadata(series_id: str) -> int:
    """Create episode rows from Kitsu/Jikan metadata for a series that has none.

    A series can exist with zero episode rows — created as a metadata-only
    stub (db.series.upsert_series_stub, used by simulcast auto-discovery and
    recommendations seeding) or via the admin downloads UI assigning a
    fallback_slug to such a stub — without ever going through /ingest. Both
    paths only touch the series row, not episodes. This mirrors what /ingest
    already does when no AnimeAV1 slug is available (_build_episodes_from_metadata),
    so it's safe to call standalone: it no-ops whenever episodes already exist.

    Returns the number of episodes created, or 0 if the series already has
    episodes, doesn't exist, or Kitsu/Jikan have no episode data yet.
    """
    if get_episode_count(series_id) > 0:
        return 0

    row = get_series_by_id(series_id)
    if not row:
        return 0

    kitsu_id = row.get("kitsu_id")
    mal_id = row.get("mal_id")
    media_type = row.get("media_type") or ""
    kitsu_eps = fetch_kitsu_episodes(kitsu_id) if kitsu_id else {}
    jikan_titles = fetch_jikan_episodes(mal_id) if mal_id else {}

    episodes = _build_episodes_from_metadata(series_id, kitsu_eps, jikan_titles, media_type)
    if not episodes:
        return 0
    return upsert_episodes(episodes)


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
    """Ingest a single franchise member discovered via Jikan relations BFS.

    Uses fetch_anime_by_id(mal_id) directly — more accurate than searching by title.
    principal_slug is only persisted once AnimeAV1 actually resolves episodes for
    it — a title-search hit that scrapes empty is not a working video source and
    must not be saved, or stream resolution will 404 on it later.
    Returns a status dict with keys: status, episodes_ingested, principal_slug.
    """
    mal_id = entry["mal_id"]
    title = entry.get("title", "")
    relation = entry["relation"]
    order = entry["order"]

    try:
        try:
            jikan_raw = fetch_anime_by_id(mal_id)
        except Exception:
            return {"status": "jikan_not_found", "episodes_ingested": 0}

        if not jikan_raw:
            return {"status": "jikan_not_found", "episodes_ingested": 0}

        series = normalize(jikan_raw)
        if not series:
            return {"status": "normalize_failed", "episodes_ingested": 0}

        existing = get_series_by_mal_id(mal_id)

        # Try to auto-match this franchise member on AnimeAV1 by title.
        # AnimeAV1 catalogs series under their romaji default title, but
        # normalize()'s "titles" list only carries English/Japanese-script
        # alternatives + synonyms (see _mal_node_to_jikan) — the romaji
        # default (jikan_raw["title"]) is never in it, so it has to be added
        # here or the real romaji match (what AnimeAV1 actually uses) never
        # gets scored at all (confirmed live: DanMachi Season 1's correct
        # AnimeAV1 page titled exactly in romaji was otherwise invisible).
        series_title = series.get("title", "") or title
        av1_alt_titles = list(series.get("titles") or [])
        if jikan_raw.get("title"):
            av1_alt_titles.append(jikan_raw["title"])
        av1_match = find_best_animeav1_match(series_title, alt_titles=av1_alt_titles)
        av1_slug = av1_match["slug"] if av1_match else None

        # Only claim av1_slug as this member's own id when no other franchise
        # member already owns it — otherwise this upsert would silently
        # overwrite that sibling's row (see _slug_claimed_by_sibling).
        slug_taken = bool(av1_slug) and _slug_claimed_by_sibling(franchise_id, av1_slug, mal_id)
        canonical_id = existing["id"] if existing else (
            f"mal-{mal_id}" if slug_taken else (av1_slug or f"mal-{mal_id}")
        )

        series["id"] = canonical_id
        series["slug"] = canonical_id
        series["franchise_id"] = franchise_id
        series["season_order"] = order
        series["franchise_relation"] = relation

        kitsu_result = search_kitsu_anime(series_title, alt_titles=series.get("titles"))
        kitsu_id = kitsu_result["id"] if kitsu_result else None
        if kitsu_result and kitsu_result.get("cover_url"):
            series["banner_url"] = kitsu_result["cover_url"]

        # A shared kitsu_id belongs to whichever sibling actually owns that
        # Kitsu entry — using it here too would apply for kitsu_status,
        # episode metadata, and future refreshes as if it were this member's
        # own (see _kitsu_id_claimed_by_sibling). Keep the cover as a
        # best-effort placeholder, but don't treat the id itself as ours.
        if kitsu_id and _kitsu_id_claimed_by_sibling(franchise_id, kitsu_id, mal_id):
            kitsu_id = None

        kitsu_eps = fetch_kitsu_episodes(kitsu_id) if kitsu_id else {}

        kitsu_status = fetch_kitsu_series_status(kitsu_id) if kitsu_id else None
        normalized_with_kitsu = normalize(jikan_raw, kitsu_id=kitsu_id, kitsu_status=kitsu_status)
        if normalized_with_kitsu:
            for field in ("broadcast_day", "broadcast_time", "broadcast_timezone", "aired_from",
                          "kitsu_id", "kitsu_status", "is_simulcast"):
                series[field] = normalized_with_kitsu.get(field)

        if existing:
            ep_count = get_episode_count(canonical_id)
            if ep_count > 0:
                # principal_slug intentionally omitted from this write — episodes
                # already exist, so a fresh title-search guess must not clobber
                # whatever slug was previously confirmed to work.
                upsert_series(series)
                return {"status": "already_scraped", "episodes_ingested": ep_count}

        jikan_titles = fetch_jikan_episodes(mal_id)
        episodes = []
        if av1_slug:
            episode_offset = _claimed_episode_offset(franchise_id, av1_slug, canonical_id)
            episodes = _build_episodes_from_animeav1(
                canonical_id, av1_slug, kitsu_eps, jikan_titles,
                episode_offset=episode_offset, max_episodes=series.get("episode_count"),
            )
        if episodes:
            series["principal_slug"] = av1_slug
            # Detect DUB availability and persist to audio_formats.
            if _detect_av1_dub(av1_slug):
                series["audio_formats"] = ["sub", "dub"]
        else:
            # AnimeAV1 has nothing for this member — try jkanime before
            # falling back to a metadata-only stub. jkanime episodes resolve
            # at stream time via fallback_slug (already wired in
            # domain/stream.py::orchestrate_stream); this only needs the
            # right episode count to create playable rows.
            jkanime_match = find_best_jkanime_match(series_title, alt_titles=av1_alt_titles)
            if jkanime_match:
                jkanime_info = fetch_jkanime_series_info(jkanime_match["slug"])
                if jkanime_info and jkanime_info.get("episode_count"):
                    jkanime_offset = _claimed_episode_offset(franchise_id, jkanime_match["slug"], canonical_id)
                    episodes = _build_episodes_from_jkanime(
                        canonical_id, jkanime_info["episode_count"], kitsu_eps, jikan_titles,
                        max_episodes=series.get("episode_count"), episode_offset=jkanime_offset,
                    )
                    if episodes:
                        series["fallback_slug"] = jkanime_match["slug"]
            if not episodes:
                episodes = _build_episodes_from_metadata(canonical_id, kitsu_eps, jikan_titles, series.get("media_type"))

        upsert_series(series)
        count = upsert_episodes(episodes)

        return {"status": "ok", "episodes_ingested": count, "principal_slug": series.get("principal_slug")}

    except Exception as exc:
        return {"status": f"error: {exc}", "episodes_ingested": 0}


@bp.route("/ingest", methods=["POST"])
def ingest():
    body = request.get_json(force=True) or {}
    mal_id = body.get("mal_id")
    fallback_slug = body.get("fallback_slug")
    animeav1_slug = body.get("animeav1_slug")

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
    canonical_id = existing["id"] if existing else (animeav1_slug or fallback_slug or f"mal-{mal_id_int}")

    series["id"] = canonical_id
    series["slug"] = canonical_id
    if fallback_slug:
        series["fallback_slug"] = fallback_slug

    # Discover full franchise (BFS) via Jikan relations
    print(f"  Discovering franchise via Jikan for mal_id={mal_id_int}...")
    franchise_entries = _discover_franchise_jikan(mal_id_int)
    franchise_id = str(franchise_entries[0]["mal_id"]) if franchise_entries else f"mal-{mal_id_int}"
    main_entry = next((e for e in franchise_entries if e["mal_id"] == mal_id_int), None)
    series["season_order"] = main_entry["order"] if main_entry else 1
    series["franchise_relation"] = main_entry["relation"] if main_entry else "root"
    series["franchise_id"] = franchise_id

    # Fetch Kitsu cover + episode metadata for main series
    kitsu_result = search_kitsu_anime(series.get("title", ""), alt_titles=series.get("titles"))
    kitsu_id = kitsu_result["id"] if kitsu_result else None
    if kitsu_result and kitsu_result.get("cover_url"):
        series["banner_url"] = kitsu_result["cover_url"]

    # See _kitsu_id_claimed_by_sibling: a kitsu_id already owned by another
    # franchise member isn't this series' own — don't apply its status/episodes.
    if kitsu_id and _kitsu_id_claimed_by_sibling(franchise_id, kitsu_id, mal_id_int):
        kitsu_id = None

    kitsu_eps = fetch_kitsu_episodes(kitsu_id) if kitsu_id else {}

    # Fetch Kitsu status and re-normalize with full simulcast metadata
    kitsu_status = fetch_kitsu_series_status(kitsu_id) if kitsu_id else None
    normalized_with_kitsu = normalize(raw, is_featured=series.get("is_featured", False), kitsu_id=kitsu_id, kitsu_status=kitsu_status)
    if normalized_with_kitsu:
        # Merge simulcast fields back into series dict (preserve already-set fields like id, slug, etc.)
        for field in ("broadcast_day", "broadcast_time", "broadcast_timezone", "aired_from",
                      "kitsu_id", "kitsu_status", "is_simulcast"):
            series[field] = normalized_with_kitsu.get(field)

    # Fetch episode titles from Jikan
    print(f"  Fetching episode titles from Jikan for mal_id={mal_id_int}...")
    jikan_titles = fetch_jikan_episodes(mal_id_int)

    # Build episodes for main series — priority: animeav1 > metadata.
    # principal_slug is only persisted once AnimeAV1 actually resolves episodes —
    # an unverified guess (e.g. the series' own canonical slug, as IngestTrigger
    # sends on first load) that scrapes empty must not be saved, or stream
    # resolution will silently 404 on it later.
    main_episodes = _build_episodes_from_animeav1(canonical_id, animeav1_slug, kitsu_eps, jikan_titles) if animeav1_slug else []
    if main_episodes:
        series["principal_slug"] = animeav1_slug
        # Detect DUB availability and persist to audio_formats.
        if _detect_av1_dub(animeav1_slug):
            series["audio_formats"] = ["sub", "dub"]
    else:
        # AnimeAV1 has nothing — try jkanime before falling back to a
        # metadata-only stub (see _ingest_related's identical waterfall).
        # Skip the auto-search when an admin already provided fallback_slug
        # explicitly (via fallback_slug body param) — don't override their choice.
        if not series.get("fallback_slug"):
            jk_alt_titles = list(series.get("titles") or [])
            if raw.get("title"):
                jk_alt_titles.append(raw["title"])
            jkanime_match = find_best_jkanime_match(series.get("title", ""), alt_titles=jk_alt_titles)
            if jkanime_match:
                jkanime_info = fetch_jkanime_series_info(jkanime_match["slug"])
                if jkanime_info and jkanime_info.get("episode_count"):
                    jkanime_offset = _claimed_episode_offset(franchise_id, jkanime_match["slug"], canonical_id)
                    main_episodes = _build_episodes_from_jkanime(
                        canonical_id, jkanime_info["episode_count"], kitsu_eps, jikan_titles,
                        max_episodes=series.get("episode_count"), episode_offset=jkanime_offset,
                    )
                    if main_episodes:
                        series["fallback_slug"] = jkanime_match["slug"]
        if not main_episodes:
            media_type = raw.get("type", "")
            main_episodes = _build_episodes_from_metadata(canonical_id, kitsu_eps, jikan_titles, media_type)

    upsert_series(series)
    main_count = upsert_episodes(main_episodes)

    # Ingest each related franchise member (skip the root entry)
    franchise_results = []
    for entry in franchise_entries:
        if entry["mal_id"] == mal_id_int:
            continue
        print(f"  Ingesting related [{entry['relation']}]: mal_id={entry['mal_id']} {entry.get('title', '')}")
        result = _ingest_related(entry, franchise_id)
        franchise_results.append({
            "mal_id": entry["mal_id"],
            "title": entry.get("title", ""),
            "relation": entry["relation"],
            "season_order": entry["order"],
            **result,
        })
        time.sleep(REQUEST_DELAY)

    return jsonify({
        "series_id": canonical_id,
        "series_title": series.get("title", ""),
        "episodes_ingested": main_count,
        "principal_slug": series.get("principal_slug"),
        "kitsu_id": kitsu_id,
        "kitsu_episodes_matched": len(kitsu_eps),
        "franchise_id": franchise_id,
        "franchise": franchise_results,
    }), 200


