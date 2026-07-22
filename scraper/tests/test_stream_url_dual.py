"""Tests for GET /api/episodes/watch/<id>/stream-url — dual-audio shape.

Covers:
  S-09: Dual probe returns {subUrl, dubUrl, subSource, audioFormats} for DUB-capable series
  S-10: DUB probe failure → dubUrl=null in 200 response
  S-11: SUB-only series → legacy {url, source} shape (single probe)
  S-12: hint=h264 bypasses DUB probe for DUB-capable series
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("INTERNAL_JWT_SECRET", "test-internal-secret-for-tests-only")
os.environ.setdefault("SERVICE_SECRET", "test-service-secret-for-tests-only")

import json
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _episode_row(series_id="s1", episode_number=1):
    return {
        "id": "ep1",
        "series_id": series_id,
        "episode_number": episode_number,
        "title": "Episode 1",
        "animeflv_slug": None,
        "thumbnail_url": None,
        "aired_at": None,
        "series": {"title": "Naruto"},
    }


def _stream_config_dub(principal_slug="naruto"):
    return {
        "principal_slug": principal_slug,
        "fallback_slug": None,
        "audio_formats": ["sub", "dub"],
    }


def _stream_config_sub_only(principal_slug="naruto"):
    return {
        "principal_slug": principal_slug,
        "fallback_slug": None,
        "audio_formats": ["sub"],
    }


_SUB_URL = "https://player.zilla-networks.com/m3u8/subhash"
_DUB_URL = "https://player.zilla-networks.com/m3u8/dubhash"


@pytest.fixture
def client():
    with patch("storage.get_client"):
        from app import create_app
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c


# ---------------------------------------------------------------------------
# S-09: DUB-capable series → dual-probe 200 response
# ---------------------------------------------------------------------------

_ROUTE_ORCH = "routes.episode_routes.orchestrate_stream"
_ROUTE_RESOLVE = "routes.episode_routes.resolve_animeav1_stream"


class TestStreamUrlDualProbe:

    def test_s09_dual_probe_returns_sub_and_dub_urls(self, client):
        """S-09: Returns {subUrl, dubUrl, subSource, audioFormats} for DUB series."""
        row = _episode_row()
        cfg = _stream_config_dub()

        sub_result = {"url": _SUB_URL, "source": "animeav1"}
        dub_result = {"url": _DUB_URL, "error_type": None}

        with patch("db.episodes.get_episode_for_watch", return_value=row), \
             patch("db.series.get_stream_config", return_value=cfg), \
             patch(_ROUTE_ORCH, return_value=sub_result), \
             patch(_ROUTE_RESOLVE, return_value=dub_result):
            res = client.get("/api/episodes/watch/ep1/stream-url")

        assert res.status_code == 200
        data = json.loads(res.data)
        assert "subUrl" in data
        assert "dubUrl" in data
        assert "subSource" in data
        assert "audioFormats" in data
        assert data["subUrl"] == _SUB_URL
        assert data["dubUrl"] == _DUB_URL
        assert data["subSource"] == "animeav1"
        assert "dub" in data["audioFormats"]

    def test_s09_both_probes_run_in_parallel(self, client):
        """S-09: Both SUB and DUB probes are called."""
        row = _episode_row()
        cfg = _stream_config_dub()

        sub_result = {"url": _SUB_URL, "source": "animeav1"}
        dub_result = {"url": _DUB_URL, "error_type": None}

        with patch("db.episodes.get_episode_for_watch", return_value=row), \
             patch("db.series.get_stream_config", return_value=cfg), \
             patch(_ROUTE_ORCH, return_value=sub_result) as mock_sub, \
             patch(_ROUTE_RESOLVE, return_value=dub_result) as mock_dub:
            client.get("/api/episodes/watch/ep1/stream-url")

        mock_sub.assert_called_once()
        mock_dub.assert_called_once()

    def test_s10_dub_probe_null_when_no_dub_hash(self, client):
        """S-10: dubUrl=null when DUB probe returns no_source."""
        row = _episode_row()
        cfg = _stream_config_dub()

        sub_result = {"url": _SUB_URL, "source": "animeav1"}
        dub_result = {"url": None, "error_type": "no_source"}

        with patch("db.episodes.get_episode_for_watch", return_value=row), \
             patch("db.series.get_stream_config", return_value=cfg), \
             patch(_ROUTE_ORCH, return_value=sub_result), \
             patch(_ROUTE_RESOLVE, return_value=dub_result):
            res = client.get("/api/episodes/watch/ep1/stream-url")

        assert res.status_code == 200
        data = json.loads(res.data)
        assert data["subUrl"] == _SUB_URL
        assert data["dubUrl"] is None

    def test_s10_dub_probe_null_when_network_error(self, client):
        """S-10: dubUrl=null when DUB probe returns network_error (silent)."""
        row = _episode_row()
        cfg = _stream_config_dub()

        sub_result = {"url": _SUB_URL, "source": "animeav1"}
        dub_result = {"url": None, "error_type": "network_error"}

        with patch("db.episodes.get_episode_for_watch", return_value=row), \
             patch("db.series.get_stream_config", return_value=cfg), \
             patch(_ROUTE_ORCH, return_value=sub_result), \
             patch(_ROUTE_RESOLVE, return_value=dub_result):
            res = client.get("/api/episodes/watch/ep1/stream-url")

        assert res.status_code == 200
        data = json.loads(res.data)
        assert data["dubUrl"] is None

    def test_sub_failure_still_raises_404(self, client):
        """SUB probe failure must still return 404 even in dual-probe mode."""
        row = _episode_row()
        cfg = _stream_config_dub()

        from domain.stream import NoSourceError

        with patch("db.episodes.get_episode_for_watch", return_value=row), \
             patch("db.series.get_stream_config", return_value=cfg), \
             patch(_ROUTE_ORCH, side_effect=NoSourceError("no sub")), \
             patch(_ROUTE_RESOLVE, return_value={"url": _DUB_URL, "error_type": None}):
            res = client.get("/api/episodes/watch/ep1/stream-url")

        assert res.status_code == 404

    def test_sub_upstream_error_returns_503(self, client):
        """SUB UpstreamError in dual-probe mode must still return 503."""
        row = _episode_row()
        cfg = _stream_config_dub()

        from domain.stream import UpstreamError

        with patch("db.episodes.get_episode_for_watch", return_value=row), \
             patch("db.series.get_stream_config", return_value=cfg), \
             patch(_ROUTE_ORCH, side_effect=UpstreamError("scrape fail")), \
             patch(_ROUTE_RESOLVE, return_value={"url": _DUB_URL, "error_type": None}):
            res = client.get("/api/episodes/watch/ep1/stream-url")

        assert res.status_code == 503


# ---------------------------------------------------------------------------
# S-11: SUB-only series → legacy shape, single probe
# ---------------------------------------------------------------------------

class TestStreamUrlSubOnly:

    def test_s11_sub_only_series_returns_legacy_shape(self, client):
        """S-11: SUB-only series (audio_formats=['sub']) returns {url, source}."""
        row = _episode_row()
        cfg = _stream_config_sub_only()

        with patch("db.episodes.get_episode_for_watch", return_value=row), \
             patch("db.series.get_stream_config", return_value=cfg), \
             patch(_ROUTE_ORCH,
                   return_value={"url": _SUB_URL, "source": "animeav1"}) as mock_sub, \
             patch(_ROUTE_RESOLVE) as mock_dub:
            res = client.get("/api/episodes/watch/ep1/stream-url")

        assert res.status_code == 200
        data = json.loads(res.data)
        # Legacy shape — single probe
        assert "url" in data
        assert data["url"] == _SUB_URL
        # DUB probe must NOT run
        mock_dub.assert_not_called()

    def test_s11_no_audio_formats_key_treated_as_sub_only(self, client):
        """stream_config without audio_formats key defaults to SUB-only path."""
        row = _episode_row()
        cfg = {"principal_slug": "naruto", "fallback_slug": None}

        with patch("db.episodes.get_episode_for_watch", return_value=row), \
             patch("db.series.get_stream_config", return_value=cfg), \
             patch(_ROUTE_ORCH,
                   return_value={"url": _SUB_URL, "source": "animeav1"}), \
             patch(_ROUTE_RESOLVE) as mock_dub:
            res = client.get("/api/episodes/watch/ep1/stream-url")

        assert res.status_code == 200
        mock_dub.assert_not_called()


# ---------------------------------------------------------------------------
# S-12: hint=h264 bypasses DUB probe
# ---------------------------------------------------------------------------

class TestStreamUrlH264Hint:

    def test_s12_h264_hint_single_probe_legacy_shape(self, client):
        """S-12: hint=h264 forces SUB-only single-probe path even for DUB series."""
        row = _episode_row()
        cfg = _stream_config_dub()

        with patch("db.episodes.get_episode_for_watch", return_value=row), \
             patch("db.series.get_stream_config", return_value=cfg), \
             patch(_ROUTE_ORCH,
                   return_value={"url": _SUB_URL, "source": "jkanime"}), \
             patch(_ROUTE_RESOLVE) as mock_dub:
            res = client.get("/api/episodes/watch/ep1/stream-url?hint=h264")

        assert res.status_code == 200
        data = json.loads(res.data)
        # When h264 hint used, legacy shape (orchestrate handles h264 bypass internally)
        assert "url" in data
        mock_dub.assert_not_called()
