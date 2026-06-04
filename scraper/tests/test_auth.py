"""Tests for scraper/auth.py — @require_auth and @require_admin decorators.

These tests use a test-only INTERNAL_JWT_SECRET and mint tokens with PyJWT
to simulate the internal HS256 tokens that Next.js would produce.
"""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Set secrets BEFORE importing auth.py (which fails-fast at import if unset).
TEST_SECRET = "test-internal-secret-for-tests-only"
os.environ["INTERNAL_JWT_SECRET"] = TEST_SECRET
os.environ.setdefault("SERVICE_SECRET", "test-service-secret-for-tests-only")

import json
import pytest
import jwt as pyjwt
from flask import Flask, g, jsonify
from unittest.mock import patch

# Patch the secret value that auth.py loaded at import time.
import auth as auth_module
auth_module._INTERNAL_JWT_SECRET = TEST_SECRET


def _make_token(sub: str = "user-123", role: str = "USER", exp_offset: int = 60) -> str:
    """Mint a test HS256 JWT valid for exp_offset seconds."""
    payload = {
        "sub": sub,
        "role": role,
        "exp": int(time.time()) + exp_offset,
    }
    return pyjwt.encode(payload, TEST_SECRET, algorithm="HS256")


def _make_expired_token(sub: str = "user-123", role: str = "USER") -> str:
    """Mint a token that expired 10 seconds ago."""
    return _make_token(sub=sub, role=role, exp_offset=-10)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app_with_auth():
    """Flask test app with a /protected endpoint using @require_auth."""
    app = Flask(__name__)
    app.config["TESTING"] = True

    @app.get("/protected")
    @auth_module.require_auth
    def protected():
        return jsonify({"user_id": g.user_id, "role": g.user_role})

    return app


@pytest.fixture
def app_with_admin():
    """Flask test app with /admin endpoint using @require_admin."""
    app = Flask(__name__)
    app.config["TESTING"] = True

    @app.get("/admin")
    @auth_module.require_admin
    def admin_only():
        return jsonify({"ok": True})

    return app


# ---------------------------------------------------------------------------
# @require_auth tests
# ---------------------------------------------------------------------------

class TestRequireAuth:
    def test_valid_token_returns_200_and_injects_context(self, app_with_auth):
        token = _make_token(sub="u-1", role="USER")
        with app_with_auth.test_client() as c:
            res = c.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data["user_id"] == "u-1"
        assert data["role"] == "USER"

    def test_missing_header_returns_401(self, app_with_auth):
        with app_with_auth.test_client() as c:
            res = c.get("/protected")
        assert res.status_code == 401

    def test_non_bearer_header_returns_401(self, app_with_auth):
        with app_with_auth.test_client() as c:
            res = c.get("/protected", headers={"Authorization": "Basic abc123"})
        assert res.status_code == 401

    def test_tampered_token_returns_401(self, app_with_auth):
        token = _make_token() + "tampered"
        with app_with_auth.test_client() as c:
            res = c.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 401

    def test_wrong_secret_token_returns_401(self, app_with_auth):
        token = pyjwt.encode(
            {"sub": "u-1", "role": "USER", "exp": int(time.time()) + 60},
            "wrong-secret",
            algorithm="HS256",
        )
        with app_with_auth.test_client() as c:
            res = c.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 401

    def test_expired_token_returns_401(self, app_with_auth):
        token = _make_expired_token()
        with app_with_auth.test_client() as c:
            res = c.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 401

    def test_completely_invalid_string_returns_401(self, app_with_auth):
        with app_with_auth.test_client() as c:
            res = c.get("/protected", headers={"Authorization": "Bearer not.a.jwt"})
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# @require_admin tests
# ---------------------------------------------------------------------------

class TestRequireAdmin:
    def test_admin_role_returns_200(self, app_with_admin):
        token = _make_token(role="ADMIN")
        with app_with_admin.test_client() as c:
            res = c.get("/admin", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200

    def test_user_role_returns_403(self, app_with_admin):
        token = _make_token(role="USER")
        with app_with_admin.test_client() as c:
            res = c.get("/admin", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 403

    def test_missing_token_returns_401(self, app_with_admin):
        with app_with_admin.test_client() as c:
            res = c.get("/admin")
        assert res.status_code == 401

    def test_expired_token_returns_401(self, app_with_admin):
        token = _make_expired_token(role="ADMIN")
        with app_with_admin.test_client() as c:
            res = c.get("/admin", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 401
