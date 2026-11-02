"""T-009 / ADR-016: strict, validated source-slug matching + pending suggestions."""
import os
import sys
from contextlib import ExitStack

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("INTERNAL_JWT_SECRET", "test-internal-secret-for-tests-only")
os.environ.setdefault("SERVICE_SECRET", "test-service-secret-for-tests-only")

import pytest
from tests.admin_origin import admin_headers, admin_post
from unittest.mock import MagicMock, patch

from db import slug_suggestions as sdb
from routes import ingest_routes as ir

MODULE = "routes.ingest_routes"


@pytest.fixture
def client():
    # Imported lazily under a patched storage.get_client, like the other route
    # tests: some route modules bind get_client at import time.
    with patch("storage.get_client"):
        from app import create_app
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c


def _series(title, **over):
    return {"mal_id": 500, "title": title, "titles": [], "media_type": "tv", "year": 2018,
            "episode_count": 12, **over}


def _av1_page(title, media_type="TV Anime", year=2018, count=12):
    return {"title": title, "media_type": media_type, "year": year, "episode_count": count,
            "episodes": [{"episode_number": n, "thumbnail_url": None} for n in range(1, count + 1)]}


def _run(client, path, body, series, av1_results=(), av1_page=None, jk_results=(), jk_info=None,
         insert_side_effect=None, post=None):
    """POST ``path`` with all I/O patched; returns (resp, upserted_series, suggestions, ctx)."""
    upserted, suggestions = [], []
    ctx = {}

    def _insert(row):
        if insert_side_effect:
            raise insert_side_effect
        suggestions.append(row)

    patches = [
        patch(f"{MODULE}.fetch_anime_by_id", return_value={"mal_id": 500, "title": series["title"]}),
        patch(f"{MODULE}.normalize", side_effect=lambda raw, **kw: dict(series)),
        patch(f"{MODULE}.get_series_by_mal_id", return_value=None),
        patch(f"{MODULE}.get_series_identity_by_id", return_value=None),
        patch(f"{MODULE}.get_series_identities_by_mal_ids", return_value=[]),
        patch(f"{MODULE}.get_series_by_franchise", return_value=[]),
        patch(f"{MODULE}.get_episode_count", return_value=0),
        patch(f"{MODULE}._discover_franchise_jikan", return_value=[]),
        patch(f"{MODULE}.search_kitsu_anime", return_value=None),
        patch(f"{MODULE}.fetch_kitsu_episodes", return_value={}),
        patch(f"{MODULE}.fetch_kitsu_series_status", return_value=None),
        patch(f"{MODULE}.fetch_jikan_episodes", return_value={}),
        patch(f"{MODULE}.animeav1_has_dub", return_value=False),
        patch(f"{MODULE}.upsert_series", side_effect=lambda s: upserted.append(dict(s))),
        patch(f"{MODULE}.upsert_episodes", side_effect=lambda e: len(e)),
        patch("scraper_animeav1.search_animeav1", return_value=list(av1_results)),
        patch("scraper_jkanime.search_jkanime", return_value=list(jk_results)),
        patch(f"{MODULE}.fetch_animeav1_page", return_value=av1_page),
        patch(f"{MODULE}.fetch_jkanime_series_info", return_value=jk_info),
        patch(f"{MODULE}.slug_suggestions_db.insert_pending", side_effect=_insert),
    ]
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        resp = post(client, path, body) if post else client.post(path, json=body)
    return resp, upserted, suggestions


def _member(client, series, **kw):
    return _run(client, "/api/ingest/member",
                {"mal_id": 500, "franchise_id": "f1", "season_order": 2, "relation": "Sequel"},
                series, **kw)


def _res(title, slug):
    return {"title": title, "slug": slug, "animeav1_url": "", "thumbnail_url": None}


class TestContainmentNeverAutoAssigns:
    @pytest.mark.parametrize("our_title,page_title,slug", [
        ("Owarimonogatari Second Season Recaps", "Owarimonogatari", "owarimonogatari"),
        ("One Punch Man 2nd Season Commemorative Special", "One Punch Man 2nd Season",
         "one-punch-man-2nd-season"),
        ("Shingeki no Kyojin: Chimi Kyara Gekijou", "Shingeki no Kyojin", "shingeki-no-kyojin"),
    ])
    def test_production_cases_become_suggestions(self, client, our_title, page_title, slug):
        page = _av1_page(page_title, count=13)
        resp, upserted, suggestions = _member(
            client, _series(our_title, media_type="special", episode_count=1),
            av1_results=[_res(page_title, slug)], av1_page=page,
        )
        assert resp.get_json()["status"] == "ok"
        assert resp.get_json()["principal_slug"] is None
        assert "principal_slug" not in upserted[-1]
        assert upserted[-1]["id"] == "mal-500"  # the parent's slug was not claimed as id
        assert len(suggestions) == 1
        s = suggestions[0]
        assert (s["series_id"], s["source"], s["slug"]) == ("mal-500", "animeav1", slug)
        assert s["page_title"] == page_title and s["score"] >= 12
        assert s["page_episodes"] == 13 and s["jikan_episodes"] == 1
        assert s["checks"]["type"]["outcome"] == "fail"


class TestExactMatchValidation:
    def test_exact_title_but_too_many_page_episodes_is_suggestion(self, client):
        page = _av1_page("Show", count=15)  # 15 > 12 + 2
        resp, upserted, suggestions = _member(
            client, _series("Show"), av1_results=[_res("Show", "show")], av1_page=page)
        assert resp.get_json()["principal_slug"] is None
        assert [s["slug"] for s in suggestions] == ["show"]
        assert suggestions[0]["checks"]["episodes"]["outcome"] == "fail"

    def test_exact_title_with_13_vs_12_is_auto_assigned(self, client):
        page = _av1_page("Show", count=13)
        resp, upserted, suggestions = _member(
            client, _series("Show"), av1_results=[_res("Show", "show")], av1_page=page)
        body = resp.get_json()
        assert body["principal_slug"] == "show" and body["episodes_ingested"] == 12
        assert upserted[-1]["principal_slug"] == "show"
        assert suggestions == []

    def test_failed_validation_continues_with_jkanime_waterfall(self, client):
        page = _av1_page("Show", media_type="Película", count=1)
        resp, upserted, suggestions = _member(
            client, _series("Show"),
            av1_results=[_res("Show", "show")], av1_page=page,
            jk_results=[{"title": "Show", "slug": "show-jk"}],
            jk_info={"episode_count": 12, "status": "x", "media_type": "Serie", "year": 2018},
        )
        assert upserted[-1].get("principal_slug") is None
        assert upserted[-1]["fallback_slug"] == "show-jk"
        assert [(s["source"], s["slug"]) for s in suggestions] == [("animeav1", "show")]

    def test_jkanime_containment_and_failed_validation_become_suggestions(self, client):
        resp, upserted, suggestions = _member(
            client, _series("Show Special", media_type="special", episode_count=1),
            jk_results=[{"title": "Show", "slug": "show"}],
            jk_info={"episode_count": 12, "status": "x", "media_type": "Serie", "year": 2018},
        )
        assert "fallback_slug" not in upserted[-1]
        assert [(s["source"], s["slug"]) for s in suggestions] == [("jkanime", "show")]
        assert suggestions[0]["page_type"] == "Serie" and suggestions[0]["jikan_type"] == "special"

    def test_jkanime_exact_valid_is_auto_assigned(self, client):
        resp, upserted, suggestions = _member(
            client, _series("Show"),
            jk_results=[{"title": "Show", "slug": "show"}],
            jk_info={"episode_count": 13, "status": "x", "media_type": "Serie", "year": 2018},
        )
        assert upserted[-1]["fallback_slug"] == "show" and suggestions == []

    def test_suggestion_failure_never_fails_ingest(self, client):
        resp, upserted, _ = _member(
            client, _series("Show Recap"), av1_results=[_res("Show", "show")],
            av1_page=_av1_page("Show"), insert_side_effect=RuntimeError("no such table"),
        )
        assert resp.get_json()["status"] == "ok"


class TestMultipleExactAndFetchFailure:
    def test_second_exact_page_that_validates_is_auto_assigned(self, client):
        pages = {"show-movie": _av1_page("Show", media_type="Película", count=1),
                 "show": _av1_page("Show", count=12)}
        exacts = [_res("Show", "show-movie"), _res("Show", "show")]
        d = ir._decide_source_match("animeav1", exacts, None, lambda s: pages[s], _series("Show"))
        assert d["slug"] == "show" and d["suggestion"] is None

    def test_no_exact_validates_suggests_the_first(self):
        pages = {"a": _av1_page("Show", media_type="Película", count=1),
                 "b": _av1_page("Show", year=1999)}
        d = ir._decide_source_match(
            "animeav1", [_res("Show", "a"), _res("Show", "b")], None, lambda s: pages[s], _series("Show"))
        assert d["slug"] is None and d["suggestion"]["slug"] == "a" and d["suggestion"]["score"] == 30

    @pytest.mark.parametrize("source", ["animeav1", "jkanime"])
    def test_exact_with_failed_fetch_is_a_suggestion_not_an_assignment(self, client, source):
        kw = ({"av1_results": [_res("Show", "show")]} if source == "animeav1"
              else {"jk_results": [{"title": "Show", "slug": "show"}]})
        resp, upserted, suggestions = _member(client, _series("Show"), **kw)  # fetches return None
        assert "principal_slug" not in upserted[-1] and "fallback_slug" not in upserted[-1]
        assert [(s["source"], s["slug"]) for s in suggestions] == [(source, "show")]
        assert suggestions[0]["checks"]["page"] == {"outcome": "fail", "reason": "fetch_failed"}

    @pytest.mark.parametrize("source", ["animeav1", "jkanime"])
    def test_non_exact_with_failed_fetch_is_a_suggestion_with_check(self, client, source):
        kw = ({"av1_results": [_res("Show", "show")]} if source == "animeav1"
              else {"jk_results": [{"title": "Show", "slug": "show"}]})
        resp, upserted, suggestions = _member(client, _series("Show Recap"), **kw)
        assert suggestions[0]["source"] == source
        assert suggestions[0]["checks"]["page"]["reason"] == "fetch_failed"


class TestExplicitAdminSlugBypass:
    """slug_source=admin + a verified admin token bypasses matching (ADR-016)."""

    def _admin_run(self, client, body, series, **kw):
        post = lambda c, path, b: admin_post(c, path, b)
        return _run(client, "/api/ingest", body, series, post=post, **kw)

    def test_explicit_animeav1_slug_skips_matching_and_validation(self, client):
        page = _av1_page("Totally Different", media_type="Película", year=1999, count=99)
        with patch(f"{MODULE}.scrape_animeav1_episodes",
                   return_value=page["episodes"][:12]) as scrape, \
             patch(f"{MODULE}.find_animeav1_candidates", side_effect=AssertionError("no matching")), \
             patch(f"{MODULE}.validate_candidate", side_effect=AssertionError("no validation")):
            resp, upserted, suggestions = self._admin_run(
                client, {"mal_id": 500, "animeav1_slug": "admin-slug"}, _series("Show"))
        assert resp.status_code == 200
        assert upserted[-1]["principal_slug"] == "admin-slug"
        assert suggestions == [] and scrape.called

    def test_explicit_fallback_slug_skips_jkanime_matching(self, client):
        with patch(f"{MODULE}.find_jkanime_candidates", side_effect=AssertionError("no matching")):
            resp, upserted, suggestions = self._admin_run(
                client, {"mal_id": 500, "fallback_slug": "admin-jk"}, _series("Show"))
        assert resp.status_code == 200
        assert upserted[-1]["fallback_slug"] == "admin-jk" and suggestions == []

    def test_main_ingest_jkanime_automatch_is_strict(self, client):
        resp, upserted, suggestions = _run(
            client, "/api/ingest", {"mal_id": 500}, _series("Show Recap"),
            jk_results=[{"title": "Show", "slug": "show"}],
            jk_info={"episode_count": 12, "status": "x", "media_type": "Serie", "year": 2018},
        )
        assert "fallback_slug" not in upserted[-1]
        assert suggestions and suggestions[0]["series_id"] == "mal-500"


class TestSkippedMediaType:
    @pytest.mark.parametrize("mt", ["cm", "pv", "music"])
    def test_member_of_skipped_type_writes_nothing(self, client, mt):
        with patch(f"{MODULE}.find_animeav1_candidates", side_effect=AssertionError("untouched")):
            resp, upserted, suggestions = _member(client, _series("Promo", media_type=mt))
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "skipped_media_type"
        assert resp.get_json()["episodes_ingested"] == 0
        assert upserted == [] and suggestions == []


class TestFranchiseBfs:
    def test_summary_not_followed_and_cm_pv_music_entries_dropped(self):
        def relations(mal_id):
            if mal_id != 1:
                return []
            return [
                {"relation": "Summary", "entry": [{"type": "anime", "mal_id": 2, "name": "Recap"}]},
                {"relation": "Sequel", "entry": [
                    {"type": "anime", "mal_id": 3, "name": "S2"},
                    {"type": "anime", "mal_id": 4, "name": "Promo", "media_type": "CM"},
                    {"type": "anime", "mal_id": 5, "name": "Clip", "media_type": "pv"},
                    {"type": "anime", "mal_id": 6, "name": "Song", "media_type": "Music"},
                ]},
            ]

        assert "Summary" not in ir._FRANCHISE_RELATIONS
        with patch(f"{MODULE}.fetch_jikan_relations", side_effect=relations), \
             patch(f"{MODULE}.time.sleep"):
            entries = ir._discover_franchise_jikan(1)
        assert sorted(e["mal_id"] for e in entries) == [1, 3]


class TestSuggestionStorage:
    def test_insert_pending_never_overwrites_existing_rows(self):
        client = MagicMock()
        with patch("storage.get_client", return_value=client):
            sdb.insert_pending({"series_id": "a", "source": "animeav1", "slug": "x"})
        _, kwargs = client.table.return_value.upsert.call_args
        # pending / accepted / denied rows alike are left untouched, so a
        # denied (series, source, slug) is never re-created.
        assert kwargs == {"on_conflict": "series_id,source,slug", "ignore_duplicates": True}


    def test_mark_decided_is_guarded_by_pending_status(self):
        client = MagicMock()
        chain = client.table.return_value.update.return_value.eq.return_value.eq.return_value
        chain.execute.return_value = MagicMock(data=[])
        with patch("storage.get_client", return_value=client):
            assert sdb.mark_decided("id-1", "denied") is False
        client.table.return_value.update.return_value.eq.assert_called_with("id", "id-1")
        client.table.return_value.update.return_value.eq.return_value.eq.assert_called_with("status", "pending")


class TestUnverifiedExplicitSlug:
    """IngestTrigger-style requests: the body slug is a candidate, not a decision."""

    BODY = {"mal_id": 500, "animeav1_slug": "own-slug"}

    def test_non_matching_title_is_suggestion_and_ingest_continues(self, client):
        page = _av1_page("Some Other Show", count=12)
        resp, upserted, suggestions = _run(
            client, "/api/ingest", self.BODY, _series("Show"), av1_page=page,
            jk_results=[{"title": "Show", "slug": "show-jk"}],
            jk_info={"episode_count": 12, "status": "x", "media_type": "Serie", "year": 2018})
        body = resp.get_json()
        assert resp.status_code == 200 and body["principal_slug"] is None
        assert "principal_slug" not in upserted[-1]
        assert upserted[-1]["fallback_slug"] == "show-jk"  # waterfall still runs
        assert [(s["source"], s["slug"]) for s in suggestions] == [("animeav1", "own-slug")]
        assert set(body) >= {"series_id", "episodes_ingested", "franchise_members"}

    def test_exact_valid_page_is_assigned_as_today(self, client):
        page = _av1_page("Show", count=13)
        resp, upserted, suggestions = _run(
            client, "/api/ingest", self.BODY, _series("Show"), av1_page=page)
        assert resp.get_json()["principal_slug"] == "own-slug"
        assert resp.get_json()["episodes_ingested"] == 12
        assert upserted[-1]["principal_slug"] == "own-slug" and suggestions == []

    def test_exact_but_invalid_page_is_suggestion(self, client):
        page = _av1_page("Show", media_type="Película", count=1)
        resp, upserted, suggestions = _run(
            client, "/api/ingest", self.BODY, _series("Show"), av1_page=page)
        assert "principal_slug" not in upserted[-1]
        assert suggestions[0]["score"] == 30

    def test_failed_fetch_is_suggestion(self, client):
        resp, upserted, suggestions = _run(
            client, "/api/ingest", self.BODY, _series("Show"), av1_page=None)
        assert "principal_slug" not in upserted[-1]
        assert suggestions[0]["checks"]["page"]["reason"] == "fetch_failed"

    def test_unverified_fallback_slug_is_validated_too(self, client):
        bad = {"episode_count": 12, "status": "x", "media_type": "Serie", "year": 2018,
               "title": "Show Recap"}
        resp, upserted, suggestions = _run(
            client, "/api/ingest", {"mal_id": 500, "fallback_slug": "jk"}, _series("Show"),
            jk_info=bad)
        assert "fallback_slug" not in upserted[-1]
        assert [(s["source"], s["slug"]) for s in suggestions] == [("jkanime", "jk")]
        good = {**bad, "title": "Show"}
        resp, upserted, suggestions = _run(
            client, "/api/ingest", {"mal_id": 500, "fallback_slug": "jk"}, _series("Show"),
            jk_info=good)
        assert upserted[-1]["fallback_slug"] == "jk" and suggestions == []

    @pytest.mark.parametrize("headers", [
        {},                                   # no token at all
        admin_headers("USER"),                # valid token, wrong role
        admin_headers(expires_in=-10),        # expired admin token
        {"Authorization": "Bearer garbage"},  # invalid token
    ])
    def test_admin_marker_without_valid_admin_token_is_ignored(self, client, headers):
        page = _av1_page("Some Other Show", count=12)
        post = lambda c, path, b: c.post(path, json={**b, "slug_source": "admin"}, headers=headers)
        resp, upserted, suggestions = _run(
            client, "/api/ingest", self.BODY, _series("Show"), av1_page=page, post=post)
        assert "principal_slug" not in upserted[-1]
        assert [s["slug"] for s in suggestions] == ["own-slug"]

    def test_valid_admin_token_without_marker_is_not_a_bypass(self, client):
        page = _av1_page("Some Other Show", count=12)
        post = lambda c, path, b: c.post(path, json=b, headers=admin_headers())
        resp, upserted, suggestions = _run(
            client, "/api/ingest", self.BODY, _series("Show"), av1_page=page, post=post)
        assert "principal_slug" not in upserted[-1] and suggestions
