-- slidegen-init 001 — create slide_* tables
--
-- IMPORTANT (per CLAUDE.md "prisma db push silent fail" Hard Rule):
--   Apply via psql, NOT via `prisma db push`. Supabase auth-schema ownership
--   causes prisma db push to silently drop new public tables.
--
-- Apply procedure:
--   Local:  docker exec supabase-db-dev psql -U supabase_admin -d postgres -f 001_create_slide_tables.sql
--   Prod:   psql "$DIRECT_URL" -f prisma/migrations/slidegen-init/001_create_slide_tables.sql
--
-- After apply:
--   1. Local verify:  docker exec supabase-db-dev psql ... -c "\d slide_decks"
--   2. Prod  verify:  psql "$DIRECT_URL" -c "\d slide_decks"
--   3. Reload PostgREST schema cache:
--        local: psql "$DATABASE_URL" -c "NOTIFY pgrst, 'reload schema'"
--               docker restart supabase-rest-dev
--        prod:  Supabase Dashboard → Settings → API → "Reload schema"
--   4. Local-first, then prod. No shortcuts.

BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------
-- slide_decks
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS slide_decks (
  id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  video_id          VARCHAR(11) NOT NULL,
  mandala_id        UUID,
  user_id           UUID,
  lang              VARCHAR(5)  NOT NULL DEFAULT 'ko',
  status            VARCHAR(20) NOT NULL DEFAULT 'queued',
  slides_json       JSONB,
  slide_count       INTEGER,
  google_slides_id  TEXT,
  google_slides_url TEXT,
  pdf_url           TEXT,
  vector_pdf_url    TEXT,
  -- SHA-256 of video_id + template_version + generator_version
  v2_fingerprint    VARCHAR(64),
  generator_version VARCHAR(30) NOT NULL DEFAULT 'slidegen-v1',
  error             TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_slide_decks_video_version UNIQUE (video_id, generator_version)
);

CREATE INDEX IF NOT EXISTS idx_slide_decks_video_id
  ON slide_decks (video_id);
CREATE INDEX IF NOT EXISTS idx_slide_decks_status
  ON slide_decks (status);
CREATE INDEX IF NOT EXISTS idx_slide_decks_mandala_id
  ON slide_decks (mandala_id);

-- ---------------------------------------------------------------
-- slide_slides
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS slide_slides (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  deck_id     UUID        NOT NULL REFERENCES slide_decks(id) ON DELETE CASCADE,
  position    INTEGER     NOT NULL,
  layout      VARCHAR(30) NOT NULL,
  title       TEXT,
  body_json   JSONB,
  notes       TEXT,
  -- 0-based index into v2 segments[]; NULL for cover/transition slides
  section_ref INTEGER
);

CREATE INDEX IF NOT EXISTS idx_slide_slides_deck_position
  ON slide_slides (deck_id, position);

-- ---------------------------------------------------------------
-- slide_figures
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS slide_figures (
  id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  deck_id             UUID        NOT NULL REFERENCES slide_decks(id) ON DELETE CASCADE,
  slide_id            UUID        REFERENCES slide_slides(id) ON DELETE SET NULL,
  -- CV service internal figure id (yt-vid + frame-offset hash)
  cv_figure_id        VARCHAR(80),
  -- "chart" | "diagram" | "equation" | "table" | "screenshot" | "keyframe"
  kind                VARCHAR(20) NOT NULL,
  png_url             TEXT        NOT NULL,
  vector_pdf_url      TEXT,
  vector_svg_url      TEXT,
  caption             TEXT,
  timestamp_sec       INTEGER,
  -- JSON array of atom indices from v2 analysis.atoms[]
  atom_refs           JSONB,
  -- "pending" | "verified" | "rejected"
  verification_status VARCHAR(20) NOT NULL DEFAULT 'pending',
  extraction_conf     REAL
);

CREATE INDEX IF NOT EXISTS idx_slide_figures_deck_id
  ON slide_figures (deck_id);
CREATE INDEX IF NOT EXISTS idx_slide_figures_verification_status
  ON slide_figures (verification_status);

-- ---------------------------------------------------------------
-- slide_keyframes
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS slide_keyframes (
  id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  youtube_video_id VARCHAR(11)  NOT NULL,
  section_index    INTEGER      NOT NULL,
  timestamp_sec    REAL         NOT NULL,
  -- "scene_change" | "title_card" | "diagram" | "chart" | "face" | "b_roll"
  frame_type       VARCHAR(16)  NOT NULL,
  type_confidence  REAL,
  selection_score  REAL,
  clip_model       VARCHAR(32)  NOT NULL DEFAULT 'clip-vit-b32',
  -- pgvector 512-dim CLIP embedding; HNSW index below
  clip_embedding   vector(512),
  quality_score    REAL,
  is_selected      BOOLEAN      NOT NULL DEFAULT FALSE,
  created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_slide_keyframes_video_section
  ON slide_keyframes (youtube_video_id, section_index);
CREATE INDEX IF NOT EXISTS idx_slide_keyframes_is_selected
  ON slide_keyframes (is_selected);

-- HNSW cosine index on clip_embedding (pgvector).
-- ef_construction=64, m=16 are safe defaults for 512-dim CLIP vectors.
CREATE INDEX IF NOT EXISTS idx_slide_keyframes_clip_hnsw
  ON slide_keyframes
  USING hnsw (clip_embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- ---------------------------------------------------------------
-- slide_caption_segments
-- BGE-M3 (1024-dim) text embeddings of caption segments.
-- Populated by captions.py before keyframe selection.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS slide_caption_segments (
  id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  youtube_video_id VARCHAR(11)  NOT NULL,
  from_sec         REAL         NOT NULL,
  to_sec           REAL         NOT NULL,
  text             TEXT         NOT NULL,
  -- True when cosine distance to the previous segment exceeds the topic-change threshold
  is_topic_change  BOOLEAN      NOT NULL DEFAULT FALSE,
  -- pgvector 1024-dim BGE-M3 embedding; HNSW index below
  embedding        vector(1024),
  model_version    VARCHAR(32)  NOT NULL DEFAULT 'bge-m3',
  created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_slide_caption_segments_video_id
  ON slide_caption_segments (youtube_video_id);

-- HNSW cosine index on BGE-M3 1024-dim embedding.
-- ef_construction=64, m=16: conservative defaults; tune upward if recall is low.
CREATE INDEX IF NOT EXISTS idx_slide_caption_segments_embedding_hnsw
  ON slide_caption_segments
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- ---------------------------------------------------------------
-- slide_jobs
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS slide_jobs (
  id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  deck_id    UUID        REFERENCES slide_decks(id) ON DELETE SET NULL,
  card_id    TEXT,
  video_id   VARCHAR(11),
  -- "resolve" | "fetch_v2" | "cv_extract" | "plan" | "build_slides" | "export_pdf"
  stage      VARCHAR(20) NOT NULL,
  -- "queued" | "running" | "done" | "error"
  status     VARCHAR(20) NOT NULL DEFAULT 'queued',
  detail     JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_slide_jobs_status
  ON slide_jobs (status);

COMMIT;
