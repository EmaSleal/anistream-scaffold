-- Migration 007: download_queue (T-015 / ADR-019)
-- Run manually in the Supabase SQL editor. It is not executed by any code path.
--
-- Why: an admin can queue a whole series for download. The scheduler worker
-- sends the queued episodes to the NAS one at a time (serial), resolving the
-- short-lived CDN URL only when an item is dispatched.
--
-- The partial unique index guarantees a (series_id, episode_number) pair is
-- never active (queued/downloading) twice, even under concurrent enqueues.
-- Finished rows (done/failed) are kept as history and do not block re-queuing.
--
-- Idempotent: safe to run more than once.
--
-- Rollback:
--   DROP TABLE IF EXISTS download_queue;

CREATE TABLE IF NOT EXISTS download_queue (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    series_id      text NOT NULL,
    episode_number int NOT NULL,
    source         text NOT NULL DEFAULT 'jkanime',
    status         text NOT NULL DEFAULT 'queued'
                   CHECK (status IN ('queued', 'downloading', 'done', 'failed')),
    nas_job_id     text,
    error          text,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    started_at     timestamptz,
    finished_at    timestamptz
);

CREATE UNIQUE INDEX IF NOT EXISTS download_queue_active_uniq
    ON download_queue (series_id, episode_number)
    WHERE status IN ('queued', 'downloading');

CREATE INDEX IF NOT EXISTS download_queue_status_created_idx
    ON download_queue (status, created_at);
