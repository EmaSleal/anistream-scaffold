"""Re-ingest the 12 validated franchises against REAL Supabase (no mocking).

Reuses the exact same production code path as /ingest
(_discover_franchise_jikan + _ingest_related) for every discovered member,
including the franchise's own root — _ingest_related's early-return guard
(``already_scraped``) means members that already have real episodes are
left untouched; only members with 0 episodes (fresh, or just deleted) get
rebuilt through the fixed matching pipeline.

Usage (from scraper/): python scripts/real_ingest_franchises.py [mal_id ...]
Defaults to all 12 franchise roots validated today.
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import routes.ingest_routes as ingest_routes

DEFAULT_ROOTS = {
    "Slime": 37430,
    "One Punch Man": 30276,
    "Re:Zero": 61316,
    "Demon Slayer": 38000,
    "Kingdom": 40682,
    "DanMachi": 40064,
    "Gintama": 28977,
    "Mushoku Tensei": 59193,
    "SAO": 36474,
    "AoT S3P2": 38524,
    "MHA S5": 41587,
    "Bunny Girl Senpai": 37450,
}


def run(mal_id: int, label: str = "") -> None:
    print(f"\n=== {label or mal_id} (mal_id={mal_id}) ===")
    franchise_entries = ingest_routes._discover_franchise_jikan(mal_id)
    franchise_id = str(franchise_entries[0]["mal_id"]) if franchise_entries else f"mal-{mal_id}"
    print(f"  franchise_id={franchise_id}  members discovered={len(franchise_entries)}")

    for entry in franchise_entries:
        result = ingest_routes._ingest_related(entry, franchise_id)
        print(
            f"  mal_id={entry['mal_id']:<8} order={entry['order']:<2} "
            f"relation={entry['relation']:<20} -> {result}"
        )
        time.sleep(0.3)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            run(int(arg))
    else:
        for label, mal_id in DEFAULT_ROOTS.items():
            run(mal_id, label)
