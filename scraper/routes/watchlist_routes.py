"""Flask Blueprint for authenticated watchlist endpoints.

Routes (all require @require_auth):
  GET    /api/watchlist           — return full Series objects for the user
  POST   /api/watchlist           — add a series to the watchlist (idempotent)
  DELETE /api/watchlist/<series_id> — remove from watchlist (idempotent)
"""
from flask import Blueprint, g, jsonify, request
from auth import require_auth
from db import watchlist as db_watchlist
from domain.series import map_series_row

watchlist_bp = Blueprint("watchlist", __name__, url_prefix="/api")


@watchlist_bp.get("/watchlist")
@require_auth
def get_watchlist():
    """GET /api/watchlist — return Series objects ordered by added_at DESC."""
    rows = db_watchlist.get_watchlist(g.user_id)
    return jsonify([map_series_row(r) for r in rows]), 200


@watchlist_bp.post("/watchlist")
@require_auth
def add_to_watchlist():
    """POST /api/watchlist — add series_id to the watchlist.

    Body: { "series_id": "<id>" }
    Returns 400 if series_id is missing.
    """
    body = request.get_json(force=True, silent=True) or {}
    series_id = body.get("series_id")
    if not series_id:
        return jsonify({"error": "series_id is required"}), 400

    db_watchlist.add_to_watchlist(g.user_id, series_id)
    return jsonify({"ok": True}), 201


@watchlist_bp.delete("/watchlist/<series_id>")
@require_auth
def remove_from_watchlist(series_id: str):
    """DELETE /api/watchlist/<series_id> — remove from watchlist (idempotent).

    Returns 204 regardless of whether the row existed.
    """
    db_watchlist.remove_from_watchlist(g.user_id, series_id)
    return "", 204
