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

from routes.ingest_routes import _build_episodes_from_animeav1, _claimed_episode_offset


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

    def test_sums_episodes_from_siblings_sharing_the_slug(self):
        siblings = [
            {"id": "s1", "principal_slug": "shared-slug"},
            {"id": "s2", "principal_slug": "other-slug"},
        ]
        with patch("routes.ingest_routes.get_series_by_franchise", return_value=siblings), \
             patch("routes.ingest_routes.get_episode_count", return_value=24):
            offset = _claimed_episode_offset("f1", "shared-slug", "s2")
        assert offset == 24  # only s1 matches the slug; s2 excluded (it's the current member)

    def test_excludes_self(self):
        siblings = [{"id": "s1", "principal_slug": "shared-slug"}]
        with patch("routes.ingest_routes.get_series_by_franchise", return_value=siblings), \
             patch("routes.ingest_routes.get_episode_count", return_value=99) as mock_count:
            offset = _claimed_episode_offset("f1", "shared-slug", "s1")
        assert offset == 0
        mock_count.assert_not_called()
