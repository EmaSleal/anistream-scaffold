-- Migration 001: Add principal_slug column to series table
-- Run manually in the Supabase SQL editor.
-- This column stores the AnimeAV1 slug used as the primary HLS stream source.
-- series.animeflv_slug remains untouched.

ALTER TABLE series ADD COLUMN IF NOT EXISTS principal_slug TEXT;

-- Backfill: copy animeflv_slug into principal_slug for existing rows.
-- Only updates rows where principal_slug is NULL and animeflv_slug is set.
-- Safe to re-run; will not overwrite rows already set.
UPDATE series
SET principal_slug = animeflv_slug
WHERE animeflv_slug IS NOT NULL
  AND principal_slug IS NULL;

-- Rollback (run manually if needed):
-- ALTER TABLE series DROP COLUMN principal_slug;
