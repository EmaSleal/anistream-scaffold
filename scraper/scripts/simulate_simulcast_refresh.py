"""Dry-run comparison of the current simulcast re-check gate vs. a proposed
episode-count-aware gate — without touching Supabase.

Bug being diagnosed: ``get_due_simulcast_series()`` (db/simulcast.py) only
selects rows where ``is_simulcast=True``. That flag is set purely from
Jikan's ``airing`` field (domain/simulcast.resolve_simulcast_status), which
flips to False as soon as Jikan reports "Finished Airing" — often before
AnimeAV1 has actually published the final episode (AnimeAV1 typically lags
2-6h behind the Japanese broadcast). Once the flag flips False, the series is
excluded from the cron job and from the page-visit re-check triggers
forever, so the trailing episode can be permanently missed unless an admin
manually re-runs a full /ingest.

This script only performs read-only Supabase SELECTs, read-only Jikan/MAL
GETs, and a read-only AnimeAV1 scrape — it never calls
update_simulcast_fields(), upsert_series(), insert_episode_if_absent(), or
any other write path. Safe to run repeatedly against production data.

Usage (must run with cwd=scraper/, so config.py's relative .env.local load
works). Requires migration 004 (simulcast_ended_at) to already be applied —
see the design doc's rollout order:

    cd scraper && python scripts/simulate_simulcast_refresh.py [recency_days]

``recency_days`` (default 14) bounds how far back a now-finished series'
``last_simulcast_check`` can be and still be considered "recently finished"
enough to include in the comparison (series that flipped off the simulcast
flag ages ago are out of scope for this diagnostic).

Writes two CSVs to scripts/output/:
  - simulcast_refresh_comparison.csv: the original is_simulcast-only gate vs.
    an episode-count-aware gate (diagnostic, unchanged from before this PR).
  - simulcast_backfill_plan.csv: grace-period eligibility (classify_recheck)
    + backward gap-backfill plan (plan_backfill) per candidate, using the
    exact same domain functions the real cron job calls — see
    build_backfill_plan_rows(). This is the simulcast-gap-recovery Phase 3
    CSV the admin reviews before SIMULCAST_GRACE_ENABLED /
    SIMULCAST_BACKFILL_MODE are flipped on.
"""
import csv
import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import storage  # noqa: E402
from fetcher import fetch_anime_by_id  # noqa: E402
from db.simulcast import get_slug_sibling_episodes  # noqa: E402
from domain.simulcast import classify_recheck, plan_backfill  # noqa: E402
from scraper_animeav1 import scrape_animeav1_episodes  # noqa: E402

_REQUEST_DELAY = 0.5  # polite spacing between Jikan/MAL calls


def _fetch_candidates(recency_days: int) -> list[dict]:
    """Read-only: series currently flagged simulcast, plus recently-finished ones.

    Two SELECTs, no writes:
      1. is_simulcast=True (what the current gate already includes).
      2. is_simulcast=False but principal_slug present and last_simulcast_check
         within ``recency_days`` (candidates the current gate just dropped).
    """
    client = storage.get_client()
    select_cols = (
        "id, title, mal_id, kitsu_id, is_simulcast, principal_slug, "
        "episode_count, last_simulcast_check, simulcast_ended_at, franchise_id"
    )

    airing_resp = (
        client.table("series")
        .select(select_cols)
        .eq("is_simulcast", True)
        .not_.is_("principal_slug", "null")
        .not_.is_("mal_id", "null")
        .execute()
    )
    rows = list(airing_resp.data or [])

    recently_finished_resp = (
        client.table("series")
        .select(select_cols)
        .eq("is_simulcast", False)
        .not_.is_("principal_slug", "null")
        .not_.is_("mal_id", "null")
        .not_.is_("last_simulcast_check", "null")
        .execute()
    )
    cutoff = datetime.now(timezone.utc) - timedelta(days=recency_days)
    for row in recently_finished_resp.data or []:
        last_check = row.get("last_simulcast_check")
        try:
            last_dt = datetime.fromisoformat(last_check)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if last_dt >= cutoff:
            rows.append(row)

    unique = {r["id"]: r for r in rows}
    return list(unique.values())


def _ingested_episode_counts(series_ids: list[str]) -> dict[str, int]:
    """Read-only: count ingested episodes per series_id via one batched SELECT."""
    if not series_ids:
        return {}
    client = storage.get_client()
    resp = (
        client.table("episodes")
        .select("series_id")
        .in_("series_id", series_ids)
        .execute()
    )
    counts: dict[str, int] = {sid: 0 for sid in series_ids}
    for ep in resp.data or []:
        sid = ep.get("series_id")
        if sid in counts:
            counts[sid] += 1
    return counts


def _own_episode_numbers(series_ids: list[str]) -> dict[str, set[int]]:
    """Read-only: ingested episode numbers per series_id via one batched SELECT."""
    if not series_ids:
        return {}
    client = storage.get_client()
    resp = (
        client.table("episodes")
        .select("series_id, episode_number")
        .in_("series_id", series_ids)
        .execute()
    )
    nums: dict[str, set[int]] = {sid: set() for sid in series_ids}
    for ep in resp.data or []:
        sid = ep.get("series_id")
        num = ep.get("episode_number")
        if sid in nums and num is not None:
            nums[sid].add(num)
    return nums


def build_backfill_plan_rows(
    candidates: list[dict],
    own_nums_map: dict[str, set[int]],
    now_utc: datetime | None = None,
) -> list[dict]:
    """Simulate the grace-period eligibility + backward gap-backfill decision
    for each candidate series using the SAME ``domain.simulcast.classify_recheck``
    / ``domain.simulcast.plan_backfill`` functions the real cron job
    (``jobs/simulcast_job.py`` -> ``simulcast_check.py``) calls — so this CSV
    validates the exact code that will later write, per the design doc.

    Read-only: performs exactly one AnimeAV1 scrape per "airing"/"grace"
    candidate (needed to know the shared source listing for ``plan_backfill``)
    and a read-only sibling-offset lookup via ``get_slug_sibling_episodes``.
    "expired" candidates are never scraped here — mirroring production, where
    they are handled entirely by ``get_expired_gap_candidates`` +
    ``mark_gap_unresolved`` with no AnimeAV1 call. Never performs any
    Supabase write.

    Args:
        candidates: Plain dicts with ``id``, ``title``, ``mal_id``,
            ``principal_slug``, ``episode_count``, ``is_simulcast``,
            ``simulcast_ended_at``, ``franchise_id`` (DB column shapes).
        own_nums_map: series_id -> this series' own ingested episode numbers
            (from ``_own_episode_numbers``).
        now_utc: Reference UTC datetime (defaults to current time; pass
            explicitly in tests for determinism).

    Returns:
        A list of plain dicts, one per candidate, ready for CSV writing.
    """
    now_utc = now_utc or datetime.now(timezone.utc)
    rows: list[dict] = []

    for row in candidates:
        series_id = row["id"]
        own = own_nums_map.get(series_id, set())
        have = len(own)
        mode = classify_recheck(row, have, now_utc)

        expected = row.get("episode_count")
        slug = row.get("principal_slug")

        offset = 0
        missing_inserts: list[int] = []
        skip_reason = ""
        source_seen: int | str = ""

        if mode in ("airing", "grace") and expected is not None and slug:
            sibling_info = get_slug_sibling_episodes(row.get("franchise_id"), slug, series_id)
            offset = sibling_info["offset"]
            sibling_nums = sibling_info["sibling_nums"]
            try:
                scraped = scrape_animeav1_episodes(slug)
            except Exception:
                scraped = []
            source_nums = {
                ep["episode_number"] for ep in scraped if ep.get("episode_number") is not None
            }
            source_seen = len(source_nums)
            current_max = max(own) if own else 0
            plan = plan_backfill(
                own=own,
                expected=expected,
                offset=offset,
                sibling_nums=sibling_nums,
                source_nums=source_nums,
                current_max=current_max,
            )
            missing_inserts = plan["inserts"]
            skip_reason = plan["skip_reason"] or ""
        elif mode == "expired":
            # Mirrors production: expired rows are surfaced via
            # get_expired_gap_candidates + mark_gap_unresolved, never scraped
            # or backfilled here.
            skip_reason = "grace_period_expired_no_scrape"

        rows.append({
            "series_id": series_id,
            "title": row.get("title") or "",
            "mal_id": row.get("mal_id"),
            "mode": mode or "not_eligible",
            "have": have,
            "expected": expected if expected is not None else "",
            "offset": offset,
            "missing_inserts": ",".join(str(n) for n in missing_inserts),
            "skip_reason": skip_reason,
            "source_episodes_seen": source_seen,
        })

    return rows


def _write_csv(path: str, rows: list[dict]) -> None:
    if not rows:
        print(f"  (no rows for {path})")
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, restval="")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main(recency_days: int = 14) -> None:
    print(f"Fetching candidates (is_simulcast=True, or flipped off within {recency_days}d)...")
    candidates = _fetch_candidates(recency_days)
    print(f"  {len(candidates)} candidate series found")

    ingested_counts = _ingested_episode_counts([c["id"] for c in candidates])

    out_rows: list[dict] = []
    flagged_count = 0

    for i, row in enumerate(candidates, start=1):
        series_id = row["id"]
        mal_id = row.get("mal_id")
        title = row.get("title") or ""
        is_simulcast_db = bool(row.get("is_simulcast"))
        episodes_ingested = ingested_counts.get(series_id, 0)

        print(f"  [{i}/{len(candidates)}] mal_id={mal_id} title={title!r}...")

        jikan_airing_now: bool | None = None
        episodes_expected: int | None = row.get("episode_count")
        jikan_error = ""
        try:
            jikan_data = fetch_anime_by_id(mal_id)
            jikan_airing_now = bool(jikan_data.get("airing", False))
            jikan_eps = jikan_data.get("episodes")
            if jikan_eps:
                episodes_expected = int(jikan_eps)
        except Exception as exc:  # fail-open, same as refresh_series_from_jikan
            jikan_error = str(exc)
        time.sleep(_REQUEST_DELAY)

        if episodes_expected is not None:
            episodes_missing = max(episodes_expected - episodes_ingested, 0)
        else:
            episodes_missing = None

        current_would_recheck = is_simulcast_db
        proposed_would_recheck = bool(episodes_missing and episodes_missing > 0)
        flagged_as_bug = (not current_would_recheck) and proposed_would_recheck

        if flagged_as_bug:
            flagged_count += 1

        out_rows.append({
            "series_id": series_id,
            "title": title,
            "mal_id": mal_id,
            "is_simulcast_db": is_simulcast_db,
            "jikan_airing_now": jikan_airing_now,
            "jikan_error": jikan_error,
            "episodes_ingested": episodes_ingested,
            "episodes_expected": episodes_expected if episodes_expected is not None else "",
            "episodes_missing": episodes_missing if episodes_missing is not None else "",
            "last_simulcast_check": row.get("last_simulcast_check") or "",
            "current_would_recheck": current_would_recheck,
            "proposed_would_recheck": proposed_would_recheck,
            "flagged_as_bug": flagged_as_bug,
        })

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "simulcast_refresh_comparison.csv")
    _write_csv(out_path, out_rows)

    print(f"\nWrote {len(out_rows)} rows -> {out_path}")
    print(f"Flagged as hitting the bug (current=skip, proposed=recheck, episodes missing): {flagged_count}")

    # ------------------------------------------------------------------
    # Simulcast gap recovery (Phase 3): simulate grace-period eligibility +
    # backward gap-backfill using the SAME domain.simulcast.classify_recheck /
    # plan_backfill functions the cron job calls. Read-only — no DB writes.
    # Requires migration 004 (simulcast_ended_at) to already be applied;
    # see design rollout step 1/2.
    # ------------------------------------------------------------------
    print("\nSimulating grace-period eligibility + backward gap-backfill plan "
          "(same domain functions as the cron job)...")
    own_nums_map = _own_episode_numbers([c["id"] for c in candidates])
    backfill_rows = build_backfill_plan_rows(candidates, own_nums_map, now_utc=datetime.now(timezone.utc))
    backfill_path = os.path.join(out_dir, "simulcast_backfill_plan.csv")
    _write_csv(backfill_path, backfill_rows)
    print(f"Wrote {len(backfill_rows)} rows -> {backfill_path}")


if __name__ == "__main__":
    recency_arg = int(sys.argv[1]) if len(sys.argv) > 1 else 14
    main(recency_arg)
