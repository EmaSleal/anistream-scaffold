"""Integration tests for POST /api/simulcast/refresh/<series_id>.

All external I/O (Supabase, Jikan, Kitsu) is mocked. No real network calls.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("INTERNAL_JWT_SECRET", "test-internal-secret-for-tests-only")
os.environ.setdefault("SERVICE_SECRET", "test-service-secret")

import json
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import jwt as pyjwt
import pytest


_SERVICE_KEY = "test-service-secret"
_SERVICE_HEADER = {"X-Service-Key": _SERVICE_KEY}
_INTERNAL_SECRET = "test-internal-secret-for-tests-only"


def _make_token(role: str = "ADMIN") -> str:
    payload = {"sub": "user-1", "role": role, "exp": int(time.time()) + 60}
    return pyjwt.encode(payload, _INTERNAL_SECRET, algorithm="HS256")


def _admin_header() -> dict:
    return {"Authorization": f"Bearer {_make_token('ADMIN')}"}


def _user_header() -> dict:
    return {"Authorization": f"Bearer {_make_token('USER')}"}

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
    principal_slug="my-series",
):
    return {
        "id": series_id,
        "kitsu_id": kitsu_id,
        "broadcast_day": broadcast_day,
        "broadcast_time": broadcast_time,
        "broadcast_timezone": broadcast_timezone,
        "episode_count": episode_count,
        "last_simulcast_check": last_simulcast_check,
        "principal_slug": principal_slug,
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
    import auth as auth_module
    auth_module._INTERNAL_JWT_SECRET = _INTERNAL_SECRET

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
        with patch("routes.simulcast_routes.get_series_simulcast_data", return_value=None):
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

        with patch("routes.simulcast_routes.get_series_simulcast_data", return_value=row):
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

        # Phase 1 moved Jikan/Kitsu calls into domain.jikan_refresh — patch there.
        with patch("routes.simulcast_routes.get_series_simulcast_data", return_value=row), \
             patch("routes.simulcast_routes.update_simulcast_fields"), \
             patch("storage.get_client", return_value=mock_client), \
             patch("domain.jikan_refresh.fetch_anime_by_id", return_value=jikan_data), \
             patch("domain.jikan_refresh.fetch_kitsu_series_status", return_value="current"):
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

        # Phase 1 moved Jikan/Kitsu calls into domain.jikan_refresh — patch there.
        with patch("routes.simulcast_routes.get_series_simulcast_data", return_value=row), \
             patch("routes.simulcast_routes.update_simulcast_fields"), \
             patch("storage.get_client", return_value=mock_client), \
             patch("domain.jikan_refresh.fetch_anime_by_id", return_value=jikan_data), \
             patch("domain.jikan_refresh.fetch_kitsu_series_status", return_value="current"):
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
    def test_jikan_not_airing_returns_is_simulcast_false(self, client):
        """is_simulcast is False when Jikan reports airing=False (Kitsu excluded per ADR).

        Note: resolve_simulcast_status now uses Jikan's `airing` field only.
        Kitsu status is stored but no longer drives the simulcast decision.
        """
        row = _series_simulcast_row()
        # Use airing=False so resolve_simulcast_status returns False.
        jikan_data = _jikan_data(airing=False)

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

        # Phase 1 moved Jikan/Kitsu calls into domain.jikan_refresh — patch there.
        with patch("routes.simulcast_routes.get_series_simulcast_data", return_value=row), \
             patch("routes.simulcast_routes.update_simulcast_fields"), \
             patch("storage.get_client", return_value=mock_client), \
             patch("domain.jikan_refresh.fetch_anime_by_id", return_value=jikan_data), \
             patch("domain.jikan_refresh.fetch_kitsu_series_status", return_value="finished"):
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

        # Phase 1 moved Jikan/Kitsu calls into domain.jikan_refresh — patch there.
        # fetch_kitsu_episodes, fetch_jikan_episodes, _build_episodes_from_animeav1, and
        # upsert_episodes are still called directly from simulcast_routes so those patches stay unchanged.
        with patch("routes.simulcast_routes.get_series_simulcast_data", return_value=row), \
             patch("routes.simulcast_routes.update_simulcast_fields"), \
             patch("storage.get_client", return_value=mock_client), \
             patch("domain.jikan_refresh.fetch_anime_by_id", return_value=jikan_data), \
             patch("domain.jikan_refresh.fetch_kitsu_series_status", return_value="current"), \
             patch("routes.simulcast_routes.fetch_kitsu_episodes", return_value={}), \
             patch("routes.simulcast_routes.fetch_jikan_episodes", return_value={}), \
             patch("routes.simulcast_routes._build_episodes_from_animeav1", return_value=fake_episodes), \
             patch("routes.simulcast_routes.upsert_episodes", return_value=2):
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

        # Phase 1 moved Jikan/Kitsu calls into domain.jikan_refresh — patch there.
        # The Kitsu-skip assertion uses the domain-level mock (the route delegates
        # to refresh_series_from_jikan when mal_id is available).
        with patch("routes.simulcast_routes.get_series_simulcast_data", return_value=row), \
             patch("routes.simulcast_routes.update_simulcast_fields"), \
             patch("storage.get_client", return_value=mock_client), \
             patch("domain.jikan_refresh.fetch_anime_by_id", return_value=jikan_data), \
             patch("domain.jikan_refresh.fetch_kitsu_series_status") as mock_kitsu_fetch:
            res = client.post(
                "/api/simulcast/refresh/my-series",
                headers=_SERVICE_HEADER,
            )

        # Kitsu status fetch must NOT have been called (kitsu_id=None)
        mock_kitsu_fetch.assert_not_called()
        assert res.status_code == 200
        data = json.loads(res.data)
        # is_simulcast is True because Jikan reports airing=True (sole signal per ADR)
        assert data["is_simulcast"] is True


# ---------------------------------------------------------------------------
# POST /api/simulcast/sync-jikan
# ---------------------------------------------------------------------------

class TestSyncJikanAuthGuard:
    def test_no_token_returns_401(self, client):
        res = client.post("/api/simulcast/sync-jikan")
        assert res.status_code == 401

    def test_non_admin_token_returns_403(self, client):
        res = client.post("/api/simulcast/sync-jikan", headers=_user_header())
        assert res.status_code == 403


class TestSyncJikanFetchFailure:
    def test_jikan_fetch_error_returns_502(self, client):
        with patch("routes.simulcast_routes.fetch_simulcasts", side_effect=RuntimeError("boom")), \
             patch("routes.simulcast_routes.config.MAL_CLIENT_ID", ""):
            res = client.post("/api/simulcast/sync-jikan", headers=_admin_header())
        assert res.status_code == 502
        assert "boom" in json.loads(res.data)["source_errors"]["jikan"]


class TestSyncJikanReconciliation:
    """Covers added / updated / skipped / finished in a single sync pass.

    mal_id 1 -> new series, not yet in DB -> added
    mal_id 2 -> in DB with is_simulcast=False -> updated
    mal_id 3 -> in DB with is_simulcast=True, still airing -> skipped
    mal_id 4 -> airing but Hentai genre -> excluded from add/update loop,
                still counts as "airing" so it must NOT be marked finished
    mal_id 5 -> airing but score <= 0 -> excluded from add/update loop,
                still counts as "airing" so it must NOT be marked finished
    mal_id 6 -> airing=False in the Jikan payload -> excluded entirely
    mal_id 999 -> flagged is_simulcast=True in DB but absent from the
                  Jikan airing set entirely -> finished
    """

    def _entries(self):
        return [
            {"mal_id": 1, "airing": True, "genres": [{"name": "Action"}], "score": 7.5},
            {"mal_id": 2, "airing": True, "genres": [{"name": "Action"}], "score": 7.5},
            {"mal_id": 3, "airing": True, "genres": [{"name": "Action"}], "score": 7.5},
            {"mal_id": 4, "airing": True, "genres": [{"name": "Hentai"}], "score": 7.5},
            {"mal_id": 5, "airing": True, "genres": [{"name": "Action"}], "score": 0},
            {"mal_id": 6, "airing": False, "genres": [{"name": "Action"}], "score": 8.0},
        ]

    def test_reconciles_added_updated_skipped_and_finished(self, client):
        calls = {"mal1": 0}

        def get_series_by_mal_id_side_effect(mal_id):
            if mal_id == 1:
                calls["mal1"] += 1
                return None if calls["mal1"] == 1 else {"id": "added-id"}
            if mal_id == 2:
                return {"id": "updated-id"}
            if mal_id == 3:
                return {"id": "skipped-id"}
            return None

        def get_series_by_id_side_effect(series_id):
            if series_id == "updated-id":
                return {"is_simulcast": False}
            if series_id == "skipped-id":
                return {"is_simulcast": True}
            return None

        currently_flagged_data = [
            {"id": "skipped-id", "mal_id": 3},
            {"id": "hentai-still-airing-id", "mal_id": 4},
            {"id": "finished-id", "mal_id": 999},
            {"id": "no-mal-id", "mal_id": None},
        ]

        select_chain = MagicMock()
        select_chain.eq.return_value = select_chain
        select_chain.execute.return_value = MagicMock(data=currently_flagged_data)

        update_chain = MagicMock()
        update_chain.eq.return_value = update_chain
        update_chain.execute.return_value = MagicMock()

        mock_table = MagicMock()
        mock_table.select.return_value = select_chain
        mock_table.update.return_value = update_chain

        mock_client = MagicMock()
        mock_client.table.return_value = mock_table

        with patch("routes.simulcast_routes.fetch_simulcasts", return_value=self._entries()), \
             patch("routes.simulcast_routes.get_series_by_mal_id", side_effect=get_series_by_mal_id_side_effect), \
             patch("routes.simulcast_routes.get_series_by_id", side_effect=get_series_by_id_side_effect), \
             patch("routes.simulcast_routes.upsert_series_stub"), \
             patch("routes.simulcast_routes.get_client", return_value=mock_client):
            res = client.post("/api/simulcast/sync-jikan", headers=_admin_header())

        assert res.status_code == 200
        data = json.loads(res.data)
        assert data == {"added": 1, "updated": 1, "skipped": 1, "finished": 1, "source": "jikan"}

        updates_by_id = {}
        for upd_call, eq_call in zip(mock_table.update.call_args_list, update_chain.eq.call_args_list):
            updates_by_id[eq_call.args[1]] = upd_call.args[0]

        assert updates_by_id["added-id"] == {"is_simulcast": True}
        assert updates_by_id["updated-id"] == {"is_simulcast": True}
        assert updates_by_id["finished-id"] == {"is_simulcast": False}
        assert "skipped-id" not in updates_by_id
        assert "hentai-still-airing-id" not in updates_by_id
        assert "no-mal-id" not in updates_by_id


# ---------------------------------------------------------------------------
# sync-jikan MAL fallback (ADR-017)
# ---------------------------------------------------------------------------

def _sync_mocks(flagged):
    select_chain = MagicMock()
    select_chain.eq.return_value = select_chain
    select_chain.execute.return_value = MagicMock(data=flagged)
    update_chain = MagicMock()
    update_chain.eq.return_value = update_chain
    table = MagicMock()
    table.select.return_value = select_chain
    table.update.return_value = update_chain
    mock_client = MagicMock()
    mock_client.table.return_value = table
    return mock_client, table, update_chain


def _updated_ids(table, update_chain):
    return {
        eq.args[1]: upd.args[0]
        for upd, eq in zip(table.update.call_args_list, update_chain.eq.call_args_list)
    }


def _mal_entries():
    return [
        {"mal_id": 1, "airing": True, "genres": [{"name": "Action"}], "score": 7.5},
        {"mal_id": 2, "airing": False, "genres": [{"name": "Action"}], "score": 7.5},
        {"mal_id": 3, "airing": True, "genres": [{"name": "Hentai"}], "score": 7.5},
    ]


class TestSyncJikanMalFallback:
    def _post(self, client, flagged, *, jikan_exc=RuntimeError("down"), mal_id="key",
              mal_entries=None, mal_exc=None, by_id=None):
        mock_client, table, update_chain = _sync_mocks(flagged)
        calls = {"n": 0}

        def by_mal(mid):
            if mid == 1:
                calls["n"] += 1
                return None if calls["n"] == 1 else {"id": "new-id"}
            return None

        mal_patch = (
            patch("routes.simulcast_routes.fetch_mal_season_airing", side_effect=mal_exc)
            if mal_exc else
            patch("routes.simulcast_routes.fetch_mal_season_airing",
                  return_value=mal_entries if mal_entries is not None else _mal_entries())
        )
        with patch("routes.simulcast_routes.fetch_simulcasts", side_effect=jikan_exc), \
             patch("routes.simulcast_routes.config.MAL_CLIENT_ID", mal_id), \
             mal_patch as mal_mock, \
             patch("routes.simulcast_routes.fetch_anime_by_id", side_effect=by_id) as by_id_mock, \
             patch("routes.simulcast_routes.get_series_by_mal_id", side_effect=by_mal), \
             patch("routes.simulcast_routes.get_series_by_id", return_value=None), \
             patch("routes.simulcast_routes.upsert_series_stub") as stub, \
             patch("routes.simulcast_routes.get_client", return_value=mock_client) as gc:
            res = client.post("/api/simulcast/sync-jikan", headers=_admin_header())
        return res, table, update_chain, stub, gc, by_id_mock, mal_mock

    def test_jikan_failure_uses_mal_and_applies_filters(self, client):
        res, table, uc, stub, _, _, mal_mock = self._post(client, [])
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data == {"added": 1, "updated": 0, "skipped": 0, "finished": 0,
                        "source": "mal", "unverified": 0}
        stub.assert_called_once()
        assert stub.call_args.args[0] == 1  # not-airing and Hentai entries skipped
        assert _updated_ids(table, uc) == {"new-id": {"is_simulcast": True}}

    def test_continuing_series_still_airing_not_finished(self, client):
        res, table, uc, _, _, by_id_mock, _ = self._post(
            client, [{"id": "cont", "mal_id": 50}],
            by_id=lambda mid: {"mal_id": mid, "status": "Currently Airing"},
        )
        data = json.loads(res.data)
        assert data["finished"] == 0 and data["unverified"] == 0
        by_id_mock.assert_called_once_with(50)
        assert "cont" not in _updated_ids(table, uc)

    def test_absent_and_finished_on_mal_is_finished(self, client):
        res, table, uc, *_ = self._post(
            client, [{"id": "done", "mal_id": 51}],
            by_id=lambda mid: {"mal_id": mid, "status": "Finished Airing"},
        )
        assert json.loads(res.data)["finished"] == 1
        assert _updated_ids(table, uc)["done"] == {"is_simulcast": False}

    def test_lookup_failure_is_unverified_flag_unchanged(self, client):
        def boom(mid):
            raise RuntimeError("mal down")

        res, table, uc, *_ = self._post(client, [{"id": "unk", "mal_id": 52}], by_id=boom)
        data = json.loads(res.data)
        assert data["finished"] == 0 and data["unverified"] == 1
        assert "unk" not in _updated_ids(table, uc)

    def test_lookup_budget_exceeded_marks_rest_unverified(self, client):
        # Clock: start=0, first check=1 (within budget), second check=1000 (over).
        ticks = iter([0, 1, 1000, 1001, 1002])
        with patch("routes.simulcast_routes.time.monotonic", side_effect=lambda: next(ticks)):
            res, table, uc, _, _, by_id_mock, _ = self._post(
                client,
                [{"id": "a", "mal_id": 60}, {"id": "b", "mal_id": 61}, {"id": "c", "mal_id": 62}],
                by_id=lambda mid: {"mal_id": mid, "status": "Finished Airing"},
            )
        data = json.loads(res.data)
        assert data["finished"] == 1 and data["unverified"] == 2
        by_id_mock.assert_called_once_with(60)
        updated = _updated_ids(table, uc)
        assert updated["a"] == {"is_simulcast": False}
        assert "b" not in updated and "c" not in updated

    def test_series_in_mal_list_not_looked_up(self, client):
        res, _, _, _, _, by_id_mock, _ = self._post(client, [{"id": "a", "mal_id": 1}])
        by_id_mock.assert_not_called()

    def test_both_sources_fail_returns_502_and_writes_nothing(self, client):
        res, table, _, stub, gc, _, _ = self._post(client, [], mal_exc=RuntimeError("mal boom"))
        assert res.status_code == 502
        body = json.loads(res.data)
        assert "error" in body
        assert "RuntimeError: down" in body["source_errors"]["jikan"]
        assert "mal boom" in body["source_errors"]["mal"]
        stub.assert_not_called()
        gc.assert_not_called()
        table.update.assert_not_called()

    def test_mal_client_id_unset_returns_502(self, client):
        res, table, _, stub, gc, _, mal_mock = self._post(client, [], mal_id="")
        assert res.status_code == 502
        body = json.loads(res.data)
        assert "jikan" in body["source_errors"] and "mal" in body["source_errors"]
        mal_mock.assert_not_called()
        stub.assert_not_called()
        gc.assert_not_called()


# ---------------------------------------------------------------------------
# GET /api/simulcast/gaps (simulcast-gap-recovery Phase 4 — admin visibility)
# ---------------------------------------------------------------------------

class TestGapsAuthGuard:
    def test_no_token_returns_401(self, client):
        res = client.get("/api/simulcast/gaps")
        assert res.status_code == 401

    def test_non_admin_token_returns_403(self, client):
        res = client.get("/api/simulcast/gaps", headers=_user_header())
        assert res.status_code == 403


class TestGapsListing:
    def test_returns_series_with_unresolved_gaps(self, client):
        gap_rows = [
            {
                "id": "daemons",
                "title": "Daemons of the Shadow Realm",
                "gap_unresolved_at": "2026-10-01T00:00:00+00:00",
                "gap_missing_episodes": [1, 2],
                "episode_count": 12,
                "principal_slug": "daemons",
            },
        ]

        with patch("routes.simulcast_routes.get_unresolved_gaps", return_value=gap_rows):
            res = client.get("/api/simulcast/gaps", headers=_admin_header())

        assert res.status_code == 200
        data = json.loads(res.data)
        assert data == [
            {
                "id": "daemons",
                "title": "Daemons of the Shadow Realm",
                "gapUnresolvedAt": "2026-10-01T00:00:00+00:00",
                "gapMissingEpisodes": [1, 2],
                "episodeCount": 12,
                "principalSlug": "daemons",
            },
        ]

    def test_returns_empty_list_when_no_unresolved_gaps(self, client):
        with patch("routes.simulcast_routes.get_unresolved_gaps", return_value=[]):
            res = client.get("/api/simulcast/gaps", headers=_admin_header())

        assert res.status_code == 200
        assert json.loads(res.data) == []

    def test_fails_open_to_empty_list_when_db_query_errors(self, client):
        """Fail-open: migration 004 (gap_unresolved_at column) may not be
        applied yet in production. This endpoint must not 500 the admin page
        that already works daily from /admin/simulcast — it degrades to an
        empty list instead."""
        with patch(
            "routes.simulcast_routes.get_unresolved_gaps",
            side_effect=Exception("column gap_unresolved_at does not exist"),
        ):
            res = client.get("/api/simulcast/gaps", headers=_admin_header())

        assert res.status_code == 200
        assert json.loads(res.data) == []
