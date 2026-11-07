import asyncio
import subprocess
import threading
from pathlib import Path

import pytest

from app.models import db
from app.routers import jobs as jobs_mod

BODY = {"url": "http://x/a.m3u8", "category": "videos",
        "series_id": "s1", "episode_number": 2,
        "series_title": "Show", "series_year": 2023}


@pytest.fixture
def ran(monkeypatch):
    calls = []

    async def fake_run(*args):
        calls.append(args)

    monkeypatch.setattr(jobs_mod, "_run_download", fake_run)
    return calls


def _count():
    with db.get_connection() as conn:
        return conn.execute("SELECT COUNT(*) FROM download_jobs").fetchone()[0]


def test_new_job_unchanged(client, ran):
    r = client.post("/api/jobs", json=BODY)
    assert r.status_code == 202
    assert r.json()["status"] == "pending"
    assert _count() == 1
    assert len(ran) == 1


@pytest.mark.parametrize("status", ["pending", "downloading"])
def test_active_job_reused(client, ran, status):
    db.create_job(job_id="j1", url="http://x/old", category="videos",
                  series_id="s1", episode_number=2)
    db.update_job("j1", status=status)
    r = client.post("/api/jobs", json=BODY)
    assert r.status_code == 202
    assert r.json()["job_id"] == "j1"
    assert r.json()["status"] == status
    assert _count() == 1
    assert ran == []


def test_other_episode_not_blocked(client, ran):
    db.create_job(job_id="j1", url="http://x/old", category="videos",
                  series_id="s1", episode_number=3)
    client.post("/api/jobs", json=BODY)
    assert _count() == 2
    assert len(ran) == 1


def test_existing_file_returns_done_job(client, ran):
    fid = db.insert_file(filename="a.mp4", stored_path="/x/a.mp4",
                       content_type="video/mp4", size_bytes=1,
                       category="videos", series_id="s1", episode_number=2)
    r = client.post("/api/jobs", json=BODY)
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "done"
    job = db.get_job(body["job_id"])
    assert job["status"] == "done" and job["file_id"] == fid
    assert _count() == 1
    assert ran == []
    polled = client.get(f"/api/jobs/{body['job_id']}")
    assert polled.json()["status"] == "done"


def test_finished_job_without_file_redownloads(client, ran):
    db.create_job(job_id="j1", url="http://x/old", category="videos",
                  series_id="s1", episode_number=2)
    db.update_job("j1", status="failed")
    client.post("/api/jobs", json=BODY)
    assert _count() == 2
    assert len(ran) == 1


# --- faststart remux runs off the event loop --------------------------------

class _YDL:
    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=True):
        out = Path(self.opts["outtmpl"].replace("%(ext)s", "mp4"))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"original")
        return {"title": "t", "ext": "mp4"}

    def prepare_filename(self, info):
        return self.opts["outtmpl"].replace("%(ext)s", "mp4")


def _run(roots, monkeypatch, fake_run):
    _, media = roots
    monkeypatch.setattr(jobs_mod.yt_dlp, "YoutubeDL", _YDL)
    monkeypatch.setattr(jobs_mod.subprocess, "run", fake_run)
    db.create_job(job_id="j", url="http://x/a.m3u8", category="videos",
                  series_id="s9", episode_number=1)

    async def go():
        await jobs_mod._run_download(
            "j", "http://x/a.m3u8", "videos", "s9", 1, "Show", 2023)
        return threading.get_ident()

    loop_thread = asyncio.run(go())
    return media, loop_thread


def test_faststart_runs_off_loop_thread(roots, monkeypatch):
    seen = []

    def fake_run(cmd, **kw):
        seen.append(threading.get_ident())
        Path(cmd[-1]).write_bytes(b"fast")
        return subprocess.CompletedProcess(cmd, 0)

    media, loop_thread = _run(roots, monkeypatch, fake_run)
    assert db.get_job("j")["status"] == "done"
    assert len(seen) == 1 and seen[0] != loop_thread
    out = media / "Show (2023)" / "Season 01" / "Show (2023) S01E01.mp4"
    assert out.read_bytes() == b"fast"


def test_faststart_failure_keeps_original(roots, monkeypatch):
    def fake_run(cmd, **kw):
        Path(cmd[-1]).write_bytes(b"partial")
        return subprocess.CompletedProcess(cmd, 1)

    media, _ = _run(roots, monkeypatch, fake_run)
    assert db.get_job("j")["status"] == "done"
    season = media / "Show (2023)" / "Season 01"
    assert (season / "Show (2023) S01E01.mp4").read_bytes() == b"original"
    assert not list(season.glob("*.faststart.mp4"))


def test_init_db_fails_stale_active_jobs(client, ran):
    for jid, st in (("a", "downloading"), ("b", "pending"), ("c", "done")):
        db.create_job(job_id=jid, url="http://x/old", category="videos",
                      series_id="s1", episode_number=2, status=st)
    db.init_db()
    for jid in ("a", "b"):
        job = db.get_job(jid)
        assert job["status"] == "failed"
        assert job["error"] == "interrupted by restart"
    assert db.get_job("c")["status"] == "done"
    assert db.get_job("c")["error"] is None
    r = client.post("/api/jobs", json=BODY)
    assert r.status_code == 202
    assert r.json()["status"] == "pending"
    assert r.json()["job_id"] not in ("a", "b", "c")
    assert len(ran) == 1
