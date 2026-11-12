"""Unit tests for scraper/domain/series.py.

All tests use inline fixture dicts — no database access.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from domain.series import (
    MEDIA_TYPE_RANK,
    media_rank,
    season_label,
    map_series_row,
    map_episode_row,
    consolidate_franchises,
    part_merge,
    build_seasons,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_series(
    id="s1",
    title="Test Series",
    media_type="tv",
    franchise_id=None,
    season_order=1,
    score=7.5,
    thumbnail_url="http://example.com/thumb.jpg",
    is_featured=False,
    principal_slug=None,
):
    return {
        "id": id,
        "mal_id": 1,
        "title": title,
        "slug": id,
        "description": "A test series.",
        "thumbnail_url": thumbnail_url,
        "banner_url": "",
        "rating": "14+",
        "genres": ["Action"],
        "audio_formats": ["sub"],
        "season_count": 1,
        "episode_count": 12,
        "year": 2020,
        "media_type": media_type,
        "is_simulcast": False,
        "is_featured": is_featured,
        "score": score,
        "franchise_id": franchise_id,
        "season_order": season_order,
        "franchise_relation": None,
        "principal_slug": principal_slug,
        "fallback_slug": None,
        "animeflv_disabled": False,
    }


def make_episode(id="ep1", series_id="s1", episode_number=1, title=None, animeflv_slug=None):
    return {
        "id": id,
        "series_id": series_id,
        "episode_number": episode_number,
        "title": title,
        "animeflv_slug": animeflv_slug or f"series-{episode_number}",
        "thumbnail_url": None,
        "aired_at": None,
        "series": {"title": "Test Series"},
    }


# ---------------------------------------------------------------------------
# media_rank
# ---------------------------------------------------------------------------

class TestMediaRank:
    def test_tv_beats_ova(self):
        assert media_rank("tv") > media_rank("ova")

    def test_movie_beats_special(self):
        assert media_rank("movie") > media_rank("special")

    def test_tv_is_highest(self):
        assert media_rank("tv") == MEDIA_TYPE_RANK["tv"]
        for mt in ("movie", "ova", "special", "music"):
            assert media_rank("tv") >= media_rank(mt)

    def test_none_defaults(self):
        assert media_rank(None) == media_rank("tv")

    def test_unknown_returns_zero(self):
        assert media_rank("xyz") == 0


# ---------------------------------------------------------------------------
# season_label
# ---------------------------------------------------------------------------

class TestSeasonLabel:
    def test_movie(self):
        assert season_label("movie", 1) == "Película"

    def test_ova(self):
        assert season_label("ova", 1) == "OVA"

    def test_ona_maps_to_ova(self):
        assert season_label("ona", 1) == "OVA"

    def test_special(self):
        assert season_label("special", 1) == "Especial"

    def test_tv_first_season(self):
        assert season_label("tv", 1) == "Temporada 1"

    def test_tv_third_season(self):
        assert season_label("tv", 3) == "Temporada 3"

    def test_none_defaults_to_tv(self):
        assert season_label(None, 2) == "Temporada 2"

    def test_unrecognized_type_falls_back_to_especial(self):
        # e.g. a crossover/collab entry Jikan tags with a type outside our
        # known set ("CM", "PV", "TV Special", "Music", ...) must not be
        # mistaken for a real numbered season (regression: "He Wei Dao x
        # Slime" crossover special was showing as "Temporada 3").
        assert season_label("cm", 3) == "Especial"
        assert season_label("music", 3) == "Especial"
        assert season_label("tv special", 3) == "Especial"


# ---------------------------------------------------------------------------
# map_series_row
# ---------------------------------------------------------------------------

class TestMapSeriesRow:
    def test_snake_to_camel(self):
        row = make_series(id="abc", thumbnail_url="http://img.com/x.jpg")
        mapped = map_series_row(row)
        assert mapped["id"] == "abc"
        assert mapped["thumbnailUrl"] == "http://img.com/x.jpg"
        assert "thumbnail_url" not in mapped

    def test_missing_optional_fields(self):
        row = make_series()
        row.pop("franchise_id", None)
        mapped = map_series_row(row)
        assert mapped["franchiseId"] is None

    def test_animeflv_disabled_defaults_false(self):
        row = make_series()
        row["animeflv_disabled"] = None
        mapped = map_series_row(row)
        assert mapped["animeflvDisabled"] is False


# ---------------------------------------------------------------------------
# map_episode_row
# ---------------------------------------------------------------------------

class TestMapEpisodeRow:
    def test_basic_mapping(self):
        row = make_episode(id="ep1", series_id="s1", episode_number=3)
        mapped = map_episode_row(row)
        assert mapped["id"] == "ep1"
        assert mapped["seriesId"] == "s1"
        assert mapped["episode"] == 3
        assert mapped["season"] == 1

    def test_series_title_from_join(self):
        row = make_episode()
        row["series"] = {"title": "My Anime"}
        mapped = map_episode_row(row)
        assert mapped["seriesTitle"] == "My Anime"

    def test_title_fallback(self):
        row = make_episode(episode_number=5, title=None)
        mapped = map_episode_row(row)
        assert mapped["title"] == "Episode 5"


# ---------------------------------------------------------------------------
# consolidate_franchises
# ---------------------------------------------------------------------------

class TestConsolidateFranchises:
    def test_tv_beats_ova(self):
        """TV member should be selected over OVA as the representative."""
        tv = map_series_row(make_series(id="tv1", media_type="tv", franchise_id="fid", season_order=1))
        ova = map_series_row(make_series(id="ova1", media_type="ova", franchise_id="fid", season_order=2))
        result = consolidate_franchises([tv, ova])
        assert len(result) == 1
        assert result[0]["id"] == "tv1"

    def test_standalone_series_pass_through(self):
        series = map_series_row(make_series(id="solo", franchise_id=None))
        result = consolidate_franchises([series])
        assert len(result) == 1
        assert result[0]["id"] == "solo"

    def test_thumbnail_from_latest_tv(self):
        tv1 = map_series_row(make_series(id="tv1", media_type="tv", franchise_id="fid", season_order=1, thumbnail_url="http://old.jpg"))
        tv2 = map_series_row(make_series(id="tv2", media_type="tv", franchise_id="fid", season_order=2, thumbnail_url="http://new.jpg"))
        result = consolidate_franchises([tv1, tv2])
        # thumbnailUrl should come from the latest TV season (tv2)
        assert result[0]["thumbnailUrl"] == "http://new.jpg"

    def test_each_franchise_appears_once(self):
        tv1 = map_series_row(make_series(id="tv1", franchise_id="f1"))
        tv2 = map_series_row(make_series(id="tv2", franchise_id="f1"))
        result = consolidate_franchises([tv1, tv2])
        assert len(result) == 1


# ---------------------------------------------------------------------------
# part_merge
# ---------------------------------------------------------------------------

class TestPartMerge:
    def _make_item(self, label, series_id, episodes, media_type="tv", base_title=None):
        return {
            "label": label,
            "seriesId": series_id,
            "episodes": episodes,
            "mediaType": media_type,
            "baseTitle": base_title or label,
            "seasonOrder": 1,
        }

    def test_part1_and_part2_collapse_into_parts(self):
        ep1 = map_episode_row(make_episode(id="ep1", episode_number=1))
        ep2 = map_episode_row(make_episode(id="ep2", episode_number=2))

        part1 = self._make_item("Temporada 1", "s1", [ep1], base_title="My Series")
        part2 = self._make_item("Temporada 1", "s2", [ep2], base_title="My Series")

        result = part_merge([part1, part2])
        assert len(result) == 1
        assert [p["seriesId"] for p in result[0]["parts"]] == ["s1", "s2"]
        assert [p["label"] for p in result[0]["parts"]] == ["Parte 1", "Parte 2"]

    def test_different_base_titles_not_merged(self):
        ep1 = map_episode_row(make_episode(id="ep1"))
        ep2 = map_episode_row(make_episode(id="ep2"))

        item1 = self._make_item("Temporada 1", "s1", [ep1], base_title="Series A")
        item2 = self._make_item("OVA", "s2", [ep2], base_title="Series B", media_type="ova")

        result = part_merge([item1, item2])
        assert len(result) == 2

    def test_overlapping_episode_numbers_are_kept_per_part(self):
        p1_ep1 = map_episode_row(make_episode(id="p1-ep1", episode_number=1))
        p1_ep2 = map_episode_row(make_episode(id="p1-ep2", episode_number=2))
        p2_ep1 = map_episode_row(make_episode(id="p2-ep1", episode_number=1))
        p2_ep3 = map_episode_row(make_episode(id="p2-ep3", episode_number=3))

        part1 = self._make_item("Temporada 1", "s1", [p1_ep1, p1_ep2], base_title="Series")
        part2 = self._make_item("Temporada 1", "s2", [p2_ep1, p2_ep3], base_title="Series")

        result = part_merge([part1, part2])
        parts = result[0]["parts"]
        assert [e["id"] for e in parts[0]["episodes"]] == ["p1-ep1", "p1-ep2"]
        assert [e["id"] for e in parts[1]["episodes"]] == ["p2-ep1", "p2-ep3"]


# ---------------------------------------------------------------------------
# build_seasons
# ---------------------------------------------------------------------------

class TestBuildSeasons:
    def _make_mapped_series(self, id, title, media_type="tv", season_order=1, franchise_id="fid"):
        row = make_series(id=id, title=title, media_type=media_type, season_order=season_order, franchise_id=franchise_id)
        return map_series_row(row)

    def test_tv_seasons_renumbered_sequentially(self):
        s1 = self._make_mapped_series("s1", "My Series Season 1", season_order=1)
        s2 = self._make_mapped_series("s2", "My Series Season 2", season_order=2)
        eps = {
            "s1": [map_episode_row(make_episode(id="e1", series_id="s1", episode_number=1))],
            "s2": [map_episode_row(make_episode(id="e2", series_id="s2", episode_number=1))],
        }
        result = build_seasons([s1, s2], eps)
        labels = [s["label"] for s in result["seasons"]]
        assert labels == ["Temporada 1", "Temporada 2"]

    def test_ova_gets_ova_label(self):
        tv = self._make_mapped_series("s1", "My Series", media_type="tv", season_order=1)
        ova = self._make_mapped_series("s2", "My Series OVA", media_type="ova", season_order=2)
        eps = {
            "s1": [map_episode_row(make_episode(id="e1", series_id="s1", episode_number=1))],
            "s2": [map_episode_row(make_episode(id="e2", series_id="s2", episode_number=1))],
        }
        result = build_seasons([tv, ova], eps)
        labels = [s["label"] for s in result["seasons"]]
        assert "Temporada 1" in labels
        assert "OVA" in labels

    def test_empty_series_excluded(self):
        s1 = self._make_mapped_series("s1", "My Series", season_order=1)
        s2 = self._make_mapped_series("s2", "My Series 2", season_order=2)
        eps = {
            "s1": [map_episode_row(make_episode(id="e1", series_id="s1", episode_number=1))],
            "s2": [],  # no episodes → excluded
        }
        result = build_seasons([s1, s2], eps)
        assert len(result["seasons"]) == 1

    def test_initial_season_idx(self):
        s1 = self._make_mapped_series("s1", "My Series Season 1", season_order=1)
        s2 = self._make_mapped_series("s2", "My Series Season 2", season_order=2)
        eps = {
            "s1": [map_episode_row(make_episode(id="e1", series_id="s1", episode_number=1))],
            "s2": [map_episode_row(make_episode(id="e2", series_id="s2", episode_number=1))],
        }
        # Pass s2 first → initial idx should point to s2's position in merged list
        result = build_seasons([s2, s1], eps)
        assert result["initialSeasonIdx"] == 0  # s2 is passed first

    def test_part_merge_collapses_parts(self):
        s1 = self._make_mapped_series("s1", "Series Part 1", season_order=1)
        s2 = self._make_mapped_series("s2", "Series Part 2", season_order=2)
        eps = {
            "s1": [map_episode_row(make_episode(id="e1", series_id="s1", episode_number=1))],
            "s2": [map_episode_row(make_episode(id="e2", series_id="s2", episode_number=2))],
        }
        result = build_seasons([s1, s2], eps)
        # Parts 1 and 2 share base title "Series" -> one season with two parts
        assert len(result["seasons"]) == 1
        assert [len(p["episodes"]) for p in result["seasons"][0]["parts"]] == [1, 1]

    def _mushoku(self):
        s1 = self._make_mapped_series("s2a", "X Season 2", season_order=1)
        s2 = self._make_mapped_series("s2b", "X Season 2 Part 2", season_order=2)
        eps = {
            "s2a": [map_episode_row(make_episode(id=f"a{n}", series_id="s2a", episode_number=n)) for n in range(0, 12)],
            "s2b": [map_episode_row(make_episode(id=f"b{n}", series_id="s2b", episode_number=n)) for n in range(1, 13)],
        }
        return s1, s2, eps

    def test_parts_keep_all_their_own_episodes(self):
        s1, s2, eps = self._mushoku()
        seasons = build_seasons([s1, s2], eps)["seasons"]
        assert len(seasons) == 1
        parts = seasons[0]["parts"]
        assert [p["label"] for p in parts] == ["Parte 1", "Parte 2"]
        assert [p["seriesId"] for p in parts] == ["s2a", "s2b"]
        assert [len(p["episodes"]) for p in parts] == [12, 12]
        # top level mirrors the first part
        assert seasons[0]["seriesId"] == "s2a"
        assert seasons[0]["episodes"] == parts[0]["episodes"]

    def test_single_member_season_has_one_part(self):
        s1 = self._make_mapped_series("s1", "My Series", season_order=1)
        eps = {"s1": [map_episode_row(make_episode(id="e1", series_id="s1", episode_number=1))]}
        season = build_seasons([s1], eps)["seasons"][0]
        assert len(season["parts"]) == 1
        assert season["parts"][0]["seriesId"] == season["seriesId"] == "s1"
        assert season["parts"][0]["episodes"] == season["episodes"]
        assert season["label"] == "Temporada 1" and season["mediaType"] == "tv"

    def test_part_without_episodes_omitted_but_label_stable(self):
        s1, s2, eps = self._mushoku()
        eps["s2a"] = []
        season = build_seasons([s1, s2], eps)["seasons"][0]
        assert [p["seriesId"] for p in season["parts"]] == ["s2b"]
        assert season["parts"][0]["label"] == "Parte 2"
        assert season["seriesId"] == "s2b"

    def test_season_with_no_episodes_in_any_part_dropped(self):
        s1, s2, eps = self._mushoku()
        eps["s2a"] = []
        eps["s2b"] = []
        assert build_seasons([s1, s2], eps)["seasons"] == []

    def test_renumbering_counts_multi_part_season_once(self):
        a = self._make_mapped_series("a", "X", season_order=1)
        b = self._make_mapped_series("b", "X Season 2", season_order=2)
        c = self._make_mapped_series("c", "X Season 2 Part 2", season_order=3)
        eps = {k: [map_episode_row(make_episode(id=f"{k}1", series_id=k, episode_number=1))] for k in "abc"}
        assert [s["label"] for s in build_seasons([a, b, c], eps)["seasons"]] == ["Temporada 1", "Temporada 2"]

    def test_initial_part_idx_for_requested_part(self):
        s1, s2, eps = self._mushoku()
        r = build_seasons([s1, s2], eps, requested_series_id="s2b")
        assert (r["initialSeasonIdx"], r["initialPartIdx"]) == (0, 1)
        r = build_seasons([s1, s2], eps, requested_series_id="s2a")
        assert (r["initialSeasonIdx"], r["initialPartIdx"]) == (0, 0)
        assert build_seasons([s1, s2], eps)["initialPartIdx"] == 0
        assert build_seasons([], {})["initialPartIdx"] == 0
