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


def _map_recent_episode(row: dict) -> dict:
    """Map a raw DB row from get_recent_simulcast_episodes to a flat camelCase DTO."""
    s = row.get("series") or {}
    # Use aired_at if set; fall back to created_at date portion for episodes
    # discovered before Jikan indexed them (created_at is always present).
    aired_at = row.get("aired_at") or row.get("_effective_date") or (row.get("created_at") or "")[:10]
    return {
        "id": row.get("id"),
        "seriesId": row.get("series_id"),
        "episodeNumber": row.get("episode_number"),
        "title": row.get("title"),
        "thumbnailUrl": row.get("thumbnail_url"),
        "airedAt": aired_at or None,
        "animeflvSlug": row.get("animeflv_slug"),
        "seriesTitle": s.get("title"),
        "seriesThumbnailUrl": s.get("thumbnail_url"),
    }


@episode_bp.get("/recent-simulcast")
def recent_simulcast_episodes():
    """GET /api/episodes/recent-simulcast — public list of recently aired simulcast episodes.

    Query params:
        limit (int, optional): number of episodes to return; default 20, clamped to 50.

    Returns:
        200  JSON array of episode DTOs ordered by airedAt DESC.
    """
    limit = min(request.args.get("limit", 20, type=int), 50)
    rows = db_episodes.get_recent_simulcast_episodes(limit)
    return jsonify([_map_recent_episode(r) for r in rows]), 200


@episode_bp.get("/debug/servers/<path:episode_slug>")
def debug_episode_servers(episode_slug: str):
    """GET /api/episodes/debug/servers/<slug> — raw server list from AnimeFlv.

    Debug-only endpoint. Returns the raw ``var videos`` dict scraped from
    AnimeFlv for the given episode slug so you can inspect server codes.
    """
    from scraper_animeflv import scrape_episode_servers
    try:
        servers = scrape_episode_servers(episode_slug)
    except RuntimeError as exc:
        return {"error": str(exc)}, 502
    return {"slug": episode_slug, "servers": servers}, 200


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
