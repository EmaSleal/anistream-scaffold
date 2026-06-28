"""Flask Blueprint for simulcast refresh endpoint.

POST /api/simulcast/refresh/<series_id>
  - Protected by @require_service (X-Service-Key header).
  - Fetches fresh Jikan + Kitsu data.
  - Recomputes is_simulcast and persists broadcast/Kitsu metadata.
  - Auto-ingests new episodes when jikan.episode_count > db.episode_count.
  - Gates itself with a 1-hour cooldown via last_simulcast_check.

Admin endpoints (require @require_admin):
  GET  /api/simulcast/list             — list all simulcast series (camelCase DTO)
  PATCH /api/simulcast/<id>/slug       — update animeflv_slug for a series
  POST /api/simulcast/sync-jikan       — sync DB with Jikan seasons/now
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request

from auth import require_admin, require_service
from db.series import get_series_list, get_series_by_id, upsert_series_stub
from db.simulcast import get_series_simulcast_data, update_simulcast_fields
from domain.jikan_refresh import refresh_series_from_jikan
from fetcher import fetch_kitsu_series_status, fetch_kitsu_episodes, fetch_jikan_episodes, fetch_simulcasts
from routes.ingest_routes import _build_episodes
from storage import get_series_by_mal_id, get_client, upsert_episodes

simulcast_bp = Blueprint("simulcast", __name__, url_prefix="/api/simulcast")

_COOLDOWN_SECONDS = 3600


def _fill_aired_at_from_cadence(episodes: list[dict]) -> None:
    """Fill null aired_at fields using 7-day weekly cadence from adjacent dated episodes.

    Mutates the list in-place. For each episode missing aired_at, finds the
    closest preceding episode that has a date and extrapolates forward at 7 days
    per episode. If no preceding dated episode exists, looks forward instead.
    Falls back to today's UTC date only when no reference point is available.
    """
    today = datetime.now(timezone.utc).date().isoformat()
    # Build a sorted map of episode_number → aired_at for dated episodes
    dated: dict[int, str] = {
        ep["episode_number"]: ep["aired_at"]
        for ep in episodes
        if ep.get("aired_at")
    }
    if not dated:
        for ep in episodes:
            if not ep.get("aired_at"):
                ep["aired_at"] = today
        return

    for ep in episodes:
        if ep.get("aired_at"):
            continue
        num = ep["episode_number"]
        # Find closest preceding dated episode
        preceding = {n: d for n, d in dated.items() if n < num}
        if preceding:
            ref_num = max(preceding)
            ref_date_str = preceding[ref_num]
        else:
            # No preceding — use the closest following dated episode, subtract days
            ref_num = min(n for n in dated if n > num)
            ref_date_str = dated[ref_num]
        try:
            ref_date = datetime.fromisoformat(ref_date_str[:10]).date()
            ep["aired_at"] = (ref_date + timedelta(days=7 * (num - ref_num))).isoformat()
        except Exception:
            ep["aired_at"] = today


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

    # 4. Resolve mal_id — stored on the series row (previously done inline inside
    #    the Jikan fetch block; lifted here so it can be passed to the domain helper).
    mal_id: int | None = None
    try:
        mal_result = (
            get_client()
            .table("series")
            .select("mal_id")
            .eq("id", series_id)
            .maybe_single()
            .execute()
        )
        mal_id_raw = (mal_result.data or {}).get("mal_id") if mal_result else None
        if mal_id_raw:
            mal_id = int(mal_id_raw)
    except Exception:
        pass

    # 5. Refresh Jikan + Kitsu metadata and persist simulcast fields.
    #    When mal_id is available, delegate to the domain helper which handles
    #    fail-open Jikan/Kitsu fetching and stamps last_simulcast_check.
    #    When mal_id is absent, persist defaults directly so the cooldown is
    #    still stamped (matching original behaviour).
    is_simulcast = False
    jikan_episode_count = db_episode_count
    if mal_id is not None:
        refresh_result = refresh_series_from_jikan(series_id, mal_id, kitsu_id)
        is_simulcast = refresh_result["is_simulcast"]
        jikan_episode_count = refresh_result["jikan_episode_count"] or db_episode_count
    else:
        _kitsu_status = fetch_kitsu_series_status(kitsu_id) if kitsu_id else None
        update_simulcast_fields(series_id, {
            "is_simulcast": False,
            "kitsu_status": _kitsu_status,
        })

    # 6. Auto-ingest new episodes when Jikan reports more than what is stored
    episodes_ingested = 0
    if jikan_episode_count > db_episode_count and animeflv_slug and mal_id is not None:
        try:
            kitsu_eps = fetch_kitsu_episodes(kitsu_id) if kitsu_id else {}
            jikan_titles = fetch_jikan_episodes(mal_id)
            new_episodes = _build_episodes(series_id, animeflv_slug, kitsu_eps, jikan_titles)
            _fill_aired_at_from_cadence(new_episodes)
            if new_episodes:
                episodes_ingested = upsert_episodes(new_episodes)
                # Update episode_count in the series row
                get_client().table("series").update(
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


# ---------------------------------------------------------------------------
# Admin routes — all protected by @require_admin
# ---------------------------------------------------------------------------


@simulcast_bp.get("/list")
@require_admin
def list_simulcast():
    """GET /api/simulcast/list

    Returns all series with is_simulcast=True ordered by title ASC,
    mapped to a camelCase DTO.

    Returns:
        200  [{id, title, animeflvSlug, malId, isSimulcast, lastSimulcastCheck}]
        401/403  via @require_admin
    """
    rows = get_series_list(simulcast=True, sort="title", limit=200)
    return jsonify([
        {
            "id": r["id"],
            "title": r["title"],
            "animeflvSlug": r.get("animeflv_slug"),
            "malId": r.get("mal_id"),
            "isSimulcast": r.get("is_simulcast"),
            "lastSimulcastCheck": r.get("last_simulcast_check"),
            "score": r.get("score"),
        }
        for r in rows
    ]), 200


@simulcast_bp.patch("/<series_id>/slug")
@require_admin
def update_slug(series_id: str):
    """PATCH /api/simulcast/<series_id>/slug

    Updates animeflv_slug for the given series.

    Request body: {"slug": "<value>"}  — value may be "" or null to clear the field.

    Returns:
        200  {id, animeflvSlug}
        400  {"error": "Missing 'slug' field"}  — if body lacks the key entirely
        404  {"error": "Series not found"}
        401/403  via @require_admin
    """
    body = request.get_json(silent=True) or {}
    if "slug" not in body:
        return jsonify({"error": "Missing 'slug' field"}), 400

    if get_series_by_id(series_id) is None:
        return jsonify({"error": "Series not found"}), 404

    # Allow empty string or None to clear the field
    slug = body.get("slug") or None
    get_client().table("series").update({"animeflv_slug": slug}).eq("id", series_id).execute()
    return jsonify({"id": series_id, "animeflvSlug": slug}), 200


@simulcast_bp.post("/sync-jikan")
@require_admin
def sync_jikan():
    """POST /api/simulcast/sync-jikan

    Fetches currently airing anime from Jikan seasons/now and reconciles
    the database:
      - mal_id not in DB → upsert_series_stub + set is_simulcast=True → added
      - mal_id in DB, is_simulcast=False → set is_simulcast=True → updated
      - mal_id in DB, is_simulcast=True → skipped

    Returns:
        200  {added, updated, skipped}
        502  {"error": "Jikan fetch failed"}  — if Jikan is unreachable
        401/403  via @require_admin
    """
    try:
        entries = fetch_simulcasts()
    except Exception:
        return jsonify({"error": "Jikan fetch failed"}), 502

    added = 0
    updated = 0
    skipped = 0

    for entry in entries:
        # Only process currently airing entries
        if not entry.get("airing"):
            continue

        # Filter out Hentai genre
        genres = [g.get("name") for g in entry.get("genres", []) if g.get("name")]
        if "Hentai" in genres:
            continue

        # Filter out entries with no score (score <= 0)
        score = entry.get("score")
        if not score or float(score) <= 0:
            continue

        mal_id = entry.get("mal_id")
        if mal_id is None:
            continue

        existing = get_series_by_mal_id(mal_id)
        if existing is None:
            # New series — create a stub and mark as simulcast immediately
            # Pass entry as fallback in case fetch_anime_by_id fails (e.g., Jikan 500 error)
            upsert_series_stub(mal_id, entry)
            # upsert_series_stub may not set is_simulcast=True via normalizer,
            # so we set it explicitly via a direct update (avoids update_simulcast_fields
            # which stamps last_simulcast_check and resets the cooldown).
            new_series = get_series_by_mal_id(mal_id)
            if new_series is not None:
                get_client().table("series").update({"is_simulcast": True}).eq(
                    "id", new_series["id"]
                ).execute()
            added += 1
        else:
            # get_series_by_mal_id only returns {id}; read full row for is_simulcast
            row = get_series_by_id(existing["id"])
            if row is not None and not row.get("is_simulcast"):
                get_client().table("series").update({"is_simulcast": True}).eq(
                    "id", existing["id"]
                ).execute()
                updated += 1
            else:
                skipped += 1

    return jsonify({"added": added, "updated": updated, "skipped": skipped}), 200
