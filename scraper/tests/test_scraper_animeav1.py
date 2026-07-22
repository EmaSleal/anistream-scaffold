"""Unit tests for scraper_animeav1 — SUB/DUB dual-audio support.

Covers:
  S-01: scrape_animeav1_hash returns ic-sub hash when audio_type="sub"
  S-02: scrape_animeav1_hash returns ic-dub hash when audio_type="dub"
  S-03: scrape_animeav1_hash returns None for dub when ic-dub row absent
  S-04: scrape_animeav1_hash default audio_type behaves as "sub"
  S-05: animeav1_has_dub returns True when ic-dub present
  S-06: animeav1_has_dub returns False when ic-dub absent
  S-07: animeav1_has_dub returns False on network error
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("INTERNAL_JWT_SECRET", "test-internal-secret-for-tests-only")
os.environ.setdefault("SERVICE_SECRET", "test-service-secret-for-tests-only")

from unittest.mock import patch, MagicMock
import pytest


# ---------------------------------------------------------------------------
# Helpers — build minimal HTML pages with ic-sub / ic-dub rows
# ---------------------------------------------------------------------------

_SUB_HASH = "aabbccdd1111"
_DUB_HASH = "eeff22223333"

def _page_both_rows():
    """Page with both SUB and DUB rows, each with a distinct Zilla hash."""
    return f"""
    <html><body>
      <div class="server-row">
        <span class="ic-sub"></span>
        <a href="https://player.zilla-networks.com/play/{_SUB_HASH}">SUB</a>
        <iframe src="https://player.zilla-networks.com/play/{_SUB_HASH}"></iframe>
      </div>
      <div class="server-row">
        <span class="ic-dub"></span>
        <a href="https://player.zilla-networks.com/play/{_DUB_HASH}">DUB</a>
        <iframe src="https://player.zilla-networks.com/play/{_DUB_HASH}"></iframe>
      </div>
    </body></html>
    """

def _page_sub_only():
    """Page with only a SUB row — no ic-dub element."""
    return f"""
    <html><body>
      <div class="server-row">
        <span class="ic-sub"></span>
        <iframe src="https://player.zilla-networks.com/play/{_SUB_HASH}"></iframe>
      </div>
    </body></html>
    """

def _mock_response(html: str, status: int = 200):
    resp = MagicMock()
    resp.status_code = status
    resp.text = html
    resp.raise_for_status = MagicMock()
    if status >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status}")
    return resp


# ---------------------------------------------------------------------------
# S-01: SUB row selected when audio_type="sub"
# ---------------------------------------------------------------------------

class TestScrapeAnimeAV1HashSub:

    def test_s01_returns_sub_hash_when_both_rows_present(self):
        """S-01: Returns ic-sub hash when audio_type='sub' and both rows present."""
        from scraper_animeav1 import scrape_animeav1_hash

        with patch("scraper_animeav1._scraper") as mock_scraper:
            mock_scraper.get.return_value = _mock_response(_page_both_rows())
            result = scrape_animeav1_hash("naruto", 1, audio_type="sub")

        assert result == _SUB_HASH

    def test_s04_default_audio_type_behaves_as_sub(self):
        """S-04: Calling without audio_type arg returns ic-sub hash (backward compat)."""
        from scraper_animeav1 import scrape_animeav1_hash

        with patch("scraper_animeav1._scraper") as mock_scraper:
            mock_scraper.get.return_value = _mock_response(_page_both_rows())
            result = scrape_animeav1_hash("naruto", 1)

        assert result == _SUB_HASH

    def test_sub_falls_back_to_page_hash_when_ic_sub_absent(self):
        """Existing fallback: if no ic-sub row, returns first Zilla hash on page."""
        from scraper_animeav1 import scrape_animeav1_hash

        html = f'<html><body><iframe src="https://player.zilla-networks.com/play/{_SUB_HASH}"></iframe></body></html>'
        with patch("scraper_animeav1._scraper") as mock_scraper:
            mock_scraper.get.return_value = _mock_response(html)
            result = scrape_animeav1_hash("naruto", 1, audio_type="sub")

        assert result == _SUB_HASH


# ---------------------------------------------------------------------------
# S-02: DUB row selected when audio_type="dub"
# ---------------------------------------------------------------------------

class TestScrapeAnimeAV1HashDub:

    def test_s02_returns_dub_hash_when_ic_dub_present(self):
        """S-02: Returns ic-dub hash when audio_type='dub' and ic-dub row present."""
        from scraper_animeav1 import scrape_animeav1_hash

        with patch("scraper_animeav1._scraper") as mock_scraper:
            mock_scraper.get.return_value = _mock_response(_page_both_rows())
            result = scrape_animeav1_hash("naruto", 1, audio_type="dub")

        assert result == _DUB_HASH

    def test_s03_returns_none_when_ic_dub_absent(self):
        """S-03: Returns None when audio_type='dub' but no ic-dub row exists."""
        from scraper_animeav1 import scrape_animeav1_hash

        with patch("scraper_animeav1._scraper") as mock_scraper:
            mock_scraper.get.return_value = _mock_response(_page_sub_only())
            result = scrape_animeav1_hash("naruto", 1, audio_type="dub")

        assert result is None

    def test_dub_no_page_level_fallback(self):
        """DUB must NOT fall back to the first hash on the page when ic-dub is absent."""
        from scraper_animeav1 import scrape_animeav1_hash

        # Page has a Zilla hash but no ic-dub span
        html = f'<html><body><iframe src="https://player.zilla-networks.com/play/{_SUB_HASH}"></iframe></body></html>'
        with patch("scraper_animeav1._scraper") as mock_scraper:
            mock_scraper.get.return_value = _mock_response(html)
            result = scrape_animeav1_hash("naruto", 1, audio_type="dub")

        assert result is None

    def test_dub_returns_none_on_network_error(self):
        """DUB returns None (not exception) when network request fails."""
        from scraper_animeav1 import scrape_animeav1_hash

        with patch("scraper_animeav1._scraper") as mock_scraper:
            mock_scraper.get.side_effect = Exception("connection reset")
            result = scrape_animeav1_hash("naruto", 1, audio_type="dub")

        assert result is None


# ---------------------------------------------------------------------------
# S-05, S-06, S-07: animeav1_has_dub
# ---------------------------------------------------------------------------

class TestAnimeAV1HasDub:

    def test_s05_returns_true_when_ic_dub_present(self):
        """S-05: animeav1_has_dub returns True when ic-dub span is on the page."""
        from scraper_animeav1 import animeav1_has_dub

        with patch("scraper_animeav1._scraper") as mock_scraper:
            mock_scraper.get.return_value = _mock_response(_page_both_rows())
            result = animeav1_has_dub("naruto")

        assert result is True

    def test_s06_returns_false_when_ic_dub_absent(self):
        """S-06: animeav1_has_dub returns False when no ic-dub span on the page."""
        from scraper_animeav1 import animeav1_has_dub

        with patch("scraper_animeav1._scraper") as mock_scraper:
            mock_scraper.get.return_value = _mock_response(_page_sub_only())
            result = animeav1_has_dub("naruto")

        assert result is False

    def test_s07_returns_false_on_network_error(self):
        """S-07: animeav1_has_dub returns False (not exception) on network failure."""
        from scraper_animeav1 import animeav1_has_dub

        with patch("scraper_animeav1._scraper") as mock_scraper:
            mock_scraper.get.side_effect = Exception("timeout")
            result = animeav1_has_dub("naruto")

        assert result is False

    def test_has_dub_defaults_to_episode_1(self):
        """animeav1_has_dub with default episode_number=1 requests ep 1 URL."""
        from scraper_animeav1 import animeav1_has_dub

        with patch("scraper_animeav1._scraper") as mock_scraper:
            mock_scraper.get.return_value = _mock_response(_page_both_rows())
            animeav1_has_dub("naruto")
            call_url = mock_scraper.get.call_args[0][0]

        assert "/1" in call_url or call_url.endswith("/1")

    def test_has_dub_returns_false_on_http_error(self):
        """animeav1_has_dub returns False when server returns non-2xx."""
        from scraper_animeav1 import animeav1_has_dub

        with patch("scraper_animeav1._scraper") as mock_scraper:
            mock_scraper.get.return_value = _mock_response("", status=503)
            result = animeav1_has_dub("naruto")

        assert result is False
