"""Scheduler entrypoint for the simulcast background job.

Runs in its own dedicated process (see ``scheduler_worker.py``), decoupled
from the gunicorn/Flask process. This avoids the multi-worker duplication
bug where each gunicorn worker forked its own APScheduler instance.

Provides ``run_scheduler_forever()``, which blocks for the lifetime of the
process. The only guard that still applies here (the Flask-specific TESTING
and Werkzeug-reloader guards are gone, since this process has neither):

  1. ``SIMULCAST_JOB_ENABLED`` env var is not ``'1'`` — opt-in, off by default.
     When disabled, the process blocks forever without busy-looping so the
     container stays up cleanly under ``restart: unless-stopped``.
"""
from __future__ import annotations

import logging
import os
import signal
import threading

logger = logging.getLogger(__name__)


def run_scheduler_forever() -> None:
    """Start the simulcast discovery scheduler and block until shutdown.

    When ``SIMULCAST_JOB_ENABLED`` is not "1", logs and blocks forever
    without starting a scheduler, so the container stays up idle.
    """
    if os.getenv("SIMULCAST_JOB_ENABLED", "0") != "1":
        logger.info("simulcast_job: scheduler disabled (SIMULCAST_JOB_ENABLED != '1'); idling")
        threading.Event().wait()
        return

    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.interval import IntervalTrigger
    from jobs.simulcast_job import run_simulcast_daily_check

    scheduler = BlockingScheduler()
    scheduler.add_job(
        run_simulcast_daily_check,
        trigger=IntervalTrigger(hours=2),
        id="simulcast_discovery",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    def _handle_shutdown(signum, frame):
        logger.info("simulcast_job: received signal %s, shutting down scheduler", signum)
        scheduler.shutdown(wait=False)

    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    logger.info("simulcast_job: scheduler starting (interval=2h, id=simulcast_discovery)")
    scheduler.start()  # blocks until shutdown() is called
