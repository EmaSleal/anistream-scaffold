"""ADR-012 Review 1: every episode-building caller must respect the shared-slug offset.

Fixtures: an earlier cour (season_order 1, episode_count 12, episodes 1-12) and a
continuation (season_order 2, episode_count 12) whose resolved page is the
earlier cour's page (native numbering 1-24).
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("INTERNAL_JWT_SECRET", "test-internal-secret-for-tests-only")
os.environ.setdefault("SERVICE_SECRET", "test-service-secret-for-tests-only")

import json
from unittest.mock import patch, MagicMock

import pytest

from routes.ingest_routes import (
    backfill_episode_metadata,
    backfill_episodes_from_jkanime,
)

_PAGE = [{"episode_number": n, "thumbnail_url": None} for n in range(1, 25)]
_PAGE_SHORT = [{"episode_number": n, "thumbnail_url": None} for n in range(1, 13)]


def _earlier(episode_count=12):
    return {
        "id": "earlier", "mal_id": 20, "season_order": 1, "episode_count": episode_count,
        "principal_slug": "shared", "fallback_slug": None,
    }


def _cont_row(episode_count=12, **extra):
    row = {
        "id": "cont", "mal_id": 21, "season_order": 2, "episode_count": episode_count,
        "principal_slug": "shared", "fallback_slug": None, "franchise_id": "20",
        "kitsu_id": None,
    }
    row.update(extra)
    return row


def _nums(episodes):
    return sorted(e["episode_number"] for e in episodes)


# ---------------------------------------------------------------------------
# (a) main ingest()
# ---------------------------------------------------------------------------

_RAW = {"mal_id": 21, "title": "Cont", "type": "TV", "genres": [], "status": "Finished Airing"}
_NORMALIZED = {
    "id": "shared", "slug": "shared", "mal_id": 21, "title": "Cont",
    "audio_formats": ["sub"], "media_type": "tv", "episode_count": 12,
}
_FRANCHISE = [
    {"mal_id": 20, "relation": "root", "order": 1, "title": "Earlier"},
    {"mal_id": 21, "relation": "Sequel", "order": 2, "title": "Cont"},
]


@pytest.fixture
def client():
    with patch("storage.get_client"):
        from app import create_app
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c


def _post_ingest(client, page, earlier_count, own_count=12):
    norm = dict(_NORMALIZED, episode_count=own_count)
    with patch("routes.ingest_routes.fetch_anime_by_id", return_value=_RAW), \
         patch("routes.ingest_routes.normalize", return_value=norm), \
         patch("routes.ingest_routes.get_series_by_mal_id", return_value=None), \
         patch("routes.ingest_routes.get_series_identity_by_id", return_value=None), \
         patch("routes.ingest_routes.get_series_identities_by_mal_ids", return_value=[]), \
         patch("routes.ingest_routes.get_episode_count", return_value=0), \
         patch("routes.ingest_routes._discover_franchise_jikan", return_value=_FRANCHISE), \
         patch("routes.ingest_routes._ingest_related", return_value={}), \
         patch("routes.ingest_routes.get_series_by_franchise", return_value=[_earlier(earlier_count)]), \
         patch("routes.ingest_routes.scrape_animeav1_episodes", return_value=page), \
         patch("routes.ingest_routes.fetch_kitsu_episodes", return_value={}), \
         patch("routes.ingest_routes.fetch_kitsu_series_status", return_value=None), \
         patch("routes.ingest_routes.search_kitsu_anime", return_value=None), \
         patch("routes.ingest_routes.fetch_jikan_episodes", return_value={}), \
         patch("routes.ingest_routes.animeav1_has_dub", return_value=False), \
         patch("routes.ingest_routes.find_jkanime_candidates", return_value=(None, None)), \
         patch("routes.ingest_routes.upsert_series") as up_series, \
         patch("routes.ingest_routes.upsert_episodes", return_value=0) as up_eps:
        res = client.post("/api/ingest", json={"mal_id": 21, "animeav1_slug": "shared"})
    assert res.status_code == 200
    return up_series, up_eps


class TestMainIngestContinuation:
    def test_page_of_earlier_cour_only_creates_no_episodes(self, client):
        up_series, up_eps = _post_ingest(client, _PAGE_SHORT, earlier_count=12)
        for call in up_eps.call_args_list:
            assert [e for e in call[0][0] if e["episode_number"] <= 12] == []
        assert "principal_slug" not in up_series.call_args[0][0]

    def test_full_page_creates_only_own_slice(self, client):
        up_series, up_eps = _post_ingest(client, _PAGE, earlier_count=12)
        assert _nums(up_eps.call_args_list[0][0][0]) == list(range(13, 25))
        assert up_series.call_args[0][0]["principal_slug"] == "shared"

    def test_undeterminable_offset_creates_no_av1_episodes(self, client):
        up_series, up_eps = _post_ingest(client, _PAGE, earlier_count=None)
        for call in up_eps.call_args_list:
            assert [e for e in call[0][0] if e["episode_number"] <= 24] == []
        assert "principal_slug" not in up_series.call_args[0][0]

    def test_capless_continuation_creates_no_av1_episodes(self, client):
        up_series, up_eps = _post_ingest(client, _PAGE, earlier_count=12, own_count=0)
        for call in up_eps.call_args_list:
            assert [e for e in call[0][0] if e["episode_number"] <= 24] == []
        assert "principal_slug" not in up_series.call_args[0][0]


# ---------------------------------------------------------------------------
# (b) simulcast refresh
# ---------------------------------------------------------------------------

_SERVICE_HEADER = {"X-Service-Key": os.environ["SERVICE_SECRET"]}


def _refresh(client, page, earlier_count, own_count=12):
    sim_row = {
        "id": "cont", "kitsu_id": None, "broadcast_day": None, "broadcast_time": None,
        "broadcast_timezone": None, "episode_count": 0, "last_simulcast_check": None,
        "principal_slug": "shared",
    }
    mal_result = MagicMock()
    mal_result.data = {"mal_id": 21, "franchise_id": "20", "season_order": 2}
    table = MagicMock()
    for m in ("select", "eq", "maybe_single", "update"):
        getattr(table, m).return_value = table
    table.execute.return_value = mal_result
    mock_client = MagicMock()
    mock_client.table.return_value = table
    with patch("routes.simulcast_routes.get_series_simulcast_data", return_value=sim_row), \
         patch("routes.simulcast_routes.update_simulcast_fields"), \
         patch("routes.simulcast_routes.get_client", return_value=mock_client), \
         patch("routes.simulcast_routes.refresh_series_from_jikan",
               return_value={"is_simulcast": False, "jikan_episode_count": own_count}), \
         patch("routes.simulcast_routes.fetch_kitsu_episodes", return_value={}), \
         patch("routes.simulcast_routes.fetch_jikan_episodes", return_value={}), \
         patch("routes.ingest_routes.get_series_by_franchise", return_value=[_earlier(earlier_count)]), \
         patch("routes.ingest_routes.scrape_animeav1_episodes", return_value=page), \
         patch("routes.simulcast_routes.upsert_episodes", side_effect=lambda e: len(e)) as up_eps:
        res = client.post("/api/simulcast/refresh/cont", headers=_SERVICE_HEADER)
    assert res.status_code == 200
    return json.loads(res.data), up_eps


class TestRefreshContinuation:
    def test_only_own_slice_upserted(self, client):
        data, up_eps = _refresh(client, _PAGE, earlier_count=12)
        assert _nums(up_eps.call_args[0][0]) == list(range(13, 25))
        assert data["episodes_ingested"] == 12

    def test_earlier_cour_page_only_upserts_nothing(self, client):
        data, up_eps = _refresh(client, _PAGE_SHORT, earlier_count=12)
        up_eps.assert_not_called()
        assert data["episodes_ingested"] == 0

    def test_zero_own_count_upserts_nothing(self, client):
        # refresh_series_from_jikan reports 0 -> falls back to db count (0): no ingest.
        data, up_eps = _refresh(client, _PAGE, earlier_count=12, own_count=0)
        up_eps.assert_not_called()
        assert data["refreshed"] is True

    def test_undeterminable_offset_upserts_nothing(self, client):
        data, up_eps = _refresh(client, _PAGE, earlier_count=None)
        up_eps.assert_not_called()
        assert data["refreshed"] is True and data["episodes_ingested"] == 0


# ---------------------------------------------------------------------------
# (c)/(d) backfill_episode_metadata
# ---------------------------------------------------------------------------

def _run_backfill(row, page, earlier_count, existing_nums):
    existing = [{"id": f"cont-ep-{n}", "episode_number": n} for n in existing_nums]
    with patch("db.series.get_series_by_id", return_value=row), \
         patch("db.episodes.get_episodes_by_series", return_value=existing), \
         patch("routes.ingest_routes.get_series_by_franchise", return_value=[_earlier(earlier_count)]), \
         patch("routes.ingest_routes.scrape_animeav1_episodes", return_value=page), \
         patch("routes.ingest_routes.fetch_kitsu_episodes", return_value={}), \
         patch("routes.ingest_routes.fetch_jikan_episodes", return_value={}), \
         patch("routes.ingest_routes.upsert_episodes", side_effect=lambda e: len(e)) as up:
        result = backfill_episode_metadata("cont")
    return result, up


class TestBackfillEpisodeMetadataContinuation:
    def test_updates_only_existing_own_episodes(self):
        result, up = _run_backfill(_cont_row(), _PAGE, 12, existing_nums=[13, 14])
        assert result == 2
        assert _nums(up.call_args[0][0]) == [13, 14]

    def test_creates_zero_rows_when_no_episodes_exist(self):
        result, up = _run_backfill(_cont_row(), _PAGE, 12, existing_nums=[])
        assert result == 0
        up.assert_not_called()

    def test_never_inserts_unknown_ids(self):
        _, up = _run_backfill(_cont_row(), _PAGE, 12, existing_nums=[13])
        assert [e["id"] for e in up.call_args[0][0]] == ["cont-ep-13"]

    def test_number_match_with_different_id_is_remapped_not_inserted(self):
        existing = [{"id": "other-id-13", "episode_number": 13}]
        with patch("db.series.get_series_by_id", return_value=_cont_row()), \
             patch("db.episodes.get_episodes_by_series", return_value=existing), \
             patch("routes.ingest_routes.get_series_by_franchise", return_value=[_earlier(12)]), \
             patch("routes.ingest_routes.scrape_animeav1_episodes", return_value=_PAGE), \
             patch("routes.ingest_routes.fetch_kitsu_episodes", return_value={}), \
             patch("routes.ingest_routes.fetch_jikan_episodes", return_value={}), \
             patch("routes.ingest_routes.upsert_episodes", side_effect=lambda e: len(e)) as up:
            backfill_episode_metadata("cont")
        upserted = up.call_args[0][0]
        assert [(e["id"], e["episode_number"]) for e in upserted] == [("other-id-13", 13)]

    def test_undeterminable_offset_writes_nothing(self):
        result, up = _run_backfill(_cont_row(), _PAGE, None, existing_nums=[13, 14])
        assert result == 0
        up.assert_not_called()


# ---------------------------------------------------------------------------
# backfill_episodes_from_jkanime (caller F)
# ---------------------------------------------------------------------------

def _run_jk_backfill(earlier_count, own_count=12):
    row = _cont_row(episode_count=own_count, principal_slug=None, fallback_slug="shared")
    with patch("routes.ingest_routes.get_episode_count", return_value=0), \
         patch("routes.ingest_routes.get_series_by_id", return_value=row), \
         patch("routes.ingest_routes.fetch_jkanime_series_info", return_value={"episode_count": 24}), \
         patch("routes.ingest_routes.get_series_by_franchise", return_value=[_earlier(earlier_count)]), \
         patch("routes.ingest_routes.fetch_kitsu_episodes", return_value={}), \
         patch("routes.ingest_routes.fetch_jikan_episodes", return_value={}), \
         patch("routes.ingest_routes.upsert_episodes", side_effect=lambda e: len(e)) as up:
        result = backfill_episodes_from_jkanime("cont", "shared")
    return result, up


class TestBackfillFromJkanimeContinuation:
    def test_only_own_slice_created(self):
        result, up = _run_jk_backfill(12)
        assert _nums(up.call_args[0][0]) == list(range(13, 25))

    def test_undeterminable_offset_creates_nothing(self):
        result, up = _run_jk_backfill(None)
        assert result == 0
        up.assert_not_called()

    def test_capless_continuation_creates_nothing(self):
        result, up = _run_jk_backfill(12, own_count=0)
        assert result == 0
        up.assert_not_called()
