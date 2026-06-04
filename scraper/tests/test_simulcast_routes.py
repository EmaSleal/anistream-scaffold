"""Integration tests for POST /api/simulcast/refresh/<series_id>.

All external I/O (Supabase, Jikan, Kitsu) is mocked. No real network calls.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("INTERNAL_JWT_SECRET", "test-internal-secret-for-tests-only")
os.environ.setdefault("SERVICE_SECRET", "test-service-secret")

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest


_SERVICE_KEY = "test-service-secret"
_SERVICE_HEADER = {"X-Service-Key": _SERVICE_KEY}

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _series_simulcast_row(
    series_id="my-series",
    kitsu_id="12345",
    broadcast_day="Wednesdays",
    broadcast_time="00:00",
    broadcast_timezone="Asia/Tokyo",
    episode_count=8,
    last_simulcast_check=None,
    animeflv_slug="my-series",
):
    return {
        "id": series_id,
        "kitsu_id": kitsu_id,
        "broadcast_day": broadcast_day,
        "broadcast_time": broadcast_time,
        "broadcast_timezone": broadcast_timezone,
        "episode_count": episode_count,
        "last_simulcast_check": last_simulcast_check,
        "animeflv_slug": animeflv_slug,
    }


def _jikan_data(airing=True, episodes=8, broadcast_day="Wednesdays"):
    return {
        "mal_id": 99,
        "airing": airing,
        "episodes": episodes,
        "broadcast": {
            "day": broadcast_day,
            "time": "00:00",
            "timezone": "Asia/Tokyo",
        },
        "aired": {"from": "2024-01-01"},
    }


@pytest.fixture
def client():
    """Flask test client with Supabase fully mocked."""
    with patch("storage.get_client"):
        from app import create_app
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c


# ---------------------------------------------------------------------------
# 401 — missing or wrong X-Service-Key
# ---------------------------------------------------------------------------

class TestAuthGuard:
    def test_missing_service_key_returns_401(self, client):
        res = client.post("/api/simulcast/refresh/my-series")
        assert res.status_code == 401

    def test_wrong_service_key_returns_401(self, client):
        res = client.post(
            "/api/simulcast/refresh/my-series",
            headers={"X-Service-Key": "wrong-key"},
        )
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# 404 — series not found
# ---------------------------------------------------------------------------

class TestNotFound:
    def test_unknown_series_returns_404(self, client):
        with patch("simulcast_routes.get_series_simulcast_data", return_value=None):
            res = client.post(
                "/api/simulcast/refresh/nonexistent",
                headers=_SERVICE_HEADER,
            )
        assert res.status_code == 404
        data = json.loads(res.data)
        assert "error" in data


# ---------------------------------------------------------------------------
# 200 + skipped cooldown
# ---------------------------------------------------------------------------

class TestCooldownSkip:
    def test_skips_when_last_check_within_1h(self, client):
        recent = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        row = _series_simulcast_row(last_simulcast_check=recent)

        with patch("simulcast_routes.get_series_simulcast_data", return_value=row):
            res = client.post(
                "/api/simulcast/refresh/my-series",
                headers=_SERVICE_HEADER,
            )

        assert res.status_code == 200
        data = json.loads(res.data)
        assert data["refreshed"] is False
        assert data["skipped"] == "cooldown"

    def test_proceeds_when_last_check_older_than_1h(self, client):
        old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        row = _series_simulcast_row(last_simulcast_check=old)

        jikan_data = _jikan_data()
        mock_mal_result = MagicMock()
        mock_mal_result.data = {"mal_id": 99}

        mock_table = MagicMock()
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.maybe_single.return_value = mock_table
        mock_table.execute.return_value = mock_mal_result
        mock_table.update.return_value = mock_table

        mock_client = MagicMock()
        mock_client.table.return_value = mock_table

        with patch("simulcast_routes.get_series_simulcast_data", return_value=row), \
             patch("simulcast_routes.update_simulcast_fields"), \
             patch("storage.get_client", return_value=mock_client), \
             patch("simulcast_routes.fetch_anime_by_id", return_value=jikan_data), \
             patch("simulcast_routes.fetch_kitsu_series_status", return_value="current"):
            res = client.post(
                "/api/simulcast/refresh/my-series",
                headers=_SERVICE_HEADER,
            )

        assert res.status_code == 200
        data = json.loads(res.data)
        assert data["refreshed"] is True


# ---------------------------------------------------------------------------
# 200 + is_simulcast: true — jikan airing + kitsu current
# ---------------------------------------------------------------------------

class TestSimulcastTrue:
    def test_jikan_airing_and_kitsu_current_returns_is_simulcast_true(self, client):
        row = _series_simulcast_row()
        jikan_data = _jikan_data(airing=True)

        mock_mal_result = MagicMock()
        mock_mal_result.data = {"mal_id": 99}
        mock_table = MagicMock()
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.maybe_single.return_value = mock_table
        mock_table.execute.return_value = mock_mal_result
        mock_table.update.return_value = mock_table
        mock_client = MagicMock()
        mock_client.table.return_value = mock_table

        with patch("simulcast_routes.get_series_simulcast_data", return_value=row), \
             patch("simulcast_routes.update_simulcast_fields"), \
             patch("storage.get_client", return_value=mock_client), \
             patch("simulcast_routes.fetch_anime_by_id", return_value=jikan_data), \
             patch("simulcast_routes.fetch_kitsu_series_status", return_value="current"):
            res = client.post(
                "/api/simulcast/refresh/my-series",
                headers=_SERVICE_HEADER,
            )

        assert res.status_code == 200
        data = json.loads(res.data)
        assert data["is_simulcast"] is True
        assert data["refreshed"] is True


# ---------------------------------------------------------------------------
# 200 + is_simulcast: false — kitsu returns "finished"
# ---------------------------------------------------------------------------

class TestSimulcastFalseKitsuFinished:
    def test_kitsu_finished_returns_is_simulcast_false(self, client):
        row = _series_simulcast_row()
        jikan_data = _jikan_data(airing=True)

        mock_mal_result = MagicMock()
        mock_mal_result.data = {"mal_id": 99}
        mock_table = MagicMock()
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.maybe_single.return_value = mock_table
        mock_table.execute.return_value = mock_mal_result
        mock_table.update.return_value = mock_table
        mock_client = MagicMock()
        mock_client.table.return_value = mock_table

        with patch("simulcast_routes.get_series_simulcast_data", return_value=row), \
             patch("simulcast_routes.update_simulcast_fields"), \
             patch("storage.get_client", return_value=mock_client), \
             patch("simulcast_routes.fetch_anime_by_id", return_value=jikan_data), \
             patch("simulcast_routes.fetch_kitsu_series_status", return_value="finished"):
            res = client.post(
                "/api/simulcast/refresh/my-series",
                headers=_SERVICE_HEADER,
            )

        assert res.status_code == 200
        data = json.loads(res.data)
        assert data["is_simulcast"] is False


# ---------------------------------------------------------------------------
# 200 + episodes_ingested: 2 — jikan episode_count > DB count
# ---------------------------------------------------------------------------

class TestAutoIngest:
    def test_episodes_ingested_when_count_grows(self, client):
        row = _series_simulcast_row(episode_count=8)
        jikan_data = _jikan_data(airing=True, episodes=10)

        mock_mal_result = MagicMock()
        mock_mal_result.data = {"mal_id": 99}
        mock_table = MagicMock()
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.maybe_single.return_value = mock_table
        mock_table.execute.return_value = mock_mal_result
        mock_table.update.return_value = mock_table
        mock_client = MagicMock()
        mock_client.table.return_value = mock_table

        # Build fake new episodes list (2 new)
        fake_episodes = [{"id": f"ep{i}"} for i in range(10)]

        with patch("simulcast_routes.get_series_simulcast_data", return_value=row), \
             patch("simulcast_routes.update_simulcast_fields"), \
             patch("storage.get_client", return_value=mock_client), \
             patch("simulcast_routes.fetch_anime_by_id", return_value=jikan_data), \
             patch("simulcast_routes.fetch_kitsu_series_status", return_value="current"), \
             patch("simulcast_routes.fetch_kitsu_episodes", return_value={}), \
             patch("simulcast_routes.fetch_jikan_episodes", return_value={}), \
             patch("simulcast_routes._build_episodes", return_value=fake_episodes), \
             patch("simulcast_routes.upsert_episodes", return_value=2):
            res = client.post(
                "/api/simulcast/refresh/my-series",
                headers=_SERVICE_HEADER,
            )

        assert res.status_code == 200
        data = json.loads(res.data)
        assert data["episodes_ingested"] == 2


# ---------------------------------------------------------------------------
# 200 + Kitsu fetch skipped when no kitsu_id
# ---------------------------------------------------------------------------

class TestNoKitsuId:
    def test_kitsu_fetch_skipped_when_no_kitsu_id(self, client):
        row = _series_simulcast_row(kitsu_id=None)
        jikan_data = _jikan_data(airing=True)

        mock_mal_result = MagicMock()
        mock_mal_result.data = {"mal_id": 99}
        mock_table = MagicMock()
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.maybe_single.return_value = mock_table
        mock_table.execute.return_value = mock_mal_result
        mock_table.update.return_value = mock_table
        mock_client = MagicMock()
        mock_client.table.return_value = mock_table

        with patch("simulcast_routes.get_series_simulcast_data", return_value=row), \
             patch("simulcast_routes.update_simulcast_fields"), \
             patch("storage.get_client", return_value=mock_client), \
             patch("simulcast_routes.fetch_anime_by_id", return_value=jikan_data), \
             patch("simulcast_routes.fetch_kitsu_series_status") as mock_kitsu_fetch:
            res = client.post(
                "/api/simulcast/refresh/my-series",
                headers=_SERVICE_HEADER,
            )

        # Kitsu status fetch must NOT have been called
        mock_kitsu_fetch.assert_not_called()
        assert res.status_code == 200
        data = json.loads(res.data)
        # is_simulcast derived from jikan.airing only (True because jikan says airing)
        assert data["is_simulcast"] is True
