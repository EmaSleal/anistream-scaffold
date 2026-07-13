CREATE TABLE user_continue_watching (
  user_id          TEXT        NOT NULL,
  franchise_key    TEXT        NOT NULL,
  series_id        TEXT        NOT NULL,
  episode_id       TEXT        NOT NULL,
  progress_sec     INT         NOT NULL DEFAULT 0,
  next_episode_id  TEXT,
  updated_at       TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (user_id, franchise_key)
);
CREATE INDEX idx_ucw_user_updated ON user_continue_watching (user_id, updated_at DESC);
