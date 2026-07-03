"""Integration tests for scraper/auth_routes.py.

Tests POST /api/auth/sync-user and GET /api/auth/role/<user_id>.
The Supabase layer (db.users) is mocked so no real connection is needed.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Set required env vars BEFORE importing auth.py (which fails-fast at import).
# NOTE: "test-service-secret" matches the value tests/conftest.py's autouse
# patch_service_secret fixture forces onto auth._SERVICE_SECRET for every test
# in the suite. Using any other value here is silently overridden per-test.
TEST_SERVICE_SECRET = "test-service-secret"
os.environ.setdefault("INTERNAL_JWT_SECRET", "test-internal-secret-for-tests-only")
os.environ.setdefault("SERVICE_SECRET", TEST_SERVICE_SECRET)

import json
import pytest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    # storage.get_client must be patched before create_app()'s first call in
    # the process — blueprints are only imported once, and routes/simulcast_routes.py
    # binds its own `get_client` name via `from storage import get_client` at
    # that import time. Doing this unpatched here would permanently bind that
    # blueprint's get_client to the real client for the rest of the test
    # session, breaking storage.get_client patches in unrelated test files
    # (e.g. test_simulcast_routes.py) that run afterward.
    with patch("storage.get_client"):
        from app import create_app
        app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _key_header(key: str = TEST_SERVICE_SECRET) -> dict:
    return {"X-Service-Key": key}


# ---------------------------------------------------------------------------
# POST /api/auth/sync-user
# ---------------------------------------------------------------------------

class TestSyncUser:
    def test_valid_key_and_body_returns_200(self, client):
        with patch("db.users.upsert_user") as mock_upsert:
            res = client.post(
                "/api/auth/sync-user",
                headers=_key_header(),
                json={"id": "g_123", "email": "a@b.com", "name": "Alice", "photo_url": None},
            )
        assert res.status_code == 200
        assert json.loads(res.data) == {"ok": True}
        mock_upsert.assert_called_once_with("g_123", "a@b.com", "Alice", None)

    def test_missing_id_returns_400(self, client):
        with patch("db.users.upsert_user"):
            res = client.post(
                "/api/auth/sync-user",
                headers=_key_header(),
                json={"email": "a@b.com"},
            )
        assert res.status_code == 400
        data = json.loads(res.data)
        assert "id" in data.get("error", "").lower()

    def test_wrong_key_returns_401(self, client):
        res = client.post(
            "/api/auth/sync-user",
            headers=_key_header("wrong-secret"),
            json={"id": "g_123"},
        )
        assert res.status_code == 401

    def test_missing_key_returns_401(self, client):
        res = client.post(
            "/api/auth/sync-user",
            json={"id": "g_123"},
        )
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/auth/role/<user_id>
# ---------------------------------------------------------------------------

class TestGetRole:
    def test_existing_user_returns_stored_role(self, client):
        with patch("db.users.get_user_role", return_value="ADMIN"):
            res = client.get("/api/auth/role/g_123", headers=_key_header())
        assert res.status_code == 200
        assert json.loads(res.data) == {"role": "ADMIN"}

    def test_unknown_user_returns_default_user_role(self, client):
        with patch("db.users.get_user_role", return_value=None):
            res = client.get("/api/auth/role/unknown", headers=_key_header())
        assert res.status_code == 200
        assert json.loads(res.data) == {"role": "USER"}

    def test_wrong_key_returns_401(self, client):
        res = client.get("/api/auth/role/g_123", headers=_key_header("bad"))
        assert res.status_code == 401

    def test_missing_key_returns_401(self, client):
        res = client.get("/api/auth/role/g_123")
        assert res.status_code == 401
