"""Flask authentication decorators for validating internal HS256 JWTs and service keys.

Auth mechanism (A2):
  1. Next.js route handlers decode the Auth.js v5 JWE token (using AUTH_SECRET),
     then sign a short-lived HS256 JWT {sub, role, exp:+60s} with INTERNAL_JWT_SECRET.
  2. Flask receives Authorization: Bearer <internal_jwt> and validates it here.

Service auth mechanism:
  - Internal server-to-server endpoints (e.g. auth sync from Next.js) use a shared
    SERVICE_SECRET compared against the X-Service-Key request header.

Required environment variables:
  - INTERNAL_JWT_SECRET: shared secret between Next.js and Flask (add to BOTH
    anistream/.env.local AND scraper/.env.local with the same value).
  - SERVICE_SECRET: shared secret for Next.js-to-Flask service auth (add to BOTH
    anistream/.env.local AND scraper/.env.local with the same value).
"""

import os
from functools import wraps

import jwt
from flask import g, jsonify, request

# Fail fast at import time if the secret is not configured.
_INTERNAL_JWT_SECRET = os.environ.get("INTERNAL_JWT_SECRET")
if not _INTERNAL_JWT_SECRET:
    raise RuntimeError(
        "INTERNAL_JWT_SECRET environment variable is not set. "
        "Add it to scraper/.env.local (must match the value in anistream/.env.local)."
    )

_SERVICE_SECRET = os.environ.get("SERVICE_SECRET")
if not _SERVICE_SECRET:
    raise RuntimeError(
        "SERVICE_SECRET environment variable is not set. "
        "Add it to scraper/.env.local (must match the value in anistream/.env.local)."
    )


def require_auth(f):
    """Decorator: validates the Authorization: Bearer <hs256-jwt> header.

    On success, injects:
      g.user_id   (from the 'sub' claim)
      g.user_role (from the 'role' claim)

    On failure:
      401 with {"error": "<reason>"}
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or malformed Authorization header"}), 401

        token = auth_header[len("Bearer "):]
        try:
            payload = jwt.decode(
                token,
                _INTERNAL_JWT_SECRET,
                algorithms=["HS256"],
            )
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token has expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401

        g.user_id = payload.get("sub")
        g.user_role = payload.get("role", "USER")
        return f(*args, **kwargs)

    return decorated


def require_service(f):
    """Decorator: validates the X-Service-Key header against SERVICE_SECRET.

    Used for internal server-to-server endpoints (Next.js -> Flask).
    On failure:
      401 with {"error": "<reason>"}
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-Service-Key", "")
        if not key or key != _SERVICE_SECRET:
            return jsonify({"error": "Invalid or missing X-Service-Key"}), 401
        return f(*args, **kwargs)

    return decorated


def require_admin(f):
    """Decorator: wraps require_auth and additionally enforces role == 'ADMIN'.

    Returns 401 if the token is invalid/missing, 403 if role is not ADMIN.
    """
    @wraps(f)
    @require_auth
    def decorated(*args, **kwargs):
        if g.user_role != "ADMIN":
            return jsonify({"error": "Forbidden: admin role required"}), 403
        return f(*args, **kwargs)

    return decorated
