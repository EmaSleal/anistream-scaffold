"""Script temporal para validar slugs de categorías en cada tienda."""
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

def count_products(html):
    soup = BeautifulSoup(html, "lxml")
    return len(soup.select("li.product"))

def get_available_categories(base_url, use_cloud=False):
    """Fetch category links from shop page."""
    for path in ["/shop/", "/tienda/", "/"]:
        status, html = get_html(base_url + path, use_cloud)
        if status == 200:
            soup = BeautifulSoup(html, "lxml")
            links = soup.select("ul.product-categories a, .widget_product_categories a, nav.woocommerce-breadcrumb a")
            hrefs = [a.get("href", "") for a in links if "product-category" in a.get("href", "")]
            slugs = [h.rstrip("/").split("/")[-1] for h in hrefs if h]
            if slugs:
                return slugs
    return []

results = {}

for store_id, cfg in STORES.items():
    print(f"\n{'='*55}")
    print(f"  {cfg.store_name} ({cfg.base_url})")
    print(f"{'='*55}")
    store_results = {}
    use_cloud = cfg.requires_cloudscraper

    for cat, slug in cfg.category_map.items():
        url = f"{cfg.base_url}/product-category/{slug}/"
        status, html = get_html(url, use_cloud)
        count = count_products(html) if status == 200 else 0

        if count == 0 and status == 200:
            # try search fallback
            search_url = f"{cfg.base_url}/?s={slug}&post_type=product"
            s2, h2 = get_html(search_url, use_cloud)
            count_s = count_products(h2) if s2 == 200 else 0
            verdict = f"CATEGORY_EMPTY slug={slug} | search={count_s} results"
        elif status == 404 or status == 0:
            verdict = f"404/ERROR slug={slug}"
            count = -1
        else:
            verdict = f"OK ({count} products)"

        icon = "OK" if count > 0 else ("WARN" if count == 0 else "ERR")
        print(f"  [{icon:4}] {cat:<22} slug={slug:<25} {verdict}")
        store_results[cat] = {"slug": slug, "status": status, "count": count}
        time.sleep(0.8)

    results[store_id] = store_results

print("\n\nDONE")
