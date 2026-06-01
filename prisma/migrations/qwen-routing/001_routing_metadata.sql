-- qwen-routing 001 — VLM routing metadata + equation/bbox columns (ADR 0001)
--
-- IMPORTANT (per CLAUDE.md "prisma db push silent fail" Hard Rule):
--   Apply via psql, NOT via `prisma db push`. Supabase auth-schema ownership
--   causes prisma db push to silently drop new public columns.
--
-- Context (ADR 0001 — docs/adr/0001-pipeline-v1-frame-selection-and-extraction.md):
--   The CLIP-embedding selector is replaced by a local VLM (Qwen2.5-VL) router
--   that emits per-frame routing metadata (contains_graph / contains_equation /
--   summary_hint). UniMERNet adds equation LaTeX; DocLayout-YOLO adds a crop bbox.
--   `frame_type` and `selection_score` already exist on slide_keyframes — not re-added.
--   `clip_embedding` / `clip_model` are kept (nullable) but marked DEPRECATED; no
--   destructive drop (Cross-Layer-Propagation + db-push-silent-fail Hard Rules).
--
-- Apply procedure:
--   Local:  docker exec supabase-db-dev psql -U supabase_admin -d postgres \
--             -f prisma/migrations/qwen-routing/001_routing_metadata.sql
--   Prod:   psql "$DIRECT_URL" -f prisma/migrations/qwen-routing/001_routing_metadata.sql
--
-- After apply:
--   1. Local verify:  docker exec supabase-db-dev psql ... -c "\d slidegen.slide_keyframes"
--                                                          -c "\d slidegen.slide_figures"
--   2. Prod  verify:  psql "$DIRECT_URL" -c "\d slidegen.slide_keyframes"
--   3. Reload PostgREST cache (only if slidegen schema is API-exposed; optional):
--        local: psql "$DATABASE_URL" -c "NOTIFY pgrst, 'reload schema'"
--        prod:  Supabase Dashboard → Settings → API → "Reload schema"
--   4. Local-first, then prod. No shortcuts.

-- Idempotent (ADD COLUMN IF NOT EXISTS) so re-running is safe.

-- slide_keyframes: VLM routing flags + summary hint
ALTER TABLE slidegen.slide_keyframes
  ADD COLUMN IF NOT EXISTS contains_graph    boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS contains_equation boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS summary_hint      text;

COMMENT ON COLUMN slidegen.slide_keyframes.contains_graph IS
  'VLM router (Qwen2.5-VL): frame contains a chart/graph/diagram region (ADR 0001).';
COMMENT ON COLUMN slidegen.slide_keyframes.contains_equation IS
  'VLM router (Qwen2.5-VL): frame contains a mathematical equation (ADR 0001).';
COMMENT ON COLUMN slidegen.slide_keyframes.summary_hint IS
  'VLM router (Qwen2.5-VL): brief description of the slide content (ADR 0001).';
COMMENT ON COLUMN slidegen.slide_keyframes.clip_embedding IS
  'DEPRECATED (ADR 0001): CLIP selection replaced by Qwen2.5-VL routing. Kept nullable for back-compat; no new writes.';
COMMENT ON COLUMN slidegen.slide_keyframes.clip_model IS
  'DEPRECATED (ADR 0001): vestigial from CLIP selection.';

-- slide_figures: equation LaTeX + crop bounding box
ALTER TABLE slidegen.slide_figures
  ADD COLUMN IF NOT EXISTS extracted_latex text,
  ADD COLUMN IF NOT EXISTS bbox            jsonb;

COMMENT ON COLUMN slidegen.slide_figures.extracted_latex IS
  'Equation OCR (UniMERNet): LaTeX transcription for kind=equation figures (ADR 0001).';
COMMENT ON COLUMN slidegen.slide_figures.bbox IS
  'DocLayout-YOLO crop region for this figure, JSON {x,y,w,h} in source-frame pixels (ADR 0001).';
