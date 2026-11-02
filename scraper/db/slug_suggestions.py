"""Supabase helpers for the slug_suggestions table (ADR-016, migration 006)."""
from __future__ import annotations

from datetime import datetime, timezone

import storage

_TABLE = "slug_suggestions"


def insert_pending(suggestion: dict) -> None:
    """Insert a pending suggestion unless (series_id, source, slug) already exists.

    ``ignore_duplicates`` makes the upsert a no-op for an existing row in ANY
    status, so pending/accepted/denied rows are never overwritten or re-created.
    """
    client = storage.get_client()
    client.table(_TABLE).upsert(
        suggestion, on_conflict="series_id,source,slug", ignore_duplicates=True
    ).execute()


def get_suggestion(suggestion_id: str) -> dict | None:
    client = storage.get_client()
    result = (
        client.table(_TABLE).select("*").eq("id", suggestion_id).maybe_single().execute()
    )
    return result.data if result else None


def list_suggestions(status: str, page: int, per_page: int) -> tuple[list[dict], int]:
    """One page of suggestions with ``status`` (newest first) plus the total count."""
    client = storage.get_client()
    start = (page - 1) * per_page
    result = (
        client.table(_TABLE)
        .select("*", count="exact")
        .eq("status", status)
        .order("created_at", desc=True)
        .range(start, start + per_page - 1)
        .execute()
    )
    return (result.data or []), (result.count or 0)


def mark_decided(suggestion_id: str, status: str) -> bool:
    """Set status accepted/denied and decided_at = now(), only while still pending.

    Returns False when no row was updated (already decided by someone else).
    """
    client = storage.get_client()
    result = (
        client.table(_TABLE)
        .update({"status": status, "decided_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", suggestion_id)
        .eq("status", "pending")
        .execute()
    )
    return bool(result.data)


def set_series_slug(series_id: str, field: str, slug: str, extra: dict | None = None) -> None:
    """Persist an accepted slug (``principal_slug`` or ``fallback_slug``) on the series row."""
    client = storage.get_client()
    client.table("series").update({field: slug, **(extra or {})}).eq("id", series_id).execute()
