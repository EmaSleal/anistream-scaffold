"""
Punto de entrada. Corré con:
    uvicorn app.main:app --host 0.0.0.0 --port 8000

Para producción liviana (sin reload, 1 solo worker dado el hardware):
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
"""
from fastapi import FastAPI, Depends
from app.routers import files, jobs
from app.models import db
from app.auth import require_api_key

app = FastAPI(
    title="astro1 Disk API",
    description="API minimalista para gestión de archivos sobre pool MergerFS",
    version="0.1.0",
)


@app.on_event("startup")
def on_startup():
    db.init_db()


@app.get("/health")
async def health_check():
    return {"status": "ok"}


# All /api/* routes require a valid X-API-Key header.
app.include_router(files.router, prefix="/api", tags=["files"], dependencies=[Depends(require_api_key)])
app.include_router(jobs.router, prefix="/api", tags=["jobs"], dependencies=[Depends(require_api_key)])
