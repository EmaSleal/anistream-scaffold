"""Export the Jellyfin placement (ADR-020) of NAS-downloaded series to JSON.

Step one of the one-off relocation of existing NAS files: Flask knows the
franchises, disk-api knows the files. The output is the input of
``disk-api/scripts/relocate_jellyfin.py --mapping``.

Run from the scraper root:
    python scripts/export_jellyfin_placement.py --out placement.json [SERIES_ID ...]

Output: ``{series_id: {show_title, show_year, season_number, episode_offset}}``
computed with ``domain.jellyfin_placement.placement`` (the same function the
download paths use). Read-only: nothing is written to the database or the NAS.

Series selection: the ids given on the command line; with none, every series
with a ``done`` row in ``download_queue`` that the NAS still lists as having
downloaded episodes (``list_downloaded_episodes``, uncached). Episodes
downloaded outside the queue (manual /trigger) have no queue row, so pass their
series ids explicitly. A series whose placement fails is reported on stderr,
left out of the mapping, and makes the exit code 1.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import download_queue as db_queue  # noqa: E402
from domain import jellyfin_placement  # noqa: E402
from domain.nas_jobs import list_downloaded_episodes  # noqa: E402


def discover_series_ids() -> list[str]:
    """Queue-done series that the NAS actually holds episodes for."""
    return [
        sid for sid in db_queue.list_done_series_ids()
        if list_downloaded_episodes(sid, use_cache=False)
    ]


def build_mapping(series_ids: list[str]) -> tuple[dict, list[str]]:
    """Return (mapping, failed_ids) using the shared placement function."""
    mapping: dict[str, dict] = {}
    failed: list[str] = []
    for sid in series_ids:
        try:
            mapping[sid] = jellyfin_placement.placement(sid)
        except Exception as exc:
            print(f"placement failed for {sid}: {exc!r}", file=sys.stderr)
            failed.append(sid)
    return mapping, failed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export Jellyfin placement mapping (see module docstring).")
    parser.add_argument("series_ids", nargs="*", help="series ids (default: queue-done series present on the NAS)")
    parser.add_argument("--out", required=True, help="output JSON file")
    args = parser.parse_args(argv)

    series_ids = list(dict.fromkeys(args.series_ids)) or discover_series_ids()
    mapping, failed = build_mapping(series_ids)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(mapping, fh, indent=2, ensure_ascii=False, sort_keys=True)
        fh.write("\n")
    print(f"{len(mapping)} series written to {args.out}; {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
