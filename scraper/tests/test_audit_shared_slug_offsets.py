"""Tests for scripts/audit_shared_slug_offsets.py (read-only ADR-012 audit)."""
import csv
import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import audit_shared_slug_offsets as audit  # noqa: E402

SLUG = "tensei-shitara-slime-datta-ken-4th-season"


class _FakeQuery:
    def __init__(self, client, name):
        self._client, self._name = client, name
        self._filters, self._range = [], None

    def select(self, *a, **k):
        return self

    @property
    def not_(self):
        return self

    def is_(self, *a, **k):
        self._filters.append(("__notnull__", a[0]))
        return self

    def in_(self, col, vals):
        self._filters.append((col, set(vals)))
        return self

    def order(self, *a, **k):
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def execute(self):
        rows = []
        for r in self._client.tables[self._name]:
            ok = True
            for col, vals in self._filters:
                if col == "__notnull__":
                    ok = ok and r.get(vals) is not None
                else:
                    ok = ok and r.get(col) in vals
            if ok:
                rows.append(dict(r))
        if self._range:
            rows = rows[self._range[0]:self._range[1] + 1]
        return MagicMock(data=rows)

    def _write(self, verb):
        def _fn(*a, **k):
            self._client.writes.append((self._name, verb))
            return self
        return _fn

    insert = property(lambda self: self._write("insert"))
    upsert = property(lambda self: self._write("upsert"))
    update = property(lambda self: self._write("update"))
    delete = property(lambda self: self._write("delete"))


class _FakeClient:
    def __init__(self, series, episodes):
        self.tables = {"series": list(series), "episodes": list(episodes)}
        self.writes = []

    def table(self, name):
        return _FakeQuery(self, name)


def _series(sid, order, count, principal=None, fallback=None, franchise="37430"):
    return {"id": sid, "title": sid.upper(), "franchise_id": franchise, "season_order": order,
            "episode_count": count, "principal_slug": principal, "fallback_slug": fallback}


def _eps(sid, nums):
    return [{"series_id": sid, "episode_number": n} for n in nums]


def _slime_bug_client():
    series = [
        _series("s4", 5, 24, principal=SLUG),
        _series("mal-63129", 6, 0, fallback=SLUG),
        _series("lone", 1, 12, principal="lone-slug"),
        _series("other-a", 1, 12, principal="x", franchise="999"),
    ]
    # The original bug: S4 has 22 of 24, Part 2 took 23-24.
    episodes = _eps("s4", range(1, 23)) + _eps("mal-63129", [23, 24])
    return _FakeClient(series, episodes)


class TestAudit:
    def test_main_is_read_only_and_writes_expected_csv(self, tmp_path, monkeypatch):
        client = _slime_bug_client()
        monkeypatch.setattr(audit.storage, "get_client", lambda: client)
        monkeypatch.setattr(audit, "OUTPUT_DIR", str(tmp_path))

        assert audit.main() == 0

        assert client.writes == []  # zero insert/update/upsert/delete calls
        with open(tmp_path / "shared_slug_offset_audit.csv", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            assert tuple(reader.fieldnames) == audit.COLUMNS
            rows = {r["series_id"]: r for r in reader}

        assert set(rows) == {"s4", "mal-63129"}  # unshared series are not audited
        assert rows["s4"]["verdict"] == "match"
        assert rows["s4"]["new_offset"] == "0"
        assert rows["s4"]["old_offset"] == "2"  # order-blind: Part 2's two rows
        assert (rows["s4"]["own_min_episode"], rows["s4"]["own_max_episode"]) == ("1", "22")
        p2 = rows["mal-63129"]
        assert p2["new_offset"] == "24"
        assert p2["old_offset"] == "22"
        assert p2["own_min_episode"] == "23"
        assert p2["verdict"] == "differs"

    def test_ambiguous_and_empty_series_verdicts(self):
        series = [
            _series("a", 1, None, principal="x"),
            _series("b", 2, 12, fallback="x"),
            _series("c", 1, 12, principal="y"),
            _series("d", 2, 12, principal="y"),
        ]
        rows = {r["series_id"] + r["slug"]: r for r in audit.build_audit_rows(series, {})}
        assert rows["bx"]["verdict"] == "ambiguous"
        assert rows["bx"]["new_offset"].startswith("ambiguous:")
        assert rows["ax"]["verdict"] == "match"  # first cour, offset 0, no episodes
        assert rows["dy"]["verdict"] == "match"  # no episodes, offset defined (12)
        assert rows["dy"]["new_offset"] == 12

    def test_series_with_both_slugs_shared_emits_one_row_per_slug(self):
        series = [
            _series("a", 1, 12, principal="x", fallback="y"),
            _series("b", 2, 12, principal="x", fallback="y"),
        ]
        rows = audit.build_audit_rows(series, {})
        assert sorted((r["series_id"], r["slug"]) for r in rows) == [
            ("a", "x"), ("a", "y"), ("b", "x"), ("b", "y"),
        ]
