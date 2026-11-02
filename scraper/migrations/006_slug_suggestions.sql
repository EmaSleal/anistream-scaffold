-- Migration 006: slug_suggestions (T-009 / ADR-016)
-- Run manually in the Supabase SQL editor. It is not executed by any code path.
--
-- Why: ingest only auto-assigns an AnimeAV1 principal_slug / jkanime
-- fallback_slug on an exact, validated title match. Every other plausible
-- candidate (non-exact above the minimum score, or exact but failing
-- validation) is stored here as a pending suggestion for the admin to accept
-- or deny. A (series_id, source, slug) row is never re-created, whatever its
-- status, so a denied suggestion is never suggested again.
--
-- Idempotent: safe to run more than once.
--
-- Rollback:
--   DROP TABLE IF EXISTS slug_suggestions;

CREATE TABLE IF NOT EXISTS slug_suggestions (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    series_id     text NOT NULL,
    source        text NOT NULL CHECK (source IN ('animeav1', 'jkanime')),
    slug          text NOT NULL,
    page_title    text,
    score         int,
    page_type     text,
    page_year     int,
    page_episodes int,
    jikan_type    text,
    jikan_year    int,
    jikan_episodes int,
    checks        jsonb,
    status        text NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'accepted', 'denied')),
    created_at    timestamptz NOT NULL DEFAULT now(),
    decided_at    timestamptz,
    UNIQUE (series_id, source, slug)
);

CREATE INDEX IF NOT EXISTS slug_suggestions_status_created_idx
    ON slug_suggestions (status, created_at DESC);
