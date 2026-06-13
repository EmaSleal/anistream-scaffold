"""Flask Blueprint for the health check endpoint.

Used by Docker Compose healthcheck to verify the service is ready before
dependent containers (nextjs) are started.
"""
from flask import Blueprint, jsonify

health_bp = Blueprint("health", __name__)


@health_bp.get("/api/health")
def health_check():
    """Return a simple OK response. No auth required."""
    return jsonify({"ok": True}), 200
