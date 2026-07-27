import re
import time
import requests
from config import JIKAN_BASE, KITSU_BASE, REQUEST_DELAY, MAL_CLIENT_ID


def _get(endpoint: str, params: dict = {}) -> dict:
    url = f"{JIKAN_BASE}/{endpoint}"
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    time.sleep(REQUEST_DELAY)
    return response.json()


_MAL_BASE = "https://api.myanimelist.net/v2"
_MAL_ANIME_FIELDS = (
    "alternative_titles,main_picture,num_episodes,status,mean,rank,popularity,"
    "media_type,rating,genres,synopsis,start_date,start_season,broadcast"
)
_MAL_TYPE_MAP = {
    "tv": "TV", "ova": "OVA", "movie": "Movie", "special": "Special",
    "ona": "ONA", "music": "Music", "cm": "CM", "pv": "PV", "tv_special": "TV Special",
}
_MAL_STATUS_MAP = {
    "finished_airing": "Finished Airing",
    "currently_airing": "Currently Airing",
    "not_yet_aired": "Not yet aired",
}
_MAL_RATING_MAP = {
    "g": "G - All Ages", "pg": "PG - Children", "pg13": "PG-13 - Teens 13 or older",
    "r17": "R - 17+ (violence & profanity)", "r": "R+ - Mild Nudity", "rx": "Rx - Hentai",
}


def _mal_node_to_jikan(node: dict) -> dict:
    """Convert a MAL API v2 anime node to Jikan-compatible response shape."""
    alt = node.get("alternative_titles") or {}
    pic = node.get("main_picture") or {}
    broadcast = node.get("broadcast") or {}
    start_date = node.get("start_date") or ""
    start_season = node.get("start_season") or {}

    titles = []
    if alt.get("en"):
        titles.append({"title": alt["en"]})
    if alt.get("ja"):
        titles.append({"title": alt["ja"]})
    for syn in (alt.get("synonyms") or []):
        if syn:
            titles.append({"title": syn})

    bcast_day = broadcast.get("day_of_week") or ""
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
        "type": _MAL_TYPE_MAP.get(node.get("media_type") or "", "TV"),
        "status": _MAL_STATUS_MAP.get(node.get("status") or "", ""),
        "score": node.get("mean"),
        "episodes": node.get("num_episodes") or None,
        "rank": node.get("rank"),
        "popularity": node.get("popularity"),
        "synopsis": node.get("synopsis"),
        "airing": node.get("status") == "currently_airing",
        "genres": [
            {"mal_id": g.get("id"), "type": "anime", "name": g.get("name"), "url": ""}
            for g in (node.get("genres") or [])
        ],
        "themes": [],
        "rating": _MAL_RATING_MAP.get(node.get("rating") or "", ""),
        "titles": titles,
        "broadcast": {
            "day": bcast_day.capitalize() if bcast_day else None,
            "time": broadcast.get("start_time"),
            "timezone": "Asia/Tokyo" if bcast_day else None,
        },
        "aired": {
            "from": start_date or None,
            "prop": {"from": {"year": int(start_date[:4]) if len(start_date) >= 4 else None}},
        },
        "year": start_season.get("year"),
    }


def fetch_anime_by_id(mal_id: int) -> dict:
    """Fetch a single anime by MAL id. Prefers MAL API v2 when MAL_CLIENT_ID is set.

    Returns data in Jikan-compatible shape.

    Raises:
        ValueError: if the anime does not exist (404).
        requests.RequestException: on other network/HTTP errors.
    """
    if MAL_CLIENT_ID:
        try:
            resp = requests.get(
                f"{_MAL_BASE}/anime/{mal_id}",
                params={"fields": _MAL_ANIME_FIELDS},
                headers={"X-MAL-CLIENT-ID": MAL_CLIENT_ID},
                timeout=10,
            )
            if resp.status_code == 404:
                raise ValueError("Anime not found")
            resp.raise_for_status()
            node = resp.json()
            if not node.get("id"):
                raise ValueError("Anime not found")
            return _mal_node_to_jikan(node)
        except ValueError:
            raise
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                raise ValueError("Anime not found") from exc
            raise

    try:
        data = _get(f"anime/{mal_id}")
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            raise ValueError("Anime not found") from exc
        raise
    if "data" not in data:
        raise ValueError("Anime not found")
    return data["data"]


def fetch_recommendations(mal_id: int) -> list[dict] | None:
    """Fetch the top-3 anime recommendations for a given MAL ID.

    Calls the Jikan ``/anime/{mal_id}/recommendations`` endpoint and returns
    the first 3 entries from the response data array.

    Returns:
        list[dict] — Jikan recommendation entries (may be empty if none exist).
        None       — network or HTTP error; caller should retry later.
    """
    try:
        response = _get(f"anime/{mal_id}/recommendations")
        return response.get("data", [])[:3]
    except Exception:
        return None


def fetch_related_anime(mal_id: int) -> tuple[list[int], list[str]] | tuple[None, None]:
    """Fetch related anime IDs and genres for a MAL ID via the official MAL API v2.

    Returns (related_mal_ids, genres) on success, (None, None) on network/HTTP error.
    An empty related_mal_ids list is a valid result (series with no related entries).
    """
    from config import MAL_CLIENT_ID
    if not MAL_CLIENT_ID:
        return None, None
    try:
        resp = requests.get(
            f"https://api.myanimelist.net/v2/anime/{mal_id}",
            params={"fields": "related_anime,genres"},
            headers={"X-MAL-CLIENT-ID": MAL_CLIENT_ID},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        related_ids = [
            entry["node"]["id"]
            for entry in data.get("related_anime", [])
            if entry.get("node", {}).get("id")
        ]
        genres = [g["name"] for g in data.get("genres", []) if g.get("name")]
        return related_ids, genres
    except Exception:
        return None, None


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


def fetch_jikan_episodes(mal_id: int) -> dict[int, dict]:
    """Fetch episode metadata for an anime from Jikan.

    Handles pagination (100 episodes per page). Returns a dict keyed by
    episode number with {"title": str | None, "aired_at": str | None}.
    """
    episodes: dict[int, dict] = {}
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
            title = ep.get("title") or ep.get("title_romanji") or ep.get("title_japanese") or None
            episodes[int(num)] = {
                "title": title,
                "aired_at": ep.get("aired"),
            }
        pagination = data.get("pagination", {})
        if not pagination.get("has_next_page"):
            break
        page += 1
    return episodes


def search_anime_by_title(title: str) -> dict | None:
    """Search Jikan for an anime by title. Returns the first match's raw data dict."""
    try:
        data = _get("anime", {"q": title, "limit": 3})
        results = data.get("data", [])
        return results[0] if results else None
    except Exception:
        return None


def fetch_simulcasts() -> list[dict]:
    """Fetch currently airing anime (current season).

    Handles pagination (25 items per page). Returns all airing anime.

    Raises:
        requests.RequestException: if any page fails to fetch. Callers that
        treat the result as the complete airing set (e.g. sync_jikan's
        finished-series reconciliation) must not silently proceed on a
        partial list — that would misclassify still-airing series as finished.
    """
    print("  Fetching simulcasts...")
    results = []
    page = 1
    while True:
        data = _get("seasons/now", {"page": page})
        results.extend(data.get("data", []))
        pagination = data.get("pagination", {})
        if not pagination.get("has_next_page"):
            break
        page += 1
    return results


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


def fetch_jikan_relations(mal_id: int) -> list[dict]:
    """Fetch related anime entries. Prefers MAL API v2; falls back to Jikan.

    Returns list of {relation, entry: [{mal_id, name, type}]} in Jikan shape.
    Empty list on any error (fail-open).
    """
    if MAL_CLIENT_ID:
        try:
            resp = requests.get(
                f"{_MAL_BASE}/anime/{mal_id}",
                params={"fields": "related_anime"},
                headers={"X-MAL-CLIENT-ID": MAL_CLIENT_ID},
                timeout=10,
            )
            resp.raise_for_status()
            related = resp.json().get("related_anime", [])
            by_relation: dict[str, list] = {}
            for item in related:
                node = item.get("node", {})
                rel = item.get("relation_type_formatted", "")
                if rel not in by_relation:
                    by_relation[rel] = []
                by_relation[rel].append({
                    "mal_id": node.get("id"),
                    "name": node.get("title", ""),
                    "type": "anime",
                    "url": "",
                })
            return [{"relation": rel, "entry": entries} for rel, entries in by_relation.items()]
        except Exception:
            return []

    try:
        data = _get(f"anime/{mal_id}/relations")
        return data.get("data", [])
    except Exception:
        return []


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


def search_animeflv(query: str, limit: int = 10) -> list[dict]:
    """Search AnimeFlv by title and return matching anime with slugs.

    Returns list of dicts with {title, slug, animeflv_url}.
    Returns [] on any error (fail-open).
    """
    if not query or len(query.strip()) < 2:
        return []

    try:
        # AnimeFlv search URL
        url = "https://www4.animeflv.net/browse"
        params = {"q": query}

        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()

        # Extract anime cards from the response HTML
        # Pattern: href="/anime/{slug}"
        pattern = r'<a\s+href="/anime/([^"]+)"[^>]*>\s*<div[^>]*class="[^"]*Image[^"]*"[^>]*>.*?<h3[^>]*class="[^"]*Title[^"]*"[^>]*>([^<]+)</h3>'
        matches = re.findall(pattern, resp.text, re.DOTALL)

        results = []
        seen_slugs = set()

        for slug, title in matches:
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)

            results.append({
                "title": title.strip(),
                "slug": slug.strip(),
                "animeflv_url": f"https://www4.animeflv.net/anime/{slug}",
            })

            if len(results) >= limit:
                break

        return results

    except Exception:
        return []
