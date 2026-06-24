"""Tests for scraper/domain/download_sources.py."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("INTERNAL_JWT_SECRET", "test-internal-secret-for-tests-only")
os.environ.setdefault("SERVICE_SECRET", "test-service-secret")

from unittest.mock import patch

from domain.download_sources import probe_sources, resolve_source


_URL = "https://cdn.example.com/ep1.m3u8"
_AV1_OK = {"url": _URL, "error_type": None}
_AV1_MISS = {"url": None, "error_type": "no_source"}
_JK_OK = {"url": _URL, "error_type": None}
_JK_MISS = {"url": None, "error_type": "no_source"}


class TestProbeSources:
    def test_both_available(self):
        config = {"principal_slug": "slug-av1", "fallback_slug": "slug-jk"}
        with patch("domain.download_sources.resolve_animeav1_stream", return_value=_AV1_OK), \
             patch("domain.download_sources.resolve_jkanime_stream", return_value=_JK_OK):
            sources = probe_sources(config, 1)
        assert {"source": "animeav1", "available": True} in sources
        assert {"source": "jkanime", "available": True} in sources

    def test_only_av1_available(self):
        config = {"principal_slug": "slug-av1", "fallback_slug": "slug-jk"}
        with patch("domain.download_sources.resolve_animeav1_stream", return_value=_AV1_OK), \
             patch("domain.download_sources.resolve_jkanime_stream", return_value=_JK_MISS):
            sources = probe_sources(config, 1)
        assert {"source": "animeav1", "available": True} in sources
        assert {"source": "jkanime", "available": False} in sources

    def test_skips_av1_when_principal_slug_absent(self):
        config = {"fallback_slug": "slug-jk"}
        with patch("domain.download_sources.resolve_jkanime_stream", return_value=_JK_OK):
            sources = probe_sources(config, 1)
        source_names = [s["source"] for s in sources]
        assert "animeav1" not in source_names
        assert "jkanime" in source_names

    def test_skips_jkanime_when_fallback_slug_absent(self):
        config = {"principal_slug": "slug-av1"}
        with patch("domain.download_sources.resolve_animeav1_stream", return_value=_AV1_OK):
            sources = probe_sources(config, 1)
        source_names = [s["source"] for s in sources]
        assert "jkanime" not in source_names
        assert "animeav1" in source_names

    def test_available_false_when_resolver_raises(self):
        config = {"principal_slug": "slug-av1"}
        with patch("domain.download_sources.resolve_animeav1_stream", side_effect=RuntimeError("fail")):
            sources = probe_sources(config, 1)
        assert sources == [{"source": "animeav1", "available": False}]

    def test_empty_when_no_slugs(self):
        config = {}
        sources = probe_sources(config, 1)
        assert sources == []


class TestResolveSource:
    def test_returns_url_for_animeav1(self):
        config = {"principal_slug": "slug-av1"}
        with patch("domain.download_sources.resolve_animeav1_stream", return_value=_AV1_OK):
            url = resolve_source(config, 1, "animeav1")
        assert url == _URL

    def test_returns_url_for_jkanime(self):
        config = {"fallback_slug": "slug-jk"}
        with patch("domain.download_sources.resolve_jkanime_stream", return_value=_JK_OK):
            url = resolve_source(config, 1, "jkanime")
        assert url == _URL

    def test_returns_none_when_av1_fails(self):
        config = {"principal_slug": "slug-av1"}
        with patch("domain.download_sources.resolve_animeav1_stream", return_value=_AV1_MISS):
            assert resolve_source(config, 1, "animeav1") is None

    def test_returns_none_when_principal_slug_absent(self):
        config = {"fallback_slug": "slug-jk"}
        assert resolve_source(config, 1, "animeav1") is None

    def test_returns_none_when_fallback_slug_absent(self):
        config = {"principal_slug": "slug-av1"}
        assert resolve_source(config, 1, "jkanime") is None

    def test_returns_none_for_unknown_source(self):
        config = {"principal_slug": "slug-av1", "fallback_slug": "slug-jk"}
        assert resolve_source(config, 1, "unknown_provider") is None
