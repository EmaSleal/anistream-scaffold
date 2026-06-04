"""
Integration smoke test — requires live network access.

Run with:  python -m pytest tests/test_integration_smoke.py -v -m integration -s
Skip in unit runs:  python -m pytest tests/ -m "not integration"
"""
import os
import pytest

from config import STORES
from storage import Storage
from orchestrator import Orchestrator


SMOKE_DB = "data/smoke_test.db"


@pytest.fixture(autouse=True)
def cleanup_smoke_db():
    yield
    # Small delay to allow SQLite WAL files to close on Windows before removal
    import time, gc
    gc.collect()
    time.sleep(0.2)
    for ext in ["", "-wal", "-shm"]:
        path = SMOKE_DB + ext
        if os.path.exists(path):
            try:
                os.remove(path)
            except PermissionError:
                pass  # best-effort cleanup


@pytest.mark.integration
def test_intelec_cpus_pipeline():
    """Full pipeline: scrape Intelec CPUs → normalise → persist → query."""
    storage = Storage(SMOKE_DB)
    storage.init_schema()

    intelec_cfg = STORES["intelec"]
    orchestrator = Orchestrator(
        storage=storage,
        stores={"intelec": intelec_cfg},
    )

    # Patch CATEGORIES to only scrape CPUs so the test is fast
    import orchestrator as orch_mod
    original_categories = orch_mod.CATEGORIES
    orch_mod.CATEGORIES = ["CPUs"]
    try:
        summary = orchestrator.run_scrape(store_ids=["intelec"])
    finally:
        orch_mod.CATEGORIES = original_categories

    # Assert pipeline ran
    assert summary["stores_attempted"] == 1
    assert summary["stores_failed"] == 0, f"Store failed: {summary}"
    assert summary["total_products"] > 0, "No products were scraped and persisted"

    # Assert data in DB
    rows = storage.get_comparison_table(category="CPUs")
    assert len(rows) > 0, "get_comparison_table returned empty for CPUs"

    # Assert data quality
    for row in rows:
        assert row.get("canonical_key"), f"Row missing canonical_key: {row}"
        # get_comparison_table returns stores nested under row["stores"]
        stores_data = row.get("stores", {})
        prices = [
            store["price_crc"]
            for store in stores_data.values()
            if isinstance(store, dict) and store.get("price_crc")
        ]
        assert any(p > 0 for p in prices), f"No valid prices in row: {row}"
