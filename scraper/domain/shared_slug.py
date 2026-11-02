"""Order-aware offset for franchise members that share one source page (ADR-012).

AnimeAV1/jkanime sometimes serve a MAL cour split ("Part 1"/"Part 2") from a
single page, so several franchise members resolve to the same slug. Each
member owns a contiguous slice of that page's native numbering: the slice
starts after the official episode counts of the members that come EARLIER in
the franchise (strictly lower ``season_order``). Later members never shift
the slice, and anything that makes the boundary unknowable is reported as
undeterminable (``offset=None``) instead of being guessed.

Pure logic — no I/O. Shared by routes/ingest_routes._claimed_episode_offset
and db/simulcast.get_slug_sibling_episodes so the two cannot drift apart.
"""

from __future__ import annotations


def shares_slug(series: dict, slug: str) -> bool:
    """True when ``series`` uses ``slug`` as principal_slug or fallback_slug."""
    return series.get("principal_slug") == slug or series.get("fallback_slug") == slug


def compute_shared_slug_offset(
    siblings: list[dict], self_series: dict, slug: str
) -> dict:
    """Return the order-aware offset of ``self_series`` on the shared ``slug``.

    Args:
        siblings: Franchise members (may include ``self_series`` itself; it is
            skipped by ``id``). Each needs ``id``, ``principal_slug``,
            ``fallback_slug``, ``season_order`` and ``episode_count``.
        self_series: The series being evaluated: ``{"id", "season_order"}``
            at minimum (it may not be persisted yet during ingest).
        slug: The shared AnimeAV1/jkanime slug.

    Returns:
        ``{"offset": int | None, "earlier_ids": list[str], "reason": str | None}``.
        ``offset`` is the sum of ``episode_count`` of sharing siblings with a
        strictly lower ``season_order`` (0 when none share the slug).
        ``earlier_ids`` lists those siblings, in ``season_order`` order.
        ``offset`` is ``None`` (with ``reason``) when the boundary can't be
        trusted: NULL or tied ``season_order`` among the series and its
        sharing siblings, or an earlier sharing sibling whose official
        ``episode_count`` is NULL or 0.
    """
    self_id = self_series.get("id")
    sharing = [s for s in siblings if s.get("id") != self_id and shares_slug(s, slug)]
    if not sharing:
        return {"offset": 0, "earlier_ids": [], "reason": None}

    self_order = self_series.get("season_order")
    if self_order is None:
        return _undeterminable("series has NULL season_order")
    null_ids = [s["id"] for s in sharing if s.get("season_order") is None]
    if null_ids:
        return _undeterminable(f"sharing siblings with NULL season_order: {null_ids}")

    orders = [self_order] + [s["season_order"] for s in sharing]
    if len(set(orders)) != len(orders):
        return _undeterminable("tied season_order among sharing series")

    earlier = sorted(
        (s for s in sharing if s["season_order"] < self_order),
        key=lambda s: s["season_order"],
    )
    unknown = [s["id"] for s in earlier if not s.get("episode_count")]
    if unknown:
        return _undeterminable(
            f"earlier sharing siblings with NULL/0 episode_count: {unknown}"
        )
    return {
        "offset": sum(s["episode_count"] for s in earlier),
        "earlier_ids": [s["id"] for s in earlier],
        "reason": None,
    }


def _undeterminable(reason: str) -> dict:
    return {"offset": None, "earlier_ids": [], "reason": reason}
