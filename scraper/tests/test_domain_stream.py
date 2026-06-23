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
    resolve_jkanime_stream,
    NoSourceError,
    UpstreamError,
)

# Proxy URL prefix used by resolve_animeav1_stream when wrapping the Zilla URL.
_PROXY_PREFIX = "/api/stream/animeav1-proxy?path="


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


def _stream_config(animeflv_disabled=False, fallback_slug=None, principal_slug=None):
    return {
        "animeflv_disabled": animeflv_disabled,
        "fallback_slug": fallback_slug,
        "principal_slug": principal_slug,
    }


# ---------------------------------------------------------------------------
# orchestrate_stream — unit tests (all scrapers mocked)
# ---------------------------------------------------------------------------

class TestOrchestrateStream:

    # 5.1 — Primary success: animeflv enabled, scraper returns URL
    def test_primary_success_returns_animeflv_source(self):
        ep = _episode()
        cfg = _stream_config(animeflv_disabled=False, fallback_slug="naruto-jk")

        with patch(
            "domain.stream.resolve_animeflv_stream",
            return_value={"url": "https://streamtape.com/v/abc", "error_type": None},
        ):
            result = orchestrate_stream(ep, cfg)

        assert result["url"] == "https://streamtape.com/v/abc"
        assert result["source"] == "animeflv"

    # 5.2 — Primary fails, fallback_slug present → fallback resolves
    def test_primary_fails_fallback_resolves(self):
        ep = _episode()
        cfg = _stream_config(animeflv_disabled=False, fallback_slug="naruto-jk")

        with patch(
            "domain.stream.resolve_animeflv_stream",
            return_value={"url": None, "error_type": "no_source"},
        ), patch(
            "domain.stream.resolve_jkanime_stream",
            return_value={"url": "https://jkanime.net/m3u8/abc123.m3u8", "error_type": None},
        ):
            result = orchestrate_stream(ep, cfg)

        assert result["url"] == "https://jkanime.net/m3u8/abc123.m3u8"
        assert result["source"] == "jkanime"

    # 5.3 — animeflv_disabled=True → skips primary entirely, resolves via jkanime
    def test_animeflv_disabled_skips_primary(self):
        ep = _episode()
        cfg = _stream_config(animeflv_disabled=True, fallback_slug="naruto-jk")

        with patch(
            "domain.stream.resolve_animeflv_stream"
        ) as mock_primary, patch(
            "domain.stream.resolve_jkanime_stream",
            return_value={"url": "https://jkanime.net/m3u8/xyz.m3u8", "error_type": None},
        ):
            result = orchestrate_stream(ep, cfg)

        mock_primary.assert_not_called()
        assert result["source"] == "jkanime"
        assert result["url"] == "https://jkanime.net/m3u8/xyz.m3u8"

    # 5.4 — animeflv_disabled=True, fallback_slug=None → NoSourceError
    def test_animeflv_disabled_no_fallback_raises_no_source(self):
        ep = _episode()
        cfg = _stream_config(animeflv_disabled=True, fallback_slug=None)

        with pytest.raises(NoSourceError):
            orchestrate_stream(ep, cfg)

    # 5.5 — Both sources fail to return a URL → NoSourceError
    def test_both_sources_fail_raises_no_source(self):
        ep = _episode()
        cfg = _stream_config(animeflv_disabled=False, fallback_slug="naruto-jk")

        with patch(
            "domain.stream.resolve_animeflv_stream",
            return_value={"url": None, "error_type": "no_source"},
        ), patch(
            "domain.stream.resolve_jkanime_stream",
            return_value={"url": None, "error_type": "no_source"},
        ):
            with pytest.raises(NoSourceError):
                orchestrate_stream(ep, cfg)

    # 5.6 — Scraper raises a network/parse exception → UpstreamError
    def test_primary_network_error_raises_upstream_error(self):
        ep = _episode()
        cfg = _stream_config(animeflv_disabled=False, fallback_slug=None)

        with patch(
            "domain.stream.resolve_animeflv_stream",
            return_value={"url": None, "error_type": "network_error"},
        ):
            with pytest.raises(UpstreamError):
                orchestrate_stream(ep, cfg)

    def test_fallback_network_error_raises_upstream_error(self):
        ep = _episode()
        cfg = _stream_config(animeflv_disabled=False, fallback_slug="naruto-jk")

        with patch(
            "domain.stream.resolve_animeflv_stream",
            return_value={"url": None, "error_type": "no_source"},
        ), patch(
            "domain.stream.resolve_jkanime_stream",
            return_value={"url": None, "error_type": "network_error"},
        ):
            with pytest.raises(UpstreamError):
                orchestrate_stream(ep, cfg)


# ---------------------------------------------------------------------------
# AnimeAV1 + hint matrix tests (TDD — verifies the new branch order)
# Patch target: domain.stream.resolve_animeav1_stream
# ---------------------------------------------------------------------------

class TestOrchestrateStreamAnimeAV1:

    # AV1 succeeds when principal_slug is set and hint is None
    def test_animeav1_succeeds_returns_animeav1_source(self):
        ep = _episode()
        cfg = _stream_config(
            animeflv_disabled=True,
            fallback_slug="naruto-jk",
            principal_slug="naruto",
        )
        proxy_url = f"{_PROXY_PREFIX}https%3A//player.zilla-networks.com/m3u8/abc123"

        with patch(
            "domain.stream.resolve_animeav1_stream",
            return_value={"url": proxy_url, "error_type": None},
        ) as mock_av1, patch(
            "domain.stream.resolve_jkanime_stream"
        ) as mock_jk:
            result = orchestrate_stream(ep, cfg, hint=None)

        mock_av1.assert_called_once_with("naruto", 1)
        mock_jk.assert_not_called()
        assert result["url"] == proxy_url
        assert result["source"] == "animeav1"

    # hint=h264 skips AV1 even when principal_slug is set
    def test_animeav1_hint_h264_skips_to_jkanime(self):
        ep = _episode()
        cfg = _stream_config(
            animeflv_disabled=True,
            fallback_slug="naruto-jk",
            principal_slug="naruto",
        )

        with patch(
            "domain.stream.resolve_animeav1_stream"
        ) as mock_av1, patch(
            "domain.stream.resolve_jkanime_stream",
            return_value={"url": "https://jkanime.net/m3u8/xyz.m3u8", "error_type": None},
        ):
            result = orchestrate_stream(ep, cfg, hint="h264")

        mock_av1.assert_not_called()
        assert result["source"] == "jkanime"
        assert result["url"] == "https://jkanime.net/m3u8/xyz.m3u8"

    # principal_slug=None: AV1 not attempted, goes directly to JKAnime
    def test_no_principal_slug_skips_to_jkanime(self):
        ep = _episode()
        cfg = _stream_config(
            animeflv_disabled=True,
            fallback_slug="naruto-jk",
            principal_slug=None,
        )

        with patch(
            "domain.stream.resolve_animeav1_stream"
        ) as mock_av1, patch(
            "domain.stream.resolve_jkanime_stream",
            return_value={"url": "https://jkanime.net/m3u8/xyz.m3u8", "error_type": None},
        ):
            result = orchestrate_stream(ep, cfg)

        mock_av1.assert_not_called()
        assert result["source"] == "jkanime"

    # AV1 returns no_source → falls through to JKAnime
    def test_animeav1_fails_falls_through_to_jkanime(self):
        ep = _episode()
        cfg = _stream_config(
            animeflv_disabled=True,
            fallback_slug="naruto-jk",
            principal_slug="naruto",
        )

        with patch(
            "domain.stream.resolve_animeav1_stream",
            return_value={"url": None, "error_type": "no_source"},
        ), patch(
            "domain.stream.resolve_jkanime_stream",
            return_value={"url": "https://jkanime.net/m3u8/xyz.m3u8", "error_type": None},
        ):
            result = orchestrate_stream(ep, cfg)

        assert result["source"] == "jkanime"
        assert result["url"] == "https://jkanime.net/m3u8/xyz.m3u8"

    # AV1 returns network_error → falls through to JKAnime
    def test_animeav1_network_error_falls_through_to_jkanime(self):
        ep = _episode()
        cfg = _stream_config(
            animeflv_disabled=True,
            fallback_slug="naruto-jk",
            principal_slug="naruto",
        )

        with patch(
            "domain.stream.resolve_animeav1_stream",
            return_value={"url": None, "error_type": "network_error"},
        ), patch(
            "domain.stream.resolve_jkanime_stream",
            return_value={"url": "https://jkanime.net/m3u8/xyz.m3u8", "error_type": None},
        ):
            result = orchestrate_stream(ep, cfg)

        assert result["source"] == "jkanime"

    # AV1 no_source + JKAnime no_source → NoSourceError
    def test_all_sources_fail_raises_no_source(self):
        ep = _episode()
        cfg = _stream_config(
            animeflv_disabled=True,
            fallback_slug="naruto-jk",
            principal_slug="naruto",
        )

        with patch(
            "domain.stream.resolve_animeav1_stream",
            return_value={"url": None, "error_type": "no_source"},
        ), patch(
            "domain.stream.resolve_jkanime_stream",
            return_value={"url": None, "error_type": "no_source"},
        ):
            with pytest.raises(NoSourceError):
                orchestrate_stream(ep, cfg)

    # AV1 network_error + JKAnime network_error → UpstreamError
    def test_all_sources_network_error_raises_upstream(self):
        ep = _episode()
        cfg = _stream_config(
            animeflv_disabled=True,
            fallback_slug="naruto-jk",
            principal_slug="naruto",
        )

        with patch(
            "domain.stream.resolve_animeav1_stream",
            return_value={"url": None, "error_type": "network_error"},
        ), patch(
            "domain.stream.resolve_jkanime_stream",
            return_value={"url": None, "error_type": "network_error"},
        ):
            with pytest.raises(UpstreamError):
                orchestrate_stream(ep, cfg)


# ---------------------------------------------------------------------------
# NAS branch 0 tests
# ---------------------------------------------------------------------------

class TestOrchestrateStreamNAS:

    def _patch_nas(self, nas_url="", nas_key=""):
        return patch.multiple(
            "domain.stream",
            NAS_BASE_URL=nas_url,
            NAS_API_KEY=nas_key,
        )

    def test_nas_hit_returns_nas_source_skips_all_scrapers(self):
        ep = _episode(series_id="s1")
        cfg = _stream_config(animeflv_disabled=True, fallback_slug="naruto-jk", principal_slug="naruto")
        nas_url = "https://nas.astro-solutions.net/api/files/42/download"

        with self._patch_nas("https://nas.astro-solutions.net", "secret"), \
             patch("domain.stream.resolve_nas_stream", return_value={"url": nas_url, "error_type": None}) as mock_nas, \
             patch("domain.stream.resolve_animeav1_stream") as mock_av1, \
             patch("domain.stream.resolve_jkanime_stream") as mock_jk:
            result = orchestrate_stream(ep, cfg)

        mock_nas.assert_called_once_with("s1", 1)
        mock_av1.assert_not_called()
        mock_jk.assert_not_called()
        assert result["source"] == "nas"
        assert result["url"] == nas_url

    def test_nas_miss_falls_through_to_animeav1(self):
        ep = _episode(series_id="s1")
        cfg = _stream_config(animeflv_disabled=True, fallback_slug=None, principal_slug="naruto")
        av1_url = "https://player.zilla-networks.com/m3u8/abc"

        with self._patch_nas("https://nas.astro-solutions.net", "secret"), \
             patch("domain.stream.resolve_nas_stream", return_value={"url": None, "error_type": "no_source"}), \
             patch("domain.stream.resolve_animeav1_stream", return_value={"url": av1_url, "error_type": None}):
            result = orchestrate_stream(ep, cfg)

        assert result["source"] == "animeav1"

    def test_nas_network_error_falls_through_gracefully(self):
        ep = _episode(series_id="s1")
        cfg = _stream_config(animeflv_disabled=True, fallback_slug="naruto-jk", principal_slug=None)
        jk_url = "https://jkanime.net/m3u8/xyz.m3u8"

        with self._patch_nas("https://nas.astro-solutions.net", "secret"), \
             patch("domain.stream.resolve_nas_stream", return_value={"url": None, "error_type": "network_error"}), \
             patch("domain.stream.resolve_jkanime_stream", return_value={"url": jk_url, "error_type": None}):
            result = orchestrate_stream(ep, cfg)

        assert result["source"] == "jkanime"

    def test_nas_disabled_when_env_not_set_skips_nas(self):
        ep = _episode(series_id="s1")
        cfg = _stream_config(animeflv_disabled=True, fallback_slug="naruto-jk")
        jk_url = "https://jkanime.net/m3u8/xyz.m3u8"

        with self._patch_nas("", ""), \
             patch("domain.stream.resolve_nas_stream") as mock_nas, \
             patch("domain.stream.resolve_jkanime_stream", return_value={"url": jk_url, "error_type": None}):
            result = orchestrate_stream(ep, cfg)

        mock_nas.assert_not_called()
        assert result["source"] == "jkanime"


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
        stream_cfg = {"animeflv_disabled": False, "fallback_slug": None}

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
        stream_cfg = {"animeflv_disabled": True, "fallback_slug": None}

        with patch("db.episodes.get_episode_for_watch", return_value=row), \
             patch("db.series.get_stream_config", return_value=stream_cfg):
            res = client.get("/api/episodes/watch/naruto-1/stream-url")

        assert res.status_code == 404

    def test_503_when_upstream_error(self, client):
        row = _episode_row()
        stream_cfg = {"animeflv_disabled": False, "fallback_slug": None}

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
