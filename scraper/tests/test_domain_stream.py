"""Unit and integration tests for domain.stream orchestration."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Set secrets before any auth.py import (which fails-fast at startup).
os.environ.setdefault("INTERNAL_JWT_SECRET", "test-internal-secret-for-tests-only")
os.environ.setdefault("SERVICE_SECRET", "test-service-secret-for-tests-only")

import json
import pytest
from unittest.mock import patch

from domain.stream import (
    orchestrate_stream,
    resolve_animeflv_stream,
    resolve_animeav1_stream,
    NoSourceError,
    UpstreamError,
)


# ---------------------------------------------------------------------------
# Fixtures — minimal episode and stream_config dicts
# ---------------------------------------------------------------------------

def _episode(animeflv_slug="naruto-1", episode_number=1, series_id="s1"):
    return {
        "id": "ep1",
        "series_id": series_id,
        "episode_number": episode_number,
        "animeflv_slug": animeflv_slug,
    }


def _stream_config(animeflv_disabled=False, animeav1_slug=None):
    return {
        "animeflv_disabled": animeflv_disabled,
        "animeav1_slug": animeav1_slug,
    }


# ---------------------------------------------------------------------------
# orchestrate_stream — unit tests (all scrapers mocked)
# ---------------------------------------------------------------------------

class TestOrchestrateStream:

    # 5.1 — Primary success: animeflv enabled, scraper returns URL
    def test_primary_success_returns_animeflv_source(self):
        ep = _episode()
        cfg = _stream_config(animeflv_disabled=False, animeav1_slug="naruto-av1")

        with patch(
            "domain.stream.resolve_animeflv_stream",
            return_value={"url": "https://streamtape.com/v/abc", "error_type": None},
        ):
            result = orchestrate_stream(ep, cfg)

        assert result["url"] == "https://streamtape.com/v/abc"
        assert result["source"] == "animeflv"

    # 5.2 — Primary fails, animeav1_slug present → fallback resolves
    def test_primary_fails_fallback_resolves(self):
        ep = _episode()
        cfg = _stream_config(animeflv_disabled=False, animeav1_slug="naruto-av1")

        with patch(
            "domain.stream.resolve_animeflv_stream",
            return_value={"url": None, "error_type": "no_source"},
        ), patch(
            "domain.stream.resolve_animeav1_stream",
            return_value={"url": "https://player.zilla-networks.com/m3u8/abc123", "error_type": None},
        ):
            result = orchestrate_stream(ep, cfg)

        assert result["url"] == "https://player.zilla-networks.com/m3u8/abc123"
        assert result["source"] == "animeav1"

    # 5.3 — animeflv_disabled=True → skips primary entirely, resolves via animeav1
    def test_animeflv_disabled_skips_primary(self):
        ep = _episode()
        cfg = _stream_config(animeflv_disabled=True, animeav1_slug="naruto-av1")

        with patch(
            "domain.stream.resolve_animeflv_stream"
        ) as mock_primary, patch(
            "domain.stream.resolve_animeav1_stream",
            return_value={"url": "https://player.zilla-networks.com/m3u8/xyz", "error_type": None},
        ):
            result = orchestrate_stream(ep, cfg)

        mock_primary.assert_not_called()
        assert result["source"] == "animeav1"
        assert result["url"] == "https://player.zilla-networks.com/m3u8/xyz"

    # 5.4 — animeflv_disabled=True, animeav1_slug=None → NoSourceError
    def test_animeflv_disabled_no_animeav1_raises_no_source(self):
        ep = _episode()
        cfg = _stream_config(animeflv_disabled=True, animeav1_slug=None)

        with pytest.raises(NoSourceError):
            orchestrate_stream(ep, cfg)

    # 5.5 — Both sources fail to return a URL → NoSourceError
    def test_both_sources_fail_raises_no_source(self):
        ep = _episode()
        cfg = _stream_config(animeflv_disabled=False, animeav1_slug="naruto-av1")

        with patch(
            "domain.stream.resolve_animeflv_stream",
            return_value={"url": None, "error_type": "no_source"},
        ), patch(
            "domain.stream.resolve_animeav1_stream",
            return_value={"url": None, "error_type": "no_source"},
        ):
            with pytest.raises(NoSourceError):
                orchestrate_stream(ep, cfg)

    # 5.6 — Scraper raises a network/parse exception → UpstreamError
    def test_primary_network_error_raises_upstream_error(self):
        ep = _episode()
        cfg = _stream_config(animeflv_disabled=False, animeav1_slug=None)

        with patch(
            "domain.stream.resolve_animeflv_stream",
            return_value={"url": None, "error_type": "network_error"},
        ):
            with pytest.raises(UpstreamError):
                orchestrate_stream(ep, cfg)

    def test_fallback_network_error_raises_upstream_error(self):
        ep = _episode()
        cfg = _stream_config(animeflv_disabled=False, animeav1_slug="naruto-av1")

        with patch(
            "domain.stream.resolve_animeflv_stream",
            return_value={"url": None, "error_type": "no_source"},
        ), patch(
            "domain.stream.resolve_animeav1_stream",
            return_value={"url": None, "error_type": "network_error"},
        ):
            with pytest.raises(UpstreamError):
                orchestrate_stream(ep, cfg)


# ---------------------------------------------------------------------------
# Integration tests — Flask test client
# 5.7 — GET /api/episodes/watch/<id>/stream-url status codes
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    with patch("storage.get_client"):
        from app import create_app
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c


def _episode_row(
    id="ep1",
    series_id="s1",
    episode_number=1,
    animeflv_slug="naruto-1",
):
    return {
        "id": id,
        "series_id": series_id,
        "episode_number": episode_number,
        "title": f"Episode {episode_number}",
        "animeflv_slug": animeflv_slug,
        "thumbnail_url": None,
        "aired_at": None,
        "series": {"title": "Naruto"},
    }


class TestWatchEpisodeStreamUrl:

    def test_200_when_stream_resolves(self, client):
        row = _episode_row()
        stream_cfg = {"animeflv_disabled": False, "animeav1_slug": None}

        with patch("db.episodes.get_episode_for_watch", return_value=row), \
             patch("db.series.get_stream_config", return_value=stream_cfg), \
             patch("domain.stream.resolve_animeflv_stream",
                   return_value={"url": "https://streamtape.com/v/abc", "error_type": None}):
            res = client.get("/api/episodes/watch/naruto-1/stream-url")

        assert res.status_code == 200
        data = json.loads(res.data)
        assert data["url"] == "https://streamtape.com/v/abc"
        assert data["source"] == "animeflv"

    def test_404_when_episode_not_found(self, client):
        with patch("db.episodes.get_episode_for_watch", return_value=None):
            res = client.get("/api/episodes/watch/nonexistent/stream-url")

        assert res.status_code == 404

    def test_404_when_no_source(self, client):
        row = _episode_row()
        stream_cfg = {"animeflv_disabled": True, "animeav1_slug": None}

        with patch("db.episodes.get_episode_for_watch", return_value=row), \
             patch("db.series.get_stream_config", return_value=stream_cfg):
            res = client.get("/api/episodes/watch/naruto-1/stream-url")

        assert res.status_code == 404

    def test_503_when_upstream_error(self, client):
        row = _episode_row()
        stream_cfg = {"animeflv_disabled": False, "animeav1_slug": None}

        with patch("db.episodes.get_episode_for_watch", return_value=row), \
             patch("db.series.get_stream_config", return_value=stream_cfg), \
             patch("domain.stream.resolve_animeflv_stream",
                   return_value={"url": None, "error_type": "network_error"}):
            res = client.get("/api/episodes/watch/naruto-1/stream-url")

        assert res.status_code == 503

    def test_legacy_stream_route_removed(self, client):
        """GET /api/stream must return 404 after route removal."""
        res = client.get("/api/stream?episode_slug=naruto-1")
        assert res.status_code == 404

    def test_legacy_stream_fallback_route_removed(self, client):
        """GET /api/stream/fallback must return 404 after route removal."""
        res = client.get("/api/stream/fallback?series_id=s1&episode_number=1")
        assert res.status_code == 404
