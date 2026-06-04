"""
Test scraping de página de catálogo de animeflv para obtener lista de episodios.
"""
import re
import json
import cloudscraper
from bs4 import BeautifulSoup

scraper = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "mobile": False}
)

URL = "https://www4.animeflv.net/anime/tsue-to-tsurugi-no-wistoria-season-2"

print(f"Fetching: {URL}")
resp = scraper.get(URL, timeout=15)
print(f"Status: {resp.status_code}\n")

soup = BeautifulSoup(resp.text, "lxml")

# --- Metadata ---
title   = soup.select_one("h1.Title, h2.Title")
synopsis = soup.select_one(".sinopsis p, .Description p, [itemprop='description']")
cover   = soup.select_one(".AnimeCover img, .cover img")
genres  = [a.text.strip() for a in soup.select(".Nvgnrs a, .genres a")]
rating  = soup.select_one(".fa-star + span, .Rnkng")

print("=== METADATA ===")
print(f"Título:   {title.text.strip() if title else 'N/A'}")
print(f"Sinopsis: {synopsis.text.strip()[:150] if synopsis else 'N/A'}...")
print(f"Cover:    {cover.get('src', 'N/A') if cover else 'N/A'}")
print(f"Géneros:  {genres}")
print(f"Rating:   {rating.text.strip() if rating else 'N/A'}")

# --- Lista de episodios ---
print("\n=== EPISODIOS ===")

# Método 1: JS variable con lista
for script in soup.find_all("script"):
    content = script.string or ""
    m = re.search(r"var\s+episodes\s*=\s*(\[.*?\]);", content, re.DOTALL)
    if m:
        eps = json.loads(m.group(1))
        print(f"var episodes encontrado: {len(eps)} episodios")
        print(f"Primeros 3: {eps[:3]}")
        print(f"Últimos 3:  {eps[-3:]}")
        break
else:
    # Método 2: lista en HTML
    ep_items = soup.select("ul.ListEpisodes li, .episode-list li")
    print(f"HTML list items: {len(ep_items)}")
    for item in ep_items[:3]:
        link = item.select_one("a")
        print(f"  {link.get('href', '')} — {link.text.strip()[:60] if link else ''}")
