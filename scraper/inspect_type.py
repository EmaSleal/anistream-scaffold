from scraper_animeflv import _scraper
from config import ANIMEFLV_BASE
from bs4 import BeautifulSoup

slug = "jujutsu-kaisen-0-movie"
url = f"{ANIMEFLV_BASE}/anime/{slug}"

resp = _scraper.get(url, timeout=15)
resp.raise_for_status()

soup = BeautifulSoup(resp.text, "html.parser")

# Look for type indicator (Película, TV, OVA, etc.)
for tag in soup.find_all(True):
    text = tag.get_text(strip=True)
    if any(k in text for k in ["Película", "Pelicula", "Movie", "TV", "OVA", "Especial", "Type", "Tipo"]):
        if tag.name in ("span", "li", "p", "a", "dt", "dd") and len(text) < 80:
            print(f"TAG: {tag.name} | CLASS: {tag.get('class')} | TEXT: {text}")
            print(f"  HTML: {tag}")
            print()

# Also dump anime_info var
import re
m = re.search(r'var\s+anime_info\s*=\s*(\[.*?\]);', resp.text, re.DOTALL)
if m:
    print("anime_info:", m.group(1)[:300])
