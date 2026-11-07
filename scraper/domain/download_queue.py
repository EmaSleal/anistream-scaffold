"""Serial download queue (ADR-019) — no Flask import.

``enqueue_series`` records the missing episodes of a series; ``dispatch_tick``
is called periodically by the scheduler worker (never by the web process) and
keeps at most one item downloading on the NAS at a time. The CDN URL is
resolved only when an item is dispatched, because those URLs are short-lived.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from db import download_queue as db_queue
from db import episodes as db_episodes
from db import series as db_series
from domain.download_sources import resolve_source
from domain.nas_jobs import NasUnavailable, create_download_job, get_job_status, list_downloaded_episodes
from domain.series import is_released

logger = logging.getLogger(__name__)

DEFAULT_SOURCE = "jkanime"
DEFAULT_TIMEOUT_MINUTES = 120
# Max queued items examined per tick. Items that fail without ever reaching the
# NAS (no_source) are skipped within the same tick; this bounds that loop so a
# long run of unresolvable items cannot monopolise a tick.
MAX_ITEMS_PER_TICK = 25


def _timeout_minutes() -> float:
    try:
        return float(os.getenv("DOWNLOAD_QUEUE_TIMEOUT_MINUTES", DEFAULT_TIMEOUT_MINUTES))
    except ValueError:
        return DEFAULT_TIMEOUT_MINUTES


def missing_episodes(series_id: str) -> list[int]:
    """Released episodes of the series that are not on the NAS yet."""
    rows = db_episodes.get_episodes_by_series(series_id)
    released = {
        r["episode_number"]
        for r in rows
        if is_released(r.get("aired_at"), r.get("thumbnail_url"))
    }
    return sorted(released - set(list_downloaded_episodes(series_id)))


def enqueue_series(series_id: str) -> dict:
    """Queue every missing episode; returns {"queued": n, "alreadyQueued": m}."""
    missing = missing_episodes(series_id)
    if not missing:
        return {"queued": 0, "alreadyQueued": 0}
    queued, already = db_queue.enqueue(series_id, missing, DEFAULT_SOURCE)
    return {"queued": queued, "alreadyQueued": already}


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def _poll_active(item: dict) -> bool:
    """Advance the downloading item. Returns True when the slot is now free."""
    status = get_job_status(item.get("nas_job_id") or "")
    phase = status.get("status")
    if phase == "done":
        db_queue.mark_done(item["id"])
        return True
    if phase == "failed":
        db_queue.mark_failed(item["id"], status.get("error") or "nas_failed")
        return True
    # pending / downloading / unknown: keep waiting, unless it has taken too long.
    started = _parse_ts(item.get("started_at"))
    if started is not None:
        elapsed = (datetime.now(timezone.utc) - started).total_seconds() / 60
        if elapsed > _timeout_minutes():
            db_queue.mark_failed(item["id"], "timeout")
            return True
    return False


def _load_title_year(series_id: str) -> tuple[str | None, int | None]:
    try:
        meta = db_series.get_series_title_year_by_id(series_id) or {}
        return meta.get("title") or None, meta.get("year") or None
    except Exception:
        logger.warning("[download_queue] could not load title/year for series=%s", series_id)
        return None, None


def _dispatch_next() -> None:
    for _ in range(MAX_ITEMS_PER_TICK):
        item = db_queue.next_queued()
        if not item:
            return
        series_id, ep = item["series_id"], item["episode_number"]
        source = item.get("source") or DEFAULT_SOURCE

        stream_config = db_series.get_stream_config(series_id)
        url = resolve_source(stream_config, ep, source) if stream_config else None
        if not url:
            db_queue.mark_failed(item["id"], "no_source")
            continue

        title, year = _load_title_year(series_id)
        try:
            job = create_download_job(
                series_id, ep, url, source, series_title=title, series_year=year
            )
        except NasUnavailable:
            logger.warning("[download_queue] NAS unavailable, will retry series=%s ep=%s", series_id, ep)
            return

        if job.get("status") == "done":
            # NAS already has the file (idempotent job): nothing to wait for.
            db_queue.mark_downloading(item["id"], job.get("jobId", ""))
            db_queue.mark_done(item["id"])
            continue
        db_queue.mark_downloading(item["id"], job.get("jobId", ""))
        return


def dispatch_tick() -> None:
    """One iteration of the serial loop; at most one item is ever downloading."""
    active = db_queue.get_active()
    if active and not _poll_active(active):
        return
    _dispatch_next()
