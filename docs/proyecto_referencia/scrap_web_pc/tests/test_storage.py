"""
tests/test_storage.py — Unit tests for storage.py

Covers (TASK-25):
  1. upsert_product — insert new product returns a positive id
  2. upsert_product — update existing product (same canonical_key + store_id) changes price
  3. record_price_history — appends a row; second call for same product appends second row
  4. get_comparison_table — returns grouped rows; cheapest store marked correctly
  5. get_comparison_table(category="GPUs") — filters by category

All tests use Storage(":memory:") — no file I/O.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from scrapers.base import CanonicalProduct
from storage import Storage


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _make_product(
    canonical_key: str = "ASUS RTX 4070 Ti Super",
    brand: str = "ASUS",
    model: str = "RTX 4070 Ti Super",
    category: str = "GPUs",
    store_id: str = "techzilla",
    url: str = "https://techzilla.cr/rtx4070",
    price_crc: int = 950_000,
    in_stock: bool = True,
    scraped_at: str | None = None,
) -> CanonicalProduct:
    return CanonicalProduct(
        canonical_key=canonical_key,
        brand=brand,
        model=model,
        category=category,
        store_id=store_id,
        url=url,
        price_crc=price_crc,
        in_stock=in_stock,
        scraped_at=scraped_at or _now(),
    )


@pytest.fixture
def db() -> Storage:
    """An in-memory Storage with schema already applied."""
    storage = Storage(":memory:")
    storage.init_schema()
    return storage


# ---------------------------------------------------------------------------
# Test 1: upsert_product — new product returns a positive id
# ---------------------------------------------------------------------------

def test_upsert_product_new_returns_positive_id(db: Storage) -> None:
    """Inserting a brand-new product must return a positive integer id."""
    product = _make_product()
    product_id = db.upsert_product(product)

    assert isinstance(product_id, int)
    assert product_id > 0


# ---------------------------------------------------------------------------
# Test 2: upsert_product — updating an existing product changes price
# ---------------------------------------------------------------------------

def test_upsert_product_update_changes_price(db: Storage) -> None:
    """Re-upserting the same (canonical_key, store_id) with a new price
    must update the row rather than inserting a duplicate."""
    product_v1 = _make_product(price_crc=950_000)
    id_v1 = db.upsert_product(product_v1)

    product_v2 = _make_product(price_crc=920_000)  # same key + store, lower price
    id_v2 = db.upsert_product(product_v2)

    # The same logical row — id must be identical (upsert, not insert)
    assert id_v1 == id_v2

    # Confirm the price was updated in the products table
    row = db._conn.execute(
        "SELECT price_crc FROM products WHERE id = ?", (id_v1,)
    ).fetchone()
    assert row["price_crc"] == 920_000


# ---------------------------------------------------------------------------
# Test 3: record_price_history — appends rows; second call creates second row
# ---------------------------------------------------------------------------

def test_record_price_history_appends_rows(db: Storage) -> None:
    """Each call to record_price_history must append a new row to price_history."""
    product = _make_product()
    product_id = db.upsert_product(product)

    db.record_price_history(
        product_id=product_id,
        price_crc=950_000,
        store="techzilla",
        scraped_at=_now(),
    )
    db.record_price_history(
        product_id=product_id,
        price_crc=920_000,
        store="techzilla",
        scraped_at=_now(),
    )

    rows = db._conn.execute(
        "SELECT price_crc FROM price_history WHERE product_id = ? ORDER BY id",
        (product_id,),
    ).fetchall()

    assert len(rows) == 2
    assert rows[0]["price_crc"] == 950_000
    assert rows[1]["price_crc"] == 920_000


# ---------------------------------------------------------------------------
# Test 4: get_comparison_table — groups rows; cheapest store marked correctly
# ---------------------------------------------------------------------------

def test_get_comparison_table_cheapest_store(db: Storage) -> None:
    """get_comparison_table must group by canonical_key and identify the
    cheapest in-stock store for each group."""
    # Same canonical product at three stores with different prices
    for store_id, price in [
        ("techzilla", 280_000),
        ("igamingcr", 265_000),   # cheapest
        ("intelec", 275_000),
    ]:
        p = _make_product(
            canonical_key="Intel Core I7-13700K",
            brand="Intel",
            model="Core I7-13700K",
            category="CPUs",
            store_id=store_id,
            url=f"https://{store_id}.cr/i7",
            price_crc=price,
        )
        db.upsert_product(p)

    table = db.get_comparison_table()

    assert len(table) == 1
    group = table[0]

    assert group["canonical_key"] == "Intel Core I7-13700K"
    assert group["cheapest_store"] == "igamingcr"
    assert len(group["stores"]) == 3

    # Verify individual store prices are recorded
    assert group["stores"]["techzilla"]["price_crc"] == 280_000
    assert group["stores"]["igamingcr"]["price_crc"] == 265_000
    assert group["stores"]["intelec"]["price_crc"] == 275_000


# ---------------------------------------------------------------------------
# Test 5: get_comparison_table(category="GPUs") — filters by category
# ---------------------------------------------------------------------------

def test_get_comparison_table_category_filter(db: Storage) -> None:
    """Passing category= must restrict results to that category only."""
    gpu_product = _make_product(
        canonical_key="MSI RTX 4060",
        brand="MSI",
        model="RTX 4060",
        category="GPUs",
        store_id="techzilla",
        price_crc=600_000,
    )
    cpu_product = _make_product(
        canonical_key="AMD Ryzen 5 7600X",
        brand="AMD",
        model="Ryzen 5 7600X",
        category="CPUs",
        store_id="techzilla",
        url="https://techzilla.cr/ryzen",
        price_crc=200_000,
    )

    db.upsert_product(gpu_product)
    db.upsert_product(cpu_product)

    gpu_results = db.get_comparison_table(category="GPUs")
    cpu_results = db.get_comparison_table(category="CPUs")
    all_results = db.get_comparison_table()

    assert len(gpu_results) == 1
    assert gpu_results[0]["canonical_key"] == "MSI RTX 4060"

    assert len(cpu_results) == 1
    assert cpu_results[0]["canonical_key"] == "AMD Ryzen 5 7600X"

    assert len(all_results) == 2
