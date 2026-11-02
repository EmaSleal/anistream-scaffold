"""Unit tests for scripts/repair_shared_slug.py (ADR-013). Fakes only: no
network, no real database."""
import copy
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

os.environ.setdefault("INTERNAL_JWT_SECRET", "test-internal-secret-for-tests-only")
os.environ.setdefault("SERVICE_SECRET", "test-service-secret")

import csv

import pytest

import repair_shared_slug as rep

PLAN_FILE = os.path.join(os.path.dirname(__file__), "..", "scripts", "repair_plans",
                         "2026-11-02-shared-slug.json")


# ---------------------------------------------------------------------------
# In-memory fake Supabase with real filter/write semantics and a write log
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, client, table):
        self.c, self.t = client, table
        self.mode, self.payload = "select", None
        self.filters, self.orders, self.rng = [], [], None

    def select(self, *_a, **_k):
        return self

    def insert(self, payload):
        self.mode, self.payload = "insert", payload
        return self

    def upsert(self, payload, **_k):
        self.mode, self.payload = "upsert", payload
        return self

    def update(self, payload):
        self.mode, self.payload = "update", payload
        return self

    def delete(self):
        self.mode = "delete"
        return self

    def eq(self, col, val):
        self.filters.append(lambda r: r.get(col) == val)
        return self

    def in_(self, col, vals):
        self.filters.append(lambda r: r.get(col) in vals)
        return self

    def is_(self, col, val):
        self.filters.append(lambda r: r.get(col) is None)
        return self

    def order(self, col, **_k):
        self.orders.append(col)
        return self

    def range(self, a, b):
        self.rng = (a, b)
        return self

    def execute(self):
        rows = self.c.tables.setdefault(self.t, [])
        match = [r for r in rows if all(f(r) for f in self.filters)]
        if self.mode == "select":
            for col in reversed(self.orders):
                match.sort(key=lambda r: (r.get(col) is None, r.get(col)))
            out = [copy.deepcopy(r) for r in match]
            if self.rng:
                out = out[self.rng[0]:self.rng[1] + 1]
            return _Result(out)
        self.c.writes.append((self.mode, self.t))
        if self.mode == "update":
            for r in match:
                r.update(self.payload)
        elif self.mode == "delete":
            self.c.tables[self.t] = [r for r in rows if r not in match]
        else:
            rows.extend(self.payload if isinstance(self.payload, list) else [self.payload])
        return _Result([])


class FakeClient:
    def __init__(self, tables):
        self.tables, self.writes = tables, []

    def table(self, name):
        return _Query(self, name)

    def rpc(self, *a, **k):
        self.writes.append(("rpc", a[0] if a else ""))
        return self


def _series(sid, principal=None, fallback=None, order=1, count=None, franchise="f1"):
    return {"id": sid, "title": sid, "franchise_id": franchise, "season_order": order,
            "episode_count": count, "principal_slug": principal, "fallback_slug": fallback}


def _eps(sid, nums):
    return [{"id": f"{sid}-ep-{n}", "series_id": sid, "episode_number": n} for n in nums]


def _wp(i, user, ep, series, sec=10, ts="2026-01-01T00:00:00+00:00"):
    return {"id": i, "user_id": user, "episode_id": ep, "series_id": series,
            "progress_sec": sec, "duration_sec": 1400, "updated_at": ts}


def _ucw(user, key, series, ep, nxt=None, sec=10, ts="2026-01-01T00:00:00+00:00"):
    return {"user_id": user, "franchise_key": key, "series_id": series, "episode_id": ep,
            "next_episode_id": nxt, "progress_sec": sec, "updated_at": ts}


class Env:
    def __init__(self, monkeypatch, tmp_path, tables, recover=None):
        self.client = FakeClient(tables)
        self.recover_calls = []
        monkeypatch.setattr(rep.storage, "get_client", lambda: self.client)
        monkeypatch.setattr(rep, "OUTPUT_DIR", str(tmp_path))
        self.out = tmp_path

        def fake_recover(series_id, slug, current_max, **kw):
            self.recover_calls.append((series_id, slug, current_max, kw))
            row = next(s for s in self.client.tables["series"] if s["id"] == series_id)
            sibs = [s for s in self.client.tables["series"] if s["franchise_id"] == row["franchise_id"]]
            from domain.shared_slug import compute_shared_slug_offset
            off = compute_shared_slug_offset(sibs, row, slug)["offset"]
            have = {e["episode_number"] for e in self.client.tables["episodes"] if e["series_id"] == series_id}
            window = range(off + 1, off + kw["expected"] + 1)
            wanted = (recover if recover is not None else window)
            new = [n for n in wanted if n in window and n not in have]
            self.client.tables["episodes"].extend(_eps(series_id, new))
            return len([n for n in new if n > current_max])

        monkeypatch.setattr(rep.simulcast_check, "run_simulcast_update", fake_recover)

    def plan(self, pages):
        path = self.out / "plan.json"
        path.write_text(json.dumps(pages))
        return str(path)

    def csv_rows(self):
        with open(self.out / "shared_slug_repair_plan.csv", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def eps(self, sid):
        return sorted(e["episode_number"] for e in self.client.tables["episodes"] if e["series_id"] == sid)


def _page(slug, owner, release, **extra):
    return {"slug": slug, "owner_series_id": owner,
            "release": [{"series_id": s, "principal_slug": None, "fallback_slug": None}
                        if isinstance(s, str) else s for s in release], **extra}


def _aot_tables(extra_wp=(), extra_ucw=()):
    slug = "shingeki-no-kyojin"
    series = [
        _series("attack-on-titan", slug, order=2, count=25),
        _series("roar", slug, order=1, count=1),
        _series("chibi", slug, order=3, count=9),
        _series("mal-39477", slug, order=4, count=7),
        _series("mal-42091", slug, order=5, count=1),
    ]
    eps = (_eps("attack-on-titan", range(19, 26)) + _eps("roar", [1]) + _eps("chibi", range(2, 11))
           + _eps("mal-39477", range(11, 18)) + _eps("mal-42091", [18]))
    return {
        "series": series, "episodes": eps,
        "watch_progress": [_wp(1, "u1", "chibi-ep-5", "chibi"), _wp(2, "u1", "mal-39477-ep-12", "mal-39477"),
                           *extra_wp],
        "user_continue_watching": [_ucw("u1", "f1", "mal-39477", "mal-39477-ep-12", "mal-39477-ep-13"),
                                   *extra_ucw],
    }


AOT_PAGE = _page("shingeki-no-kyojin", "attack-on-titan",
                 ["roar", "chibi", "mal-39477", "mal-42091"])


# ---------------------------------------------------------------------------
# Plan validation and discovery
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [
    {"pages": []},
    [{"slug": "a", "owner_series_id": "o"}],
    [{"slug": "a", "owner_series_id": "o", "release": []}],
    [{"slug": "a", "owner_series_id": "o", "release": [{"series_id": "x", "principal_slug": 5, "fallback_slug": None}]}],
    [{"slug": "a", "owner_series_id": "o", "release": [{"series_id": "x", "principal_slug": None}]}],
    [{"slug": "a", "owner_series_id": "o", "extra": 1, "release": [{"series_id": "x", "principal_slug": None, "fallback_slug": None}]}],
])
def test_schema_errors_exit_2_before_db(bad, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(rep.storage, "get_client", lambda: pytest.fail("DB accessed"))
    p = tmp_path / "p.json"
    p.write_text(json.dumps(bad))
    assert rep.repair_main(str(p)) == 2
    assert "Invalid plan" in capsys.readouterr().out


def test_malformed_json_exit_2(tmp_path):
    p = tmp_path / "p.json"
    p.write_text("{nope")
    assert rep.repair_main(str(p)) == 2


def test_shipped_plan_is_valid_and_sets_bleach_principal_slug():
    pages = rep.load_plan(PLAN_FILE)
    assert len(pages) == 5
    bleach = next(p for p in pages if p["slug"] == "bleach-sennen-kessen-hen-soukoku-tan")
    rel = bleach["release"][0]
    assert rel["principal_slug"] == "bleach-sennen-kessen-hen" and "todo" not in rel
    assert next(p for p in pages if p["slug"] == "tensei-shitara-slime-datta-ken-2nd-season")["release"][0]["series_id"] == "mal-49318"


def test_discovery_lists_columns_with_sources():
    cols = {(c["table"], c["column"]): c for c in rep.discover_reference_columns()}
    assert set(cols) >= {("watch_progress", "episode_id"), ("user_continue_watching", "episode_id"),
                         ("user_continue_watching", "next_episode_id")}
    assert "002_add_user_continue_watching.sql" in cols[("user_continue_watching", "next_episode_id")]["source"]
    assert "db/progress.py" in cols[("watch_progress", "episode_id")]["source"]
    assert all(c["handled"] for c in cols.values())


def test_discovery_flags_unhandled_column_and_blocks_apply(monkeypatch, tmp_path):
    env = Env(monkeypatch, tmp_path, _aot_tables())
    mig = tmp_path / "mig"
    mig.mkdir()
    (mig / "009.sql").write_text("ALTER TABLE favorites ADD COLUMN IF NOT EXISTS last_episode_id TEXT;")
    monkeypatch.setattr(rep, "MIGRATIONS_DIR", str(mig))
    assert rep.repair_main(env.plan([AOT_PAGE]), apply=True, assume_yes=True) == 1
    assert env.client.writes == []


# ---------------------------------------------------------------------------
# Dry-run
# ---------------------------------------------------------------------------


def test_dry_run_performs_zero_writes_and_writes_csv(monkeypatch, tmp_path):
    env = Env(monkeypatch, tmp_path, _aot_tables())
    assert rep.repair_main(env.plan([AOT_PAGE])) == 0
    assert env.client.writes == [] and env.recover_calls == []
    rows = {r["series_id"]: r for r in env.csv_rows()}
    chibi = rows["chibi"]
    assert chibi["status"] == "ok" and chibi["released_numbers"] == ",".join(map(str, range(2, 11)))
    assert "watch_progress.episode_id=1" in chibi["ref_counts"]
    assert chibi["owner_existing_numbers"] == ",".join(map(str, range(19, 26)))
    assert chibi["owner_to_recover"] == ",".join(map(str, range(1, 19)))
    assert "5->(after recovery)" in chibi["remap_targets"]
    assert chibi["planned_deletions"] == "9"
    assert "user_continue_watching.next_episode_id=1" in rows["mal-39477"]["ref_counts"]


# ---------------------------------------------------------------------------
# Apply scenarios
# ---------------------------------------------------------------------------


def test_aot_page_recovers_remaps_and_deletes(monkeypatch, tmp_path):
    env = Env(monkeypatch, tmp_path, _aot_tables())
    assert rep.repair_main(env.plan([AOT_PAGE]), apply=True, assume_yes=True) == 0
    t = env.client.tables
    assert env.eps("attack-on-titan") == list(range(1, 26))
    for sid in ("roar", "chibi", "mal-39477", "mal-42091"):
        assert env.eps(sid) == []
        row = next(s for s in t["series"] if s["id"] == sid)
        assert row["principal_slug"] is None and row["fallback_slug"] is None
    assert {(r["id"], r["episode_id"], r["series_id"]) for r in t["watch_progress"]} == {
        (1, "attack-on-titan-ep-5", "attack-on-titan"), (2, "attack-on-titan-ep-12", "attack-on-titan")}
    u = t["user_continue_watching"][0]
    assert (u["episode_id"], u["next_episode_id"], u["series_id"]) == (
        "attack-on-titan-ep-12", "attack-on-titan-ep-13", "attack-on-titan")
    series_id, slug, cur, kw = env.recover_calls[0]
    assert (series_id, slug, cur) == ("attack-on-titan", "shingeki-no-kyojin", 25)
    assert kw["mode"] == "grace" and kw["backfill_mode"] == "write" and kw["expected"] == 25


def test_slime_part2_gets_13_and_progress_remapped(monkeypatch, tmp_path):
    slug = "slime-s2"
    tables = {
        "series": [_series("slime-s2", slug, order=1, count=12), _series("part2", slug, order=2, count=12),
                   _series("veldora", slug, order=3, count=1)],
        "episodes": _eps("slime-s2", range(1, 13)) + _eps("veldora", [13]),
        "watch_progress": [_wp(1, "u1", "veldora-ep-13", "veldora")],
        "user_continue_watching": [],
    }
    env = Env(monkeypatch, tmp_path, tables)
    assert rep.repair_main(env.plan([_page(slug, "part2", ["veldora"])]), apply=True, assume_yes=True) == 0
    assert env.eps("part2") == list(range(13, 25))
    assert env.eps("veldora") == []
    assert env.client.tables["watch_progress"][0]["episode_id"] == "part2-ep-13"
    assert env.recover_calls[0][3]["expected"] == 12


def test_duplicate_case_remaps_without_recovery(monkeypatch, tmp_path):
    slug = "gintama-season-1"
    tables = {
        "series": [_series("gintama", slug, count=201), _series("mal-2951", slug, order=2, count=1)],
        "episodes": _eps("gintama", range(1, 51)) + _eps("mal-2951", [50]),
        "watch_progress": [_wp(1, "u1", "mal-2951-ep-50", "mal-2951")],
        "user_continue_watching": [],
    }
    env = Env(monkeypatch, tmp_path, tables)
    assert rep.repair_main(env.plan([_page(slug, "gintama", ["mal-2951"])]), apply=True, assume_yes=True) == 0
    assert env.recover_calls == []
    assert env.eps("mal-2951") == [] and env.eps("gintama") == list(range(1, 51))
    assert env.client.tables["watch_progress"][0]["episode_id"] == "gintama-ep-50"


def _gintama_conflict(released_ts, owner_ts, released_sec=10, owner_sec=10):
    slug = "gintama-season-1"
    return {
        "series": [_series("gintama", slug, count=201), _series("mal-2951", slug, order=2, count=1)],
        "episodes": _eps("gintama", range(1, 51)) + _eps("mal-2951", [50]),
        "watch_progress": [_wp(1, "u1", "mal-2951-ep-50", "mal-2951", released_sec, released_ts),
                           _wp(2, "u1", "gintama-ep-50", "gintama", owner_sec, owner_ts)],
        "user_continue_watching": [],
    }, slug


@pytest.mark.parametrize("r_ts,o_ts,r_sec,o_sec,kept_id", [
    ("2026-02-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00", 5, 99, 1),   # released newer
    ("2026-01-01T00:00:00+00:00", "2026-02-01T00:00:00+00:00", 99, 5, 2),   # owner newer
    ("2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00", 50, 10, 1),   # tie -> progress
    ("2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00", 10, 50, 2),
])
def test_conflict_keeps_most_recent(monkeypatch, tmp_path, r_ts, o_ts, r_sec, o_sec, kept_id):
    tables, slug = _gintama_conflict(r_ts, o_ts, r_sec, o_sec)
    env = Env(monkeypatch, tmp_path, tables)
    assert rep.repair_main(env.plan([_page(slug, "gintama", ["mal-2951"])]), apply=True, assume_yes=True) == 0
    rows = env.client.tables["watch_progress"]
    assert [(r["id"], r["episode_id"]) for r in rows] == [(kept_id, "gintama-ep-50")]


def test_continue_watching_franchise_key_conflict_keeps_most_recent(monkeypatch, tmp_path):
    tables, slug = _gintama_conflict("2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00")
    tables["watch_progress"] = []
    tables["series"][0]["franchise_id"] = "fg"
    tables["series"][1]["franchise_id"] = "fg"
    tables["user_continue_watching"] = [
        _ucw("u1", "mal-2951", "mal-2951", "mal-2951-ep-50", ts="2026-03-01T00:00:00+00:00"),
        _ucw("u1", "fg", "gintama", "gintama-ep-3", ts="2026-02-01T00:00:00+00:00"),
    ]
    env = Env(monkeypatch, tmp_path, tables)
    assert rep.repair_main(env.plan([_page(slug, "gintama", ["mal-2951"])]), apply=True, assume_yes=True) == 0
    rows = env.client.tables["user_continue_watching"]
    assert len(rows) == 1
    assert (rows[0]["franchise_key"], rows[0]["episode_id"], rows[0]["series_id"]) == ("fg", "gintama-ep-50", "gintama")


def test_owner_recovery_missing_referenced_number_stops_page(monkeypatch, tmp_path):
    env = Env(monkeypatch, tmp_path, _aot_tables(), recover=[n for n in range(1, 19) if n != 12])
    assert rep.repair_main(env.plan([AOT_PAGE]), apply=True, assume_yes=True) == 1
    assert env.eps("mal-39477") == list(range(11, 18))  # nothing deleted
    assert env.client.tables["watch_progress"][1]["episode_id"] == "mal-39477-ep-12"  # nothing remapped
    assert ("delete", "episodes") not in env.client.writes


def test_failure_in_one_page_does_not_stop_others(monkeypatch, tmp_path):
    tables, slug = _gintama_conflict("2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00")
    aot = _aot_tables()
    tables["series"] += aot["series"]
    tables["episodes"] += aot["episodes"]
    tables["watch_progress"] += aot["watch_progress"]
    env = Env(monkeypatch, tmp_path, tables, recover=[n for n in range(1, 19) if n != 12])
    code = rep.repair_main(env.plan([AOT_PAGE, _page(slug, "gintama", ["mal-2951"])]),
                           apply=True, assume_yes=True)
    assert code == 1
    assert env.eps("mal-2951") == []  # second page still repaired


# ---------------------------------------------------------------------------
# Idempotency, todo, invalid plans, ambiguity, confirmation
# ---------------------------------------------------------------------------


def test_rerun_is_no_changes_with_zero_writes(monkeypatch, tmp_path):
    env = Env(monkeypatch, tmp_path, _aot_tables())
    path = env.plan([AOT_PAGE])
    assert rep.repair_main(path, apply=True, assume_yes=True) == 0
    env.client.writes.clear()
    env.recover_calls.clear()
    assert rep.repair_main(path, apply=True, assume_yes=True) == 0
    assert {r["status"] for r in env.csv_rows()} == {"no_changes"}
    assert env.client.writes == [] and env.recover_calls == []


def test_interrupted_run_is_resumed(monkeypatch, tmp_path):
    tables = _aot_tables()
    for s in tables["series"][1:]:
        s["principal_slug"] = None  # slugs already released, episodes left behind
    env = Env(monkeypatch, tmp_path, tables)
    assert rep.repair_main(env.plan([AOT_PAGE]), apply=True, assume_yes=True) == 0
    assert env.eps("chibi") == [] and env.eps("attack-on-titan") == list(range(1, 26))


def test_todo_page_is_refused_on_apply(monkeypatch, tmp_path):
    env = Env(monkeypatch, tmp_path, _aot_tables())
    page = copy.deepcopy(AOT_PAGE)
    page["release"][0]["todo"] = "fill me"
    assert rep.repair_main(env.plan([page]), apply=True, assume_yes=True) == 0
    assert env.client.writes == [] and env.recover_calls == []
    assert "fill me" in env.csv_rows()[0]["todo"]


def test_invalid_plan_cases(monkeypatch, tmp_path):
    tables = _aot_tables()
    env = Env(monkeypatch, tmp_path, tables)
    pages = [
        _page("shingeki-no-kyojin", "attack-on-titan", ["ghost"]),                   # unknown series
        _page("other-slug", "attack-on-titan", ["roar"]),                            # owner slug mismatch
        _page("shingeki-no-kyojin", "no-owner", ["roar"]),                           # missing owner
        _page("shingeki-no-kyojin", "attack-on-titan",
              [{"series_id": "roar", "principal_slug": "shingeki-no-kyojin", "fallback_slug": None}]),
    ]
    tables["series"].append(_series("loner", "something-else"))
    pages.append(_page("shingeki-no-kyojin", "attack-on-titan", ["loner"]))          # does not hold slug
    assert rep.repair_main(env.plan(pages), apply=True, assume_yes=True) == 0
    assert [r["status"] for r in env.csv_rows()] == ["invalid_plan"] * 5
    assert env.client.writes == []


def test_ambiguous_offset_skips_page(monkeypatch, tmp_path):
    tables = _aot_tables()
    # a legitimate sharer that stays on the page has an unknown season_order
    tables["series"].append(_series("keeper", "shingeki-no-kyojin", order=None, count=3))
    env = Env(monkeypatch, tmp_path, tables)
    assert rep.repair_main(env.plan([AOT_PAGE]), apply=True, assume_yes=True) == 0
    assert {r["status"] for r in env.csv_rows()} == {"ambiguous_offset"}
    assert env.client.writes == []


def test_confirmation_prompt(monkeypatch, tmp_path):
    env = Env(monkeypatch, tmp_path, _aot_tables())
    prompts = []
    monkeypatch.setattr("builtins.input", lambda p: prompts.append(p) or "n")
    assert rep.repair_main(env.plan([AOT_PAGE]), apply=True) == 0
    assert prompts == ["Apply repair to 1 pages? [y/N] "] and env.client.writes == []
    monkeypatch.setattr("builtins.input", lambda p: "y")
    assert rep.repair_main(env.plan([AOT_PAGE]), apply=True) == 0
    assert env.eps("chibi") == []


def test_recovery_current_max_never_below_offset(monkeypatch, tmp_path):
    """Real forward path inserts every page number > current_max and
    <= offset+expected; an empty owner at offset 12 must only get 13.."""
    slug = "slime-s2"
    tables = {
        "series": [_series("slime-s2", slug, order=1, count=12), _series("part2", slug, order=2, count=12),
                   _series("veldora", slug, order=3, count=1)],
        "episodes": _eps("slime-s2", range(1, 13)) + _eps("veldora", [13]),
        "watch_progress": [], "user_continue_watching": [],
    }
    env = Env(monkeypatch, tmp_path, tables)
    calls = []

    def forward_only(series_id, slug_, current_max, **kw):
        calls.append(current_max)
        for n in range(1, 25):  # page lists 1..24
            if current_max < n <= 12 + kw["expected"]:
                env.client.tables["episodes"].append(_eps(series_id, [n])[0])
        return 0

    monkeypatch.setattr(rep.simulcast_check, "run_simulcast_update", forward_only)
    assert rep.repair_main(env.plan([_page(slug, "part2", ["veldora"])]), apply=True, assume_yes=True) == 0
    assert calls == [12]
    assert env.eps("part2") == list(range(13, 25))


def test_continue_watching_stale_row_does_not_overwrite_winner(monkeypatch, tmp_path):
    tables, slug = _gintama_conflict("2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00")
    tables["watch_progress"] = []
    tables["series"][0]["franchise_id"] = "fg"
    tables["series"][1]["franchise_id"] = "fg"
    tables["user_continue_watching"] = [
        _ucw("u1", "mal-2951", "mal-2951", "mal-2951-ep-50", sec=77, ts="2026-03-01T00:00:00+00:00"),
        _ucw("u1", "fg", "mal-2951", "mal-2951-ep-50", sec=5, ts="2026-02-01T00:00:00+00:00"),
    ]
    env = Env(monkeypatch, tmp_path, tables)
    assert rep.repair_main(env.plan([_page(slug, "gintama", ["mal-2951"])]), apply=True, assume_yes=True) == 0
    rows = env.client.tables["user_continue_watching"]
    assert len(rows) == 1
    assert (rows[0]["franchise_key"], rows[0]["episode_id"], rows[0]["progress_sec"]) == ("fg", "gintama-ep-50", 77)
