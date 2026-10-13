-- Migration 004: Simulcast gap recovery — columns + trigger
-- Run manually in the Supabase SQL editor.
--
-- Additive only. No existing behavior changes until the feature flags
-- SIMULCAST_GRACE_ENABLED and SIMULCAST_BACKFILL_MODE are flipped on in a
-- later PR. This migration only adds inert columns and a trigger that keeps
-- one of them in sync.
--
-- simulcast_ended_at: stamped by the trigger below whenever is_simulcast
-- flips true -> false, and cleared whenever it flips false -> true. This
-- replaces using last_simulcast_check as a "finished" proxy — every
-- simulcast check re-stamps last_simulcast_check, so a proxy based on it
-- would never let the 14-day grace window expire. is_simulcast is flipped
-- from jikan_refresh.py, routes/simulcast_routes.py, and admin manual edits;
-- a trigger covers all of them without touching each call site.
--
-- gap_unresolved_at / gap_missing_episodes: surfaced to the admin once the
-- 14-day grace period elapses for a series that still has fewer ingested
-- episodes than Jikan expects. Written by a later PR's job wiring; both
-- columns stay NULL until then.

ALTER TABLE series ADD COLUMN IF NOT EXISTS simulcast_ended_at TIMESTAMPTZ;
ALTER TABLE series ADD COLUMN IF NOT EXISTS gap_unresolved_at TIMESTAMPTZ;
ALTER TABLE series ADD COLUMN IF NOT EXISTS gap_missing_episodes INT[];

-- Trigger function: stamp/clear simulcast_ended_at on is_simulcast transitions.
CREATE OR REPLACE FUNCTION set_simulcast_ended_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  IF OLD.is_simulcast IS TRUE AND NEW.is_simulcast IS FALSE THEN
    NEW.simulcast_ended_at := now();
  ELSIF OLD.is_simulcast IS FALSE AND NEW.is_simulcast IS TRUE THEN
    NEW.simulcast_ended_at := NULL;
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_set_simulcast_ended_at ON series;
CREATE TRIGGER trg_set_simulcast_ended_at
  BEFORE UPDATE OF is_simulcast ON series
  FOR EACH ROW
  WHEN (OLD.is_simulcast IS DISTINCT FROM NEW.is_simulcast)
  EXECUTE FUNCTION set_simulcast_ended_at();

-- Backfill seed: only for rows that already look "recently finished" —
-- is_simulcast=false, principal_slug present (AnimeAV1-backed), and the
-- last check happened within the last 14 days. Anything older (e.g.
-- Attack on Titan S1) or without a principal_slug (jkanime-only) is
-- intentionally left NULL, per the out-of-scope exclusions in the spec.
UPDATE series
SET simulcast_ended_at = last_simulcast_check
WHERE is_simulcast = false
  AND principal_slug IS NOT NULL
  AND last_simulcast_check IS NOT NULL
  AND last_simulcast_check > (now() - interval '14 days')
  AND simulcast_ended_at IS NULL;

-- Rollback (run manually if needed):
-- DROP TRIGGER IF EXISTS trg_set_simulcast_ended_at ON series;
-- DROP FUNCTION IF EXISTS set_simulcast_ended_at();
-- ALTER TABLE series DROP COLUMN IF EXISTS simulcast_ended_at;
-- ALTER TABLE series DROP COLUMN IF EXISTS gap_unresolved_at;
-- ALTER TABLE series DROP COLUMN IF EXISTS gap_missing_episodes;
