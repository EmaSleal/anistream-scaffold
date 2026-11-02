"""Read-only audit of ADR-012 shared-slug offsets against the live catalog.

For every franchise in which two or more series share a principal_slug or
fallback_slug, compares the OLD offset (order-blind count of the other sharing
series' ingested episode rows) with the NEW offset from
``domain.shared_slug.compute_shared_slug_offset`` and checks it against the
series' actual first ingested episode.

Run from the scraper root:  python scripts/audit_shared_slug_offsets.py

Prints one line per (series, shared slug) and writes
``scripts/output/shared_slug_offset_audit.csv`` with: franchise_id, series_id,
title, season_order, episode_count, slug, old_offset, new_offset, own_min_episode,
own_max_episode, verdict.

Verdicts:
  match      own_min_episode == new_offset + 1, or the series has no episodes
             and new_offset is defined
  differs    new_offset is defined but the series' first episode isn't new_offset + 1
  ambiguous  new_offset is undeterminable (new_offset shows the reason)

Strictly read-only: it issues SELECTs only (paginated via db._paging.fetch_all,
ADR-010) and never writes to the database.
"""
import csv
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import storage  # noqa: E402
from db._paging import fetch_all  # noqa: E402
from domain.shared_slug import compute_shared_slug_offset, shares_slug  # noqa: E402

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
_CSV_NAME = "shared_slug_offset_audit.csv"
COLUMNS = (
    "franchise_id", "series_id", "title", "season_order", "episode_count", "slug",
    "old_offset", "new_offset", "own_min_episode", "own_max_episode", "verdict",
)
_ID_CHUNK = 100  # keep the IN (...) filter's URL short


def _fetch_series() -> list[dict]:
    client = storage.get_client()
    return fetch_all(
        lambda: client.table("series")
        .select("id, title, franchise_id, season_order, episode_count, principal_slug, fallback_slug")
        .not_.is_("franchise_id", "null")
        .order("id")
    )


def _fetch_episode_numbers(series_ids: list[str]) -> dict[str, list[int]]:
    """Ingested episode numbers per series id, read in paginated id chunks."""
    client = storage.get_client()
    nums: dict[str, list[int]] = defaultdict(list)
    for i in range(0, len(series_ids), _ID_CHUNK):
        chunk = series_ids[i:i + _ID_CHUNK]
        rows = fetch_all(
            lambda chunk=chunk: client.table("episodes")
            .select("series_id, episode_number")
            .in_("series_id", chunk)
            .order("series_id")
            .order("episode_number")
        )
        for r in rows:
            if r.get("episode_number") is not None:
                nums[r["series_id"]].append(r["episode_number"])
    return nums


def find_shared_groups(series_rows: list[dict]) -> list[tuple[str, str, list[dict]]]:
    """Return ``(franchise_id, slug, members)`` for every slug shared by 2+
    series of one franchise (principal_slug or fallback_slug), in a stable order."""
    by_franchise: dict[str, list[dict]] = defaultdict(list)
    for s in series_rows:
        if s.get("franchise_id"):
            by_franchise[s["franchise_id"]].append(s)
    groups = []
    for franchise_id in sorted(by_franchise):
        members = by_franchise[franchise_id]
        slugs = sorted({
            slug for s in members
            for slug in (s.get("principal_slug"), s.get("fallback_slug")) if slug
        })
        for slug in slugs:
            sharing = [s for s in members if shares_slug(s, slug)]
            if len(sharing) >= 2:
                groups.append((franchise_id, slug, sharing))
    return groups


def build_audit_rows(
    series_rows: list[dict], episode_nums: dict[str, list[int]]
) -> list[dict]:
    """Pure: build the audit rows from series rows and per-series episode numbers."""
    by_franchise: dict[str, list[dict]] = defaultdict(list)
    for s in series_rows:
        if s.get("franchise_id"):
            by_franchise[s["franchise_id"]].append(s)

    rows: list[dict] = []
    for franchise_id, slug, sharing in find_shared_groups(series_rows):
        siblings = by_franchise[franchise_id]
        for s in sorted(sharing, key=lambda r: (r.get("season_order") is None, r.get("season_order") or 0, r["id"])):
            # Previous logic: order-blind count of the other sharers' ingested rows.
            old_offset = sum(len(episode_nums.get(o["id"], [])) for o in sharing if o["id"] != s["id"])
            result = compute_shared_slug_offset(
                siblings, {"id": s["id"], "season_order": s.get("season_order")}, slug
            )
            new_offset = result["offset"]
            own = episode_nums.get(s["id"], [])
            own_min, own_max = (min(own), max(own)) if own else ("", "")
            if new_offset is None:
                verdict, shown = "ambiguous", f"ambiguous: {result['reason']}"
            else:
                shown = new_offset
                if not own or own_min == new_offset + 1:
                    verdict = "match"
                else:
                    verdict = "differs"
            rows.append({
                "franchise_id": franchise_id,
                "series_id": s["id"],
                "title": s.get("title") or "",
                "season_order": "" if s.get("season_order") is None else s["season_order"],
                "episode_count": "" if s.get("episode_count") is None else s["episode_count"],
                "slug": slug,
                "old_offset": old_offset,
                "new_offset": shown,
                "own_min_episode": own_min,
                "own_max_episode": own_max,
                "verdict": verdict,
            })
    return rows


def _write_csv(rows: list[dict]) -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, _CSV_NAME)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def main() -> int:
    series_rows = _fetch_series()
    groups = find_shared_groups(series_rows)
    ids = sorted({s["id"] for _, _, members in groups for s in members})
    rows = build_audit_rows(series_rows, _fetch_episode_numbers(ids))

    for r in rows:
        print(
            f"  [{r['verdict']}] franchise={r['franchise_id']} {r['series_id']} {r['title']!r} "
            f"order={r['season_order']} count={r['episode_count']} slug={r['slug']} "
            f"old={r['old_offset']} new={r['new_offset']} "
            f"own={r['own_min_episode']}..{r['own_max_episode']}"
        )
    counts = defaultdict(int)
    for r in rows:
        counts[r["verdict"]] += 1
    print(f"{len(rows)} rows: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print(f"CSV written to {_write_csv(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
