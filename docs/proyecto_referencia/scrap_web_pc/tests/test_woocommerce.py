"""
tests/test_woocommerce.py — Unit tests for scrapers/woocommerce.py

Covers:
    TASK-26:
      1. Happy path — 3 product cards parsed correctly
      2. Empty second page stops pagination
      3. HTTP error propagates as ScraperError
      4. Card with missing price is skipped, others returned
      5. Unmapped category returns [] without any HTTP call
      6. Category page empty → search fallback tried

No real HTTP calls are made.  All network I/O is intercepted by
monkeypatching WooCommerceScraper._http_get.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from scrapers.base import RawProduct, ScraperError
from scrapers.woocommerce import WooCommerceScraper


# ---------------------------------------------------------------------------
# HTML fixture helpers
# ---------------------------------------------------------------------------

def _card(name: str, price: str, href: str = "https://example.com/prod",
          out_of_stock: bool = False) -> str:
    """Build a minimal WooCommerce product card HTML snippet."""
    oos_class = " out-of-stock" if out_of_stock else ""
    return f"""
<li class="product{oos_class}">
  <a href="{href}" class="woocommerce-LoopProduct-link">
    <h2 class="woocommerce-loop-product__title">{name}</h2>
    <span class="price">
      <span class="woocommerce-Price-amount amount">
        <bdi>{price}</bdi>
      </span>
    </span>
  </a>
</li>
"""


def _page(cards: list[str]) -> str:
    """Wrap card snippets in a minimal WooCommerce page shell."""
    return f"""
<html><body>
<ul class="products">
{''.join(cards)}
</ul>
</body></html>
"""


def _card_no_price(name: str) -> str:
    """A product card that is missing the price element entirely."""
    return f"""
<li class="product">
  <a href="https://example.com/noprice" class="woocommerce-LoopProduct-link">
    <h2 class="woocommerce-loop-product__title">{name}</h2>
  </a>
</li>
"""


# ---------------------------------------------------------------------------
# Shared StoreConfig-like object
# ---------------------------------------------------------------------------

class _FakeConfig:
    """Minimal stand-in for StoreConfig, providing only what the scraper uses."""

    store_id = "teststore"
    store_name = "Test Store"
    base_url = "https://test.example.com"
    requires_cloudscraper = False
    delay_seconds = 0.0           # no sleeping in tests
    HTTP_USER_AGENT = "TestAgent/1.0"
    url_template = "{base}/product-category/{slug}/"  # standard WC default
    category_map = {
        "GPUs": "tarjetas-de-video",
        "CPUs": "procesadores",
    }
    selectors = {
        "product_card": "li.product",
        "name": "h2.woocommerce-loop-product__title",
        "price": "span.price",
        "link": "a.woocommerce-LoopProduct-link",
        "stock": ".out-of-stock",
    }
    pagination = {"style": "page_param", "max_pages": 5}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def scraper() -> WooCommerceScraper:
    """A WooCommerceScraper instance built from _FakeConfig.

    The session setup in BaseScraper.__init__ imports HTTP_USER_AGENT from
    config; we patch it so no real config.py dependency is needed here.
    """
    with patch("scrapers.base.cloudscraper"), \
         patch("scrapers.base.requests") as mock_requests:
        # Make requests.Session() return a MagicMock session.
        mock_requests.Session.return_value = MagicMock()
        mock_requests.ConnectionError = ConnectionError
        mock_requests.Timeout = TimeoutError

        # Patch the import inside __init__ that pulls HTTP_USER_AGENT.
        with patch("scrapers.base.BaseScraper.__init__") as mock_init:
            mock_init.side_effect = _fake_init
            instance = WooCommerceScraper.__new__(WooCommerceScraper)
            _fake_init(instance, _FakeConfig())
            return instance


def _fake_init(self, config) -> None:
    """Replaces BaseScraper.__init__ in tests — sets up attributes without
    creating a real requests.Session or importing from config.py."""
    self.config = config
    self.store_id = config.store_id
    self.store_name = config.store_name
    self._session = MagicMock()


def _make_response(html: str, status_code: int = 200) -> MagicMock:
    """Return a mock requests.Response with the given HTML body."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = html
    return resp


# ---------------------------------------------------------------------------
# Test 1: Happy path — 3 products returned
# ---------------------------------------------------------------------------

def test_scrape_happy_path_returns_three_products(scraper):
    """Category page with 3 valid cards → 3 RawProducts, correct fields."""
    cards = [
        _card("RTX 4070 Ti SUPER", "₡950,000", "https://test.example.com/rtx4070ti"),
        _card("RTX 3060", "₡450,000", "https://test.example.com/rtx3060"),
        _card("RX 7800 XT", "₡680,000", "https://test.example.com/rx7800"),
    ]
    page1_html = _page(cards)
    page2_html = _page([])  # empty second page stops pagination

    call_count = 0

    def fake_http_get(url: str):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_response(page1_html)
        return _make_response(page2_html)

    scraper._http_get = fake_http_get

    results = scraper.scrape("GPUs")

    assert len(results) == 3
    assert all(isinstance(p, RawProduct) for p in results)

    names = [p.raw_name for p in results]
    assert "RTX 4070 Ti SUPER" in names
    assert "RTX 3060" in names
    assert "RX 7800 XT" in names

    assert all(p.store_id == "teststore" for p in results)
    assert all(p.category == "GPUs" for p in results)
    assert all(p.in_stock is True for p in results)
    assert results[0].price_str == "₡950,000"
    assert results[0].url == "https://test.example.com/rtx4070ti"
    assert results[0].scraped_at.endswith("Z")


# ---------------------------------------------------------------------------
# Test 2: Empty second page stops pagination
# ---------------------------------------------------------------------------

def test_scrape_stops_at_empty_page(scraper):
    """Only products from pages that return cards are included."""
    page1_cards = [
        _card("RTX 4070", "₡800,000"),
        _card("RTX 4080", "₡1,200,000"),
    ]
    calls: list[str] = []

    def fake_http_get(url: str):
        calls.append(url)
        if len(calls) == 1:
            return _make_response(_page(page1_cards))
        return _make_response(_page([]))  # page 2 empty → stop

    scraper._http_get = fake_http_get

    results = scraper.scrape("GPUs")

    assert len(results) == 2
    # Only 2 HTTP calls: page 1 (products) + page 2 (empty → stop)
    assert len(calls) == 2


# ---------------------------------------------------------------------------
# Test 3: HTTP error propagates as ScraperError
# ---------------------------------------------------------------------------

def test_scrape_propagates_scraper_error(scraper):
    """ScraperError from _http_get is NOT swallowed — it propagates to the caller."""
    def fake_http_get(url: str):
        raise ScraperError(url=url, status_code=503, message="Service Unavailable")

    scraper._http_get = fake_http_get

    with pytest.raises(ScraperError) as exc_info:
        scraper.scrape("GPUs")

    assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# Test 4: Card with missing price is skipped
# ---------------------------------------------------------------------------

def test_scrape_skips_card_missing_price(scraper):
    """Card without a price element is silently skipped; others are returned."""
    cards_html = _page([
        _card("RTX 4070", "₡800,000"),
        _card_no_price("Mystery GPU"),       # missing price → skipped
        _card("RTX 3060", "₡450,000"),
    ])
    call_count = 0

    def fake_http_get(url: str):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_response(cards_html)
        return _make_response(_page([]))

    scraper._http_get = fake_http_get

    results = scraper.scrape("GPUs")

    assert len(results) == 2
    names = [p.raw_name for p in results]
    assert "Mystery GPU" not in names
    assert "RTX 4070" in names
    assert "RTX 3060" in names


# ---------------------------------------------------------------------------
# Test 5: Unmapped category returns [] without HTTP call
# ---------------------------------------------------------------------------

def test_scrape_unmapped_category_returns_empty_no_http(scraper):
    """An unmapped category should return [] immediately, with zero HTTP calls."""
    calls: list[str] = []

    def fake_http_get(url: str):
        calls.append(url)
        return _make_response(_page([]))

    scraper._http_get = fake_http_get

    results = scraper.scrape("UnknownCategory")

    assert results == []
    assert calls == [], "Expected zero HTTP calls for unmapped category"


# ---------------------------------------------------------------------------
# Test 6: Search fallback when category page returns 0 products
# ---------------------------------------------------------------------------

def test_scrape_search_fallback_when_category_page_empty(scraper):
    """If page 1 returns no products, the search URL is tried as fallback."""
    search_cards = [
        _card("GTX 1080", "₡320,000", "https://test.example.com/gtx1080"),
    ]
    calls: list[str] = []

    def fake_http_get(url: str):
        calls.append(url)
        if "product-category" in url:
            # Category page is empty
            return _make_response(_page([]))
        else:
            # Search URL returns one result
            return _make_response(_page(search_cards))

    scraper._http_get = fake_http_get

    results = scraper.scrape("GPUs")

    assert len(results) == 1
    assert results[0].raw_name == "GTX 1080"

    # Verify the search URL was called
    search_calls = [u for u in calls if "post_type=product" in u]
    assert len(search_calls) == 1
    assert "tarjetas-de-video" in search_calls[0]
