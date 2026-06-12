"""Pure domain functions for watch-progress and continue-watching logic.

No database access — all functions accept raw dicts and return transformed
structures. Testable in isolation (mirrors the Wave 1/2 domain layer pattern).

Routes summary:
  build_continue_watching — franchise-deduped, completion-filtered, capped at 10
  build_watch_history     — unfiltered, no dedup, capped at `limit`
"""
from domain.series import map_episode_row


def build_continue_watching(
    progress_rows: list[dict],
    franchise_map: dict[str, str],
    episode_rows: list[dict],
) -> list[dict]:
    """Build the continue-watching list from raw DB data.

    Pipeline:
      1. Franchise dedup — keep only the most-recently-watched episode per
         franchise (franchise_id falls back to series_id when NULL).
      2. Enrich each survivor with episode details.
      3. Filter out episodes where progress_sec / duration_sec >= 0.95
         (treat as completed). Episodes with duration_sec == 0 are NOT filtered.
      4. Cap the result at 10 items.

    Args:
        progress_rows:  Raw watch_progress rows (episode_id, series_id,
                        progress_sec, duration_sec, updated_at), already
                        pre-sorted by updated_at DESC and capped at 30.
        franchise_map:  Dict of series_id -> franchise_id (fallback series_id).
                        From db.progress.get_series_franchise_map().
        episode_rows:   Raw episode rows (with series join) for the surviving
                        episode_ids. From db.progress.get_episodes_by_ids().

    Returns:
        List of dicts: {episode: <camelCase Episode>, progressSeconds: int,
                        seriesId: str}
    """
    # Step 1: franchise dedup — first occurrence per franchise wins
    # (rows are already ordered updated_at DESC, so first = most recent)
    seen_franchises: set[str] = set()
    deduped: list[dict] = []
    for row in progress_rows:
        series_id = row.get("series_id") or ""
        franchise_key = franchise_map.get(series_id) or series_id or row.get("episode_id", "")
        if franchise_key in seen_franchises:
            continue
        seen_franchises.add(franchise_key)
        deduped.append(row)

    # Step 2: build episode lookup
    episode_by_id: dict[str, dict] = {ep["id"]: ep for ep in episode_rows}

    # Step 3 + 4: enrich, filter completed, cap at 10
    result: list[dict] = []
    for row in deduped:
        if len(result) >= 10:
            break

        episode_id = row.get("episode_id")
        ep_raw = episode_by_id.get(episode_id)
        if not ep_raw:
            # Episode not found — skip (data integrity gap)
            continue

        progress_sec = row.get("progress_sec", 0) or 0
        duration_sec = row.get("duration_sec", 0) or 0

        # Filter out completed (>= 95%) — skip only when duration is known
        if duration_sec > 0 and progress_sec / duration_sec >= 0.95:
            continue

        episode = map_episode_row(ep_raw)
        # Duration from the progress row is more reliable than the episodes table
        # (which may have the column empty). Overwrite only when progress has it.
        if duration_sec > 0:
            episode["duration"] = duration_sec
        result.append(
            {
                "episode": episode,
                "progressSeconds": progress_sec,
                "seriesId": row.get("series_id"),
            }
        )

    return result


def build_watch_history(
    progress_rows: list[dict],
    episode_rows: list[dict],
    limit: int,
) -> list[dict]:
    """Build the watch-history list from raw DB data.

    Unlike build_continue_watching, this function:
    - Applies NO completion (>=95%) filter — all watched episodes are included.
    - Applies NO franchise deduplication — each episode appears independently.
    - Produces NO simulcast side-effects.
    - Caps the result at `limit` items (not a fixed 10).

    Args:
        progress_rows:  Raw watch_progress rows (episode_id, series_id,
                        progress_sec, duration_sec, updated_at), already
                        pre-sorted by updated_at DESC and capped by the caller.
        episode_rows:   Raw episode rows (with series join) for the episode_ids
                        in progress_rows. From db.progress.get_episodes_by_ids().
        limit:          Maximum number of items to return.

    Returns:
        List of dicts: {episode: <camelCase Episode>, progressSeconds: int,
                        seriesId: str}
    """
    episode_by_id: dict[str, dict] = {ep["id"]: ep for ep in episode_rows}

    result: list[dict] = []
    for row in progress_rows:
        if len(result) >= limit:
            break

        episode_id = row.get("episode_id")
        ep_raw = episode_by_id.get(episode_id)
        if not ep_raw:
            # Episode not found — skip (data integrity gap, same as build_continue_watching)
            continue

        progress_sec = row.get("progress_sec", 0) or 0
        duration_sec = row.get("duration_sec", 0) or 0

        episode = map_episode_row(ep_raw)
        # Duration from the progress row is more reliable than the episodes table.
        # Overwrite only when progress has it (same logic as build_continue_watching).
        if duration_sec > 0:
            episode["duration"] = duration_sec

        result.append(
            {
                "episode": episode,
                "progressSeconds": progress_sec,
                "seriesId": row.get("series_id"),
            }
        )

    return result
