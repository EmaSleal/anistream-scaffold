"""Jellyfin placement of NAS downloads (ADR-020) — no Flask import.

A whole franchise is one Jellyfin show, named after its first TV member
(ADR-021): TV entries become "Season NN" (the same sequential index the series
page shows), movies/OVAs/specials go to "Season 00"
numbered consecutively. ``compute_placement`` is a pure function over rows that
are already loaded; ``placement`` loads them; ``job_naming`` builds the naming
kwargs for ``create_download_job`` with the ADR-018 fallback.
"""
from __future__ import annotations

import logging

from db import episodes as db_episodes
from db import series as db_series
from domain.series import (
    _PART_RE,
    build_seasons,
    is_released,
    map_episode_row,
    map_series_row,
    season_label,
)

logger = logging.getLogger(__name__)


def _base_title(title: str | None) -> str:
    return _PART_RE.sub("", title or "").strip()


def _is_tv_slot(media_type: str | None) -> bool:
    return season_label(media_type, 1).startswith("Temporada")


def _part_offset(
    series_id: str,
    members: list[dict],
    episodes_by_series: dict[str, list[dict]],
    order: dict[str, int],
) -> int:
    """Episode offset of a TV part within its season (ADR-023/024); 0 for a first part."""
    me = members[order[series_id]]
    base = _base_title(me.get("title"))
    earlier = [
        m for m in members
        if order[m["id"]] < order[series_id] and _base_title(m.get("title")) == base
    ]
    mine = [e.get("episode", 0) for e in episodes_by_series.get(series_id, [])]
    prior = [e.get("episode", 0) for m in earlier for e in episodes_by_series.get(m["id"], [])]
    if not earlier or not mine or not prior or min(mine) > max(prior):
        return 0
    return sum(m.get("episodeCount") or 0 for m in earlier)


def compute_placement(
    series_id: str,
    members: list[dict],
    episodes_by_series: dict[str, list[dict]],
) -> dict:
    """Return {show_title, show_year, season_number, episode_offset} for series_id.

    ``members`` are camelCase series dicts (map_series_row) in franchise order
    (season_order); ``episodes_by_series`` maps seriesId -> *released* camelCase
    episode dicts — the same input as ``build_seasons`` / ``/api/series/<id>/seasons``.

    Part siblings (same base title) collapse into one slot led by the first
    sibling and share its season number (ADR-023). TV slots are numbered like
    the series page. Slots with no released
    episodes are dropped by build_seasons, so for the requested series' own slot
    the season is derived from its position instead: TV index = number of
    output TV seasons led by an earlier member + 1 (it therefore shares a number
    with the next populated season until it gains released episodes). Empty
    non-TV slots contribute 0 to later offsets; non-TV offsets count episodes
    across all parts of earlier slots. A later TV part is offset by the sum of
    the official ``episodeCount`` of the earlier parts of its season (not the
    max episode number: AnimeAV1 pages can start at episode 0) only when its
    numbering restarts (ADR-024: its lowest released episode <= the highest
    released episode of the earlier parts); a continuation keeps offset 0, and
    so does a part with no released episodes. Raises LookupError when
    series_id is not among ``members``.
    """
    order = {m["id"]: i for i, m in enumerate(members)}
    if series_id not in order:
        raise LookupError(series_id)

    # ADR-021: name the show after the first TV member — season_order is
    # chronological, so a prequel movie may come first.
    first = next((m for m in members if _is_tv_slot(m.get("mediaType"))), members[0])
    show = {
        "show_title": _base_title(first.get("title")),
        "show_year": first.get("year") or None,
    }

    leader = next(
        m for m in members
        if _base_title(m.get("title")) == _base_title(members[order[series_id]].get("title"))
    )
    leader_idx = order[leader["id"]]

    seasons = build_seasons(members, episodes_by_series)["seasons"]
    tv_before = 0
    offset = 0
    for s in seasons:
        idx = min(order.get(p["seriesId"], len(members)) for p in s["parts"])
        if idx >= leader_idx:
            continue
        if _is_tv_slot(s.get("mediaType")):
            tv_before += 1
        else:
            offset += sum(
                max((e.get("episode", 0) for e in p["episodes"]), default=0) for p in s["parts"]
            )

    if _is_tv_slot(leader.get("mediaType")):
        return {**show, "season_number": tv_before + 1,
                "episode_offset": _part_offset(series_id, members, episodes_by_series, order)}
    return {**show, "season_number": 0, "episode_offset": offset}


def placement(series_id: str) -> dict:
    """Load the series' franchise and compute its Jellyfin placement.

    Raises LookupError for an unknown series; DB errors propagate to the caller.
    A series without franchise_id is its own show: season 1, offset 0.
    """
    row = db_series.get_series_by_id(series_id)
    if not row:
        raise LookupError(series_id)
    franchise_id = row.get("franchise_id")
    if not franchise_id:
        return {
            "show_title": row.get("title"),
            "show_year": row.get("year") or None,
            "season_number": 1,
            "episode_offset": 0,
        }

    members = [map_series_row(r) for r in db_series.get_series_by_franchise(franchise_id)]
    released: dict[str, list[dict]] = {}
    for m in members:
        eps = [map_episode_row(e) for e in db_episodes.get_episodes_by_series(m["id"])]
        released[m["id"]] = [e for e in eps if is_released(e.get("releasedAt"), e.get("thumbnailUrl"))]
    return compute_placement(series_id, members, released)


def job_naming(series_id: str, episode_number: int) -> dict:
    """kwargs for create_download_job: franchise placement, or the ADR-018 fallback.

    On any placement failure (DB error, unknown series) logs a warning and falls
    back to the series' own title/year with no season fields, so the job is
    still created.
    """
    try:
        p = placement(series_id)
        return {
            "series_title": p["show_title"],
            "series_year": p["show_year"],
            "season_number": p["season_number"],
            "file_episode_number": p["episode_offset"] + episode_number,
        }
    except Exception:
        logger.warning("[jellyfin_placement] placement failed for series=%s, using own title/year",
                       series_id, exc_info=True)
    try:
        meta = db_series.get_series_title_year_by_id(series_id) or {}
        return {"series_title": meta.get("title") or None, "series_year": meta.get("year") or None}
    except Exception:
        logger.warning("[jellyfin_placement] could not load title/year for series=%s", series_id)
        return {"series_title": None, "series_year": None}
