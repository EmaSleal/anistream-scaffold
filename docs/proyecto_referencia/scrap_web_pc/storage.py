"""
storage.py — SQLite Data Access Layer.

Public API:
    Storage.init_schema()              — apply DDL (idempotent)
    Storage.start_scrape_run(stores)   — open a scrape_runs row, return run_id
    Storage.finish_scrape_run(...)     — close a scrape_runs row
    Storage.upsert_product(product)    — insert or update products table
    Storage.record_price_history(...)  — append a price_history row
    Storage.get_comparison_table(...)  — pivot products by canonical_key
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any

from init_db import init_schema as _init_schema
from scrapers.base import CanonicalProduct

logger = logging.getLogger(__name__)


class Storage:
    """SQLite DAL.  One instance per process; connection opened on __init__."""

    def __init__(self, db_path: str) -> None:
        """Open (or create) the database and configure the connection.

        WAL mode and FK enforcement are set on every new connection.  The
        schema is NOT applied here; call init_schema() explicitly so callers
        can control when DDL runs (useful for tests with :memory: databases).
        """
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._apply_connection_pragmas(self._conn)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_connection_pragmas(conn: sqlite3.Connection) -> None:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA foreign_keys = ON;")

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    # ------------------------------------------------------------------
    # TASK-05 — schema + scrape_runs
    # ------------------------------------------------------------------

    def init_schema(self) -> None:
        """Apply all DDL to the open connection.  Idempotent."""
        with self._conn:
            _init_schema(self._conn)
        logger.debug("Storage.init_schema() complete for %s", self._db_path)

    def start_scrape_run(self, stores: list[str]) -> int:
        """Insert a new 'running' row into scrape_runs.

        Args:
            stores: list of store_id strings that will participate in this run.

        Returns:
            The auto-generated run_id (INTEGER PRIMARY KEY).
        """
        started_at = self._now_iso()
        initial_summary = json.dumps({s: {"count": 0, "error": None} for s in stores})
        with self._conn:
            cursor = self._conn.execute(
                """
                INSERT INTO scrape_runs (started_at, status, summary_json, trigger)
                VALUES (?, 'running', ?, 'manual')
                """,
                (started_at, initial_summary),
            )
        run_id: int = cursor.lastrowid  # type: ignore[assignment]
        logger.info("scrape_run started: run_id=%d stores=%s", run_id, stores)
        return run_id

    def finish_scrape_run(
        self,
        run_id: int,
        status: str,
        products_scraped: int,
    ) -> None:
        """Update an existing scrape_runs row to mark it finished.

        Args:
            run_id:           Row to update (returned by start_scrape_run).
            status:           'success' | 'partial' | 'failed'
            products_scraped: Total product rows upserted during this run.
        """
        finished_at = self._now_iso()
        summary = json.dumps({"products_scraped": products_scraped})
        with self._conn:
            self._conn.execute(
                """
                UPDATE scrape_runs
                SET finished_at  = ?,
                    status       = ?,
                    summary_json = ?
                WHERE id = ?
                """,
                (finished_at, status, summary, run_id),
            )
        logger.info(
            "scrape_run finished: run_id=%d status=%s products=%d",
            run_id,
            status,
            products_scraped,
        )

    # ------------------------------------------------------------------
    # TASK-06 — product persistence
    # ------------------------------------------------------------------

    def upsert_product(self, product: CanonicalProduct) -> int:
        """Insert or update the products table row for (canonical_key, store).

        Uses INSERT ... ON CONFLICT DO UPDATE so the row is created on first
        sight and updated on subsequent scrapes.  The unique constraint is
        (canonical_key, store).

        Returns:
            The product_id (id column) of the inserted or updated row.
        """
        with self._conn:
            cursor = self._conn.execute(
                """
                INSERT INTO products
                    (canonical_key, brand, model, category,
                     store, raw_name, url, price_crc, in_stock, scraped_at)
                VALUES
                    (:canonical_key, :brand, :model, :category,
                     :store_id, :canonical_key, :url, :price_crc, :in_stock, :scraped_at)
                ON CONFLICT(canonical_key, store) DO UPDATE SET
                    brand      = excluded.brand,
                    model      = excluded.model,
                    url        = excluded.url,
                    price_crc  = excluded.price_crc,
                    in_stock   = excluded.in_stock,
                    scraped_at = excluded.scraped_at
                """,
                {
                    "canonical_key": product.canonical_key,
                    "brand":         product.brand,
                    "model":         product.model,
                    "category":      product.category,
                    "store_id":      product.store_id,
                    "url":           product.url,
                    "price_crc":     product.price_crc,
                    "in_stock":      1 if product.in_stock else 0,
                    "scraped_at":    product.scraped_at,
                },
            )

        # SQLite lastrowid is unreliable for ON CONFLICT DO UPDATE (returns the
        # last INSERT rowid for the connection, not the updated row's id).
        # Always use a SELECT to get the canonical product_id.
        row = self._conn.execute(
            "SELECT id FROM products WHERE canonical_key = ? AND store = ?",
            (product.canonical_key, product.store_id),
        ).fetchone()
        product_id: int = row["id"]

        logger.debug(
            "upsert_product: product_id=%d key=%s store=%s price=%d",
            product_id,
            product.canonical_key,
            product.store_id,
            product.price_crc,
        )
        return product_id

    def record_price_history(
        self,
        product_id: int,
        price_crc: int,
        store: str,
        scraped_at: str,
    ) -> None:
        """Append one row to price_history.

        A row is written on every scrape, even when the price is unchanged,
        to support 'last seen' tracking.

        Args:
            product_id: FK into products.id.
            price_crc:  Price in Costa Rican colones.
            store:      store_id (informational; not stored in price_history
                        but used for debug logging).
            scraped_at: ISO 8601 timestamp string.
        """
        # Retrieve in_stock from the products row so we keep the snapshot
        # consistent with the just-upserted state.
        row = self._conn.execute(
            "SELECT in_stock FROM products WHERE id = ?",
            (product_id,),
        ).fetchone()
        in_stock_int: int = row["in_stock"] if row else 1

        with self._conn:
            self._conn.execute(
                """
                INSERT INTO price_history (product_id, price_crc, in_stock, scraped_at)
                VALUES (?, ?, ?, ?)
                """,
                (product_id, price_crc, in_stock_int, scraped_at),
            )
        logger.debug(
            "record_price_history: product_id=%d store=%s price=%d",
            product_id,
            store,
            price_crc,
        )

    # ------------------------------------------------------------------
    # TASK-07 — comparison query
    # ------------------------------------------------------------------

    def get_comparison_table(
        self, category: str | None = None
    ) -> list[dict[str, Any]]:
        """Return comparison rows grouped by canonical_key.

        Each dict has:
            canonical_key  — string key
            brand          — brand string
            model          — model string
            category       — logical category
            stores         — dict keyed by store_id, each value:
                             {"price_crc": int, "url": str, "in_stock": bool}
            cheapest_store — store_id of the cheapest in-stock listing
                             (falls back to overall min if all are out-of-stock;
                              None if no listings exist)

        Stores that do not carry a given product simply have no entry in the
        nested ``stores`` dict (sparse — not a NULL column).

        Args:
            category: Optional filter.  If None, all categories are returned.
        """
        if category:
            rows = self._conn.execute(
                """
                SELECT canonical_key, brand, model, category,
                       store, price_crc, url, in_stock
                FROM   products
                WHERE  category = ?
                ORDER  BY canonical_key, store
                """,
                (category,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT canonical_key, brand, model, category,
                       store, price_crc, url, in_stock
                FROM   products
                ORDER  BY canonical_key, store
                """,
            ).fetchall()

        # Group by canonical_key
        groups: dict[str, dict[str, Any]] = {}
        for row in rows:
            key = row["canonical_key"]
            if key not in groups:
                groups[key] = {
                    "canonical_key": key,
                    "brand":         row["brand"],
                    "model":         row["model"],
                    "category":      row["category"],
                    "stores":        {},
                    "cheapest_store": None,
                }
            groups[key]["stores"][row["store"]] = {
                "price_crc": row["price_crc"],
                "url":       row["url"],
                "in_stock":  bool(row["in_stock"]),
            }

        # Compute cheapest_store per group
        for group in groups.values():
            listings = list(group["stores"].items())  # [(store_id, data), ...]
            if not listings:
                continue
            in_stock_listings = [
                (sid, d) for sid, d in listings if d["in_stock"]
            ]
            pool = in_stock_listings if in_stock_listings else listings
            cheapest = min(pool, key=lambda t: t[1]["price_crc"])
            group["cheapest_store"] = cheapest[0]

        return list(groups.values())

    # ------------------------------------------------------------------
    # TASK-19 — last run summary
    # ------------------------------------------------------------------

    def get_last_run(self) -> dict | None:
        """Return the most recent scrape_runs row as a dict, or None.

        Returns a dict with keys:
            run_id, stores_attempted, stores_failed, total_products,
            duration_seconds, status, started_at, finished_at
        The summary_json column is parsed and merged into the result when
        it contains the expected fields (products_scraped).
        """
        row = self._conn.execute(
            """
            SELECT id, started_at, finished_at, status, summary_json
            FROM   scrape_runs
            ORDER  BY id DESC
            LIMIT  1
            """,
        ).fetchone()

        if row is None:
            return None

        summary: dict = {}
        if row["summary_json"]:
            try:
                summary = json.loads(row["summary_json"])
            except (json.JSONDecodeError, TypeError):
                pass

        return {
            "run_id":           row["id"],
            "status":           row["status"],
            "started_at":       row["started_at"],
            "finished_at":      row["finished_at"],
            "stores_attempted": summary.get("stores_attempted"),
            "stores_failed":    summary.get("stores_failed"),
            "total_products":   summary.get("products_scraped"),
            "duration_seconds": summary.get("duration_seconds"),
        }
