import re
from domain.simulcast import resolve_simulcast_status

RATING_MAP = {
    "G - All Ages": "G",
    "PG - Children": "PG",
    "PG-13 - Teens 13 or older": "PG-13",
    "R - 17+ (violence & profanity)": "17+",
    "R+ - Mild Nudity": "17+",
}


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text


def normalize(
    raw: dict,
    is_featured: bool = False,
    kitsu_id: str | None = None,
    kitsu_status: str | None = None,
) -> dict | None:
    """Normalize a raw Jikan anime dict into the series DB shape.

    Args:
        raw:          Raw Jikan API response data dict (the ``data`` object).
        is_featured:  Whether to mark this series as featured.
        kitsu_id:     Kitsu anime ID if available, or None.
        kitsu_status: Kitsu ``attributes.status`` string if available, or None.

    Returns:
        Normalized series dict, or None if required fields are missing.
    """
    mal_id = raw.get("mal_id")
    title = raw.get("title_english") or raw.get("title") or ""
    if not title or not mal_id:
        return None

    synopsis = (raw.get("synopsis") or "").replace("\n", " ").strip()
    if synopsis.endswith("[Written by MAL Rewrite]"):
        synopsis = synopsis[: -len("[Written by MAL Rewrite]")].strip()

    images = raw.get("images", {}).get("jpg", {})
    thumbnail_url = images.get("image_url", "")
    banner_url = images.get("large_image_url", "") or thumbnail_url

    raw_rating = raw.get("rating") or ""
    rating = RATING_MAP.get(raw_rating, "14+")

    genres = [g["name"] for g in raw.get("genres", [])]
    themes = [t["name"] for t in raw.get("themes", [])]
    all_genres = list(dict.fromkeys(genres + themes))  # dedup, preserve order

    titles = [t["title"] for t in raw.get("titles", []) if t.get("title")]

    airing = raw.get("airing", False)
    is_simulcast = resolve_simulcast_status(
        jikan_airing=bool(airing),
        kitsu_status=kitsu_status,
        has_kitsu=bool(kitsu_id),
    )

    # Broadcast metadata from Jikan
    broadcast = raw.get("broadcast") or {}
    broadcast_day = broadcast.get("day")
    broadcast_time = broadcast.get("time")
    broadcast_timezone = broadcast.get("timezone")

    # Aired-from date
    aired_from = (raw.get("aired") or {}).get("from")

    slug = _slugify(title)

    return {
        "id": slug,
        "mal_id": mal_id,
        "title": title,
        "slug": slug,
        "description": synopsis,
        "thumbnail_url": thumbnail_url,
        "banner_url": banner_url,
        "rating": rating,
        "genres": all_genres,
        "audio_formats": ["sub"],
        "season_count": 1,
        "episode_count": raw.get("episodes") or 0,
        "year": raw.get("year") or (raw.get("aired", {}).get("prop", {}).get("from", {}).get("year")),
        "media_type": (raw.get("type") or "TV").lower(),
        "is_simulcast": is_simulcast,
        "is_featured": is_featured,
        "score": raw.get("score"),
        "titles": titles,
        # Simulcast metadata
        "broadcast_day": broadcast_day,
        "broadcast_time": broadcast_time,
        "broadcast_timezone": broadcast_timezone,
        "aired_from": aired_from,
        "kitsu_id": kitsu_id,
        "kitsu_status": kitsu_status,
    }
