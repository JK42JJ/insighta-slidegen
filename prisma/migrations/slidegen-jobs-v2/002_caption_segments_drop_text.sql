-- slidegen-jobs-v2 002 — slide_caption_segments: drop verbatim caption text (ADR 0003 D6)
--
-- PR-G. Captions are NOT stored verbatim in slidegen — embeddings + boundary
-- flags only. After this migration the table keeps: timing (from_sec/to_sec),
-- the 1024-dim BGE-M3 embedding, and is_topic_change.
--
-- DESTRUCTIVE on existing rows, but the source text is preserved in insighta's
-- video_captions (read-only source); rows are reconstructable by re-running
-- captions.py. Prod apply requires its own explicit approval (PR-G 승인 3).
--
-- IMPORTANT: apply via psql, NOT `prisma db push` (Supabase silent-fail rule).
--
-- Apply procedure:
--   Local:  docker exec supabase-db-dev psql -U supabase_admin -d postgres \
--             -f 002_caption_segments_drop_text.sql
--   Prod:   psql "$DIRECT_URL" -f prisma/migrations/slidegen-jobs-v2/002_caption_segments_drop_text.sql
--
-- After apply:
--   1. Verify:  \d slidegen.slide_caption_segments  (NO text column)
--   2. Reload PostgREST schema cache (local NOTIFY / prod Dashboard reload).

BEGIN;

SET search_path TO slidegen, public;

ALTER TABLE slide_caption_segments
  DROP COLUMN IF EXISTS text;

COMMIT;

-- ---------------------------------------------------------------
-- ROLLBACK (manual):
--   ALTER TABLE slidegen.slide_caption_segments ADD COLUMN text TEXT;
--   (Re-added nullable — the original NOT NULL cannot be restored without a
--   backfill. Backfill by re-running captions.py from insighta video_captions.)
-- ---------------------------------------------------------------
