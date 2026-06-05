"""Flask Blueprint for authenticated watch-progress endpoints.

Routes (all require @require_auth):
  POST /api/progress                      — upsert progress for an episode
  GET  /api/progress/continue-watching    — continue-watching list (BEFORE <episode_id>)
  GET  /api/progress/<episode_id>         — get progress for a single episode

CRITICAL: The continue-watching route MUST be registered before <episode_id>
or Flask will match the literal string "continue-watching" as an episode_id.
"""
import logging
import threading
from datetime import datetime, timezone

from flask import Blueprint, g, jsonify, request
from auth import require_auth
from db import progress as db_progress
from domain.progress import build_continue_watching
from domain.simulcast import cooldown_elapsed, is_simulcast_candidate
from simulcast_check import run_simulcast_check

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

    # Capture user_id into a local variable BEFORE any thread spawn.
    # Flask g is request-scoped and MUST NOT be accessed from inside a thread.
    user_id = g.user_id

    # Resolve franchise IDs for deduplication
    unique_series_ids = list({r["series_id"] for r in progress_rows if r.get("series_id")})
    franchise_map = db_progress.get_series_franchise_map(unique_series_ids)

    # Fetch episode details for all episodes in the progress window
    episode_ids = [r["episode_id"] for r in progress_rows if r.get("episode_id")]
    episode_rows = db_progress.get_episodes_by_ids(episode_ids)

    # Fetch simulcast metadata for all series in a single batched query.
    series_meta = db_progress.get_series_simulcast_meta(unique_series_ids)

    # Evaluate each progress row (pre-filter) for simulcast candidate conditions.
    # CRITICAL: Must run over raw progress_rows, NOT build_continue_watching()'s
    # output — that function filters out >=95% completed episodes, removing exactly
    # the caught-up-on-last-episode rows we want to detect here.
    now_utc = datetime.now(timezone.utc)
    seen_series_spawned: set[str] = set()

    for row in progress_rows:
        sid = row.get("series_id")
        if not sid or sid not in series_meta:
            continue
        if sid in seen_series_spawned:
            continue

        meta = series_meta[sid]

        if not meta.get("animeflv_slug"):
            logging.warning("simulcast skip [%s]: no animeflv_slug", sid)
            continue

        if not cooldown_elapsed(meta.get("last_simulcast_check")):
            logging.warning("simulcast skip [%s]: cooldown active (last=%s)", sid, meta.get("last_simulcast_check"))
            continue

        ep_id = row.get("episode_id")
        ep_data = next((e for e in episode_rows if e.get("id") == ep_id), None)
        last_aired_at = ep_data.get("aired_at") if ep_data else None

        ep_num = ep_data.get("episode_number") if ep_data else None
        series_max_ep = meta.get("max_episode_number")
        if ep_num is None or series_max_ep is None or ep_num < series_max_ep:
            logging.warning("simulcast skip [%s]: ep_num=%s series_max=%s (not last ep)", sid, ep_num, series_max_ep)
            continue

        progress_sec = float(row.get("progress_sec") or 0)
        duration_sec = float(row.get("duration_sec") or 0)
        logging.warning(
            "simulcast candidate check [%s]: ep=%s is_simulcast=%s progress=%.0f duration=%.0f aired_at=%s",
            sid, ep_num, meta.get("is_simulcast"), progress_sec, duration_sec, last_aired_at,
        )

        if not is_simulcast_candidate(
            is_simulcast=meta.get("is_simulcast", False),
            progress_sec=progress_sec,
            duration_sec=duration_sec,
            last_aired_at=last_aired_at,
            broadcast_day=meta.get("broadcast_day"),
            broadcast_time=meta.get("broadcast_time"),
            broadcast_timezone=meta.get("broadcast_timezone"),
            now_utc=now_utc,
        ):
            logging.warning("simulcast skip [%s]: is_simulcast_candidate=False", sid)
            continue

        current_max_ep = series_max_ep
        slug = meta["animeflv_slug"]

        threading.Thread(
            target=run_simulcast_check,
            args=(user_id, sid, slug, current_max_ep),
            daemon=True,
        ).start()

        seen_series_spawned.add(sid)

    result = build_continue_watching(progress_rows, franchise_map, episode_rows)
    return jsonify(result), 200


@progress_bp.get("/progress/<episode_id>")
@require_auth
def get_episode_progress(episode_id: str):
    """GET /api/progress/<episode_id> — progress_sec for the given episode.

    Returns {"progress_sec": 0} if no row exists.
    """
    progress_sec = db_progress.get_episode_progress(g.user_id, episode_id)
    return jsonify({"progress_sec": progress_sec}), 200
