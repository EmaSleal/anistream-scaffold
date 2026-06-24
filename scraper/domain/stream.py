"""Domain logic for stream URL resolution.

Internal orchestration module — not a public HTTP route.
All public scraper calls are wrapped here; callers (route handlers, tests)
never import the scrapers directly for stream resolution.

Return shape for internal resolver helpers:
    { "url": str | None, "error_type": "no_source" | "network_error" | None }

Raised exceptions from orchestrate_stream:
    NoSourceError  — no usable URL found (map to HTTP 404)
    UpstreamError  — network or parse failure (map to HTTP 503)
"""

import re
import logging
import requests
from urllib.parse import quote
from config import NAS_BASE_URL, NAS_API_KEY

logger = logging.getLogger(__name__)


class NoSourceError(Exception):
    """Raised when no stream URL can be resolved (no_source)."""


class UpstreamError(Exception):
    """Raised when an upstream scraping call fails (network/parse error)."""


def resolve_nas_stream(series_id: str, episode_number: int) -> dict:
    """Check whether the NAS already has a local copy of this episode.

    Returns the NAS download URL when found so the orchestrator can skip all
    stream-site dependencies.  Network errors fall through silently — a NAS
    outage must never break playback.

    Returns:
        { "url": str | None, "error_type": "no_source" | "network_error" | None }
    """
    try:
        resp = requests.get(
            f"{NAS_BASE_URL}/api/episodes/{series_id}/{episode_number}",
            headers={"X-API-Key": NAS_API_KEY},
            timeout=5,
        )
    except Exception:
        logger.warning("[stream] NAS unreachable for series=%s ep=%s", series_id, episode_number)
        return {"url": None, "error_type": "network_error"}

    if resp.status_code == 404:
        return {"url": None, "error_type": "no_source"}

    if not resp.ok:
        logger.warning("[stream] NAS error %s for series=%s ep=%s", resp.status_code, series_id, episode_number)
        return {"url": None, "error_type": "network_error"}

    data = resp.json()
    file_id = data.get("id")
    url = f"{NAS_BASE_URL}/api/files/{file_id}/download"
    logger.warning("[stream] NAS hit for series=%s ep=%s → %s", series_id, episode_number, url)
    return {"url": url, "error_type": None}


def resolve_animeflv_stream(episode_slug: str) -> dict:
    """Attempt to resolve a stream URL via the animeflv scraper.

    Wraps the animeflv scraper logic extracted from the legacy /api/stream
    route.  Handles both failure modes from the original handler:
      1. Non-fatal return (no compatible server found) — translates to
         error_type="no_source".
      2. Raised exception (network/parse error) — translates to
         error_type="network_error".

    Returns:
        { "url": str | None, "error_type": "no_source" | "network_error" | None }
    """
    from scraper_animeflv import scrape_episode_servers
    from extractor import extract_streamtape, ExtractionError

    try:
        servers = scrape_episode_servers(episode_slug)
    except RuntimeError as exc:
        logger.warning("[stream] animeflv scrape failed for slug=%s: %s", episode_slug, exc)
        return {"url": None, "error_type": "network_error"}

    all_codes = [
        s.get("title", "") or s.get("code", "")
        for lang in servers.values()
        for s in lang
    ]
    logger.warning("[stream] animeflv servers for slug=%s: %s", episode_slug, all_codes)

    video_id = None
    for lang_servers in servers.values():
        for s in lang_servers:
            code = s.get("code", "") or ""
            if "streamtape" in code.lower():
                m = re.search(r"streamtape\.[^/]+/e/([^/?&\"']+)", code)
                if m:
                    video_id = m.group(1)
                    break
        if video_id:
            break

    if not video_id:
        logger.warning("[stream] no streamtape server found for slug=%s", episode_slug)
        return {"url": None, "error_type": "no_source"}

    try:
        url = extract_streamtape(video_id)
        logger.warning("[stream] streamtape resolved for slug=%s", episode_slug)
        return {"url": url, "error_type": None}
    except ExtractionError as exc:
        logger.warning("[stream] streamtape extraction failed for slug=%s: %s", episode_slug, exc)
        return {"url": None, "error_type": "network_error"}


def resolve_animeav1_stream(serie_slug: str, episode_number: int) -> dict:
    """Attempt to resolve a stream URL via the AnimeAV1 scraper.

    Calls scraper_animeav1 to extract the Zilla hash for the episode, constructs
    the raw Zilla m3u8 URL, then wraps it in the server-side proxy URL so the
    caller receives a self-contained playable URL that enforces the required
    Referer header.

    Returns:
        { "url": str | None, "error_type": "no_source" | "network_error" | None }
    """
    from scraper_animeav1 import scrape_animeav1_hash, get_zilla_m3u8_url
    from config import SCRAPER_BASE_URL

    try:
        hash_id = scrape_animeav1_hash(serie_slug, episode_number)
    except Exception:
        logger.warning(
            "[stream] animeav1 scrape raised for slug=%s ep=%s",
            serie_slug,
            episode_number,
        )
        return {"url": None, "error_type": "network_error"}

    if not hash_id:
        logger.warning(
            "[stream] animeav1 no hash found for slug=%s ep=%s",
            serie_slug,
            episode_number,
        )
        return {"url": None, "error_type": "no_source"}

    raw_m3u8 = get_zilla_m3u8_url(hash_id)
    logger.warning(
        "[stream] animeav1 resolved for slug=%s ep=%s → m3u8=%s",
        serie_slug,
        episode_number,
        raw_m3u8,
    )
    return {"url": raw_m3u8, "error_type": None}


def resolve_jkanime_stream(fallback_slug: str, episode_number: int) -> dict:
    """Attempt to resolve a stream URL via the jkanime scraper.

    jkanime streams are H.264 HLS — playable directly without transcoding.

    Returns:
        { "url": str | None, "error_type": "no_source" | "network_error" | None }
    """
    from scraper_jkanime import scrape_jkanime_m3u8

    try:
        url = scrape_jkanime_m3u8(fallback_slug, episode_number)
    except Exception:
        return {"url": None, "error_type": "network_error"}

    if not url:
        return {"url": None, "error_type": "no_source"}

    return {"url": url, "error_type": None}


def orchestrate_stream(episode: dict, stream_config: dict, hint: str | None = None) -> dict:
    """Orchestrate stream URL resolution following the branch order from the spec.

    Branch order:
      1. If hint != "h264" AND stream_config.principal_slug is set: attempt AnimeAV1.
         On success: return { url, source: "animeav1" }.
         On no_source or network_error: continue to next branch.
      2. If fallback_slug is set: attempt JKAnime.
         On success: return { url, source: "jkanime" }.
      3. If any network_error was encountered: raise UpstreamError (503).
      4. Otherwise: raise NoSourceError (404).

    Args:
        episode: raw episode dict from DB (must contain episode_number, series_id).
        stream_config: raw stream-config dict from DB (fallback_slug, principal_slug).
        hint: optional client hint string. "h264" causes AnimeAV1 to be skipped
              (Safari fallback). Any other value is treated as absent.

    Returns:
        { "url": str, "source": "animeav1" | "jkanime" }

    Raises:
        NoSourceError: no URL could be resolved.
        UpstreamError: a network or parse error occurred.
    """
    fallback_slug = stream_config.get("fallback_slug")
    principal_slug = stream_config.get("principal_slug")
    episode_number = episode.get("episode_number", 0)
    series_id = episode.get("series_id")

    logger.warning(
        "[stream] orchestrate series=%s ep=%s principal_slug=%s fallback_slug=%s hint=%s",
        series_id, episode_number, principal_slug, fallback_slug, hint,
    )

    upstream_error_seen = False

    # Branch 0: NAS — local copy takes priority over all stream sites.
    # Falls through silently on miss or network error (never blocks playback).
    if NAS_BASE_URL and NAS_API_KEY and series_id:
        nas_result = resolve_nas_stream(series_id, episode_number)
        if nas_result["url"] is not None:
            logger.warning("[stream] RESOLVED source=nas url=%s", nas_result["url"])
            return {"url": nas_result["url"], "source": "nas"}

    # Branch 1: AnimeAV1 — primary HLS source
    # Skip when hint="h264" (Safari) or when principal_slug is absent.
    if hint != "h264" and principal_slug:
        av1_result = resolve_animeav1_stream(principal_slug, episode_number)
        if av1_result["url"] is not None:
            logger.warning("[stream] RESOLVED source=animeav1 url=%s", av1_result["url"])
            return {"url": av1_result["url"], "source": "animeav1"}
        if av1_result["error_type"] == "network_error":
            upstream_error_seen = True

    # Branch 2: JKAnime fallback
    if fallback_slug:
        fallback_result = resolve_jkanime_stream(fallback_slug, episode_number)
        if fallback_result["url"] is not None:
            logger.warning("[stream] RESOLVED source=jkanime url=%s", fallback_result["url"])
            return {"url": fallback_result["url"], "source": "jkanime"}
        if fallback_result["error_type"] == "network_error":
            upstream_error_seen = True

    if upstream_error_seen:
        raise UpstreamError("An upstream scraping error occurred")

    raise NoSourceError("No stream URL could be resolved for this episode")
