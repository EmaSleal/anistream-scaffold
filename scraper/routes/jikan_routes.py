"""Flask Blueprint for proxying anime search through the MAL official API v2.

Replaces the previous Jikan scraper proxy. The public Jikan instance
(api.jikan.moe) is unreliable because MAL blocks Jikan's scraping IP for
search queries. The MAL v2 API is a proper REST API that requires only a
client_id header — no user OAuth needed for public search.

Response is transformed to the Jikan shape so the Next.js client is unchanged.
"""
import logging
import requests
from flask import Blueprint, request, jsonify
from auth import require_admin
from config import MAL_CLIENT_ID

logger = logging.getLogger(__name__)

jikan_bp = Blueprint("jikan", __name__, url_prefix="/api/jikan")

_MAL_BASE = "https://api.myanimelist.net/v2"
_MAL_FIELDS = (
    "id,title,alternative_titles,main_picture,num_episodes,"
    "status,mean,rank,popularity,media_type,rating,genres,synopsis"
)

_MAL_STATUS_TO_JIKAN = {
    "finished_airing": "Finished Airing",
    "currently_airing": "Currently Airing",
    "not_yet_aired": "Not yet aired",
}

_MAL_TYPE_TO_JIKAN = {
    "tv": "TV",
    "ova": "OVA",
    "movie": "Movie",
    "special": "Special",
    "ona": "ONA",
    "music": "Music",
    "cm": "CM",
    "pv": "PV",
    "tv_special": "TV Special",
}

_MAL_RATING_TO_JIKAN = {
    "g": "G - All Ages",
    "pg": "PG - Children",
    "pg13": "PG-13 - Teens 13 or older",
    "r17": "R - 17+ (violence & profanity)",
    "r": "R+ - Mild Nudity",
    "rx": "Rx - Hentai",
}

_JIKAN_STATUS_TO_MAL = {
    "airing": "currently_airing",
    "complete": "finished_airing",
    "upcoming": "not_yet_aired",
}


def _mal_headers() -> dict:
    return {"X-MAL-CLIENT-ID": MAL_CLIENT_ID}


def _node_to_jikan(node: dict) -> dict:
    """Transform a MAL v2 anime node into a Jikan-compatible response dict."""
    alt = node.get("alternative_titles") or {}
    pic = node.get("main_picture") or {}
    mal_status = node.get("status") or ""
    mal_type = node.get("media_type") or ""

    return {
        "mal_id": node.get("id"),
        "title": node.get("title"),
        "title_english": alt.get("en") or None,
        "title_japanese": alt.get("ja") or None,
        "images": {
            "jpg": {
                "image_url": pic.get("large") or pic.get("medium"),
                "small_image_url": pic.get("medium"),
                "large_image_url": pic.get("large"),
            }
        },
        "type": _MAL_TYPE_TO_JIKAN.get(mal_type),
        "status": _MAL_STATUS_TO_JIKAN.get(mal_status, mal_status),
        "score": node.get("mean"),
        "episodes": node.get("num_episodes") or None,
        "rank": node.get("rank"),
        "popularity": node.get("popularity"),
        "synopsis": node.get("synopsis"),
        "airing": mal_status == "currently_airing",
        "approved": True,
        "genres": [
            {"mal_id": g.get("id"), "type": "anime", "name": g.get("name"), "url": ""}
            for g in (node.get("genres") or [])
        ],
        "rating": _MAL_RATING_TO_JIKAN.get(node.get("rating") or ""),
    }


def _apply_client_filters(items: list[dict], args: dict) -> list[dict]:
    """Apply filters that the MAL API doesn't support natively as search params."""
    result = items

    if type_filter := args.get("type"):
        jikan_type = _MAL_TYPE_TO_JIKAN.get(type_filter.lower())
        if jikan_type:
            result = [i for i in result if i.get("type") == jikan_type]

    if status_filter := args.get("status"):
        mal_status = _JIKAN_STATUS_TO_MAL.get(status_filter)
        if mal_status:
            jikan_status = _MAL_STATUS_TO_JIKAN.get(mal_status, "")
            result = [i for i in result if i.get("status") == jikan_status]

    if min_score := args.get("min_score"):
        try:
            min_val = float(min_score)
            result = [i for i in result if i.get("score") is not None and i["score"] >= min_val]
        except ValueError:
            pass

    if max_score := args.get("max_score"):
        try:
            max_val = float(max_score)
            result = [i for i in result if i.get("score") is not None and i["score"] <= max_val]
        except ValueError:
            pass

    exclude_raw = args.get("genres_exclude", "12")
    exclude_ids = {int(x) for x in exclude_raw.split(",") if x.strip().isdigit()}
    if exclude_ids:
        result = [
            i for i in result
            if not any(g.get("mal_id") in exclude_ids for g in (i.get("genres") or []))
        ]

    return result


@jikan_bp.get("/anime")
@require_admin
def search_anime():
    """GET /api/jikan/anime — proxy anime search through the MAL official API v2.

    Uses MAL's search endpoint when a query (q) is provided, and the ranking
    endpoint (ranking_type=all) when browsing without a query. Results are
    filtered client-side for params MAL doesn't expose natively (type, status,
    score range, genre exclusion), then transformed into the Jikan response shape.
    """
    if not MAL_CLIENT_ID:
        logger.error("mal_proxy: MAL_CLIENT_ID is not configured")
        return jsonify({"error": "MAL_CLIENT_ID is not set in server config."}), 502

    q = (request.args.get("q") or "").strip()
    page = max(1, int(request.args.get("page") or 1))
    limit = min(100, max(1, int(request.args.get("limit") or 25)))
    offset = (page - 1) * limit

    if q and len(q) < 3:
        return jsonify({"error": "Search query must be at least 3 characters."}), 400

    try:
        if q:
            logger.info("mal_proxy: search q=%r page=%d limit=%d", q, page, limit)
            resp = requests.get(
                f"{_MAL_BASE}/anime",
                params={"q": q, "limit": limit, "offset": offset, "fields": _MAL_FIELDS, "nsfw": "false"},
                headers=_mal_headers(),
                timeout=15,
            )
        else:
            logger.info("mal_proxy: ranking browse page=%d limit=%d", page, limit)
            resp = requests.get(
                f"{_MAL_BASE}/anime/ranking",
                params={"ranking_type": "all", "limit": limit, "offset": offset, "fields": _MAL_FIELDS, "nsfw": "false"},
                headers=_mal_headers(),
                timeout=15,
            )

        resp.raise_for_status()
        mal_data = resp.json()

    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else 0
        body = exc.response.text[:300] if exc.response is not None else ""
        logger.error("mal_proxy: HTTPError status=%s body=%r", status, body)
        if status == 401:
            return jsonify({"error": "MAL API auth failed — check MAL_CLIENT_ID."}), 502
        return jsonify({"error": f"MAL request failed ({status})."}), 502
    except requests.RequestException as exc:
        logger.error("mal_proxy: RequestException %s", exc)
        return jsonify({"error": "Network error — unable to reach MAL API."}), 502

    raw = [_node_to_jikan(item.get("node", item)) for item in mal_data.get("data", [])]
    filtered = _apply_client_filters(raw, request.args)

    has_next = bool(mal_data.get("paging", {}).get("next"))

    return jsonify({
        "data": filtered,
        "pagination": {
            "current_page": page,
            "has_next_page": has_next,
            "last_visible_page": page + 1 if has_next else page,
            "items": {"count": len(filtered), "total": None, "per_page": limit},
        },
    })
