from supabase import create_client, ClientOptions
from config import SUPABASE_URL, SUPABASE_KEY


def get_client():
    """Return a fresh Supabase client on every call.

    supabase-py uses httpx with HTTP/2 when h2 is installed. The HTTP/2
    connection pool reuses connections that Supabase has already closed on
    its side, causing RemoteProtocolError: Server disconnected. Creating a
    new client per call avoids stale pool connections entirely.
    """
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def upsert_series(series: dict) -> None:
    client = get_client()
    client.table("series").upsert(series, on_conflict="id").execute()


def upsert_many(series_list: list[dict]) -> int:
    client = get_client()
    if not series_list:
        return 0
    unique = list({s["id"]: s for s in series_list}.values())
    client.table("series").upsert(unique, on_conflict="id").execute()
    return len(unique)


def upsert_episode(episode: dict) -> None:
    """Upsert a single episode row to the ``episodes`` table."""
    client = get_client()
    client.table("episodes").upsert(episode, on_conflict="id").execute()


def upsert_episodes(episodes: list[dict]) -> int:
    """Deduplicate by ``id``, upsert the batch, and return the count upserted."""
    client = get_client()
    if not episodes:
        return 0
    unique = list({ep["id"]: ep for ep in episodes}.values())
    client.table("episodes").upsert(unique, on_conflict="id").execute()
    return len(unique)


def get_series_by_mal_id(mal_id: int) -> dict | None:
    """Return the series row matching ``mal_id``, or ``None`` if absent."""
    client = get_client()
    result = (
        client.table("series")
        .select("id")
        .eq("mal_id", mal_id)
        .maybe_single()
        .execute()
    )
    return result.data if result else None


def get_series_by_id(series_id: str) -> dict | None:
    """Return the series row matching ``series_id``, or ``None`` if absent."""
    client = get_client()
    result = (
        client.table("series")
        .select("id, animeav1_slug")
        .eq("id", series_id)
        .maybe_single()
        .execute()
    )
    return result.data if result else None


def get_episode_by_slug(animeflv_slug: str) -> dict | None:
    """Return the episode row matching ``animeflv_slug``, or ``None`` if absent."""
    client = get_client()
    result = (
        client.table("episodes")
        .select("*")
        .eq("animeflv_slug", animeflv_slug)
        .maybe_single()
        .execute()
    )
    return result.data if result else None
