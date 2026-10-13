"""Background task: discover and seed a new simulcast episode.

This module is the sole implementation of the simulcast episode-check thread body.
It is intentionally separate from the route layer so it can be unit-tested in
isolation without a running Flask app.

Public API
----------
run_simulcast_check(user_id, series_id, principal_slug, current_max_ep)
    Call from a daemon thread spawned inside the continue_watching route.
    Never call thread.join() on it — the route must return immediately.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import storage
import db.episodes as db_episodes
import db.progress as db_progress
import db.simulcast as db_simulcast
from domain.simulcast import plan_backfill
from fetcher import fetch_jikan_episodes
from scraper_animeav1 import scrape_animeav1_episodes

logger = logging.getLogger(__name__)


def _today_iso() -> str:
    """Return today's UTC date as a YYYY-MM-DD string."""
    return datetime.now(timezone.utc).date().isoformat()


def _get_series_mal_id(series_id: str) -> int | None:
    """Return the MAL ID for a series, or None if unavailable or on any error."""
    try:
        client = storage.get_client()
        result = (
            client.table("series")
            .select("mal_id")
            .eq("id", series_id)
            .maybe_single()
            .execute()
        )
        if result and result.data:
            return result.data.get("mal_id")
        return None
    except Exception:
        return None


def _get_last_episode_aired_at(series_id: str, episode_number: int) -> str | None:
    """Return the aired_at of a specific episode from DB, or None on any error."""
    try:
        client = storage.get_client()
        result = (
            client.table("episodes")
            .select("aired_at")
            .eq("series_id", series_id)
            .eq("episode_number", episode_number)
            .maybe_single()
            .execute()
        )
        if result and result.data:
            return result.data.get("aired_at")
        return None
    except Exception:
        return None


def _estimate_from_cadence(last_aired_at: str, ep_gap: int) -> str | None:
    """Estimate aired_at by adding 7 days per episode gap from a known date."""
    try:
        base = datetime.fromisoformat(last_aired_at[:10]).date()
        return (base + timedelta(days=7 * ep_gap)).isoformat()
    except Exception:
        return None


def _resolve_aired_at(
    mal_id: int | None,
    ep_num: int,
    series_id: str,
    current_max_ep: int,
) -> str:
    """Resolve aired_at for a simulcast episode.

    Resolution order:
    1. Jikan episode data (if mal_id is non-null): normalize to YYYY-MM-DD.
    2. Estimate from the last known episode's aired_at + 7 days per episode gap.
    3. Today's UTC date as last-resort fallback.

    Never raises — all paths return a date string.
    """
    # 1. Try Jikan
    if mal_id is not None:
        try:
            episodes = fetch_jikan_episodes(mal_id)
            raw = episodes.get(ep_num, {}).get("aired_at")
            if raw:
                return raw[:10]
        except Exception:
            pass

    # 2. Estimate from weekly cadence
    last_aired_at = _get_last_episode_aired_at(series_id, current_max_ep)
    if last_aired_at:
        estimated = _estimate_from_cadence(last_aired_at, ep_num - current_max_ep)
        if estimated:
            return estimated

    # 3. Last resort
    return _today_iso()


def run_simulcast_check(
    user_id: str,
    series_id: str,
    principal_slug: str,
    current_max_ep: int,
) -> None:
    """Scrape AnimeAV1 for the series, upsert any new episode, and seed progress.

    This function is designed to run in a daemon thread spawned from the
    continue_watching route. It MUST NOT access Flask ``g`` — ``user_id``
    is passed explicitly as an argument.

    Steps (executed unconditionally — cooldown stamp always happens):
      1. Scrape episode list from AnimeAV1.
      2. Compare the maximum scraped episode number against ``current_max_ep``.
      3. If new episodes exist:
           a. Upsert each new episode row via ``storage.upsert_episode``.
           b. Seed a ``watch_progress`` row for ``user_id`` at ``progress_sec=1``
              so the new episode appears in Continue Watching.
      4. Stamp ``series.last_simulcast_check = now()`` unconditionally.

    On any exception the function logs a warning, attempts to stamp the cooldown
    (to avoid hammering a broken series), and exits silently — it never propagates
    the exception to the caller.

    Args:
        user_id:         Authenticated user's ID captured in request scope.
        series_id:       Series primary key (slug-based).
        principal_slug:  AnimeAV1 slug for the series.
        current_max_ep:  Highest episode_number currently in the DB for this series.
    """
    mal_id = _get_series_mal_id(series_id)

    try:
        scraped_episodes = scrape_animeav1_episodes(principal_slug)
    except Exception as exc:
        logger.warning(
            "simulcast_check: scrape_episode_list failed for series=%r slug=%r: %s",
            series_id, principal_slug, exc,
        )
        _stamp_cooldown(series_id)
        return

    try:
        _process_scraped_episodes(
            scraped_episodes=scraped_episodes,
            series_id=series_id,
            user_id=user_id,
            current_max_ep=current_max_ep,
            mal_id=mal_id,
        )
    except Exception as exc:
        logger.warning(
            "simulcast_check: error processing scraped episodes for series=%r: %s",
            series_id, exc,
        )
    finally:
        _stamp_cooldown(series_id)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def run_simulcast_update(
    series_id: str,
    principal_slug: str,
    current_max_ep: int,
    mode: str = "airing",
    backfill_mode: str = "off",
    franchise_id: str | None = None,
    expected: int | None = None,
) -> int:
    """Like run_simulcast_check but without seeding watch_progress.

    Use this when the trigger is a series page visit (user has no watch_progress).
    Discovers and upserts new episodes, stamps the cooldown — does NOT seed progress.

    New args (all default to today's exact behavior — page-visit callers in
    ``routes/series_routes.py`` never pass these, so they are entirely unaffected):
        mode: ``"airing"`` (default, unchanged forward-scrape behavior) or
            ``"grace"`` — caps the forward path at ``offset + expected`` so a
            same-slug next-cour sibling's episodes aren't swallowed during
            the 14-day grace window. Only the scheduled cron job
            (``jobs/simulcast_job.py``) ever passes ``"grace"``.
        backfill_mode: ``"off"`` (default, no-op), ``"log"`` (compute the
            backfill plan but write nothing), or ``"write"`` (insert via
            ``storage.insert_episode_if_absent``). Only the scheduled cron
            job ever passes anything other than ``"off"``.
        franchise_id / expected: only consulted when ``mode == "grace"`` or
            ``backfill_mode != "off"`` (to resolve the slug-sibling offset
            via ``db.simulcast.get_slug_sibling_episodes``); ignored
            otherwise.

    Returns the number of new episodes upserted via the forward path (0 if
    none or on error). Backfilled inserts are not counted here — they are
    reported separately via INFO/WARNING logs tagged ``simulcast_backfill``.
    """
    mal_id = _get_series_mal_id(series_id)

    try:
        scraped_episodes = scrape_animeav1_episodes(principal_slug)
    except Exception as exc:
        logger.warning(
            "simulcast_check: scrape_episode_list failed for series=%r slug=%r: %s",
            series_id, principal_slug, exc,
        )
        _stamp_cooldown(series_id)
        return 0

    episodes_added = 0
    try:
        episodes_added = _process_scraped_episodes(
            scraped_episodes=scraped_episodes,
            series_id=series_id,
            user_id=None,
            current_max_ep=current_max_ep,
            mal_id=mal_id,
            mode=mode,
            backfill_mode=backfill_mode,
            franchise_id=franchise_id,
            principal_slug=principal_slug,
            expected=expected,
        )
    except Exception as exc:
        logger.warning(
            "simulcast_check: error processing scraped episodes for series=%r: %s",
            series_id, exc,
        )
    finally:
        _stamp_cooldown(series_id)
    return episodes_added


def _process_scraped_episodes(
    *,
    scraped_episodes: list[dict],
    series_id: str,
    user_id: str | None,
    current_max_ep: int,
    mal_id: int | None,
    mode: str = "airing",
    backfill_mode: str = "off",
    franchise_id: str | None = None,
    principal_slug: str | None = None,
    expected: int | None = None,
) -> int:
    """Upsert new episodes and optionally seed watch_progress for the user.

    Forward path: only episodes with ``episode_number > current_max_ep`` are
    considered new. When ``mode == "grace"``, the forward path is additionally
    capped at ``offset + expected`` so a same-slug next-cour sibling's
    episodes (which share this page during the 14-day grace window) aren't
    swallowed. ``mode == "airing"`` (default) is completely unchanged.
    Episode IDs follow the ``{series_id}-ep-{num}`` convention (no
    zero-padding), matching the format used in ``_build_episodes`` (routes.py).

    Backward gap-backfill: when ``backfill_mode != "off"``, runs
    ``domain.simulcast.plan_backfill`` against this same scrape (no extra
    AnimeAV1 call) to find missing episode numbers below ``current_max_ep``
    within this series' own owned range. ``"log"`` computes the plan and logs
    it without writing; ``"write"`` additionally inserts each planned episode
    via ``storage.insert_episode_if_absent`` (never ``upsert_episode`` — a
    backfilled guess must never overwrite an existing row). A
    ``skip_reason="ambiguous_offset"`` plan writes nothing and is logged as a
    WARNING for admin review.

    Returns the number of episodes upserted via the forward path only (not
    backfilled inserts — those are reported separately via logs).
    """
    offset = 0
    sibling_nums: set[int] = set()
    need_offset = mode == "grace" or backfill_mode != "off"
    if need_offset and franchise_id is not None and principal_slug is not None:
        sibling_info = db_simulcast.get_slug_sibling_episodes(
            franchise_id, principal_slug, series_id
        )
        offset = sibling_info["offset"]
        sibling_nums = sibling_info["sibling_nums"]

    forward_cap = offset + expected if (mode == "grace" and expected is not None) else None

    new_episodes = [
        ep for ep in scraped_episodes
        if ep.get("episode_number") is not None
        and ep["episode_number"] > current_max_ep
        and (forward_cap is None or ep["episode_number"] <= forward_cap)
    ]

    if not new_episodes:
        logger.debug(
            "simulcast_check: no new episodes for series=%r (db_max=%d, scraped_max=%s)",
            series_id,
            current_max_ep,
            max((ep["episode_number"] for ep in scraped_episodes), default="N/A"),
        )
    else:
        for ep in new_episodes:
            ep_num = ep["episode_number"]
            ep_id = f"{series_id}-ep-{ep_num}"

            storage.upsert_episode({
                "id": ep_id,
                "series_id": series_id,
                "episode_number": ep_num,
                "title": ep.get("title"),
                "thumbnail_url": ep.get("thumbnail_url"),
                # AnimeAV1-sourced episodes have no AnimeFlv slug — matches the
                # convention in _build_episodes_from_animeav1 (ingest_routes.py).
                "animeflv_slug": None,
                "aired_at": _resolve_aired_at(mal_id, ep_num, series_id, current_max_ep),
            })

            prev_ep_id = f"{series_id}-ep-{ep_num - 1}"
            db_progress.refresh_simulcast_next_episodes(series_id, prev_ep_id, ep_id)

            if user_id is not None:
                # Seed at progress_sec=1 so the new episode appears in Continue Watching.
                db_progress.upsert_progress(
                    user_id=user_id,
                    episode_id=ep_id,
                    series_id=series_id,
                    progress_sec=1,
                    duration_sec=0,
                )

            logger.info(
                "simulcast_check: upserted new episode %r for series=%r, seeded progress for user=%r",
                ep_id, series_id, user_id,
            )

    if backfill_mode != "off" and expected is not None:
        _backfill_missing_episodes(
            scraped_episodes=scraped_episodes,
            new_episodes=new_episodes,
            series_id=series_id,
            current_max_ep=current_max_ep,
            mal_id=mal_id,
            backfill_mode=backfill_mode,
            offset=offset,
            sibling_nums=sibling_nums,
            expected=expected,
        )

    return len(new_episodes)


def _backfill_missing_episodes(
    *,
    scraped_episodes: list[dict],
    new_episodes: list[dict],
    series_id: str,
    current_max_ep: int,
    mal_id: int | None,
    backfill_mode: str,
    offset: int,
    sibling_nums: set[int],
    expected: int,
) -> None:
    """Plan and (depending on ``backfill_mode``) write a backward gap-backfill.

    Runs only from the scheduled cron job — never from the page-visit
    trigger paths in ``routes/series_routes.py`` (those never pass
    ``backfill_mode != "off"``).
    """
    own_rows = db_episodes.get_episodes_by_series(series_id)
    own_nums = {
        r["episode_number"] for r in own_rows if r.get("episode_number") is not None
    }
    # Include episodes the forward path just upserted in this same pass, so
    # a number inserted moments ago is never also proposed for backfill.
    own_nums |= {ep["episode_number"] for ep in new_episodes}

    source_nums = {
        ep["episode_number"] for ep in scraped_episodes
        if ep.get("episode_number") is not None
    }

    plan = plan_backfill(
        own=own_nums,
        expected=expected,
        offset=offset,
        sibling_nums=sibling_nums,
        source_nums=source_nums,
        current_max=current_max_ep,
    )

    if plan["skip_reason"]:
        logger.warning(
            "simulcast_backfill: skipped for series=%r reason=%s",
            series_id, plan["skip_reason"],
        )
        return

    if not plan["inserts"]:
        return

    logger.info(
        "simulcast_backfill: series=%r plan=%s mode=%s",
        series_id, plan["inserts"], backfill_mode,
    )

    if backfill_mode != "write":
        return

    # Fetch once for the whole plan — fetch_jikan_episodes() is uncached and
    # paginates the full episode list, so calling it per-episode inside the
    # loop below would hit Jikan once per missing episode (e.g. 12 separate
    # paginated calls for a 12-episode gap like Daemons/Bookworm).
    jikan_eps: dict = {}
    if mal_id is not None:
        try:
            jikan_eps = fetch_jikan_episodes(mal_id)
        except Exception:
            jikan_eps = {}

    for ep_num in plan["inserts"]:
        ep_id = f"{series_id}-ep-{ep_num}"
        rel_num = ep_num - offset
        raw_aired = jikan_eps.get(rel_num, {}).get("aired_at")
        aired_at = raw_aired[:10] if raw_aired else None

        storage.insert_episode_if_absent({
            "id": ep_id,
            "series_id": series_id,
            "episode_number": ep_num,
            "title": None,
            "thumbnail_url": None,
            "animeflv_slug": None,
            "aired_at": aired_at,
        })
        logger.info(
            "simulcast_backfill: inserted series=%r episode=%r id=%r",
            series_id, ep_num, ep_id,
        )


def _stamp_cooldown(series_id: str) -> None:
    """Unconditionally stamp last_simulcast_check = now() for the series.

    Silently swallows any DB error so the calling try/except is not interrupted.
    """
    try:
        db_simulcast.update_simulcast_fields(series_id, {})
    except Exception as exc:
        logger.warning(
            "simulcast_check: failed to stamp cooldown for series=%r: %s",
            series_id, exc,
        )
