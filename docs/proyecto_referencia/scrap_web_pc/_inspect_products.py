"""Inspecciona selectores de productos reales en cada tienda."""
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

PROBE_PATHS = ["/shop/", "/tienda/", "/", "/productos/", "/shop/?paged=1"]

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

def analyze_products(html, label):
    soup = BeautifulSoup(html, "lxml")
    selectors = [
        ("li.product", "h2.woocommerce-loop-product__title", "span.price"),
        ("li.product", "h3", "span.price"),
        (".product-item", ".product-title", ".price"),
        ("article.product", "h2", ".price"),
        (".woocommerce-loop-product", "h2", ".price"),
        ("ul.products > li", "h2", "span.price"),
    ]
    for card_sel, name_sel, price_sel in selectors:
        cards = soup.select(card_sel)
        if cards:
            names = [c.select_one(name_sel) for c in cards[:3] if c.select_one(name_sel)]
            prices = [c.select_one(price_sel) for c in cards[:3] if c.select_one(price_sel)]
            print(f"  [{label}] FOUND {len(cards)} cards with selector '{card_sel}'")
            print(f"    Name selector '{name_sel}': {[n.get_text(strip=True)[:40] for n in names]}")
            print(f"    Price selector '{price_sel}': {[p.get_text(strip=True)[:30] for p in prices]}")
            return True

    # Deep scan - look for any element with price-like content
    price_els = soup.find_all(string=lambda t: t and "₡" in t)
    if price_els:
        print(f"  [{label}] Price symbol found in {len(price_els)} elements:")
        for el in price_els[:5]:
            parent = el.parent
            print(f"    tag=<{parent.name}> class={parent.get('class')} text='{str(el).strip()[:50]}'")
    else:
        print(f"  [{label}] No product cards or prices found (JS-rendered?)")
    return False

for store_id, cfg in STORES.items():
    print(f"\n{'='*60}")
    print(f"  {cfg.store_name} ({cfg.base_url})")
    print(f"{'='*60}")
    use_cloud = cfg.requires_cloudscraper
    found = False

    for path in PROBE_PATHS:
        url = cfg.base_url + path
        status, html = get_html(url, use_cloud)
        if status == 200 and len(html) > 5000:
            found = analyze_products(html, path)
            if found:
                # Also check what category URLs exist in the HTML
                soup = BeautifulSoup(html, "lxml")
                cat_links = [(a["href"], a.get_text(strip=True)) for a in soup.find_all("a", href=True)
                             if "product-category" in a.get("href", "") and a.get_text(strip=True)]
                if cat_links:
                    print(f"  Category links found:")
                    seen = set()
                    for href, text in cat_links:
                        slug = href.rstrip("/").split("/")[-1]
                        if slug not in seen:
                            print(f"    {slug:<40} {text[:35]}")
                            seen.add(slug)
                break
        time.sleep(0.5)

    if not found:
        print(f"  >> No products found in HTML — likely JS-rendered")
    time.sleep(1)

print("\nDONE")
