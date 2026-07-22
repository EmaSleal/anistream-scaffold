"""AnimeAV1 scraper module.

Mirrors the structure of scraper_jkanime.py.
All page requests use cloudscraper to bypass Cloudflare.
Zilla player requests always include the required Referer/Origin headers.
"""

import logging
import re
from typing import Literal
import cloudscraper
from bs4 import BeautifulSoup
from config import CLOUDSCRAPER_BROWSER

logger = logging.getLogger(__name__)

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
    except Exception as exc:
        logger.warning("scraper_animeav1: HTTP error for slug=%r: %s", slug, exc)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    # Extract numeric anime_id for CDN thumbnail URLs.
    # Priority: data-id attr → JS "anime_id" → CDN URL already present in page.
    numeric_id = None
    data_id_tag = soup.find(attrs={"data-id": True})
    if data_id_tag:
        numeric_id = str(data_id_tag.get("data-id"))
    if not numeric_id:
        for script in soup.find_all("script"):
            text = script.string or ""
            m = re.search(r'"anime_id"\s*:\s*(\d+)', text)
            if m:
                numeric_id = m.group(1)
                break
    if not numeric_id:
        # Last resort: pick numeric_id from any CDN screenshot URL already in the HTML
        cdn_m = re.search(r'cdn\.animeav1\.com/screenshots/(\d+)/', resp.text)
        if cdn_m:
            numeric_id = cdn_m.group(1)

    episodes = []
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

        thumbnail_url = None
        if numeric_id:
            thumbnail_url = (
                f"https://cdn.animeav1.com/screenshots/{numeric_id}/{ep_num}.jpg"
            )

        # Prefer an actual img in the card; handle lazy-loaded src attributes.
        img = link.find("img")
        if img:
            src = img.get("src") or img.get("data-src") or img.get("data-lazy-src") or img.get("data-original")
            if src:
                thumbnail_url = src

        episodes.append({
            "episode_number": ep_num,
            "thumbnail_url": thumbnail_url,
        })

    episodes.sort(key=lambda e: e["episode_number"])
    if not episodes:
        logger.warning("scraper_animeav1: page loaded but 0 episodes found for slug=%r", slug)
    return episodes


def _detect_active_audio(soup: BeautifulSoup) -> str | None:
    """Return the audio type whose row contains the active (bg-main) button.

    AnimeAV1 marks the currently loaded source with a button styled bg-main.
    The Zilla player hash embedded in the page corresponds to that source.
    Returns None when neither row has an active button (indeterminate).
    """
    for audio, cls in [("sub", "ic-sub"), ("dub", "ic-dub")]:
        span = soup.find("span", class_=lambda c: c and cls in c.split())
        if not span:
            continue
        row = span.find_parent("div")
        if row and row.find("button", class_=lambda c: c and "bg-main" in c.split()):
            return audio
    return None


def scrape_animeav1_hash(
    serie_slug: str,
    episode_number: int,
    audio_type: Literal["sub", "dub"] = "sub",
) -> str | None:
    """Fetch an AnimeAV1 episode page and extract the Zilla player hash.

    GET https://animeav1.com/media/{serie_slug}/{episode_number}
    Sends Referer: https://animeav1.com/ as required by the Zilla player.

    Zilla hashes are not embedded inside the row divs — they sit elsewhere in
    the page HTML (typically a single iframe for the currently active source).
    _detect_active_audio() reads the bg-main button to identify which audio
    row is active, ensuring the page-level hash is only used when it matches
    the requested audio_type.

    When audio_type="sub":
        Tries the ic-sub row first. Falls back to the page hash only when SUB
        is the active source (or when the active source cannot be determined).

    When audio_type="dub":
        Tries the ic-dub row first. Falls back to the page hash only when DUB
        is the active source. Returns None if the ic-dub row is absent or if
        SUB is the active source — avoids returning a SUB hash for DUB.

    Returns:
        The hex hash string (e.g. "a1b2c3d4...") or None if not found.
    """
    url = f"{ANIMEAV1_BASE}/media/{serie_slug}/{episode_number}"
    try:
        resp = _scraper.get(url, headers=_ZILLA_HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    if audio_type == "dub":
        dub_span = soup.find("span", class_=lambda c: c and "ic-dub" in c.split())
        if not dub_span:
            return None
        dub_row = dub_span.find_parent("div")
        if not dub_row:
            return None
        m = re.search(r"zilla-networks\.com/play/([a-f0-9]+)", str(dub_row))
        if m:
            return m.group(1)
        # Hash not in the row div — use the page hash only when DUB is active.
        if _detect_active_audio(soup) == "dub":
            m = _ZILLA_HASH_RE.search(resp.text)
            return m.group(1) if m else None
        return None

    # audio_type == "sub"
    sub_span = soup.find("span", class_=lambda c: c and "ic-sub" in c.split())
    if sub_span:
        sub_row = sub_span.find_parent("div")
        if sub_row:
            m = re.search(r"zilla-networks\.com/play/([a-f0-9]+)", str(sub_row))
            if m:
                return m.group(1)

    # Page-level fallback — only when the active source is SUB (or indeterminate).
    # Avoids returning a DUB hash as SUB when the DUB row loads first.
    if _detect_active_audio(soup) != "dub":
        m = _ZILLA_HASH_RE.search(resp.text)
        return m.group(1) if m else None
    return None


def animeav1_has_dub(serie_slug: str, episode_number: int = 1) -> bool:
    """Check whether an AnimeAV1 series has a DUB audio track available.

    Fetches the episode page for episode_number (default 1) and returns True
    if a span.ic-dub element is present. Used during ingest to set
    series.audio_formats = ["sub","dub"] when applicable.

    Returns False on any network or parse error — never raises.
    """
    url = f"{ANIMEAV1_BASE}/media/{serie_slug}/{episode_number}"
    try:
        resp = _scraper.get(url, headers=_ZILLA_HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception:
        return False

    soup = BeautifulSoup(resp.text, "html.parser")
    return bool(soup.find("span", class_=lambda c: c and "ic-dub" in c.split()))


def get_zilla_m3u8_url(hash_id: str) -> str:
    """Construct the Zilla m3u8 URL for a given hash.

    No network request is made — this is a pure URL builder.

    Args:
        hash_id: The hex hash extracted from the Zilla /play/{hash} embed.

    Returns:
        The full Zilla m3u8 URL string.
    """
    return f"https://player.zilla-networks.com/m3u8/{hash_id}"
