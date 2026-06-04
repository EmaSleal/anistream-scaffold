"""
orchestrator.py — Scrape pipeline coordinator.

Public API:
    Orchestrator(storage, stores) — glues scrape -> normalize -> match -> persist
    Orchestrator.run_scrape(store_ids) -> dict  — executes a full scrape run
"""
from __future__ import annotations

import importlib
import logging
import shutil
import time
from pathlib import Path
from typing import Any

from config import CATEGORIES, STORES
from normalizer import match
from scrapers.base import CanonicalProduct, RawProduct
from storage import Storage
from validators import CategoryValidator, ValidationResult

logger = logging.getLogger(__name__)


class Orchestrator:
    """Coordinates scraping, normalisation, and persistence for all enabled stores.

    The orchestrator is intentionally Flask-free — it can be called from a
    scheduler, a CLI script, or a Flask route without any web-framework import.
    """

    def __init__(
        self,
        storage: Storage,
        stores: dict | None = None,
        validator: CategoryValidator | None = None,
    ) -> None:
        """Initialise the orchestrator.

        Args:
            storage:   An open Storage instance (schema must already be applied).
            stores:    Dict of {store_id: StoreConfig}.  Defaults to config.STORES.
            validator: CategoryValidator instance.  Defaults to CategoryValidator().
                       Pass a mock or stub in tests to bypass Ollama.
        """
        self._storage = storage
        self._stores = stores if stores is not None else STORES
        self._validator = validator if validator is not None else CategoryValidator()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_scrape(self, store_ids: list[str] | None = None) -> dict[str, Any]:
        """Execute a full scrape run across the specified (or all enabled) stores.

        Steps:
          1. Resolve the store list (filter by store_ids and enabled flag).
          2. Backup the DB file (skip if DB does not exist yet).
          3. Open a scrape_run row in storage.
          4. For each store:
             a. Instantiate the scraper via importlib.
             b. For each category: scrape -> normalise -> match -> persist.
             c. On any exception: log ERROR and continue to the next store.
          5. Close the scrape_run row with final status.
          6. Return a summary dict.

        Args:
            store_ids: Optional list of store_id strings to restrict the run.
                       If None, all stores with enabled=True are used.

        Returns:
            {
                "run_id":           int,
                "stores_attempted": int,
                "stores_failed":    int,
                "total_products":   int,
                "duration_seconds": float,
            }
        """
        start_time = time.monotonic()

        # Step 1: resolve store list
        active_stores = self._resolve_stores(store_ids)
        store_id_list = list(active_stores.keys())
        logger.info(
            "orchestrator.run_scrape: starting — stores=%s", store_id_list
        )

        # Step 2: backup DB
        self._backup_db()

        # Step 3: open scrape_run row
        run_id = self._storage.start_scrape_run(store_id_list)

        # Step 4: iterate stores
        total_products = 0
        stores_failed: list[str] = []

        for store_id, store_config in active_stores.items():
            try:
                count = self._scrape_store(store_id, store_config)
                total_products += count
                logger.info(
                    "orchestrator: store=%s done products=%d", store_id, count
                )
            except Exception as exc:
                logger.error(
                    "orchestrator: store=%s FAILED — %s: %s",
                    store_id,
                    type(exc).__name__,
                    exc,
                )
                stores_failed.append(store_id)

        # Step 5: close scrape_run row
        status = "success" if not stores_failed else "partial"
        if len(stores_failed) == len(active_stores):
            status = "failed"
        self._storage.finish_scrape_run(run_id, status, total_products)

        duration = time.monotonic() - start_time
        logger.info(
            "orchestrator.run_scrape: finished run_id=%d status=%s "
            "products=%d duration=%.1fs",
            run_id, status, total_products, duration,
        )

        # Step 6: return summary
        return {
            "run_id": run_id,
            "stores_attempted": len(active_stores),
            "stores_failed": len(stores_failed),
            "total_products": total_products,
            "duration_seconds": round(duration, 2),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _resolve_stores(self, store_ids: list[str] | None) -> dict:
        """Return {store_id: StoreConfig} for enabled stores, optionally filtered."""
        enabled = {sid: cfg for sid, cfg in self._stores.items() if cfg.enabled}
        if store_ids is None:
            return enabled
        return {sid: cfg for sid, cfg in enabled.items() if sid in store_ids}

    def _backup_db(self) -> None:
        """Copy data/data.db -> data/data.db.bak if the DB file exists."""
        db_path = Path(self._storage._db_path)
        if db_path.exists():
            bak_path = db_path.with_suffix(db_path.suffix + ".bak")
            try:
                shutil.copy2(db_path, bak_path)
                logger.info("orchestrator: DB backed up to %s", bak_path)
            except OSError as exc:
                logger.warning("orchestrator: DB backup failed — %s", exc)

    def _scrape_store(self, store_id: str, store_config) -> int:
        """Scrape all categories for one store and persist results.

        Returns the total number of products upserted for this store.
        Raises any exception from the scraper so the caller can do
        per-store isolation.
        """
        scraper_class = _resolve_scraper_class(store_config.scraper_class)
        scraper = scraper_class(store_config)
        products_count = 0

        for category in CATEGORIES:
            raw_products: list[RawProduct] = scraper.scrape(category)

            if not raw_products:
                continue

            product_groups = match(raw_products, category)

            for group in product_groups:
                for listing in group.listings:
                    canonical = CanonicalProduct(
                        canonical_key=listing.canonical_key,
                        brand=listing.brand,
                        model=listing.model,
                        category=listing.category,
                        store_id=listing.store_id,
                        url=listing.url,
                        price_crc=listing.price_crc,
                        in_stock=listing.in_stock,
                        scraped_at=listing.scraped_at,
                    )
                    val_result = self._validator.run(
                        canonical.canonical_key, canonical.category
                    )
                    if val_result == ValidationResult.DISCARD:
                        continue
                    product_id = self._storage.upsert_product(canonical)
                    self._storage.record_price_history(
                        product_id=product_id,
                        price_crc=listing.price_crc,
                        store=listing.store_id,
                        scraped_at=listing.scraped_at,
                    )
                    products_count += 1

        return products_count


def _resolve_scraper_class(dotted_path: str) -> type:
    """Import and return a class from a dotted module path.

    Args:
        dotted_path: e.g. "scrapers.woocommerce.WooCommerceScraper"

    Returns:
        The class object.

    Raises:
        ImportError if the module cannot be found.
        AttributeError if the class does not exist in the module.
    """
    module_path, class_name = dotted_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)
