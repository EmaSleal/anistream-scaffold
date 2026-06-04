"""Inspecciona el HTML interno de los product cards en cada tienda."""
import time
import requests
import cloudscraper
from bs4 import BeautifulSoup
from config import STORES, HTTP_USER_AGENT

HEADERS = {
    "User-Agent": HTTP_USER_AGENT,
    "Accept-Language": "es-CR,es;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def get_html(url, use_cloud=False):
    try:
        if use_cloud:
            s = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "windows", "mobile": False})
            r = s.get(url, timeout=15)
        else:
            r = requests.get(url, headers=HEADERS, timeout=12)
        return r.status_code, r.text
    except Exception as e:
        return 0, str(e)

BEST_PATHS = {
    "techzilla":    "/shop/",
    "crtechstore":  "/shop/",
    "igamingcr":    "/tienda/",
    "intelec":      "/",
    "extremetechcr": "/shop/",
}

for store_id, cfg in STORES.items():
    print(f"\n{'='*60}")
    print(f"  {cfg.store_name}")
    print(f"{'='*60}")
    path = BEST_PATHS.get(store_id, "/shop/")
    url = cfg.base_url + path
    status, html = get_html(url, cfg.requires_cloudscraper)

    if status != 200:
        print(f"  HTTP {status}")
        continue

    soup = BeautifulSoup(html, "lxml")

    # Try multiple card selectors
    for card_sel in ["li.product", "article.product", ".product-inner", ".product-item"]:
        cards = soup.select(card_sel)
        if not cards:
            continue
        print(f"  Card selector: '{card_sel}' -> {len(cards)} cards")
        card = cards[0]

        # Print tag tree of first card
        def print_tree(el, depth=0, max_depth=4):
            if depth > max_depth:
                return
            text = el.get_text(strip=True)[:50] if el.get_text(strip=True) else ""
            classes = " ".join(el.get("class", []))[:50]
            if text or classes:
                print(f"  {'  '*depth}<{el.name} class='{classes}'> {repr(text[:40]) if text else ''}")
            for child in el.children:
                if hasattr(child, "name") and child.name:
                    print_tree(child, depth+1, max_depth)

        print(f"\n  First card structure:")
        print_tree(card, max_depth=5)
        break

    # Also check category links
    cat_links = []
    for a in soup.find_all("a", href=True):
        if "product-category" in a.get("href", ""):
            text = a.get_text(strip=True)
            if text:
                slug = a["href"].rstrip("/").split("/")[-1]
                cat_links.append((slug, text[:40]))
    if cat_links:
        seen = set()
        print(f"\n  Category URLs in HTML:")
        for slug, text in cat_links:
            if slug not in seen and slug:
                print(f"    {slug:<40} {text}")
                seen.add(slug)

    time.sleep(1)

print("\nDONE")
