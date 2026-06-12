from scraper_animeflv import _scraper
from config import ANIMEFLV_BASE
from bs4 import BeautifulSoup

slug = "jujutsu-kaisen-0-movie"
url = f"{ANIMEFLV_BASE}/anime/{slug}"

resp = _scraper.get(url, timeout=15)
resp.raise_for_status()

soup = BeautifulSoup(resp.text, "html.parser")

# Buscar cualquier sección que contenga "Secuela", "Precuela", "Historia paralela", "OVA"
for tag in soup.find_all(True):
    text = tag.get_text(separator=" ", strip=True)
    if any(k in text for k in ["Secuela", "Precuela", "Historia paralela", "OVA"]):
        if len(text) < 800:
            print("=== TAG:", tag.name, "| CLASS:", tag.get("class"), "===")
            print(tag)
            print()
