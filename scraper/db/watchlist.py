"""Supabase query functions for the watchlist table.

All functions return raw dicts from the DB (snake_case).
The watchlist table schema: (id, user_id, series_id, added_at).
"""
import storage


def get_watchlist(user_id: str) -> list[dict]:
    """Return full Series rows for all entries in the user's watchlist.

    Two-query approach: PostgREST requires a declared FK to do implicit joins,
    and the watchlist table has no FK constraint on series_id.
    """
    client = storage.get_client()
    wl_result = (
        client.table("watchlist")
        .select("series_id, added_at")
        .eq("user_id", user_id)
        .order("added_at", desc=True)
        .execute()
    )
    wl_rows = wl_result.data or []
    if not wl_rows:
        return []

    series_ids = [row["series_id"] for row in wl_rows]
    added_at_map = {row["series_id"]: row["added_at"] for row in wl_rows}

    series_result = (
        client.table("series")
        .select("*")
        .in_("id", series_ids)
        .execute()
    )
    series_rows = series_result.data or []

    # Preserve watchlist order (added_at DESC)
    series_rows.sort(key=lambda s: added_at_map.get(s["id"], ""), reverse=True)
    return series_rows


def add_to_watchlist(user_id: str, series_id: str) -> None:
    """Upsert a (user_id, series_id) row — no error if already present.

    Uses INSERT OR IGNORE semantics via Supabase upsert with on_conflict.
    """
    client = storage.get_client()
    client.table("watchlist").upsert(
        {"user_id": user_id, "series_id": series_id},
        on_conflict="user_id,series_id",
    ).execute()


def remove_from_watchlist(user_id: str, series_id: str) -> None:
    """Delete the (user_id, series_id) row if it exists. Silent if absent."""
    client = storage.get_client()
    client.table("watchlist").delete().eq("user_id", user_id).eq(
        "series_id", series_id
    ).execute()
