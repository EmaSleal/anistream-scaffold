import re
import cloudscraper
from config import CLOUDSCRAPER_BROWSER, ANIMEAV1_BASE

s = cloudscraper.create_scraper(browser=CLOUDSCRAPER_BROWSER)
r = s.get(f"{ANIMEAV1_BASE}/media/tsue-to-tsurugi-no-wistoria-season-2")

# Look for animeflv internal anime ID in JS variables
patterns = [
    r"var\s+anime_info\s*=\s*(\[.*?\]);",
    r'"id"\s*:\s*(\d+)',
    r"/uploads/animes/(?:covers|thumbs)/(\d+)/",
    r"screenshots/(\d+)/",
]

for pattern in patterns:
    m = re.search(pattern, r.text)
    if m:
        print(f"Pattern '{pattern[:40]}' → {m.group(1)[:80]}")
