"""Unit tests for db/download_queue.py (Supabase client mocked)."""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("INTERNAL_JWT_SECRET", "test-internal-secret-for-tests-only")
os.environ.setdefault("SERVICE_SECRET", "test-service-secret")

from db import download_queue as dq


def _enqueue(client, active_rows, eps):
    with patch("storage.get_client", return_value=client), \
         patch("db.download_queue.fetch_all", return_value=active_rows):
        return dq.enqueue("s1", eps)


def test_enqueue_inserts_only_missing_from_active():
    client = MagicMock()
    result = _enqueue(client, [{"episode_number": 2}], [1, 2, 3, 3])
    assert result == (2, 1)
    inserted = client.table.return_value.insert.call_args.args[0]
    assert [r["episode_number"] for r in inserted] == [1, 3]
    assert all(r["status"] == "queued" and r["source"] == "jkanime" for r in inserted)


def test_enqueue_all_active_does_not_insert():
    client = MagicMock()
    assert _enqueue(client, [{"episode_number": 1}, {"episode_number": 2}], [1, 2]) == (0, 2)
    client.table.return_value.insert.assert_not_called()


def test_enqueue_race_falls_back_row_by_row():
    client = MagicMock()
    insert = client.table.return_value.insert
    dup = Exception("duplicate key value violates unique constraint (23505)")
    results = [dup, MagicMock(), dup]
    insert.return_value.execute.side_effect = results
    assert _enqueue(client, [], [1, 2]) == (1, 1)


def test_enqueue_non_unique_error_on_bulk_propagates():
    client = MagicMock()
    client.table.return_value.insert.return_value.execute.side_effect = Exception(
        'relation "download_queue" does not exist'
    )
    with pytest.raises(Exception, match="does not exist"):
        _enqueue(client, [], [1, 2])


def test_enqueue_non_unique_error_per_row_propagates():
    client = MagicMock()
    dup = Exception("23505")
    client.table.return_value.insert.return_value.execute.side_effect = [dup, Exception("boom")]
    with pytest.raises(Exception, match="boom"):
        _enqueue(client, [], [1, 2])


def test_enqueue_unique_violation_detected_by_code_attribute():
    client = MagicMock()
    err = Exception("x")
    err.code = "23505"
    client.table.return_value.insert.return_value.execute.side_effect = [err, MagicMock()]
    assert _enqueue(client, [], [1]) == (1, 0)


def test_next_queued_returns_first_or_none():
    client = MagicMock()
    chain = client.table.return_value.select.return_value.eq.return_value.order.return_value.order.return_value.limit.return_value
    chain.execute.return_value = MagicMock(data=[{"id": "a"}])
    with patch("storage.get_client", return_value=client):
        assert dq.next_queued() == {"id": "a"}
    chain.execute.return_value = MagicMock(data=[])
    with patch("storage.get_client", return_value=client):
        assert dq.next_queued() is None


def test_get_active_none_when_no_rows():
    client = MagicMock()
    chain = client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value
    chain.execute.return_value = MagicMock(data=[])
    with patch("storage.get_client", return_value=client):
        assert dq.get_active() is None


def test_mark_transitions_update_status():
    client = MagicMock()
    update = client.table.return_value.update
    with patch("storage.get_client", return_value=client):
        dq.mark_downloading("i1", "job-1")
        dq.mark_done("i1")
        dq.mark_failed("i1", "boom")
    payloads = [c.args[0] for c in update.call_args_list]
    assert payloads[0]["status"] == "downloading" and payloads[0]["nas_job_id"] == "job-1"
    assert payloads[0]["started_at"]
    assert payloads[1]["status"] == "done" and payloads[1]["finished_at"]
    assert payloads[2]["status"] == "failed" and payloads[2]["error"] == "boom"
    assert all("updated_at" in p for p in payloads)


def test_list_for_series_uses_paging_helper():
    with patch("storage.get_client"), \
         patch("db.download_queue.fetch_all", return_value=[{"id": "x"}]) as fa:
        assert dq.list_for_series("s1") == [{"id": "x"}]
    fa.assert_called_once()
