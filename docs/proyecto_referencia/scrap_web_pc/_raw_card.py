"""Imprime HTML raw del primer product card por tienda."""
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

PATHS = {
    "techzilla":    "/shop/",
    "crtechstore":  "/shop/",
    "igamingcr":    "/tienda/",
    "intelec":      "/",
    "extremetechcr": "/shop/",
}

def get(url, use_cloud=False):
    try:
        if use_cloud:
            s = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "windows", "mobile": False})
            r = s.get(url, timeout=15)
        else:
            r = requests.get(url, headers=HEADERS, timeout=12)
        return r.status_code, r.text
    except Exception as e:
        return 0, str(e)

for store_id, cfg in STORES.items():
    print(f"\n{'='*60}")
    print(f"  {cfg.store_name}")
    print(f"{'='*60}")
    path = PATHS[store_id]
    status, html = get(cfg.base_url + path, cfg.requires_cloudscraper)
    if status != 200:
        print(f"  HTTP {status}")
        continue

    soup = BeautifulSoup(html, "lxml")

    # Try common card selectors
    card = None
    for sel in ["li.product", "article.product", ".product-item"]:
        cards = soup.select(sel)
        if cards:
            card = cards[0]
            print(f"  Selector: '{sel}' ({len(cards)} total)")
            break

    if card:
        raw = str(card)[:1500]
        print(raw)
    else:
        # Look for any element containing a price
        price_parents = []
        for span in soup.select("span.woocommerce-Price-amount"):
            # Walk up to find product container
            el = span
            for _ in range(6):
                el = el.parent
                if el.name in ["li", "article", "div"] and any(c in el.get("class", []) for c in ["product", "product-item", "product-inner"]):
                    price_parents.append(el)
                    break
        if price_parents:
            print(f"  Found via price walk-up: {price_parents[0].name} class={price_parents[0].get('class')}")
            print(str(price_parents[0])[:1500])
        else:
            print("  No product card found in static HTML.")
    time.sleep(1)
