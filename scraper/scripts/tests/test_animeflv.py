"""
Test de viabilidad: extrae metadata y fuentes de video de un episodio de animeflv.
Requiere: pip install cloudscraper beautifulsoup4 lxml
"""
import re
import json
import cloudscraper
from bs4 import BeautifulSoup

URL = "https://www4.animeflv.net/ver/tsue-to-tsurugi-no-wistoria-season-2-8"

scraper = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "mobile": False}
)

print(f"Fetching: {URL}\n")
resp = scraper.get(URL, timeout=15)
print(f"Status: {resp.status_code}")

if resp.status_code != 200:
    print("Acceso bloqueado. Intentando con headers adicionales...")
    resp = scraper.get(URL, timeout=15, headers={
        "Referer": "https://www4.animeflv.net/",
        "Accept-Language": "es-ES,es;q=0.9",
    })
    print(f"Status retry: {resp.status_code}")

if resp.status_code != 200:
    print("No se pudo acceder a la página.")
    exit(1)

soup = BeautifulSoup(resp.text, "lxml")

# --- Metadata ---
title = soup.select_one("h1.Title")
synopsis = soup.select_one(".sinopsis p, .Description p")
print("\n=== METADATA ===")
print(f"Título:   {title.text.strip() if title else 'N/A'}")
print(f"Sinopsis: {synopsis.text.strip()[:120] if synopsis else 'N/A'}...")

# --- Video sources (var videos = {...}) ---
print("\n=== FUENTES DE VIDEO ===")
scripts = [s.string for s in soup.find_all("script") if s.string]
videos_data = None

for script in scripts:
    match = re.search(r"var\s+videos\s*=\s*(\{.*?\});", script, re.DOTALL)
    if match:
        try:
            videos_data = json.loads(match.group(1))
            break
        except json.JSONDecodeError:
            pass

if videos_data:
    for lang, servers in videos_data.items():
        print(f"\n  [{lang}] — {len(servers)} servidor(es):")
        for s in servers:
            print(f"    • {s.get('title', s.get('server', '?'))} → {s.get('code', '')[:80]}")
else:
    print("  No se encontró var videos = {...}")
    # Intentar encontrar cualquier dato de video en los scripts
    for script in scripts:
        if "source" in script.lower() or "player" in script.lower():
            print(f"\n  Script sospechoso (primeros 300 chars):\n  {script[:300]}")
            break
