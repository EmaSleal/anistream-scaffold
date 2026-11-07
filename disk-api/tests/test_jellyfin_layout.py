import asyncio
import subprocess
from pathlib import Path

import pytest

from app.models import db
from app.routers import files as files_mod
from app.routers import jobs as jobs_mod
from app.routers.files import sanitize_name


# --- sanitization -----------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("Re:Zero − Starting Life in Another World", "ReZero − Starting Life in Another World"),
    ("Fate/stay night", "Fatestay night"),
    ("Dr. Stone.", "Dr. Stone"),
    ('  A*B?"C"<D>|E\\F  ', "ABCDEF"),
    ("a\x00b\tc\n\nd", "ab c d"),
    ("  ...  ", "fallback-id"),
    ("", "fallback-id"),
])
def test_sanitize_name(raw, expected):
    assert sanitize_name(raw, "fallback-id") == expected


def test_target_helper_rules(roots):
    _, media = roots
    d, base = files_mod.jellyfin_episode_target("s1", 100, "Show", 2020)
    assert d == media / "Show (2020)" / "Season 01"
    assert base == "Show (2020) S01E100"
    assert files_mod.jellyfin_episode_target("s1", 5, "Show", None)[1] == "Show S01E05"
    assert files_mod.jellyfin_episode_target("s1", 5, "Show", 0)[1] == "Show S01E05"
    assert files_mod.jellyfin_episode_target("s1", 5, None, 2020) is None
    assert files_mod.jellyfin_episode_target("s1", None, "Show", 2020) is None
    assert files_mod.jellyfin_episode_target(None, 1, "Show", 2020) is None
    assert files_mod.jellyfin_episode_target("s1", 1, "...", 2020)[1] == "s1 (2020) S01E01"


def test_target_none_without_media_root(roots, monkeypatch):
    monkeypatch.setattr(files_mod, "MEDIA_ROOT", None)
    assert files_mod.jellyfin_episode_target("s1", 1, "Show", 2020) is None


# --- direct download --------------------------------------------------------

class _FakeResponse:
    def __init__(self, headers):
        self.headers = headers

    def raise_for_status(self):
        pass

    async def aiter_bytes(self, chunk_size=0):
        yield b"video-bytes"

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _FakeClient:
    def __init__(self, headers):
        self._headers = headers

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def stream(self, method, url):
        return _FakeResponse(self._headers)


def _patch_httpx(monkeypatch, headers):
    monkeypatch.setattr(jobs_mod.httpx, "AsyncClient", lambda **kw: _FakeClient(headers))


def _run(**kw):
    db.create_job(job_id="j1", url="http://x/y.mp4", category="videos",
                  series_id=kw.get("series_id"), episode_number=kw.get("episode_number"))
    asyncio.run(jobs_mod._run_download("j1", "http://x/y.mp4", "videos", **kw))
    return db.get_job("j1")


def test_direct_download_jellyfin_layout(roots, client, monkeypatch):
    _, media = roots
    _patch_httpx(monkeypatch, {"content-type": "video/mp4"})
    job = _run(series_id="s1", episode_number=3, series_title="Fate/stay night", series_year=2006)
    assert job["status"] == "done", job
    expected = media / "Fatestay night (2006)" / "Season 01" / "Fatestay night (2006) S01E03.mp4"
    assert expected.read_bytes() == b"video-bytes"
    rec = db.get_file_by_episode("s1", 3)
    assert rec["stored_path"] == str(expected)
    # NAS lookup by (series_id, episode_number) still works
    r = client.get("/api/episodes/s1/3")
    assert r.status_code == 200
    assert r.json()["stored_path"] == str(expected)


def test_direct_download_extension_from_content_disposition(roots, monkeypatch):
    _, media = roots
    _patch_httpx(monkeypatch, {"content-type": "video/x-matroska",
                               "content-disposition": 'attachment; filename="ep.mkv"'})
    job = _run(series_id="s1", episode_number=100, series_title="Show", series_year=None)
    assert job["status"] == "done", job
    assert (media / "Show" / "Season 01" / "Show S01E100.mkv").exists()


def test_direct_download_legacy_without_title(roots, monkeypatch):
    storage, media = roots
    _patch_httpx(monkeypatch, {"content-type": "video/mp4"})
    job = _run(series_id="s1", episode_number=3)
    assert job["status"] == "done", job
    assert (storage / "videos" / "episodes" / "s1" / "y.mp4").exists()
    assert not media.exists()


def test_direct_download_legacy_without_media_root(roots, monkeypatch):
    storage, _ = roots
    monkeypatch.setattr(files_mod, "MEDIA_ROOT", None)
    _patch_httpx(monkeypatch, {"content-type": "video/mp4"})
    job = _run(series_id="s1", episode_number=3, series_title="Show", series_year=2020)
    assert job["status"] == "done", job
    assert (storage / "videos" / "episodes" / "s1" / "y.mp4").exists()


# --- yt-dlp -----------------------------------------------------------------

class _FakeYDL:
    captured = {}

    def __init__(self, opts):
        type(self).captured = opts
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=True):
        path = Path(self.opts["outtmpl"].replace("%%", "%").replace("%(ext)s", "mp4"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"hls-bytes")
        return {"title": "whatever", "ext": "mp4"}

    def prepare_filename(self, info):
        return self.opts["outtmpl"].replace("%%", "%").replace("%(ext)s", "mp4")


def test_ytdlp_jellyfin_layout_and_faststart(roots, monkeypatch):
    _, media = roots
    monkeypatch.setattr(jobs_mod.yt_dlp, "YoutubeDL", _FakeYDL)
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        Path(cmd[-1]).write_bytes(b"faststart-bytes")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(jobs_mod.subprocess, "run", fake_run)
    db.create_job(job_id="j2", url="http://x/a.m3u8", category="videos",
                  series_id="s2", episode_number=7)
    asyncio.run(jobs_mod._run_download(
        "j2", "http://x/a.m3u8", "videos", "s2", 7, "100% Show", 2021))
    assert db.get_job("j2")["status"] == "done", db.get_job("j2")
    expected = media / "100% Show (2021)" / "Season 01" / "100% Show (2021) S01E07.mp4"
    assert _FakeYDL.captured["outtmpl"].endswith("100%% Show (2021) S01E07.%(ext)s")
    assert expected.read_bytes() == b"faststart-bytes"
    assert len(calls) == 1
    assert db.get_file_by_episode("s2", 7)["stored_path"] == str(expected)


# --- upload + enqueue -------------------------------------------------------

def test_upload_jellyfin_layout(roots, client):
    _, media = roots
    r = client.post(
        "/api/upload",
        files={"file": ("whatever.mp4", b"abc", "video/mp4")},
        data={"series_id": "s3", "episode_number": "12",
              "series_title": "Show: Two.", "series_year": "2019"},
    )
    assert r.status_code == 200, r.text
    expected = media / "Show Two (2019)" / "Season 01" / "Show Two (2019) S01E12.mp4"
    assert expected.read_bytes() == b"abc"
    assert r.json()["stored_path"] == str(expected)
    assert client.get("/api/episodes/s3/12").json()["stored_path"] == str(expected)


def test_upload_legacy_layout_without_title(roots, client):
    storage, media = roots
    r = client.post(
        "/api/upload",
        files={"file": ("ep.mp4", b"abc", "video/mp4")},
        data={"series_id": "s3", "episode_number": "12"},
    )
    assert r.status_code == 200
    assert (storage / "videos" / "episodes" / "s3" / "ep.mp4").exists()
    assert not media.exists()


def test_enqueue_accepts_title_and_year(roots, client, monkeypatch):
    seen = {}

    async def fake_run(*args):
        seen["args"] = args

    monkeypatch.setattr(jobs_mod, "_run_download", fake_run)
    r = client.post("/api/jobs", json={
        "url": "http://x/y.mp4", "category": "videos", "series_id": "s1",
        "episode_number": 1, "series_title": "Show", "series_year": 2020})
    assert r.status_code == 202
    assert seen["args"][-2:] == ("Show", 2020)


def test_requires_api_key(roots):
    from fastapi.testclient import TestClient
    from app.main import app
    assert TestClient(app).get("/api/episodes/s1/1").status_code == 403


class _FakeYDLExtChange(_FakeYDL):
    def prepare_filename(self, info):
        return self.opts["outtmpl"].replace("%%", "%").replace("%(ext)s", "webm")


def test_ytdlp_fallback_lookup_with_glob_chars_in_title(roots, monkeypatch):
    _, media = roots
    monkeypatch.setattr(jobs_mod.yt_dlp, "YoutubeDL", _FakeYDLExtChange)
    monkeypatch.setattr(
        jobs_mod.subprocess, "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1),
    )
    db.create_job(job_id="j3", url="http://x/a.m3u8", category="videos",
                  series_id="s4", episode_number=1)
    asyncio.run(jobs_mod._run_download(
        "j3", "http://x/a.m3u8", "videos", "s4", 1, "[Oshi no Ko]", 2023))
    assert db.get_job("j3")["status"] == "done", db.get_job("j3")
    expected = media / "[Oshi no Ko] (2023)" / "Season 01" / "[Oshi no Ko] (2023) S01E01.mp4"
    assert db.get_file_by_episode("s4", 1)["stored_path"] == str(expected)
