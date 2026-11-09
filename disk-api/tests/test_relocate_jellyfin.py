import json
import sqlite3
import sys
from pathlib import Path

import pytest

from app.models import db

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import relocate_jellyfin as rel  # noqa: E402

MAPPING = {
    "s1": {"show_title": "Rascal", "show_year": 2018, "season_number": 0, "episode_offset": 2},
    "s2": {"show_title": "Rascal", "show_year": 2018, "season_number": 2, "episode_offset": 0},
}


def _add(media, rel_path, series_id, ep, content=b"x"):
    p = media / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    db.insert_file(p.name, str(p), "video/mp4", len(content), "videos", series_id, ep)
    return p


def _rows():
    with db.get_connection() as conn:
        return {r["id"]: dict(r) for r in conn.execute("SELECT * FROM files")}


def _conn():
    return rel.connect(db.DB_PATH)


@pytest.fixture
def setup(roots):
    _, media = roots
    old1 = _add(media, "Movie (2019)/Season 01/Movie (2019) S01E01.mp4", "s1", 1)
    old2 = _add(media, "Other (2023)/Season 01/Other (2023) S01E01.mp4", "s2", 1)
    return media, old1, old2


def test_dry_run_changes_nothing(setup):
    media, old1, old2 = setup
    before = _rows()
    entries = rel.plan(_conn(), MAPPING, media)
    assert {e["status"] for e in entries} == {"move"}
    assert old1.exists() and old2.exists()
    assert _rows() == before


def test_apply_moves_and_updates(setup):
    media, old1, old2 = setup
    entries = rel.plan(_conn(), MAPPING, media)
    rel.apply(_conn(), entries, media)
    new1 = media / "Rascal (2018)" / "Season 00" / "Rascal (2018) S00E03.mp4"
    new2 = media / "Rascal (2018)" / "Season 02" / "Rascal (2018) S02E01.mp4"
    assert new1.exists() and new2.exists()
    assert not old1.exists() and not old2.exists()
    rows = _rows()
    assert {r["stored_path"] for r in rows.values()} == {str(new1), str(new2)}
    assert {r["filename"] for r in rows.values()} == {new1.name, new2.name}


def test_existing_target_reported_not_overwritten(setup):
    media, old1, _ = setup
    target = media / "Rascal (2018)" / "Season 00" / "Rascal (2018) S00E03.mp4"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"keep")
    entries = rel.plan(_conn(), MAPPING, media)
    by_series = {e["series_id"]: e for e in entries}
    assert by_series["s1"]["status"] == "conflict"
    rel.apply(_conn(), entries, media)
    assert target.read_bytes() == b"keep"
    assert old1.exists()
    assert str(old1) in {r["stored_path"] for r in _rows().values()}


def test_active_job_series_skipped(setup):
    media, old1, old2 = setup
    db.create_job("j1", "http://x", "videos", "s1", 2, status="downloading")
    entries = rel.plan(_conn(), MAPPING, media)
    by_series = {e["series_id"]: e for e in entries}
    assert by_series["s1"]["status"] == "skip_active"
    assert by_series["s2"]["status"] == "move"
    rel.apply(_conn(), entries, media)
    assert old1.exists() and not old2.exists()


def test_second_apply_is_noop(setup):
    media, *_ = setup
    rel.apply(_conn(), rel.plan(_conn(), MAPPING, media), media)
    after = _rows()
    entries = rel.plan(_conn(), MAPPING, media)
    assert {e["status"] for e in entries} == {"ok"}
    rel.apply(_conn(), entries, media)
    assert _rows() == after


def test_empty_old_dirs_removed(setup):
    media, old1, old2 = setup
    rel.apply(_conn(), rel.plan(_conn(), MAPPING, media), media)
    assert not old1.parent.exists() and not old1.parent.parent.exists()
    assert not old2.parent.parent.exists()
    assert media.exists()


def test_non_empty_old_dir_kept(setup):
    media, old1, _ = setup
    (old1.parent / "extra.nfo").write_text("keep")
    rel.apply(_conn(), rel.plan(_conn(), MAPPING, media), media)
    assert (old1.parent / "extra.nfo").exists()


def test_outside_media_root_skipped(roots):
    _, media = roots
    legacy = roots[0] / "videos" / "episodes" / "s1" / "ep.mp4"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"x")
    db.insert_file("ep.mp4", str(legacy), "video/mp4", 1, "videos", "s1", 1)
    entries = rel.plan(_conn(), MAPPING, media)
    assert [e["status"] for e in entries] == ["skip_outside"]
    rel.apply(_conn(), entries, media)
    assert legacy.exists()


def test_missing_source_reported(roots):
    _, media = roots
    ghost = media / "Gone (2020)" / "Season 01" / "Gone (2020) S01E01.mp4"
    db.insert_file(ghost.name, str(ghost), "video/mp4", 1, "videos", "s1", 1)
    entries = rel.plan(_conn(), MAPPING, media)
    assert [e["status"] for e in entries] == ["missing"]
    rel.apply(_conn(), entries, media)
    assert _rows()[1]["stored_path"] == str(ghost)


def test_unmapped_series_untouched(roots):
    _, media = roots
    _add(media, "Z (2020)/Season 01/Z (2020) S01E01.mp4", "zz", 1)
    assert rel.plan(_conn(), MAPPING, media) == []


def test_main_dry_run_and_apply(setup, tmp_path, capsys):
    media, old1, _ = setup
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(MAPPING))
    args = ["--mapping", str(mp), "--db", str(db.DB_PATH), "--media-root", str(media)]
    assert rel.main(args) == 0
    assert old1.exists()
    assert "dry-run" in capsys.readouterr().out
    assert rel.main(args + ["--apply"]) == 0
    assert not old1.exists()
