"""
scrapers/base.py — Data models and BaseScraper ABC.

Public API:
    RawProduct        — raw data as scraped from a store page
    CanonicalProduct  — normalised, store-specific listing
    ProductGroup      — canonical product grouped across stores
    BaseScraper       — abstract base class all scrapers must implement
    ScraperError      — raised after exhausting HTTP retries
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

import cloudscraper
import requests

if TYPE_CHECKING:
    from config import StoreConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ScraperError(Exception):
    """Raised when all HTTP retries are exhausted or a non-retryable error occurs.

    Attributes:
        url         — the request URL that failed
        status_code — HTTP status code, or None for connection-level failures
        message     — human-readable description
    """

    def __init__(self, url: str, status_code: int | None, message: str) -> None:
        self.url = url
        self.status_code = status_code
        self.message = message
        super().__init__(f"ScraperError [{status_code}] {url} — {message}")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RawProduct:
    """Raw product data as scraped directly from a store page.

    Fields are intentionally unprocessed — price_str keeps the original
    text for debugging; parsing happens in the normaliser layer.
    """
    store_id: str            # matches StoreConfig.store_id
    raw_name: str            # product title as it appears on the page
    price_str: str           # original price text, e.g. "₡700,000"
    url: str                 # product URL
    in_stock: bool           # True if available, False if out-of-stock
    category: str            # logical category (one of CATEGORIES)
    scraped_at: str          # ISO 8601 timestamp, e.g. "2024-01-15T03:00:00"


@dataclass
class CanonicalProduct:
    """Normalised product listing for a specific (canonical_key, store) pair.

    canonical_key is the matchable string built by the normaliser
    (e.g. "ASUS RTX 4070 Ti SUPER").  price_crc is already parsed to an
    integer count of Costa Rican colones.
    """
    canonical_key: str       # normalised key, e.g. "ASUS RTX 4070 Ti SUPER"
    brand: str               # e.g. "ASUS"; empty string if unknown
    model: str               # e.g. "RTX 4070 Ti SUPER"
    category: str            # logical category
    store_id: str            # matches StoreConfig.store_id
    url: str
    price_crc: int           # price in Costa Rican colones (integer)
    in_stock: bool
    scraped_at: str          # ISO 8601 timestamp


@dataclass
class ProductGroup:
    """A canonical product seen across one or more stores.

    listings holds one CanonicalProduct per store that carries the item.
    cheapest_store_id is computed after all listings are attached; it is
    set by the caller (orchestrator or storage layer) and may be None if
    no listings exist.
    """
    canonical_key: str
    brand: str
    model: str
    category: str
    listings: list[CanonicalProduct]
    cheapest_store_id: str | None = None


# ---------------------------------------------------------------------------
# BaseScraper ABC
# ---------------------------------------------------------------------------

class BaseScraper(ABC):
    """Contract that every concrete store scraper must implement.

    Subclasses MUST:
    - implement scrape(category) — handle pagination internally
    - implement supported_categories() — return categories from config
    - NOT raise on per-product parse failure; log and continue

    Subclasses MAY:
    - override delay_seconds, requires_cloudscraper at the class level
    """

    delay_seconds: float = 1.5
    requires_cloudscraper: bool = False

    def __init__(self, config: StoreConfig) -> None:
        self.config = config
        self.store_id: str = config.store_id
        self.store_name: str = config.store_name

        # Build the HTTP session once; reused for all requests from this instance.
        if config.requires_cloudscraper:
            self._session: requests.Session = cloudscraper.create_scraper()
        else:
            self._session = requests.Session()

        # HTTP_USER_AGENT is a module-level constant in config.py.
        from config import HTTP_USER_AGENT  # deferred to avoid circular import
        self._session.headers.update({"User-Agent": HTTP_USER_AGENT})

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def scrape(self, category: str) -> list[RawProduct]:
        """Fetch and parse one category from the store.

        Must handle pagination internally.
        Must NOT raise on per-product parse failure — log and skip.
        Returns an empty list when the store does not carry the category
        or when all retries are exhausted.
        """

    @abstractmethod
    def supported_categories(self) -> list[str]:
        """Return the logical categories this store offers.

        Typically derived from config.category_map.keys().
        """

    # ------------------------------------------------------------------
    # Shared HTTP helper
    # ------------------------------------------------------------------

    def _http_get(self, url: str) -> requests.Response:
        """Fetch *url* with rate limiting, a browser User-Agent, and 3-retry
        exponential backoff.

        Retry policy:
        - Retries on: ConnectionError, Timeout, HTTP 429, HTTP 5xx.
        - Does NOT retry on HTTP 4xx (except 429).
        - Wait between retries: 2^attempt seconds (1 s, 2 s, 4 s).
        - Enforces per-instance rate limit via config.delay_seconds before
          every request (including the first).

        Raises:
            ScraperError — after all retries are exhausted or a non-retryable
                           HTTP error is encountered.
        """
        max_attempts = 3
        last_exc: Exception | None = None
        last_status: int | None = None

        for attempt in range(max_attempts):
            # Rate-limit: wait before every request.
            time.sleep(self.config.delay_seconds)

            try:
                response = self._session.get(url, timeout=30)
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_exc = exc
                wait = 2 ** attempt
                logger.warning(
                    "HTTP connection error store=%s url=%s attempt=%d/%d err=%s — retrying in %ds",
                    self.store_id, url, attempt + 1, max_attempts, exc, wait,
                )
                time.sleep(wait)
                continue

            status = response.status_code

            # Success.
            if status < 400:
                return response

            # Retryable HTTP errors: 429 or 5xx.
            if status == 429 or status >= 500:
                last_status = status
                wait = 2 ** attempt
                logger.warning(
                    "Retryable HTTP %d store=%s url=%s attempt=%d/%d — retrying in %ds",
                    status, self.store_id, url, attempt + 1, max_attempts, wait,
                )
                time.sleep(wait)
                continue

            # Non-retryable 4xx (but not 429, already handled above).
            raise ScraperError(
                url=url,
                status_code=status,
                message=f"HTTP {status} — not retrying",
            )

        # Exhausted all retries.
        if last_exc is not None:
            raise ScraperError(
                url=url,
                status_code=None,
                message=f"Connection failed after {max_attempts} attempts: {last_exc}",
            )
        raise ScraperError(
            url=url,
            status_code=last_status,
            message=f"HTTP {last_status} after {max_attempts} attempts",
        )
