"""Unit tests for domain/download_queue.py using an in-memory fake queue."""
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("INTERNAL_JWT_SECRET", "test-internal-secret-for-tests-only")
os.environ.setdefault("SERVICE_SECRET", "test-service-secret")

from domain import download_queue as dom
from domain.nas_jobs import NasUnavailable


class FakeQueue:
    """In-memory stand-in for db.download_queue."""

    def __init__(self, eps=(), series_id="s1"):
        self.items = [
            {"id": f"i{n}", "series_id": series_id, "episode_number": n, "source": "jkanime",
             "status": "queued", "nas_job_id": None, "error": None, "started_at": None}
            for n in eps
        ]

    def _get(self, item_id):
        return next(i for i in self.items if i["id"] == item_id)

    def enqueue(self, series_id, nums, source="jkanime"):
        active = {i["episode_number"] for i in self.items
                  if i["series_id"] == series_id and i["status"] in ("queued", "downloading")}
        new = [n for n in sorted(set(nums)) if n not in active]
        for n in new:
            self.items.append({"id": f"i{n}", "series_id": series_id, "episode_number": n,
                               "source": source, "status": "queued", "nas_job_id": None,
                               "error": None, "started_at": None})
        return len(new), len(set(nums)) - len(new)

    def get_active(self):
        return next((i for i in self.items if i["status"] == "downloading"), None)

    def next_queued(self):
        return next((i for i in self.items if i["status"] == "queued"), None)

    def mark_downloading(self, item_id, job_id):
        it = self._get(item_id)
        it.update(status="downloading", nas_job_id=job_id,
                  started_at=datetime.now(timezone.utc).isoformat())

    def mark_done(self, item_id):
        self._get(item_id)["status"] = "done"

    def mark_failed(self, item_id, error):
        self._get(item_id).update(status="failed", error=error)

    def count(self, status):
        return sum(1 for i in self.items if i["status"] == status)


@pytest.fixture
def env():
    """Patch every collaborator; returns (fake_queue, mocks namespace)."""
    fq = FakeQueue([1, 2, 3])

    class M: ...
    m = M()
    with patch.object(dom, "db_queue", fq), \
         patch.object(dom.db_series, "get_stream_config", return_value={"fallback_slug": "x"}) as sc, \
         patch.object(dom.db_series, "get_series_title_year_by_id",
                      return_value={"title": "T", "year": 2020}), \
         patch.object(dom, "resolve_source", side_effect=lambda cfg, ep, src: f"http://cdn/{ep}") as rs, \
         patch.object(dom, "create_download_job",
                      side_effect=lambda *a, **k: {"jobId": f"job-{a[1]}", "status": "pending"}) as cj, \
         patch.object(dom, "get_job_status", return_value={"status": "downloading"}) as gs:
        m.stream_config, m.resolve, m.create, m.status = sc, rs, cj, gs
        yield fq, m


def test_first_tick_dispatches_exactly_one(env):
    fq, m = env
    dom.dispatch_tick()
    assert fq.count("downloading") == 1 and fq.count("queued") == 2
    assert m.create.call_count == 1
    assert fq._get("i1")["nas_job_id"] == "job-1"


def test_waits_while_downloading_and_never_two(env):
    fq, m = env
    dom.dispatch_tick()
    for _ in range(3):
        dom.dispatch_tick()
    assert fq.count("downloading") == 1
    assert m.create.call_count == 1


@pytest.mark.parametrize("phase", ["pending", "unknown"])
def test_pending_or_unknown_keeps_waiting(env, phase):
    fq, m = env
    dom.dispatch_tick()
    m.status.return_value = {"status": phase}
    dom.dispatch_tick()
    assert fq._get("i1")["status"] == "downloading"
    assert m.create.call_count == 1


def test_next_sent_only_after_done(env):
    fq, m = env
    dom.dispatch_tick()
    m.status.return_value = {"status": "done"}
    dom.dispatch_tick()
    assert fq._get("i1")["status"] == "done"
    assert fq._get("i2")["status"] == "downloading"
    assert m.create.call_count == 2
    assert fq.count("downloading") == 1


def test_next_sent_after_failed_and_error_recorded(env):
    fq, m = env
    dom.dispatch_tick()
    m.status.return_value = {"status": "failed", "error": "disk full"}
    dom.dispatch_tick()
    assert fq._get("i1")["status"] == "failed" and fq._get("i1")["error"] == "disk full"
    assert fq._get("i2")["status"] == "downloading"


def test_url_resolved_at_dispatch_time_not_enqueue(env):
    fq, m = env
    assert m.resolve.call_count == 0
    dom.dispatch_tick()
    assert m.resolve.call_count == 1
    assert m.resolve.call_args.args[1] == 1
    assert m.create.call_args.args[2] == "http://cdn/1"
    assert m.create.call_args.kwargs == {"series_title": "T", "series_year": 2020}


def test_no_source_fails_and_continues_in_same_tick(env):
    fq, m = env
    m.resolve.side_effect = lambda cfg, ep, src: None if ep == 1 else f"http://cdn/{ep}"
    dom.dispatch_tick()
    assert fq._get("i1")["status"] == "failed" and fq._get("i1")["error"] == "no_source"
    assert fq._get("i2")["status"] == "downloading"


def test_missing_stream_config_is_no_source(env):
    fq, m = env
    m.stream_config.return_value = None
    dom.dispatch_tick()
    assert fq.count("failed") == 3
    assert all(i["error"] == "no_source" for i in fq.items)
    m.create.assert_not_called()


def test_no_source_loop_is_bounded(env):
    fq, m = env
    fq.items = FakeQueue(range(1, 60)).items
    m.resolve.side_effect = lambda *a: None
    dom.dispatch_tick()
    assert fq.count("failed") == dom.MAX_ITEMS_PER_TICK
    assert fq.count("queued") == 59 - dom.MAX_ITEMS_PER_TICK


def test_nas_unavailable_leaves_item_queued(env):
    fq, m = env
    m.create.side_effect = NasUnavailable("down")
    dom.dispatch_tick()
    assert fq.count("queued") == 3 and fq.count("downloading") == 0
    m.create.side_effect = lambda *a, **k: {"jobId": "j", "status": "pending"}
    dom.dispatch_tick()
    assert fq._get("i1")["status"] == "downloading"


def test_nas_done_response_marks_done_and_moves_on(env):
    fq, m = env
    m.create.side_effect = lambda *a, **k: (
        {"jobId": "j1", "status": "done"} if a[1] == 1 else {"jobId": f"j{a[1]}", "status": "pending"}
    )
    dom.dispatch_tick()
    assert fq._get("i1")["status"] == "done"
    assert fq._get("i2")["status"] == "downloading"
    assert fq.count("downloading") == 1


def test_timeout_marks_failed_then_dispatches_next(env):
    fq, m = env
    dom.dispatch_tick()
    fq._get("i1")["started_at"] = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    m.status.return_value = {"status": "unknown"}
    dom.dispatch_tick()
    assert fq._get("i1")["status"] == "failed" and fq._get("i1")["error"] == "timeout"
    assert fq._get("i2")["status"] == "downloading"


def test_timeout_is_configurable(env, monkeypatch):
    fq, m = env
    monkeypatch.setenv("DOWNLOAD_QUEUE_TIMEOUT_MINUTES", "10")
    dom.dispatch_tick()
    fq._get("i1")["started_at"] = (datetime.now(timezone.utc) - timedelta(minutes=11)).isoformat()
    dom.dispatch_tick()
    assert fq._get("i1")["error"] == "timeout"


def test_empty_queue_is_noop(env):
    fq, m = env
    fq.items = []
    dom.dispatch_tick()
    m.create.assert_not_called()


class TestEnqueueSeries:
    def _run(self, fq, rows, downloaded):
        with patch.object(dom, "db_queue", fq), \
             patch.object(dom.db_episodes, "get_episodes_by_series", return_value=rows), \
             patch.object(dom, "list_downloaded_episodes", return_value=downloaded):
            return dom.enqueue_series("s1")

    ROWS = [
        {"episode_number": 1, "aired_at": "2020-01-01"},
        {"episode_number": 2, "aired_at": "2020-01-08"},
        {"episode_number": 3, "aired_at": "2999-01-01"},  # not released
        {"episode_number": 4, "aired_at": None, "thumbnail_url": None},  # placeholder
        {"episode_number": 5, "aired_at": None, "thumbnail_url": "http://t"},
    ]

    def test_queues_released_minus_downloaded(self):
        fq = FakeQueue()
        assert self._run(fq, self.ROWS, [1]) == {"queued": 2, "alreadyQueued": 0}
        assert [i["episode_number"] for i in fq.items] == [2, 5]

    def test_idempotent(self):
        fq = FakeQueue()
        self._run(fq, self.ROWS, [1])
        assert self._run(fq, self.ROWS, [1]) == {"queued": 0, "alreadyQueued": 2}
        assert len(fq.items) == 2

    def test_nothing_missing(self):
        fq = FakeQueue()
        assert self._run(fq, self.ROWS, [1, 2, 5]) == {"queued": 0, "alreadyQueued": 0}
