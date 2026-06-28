"""Flask Blueprint for authenticated watch-progress endpoints.

Routes (all require @require_auth):
  POST /api/progress                      — upsert progress for an episode
  GET  /api/progress/continue-watching    — continue-watching list (BEFORE <episode_id>)
  GET  /api/progress/history              — watch-history list (BEFORE <episode_id>)
  GET  /api/progress/recent-series        — recently watched series (BEFORE <episode_id>)
  GET  /api/progress/<episode_id>         — get progress for a single episode

CRITICAL: Literal-string routes MUST be registered before <episode_id>
or Flask will match them as an episode_id parameter.
"""
import logging

from flask import Blueprint, g, jsonify, request
from auth import require_auth
from db import progress as db_progress
from domain.progress import build_continue_watching, build_watch_history
from domain.series import map_episode_row, map_series_row

progress_bp = Blueprint("progress", __name__, url_prefix="/api")


@progress_bp.post("/progress")
@require_auth
def upsert_progress():
    """POST /api/progress — upsert a watch_progress row.

    Required body fields: episode_id, series_id, progress_sec
    Optional: duration_sec (defaults to 0 if absent — never returns 400 for it)
    Returns 400 if any required field is missing.
    """
    body = request.get_json(force=True, silent=True) or {}

    episode_id = body.get("episode_id")
    series_id = body.get("series_id")
    progress_sec = body.get("progress_sec")

    if episode_id is None or series_id is None or progress_sec is None:
        return jsonify({"error": "episode_id, series_id, and progress_sec are required"}), 400

    # duration_sec is nullable — default to 0 if absent
    duration_sec = body.get("duration_sec") or 0

    db_progress.upsert_progress(
        user_id=g.user_id,
        episode_id=episode_id,
        series_id=series_id,
        progress_sec=float(progress_sec),
        duration_sec=float(duration_sec),
    )
    return jsonify({"ok": True}), 200


@progress_bp.post("/progress/advance")
@require_auth
def advance_episode():
    """POST /api/progress/advance — mark current episode watched, seed next at 0.

    Required body fields: current_episode_id, current_series_id, duration_sec,
                          next_episode_id, next_series_id
    Returns 400 if next_episode_id is absent.
    """
    body = request.get_json(force=True, silent=True) or {}

    next_episode_id = body.get("next_episode_id")
    if not next_episode_id:
        return jsonify({"error": "missing next_episode_id"}), 400

    current_episode_id = body.get("current_episode_id")
    current_series_id = body.get("current_series_id")
    duration_sec = body.get("duration_sec", 0)
    next_series_id = body.get("next_series_id", "")

    db_progress.advance_episode(
        user_id=g.user_id,
        current_ep_id=current_episode_id,
        current_series_id=current_series_id,
        duration_sec=float(duration_sec),
        next_ep_id=next_episode_id,
        next_series_id=next_series_id,
    )
    return jsonify({"advanced": True}), 200


# IMPORTANT: This route is defined BEFORE /progress/<episode_id> to prevent
# Flask from matching "continue-watching" as an episode_id parameter.
@progress_bp.get("/progress/continue-watching")
@require_auth
def continue_watching():
    """GET /api/progress/continue-watching — enriched continue-watching list."""
    progress_rows = db_progress.get_recent_progress(g.user_id, limit=30)
    if not progress_rows:
        return jsonify([]), 200

    # Resolve franchise IDs for deduplication
    unique_series_ids = list({r["series_id"] for r in progress_rows if r.get("series_id")})
    franchise_map = db_progress.get_series_franchise_map(unique_series_ids)

    # Fetch episode details for all episodes in the progress window
    episode_ids = [r["episode_id"] for r in progress_rows if r.get("episode_id")]
    episode_rows = db_progress.get_episodes_by_ids(episode_ids)

    # Fetch simulcast metadata for all series in a single batched query.
    series_meta = db_progress.get_series_simulcast_meta(unique_series_ids)

    result = build_continue_watching(progress_rows, franchise_map, episode_rows)

    # Simulcast look-ahead: for each simulcast series, check if the next episode
    # (current_ep + 1) is already in the DB. If yes, synthesize a CW entry with
    # progressSeconds=0. Purely additive — never removes or modifies existing
    # entries. All DB access is synchronous; no external HTTP calls.
    simulcast_ids = [
        sid for sid in unique_series_ids
        if series_meta.get(sid, {}).get("is_simulcast")
    ]
    if simulcast_ids:
        episode_id_set = set(episode_ids)
        episode_by_id = {ep["id"]: ep for ep in episode_rows}

        # Find the user's most-recent episode number per simulcast series.
        # progress_rows are ordered updated_at DESC, so first match = most recent.
        series_current_ep: dict[str, int] = {}
        for row in progress_rows:
            sid = row.get("series_id")
            if sid not in simulcast_ids or sid in series_current_ep:
                continue
            ep_data = episode_by_id.get(row.get("episode_id"))
            if ep_data is None:
                continue
            ep_num = ep_data.get("episode_number")
            if ep_num is not None:
                series_current_ep[sid] = ep_num

        if series_current_ep:
            # Single batched query for all simulcast series episodes.
            try:
                from storage import get_client
                eps_result = (
                    get_client()
                    .table("episodes")
                    .select("id, series_id, episode_number, aired_at, title, thumbnail_url, animeflv_slug")
                    .in_("series_id", list(series_current_ep.keys()))
                    .execute()
                )
                lookahead_eps = eps_result.data or []
            except Exception:
                logging.warning("simulcast look-ahead query failed; skipping", exc_info=True)
                lookahead_eps = []

            # Build lookup: {series_id: {episode_number: episode_row}}
            eps_by_series: dict[str, dict[int, dict]] = {}
            for ep in lookahead_eps:
                sid = ep.get("series_id")
                ep_num = ep.get("episode_number")
                if sid is not None and ep_num is not None:
                    eps_by_series.setdefault(sid, {})[ep_num] = ep

            # Synthesize a CW entry for each simulcast series where the next
            # episode is available but not yet in the user's progress.
            for sid, current_num in series_current_ep.items():
                next_ep = eps_by_series.get(sid, {}).get(current_num + 1)
                if next_ep is None:
                    continue
                if next_ep["id"] in episode_id_set:
                    # User already has progress on the next episode; skip.
                    continue
                result.append({
                    "episode": map_episode_row(next_ep),
                    "progressSeconds": 0,
                    "seriesId": sid,
                })

    return jsonify(result), 200


@progress_bp.get("/progress/watched-episodes")
@require_auth
def get_watched_episodes():
    """GET /api/progress/watched-episodes — episode IDs the authenticated user has started watching.

    Uses g.user_id from the bearer token — no user_id in URL.
    Returns episodes where progress_sec > 0 and remaining time <= 120s (considered watched).
    """
    try:
        from storage import get_client
        series_id = request.args.get("series_id")
        query = (
            get_client()
            .table("watch_progress")
            .select("episode_id, progress_sec, duration_sec")
            .eq("user_id", g.user_id)
            .gt("progress_sec", 0)
        )
        if series_id:
            query = query.eq("series_id", series_id)
        result = query.execute()
        rows = [
            {
                "episode_id": row["episode_id"],
                "progress_sec": row["progress_sec"],
                "duration_sec": row["duration_sec"],
            }
            for row in (result.data or [])
        ]
        return jsonify(rows), 200
    except Exception as e:
        logging.error("get_watched_episodes failed: %s", e)
        return jsonify({"error": "Failed to fetch watched episodes"}), 500


@progress_bp.get("/progress/last-in-franchise")
@require_auth
def last_watched_in_franchise():
    """GET /api/progress/last-in-franchise?series_ids=id1,id2,id3

    Returns the series_id (from the provided list) with the most recent
    watch_progress row for the authenticated user.
    """
    series_ids_param = request.args.get("series_ids", "")
    series_ids = [s.strip() for s in series_ids_param.split(",") if s.strip()]
    if not series_ids:
        return jsonify({"series_id": None}), 200

    try:
        from storage import get_client
        result = (
            get_client()
            .table("watch_progress")
            .select("series_id, updated_at")
            .eq("user_id", g.user_id)
            .in_("series_id", series_ids)
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )
        series_id = result.data[0]["series_id"] if result.data else None
        return jsonify({"series_id": series_id}), 200
    except Exception as e:
        logging.error("last_watched_in_franchise failed: %s", e)
        return jsonify({"error": "Failed to fetch last watched series"}), 500


# IMPORTANT: This route is defined BEFORE /progress/<episode_id> to prevent
# Flask from matching "history" as an episode_id parameter.
@progress_bp.get("/progress/history")
@require_auth
def watch_history():
    """GET /api/progress/history?limit=N — enriched watch-history list.

    Returns up to `limit` (default 25, max 50) most-recently-watched episodes
    in reverse-chronological order. No completion filter, no franchise dedup.
    """
    raw_limit = request.args.get("limit", 25, type=int)
    # Cap silently — never reject with an error
    limit = min(max(raw_limit, 1), 50)

    progress_rows = db_progress.get_recent_progress(g.user_id, limit=limit)
    if not progress_rows:
        return jsonify([]), 200

    episode_ids = [r["episode_id"] for r in progress_rows if r.get("episode_id")]
    episode_rows = db_progress.get_episodes_by_ids(episode_ids)

    result = build_watch_history(progress_rows, episode_rows, limit)
    return jsonify(result), 200


# IMPORTANT: Registered BEFORE /progress/<episode_id> to prevent Flask from
# matching "recent-series" as an episode_id parameter.
@progress_bp.get("/progress/recent-series")
@require_auth
def recent_series():
    """GET /api/progress/recent-series?limit=N — recently watched series.

    Returns up to `limit` (default 10, max 25) unique series/franchises ordered
    by most recently watched. Deduplicates by franchise_id so only one entry per
    franchise appears. No episode enrichment — returns Series-shaped objects.
    """
    raw_limit = request.args.get("limit", 10, type=int)
    limit = min(max(raw_limit, 1), 25)

    # Fetch more rows than needed to survive franchise deduplication
    progress_rows = db_progress.get_recent_progress(g.user_id, limit=limit * 4)
    if not progress_rows:
        return jsonify([]), 200

    unique_series_ids = list({r["series_id"] for r in progress_rows if r.get("series_id")})
    franchise_map = db_progress.get_series_franchise_map(unique_series_ids)

    # Walk rows (already updated_at DESC) and keep first series per franchise
    seen_franchises: set[str] = set()
    deduped_series_ids: list[str] = []
    for row in progress_rows:
        sid = row.get("series_id")
        if not sid:
            continue
        franchise_id = franchise_map.get(sid, sid)
        if franchise_id not in seen_franchises:
            seen_franchises.add(franchise_id)
            deduped_series_ids.append(sid)
        if len(deduped_series_ids) >= limit:
            break

    if not deduped_series_ids:
        return jsonify([]), 200

    series_rows = db_progress.get_series_by_ids(deduped_series_ids)
    series_map = {s["id"]: s for s in series_rows}
    result = [map_series_row(series_map[sid]) for sid in deduped_series_ids if sid in series_map]
    return jsonify(result), 200


@progress_bp.get("/progress/<episode_id>")
@require_auth
def get_episode_progress(episode_id: str):
    """GET /api/progress/<episode_id> — progress_sec for the given episode.

    Returns {"progress_sec": 0} if no row exists.
    """
    progress_sec = db_progress.get_episode_progress(g.user_id, episode_id)
    return jsonify({"progress_sec": progress_sec}), 200

