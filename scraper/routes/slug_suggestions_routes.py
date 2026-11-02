"""Admin endpoints for slug suggestions (ADR-016, T-009).

All routes require an admin JWT (``@require_admin``) and answer JSON only.

  GET  /api/admin/slug-suggestions?status=pending&page=1&per_page=20
  POST /api/admin/slug-suggestions/accept   {"id": "<uuid>"}
  POST /api/admin/slug-suggestions/deny     {"id": "<uuid>"}
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request
from werkzeug.exceptions import HTTPException

from auth import require_admin
from db import slug_suggestions as db
from db.series import get_series_by_id
from fetcher import fetch_jikan_episodes, fetch_kitsu_episodes
from routes.ingest_routes import (
    _build_episodes_from_animeav1,
    _build_episodes_from_jkanime,
    _claimed_episode_offset,
    _detect_av1_dub,
)
from scraper_jkanime import fetch_jkanime_series_info
from storage import upsert_episodes

slug_suggestions_bp = Blueprint(
    "slug_suggestions", __name__, url_prefix="/api/admin/slug-suggestions"
)

_STATUSES = ("pending", "accepted", "denied")
_SLUG_FIELD = {"animeav1": "principal_slug", "jkanime": "fallback_slug"}
_MAX_PER_PAGE = 100


@slug_suggestions_bp.errorhandler(Exception)
def _json_error(exc):
    if isinstance(exc, HTTPException):
        return jsonify({"error": exc.description or exc.name}), exc.code
    return jsonify({"error": f"Internal error: {exc}"}), 500


def _int_arg(name: str, default: int, minimum: int = 1, maximum: int | None = None) -> int:
    try:
        value = int(request.args.get(name, default))
    except (TypeError, ValueError):
        return default
    value = max(minimum, value)
    return min(value, maximum) if maximum else value


def _body_id():
    body = request.get_json(force=True, silent=True)
    sid = body.get("id") if isinstance(body, dict) else None
    if not isinstance(sid, str) or not sid.strip():
        return None
    return sid.strip()


@slug_suggestions_bp.get("")
@require_admin
def list_suggestions():
    status = request.args.get("status", "pending")
    if status not in _STATUSES:
        return jsonify({"error": f"status must be one of {', '.join(_STATUSES)}"}), 400
    page = _int_arg("page", 1)
    per_page = _int_arg("per_page", 20, maximum=_MAX_PER_PAGE)
    rows, total = db.list_suggestions(status, page, per_page)
    return jsonify({"items": rows, "total": total, "page": page, "per_page": per_page}), 200


def _load_pending(suggestion_id):
    """Return ``(suggestion, error_response)``; exactly one is None."""
    if not suggestion_id:
        return None, (jsonify({"error": "id is required"}), 400)
    suggestion = db.get_suggestion(suggestion_id)
    if not suggestion:
        return None, (jsonify({"error": "Suggestion not found"}), 404)
    if suggestion.get("status") != "pending":
        return None, (
            jsonify({"error": f"Suggestion is already {suggestion.get('status')}"}), 409
        )
    return suggestion, None


@slug_suggestions_bp.post("/accept")
@require_admin
def accept_suggestion():
    """Persist the slug and build the series' episodes from that page.

    Uses the ADR-012 offset rules. Answers 409 with a ``reason`` and writes
    nothing when the offset is undeterminable, the member is a capless
    continuation, or the source yields no episodes.
    """
    suggestion, err = _load_pending(_body_id())
    if err:
        return err

    series_id, source, slug = suggestion["series_id"], suggestion["source"], suggestion["slug"]
    field = _SLUG_FIELD.get(source)
    if not field:
        return jsonify({"error": f"Unknown source {source!r}"}), 422
    row = get_series_by_id(series_id)
    if not row:
        return jsonify({"error": "Series not found"}), 404

    offset = _claimed_episode_offset(row.get("franchise_id"), slug, series_id, row.get("season_order"))
    if offset is None:
        return jsonify({
            "error": "Cannot accept: shared-slug offset is undeterminable",
            "reason": "ambiguous_shared_slug_offset",
        }), 409
    max_episodes = row.get("episode_count")
    if offset > 0 and not max_episodes:
        return jsonify({
            "error": "Cannot accept: continuation without its own episode count",
            "reason": "capless_continuation",
        }), 409

    kitsu_id, mal_id = row.get("kitsu_id"), row.get("mal_id")
    kitsu_eps = fetch_kitsu_episodes(kitsu_id) if kitsu_id else {}
    jikan_titles = fetch_jikan_episodes(mal_id) if mal_id else {}

    extra = None
    if source == "animeav1":
        episodes = _build_episodes_from_animeav1(
            series_id, slug, kitsu_eps, jikan_titles,
            episode_offset=offset, max_episodes=max_episodes,
        )
        if episodes and _detect_av1_dub(slug):
            extra = {"audio_formats": ["sub", "dub"]}
    else:
        info = fetch_jkanime_series_info(slug)
        episodes = []
        if info and info.get("episode_count"):
            episodes = _build_episodes_from_jkanime(
                series_id, info["episode_count"], kitsu_eps, jikan_titles,
                max_episodes=max_episodes, episode_offset=offset,
            )
    if not episodes:
        return jsonify({
            "error": "Cannot accept: the source page yielded no episodes",
            "reason": "no_episodes",
        }), 409

    db.set_series_slug(series_id, field, slug, extra)
    count = upsert_episodes(episodes)
    if not db.mark_decided(suggestion["id"], "accepted"):
        # Lost a race with another decision. The slug / episode writes above are
        # idempotent (same ids, same slug), so retrying or re-reading is safe.
        return jsonify({"error": "Suggestion was already decided",
                        "reason": "already_decided"}), 409
    return jsonify({
        "id": suggestion["id"], "status": "accepted", "series_id": series_id,
        "source": source, "slug": slug, "episodes_ingested": count,
    }), 200


@slug_suggestions_bp.post("/deny")
@require_admin
def deny_suggestion():
    """Record the rejection; nothing else is written."""
    suggestion, err = _load_pending(_body_id())
    if err:
        return err
    if not db.mark_decided(suggestion["id"], "denied"):
        return jsonify({"error": "Suggestion was already decided",
                        "reason": "already_decided"}), 409
    return jsonify({"id": suggestion["id"], "status": "denied"}), 200
