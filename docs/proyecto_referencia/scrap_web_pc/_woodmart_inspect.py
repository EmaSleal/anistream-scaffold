"""Extrae selectores reales del tema WoodMart y categorías disponibles."""
import time, re
import requests
from bs4 import BeautifulSoup
from config import STORES, HTTP_USER_AGENT

HEADERS = {
    "User-Agent": HTTP_USER_AGENT,
    "Accept-Language": "es-CR,es;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

PATHS = {
    "techzilla":   "/shop/",
    "crtechstore": "/shop/",
    "intelec":     "/",
}

for store_id in ["techzilla", "crtechstore", "intelec"]:
    cfg = STORES[store_id]
    path = PATHS[store_id]
    print(f"\n{'='*60}")
    print(f"  {cfg.store_name}")
    print(f"{'='*60}")

    r = requests.get(cfg.base_url + path, headers=HEADERS, timeout=12)
    soup = BeautifulSoup(r.text, "lxml")

    cards = soup.select("div.wd-product")
    print(f"  div.wd-product cards: {len(cards)}")

    if cards:
        card = cards[0]
        # Name from aria-label
        link = card.select_one("a.wd-product-img-link, a.product-image-link")
        name = link["aria-label"] if link and link.get("aria-label") else "NOT FOUND"
        href = link["href"] if link else "N/A"
        print(f"  Name (aria-label): {name[:60]}")
        print(f"  URL: {href}")

        # Price
        price_el = card.select_one("span.woocommerce-Price-amount bdi, .price bdi, .woocommerce-Price-amount")
        if price_el:
            print(f"  Price selector: span.woocommerce-Price-amount bdi -> '{price_el.get_text(strip=True)}'")
        else:
            # Try .price
            price_block = card.select_one(".price")
            if price_block:
                print(f"  .price block: '{price_block.get_text(strip=True)[:50]}'")

        # In-stock
        oos = card.select_one(".out-of-stock, .outofstock, .stock")
        print(f"  Out-of-stock el: {oos}")

        # Categories from class names
        all_cats = set()
        for c in cards:
            classes = c.get("class", [])
            for cls in classes:
                if cls.startswith("product_cat-"):
                    all_cats.add(cls.replace("product_cat-", ""))

        print(f"\n  Available product_cat slugs ({len(all_cats)}):")
        for cat in sorted(all_cats):
            print(f"    {cat}")

    # Also extract from nav menu
    cat_links = [(a["href"].rstrip("/").split("/")[-1], a.get_text(strip=True))
                 for a in soup.find_all("a", href=True)
                 if "product-category" in a.get("href","") and a.get_text(strip=True)]
    if cat_links:
        seen = set()
        print(f"\n  Nav category links:")
        for slug, text in cat_links:
            if slug not in seen:
                print(f"    {slug:<40} {text[:40]}")
                seen.add(slug)

    time.sleep(1)
