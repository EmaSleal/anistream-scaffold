"""Flask Blueprint for proxying Jikan anime search requests.

Centralises all Jikan traffic through Flask so that the shared REQUEST_DELAY
in fetcher._get() serialises calls from both background jobs and Next.js server
actions, preventing IP-level 60 req/min exhaustion.
"""
import time
import requests
from flask import Blueprint, request, jsonify
from auth import require_admin
from fetcher import _get

_RETRYABLE_STATUSES = {429, 503, 504}


def _get_with_retry(params: dict, max_attempts: int = 3) -> dict:
    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(max_attempts):
        if attempt > 0:
            time.sleep(attempt * 1.5)
        try:
            return _get("anime", params)
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code in _RETRYABLE_STATUSES:
                last_exc = exc
                continue
            raise
        except requests.RequestException as exc:
            last_exc = exc
            continue
    raise last_exc

jikan_bp = Blueprint("jikan", __name__, url_prefix="/api/jikan")

_ANIME_PARAMS = (
    "q",
    "type",
    "status",
    "rating",
    "min_score",
    "max_score",
    "order_by",
    "sort",
    "genres",
    "genres_exclude",
    "start_date",
    "end_date",
    "letter",
    "page",
    "limit",
)


@jikan_bp.get("/anime")
@require_admin
def search_anime():
    """GET /api/jikan/anime — proxy Jikan anime search with content guards.

    Reads caller-supplied query params, applies content safety guards, and
    forwards the request to Jikan via fetcher._get() which already enforces
    REQUEST_DELAY between calls.

    Content guards (applied server-side, cannot be overridden by callers):
      - sfw=true is always forced (approved=true omitted — causes slow Jikan queries).
      - rating=rx is dropped.
      - MAL genre 12 (hentai) is always appended to genres_exclude.
      - min_score defaults to "5" if the caller did not supply it.
    """
    params: dict[str, str] = {}

    for key in _ANIME_PARAMS:
        value = request.args.get(key)
        if value is not None:
            params[key] = value

    # Content guards — applied last so callers cannot override them.
    # approved=true is intentionally omitted: it causes slow Jikan queries and 504s.
    # sfw=true + genre_12 exclusion is sufficient for content safety.
    params["sfw"] = "true"

    if params.get("rating") == "rx":
        params.pop("rating")

    existing_exclude = params.get("genres_exclude", "")
    exclude_ids = list({*existing_exclude.split(","), "12"} - {""})
    params["genres_exclude"] = ",".join(exclude_ids)

    if "min_score" not in params:
        params["min_score"] = "5"

    try:
        data = _get_with_retry(params)
        return jsonify(data)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 429:
            return jsonify({"error": "rate_limited"}), 429
        status = exc.response.status_code if exc.response is not None else 502
        return jsonify({"error": f"jikan_{status}"}), 502
    except Exception:
        return jsonify({"error": "jikan_unavailable"}), 502
