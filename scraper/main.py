import time
import threading
from fetcher import fetch_top_anime, fetch_simulcasts, search_kitsu_anime, fetch_kitsu_series_status
from normalizer import normalize
from storage import upsert_many
from db import series as db_series


def _normalize_with_kitsu(raw: dict, is_featured: bool = False) -> dict | None:
    """Fetch Kitsu data, then normalize — so kitsu_id/kitsu_status inform is_simulcast."""
    title = (raw.get("title") or "").strip()
    kitsu_id: str | None = None
    kitsu_status: str | None = None
    banner_url_override: str | None = None

    if title:
        kitsu = search_kitsu_anime(title)
        time.sleep(0.3)
        if kitsu:
            kitsu_id = kitsu.get("id")
            banner_url_override = kitsu.get("cover_url")
            if kitsu_id:
                kitsu_status = fetch_kitsu_series_status(kitsu_id)
                time.sleep(0.2)

    entry = normalize(raw, is_featured=is_featured, kitsu_id=kitsu_id, kitsu_status=kitsu_status)
    if entry and banner_url_override:
        entry["banner_url"] = banner_url_override
    return entry


def run():
    print("=== Anistream Scraper ===\n")

    # --- Top anime (first 50) ---
    print("[1/2] Fetching top anime...")
    raw_top = fetch_top_anime(pages=2)
    top_ids = {r["mal_id"] for r in raw_top}

    sorted_by_score = sorted(raw_top, key=lambda r: r.get("score") or 0, reverse=True)
    featured_ids = {r["mal_id"] for r in sorted_by_score[:5]}

    normalized_top = []
    for i, raw in enumerate(raw_top):
        title = raw.get("title", "")
        entry = _normalize_with_kitsu(raw, is_featured=raw["mal_id"] in featured_ids)
        if entry:
            normalized_top.append(entry)
            kitsu_label = f"kitsu:{entry.get('kitsu_id') or '—'} status:{entry.get('kitsu_status') or '—'}"
            print(f"  [{i+1}/{len(raw_top)}] {title} — {kitsu_label}")

    saved = upsert_many(normalized_top)
    print(f"  Saved {saved} series from top anime.\n")

    _top_mal_ids = [e["mal_id"] for e in normalized_top if e.get("mal_id")]
    if _top_mal_ids:
        threading.Thread(target=db_series.warm_recommendations, args=(_top_mal_ids,), daemon=True).start()

    # --- Simulcasts ---
    print("[2/2] Fetching simulcasts...")
    raw_sim = fetch_simulcasts()

    normalized_sim = []
    for i, raw in enumerate(raw_sim):
        if raw.get("mal_id") in top_ids:
            continue
        title = raw.get("title", "")
        entry = _normalize_with_kitsu(raw, is_featured=False)
        if entry:
            normalized_sim.append(entry)
            kitsu_label = f"kitsu:{entry.get('kitsu_id') or '—'} status:{entry.get('kitsu_status') or '—'}"
            print(f"  [{i+1}/{len(raw_sim)}] {title} — {kitsu_label}")

    saved = upsert_many(normalized_sim)
    print(f"  Saved {saved} simulcast series.\n")

    _sim_mal_ids = [e["mal_id"] for e in normalized_sim if e.get("mal_id")]
    if _sim_mal_ids:
        threading.Thread(target=db_series.warm_recommendations, args=(_sim_mal_ids,), daemon=True).start()

    print("Done.")


if __name__ == "__main__":
    run()
