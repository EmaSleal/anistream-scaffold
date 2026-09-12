"""Flask Blueprint for admin downloads endpoints.

All routes require @require_admin (401 without token, 403 for non-ADMIN role).

Endpoints:
  GET  /api/admin/downloads/episodes/<series_id>
  GET  /api/admin/downloads/sources/<series_id>?episode_number=N
  POST /api/admin/downloads/trigger
  GET  /api/admin/downloads/jobs/<job_id>
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import Blueprint, jsonify, request

from auth import require_admin
from db import episodes as db_episodes
from db import series as db_series
from domain.download_sources import probe_sources, resolve_source
from domain.nas_jobs import NasUnavailable, check_episode_status, create_download_job, get_job_status, nas_configured

logger = logging.getLogger(__name__)

downloads_bp = Blueprint("downloads", __name__, url_prefix="/api/admin/downloads")

_NAS_WORKERS = 8


@downloads_bp.get("/episodes/<series_id>")
@require_admin
def list_episodes_with_status(series_id: str):
    """Return all episodes for a series with their NAS download status.

    Uses a bounded thread pool to fan out per-episode NAS checks in parallel.
    Falls back to status="unknown" for every episode when NAS is not configured
    or when individual checks fail.

    Returns:
        200  {"episodes": [{episode_number, title, status}]}
        200  {"episodes": []} when the series has no episodes
    """
    episodes = db_episodes.get_episodes_by_series(series_id)

    if not episodes:
        return jsonify({"episodes": []}), 200

    if not nas_configured():
        return jsonify({
            "episodes": [
                {
                    "episode_number": ep["episode_number"],
                    "title": ep.get("title") or "",
                    "status": "unknown",
                }
                for ep in episodes
            ]
        }), 200

    status_map: dict[int, str] = {}

    def _check(ep: dict) -> tuple[int, str]:
        try:
            status = check_episode_status(series_id, ep["episode_number"])
        except Exception:
            status = "unknown"
        return ep["episode_number"], status

    with ThreadPoolExecutor(max_workers=_NAS_WORKERS) as pool:
        futures = {pool.submit(_check, ep): ep for ep in episodes}
        for future in as_completed(futures):
            try:
                ep_num, status = future.result()
                status_map[ep_num] = status
            except Exception:
                ep = futures[future]
                status_map[ep["episode_number"]] = "unknown"

    return jsonify({
        "episodes": [
            {
                "episode_number": ep["episode_number"],
                "title": ep.get("title") or "",
                "status": status_map.get(ep["episode_number"], "unknown"),
            }
            for ep in episodes
        ]
    }), 200


@downloads_bp.get("/sources/<series_id>")
@require_admin
def list_sources(series_id: str):
    """Return available stream sources for one episode of a series.

    Query params:
        episode_number (int, required)

    Returns:
        200  {"sources": [{source, available}]}
        400  {"error": "episode_number required"} when the param is absent/invalid
        404  {"error": "Series not found"} when stream_config is absent
    """
    raw_ep = request.args.get("episode_number", "")
    try:
        episode_number = int(raw_ep)
    except (ValueError, TypeError):
        return jsonify({"error": "episode_number required"}), 400

    stream_config = db_series.get_stream_config(series_id)
    if stream_config is None:
        return jsonify({"error": "Series not found"}), 404

    sources = probe_sources(stream_config, episode_number)
    return jsonify({"sources": sources}), 200


@downloads_bp.post("/trigger")
@require_admin
def trigger_download():
    """Resolve a source URL and atomically create a NAS download job.

    Request body: {series_id, episode_number, source}

    The raw CDN URL is resolved and forwarded to the NAS within this single
    request — it is never surfaced to the browser.

    Returns:
        202  {"jobId": str, "status": str}
        400  {"error": "Missing required fields"} when body is incomplete
        404  {"error": "Series not found"} when stream_config is absent
        422  {"error": "no_source"} when the chosen provider cannot resolve a URL
        503  {"error": "nas_unavailable"} when the NAS rejects or is unreachable
    """
    body = request.get_json(silent=True) or {}
    series_id = body.get("series_id", "")
    source = body.get("source", "")
    try:
        episode_number = int(body.get("episode_number", ""))
    except (ValueError, TypeError):
        return jsonify({"error": "Missing required fields"}), 400

    if not series_id or not source:
        return jsonify({"error": "Missing required fields"}), 400

    stream_config = db_series.get_stream_config(series_id)
    if stream_config is None:
        return jsonify({"error": "Series not found"}), 404

    url = resolve_source(stream_config, episode_number, source)
    if not url:
        return jsonify({"error": "no_source"}), 422

    try:
        job = create_download_job(series_id, episode_number, url, source)
    except NasUnavailable:
        return jsonify({"error": "nas_unavailable"}), 503

    return jsonify(job), 202


@downloads_bp.get("/jobs/<job_id>")
@require_admin
def get_job(job_id: str):
    """Proxy a NAS job status check.

    Always returns 200; uses {"status": "unknown"} when the NAS is unreachable
    or when the job ID is not found.

    Returns:
        200  {"status": str, "error"?: str}
    """
    result = get_job_status(job_id)
    return jsonify(result), 200
