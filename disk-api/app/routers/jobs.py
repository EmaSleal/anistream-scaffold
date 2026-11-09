"""
Endpoints para descargas asíncronas por URL.

Flujo:
  POST /api/jobs          → encola el job, devuelve job_id inmediatamente
  GET  /api/jobs/{job_id} → consulta estado (pending/downloading/done/failed)

La descarga corre en asyncio background task para no bloquear Uvicorn.
yt-dlp cubre links directos + YouTube, Google Drive, Mega, y ~1800 sitios.
Para links directos simples (sin plataforma especial) usa httpx para
eficiencia, y cae a yt-dlp si httpx detecta redirección a plataforma conocida.
"""
import asyncio
import glob
import subprocess
import uuid
import mimetypes
from pathlib import Path
from datetime import datetime

import httpx
import yt_dlp
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, HttpUrl

from app.models import db
from app.routers import files as files_mod
from app.routers.files import categorize, jellyfin_episode_target

router = APIRouter()

VALID_CATEGORIES = {"photos", "videos", "documents", "other"}

# Dominios que requieren yt-dlp (links directos van por httpx)
YT_DLP_DOMAINS = {
    "youtube.com", "youtu.be", "drive.google.com", "mega.nz",
    "mega.co.nz", "vimeo.com", "twitch.tv", "dailymotion.com",
    "twitter.com", "x.com", "instagram.com", "tiktok.com",
    "facebook.com", "reddit.com",
}


class DownloadRequest(BaseModel):
    url: HttpUrl
    category: str = "other"
    series_id: str | None = None
    episode_number: int | None = None
    series_title: str | None = None
    series_year: int | None = None
    season_number: int | None = None
    file_episode_number: int | None = None


_ZILLA_DOMAIN = "player.zilla-networks.com"

def _needs_ytdlp(url: str) -> bool:
    """HLS streams and known platforms always go through yt-dlp."""
    from urllib.parse import urlsplit
    parsed = urlsplit(url)
    # Catch both /path/file.m3u8 and /m3u8/<hash> (Zilla-style path)
    if "m3u8" in parsed.path.lower():
        return True
    domain = parsed.netloc.lower().removeprefix("www.")
    return any(domain == d or domain.endswith("." + d) for d in YT_DLP_DOMAINS)


def _ytdlp_extra_opts(url: str) -> dict:
    """Return extra yt-dlp options needed for specific upstream CDNs."""
    from urllib.parse import urlsplit
    domain = urlsplit(url).netloc.lower()
    if _ZILLA_DOMAIN in domain:
        return {"http_headers": {"Referer": "https://animeav1.com/", "Origin": "https://animeav1.com"}}
    return {}


async def _run_download(
    job_id: str,
    url: str,
    category: str,
    series_id: str | None = None,
    episode_number: int | None = None,
    series_title: str | None = None,
    series_year: int | None = None,
    season_number: int | None = None,
    file_episode_number: int | None = None,
):
    """
    Tarea en background. Actualiza el estado del job en SQLite a medida que avanza.
    """
    db.update_job(job_id, status="downloading")

    storage_root = files_mod.STORAGE_ROOT
    jellyfin = jellyfin_episode_target(
        series_id, episode_number, series_title, series_year,
        season_number=season_number, file_episode_number=file_episode_number,
    )
    fixed_stem: str | None = None
    if jellyfin:
        subdir, fixed_stem = jellyfin
    elif series_id and episode_number is not None:
        subdir = storage_root / "videos" / "episodes" / series_id
    else:
        subdir = storage_root / category / datetime.utcnow().strftime("%Y-%m")
    subdir.mkdir(parents=True, exist_ok=True)

    try:
        if _needs_ytdlp(url):
            file_id = await _download_with_ytdlp(job_id, url, category, subdir, series_id, episode_number, _ytdlp_extra_opts(url), fixed_stem)
        else:
            file_id = await _download_direct(job_id, url, category, subdir, series_id, episode_number, fixed_stem)

        db.update_job(job_id, status="done", file_id=file_id)

    except Exception as exc:
        db.update_job(job_id, status="failed", error=str(exc)[:500])


async def _download_direct(
    job_id: str, url: str, category: str, subdir: Path,
    series_id: str | None = None, episode_number: int | None = None,
    fixed_stem: str | None = None,
) -> int:
    """Descarga un link directo con httpx en modo streaming."""
    async with httpx.AsyncClient(follow_redirects=True, timeout=300) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()

            # Nombre del archivo: desde Content-Disposition o la URL
            cd = response.headers.get("content-disposition", "")
            if "filename=" in cd:
                filename = cd.split("filename=")[-1].strip().strip('"\'')
            else:
                filename = Path(str(url).split("?")[0]).name or f"download_{job_id[:8]}"

            content_type = response.headers.get("content-type", "application/octet-stream").split(";")[0]

            if fixed_stem:
                # Jellyfin layout: fixed name, extension from the resolved name/content-type
                ext = Path(filename).suffix or mimetypes.guess_extension(content_type) or ".mp4"
                filename = fixed_stem + ext

            # Recategorizar si el content-type revela algo diferente a lo pedido
            guessed_cat = categorize(filename)
            final_category = guessed_cat if guessed_cat != "other" else category

            dest = _unique_path(subdir, filename)
            with dest.open("wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    f.write(chunk)

    size = dest.stat().st_size
    return db.insert_file(
        filename=filename,
        stored_path=str(dest),
        content_type=content_type,
        size_bytes=size,
        category=final_category,
        series_id=series_id,
        episode_number=episode_number,
    )


async def _download_with_ytdlp(
    job_id: str, url: str, category: str, subdir: Path,
    series_id: str | None = None, episode_number: int | None = None,
    extra_opts: dict | None = None,
    fixed_stem: str | None = None,
) -> int:
    """Descarga usando yt-dlp. Corre en threadpool para no bloquear el event loop."""

    output_path: dict = {}

    def _sync_download():
        from urllib.parse import urlsplit
        is_hls = "m3u8" in urlsplit(url).path.lower()

        if fixed_stem:
            # Escape % so sanitized titles are not read as yt-dlp template fields
            outtmpl = str(subdir / (fixed_stem.replace("%", "%%") + ".%(ext)s"))
        else:
            outtmpl = str(subdir / "%(title)s.%(ext)s")

        if is_hls:
            # HLS streams: download fragments and remux to proper MP4 via ffmpeg.
            # faststart moves moov atom to file start so browsers know duration
            # immediately and can seek without downloading the full file.
            ydl_opts = {
                "outtmpl": outtmpl,
                "format": "best",
                "merge_output_format": "mp4",
                "postprocessor_args": {"ffmpeg": ["-movflags", "faststart"]},
                **(extra_opts or {}),
            }
        else:
            ydl_opts = {
                "outtmpl": outtmpl,
                "quiet": True,
                "no_warnings": True,
                # On ARM without AVX, avoid heavy remuxing
                "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "merge_output_format": "mp4",
                "postprocessors": [],
                **(extra_opts or {}),
            }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            output_path["filename"] = filename
            output_path["title"] = info.get("title", "download")
            output_path["ext"] = info.get("ext", "mp4")

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _sync_download)

    filepath = Path(output_path["filename"])
    if not filepath.exists():
        # yt-dlp puede cambiar la extensión tras el merge — buscar archivo con mismo stem
        matches = list(filepath.parent.glob(f"{glob.escape(filepath.stem)}.*"))
        if not matches:
            raise FileNotFoundError(f"yt-dlp no generó archivo en {subdir}")
        filepath = matches[0]

    # Apply faststart to MP4 files: moves moov atom to the start so browsers
    # know duration immediately and can seek without downloading the full file.
    if filepath.suffix == ".mp4":
        tmp = filepath.with_suffix(".faststart.mp4")
        result = await loop.run_in_executor(None, _run_faststart, filepath, tmp)
        if result.returncode == 0:
            tmp.replace(filepath)
        else:
            tmp.unlink(missing_ok=True)

    filename = filepath.name
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    final_category = categorize(filename) if categorize(filename) != "other" else category

    return db.insert_file(
        filename=filename,
        stored_path=str(filepath),
        content_type=content_type,
        size_bytes=filepath.stat().st_size,
        category=final_category,
        series_id=series_id,
        episode_number=episode_number,
    )


def _run_faststart(src: Path, tmp: Path) -> subprocess.CompletedProcess:
    """Blocking ffmpeg remux; call it through run_in_executor, never on the loop."""
    return subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), "-c", "copy", "-movflags", "faststart", str(tmp)],
        capture_output=True,
    )


def _unique_path(directory: Path, filename: str) -> Path:
    """Evita colisiones de nombre igual que en el router de upload."""
    dest = directory / filename
    if not dest.exists():
        return dest
    stem, suffix = Path(filename).stem, Path(filename).suffix
    return directory / f"{stem}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}{suffix}"


@router.post("/jobs", status_code=202)
async def enqueue_download(request: DownloadRequest,
                           background_tasks: BackgroundTasks):
    """
    Encola una descarga por URL. Devuelve job_id inmediatamente.
    Consultá el estado con GET /api/jobs/{job_id}.
    """
    if request.category not in VALID_CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail=f"Categoría inválida. Opciones: {sorted(VALID_CATEGORIES)}"
        )

    # Idempotency per episode. No await between check and create: with a single
    # uvicorn worker this section is atomic. Reuse cases also answer 202 so
    # clients (Flask polling GET /api/jobs/{id}) need no special handling.
    if request.series_id and request.episode_number is not None:
        active = db.get_active_job_for_episode(
            request.series_id, request.episode_number)
        if active:
            return {
                "job_id": active["id"],
                "status": active["status"],
                "message": "Ya hay una descarga activa para este episodio.",
            }
        existing = db.get_file_by_episode(
            request.series_id, request.episode_number)
        if existing:
            done_id = str(uuid.uuid4())
            db.create_job(
                job_id=done_id,
                url=str(request.url),
                category=request.category,
                series_id=request.series_id,
                episode_number=request.episode_number,
                status="done",
                file_id=existing["id"],
            )
            return {
                "job_id": done_id,
                "status": "done",
                "message": "El episodio ya existe; no se descargó de nuevo.",
            }

    job_id = str(uuid.uuid4())
    db.create_job(
        job_id=job_id,
        url=str(request.url),
        category=request.category,
        series_id=request.series_id,
        episode_number=request.episode_number,
    )
    # Franchise layout fields (ADR-020) are passed only when present.
    layout = {
        k: v for k, v in (
            ("season_number", request.season_number),
            ("file_episode_number", request.file_episode_number),
        ) if v is not None
    }
    background_tasks.add_task(
        _run_download, job_id, str(request.url), request.category,
        request.series_id, request.episode_number,
        request.series_title, request.series_year,
        **layout,
    )

    return {
        "job_id": job_id,
        "status": "pending",
        "message": "Descarga encolada. Consultá el estado en GET /api/jobs/{job_id}",
    }


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """
    Consulta el estado de un job de descarga.

    Estados posibles:
    - pending: encolado, aún no inició
    - downloading: en progreso
    - done: completado, file_id disponible para usar los endpoints de /files
    - failed: error, campo 'error' contiene el detalle
    """
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    return job
