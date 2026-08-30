-- VideoExplore base schema (P1: テキスト検索 + 動画リスト可視化)
-- pgroonga は P3 で導入予定。現行は pg_trgm + ILIKE で日本語部分一致をカバー。

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE videos (
  id              BIGSERIAL PRIMARY KEY,
  path            TEXT UNIQUE NOT NULL,            -- VIDEO_DIR からの相対パス
  filename        TEXT NOT NULL,
  dirpath         TEXT NOT NULL DEFAULT '',
  sha256          TEXT,
  size_bytes      BIGINT,
  duration_sec    DOUBLE PRECISION,
  width           INTEGER,
  height          INTEGER,
  fps             DOUBLE PRECISION,
  codec           TEXT,
  mtime           TIMESTAMPTZ,
  shot_at         TIMESTAMPTZ,
  status          TEXT NOT NULL DEFAULT 'discovered',
  error           TEXT,
  thumbnail_path  TEXT,
  proxy_path      TEXT,
  profile         TEXT NOT NULL DEFAULT 'fast',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_videos_status ON videos (status);
CREATE INDEX idx_videos_filename_trgm ON videos USING gin (filename gin_trgm_ops);

-- 管理語彙(タグ日本語名 + 英語プロンプト等のエイリアス)
CREATE TABLE taxonomy (
  tag        TEXT PRIMARY KEY,
  aliases    TEXT[] NOT NULL DEFAULT '{}',
  category   TEXT,
  is_active  BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE video_tags (
  video_id    BIGINT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
  tag         TEXT NOT NULL REFERENCES taxonomy(tag) ON DELETE CASCADE,
  confidence  DOUBLE PRECISION NOT NULL DEFAULT 0,
  frames_hit  INTEGER NOT NULL DEFAULT 0,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (video_id, tag)
);
CREATE INDEX idx_video_tags_tag ON video_tags (tag);

CREATE TABLE jobs (
  id          BIGSERIAL PRIMARY KEY,
  video_id    BIGINT REFERENCES videos(id) ON DELETE CASCADE,
  stage       TEXT NOT NULL,
  state       TEXT NOT NULL DEFAULT 'pending',
  priority    INTEGER NOT NULL DEFAULT 5,
  detail      JSONB NOT NULL DEFAULT '{}',
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ===== P2 以降で使用(設計書 docs/design.md 参照) =====

CREATE TABLE scenes (
  id             BIGSERIAL PRIMARY KEY,
  video_id       BIGINT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
  start_sec      DOUBLE PRECISION NOT NULL,
  end_sec        DOUBLE PRECISION,
  keyframe_path  TEXT,
  description_ja TEXT,
  description_en TEXT,
  tags           TEXT[] NOT NULL DEFAULT '{}',
  vec_text       VECTOR(1024),
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE frames (
  id         BIGSERIAL PRIMARY KEY,
  video_id   BIGINT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
  scene_id   BIGINT REFERENCES scenes(id) ON DELETE SET NULL,
  ts_sec     DOUBLE PRECISION NOT NULL,
  path       TEXT,
  vec_img    VECTOR(768),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE detections (
  id         BIGSERIAL PRIMARY KEY,
  video_id   BIGINT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
  frame_id   BIGINT REFERENCES frames(id) ON DELETE SET NULL,
  ts_sec     DOUBLE PRECISION NOT NULL,
  cls        TEXT,
  score      DOUBLE PRECISION,
  bbox       DOUBLE PRECISION[4],
  crop_path  TEXT,
  vec        VECTOR(768),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE transcripts (
  id         BIGSERIAL PRIMARY KEY,
  video_id   BIGINT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
  start_sec  DOUBLE PRECISION NOT NULL,
  end_sec    DOUBLE PRECISION,
  text       TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
