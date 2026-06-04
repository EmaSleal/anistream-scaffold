import re
from config import TPEAD_BASE
from scraper_animeflv import _scraper


class ExtractionError(Exception):
    """Raised when a stream URL cannot be extracted from the embed page."""


def extract_streamtape(video_id: str) -> str:
    """Fetch tpead.net and extract an MP4 stream URL for a StreamTape video.

    Args:
        video_id: The StreamTape video identifier (from ``streamtape.com/e/{video_id}``).

    Returns:
        A direct MP4 URL string (``https://...&stream=1``).

    Raises:
        ExtractionError: if the page cannot be fetched or the regex does not match.
    """
    url = f"{TPEAD_BASE}/v/{video_id}/"
    try:
        response = _scraper.get(
            url,
            headers={"Referer": "streamtape.com"},
            timeout=15,
        )
        response.raise_for_status()
    except Exception as exc:
        raise ExtractionError("Could not extract stream URL") from exc

    pattern = (
        r"getElementById\('captchalink'\)\.innerHTML\s*=\s*'([^']+)'"
        r"\s*\+\s*\('([^']+)'\)\.substring\((\d+)\)"
    )
    match = re.search(pattern, response.text)
    if not match:
        raise ExtractionError("Could not extract stream URL")

    part1, part2, offset_str = match.group(1), match.group(2), match.group(3)
    offset = int(offset_str)
    stream_url = f"https:{part1}{part2[offset:]}&stream=1"
    return stream_url
