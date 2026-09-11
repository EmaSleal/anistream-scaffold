-- Migration 003: get_recent_distinct_series() Postgres function
-- Run manually in the Supabase SQL editor.
--
-- Returns a user's N most-recently-watched series, deduplicated by
-- franchise_id (falls back to series_id when a series has no franchise) in a
-- single query. Replaces the old pattern of pulling raw watch_progress rows
-- (one per episode) and deduping in application code, which let a single
-- binge-watched show or multi-season franchise monopolize every seed slot.
--
-- Reusable by any process talking to this Supabase project via
-- client.rpc("get_recent_distinct_series", {...}) — currently wired into
-- GET /api/series/recommendations (seed selection) and
-- GET /api/progress/recent-series.

CREATE OR REPLACE FUNCTION get_recent_distinct_series(
  p_user_id TEXT,
  p_limit INT DEFAULT 10
)
RETURNS TABLE (
  series_id TEXT,
  franchise_id TEXT,
  last_watched_at TIMESTAMPTZ
)
LANGUAGE sql
STABLE
AS $$
  SELECT series_id, franchise_id, last_watched_at
  FROM (
    SELECT DISTINCT ON (COALESCE(s.franchise_id, wp.series_id))
      wp.series_id,
      COALESCE(s.franchise_id, wp.series_id) AS franchise_id,
      wp.updated_at AS last_watched_at
    FROM watch_progress wp
    LEFT JOIN series s ON s.id = wp.series_id
    WHERE wp.user_id = p_user_id
      AND wp.progress_sec > 0
    ORDER BY COALESCE(s.franchise_id, wp.series_id), wp.updated_at DESC
  ) deduped
  ORDER BY last_watched_at DESC
  LIMIT p_limit;
$$;

-- Rollback (run manually if needed):
-- DROP FUNCTION IF EXISTS get_recent_distinct_series(TEXT, INT);
