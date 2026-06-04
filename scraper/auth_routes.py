"""Flask Blueprint for internal auth service endpoints.

These routes are called server-to-server by Next.js (Auth.js callbacks) and
are protected by the @require_service decorator (X-Service-Key header).
They are NOT exposed to the browser.
"""
from flask import Blueprint, jsonify, request

from auth import require_service
from db import users as db_users

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.post("/sync-user")
@require_service
def sync_user():
    """Upsert a user row from Auth.js signIn callback.

    Body: { "id": str, "email": str, "name": str|null, "photo_url": str|null }
    Returns: 200 { "ok": true } | 400 { "error": "..." } | 401
    """
    body = request.get_json(silent=True) or {}
    user_id = body.get("id")
    if not user_id:
        return jsonify({"error": "id is required"}), 400
    db_users.upsert_user(
        user_id,
        body.get("email", ""),
        body.get("name"),
        body.get("photo_url"),
    )
    return jsonify({"ok": True}), 200


@auth_bp.get("/role/<user_id>")
@require_service
def get_role(user_id: str):
    """Return the stored role for a user, defaulting to USER if not found.

    Returns: 200 { "role": "USER" | "ADMIN" } | 401
    """
    role = db_users.get_user_role(user_id)
    return jsonify({"role": role or "USER"}), 200
