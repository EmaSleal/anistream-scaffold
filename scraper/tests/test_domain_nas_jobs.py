"""Tests for scraper/domain/nas_jobs.py."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("INTERNAL_JWT_SECRET", "test-internal-secret-for-tests-only")
os.environ.setdefault("SERVICE_SECRET", "test-service-secret")

from unittest.mock import patch, MagicMock

import pytest

import domain.nas_jobs as nas_jobs_module
from domain.nas_jobs import (
    NasUnavailable,
    check_episode_status,
    create_download_job,
    get_job_status,
    nas_configured,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(status_code: int, json_data: dict | None = None, ok: bool | None = None):
    m = MagicMock()
    m.status_code = status_code
    m.ok = ok if ok is not None else (200 <= status_code < 300)
    if json_data is not None:
        m.json.return_value = json_data
    m.text = ""
    return m


# ---------------------------------------------------------------------------
# nas_configured
# ---------------------------------------------------------------------------

class TestNasConfigured:
    def test_true_when_both_set(self, monkeypatch):
        monkeypatch.setattr(nas_jobs_module, "NAS_BASE_URL", "http://nas")
        monkeypatch.setattr(nas_jobs_module, "NAS_API_KEY", "key")
        assert nas_configured() is True

    def test_false_when_url_missing(self, monkeypatch):
        monkeypatch.setattr(nas_jobs_module, "NAS_BASE_URL", "")
        monkeypatch.setattr(nas_jobs_module, "NAS_API_KEY", "key")
        assert nas_configured() is False

    def test_false_when_key_missing(self, monkeypatch):
        monkeypatch.setattr(nas_jobs_module, "NAS_BASE_URL", "http://nas")
        monkeypatch.setattr(nas_jobs_module, "NAS_API_KEY", "")
        assert nas_configured() is False


# ---------------------------------------------------------------------------
# check_episode_status
# ---------------------------------------------------------------------------

class TestCheckEpisodeStatus:
    def test_downloaded_on_200(self, monkeypatch):
        monkeypatch.setattr(nas_jobs_module, "NAS_BASE_URL", "http://nas")
        monkeypatch.setattr(nas_jobs_module, "NAS_API_KEY", "key")
        with patch("domain.nas_jobs.requests.get", return_value=_mock_response(200, {"id": 1})):
            assert check_episode_status("series-1", 1) == "downloaded"

    def test_missing_on_404(self, monkeypatch):
        monkeypatch.setattr(nas_jobs_module, "NAS_BASE_URL", "http://nas")
        monkeypatch.setattr(nas_jobs_module, "NAS_API_KEY", "key")
        with patch("domain.nas_jobs.requests.get", return_value=_mock_response(404)):
            assert check_episode_status("series-1", 1) == "missing"

    def test_unknown_on_network_error(self, monkeypatch):
        monkeypatch.setattr(nas_jobs_module, "NAS_BASE_URL", "http://nas")
        monkeypatch.setattr(nas_jobs_module, "NAS_API_KEY", "key")
        with patch("domain.nas_jobs.requests.get", side_effect=ConnectionError("timeout")):
            assert check_episode_status("series-1", 1) == "unknown"

    def test_unknown_on_unexpected_status(self, monkeypatch):
        monkeypatch.setattr(nas_jobs_module, "NAS_BASE_URL", "http://nas")
        monkeypatch.setattr(nas_jobs_module, "NAS_API_KEY", "key")
        with patch("domain.nas_jobs.requests.get", return_value=_mock_response(500)):
            assert check_episode_status("series-1", 1) == "unknown"

    def test_unknown_when_not_configured(self, monkeypatch):
        monkeypatch.setattr(nas_jobs_module, "NAS_BASE_URL", "")
        monkeypatch.setattr(nas_jobs_module, "NAS_API_KEY", "")
        assert check_episode_status("series-1", 1) == "unknown"


# ---------------------------------------------------------------------------
# create_download_job
# ---------------------------------------------------------------------------

class TestCreateDownloadJob:
    def test_returns_job_dict_on_success(self, monkeypatch):
        monkeypatch.setattr(nas_jobs_module, "NAS_BASE_URL", "http://nas")
        monkeypatch.setattr(nas_jobs_module, "NAS_API_KEY", "key")
        resp = _mock_response(200, {"job_id": "abc-123", "status": "pending"})
        with patch("domain.nas_jobs.requests.post", return_value=resp):
            result = create_download_job("series-1", 1, "http://cdn/ep1.m3u8", "animeav1")
        assert result["jobId"] == "abc-123"
        assert result["status"] == "pending"

    def test_raises_nas_unavailable_on_5xx(self, monkeypatch):
        monkeypatch.setattr(nas_jobs_module, "NAS_BASE_URL", "http://nas")
        monkeypatch.setattr(nas_jobs_module, "NAS_API_KEY", "key")
        with patch("domain.nas_jobs.requests.post", return_value=_mock_response(500)):
            with pytest.raises(NasUnavailable):
                create_download_job("series-1", 1, "http://cdn/ep1.m3u8", "animeav1")

    def test_raises_nas_unavailable_on_network_error(self, monkeypatch):
        monkeypatch.setattr(nas_jobs_module, "NAS_BASE_URL", "http://nas")
        monkeypatch.setattr(nas_jobs_module, "NAS_API_KEY", "key")
        with patch("domain.nas_jobs.requests.post", side_effect=ConnectionError("timeout")):
            with pytest.raises(NasUnavailable):
                create_download_job("series-1", 1, "http://cdn/ep1.m3u8", "animeav1")

    def test_raises_nas_unavailable_when_not_configured(self, monkeypatch):
        monkeypatch.setattr(nas_jobs_module, "NAS_BASE_URL", "")
        monkeypatch.setattr(nas_jobs_module, "NAS_API_KEY", "")
        with pytest.raises(NasUnavailable):
            create_download_job("series-1", 1, "http://cdn/ep1.m3u8", "animeav1")


# ---------------------------------------------------------------------------
# get_job_status
# ---------------------------------------------------------------------------

class TestGetJobStatus:
    def test_returns_status_on_200(self, monkeypatch):
        monkeypatch.setattr(nas_jobs_module, "NAS_BASE_URL", "http://nas")
        monkeypatch.setattr(nas_jobs_module, "NAS_API_KEY", "key")
        resp = _mock_response(200, {"status": "done"})
        with patch("domain.nas_jobs.requests.get", return_value=resp):
            result = get_job_status("job-1")
        assert result["status"] == "done"

    def test_includes_error_field_when_failed(self, monkeypatch):
        monkeypatch.setattr(nas_jobs_module, "NAS_BASE_URL", "http://nas")
        monkeypatch.setattr(nas_jobs_module, "NAS_API_KEY", "key")
        resp = _mock_response(200, {"status": "failed", "error": "disk full"})
        with patch("domain.nas_jobs.requests.get", return_value=resp):
            result = get_job_status("job-1")
        assert result["status"] == "failed"
        assert result["error"] == "disk full"

    def test_unknown_on_404(self, monkeypatch):
        monkeypatch.setattr(nas_jobs_module, "NAS_BASE_URL", "http://nas")
        monkeypatch.setattr(nas_jobs_module, "NAS_API_KEY", "key")
        with patch("domain.nas_jobs.requests.get", return_value=_mock_response(404)):
            assert get_job_status("job-1") == {"status": "unknown"}

    def test_unknown_on_network_error(self, monkeypatch):
        monkeypatch.setattr(nas_jobs_module, "NAS_BASE_URL", "http://nas")
        monkeypatch.setattr(nas_jobs_module, "NAS_API_KEY", "key")
        with patch("domain.nas_jobs.requests.get", side_effect=ConnectionError("timeout")):
            assert get_job_status("job-1") == {"status": "unknown"}

    def test_unknown_when_not_configured(self, monkeypatch):
        monkeypatch.setattr(nas_jobs_module, "NAS_BASE_URL", "")
        monkeypatch.setattr(nas_jobs_module, "NAS_API_KEY", "")
        assert get_job_status("job-1") == {"status": "unknown"}
