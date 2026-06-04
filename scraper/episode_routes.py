"""Flask Blueprint for public episode endpoints."""
from flask import Blueprint, request, jsonify
from db import episodes as db_episodes
from db import series as db_series
from domain.series import map_episode_row
from domain.stream import orchestrate_stream, NoSourceError, UpstreamError

episode_bp = Blueprint("episodes", __name__, url_prefix="/api/episodes")


@episode_bp.get("/watch/<watch_id>")
def watch_episode(watch_id: str):
    """GET /api/episodes/watch/<id> — dual-lookup by slug then UUID."""
    row = db_episodes.get_episode_for_watch(watch_id)
    if not row:
        return jsonify({"error": "Episode not found"}), 404

    episode = map_episode_row(row)
    return jsonify({
        "episode": episode,
        "animeflvSlug": row.get("animeflv_slug"),
    })


@episode_bp.get("/watch/<watch_id>/stream-url")
def watch_episode_stream(watch_id: str):
    """GET /api/episodes/watch/<id>/stream-url — resolve a playable stream URL.

    Accepts both UUID and animeflv_slug (dual-lookup via get_episode_for_watch).
    Returns:
        200  { url, source }            — stream resolved
        404  { error }                  — episode not found or no source
        503  { error }                  — upstream scraping failure
    """
    row = db_episodes.get_episode_for_watch(watch_id)
    if not row:
        return jsonify({"error": "Episode not found"}), 404

    series_id = row.get("series_id")
    stream_config = db_series.get_stream_config(series_id)
    if not stream_config:
        return jsonify({"error": "Series not found"}), 404

    try:
        result = orchestrate_stream(row, stream_config)
        return jsonify({"url": result["url"], "source": result["source"]}), 200
    except NoSourceError:
        return jsonify({"error": "No stream source available for this episode"}), 404
    except UpstreamError:
        return jsonify({"error": "Upstream scraping error"}), 503


@episode_bp.get("/<series_id>/adjacent")
def adjacent_episodes(series_id: str):
    """GET /api/episodes/<series_id>/adjacent?episode_number=N — prev/next."""
    ep_number_param = request.args.get("episode_number")
    if ep_number_param is None:
        return jsonify({"error": "Missing required parameter: episode_number"}), 400

    try:
        ep_number = int(ep_number_param)
    except (TypeError, ValueError):
        return jsonify({"error": "episode_number must be an integer"}), 400

    adjacent = db_episodes.get_adjacent_episodes(series_id, ep_number)
    return jsonify({
        "prev": map_episode_row(adjacent["prev"]) if adjacent["prev"] else None,
        "next": map_episode_row(adjacent["next"]) if adjacent["next"] else None,
    })
