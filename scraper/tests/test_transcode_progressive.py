"""Tests for the progressive HLS transcode engine.

Covers:
  - EVENT playlist written after first batch (4.3)
  - VOD upgrade after final batch (4.3)
  - Atomic rewrite — incomplete batches never appear in playlist (4.4)
  - Job state transitions: pending→streaming→done and streaming→error→done (4.5)
  - Flask test client — 202 with < MIN_SEGMENTS; 200 EVENT playlist with >= (4.6)
  - Duplicate-request guard — second request while .streaming exists does NOT
    spawn a second FFmpeg process (4.7)
"""
import os
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("INTERNAL_JWT_SECRET", "test-internal-secret-for-tests-only")
os.environ.setdefault("SERVICE_SECRET", "test-service-secret-for-tests-only")
os.environ.setdefault("TRANSCODE_PROGRESSIVE", "1")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ts_files(directory: Path, count: int) -> list[str]:
    """Create stub .ts files in directory and return their names."""
    names = []
    for i in range(count):
        name = f"seg{i:03d}.ts"
        (directory / name).write_bytes(b"\x00" * 10)
        names.append(name)
    return names


def _read_playlist(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 4.3 — EVENT playlist after batch 1; VOD upgrade after final batch
# ---------------------------------------------------------------------------

class TestWriteEventPlaylist:

    def test_event_playlist_written_after_first_batch(self, tmp_path):
        import domain.transcode as tc

        ts_names = _make_ts_files(tmp_path, 3)
        tc._write_event_playlist(tmp_path, ts_names, finalize=False)

        content = _read_playlist(tmp_path / "playlist.m3u8")
        assert "#EXT-X-PLAYLIST-TYPE:EVENT" in content
        assert "#EXT-X-ENDLIST" not in content

    def test_event_playlist_contains_all_segment_names(self, tmp_path):
        import domain.transcode as tc

        ts_names = _make_ts_files(tmp_path, 2)
        tc._write_event_playlist(tmp_path, ts_names, finalize=False)

        content = _read_playlist(tmp_path / "playlist.m3u8")
        for name in ts_names:
            assert name in content

    def test_vod_upgrade_after_final_batch(self, tmp_path):
        import domain.transcode as tc

        ts_names = _make_ts_files(tmp_path, 4)
        tc._write_event_playlist(tmp_path, ts_names, finalize=True)

        content = _read_playlist(tmp_path / "playlist.m3u8")
        assert "#EXT-X-PLAYLIST-TYPE:VOD" in content
        assert "#EXT-X-ENDLIST" in content

    def test_vod_playlist_ends_with_endlist(self, tmp_path):
        import domain.transcode as tc

        ts_names = _make_ts_files(tmp_path, 4)
        tc._write_event_playlist(tmp_path, ts_names, finalize=True)

        content = _read_playlist(tmp_path / "playlist.m3u8")
        # #EXT-X-ENDLIST must be the final non-empty line
        non_empty = [line for line in content.splitlines() if line.strip()]
        assert non_empty[-1] == "#EXT-X-ENDLIST"


# ---------------------------------------------------------------------------
# 4.4 — Atomic rewrite: tmp file is renamed; no half-written segments in playlist
# ---------------------------------------------------------------------------

class TestAtomicRewrite:

    def test_write_goes_through_tmp_file(self, tmp_path):
        """_write_event_playlist writes to .tmp then atomically replaces final."""
        import domain.transcode as tc

        replace_calls = []
        original_replace = os.replace

        def capturing_replace(src, dst):
            replace_calls.append((str(src), str(dst)))
            original_replace(src, dst)

        ts_names = _make_ts_files(tmp_path, 2)

        with patch("domain.transcode.os.replace", side_effect=capturing_replace):
            tc._write_event_playlist(tmp_path, ts_names, finalize=False)

        assert len(replace_calls) == 1
        src, dst = replace_calls[0]
        assert src.endswith("playlist.m3u8.tmp")
        assert dst.endswith("playlist.m3u8")

    def test_playlist_never_references_segments_not_yet_renamed(self, tmp_path):
        """A batch of segments is fully written before the playlist is updated."""
        import domain.transcode as tc

        # Simulate 2 batches — only first batch present in playlist between writes
        first_batch = _make_ts_files(tmp_path, 2)
        tc._write_event_playlist(tmp_path, first_batch, finalize=False)

        content_after_batch1 = _read_playlist(tmp_path / "playlist.m3u8")
        # seg002 (from second batch) must NOT appear yet
        assert "seg002.ts" not in content_after_batch1

        second_batch_name = f"seg{2:03d}.ts"
        (tmp_path / second_batch_name).write_bytes(b"\x00")
        tc._write_event_playlist(tmp_path, first_batch + [second_batch_name], finalize=True)

        content_after_batch2 = _read_playlist(tmp_path / "playlist.m3u8")
        assert "seg002.ts" in content_after_batch2


# ---------------------------------------------------------------------------
# 4.5 — Job state transitions
# ---------------------------------------------------------------------------

class TestJobStateTransitions:

    def _clear_jobs(self):
        import domain.transcode as tc
        with tc._jobs_mutex:
            tc._jobs.clear()
            tc._job_events.clear()

    def test_pending_to_streaming_to_done(self, tmp_path):
        """State goes pending → streaming → done on a successful run."""
        import domain.transcode as tc

        self._clear_jobs()

        source_url = "http://example.com/source.m3u8"
        video_id = "test_state_success"
        output_dir = tmp_path / video_id
        output_dir.mkdir()
        tmp_dir = tmp_path / f"{video_id}_tmp"
        tmp_dir.mkdir()
        sentinel = output_dir / ".streaming"
        sentinel.touch()
        ready_event = threading.Event()

        with tc._jobs_mutex:
            tc._jobs[video_id] = tc.JobStatus(status="pending", playlist_path=None, segment_count=0)
            tc._jobs[video_id]["status"] = "streaming"
            tc._job_events[video_id] = ready_event

        # Mock _fetch_source_playlist to return 2 URLs
        fake_segs = ["http://example.com/seg0.m4s", "http://example.com/seg1.m4s"]

        def fake_fetch(url):
            return ([], fake_segs, "http://example.com/init.m4s")

        def fake_download_init(url, work_dir):
            (work_dir / "init.m4s").write_bytes(b"\x00")

        def fake_download_batch(urls, work_dir, start_idx):
            names = []
            for i, _ in enumerate(urls):
                name = f"seg{start_idx + i:04d}.m4s"
                (work_dir / name).write_bytes(b"\x00")
                names.append(name)
            return names

        def fake_build_m3u8(work_dir, local_names, extinf_duration=6.0, batch_idx=0):
            p = work_dir / f"batch_{batch_idx:03d}.m3u8"
            p.write_text("#EXTM3U\n", encoding="utf-8")
            return p

        def fake_run_ffmpeg(batch_m3u8, output_dir, tmp_dir, batch_idx, global_seg_offset, preset):
            # Produce one .ts file
            name = f"seg{global_seg_offset:03d}.ts"
            (output_dir / name).write_bytes(b"\x00")
            return [name]

        with patch("domain.transcode._fetch_source_playlist", side_effect=fake_fetch), \
             patch("domain.transcode._download_init_segment", side_effect=fake_download_init), \
             patch("domain.transcode._download_segment_batch", side_effect=fake_download_batch), \
             patch("domain.transcode._build_batch_m3u8", side_effect=fake_build_m3u8), \
             patch("domain.transcode._run_ffmpeg_batch", side_effect=fake_run_ffmpeg), \
             patch("domain.transcode.TRANSCODE_MIN_SEGMENTS", 1), \
             patch("domain.transcode.TRANSCODE_BATCH_SIZE", 2):

            tc._progressive_producer(
                video_id, source_url, output_dir, tmp_dir, sentinel, ready_event
            )

        with tc._jobs_mutex:
            final_status = tc._jobs[video_id]["status"]

        assert final_status == "done"
        assert ready_event.is_set()

    def test_streaming_to_error_to_done_on_ffmpeg_failure(self, tmp_path):
        """When FFmpeg fails, state goes streaming → error → done (fallback)."""
        import domain.transcode as tc

        self._clear_jobs()

        source_url = "http://example.com/source.m3u8"
        video_id = "test_state_error"
        output_dir = tmp_path / video_id
        output_dir.mkdir()
        tmp_dir = tmp_path / f"{video_id}_tmp"
        tmp_dir.mkdir()
        sentinel = output_dir / ".streaming"
        sentinel.touch()
        ready_event = threading.Event()

        with tc._jobs_mutex:
            tc._jobs[video_id] = tc.JobStatus(status="streaming", playlist_path=None, segment_count=0)
            tc._job_events[video_id] = ready_event

        fake_segs = ["http://example.com/seg0.m4s"]

        def fake_fetch(url):
            return ([], fake_segs, None)

        def fake_download_batch(urls, work_dir, start_idx):
            return [f"seg{start_idx:04d}.m4s"]

        def fake_build_m3u8(work_dir, local_names, extinf_duration=6.0, batch_idx=0):
            p = work_dir / f"batch_{batch_idx:03d}.m3u8"
            p.write_text("#EXTM3U\n", encoding="utf-8")
            return p

        def failing_ffmpeg(batch_m3u8, output_dir, tmp_dir, batch_idx, global_seg_offset, preset):
            raise RuntimeError("FFmpeg batch 0 failed (exit 1)")

        fallback_playlist = output_dir / "playlist.m3u8"
        fallback_playlist.write_text("#EXTM3U\n#EXT-X-ENDLIST\n", encoding="utf-8")

        with patch("domain.transcode._fetch_source_playlist", side_effect=fake_fetch), \
             patch("domain.transcode._download_init_segment"), \
             patch("domain.transcode._download_segment_batch", side_effect=fake_download_batch), \
             patch("domain.transcode._build_batch_m3u8", side_effect=fake_build_m3u8), \
             patch("domain.transcode._run_ffmpeg_batch", side_effect=failing_ffmpeg), \
             patch("domain.transcode.transcode_and_cache", return_value=fallback_playlist) as mock_fallback, \
             patch("domain.transcode.TRANSCODE_BATCH_SIZE", 1):

            tc._progressive_producer(
                video_id, source_url, output_dir, tmp_dir, sentinel, ready_event
            )

        mock_fallback.assert_called_once_with(video_id, source_url)
        assert ready_event.is_set()

        with tc._jobs_mutex:
            final_status = tc._jobs[video_id]["status"]

        assert final_status == "done"


# ---------------------------------------------------------------------------
# 4.6 — Flask test client: 202 with < MIN_SEGMENTS; 200 EVENT with >= MIN_SEGMENTS
# ---------------------------------------------------------------------------

@pytest.fixture
def flask_client():
    with patch("storage.get_client"):
        from app import create_app
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c


class TestProgressivePlaylistEndpoint:

    def _clear_jobs(self):
        import domain.transcode as tc
        with tc._jobs_mutex:
            tc._jobs.clear()
            tc._job_events.clear()

    def test_202_when_fewer_than_min_segments_ready(self, flask_client, tmp_path):
        """Endpoint returns 202 when progressive job has < MIN_SEGMENTS segments."""
        import domain.transcode as tc

        self._clear_jobs()

        video_id = "vid_202_test"
        # Simulate a job in 'streaming' state with 0 segments
        ready_event = threading.Event()
        ready_event.set()  # Don't block the mock
        with tc._jobs_mutex:
            tc._jobs[video_id] = tc.JobStatus(status="streaming", playlist_path=None, segment_count=0)
            tc._job_events[video_id] = ready_event

        fake_playlist = tmp_path / "playlist.m3u8"
        fake_playlist.write_text("#EXTM3U\n#EXT-X-PLAYLIST-TYPE:EVENT\n", encoding="utf-8")

        # Patch at both module levels: domain.transcode (for constant reads)
        # and routes.transcode_routes (for the imported reference)
        with patch("routes.transcode_routes.PROGRESSIVE_ENABLED", True), \
             patch("routes.transcode_routes.TRANSCODE_MIN_SEGMENTS", 4), \
             patch("routes.transcode_routes.get_cache_path", return_value=None), \
             patch("routes.transcode_routes.transcode_progressive", return_value=fake_playlist), \
             patch("routes.transcode_routes._jobs", tc._jobs), \
             patch("routes.transcode_routes._jobs_mutex", tc._jobs_mutex):

            resp = flask_client.get(
                f"/api/proxy/transcode/{video_id}/playlist.m3u8?src=http://example.com/s.m3u8"
            )

        assert resp.status_code == 202

    def test_200_event_playlist_when_min_segments_ready(self, flask_client, tmp_path):
        """Endpoint returns 200 EVENT playlist when >= MIN_SEGMENTS are ready."""
        import domain.transcode as tc

        self._clear_jobs()

        video_id = "vid_200_test"
        ready_event = threading.Event()
        ready_event.set()
        with tc._jobs_mutex:
            tc._jobs[video_id] = tc.JobStatus(status="streaming", playlist_path=None, segment_count=4)
            tc._job_events[video_id] = ready_event

        fake_playlist = tmp_path / "playlist.m3u8"
        fake_playlist.write_text(
            "#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:6\n"
            "#EXT-X-PLAYLIST-TYPE:EVENT\n"
            "#EXTINF:6.000,\nseg000.ts\n#EXTINF:6.000,\nseg001.ts\n"
            "#EXTINF:6.000,\nseg002.ts\n#EXTINF:6.000,\nseg003.ts\n",
            encoding="utf-8",
        )

        with patch("routes.transcode_routes.PROGRESSIVE_ENABLED", True), \
             patch("routes.transcode_routes.TRANSCODE_MIN_SEGMENTS", 4), \
             patch("routes.transcode_routes.get_cache_path", return_value=None), \
             patch("routes.transcode_routes.transcode_progressive", return_value=fake_playlist), \
             patch("routes.transcode_routes._jobs", tc._jobs), \
             patch("routes.transcode_routes._jobs_mutex", tc._jobs_mutex), \
             patch("routes.transcode_routes.update_last_accessed"), \
             patch("routes.transcode_routes.purge_lru_if_needed"):

            resp = flask_client.get(
                f"/api/proxy/transcode/{video_id}/playlist.m3u8?src=http://example.com/s.m3u8"
            )

        assert resp.status_code == 200
        body = resp.data.decode()
        assert "#EXT-X-PLAYLIST-TYPE:EVENT" in body

    def test_sentinel_removed_on_completion(self, tmp_path):
        """The .streaming sentinel is removed after the producer finishes."""
        import domain.transcode as tc

        self._clear_jobs()

        video_id = "vid_sentinel_test"
        output_dir = tmp_path / video_id
        output_dir.mkdir()
        tmp_dir = tmp_path / f"{video_id}_tmp"
        tmp_dir.mkdir()
        sentinel = output_dir / ".streaming"
        sentinel.touch()
        ready_event = threading.Event()

        with tc._jobs_mutex:
            tc._jobs[video_id] = tc.JobStatus(status="streaming", playlist_path=None, segment_count=0)
            tc._job_events[video_id] = ready_event

        source_url = "http://example.com/source.m3u8"

        def fake_fetch(url):
            return ([], ["http://example.com/seg0.m4s"], None)

        def fake_download_batch(urls, work_dir, start_idx):
            return [f"seg{start_idx:04d}.m4s"]

        def fake_build_m3u8(work_dir, local_names, extinf_duration=6.0, batch_idx=0):
            p = work_dir / f"batch_{batch_idx:03d}.m3u8"
            p.write_text("#EXTM3U\n", encoding="utf-8")
            return p

        def fake_run_ffmpeg(batch_m3u8, output_dir, tmp_dir, batch_idx, global_seg_offset, preset):
            name = f"seg{global_seg_offset:03d}.ts"
            (output_dir / name).write_bytes(b"\x00")
            return [name]

        with patch("domain.transcode._fetch_source_playlist", side_effect=fake_fetch), \
             patch("domain.transcode._download_init_segment"), \
             patch("domain.transcode._download_segment_batch", side_effect=fake_download_batch), \
             patch("domain.transcode._build_batch_m3u8", side_effect=fake_build_m3u8), \
             patch("domain.transcode._run_ffmpeg_batch", side_effect=fake_run_ffmpeg), \
             patch("domain.transcode.TRANSCODE_MIN_SEGMENTS", 1), \
             patch("domain.transcode.TRANSCODE_BATCH_SIZE", 1):

            tc._progressive_producer(video_id, source_url, output_dir, tmp_dir, sentinel, ready_event)

        assert not sentinel.exists(), "Sentinel must be removed after producer completes"


# ---------------------------------------------------------------------------
# 4.7 — Duplicate-request guard: second request while .streaming exists does NOT
#        spawn a second FFmpeg process
# ---------------------------------------------------------------------------

class TestDuplicateRequestGuard:

    def _clear_jobs(self):
        import domain.transcode as tc
        with tc._jobs_mutex:
            tc._jobs.clear()
            tc._job_events.clear()

    def test_second_request_does_not_spawn_new_ffmpeg(self, tmp_path):
        """If video_id is already in _jobs with status 'streaming', a second call
        to transcode_progressive() must NOT launch a new producer thread."""
        import domain.transcode as tc

        self._clear_jobs()

        video_id = "vid_dedup_test"
        output_dir = tmp_path / video_id
        output_dir.mkdir()
        sentinel = output_dir / ".streaming"
        sentinel.touch()
        ready_event = threading.Event()
        ready_event.set()  # Pretend segments are ready immediately

        # Write a minimal playlist so the function can return a Path
        playlist = output_dir / "playlist.m3u8"
        playlist.write_text(
            "#EXTM3U\n#EXT-X-PLAYLIST-TYPE:EVENT\n#EXTINF:6.000,\nseg000.ts\n",
            encoding="utf-8",
        )

        with tc._jobs_mutex:
            tc._jobs[video_id] = tc.JobStatus(status="streaming", playlist_path=None, segment_count=1)
            tc._job_events[video_id] = ready_event

        ffmpeg_call_count = {"n": 0}

        def counting_ffmpeg(*args, **kwargs):
            ffmpeg_call_count["n"] += 1
            return []

        with patch("domain.transcode.CACHE_DIR", tmp_path), \
             patch("domain.transcode.get_cache_path", return_value=None), \
             patch("domain.transcode._run_ffmpeg_batch", side_effect=counting_ffmpeg):

            # First call: job already exists, should join it
            result = tc.transcode_progressive(video_id, "http://example.com/s.m3u8")

        assert ffmpeg_call_count["n"] == 0, (
            "Second call while .streaming+job exists must NOT spawn a new FFmpeg process"
        )
        assert result == output_dir / "playlist.m3u8"

    def test_cross_worker_sentinel_triggers_fallback(self, tmp_path):
        """If .streaming sentinel exists but video_id NOT in _jobs (other worker),
        transcode_progressive falls back to transcode_and_cache."""
        import domain.transcode as tc

        self._clear_jobs()

        video_id = "vid_cross_worker"
        output_dir = tmp_path / video_id
        output_dir.mkdir()
        sentinel = output_dir / ".streaming"
        sentinel.touch()

        # _jobs does NOT contain video_id → simulates other worker owns the sentinel

        fallback_playlist = output_dir / "playlist.m3u8"
        fallback_playlist.write_text("#EXTM3U\n#EXT-X-ENDLIST\n", encoding="utf-8")

        with patch("domain.transcode.CACHE_DIR", tmp_path), \
             patch("domain.transcode.get_cache_path", return_value=None), \
             patch("domain.transcode.transcode_and_cache", return_value=fallback_playlist) as mock_fallback:

            result = tc.transcode_progressive(video_id, "http://example.com/s.m3u8")

        mock_fallback.assert_called_once_with(video_id, "http://example.com/s.m3u8")
        assert result == fallback_playlist
