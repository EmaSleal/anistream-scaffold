import re
import json
import cloudscraper
from config import ANIMEFLV_BASE, CLOUDSCRAPER_BROWSER

_scraper = cloudscraper.create_scraper(browser=CLOUDSCRAPER_BROWSER)


def scrape_episode_list(slug: str) -> list[dict]:
    """Scrape the episode list for an anime series from animeflv.

    Fetches ``{ANIMEFLV_BASE}/anime/{slug}`` and parses the inline
    ``var episodes = [...]`` JavaScript variable.

    Each array entry has the shape ``[episode_number, ?, title_or_null]``.

    Returns:
        list of dicts with keys ``episode_number`` (int) and ``title`` (str | None).

    Raises:
        RuntimeError: if the page is unreachable or the variable is absent.
    """
    url = f"{ANIMEFLV_BASE}/anime/{slug}"
    try:
        response = _scraper.get(url, timeout=15)
        response.raise_for_status()
    except Exception as exc:
        raise RuntimeError(f"HTTP error fetching {url}: {exc}") from exc

    match = re.search(r"var\s+episodes\s*=\s*(\[.*?\]);", response.text, re.DOTALL)
    if not match:
        raise RuntimeError(
            f"'var episodes' not found in {url} (status {response.status_code}) — "
            f"page may have changed structure or Cloudflare blocked the request"
        )

    try:
        raw_episodes = json.loads(match.group(1))
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError("Could not fetch episode list from animeflv") from exc

    # Extract internal anime ID for thumbnail URL construction
    anime_id_match = re.search(r'var\s+anime_info\s*=\s*\["(\d+)"', response.text)
    anime_id = anime_id_match.group(1) if anime_id_match else None

    episodes = []
    for entry in raw_episodes:
        # entry shape: [episode_number, something, title_or_null]
        ep_number = int(entry[0]) if entry else None
        title = entry[2] if len(entry) > 2 else None
        if ep_number is not None:
            thumb = (
                f"https://cdn.animeflv.net/screenshots/{anime_id}/{ep_number}/3.jpg"
                if anime_id else None
            )
            episodes.append({
                "episode_number": ep_number,
                "title": title if title else None,
                "thumbnail_url": thumb,
            })

    return episodes


def scrape_next_episode_date(slug: str) -> str | None:
    """Return the next episode air date for an anime from animeflv.

    Parses the ``<li class="fa-play-circle Next">`` card in the episode list,
    which contains a ``<span class="Date ...">YYYY-MM-DD</span>``.

    Returns the date string (e.g. ``"2026-06-05"``) or None if not found.
    """
    url = f"{ANIMEFLV_BASE}/anime/{slug}"
    try:
        response = _scraper.get(url, timeout=15)
        response.raise_for_status()
    except Exception:
        return None

    match = re.search(
        r'class="fa-play-circle Next".*?<span[^>]*class="Date[^"]*"[^>]*>\s*(\d{4}-\d{2}-\d{2})\s*</span>',
        response.text,
        re.DOTALL,
    )
    return match.group(1) if match else None


def scrape_related_series(slug: str) -> list[dict]:
    """Return related series listed on the animeflv series page.

    Parses ``ul.ListAnmRel`` and returns [{slug, title, relation}] where
    relation is one of "Secuela", "Precuela", "Historia paralela", "OVA", etc.
    Returns an empty list if the page is unreachable or no relations exist.
    """
    url = f"{ANIMEFLV_BASE}/anime/{slug}"
    try:
        response = _scraper.get(url, timeout=15)
        response.raise_for_status()
    except Exception:
        return []

    ul_match = re.search(
        r'<ul[^>]*class="ListAnmRel"[^>]*>(.*?)</ul>',
        response.text,
        re.DOTALL,
    )
    if not ul_match:
        return []

    items = re.findall(
        r'<a\s+href="/anime/([^"]+)">([^<]+)</a>\s*\(([^)]+)\)',
        ul_match.group(1),
    )
    return [
        {"slug": s.strip("/"), "title": t.strip(), "relation": r.strip()}
        for s, t, r in items
    ]


def scrape_episode_servers(episode_slug: str) -> dict:
    """Scrape the server list for an episode from animeflv.

    Fetches ``{ANIMEFLV_BASE}/ver/{episode_slug}`` and parses the inline
    ``var videos = {...}`` JavaScript variable.

    Returns:
        dict with keys like ``"SUB"`` and ``"LAT"``, each containing a list
        of server dicts.

    Raises:
        RuntimeError: if the page is unreachable or the variable is absent.
    """
    url = f"{ANIMEFLV_BASE}/ver/{episode_slug}"
    try:
        response = _scraper.get(url, timeout=15)
        response.raise_for_status()
    except Exception as exc:
        raise RuntimeError("Could not fetch servers from animeflv") from exc

    match = re.search(r"var\s+videos\s*=\s*(\{.*?\});", response.text, re.DOTALL)
    if not match:
        raise RuntimeError("Could not fetch servers from animeflv")

    try:
        videos = json.loads(match.group(1))
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError("Could not fetch servers from animeflv") from exc

    return videos
