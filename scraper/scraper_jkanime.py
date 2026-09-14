import re
from urllib.parse import quote
import cloudscraper
from bs4 import BeautifulSoup
from config import CLOUDSCRAPER_BROWSER
from fetcher import _extract_base_title

_scraper = cloudscraper.create_scraper(browser=CLOUDSCRAPER_BROWSER)

JKANIME_BASE = "https://jkanime.net"


def search_jkanime(query: str, limit: int = 10) -> list[dict]:
    """Search the jkanime.net catalog and return matching series.

    GET https://jkanime.net/buscar/{query}
    Parses .anime__item cards and extracts slug, title, and thumbnail_url.

    Returns:
        list of { title, slug, jkanime_url, thumbnail_url }
        Empty list on any error or no results.
    """
    query = query.strip()
    if not query:
        return []

    try:
        resp = _scraper.get(f"{JKANIME_BASE}/buscar/{quote(query, safe=':')}", timeout=20)
        resp.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []

    for item in soup.find_all("div", class_="anime__item"):
        link = item.find("a", href=True)
        if not link:
            continue
        slug = link["href"].rstrip("/").rsplit("/", 1)[-1]
        if not slug:
            continue

        title_tag = item.select_one(".anime__item__text h5 a")
        title = title_tag.get_text(strip=True) if title_tag else slug

        pic = item.find("div", class_="anime__item__pic")
        thumbnail_url = pic.get("data-setbg") if pic else None

        results.append({
            "title": title,
            "slug": slug,
            "jkanime_url": f"{JKANIME_BASE}/{slug}/",
            "thumbnail_url": thumbnail_url,
        })
        if len(results) >= limit:
            break

    return results


# Minimum score (see _score_jkanime_item) required for select_best_jkanime_match
# to accept a candidate. Mirrors scraper_animeav1's floor — below this, none of
# the titles compared meaningfully overlap, so guessing anyway risks assigning
# the wrong season's slug rather than finding the right one.
_MIN_JKANIME_SCORE = 12


def _score_jkanime_item(item: dict, title: str, base: str) -> int:
    """Score a jkanime search result by how closely its own title matches ours.

    Mirrors scraper_animeav1._score_animeav1_item: exact-title equality is
    weighted far above mere substring containment, since multi-season
    franchises otherwise all score similarly on the shared base title alone.
    """
    candidate = (item.get("title") or "").strip().lower()
    if not candidate:
        return 0
    orig_lower = title.strip().lower()
    base_lower = base.strip().lower()

    if candidate == orig_lower:
        return 30
    if candidate == base_lower:
        return 20
    if orig_lower in candidate or candidate in orig_lower:
        return 12
    if base_lower in candidate or candidate in base_lower:
        return 6
    return 0


def select_best_jkanime_match(
    results: list[dict], title: str, alt_titles: list[str] | None = None
) -> dict | None:
    """Pick the jkanime search result whose own title best matches ours.

    Same rationale as scraper_animeav1.select_best_animeav1_match: jkanime's
    search returns multiple candidates with no ranking guarantee, so blindly
    taking results[0] risks assigning the wrong season's slug.
    """
    if not results:
        return None

    base = _extract_base_title(title)
    scored = [(r, _score_jkanime_item(r, title, base)) for r in results]

    for alt in (alt_titles or []):
        if not alt:
            continue
        alt_base = _extract_base_title(alt)
        scored.extend((r, _score_jkanime_item(r, alt, alt_base)) for r in results)

    best_item, best_score = max(scored, key=lambda pair: pair[1])
    if best_score < _MIN_JKANIME_SCORE:
        return None
    return best_item


def find_best_jkanime_match(title: str, alt_titles: list[str] | None = None) -> dict | None:
    """Search jkanime for the best-matching series, retrying with alt titles.

    Mirrors scraper_animeav1.find_best_animeav1_match's retry strategy: try
    the primary title first, then each alt title, always scoring against the
    *original* title/alt_titles so the final pick is judged consistently
    regardless of which query surfaced it.
    """
    match = select_best_jkanime_match(search_jkanime(title), title, alt_titles=alt_titles)
    if match:
        return match

    for alt in (alt_titles or []):
        if not alt or alt == title:
            continue
        match = select_best_jkanime_match(search_jkanime(alt), title, alt_titles=alt_titles)
        if match:
            return match

    return None


def fetch_jkanime_series_info(slug: str) -> dict | None:
    """Fetch episode count and airing status from a jkanime series page.

    GET https://jkanime.net/{slug}/
    Parses the info sidebar list items for "Episodios: N" and "Estado: ...".

    Returns {"episode_count": int | None, "status": str | None}, or None on
    any error (fail-open — caller falls back to metadata-only episodes).
    """
    try:
        resp = _scraper.get(f"{JKANIME_BASE}/{slug}/", timeout=20)
        resp.raise_for_status()
    except Exception:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    episode_count = None
    status = None

    for li in soup.find_all("li"):
        text = li.get_text(" ", strip=True)
        low = text.lower()
        if low.startswith("episodios"):
            m = re.search(r"(\d+)", text)
            if m:
                episode_count = int(m.group(1))
        elif low.startswith("estado") and ":" in text:
            status = text.split(":", 1)[-1].strip() or None

    if episode_count is None and status is None:
        return None
    return {"episode_count": episode_count, "status": status}


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
