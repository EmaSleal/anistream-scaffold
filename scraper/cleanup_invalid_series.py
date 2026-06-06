"""Script to remove invalid simulcast series (Hentai genre or no score)."""
import logging
from storage import get_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def cleanup_invalid_series(delete: bool = False) -> dict:
    """Remove invalid series (Hentai genre or without score).

    Args:
        delete: If True, DELETE rows from DB. If False, mark as is_simulcast=false.

    Returns:
        {removed: int, hentai_removed: int, no_score_removed: int}
    """
    client = get_client()

    # Fetch all series with Hentai or no score (regardless of simulcast status)
    all_result = (
        client.table("series")
        .select("id, title, genres, score, is_simulcast")
        .execute()
    )

    rows = all_result.data or []
    logger.info(f"Scanning {len(rows)} total series")

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
        elif not score or (isinstance(score, (int, float)) and score <= 0) or score == "":
            logger.warning(f"No score: {row['title']} (score={score})")
            to_remove.append(row["id"])
            no_score_count += 1

    if not to_remove:
        logger.info("No invalid series found")
        return {"removed": 0, "hentai_removed": 0, "no_score_removed": 0}

    logger.info(f"Found {len(to_remove)} invalid series (Hentai: {hentai_count}, No score: {no_score_count})")

    if delete:
        logger.info("DELETING from database...")
        for series_id in to_remove:
            try:
                client.table("series").delete().eq("id", series_id).execute()
                logger.info(f"Deleted: {series_id}")
            except Exception as e:
                logger.error(f"Failed to delete {series_id}: {e}")
    else:
        logger.info("Marking as non-simulcast...")
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
    import sys

    # Run with --delete flag to actually delete rows
    delete_mode = "--delete" in sys.argv

    if delete_mode:
        print("⚠️  DELETE MODE ENABLED — series will be REMOVED from database")
        confirm = input("Type 'yes' to confirm: ")
        if confirm.lower() != "yes":
            print("Cancelled")
            sys.exit(0)

    result = cleanup_invalid_series(delete=delete_mode)
    print(f"\n✓ Cleanup result: {result}")
    if delete_mode:
        print("✓ Rows deleted from database")
