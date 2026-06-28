"""Integration tests for progress routes and build_continue_watching domain function.

The DB layer is mocked. Auth is bypassed via patched INTERNAL_JWT_SECRET and PyJWT tokens.
"""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

TEST_SECRET = "test-internal-secret-for-tests-only"
os.environ.setdefault("INTERNAL_JWT_SECRET", TEST_SECRET)
os.environ.setdefault("SERVICE_SECRET", "test-service-secret-for-tests-only")

import json
import pytest
import jwt as pyjwt
from unittest.mock import patch, MagicMock

import auth as auth_module
auth_module._INTERNAL_JWT_SECRET = TEST_SECRET


def _token(user_id: str = "u-1", role: str = "USER") -> str:
    return pyjwt.encode(
        {"sub": user_id, "role": role, "exp": int(time.time()) + 60},
        TEST_SECRET,
        algorithm="HS256",
    )


def _auth_header(user_id: str = "u-1") -> dict:
    return {"Authorization": f"Bearer {_token(user_id)}"}


def _progress_row(
    episode_id: str = "ep1",
    series_id: str = "s1",
    progress_sec: float = 100.0,
    duration_sec: float = 1440.0,
    updated_at: str = "2026-01-01T00:00:00Z",
) -> dict:
    return {
        "episode_id": episode_id,
        "series_id": series_id,
        "progress_sec": progress_sec,
        "duration_sec": duration_sec,
        "updated_at": updated_at,
    }


def _episode_row(id: str = "ep1", series_id: str = "s1") -> dict:
    return {
        "id": id,
        "series_id": series_id,
        "episode_number": 1,
        "title": "Episode 1",
        "animeflv_slug": f"{series_id}-1",
        "thumbnail_url": None,
        "aired_at": None,
        "series": {"title": "Naruto"},
    }


@pytest.fixture
def client():
    with patch("storage.get_client"):
        from app import create_app
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c


# ---------------------------------------------------------------------------
# POST /api/progress
# ---------------------------------------------------------------------------

class TestUpsertProgress:
    def test_creates_row_returns_200(self, client):
        with patch("db.progress.upsert_progress") as mock_up:
            res = client.post(
                "/api/progress",
                headers=_auth_header(),
                data=json.dumps({
                    "episode_id": "ep1",
                    "series_id": "s1",
                    "progress_sec": 120,
                    "duration_sec": 1440,
                }),
                content_type="application/json",
            )
        assert res.status_code == 200
        mock_up.assert_called_once()

    def test_update_same_episode_returns_200(self, client):
        with patch("db.progress.upsert_progress"):
            res1 = client.post(
                "/api/progress",
                headers=_auth_header(),
                data=json.dumps({"episode_id": "ep1", "series_id": "s1", "progress_sec": 100}),
                content_type="application/json",
            )
            res2 = client.post(
                "/api/progress",
                headers=_auth_header(),
                data=json.dumps({"episode_id": "ep1", "series_id": "s1", "progress_sec": 500}),
                content_type="application/json",
            )
        assert res1.status_code == 200
        assert res2.status_code == 200

    def test_missing_episode_id_returns_400(self, client):
        res = client.post(
            "/api/progress",
            headers=_auth_header(),
            data=json.dumps({"series_id": "s1", "progress_sec": 100}),
            content_type="application/json",
        )
        assert res.status_code == 400

    def test_missing_series_id_returns_400(self, client):
        res = client.post(
            "/api/progress",
            headers=_auth_header(),
            data=json.dumps({"episode_id": "ep1", "progress_sec": 100}),
            content_type="application/json",
        )
        assert res.status_code == 400

    def test_missing_progress_sec_returns_400(self, client):
        res = client.post(
            "/api/progress",
            headers=_auth_header(),
            data=json.dumps({"episode_id": "ep1", "series_id": "s1"}),
            content_type="application/json",
        )
        assert res.status_code == 400

    def test_missing_duration_sec_does_not_return_400(self, client):
        """duration_sec is nullable — default to 0, NEVER return 400."""
        with patch("db.progress.upsert_progress") as mock_up:
            res = client.post(
                "/api/progress",
                headers=_auth_header(),
                data=json.dumps({"episode_id": "ep1", "series_id": "s1", "progress_sec": 100}),
                content_type="application/json",
            )
        assert res.status_code == 200
        # Verify duration_sec defaulted to 0
        call_kwargs = mock_up.call_args
        assert call_kwargs.kwargs.get("duration_sec") == 0.0

    def test_unauthenticated_returns_401(self, client):
        res = client.post(
            "/api/progress",
            data=json.dumps({"episode_id": "ep1", "series_id": "s1", "progress_sec": 100}),
            content_type="application/json",
        )
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/progress/<episode_id>
# ---------------------------------------------------------------------------

class TestGetEpisodeProgress:
    def test_existing_row_returns_progress_sec(self, client):
        with patch("db.progress.get_episode_progress", return_value=350.0):
            res = client.get("/api/progress/ep1", headers=_auth_header())
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data["progress_sec"] == 350.0

    def test_no_row_returns_zero(self, client):
        with patch("db.progress.get_episode_progress", return_value=0):
            res = client.get("/api/progress/ep99", headers=_auth_header())
        assert res.status_code == 200
        assert json.loads(res.data)["progress_sec"] == 0

    def test_unauthenticated_returns_401(self, client):
        res = client.get("/api/progress/ep1")
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/progress/continue-watching
# ---------------------------------------------------------------------------

class TestContinueWatching:
    def test_empty_progress_returns_empty_array(self, client):
        with patch("db.progress.get_recent_progress", return_value=[]):
            res = client.get("/api/progress/continue-watching", headers=_auth_header())
        assert res.status_code == 200
        assert json.loads(res.data) == []

    def test_returns_enriched_episodes(self, client):
        rows = [_progress_row("ep1", "s1", 100, 1440)]
        eps = [_episode_row("ep1", "s1")]
        with (
            patch("db.progress.get_recent_progress", return_value=rows),
            patch("db.progress.get_series_franchise_map", return_value={"s1": "f1"}),
            patch("db.progress.get_episodes_by_ids", return_value=eps),
        ):
            res = client.get("/api/progress/continue-watching", headers=_auth_header())
        data = json.loads(res.data)
        assert res.status_code == 200
        assert len(data) == 1
        assert "episode" in data[0]
        assert data[0]["progressSeconds"] == 100

    def test_unauthenticated_returns_401(self, client):
        res = client.get("/api/progress/continue-watching")
        assert res.status_code == 401

    def test_continue_watching_route_not_matched_as_episode_id(self, client):
        """Ensure 'continue-watching' is NOT treated as an episode_id param."""
        # If routing were wrong, it would call get_episode_progress("continue-watching")
        with patch("db.progress.get_recent_progress", return_value=[]):
            res = client.get("/api/progress/continue-watching", headers=_auth_header())
        # Should hit continue_watching route (200), not episode progress route
        assert res.status_code == 200
        assert isinstance(json.loads(res.data), list)


# ---------------------------------------------------------------------------
# POST /api/progress/advance
# ---------------------------------------------------------------------------

class TestAdvanceEpisode:
    def test_advance_200(self, client):
        """Authenticated POST with all required fields returns 200 {"advanced": true}."""
        with patch("db.progress.advance_episode") as mock_advance:
            res = client.post(
                "/api/progress/advance",
                headers=_auth_header(),
                data=json.dumps({
                    "current_episode_id": "ep1",
                    "current_series_id": "s1",
                    "duration_sec": 1440,
                    "next_episode_id": "ep2",
                    "next_series_id": "s1",
                }),
                content_type="application/json",
            )
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data == {"advanced": True}
        mock_advance.assert_called_once_with(
            user_id="u-1",
            current_ep_id="ep1",
            current_series_id="s1",
            duration_sec=1440.0,
            next_ep_id="ep2",
            next_series_id="s1",
        )

    def test_advance_400_missing_next_episode_id(self, client):
        """Authenticated POST without next_episode_id returns 400."""
        res = client.post(
            "/api/progress/advance",
            headers=_auth_header(),
            data=json.dumps({
                "current_episode_id": "ep1",
                "current_series_id": "s1",
                "duration_sec": 1440,
            }),
            content_type="application/json",
        )
        assert res.status_code == 400
        data = json.loads(res.data)
        assert "error" in data

    def test_advance_401_unauthenticated(self, client):
        """POST without auth token returns 401."""
        res = client.post(
            "/api/progress/advance",
            data=json.dumps({
                "current_episode_id": "ep1",
                "current_series_id": "s1",
                "duration_sec": 1440,
                "next_episode_id": "ep2",
                "next_series_id": "s1",
            }),
            content_type="application/json",
        )
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# Unit tests: build_continue_watching (domain/progress.py)
# ---------------------------------------------------------------------------

from domain.progress import build_continue_watching, build_watch_history


# ---------------------------------------------------------------------------
# Unit tests: build_watch_history (domain/progress.py)
# ---------------------------------------------------------------------------

class TestBuildWatchHistory:
    def test_empty_input_returns_empty_list(self):
        result = build_watch_history([], [], 25)
        assert result == []

    def test_completed_episodes_are_included(self):
        """AC-B.2 / AC-B.4: NO >=95% completion filter — completed eps MUST appear."""
        rows = [_progress_row("ep1", "s1", progress_sec=1400, duration_sec=1440)]
        # 1400/1440 = 0.972 >= 0.95 → would be filtered by build_continue_watching, NOT here
        eps = [_episode_row("ep1", "s1")]

        result = build_watch_history(rows, eps, 25)
        assert len(result) == 1
        assert result[0]["episode"]["id"] == "ep1"

    def test_no_franchise_dedup_all_included(self):
        """AC-B.4: NO franchise dedup — all rows appear even from the same series."""
        rows = [
            _progress_row("ep1", "s1", 100, 1440, "2026-01-02T00:00:00Z"),
            _progress_row("ep2", "s1", 200, 1440, "2026-01-01T00:00:00Z"),
        ]
        eps = [_episode_row("ep1", "s1"), _episode_row("ep2", "s1")]

        result = build_watch_history(rows, eps, 25)
        assert len(result) == 2
        ids = [item["episode"]["id"] for item in result]
        assert "ep1" in ids
        assert "ep2" in ids

    def test_caps_at_limit(self):
        """AC-B.3: output is capped at `limit` rows."""
        rows = [_progress_row(f"ep{i}", f"s{i}", 100, 1440) for i in range(10)]
        eps = [_episode_row(f"ep{i}", f"s{i}") for i in range(10)]

        result = build_watch_history(rows, eps, 5)
        assert len(result) == 5

    def test_respects_ordering(self):
        """Output order mirrors the input order (caller passes rows sorted by updated_at DESC)."""
        rows = [
            _progress_row("ep3", "s3", 100, 1440, "2026-01-03T00:00:00Z"),
            _progress_row("ep1", "s1", 100, 1440, "2026-01-01T00:00:00Z"),
        ]
        eps = [_episode_row("ep3", "s3"), _episode_row("ep1", "s1")]

        result = build_watch_history(rows, eps, 25)
        assert result[0]["episode"]["id"] == "ep3"
        assert result[1]["episode"]["id"] == "ep1"

    def test_episode_not_found_is_skipped(self):
        """Data integrity skip — same behaviour as build_continue_watching."""
        rows = [_progress_row("ep-missing", "s1", 100, 1440)]
        result = build_watch_history(rows, [], 25)
        assert result == []

    def test_result_structure(self):
        """Each item has episode (camelCase), progressSeconds, seriesId."""
        rows = [_progress_row("ep1", "s1", 250, 1440)]
        eps = [_episode_row("ep1", "s1")]

        result = build_watch_history(rows, eps, 25)
        assert len(result) == 1
        item = result[0]
        assert "episode" in item
        assert "progressSeconds" in item
        assert "seriesId" in item
        assert item["progressSeconds"] == 250
        assert item["seriesId"] == "s1"
        assert "seriesId" in item["episode"]

    def test_duration_override_from_progress_row(self):
        """Duration from progress row overwrites the episode row value."""
        rows = [_progress_row("ep1", "s1", 200, 1500)]  # progress says 1500s
        ep = {**_episode_row("ep1", "s1")}  # episode row has no duration field
        result = build_watch_history(rows, [ep], 25)
        assert result[0]["episode"]["duration"] == 1500

    def test_zero_duration_no_override(self):
        """When duration_sec == 0, the episode's own duration is NOT overwritten."""
        rows = [_progress_row("ep1", "s1", 100, 0)]
        ep = {**_episode_row("ep1", "s1"), "duration_sec": 500}
        result = build_watch_history(rows, [ep], 25)
        # progress duration_sec=0 must not overwrite the episode's 500s duration
        assert result[0]["episode"]["duration"] == 500


# ---------------------------------------------------------------------------
# Route: GET /api/progress/history
# ---------------------------------------------------------------------------

class TestWatchHistoryRoute:
    def test_history_route_not_matched_as_episode_id(self, client):
        """ADR-004: 'history' MUST NOT resolve to get_episode_progress."""
        with patch("db.progress.get_recent_progress", return_value=[]):
            res = client.get("/api/progress/history", headers=_auth_header())
        # Should hit watch_history route (200 + list), not episode progress route
        assert res.status_code == 200
        assert isinstance(json.loads(res.data), list)

    def test_empty_progress_returns_empty_array(self, client):
        with patch("db.progress.get_recent_progress", return_value=[]):
            res = client.get("/api/progress/history", headers=_auth_header())
        assert res.status_code == 200
        assert json.loads(res.data) == []

    def test_returns_enriched_episodes(self, client):
        rows = [_progress_row("ep1", "s1", 100, 1440)]
        eps = [_episode_row("ep1", "s1")]
        with (
            patch("db.progress.get_recent_progress", return_value=rows),
            patch("db.progress.get_episodes_by_ids", return_value=eps),
        ):
            res = client.get("/api/progress/history", headers=_auth_header())
        data = json.loads(res.data)
        assert res.status_code == 200
        assert len(data) == 1
        assert "episode" in data[0]
        assert data[0]["progressSeconds"] == 100

    def test_default_limit_is_25(self, client):
        """AC-B.3: default limit is 25 when param is omitted."""
        with (
            patch("db.progress.get_recent_progress") as mock_rp,
            patch("db.progress.get_episodes_by_ids", return_value=[]),
        ):
            mock_rp.return_value = []
            client.get("/api/progress/history", headers=_auth_header())
        mock_rp.assert_called_once_with("u-1", limit=25)

    def test_custom_limit_respected(self, client):
        """Limit query param is forwarded to get_recent_progress."""
        with (
            patch("db.progress.get_recent_progress") as mock_rp,
            patch("db.progress.get_episodes_by_ids", return_value=[]),
        ):
            mock_rp.return_value = []
            client.get("/api/progress/history?limit=10", headers=_auth_header())
        mock_rp.assert_called_once_with("u-1", limit=10)

    def test_limit_capped_at_50(self, client):
        """AC-B.3: requests with limit > 50 are silently capped at 50."""
        with (
            patch("db.progress.get_recent_progress") as mock_rp,
            patch("db.progress.get_episodes_by_ids", return_value=[]),
        ):
            mock_rp.return_value = []
            client.get("/api/progress/history?limit=999", headers=_auth_header())
        mock_rp.assert_called_once_with("u-1", limit=50)

    def test_unauthenticated_returns_401(self, client):
        res = client.get("/api/progress/history")
        assert res.status_code == 401

    def test_completed_episodes_included_in_history(self, client):
        """AC-B.2: completed episodes (>=95%) must appear in history response."""
        rows = [_progress_row("ep1", "s1", progress_sec=1400, duration_sec=1440)]
        eps = [_episode_row("ep1", "s1")]
        with (
            patch("db.progress.get_recent_progress", return_value=rows),
            patch("db.progress.get_episodes_by_ids", return_value=eps),
        ):
            res = client.get("/api/progress/history", headers=_auth_header())
        data = json.loads(res.data)
        assert res.status_code == 200
        # Episode with 97.2% progress MUST appear (unlike continue-watching which filters it)
        assert len(data) == 1
        assert data[0]["episode"]["id"] == "ep1"


# ---------------------------------------------------------------------------
# Task 4.5: GET /api/progress/continue-watching — simulcast look-ahead
# ---------------------------------------------------------------------------


class TestContinueWatchingLookahead:
    """Simulcast look-ahead: synthesizes a CW entry (progressSeconds=0) when the
    next episode (current_ep + 1) exists in the DB but is not yet in the user's
    progress. All assertions are DB-only — zero external HTTP calls are made.
    """

    def _simulcast_meta(self, series_id: str, is_simulcast: bool = True) -> dict:
        """Return a series_meta dict as returned by get_series_simulcast_meta."""
        return {
            series_id: {
                "id": series_id,
                "is_simulcast": is_simulcast,
                "animeflv_slug": f"{series_id}-slug",
                "broadcast_day": None,
                "broadcast_time": None,
                "broadcast_timezone": None,
                "last_simulcast_check": None,
                "max_episode_number": 5,
            }
        }

    def _lookahead_client(self, next_ep_rows: list) -> MagicMock:
        """Build a Supabase client mock that returns next_ep_rows for the episodes look-ahead query."""
        eps_chain = MagicMock()
        eps_chain.select.return_value = eps_chain
        eps_chain.in_.return_value = eps_chain
        eps_result = MagicMock()
        eps_result.data = next_ep_rows
        eps_chain.execute.return_value = eps_result

        mock_client = MagicMock()
        mock_client.table.return_value = eps_chain
        return mock_client

    def test_next_episode_in_db_synthesized_as_cw_entry(self, client):
        """N+1 episode in DB and not in user progress → synthesized CW entry with progressSeconds=0."""
        # User has ep5 at 97% complete (filtered from regular CW by the 95% threshold)
        progress_rows = [_progress_row("ep5", "s1", 1400.0, 1440.0)]
        ep5 = {**_episode_row("ep5", "s1"), "episode_number": 5}
        meta = self._simulcast_meta("s1", is_simulcast=True)

        # Look-ahead query returns episode 6 (N+1 for series s1)
        ep6_lookahead = {
            "id": "ep6",
            "series_id": "s1",
            "episode_number": 6,
            "aired_at": None,
            "title": "Episode 6",
            "thumbnail_url": None,
            "animeflv_slug": "s1-6",
        }
        mock_storage = self._lookahead_client([ep6_lookahead])

        with (
            patch("db.progress.get_recent_progress", return_value=progress_rows),
            patch("db.progress.get_series_franchise_map", return_value={"s1": "f1"}),
            patch("db.progress.get_episodes_by_ids", return_value=[ep5]),
            patch("db.progress.get_series_simulcast_meta", return_value=meta),
            patch("storage.get_client", return_value=mock_storage),
        ):
            res = client.get("/api/progress/continue-watching", headers=_auth_header())

        assert res.status_code == 200
        data = json.loads(res.data)

        synthesized = [item for item in data if item.get("progressSeconds") == 0]
        assert len(synthesized) == 1
        assert synthesized[0]["seriesId"] == "s1"
        # map_episode_row stores episode_number under the "episode" key
        assert synthesized[0]["episode"]["episode"] == 6

    def test_next_episode_absent_from_db_not_synthesized(self, client):
        """N+1 episode NOT in DB → no synthesized entry added to result."""
        progress_rows = [_progress_row("ep5", "s1", 1400.0, 1440.0)]
        ep5 = {**_episode_row("ep5", "s1"), "episode_number": 5}
        meta = self._simulcast_meta("s1", is_simulcast=True)

        # Look-ahead query returns nothing: episode 6 does not exist yet
        mock_storage = self._lookahead_client([])

        with (
            patch("db.progress.get_recent_progress", return_value=progress_rows),
            patch("db.progress.get_series_franchise_map", return_value={"s1": "f1"}),
            patch("db.progress.get_episodes_by_ids", return_value=[ep5]),
            patch("db.progress.get_series_simulcast_meta", return_value=meta),
            patch("storage.get_client", return_value=mock_storage),
        ):
            res = client.get("/api/progress/continue-watching", headers=_auth_header())

        assert res.status_code == 200
        data = json.loads(res.data)

        # ep5 is 97% complete → filtered from regular CW; no look-ahead → empty result
        synthesized = [item for item in data if item.get("progressSeconds") == 0]
        assert len(synthesized) == 0

    def test_next_episode_already_in_user_progress_not_synthesized(self, client):
        """N+1 episode already in user's progress (episode_id_set) → dedup guard skips it."""
        # ep5 is most recent (updated_at newer), ep6 already started by user
        progress_rows = [
            _progress_row("ep5", "s1", 1400.0, 1440.0, "2026-01-02T00:00:00Z"),
            _progress_row("ep6", "s1", 100.0, 1440.0, "2026-01-01T00:00:00Z"),
        ]
        ep5 = {**_episode_row("ep5", "s1"), "episode_number": 5}
        ep6 = {**_episode_row("ep6", "s1"), "episode_number": 6}
        meta = self._simulcast_meta("s1", is_simulcast=True)

        # Look-ahead query returns ep6 — but its id is already in episode_id_set
        ep6_lookahead = {
            "id": "ep6",
            "series_id": "s1",
            "episode_number": 6,
            "aired_at": None,
            "title": "Episode 6",
            "thumbnail_url": None,
            "animeflv_slug": "s1-6",
        }
        mock_storage = self._lookahead_client([ep6_lookahead])

        with (
            patch("db.progress.get_recent_progress", return_value=progress_rows),
            patch("db.progress.get_series_franchise_map", return_value={"s1": "f1"}),
            patch("db.progress.get_episodes_by_ids", return_value=[ep5, ep6]),
            patch("db.progress.get_series_simulcast_meta", return_value=meta),
            patch("storage.get_client", return_value=mock_storage),
        ):
            res = client.get("/api/progress/continue-watching", headers=_auth_header())

        assert res.status_code == 200
        data = json.loads(res.data)

        # ep6 already in user progress → NOT synthesized as a fresh look-ahead entry
        synthesized = [item for item in data if item.get("progressSeconds") == 0]
        assert len(synthesized) == 0


class TestBuildContinueWatching:
    def test_empty_input_returns_empty_list(self):
        result = build_continue_watching([], {}, [])
        assert result == []

    def test_franchise_dedup_keeps_most_recent(self):
        """Two series in the same franchise — only keep the first (most recent)."""
        rows = [
            _progress_row("ep1", "s1", 100, 1440, "2026-01-02T00:00:00Z"),
            _progress_row("ep2", "s2", 200, 1440, "2026-01-01T00:00:00Z"),
        ]
        franchise_map = {"s1": "franchise-A", "s2": "franchise-A"}
        eps = [_episode_row("ep1", "s1"), _episode_row("ep2", "s2")]

        result = build_continue_watching(rows, franchise_map, eps)
        assert len(result) == 1
        assert result[0]["episode"]["id"] == "ep1"

    def test_different_franchises_both_included(self):
        rows = [
            _progress_row("ep1", "s1", 100, 1440),
            _progress_row("ep2", "s2", 200, 1440),
        ]
        franchise_map = {"s1": "f1", "s2": "f2"}
        eps = [_episode_row("ep1", "s1"), _episode_row("ep2", "s2")]

        result = build_continue_watching(rows, franchise_map, eps)
        assert len(result) == 2

    def test_near_complete_episode_filtered_out(self):
        """progress_sec / duration_sec >= 0.95 → episode filtered."""
        rows = [_progress_row("ep1", "s1", progress_sec=1400, duration_sec=1440)]
        # 1400/1440 = 0.972 >= 0.95 → filtered
        franchise_map = {"s1": "f1"}
        eps = [_episode_row("ep1", "s1")]

        result = build_continue_watching(rows, franchise_map, eps)
        assert result == []

    def test_exactly_95_percent_filtered_out(self):
        rows = [_progress_row("ep1", "s1", progress_sec=1368, duration_sec=1440)]
        # 1368/1440 = 0.95 → filtered
        franchise_map = {"s1": "f1"}
        eps = [_episode_row("ep1", "s1")]

        result = build_continue_watching(rows, franchise_map, eps)
        assert result == []

    def test_below_95_percent_included(self):
        rows = [_progress_row("ep1", "s1", progress_sec=1300, duration_sec=1440)]
        # 1300/1440 = 0.903 < 0.95 → included
        franchise_map = {"s1": "f1"}
        eps = [_episode_row("ep1", "s1")]

        result = build_continue_watching(rows, franchise_map, eps)
        assert len(result) == 1

    def test_zero_duration_not_filtered(self):
        """When duration_sec == 0, we cannot compute pct — do NOT filter."""
        rows = [_progress_row("ep1", "s1", progress_sec=500, duration_sec=0)]
        franchise_map = {"s1": "f1"}
        eps = [_episode_row("ep1", "s1")]

        result = build_continue_watching(rows, franchise_map, eps)
        assert len(result) == 1

    def test_caps_at_10_items(self):
        """Output is capped at 10 regardless of input size."""
        rows = [_progress_row(f"ep{i}", f"s{i}", 100, 1440) for i in range(20)]
        franchise_map = {f"s{i}": f"f{i}" for i in range(20)}
        eps = [_episode_row(f"ep{i}", f"s{i}") for i in range(20)]

        result = build_continue_watching(rows, franchise_map, eps)
        assert len(result) == 10

    def test_episode_not_found_is_skipped(self):
        """If an episode ID has no matching row in episode_rows, skip it."""
        rows = [_progress_row("ep-missing", "s1", 100, 1440)]
        franchise_map = {"s1": "f1"}
        eps = []  # No episode data returned

        result = build_continue_watching(rows, franchise_map, eps)
        assert result == []

    def test_result_structure(self):
        """Each item has episode (camelCase), progressSeconds, seriesId."""
        rows = [_progress_row("ep1", "s1", 250, 1440)]
        franchise_map = {"s1": "f1"}
        eps = [_episode_row("ep1", "s1")]

        result = build_continue_watching(rows, franchise_map, eps)
        assert len(result) == 1
        item = result[0]
        assert "episode" in item
        assert "progressSeconds" in item
        assert "seriesId" in item
        assert item["progressSeconds"] == 250
        assert item["seriesId"] == "s1"
        # Episode is camelCase-mapped
        assert "seriesId" in item["episode"]
