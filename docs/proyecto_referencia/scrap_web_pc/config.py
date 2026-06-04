"""
config.py — Declarative store and application configuration.

All five Phase-1 WooCommerce stores are defined here.
Phase-2 stores (extremeoutlet, adntienda) are commented out at the bottom.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Application-level constants
# ---------------------------------------------------------------------------

CATEGORIES: list[str] = [
    "CPUs",
    "GPUs",
    "Placas madre",
    "RAM",
    "Disipadores",
    "Almacenamiento",
    "Fuentes de poder",
    "Cases",
    "Monitores",
]

FUZZY_THRESHOLD: int = 88

DB_PATH: str = os.environ.get("DB_PATH", "data/data.db")

SCHEDULE_CRON: str = os.environ.get("SCHEDULE_CRON", "0 3 * * *")

HTTP_USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

OLLAMA_URL: str = os.environ.get("OLLAMA_URL", "http://localhost:11434")
# Run `ollama pull phi4-mini` before first use.
# Override with OLLAMA_MODEL env var to switch models.
OLLAMA_MODEL: str = os.environ.get("OLLAMA_MODEL", "phi4-mini:latest")
OLLAMA_TIMEOUT: float = float(os.environ.get("OLLAMA_TIMEOUT", "30"))


# ---------------------------------------------------------------------------
# StoreConfig dataclass
# ---------------------------------------------------------------------------

@dataclass
class StoreConfig:
    store_id: str
    store_name: str
    base_url: str
    scraper_class: str                  # dotted import path; resolved at boot
    category_map: dict[str, str]        # logical category -> URL slug/keyword
    # URL template for category pages. Use "{base}/?s={slug}&post_type=product"
    # for WoodMart-theme stores where category pages are JS-rendered.
    url_template: str = "{base}/product-category/{slug}/"
    requires_cloudscraper: bool = False
    delay_seconds: float = 1.5
    enabled: bool = True
    selectors: dict = field(
        default_factory=lambda: {
            "product_card": "li.product",
            "name": "h2.woocommerce-loop-product__title",
            "price": "span.price",
            "link": "a.woocommerce-LoopProduct-link",
            "stock": ".out-of-stock",
        }
    )
    pagination: dict = field(
        default_factory=lambda: {
            "style": "page_path",       # "page_path" | "page_param" | "search_paged"
            "max_pages": 5,
        }
    )


# ---------------------------------------------------------------------------
# Phase-1 store registry
# ---------------------------------------------------------------------------

STORES: dict[str, StoreConfig] = {
    # ------------------------------------------------------------------
    # Techzilla — WATER COOLING SPECIALTY store (EKWB, Alphacool).
    # Does NOT stock CPUs/GPUs/RAM/Cases/PSUs/Monitors.
    # Validated 2026-05-27: only water-cooling categories present.
    # Disabled in Phase-1; replace with a general PC component store in Phase-2.
    # ------------------------------------------------------------------
    "techzilla": StoreConfig(
        store_id="techzilla",
        store_name="Techzilla",
        base_url="https://techzilla.cr",
        scraper_class="scrapers.woocommerce.WooCommerceScraper",
        requires_cloudscraper=False,
        delay_seconds=1.5,
        enabled=False,  # water-cooling-only; no standard PC components available
        category_map={
            # All standard PC categories NOT AVAILABLE at this store.
            # Real categories: kits-de-enfriamiento, componentes-wc,
            #                  herramientas-custom-water-cooling, otras-categorias
            "CPUs":             "procesadores",             # not available
            "GPUs":             "tarjetas-de-video",        # not available
            "Placas madre":     "tarjetas-madre",           # not available
            "RAM":              "memorias-ram",             # not available
            "Disipadores":      "kits-de-enfriamiento",     # WC kits only, not CPU/case coolers
            "Almacenamiento":   "almacenamiento",           # not available
            "Fuentes de poder": "fuentes-de-poder",         # not available
            "Cases":            "cases",                    # not available
            "Monitores":        "monitores",                # not available
        },
    ),

    # ------------------------------------------------------------------
    # CRTechStore — WoodMart theme. Category pages are JS-rendered.
    # Scraping strategy: WooCommerce search (?s=keyword&post_type=product).
    # Validated 2026-05-28: search returns WoodMart div.wd-product cards.
    # url_template uses search pattern; category_map holds search keywords.
    # ------------------------------------------------------------------
    "crtechstore": StoreConfig(
        store_id="crtechstore",
        store_name="CRTechStore",
        base_url="https://crtechstore.com",
        scraper_class="scrapers.woocommerce.WooCommerceScraper",
        requires_cloudscraper=False,
        delay_seconds=1.5,
        url_template="{base}/?s={slug}&post_type=product&paged={page}",
        selectors={
            "product_card": "div.wd-product",
            "name_attr":    "aria-label",           # name from aria-label on product link
            "name_link":    "a.wd-product-img-link, a.product-image-link",
            "price":        "span.woocommerce-Price-amount bdi",
            "link":         "a.wd-product-img-link, a.product-image-link",
            "stock":        ".button.disabled, .out-of-stock",
        },
        pagination={"style": "search_paged", "max_pages": 5},
        category_map={
            "CPUs":             "procesador",
            "GPUs":             "tarjeta de video",
            "Placas madre":     "placa madre",
            "RAM":              "memoria ram",
            "Disipadores":      "disipador",
            "Almacenamiento":   "disco ssd",
            "Fuentes de poder": "fuente de poder",
            "Cases":            "case gabinete",
            "Monitores":        "monitor",
        },
    ),

    # ------------------------------------------------------------------
    # iGaming CR — fully JS-rendered (Flatsome theme). li.product cards
    # exist in HTML but are empty — content requires JavaScript execution.
    # Disabled in Phase-1; Phase-2 requires Playwright.
    # ------------------------------------------------------------------
    "igamingcr": StoreConfig(
        store_id="igamingcr",
        store_name="iGaming CR",
        base_url="https://igamingcr.com",
        scraper_class="scrapers.woocommerce.WooCommerceScraper",
        requires_cloudscraper=False,
        delay_seconds=1.5,
        enabled=False,
        category_map={
            "CPUs": "procesador", "GPUs": "tarjeta de video",
            "Placas madre": "placa madre", "RAM": "memoria ram",
            "Disipadores": "disipador", "Almacenamiento": "disco ssd",
            "Fuentes de poder": "fuente de poder", "Cases": "case",
            "Monitores": "monitor",
        },
    ),

    # ------------------------------------------------------------------
    # Intelec — WoodMart theme. Category pages are JS-rendered (0 cards).
    # Scraping strategy: WooCommerce search (?s=keyword&post_type=product).
    # Validated 2026-05-28: search "procesador" → 20 CPU cards, works correctly.
    # url_template uses search pattern; category_map holds search keywords.
    # ------------------------------------------------------------------
    "intelec": StoreConfig(
        store_id="intelec",
        store_name="Intelec",
        base_url="https://www.intelec.co.cr",
        scraper_class="scrapers.woocommerce.WooCommerceScraper",
        requires_cloudscraper=False,
        delay_seconds=1.5,
        url_template="{base}/?s={slug}&post_type=product&paged={page}",
        selectors={
            "product_card": "div.wd-product",
            "name_attr":    "aria-label",
            "name_link":    "a.wd-product-img-link, a.product-image-link",
            "price":        "span.woocommerce-Price-amount bdi",
            "link":         "a.wd-product-img-link, a.product-image-link",
            "stock":        ".button.disabled, .out-of-stock",
        },
        pagination={"style": "search_paged", "max_pages": 5},
        category_map={
            "CPUs":             "procesador",
            "GPUs":             "tarjeta de video",
            "Placas madre":     "placa madre",
            "RAM":              "memoria ram",
            "Disipadores":      "disipador enfriamiento",
            "Almacenamiento":   "disco ssd almacenamiento",
            "Fuentes de poder": "fuente de poder",
            "Cases":            "case gabinete",
            "Monitores":        "monitor",
        },
    ),

    # ------------------------------------------------------------------
    # ExtremeTech CR — JS-rendered SPA; cloudscraper is insufficient.
    # Static HTML body is nearly empty (no product or nav content visible).
    # Validated 2026-05-27: cannot be scraped with requests/cloudscraper alone.
    # Phase-2: requires headless browser (Playwright).
    # Disabled in Phase-1 (enabled=False).
    # ------------------------------------------------------------------
    "extremetechcr": StoreConfig(
        store_id="extremetechcr",
        store_name="ExtremeTech CR",
        base_url="https://extremetechcr.com",
        scraper_class="scrapers.woocommerce.WooCommerceScraper",
        requires_cloudscraper=True,
        delay_seconds=2.5,
        enabled=False,  # Phase-2: requires Playwright for JS rendering
        category_map={
            # URL slugs confirmed where not 404; content requires JS execution
            "CPUs":             "procesadores",     # URL 200, content JS-rendered
            "GPUs":             "tarjetas-graficas",# URL 200 (403 on one attempt), JS-rendered
            "Placas madre":     "motherboards",     # URL 404 — correct slug unknown
            "RAM":              "memorias",         # URL 404 — correct slug unknown
            "Disipadores":      "cooling",          # URL 404 — correct slug unknown
            "Almacenamiento":   "almacenamiento",   # URL 200, content JS-rendered
            "Fuentes de poder": "fuentes-poder",    # URL 404 — correct slug unknown
            "Cases":            "cases",            # URL 404 — correct slug unknown
            "Monitores":        "monitores",        # URL 200, content JS-rendered
        },
    ),

    # ------------------------------------------------------------------
    # Phase-2 stores (deferred — custom scrapers not yet built)
    # ------------------------------------------------------------------
    # "extremeoutlet": StoreConfig(
    #     store_id="extremeoutlet",
    #     store_name="Extreme Outlet CR",
    #     base_url="https://extremeoutletcr.com",
    #     scraper_class="scrapers.extreme_outlet.ExtremeOutletScraper",
    #     requires_cloudscraper=False,
    #     delay_seconds=1.5,
    #     enabled=False,
    #     category_map={},
    # ),
    # "adntienda": StoreConfig(
    #     store_id="adntienda",
    #     store_name="ADN Tienda",
    #     base_url="https://adntienda.com",
    #     scraper_class="scrapers.adntienda.AdnTiendaScraper",
    #     requires_cloudscraper=False,
    #     delay_seconds=1.5,
    #     enabled=False,
    #     category_map={},
    # ),
}
