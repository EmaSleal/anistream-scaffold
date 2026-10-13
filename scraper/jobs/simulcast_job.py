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
import os
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
           b. Call ``run_simulcast_update()`` to scrape AnimeAV1, upsert any
              new episodes, and stamp the cooldown unconditionally. ``mode``
              and ``franchise_id``/``expected`` are read straight off the
              candidate row (present only when ``SIMULCAST_GRACE_ENABLED=1``);
              ``backfill_mode`` comes from ``SIMULCAST_BACKFILL_MODE``.
      4. Log a summary line (processed / errors).
      5. When ``SIMULCAST_GRACE_ENABLED=1``, run the expired-gap surfacing
         pass once: ``get_expired_gap_candidates()`` → ``mark_gap_unresolved()``
         + a WARNING log per unresolved series. Gated behind the same flag
         as step 3 so this stays fully inert — including against querying
         the ``gap_unresolved_at``/``gap_missing_episodes`` columns, which
         may not exist yet in production before migration 004 is applied —
         until the flag is explicitly turned on.

    Both ``SIMULCAST_GRACE_ENABLED`` and ``SIMULCAST_BACKFILL_MODE`` default
    OFF, so with no env vars set this function's behavior (and the exact
    ``run_simulcast_update`` call shape) is unchanged from before this change.
    """
    if not _within_cr_window():
        logger.info("simulcast_job: outside CR window (07:00–19:00), skipping run")
        return

    grace_enabled = os.getenv("SIMULCAST_GRACE_ENABLED", "0") == "1"
    backfill_mode = os.getenv("SIMULCAST_BACKFILL_MODE", "off")

    try:
        candidates = db_simulcast.get_due_simulcast_series()
    except Exception as exc:
        logger.warning("simulcast_job: failed to fetch candidates: %s", exc)
        return

    if not candidates:
        logger.info("simulcast_job: no candidates due for today")
    else:
        logger.info("simulcast_job: %d candidate(s) to process", len(candidates))

        processed = 0
        errors = 0
        episodes_added = 0

        for series in candidates:
            series_id: str = series["id"]
            principal_slug: str = series["principal_slug"]
            mal_id: int | None = series.get("mal_id")
            kitsu_id: str | None = series.get("kitsu_id")
            max_ep: int = series.get("max_episode_number") or 0
            mode: str = series.get("mode", "airing")
            franchise_id: str | None = series.get("franchise_id")
            expected: int | None = series.get("expected")

            try:
                # Refresh Jikan metadata (is_simulcast, broadcast fields) and stamp
                # last_simulcast_check.  Skip when no MAL ID is stored — the series
                # can still get episode-upserts via the AnimeAV1 scrape below.
                if mal_id is not None:
                    refresh_series_from_jikan(series_id, mal_id, kitsu_id)

                # Scrape AnimeAV1, upsert new episodes, stamp cooldown.
                # run_simulcast_update handles its own internal try/finally cooldown
                # stamp, so even on failure the series won't be re-checked immediately.
                episodes_added += run_simulcast_update(
                    series_id,
                    principal_slug,
                    max_ep,
                    mode=mode,
                    backfill_mode=backfill_mode,
                    franchise_id=franchise_id,
                    expected=expected,
                )

                processed += 1
            except Exception as exc:
                logger.warning(
                    "simulcast_job: series %r failed: %s",
                    series_id,
                    exc,
                )
                errors += 1

        logger.info(
            "simulcast_job: done — processed=%d, episodes_added=%d, errors=%d",
            processed,
            episodes_added,
            errors,
        )

    if grace_enabled:
        _run_expired_gap_surfacing_pass()


def _run_expired_gap_surfacing_pass() -> None:
    """Surface unresolved episode gaps to the admin, once per cron run.

    Never raises — a failure here must not affect the main recheck loop
    above (which has already completed by the time this runs).
    """
    try:
        expired = db_simulcast.get_expired_gap_candidates()
    except Exception as exc:
        logger.warning("simulcast_job: failed to fetch expired gap candidates: %s", exc)
        return

    for candidate in expired:
        series_id = candidate["id"]
        expected = candidate["expected"]
        own_nums = candidate.get("own_episode_numbers") or set()
        missing = sorted(set(range(1, expected + 1)) - own_nums)
        try:
            db_simulcast.mark_gap_unresolved(series_id, missing)
            logger.warning(
                "simulcast_job: unresolved episode gap for series=%r missing=%s",
                series_id,
                missing,
            )
        except Exception as exc:
            logger.warning(
                "simulcast_job: failed to mark gap unresolved for series=%r: %s",
                series_id,
                exc,
            )
