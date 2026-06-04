import re
import time
import requests
from config import JIKAN_BASE, KITSU_BASE, REQUEST_DELAY


def _get(endpoint: str, params: dict = {}) -> dict:
    url = f"{JIKAN_BASE}/{endpoint}"
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    time.sleep(REQUEST_DELAY)
    return response.json()


def fetch_anime_by_id(mal_id: int) -> dict:
    """Fetch a single anime by its MAL id from Jikan.

    Returns the ``data`` object from the Jikan response.

    Raises:
        ValueError: if Jikan returns 404 (anime does not exist on MAL).
        requests.RequestException: for any other network or HTTP error.
    """
    try:
        data = _get(f"anime/{mal_id}")
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            raise ValueError("Anime not found") from exc
        raise
    if "data" not in data:
        raise ValueError("Anime not found")
    return data["data"]


def fetch_recommendations(mal_id: int) -> list[dict]:
    """Fetch the top-3 anime recommendations for a given MAL ID.

    Calls the Jikan ``/anime/{mal_id}/recommendations`` endpoint and returns
    the first 3 entries from the response data array.

    Returns an empty list on any network or HTTP error (fail-open).
    """
    try:
        response = _get(f"anime/{mal_id}/recommendations")
        return response.get("data", [])[:3]
    except Exception:
        return []


def fetch_top_anime(pages: int = 2) -> list[dict]:
    """Fetch top anime by popularity (25 per page)."""
    results = []
    for page in range(1, pages + 1):
        print(f"  Fetching top anime page {page}...")
        data = _get("top/anime", {"limit": 25, "page": page, "filter": "bypopularity"})
        results.extend(data.get("data", []))
    return results


def _extract_base_title(title: str) -> str:
    """Strip season/part suffixes and subtitle separators to get the root title."""
    t = re.sub(
        r"\s+(\d+(st|nd|rd|th)\s+)?(Season|Part)\s*\d+.*$", "", title, flags=re.IGNORECASE
    ).strip()
    if ": " in t:
        t = t.split(": ")[0]
    if " -" in t:
        t = t.split(" -")[0]
    return t.strip()


def _search_kitsu_multi(query: str, limit: int = 8) -> list[dict]:
    """Fetch up to `limit` Kitsu results for a query string."""
    try:
        resp = requests.get(
            f"{KITSU_BASE}/anime",
            params={"filter[text]": query, "page[limit]": limit},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("data", [])
    except Exception:
        return []


def _score_kitsu_item(item: dict, original: str, base: str) -> int:
    """Score a Kitsu result by how well it matches the original title."""
    attrs = item.get("attributes", {})
    titles = list((attrs.get("titles") or {}).values())
    titles.append(attrs.get("canonicalTitle") or "")
    titles.append(attrs.get("abbreviatedTitles") or "")
    all_lower = [str(t).lower() for t in titles if t]

    orig_lower = original.lower()
    base_lower = base.lower()
    score = 0

    for t in all_lower:
        if not t:
            continue
        if orig_lower == t:
            score += 30
        elif orig_lower in t or t in orig_lower:
            score += 15
        if base_lower == t:
            score += 20
        elif base_lower in t or t in base_lower:
            score += 10

    cover = attrs.get("coverImage") or {}
    if cover.get("large") or cover.get("original"):
        score += 5

    return score


def search_kitsu_anime(title: str) -> dict | None:
    """Search Kitsu for the best-matching anime and return its cover.

    Strategy:
    1. Search with the base title (strips season suffixes and subtitles) to get
       multiple candidates from Kitsu.
    2. Score each candidate against the original full title.
    3. Return the highest-scoring result that has a cover image; fall back to
       the highest-scoring result without one.

    Returns {"id": str, "cover_url": str | None} or None.
    """
    base = _extract_base_title(title)
    search_query = base if base else title

    candidates = _search_kitsu_multi(search_query)
    time.sleep(0.2)

    # If base search returned nothing, try the full title as a last resort
    if not candidates and search_query != title:
        candidates = _search_kitsu_multi(title)
        time.sleep(0.2)

    if not candidates:
        return None

    scored = sorted(candidates, key=lambda c: _score_kitsu_item(c, title, base), reverse=True)

    for item in scored:
        attrs = item.get("attributes", {})
        cover = attrs.get("coverImage") or {}
        cover_url = cover.get("large") or cover.get("original")
        if cover_url:
            return {"id": item["id"], "cover_url": cover_url}

    # No cover found — return the best match anyway
    best = scored[0]
    return {"id": best["id"], "cover_url": None}


def fetch_kitsu_episodes(kitsu_anime_id: str) -> dict[int, dict]:
    """Fetch all episodes for a Kitsu anime. Returns a dict keyed by episode number."""
    episodes: dict[int, dict] = {}
    try:
        resp = requests.get(
            f"{KITSU_BASE}/episodes",
            params={"filter[mediaId]": kitsu_anime_id, "page[limit]": 100},
            timeout=10,
        )
        resp.raise_for_status()
        for ep in resp.json().get("data", []):
            attrs = ep.get("attributes", {})
            num = attrs.get("number")
            if not num:
                continue
            thumb = attrs.get("thumbnail")
            episodes[int(num)] = {
                "title": attrs.get("canonicalTitle"),
                "description": attrs.get("synopsis") or attrs.get("description"),
                "thumbnail_url": thumb.get("original") if isinstance(thumb, dict) else None,
                "aired_at": attrs.get("airdate"),
                "duration_sec": (attrs.get("length") or 0) * 60,
            }
    except Exception:
        pass
    return episodes


def fetch_jikan_episodes(mal_id: int) -> dict[int, str]:
    """Fetch episode titles for an anime from Jikan.

    Handles pagination (100 episodes per page). Returns a dict keyed by
    episode number with the English title (falls back to romanji or default title).
    """
    titles: dict[int, str] = {}
    page = 1
    while True:
        try:
            data = _get(f"anime/{mal_id}/episodes", {"page": page})
        except Exception:
            break
        for ep in data.get("data", []):
            num = ep.get("mal_id")
            if not num:
                continue
            title = ep.get("title") or ep.get("title_romanji") or ep.get("title_japanese") or ""
            if title:
                titles[int(num)] = title
        pagination = data.get("pagination", {})
        if not pagination.get("has_next_page"):
            break
        page += 1
    return titles


def search_anime_by_title(title: str) -> dict | None:
    """Search Jikan for an anime by title. Returns the first match's raw data dict."""
    try:
        data = _get("anime", {"q": title, "limit": 3})
        results = data.get("data", [])
        return results[0] if results else None
    except Exception:
        return None


def fetch_simulcasts() -> list[dict]:
    """Fetch currently airing anime (current season)."""
    print("  Fetching simulcasts...")
    data = _get("seasons/now", {"limit": 25})
    return data.get("data", [])


def fetch_kitsu_series_status(kitsu_id: str) -> str | None:
    """Fetch the ``attributes.status`` for a Kitsu anime entry.

    Calls the Kitsu public API (no auth required):
    GET https://kitsu.app/api/edge/anime/{kitsu_id}

    Args:
        kitsu_id: The Kitsu anime ID (numeric string).

    Returns:
        The status string (e.g. "current", "finished", "upcoming"), or None
        if the request fails for any reason (fail-open — never crashes the
        refresh path).
    """
    try:
        resp = requests.get(
            f"{KITSU_BASE}/anime/{kitsu_id}",
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("data", {}).get("attributes", {}).get("status")
    except Exception:
        return None


def fetch_jikan_by_genre(genre_id: int, limit: int = 15) -> list[dict]:
    """Fetch top-scored anime for a Jikan genre ID.

    Returns up to `limit` raw Jikan anime dicts (same shape as fetch_anime_by_id).
    Returns [] on any error (fail-open).
    """
    try:
        resp = _get("anime", params={"genres": genre_id, "order_by": "score", "sort": "desc", "limit": 25})
        return (resp.get("data") or [])[:limit]
    except Exception:
        return []
