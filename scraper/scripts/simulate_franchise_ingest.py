"""Dry-run the franchise ingest pipeline against live Jikan/MAL, Kitsu and
AnimeAV1 — without touching Supabase.

Reuses the real ingest code path unmodified (routes.ingest_routes.
_discover_franchise_jikan + _ingest_related) so this reproduces exactly what
a live /ingest call would persist, bugs included. Only the DB read/write
functions are monkeypatched to an in-memory store: every member is treated
as a fresh, not-yet-ingested series, and nothing is written to Supabase.

Usage (must run with cwd=scraper/, so config.py's relative .env.local load
works):

    cd scraper && python scripts/simulate_franchise_ingest.py [mal_id] [root_animeav1_slug]

Defaults to mal_id=37430 (That Time I Got Reincarnated as a Slime).
``root_animeav1_slug`` mirrors the admin-provided slug the real /ingest route
receives for the root series — pass it so the root's turn doesn't rely on a
fuzzy AnimeAV1 title search like every other franchise member does.
Writes scripts/output/<mal_id>_series.csv and scripts/output/<mal_id>_episodes.csv.
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import routes.ingest_routes as ingest_routes  # noqa: E402

_series_store: dict[str, dict] = {}
_episode_store: dict[str, dict] = {}


def _fake_upsert_series(series: dict) -> None:
    _series_store[series["id"]] = series


def _fake_upsert_episodes(episodes: list[dict]) -> int:
    unique = {ep["id"]: ep for ep in episodes}
    _episode_store.update(unique)
    return len(unique)


def _fake_get_series_by_mal_id(mal_id: int) -> dict | None:
    return None  # simulate a from-scratch ingest for every franchise member


def _fake_get_episode_count(series_id: str) -> int:
    return sum(1 for ep in _episode_store.values() if ep.get("series_id") == series_id)


def _fake_get_series_by_franchise(franchise_id: str) -> list[dict]:
    return [s for s in _series_store.values() if s.get("franchise_id") == franchise_id]


def _patch() -> None:
    ingest_routes.upsert_series = _fake_upsert_series
    ingest_routes.upsert_episodes = _fake_upsert_episodes
    ingest_routes.get_series_by_mal_id = _fake_get_series_by_mal_id
    ingest_routes.get_episode_count = _fake_get_episode_count
    ingest_routes.get_series_by_franchise = _fake_get_series_by_franchise


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


def main(mal_id: int, root_slug: str | None = None) -> None:
    _patch()

    # The real /ingest route assigns the root series' AnimeAV1 slug from an
    # explicit admin-provided param, not a fuzzy title search (only every
    # *other* franchise member goes through _ingest_related's auto-discovery
    # search). Reusing _ingest_related for the root too — for one call —
    # would let AnimeAV1's ambiguous search steal a slug and block whichever
    # real member that page belongs to. When the caller knows the root's
    # already-confirmed slug, force it here so the root's turn matches
    # production instead of guessing.
    _root_turn = {"active": False}
    real_find_best_animeav1_match = ingest_routes.find_best_animeav1_match
    if root_slug:
        def _find_best_animeav1_match_root_override(query: str, alt_titles=None):
            if _root_turn["active"]:
                return {"slug": root_slug, "title": query}
            return real_find_best_animeav1_match(query, alt_titles=alt_titles)
        ingest_routes.find_best_animeav1_match = _find_best_animeav1_match_root_override

    print(f"Discovering franchise via Jikan relations BFS for mal_id={mal_id}...")
    franchise_entries = ingest_routes._discover_franchise_jikan(mal_id)
    franchise_id = str(franchise_entries[0]["mal_id"]) if franchise_entries else f"mal-{mal_id}"
    print(f"  franchise_id={franchise_id}  members discovered={len(franchise_entries)}")

    for entry in franchise_entries:
        _root_turn["active"] = bool(root_slug) and entry["mal_id"] == mal_id
        print(
            f"  ingesting mal_id={entry['mal_id']} title={entry['title'] or '?'!r} "
            f"relation={entry['relation']} order={entry['order']}..."
        )
        result = ingest_routes._ingest_related(entry, franchise_id)
        print(f"    -> {result}")
        for series in _series_store.values():
            if series.get("mal_id") == entry["mal_id"]:
                series["_ingest_status"] = result.get("status")
                series["_episodes_ingested"] = result.get("episodes_ingested")

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(out_dir, exist_ok=True)
    series_path = os.path.join(out_dir, f"{mal_id}_series.csv")
    episodes_path = os.path.join(out_dir, f"{mal_id}_episodes.csv")

    _write_csv(series_path, list(_series_store.values()))
    _write_csv(episodes_path, list(_episode_store.values()))

    print(f"\nWrote {len(_series_store)} series rows -> {series_path}")
    print(f"Wrote {len(_episode_store)} episode rows -> {episodes_path}")


if __name__ == "__main__":
    mal_id_arg = int(sys.argv[1]) if len(sys.argv) > 1 else 37430
    root_slug_arg = sys.argv[2] if len(sys.argv) > 2 else None
    main(mal_id_arg, root_slug=root_slug_arg)
