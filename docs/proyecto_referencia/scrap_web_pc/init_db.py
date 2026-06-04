"""
init_db.py — Idempotent SQLite schema bootstrap.

Run directly:
    python init_db.py

Or call from storage.py:
    from init_db import init_schema
    init_schema(conn)

Safe to run multiple times; uses CREATE TABLE IF NOT EXISTS throughout.
"""
from __future__ import annotations

import logging
import os
import sqlite3

from config import DB_PATH

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DDL statements
# ---------------------------------------------------------------------------

_PRAGMAS = [
    "PRAGMA journal_mode = WAL;",
    "PRAGMA foreign_keys = ON;",
]

_DDL_PRODUCTS = """
CREATE TABLE IF NOT EXISTS products (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_key   TEXT    NOT NULL,
    brand           TEXT    NOT NULL DEFAULT '',
    model           TEXT    NOT NULL,
    category        TEXT    NOT NULL,
    store           TEXT    NOT NULL,
    raw_name        TEXT    NOT NULL,
    url             TEXT    NOT NULL,
    price_crc       INTEGER NOT NULL,
    in_stock        INTEGER NOT NULL DEFAULT 1,
    scraped_at      TEXT    NOT NULL,
    UNIQUE(canonical_key, store)
);
"""

_DDL_IDX_PRODUCTS_CATEGORY = """
CREATE INDEX IF NOT EXISTS idx_products_category
    ON products(category);
"""

_DDL_IDX_PRODUCTS_CANONICAL = """
CREATE INDEX IF NOT EXISTS idx_products_canonical
    ON products(canonical_key);
"""

_DDL_PRICE_HISTORY = """
CREATE TABLE IF NOT EXISTS price_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    price_crc   INTEGER NOT NULL,
    in_stock    INTEGER NOT NULL,
    scraped_at  TEXT    NOT NULL
);
"""

_DDL_IDX_HISTORY_PRODUCT = """
CREATE INDEX IF NOT EXISTS idx_history_product
    ON price_history(product_id, scraped_at DESC);
"""

_DDL_SCRAPE_RUNS = """
CREATE TABLE IF NOT EXISTS scrape_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at   TEXT    NOT NULL,
    finished_at  TEXT,
    status       TEXT    NOT NULL DEFAULT 'running',
    summary_json TEXT,
    trigger      TEXT    NOT NULL
);
"""

_ALL_DDL = [
    *_PRAGMAS,
    _DDL_PRODUCTS,
    _DDL_IDX_PRODUCTS_CATEGORY,
    _DDL_IDX_PRODUCTS_CANONICAL,
    _DDL_PRICE_HISTORY,
    _DDL_IDX_HISTORY_PRODUCT,
    _DDL_SCRAPE_RUNS,
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init_schema(conn: sqlite3.Connection) -> None:
    """Apply all DDL statements to an open connection.

    Idempotent — safe to call on an existing database.
    WAL mode and FK enforcement are set on every call (they are connection-
    level and are reset when the connection is closed).
    """
    cursor = conn.cursor()
    for statement in _ALL_DDL:
        cursor.execute(statement)
    conn.commit()
    logger.debug("Schema initialised (or already up-to-date).")


def _ensure_data_dir(db_path: str) -> None:
    directory = os.path.dirname(db_path)
    if directory:
        os.makedirs(directory, exist_ok=True)


def create_db(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Open (or create) the database at *db_path* and apply the schema."""
    _ensure_data_dir(db_path)
    conn = sqlite3.connect(db_path)
    init_schema(conn)
    return conn


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    db_path = DB_PATH
    logger.info("Initialising database at: %s", db_path)
    conn = create_db(db_path)
    conn.close()
    logger.info("Done. Database ready at: %s", db_path)
