"""Read-only audit of the stored source slugs against the ADR-016 rules.

For every series with a ``principal_slug`` (AnimeAV1) or ``fallback_slug``
(jkanime), fetches the source page and applies the same exact-title match +
validation (media type family, start year, episode count) that ingest uses
for auto-assignment, using the STORED series fields (title, titles, media_type,
year, episode_count) as the Jikan side — no Jikan calls.

Run from the scraper root:  python scripts/audit_source_slugs.py

Writes, under ``scripts/output/``:
  source_slug_audit.csv      series_id, title, mal_id, media_type, source, slug,
                             page_title, exact_match, checks, verdict (ok|suspect)
  summary_relation_audit.csv series whose franchise_relation is 'Summary' or whose
                             media_type is cm/pv/music (manual review)

Nothing is deleted or modified: the database is only read (paginated via
db._paging.fetch_all, ADR-010) and page fetches are rate-limited with
``REQUEST_DELAY``. A page that cannot be fetched is verdict ``suspect``
(page_title empty, checks ``fetch_failed``).
"""
import csv
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import storage  # noqa: E402
from config import REQUEST_DELAY  # noqa: E402
from db._paging import fetch_all  # noqa: E402
from domain.source_match import SKIPPED_MEDIA_TYPES, is_exact_match, validate_candidate  # noqa: E402
from scraper_animeav1 import fetch_animeav1_page  # noqa: E402
from scraper_jkanime import fetch_jkanime_series_info  # noqa: E402

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
_CSV_NAME = "source_slug_audit.csv"
_REVIEW_CSV_NAME = "summary_relation_audit.csv"
COLUMNS = (
    "series_id", "title", "mal_id", "media_type", "source", "slug",
    "page_title", "exact_match", "checks", "verdict",
)
REVIEW_COLUMNS = ("series_id", "title", "mal_id", "media_type", "franchise_relation", "reason")
_SOURCES = (("animeav1", "principal_slug"), ("jkanime", "fallback_slug"))


def _fetch_series() -> list[dict]:
    client = storage.get_client()
    return fetch_all(
        lambda: client.table("series")
        .select("id, mal_id, title, titles, media_type, year, episode_count, "
                "principal_slug, fallback_slug, franchise_relation")
        .order("id")
    )


def _page_facts(source: str, slug: str):
    """``(page_title, page_facts)`` for a slug; ``(None, None)`` on fetch failure."""
    if source == "animeav1":
        page = fetch_animeav1_page(slug)
    else:
        page = fetch_jkanime_series_info(slug)
    if not page:
        return None, None
    return page.get("title"), page


def audit_row(series: dict, source: str, slug: str, page_title, page) -> dict:
    """Pure: the CSV row for one stored (series, source, slug)."""
    titles = [series.get("title"), *(series.get("titles") or [])]
    if page is None:
        exact, checks, verdict = False, "fetch_failed", "suspect"
    else:
        exact = is_exact_match(page_title, titles)
        validation = validate_candidate(page, series)
        checks = json.dumps(
            {k: v["outcome"] for k, v in validation["checks"].items()}, sort_keys=True
        )
        verdict = "ok" if exact and validation["passed"] else "suspect"
    return {
        "series_id": series["id"],
        "title": series.get("title"),
        "mal_id": series.get("mal_id"),
        "media_type": series.get("media_type"),
        "source": source,
        "slug": slug,
        "page_title": page_title or "",
        "exact_match": exact,
        "checks": checks,
        "verdict": verdict,
    }


def build_review_rows(series_rows: list[dict]) -> list[dict]:
    """Pure: series flagged for manual review (Summary relation, cm/pv/music)."""
    rows = []
    for s in series_rows:
        reasons = []
        if s.get("franchise_relation") == "Summary":
            reasons.append("franchise_relation=Summary")
        if (s.get("media_type") or "").lower() in SKIPPED_MEDIA_TYPES:
            reasons.append(f"media_type={s['media_type']}")
        if reasons:
            rows.append({
                "series_id": s["id"], "title": s.get("title"), "mal_id": s.get("mal_id"),
                "media_type": s.get("media_type"),
                "franchise_relation": s.get("franchise_relation"),
                "reason": "; ".join(reasons),
            })
    return rows


def _write_csv(name: str, columns, rows: list[dict]) -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, name)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    return path


def main() -> int:
    series_rows = _fetch_series()
    rows = []
    for s in series_rows:
        for source, field in _SOURCES:
            slug = s.get(field)
            if not slug:
                continue
            time.sleep(REQUEST_DELAY)
            page_title, page = _page_facts(source, slug)
            row = audit_row(s, source, slug, page_title, page)
            rows.append(row)
            print(f"  [{row['verdict']}] {s['id']} {source}={slug} page={row['page_title']!r} {row['checks']}")

    review = build_review_rows(series_rows)
    suspect = sum(1 for r in rows if r["verdict"] == "suspect")
    print(f"{len(rows)} stored slugs audited: {suspect} suspect; {len(review)} series to review")
    print(f"CSV written to {_write_csv(_CSV_NAME, COLUMNS, rows)}")
    print(f"CSV written to {_write_csv(_REVIEW_CSV_NAME, REVIEW_COLUMNS, review)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
