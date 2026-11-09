"""Supabase helpers for the download_queue table (ADR-019, migration 007)."""
from __future__ import annotations

from datetime import datetime, timezone

import storage
from db._paging import fetch_all

_TABLE = "download_queue"
_ACTIVE = ("queued", "downloading")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_unique_violation(exc: Exception) -> bool:
    """True for a Postgres unique violation (23505); anything else is a real error."""
    if str(getattr(exc, "code", "")) == "23505":
        return True
    text = str(exc).lower()
    return "23505" in text or "duplicate key" in text


def enqueue(series_id: str, episode_numbers: list[int], source: str = "jkanime") -> tuple[int, int]:
    """Queue ``episode_numbers`` of a series; return ``(queued, already_queued)``.

    Episodes that already have a queued/downloading row are skipped, so calling
    this twice is idempotent. The partial unique index
    (series_id, episode_number) WHERE status IN ('queued','downloading') is the
    DB-level guard: if a concurrent request inserts the same episode between our
    read and our insert, the bulk insert fails with a unique violation; we then
    retry row by row and count the conflicting rows as already queued. Any other
    error (missing table, Supabase down) propagates to the caller.
    """
    client = storage.get_client()
    rows = fetch_all(
        lambda: client.table(_TABLE)
        .select("episode_number")
        .eq("series_id", series_id)
        .in_("status", list(_ACTIVE))
        .order("episode_number")
    )
    active = {r["episode_number"] for r in rows}
    wanted = sorted(set(episode_numbers))
    todo = [n for n in wanted if n not in active]
    already = len(wanted) - len(todo)
    if not todo:
        return 0, already

    def _row(n: int) -> dict:
        return {"series_id": series_id, "episode_number": n, "source": source, "status": "queued"}

    try:
        client.table(_TABLE).insert([_row(n) for n in todo]).execute()
        return len(todo), already
    except Exception as exc:
        if not _is_unique_violation(exc):
            raise
        # Lost a race on the partial unique index: fall back to one insert per row.
        queued = 0
        for n in todo:
            try:
                client.table(_TABLE).insert(_row(n)).execute()
                queued += 1
            except Exception as row_exc:
                if not _is_unique_violation(row_exc):
                    raise
                already += 1
        return queued, already


def get_active() -> dict | None:
    """The item currently downloading (oldest first), or None."""
    client = storage.get_client()
    result = (
        client.table(_TABLE)
        .select("*")
        .eq("status", "downloading")
        .order("started_at")
        .limit(1)
        .execute()
    )
    rows = result.data if result else None
    return rows[0] if rows else None


def next_queued() -> dict | None:
    """The oldest queued item, or None."""
    client = storage.get_client()
    result = (
        client.table(_TABLE)
        .select("*")
        .eq("status", "queued")
        .order("created_at")
        .order("episode_number")
        .limit(1)
        .execute()
    )
    rows = result.data if result else None
    return rows[0] if rows else None


def _update(item_id: str, fields: dict) -> None:
    client = storage.get_client()
    client.table(_TABLE).update({**fields, "updated_at": _now()}).eq("id", item_id).execute()


def mark_downloading(item_id: str, nas_job_id: str) -> None:
    now = _now()
    _update(item_id, {"status": "downloading", "nas_job_id": nas_job_id, "started_at": now})


def mark_done(item_id: str) -> None:
    _update(item_id, {"status": "done", "finished_at": _now(), "error": None})


def mark_failed(item_id: str, error: str) -> None:
    _update(item_id, {"status": "failed", "error": error, "finished_at": _now()})


def list_for_series(series_id: str) -> list[dict]:
    """Every queue row of a series, ordered by episode number then creation."""
    client = storage.get_client()
    return fetch_all(
        lambda: client.table(_TABLE)
        .select("*")
        .eq("series_id", series_id)
        .order("episode_number")
        .order("created_at")
    )


def list_done_series_ids() -> list[str]:
    """Distinct series ids that have at least one 'done' queue row."""
    client = storage.get_client()
    rows = fetch_all(
        lambda: client.table(_TABLE)
        .select("id, series_id")
        .eq("status", "done")
        .order("id")
    )
    return sorted({r["series_id"] for r in rows})
