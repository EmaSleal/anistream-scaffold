-- Migration 005: Reset false simulcast gap markers — ONE-OFF DATA RESET
-- Run manually in the Supabase SQL editor, AFTER deploying the paginated
-- simulcast reads (T-003 / ADR-010). It is not executed by any code path.
--
-- Why: before T-003, get_expired_gap_candidates read episodes for every
-- candidate series in a single request, which PostgREST truncates at ~1000
-- rows. Series whose episodes fell past the cap looked incomplete, so the
-- expired-gap pass wrote false markers (e.g. a 13/13 series marked as
-- missing 12 episodes). See P-010.
--
-- What: clears gap_unresolved_at and gap_missing_episodes on every series
-- that currently has a marker. Real gaps are re-detected and re-marked by the
-- next scheduler run with SIMULCAST_GRACE_ENABLED=1, now with complete reads.
--
-- Idempotent: running it again is a no-op once no marker remains.
-- No schema change.

UPDATE series
SET gap_unresolved_at = NULL,
    gap_missing_episodes = NULL
WHERE gap_unresolved_at IS NOT NULL;
