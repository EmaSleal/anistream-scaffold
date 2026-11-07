"""run_scheduler_forever(): each job is gated by its own flag."""
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("INTERNAL_JWT_SECRET", "test-internal-secret-for-tests-only")
os.environ.setdefault("SERVICE_SECRET", "test-service-secret")

from scheduler import run_scheduler_forever


def _run(env):
    sched = MagicMock()
    with patch.dict(os.environ, env, clear=False), \
         patch("apscheduler.schedulers.blocking.BlockingScheduler", return_value=sched) as cls, \
         patch("apscheduler.triggers.interval.IntervalTrigger") as trig, \
         patch("signal.signal"), \
         patch("threading.Event") as ev:
        run_scheduler_forever()
    ids = [c.kwargs["id"] for c in sched.add_job.call_args_list]
    return ids, sched, cls, trig, ev


def test_only_download_queue_enabled():
    ids, sched, _, trig, _ = _run({"SIMULCAST_JOB_ENABLED": "0", "DOWNLOAD_QUEUE_ENABLED": "1"})
    assert ids == ["download_queue_dispatch"]
    trig.assert_called_once_with(seconds=30)
    kw = sched.add_job.call_args.kwargs
    assert kw["max_instances"] == 1 and kw["coalesce"] is True
    sched.start.assert_called_once()


def test_both_enabled():
    ids, sched, *_ = _run({"SIMULCAST_JOB_ENABLED": "1", "DOWNLOAD_QUEUE_ENABLED": "1"})
    assert ids == ["simulcast_discovery", "recommendations_warmup", "download_queue_dispatch"]
    sched.start.assert_called_once()


def test_only_simulcast_enabled():
    ids, *_ = _run({"SIMULCAST_JOB_ENABLED": "1", "DOWNLOAD_QUEUE_ENABLED": "0"})
    assert ids == ["simulcast_discovery", "recommendations_warmup"]


def test_none_enabled_idles_without_scheduler():
    ids, sched, cls, _, ev = _run({"SIMULCAST_JOB_ENABLED": "0", "DOWNLOAD_QUEUE_ENABLED": "0"})
    cls.assert_not_called()
    ev.return_value.wait.assert_called_once()


def test_tick_exception_is_swallowed():
    from scheduler import _run_download_queue_tick
    with patch("domain.download_queue.dispatch_tick", side_effect=RuntimeError("x")):
        _run_download_queue_tick()  # must not raise
