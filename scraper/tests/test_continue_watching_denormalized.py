"""Test stubs for the denormalized continue-watching feature.

Covers:
  4.1 — _resolve_franchise_key returns series_id when client raises
  4.2 — _resolve_franchise_key returns franchise_id on success
  4.3 — _resolve_next_episode_id returns None when no next episode exists
  4.4 — advance_episode with next_ep_id=None does NOT call _upsert_continue_watching
  4.5 — get_continue_watching excludes rows with progress_sec/duration_sec >= 0.95
  4.6 — refresh_simulcast_next_episodes swallows DB error
  4.7 — GET /api/progress/continue-watching calls get_continue_watching exactly once
"""
from __future__ import annotations

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("INTERNAL_JWT_SECRET", "test-internal-secret-for-tests-only")
os.environ.setdefault("SERVICE_SECRET", "test-service-secret-for-tests-only")

import pytest
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_client(table_data=None, raise_on_execute=False):
    """Return a mock Supabase client.

    table_data: value returned by .execute().data (or wrapped in APIResponse mock)
    raise_on_execute: if True, .execute() raises RuntimeError
    """
    mock_execute = MagicMock()
    if raise_on_execute:
        mock_execute.side_effect = RuntimeError("db error")
    else:
        mock_response = MagicMock()
        mock_response.data = table_data
        mock_execute.return_value = mock_response

    chain = MagicMock()
    chain.execute = mock_execute
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.in_.return_value = chain
    chain.maybe_single.return_value = chain
    chain.order.return_value = chain
    chain.limit.return_value = chain
    chain.update.return_value = chain
    chain.upsert.return_value = chain
    chain.is_.return_value = chain

    mock_client = MagicMock()
    mock_client.table.return_value = chain
    return mock_client, chain


# ---------------------------------------------------------------------------
# 4.1 — _resolve_franchise_key returns series_id when client raises
# ---------------------------------------------------------------------------

def test_resolve_franchise_key_returns_series_id_on_error():
    """T4.1: _resolve_franchise_key falls back to series_id when the DB raises."""
    import db.progress as db_progress

    mock_client, _ = _make_mock_client(raise_on_execute=True)
    with patch.object(db_progress.storage, "get_client", return_value=mock_client):
        result = db_progress._resolve_franchise_key("series-x")
    assert result == "series-x"


# ---------------------------------------------------------------------------
# 4.2 — _resolve_franchise_key returns franchise_id on success
# ---------------------------------------------------------------------------

def test_resolve_franchise_key_returns_franchise_id_on_success():
    """T4.2: _resolve_franchise_key returns franchise_id when DB returns it."""
    import db.progress as db_progress

    mock_client, _ = _make_mock_client(table_data={"franchise_id": "FX"})
    with patch.object(db_progress.storage, "get_client", return_value=mock_client):
        result = db_progress._resolve_franchise_key("series-x")
    assert result == "FX"


# ---------------------------------------------------------------------------
# 4.3 — _resolve_next_episode_id returns None when no next episode row exists
# ---------------------------------------------------------------------------

def test_resolve_next_episode_id_returns_none_when_no_next_episode():
    """T4.3: _resolve_next_episode_id returns None when no N+1 episode row exists."""
    import db.progress as db_progress

    mock_client, _ = _make_mock_client(table_data=None)
    with patch.object(db_progress.storage, "get_client", return_value=mock_client):
        result = db_progress._resolve_next_episode_id("series-x-ep-12", "series-x")
    assert result is None


# ---------------------------------------------------------------------------
# 4.4 — advance_episode with next_ep_id=None does NOT call _upsert_continue_watching
# ---------------------------------------------------------------------------

def test_advance_episode_none_next_ep_id_skips_ucw():
    """T4.4: advance_episode skips the next-episode UCW block when next_ep_id is None.

    UCW is still called once (for the current episode via upsert_progress), but
    the next-episode branch is skipped so it is NOT called a second time.
    """
    import db.progress as db_progress

    mock_client, _ = _make_mock_client(table_data=None)
    with patch.object(db_progress.storage, "get_client", return_value=mock_client):
        with patch.object(db_progress, "_upsert_continue_watching") as mock_ucw:
            db_progress.advance_episode(
                user_id="u-1",
                current_ep_id="series-x-ep-5",
                current_series_id="series-x",
                duration_sec=1440.0,
                next_ep_id=None,
                next_series_id=None,
            )
    # Called exactly once: for the current episode (via upsert_progress).
    # The next-episode UCW block is skipped because next_ep_id is None.
    mock_ucw.assert_called_once()


# ---------------------------------------------------------------------------
# 4.5 — get_continue_watching excludes completed episodes
# ---------------------------------------------------------------------------

def test_get_continue_watching_excludes_completed_episodes():
    """T4.5: get_continue_watching excludes rows where progress_sec/duration_sec >= 0.95."""
    import db.progress as db_progress

    ucw_rows = [
        {
            "user_id": "u-1",
            "franchise_key": "FX",
            "series_id": "series-x",
            "episode_id": "series-x-ep-1",
            "progress_sec": 1368,   # >= 0.95 of 1440 → completed, should be excluded
            "updated_at": "2026-01-02T00:00:00Z",
        },
        {
            "user_id": "u-1",
            "franchise_key": "FY",
            "series_id": "series-y",
            "episode_id": "series-y-ep-1",
            "progress_sec": 100,    # < 0.95 of 1440 → in-progress, should be included
            "updated_at": "2026-01-01T00:00:00Z",
        },
    ]
    episode_rows = [
        {
            "id": "series-x-ep-1",
            "series_id": "series-x",
            "episode_number": 1,
            "duration_sec": 1440,
            "title": "Ep 1",
            "thumbnail_url": "",
            "aired_at": "",
        },
        {
            "id": "series-y-ep-1",
            "series_id": "series-y",
            "episode_number": 1,
            "duration_sec": 1440,
            "title": "Ep 1",
            "thumbnail_url": "",
            "aired_at": "",
        },
    ]

    mock_ucw_client, _ = _make_mock_client(table_data=ucw_rows)
    with patch.object(db_progress.storage, "get_client", return_value=mock_ucw_client):
        with patch.object(db_progress, "get_episodes_by_ids", return_value=episode_rows):
            result = db_progress.get_continue_watching("u-1", limit=10)

    assert len(result) == 1
    assert result[0]["seriesId"] == "series-y"
    assert result[0]["progressSeconds"] == 100


# ---------------------------------------------------------------------------
# 4.6 — refresh_simulcast_next_episodes swallows DB error
# ---------------------------------------------------------------------------

def test_refresh_simulcast_next_episodes_swallows_db_error():
    """T4.6: refresh_simulcast_next_episodes returns None without raising on DB error."""
    import db.progress as db_progress

    mock_client, _ = _make_mock_client(raise_on_execute=True)
    with patch.object(db_progress.storage, "get_client", return_value=mock_client):
        result = db_progress.refresh_simulcast_next_episodes(
            "series-x", "series-x-ep-12", "series-x-ep-13"
        )
    assert result is None


# ---------------------------------------------------------------------------
# 4.7 — GET /api/progress/continue-watching calls get_continue_watching exactly once
# ---------------------------------------------------------------------------

def test_continue_watching_route_calls_get_continue_watching_once():
    """T4.7: The continue-watching route calls get_continue_watching exactly once."""
    import jwt as pyjwt

    SECRET = "test-internal-secret-for-tests-only"
    token = pyjwt.encode(
        {"sub": "u-1", "role": "USER", "exp": int(time.time()) + 60},
        SECRET,
        algorithm="HS256",
    )

    import auth as auth_module
    auth_module._INTERNAL_JWT_SECRET = SECRET

    from app import create_app
    app = create_app()

    with patch("db.progress.get_continue_watching", return_value=[]) as mock_gcw:
        with app.test_client() as client:
            resp = client.get(
                "/api/progress/continue-watching",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        mock_gcw.assert_called_once_with("u-1")
