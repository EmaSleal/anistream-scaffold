"""Domain logic for AV1 → H.264 HLS transcoding with disk-based LRU cache.

NOTE: Transcoding is CPU-bound and blocks a gunicorn sync worker for the full
duration (potentially minutes). This is acceptable for the current traffic
volume. If concurrency becomes an issue, switch to async workers (gevent/eventlet)
or offload to a dedicated task queue (Celery + Redis).
"""

import logging
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Literal, TypedDict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration — all overridable via environment variables
# ---------------------------------------------------------------------------

CACHE_DIR = Path(os.environ.get("TRANSCODE_CACHE_DIR", "/cache/videos"))
MAX_CACHE_SIZE_GB = float(os.environ.get("TRANSCODE_MAX_CACHE_GB", "20"))
FFMPEG_TIMEOUT_SEC = int(os.environ.get("TRANSCODE_FFMPEG_TIMEOUT", "3600"))  # 1 hour

# Progressive transcode configuration
PROGRESSIVE_ENABLED = os.environ.get("TRANSCODE_PROGRESSIVE", "0") == "1"
TRANSCODE_MIN_SEGMENTS = int(os.environ.get("TRANSCODE_MIN_SEGMENTS", "4"))
TRANSCODE_BATCH_SIZE = int(os.environ.get("TRANSCODE_BATCH_SIZE", "20"))

# Ensure cache directory exists at import time so the app never races on mkdir
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Per-video-id locking — prevents duplicate concurrent transcode jobs
# ---------------------------------------------------------------------------

_locks: dict[str, threading.Lock] = {}
_locks_mutex = threading.Lock()


def get_lock(video_id: str) -> threading.Lock:
    """Return (creating if needed) the Lock dedicated to video_id."""
    with _locks_mutex:
        if video_id not in _locks:
            _locks[video_id] = threading.Lock()
        return _locks[video_id]


# ---------------------------------------------------------------------------
# Progressive job state — in-memory per-process tracking
# ---------------------------------------------------------------------------

JobStatusValue = Literal["pending", "streaming", "done", "error"]


class JobStatus(TypedDict):
    status: JobStatusValue
    playlist_path: "Path | None"
    segment_count: int


_jobs: dict[str, JobStatus] = {}
_job_events: dict[str, threading.Event] = {}
_jobs_mutex = threading.Lock()


# ---------------------------------------------------------------------------
# CPU capability detection
# ---------------------------------------------------------------------------

def _has_avx2() -> bool:
    """Return True if the host CPU advertises AVX2 support via /proc/cpuinfo."""
    try:
        with open("/proc/cpuinfo", "r") as fh:
            for line in fh:
                if line.startswith("flags") and "avx2" in line:
                    return True
    except OSError:
        pass
    return False


def _choose_preset() -> str:
    """Pick an x264 preset based on AVX2 availability."""
    if _has_avx2():
        return "veryfast"
    logger.warning("[transcode] AVX2 not detected — falling back to ultrafast preset")
    return "ultrafast"


# ---------------------------------------------------------------------------
# FFprobe helper
# ---------------------------------------------------------------------------

def _probe_duration(source_url: str) -> float | None:
    """Return stream duration in seconds via ffprobe, or None on failure."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-protocol_whitelist", "file,http,https,tcp,tls,crypto",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                source_url,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return float(result.stdout.strip())
    except Exception as exc:
        logger.warning("[transcode] ffprobe failed: %s", exc)
    return None


# ---------------------------------------------------------------------------
# Public cache helpers
# ---------------------------------------------------------------------------

def get_cache_path(video_id: str) -> Path | None:
    """Return Path to the cached playlist.m3u8 if the cache entry is complete."""
    playlist = CACHE_DIR / video_id / "playlist.m3u8"
    if playlist.is_file():
        return playlist
    return None


def update_last_accessed(video_id: str) -> None:
    """Touch a .accessed sentinel file to record LRU timestamp for video_id."""
    accessed_file = CACHE_DIR / video_id / ".accessed"
    try:
        accessed_file.touch()
    except OSError as exc:
        logger.warning("[transcode] could not update .accessed for %s: %s", video_id, exc)


# ---------------------------------------------------------------------------
# LRU cache eviction
# ---------------------------------------------------------------------------

def _cache_size_gb() -> float:
    """Return current total size of CACHE_DIR in gigabytes."""
    total = 0
    for dirpath, _dirnames, filenames in os.walk(CACHE_DIR):
        for fname in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, fname))
            except OSError:
                pass
    return total / (1024 ** 3)


def _purge_lru() -> None:
    """Evict the least-recently-accessed video dirs until under MAX_CACHE_SIZE_GB."""
    while _cache_size_gb() > MAX_CACHE_SIZE_GB:
        # Collect all video_id directories that have a completed playlist
        candidates: list[tuple[float, Path]] = []
        try:
            for entry in CACHE_DIR.iterdir():
                if not entry.is_dir():
                    continue
                accessed_file = entry / ".accessed"
                if accessed_file.exists():
                    mtime = accessed_file.stat().st_mtime
                else:
                    # Fall back to directory mtime when sentinel is absent
                    mtime = entry.stat().st_mtime
                candidates.append((mtime, entry))
        except OSError as exc:
            logger.warning("[transcode] purge scan error: %s", exc)
            break

        if not candidates:
            break

        # Oldest access first
        candidates.sort(key=lambda t: t[0])
        oldest_path = candidates[0][1]
        logger.warning("[transcode] purging LRU entry: %s", oldest_path.name)
        shutil.rmtree(oldest_path, ignore_errors=True)


def purge_lru_if_needed() -> None:
    """Non-blocking: spawn a daemon thread that runs LRU eviction if cache is over budget."""
    if _cache_size_gb() <= MAX_CACHE_SIZE_GB:
        return
    thread = threading.Thread(target=_purge_lru, daemon=True, name="transcode-purge")
    thread.start()


# ---------------------------------------------------------------------------
# Segment download helpers
# ---------------------------------------------------------------------------

def _fetch_source_playlist(source_url: str) -> tuple[list[str], list[str], str | None]:
    """Fetch the source m3u8 and parse it into header lines, segment URLs, and init URL.

    Returns (header_lines, segment_urls, init_url_or_none).
    header_lines includes all #EXT* tags except segment-specific EXTINF lines.
    segment_urls is an ordered list of absolute segment URLs.
    init_url_or_none is the absolute URL of the init segment (#EXT-X-MAP), if present.
    """
    import re
    import requests as req
    from urllib.parse import urljoin

    resp = req.get(source_url, timeout=30)
    resp.raise_for_status()

    header_lines: list[str] = []
    segment_urls: list[str] = []
    init_url: str | None = None
    pending_extinf: str | None = None

    for line in resp.text.splitlines():
        stripped = line.strip()

        if stripped.startswith("#EXT-X-MAP:"):
            uri_match = re.search(r'URI="([^"]+)"', stripped)
            if uri_match:
                uri = uri_match.group(1)
                init_url = uri if uri.startswith("http") else urljoin(source_url, uri)
            header_lines.append(line)

        elif stripped.startswith("#EXTINF:"):
            pending_extinf = line

        elif stripped and not stripped.startswith("#"):
            abs_url = stripped if stripped.startswith("http") else urljoin(source_url, stripped)
            segment_urls.append(abs_url)
            if pending_extinf is not None:
                pending_extinf = None

        else:
            if stripped and not stripped.startswith("#EXTINF"):
                header_lines.append(line)

    return header_lines, segment_urls, init_url


def _download_init_segment(init_url: str, work_dir: Path) -> None:
    """Download the #EXT-X-MAP init segment to work_dir/init.m4s."""
    import requests as req

    if (work_dir / "init.m4s").exists():
        return
    r = req.get(init_url, timeout=60)
    r.raise_for_status()
    (work_dir / "init.m4s").write_bytes(r.content)


def _download_segment_batch(
    segment_urls: list[str],
    work_dir: Path,
    start_idx: int,
) -> list[str]:
    """Download a batch of segments to work_dir, starting numbering at start_idx.

    Returns the list of local filenames in order.
    """
    import requests as req

    local_names: list[str] = []
    for i, url in enumerate(segment_urls):
        global_idx = start_idx + i
        local_name = f"seg{global_idx:04d}.m4s"
        logger.warning("[transcode] downloading segment %d → %s", global_idx, local_name)
        r = req.get(url, timeout=120)
        r.raise_for_status()
        (work_dir / local_name).write_bytes(r.content)
        local_names.append(local_name)
    return local_names


def _build_batch_m3u8(
    work_dir: Path,
    local_names: list[str],
    extinf_duration: float = 6.0,
    batch_idx: int = 0,
) -> Path:
    """Write a local m3u8 for a single batch that FFmpeg can read.

    The batch m3u8 includes the init segment and the batch's .m4s files.
    """
    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:6",
        f"#EXT-X-TARGETDURATION:{int(extinf_duration)}",
        '#EXT-X-MAP:URI="init.m4s"',
    ]
    for name in local_names:
        lines.append(f"#EXTINF:{extinf_duration:.3f},")
        lines.append(name)
    lines.append("#EXT-X-ENDLIST")

    batch_m3u8 = work_dir / f"batch_{batch_idx:03d}.m3u8"
    batch_m3u8.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return batch_m3u8


def _download_segments_locally(source_url: str, work_dir: Path) -> Path:
    """Download m3u8 playlist and all segments to work_dir with .m4s extensions.

    Returns the path to a rewritten local m3u8 that references local files.
    FFmpeg reads only local files, bypassing any HTTP extension restrictions.
    """
    import re
    import requests as req
    from urllib.parse import urljoin

    resp = req.get(source_url, timeout=30)
    resp.raise_for_status()

    seg_index = 0
    new_lines: list[str] = []

    for line in resp.text.splitlines():
        stripped = line.strip()

        if stripped.startswith("#EXT-X-MAP:"):
            uri_match = re.search(r'URI="([^"]+)"', stripped)
            if uri_match:
                uri = uri_match.group(1)
                abs_url = uri if uri.startswith("http") else urljoin(source_url, uri)
                local_name = "init.m4s"
                r = req.get(abs_url, timeout=60)
                r.raise_for_status()
                (work_dir / local_name).write_bytes(r.content)
                new_lines.append(stripped.replace(f'URI="{uri}"', f'URI="{local_name}"'))
            else:
                new_lines.append(line)

        elif stripped and not stripped.startswith("#"):
            abs_url = stripped if stripped.startswith("http") else urljoin(source_url, stripped)
            local_name = f"seg{seg_index:04d}.m4s"
            logger.warning("[transcode] segment %d → %s", seg_index, local_name)
            r = req.get(abs_url, timeout=120)
            r.raise_for_status()
            (work_dir / local_name).write_bytes(r.content)
            new_lines.append(local_name)
            seg_index += 1

        else:
            new_lines.append(line)

    local_m3u8 = work_dir / "source.m3u8"
    local_m3u8.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    logger.warning("[transcode] downloaded %d segments to %s", seg_index, work_dir)
    return local_m3u8


# ---------------------------------------------------------------------------
# Progressive HLS playlist writer
# ---------------------------------------------------------------------------

_TARGET_DURATION = 6  # seconds, matches -hls_time value


def _write_event_playlist(
    output_dir: Path,
    ts_filenames: list[str],
    finalize: bool = False,
) -> None:
    """Atomically write (or overwrite) playlist.m3u8 in output_dir.

    When finalize=False the playlist type is EVENT (open-ended).
    When finalize=True the type is upgraded to VOD and #EXT-X-ENDLIST is appended.
    """
    playlist_type = "VOD" if finalize else "EVENT"
    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        f"#EXT-X-TARGETDURATION:{_TARGET_DURATION}",
        f"#EXT-X-PLAYLIST-TYPE:{playlist_type}",
    ]
    for fname in ts_filenames:
        lines.append(f"#EXTINF:{_TARGET_DURATION}.000,")
        lines.append(fname)
    if finalize:
        lines.append("#EXT-X-ENDLIST")

    content = "\n".join(lines) + "\n"
    tmp_path = output_dir / "playlist.m3u8.tmp"
    tmp_path.write_text(content, encoding="utf-8")
    # os.replace is atomic on POSIX and replaces the destination on Windows
    # (unlike os.rename which raises FileExistsError on Windows when dst exists)
    os.replace(tmp_path, output_dir / "playlist.m3u8")


def _count_output_segments(output_dir: Path) -> int:
    """Count .ts segment files currently present in output_dir."""
    return len(list(output_dir.glob("seg*.ts")))


def _run_ffmpeg_batch(
    batch_m3u8: Path,
    output_dir: Path,
    tmp_dir: Path,
    batch_idx: int,
    global_seg_offset: int,
    preset: str,
) -> list[str]:
    """Run FFmpeg on a single batch m3u8 and move output .ts files to output_dir.

    Returns the list of .ts filenames (relative to output_dir) produced.
    Raises RuntimeError on FFmpeg failure.
    """
    batch_playlist_tmp = tmp_dir / f"batch_{batch_idx:03d}_out.m3u8"
    seg_pattern = str(tmp_dir / f"seg%03d_b{batch_idx:03d}.ts")

    cmd = [
        "ffmpeg", "-y",
        "-protocol_whitelist", "file",
        "-i", str(batch_m3u8),
        "-pix_fmt", "yuv420p",
        "-c:v", "libx264", "-profile:v", "main", "-level", "4.1", "-preset", preset,
        "-c:a", "aac", "-b:a", "128k",
        "-hls_time", str(_TARGET_DURATION),
        "-hls_segment_filename", seg_pattern,
        "-start_number", str(global_seg_offset),
        str(batch_playlist_tmp),
    ]

    try:
        subprocess.run(
            cmd,
            check=True,
            timeout=FFMPEG_TIMEOUT_SEC,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as exc:
        stderr_tail = (exc.stderr or b"")[-2000:].decode("utf-8", errors="replace")
        raise RuntimeError(
            f"FFmpeg batch {batch_idx} failed (exit {exc.returncode}): {stderr_tail}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"FFmpeg batch {batch_idx} timed out") from exc

    # Move produced .ts files into output_dir with stable global names
    produced: list[str] = []
    seg_num = global_seg_offset
    for ts_file in sorted(tmp_dir.glob(f"seg*_b{batch_idx:03d}.ts")):
        dest_name = f"seg{seg_num:03d}.ts"
        dest = output_dir / dest_name
        os.rename(ts_file, dest)
        produced.append(dest_name)
        seg_num += 1

    # Clean up batch m3u8 produced by FFmpeg
    batch_playlist_tmp.unlink(missing_ok=True)
    return produced


# ---------------------------------------------------------------------------
# Progressive transcode engine
# ---------------------------------------------------------------------------

def _progressive_producer(
    video_id: str,
    source_url: str,
    output_dir: Path,
    tmp_dir: Path,
    sentinel: Path,
    ready_event: threading.Event,
) -> None:
    """Background producer: downloads + transcodes in batches, updates EVENT playlist.

    Signals ready_event once >= TRANSCODE_MIN_SEGMENTS output segments exist.
    On any FFmpeg failure falls back to transcode_and_cache().
    """
    try:
        logger.warning("[progressive] video_id=%s producer started", video_id)

        preset = _choose_preset()
        _, segment_urls, init_url = _fetch_source_playlist(source_url)

        if init_url:
            _download_init_segment(init_url, tmp_dir)

        all_ts: list[str] = []
        total_segs = len(segment_urls)
        batch_size = TRANSCODE_BATCH_SIZE
        global_seg_offset = 0
        batch_idx = 0

        for batch_start in range(0, total_segs, batch_size):
            batch_urls = segment_urls[batch_start: batch_start + batch_size]
            is_last_batch = (batch_start + batch_size) >= total_segs

            # Download this batch
            local_names = _download_segment_batch(batch_urls, tmp_dir, start_idx=global_seg_offset)

            # Copy init.m4s into tmp_dir if not already there (needed for batch m3u8)
            batch_m3u8 = _build_batch_m3u8(
                tmp_dir,
                local_names,
                extinf_duration=float(_TARGET_DURATION),
                batch_idx=batch_idx,
            )

            # Transcode this batch
            try:
                produced_ts = _run_ffmpeg_batch(
                    batch_m3u8,
                    output_dir,
                    tmp_dir,
                    batch_idx,
                    global_seg_offset,
                    preset,
                )
            except RuntimeError as exc:
                logger.warning("[progressive] video_id=%s batch %d failed: %s — falling back", video_id, batch_idx, exc)
                _progressive_fallback(video_id, source_url, output_dir, ready_event)
                return

            all_ts.extend(produced_ts)
            global_seg_offset += len(produced_ts)
            batch_idx += 1

            # Update playlist atomically
            _write_event_playlist(output_dir, all_ts, finalize=is_last_batch)

            # Signal waiting callers once MIN_SEGMENTS are ready
            if not ready_event.is_set() and len(all_ts) >= TRANSCODE_MIN_SEGMENTS:
                with _jobs_mutex:
                    job = _jobs.get(video_id)
                    if job is not None:
                        job["segment_count"] = len(all_ts)
                ready_event.set()

            # Keep segment count current even after signalling
            with _jobs_mutex:
                job = _jobs.get(video_id)
                if job is not None:
                    job["segment_count"] = len(all_ts)

        # All batches done
        with _jobs_mutex:
            job = _jobs.get(video_id)
            if job is not None:
                job["status"] = "done"
                job["playlist_path"] = output_dir / "playlist.m3u8"
                job["segment_count"] = len(all_ts)

        # Signal if we never hit MIN_SEGMENTS threshold (very short video)
        if not ready_event.is_set():
            ready_event.set()

        logger.warning("[progressive] video_id=%s done (%d segments)", video_id, len(all_ts))

    except Exception as exc:
        logger.warning("[progressive] video_id=%s unexpected error: %s — falling back", video_id, exc)
        _progressive_fallback(video_id, source_url, output_dir, ready_event)

    finally:
        sentinel.unlink(missing_ok=True)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _progressive_fallback(
    video_id: str,
    source_url: str,
    output_dir: Path,
    ready_event: threading.Event,
) -> None:
    """On progressive failure: run full transcode_and_cache as fallback."""
    with _jobs_mutex:
        job = _jobs.get(video_id)
        if job is not None:
            job["status"] = "error"

    logger.warning("[progressive] video_id=%s starting full-transcode fallback", video_id)
    try:
        playlist = transcode_and_cache(video_id, source_url)
        with _jobs_mutex:
            job = _jobs.get(video_id)
            if job is not None:
                job["status"] = "done"
                job["playlist_path"] = playlist
    except Exception as exc:
        logger.warning("[progressive] video_id=%s fallback also failed: %s", video_id, exc)
    finally:
        if not ready_event.is_set():
            ready_event.set()


def transcode_progressive(video_id: str, source_url: str) -> Path:
    """Start (or join) a progressive transcode job for video_id.

    NON-BLOCKING — returns immediately with the output_dir path regardless of
    whether segments are ready yet.  The caller (route) must check readiness by
    counting .ts files on disk and return HTTP 202 until enough are present.

    Thread/process safety:
    - Single process: in-memory _jobs dict prevents duplicate producers.
    - Multiple gunicorn workers: if the .streaming sentinel exists but video_id
      is not in _jobs (another worker owns the producer), return the path and let
      the route poll — do NOT call transcode_and_cache() which would block.
    """
    output_dir = CACHE_DIR / video_id

    # Fast path: already fully cached (VOD playlist)
    cached = get_cache_path(video_id)
    if cached is not None:
        return cached

    sentinel = output_dir / ".streaming"

    # Cross-worker: sentinel exists but this worker has no producer.
    # Distinguish between a live producer in another worker (has output segments)
    # and a stale sentinel left by a worker killed before its producer could clean up.
    if sentinel.exists() and video_id not in _jobs:
        seg_count = len(list(output_dir.glob("seg*.ts"))) if output_dir.exists() else 0
        if seg_count > 0:
            # Another worker is actively producing — poll for readiness.
            logger.warning(
                "[progressive] video_id=%s sentinel from another worker (%d segs) — polling",
                video_id, seg_count,
            )
            output_dir.mkdir(parents=True, exist_ok=True)
            return output_dir / "playlist.m3u8"

        # No segments yet and no in-memory job → stale sentinel from a killed worker.
        # Clean up and restart the producer in this worker.
        logger.warning(
            "[progressive] video_id=%s stale sentinel (0 segs, no job) — clearing and restarting",
            video_id,
        )
        sentinel.unlink(missing_ok=True)
        stale_tmp = CACHE_DIR / f"{video_id}_prog_tmp"
        shutil.rmtree(stale_tmp, ignore_errors=True)
        # Fall through to the new-job path below.

    with _jobs_mutex:
        existing_job = _jobs.get(video_id)

        if existing_job is not None:
            # Job already tracked by this worker — return path, route will poll.
            playlist = existing_job.get("playlist_path")
            return playlist if playlist is not None else output_dir / "playlist.m3u8"

        # New job: create output dir, sentinel, and start producer thread.
        output_dir.mkdir(parents=True, exist_ok=True)
        tmp_dir = CACHE_DIR / f"{video_id}_prog_tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        sentinel.touch()

        ready_event = threading.Event()
        _job_events[video_id] = ready_event
        _jobs[video_id] = JobStatus(status="streaming", playlist_path=None, segment_count=0)

    thread = threading.Thread(
        target=_progressive_producer,
        args=(video_id, source_url, output_dir, tmp_dir, sentinel, ready_event),
        daemon=True,
        name=f"prog-{video_id}",
    )
    thread.start()

    # Return immediately — the route polls for readiness via HTTP 202/200.
    return output_dir / "playlist.m3u8"


# ---------------------------------------------------------------------------
# Core transcoding
# ---------------------------------------------------------------------------

def transcode_and_cache(video_id: str, source_url: str) -> Path:
    """Transcode source_url → H.264 HLS, cache to disk, return cached playlist path.

    Thread-safe: concurrent requests for the same video_id wait on a per-id
    lock so only one FFmpeg process runs per video_id at a time.
    """
    lock = get_lock(video_id)
    with lock:
        # Re-check cache inside the lock — a concurrent request may have
        # finished transcoding while we were waiting.
        cached = get_cache_path(video_id)
        if cached is not None:
            logger.warning("[transcode] video_id=%s already cached (waited on lock)", video_id)
            return cached

        preset = _choose_preset()
        tmp_dir = CACHE_DIR / f"{video_id}_tmp"
        final_dir = CACHE_DIR / video_id

        duration = _probe_duration(source_url)
        duration_label = f"{duration:.1f}s" if duration is not None else "unknown"

        logger.warning(
            "[transcode] video_id=%s started  preset=%s  source_duration=%s",
            video_id, preset, duration_label,
        )

        tmp_dir.mkdir(parents=True, exist_ok=True)
        start_ts = time.monotonic()

        try:
            # Download all segments locally to avoid FFmpeg's HTTP extension checks
            dl_dir = tmp_dir / "dl"
            dl_dir.mkdir()
            local_m3u8 = _download_segments_locally(source_url, dl_dir)
        except Exception as exc:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            logger.warning("[transcode] video_id=%s segment download failed: %s", video_id, exc)
            raise RuntimeError(f"Segment download failed for {video_id}") from exc

        cmd = [
            "ffmpeg",
            "-protocol_whitelist", "file",
            "-i", str(local_m3u8),
            "-pix_fmt", "yuv420p",
            "-c:v", "libx264",
            "-profile:v", "main",
            "-level", "4.1",
            "-preset", preset,
            "-c:a", "aac",
            "-b:a", "128k",
            "-hls_time", "6",
            "-hls_playlist_type", "vod",
            "-hls_segment_filename", str(tmp_dir / "seg%03d.ts"),
            str(tmp_dir / "playlist.m3u8"),
        ]

        try:
            subprocess.run(
                cmd,
                check=True,
                timeout=FFMPEG_TIMEOUT_SEC,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except subprocess.CalledProcessError as exc:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            stderr_tail = (exc.stderr or b"")[-2000:].decode("utf-8", errors="replace")
            logger.warning(
                "[transcode] video_id=%s FFmpeg failed (exit %d): %s",
                video_id, exc.returncode, stderr_tail,
            )
            raise RuntimeError(f"FFmpeg transcoding failed for {video_id}") from exc
        except subprocess.TimeoutExpired:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            logger.warning("[transcode] video_id=%s timed out after %ds", video_id, FFMPEG_TIMEOUT_SEC)
            raise RuntimeError(f"FFmpeg timed out for {video_id}")

        # Atomic promotion: rename tmp → final so a partial cache is never served
        if final_dir.exists():
            shutil.rmtree(final_dir, ignore_errors=True)
        os.rename(tmp_dir, final_dir)

        elapsed = time.monotonic() - start_ts
        logger.warning(
            "[transcode] video_id=%s done in %.1fs (video duration: %s)",
            video_id, elapsed, duration_label,
        )

        playlist = final_dir / "playlist.m3u8"
        return playlist
