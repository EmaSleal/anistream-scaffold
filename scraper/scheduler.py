"""Scheduler bootstrap for the simulcast background job.

Provides ``init_scheduler(app)`` which registers and starts an APScheduler
``BackgroundScheduler`` inside the Flask process.  The function returns None
(no-op) under any of three guards:

  1. ``app.config['TESTING']`` is True — never schedule under pytest.
  2. ``SIMULCAST_JOB_ENABLED`` env var is not ``'1'`` — opt-in, off by default.
  3. Flask debug reloader is active — avoids duplicate scheduling in the parent
     process that the Werkzeug reloader spawns before the real child.

Usage in ``create_app()``::

    from scheduler import init_scheduler
    scheduler = init_scheduler(app)
    if scheduler is not None:
        app.extensions["scheduler"] = scheduler
"""
from __future__ import annotations

import atexit
import logging
import os

from flask import Flask

logger = logging.getLogger(__name__)


def init_scheduler(app: Flask):
    """Register and start the simulcast discovery scheduler.

    Args:
        app: The Flask application instance.

    Returns:
        The started ``BackgroundScheduler`` instance, or ``None`` when
        scheduling is disabled or guarded out.
    """
    # Guard 1: never schedule under pytest or any test harness.
    if app.config.get("TESTING"):
        return None

    # Guard 2: opt-in flag keeps the scheduler off in dev/CI by default.
    if os.getenv("SIMULCAST_JOB_ENABLED", "0") != "1":
        return None

    # Guard 3: Werkzeug debug reloader spawns a parent process before the
    # real child (WERKZEUG_RUN_MAIN=true).  Only start the scheduler in the
    # child to avoid registering the job twice.
    if app.debug and os.getenv("WERKZEUG_RUN_MAIN") != "true":
        return None

    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.interval import IntervalTrigger
    from jobs.simulcast_job import run_simulcast_daily_check

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        run_simulcast_daily_check,
        trigger=IntervalTrigger(hours=2),
        id="simulcast_discovery",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown(wait=False))

    logger.info("simulcast_job: scheduler started (interval=2h, id=simulcast_discovery)")
    return scheduler
