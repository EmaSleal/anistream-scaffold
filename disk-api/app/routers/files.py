"""
Endpoints REST para gestión de archivos sobre el pool de MergerFS.
"""
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Form
from fastapi.responses import FileResponse

from app.models import db

router = APIRouter()

# Punto de montaje del pool MergerFS — ajustar si cambia
STORAGE_ROOT = Path("/mnt/data_safe/storage")

CATEGORY_MAP = {
    ".jpg": "photos", ".jpeg": "photos", ".png": "photos", ".heic": "photos", ".webp": "photos",
    ".mp4": "videos", ".mov": "videos", ".mkv": "videos", ".avi": "videos",
    ".pdf": "documents", ".docx": "documents", ".txt": "documents", ".odt": "documents",
}


def categorize(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return CATEGORY_MAP.get(ext, "other")


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    series_id: Optional[str] = Form(default=None),
    episode_number: Optional[int] = Form(default=None),
):
    """
    Sube un archivo. Opcionalmente acepta series_id y episode_number (Form fields)
    para asociar el archivo a un episodio específico.
    """
    category = categorize(file.filename)
    now = datetime.utcnow()

    if series_id and episode_number is not None:
        subdir = STORAGE_ROOT / "videos" / "episodes" / series_id
    else:
        subdir = STORAGE_ROOT / category / f"{now.year:04d}-{now.month:02d}"

    subdir.mkdir(parents=True, exist_ok=True)

    destination = subdir / file.filename
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
        filename=file.filename,
        stored_path=str(destination),
        content_type=file.content_type,
        size_bytes=size_bytes,
        category=category,
        series_id=series_id,
        episode_number=episode_number,
    )

    return {
        "id": file_id,
        "filename": file.filename,
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
