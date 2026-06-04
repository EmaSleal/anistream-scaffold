"""Flask Blueprint for simulcast refresh endpoint.

POST /api/simulcast/refresh/<series_id>
  - Protected by @require_service (X-Service-Key header).
  - Fetches fresh Jikan + Kitsu data.
  - Recomputes is_simulcast and persists broadcast/Kitsu metadata.
  - Auto-ingests new episodes when jikan.episode_count > db.episode_count.
  - Gates itself with a 1-hour cooldown via last_simulcast_check.
"""
from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, jsonify

from auth import require_service
from db.simulcast import get_series_simulcast_data, update_simulcast_fields
from domain.simulcast import resolve_simulcast_status
from fetcher import fetch_anime_by_id, fetch_kitsu_series_status, fetch_kitsu_episodes, fetch_jikan_episodes
from routes import _build_episodes
from storage import upsert_episodes

simulcast_bp = Blueprint("simulcast", __name__, url_prefix="/api/simulcast")

_COOLDOWN_SECONDS = 3600


@simulcast_bp.post("/refresh/<series_id>")
@require_service
def refresh_simulcast(series_id: str):
    """POST /api/simulcast/refresh/<series_id>

    Refresh simulcast status and broadcast metadata for a series.

    Returns:
        200  {"refreshed": true,  "is_simulcast": bool, "episodes_ingested": int}
        200  {"refreshed": false, "skipped": "cooldown"}  — cooldown not elapsed
        404  {"error": "Series not found"}
        401  via @require_service when X-Service-Key is missing/wrong
    """
    # 1. Fetch the series simulcast row
    row = get_series_simulcast_data(series_id)
    if row is None:
        return jsonify({"error": "Series not found"}), 404

    # 2. Cooldown gate
    last_check = row.get("last_simulcast_check")
    if last_check is not None:
        if isinstance(last_check, str):
            # Supabase returns TIMESTAMPTZ as ISO string; parse it
            try:
                last_check_dt = datetime.fromisoformat(last_check)
                if last_check_dt.tzinfo is None:
                    last_check_dt = last_check_dt.replace(tzinfo=timezone.utc)
            except ValueError:
                last_check_dt = None
        elif isinstance(last_check, datetime):
            last_check_dt = last_check
            if last_check_dt.tzinfo is None:
                last_check_dt = last_check_dt.replace(tzinfo=timezone.utc)
        else:
            last_check_dt = None

        if last_check_dt is not None:
            age_seconds = (datetime.now(timezone.utc) - last_check_dt).total_seconds()
            if age_seconds < _COOLDOWN_SECONDS:
                return jsonify({"skipped": "cooldown", "refreshed": False}), 200

    # 3. Extract stored DB values
    kitsu_id = row.get("kitsu_id")
    db_episode_count = row.get("episode_count") or 0
    animeflv_slug = row.get("animeflv_slug")

    # 4. Fetch fresh Jikan data — we need airing, broadcast, episode_count
    #    Use the series id as a fallback; in practice mal_id lookup isn't exposed
    #    here, so we fetch by animeflv_slug title search or rely on stored mal_id.
    #    The series id is the animeflv slug in this project.
    jikan_airing = False
    jikan_episode_count = db_episode_count
    jikan_broadcast: dict = {}
    jikan_aired_from: str | None = None
    jikan_mal_id: int | None = None

    try:
        # Look up the series by its stored mal_id via the DB (series row has mal_id)
        import storage as _storage
        mal_result = (
            _storage.get_client()
            .table("series")
            .select("mal_id")
            .eq("id", series_id)
            .maybe_single()
            .execute()
        )
        mal_id_val = (mal_result.data or {}).get("mal_id") if mal_result else None
        if mal_id_val:
            jikan_mal_id = int(mal_id_val)
            jikan_data = fetch_anime_by_id(jikan_mal_id)
            jikan_airing = bool(jikan_data.get("airing", False))
            jikan_episode_count = jikan_data.get("episodes") or db_episode_count
            jikan_broadcast = jikan_data.get("broadcast") or {}
            jikan_aired_from = (jikan_data.get("aired") or {}).get("from")
    except Exception:
        # Fail-open: if Jikan is unavailable, use DB values and skip recompute
        pass

    # 5. Fetch Kitsu status (only when kitsu_id is present)
    kitsu_status: str | None = None
    if kitsu_id:
        kitsu_status = fetch_kitsu_series_status(kitsu_id)

    # 6. Resolve simulcast status
    is_simulcast = resolve_simulcast_status(
        jikan_airing=jikan_airing,
        kitsu_status=kitsu_status,
        has_kitsu=bool(kitsu_id),
    )

    # 7. Persist updated simulcast fields (last_simulcast_check is set inside the helper)
    fields_to_update: dict = {
        "is_simulcast": is_simulcast,
        "kitsu_status": kitsu_status,
    }
    if jikan_broadcast.get("day") is not None:
        fields_to_update["broadcast_day"] = jikan_broadcast.get("day")
    if jikan_broadcast.get("time") is not None:
        fields_to_update["broadcast_time"] = jikan_broadcast.get("time")
    if jikan_broadcast.get("timezone") is not None:
        fields_to_update["broadcast_timezone"] = jikan_broadcast.get("timezone")
    if jikan_aired_from is not None:
        fields_to_update["aired_from"] = jikan_aired_from

    update_simulcast_fields(series_id, fields_to_update)

    # 8. Auto-ingest new episodes when Jikan reports more than what is stored
    episodes_ingested = 0
    if jikan_episode_count > db_episode_count and animeflv_slug and jikan_mal_id:
        try:
            kitsu_eps = fetch_kitsu_episodes(kitsu_id) if kitsu_id else {}
            jikan_titles = fetch_jikan_episodes(jikan_mal_id)
            new_episodes = _build_episodes(series_id, animeflv_slug, kitsu_eps, jikan_titles)
            if new_episodes:
                episodes_ingested = upsert_episodes(new_episodes)
                # Update episode_count in the series row
                _storage.get_client().table("series").update(
                    {"episode_count": jikan_episode_count}
                ).eq("id", series_id).execute()
        except Exception:
            # Fail-open: episode ingest failure should not fail the refresh response
            pass

    return jsonify({
        "refreshed": True,
        "is_simulcast": is_simulcast,
        "episodes_ingested": episodes_ingested,
    }), 200
