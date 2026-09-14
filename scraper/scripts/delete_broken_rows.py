"""Delete the 8 series rows (and their episodes) identified as holding wrong
data from the old canonical-id collision bug, so a fresh /ingest can rebuild
them correctly. Confirmed against live production state via inspect_prod_state.py.

Usage (from scraper/): python scripts/delete_broken_rows.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import storage

# mal_id -> id, purely for logging/verification; deletion itself keys off id.
TARGETS = {
    59493: "tensei-shitara-slime-datta-ken-3rd-season",
    63129: "tensei-shitara-slime-datta-ken-4th-season",
    63185: "kingdom-6th-season",
    40453: "is-it-wrong-to-try-to-pick-up-girls-in-a-dungeon-ii-is-it-wrong-to-go-searching-for-herbs-on-a-deserted-island",
    37348: "is-it-wrong-to-try-to-pick-up-girls-in-a-dungeon-arrow-of-the-orion",
    52357: "is-it-wrong-to-try-to-pick-up-girls-in-a-dungeon-iv-play-back",
    53111: "danmachi-v",
    55888: "mushoku-tensei-ii-isekai-ittara-honki-dasu",
}


def main() -> None:
    client = storage.get_client()
    ids = list(TARGETS.values())

    # Verify each id's current mal_id matches what we expect before deleting anything.
    check = client.table("series").select("id, mal_id, title").in_("id", ids).execute()
    found = {r["id"]: r for r in (check.data or [])}
    for mal_id, series_id in TARGETS.items():
        row = found.get(series_id)
        if not row:
            print(f"  SKIP {series_id}: not found in DB (already gone?)")
            continue
        if row["mal_id"] != mal_id:
            print(f"  ABORT {series_id}: mal_id mismatch — expected {mal_id}, found {row['mal_id']} ({row['title']!r}). Not touching.")
            return
        print(f"  OK    {series_id}: mal_id={row['mal_id']} title={row['title']!r}")

    confirmed_ids = [sid for sid in ids if sid in found]
    if not confirmed_ids:
        print("Nothing to delete.")
        return

    ep_del = client.table("episodes").delete().in_("series_id", confirmed_ids).execute()
    print(f"\nDeleted {len(ep_del.data or [])} episode rows for {len(confirmed_ids)} series.")

    series_del = client.table("series").delete().in_("id", confirmed_ids).execute()
    print(f"Deleted {len(series_del.data or [])} series rows.")


if __name__ == "__main__":
    main()
