"""Background task: discover and seed a new simulcast episode.

This module is the sole implementation of the simulcast episode-check thread body.
It is intentionally separate from the route layer so it can be unit-tested in
isolation without a running Flask app.

Public API
----------
run_simulcast_check(user_id, series_id, animeflv_slug, current_max_ep)
    Call from a daemon thread spawned inside the continue_watching route.
    Never call thread.join() on it — the route must return immediately.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import storage
import db.progress as db_progress
import db.simulcast as db_simulcast
from fetcher import fetch_jikan_episodes
from scraper_animeav1 import scrape_animeav1_episodes

logger = logging.getLogger(__name__)


def _today_iso() -> str:
    """Return today's UTC date as a YYYY-MM-DD string."""
    return datetime.now(timezone.utc).date().isoformat()


def _get_series_mal_id(series_id: str) -> int | None:
    """Return the MAL ID for a series, or None if unavailable or on any error."""
    try:
        client = storage.get_client()
        result = (
            client.table("series")
            .select("mal_id")
            .eq("id", series_id)
            .maybe_single()
            .execute()
        )
        if result and result.data:
            return result.data.get("mal_id")
        return None
    except Exception:
        return None


def _get_last_episode_aired_at(series_id: str, episode_number: int) -> str | None:
    """Return the aired_at of a specific episode from DB, or None on any error."""
    try:
        client = storage.get_client()
        result = (
            client.table("episodes")
            .select("aired_at")
            .eq("series_id", series_id)
            .eq("episode_number", episode_number)
            .maybe_single()
            .execute()
        )
        if result and result.data:
            return result.data.get("aired_at")
        return None
    except Exception:
        return None


def _estimate_from_cadence(last_aired_at: str, ep_gap: int) -> str | None:
    """Estimate aired_at by adding 7 days per episode gap from a known date."""
    try:
        base = datetime.fromisoformat(last_aired_at[:10]).date()
        return (base + timedelta(days=7 * ep_gap)).isoformat()
    except Exception:
        return None


def _resolve_aired_at(
    mal_id: int | None,
    ep_num: int,
    series_id: str,
    current_max_ep: int,
) -> str:
    """Resolve aired_at for a simulcast episode.

    Resolution order:
    1. Jikan episode data (if mal_id is non-null): normalize to YYYY-MM-DD.
    2. Estimate from the last known episode's aired_at + 7 days per episode gap.
    3. Today's UTC date as last-resort fallback.

    Never raises — all paths return a date string.
    """
    # 1. Try Jikan
    if mal_id is not None:
        try:
            episodes = fetch_jikan_episodes(mal_id)
            raw = episodes.get(ep_num, {}).get("aired_at")
            if raw:
                return raw[:10]
        except Exception:
            pass

    # 2. Estimate from weekly cadence
    last_aired_at = _get_last_episode_aired_at(series_id, current_max_ep)
    if last_aired_at:
        estimated = _estimate_from_cadence(last_aired_at, ep_num - current_max_ep)
        if estimated:
            return estimated

    # 3. Last resort
    return _today_iso()


def run_simulcast_check(
    user_id: str,
    series_id: str,
    animeflv_slug: str,
    current_max_ep: int,
) -> None:
    """Scrape AnimeFlv for the series, upsert any new episode, and seed progress.

    This function is designed to run in a daemon thread spawned from the
    continue_watching route. It MUST NOT access Flask ``g`` — ``user_id``
    is passed explicitly as an argument.

    Steps (executed unconditionally — cooldown stamp always happens):
      1. Scrape episode list from AnimeFlv.
      2. Compare the maximum scraped episode number against ``current_max_ep``.
      3. If new episodes exist:
           a. Upsert each new episode row via ``storage.upsert_episode``.
           b. Seed a ``watch_progress`` row for ``user_id`` at ``progress_sec=1``
              so the new episode appears in Continue Watching.
      4. Stamp ``series.last_simulcast_check = now()`` unconditionally.

    On any exception the function logs a warning, attempts to stamp the cooldown
    (to avoid hammering a broken series), and exits silently — it never propagates
    the exception to the caller.

    Args:
        user_id:         Authenticated user's ID captured in request scope.
        series_id:       Series primary key (slug-based).
        animeflv_slug:   AnimeFlv URL slug for the series page.
        current_max_ep:  Highest episode_number currently in the DB for this series.
    """
    mal_id = _get_series_mal_id(series_id)

    try:
        scraped_episodes = scrape_animeav1_episodes(animeflv_slug)
    except Exception as exc:
        logger.warning(
            "simulcast_check: scrape_episode_list failed for series=%r slug=%r: %s",
            series_id, animeflv_slug, exc,
        )
        _stamp_cooldown(series_id)
        return

    try:
        _process_scraped_episodes(
            scraped_episodes=scraped_episodes,
            series_id=series_id,
            animeflv_slug=animeflv_slug,
            user_id=user_id,
            current_max_ep=current_max_ep,
            mal_id=mal_id,
        )
    except Exception as exc:
        logger.warning(
            "simulcast_check: error processing scraped episodes for series=%r: %s",
            series_id, exc,
        )
    finally:
        _stamp_cooldown(series_id)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def run_simulcast_update(
    series_id: str,
    animeflv_slug: str,
    current_max_ep: int,
) -> None:
    """Like run_simulcast_check but without seeding watch_progress.

    Use this when the trigger is a series page visit (user has no watch_progress).
    Discovers and upserts new episodes, stamps the cooldown — does NOT seed progress.
    """
    mal_id = _get_series_mal_id(series_id)

    try:
        scraped_episodes = scrape_animeav1_episodes(animeflv_slug)
    except Exception as exc:
        logger.warning(
            "simulcast_check: scrape_episode_list failed for series=%r slug=%r: %s",
            series_id, animeflv_slug, exc,
        )
        _stamp_cooldown(series_id)
        return

    try:
        _process_scraped_episodes(
            scraped_episodes=scraped_episodes,
            series_id=series_id,
            animeflv_slug=animeflv_slug,
            user_id=None,
            current_max_ep=current_max_ep,
            mal_id=mal_id,
        )
    except Exception as exc:
        logger.warning(
            "simulcast_check: error processing scraped episodes for series=%r: %s",
            series_id, exc,
        )
    finally:
        _stamp_cooldown(series_id)


def _process_scraped_episodes(
    *,
    scraped_episodes: list[dict],
    series_id: str,
    animeflv_slug: str,
    user_id: str | None,
    current_max_ep: int,
    mal_id: int | None,
) -> None:
    """Upsert new episodes and optionally seed watch_progress for the user.

    Only episodes with episode_number > current_max_ep are considered new.
    Episode IDs follow the ``{series_id}-ep-{num}`` convention (no zero-padding),
    matching the format used in ``_build_episodes`` (routes.py).
    """
    new_episodes = [
        ep for ep in scraped_episodes
        if ep.get("episode_number") is not None
        and ep["episode_number"] > current_max_ep
    ]

    if not new_episodes:
        logger.debug(
            "simulcast_check: no new episodes for series=%r (db_max=%d, scraped_max=%s)",
            series_id,
            current_max_ep,
            max((ep["episode_number"] for ep in scraped_episodes), default="N/A"),
        )
        return

    for ep in new_episodes:
        ep_num = ep["episode_number"]
        ep_id = f"{series_id}-ep-{ep_num}"

        storage.upsert_episode({
            "id": ep_id,
            "series_id": series_id,
            "episode_number": ep_num,
            "title": ep.get("title"),
            "thumbnail_url": ep.get("thumbnail_url"),
            "animeflv_slug": f"{animeflv_slug}-{ep_num}",
            "aired_at": _resolve_aired_at(mal_id, ep_num, series_id, current_max_ep),
        })

        if user_id is not None:
            # Seed at progress_sec=1 so the new episode appears in Continue Watching.
            db_progress.upsert_progress(
                user_id=user_id,
                episode_id=ep_id,
                series_id=series_id,
                progress_sec=1,
                duration_sec=0,
            )

        logger.info(
            "simulcast_check: upserted new episode %r for series=%r, seeded progress for user=%r",
            ep_id, series_id, user_id,
        )


def _stamp_cooldown(series_id: str) -> None:
    """Unconditionally stamp last_simulcast_check = now() for the series.

    Silently swallows any DB error so the calling try/except is not interrupted.
    """
    try:
        db_simulcast.update_simulcast_fields(series_id, {})
    except Exception as exc:
        logger.warning(
            "simulcast_check: failed to stamp cooldown for series=%r: %s",
            series_id, exc,
        )
