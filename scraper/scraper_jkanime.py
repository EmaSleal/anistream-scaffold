import re
import cloudscraper
from bs4 import BeautifulSoup
from config import CLOUDSCRAPER_BROWSER

_scraper = cloudscraper.create_scraper(browser=CLOUDSCRAPER_BROWSER)

JKANIME_BASE = "https://jkanime.net"


def scrape_jkanime_m3u8(serie_slug: str, episode_number: int) -> str | None:
    """Fetch the jkanime episode page and extract the HLS m3u8 URL.

    Tries the 'umv' (Magi) player first — it exposes a direct <source> tag.
    Falls back to the 'um' (Desu) player which embeds the URL in commented JS.
    Returns the signed m3u8 URL or None if extraction fails.
    """
    episode_url = f"{JKANIME_BASE}/{serie_slug}/{episode_number}/"
    try:
        resp = _scraper.get(episode_url, timeout=20)
        resp.raise_for_status()
    except Exception:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # The page injects iframes via a JS array: video[N] = '<iframe ... src="URL">';
    player_urls: dict[int, str] = {}
    for script in soup.find_all("script"):
        text = script.string or ""
        for idx_str, iframe_html in re.findall(r"video\[(\d+)\]\s*=\s*'(<iframe[^']+)'", text):
            src_match = re.search(r'src="([^"]+)"', iframe_html)
            if src_match:
                player_urls[int(idx_str)] = src_match.group(1)

    if not player_urls:
        return None

    # index 1 = Magi (umv) — direct <source>; index 0 = Desu (um) — JS fallback
    for idx in [1, 0]:
        player_url = player_urls.get(idx)
        if player_url:
            m3u8 = _extract_m3u8_from_player(player_url, episode_url)
            if m3u8:
                return m3u8

    return None


def _extract_m3u8_from_player(player_url: str, referer: str) -> str | None:
    """Follow a jkplayer URL and extract the m3u8 source."""
    try:
        r = _scraper.get(player_url, headers={"Referer": referer}, timeout=20)
        r.raise_for_status()
    except Exception:
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    # Magi player: <source src="...m3u8...">
    source = soup.find("source", src=re.compile(r"\.m3u8"))
    if source:
        return source["src"]

    # Desu player: url: '...m3u8...' in JS (may be in a comment block)
    for script in soup.find_all("script"):
        m = re.search(r"url:\s*['\"]([^'\"]+\.m3u8[^'\"]*)['\"]", script.string or "")
        if m:
            return m.group(1)

    return None
