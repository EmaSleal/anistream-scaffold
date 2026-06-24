"""Source resolution for the admin downloads feature.

Wraps the existing stream resolvers for two purposes:
  - probe_sources: check which providers have a URL (for the source selector UI).
  - resolve_source: resolve a single chosen provider to a raw CDN URL (for trigger).

Neither function touches the NAS or caches URLs.
"""

import logging
from domain.stream import resolve_animeav1_stream, resolve_jkanime_stream

logger = logging.getLogger(__name__)


def probe_sources(stream_config: dict, episode_number: int) -> list[dict]:
    """Return available sources for the given episode.

    Tries both resolvers and returns a list of
    {"source": "animeav1"|"jkanime", "available": bool}.

    A source is skipped entirely when its slug is absent in stream_config —
    there is no point calling the resolver without a slug.
    """
    results: list[dict] = []

    principal_slug = stream_config.get("principal_slug")
    fallback_slug = stream_config.get("fallback_slug")

    if principal_slug:
        try:
            av1 = resolve_animeav1_stream(principal_slug, episode_number)
            results.append({"source": "animeav1", "available": av1["url"] is not None})
        except Exception:
            logger.warning(
                "[download_sources] probe animeav1 raised for slug=%s ep=%s",
                principal_slug,
                episode_number,
            )
            results.append({"source": "animeav1", "available": False})

    if fallback_slug:
        try:
            jk = resolve_jkanime_stream(fallback_slug, episode_number)
            results.append({"source": "jkanime", "available": jk["url"] is not None})
        except Exception:
            logger.warning(
                "[download_sources] probe jkanime raised for slug=%s ep=%s",
                fallback_slug,
                episode_number,
            )
            results.append({"source": "jkanime", "available": False})

    return results


def resolve_source(stream_config: dict, episode_number: int, source: str) -> str | None:
    """Resolve a single provider to a raw CDN URL.

    Returns the raw URL string on success, None on failure or missing slug.
    The URL is intentionally NOT forwarded to the browser — callers hand it
    directly to the NAS downloader.
    """
    if source == "animeav1":
        principal_slug = stream_config.get("principal_slug")
        if not principal_slug:
            return None
        result = resolve_animeav1_stream(principal_slug, episode_number)
        return result.get("url")

    if source == "jkanime":
        fallback_slug = stream_config.get("fallback_slug")
        if not fallback_slug:
            return None
        result = resolve_jkanime_stream(fallback_slug, episode_number)
        return result.get("url")

    logger.warning("[download_sources] unknown source=%s", source)
    return None
