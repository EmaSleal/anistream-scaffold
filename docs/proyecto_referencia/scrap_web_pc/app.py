"""
app.py — Flask application factory.

Public API:
    create_app(testing=False) -> Flask

Routes:
    GET  /                  — redirect to /compare
    GET  /compare           — rendered comparison table (Jinja2)
    POST /api/scrape        — trigger a scrape run (async by default)
    GET  /api/compare       — JSON comparison payload
    GET  /api/status        — last run summary + idle/running status
"""
from __future__ import annotations

import atexit
import logging
import threading
from typing import Any

from flask import Flask, jsonify, redirect, render_template, request, url_for

import config as cfg
from orchestrator import Orchestrator
from scheduler import build_scheduler
from storage import Storage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level busy guard — shared across all requests in one process.
# ---------------------------------------------------------------------------
_scrape_lock = threading.Lock()
_scrape_running = False


def create_app(testing: bool = False) -> Flask:
    """Application factory.

    Args:
        testing: When True the scheduler is NOT started and the DB is opened
                 as an in-memory SQLite database.  This keeps pytest fast and
                 prevents any real HTTP traffic.

    Returns:
        A configured Flask application instance.
    """
    app = Flask(__name__, template_folder="templates")
    app.config["TESTING"] = testing

    # ------------------------------------------------------------------
    # Storage + orchestrator
    # ------------------------------------------------------------------
    db_path = ":memory:" if testing else cfg.DB_PATH
    storage = Storage(db_path)
    storage.init_schema()

    orchestrator = Orchestrator(storage=storage)

    # Attach to app so route handlers can reach them without globals.
    app.storage = storage        # type: ignore[attr-defined]
    app.orchestrator = orchestrator  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Scheduler (skipped when testing=True)
    # ------------------------------------------------------------------
    if not testing:
        scheduler = build_scheduler(orchestrator)
        scheduler.start()
        atexit.register(scheduler.shutdown)
        logger.info("create_app: scheduler started (cron=%s)", cfg.SCHEDULE_CRON)

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    @app.route("/")
    def index():
        return redirect(url_for("compare"))

    @app.route("/compare")
    def compare():
        category = request.args.get("category") or None
        products = storage.get_comparison_table(category=category)
        return render_template(
            "compare.html",
            products=products,
            categories=cfg.CATEGORIES,
            selected_category=category,
        )

    @app.route("/api/scrape", methods=["POST"])
    def api_scrape():
        global _scrape_running

        with _scrape_lock:
            if _scrape_running:
                return jsonify({"status": "busy"}), 409
            _scrape_running = True

        data: dict[str, Any] = request.get_json(silent=True) or {}
        store_ids: list[str] | None = data.get("store_ids") or None
        sync: bool = bool(data.get("sync", False))

        if sync:
            try:
                summary = orchestrator.run_scrape(store_ids=store_ids)
            finally:
                with _scrape_lock:
                    _scrape_running = False
            return jsonify({"status": "completed", "summary": summary})

        # Async: fire and forget in a daemon thread.
        def _run() -> None:
            global _scrape_running
            try:
                orchestrator.run_scrape(store_ids=store_ids)
            except Exception as exc:
                logger.error("api_scrape background run failed: %s", exc)
            finally:
                with _scrape_lock:
                    _scrape_running = False

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        return jsonify({"status": "started", "run_id": None})

    @app.route("/api/compare")
    def api_compare():
        category = request.args.get("category") or None
        products = storage.get_comparison_table(category=category)
        return jsonify({"products": products, "count": len(products)})

    @app.route("/api/status")
    def api_status():
        last_run = storage.get_last_run()
        status = "running" if _scrape_running else "idle"
        return jsonify({"status": status, "last_run": last_run})

    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    create_app().run(debug=True, use_reloader=False)
