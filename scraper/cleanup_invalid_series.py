"""Script to remove invalid simulcast series (Hentai genre or no score)."""
import logging
from storage import get_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def cleanup_invalid_series() -> dict:
    """Remove simulcast series with Hentai genre or without score.

    Returns:
        {removed: int, hentai_removed: int, no_score_removed: int}
    """
    client = get_client()

    # Fetch all simulcast series
    result = (
        client.table("series")
        .select("id, title, genres, score, is_simulcast")
        .eq("is_simulcast", True)
        .execute()
    )

    rows = result.data or []
    logger.info(f"Found {len(rows)} simulcast series")

    to_remove = []
    hentai_count = 0
    no_score_count = 0

    for row in rows:
        genres = row.get("genres") or []
        score = row.get("score")

        # Remove if Hentai or no score
        if "Hentai" in genres:
            logger.warning(f"Hentai series: {row['title']} (genres={genres})")
            to_remove.append(row["id"])
            hentai_count += 1
        elif not score or score == 0:
            logger.warning(f"No score: {row['title']} (score={score})")
            to_remove.append(row["id"])
            no_score_count += 1

    if not to_remove:
        logger.info("No invalid series found")
        return {"removed": 0, "hentai_removed": 0, "no_score_removed": 0}

    logger.info(f"Removing {len(to_remove)} series (Hentai: {hentai_count}, No score: {no_score_count})")

    # Mark as non-simulcast instead of deleting
    for series_id in to_remove:
        try:
            client.table("series").update({"is_simulcast": False}).eq("id", series_id).execute()
        except Exception as e:
            logger.error(f"Failed to update {series_id}: {e}")

    logger.info("Cleanup complete")
    return {
        "removed": len(to_remove),
        "hentai_removed": hentai_count,
        "no_score_removed": no_score_count,
    }


if __name__ == "__main__":
    result = cleanup_invalid_series()
    print(f"\n✓ Cleanup result: {result}")
