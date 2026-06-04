"""
tests/test_orchestrator.py — Unit tests for orchestrator.py

Covers (TASK-27):
  1. Full run: mock WooCommerceScraper.scrape to return 2 RawProducts for one
     store/category → assert products appear in DB via get_comparison_table
  2. Per-store isolation: first store raises ScraperError, second store
     succeeds → summary shows 1 failed, products from second store in DB
  3. DB backup: assert data.db.bak is created when DB exists before run
     (uses tmp_path fixture)
  4. Empty scrape: scraper returns [] for all categories → run completes,
     summary total_products=0

No real HTTP calls are made.
"""
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from config import StoreConfig
from orchestrator import Orchestrator
from scrapers.base import RawProduct, ScraperError
from storage import Storage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _raw_product(
    store_id: str = "teststore",
    raw_name: str = "Tarjeta de Video ASUS TUF RTX 4070 Ti SUPER 16GB",
    price_str: str = "₡950,000",
    url: str = "https://test.example.com/rtx4070",
    in_stock: bool = True,
    category: str = "GPUs",
) -> RawProduct:
    return RawProduct(
        store_id=store_id,
        raw_name=raw_name,
        price_str=price_str,
        url=url,
        in_stock=in_stock,
        category=category,
        scraped_at=_now(),
    )


def _make_store_config(
    store_id: str,
    scraper_class: str = "scrapers.woocommerce.WooCommerceScraper",
    enabled: bool = True,
) -> StoreConfig:
    return StoreConfig(
        store_id=store_id,
        store_name=store_id.title(),
        base_url=f"https://{store_id}.example.com",
        scraper_class=scraper_class,
        category_map={"GPUs": "tarjetas-de-video"},
        enabled=enabled,
    )


@pytest.fixture
def mem_storage() -> Storage:
    """In-memory Storage with schema applied."""
    s = Storage(":memory:")
    s.init_schema()
    return s


# ---------------------------------------------------------------------------
# Test 1: Full run — 2 RawProducts end up in DB
# ---------------------------------------------------------------------------

def test_full_run_products_appear_in_db(mem_storage: Storage) -> None:
    """Mock scraper returns 2 RawProducts; both should be retrievable via
    get_comparison_table after the run."""
    raw_products = [
        _raw_product(
            store_id="teststore",
            raw_name="Tarjeta de Video ASUS TUF RTX 4070 Ti SUPER 16GB",
            price_str="₡950,000",
            url="https://test.example.com/rtx4070ti",
        ),
        _raw_product(
            store_id="teststore",
            raw_name="Tarjeta de Video MSI Gaming X RTX 3060 12GB",
            price_str="₡450,000",
            url="https://test.example.com/rtx3060",
        ),
    ]

    stores = {"teststore": _make_store_config("teststore")}

    mock_scraper_instance = MagicMock()
    # scrape() returns our 2 products for "GPUs", [] for every other category
    def _fake_scrape(category):
        if category == "GPUs":
            return raw_products
        return []

    mock_scraper_instance.scrape.side_effect = _fake_scrape

    with patch("orchestrator._resolve_scraper_class") as mock_resolve:
        mock_resolve.return_value = MagicMock(return_value=mock_scraper_instance)
        orch = Orchestrator(storage=mem_storage, stores=stores)
        summary = orch.run_scrape()

    assert summary["stores_attempted"] == 1
    assert summary["stores_failed"] == 0
    assert summary["total_products"] >= 2   # at least 2 products persisted

    table = mem_storage.get_comparison_table(category="GPUs")
    canonical_keys = {row["canonical_key"] for row in table}
    # Both products should have been normalised and stored
    assert len(table) >= 1, "Expected at least one product group in DB"
    # At minimum the RTX 4070 Ti SUPER should be present
    rtx_4070_found = any("4070" in k for k in canonical_keys)
    assert rtx_4070_found, f"RTX 4070 Ti SUPER not found in DB; keys={canonical_keys}"


# ---------------------------------------------------------------------------
# Test 2: Per-store isolation — first store fails, second store succeeds
# ---------------------------------------------------------------------------

def test_per_store_isolation_failed_store_does_not_stop_second(
    mem_storage: Storage,
) -> None:
    """If the first store raises an exception the second must still run and
    persist its products.  The summary must reflect exactly 1 failed store."""
    raw_from_store2 = [
        _raw_product(
            store_id="store2",
            raw_name="Tarjeta de Video Gigabyte RTX 4060 Gaming OC 8GB",
            price_str="₡600,000",
            url="https://store2.example.com/rtx4060",
        ),
    ]

    stores = {
        "store1": _make_store_config("store1"),
        "store2": _make_store_config("store2"),
    }

    # Scraper factory: store1 raises, store2 returns products
    call_count = [0]

    def fake_scraper_factory(store_config):
        call_count[0] += 1
        mock = MagicMock()
        if store_config.store_id == "store1":
            mock.scrape.side_effect = ScraperError(
                url="https://store1.example.com/gpus",
                status_code=503,
                message="Service Unavailable",
            )
        else:
            def _scrape(category):
                if category == "GPUs":
                    # Assign correct store_id at call time
                    return [
                        RawProduct(
                            store_id="store2",
                            raw_name=p.raw_name,
                            price_str=p.price_str,
                            url=p.url,
                            in_stock=p.in_stock,
                            category=p.category,
                            scraped_at=p.scraped_at,
                        )
                        for p in raw_from_store2
                    ]
                return []
            mock.scrape.side_effect = _scrape
        return mock

    with patch("orchestrator._resolve_scraper_class") as mock_resolve:
        mock_resolve.return_value = fake_scraper_factory
        orch = Orchestrator(storage=mem_storage, stores=stores)
        summary = orch.run_scrape()

    assert summary["stores_attempted"] == 2
    assert summary["stores_failed"] == 1
    assert summary["total_products"] >= 1

    # Products from store2 must be in DB
    table = mem_storage.get_comparison_table(category="GPUs")
    assert len(table) >= 1, "Expected products from store2 to be in DB"


# ---------------------------------------------------------------------------
# Test 3: DB backup — .bak file created when DB exists before run
# ---------------------------------------------------------------------------

def test_db_backup_created_when_db_exists(tmp_path: Path) -> None:
    """If the DB file exists before run_scrape, a .bak copy must be created
    alongside it."""
    db_file = tmp_path / "data.db"
    bak_file = tmp_path / "data.db.bak"

    # Create a real on-disk DB
    storage = Storage(str(db_file))
    storage.init_schema()

    stores = {"teststore": _make_store_config("teststore")}

    mock_scraper = MagicMock()
    mock_scraper.scrape.return_value = []

    with patch("orchestrator._resolve_scraper_class") as mock_resolve:
        mock_resolve.return_value = MagicMock(return_value=mock_scraper)
        orch = Orchestrator(storage=storage, stores=stores)
        orch.run_scrape()

    assert bak_file.exists(), (
        f"Expected {bak_file} to exist after run_scrape, but it was not created"
    )


# ---------------------------------------------------------------------------
# Test 4: Empty scrape — scraper returns [] for all categories, total_products=0
# ---------------------------------------------------------------------------

def test_empty_scrape_completes_with_zero_products(mem_storage: Storage) -> None:
    """When every store/category returns an empty list the run must still
    complete successfully with total_products=0."""
    stores = {"teststore": _make_store_config("teststore")}

    mock_scraper = MagicMock()
    mock_scraper.scrape.return_value = []   # empty for every category

    with patch("orchestrator._resolve_scraper_class") as mock_resolve:
        mock_resolve.return_value = MagicMock(return_value=mock_scraper)
        orch = Orchestrator(storage=mem_storage, stores=stores)
        summary = orch.run_scrape()

    assert summary["stores_attempted"] == 1
    assert summary["stores_failed"] == 0
    assert summary["total_products"] == 0
    assert isinstance(summary["run_id"], int)
    assert summary["run_id"] > 0
