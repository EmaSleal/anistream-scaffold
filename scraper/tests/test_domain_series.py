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
    animeflv_slug=None,
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
        "animeflv_slug": animeflv_slug,
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

    def test_part1_and_part2_collapse(self):
        ep1 = map_episode_row(make_episode(id="ep1", episode_number=1))
        ep2 = map_episode_row(make_episode(id="ep2", episode_number=2))

        part1 = self._make_item("Temporada 1", "s1", [ep1], base_title="My Series")
        part2 = self._make_item("Temporada 1", "s2", [ep2], base_title="My Series")

        result = part_merge([part1, part2])
        assert len(result) == 1
        assert len(result[0]["episodes"]) == 2

    def test_different_base_titles_not_merged(self):
        ep1 = map_episode_row(make_episode(id="ep1"))
        ep2 = map_episode_row(make_episode(id="ep2"))

        item1 = self._make_item("Temporada 1", "s1", [ep1], base_title="Series A")
        item2 = self._make_item("OVA", "s2", [ep2], base_title="Series B", media_type="ova")

        result = part_merge([item1, item2])
        assert len(result) == 2

    def test_merged_episodes_sorted_by_number(self):
        ep3 = map_episode_row(make_episode(id="ep3", episode_number=3))
        ep1 = map_episode_row(make_episode(id="ep1", episode_number=1))

        part1 = self._make_item("Temporada 1", "s1", [ep3], base_title="Series")
        part2 = self._make_item("Temporada 1", "s2", [ep1], base_title="Series")

        result = part_merge([part1, part2])
        assert result[0]["episodes"][0]["episode"] == 1
        assert result[0]["episodes"][1]["episode"] == 3


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
        # Parts 1 and 2 share base title "Series" → merged into one
        assert len(result["seasons"]) == 1
        assert len(result["seasons"][0]["episodes"]) == 2
