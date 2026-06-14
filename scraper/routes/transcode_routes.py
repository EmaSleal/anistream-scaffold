"""Flask Blueprint for AV1 → H.264 HLS transcoding proxy.

Endpoints are internal-only — the flask service is not exposed publicly.
Only the nextjs container (on the same Docker network) can reach these routes.

No authentication is applied here; network-level isolation is the boundary.
"""

import logging
import threading
from pathlib import Path

from flask import Blueprint, Response, abort, request, send_file

from domain.transcode import (
    CACHE_DIR,
    PROGRESSIVE_ENABLED,
    TRANSCODE_MIN_SEGMENTS,
    get_cache_path,
    purge_lru_if_needed,
    transcode_and_cache,
    transcode_progressive,
    update_last_accessed,
)

logger = logging.getLogger(__name__)

transcode_bp = Blueprint("transcode", __name__, url_prefix="/api/proxy/transcode")

_PLAYLIST_MIME = "application/vnd.apple.mpegurl"


def _serve_playlist(path: Path, video_id: str) -> Response:
    """Read a playlist file into memory and return it as a Response.

    Using read_bytes() instead of send_file() for playlists avoids a class of
    Docker-volume / FileWrapper edge cases where send_file() returns 0 bytes
    even when the file has content. Playlists are small (<1 MB) so this is safe.
    """
    try:
        content = path.read_bytes()
    except OSError as exc:
        logger.warning("[transcode] playlist read error video_id=%s path=%s: %s", video_id, path, exc)
        abort(500, description="Playlist file unreadable")

    if not content:
        logger.warning("[transcode] playlist is 0 bytes video_id=%s path=%s", video_id, path)
        abort(500, description="Playlist file is empty")

    logger.warning(
        "[transcode] serving playlist video_id=%s bytes=%d path=%s",
        video_id, len(content), path.name,
    )
    return Response(content, status=200, mimetype=_PLAYLIST_MIME)


@transcode_bp.get("/<video_id>/playlist.m3u8")
def serve_playlist(video_id: str) -> Response:
    """Return the H.264 HLS playlist for video_id.

    Query params:
        src (str): Original AV1 m3u8 URL — required only on cache miss.

    Behavior:
    - Cache hit (full VOD): serve immediately regardless of PROGRESSIVE_ENABLED.
    - PROGRESSIVE_ENABLED=1: call transcode_progressive(); return 202 if fewer
      than TRANSCODE_MIN_SEGMENTS segments are ready, 200 EVENT playlist once ready.
    - PROGRESSIVE_ENABLED=0: call transcode_and_cache() (existing behavior).
    """
    cached = get_cache_path(video_id)

    if cached is not None:
        # Cache hit — update LRU timestamp and kick off eviction check
        update_last_accessed(video_id)
        threading.Thread(target=purge_lru_if_needed, daemon=True).start()
        try:
            ts_count = sum(1 for _ in (CACHE_DIR / video_id).glob("seg*.ts"))
        except OSError:
            ts_count = -1
        logger.warning(
            "[transcode] playlist cache hit video_id=%s ts_files=%d",
            video_id, ts_count,
        )
        return _serve_playlist(cached, video_id)

    # Cache miss — source URL is required
    source_url = request.args.get("src", "").strip()
    if not source_url:
        logger.warning("[transcode] missing src param for video_id=%s", video_id)
        abort(400, description="Query param 'src' is required on cache miss")

    if PROGRESSIVE_ENABLED:
        # transcode_progressive() is non-blocking — starts the job and returns
        # the output path immediately. Readiness is determined by counting .ts
        # files on disk so it works correctly across gunicorn workers.
        try:
            playlist = transcode_progressive(video_id, source_url)
        except RuntimeError as exc:
            logger.warning("[transcode] progressive transcode failed for video_id=%s: %s", video_id, exc)
            abort(502, description=str(exc))

        # Full VOD cache takes priority (covers fallback path from transcode_and_cache).
        full_cache = get_cache_path(video_id)
        if full_cache is not None:
            update_last_accessed(video_id)
            threading.Thread(target=purge_lru_if_needed, daemon=True).start()
            return _serve_playlist(full_cache, video_id)

        # Count .ts segments on disk — works across all gunicorn workers.
        output_dir = CACHE_DIR / video_id
        seg_count = len(list(output_dir.glob("seg*.ts")))

        if seg_count < TRANSCODE_MIN_SEGMENTS:
            logger.warning(
                "[transcode] progressive video_id=%s not ready yet (%d/%d segments)",
                video_id, seg_count, TRANSCODE_MIN_SEGMENTS,
            )
            return Response(
                "Transcoding in progress — retry shortly",
                status=202,
                mimetype="text/plain",
            )

        # Guard: playlist must be non-empty — producer may have segments on disk
        # but not yet written the first EVENT playlist (batch still transcoding).
        try:
            if playlist.stat().st_size == 0:
                return Response(
                    "Transcoding in progress — retry shortly",
                    status=202,
                    mimetype="text/plain",
                )
        except OSError:
            return Response(
                "Transcoding in progress — retry shortly",
                status=202,
                mimetype="text/plain",
            )

        update_last_accessed(video_id)
        threading.Thread(target=purge_lru_if_needed, daemon=True).start()
        return _serve_playlist(playlist, video_id)

    # Standard (non-progressive) path
    try:
        playlist = transcode_and_cache(video_id, source_url)
    except RuntimeError as exc:
        logger.warning("[transcode] transcode failed for video_id=%s: %s", video_id, exc)
        abort(502, description=str(exc))

    update_last_accessed(video_id)
    threading.Thread(target=purge_lru_if_needed, daemon=True).start()

    return _serve_playlist(playlist, video_id)


@transcode_bp.get("/<video_id>/<filename>")
def serve_segment(video_id: str, filename: str) -> Response:
    """Serve a cached .ts segment file for video_id.

    Supports HTTP Range requests via Flask's conditional send_file so the
    player can seek without downloading the whole segment.
    """
    # Restrict to .ts files — reject anything else to avoid path traversal
    if not filename.endswith(".ts"):
        abort(400, description="Only .ts segment files are served here")

    # Prevent path traversal: filename must be a plain name with no directory parts
    if Path(filename).name != filename:
        abort(400, description="Invalid segment filename")

    segment_path = CACHE_DIR / video_id / filename
    if not segment_path.is_file():
        try:
            sample = sorted(f.name for f in (CACHE_DIR / video_id).iterdir())[:8]
        except OSError:
            sample = ["<dir missing>"]
        logger.warning(
            "[transcode] segment not found video_id=%s filename=%s dir_sample=%s",
            video_id, filename, sample,
        )
        abort(404)

    return send_file(
        segment_path,
        mimetype="video/MP2T",
        conditional=True,  # enables Range / 206 Partial Content
    )
