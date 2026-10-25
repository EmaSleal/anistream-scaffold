"""Supabase query helpers for simulcast-related fields on the series table.

All functions return raw dicts from the DB (snake_case). Callers are
responsible for any domain transformations.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import storage
from db._paging import fetch_all
from db.series import get_series_by_franchise
from domain.simulcast import classify_recheck

_CR_TZ = ZoneInfo("America/Costa_Rica")


def get_series_simulcast_data(series_id: str) -> dict | None:
    """Return the simulcast-relevant columns for a series row.

    Fetches: id, kitsu_id, broadcast_day, broadcast_time, broadcast_timezone,
             episode_count, last_simulcast_check, principal_slug.

    Args:
        series_id: The series ``id`` (slug-based primary key).

    Returns:
        A dict with the listed keys, or None if no row matches.
    """
    client = storage.get_client()
    result = (
        client.table("series")
        .select(
            "id, kitsu_id, broadcast_day, broadcast_time, broadcast_timezone, "
            "episode_count, last_simulcast_check, principal_slug"
        )
        .eq("id", series_id)
        .maybe_single()
        .execute()
    )
    return result.data if result else None


def update_simulcast_fields(series_id: str, fields: dict) -> None:
    """PATCH only the provided fields plus last_simulcast_check = now().

    Args:
        series_id: The series ``id`` to update.
        fields:    A dict of column→value pairs to update. Only keys present
                   in this dict are written; ``last_simulcast_check`` is always
                   set to the current UTC timestamp.
    """
    client = storage.get_client()
    payload = {
        **fields,
        "last_simulcast_check": datetime.now(timezone.utc).isoformat(),
    }
    client.table("series").update(payload).eq("id", series_id).execute()


# ---------------------------------------------------------------------------
# Simulcast job helpers
# ---------------------------------------------------------------------------


def _cr_date(iso_str: str) -> date | None:
    """Parse an ISO 8601 string into a calendar date in Costa Rica timezone.

    Args:
        iso_str: An ISO 8601 timestamp string (e.g. ``"2026-06-27T10:00:00+00:00"``).

    Returns:
        The local date in ``America/Costa_Rica``, or None when the string
        cannot be parsed.
    """
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(_CR_TZ).date()
    except Exception:
        return None


def get_due_simulcast_series() -> list[dict]:
    """Return simulcast series not checked within the last 4 hours.

    Fetches all rows where ``is_simulcast=True`` and ``principal_slug IS NOT
    NULL`` (AnimeAV1 integration marker), then applies a Python-side filter
    that excludes any series whose ``last_simulcast_check`` is within the
    4-hour cooldown window. The time-based cooldown (rather than once-per-day)
    lets the job re-check later in the same day when AnimeAV1 hasn't posted
    the episode yet at the time of the first pass.

    One paged ``episodes`` read (``db._paging.fetch_all``, ADR-010) resolves
    ``max_episode_number`` for all surviving candidates.

    Grace-period extension (``SIMULCAST_GRACE_ENABLED=1``, default OFF):
    when enabled, the candidate selection is routed through
    ``domain.simulcast.classify_recheck`` instead of the hard ``is_simulcast``
    filter alone — this is what lets a series stop being excluded the instant
    ``is_simulcast`` flips False (rather than permanently, as a hard SQL
    ``eq`` filter would), while still respecting the same 4-hour cooldown for
    both ``"airing"`` and ``"grace"`` classifications. The grace clock is
    anchored to the ``aired_at`` of each series' own highest-numbered
    ingested episode (not a stamped status-transition timestamp), so
    eligibility falls straight out of the episodes already ingested. When
    the flag is off, behavior is byte-for-byte identical to before this
    change.

    Returns:
        A list of dicts with keys: ``id``, ``principal_slug``, ``mal_id``,
        ``kitsu_id``, ``max_episode_number`` (int or None). When
        ``SIMULCAST_GRACE_ENABLED=1``, each dict additionally has: ``mode``
        (``"airing"`` or ``"grace"``), ``have`` (int), ``expected``
        (int or None), ``franchise_id`` (str or None).
    """
    client = storage.get_client()
    grace_enabled = os.getenv("SIMULCAST_GRACE_ENABLED", "0") == "1"

    select_cols = "id, principal_slug, mal_id, kitsu_id, last_simulcast_check"
    if grace_enabled:
        select_cols += ", is_simulcast, episode_count, franchise_id"

    def _series_query():
        query = client.table("series").select(select_cols).not_.is_("principal_slug", "null")
        if not grace_enabled:
            # Today's exact behavior: only series still flagged as airing.
            query = query.eq("is_simulcast", True)
        return query.order("id")

    # Paged (ADR-010): PostgREST caps each response at ~1000 rows.
    rows = fetch_all(_series_query)

    now_utc = datetime.now(timezone.utc)
    _cooldown = timedelta(hours=4)

    # Grace mode needs each row's own ingested episode numbers (and the
    # aired_at of the highest-numbered one, to anchor classify_recheck) up
    # front; this also doubles as the max_episode_number source later, so no
    # second episodes query is needed in this branch.
    own_nums_map: dict[str, set[int]] = {}
    last_aired_map: dict[str, str | None] = {}
    if grace_enabled and rows:
        row_ids = [r["id"] for r in rows]
        eps_rows = fetch_all(
            lambda: client.table("episodes")
            .select("series_id, episode_number, aired_at")
            .in_("series_id", row_ids)
            .order("series_id")
            .order("episode_number")
        )
        own_nums_map = {rid: set() for rid in row_ids}
        last_aired_map = {rid: None for rid in row_ids}
        max_num_tracker: dict[str, int] = {}
        for ep in eps_rows:
            sid = ep.get("series_id")
            ep_num = ep.get("episode_number")
            if sid in own_nums_map and ep_num is not None:
                own_nums_map[sid].add(ep_num)
                if ep_num > max_num_tracker.get(sid, -1):
                    max_num_tracker[sid] = ep_num
                    last_aired_map[sid] = ep.get("aired_at")

    # Filter out series checked within the last 4 hours.
    # A time-based cooldown (rather than once-per-day) lets the scheduler
    # re-check later the same day when an episode wasn't on AnimeAV1 yet at
    # the time of the previous check (AnimeAV1 typically lags 2–6 h after
    # the Japanese broadcast). The same cooldown applies to grace rows.
    candidates = []
    modes: dict[str, str] = {}
    for row in rows:
        if grace_enabled:
            have = len(own_nums_map.get(row["id"], set()))
            mode = classify_recheck(row, have, now_utc, last_aired_map.get(row["id"]))
            if mode not in ("airing", "grace"):
                continue  # "expired" or None — not due for a recheck here
        else:
            # SQL already filtered to is_simulcast=True rows above — no
            # Python-side re-check needed (and the "off" select doesn't even
            # fetch the is_simulcast column, to keep the query identical to
            # before this change).
            mode = "airing"

        last_check = row.get("last_simulcast_check")
        if last_check is not None:
            try:
                last_dt = datetime.fromisoformat(last_check)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                if now_utc - last_dt < _cooldown:
                    continue  # checked within cooldown window — skip
            except Exception:
                pass

        modes[row["id"]] = mode
        candidates.append(row)

    if not candidates:
        return []

    candidate_ids = [c["id"] for c in candidates]

    if grace_enabled:
        # Derive max_episode_number from the own_nums_map already fetched above.
        max_ep_map: dict[str, int | None] = {
            cid: (max(own_nums_map[cid]) if own_nums_map.get(cid) else None)
            for cid in candidate_ids
        }
    else:
        # Resolve max_episode_number per candidate via one paged episodes read.
        eps_rows = fetch_all(
            lambda: client.table("episodes")
            .select("series_id, episode_number")
            .in_("series_id", candidate_ids)
            .order("series_id")
            .order("episode_number")
        )
        max_ep_map = {cid: None for cid in candidate_ids}
        for ep in eps_rows:
            sid = ep.get("series_id")
            ep_num = ep.get("episode_number")
            if sid in max_ep_map and ep_num is not None:
                current = max_ep_map[sid]
                if current is None or ep_num > current:
                    max_ep_map[sid] = ep_num

    out = []
    for row in candidates:
        item = {
            "id": row["id"],
            "principal_slug": row["principal_slug"],
            "mal_id": row.get("mal_id"),
            "kitsu_id": row.get("kitsu_id"),
            "max_episode_number": max_ep_map.get(row["id"]),
        }
        if grace_enabled:
            item["mode"] = modes[row["id"]]
            item["have"] = len(own_nums_map.get(row["id"], set()))
            item["expected"] = row.get("episode_count")
            item["franchise_id"] = row.get("franchise_id")
        out.append(item)
    return out


# ---------------------------------------------------------------------------
# Simulcast gap recovery: slug-sibling offset + unresolved-gap surfacing.
# ---------------------------------------------------------------------------


def get_slug_sibling_episodes(
    franchise_id: str | None, slug: str, exclude_id: str
) -> dict:
    """Return the episode offset and claimed episode numbers for franchise
    siblings that share ``slug`` as ``principal_slug`` or ``fallback_slug``.

    Mirrors ``routes.ingest_routes._claimed_episode_offset``'s selection
    logic exactly (guarded by a parity test in ``test_db_simulcast.py``) so
    the two never silently drift apart: franchise members excluding
    ``exclude_id``, whose ``principal_slug`` or ``fallback_slug`` equals
    ``slug``.

    Args:
        franchise_id: The franchise to scan, or None (no franchise → 0).
        slug: The shared AnimeAV1/jkanime slug to match against.
        exclude_id: The series being evaluated — never counted as its own
            sibling.

    Returns:
        ``{"offset": int, "sibling_nums": set[int]}``. ``offset`` is the sum
        of episode counts across matching siblings (same semantics as
        ``_claimed_episode_offset``). ``sibling_nums`` is the union of those
        siblings' actual ingested episode numbers, in the shared source's
        native numbering.
    """
    if not franchise_id:
        return {"offset": 0, "sibling_nums": set()}

    siblings = get_series_by_franchise(franchise_id)
    matching_ids = [
        s["id"]
        for s in siblings
        if s.get("id") != exclude_id
        and (s.get("principal_slug") == slug or s.get("fallback_slug") == slug)
    ]
    if not matching_ids:
        return {"offset": 0, "sibling_nums": set()}

    client = storage.get_client()
    rows = fetch_all(
        lambda: client.table("episodes")
        .select("series_id, episode_number")
        .in_("series_id", matching_ids)
        .order("series_id")
        .order("episode_number")
    )
    sibling_nums = {
        r["episode_number"] for r in rows if r.get("episode_number") is not None
    }
    return {"offset": len(rows), "sibling_nums": sibling_nums}


def mark_gap_unresolved(series_id: str, missing_episodes: list[int]) -> None:
    """Record an unresolved episode gap for admin review.

    Sets ``gap_unresolved_at = now()`` and ``gap_missing_episodes`` to the
    sorted list of missing episode numbers. Idempotent at the SQL level —
    callers should still gate repeat calls via
    ``get_expired_gap_candidates()``'s ``gap_unresolved_at IS NULL`` filter
    so admins aren't re-notified every cron run for the same gap.

    Args:
        series_id: The series ``id`` to update.
        missing_episodes: The episode numbers believed to be missing.
    """
    client = storage.get_client()
    client.table("series").update(
        {
            "gap_unresolved_at": datetime.now(timezone.utc).isoformat(),
            "gap_missing_episodes": sorted(missing_episodes),
        }
    ).eq("id", series_id).execute()


def get_expired_gap_candidates() -> list[dict]:
    """Return series whose grace period has expired with an unresolved gap.

    Candidate selection (SQL-side): ``is_simulcast=False``,
    ``episode_count IS NOT NULL``, and ``gap_unresolved_at IS NULL`` (not
    already surfaced). No longer requires a seeded ``simulcast_ended_at`` —
    the grace clock is anchored to the ``aired_at`` of each series' own
    highest-numbered ingested episode, computed below from a live episodes
    query, so any already-finished series with a real gap is caught without
    depending on a one-time backfill seed. The actual day-threshold decision
    is delegated to ``domain.simulcast.classify_recheck`` (same pure
    function used by ``get_due_simulcast_series``) so that logic is never
    duplicated here — only rows classified ``"expired"`` are returned.

    Returns:
        A list of dicts with keys: ``id``, ``have`` (int), ``expected``
        (int), ``own_episode_numbers`` (set[int] — this series' own
        ingested episode_number values, for the caller to compute
        ``gap_missing_episodes``).
    """
    client = storage.get_client()
    # Paged (ADR-010): PostgREST caps each response at ~1000 rows.
    rows = fetch_all(
        lambda: client.table("series")
        .select("id, is_simulcast, episode_count")
        .eq("is_simulcast", False)
        .not_.is_("episode_count", "null")
        .is_("gap_unresolved_at", "null")
        .order("id")
    )
    if not rows:
        return []

    series_ids = [r["id"] for r in rows]
    eps_rows = fetch_all(
        lambda: client.table("episodes")
        .select("series_id, episode_number, aired_at")
        .in_("series_id", series_ids)
        .order("series_id")
        .order("episode_number")
    )
    own_nums_map: dict[str, set[int]] = {sid: set() for sid in series_ids}
    last_aired_map: dict[str, str | None] = {sid: None for sid in series_ids}
    max_num_tracker: dict[str, int] = {}
    for ep in eps_rows:
        sid = ep.get("series_id")
        num = ep.get("episode_number")
        if sid in own_nums_map and num is not None:
            own_nums_map[sid].add(num)
            if num > max_num_tracker.get(sid, -1):
                max_num_tracker[sid] = num
                last_aired_map[sid] = ep.get("aired_at")

    now_utc = datetime.now(timezone.utc)
    candidates = []
    for row in rows:
        own_nums = own_nums_map.get(row["id"], set())
        have = len(own_nums)
        mode = classify_recheck(row, have, now_utc, last_aired_map.get(row["id"]))
        if mode == "expired":
            candidates.append(
                {
                    "id": row["id"],
                    "have": have,
                    "expected": row["episode_count"],
                    "own_episode_numbers": own_nums,
                }
            )
    return candidates


def get_unresolved_gaps() -> list[dict]:
    """Return series with an unresolved episode gap, for admin review.

    Candidate selection: ``gap_unresolved_at IS NOT NULL`` (set by
    ``mark_gap_unresolved`` once a series' grace period expires with a real
    gap), ordered most-recently-surfaced first.

    Returns:
        A list of dicts with keys: ``id``, ``title``, ``gap_unresolved_at``,
        ``gap_missing_episodes`` (list[int] or None), ``episode_count``,
        ``principal_slug``.
    """
    client = storage.get_client()
    result = (
        client.table("series")
        .select("id, title, gap_unresolved_at, gap_missing_episodes, episode_count, principal_slug")
        .not_.is_("gap_unresolved_at", "null")
        .order("gap_unresolved_at", desc=True)
        .execute()
    )
    return result.data or []
