"""Read-only inspection of the current production series/episodes state for
the 12 franchises validated today, so we can plan an exact delete+reingest
instead of guessing. Never writes anything.

Usage (from scraper/): python scripts/inspect_prod_state.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import storage

FRANCHISES = {
    "Slime": [37430,38793,39607,45753,39551,49318,41487,49877,54565,58592,53580,59493,59971,59970,63129],
    "One Punch Man": [30276,31704,31772,39652,34134,39705,62653,52807,63193],
    "Re:Zero": [38414,31240,36286,39587,42203,54857,61316],
    "Demon Slayer": [38000,40456,49926,47778,51019,55701,59192,62546,62547],
    "Kingdom": [12031,17389,40682,50160,53223,61517,63185],
    "DanMachi": [40064,28121,32801,32887,37348,52357,37347,40453,40454,44983,47164,53111,57066,63442],
    "Gintama": [918,2951,7472,62277,6945,10643,9969,21899,56544,15417,15335,25313,58091,59688,28977,32122,32366,34096,35843,36838,37491,44087,39486],
    "AoT S3P2": [25777,36702,19391,35760,39477,38524,42091,16498,18397,19285,23775,23777,40028,49627,48583,51535,59571],
    "MHA S5": [31964,35262,33929,33486,35459,36456,36896,42603,38699,38408,39565,41587,44200,51781,56685,43683,49918,57519,54789,56196,60645,60098,63130,64107],
    "Bunny Girl Senpai": [37450,38329,53129,54870,57433,62582],
    "Mushoku Tensei": [39535,45576,50360,55818,51179,55888,59193],
    "SAO": [11757,42916,20021,50275,21881,27891,36475,55994,37831,59968,31765,36474,39239,40489,39597,41341,40540,53529],
}


def main() -> None:
    client = storage.get_client()

    total_found = 0
    total_checked = 0
    for franchise_name, mal_ids in FRANCHISES.items():
        total_checked += len(mal_ids)
        resp = (
            client.table("series")
            .select("id, mal_id, title, principal_slug, fallback_slug, franchise_id, season_order")
            .in_("mal_id", mal_ids)
            .execute()
        )
        rows = resp.data or []
        total_found += len(rows)

        print(f"\n=== {franchise_name} ({len(rows)}/{len(mal_ids)} mal_ids found in DB) ===")
        if not rows:
            print("  (none of these mal_ids exist in the DB yet)")
            continue

        ids = [r["id"] for r in rows]
        ep_resp = (
            client.table("episodes")
            .select("series_id")
            .in_("series_id", ids)
            .execute()
        )
        ep_counts: dict[str, int] = {}
        for ep in (ep_resp.data or []):
            sid = ep["series_id"]
            ep_counts[sid] = ep_counts.get(sid, 0) + 1

        for r in sorted(rows, key=lambda x: x.get("season_order") or 0):
            eps = ep_counts.get(r["id"], 0)
            print(
                f"  mal_id={r['mal_id']:<8} id={r['id']:<55} eps={eps:<4} "
                f"principal_slug={r.get('principal_slug') or '-':<45} "
                f"fallback_slug={r.get('fallback_slug') or '-':<20} "
                f"title={r.get('title')}"
            )

        missing = set(mal_ids) - {r["mal_id"] for r in rows}
        if missing:
            print(f"  NOT in DB yet: {sorted(missing)}")

    print(f"\nTOTAL: {total_found}/{total_checked} mal_ids already exist in the DB")


if __name__ == "__main__":
    main()
