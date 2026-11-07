"""
Modelo de datos y acceso a SQLite.
Sin ORM pesado — sqlite3 estándar de Python es suficiente a esta escala.
"""
import sqlite3
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager

DB_PATH = Path(__file__).parent.parent / "metadata.db"


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, col_type: str) -> None:
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
    except sqlite3.OperationalError:
        pass  # column already exists


def init_db():
    """Crea todas las tablas si no existen y aplica migraciones de columnas."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                stored_path TEXT NOT NULL UNIQUE,
                content_type TEXT,
                size_bytes INTEGER,
                category TEXT,
                series_id TEXT,
                episode_number INTEGER,
                uploaded_at TEXT NOT NULL
            )
        """)
        # Migrations for existing DBs that predate series_id / episode_number
        _add_column_if_missing(conn, "files", "series_id", "TEXT")
        _add_column_if_missing(conn, "files", "episode_number", "INTEGER")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON files(category)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_uploaded_at ON files(uploaded_at)")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_episode ON files(series_id, episode_number) "
            "WHERE series_id IS NOT NULL AND episode_number IS NOT NULL"
        )

        conn.execute("""
            CREATE TABLE IF NOT EXISTS download_jobs (
                id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                category TEXT NOT NULL,
                series_id TEXT,
                episode_number INTEGER,
                status TEXT NOT NULL DEFAULT 'pending',
                error TEXT,
                file_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        _add_column_if_missing(conn, "download_jobs", "series_id", "TEXT")
        _add_column_if_missing(conn, "download_jobs", "episode_number", "INTEGER")

        # Single uvicorn worker: background tasks cannot survive a restart, and a
        # stale active job would block re-downloads via get_active_job_for_episode.
        conn.execute(
            "UPDATE download_jobs SET status = 'failed', error = 'interrupted by restart', "
            "updated_at = ? WHERE status IN ('pending', 'downloading')",
            (datetime.utcnow().isoformat(),),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

def insert_file(
    filename: str,
    stored_path: str,
    content_type: str,
    size_bytes: int,
    category: str,
    series_id: str | None = None,
    episode_number: int | None = None,
) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO files
               (filename, stored_path, content_type, size_bytes, category, series_id, episode_number, uploaded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (filename, stored_path, content_type, size_bytes, category,
             series_id, episode_number, datetime.utcnow().isoformat())
        )
        conn.commit()
        return cursor.lastrowid


def list_files(category: str | None = None, limit: int = 100, offset: int = 0):
    with get_connection() as conn:
        if category:
            rows = conn.execute(
                "SELECT * FROM files WHERE category = ? ORDER BY uploaded_at DESC LIMIT ? OFFSET ?",
                (category, limit, offset)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM files ORDER BY uploaded_at DESC LIMIT ? OFFSET ?",
                (limit, offset)
            ).fetchall()
        return [dict(row) for row in rows]


def get_file_by_id(file_id: int):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        return dict(row) if row else None


def get_file_by_episode(series_id: str, episode_number: int):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM files WHERE series_id = ? AND episode_number = ?",
            (series_id, episode_number)
        ).fetchone()
        return dict(row) if row else None


def list_episode_numbers(series_id: str) -> list[int]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT episode_number FROM files "
            "WHERE series_id = ? AND episode_number IS NOT NULL "
            "ORDER BY episode_number",
            (series_id,),
        ).fetchall()
        return [r["episode_number"] for r in rows]


def delete_file_record(file_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
        conn.commit()
        return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Download jobs
# ---------------------------------------------------------------------------

def create_job(
    job_id: str,
    url: str,
    category: str,
    series_id: str | None = None,
    episode_number: int | None = None,
    status: str = "pending",
    file_id: int | None = None,
) -> dict:
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO download_jobs
               (id, url, category, series_id, episode_number, status, file_id,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (job_id, url, category, series_id, episode_number, status, file_id, now, now)
        )
        conn.commit()
    return get_job(job_id)


def get_active_job_for_episode(series_id: str, episode_number: int) -> dict | None:
    """Oldest pending/downloading job for this episode, if any."""
    with get_connection() as conn:
        row = conn.execute(
            """SELECT * FROM download_jobs
               WHERE series_id = ? AND episode_number = ?
                 AND status IN ('pending', 'downloading')
               ORDER BY created_at LIMIT 1""",
            (series_id, episode_number),
        ).fetchone()
    return dict(row) if row else None


def get_job(job_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM download_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return dict(row) if row else None


def update_job(job_id: str, status: str, error: str | None = None,
               file_id: int | None = None):
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        conn.execute(
            """UPDATE download_jobs
               SET status = ?, error = ?, file_id = ?, updated_at = ?
               WHERE id = ?""",
            (status, error, file_id, now, job_id)
        )
        conn.commit()
