"""AnimeAV1 scraper module.

Mirrors the structure of scraper_jkanime.py.
All page requests use cloudscraper to bypass Cloudflare.
Zilla player requests always include the required Referer/Origin headers.
"""

import re
import cloudscraper
from bs4 import BeautifulSoup
from config import CLOUDSCRAPER_BROWSER

_scraper = cloudscraper.create_scraper(browser=CLOUDSCRAPER_BROWSER)

ANIMEAV1_BASE = "https://animeav1.com"
_ZILLA_HEADERS = {
    "Referer": "https://animeav1.com/",
    "Origin": "https://animeav1.com",
}

# Regex to extract the Zilla hash from the /play/{hash} embed src.
_ZILLA_HASH_RE = re.compile(
    r'src="https://player\.zilla-networks\.com/play/([a-f0-9]+)"'
)


def search_animeav1(query: str) -> list[dict]:
    """Search the AnimeAV1 catalog and return matching series.

    GET https://animeav1.com/catalogo?search={query}
    Parses <article> cards and extracts slug, title, and thumbnail_url.

    Returns:
        list of { title, slug, animeav1_url, thumbnail_url }
        Empty list on any error or no results.
    """
    try:
        resp = _scraper.get(
            f"{ANIMEAV1_BASE}/catalogo",
            params={"search": query},
            timeout=20,
        )
        resp.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []

    for article in soup.find_all("article"):
        # Slug from href="/media/{slug}"
        link = article.find("a", href=re.compile(r"^/media/[^/]+$"))
        if not link:
            continue
        href = link.get("href", "")
        slug = href.split("/media/")[-1].strip("/")
        if not slug:
            continue

        title_tag = article.find(["h2", "h3", "h4"])
        title = title_tag.get_text(strip=True) if title_tag else slug

        img = article.find("img")
        thumbnail_url = img.get("src") if img else None

        results.append({
            "title": title,
            "slug": slug,
            "animeav1_url": f"{ANIMEAV1_BASE}/media/{slug}",
            "thumbnail_url": thumbnail_url,
        })

    return results


def scrape_animeav1_episodes(slug: str) -> list[dict]:
    """Fetch the episode list for a series from AnimeAV1.

    GET https://animeav1.com/media/{slug}
    Parses episode cards and returns episode_number + thumbnail_url.
    Episode number comes from href="/media/{slug}/{N}".
    Thumbnail is best-effort from the CDN pattern; nullable.

    Returns:
        list of { episode_number: int, thumbnail_url: str | None }
        Empty list on any error or unknown slug.
    """
    try:
        resp = _scraper.get(
            f"{ANIMEAV1_BASE}/media/{slug}",
            headers=_ZILLA_HEADERS,
            timeout=20,
        )
        resp.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    # Try to extract the numeric anime_id for CDN thumbnail URLs.
    # Best-effort: look for data-id attribute or a known JS pattern.
    numeric_id = None
    data_id_tag = soup.find(attrs={"data-id": True})
    if data_id_tag:
        numeric_id = data_id_tag.get("data-id")
    if not numeric_id:
        # Fallback: scan script tags for a numeric ID pattern
        for script in soup.find_all("script"):
            text = script.string or ""
            m = re.search(r'"anime_id"\s*:\s*(\d+)', text)
            if m:
                numeric_id = m.group(1)
                break

    episodes = []
    # Episode links match /media/{slug}/{N}
    ep_pattern = re.compile(rf"^/media/{re.escape(slug)}/(\d+)$")

    seen = set()
    for link in soup.find_all("a", href=ep_pattern):
        href = link.get("href", "")
        m = ep_pattern.match(href)
        if not m:
            continue
        ep_num = int(m.group(1))
        if ep_num in seen:
            continue
        seen.add(ep_num)

        # Thumbnail: cdn.animeav1.com/screenshots/{numeric_id}/{ep_num}.jpg
        thumbnail_url = None
        if numeric_id:
            thumbnail_url = (
                f"https://cdn.animeav1.com/screenshots/{numeric_id}/{ep_num}.jpg"
            )
        # Also check for an <img> inside this link/card
        img = link.find("img")
        if img and img.get("src"):
            thumbnail_url = img["src"]

        episodes.append({
            "episode_number": ep_num,
            "thumbnail_url": thumbnail_url,
        })

    # Return sorted ascending by episode number
    episodes.sort(key=lambda e: e["episode_number"])
    return episodes


def scrape_animeav1_hash(serie_slug: str, episode_number: int) -> str | None:
    """Fetch an AnimeAV1 episode page and extract the Zilla player hash.

    GET https://animeav1.com/media/{serie_slug}/{episode_number}
    Sends Referer: https://animeav1.com/ as required by the Zilla player.

    Returns:
        The hex hash string (e.g. "a1b2c3d4...") or None if not found.
    """
    url = f"{ANIMEAV1_BASE}/media/{serie_slug}/{episode_number}"
    try:
        resp = _scraper.get(url, headers=_ZILLA_HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception:
        return None

    m = _ZILLA_HASH_RE.search(resp.text)
    return m.group(1) if m else None


def get_zilla_m3u8_url(hash_id: str) -> str:
    """Construct the Zilla m3u8 URL for a given hash.

    No network request is made — this is a pure URL builder.

    Args:
        hash_id: The hex hash extracted from the Zilla /play/{hash} embed.

    Returns:
        The full Zilla m3u8 URL string.
    """
    return f"https://player.zilla-networks.com/m3u8/{hash_id}"
