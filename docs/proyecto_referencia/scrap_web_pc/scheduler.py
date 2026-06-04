"""
scheduler.py — APScheduler bootstrap for the nightly scrape job.

Public API:
    build_scheduler(orchestrator) -> BackgroundScheduler
    TESTING: bool — set to True in tests to suppress scheduler auto-start

Usage:
    scheduler = build_scheduler(orchestrator)
    scheduler.start()   # caller is responsible for start/shutdown

The scheduler is NOT started here; the caller (Flask app or test) decides
when to start and stop it.  This keeps the module testable without side effects.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from config import SCHEDULE_CRON
from orchestrator import Orchestrator

logger = logging.getLogger(__name__)

# Set to True in tests to prevent scheduler from starting.
TESTING: bool = False


def build_scheduler(orchestrator: Orchestrator) -> BackgroundScheduler:
    """Create and configure a BackgroundScheduler for the nightly scrape.

    The job uses CronTrigger driven by SCHEDULE_CRON from config
    (default: "0 3 * * *" — 03:00 local time nightly).

    Coalesce=True + max_instances=1 ensures that if a run overruns its
    scheduled time the next trigger does NOT pile up additional instances.

    Args:
        orchestrator: A fully configured Orchestrator instance.  The job
                      calls orchestrator.run_scrape() with no arguments,
                      which scrapes all enabled stores.

    Returns:
        A configured (but not yet started) BackgroundScheduler.
    """
    scheduler = BackgroundScheduler()

    # Parse the five-field cron expression from config.
    # CronTrigger.from_crontab handles standard "min hour dom month dow" syntax.
    trigger = CronTrigger.from_crontab(SCHEDULE_CRON)

    scheduler.add_job(
        func=orchestrator.run_scrape,
        trigger=trigger,
        id="nightly_scrape",
        name="Nightly scrape — all enabled stores",
        coalesce=True,
        max_instances=1,
        replace_existing=True,
    )

    logger.info(
        "scheduler: job 'nightly_scrape' registered with cron='%s'",
        SCHEDULE_CRON,
    )
    return scheduler
