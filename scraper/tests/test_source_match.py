"""T-009 / ADR-016: normalization, exact matching, validation, page parsing."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("INTERNAL_JWT_SECRET", "test-internal-secret-for-tests-only")
os.environ.setdefault("SERVICE_SECRET", "test-service-secret-for-tests-only")

from unittest.mock import MagicMock, patch

import pytest

import scraper_animeav1 as av1
import scraper_jkanime as jk
from domain.source_match import (
    is_exact_match, media_type_family, normalize_title, validate_candidate,
)


class TestNormalize:
    def test_case_punctuation_unicode_and_spaces(self):
        assert normalize_title("  One-Punch  Man: 2nd Season! ") == "one punch man 2nd season"
        assert normalize_title("ＦＵＬＬ　ｗｉｄｔｈ") == "full width"  # NFKC
        assert normalize_title(None) == ""

    def test_season_wording_is_not_unified(self):
        assert normalize_title("Show 2nd Season") != normalize_title("Show Season 2")

    def test_exact_match_uses_any_alt_title(self):
        assert is_exact_match("Shingeki no Kyojin", ["Attack on Titan", "shingeki no kyojin!"])
        assert not is_exact_match("Shingeki no Kyojin", ["Shingeki no Kyojin: Chimi Kyara Gekijou"])
        assert not is_exact_match("", [""])


class TestValidate:
    J = {"media_type": "tv", "year": 2015, "episode_count": 12}

    def test_pass_with_tolerance(self):
        r = validate_candidate({"media_type": "TV Anime", "year": 2015, "episode_count": 14}, self.J)
        assert r["passed"] and r["checks"]["episodes"]["outcome"] == "pass"

    def test_episode_overflow_fails(self):
        r = validate_candidate({"media_type": "TV Anime", "year": 2015, "episode_count": 15}, self.J)
        assert not r["passed"] and r["checks"]["episodes"]["outcome"] == "fail"

    def test_type_family_and_year_mismatch_fail(self):
        assert not validate_candidate({"media_type": "Película"}, self.J)["passed"]
        assert not validate_candidate({"year": 2016}, self.J)["passed"]

    def test_unknown_sides_are_skipped(self):
        r = validate_candidate({}, {"media_type": "tv", "year": None, "episode_count": 0})
        assert r["passed"]
        assert {c["outcome"] for c in r["checks"].values()} == {"unknown"}

    @pytest.mark.parametrize("label,family", [
        ("TV Anime", "tv"), ("Serie", "tv"), ("TV", "tv"), ("Película", "movie"),
        ("Movie", "movie"), ("OVA", "short"), ("Especial", "short"), ("special", "short"),
        ("ONA", "short"), ("TV Special", "short"), ("???", None), (None, None),
    ])
    def test_families(self, label, family):
        assert media_type_family(label) == family


_RESULTS = lambda *titles: [{"title": t, "slug": t.lower().replace(" ", "-")} for t in titles]


class TestSelectors:
    @pytest.mark.parametrize("mod,fn", [
        (av1, "select_best_animeav1_match"), (jk, "select_best_jkanime_match"),
    ])
    def test_containment_is_never_exact(self, mod, fn):
        select = getattr(mod, fn)
        res = _RESULTS("Owarimonogatari")
        assert select(res, "Owarimonogatari Second Season Recaps") is None
        assert select(_RESULTS("One Punch Man 2nd Season"),
                      "One Punch Man 2nd Season Commemorative Special") is None
        assert select(_RESULTS("Shingeki no Kyojin"),
                      "Shingeki no Kyojin: Chimi Kyara Gekijou") is None

    @pytest.mark.parametrize("mod,fn", [
        (av1, "select_best_animeav1_match"), (jk, "select_best_jkanime_match"),
    ])
    def test_exact_via_alt_title_and_punctuation(self, mod, fn):
        res = _RESULTS("Owarimonogatari 2nd Season!") + _RESULTS("Other")
        got = getattr(mod, fn)(res, "Monogatari Series: Second Season", ["Owarimonogatari 2nd season"])
        assert got["title"] == "Owarimonogatari 2nd Season!"

    @pytest.mark.parametrize("mod,fn", [
        (av1, "select_animeav1_candidates"), (jk, "select_jkanime_candidates"),
    ])
    def test_containment_becomes_scored_candidate(self, mod, fn):
        exact, cand = getattr(mod, fn)(_RESULTS("Owarimonogatari"), "Owarimonogatari Second Season Recaps")
        assert exact == [] and cand["slug"] == "owarimonogatari" and cand["score"] >= 12

    @pytest.mark.parametrize("mod,fn", [
        (av1, "select_animeav1_candidates"), (jk, "select_jkanime_candidates"),
    ])
    def test_unrelated_results_yield_nothing(self, mod, fn):
        assert getattr(mod, fn)(_RESULTS("Naruto"), "Bleach") == ([], None)


# Header markup copied from the live site (verified 2026-11-02).
_AV1_PAGE = """
<html><body><div><h1 class="text-lead">One Punch Man 2nd Season</h1>
<h2 class="text-main">ワンパンマン 2期</h2></div>
<div class="flex flex-wrap items-center gap-2 text-sm"><span>{type}</span> <span>•</span>
<span>2019</span> <span>•</span> <span>Temporada Primavera</span> <span>•</span> <span>Finalizado</span></div>
<a href="/media/opm/1"><img src="x.jpg"/></a><a href="/media/opm/2"></a><a href="/media/opm/2"></a>
</body></html>
"""


def _resp(html):
    return MagicMock(text=html, raise_for_status=MagicMock())


class TestAnimeav1PageParsing:
    def test_parses_title_type_year_and_unique_episodes(self):
        with patch.object(av1._scraper, "get", return_value=_resp(_AV1_PAGE.format(type="TV Anime"))):
            page = av1.fetch_animeav1_page("opm")
        assert (page["title"], page["media_type"], page["year"], page["episode_count"]) == (
            "One Punch Man 2nd Season", "TV Anime", 2019, 2)
        assert [e["episode_number"] for e in page["episodes"]] == [1, 2]

    def test_movie_label_and_scrape_wrapper_unchanged(self):
        with patch.object(av1._scraper, "get", return_value=_resp(_AV1_PAGE.format(type="Película"))):
            assert av1.fetch_animeav1_page("opm")["media_type"] == "Película"
            assert [e["episode_number"] for e in av1.scrape_animeav1_episodes("opm")] == [1, 2]

    def test_missing_header_is_unknown(self):
        with patch.object(av1._scraper, "get", return_value=_resp("<html><a href='/media/s/1'></a></html>")):
            page = av1.fetch_animeav1_page("s")
        assert page["title"] is None and page["media_type"] is None and page["year"] is None

    def test_http_error_returns_none(self):
        with patch.object(av1._scraper, "get", side_effect=RuntimeError("boom")):
            assert av1.fetch_animeav1_page("s") is None


_JK_PAGE = """
<html><head><meta property="og:title" content="One Punch Man 2nd Season - anime One Punch Man 2nd Season online JkAnime"/></head>
<body><ul><li rel="tipo"><span>Tipo:</span> Serie</li>
<li><span>Episodios:</span> 12</li>
<li><span> Emitido: </span> Lunes, 08 de Abril de 2019</li>
<li><span>Estado:</span> <div>Concluido</div></li></ul></body></html>
"""


class TestJkanimeInfo:
    def test_parses_type_year_title_and_count(self):
        with patch.object(jk._scraper, "get", return_value=_resp(_JK_PAGE)):
            info = jk.fetch_jkanime_series_info("opm")
        assert info == {"episode_count": 12, "status": "Concluido", "media_type": "Serie",
                        "year": 2019, "title": "One Punch Man 2nd Season"}
