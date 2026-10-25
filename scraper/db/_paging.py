"""Paginated Supabase reads (ADR-010).

Supabase/PostgREST caps every response at ~1000 rows, so a single
``.execute()`` over many series silently truncates. ``fetch_all`` pages with
``.range(start, end)`` until a short page comes back.
"""
from __future__ import annotations

from typing import Callable

DEFAULT_PAGE_SIZE = 1000


def fetch_all(build_query: Callable[[], object], page_size: int = DEFAULT_PAGE_SIZE) -> list[dict]:
    """Run a Supabase select in pages and return every row, in order.

    Args:
        build_query: A callable returning a fresh, fully-filtered select query
            (supabase-py builders mutate in place, so each page needs its own).
            The query should carry a deterministic ``.order()`` so pages do not
            overlap or skip rows.
        page_size: Rows requested per page. Must be positive.

    Returns:
        The concatenated ``data`` of every page.
    """
    if page_size <= 0:
        raise ValueError("page_size must be positive")

    rows: list[dict] = []
    start = 0
    while True:
        result = build_query().range(start, start + page_size - 1).execute()
        page = (result.data if result else None) or []
        rows.extend(page)
        if len(page) < page_size:
            return rows
        start += page_size
