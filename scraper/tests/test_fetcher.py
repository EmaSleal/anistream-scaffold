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

    def test_returns_none_on_requests_exception(self):
        with patch.object(fetcher, "_get", side_effect=requests.RequestException("timeout")):
            result = fetcher.fetch_recommendations(1)
        assert result is None

    def test_returns_none_on_http_error(self):
        mock_response = MagicMock()
        mock_response.status_code = 500
        with patch.object(
            fetcher, "_get", side_effect=requests.HTTPError(response=mock_response)
        ):
            result = fetcher.fetch_recommendations(1)
        assert result is None

    def test_returns_empty_list_when_data_key_missing(self):
        # Successful Jikan response with no recommendations → [] (not None)
        with patch.object(fetcher, "_get", return_value={}):
            result = fetcher.fetch_recommendations(1)
        assert result == []

    def test_returns_none_on_generic_exception(self):
        with patch.object(fetcher, "_get", side_effect=ValueError("unexpected")):
            result = fetcher.fetch_recommendations(1)
        assert result is None


# ---------------------------------------------------------------------------
# fetch_related_anime
# ---------------------------------------------------------------------------

class TestFetchRelatedAnime:
    def _make_mal_response(self, related_ids: list[int], genres: list[str]) -> dict:
        return {
            "related_anime": [
                {"node": {"id": mid, "title": f"Anime {mid}"}, "relation_type": "sequel"}
                for mid in related_ids
            ],
            "genres": [{"id": i + 1, "name": g} for i, g in enumerate(genres)],
        }

    def test_returns_related_ids_and_genres(self):
        payload = self._make_mal_response([10, 20], ["Action", "Fantasy"])
        mock_resp = MagicMock()
        mock_resp.json.return_value = payload
        mock_resp.raise_for_status = MagicMock()
        with patch("fetcher.requests.get", return_value=mock_resp):
            with patch("fetcher.MAL_CLIENT_ID", "test-key", create=True):
                import importlib, config
                config.MAL_CLIENT_ID = "test-key"
                related_ids, genres = fetcher.fetch_related_anime(1)
        assert related_ids == [10, 20]
        assert genres == ["Action", "Fantasy"]

    def test_returns_empty_lists_when_no_related_anime(self):
        payload = self._make_mal_response([], ["Action"])
        mock_resp = MagicMock()
        mock_resp.json.return_value = payload
        mock_resp.raise_for_status = MagicMock()
        with patch("fetcher.requests.get", return_value=mock_resp):
            with patch("fetcher.MAL_CLIENT_ID", "test-key", create=True):
                import config
                config.MAL_CLIENT_ID = "test-key"
                related_ids, genres = fetcher.fetch_related_anime(1)
        assert related_ids == []
        assert genres == ["Action"]

    def test_returns_none_tuple_on_http_error(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError()
        with patch("fetcher.requests.get", return_value=mock_resp):
            with patch("fetcher.MAL_CLIENT_ID", "test-key", create=True):
                import config
                config.MAL_CLIENT_ID = "test-key"
                result = fetcher.fetch_related_anime(1)
        assert result == (None, None)

    def test_returns_none_tuple_on_network_error(self):
        with patch("fetcher.requests.get", side_effect=requests.RequestException("timeout")):
            with patch("fetcher.MAL_CLIENT_ID", "test-key", create=True):
                import config
                config.MAL_CLIENT_ID = "test-key"
                result = fetcher.fetch_related_anime(1)
        assert result == (None, None)

    def test_returns_none_tuple_when_no_client_id(self):
        import config
        original = config.MAL_CLIENT_ID
        config.MAL_CLIENT_ID = ""
        try:
            result = fetcher.fetch_related_anime(1)
        finally:
            config.MAL_CLIENT_ID = original
        assert result == (None, None)


class TestMalSeasonAiring:
    @staticmethod
    def _resp(body):
        r = MagicMock()
        r.json.return_value = body
        r.raise_for_status.return_value = None
        return r

    def test_paginates_unwraps_nodes_and_flags_airing(self):
        from datetime import date
        page1 = self._resp({
            "data": [{"node": {"id": 1, "title": "A", "status": "currently_airing", "mean": 7.5,
                               "genres": [{"id": 1, "name": "Action"}]}}],
            "paging": {"next": "https://api.myanimelist.net/v2/anime/season/2026/fall?offset=1"},
        })
        page2 = self._resp({
            "data": [{"node": {"id": 2, "title": "B", "status": "finished_airing"}}],
            "paging": {},
        })
        with patch("fetcher.MAL_CLIENT_ID", "key"), \
             patch("fetcher.requests.get", side_effect=[page1, page2]) as get:
            out = fetcher.fetch_mal_season_airing(today=date(2026, 11, 2))
        assert [e["mal_id"] for e in out] == [1, 2]
        assert out[0]["airing"] is True and out[1]["airing"] is False
        assert out[0]["score"] == 7.5 and out[0]["genres"][0]["name"] == "Action"
        first, second = get.call_args_list
        assert first.args[0].endswith("/anime/season/2026/fall")
        assert first.kwargs["headers"] == {"X-MAL-CLIENT-ID": "key"}
        assert first.kwargs["params"]["limit"] == 500
        assert "status" in first.kwargs["params"]["fields"]
        assert second.args[0].endswith("offset=1")
        assert second.kwargs["headers"] == {"X-MAL-CLIENT-ID": "key"}

    def test_mid_pagination_failure_raises(self):
        page1 = self._resp({
            "data": [{"node": {"id": 1, "status": "currently_airing"}}],
            "paging": {"next": "https://api.myanimelist.net/v2/next"},
        })
        with patch("fetcher.MAL_CLIENT_ID", "key"), \
             patch("fetcher.requests.get", side_effect=[page1, requests.ConnectionError("x")]):
            with pytest.raises(requests.RequestException):
                fetcher.fetch_mal_season_airing()

    def test_http_error_raises(self):
        bad = MagicMock()
        bad.raise_for_status.side_effect = requests.HTTPError("500")
        with patch("fetcher.MAL_CLIENT_ID", "key"), patch("fetcher.requests.get", return_value=bad):
            with pytest.raises(requests.HTTPError):
                fetcher.fetch_mal_season_airing()

    @pytest.mark.parametrize("d,expected", [
        ((2026, 1, 1), (2026, "winter")),
        ((2026, 3, 31), (2026, "winter")),
        ((2026, 4, 1), (2026, "spring")),
        ((2026, 6, 30), (2026, "spring")),
        ((2026, 7, 1), (2026, "summer")),
        ((2026, 9, 30), (2026, "summer")),
        ((2026, 10, 1), (2026, "fall")),
        ((2026, 12, 31), (2026, "fall")),
    ])
    def test_season_boundaries(self, d, expected):
        from datetime import date
        assert fetcher.mal_season_for(date(*d)) == expected
