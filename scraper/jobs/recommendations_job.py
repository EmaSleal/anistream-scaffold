"""Recommendations pre-warm background job.

Entrypoint for the APScheduler background job that proactively warms
``recommended_mal_ids`` for all series that have never had their
recommendations fetched from Jikan (i.e. ``recommended_mal_ids IS NULL``).

Public API
----------
run_recommendations_warmup()
    Called by the scheduler every 6 hours. Never raises — all per-chunk
    errors are caught, logged, and skipped so the rest of the batch continues.
"""
from __future__ import annotations

import logging

import db.series as db_series
import storage

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 50


def run_recommendations_warmup() -> None:
    """Warm ``recommended_mal_ids`` for all cold series in the catalog.

    A "cold" series has ``mal_id IS NOT NULL AND recommended_mal_ids IS NULL``.
    The function processes them in chunks of 50 via the existing
    ``db_series.warm_recommendations()`` helper which handles Jikan rate-limits
    and is itself fail-open.

    Steps:
      1. Query the series table for cold series (single DB call).
      2. If the result is empty, log and return immediately (no-op).
      3. Process mal_ids in chunks of 50, catching per-chunk exceptions.
      4. Emit a summary log line with processed/error counts.
    """
    try:
        result = (
            storage.get_client()
            .table("series")
            .select("mal_id")
            .not_.is_("mal_id", "null")
            .is_("recommended_mal_ids", "null")
            .limit(10)
            .execute()
        )
    except Exception as exc:
        logger.warning("recommendations_job: failed to fetch cold series: %s", exc)
        return

    mal_ids = [row["mal_id"] for row in result.data or []]

    if not mal_ids:
        logger.info("recommendations_job: no cold series found")
        return

    logger.info("recommendations_job: %d cold series to warm", len(mal_ids))

    processed = 0
    errors = 0

    chunks = [mal_ids[i : i + _CHUNK_SIZE] for i in range(0, len(mal_ids), _CHUNK_SIZE)]
    for chunk in chunks:
        try:
            db_series.warm_recommendations(chunk)
            processed += len(chunk)
        except Exception as exc:
            logger.warning("recommendations_job: chunk failed: %s", exc)
            errors += 1

    logger.info(
        "recommendations_job: done — processed=%d, errors=%d",
        processed,
        errors,
    )
