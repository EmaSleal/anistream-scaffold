"""Flask Blueprint for authenticated watch-progress endpoints.

Routes (all require @require_auth):
  POST /api/progress                      — upsert progress for an episode
  GET  /api/progress/continue-watching    — continue-watching list (BEFORE <episode_id>)
  GET  /api/progress/<episode_id>         — get progress for a single episode

CRITICAL: The continue-watching route MUST be registered before <episode_id>
or Flask will match the literal string "continue-watching" as an episode_id.
"""
from flask import Blueprint, g, jsonify, request
from auth import require_auth
from db import progress as db_progress
from domain.progress import build_continue_watching

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
