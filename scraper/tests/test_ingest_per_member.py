"""T-008 / ADR-015: /api/ingest no longer ingests related members; each member
is ingested through POST /api/ingest/member; franchise BFS is capped."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("INTERNAL_JWT_SECRET", "test-internal-secret-for-tests-only")
os.environ.setdefault("SERVICE_SECRET", "test-service-secret-for-tests-only")

import pytest
from unittest.mock import patch

from routes import ingest_routes as ir
from tests.test_ingest_id_and_franchise_safety import FakeCatalog, _run_ingest, MODULE


@pytest.fixture
def client():
    with patch("storage.get_client"):
        from app import create_app
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c


_ENTRIES = [
    {"mal_id": 300, "title": "Root", "relation": "root", "order": 1},
    {"mal_id": 301, "title": "S2", "relation": "Sequel", "order": 2},
    {"mal_id": 302, "title": "S3", "relation": "Sequel", "order": 3},
]


class TestIngestReturnsMembers:
    def test_returns_members_and_never_ingests_related(self, client):
        catalog = FakeCatalog([
            {"id": "s2", "mal_id": 301, "franchise_id": "300", "season_order": 2},
        ])
        with patch(f"{MODULE}._ingest_related") as related:
            resp = _run_ingest(client, catalog, _ENTRIES, mal_id=300, av1_slug="root-slug",
                                drive_members=False)
        assert resp.status_code == 200
        related.assert_not_called()
        data = resp.get_json()
        assert data["franchise_id"] == "300"
        assert "franchise" not in data
        assert data["franchise_members"] == [
            {"mal_id": 301, "title": "S2", "relation": "Sequel", "season_order": 2,
             "already_in_catalog": True},
            {"mal_id": 302, "title": "S3", "relation": "Sequel", "season_order": 3,
             "already_in_catalog": False},
        ]
        # only the main series was written
        assert [u["mal_id"] for u in catalog.upserts] == [300]


class TestMemberEndpoint:
    def _body(self, **over):
        body = {"mal_id": 301, "franchise_id": "300", "season_order": 2,
                "relation": "Sequel", "title": "S2"}
        body.update(over)
        return body

    def test_calls_ingest_related_exactly_once(self, client):
        fake = {"status": "ok", "episodes_ingested": 12, "principal_slug": "s2-slug"}
        with patch(f"{MODULE}._ingest_related", return_value=fake) as related:
            resp = client.post("/api/ingest/member", json=self._body())
        assert resp.status_code == 200
        related.assert_called_once_with(
            {"mal_id": 301, "relation": "Sequel", "order": 2, "title": "S2"}, "300"
        )
        assert resp.get_json() == {
            "mal_id": 301, "status": "ok", "episodes_ingested": 12, "principal_slug": "s2-slug",
        }

    def test_error_status_keeps_shape_with_http_200(self, client):
        with patch(f"{MODULE}._ingest_related",
                   return_value={"status": "error: boom", "episodes_ingested": 0}):
            resp = client.post("/api/ingest/member", json=self._body())
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "error: boom"
        assert resp.get_json()["principal_slug"] is None

    @pytest.mark.parametrize("over", [
        {"mal_id": "301"}, {"mal_id": 0}, {"mal_id": True}, {"franchise_id": ""},
        {"franchise_id": 300}, {"season_order": "2"}, {"relation": ""}, {"title": 5},
    ])
    def test_validation_errors_are_json_400(self, client, over):
        with patch(f"{MODULE}._ingest_related") as related:
            resp = client.post("/api/ingest/member", json=self._body(**over))
        assert resp.status_code == 400
        assert resp.is_json and resp.get_json()["error"]
        related.assert_not_called()

    def test_non_object_body_is_json_400(self, client):
        resp = client.post("/api/ingest/member", json=[1])
        assert resp.status_code == 400 and resp.is_json

    def test_unexpected_error_is_json_500(self, client):
        with patch(f"{MODULE}._ingest_related", side_effect=RuntimeError("kaboom")):
            resp = client.post("/api/ingest/member", json=self._body())
        assert resp.status_code == 500
        assert resp.is_json and "kaboom" in resp.get_json()["error"]

    def test_existing_member_returns_already_scraped(self, client):
        existing = {"id": "s2", "franchise_id": "300"}
        with patch(f"{MODULE}.fetch_anime_by_id", return_value={"mal_id": 301, "title": "S2"}), \
             patch(f"{MODULE}.normalize", return_value={"mal_id": 301, "title": "S2"}), \
             patch(f"{MODULE}.get_series_by_mal_id", return_value=existing), \
             patch(f"{MODULE}.find_animeav1_candidates", return_value=(None, None)), \
             patch(f"{MODULE}.get_series_by_franchise", return_value=[]), \
             patch(f"{MODULE}.search_kitsu_anime", return_value=None), \
             patch(f"{MODULE}.fetch_kitsu_episodes", return_value={}), \
             patch(f"{MODULE}.fetch_kitsu_series_status", return_value=None), \
             patch(f"{MODULE}.get_episode_count", return_value=12), \
             patch(f"{MODULE}.upsert_series") as upsert_series, \
             patch(f"{MODULE}.upsert_episodes") as upsert_episodes:
            resp = client.post("/api/ingest/member", json=self._body())
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "already_scraped"
        assert resp.get_json()["episodes_ingested"] == 12
        upsert_episodes.assert_not_called()


class TestDiscoveryCap:
    def test_bfs_stops_at_cap(self):
        # Every node has two fresh Sequel children: unbounded graph.
        def relations(mal_id):
            return [{"relation": "Sequel", "entry": [
                {"type": "anime", "mal_id": mal_id * 2, "name": f"n{mal_id * 2}"},
                {"type": "anime", "mal_id": mal_id * 2 + 1, "name": f"n{mal_id * 2 + 1}"},
            ]}]

        with patch(f"{MODULE}.fetch_jikan_relations", side_effect=relations) as fetch, \
             patch(f"{MODULE}.time.sleep"):
            entries = ir._discover_franchise_jikan(1, max_members=5)
        assert len(entries) == 5
        assert fetch.call_count == 5

    def test_default_cap_is_config_constant(self):
        from config import MAX_FRANCHISE_MEMBERS
        assert MAX_FRANCHISE_MEMBERS == 80
        with patch(f"{MODULE}.fetch_jikan_relations", return_value=[]), \
             patch(f"{MODULE}.time.sleep"):
            assert len(ir._discover_franchise_jikan(1)) == 1
