"""
One-off relocation of existing NAS files to the franchise Jellyfin layout (ADR-020).

Reads a mapping produced by scraper/scripts/export_jellyfin_placement.py:
    {"<series_id>": {"show_title", "show_year", "season_number", "episode_offset"}}
and moves each matching ``files`` row to the path ``jellyfin_episode_target``
would build today. Dry-run by default; pass --apply to move files.

Usage (from disk-api/):
    python -m scripts.relocate_jellyfin --mapping placement.json
    python -m scripts.relocate_jellyfin --mapping placement.json --apply
"""
import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models import db  # noqa: E402
from app.routers import files as files_mod  # noqa: E402

ACTIVE_STATUSES = ("pending", "downloading")


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _active_series(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT DISTINCT series_id FROM download_jobs "
        "WHERE series_id IS NOT NULL AND status IN (?, ?)",
        ACTIVE_STATUSES,
    ).fetchall()
    return {r["series_id"] for r in rows}


def plan(conn: sqlite3.Connection, mapping: dict, media_root: Path) -> list[dict]:
    """Compute one entry per ``files`` row whose series_id is in ``mapping``.

    Status: move | ok (already in place) | conflict (target exists or is taken
    by another row) | missing (source absent) | skip_outside (stored_path not
    under media_root) | skip_active (series has a pending/downloading job).
    """
    active = _active_series(conn)
    placeholders = ",".join("?" for _ in mapping)
    rows = conn.execute(
        f"SELECT * FROM files WHERE series_id IN ({placeholders}) "
        "AND episode_number IS NOT NULL ORDER BY series_id, episode_number",
        list(mapping),
    ).fetchall() if mapping else []

    entries: list[dict] = []
    claimed: set[Path] = set()
    for row in rows:
        old = Path(row["stored_path"])
        entry = {"id": row["id"], "series_id": row["series_id"],
                 "episode_number": row["episode_number"], "old": old, "new": None}
        entries.append(entry)

        if row["series_id"] in active:
            entry["status"] = "skip_active"
            continue
        if not old.is_relative_to(media_root):
            entry["status"] = "skip_outside"
            continue

        m = mapping[row["series_id"]]
        target = files_mod.jellyfin_episode_target(
            row["series_id"], row["episode_number"], m.get("show_title"), m.get("show_year"),
            season_number=m["season_number"],
            file_episode_number=m.get("episode_offset", 0) + row["episode_number"],
            media_root=media_root,
        )
        if target is None:
            entry["status"] = "skip_outside"  # no usable show title in the mapping
            continue
        subdir, base = target
        new = subdir / (base + (old.suffix or ".mp4"))
        entry["new"] = new

        if new == old:
            entry["status"] = "ok"
            claimed.add(new)
        elif not old.exists():
            entry["status"] = "missing"
        elif new.exists() or new in claimed:
            entry["status"] = "conflict"
        else:
            entry["status"] = "move"
            claimed.add(new)
    return entries


def _remove_empty_dirs(start: Path, media_root: Path) -> None:
    d = start
    while d != media_root and d.is_relative_to(media_root):
        try:
            d.rmdir()  # only succeeds when empty
        except OSError:
            return
        d = d.parent


def apply(conn: sqlite3.Connection, entries: list[dict], media_root: Path) -> int:
    """Execute the ``move`` entries. Returns the number of files moved."""
    moved = 0
    for e in entries:
        if e["status"] != "move":
            continue
        old, new = e["old"], e["new"]
        new.parent.mkdir(parents=True, exist_ok=True)
        os.rename(old, new)
        try:
            conn.execute(
                "UPDATE files SET stored_path = ?, filename = ? WHERE id = ?",
                (str(new), new.name, e["id"]),
            )
            conn.commit()
        except sqlite3.Error:
            os.rename(new, old)  # keep disk and DB consistent
            raise
        e["status"] = "moved"
        moved += 1
        _remove_empty_dirs(old.parent, media_root)
    return moved


def _print_plan(entries: list[dict]) -> None:
    for e in entries:
        arrow = f"{e['old']} -> {e['new']}" if e["new"] else str(e["old"])
        print(f"[{e['status']}] {e['series_id']} ep{e['episode_number']}: {arrow}")
    counts: dict[str, int] = {}
    for e in entries:
        counts[e["status"]] = counts.get(e["status"], 0) + 1
    print("summary: " + (", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "nothing to do"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--mapping", required=True, type=Path, help="JSON from export_jellyfin_placement.py")
    ap.add_argument("--apply", action="store_true", help="move files (default: dry-run)")
    ap.add_argument("--db", type=Path, default=db.DB_PATH, help="SQLite path (default: app DB)")
    ap.add_argument("--media-root", type=Path, default=files_mod.MEDIA_ROOT,
                    help="Jellyfin media root (default: DISK_MEDIA_ROOT)")
    args = ap.parse_args(argv)

    if args.media_root is None:
        ap.error("--media-root or DISK_MEDIA_ROOT is required")
    mapping = json.loads(args.mapping.read_text())

    conn = connect(args.db)
    try:
        entries = plan(conn, mapping, args.media_root)
        if args.apply:
            moved = apply(conn, entries, args.media_root)
            _print_plan(entries)
            print(f"applied: {moved} file(s) moved")
        else:
            _print_plan(entries)
            print("dry-run: nothing changed (use --apply)")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
