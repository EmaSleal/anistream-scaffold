"""Tests for scripts/export_jellyfin_placement.py (DB and NAS mocked)."""
import json
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import export_jellyfin_placement as exp  # noqa: E402

_P = {
    "a": {"show_title": "Rascal", "show_year": 2018, "season_number": 1, "episode_offset": 0},
    "b": {"show_title": "Rascal", "show_year": 2018, "season_number": 0, "episode_offset": 1},
}


def test_writes_mapping_for_given_series_ids(tmp_path):
    out = tmp_path / "m.json"
    with patch.object(exp.jellyfin_placement, "placement", side_effect=lambda s: _P[s]):
        assert exp.main(["a", "b", "a", "--out", str(out)]) == 0
    assert json.loads(out.read_text()) == _P


def test_without_ids_uses_queue_done_series_present_on_nas(tmp_path):
    out = tmp_path / "m.json"
    nas = {"a": [1, 2], "b": []}
    with patch.object(exp.db_queue, "list_done_series_ids", return_value=["a", "b"]), \
         patch.object(exp, "list_downloaded_episodes", side_effect=lambda s, **k: nas[s]), \
         patch.object(exp.jellyfin_placement, "placement", side_effect=lambda s: _P[s]):
        assert exp.main(["--out", str(out)]) == 0
    assert list(json.loads(out.read_text())) == ["a"]


def test_failed_placement_is_skipped_and_exit_code_1(tmp_path):
    out = tmp_path / "m.json"

    def fake(sid):
        if sid == "b":
            raise RuntimeError("db")
        return _P[sid]

    with patch.object(exp.jellyfin_placement, "placement", side_effect=fake):
        assert exp.main(["a", "b", "--out", str(out)]) == 1
    assert list(json.loads(out.read_text())) == ["a"]
