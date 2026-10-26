"""Unit tests for scraper/scripts/simulate_simulcast_refresh.py's grace-period
eligibility + backward gap-backfill simulation extension (Phase 3 of
simulcast-gap-recovery).

Covers:
  3.1  build_backfill_plan_rows() calls the SAME domain.simulcast.classify_recheck
       / plan_backfill functions the real cron job uses (no duplicated logic),
       performs a read-only AnimeAV1 scrape only for "airing"/"grace" candidates,
       and never performs a Supabase write.
  3.2  main() wires this into a new simulcast_backfill_plan.csv output.

All external I/O (Supabase, AnimeAV1 HTTP, Jikan HTTP) is mocked. No real
network calls.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

os.environ.setdefault("INTERNAL_JWT_SECRET", "test-internal-secret-for-tests-only")
os.environ.setdefault("SERVICE_SECRET", "test-service-secret")

from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest

import simulate_simulcast_refresh as sim

NOW = datetime(2026, 10, 12, tzinfo=timezone.utc)


def _row(**overrides):
    base = {
        "id": "series-1",
        "title": "Test Series",
        "mal_id": 1,
        "principal_slug": "test-series",
        "episode_count": 12,
        "is_simulcast": False,
        "franchise_id": None,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# build_backfill_plan_rows — parity with the real cron path
# ---------------------------------------------------------------------------


class TestBuildBackfillPlanRowsUsesRealDomainFunctions:
    def test_calls_classify_recheck_and_plan_backfill_not_duplicated(self):
        """Spies on the real domain functions to prove this script calls them
        directly rather than re-implementing the decision logic locally."""
        row = _row()
        own_nums_map = {"series-1": set(range(2, 13))}  # 2..12 ingested, episode 1 missing
        last_aired_map = {"series-1": NOW - timedelta(days=5)}

        with patch.object(sim, "classify_recheck", wraps=sim.classify_recheck) as mock_classify, \
             patch.object(sim, "plan_backfill", wraps=sim.plan_backfill) as mock_plan, \
             patch.object(sim, "get_slug_sibling_episodes", return_value={"offset": 0, "sibling_nums": set()}), \
             patch.object(sim, "scrape_animeav1_episodes", return_value=[{"episode_number": n} for n in range(1, 13)]):
            rows = sim.build_backfill_plan_rows([row], own_nums_map, last_aired_map, now_utc=NOW)

        mock_classify.assert_called_once()
        mock_plan.assert_called_once()
        assert rows[0]["mode"] == "grace"
        assert rows[0]["missing_inserts"] == "1"
        assert rows[0]["skip_reason"] == ""

    def test_ambiguous_offset_is_surfaced_for_admin_review(self):
        row = _row(franchise_id="franchise-1")
        own_nums_map = {"series-1": {13, 14}}
        last_aired_map = {"series-1": NOW - timedelta(days=5)}

        with patch.object(sim, "get_slug_sibling_episodes", return_value={
            "offset": 12,
            "sibling_nums": {1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12},  # sibling has its own gap
        }), \
             patch.object(sim, "scrape_animeav1_episodes", return_value=[{"episode_number": n} for n in range(1, 25)]):
            rows = sim.build_backfill_plan_rows(
                [row], own_nums_map, last_aired_map, now_utc=NOW,
            )

        assert rows[0]["skip_reason"] == "ambiguous_offset"
        assert rows[0]["missing_inserts"] == ""


class TestBuildBackfillPlanRowsReadOnlyScraping:
    def test_performs_read_only_animeav1_scrape_for_grace_candidate(self):
        row = _row()
        own_nums_map = {"series-1": {1, 2, 3}}
        last_aired_map = {"series-1": NOW - timedelta(days=5)}

        with patch.object(sim, "get_slug_sibling_episodes", return_value={"offset": 0, "sibling_nums": set()}), \
             patch.object(sim, "scrape_animeav1_episodes", return_value=[{"episode_number": n} for n in range(1, 5)]) as mock_scrape:
            sim.build_backfill_plan_rows([row], own_nums_map, last_aired_map, now_utc=NOW)

        mock_scrape.assert_called_once_with("test-series")

    def test_expired_mode_skips_scrape_and_is_marked_informational(self):
        """Mirrors production: expired rows go through get_expired_gap_candidates
        + mark_gap_unresolved only — never scraped or backfilled."""
        row = _row()
        own_nums_map = {"series-1": {1, 2, 3}}
        last_aired_map = {"series-1": NOW - timedelta(days=20)}

        with patch.object(sim, "scrape_animeav1_episodes") as mock_scrape:
            rows = sim.build_backfill_plan_rows([row], own_nums_map, last_aired_map, now_utc=NOW)

        mock_scrape.assert_not_called()
        assert rows[0]["mode"] == "expired"
        assert rows[0]["skip_reason"] == "grace_period_expired_no_scrape"

    def test_not_eligible_mode_skips_scrape(self):
        """have == expected -> classify_recheck returns None (regardless of
        the anchor) -> not eligible, no scrape performed."""
        row = _row(episode_count=12)
        own_nums_map = {"series-1": set(range(1, 13))}
        last_aired_map = {"series-1": NOW - timedelta(days=3)}

        with patch.object(sim, "scrape_animeav1_episodes") as mock_scrape:
            rows = sim.build_backfill_plan_rows([row], own_nums_map, last_aired_map, now_utc=NOW)

        mock_scrape.assert_not_called()
        assert rows[0]["mode"] == "not_eligible"

    def test_airing_mode_still_eligible_for_backfill_scrape(self):
        """mode='airing' also gets a backfill plan — the cron job's backward
        gap-backfill is not gated on grace mode specifically. No anchor is
        needed here since is_simulcast=True short-circuits classify_recheck."""
        row = _row(is_simulcast=True)
        own_nums_map = {"series-1": {2, 3, 4}}  # episode 1 missing

        with patch.object(sim, "get_slug_sibling_episodes", return_value={"offset": 0, "sibling_nums": set()}), \
             patch.object(sim, "scrape_animeav1_episodes", return_value=[{"episode_number": n} for n in range(1, 5)]) as mock_scrape:
            rows = sim.build_backfill_plan_rows([row], own_nums_map, {}, now_utc=NOW)

        mock_scrape.assert_called_once_with("test-series")
        assert rows[0]["mode"] == "airing"
        assert rows[0]["missing_inserts"] == "1"


# ---------------------------------------------------------------------------
# main() — zero DB writes, CSV output wiring
# ---------------------------------------------------------------------------


class TestMainIsReadOnly:
    def test_main_writes_backfill_csv_and_performs_zero_db_writes(self, tmp_path, monkeypatch):
        candidate_row = _row()

        # storage.get_client(): track every call so we can assert no write verbs
        # (update/upsert/insert) were ever invoked anywhere in the run.
        mock_client = MagicMock()
        series_select_chain = MagicMock()
        series_select_chain.select.return_value = series_select_chain
        series_select_chain.eq.return_value = series_select_chain
        series_select_chain.not_ = MagicMock()
        series_select_chain.not_.is_.return_value = series_select_chain
        series_select_chain.execute.return_value = MagicMock(data=[candidate_row])

        empty_series_chain = MagicMock()
        empty_series_chain.select.return_value = empty_series_chain
        empty_series_chain.eq.return_value = empty_series_chain
        empty_series_chain.not_ = MagicMock()
        empty_series_chain.not_.is_.return_value = empty_series_chain
        empty_series_chain.execute.return_value = MagicMock(data=[])

        episodes_chain = MagicMock()
        episodes_chain.select.return_value = episodes_chain
        episodes_chain.in_.return_value = episodes_chain
        episodes_chain.execute.return_value = MagicMock(
            data=[
                {
                    "series_id": "series-1",
                    "episode_number": n,
                    "aired_at": (NOW - timedelta(days=5)).isoformat(),
                }
                for n in range(1, 12)
            ]
        )

        call_count = {"series": 0}

        def _table(name):
            if name == "series":
                call_count["series"] += 1
                return series_select_chain if call_count["series"] == 1 else empty_series_chain
            return episodes_chain

        mock_client.table.side_effect = _table

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sim, "__file__", str(tmp_path / "simulate_simulcast_refresh.py"))

        with patch.object(sim.storage, "get_client", return_value=mock_client), \
             patch.object(sim, "fetch_anime_by_id", return_value={"airing": False, "episodes": 12}), \
             patch.object(sim, "get_slug_sibling_episodes", return_value={"offset": 0, "sibling_nums": set()}), \
             patch.object(sim, "scrape_animeav1_episodes", return_value=[{"episode_number": n} for n in range(1, 13)]), \
             patch("time.sleep"):
            sim.main(recency_days=14)

        # Zero DB writes anywhere in the run.
        mock_client.table.return_value.update.assert_not_called()
        for chain in (series_select_chain, empty_series_chain, episodes_chain):
            chain.update.assert_not_called() if hasattr(chain, "update") else None

        out_dir = os.path.join(os.path.dirname(os.path.abspath(sim.__file__)), "output")
        backfill_csv = os.path.join(out_dir, "simulcast_backfill_plan.csv")
        assert os.path.exists(backfill_csv)

        with open(backfill_csv, encoding="utf-8") as f:
            content = f.read()
        assert "series-1" in content
        assert "grace" in content


# ===========================================================================
# T-004 — recovery mode: --series / --apply / --yes (ADR-011)
# ===========================================================================

WRITE_FUNCTIONS = [
    ("storage", "upsert_series"),
    ("storage", "upsert_many"),
    ("storage", "upsert_episode"),
    ("storage", "insert_episode_if_absent"),
    ("storage", "upsert_episodes"),
    ("db.simulcast", "update_simulcast_fields"),
    ("db.simulcast", "mark_gap_unresolved"),
    ("db.progress", "upsert_progress"),
    ("db.progress", "refresh_simulcast_next_episodes"),
]


class _FakeQuery:
    def __init__(self, client, name):
        self._client = client
        self._name = name
        self._filters = []
        self._range = None

    def select(self, *a, **k):
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
        rows = [
            dict(r) for r in self._client.tables[self._name]
            if all(r.get(c) in vals for c, vals in self._filters)
        ]
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


def _eps(series_id, nums):
    return [{"series_id": series_id, "episode_number": n} for n in nums]


def _src(nums):
    return [{"episode_number": n} for n in nums]


NO_SIBLINGS = {"offset": 0, "sibling_nums": set()}


def _plan(rows_by_id, own, ids, source, siblings=NO_SIBLINGS):
    with patch.object(sim, "get_slug_sibling_episodes", return_value=siblings), \
         patch.object(sim, "scrape_animeav1_episodes", return_value=_src(source)):
        return sim.build_recovery_plan_rows(rows_by_id, own, ids)


class TestBuildRecoveryPlanRows:
    def test_trailing_gap_plans_forward_only(self):
        rows = _plan({"s1": _row(id="s1")}, {"s1": set(range(1, 12))}, ["s1"], range(1, 13))
        r = rows[0]
        assert r["forward_inserts"] == [12]
        assert r["backfill_inserts"] == []
        assert r["status"] == "ok"
        assert (r["have"], r["expected"], r["current_max"], r["offset"]) == (11, 12, 11, 0)
        assert r["source_episodes_seen"] == 12

    def test_interior_gap_plans_backfill(self):
        own = set(range(1, 6)) | set(range(7, 13))
        r = _plan({"s1": _row(id="s1")}, {"s1": own}, ["s1"], range(1, 13))[0]
        assert r["backfill_inserts"] == [6]
        assert r["forward_inserts"] == []
        assert r["status"] == "ok"

    def test_shared_slug_second_cour_never_plans_outside_offset_window(self):
        row = _row(id="s2", franchise_id="f1", episode_count=12)
        siblings = {"offset": 12, "sibling_nums": set(range(1, 13))}
        r = _plan({"s2": row}, {"s2": {13, 14}}, ["s2"], range(1, 31), siblings)[0]
        planned = r["forward_inserts"] + r["backfill_inserts"]
        assert planned, "expected some planned numbers"
        assert all(12 < n <= 24 for n in planned)
        assert r["forward_inserts"] == list(range(15, 25))
        assert r["offset"] == 12

    def test_ambiguous_offset_reports_and_plans_nothing(self):
        row = _row(id="s2", franchise_id="f1")
        siblings = {"offset": 12, "sibling_nums": set(range(1, 13)) - {3}}
        r = _plan({"s2": row}, {"s2": {13, 14}}, ["s2"], range(1, 25), siblings)[0]
        assert r["status"] == "ambiguous_offset"
        assert r["skip_reason"] == "ambiguous_offset"
        assert r["forward_inserts"] == [] and r["backfill_inserts"] == []

    def test_nothing_to_do(self):
        r = _plan({"s1": _row(id="s1")}, {"s1": set(range(1, 13))}, ["s1"], range(1, 13))[0]
        assert r["status"] == "nothing_to_do"

    def test_not_found_and_no_principal_slug_are_reported_not_fatal(self):
        rows_by_id = {"s1": _row(id="s1", principal_slug=None), "s3": _row(id="s3")}
        rows = _plan(rows_by_id, {"s3": {1}}, ["missing", "s1", "s3"], range(1, 4))
        assert [r["status"] for r in rows] == ["not_found", "no_principal_slug", "ok"]

    def test_no_expected_is_reported_and_not_scraped(self):
        with patch.object(sim, "scrape_animeav1_episodes") as scrape:
            rows = sim.build_recovery_plan_rows(
                {"s1": _row(id="s1", episode_count=None)}, {"s1": {1}}, ["s1"]
            )
        scrape.assert_not_called()
        assert rows[0]["status"] == "no_expected"

    def test_scrape_failure_is_reported(self):
        with patch.object(sim, "get_slug_sibling_episodes", return_value=NO_SIBLINGS), \
             patch.object(sim, "scrape_animeav1_episodes", side_effect=RuntimeError("boom")):
            rows = sim.build_recovery_plan_rows({"s1": _row(id="s1")}, {"s1": {1}}, ["s1"])
        assert rows[0]["status"] == "scrape_failed"

    def test_requested_order_preserved_and_deduped(self):
        rows_by_id = {"a": _row(id="a"), "b": _row(id="b")}
        rows = _plan(rows_by_id, {}, ["b", "a", "b"], range(1, 3))
        assert [r["series_id"] for r in rows] == ["b", "a"]

    def test_uses_real_domain_plan_backfill(self):
        with patch.object(sim, "plan_backfill", wraps=sim.plan_backfill) as spy:
            _plan({"s1": _row(id="s1")}, {"s1": {1}}, ["s1"], range(1, 13))
        spy.assert_called_once()


@pytest.fixture
def recovery_env(tmp_path, monkeypatch):
    """Fake client with series s1 (have 11/12), s2 (ambiguous second cour)."""
    series = [
        _row(id="s1", franchise_id="f1", principal_slug="slug-1"),
        _row(id="s2", franchise_id="f1", principal_slug="slug-2"),
    ]
    episodes = _eps("s1", range(1, 12)) + _eps("s2", [13, 14])
    client = _FakeClient(series, episodes)
    monkeypatch.setattr(sim, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(sim.storage, "get_client", lambda: client)

    def _siblings(franchise_id, slug, exclude_id):
        if exclude_id == "s1":
            return NO_SIBLINGS
        return {"offset": 12, "sibling_nums": set(range(1, 13)) - {3}}

    monkeypatch.setattr(sim, "get_slug_sibling_episodes", _siblings)
    monkeypatch.setattr(
        sim, "scrape_animeav1_episodes", lambda slug: _src(range(1, 25))
    )
    return client, tmp_path


class TestRecoveryDryRun:
    def test_dry_run_writes_csv_and_makes_zero_write_calls(self, recovery_env):
        client, out = recovery_env
        patches = [patch(f"{mod}.{fn}") for mod, fn in WRITE_FUNCTIONS]
        mocks = [p.start() for p in patches]
        try:
            with patch.object(sim.simulcast_check, "run_simulcast_update") as run:
                code = sim.cli(["--series", "s1,s2,ghost"])
        finally:
            for p in patches:
                p.stop()

        assert code == 0
        run.assert_not_called()
        for m in mocks:
            m.assert_not_called()
        assert client.writes == []

        import csv as _csv
        with open(out / "simulcast_recovery_plan.csv", encoding="utf-8") as f:
            rows = list(_csv.DictReader(f))
        assert [r["series_id"] for r in rows] == ["s1", "s2", "ghost"]
        assert rows[0]["forward_inserts"] == "12"
        assert rows[0]["status"] == "ok"
        assert rows[1]["status"] == "ambiguous_offset"
        assert rows[2]["status"] == "not_found"
        for col in ("title", "have", "expected", "offset", "current_max",
                    "source_episodes_seen", "backfill_inserts", "skip_reason"):
            assert col in rows[0]


class TestRecoveryApply:
    def _run_side_effect(self, client, sid, add):
        def _fn(*a, **k):
            client.tables["episodes"].extend(_eps(sid, add))
            return len(add)
        return _fn

    def test_apply_calls_run_simulcast_update_with_grace_and_write(self, recovery_env):
        client, _ = recovery_env
        with patch.object(
            sim.simulcast_check, "run_simulcast_update",
            side_effect=self._run_side_effect(client, "s1", [12]),
        ) as run:
            code = sim.cli(["--series", "s1", "--apply", "--yes"])
        assert code == 0
        run.assert_called_once_with(
            "s1", "slug-1", 11, mode="grace", backfill_mode="write",
            franchise_id="f1", expected=12,
        )

    def test_apply_never_runs_non_ok_series(self, recovery_env, capsys):
        client, _ = recovery_env
        with patch.object(sim.simulcast_check, "run_simulcast_update") as run:
            code = sim.cli(["--series", "s2,ghost", "--apply", "--yes"])
        run.assert_not_called()
        assert code == 0
        out = capsys.readouterr().out
        assert "ambiguous_offset" in out and "not_found" in out

    def test_mismatch_is_reported_and_exit_nonzero(self, recovery_env, capsys):
        client, _ = recovery_env
        # planned forward [12]; the run inserts 12 and 13 (unplanned)
        with patch.object(
            sim.simulcast_check, "run_simulcast_update",
            side_effect=self._run_side_effect(client, "s1", [12, 13]),
        ):
            code = sim.cli(["--series", "s1", "--apply", "--yes"])
        assert code == 1
        out = capsys.readouterr().out
        assert "MISMATCH" in out
        assert "[12]" in out and "[12, 13]" in out

    def test_failure_does_not_stop_others_and_exit_nonzero(self, recovery_env, capsys):
        client, _ = recovery_env
        client.tables["series"].append(_row(id="s3", principal_slug="slug-3"))
        client.tables["episodes"].extend(_eps("s3", range(1, 12)))

        def _fn(series_id, *a, **k):
            if series_id == "s1":
                raise RuntimeError("boom")
            client.tables["episodes"].extend(_eps(series_id, [12]))
            return 1

        with patch.object(sim.simulcast_check, "run_simulcast_update", side_effect=_fn) as run:
            code = sim.cli(["--series", "s1,s3", "--apply", "--yes"])
        assert [c.args[0] for c in run.call_args_list] == ["s1", "s3"]
        assert code == 1
        assert "FAILED" in capsys.readouterr().out

    def test_confirmation_declined_aborts_without_running(self, recovery_env, capsys):
        for answer in ("n", ""):
            with patch.object(sim.simulcast_check, "run_simulcast_update") as run, \
                 patch("builtins.input", return_value=answer):
                code = sim.cli(["--series", "s1", "--apply"])
            run.assert_not_called()
            assert code == 0
        assert "Aborted, nothing written." in capsys.readouterr().out

    def test_confirmation_yes_proceeds_and_yes_flag_skips_prompt(self, recovery_env):
        client, _ = recovery_env
        with patch.object(
            sim.simulcast_check, "run_simulcast_update",
            side_effect=self._run_side_effect(client, "s1", [12]),
        ) as run, patch("builtins.input", return_value="Y") as prompt:
            assert sim.cli(["--series", "s1", "--apply"]) == 0
        prompt.assert_called_once()
        run.assert_called_once()

        client.tables["episodes"] = [e for e in client.tables["episodes"] if e["episode_number"] != 12]
        with patch.object(
            sim.simulcast_check, "run_simulcast_update",
            side_effect=self._run_side_effect(client, "s1", [12]),
        ), patch("builtins.input", side_effect=AssertionError("must not prompt")):
            assert sim.cli(["--series", "s1", "--apply", "--yes"]) == 0

    def test_eof_on_prompt_aborts(self, recovery_env):
        with patch.object(sim.simulcast_check, "run_simulcast_update") as run, \
             patch("builtins.input", side_effect=EOFError):
            assert sim.cli(["--series", "s1", "--apply"]) == 0
        run.assert_not_called()


class TestCliArguments:
    def test_apply_without_series_fails_without_touching_anything(self, capsys):
        with patch.object(sim.storage, "get_client") as get_client, \
             patch.object(sim.simulcast_check, "run_simulcast_update") as run, \
             patch.object(sim, "main") as legacy:
            with pytest.raises(SystemExit) as exc:
                sim.cli(["--apply"])
        assert exc.value.code != 0
        get_client.assert_not_called()
        run.assert_not_called()
        legacy.assert_not_called()
        assert "--series" in capsys.readouterr().err

    def test_no_series_keeps_legacy_path_with_positional_recency_days(self):
        with patch.object(sim, "main") as legacy:
            assert sim.cli(["30"]) == 0
            legacy.assert_called_once_with(30)
            legacy.reset_mock()
            sim.cli([])
            legacy.assert_called_once_with(14)


class TestApplyPreReadFailure:
    def test_pre_read_error_fails_that_series_and_continues(self, recovery_env, capsys):
        client, _ = recovery_env
        client.tables["series"].append(_row(id="s3", principal_slug="slug-3"))
        client.tables["episodes"].extend(_eps("s3", range(1, 12)))

        real = sim._fetch_own_nums
        state = {"apply_reads": 0}

        def _flaky(ids):
            # Plan phase reads several ids at once; apply phase reads one id.
            if len(ids) == 1:
                state["apply_reads"] += 1
                if state["apply_reads"] == 1:
                    raise RuntimeError("read boom")
            return real(ids)

        def _fn(series_id, *a, **k):
            client.tables["episodes"].extend(_eps(series_id, [12]))
            return 1

        with patch.object(sim, "_fetch_own_nums", side_effect=_flaky), \
             patch.object(sim.simulcast_check, "run_simulcast_update", side_effect=_fn) as run:
            code = sim.cli(["--series", "s1,s3", "--apply", "--yes"])
        assert [c.args[0] for c in run.call_args_list] == ["s3"]
        assert code == 1
        assert "FAILED s1" in capsys.readouterr().out
