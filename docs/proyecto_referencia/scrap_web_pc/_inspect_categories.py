"""Inspecciona la estructura real de categorías de cada tienda."""
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

def extract_category_links(html, base_url):
    soup = BeautifulSoup(html, "lxml")
    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "product-category" in href or "product_cat" in href:
            if base_url.replace("https://", "").replace("www.", "") in href or href.startswith("/"):
                slug = href.rstrip("/").split("/")[-1]
                text = a.get_text(strip=True)
                links.add((slug, text[:40], href))
    return sorted(links)

def count_products(html):
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select("li.product")
    return len(cards), [c.select_one("h2, h3") and c.select_one("h2, h3").get_text(strip=True)[:40] for c in cards[:3]]

PROBE_PATHS = ["/", "/shop/", "/tienda/", "/productos/", "/categoria-producto/"]

for store_id, cfg in STORES.items():
    print(f"\n{'='*60}")
    print(f"  {cfg.store_name}")
    print(f"{'='*60}")
    use_cloud = cfg.requires_cloudscraper

    # Find homepage with most category links
    best_html = ""
    for path in PROBE_PATHS:
        url = cfg.base_url + path
        status, html = get_html(url, use_cloud)
        if status == 200:
            cats = extract_category_links(html, cfg.base_url)
            if cats:
                print(f"  Found {len(cats)} category links at {path}")
                for slug, text, href in cats[:25]:
                    print(f"    slug={slug:<35} text={text}")
                best_html = html
                break
        time.sleep(0.5)

    # Also try a direct product listing page to check selectors
    if best_html:
        count, samples = count_products(best_html)
        print(f"\n  Products on homepage: {count}")
        if samples:
            print(f"  Sample names: {[s for s in samples if s][:3]}")

    time.sleep(1)

print("\nDONE")
