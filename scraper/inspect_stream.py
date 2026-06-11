"""Debug script: inspect stream resolution for a given episode slug.

Usage (from scraper/):
    python inspect_stream.py class-de-2banme-ni-kawaii-onnanoko-to-tomodachi-ni-natta-10

Prints:
  - Raw server codes from AnimeFlv
  - Which server/code was selected (or why none matched)
  - Final stream URL if extraction succeeds
"""
import sys
import re
import json

SLUG = sys.argv[1] if len(sys.argv) > 1 else "class-de-2banme-ni-kawaii-onnanoko-to-tomodachi-ni-natta-10"

from scraper_animeflv import scrape_episode_servers
from extractor import extract_streamtape, ExtractionError

print(f"\n=== scrape_episode_servers('{SLUG}') ===\n")
try:
    servers = scrape_episode_servers(SLUG)
except RuntimeError as e:
    print(f"ERROR fetching servers: {e}")
    sys.exit(1)

for lang, server_list in servers.items():
    print(f"[{lang}]")
    for s in server_list:
        code = s.get("code", "") or ""
        print(f"  server={s.get('server')!r:20}  title={s.get('title')!r:20}  code={code[:80]!r}")
    print()

print("=== Streamtape search ===\n")

video_id = None
for lang, server_list in servers.items():
    for s in server_list:
        code = s.get("code", "") or ""
        if "streamtape" in code.lower():
            print(f"Found 'streamtape' in code: {code!r}")
            # Original regex (strict .com)
            m_strict = re.search(r"streamtape\.com/e/([^/?&]+)", code)
            # Fixed regex (any TLD)
            m_loose  = re.search(r"streamtape\.[^/]+/e/([^/?&\"']+)", code)
            print(f"  strict (.com) match : {m_strict}")
            print(f"  loose  (any TLD) match : {m_loose}")
            if m_loose:
                video_id = m_loose.group(1)
                print(f"  -> video_id = {video_id!r}")
                break
    if video_id:
        break

if not video_id:
    print("No streamtape video_id found.")
    sys.exit(1)

print(f"\n=== extract_streamtape('{video_id}') ===\n")
try:
    url = extract_streamtape(video_id)
    print(f"Stream URL: {url}")
except ExtractionError as e:
    print(f"ExtractionError: {e}")

print(f"\n=== DB state for episode slug ===\n")
import storage
client = storage.get_client()

ep_row = (
    client.table("episodes")
    .select("id, series_id, animeflv_slug")
    .eq("animeflv_slug", SLUG)
    .maybe_single()
    .execute()
)
if not ep_row or not ep_row.data:
    print("Episode NOT found in DB by animeflv_slug")
else:
    ep = ep_row.data
    print(f"Episode found: id={ep['id']!r}  series_id={ep['series_id']!r}  animeflv_slug={ep['animeflv_slug']!r}")

    series_row = (
        client.table("series")
        .select("id, animeflv_slug, animeflv_disabled, animeav1_slug, is_simulcast")
        .eq("id", ep["series_id"])
        .maybe_single()
        .execute()
    )
    if not series_row or not series_row.data:
        print(f"Series NOT found in DB for series_id={ep['series_id']!r}")
    else:
        s = series_row.data
        print(f"\nSeries:")
        print(f"  id               = {s['id']!r}")
        print(f"  animeflv_slug    = {s.get('animeflv_slug')!r}")
        print(f"  animeflv_disabled= {s.get('animeflv_disabled')!r}")
        print(f"  animeav1_slug    = {s.get('animeav1_slug')!r}")
        print(f"  is_simulcast     = {s.get('is_simulcast')!r}")
