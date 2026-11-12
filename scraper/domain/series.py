"""Pure domain functions for series/episode data.

No database access here — all functions accept raw dicts and return
transformed dicts or values. This keeps business logic testable in isolation.
"""
import re
from datetime import date

# ---------------------------------------------------------------------------
# Media-type rank: higher number = higher priority when picking the
# "representative" entry for a consolidated franchise view.
# ---------------------------------------------------------------------------
MEDIA_TYPE_RANK: dict[str, int] = {
    "tv": 4,
    "movie": 3,
    "ova": 2,
    "special": 1,
    "ona": 1,
    "music": 0,
}

_PART_RE = re.compile(r"\s+[Pp]art[-\s]*\d+\s*.*$")

# camelCase keys from map_series_row that catalog/browse endpoints include in
# their response. Streaming-config keys (principalSlug, fallbackSlug,
# animeflvDisabled) and operational-metadata keys (broadcast*, airedFrom,
# kitsuStatus, lastSimulcastCheck) are intentionally absent.
_CATALOG_KEYS: frozenset[str] = frozenset({
    "id", "malId", "title", "slug", "description",
    "thumbnailUrl", "bannerUrl",
    "rating", "genres", "audioFormats",
    "seasonCount", "episodeCount", "year",
    "isSimulcast", "isFeatured", "score",
    "franchiseId", "seasonOrder", "franchiseRelation", "mediaType",
})


def strip_to_catalog(series: dict) -> dict:
    """Return only catalog-display fields from a fully mapped series dict."""
    return {k: v for k, v in series.items() if k in _CATALOG_KEYS}


def media_rank(media_type: str | None) -> int:
    """Return the numeric rank for a media_type string (default 0 for unknowns)."""
    return MEDIA_TYPE_RANK.get((media_type or "tv").lower(), 0)


def season_label(media_type: str | None, tv_index: int) -> str:
    """Return the display label for a season slot.

    tv_index is 1-based and applies only when media_type is TV (or missing —
    legacy/stub rows with no media_type recorded are assumed to be a real
    season). Any OTHER value — recognized-but-non-TV (movie/ova/ona/special)
    or unrecognized (e.g. Jikan's "CM"/"PV"/"TV Special"/"Music", or an
    oddly-typed crossover entry) — falls back to "Especial" rather than
    silently inflating the TV season count: a numbered "Temporada" should
    only ever come from an actual "tv" media_type.
    """
    if media_type is None:
        return f"Temporada {tv_index}"
    mt = media_type.lower()
    if mt == "tv":
        return f"Temporada {tv_index}"
    if mt == "movie":
        return "Película"
    if mt in ("ova", "ona"):
        return "OVA"
    return "Especial"


def map_series_row(row: dict) -> dict:
    """Map a snake_case Supabase series row to the camelCase shape
    expected by the TypeScript Series interface.
    """
    return {
        "id": row.get("id"),
        "malId": row.get("mal_id"),
        "title": row.get("title"),
        "slug": row.get("slug"),
        "description": row.get("description", ""),
        "thumbnailUrl": row.get("thumbnail_url", ""),
        "bannerUrl": row.get("banner_url", ""),
        "rating": row.get("rating", "14+"),
        "genres": row.get("genres") or [],
        "audioFormats": row.get("audio_formats") or ["sub"],
        "seasonCount": row.get("season_count", 1),
        "episodeCount": row.get("episode_count", 0),
        "year": row.get("year", 0),
        "isSimulcast": row.get("is_simulcast", False),
        "isFeatured": row.get("is_featured", False),
        "score": row.get("score"),
        "franchiseId": row.get("franchise_id"),
        "seasonOrder": row.get("season_order"),
        "franchiseRelation": row.get("franchise_relation"),
        "mediaType": row.get("media_type"),
        "principalSlug": row.get("principal_slug"),
        "fallbackSlug": row.get("fallback_slug"),
        "animeflvDisabled": bool(row.get("animeflv_disabled") or False),
        "broadcastDay": row.get("broadcast_day"),
        "broadcastTime": row.get("broadcast_time"),
        "broadcastTimezone": row.get("broadcast_timezone"),
        "airedFrom": row.get("aired_from"),
        "kitsuStatus": row.get("kitsu_status"),
        "lastSimulcastCheck": row.get("last_simulcast_check"),
    }


def map_episode_row(row: dict) -> dict:
    """Map a snake_case Supabase episode row to the camelCase shape
    expected by the TypeScript Episode interface.

    The ``series`` join key (if present) supplies seriesTitle.
    """
    series_join = row.get("series") or {}
    series_title = series_join.get("title") if isinstance(series_join, dict) else None
    ep_num = row.get("episode_number", 0)
    return {
        "id": row.get("id"),
        "seriesId": row.get("series_id"),
        "seriesTitle": series_title or row.get("series_id", ""),
        "season": 1,
        "episode": ep_num,
        "title": row.get("title") or f"Episode {ep_num}",
        "description": "",
        "thumbnailUrl": row.get("thumbnail_url", ""),
        "duration": row.get("duration_sec") or row.get("duration") or 0,
        "audioFormats": ["sub"],
        "rating": "14+",
        "releasedAt": row.get("aired_at") or "",
        "isSeen": False,
        "animeflvSlug": row.get("animeflv_slug"),
    }


def consolidate_franchises(series_list: list[dict]) -> list[dict]:
    """Return one representative entry per franchise.

    Selection rules (matching the TypeScript consolidateFranchises logic):
    - Series without a franchiseId pass through unchanged.
    - For each franchise, pick the member with the highest media-type rank
      (TV > Movie > OVA/ONA > Special > Music).
    - The coverImage (thumbnailUrl) is sourced from the latest TV season
      in the franchise; falls back to the absolute last member by seasonOrder.

    ``series_list`` must contain camelCase dicts (already mapped by map_series_row).
    """
    seen: set = set()
    result: list[dict] = []

    for s in series_list:
        franchise_id = s.get("franchiseId")
        if not franchise_id:
            result.append(s)
            continue
        if franchise_id in seen:
            continue
        seen.add(franchise_id)

        members = sorted(
            [m for m in series_list if m.get("franchiseId") == franchise_id],
            key=lambda m: (m.get("seasonOrder") or 1, media_rank(m.get("mediaType"))),
        )

        # Highest-rank member (by media type) as the representative
        best = max(members, key=lambda m: media_rank(m.get("mediaType")))

        # Thumbnail from the latest TV season, fallback to last member
        tv_members = [m for m in members if (m.get("mediaType") or "tv").lower() == "tv"]
        thumbnail_source = tv_members[-1] if tv_members else members[-1]

        result.append({
            **best,
            "thumbnailUrl": thumbnail_source.get("thumbnailUrl") or best.get("thumbnailUrl", ""),
        })

    return result


def part_merge(members_with_episodes: list[dict]) -> list[dict]:
    """Group franchise members that share a base title into one slot (ADR-023).

    Each item in ``members_with_episodes`` must be a dict with:
      - ``seriesId``: str
      - ``label``: str   (season label, already computed)
      - ``episodes``: list[dict]   (already mapped episode dicts)
      - ``mediaType``: str | None
      - ``baseTitle``: str   (pre-stripped base title, or computed here)
      - ``seasonOrder``: int | None

    Returns one slot per base title, led by its first item, with ``parts``: a
    list of ``{seriesId, label, episodes}`` in input order. The part label is
    "Parte N" from the part's position among ALL siblings (so it stays stable
    when an earlier part has no episodes). Each part keeps its own episodes —
    nothing is deduplicated or dropped; parts with no episodes are kept here
    and filtered by the caller.
    """
    part_map: dict[str, dict] = {}

    for item in members_with_episodes:
        base = item.get("baseTitle") or _PART_RE.sub("", item.get("label", "")).strip()
        slot = part_map.setdefault(base, {
            "label": item["label"],
            "mediaType": item.get("mediaType"),
            "baseTitle": base,
            "seasonOrder": item.get("seasonOrder"),
            "parts": [],
        })
        slot["parts"].append({
            "seriesId": item["seriesId"],
            "label": f"Parte {len(slot['parts']) + 1}",
            "episodes": list(item["episodes"]),
        })

    return list(part_map.values())


def build_seasons(
    franchise_members: list[dict],
    episodes_by_series: dict[str, list[dict]],
    requested_series_id: str | None = None,
) -> dict:
    """Build the seasons payload for the /seasons endpoint.

    Args:
        franchise_members: camelCase series dicts (from map_series_row), ordered by seasonOrder.
        episodes_by_series: mapping of seriesId -> list of camelCase episode dicts.
        requested_series_id: the series_id that was originally requested (used to set
            initialSeasonIdx / initialPartIdx to the correct season and part instead
            of always defaulting to the first franchise member).

    Returns:
        {
            "seasons": [{"label", "seriesId", "mediaType", "episodes",
                         "parts": [{"seriesId", "label", "episodes"}]}],
            "initialSeasonIdx": int,
            "initialPartIdx": int
        }

    A season's top-level ``seriesId``/``episodes`` are those of its first part,
    so a single-member season looks exactly as before.

    Steps:
        1. For each member, compute the base title and initial label.
        2. Call part_merge to group Part splits into one slot with ``parts``.
        3. Drop parts with zero episodes, then slots with no parts left.
        4. Re-number TV seasons sequentially (Temporada 1, 2, …).
        5. Compute initialSeasonIdx/initialPartIdx: prefer the slot holding
           requested_series_id, fall back to the requested (or first) member's
           baseTitle.
    """
    if not franchise_members:
        return {"seasons": [], "initialSeasonIdx": 0, "initialPartIdx": 0}

    # Build pre-merge items
    pre_merge: list[dict] = []
    for member in franchise_members:
        media_type = member.get("mediaType")
        series_id = member.get("id")
        episodes = episodes_by_series.get(series_id, [])
        episodes_sorted = sorted(episodes, key=lambda e: e.get("episode", 0))
        raw_title = member.get("title", "")
        base_title = _PART_RE.sub("", raw_title).strip()

        # Temporary label — TV index will be fixed during renumbering step
        lbl = season_label(media_type, member.get("seasonOrder") or 1)

        pre_merge.append({
            "seriesId": series_id,
            "label": lbl,
            "episodes": episodes_sorted,
            "mediaType": media_type,
            "baseTitle": base_title,
            "seasonOrder": member.get("seasonOrder"),
        })

    merged = []
    for slot in part_merge(pre_merge):
        parts = [p for p in slot["parts"] if p["episodes"]]
        if parts:
            merged.append({**slot, "parts": parts})

    # Renumber TV seasons sequentially
    tv_count = 0
    seasons: list[dict] = []
    for slot in merged:
        label = slot["label"]
        if label.startswith("Temporada"):
            tv_count += 1
            label = f"Temporada {tv_count}"
        seasons.append({
            "label": label,
            "seriesId": slot["parts"][0]["seriesId"],
            "mediaType": slot.get("mediaType"),
            "episodes": slot["parts"][0]["episodes"],
            "parts": slot["parts"],
        })

    # initialSeasonIdx: prefer the slot that matches the requested series, then fall
    # back to the first franchise member's baseTitle.
    initial_idx = 0
    initial_part_idx = 0
    base_titles = [s.get("baseTitle", "") for s in merged]
    found = False
    if requested_series_id:
        for i, s in enumerate(seasons):
            for j, part in enumerate(s["parts"]):
                if part["seriesId"] == requested_series_id:
                    initial_idx, initial_part_idx, found = i, j, True
                    break
            if found:
                break
        if not found:
            # requested series has no episodes of its own (its part was dropped);
            # fall back to baseTitle matching against the requested series title
            req_title = next(
                (m.get("title") or "" for m in franchise_members if m.get("id") == requested_series_id),
                "",
            )
            req_base = _PART_RE.sub("", req_title).strip()
            initial_idx = base_titles.index(req_base) if req_base in base_titles else 0
    else:
        first_base = _PART_RE.sub("", (franchise_members[0].get("title") or "")).strip()
        initial_idx = base_titles.index(first_base) if first_base in base_titles else 0

    return {"seasons": seasons, "initialSeasonIdx": initial_idx, "initialPartIdx": initial_part_idx}


def is_released(date_str: str | None, thumbnail_url: str | None = None) -> bool:
    """True if the episode should be visible to viewers.

    A set aired_at is authoritative: released only if it's today or earlier —
    this also catches the simulcast weekly-cadence fill
    (routes/simulcast_routes.py::_fill_aired_at_from_cadence) extrapolating a
    future date for an episode AnimeAV1 has only pre-generated a thumbnail
    for.

    With no aired_at at all, fall back to thumbnail_url: jkanime-only
    placeholder rows (a source that reports just a total episode count, see
    _build_episodes_from_jkanime) have neither and must stay hidden. But
    AnimeAV1-sourced episodes always carry a real screenshot thumbnail even
    when Jikan/Kitsu enrichment failed to supply aired_at (confirmed live on
    Slime Season 1) — treat those as already released rather than masking a
    working ingest as "no episodes" and looping the reingest UI.
    """
    if date_str:
        return str(date_str)[:10] <= date.today().isoformat()
    return bool(thumbnail_url)
