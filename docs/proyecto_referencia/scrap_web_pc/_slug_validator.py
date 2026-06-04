"""
_slug_validator.py — One-shot slug validation script for TASK-15.

Validates every category slug in config.STORES against live HTTP responses.
Run with: python _slug_validator.py

NOT imported by the application.  Results are written to slug_validation_report.py.
"""
from __future__ import annotations

import time
import sys
import re
from urllib.parse import urljoin

import requests
import cloudscraper
from bs4 import BeautifulSoup

# --- bring project root onto sys.path so we can import config
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import STORES, HTTP_USER_AGENT

HEADERS = {
    "User-Agent": HTTP_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-CR,es;q=0.9,en;q=0.8",
}

TIMEOUT = 20
DELAY = 2.0   # seconds between requests per store


def make_session(requires_cloudscraper: bool):
    if requires_cloudscraper:
        return cloudscraper.create_scraper()
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def count_products(session, url: str) -> tuple[int, int]:
    """Return (status_code, product_count) for the given URL."""
    try:
        resp = session.get(url, timeout=TIMEOUT, allow_redirects=True)
        code = resp.status_code
        if code != 200:
            return code, 0
        soup = BeautifulSoup(resp.text, "lxml")
        products = soup.select("li.product")
        return 200, len(products)
    except Exception as exc:
        print(f"    ERROR fetching {url}: {exc}")
        return 0, 0


def discover_category_links(session, base_url: str) -> dict[str, str]:
    """Try to discover WooCommerce category slugs from /shop/ or /tienda/.

    Returns {slug: full_url} dict (slug is extracted from href path).
    """
    discovered: dict[str, str] = {}
    for path in ("/shop/", "/tienda/", "/categoria-producto/", "/"):
        url = base_url.rstrip("/") + path
        try:
            resp = session.get(url, timeout=TIMEOUT, allow_redirects=True)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "lxml")
            # WooCommerce category nav selectors
            links = (
                soup.select("ul.product-categories a")
                + soup.select(".widget_product_categories a")
                + soup.select("nav.woocommerce-breadcrumb a")
                + soup.select("a[href*='/product-category/']")
            )
            for a in links:
                href = a.get("href", "")
                m = re.search(r"/product-category/([^/?#]+)", href)
                if m:
                    slug = m.group(1).strip("/")
                    discovered[slug] = href
            if discovered:
                break
        except Exception as exc:
            print(f"    discovery error on {url}: {exc}")
            continue
    return discovered


def validate_store(store_id: str, store_config) -> dict:
    """Validate all slugs for one store. Returns per-category results dict."""
    print(f"\n{'='*60}")
    print(f"  Store: {store_id} ({store_config.base_url})")
    print(f"{'='*60}")

    session = make_session(store_config.requires_cloudscraper)
    results: dict[str, dict] = {}

    # First, discover available slugs
    print("  Discovering available category slugs...")
    discovered = discover_category_links(session, store_config.base_url)
    print(f"  Found {len(discovered)} discovered slugs: {list(discovered.keys())[:15]}")
    time.sleep(DELAY)

    for category, slug in store_config.category_map.items():
        base = store_config.base_url.rstrip("/")
        url = f"{base}/product-category/{slug}/"
        print(f"\n  [{category}] slug={slug!r}")
        print(f"    URL: {url}")

        status, count = count_products(session, url)
        print(f"    status={status}  products={count}")

        time.sleep(DELAY)

        entry = {
            "original_slug": slug,
            "validated_slug": slug,
            "url_tested": url,
            "status_code": status,
            "product_count": count,
            "valid": False,
            "note": "",
        }

        if status == 200 and count > 0:
            entry["valid"] = True
            entry["note"] = f"OK — {count} products"
            print(f"    VALID ({count} products)")

        elif status == 200 and count == 0:
            # Try search fallback
            search_url = f"{base}/?s={slug}&post_type=product"
            print(f"    0 products on category page — trying search: {search_url}")
            s_status, s_count = count_products(session, search_url)
            print(f"    search status={s_status}  products={s_count}")
            time.sleep(DELAY)

            if s_count > 0:
                entry["valid"] = True
                entry["note"] = f"slug page empty but search found {s_count} products — slug may be wrong"
                print(f"    search found {s_count} products")
            else:
                # Try to find the right slug from discovered
                best_match = _find_best_slug(slug, discovered)
                if best_match:
                    # Validate the best match
                    alt_url = f"{base}/product-category/{best_match}/"
                    _, alt_count = count_products(session, alt_url)
                    time.sleep(DELAY)
                    if alt_count > 0:
                        entry["validated_slug"] = best_match
                        entry["valid"] = True
                        entry["note"] = f"CORRECTED from {slug!r} to {best_match!r} — {alt_count} products"
                        print(f"    CORRECTED: {best_match!r} has {alt_count} products")
                    else:
                        entry["note"] = f"INVALID — 0 products; discovered={list(discovered.keys())[:10]}"
                        print(f"    INVALID — no products found anywhere for this category")
                else:
                    entry["note"] = f"INVALID — not available at this store"
                    print(f"    NOT AVAILABLE — no matching slug discovered")
        else:
            # 404 or error
            best_match = _find_best_slug(slug, discovered)
            if best_match:
                alt_url = f"{base}/product-category/{best_match}/"
                _, alt_count = count_products(session, alt_url)
                time.sleep(DELAY)
                if alt_count > 0:
                    entry["validated_slug"] = best_match
                    entry["valid"] = True
                    entry["note"] = f"CORRECTED from {slug!r} to {best_match!r} — {alt_count} products (original returned {status})"
                    print(f"    CORRECTED: {best_match!r} has {alt_count} products")
                else:
                    entry["note"] = f"INVALID — HTTP {status}; no alternative found"
                    print(f"    INVALID — HTTP {status}")
            else:
                entry["note"] = f"INVALID — HTTP {status}"
                print(f"    INVALID — HTTP {status}")

        results[category] = entry

    return results


def _find_best_slug(original: str, discovered: dict[str, str]) -> str | None:
    """Try to find a slug in discovered that looks similar to original."""
    if original in discovered:
        return original
    # Partial match: discovered slug contains key word from original
    parts = original.replace("-", " ").split()
    for d_slug in discovered:
        for part in parts:
            if len(part) > 3 and part in d_slug:
                return d_slug
    return None


def main():
    all_results: dict[str, dict] = {}
    for store_id, store_config in STORES.items():
        if not store_config.enabled:
            continue
        store_results = validate_store(store_id, store_config)
        all_results[store_id] = store_results

    # Print summary
    print("\n\n" + "="*70)
    print("SLUG VALIDATION SUMMARY")
    print("="*70)
    for store_id, categories in all_results.items():
        print(f"\n{store_id}:")
        for cat, info in categories.items():
            status_mark = "OK" if info["valid"] else "FAIL"
            changed = " **CHANGED**" if info["validated_slug"] != info["original_slug"] else ""
            print(f"  [{status_mark}] {cat}: {info['original_slug']!r} -> {info['validated_slug']!r}  {info['note']}{changed}")

    # Write the report file
    _write_report(all_results)
    return all_results


def _write_report(results: dict) -> None:
    lines = [
        '"""',
        "slug_validation_report.py — Auto-generated by _slug_validator.py",
        "",
        "Records the outcome of live slug validation for all Phase-1 stores.",
        "NOT imported by the application.",
        '"""',
        "",
        "SLUG_VALIDATION_REPORT: dict = {",
    ]
    for store_id, cats in results.items():
        lines.append(f"    {store_id!r}: {{")
        for cat, info in cats.items():
            lines.append(f"        {cat!r}: {{")
            for k, v in info.items():
                lines.append(f"            {k!r}: {v!r},")
            lines.append("        },")
        lines.append("    },")
    lines.append("}")
    lines.append("")

    report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "slug_validation_report.py")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\nReport written to: {report_path}")


if __name__ == "__main__":
    main()
