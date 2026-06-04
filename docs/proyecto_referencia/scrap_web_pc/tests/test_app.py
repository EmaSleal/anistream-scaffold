"""
tests/test_app.py — Unit tests for Flask app routes (TASK-28).

All tests use create_app(testing=True):
  - DB is in-memory SQLite
  - Scheduler is NOT started
  - No real HTTP calls are made

Covered:
  1. GET /compare returns 200 with empty table when DB has no products
  2. GET /compare?category=GPUs returns 200 and page contains "GPUs"
  3. POST /api/scrape with sync=false returns 200 with {"status": "started"}
  4. POST /api/scrape while busy returns 409 with {"status": "busy"}
  5. GET /api/status returns 200 with "status" key
  6. GET /api/compare returns 200 with "products" and "count" keys
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from app import create_app, _scrape_lock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    """Flask app configured for testing (in-memory DB, no scheduler)."""
    application = create_app(testing=True)
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


# ---------------------------------------------------------------------------
# Helper: reset the busy flag between tests that touch it
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_busy_flag():
    """Ensure _scrape_running is False before and after each test."""
    import app as app_module
    app_module._scrape_running = False
    yield
    app_module._scrape_running = False


# ---------------------------------------------------------------------------
# Test 1: GET /compare — empty DB returns 200
# ---------------------------------------------------------------------------

def test_compare_empty_db_returns_200(client) -> None:
    """GET /compare must return 200 even when there are no products in the DB."""
    response = client.get("/compare")
    assert response.status_code == 200
    # The empty-state placeholder text should be present
    body = response.data.decode("utf-8")
    assert "Comparador" in body


# ---------------------------------------------------------------------------
# Test 2: GET /compare?category=GPUs — page contains "GPUs"
# ---------------------------------------------------------------------------

def test_compare_category_filter_renders_category_name(client) -> None:
    """GET /compare?category=GPUs must return 200 and contain the word GPUs."""
    response = client.get("/compare?category=GPUs")
    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert "GPUs" in body


# ---------------------------------------------------------------------------
# Test 3: POST /api/scrape async — returns {"status": "started"}
# ---------------------------------------------------------------------------

def test_api_scrape_async_returns_started(client) -> None:
    """POST /api/scrape with sync=false (default) must immediately return
    {"status": "started"} without running the actual scrape."""
    # Patch orchestrator.run_scrape so no real work happens in the thread.
    with patch.object(
        client.application.orchestrator, "run_scrape", return_value={}
    ):
        response = client.post(
            "/api/scrape",
            data=json.dumps({"sync": False}),
            content_type="application/json",
        )

    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "started"


# ---------------------------------------------------------------------------
# Test 4: POST /api/scrape while busy — returns 409
# ---------------------------------------------------------------------------

def test_api_scrape_busy_returns_409(client) -> None:
    """If a scrape is already running (busy flag set) the endpoint must return
    HTTP 409 with {"status": "busy"}."""
    import app as app_module
    app_module._scrape_running = True

    response = client.post(
        "/api/scrape",
        data=json.dumps({}),
        content_type="application/json",
    )

    assert response.status_code == 409
    body = response.get_json()
    assert body["status"] == "busy"


# ---------------------------------------------------------------------------
# Test 5: GET /api/status — returns 200 with "status" key
# ---------------------------------------------------------------------------

def test_api_status_returns_status_key(client) -> None:
    """GET /api/status must return HTTP 200 with a JSON body that has a
    "status" key whose value is "idle" or "running"."""
    response = client.get("/api/status")
    assert response.status_code == 200
    body = response.get_json()
    assert "status" in body
    assert body["status"] in ("idle", "running")


# ---------------------------------------------------------------------------
# Test 6: GET /api/compare — returns 200 with "products" and "count" keys
# ---------------------------------------------------------------------------

def test_api_compare_returns_products_and_count(client) -> None:
    """GET /api/compare must return HTTP 200 with a JSON body containing
    "products" (list) and "count" (int)."""
    response = client.get("/api/compare")
    assert response.status_code == 200
    body = response.get_json()
    assert "products" in body
    assert "count" in body
    assert isinstance(body["products"], list)
    assert isinstance(body["count"], int)
    assert body["count"] == len(body["products"])
