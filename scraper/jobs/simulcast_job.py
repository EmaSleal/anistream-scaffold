"""Simulcast daily discovery job.

Entrypoint for the APScheduler background job that proactively discovers and
upserts new simulcast episodes for all series that are due today (CR tz) and
within the Costa Rica daytime window (07:00–19:00).

Public API
----------
run_simulcast_daily_check()
    Called by the scheduler every 2 hours. Never raises — all per-series
    errors are caught, logged, and skipped so the rest of the batch continues.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import db.simulcast as db_simulcast
from domain.jikan_refresh import refresh_series_from_jikan
from simulcast_check import run_simulcast_update

logger = logging.getLogger(__name__)

_CR_TZ = ZoneInfo("America/Costa_Rica")


def _within_cr_window(now: datetime | None = None) -> bool:
    """Return True when the current CR local time falls within 07:00–19:00.

    Args:
        now: Optional UTC-aware datetime for injection in unit tests.
             Defaults to ``datetime.now(timezone.utc)``.

    Returns:
        True if 07:00 <= CR local hour < 19:00, False otherwise.
    """
    utc_now = now or datetime.now(timezone.utc)
    local = utc_now.astimezone(_CR_TZ)
    return 7 <= local.hour < 19


def run_simulcast_daily_check() -> None:
    """Discover and upsert new episodes for all simulcast series due today.

    Scheduled entrypoint — registered by ``scheduler.init_scheduler()``.
    The function is intentionally a no-op outside the CR daytime window and
    never propagates exceptions to the scheduler.

    Steps:
      1. Window guard: return early when outside 07:00–19:00 CR local time.
      2. Fetch candidates via ``db.simulcast.get_due_simulcast_series()``.
      3. For each candidate (inside a per-series try/except):
           a. If a MAL ID is available, call ``refresh_series_from_jikan()``
              to update ``is_simulcast``, broadcast fields, and
              ``last_simulcast_check``.
           b. Call ``run_simulcast_update()`` to scrape AnimeFlv, upsert any
              new episodes, and stamp the cooldown unconditionally.
      4. Log a summary line (processed / errors).
    """
    if not _within_cr_window():
        logger.info("simulcast_job: outside CR window (07:00–19:00), skipping run")
        return

    try:
        candidates = db_simulcast.get_due_simulcast_series()
    except Exception as exc:
        logger.warning("simulcast_job: failed to fetch candidates: %s", exc)
        return

    if not candidates:
        logger.info("simulcast_job: no candidates due for today")
        return

    logger.info("simulcast_job: %d candidate(s) to process", len(candidates))

    processed = 0
    errors = 0

    for series in candidates:
        series_id: str = series["id"]
        animeflv_slug: str = series["animeflv_slug"]
        mal_id: int | None = series.get("mal_id")
        kitsu_id: str | None = series.get("kitsu_id")
        max_ep: int = series.get("max_episode_number") or 0

        try:
            # Refresh Jikan metadata (is_simulcast, broadcast fields) and stamp
            # last_simulcast_check.  Skip when no MAL ID is stored — the series
            # can still get episode-upserts via the AnimeFlv scrape below.
            if mal_id is not None:
                refresh_series_from_jikan(series_id, mal_id, kitsu_id)

            # Scrape AnimeFlv, upsert new episodes, stamp cooldown.
            # run_simulcast_update handles its own internal try/finally cooldown
            # stamp, so even on failure the series won't be re-checked immediately.
            run_simulcast_update(series_id, animeflv_slug, max_ep)

            processed += 1
        except Exception as exc:
            logger.warning(
                "simulcast_job: series %r failed: %s",
                series_id,
                exc,
            )
            errors += 1

    logger.info(
        "simulcast_job: done — processed=%d, errors=%d",
        processed,
        errors,
    )
