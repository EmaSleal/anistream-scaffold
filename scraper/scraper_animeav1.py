import re
import cloudscraper
from config import CLOUDSCRAPER_BROWSER

_scraper = cloudscraper.create_scraper(browser=CLOUDSCRAPER_BROWSER)

ANIMEAV1_BASE = "https://animeav1.com"
ZILLA_M3U8_BASE = "https://player.zilla-networks.com/m3u8"


def scrape_animeav1_hash(serie_slug: str, episode_number: int) -> str | None:
    """Fetch the animeav1 episode page and extract the zilla-networks player hash.

    Returns the hex hash string, or None if not found.
    """
    url = f"{ANIMEAV1_BASE}/media/{serie_slug}/{episode_number}"
    try:
        resp = _scraper.get(url, timeout=15)
        resp.raise_for_status()
    except Exception:
        return None

    m = re.search(
        r'src="https://player\.zilla-networks\.com/play/([a-f0-9]+)"',
        resp.text,
    )
    return m.group(1) if m else None


def get_zilla_m3u8_url(hash_id: str) -> str:
    """Build the HLS stream URL for a given zilla-networks hash."""
    return f"{ZILLA_M3U8_BASE}/{hash_id}"
