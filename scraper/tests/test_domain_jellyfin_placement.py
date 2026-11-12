"""Tests for domain/jellyfin_placement.py (ADR-020): pure placement over loaded rows."""
import os
import sys
from datetime import date, timedelta
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("INTERNAL_JWT_SECRET", "test-internal-secret-for-tests-only")
os.environ.setdefault("SERVICE_SECRET", "test-service-secret")

from domain import jellyfin_placement as jp

BB = "Rascal Does Not Dream of Bunny Girl Senpai"


def _m(sid, title, media="tv", order=1, year=2018, count=0):
    return {"id": sid, "title": title, "mediaType": media, "seasonOrder": order, "year": year,
            "episodeCount": count}


def _eps(*nums):
    return [{"episode": n} for n in nums]


@pytest.fixture
def rascal():
    members = [
        _m("bb", BB, "tv", 1, 2018),
        _m("dg", "Seishun Buta Yarou wa Yumemiru Shoujo no Yume wo Minai", "movie", 2, 2019),
        _m("sv", "Rascal Does Not Dream of a Sister Venturing Out", "movie", 3, 2023),
        _m("kk", "Rascal Does Not Dream of a Knapsack Kid", "movie", 4, 2023),
        _m("sc", "Rascal Does Not Dream of a Santa Claus", "tv", 5, 2025),
    ]
    eps = {"bb": _eps(*range(1, 14)), "dg": _eps(1), "sv": _eps(1), "kk": _eps(1), "sc": _eps(1, 2)}
    return members, eps


class TestComputePlacement:
    def test_first_tv_is_season_one(self, rascal):
        members, eps = rascal
        assert jp.compute_placement("bb", members, eps) == {
            "show_title": BB, "show_year": 2018, "season_number": 1, "episode_offset": 0}

    def test_second_tv_is_season_two_with_offset_zero(self, rascal):
        members, eps = rascal
        p = jp.compute_placement("sc", members, eps)
        assert (p["season_number"], p["episode_offset"]) == (2, 0)
        assert p["show_title"] == BB and p["show_year"] == 2018

    def test_movies_are_season_zero_with_consecutive_offsets(self, rascal):
        members, eps = rascal
        got = [jp.compute_placement(s, members, eps) for s in ("dg", "sv", "kk")]
        assert [(p["season_number"], p["episode_offset"]) for p in got] == [(0, 0), (0, 1), (0, 2)]

    def test_offset_uses_highest_episode_number_of_preceding_slot(self):
        members = [_m("tv", "Show"), _m("o1", "Show OVA", "ova", 2), _m("o2", "Show Special", "special", 3)]
        eps = {"tv": _eps(1), "o1": _eps(1, 2, 3), "o2": _eps(1)}
        assert jp.compute_placement("o2", members, eps)["episode_offset"] == 3

    def test_part_siblings_share_season(self):
        members = [_m("a", "Show"), _m("p1", "Show 2 Part 1", order=2), _m("p2", "Show 2 Part 2", order=3)]
        eps = {"a": _eps(1), "p1": _eps(1, 2), "p2": _eps(3, 4)}
        s1 = jp.compute_placement("p1", members, eps)["season_number"]
        s2 = jp.compute_placement("p2", members, eps)["season_number"]
        assert s1 == s2 == 2

    def test_part_two_without_released_episodes_still_maps_to_merged_season(self):
        members = [_m("a", "Show"), _m("p1", "Show 2 Part 1", order=2), _m("p2", "Show 2 Part 2", order=3)]
        eps = {"a": _eps(1), "p1": _eps(1, 2), "p2": []}
        assert jp.compute_placement("p2", members, eps)["season_number"] == 2

    def test_restarting_part_two_is_offset_by_official_count_of_part_one(self):
        members = [_m("p1", "Show 2", order=1, count=12), _m("p2", "Show 2 Part 2", order=2, count=12)]
        eps = {"p1": _eps(*range(0, 12)), "p2": _eps(*range(1, 13))}
        p1 = jp.compute_placement("p1", members, eps)
        p2 = jp.compute_placement("p2", members, eps)
        assert (p1["season_number"], p1["episode_offset"]) == (1, 0)
        assert (p2["season_number"], p2["episode_offset"]) == (1, 12)  # ep 1 -> file episode 13

    def test_continuation_part_two_has_no_offset(self):
        members = [_m("p1", "Show 2", order=1, count=13), _m("p2", "Show 2 Part 2", order=2, count=12)]
        eps = {"p1": _eps(*range(1, 14)), "p2": _eps(*range(14, 26))}
        assert jp.compute_placement("p2", members, eps)["episode_offset"] == 0

    def test_part_without_released_episodes_has_no_offset(self):
        members = [_m("p1", "Show 2", order=1, count=12), _m("p2", "Show 2 Part 2", order=2)]
        eps = {"p1": _eps(1, 2), "p2": []}
        assert jp.compute_placement("p2", members, eps)["episode_offset"] == 0

    def test_non_tv_offset_counts_episodes_across_all_parts_of_earlier_slots(self):
        members = [_m("tv", "Show"), _m("o1", "Show OVA", "ova", 2), _m("o2", "Show OVA Part 2", "ova", 3),
                   _m("sp", "Show Special", "special", 4)]
        eps = {"tv": _eps(1), "o1": _eps(1, 2), "o2": _eps(1, 2, 3), "sp": _eps(1)}
        assert jp.compute_placement("sp", members, eps)["episode_offset"] == 5

    def test_series_with_no_released_episodes_gets_next_tv_index(self):
        members = [_m("a", "Show"), _m("b", "Show 2", order=2)]
        assert jp.compute_placement("b", members, {"a": _eps(1), "b": []})["season_number"] == 2

    def test_no_franchise_single_member_is_season_one(self):
        members = [_m("solo", "Solo Show", "tv", None, 2020)]
        assert jp.compute_placement("solo", members, {"solo": _eps(1)}) == {
            "show_title": "Solo Show", "show_year": 2020, "season_number": 1, "episode_offset": 0}

    def test_part_suffix_stripped_from_first_member_title(self):
        members = [_m("p2", "Grand Show Part 2", order=1, year=2021), _m("b", "Grand Show 2", order=2)]
        p = jp.compute_placement("b", members, {"p2": _eps(1), "b": _eps(1)})
        assert p["show_title"] == "Grand Show" and p["show_year"] == 2021

    def test_show_named_after_first_tv_member_when_a_movie_comes_first(self):
        # ADR-021: a prequel movie with season_order 1 must not name the show.
        members = [
            _m("jjk0", "Jujutsu Kaisen 0", "movie", 1, 2021),
            _m("jjk", "Jujutsu Kaisen", "tv", 2, 2020),
            _m("jjk2", "Jujutsu Kaisen Season 2", "tv", 3, 2023),
        ]
        eps = {"jjk0": _eps(1), "jjk": _eps(*range(1, 25)), "jjk2": _eps(1)}
        for sid, season, offset in (("jjk", 1, 0), ("jjk2", 2, 0), ("jjk0", 0, 0)):
            p = jp.compute_placement(sid, members, eps)
            assert p == {"show_title": "Jujutsu Kaisen", "show_year": 2020,
                         "season_number": season, "episode_offset": offset}

    def test_show_falls_back_to_first_member_without_tv(self):
        members = [_m("m1", "Movie One", "movie", 1, 2010), _m("m2", "Movie Two", "movie", 2, 2012)]
        p = jp.compute_placement("m2", members, {"m1": _eps(1), "m2": _eps(1)})
        assert (p["show_title"], p["show_year"], p["season_number"], p["episode_offset"]) == (
            "Movie One", 2010, 0, 1)

    def test_zero_year_becomes_none(self):
        members = [_m("a", "Show", year=0)]
        assert jp.compute_placement("a", members, {"a": _eps(1)})["show_year"] is None

    def test_unknown_series_raises(self, rascal):
        members, eps = rascal
        with pytest.raises(LookupError):
            jp.compute_placement("nope", members, eps)


def _row(sid, title, media="tv", order=1, year=2018, franchise="f"):
    return {"id": sid, "title": title, "media_type": media, "season_order": order,
            "year": year, "franchise_id": franchise}


def _ep_row(n, aired="2000-01-01"):
    return {"episode_number": n, "aired_at": aired, "thumbnail_url": ""}


class TestPlacementLoader:
    def test_loads_franchise_and_filters_unreleased(self):
        rows = {"a": _row("a", "Show"), "b": _row("b", "Show 2", order=2)}
        future = (date.today() + timedelta(days=30)).isoformat()
        eps = {"a": [_ep_row(1)], "b": [_ep_row(1, future)]}
        with patch.object(jp.db_series, "get_series_by_id", side_effect=lambda s: rows[s]), \
             patch.object(jp.db_series, "get_series_by_franchise", return_value=list(rows.values())), \
             patch.object(jp.db_episodes, "get_episodes_by_series", side_effect=lambda s: eps[s]):
            assert jp.placement("a")["season_number"] == 1
            assert jp.placement("b")["season_number"] == 2  # unreleased slot still gets next TV index

    def test_no_franchise_uses_own_row(self):
        row = _row("solo", "Solo", franchise=None, year=2020)
        with patch.object(jp.db_series, "get_series_by_id", return_value=row), \
             patch.object(jp.db_series, "get_series_by_franchise") as by_f:
            assert jp.placement("solo") == {
                "show_title": "Solo", "show_year": 2020, "season_number": 1, "episode_offset": 0}
        by_f.assert_not_called()

    def test_missing_series_raises(self):
        with patch.object(jp.db_series, "get_series_by_id", return_value=None):
            with pytest.raises(LookupError):
                jp.placement("x")


class TestJobNaming:
    def test_success_adds_season_fields(self):
        p = {"show_title": "S", "show_year": 2018, "season_number": 0, "episode_offset": 2}
        with patch.object(jp, "placement", return_value=p):
            assert jp.job_naming("x", 1) == {
                "series_title": "S", "series_year": 2018, "season_number": 0, "file_episode_number": 3}

    def test_fallback_on_error_uses_own_title_without_season(self):
        with patch.object(jp, "placement", side_effect=RuntimeError("db")), \
             patch.object(jp.db_series, "get_series_title_year_by_id",
                          return_value={"title": "Own", "year": 2020}):
            assert jp.job_naming("x", 1) == {"series_title": "Own", "series_year": 2020}

    def test_fallback_when_title_lookup_also_fails(self):
        with patch.object(jp, "placement", side_effect=RuntimeError("db")), \
             patch.object(jp.db_series, "get_series_title_year_by_id", side_effect=RuntimeError("db")):
            assert jp.job_naming("x", 1) == {"series_title": None, "series_year": None}
