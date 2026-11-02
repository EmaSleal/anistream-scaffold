"""T-007 / ADR-014: an ingest must never overwrite another MAL entry's row,
never re-parent existing rows, and always answer with JSON errors.

Covers the 2026-11-02 incident (Bleach TYBW Part 3 reused a slug that belonged
to another MAL id, and its BFS root split the franchise from '269' to '56671').
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("INTERNAL_JWT_SECRET", "test-internal-secret-for-tests-only")
os.environ.setdefault("SERVICE_SECRET", "test-service-secret-for-tests-only")

import pytest
from unittest.mock import patch

from domain.franchise import pick_franchise_id
from routes import ingest_routes as ir

MODULE = "routes.ingest_routes"


# ---------------------------------------------------------------------------
# Pure franchise tie-break
# ---------------------------------------------------------------------------
class TestPickFranchiseId:
    def test_none_when_no_rows(self):
        assert pick_franchise_id([]) is None

    def test_null_and_empty_do_not_count(self):
        assert pick_franchise_id([None, "", None]) is None
        assert pick_franchise_id([None, "269"]) == "269"

    def test_most_frequent_wins(self):
        assert pick_franchise_id(["56671", "269", "269"]) == "269"

    def test_tie_prefers_smallest_numeric(self):
        assert pick_franchise_id(["56671", "269"]) == "269"
        assert pick_franchise_id(["9", "10"]) == "9"

    def test_tie_numeric_before_non_numeric_then_lexicographic(self):
        assert pick_franchise_id(["mal-5", "700"]) == "700"
        assert pick_franchise_id(["mal-b", "mal-a"]) == "mal-a"


# ---------------------------------------------------------------------------
# Canonical id helper
# ---------------------------------------------------------------------------
class TestResolveCanonicalId:
    def test_own_row_wins(self):
        with patch(f"{MODULE}.get_series_identity_by_id") as lookup:
            assert ir._resolve_canonical_id(222, {"id": "old"}, ["slug"]) == "old"
            lookup.assert_not_called()

    def test_free_candidate_is_used(self):
        with patch(f"{MODULE}.get_series_identity_by_id", return_value=None):
            assert ir._resolve_canonical_id(222, None, ["slug"]) == "slug"

    def test_row_with_same_mal_id_is_reused(self):
        row = {"id": "slug", "mal_id": 222}
        with patch(f"{MODULE}.get_series_identity_by_id", return_value=row):
            assert ir._resolve_canonical_id(222, None, ["slug"]) == "slug"

    def test_row_of_another_mal_id_is_rejected(self):
        row = {"id": "slug", "mal_id": 111}
        with patch(f"{MODULE}.get_series_identity_by_id", return_value=row):
            assert ir._resolve_canonical_id(222, None, ["slug"]) == "mal-222"

    def test_falls_through_to_fallback_slug_candidate(self):
        def lookup(sid):
            return {"id": sid, "mal_id": 111} if sid == "taken" else None
        with patch(f"{MODULE}.get_series_identity_by_id", side_effect=lookup):
            assert ir._resolve_canonical_id(222, None, ["taken", "fallback"]) == "fallback"

    def test_empty_candidates_give_mal_id(self):
        with patch(f"{MODULE}.get_series_identity_by_id") as lookup:
            assert ir._resolve_canonical_id(222, None, [None, ""]) == "mal-222"
            lookup.assert_not_called()


# ---------------------------------------------------------------------------
# Franchise resolver
# ---------------------------------------------------------------------------
class TestResolveFranchiseId:
    def test_uses_existing_rows(self):
        rows = [
            {"id": "a", "mal_id": 269, "franchise_id": "269"},
            {"id": "b", "mal_id": 41467, "franchise_id": "269"},
        ]
        entries = [{"mal_id": 56671}, {"mal_id": 56784}]
        with patch(f"{MODULE}.get_series_identities_by_mal_ids", return_value=rows):
            assert ir._resolve_franchise_id(entries, 56784) == "269"

    def test_falls_back_to_bfs_root(self):
        entries = [{"mal_id": 56671}, {"mal_id": 56784}]
        with patch(f"{MODULE}.get_series_identities_by_mal_ids", return_value=[]):
            assert ir._resolve_franchise_id(entries, 56784) == "56671"

    def test_no_entries_gives_mal_prefixed(self):
        with patch(f"{MODULE}.get_series_identities_by_mal_ids", return_value=[]):
            assert ir._resolve_franchise_id([], 5) == "mal-5"

    def test_existing_row_keeps_its_franchise(self):
        assert ir._effective_franchise_id({"id": "x", "franchise_id": "269"}, "56671", 1) == "269"
        assert ir._effective_franchise_id({"id": "x", "franchise_id": None}, "56671", 1) == "56671"
        assert ir._effective_franchise_id(None, "56671", 1) == "56671"


# ---------------------------------------------------------------------------
# Route-level scenarios
# ---------------------------------------------------------------------------
@pytest.fixture
def client():
    with patch("storage.get_client"):
        from app import create_app
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c


class FakeCatalog:
    """In-memory series table behind the ingest route's DB helpers."""

    def __init__(self, rows):
        self.rows = {r["id"]: dict(r) for r in rows}
        self.upserts = []

    def by_mal_id(self, mal_id):
        for r in self.rows.values():
            if r.get("mal_id") == mal_id:
                return {"id": r["id"], "franchise_id": r.get("franchise_id")}
        return None

    def identity_by_id(self, sid):
        r = self.rows.get(sid)
        return None if r is None else {k: r.get(k) for k in ("id", "mal_id", "franchise_id")}

    def identities_by_mal_ids(self, mal_ids):
        return [
            {k: r.get(k) for k in ("id", "mal_id", "franchise_id")}
            for r in self.rows.values() if r.get("mal_id") in mal_ids
        ]

    def by_franchise(self, fid):
        return [r for r in self.rows.values() if r.get("franchise_id") == fid]

    def upsert(self, series):
        self.upserts.append(dict(series))
        self.rows.setdefault(series["id"], {}).update(series)


def _run_ingest(client, catalog, entries, *, mal_id, av1_slug, related_slug=None, body_extra=None,
            drive_members=True):
    """POST /api/ingest, then drive every returned member through POST /api/ingest/member.

    All network edges are mocked and the catalog faked. The member responses are
    exposed as ``resp.member_responses`` (ADR-015: members are ingested one by one).
    """
    def fetch(mid):
        return {"mal_id": mid, "title": f"T{mid}", "type": "TV"}

    def norm(raw, **_kw):
        return {"mal_id": raw["mal_id"], "title": raw["title"], "media_type": "tv"}

    def match(*_a, **_kw):
        return ([{"slug": related_slug, "title": "x"}] if related_slug else []), None

    patches = [
        patch(f"{MODULE}.fetch_anime_by_id", side_effect=fetch),
        patch(f"{MODULE}.normalize", side_effect=norm),
        patch(f"{MODULE}._discover_franchise_jikan", return_value=entries),
        patch(f"{MODULE}.get_series_by_mal_id", side_effect=catalog.by_mal_id),
        patch(f"{MODULE}.get_series_identity_by_id", side_effect=catalog.identity_by_id),
        patch(f"{MODULE}.get_series_identities_by_mal_ids", side_effect=catalog.identities_by_mal_ids),
        patch(f"{MODULE}.get_series_by_franchise", side_effect=catalog.by_franchise),
        patch(f"{MODULE}.get_series_by_id", return_value=None),
        patch(f"{MODULE}.get_episode_count", return_value=0),
        patch(f"{MODULE}.find_animeav1_candidates", side_effect=match),
        patch(f"{MODULE}.fetch_animeav1_page", return_value={"title": "x"}),
        patch(f"{MODULE}.find_jkanime_candidates", return_value=([], None)),
        patch(f"{MODULE}.scrape_animeav1_episodes", return_value=[]),
        patch(f"{MODULE}.search_kitsu_anime", return_value=None),
        patch(f"{MODULE}.fetch_kitsu_episodes", return_value={}),
        patch(f"{MODULE}.fetch_kitsu_series_status", return_value=None),
        patch(f"{MODULE}.fetch_jikan_episodes", return_value={}),
        patch(f"{MODULE}.animeav1_has_dub", return_value=False),
        patch(f"{MODULE}.upsert_series", side_effect=catalog.upsert),
        patch(f"{MODULE}.upsert_episodes", return_value=0),
        patch(f"{MODULE}.time.sleep"),
    ]
    for p in patches:
        p.start()
    try:
        body = {"mal_id": mal_id, "animeav1_slug": av1_slug, **(body_extra or {})}
        resp = client.post("/api/ingest", json=body)
        resp.member_responses = []
        if resp.status_code == 200 and drive_members:
            data = resp.get_json()
            for m in data["franchise_members"]:
                resp.member_responses.append(client.post("/api/ingest/member", json={
                    "mal_id": m["mal_id"], "franchise_id": data["franchise_id"],
                    "season_order": m["season_order"], "relation": m["relation"],
                    "title": m["title"],
                }))
        return resp
    finally:
        for p in patches:
            p.stop()


def _assert_no_mal_id_change(catalog_before, upserts):
    for payload in upserts:
        before = catalog_before.get(payload["id"])
        if before and before.get("mal_id") is not None:
            assert payload["mal_id"] == before["mal_id"], payload["id"]


_SHARED_ROW = {
    "id": "shared-slug", "mal_id": 111, "franchise_id": "A",
    "title": "Other entry", "principal_slug": "shared-slug", "season_order": 1,
}


class TestSharedSlugIncident:
    def test_main_path_does_not_overwrite_other_mal_row(self, client):
        catalog = FakeCatalog([_SHARED_ROW])
        before = {k: dict(v) for k, v in catalog.rows.items()}
        entries = [{"mal_id": 222, "title": "T222", "relation": "root", "order": 1}]

        resp = _run_ingest(client, catalog, entries, mal_id=222, av1_slug="shared-slug")

        assert resp.status_code == 200
        assert resp.get_json()["series_id"] == "mal-222"
        assert catalog.rows["shared-slug"] == before["shared-slug"]
        assert [u["id"] for u in catalog.upserts] == ["mal-222"]
        assert catalog.upserts[0]["mal_id"] == 222
        _assert_no_mal_id_change(before, catalog.upserts)

    def test_related_path_does_not_overwrite_other_mal_row(self, client):
        # Franchise B has no members besides the new ones, so the sibling
        # check inside the franchise cannot catch the collision: only the
        # catalog-wide id check does.
        catalog = FakeCatalog([_SHARED_ROW])
        before = {k: dict(v) for k, v in catalog.rows.items()}
        entries = [
            {"mal_id": 300, "title": "T300", "relation": "root", "order": 1},
            {"mal_id": 222, "title": "T222", "relation": "Sequel", "order": 2},
        ]

        resp = _run_ingest(
            client, catalog, entries, mal_id=300, av1_slug="main-slug",
            related_slug="shared-slug",
        )

        assert resp.status_code == 200
        assert resp.member_responses[0].get_json()["status"] == "ok"
        assert catalog.rows["shared-slug"] == before["shared-slug"]
        assert "mal-222" in catalog.rows
        assert all(u["id"] != "shared-slug" for u in catalog.upserts)
        _assert_no_mal_id_change(before, catalog.upserts)

    def test_same_mal_row_slug_is_reused(self, client):
        # Candidate slug belongs to a row with the SAME mal_id -> fine to reuse.
        catalog = FakeCatalog([{"id": "mine", "mal_id": 5, "franchise_id": "5"}])
        catalog.rows["mine"]["mal_id"] = 5
        # Hide the row from the by-mal lookup (as if it was not found there) but
        # keep it visible by id, to exercise the same-mal_id branch of the helper.
        with patch(f"{MODULE}.get_series_identity_by_id", return_value={"id": "mine", "mal_id": 5}):
            assert ir._resolve_canonical_id(5, None, ["mine"]) == "mine"


class TestFranchiseSplit:
    def test_all_rows_keep_resolved_franchise(self, client):
        catalog = FakeCatalog([
            {"id": "bleach", "mal_id": 269, "franchise_id": "269", "season_order": 1},
            {"id": "tybw", "mal_id": 41467, "franchise_id": "269", "season_order": 2},
        ])
        before = {k: dict(v) for k, v in catalog.rows.items()}
        entries = [
            {"mal_id": 56671, "title": "Burn the Witch", "relation": "Side story", "order": 1},
            {"mal_id": 269, "title": "Bleach", "relation": "Side story", "order": 2},
            {"mal_id": 41467, "title": "TYBW", "relation": "Sequel", "order": 3},
            {"mal_id": 56784, "title": "TYBW 3", "relation": "root", "order": 4},
        ]

        resp = _run_ingest(client, catalog, entries, mal_id=56784, av1_slug="tybw-3")

        assert resp.status_code == 200
        assert resp.get_json()["franchise_id"] == "269"
        assert {u["id"] for u in catalog.upserts} == {"tybw-3", "bleach", "tybw", "mal-56671"}
        assert all(u["franchise_id"] == "269" for u in catalog.upserts)
        _assert_no_mal_id_change(before, catalog.upserts)

    def test_existing_differing_franchise_is_kept(self, client):
        catalog = FakeCatalog([
            {"id": "a", "mal_id": 1, "franchise_id": "100", "season_order": 1},
            {"id": "b", "mal_id": 2, "franchise_id": "100", "season_order": 2},
            {"id": "odd", "mal_id": 3, "franchise_id": "999", "season_order": 3},
        ])
        entries = [
            {"mal_id": 1, "title": "A", "relation": "root", "order": 1},
            {"mal_id": 2, "title": "B", "relation": "Sequel", "order": 2},
            {"mal_id": 3, "title": "C", "relation": "Sequel", "order": 3},
        ]

        resp = _run_ingest(client, catalog, entries, mal_id=1, av1_slug=None)

        assert resp.status_code == 200
        by_id = {u["id"]: u for u in catalog.upserts}
        assert by_id["a"]["franchise_id"] == "100"
        assert by_id["b"]["franchise_id"] == "100"
        assert by_id["odd"]["franchise_id"] == "999"


# ---------------------------------------------------------------------------
# JSON errors
# ---------------------------------------------------------------------------
class TestJsonErrors:
    def test_unexpected_exception_is_json_500(self, client):
        with patch(f"{MODULE}.fetch_anime_by_id", return_value={"mal_id": 1}), \
             patch(f"{MODULE}.normalize", side_effect=RuntimeError("boom")):
            resp = client.post("/api/ingest", json={"mal_id": 1})
        assert resp.status_code == 500
        assert resp.is_json
        assert "boom" in resp.get_json()["error"]

    def test_malformed_json_is_json_4xx(self, client):
        resp = client.post("/api/ingest", data="{not json", content_type="application/json")
        assert 400 <= resp.status_code < 500
        assert resp.is_json
        assert resp.get_json()["error"]

    def test_non_object_body_is_json_400(self, client):
        resp = client.post("/api/ingest", json=[1, 2])
        assert resp.status_code == 400
        assert resp.is_json

    def test_missing_mal_id_is_json_422(self, client):
        resp = client.post("/api/ingest", json={})
        assert resp.status_code == 422
        assert resp.is_json
