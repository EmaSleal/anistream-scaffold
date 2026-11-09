"""
Endpoints REST para gestión de archivos sobre el pool de MergerFS.
"""
import os
import re
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Form
from fastapi.responses import FileResponse

from app.models import db

router = APIRouter()

# Punto de montaje del pool MergerFS — ajustar si cambia
STORAGE_ROOT = Path(os.environ.get("DISK_STORAGE_ROOT", "/mnt/data_safe/storage"))

# Optional Jellyfin media root (ADR-018). When unset, the legacy
# videos/episodes/<series_id>/ layout under STORAGE_ROOT is used.
MEDIA_ROOT: Path | None = (
    Path(os.environ["DISK_MEDIA_ROOT"]) if os.environ.get("DISK_MEDIA_ROOT") else None
)

_FORBIDDEN_CHARS = re.compile(r'[/\\:*?"<>|\x00-\x1f\x7f]')

CATEGORY_MAP = {
    ".jpg": "photos", ".jpeg": "photos", ".png": "photos", ".heic": "photos", ".webp": "photos",
    ".mp4": "videos", ".mov": "videos", ".mkv": "videos", ".avi": "videos",
    ".pdf": "documents", ".docx": "documents", ".txt": "documents", ".odt": "documents",
}


def categorize(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return CATEGORY_MAP.get(ext, "other")


def sanitize_name(name: str | None, fallback: str) -> str:
    """Make ``name`` safe as a single path component.

    Removes / \\ : * ? " < > | and control chars, collapses whitespace and
    strips leading/trailing spaces and dots. Falls back to ``fallback`` when
    nothing is left.
    """
    cleaned = re.sub(r"\s+", " ", name or "")  # tabs/newlines become spaces first
    cleaned = _FORBIDDEN_CHARS.sub("", cleaned)
    cleaned = re.sub(r" {2,}", " ", cleaned).strip(" .")
    return cleaned or fallback


def jellyfin_episode_target(
    series_id: str | None,
    episode_number: int | None,
    series_title: str | None,
    series_year: int | None,
    *,
    season_number: int | None = None,
    file_episode_number: int | None = None,
    media_root: Path | None = None,
) -> tuple[Path, str] | None:
    """Return (directory, base name without extension) for the Jellyfin layout.

    ``<MEDIA_ROOT>/<Show>/Season NN/<Show> SNNE<NN>``. ``season_number`` and
    ``file_episode_number`` (ADR-020, franchise layout) default to season 1 and
    ``episode_number``. ``media_root`` overrides MEDIA_ROOT (relocation script).
    Returns None (legacy layout) unless the root is set and series_id,
    episode_number and series_title are all present.
    """
    root = media_root if media_root is not None else MEDIA_ROOT
    if root is None or not series_id or episode_number is None or not series_title:
        return None
    show = sanitize_name(series_title, series_id)
    if isinstance(series_year, int) and not isinstance(series_year, bool) and series_year > 0:
        show = f"{show} ({series_year})"
    season = 1 if season_number is None else season_number
    file_ep = episode_number if file_episode_number is None else file_episode_number
    return root / show / f"Season {season:02d}", f"{show} S{season:02d}E{file_ep:02d}"


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    series_id: Optional[str] = Form(default=None),
    episode_number: Optional[int] = Form(default=None),
    series_title: Optional[str] = Form(default=None),
    series_year: Optional[int] = Form(default=None),
):
    """
    Sube un archivo. Opcionalmente acepta series_id y episode_number (Form fields)
    para asociar el archivo a un episodio específico.
    """
    category = categorize(file.filename)
    now = datetime.utcnow()

    jellyfin = jellyfin_episode_target(series_id, episode_number, series_title, series_year)
    stored_name = file.filename
    if jellyfin:
        subdir, base = jellyfin
        stored_name = base + (Path(file.filename).suffix or ".mp4")
    elif series_id and episode_number is not None:
        subdir = STORAGE_ROOT / "videos" / "episodes" / series_id
    else:
        subdir = STORAGE_ROOT / category / f"{now.year:04d}-{now.month:02d}"

    subdir.mkdir(parents=True, exist_ok=True)

    destination = subdir / stored_name
    if destination.exists():
        stem, suffix = destination.stem, destination.suffix
        destination = subdir / f"{stem}_{now.strftime('%Y%m%d%H%M%S')}{suffix}"

    try:
        with destination.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except OSError as e:
        raise HTTPException(status_code=507, detail=f"Error de escritura en disco: {e}")
    finally:
        await file.close()

    size_bytes = destination.stat().st_size

    file_id = db.insert_file(
        filename=stored_name,
        stored_path=str(destination),
        content_type=file.content_type,
        size_bytes=size_bytes,
        category=category,
        series_id=series_id,
        episode_number=episode_number,
    )

    return {
        "id": file_id,
        "filename": stored_name,
        "category": category,
        "size_bytes": size_bytes,
        "stored_path": str(destination),
        "series_id": series_id,
        "episode_number": episode_number,
    }


@router.get("/files")
async def list_files(
    category: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
):
    return db.list_files(category=category, limit=limit, offset=offset)


@router.get("/episodes/{series_id}")
async def list_episode_numbers(series_id: str):
    """Bulk status: episode numbers stored for a series (empty list if unknown)."""
    return {"series_id": series_id, "episode_numbers": db.list_episode_numbers(series_id)}


@router.get("/episodes/{series_id}/{episode_number}")
async def get_episode_file(series_id: str, episode_number: int):
    """
    Devuelve la metadata del archivo asociado a un episodio.
    El campo download_url apunta al endpoint de descarga del archivo.
    """
    record = db.get_file_by_episode(series_id, episode_number)
    if not record:
        raise HTTPException(status_code=404, detail="Episode file not found")
    return {
        **record,
        "download_url": f"/api/files/{record['id']}/download",
    }


@router.get("/files/{file_id}")
async def get_file_metadata(file_id: int):
    record = db.get_file_by_id(file_id)
    if not record:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return record


@router.get("/files/{file_id}/download")
async def download_file(file_id: int):
    record = db.get_file_by_id(file_id)
    if not record:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    path = Path(record["stored_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="El archivo está registrado en la BD pero no existe en disco")

    return FileResponse(path=path, filename=record["filename"], media_type=record["content_type"])


@router.delete("/files/{file_id}")
async def delete_file(file_id: int):
    record = db.get_file_by_id(file_id)
    if not record:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    path = Path(record["stored_path"])
    if path.exists():
        path.unlink()

    db.delete_file_record(file_id)
    return {"deleted": True, "id": file_id}
