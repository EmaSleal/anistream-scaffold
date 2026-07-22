"""Tests for DUB detection at AnimeAV1 ingest time.

Covers:
  S-13: DUB detected on episode 1 → series.audio_formats = ["sub","dub"]
  S-14: DUB absent on episode 1 → series.audio_formats = ["sub"]
  S-15: No episodes found → animeav1_has_dub NOT called
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("INTERNAL_JWT_SECRET", "test-internal-secret-for-tests-only")
os.environ.setdefault("SERVICE_SECRET", "test-service-secret-for-tests-only")

import json
import pytest
from unittest.mock import patch, MagicMock, call


_MAL_ID = 21
_RAW_JIKAN = {
    "mal_id": _MAL_ID,
    "title": "Naruto",
    "type": "TV",
    "genres": [],
    "demographics": [],
    "status": "Finished Airing",
    "episodes": 220,
    "score": 8.0,
    "year": 2002,
    "images": {"jpg": {"large_image_url": "http://img"}},
    "synopsis": "",
}

_NORMALIZED = {
    "id": "naruto",
    "slug": "naruto",
    "mal_id": _MAL_ID,
    "title": "Naruto",
    "audio_formats": ["sub"],
    "media_type": "tv",
}

_AV1_EPISODES = [{"episode_number": 1, "thumbnail_url": None}]


@pytest.fixture
def client():
    with patch("storage.get_client"):
        from app import create_app
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c


def _base_patches(dub_detected: bool, has_episodes: bool = True):
    """Return a context manager that patches the common ingest dependencies."""
    episodes = _AV1_EPISODES if has_episodes else []

    # The ingest route imports these via 'from X import Y' so patch in route module.
    return [
        patch("routes.ingest_routes.fetch_anime_by_id", return_value=_RAW_JIKAN),
        patch("routes.ingest_routes.normalize", return_value=dict(_NORMALIZED)),
        patch("routes.ingest_routes.get_series_by_mal_id", return_value=None),
        patch("routes.ingest_routes.get_episode_count", return_value=0),
        patch("routes.ingest_routes.search_animeav1", return_value=[{"slug": "naruto", "title": "Naruto"}]),
        patch("routes.ingest_routes.scrape_animeav1_episodes", return_value=episodes),
        patch("routes.ingest_routes.fetch_kitsu_episodes", return_value={}),
        patch("routes.ingest_routes.fetch_kitsu_series_status", return_value=None),
        patch("routes.ingest_routes.search_kitsu_anime", return_value=None),
        patch("routes.ingest_routes.fetch_jikan_episodes", return_value={}),
        patch("routes.ingest_routes.fetch_jikan_relations", return_value=[]),
        patch("routes.ingest_routes.animeav1_has_dub", return_value=dub_detected),
        patch("routes.ingest_routes.upsert_series"),
        patch("routes.ingest_routes.upsert_episodes", return_value=1),
    ]


class TestIngestDubDetect:

    def test_s13_dub_detected_sets_audio_formats_sub_dub(self, client):
        """S-13: When DUB detected on episode 1, series.audio_formats = ['sub','dub']."""
        upserted_series = {}

        def capture_upsert(series):
            upserted_series.update(series)

        patches = _base_patches(dub_detected=True)
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5], patches[6], patches[7], patches[8], patches[9], \
             patches[10], patches[11], \
             patch("routes.ingest_routes.upsert_series", side_effect=capture_upsert), \
             patch("routes.ingest_routes.upsert_episodes", return_value=1):
            res = client.post(
                "/api/ingest",
                json={"mal_id": _MAL_ID, "animeav1_slug": "naruto"},
            )

        assert res.status_code == 200
        # The series passed to upsert_series must have audio_formats including "dub"
        assert "dub" in upserted_series.get("audio_formats", [])

    def test_s14_no_dub_detected_audio_formats_remains_sub(self, client):
        """S-14: When DUB absent, series.audio_formats = ['sub'] (normalizer default)."""
        upserted_series = {}

        def capture_upsert(series):
            upserted_series.update(series)

        patches = _base_patches(dub_detected=False)
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5], patches[6], patches[7], patches[8], patches[9], \
             patches[10], patches[11], \
             patch("storage.upsert_series", side_effect=capture_upsert), \
             patch("storage.upsert_episodes", return_value=1):
            res = client.post(
                "/api/ingest",
                json={"mal_id": _MAL_ID, "animeav1_slug": "naruto"},
            )

        assert res.status_code == 200
        audio_formats = upserted_series.get("audio_formats", [])
        assert "dub" not in audio_formats

    def test_s15_no_episodes_skips_dub_detection(self, client):
        """S-15: When AnimeAV1 returns no episodes, animeav1_has_dub is NOT called."""
        patches = _base_patches(dub_detected=False, has_episodes=False)
        # patches[11] is animeav1_has_dub
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5], patches[6], patches[7], patches[8], patches[9], \
             patches[10], patches[11] as mock_has_dub, \
             patches[12], patches[13]:
            res = client.post(
                "/api/ingest",
                json={"mal_id": _MAL_ID, "animeav1_slug": "naruto"},
            )

        assert res.status_code == 200
        mock_has_dub.assert_not_called()
