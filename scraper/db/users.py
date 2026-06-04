"""Supabase query functions for the users table.

All functions operate on raw dicts from the DB. No domain transformation is
performed here — callers handle any mapping they need.
"""
from datetime import datetime, timezone

import storage


def upsert_user(
    id: str,
    email: str,
    name: str | None,
    photo_url: str | None,
) -> None:
    """Upsert a user row. Conflict key: id.

    Always updates email, name, photo_url, and updated_at on conflict.
    """
    client = storage.get_client()
    client.table("users").upsert(
        {
            "id": id,
            "email": email,
            "name": name,
            "photo_url": photo_url,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="id",
    ).execute()


def get_user_role(user_id: str) -> str | None:
    """Return the role string for user_id, or None if user not found."""
    client = storage.get_client()
    result = (
        client.table("users")
        .select("role")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    if result and result.data:
        return result.data.get("role")
    return None
