"""
scrapers/woocommerce.py — Generic WooCommerce listing scraper.

A single configurable class handles all five Phase-1 WooCommerce stores.
The entire behaviour is driven by StoreConfig: base URL, category-slug map,
CSS selectors, and pagination settings.

Public API:
    WooCommerceScraper
"""
from __future__ import annotations

import logging
from datetime import datetime

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, RawProduct, ScraperError

logger = logging.getLogger(__name__)


class WooCommerceScraper(BaseScraper):
    """Generic WooCommerce product-listing scraper.

    Reused by all five Phase-1 stores.  Configuration comes entirely from
    ``StoreConfig`` — this class contains no store-specific constants.

    Selectors used (from ``self.config.selectors``):
        product_card  — ``li.product``
        name          — ``h2.woocommerce-loop-product__title``
        price         — ``span.price .woocommerce-Price-amount bdi``
        link          — ``a.woocommerce-LoopProduct-link`` (href attribute)
        stock         — ``".button.disabled"`` or ``".out-of-stock"``
                        (presence on the card → out of stock)
    """

    # ------------------------------------------------------------------
    # Abstract interface implementation
    # ------------------------------------------------------------------

    def scrape(self, category: str) -> list[RawProduct]:
        """Fetch and parse all pages for *category*, returning RawProducts.

        Pagination stops when a page returns 0 product cards or the page
        number exceeds ``config.pagination["max_pages"]``.

        If *category* is not in ``config.category_map``, logs a WARNING and
        returns an empty list without making any HTTP request.

        If page 1 returns 0 products, falls back to a WooCommerce search URL
        (TASK-14).  If the search also yields 0 results, logs INFO and returns
        an empty list.
        """
        slug = self.config.category_map.get(category)
        if slug is None:
            logger.warning(
                "Category %r not mapped for store %s", category, self.store_id
            )
            return []

        max_pages: int = self.config.pagination.get("max_pages", 5)
        results: list[RawProduct] = []

        for page in range(1, max_pages + 1):
            url = self._build_category_url(slug, page)
            try:
                response = self._http_get(url)
            except ScraperError as exc:
                if exc.status_code == 404 and page > 1:
                    # No more pages — natural end of pagination
                    logger.info(
                        "Page %d returned 404 store=%s category=%r — end of pages",
                        page, self.store_id, category,
                    )
                    break
                raise  # real errors still propagate

            cards = self._parse_cards(response.text)

            if not cards:
                if page == 1:
                    # No products on page 1 → try search fallback (TASK-14)
                    results = self._search_fallback(category, slug)
                # Whether fallback succeeded or not, pagination ends here
                break

            results.extend(self._extract_products(cards, category))

        return results

    def supported_categories(self) -> list[str]:
        """Return the logical categories configured for this store."""
        return list(self.config.category_map.keys())

    # ------------------------------------------------------------------
    # URL helpers
    # ------------------------------------------------------------------

    def _build_category_url(self, slug: str, page: int) -> str:
        """Build a paginated URL.

        Handles three template styles:
        - ``{base}/?s={slug}&post_type=product&paged={page}`` — WoodMart search
        - ``{base}/product-category/{slug}/`` — standard WooCommerce category
        - Custom templates with ``{base}`` and ``{slug}`` placeholders
        """
        base = self.config.base_url.rstrip("/")
        template = self.config.url_template

        if "{page}" in template:
            # Search-based template — page is inlined, no suffix needed
            return (
                template
                .replace("{base}", base)
                .replace("{slug}", slug)
                .replace("{page}", str(page))
            )

        if template and "{slug}" in template:
            url = template.replace("{base}", base).replace("{slug}", slug).rstrip("/") + "/"
        else:
            url = f"{base}/product-category/{slug}/"

        if page > 1:
            url = f"{url}?page={page}"
        return url

    def _build_search_url(self, slug: str) -> str:
        """Build the WooCommerce search URL for a given slug/keyword."""
        base = self.config.base_url.rstrip("/")
        return f"{base}/?s={slug}&post_type=product"

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def _parse_cards(self, html: str) -> list:
        """Parse the HTML page and return a list of product card elements."""
        soup = BeautifulSoup(html, "lxml")
        card_selector = self.config.selectors.get("product_card", "li.product")
        return soup.select(card_selector)

    def _extract_products(
        self, cards: list, category: str
    ) -> list[RawProduct]:
        """Convert a list of BeautifulSoup card elements to RawProducts.

        Cards missing a name or price are logged as WARNINGs and skipped.
        """
        products: list[RawProduct] = []
        for card in cards:
            raw = self._parse_card(card, category)
            if raw is not None:
                products.append(raw)
        return products

    def _parse_card(self, card, category: str) -> RawProduct | None:
        """Extract a single RawProduct from a card element.

        Returns None (and logs a WARNING) if the name or price is missing.
        Supports two name extraction strategies:
        - ``name_attr`` + ``name_link``: read ``aria-label`` (WoodMart theme)
        - ``name``: CSS selector text content (standard WooCommerce)
        """
        selectors = self.config.selectors
        price_sel = selectors.get("price", "span.price")
        link_sel = selectors.get("link", "a.woocommerce-LoopProduct-link")

        # --- Name extraction ---
        raw_name: str | None = None
        if "name_attr" in selectors and "name_link" in selectors:
            # WoodMart: name is in the aria-label attribute of the product link
            link_tag = card.select_one(selectors["name_link"])
            if link_tag:
                raw_name = link_tag.get(selectors["name_attr"]) or link_tag.get_text(strip=True) or None
        if not raw_name:
            name_sel = selectors.get("name", "h2.woocommerce-loop-product__title")
            name_tag = card.select_one(name_sel)
            raw_name = name_tag.get_text(strip=True) if name_tag else None

        # --- Price extraction ---
        price_tag = card.select_one(price_sel)
        price_text = price_tag.get_text(strip=True) if price_tag else None

        if not raw_name or not price_text:
            logger.warning(
                "Skipping card — missing %s for store=%s category=%s",
                "name" if not raw_name else "price",
                self.store_id,
                category,
            )
            return None

        link_tag = card.select_one(link_sel)
        url = link_tag["href"] if link_tag and link_tag.get("href") else ""

        in_stock = self._is_in_stock(card)

        return RawProduct(
            store_id=self.store_id,
            raw_name=raw_name,
            price_str=price_text,
            url=url,
            in_stock=in_stock,
            category=category,
            scraped_at=datetime.utcnow().isoformat() + "Z",
        )

    def _is_in_stock(self, card) -> bool:
        """Return True if the product card indicates the item is in stock.

        Out-of-stock is signalled by the presence of either:
        - ``.button.disabled`` on the card, or
        - ``.out-of-stock`` class on the card itself or any descendant.
        """
        if card.select_one(".button.disabled"):
            return False
        # Check the card element itself for the out-of-stock class.
        card_classes = card.get("class", [])
        if "out-of-stock" in card_classes:
            return False
        if card.select_one(".out-of-stock"):
            return False
        return True

    # ------------------------------------------------------------------
    # Search fallback (TASK-14)
    # ------------------------------------------------------------------

    def _search_fallback(self, category: str, slug: str) -> list[RawProduct]:
        """Try a WooCommerce site-search URL when the category page is empty.

        Only one page is attempted.  Returns an empty list and logs INFO
        if the search also yields no results.
        """
        search_url = self._build_search_url(slug)
        logger.info(
            "Category page empty for store=%s category=%r — trying search fallback: %s",
            self.store_id, category, search_url,
        )

        try:
            response = self._http_get(search_url)
        except ScraperError as exc:
            logger.warning(
                "Search fallback failed store=%s category=%r: %s",
                self.store_id, category, exc,
            )
            return []

        cards = self._parse_cards(response.text)
        if not cards:
            logger.info(
                "Search fallback also returned 0 results store=%s category=%r",
                self.store_id, category,
            )
            return []

        return self._extract_products(cards, category)
