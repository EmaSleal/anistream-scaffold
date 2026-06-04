"""Unit tests for fetcher.py helpers."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import requests
import pytest
from unittest.mock import patch, MagicMock

import fetcher


# ---------------------------------------------------------------------------
# fetch_recommendations
# ---------------------------------------------------------------------------

class TestFetchRecommendations:
    def _make_entry(self, mal_id: int) -> dict:
        return {
            "entry": {
                "mal_id": mal_id,
                "title": f"Anime {mal_id}",
                "images": {"jpg": {"image_url": f"http://img/{mal_id}.jpg"}},
            },
            "votes": 10,
        }

    def test_returns_at_most_three_entries(self):
        entries = [self._make_entry(i) for i in range(1, 6)]  # 5 entries
        response = {"data": entries}
        with patch.object(fetcher, "_get", return_value=response):
            result = fetcher.fetch_recommendations(1)
        assert len(result) == 3

    def test_returns_all_entries_when_fewer_than_three(self):
        entries = [self._make_entry(i) for i in range(1, 3)]  # 2 entries
        response = {"data": entries}
        with patch.object(fetcher, "_get", return_value=response):
            result = fetcher.fetch_recommendations(1)
        assert len(result) == 2

    def test_returned_entries_contain_mal_id(self):
        entries = [self._make_entry(i) for i in range(1, 4)]
        with patch.object(fetcher, "_get", return_value={"data": entries}):
            result = fetcher.fetch_recommendations(42)
        assert all("entry" in r for r in result)
        assert all(r["entry"]["mal_id"] in [1, 2, 3] for r in result)

    def test_returns_empty_list_on_requests_exception(self):
        with patch.object(fetcher, "_get", side_effect=requests.RequestException("timeout")):
            result = fetcher.fetch_recommendations(1)
        assert result == []

    def test_returns_empty_list_on_http_error(self):
        mock_response = MagicMock()
        mock_response.status_code = 500
        with patch.object(
            fetcher, "_get", side_effect=requests.HTTPError(response=mock_response)
        ):
            result = fetcher.fetch_recommendations(1)
        assert result == []

    def test_returns_empty_list_when_data_key_missing(self):
        with patch.object(fetcher, "_get", return_value={}):
            result = fetcher.fetch_recommendations(1)
        assert result == []

    def test_returns_empty_list_on_generic_exception(self):
        with patch.object(fetcher, "_get", side_effect=ValueError("unexpected")):
            result = fetcher.fetch_recommendations(1)
        assert result == []
