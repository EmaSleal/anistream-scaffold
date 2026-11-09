"""Scheduler entrypoint for the background jobs.

Runs in its own dedicated process (see ``scheduler_worker.py``), decoupled
from the gunicorn/Flask process. This avoids the multi-worker duplication
bug where each gunicorn worker forked its own APScheduler instance (it also
keeps the download dispatcher (ADR-019/ADR-022) out of the web workers).

Provides ``run_scheduler_forever()``, which blocks for the lifetime of the
process. Each job is opt-in through its own env flag (off by default):

  * ``SIMULCAST_JOB_ENABLED=1``  — simulcast discovery (2h) + recommendations
    warmup (6h).
  * ``DOWNLOAD_QUEUE_ENABLED=1`` — download queue dispatcher every 30 s
    (ADR-019), independent of the simulcast flag.

When no flag is enabled the process blocks forever without busy-looping so the
container stays up cleanly under ``restart: unless-stopped``.
"""
from __future__ import annotations

import logging
import os
import signal
import threading

logger = logging.getLogger(__name__)


def _run_download_queue_tick() -> None:
    """Dispatcher job body: a failing tick is logged and never propagates."""
    try:
        from domain.download_queue import dispatch_tick

        dispatch_tick()
    except Exception:
        logger.exception("download_queue: dispatch tick failed")


def run_scheduler_forever() -> None:
    """Start the enabled background jobs and block until shutdown.

    Each job has its own flag. When none is enabled, logs and blocks forever
    without starting a scheduler, so the container stays up idle.
    """
    simulcast_enabled = os.getenv("SIMULCAST_JOB_ENABLED", "0") == "1"
    queue_enabled = os.getenv("DOWNLOAD_QUEUE_ENABLED", "0") == "1"

    if not (simulcast_enabled or queue_enabled):
        logger.info(
            "scheduler: no job enabled (SIMULCAST_JOB_ENABLED / DOWNLOAD_QUEUE_ENABLED != '1'); idling"
        )
        threading.Event().wait()
        return

    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.interval import IntervalTrigger

    scheduler = BlockingScheduler()
    if simulcast_enabled:
        from jobs.simulcast_job import run_simulcast_daily_check
        from jobs.recommendations_job import run_recommendations_warmup

        scheduler.add_job(
            run_simulcast_daily_check,
            trigger=IntervalTrigger(hours=2),
            id="simulcast_discovery",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        scheduler.add_job(
            run_recommendations_warmup,
            trigger=IntervalTrigger(hours=6),
            id="recommendations_warmup",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        logger.info("simulcast_job: scheduled (interval=2h, id=simulcast_discovery)")
    if queue_enabled:
        scheduler.add_job(
            _run_download_queue_tick,
            trigger=IntervalTrigger(seconds=30),
            id="download_queue_dispatch",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        logger.info("download_queue: scheduled (interval=30s, id=download_queue_dispatch)")

    def _handle_shutdown(signum, frame):
        logger.info("scheduler: received signal %s, shutting down", signum)
        scheduler.shutdown(wait=False)

    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    logger.info("scheduler: starting")
    scheduler.start()  # blocks until shutdown() is called
