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
works). No migration prerequisite: the grace/backfill plan below is anchored
to each series' own ingested episodes' ``aired_at``, not to a seeded
``simulcast_ended_at`` column, so it works on any already-finished series
without a one-time backfill step:

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

Recovery mode (ADR-011)
-----------------------
Manual, explicit recovery of finished simulcast series whose episode gaps are
past the grace window (mode=expired). Opt-in via ``--series``; without it the
legacy comparison above runs unchanged (positional ``recency_days`` included).

    # 1. Dry-run (default): prints the plan and writes
    #    scripts/output/simulcast_recovery_plan.csv. No database writes.
    cd scraper && python scripts/simulate_simulcast_refresh.py --series id1,id2

    # 2. Review the CSV: forward_inserts are capped to offset+expected (same
    #    cap as grace mode), backfill_inserts / skip_reason come from
    #    plan_backfill. Split-cour series (expected 24) show their offset.

    # 3. Apply, for the listed series only. Prints the plan, then asks y/N;
    #    --yes skips the prompt.
    cd scraper && python scripts/simulate_simulcast_refresh.py --series id1,id2 --apply [--yes]

Plan statuses: ok, nothing_to_do, ambiguous_offset (nothing planned),
no_principal_slug, not_found, scrape_failed, no_expected (episode_count unset:
backfill cannot run and the forward cap would be unbounded).

--apply WRITES: it runs only the series with status=ok in the plan of that same
run (all others are reported as skipped with their reason) by calling
simulcast_check.run_simulcast_update(..., mode="grace", backfill_mode="write"),
i.e. forward episode upserts, backfill inserts, the cooldown stamp and
refresh_simulcast_next_episodes. After each series it re-reads the episodes and
compares forward inserts against the plan; a difference prints a MISMATCH line
(nothing is reverted). One series failing does not stop the others.

Exit codes: 0 success (also dry-run, declined prompt, nothing to apply);
1 if any series failed or mismatched; 2 for --apply/--yes without --series.
"""
import argparse
import csv
import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import simulcast_check  # noqa: E402
import storage  # noqa: E402
from db._paging import fetch_all  # noqa: E402
from fetcher import fetch_anime_by_id  # noqa: E402
from db.simulcast import get_slug_sibling_episodes  # noqa: E402
from domain.simulcast import classify_recheck, plan_backfill  # noqa: E402
from scraper_animeav1 import scrape_animeav1_episodes  # noqa: E402

_REQUEST_DELAY = 0.5  # polite spacing between Jikan/MAL calls
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


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
        "episode_count, last_simulcast_check, franchise_id"
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


def _own_episode_numbers(
    series_ids: list[str],
) -> tuple[dict[str, set[int]], dict[str, str | None]]:
    """Read-only: ingested episode numbers + last-aired-episode anchor per
    series_id, via one batched SELECT.

    Returns ``(own_nums_map, last_aired_map)``: ``own_nums_map`` is this
    series' own ingested episode numbers; ``last_aired_map`` is the
    ``aired_at`` of the episode with the highest ``episode_number`` per
    series — the anchor ``classify_recheck`` uses for grace-period
    eligibility.
    """
    if not series_ids:
        return {}, {}
    client = storage.get_client()
    resp = (
        client.table("episodes")
        .select("series_id, episode_number, aired_at")
        .in_("series_id", series_ids)
        .execute()
    )
    nums: dict[str, set[int]] = {sid: set() for sid in series_ids}
    last_aired: dict[str, str | None] = {sid: None for sid in series_ids}
    max_tracker: dict[str, int] = {}
    for ep in resp.data or []:
        sid = ep.get("series_id")
        num = ep.get("episode_number")
        if sid in nums and num is not None:
            nums[sid].add(num)
            if num > max_tracker.get(sid, -1):
                max_tracker[sid] = num
                last_aired[sid] = ep.get("aired_at")
    return nums, last_aired


def build_backfill_plan_rows(
    candidates: list[dict],
    own_nums_map: dict[str, set[int]],
    last_aired_map: dict[str, str | None] | None = None,
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
            ``franchise_id`` (DB column shapes).
        own_nums_map: series_id -> this series' own ingested episode numbers
            (from ``_own_episode_numbers``).
        last_aired_map: series_id -> ``aired_at`` of this series' own
            highest-numbered ingested episode (from ``_own_episode_numbers``),
            the anchor ``classify_recheck`` uses for grace-period eligibility.
        now_utc: Reference UTC datetime (defaults to current time; pass
            explicitly in tests for determinism).

    Returns:
        A list of plain dicts, one per candidate, ready for CSV writing.
    """
    now_utc = now_utc or datetime.now(timezone.utc)
    last_aired_map = last_aired_map or {}
    rows: list[dict] = []

    for row in candidates:
        series_id = row["id"]
        own = own_nums_map.get(series_id, set())
        have = len(own)
        mode = classify_recheck(row, have, now_utc, last_aired_map.get(series_id))

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
    # The grace anchor comes from each series' own ingested episodes'
    # aired_at, so no migration/seed prerequisite applies here.
    # ------------------------------------------------------------------
    print("\nSimulating grace-period eligibility + backward gap-backfill plan "
          "(same domain functions as the cron job)...")
    own_nums_map, last_aired_map = _own_episode_numbers([c["id"] for c in candidates])
    backfill_rows = build_backfill_plan_rows(
        candidates, own_nums_map, last_aired_map, now_utc=datetime.now(timezone.utc)
    )
    backfill_path = os.path.join(out_dir, "simulcast_backfill_plan.csv")
    _write_csv(backfill_path, backfill_rows)
    print(f"Wrote {len(backfill_rows)} rows -> {backfill_path}")


# ---------------------------------------------------------------------------
# Recovery mode (ADR-011): --series / --apply
# ---------------------------------------------------------------------------

_SERIES_COLS = "id, title, mal_id, principal_slug, episode_count, franchise_id"
_RECOVERY_CSV = "simulcast_recovery_plan.csv"


def _fetch_series_rows(series_ids: list[str]) -> dict[str, dict]:
    """Read-only, paged (ADR-010): series rows keyed by id."""
    if not series_ids:
        return {}
    client = storage.get_client()
    rows = fetch_all(
        lambda: client.table("series")
        .select(_SERIES_COLS)
        .in_("id", series_ids)
        .order("id")
    )
    return {r["id"]: r for r in rows}


def _fetch_own_nums(series_ids: list[str]) -> dict[str, set[int]]:
    """Read-only, paged (ADR-010): own ingested episode numbers per series."""
    nums: dict[str, set[int]] = {sid: set() for sid in series_ids}
    if not series_ids:
        return nums
    client = storage.get_client()
    rows = fetch_all(
        lambda: client.table("episodes")
        .select("series_id, episode_number")
        .in_("series_id", series_ids)
        .order("series_id")
        .order("episode_number")
    )
    for ep in rows:
        sid, num = ep.get("series_id"), ep.get("episode_number")
        if sid in nums and num is not None:
            nums[sid].add(num)
    return nums


def _recovery_row(series_id: str, row: dict | None, status: str, **extra) -> dict:
    base = {
        "series_id": series_id,
        "title": (row or {}).get("title") or "",
        "have": 0,
        "expected": (row or {}).get("episode_count"),
        "offset": 0,
        "current_max": 0,
        "source_episodes_seen": 0,
        "forward_inserts": [],
        "backfill_inserts": [],
        "skip_reason": "",
        "status": status,
        "principal_slug": (row or {}).get("principal_slug"),
        "franchise_id": (row or {}).get("franchise_id"),
    }
    base.update(extra)
    return base


def build_recovery_plan_rows(
    series_rows_by_id: dict[str, dict],
    own_nums_map: dict[str, set[int]],
    requested_ids: list[str],
) -> list[dict]:
    """Plan recovery for explicitly requested series (read-only).

    Uses the same inputs the cron's grace path resolves: ``current_max`` is the
    max own episode number (0 if none), ``expected`` is ``episode_count``,
    offset/sibling numbers come from ``get_slug_sibling_episodes`` (only when
    ``franchise_id`` is set, else offset 0), and the backfill plan is
    ``domain.simulcast.plan_backfill``. The forward cap mirrors the inline
    expression in ``simulcast_check._process_scraped_episodes`` (grace mode):
    source numbers > current_max and <= offset + expected.

    Statuses: ok, nothing_to_do, ambiguous_offset (nothing planned at all),
    no_principal_slug, not_found, scrape_failed, and no_expected
    (``episode_count`` is NULL: plan_backfill cannot run and the forward cap
    would be unbounded, so the series is never applied).

    Ids are stripped and deduplicated; requested order is preserved.
    """
    rows: list[dict] = []
    seen: set[str] = set()
    for raw in requested_ids:
        series_id = raw.strip()
        if not series_id or series_id in seen:
            continue
        seen.add(series_id)

        row = series_rows_by_id.get(series_id)
        if row is None:
            rows.append(_recovery_row(series_id, None, "not_found"))
            continue
        own = own_nums_map.get(series_id, set())
        have, current_max = len(own), (max(own) if own else 0)
        slug = row.get("principal_slug")
        expected = row.get("episode_count")
        common = {"have": have, "current_max": current_max}
        if not slug:
            rows.append(_recovery_row(series_id, row, "no_principal_slug", **common))
            continue
        if expected is None:
            rows.append(_recovery_row(series_id, row, "no_expected", **common))
            continue

        franchise_id = row.get("franchise_id")
        offset, sibling_nums = 0, set()
        if franchise_id is not None:
            info = get_slug_sibling_episodes(franchise_id, slug, series_id)
            offset, sibling_nums = info["offset"], info["sibling_nums"]
        try:
            scraped = scrape_animeav1_episodes(slug)
        except Exception as exc:
            rows.append(_recovery_row(
                series_id, row, "scrape_failed", offset=offset,
                skip_reason=f"scrape_failed: {exc}", **common,
            ))
            continue
        source_nums = {
            ep["episode_number"] for ep in scraped if ep.get("episode_number") is not None
        }

        plan = plan_backfill(
            own=own, expected=expected, offset=offset, sibling_nums=sibling_nums,
            source_nums=source_nums, current_max=current_max,
        )
        skip_reason = plan["skip_reason"] or ""
        forward_cap = offset + expected  # source of truth: simulcast_check.py:297
        forward = sorted(n for n in source_nums if n > current_max and n <= forward_cap)
        backfill = sorted(plan["inserts"])
        if skip_reason == "ambiguous_offset":
            status, forward, backfill = "ambiguous_offset", [], []
        elif forward or backfill:
            status = "ok"
        else:
            status = "nothing_to_do"
        rows.append(_recovery_row(
            series_id, row, status, offset=offset, skip_reason=skip_reason,
            source_episodes_seen=len(source_nums), forward_inserts=forward,
            backfill_inserts=backfill, **common,
        ))
    return rows


def _fmt_nums(nums: list[int]) -> str:
    return ",".join(str(n) for n in nums)


def _print_recovery_plan(rows: list[dict]) -> None:
    for r in rows:
        print(
            f"  [{r['status']}] {r['series_id']} {r['title']!r}: have={r['have']} "
            f"expected={r['expected']} offset={r['offset']} current_max={r['current_max']} "
            f"source_seen={r['source_episodes_seen']} "
            f"forward={r['forward_inserts']} backfill={r['backfill_inserts']}"
            + (f" skip_reason={r['skip_reason']}" if r["skip_reason"] else "")
        )


def _write_recovery_csv(rows: list[dict]) -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, _RECOVERY_CSV)
    cols = ("series_id", "title", "have", "expected", "offset", "current_max",
            "source_episodes_seen", "forward_inserts", "backfill_inserts",
            "skip_reason", "status")
    _write_csv(path, [
        {
            **{c: r[c] for c in cols},
            "expected": r["expected"] if r["expected"] is not None else "",
            "forward_inserts": _fmt_nums(r["forward_inserts"]),
            "backfill_inserts": _fmt_nums(r["backfill_inserts"]),
        }
        for r in rows
    ])
    return path


def _confirm(count: int) -> bool:
    try:
        answer = input(f"Apply recovery to {count} series? [y/N] ")
    except EOFError:
        return False
    return answer.strip().lower() in ("y", "yes")


def _apply_series(row: dict) -> str:
    """Run the cron's grace routine for one planned series; returns
    ``applied`` / ``mismatch`` / ``failed``. Never reverts anything."""
    sid, pre_max = row["series_id"], row["current_max"]
    try:
        pre_own = _fetch_own_nums([sid])[sid]
    except Exception as exc:
        print(f"  FAILED {sid}: pre-apply read error: {exc}")
        return "failed"
    try:
        added = simulcast_check.run_simulcast_update(
            sid, row["principal_slug"], pre_max,
            mode="grace", backfill_mode="write",
            franchise_id=row["franchise_id"], expected=row["expected"],
        )
    except Exception as exc:
        print(f"  FAILED {sid}: {exc}")
        return "failed"

    planned_fwd = row["forward_inserts"]
    try:
        new = _fetch_own_nums([sid])[sid] - pre_own
    except Exception as exc:
        print(f"  MISMATCH {sid}: could not verify inserted episodes ({exc})")
        return "mismatch"
    actual_fwd = sorted(n for n in new if n > pre_max)
    actual_back = sorted(n for n in new if n < pre_max)
    print(f"  {sid}: forward added={added} {actual_fwd}; backfill added={actual_back} "
          f"(planned backfill {row['backfill_inserts']})")
    if actual_fwd != planned_fwd or added != len(planned_fwd):
        print(f"  MISMATCH {sid}: planned forward {planned_fwd} vs inserted "
              f"{actual_fwd} (returned count {added})")
        return "mismatch"
    return "applied"


def recovery_main(series_ids: list[str], apply: bool = False, assume_yes: bool = False) -> int:
    """Plan (always) and optionally apply recovery. Returns the exit code."""
    requested = list(dict.fromkeys(s.strip() for s in series_ids if s.strip()))
    print(f"Recovery plan for {len(requested)} series (dry-run reads only)...")
    rows = build_recovery_plan_rows(
        _fetch_series_rows(requested), _fetch_own_nums(requested), requested
    )
    _print_recovery_plan(rows)
    print(f"Wrote {len(rows)} rows -> {_write_recovery_csv(rows)}")
    if not apply:
        return 0

    ok_rows = [r for r in rows if r["status"] == "ok"]
    skipped = [r for r in rows if r["status"] != "ok"]
    for r in skipped:
        print(f"  skipped {r['series_id']}: {r['status']}"
              + (f" ({r['skip_reason']})" if r["skip_reason"] else ""))
    if not ok_rows:
        print("No series with status=ok; nothing to apply.")
        return 0
    if not assume_yes and not _confirm(len(ok_rows)):
        print("Aborted, nothing written.")
        return 0

    outcomes = [_apply_series(r) for r in ok_rows]
    failed, mismatch = outcomes.count("failed"), outcomes.count("mismatch")
    print(f"Summary: applied={outcomes.count('applied')} mismatch={mismatch} "
          f"failed={failed} skipped={len(skipped)}")
    return 1 if (failed or mismatch) else 0


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Simulcast refresh diagnostic and recovery tool (see module docstring)."
    )
    parser.add_argument("recency_days", nargs="?", type=int, default=14,
                        help="legacy comparison window in days (default 14)")
    parser.add_argument("--series", help="comma-separated series ids to plan recovery for")
    parser.add_argument("--apply", action="store_true",
                        help="write the planned recovery (requires --series)")
    parser.add_argument("--yes", action="store_true",
                        help="skip the interactive confirmation before --apply")
    args = parser.parse_args(argv)

    if args.series is None:
        if args.apply or args.yes:
            parser.error("--apply/--yes require --series")
        main(args.recency_days)
        return 0
    ids = [s.strip() for s in args.series.split(",") if s.strip()]
    if not ids:
        parser.error("--series needs at least one series id")
    return recovery_main(ids, apply=args.apply, assume_yes=args.yes)


if __name__ == "__main__":
    sys.exit(cli())
