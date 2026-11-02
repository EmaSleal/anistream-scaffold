"""Franchise id resolution for an ingest run (ADR-014).

Pure logic — no I/O. An ingest must join the franchise the catalog already
uses for the entries it discovers instead of minting a new id from the BFS
root, which can differ from run to run (e.g. a spin-off reachable only from
one entry).
"""

from __future__ import annotations

from collections import Counter


def _tie_key(value: str) -> tuple[int, int, str]:
    """Sort key for ties: numeric ids first (smallest int), then the rest lexicographically."""
    if value.isdigit():
        return (0, int(value), "")
    return (1, 0, value)


def pick_franchise_id(existing_franchise_ids: list[str | None]) -> str | None:
    """Return the most frequent non-null franchise_id, or ``None`` when there is none.

    Ties are broken by the smallest numeric value first; non-numeric ids
    (e.g. ``mal-123``) rank after every numeric one and compare
    lexicographically.
    """
    counts = Counter(str(f) for f in existing_franchise_ids if f not in (None, ""))
    if not counts:
        return None
    return min(counts, key=lambda f: (-counts[f], _tie_key(f)))
