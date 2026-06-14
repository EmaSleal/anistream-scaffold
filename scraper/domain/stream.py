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

logger = logging.getLogger(__name__)


class NoSourceError(Exception):
    """Raised when no stream URL can be resolved (no_source)."""


class UpstreamError(Exception):
    """Raised when an upstream scraping call fails (network/parse error)."""


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


def orchestrate_stream(episode: dict, stream_config: dict) -> dict:
    """Orchestrate stream URL resolution following the branch order from the spec.

    Branch order:
      1. If animeflv_disabled is False: attempt primary (animeflv).
      2. If primary succeeds: return { url, source: "animeflv" }.
      3. If primary fails (no_source OR network_error) OR animeflv_disabled is True:
         attempt fallback (jkanime) when fallback_slug is set.
      4. If fallback succeeds: return { url, source: "jkanime" }.
      5. If network_error occurred (primary or fallback): raise UpstreamError.
      6. If neither resolves: raise NoSourceError.

    Args:
        episode: raw episode dict from DB (must contain animeflv_slug,
                 episode_number, series_id).
        stream_config: raw stream-config dict from DB (animeflv_disabled,
                       fallback_slug).

    Returns:
        { "url": str, "source": "animeflv" | "jkanime" }

    Raises:
        NoSourceError: no URL could be resolved.
        UpstreamError: a network or parse error occurred.
    """
    animeflv_disabled = bool(stream_config.get("animeflv_disabled") or False)
    fallback_slug = stream_config.get("fallback_slug")
    episode_slug = episode.get("animeflv_slug")
    episode_number = episode.get("episode_number", 0)

    logger.warning(
        "[stream] orchestrate episode_slug=%s animeflv_disabled=%s fallback_slug=%s",
        episode_slug, animeflv_disabled, fallback_slug,
    )

    upstream_error_seen = False

    if not animeflv_disabled:
        primary_result = resolve_animeflv_stream(episode_slug)
        if primary_result["url"] is not None:
            return {"url": primary_result["url"], "source": "animeflv"}
        if primary_result["error_type"] == "network_error":
            upstream_error_seen = True

    if fallback_slug:
        fallback_result = resolve_jkanime_stream(fallback_slug, episode_number)
        if fallback_result["url"] is not None:
            return {"url": fallback_result["url"], "source": "jkanime"}
        if fallback_result["error_type"] == "network_error":
            upstream_error_seen = True

    if upstream_error_seen:
        raise UpstreamError("An upstream scraping error occurred")

    raise NoSourceError("No stream URL could be resolved for this episode")
