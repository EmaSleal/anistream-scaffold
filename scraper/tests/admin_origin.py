"""Helpers to post an ingest request with a verified admin origin (ADR-016)."""
import time

import jwt as pyjwt

import auth


def admin_headers(role: str = "ADMIN", expires_in: int = 60) -> dict:
    token = pyjwt.encode(
        {"sub": "admin", "role": role, "exp": int(time.time()) + expires_in},
        auth._INTERNAL_JWT_SECRET, algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def admin_post(client, path: str, body: dict):
    """POST with slug_source=admin and a valid admin internal token."""
    return client.post(path, json={**body, "slug_source": "admin"}, headers=admin_headers())
