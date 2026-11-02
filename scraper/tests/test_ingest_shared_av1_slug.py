"""Tests for the shared-AnimeAV1-slug fix (Jikan Part 1/Part 2 cour splits).

Covers the Slime Season 4 Part 1/Part 2 bug: AnimeAV1 doesn't split a MAL
cour split into separate pages, so both parts' title search resolves to the
same slug (confirmed against the live site). Without offsetting, both series
rows end up scraping the full duplicate episode range from that shared page.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("INTERNAL_JWT_SECRET", "test-internal-secret-for-tests-only")
os.environ.setdefault("SERVICE_SECRET", "test-service-secret-for-tests-only")

from unittest.mock import patch

from routes.ingest_routes import (
    _build_episodes_from_animeav1,
    _build_episodes_from_jkanime,
    _claimed_episode_offset,
)


class TestBuildEpisodesFromAnimeav1Offset:
    def test_no_offset_behaves_as_before(self):
        eps = [{"episode_number": 1, "thumbnail_url": None}, {"episode_number": 2, "thumbnail_url": None}]
        with patch("routes.ingest_routes.scrape_animeav1_episodes", return_value=eps):
            result = _build_episodes_from_animeav1(
                "s1", "slug", {}, {1: {"title": "Ep 1"}, 2: {"title": "Ep 2"}},
            )
        assert [e["episode_number"] for e in result] == [1, 2]
        assert result[0]["title"] == "Ep 1"

    def test_offset_skips_claimed_episodes_and_rebases_metadata(self):
        # Shared AnimeAV1 page has 4 episodes total; Part 1 already claimed 1-2.
        eps = [{"episode_number": n, "thumbnail_url": None} for n in range(1, 5)]
        jikan_titles = {1: {"title": "Part2 Ep1"}, 2: {"title": "Part2 Ep2"}}
        with patch("routes.ingest_routes.scrape_animeav1_episodes", return_value=eps):
            result = _build_episodes_from_animeav1(
                "part2-id", "shared-slug", {}, jikan_titles, episode_offset=2,
                max_episodes=2,
            )
        # Keeps native AnimeAV1 numbers 3, 4 — needed for correct stream resolution.
        assert [e["episode_number"] for e in result] == [3, 4]
        # But metadata lookup rebases via (num - offset) = Part 2's own numbering.
        assert result[0]["title"] == "Part2 Ep1"
        assert result[1]["title"] == "Part2 Ep2"

    def test_max_episodes_caps_output(self):
        eps = [{"episode_number": n, "thumbnail_url": None} for n in range(1, 10)]
        with patch("routes.ingest_routes.scrape_animeav1_episodes", return_value=eps):
            result = _build_episodes_from_animeav1("s1", "slug", {}, {}, max_episodes=3)
        assert [e["episode_number"] for e in result] == [1, 2, 3]

    def test_offset_beyond_available_episodes_returns_empty(self):
        eps = [{"episode_number": 1, "thumbnail_url": None}]
        with patch("routes.ingest_routes.scrape_animeav1_episodes", return_value=eps):
            result = _build_episodes_from_animeav1("s1", "slug", {}, {}, episode_offset=5)
        assert result == []


class TestClaimedEpisodeOffset:
    def test_no_franchise_id_returns_zero(self):
        assert _claimed_episode_offset(None, "slug", "s1") == 0

    def test_sums_official_counts_of_earlier_siblings_sharing_the_slug(self):
        siblings = [
            {"id": "s1", "principal_slug": "shared-slug", "season_order": 1, "episode_count": 24},
            {"id": "s2", "principal_slug": "other-slug", "season_order": 2, "episode_count": 12},
        ]
        with patch("routes.ingest_routes.get_series_by_franchise", return_value=siblings):
            offset = _claimed_episode_offset("f1", "shared-slug", "s2", 2)
        assert offset == 24  # only s1 matches the slug; s2 excluded (it's the current member)

    def test_excludes_self(self):
        siblings = [{"id": "s1", "principal_slug": "shared-slug", "season_order": 1, "episode_count": 99}]
        with patch("routes.ingest_routes.get_series_by_franchise", return_value=siblings):
            offset = _claimed_episode_offset("f1", "shared-slug", "s1", 1)
        assert offset == 0

    def test_season_order_defaults_to_persisted_row(self):
        siblings = [
            {"id": "s1", "principal_slug": "shared-slug", "season_order": 1, "episode_count": 12},
            {"id": "s2", "fallback_slug": "shared-slug", "season_order": 2, "episode_count": 12},
        ]
        with patch("routes.ingest_routes.get_series_by_franchise", return_value=siblings):
            assert _claimed_episode_offset("f1", "shared-slug", "s2") == 12

    def test_undeterminable_returns_none(self):
        siblings = [
            {"id": "s1", "principal_slug": "shared-slug", "season_order": 1, "episode_count": None},
        ]
        with patch("routes.ingest_routes.get_series_by_franchise", return_value=siblings):
            assert _claimed_episode_offset("f1", "shared-slug", "s2", 2) is None


class TestContinuationRule:
    """ADR-012: a continuation with unknown own episode_count claims nothing."""

    def test_av1_continuation_without_cap_claims_nothing(self):
        eps = [{"episode_number": n, "thumbnail_url": None} for n in range(1, 25)]
        for cap in (None, 0):
            with patch("routes.ingest_routes.scrape_animeav1_episodes", return_value=eps):
                result = _build_episodes_from_animeav1(
                    "p2", "slug", {}, {}, episode_offset=24, max_episodes=cap,
                )
            assert result == []

    def test_av1_first_cour_stays_uncapped_while_count_unknown(self):
        eps = [{"episode_number": n, "thumbnail_url": None} for n in range(1, 5)]
        with patch("routes.ingest_routes.scrape_animeav1_episodes", return_value=eps):
            result = _build_episodes_from_animeav1("s1", "slug", {}, {}, max_episodes=None)
        assert [e["episode_number"] for e in result] == [1, 2, 3, 4]

    def test_jkanime_continuation_without_cap_claims_nothing(self):
        assert _build_episodes_from_jkanime("p2", 24, {}, {}, max_episodes=None, episode_offset=12) == []
        assert _build_episodes_from_jkanime("p2", 24, {}, {}, max_episodes=0, episode_offset=12) == []

    def test_jkanime_continuation_with_cap(self):
        result = _build_episodes_from_jkanime("p2", 24, {}, {}, max_episodes=12, episode_offset=12)
        assert [e["episode_number"] for e in result] == list(range(13, 25))


class TestSlimeRegression:
    """Production franchise 37430: Part 2 (mal-63129, episode_count 0,
    fallback_slug = S4's slug) was ingested while S4 had 22 of 24 episodes
    ingested. The old ingested-row offset (22) plus an uncapped (falsy 0)
    cap let Part 2 claim episodes 23-24."""

    SLUG = "tensei-shitara-slime-datta-ken-4th-season"

    def _siblings(self):
        return [
            {"id": self.SLUG, "principal_slug": self.SLUG, "fallback_slug": None,
             "season_order": 5, "episode_count": 24},
            {"id": "mal-63129", "principal_slug": None, "fallback_slug": self.SLUG,
             "season_order": 6, "episode_count": 0},
        ]

    def test_part2_claims_nothing_while_s4_is_incomplete(self):
        eps = [{"episode_number": n, "thumbnail_url": None} for n in range(1, 25)]
        with patch("routes.ingest_routes.get_series_by_franchise", return_value=self._siblings()), \
             patch("routes.ingest_routes.scrape_animeav1_episodes", return_value=eps):
            offset = _claimed_episode_offset("37430", self.SLUG, "mal-63129", 6)
            result = _build_episodes_from_animeav1(
                "mal-63129", self.SLUG, {}, {}, episode_offset=offset, max_episodes=0,
            )
        assert offset == 24
        assert [e["episode_number"] for e in result] == []

    def test_s4_keeps_offset_zero_despite_later_part2(self):
        with patch("routes.ingest_routes.get_series_by_franchise", return_value=self._siblings()):
            assert _claimed_episode_offset("37430", self.SLUG, self.SLUG, 5) == 0
