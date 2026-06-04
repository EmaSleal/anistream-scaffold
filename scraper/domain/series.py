"""Pure domain functions for series/episode data.

No database access here — all functions accept raw dicts and return
transformed dicts or values. This keeps business logic testable in isolation.
"""
import re

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


def media_rank(media_type: str | None) -> int:
    """Return the numeric rank for a media_type string (default 0 for unknowns)."""
    return MEDIA_TYPE_RANK.get((media_type or "tv").lower(), 0)


def season_label(media_type: str | None, tv_index: int) -> str:
    """Return the display label for a season slot.

    tv_index is 1-based and applies only when media_type is TV.
    """
    mt = (media_type or "tv").lower()
    if mt == "movie":
        return "Película"
    if mt in ("ova", "ona"):
        return "OVA"
    if mt == "special":
        return "Especial"
    # Default: TV or unknown
    return f"Temporada {tv_index}"


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
        "animeflvSlug": row.get("animeflv_slug"),
        "animeav1Slug": row.get("animeav1_slug"),
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
    """Merge franchise members that share a base title (Part 1 / Part 2 splitting).

    Each item in ``members_with_episodes`` must be a dict with:
      - ``seriesId``: str
      - ``label``: str   (season label, already computed)
      - ``episodes``: list[dict]   (already mapped episode dicts)
      - ``mediaType``: str | None
      - ``baseTitle``: str   (pre-stripped base title, or computed here)
      - ``seasonOrder``: int | None

    Returns a list with Part 1 / Part 2 siblings collapsed into one entry.
    Episodes are merged and sorted by ``episode`` key ascending.
    """
    part_map: dict[str, dict] = {}

    for item in members_with_episodes:
        base = item.get("baseTitle") or _PART_RE.sub("", item.get("label", "")).strip()
        if base in part_map:
            existing = part_map[base]
            merged_eps = existing["episodes"] + item["episodes"]
            merged_eps.sort(key=lambda e: e.get("episode", 0))
            existing["episodes"] = merged_eps
        else:
            part_map[base] = {
                "label": item["label"],
                "seriesId": item["seriesId"],
                "episodes": list(item["episodes"]),
                "mediaType": item.get("mediaType"),
                "baseTitle": base,
                "seasonOrder": item.get("seasonOrder"),
            }

    return list(part_map.values())


def build_seasons(franchise_members: list[dict], episodes_by_series: dict[str, list[dict]]) -> dict:
    """Build the seasons payload for the /seasons endpoint.

    Args:
        franchise_members: camelCase series dicts (from map_series_row), ordered by seasonOrder.
        episodes_by_series: mapping of seriesId -> list of camelCase episode dicts.

    Returns:
        {
            "seasons": [{"label": str, "seriesId": str, "episodes": list}],
            "initialSeasonIdx": int   (index of the first member passed in, after merging)
        }

    Steps:
        1. For each member, compute the base title and initial label.
        2. Call part_merge to collapse Part splits.
        3. Re-number TV seasons sequentially (Temporada 1, 2, …).
        4. Filter out seasons with zero episodes.
        5. Compute initialSeasonIdx from the first franchise_member's baseTitle.
    """
    if not franchise_members:
        return {"seasons": [], "initialSeasonIdx": 0}

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

    merged = part_merge(pre_merge)

    # Filter to entries with at least one episode
    merged = [s for s in merged if s["episodes"]]

    # Renumber TV seasons sequentially
    tv_count = 0
    seasons: list[dict] = []
    for slot in merged:
        if slot["label"].startswith("Temporada"):
            tv_count += 1
            slot = {**slot, "label": f"Temporada {tv_count}"}
        seasons.append({"label": slot["label"], "seriesId": slot["seriesId"], "episodes": slot["episodes"]})

    # initialSeasonIdx: index of the first franchise member's base title after merge
    first_base = _PART_RE.sub("", (franchise_members[0].get("title") or "")).strip()
    base_titles = [s.get("baseTitle", "") for s in merged]
    initial_idx = base_titles.index(first_base) if first_base in base_titles else 0

    return {"seasons": seasons, "initialSeasonIdx": initial_idx}
