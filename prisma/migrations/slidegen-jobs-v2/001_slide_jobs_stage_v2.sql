-- slidegen-jobs-v2 001 — slide_jobs v2: A-pipeline stages + self-correction/timeout tracking
--
-- PR-G. stage/failure_stage CHECK domain is the A-pipeline stage set (ADR 0003
-- D2 harness); failure_stage is the physical column for ADR 0004 failure-stage
-- attribution (recognition family vs build family → B-switch judgement).
--
-- IMPORTANT (per CLAUDE.md "prisma db push silent fail" Hard Rule):
--   Apply via psql, NOT via `prisma db push`. Supabase auth-schema ownership
--   causes prisma db push to silently drop new columns.
--
-- Apply procedure:
--   Local:  docker exec supabase-db-dev psql -U supabase_admin -d postgres \
--             -f 001_slide_jobs_stage_v2.sql
--   Prod:   psql "$DIRECT_URL" -f prisma/migrations/slidegen-jobs-v2/001_slide_jobs_stage_v2.sql
--
-- GUARD (run BEFORE applying):
--   SELECT count(*) FROM slidegen.slide_jobs;
--   Must be 0. Rows carrying a v1 stage value (resolve|fetch_v2|cv_extract|
--   plan|build_slides|export_pdf) would fail the new stage CHECK — if any
--   exist, STOP and map them to v2 stages first. (Expected 0: no live
--   slide_jobs write path ships before PR-G.)
--
-- After apply:
--   1. Verify:  \d slidegen.slide_jobs  (5 new columns + 2 CHECKs + partial index)
--   2. Reload PostgREST schema cache:
--        local: psql "$DATABASE_URL" -c "NOTIFY pgrst, 'reload schema'"
--        prod:  Supabase Dashboard → Settings → API → "Reload schema"
--   3. Local-first, then prod. No shortcuts.

BEGIN;

SET search_path TO slidegen, public;

-- v2 pipeline-A stage set — 1:1 with ADR 0004 B-switch attribution families:
--   detect / select / numerize = recognition family (failures here argue for B)
--   build / validate           = build family (failures here argue for prompt/harness fixes)
-- stage:  "acquire" | "keyframe" | "detect" | "select" | "numerize" | "build" | "validate"
-- status stays the 4-value set (queued | running | done | error); a timed-out
-- job is expressed as status='error' + last_error='timeout' + failure_stage
-- (decided PR-G: no 'timeout' status, no heartbeat — timeout_at only).

ALTER TABLE slide_jobs
  ADD COLUMN attempt_count INTEGER     NOT NULL DEFAULT 0,
  -- ADR 0004 G2 gate: self-correction attempts <= 2.0 → default budget per job.
  ADD COLUMN max_attempts  INTEGER     NOT NULL DEFAULT 2,
  -- Stage deadline stamped by the orchestrator at stage start; a watcher treats
  -- (now() > timeout_at AND status = 'running') as a timeout.
  ADD COLUMN timeout_at    TIMESTAMPTZ,
  ADD COLUMN last_error    TEXT,
  -- Stage attributed on failure (ADR 0004 aggregation); same domain as stage.
  ADD COLUMN failure_stage VARCHAR(20);

ALTER TABLE slide_jobs
  ADD CONSTRAINT chk_slide_jobs_stage CHECK (
    stage IN ('acquire', 'keyframe', 'detect', 'select', 'numerize', 'build', 'validate')
  ),
  ADD CONSTRAINT chk_slide_jobs_failure_stage CHECK (
    failure_stage IS NULL
    OR failure_stage IN ('acquire', 'keyframe', 'detect', 'select', 'numerize', 'build', 'validate')
  );

-- ADR 0004 aggregation: failure counts per stage (only failed jobs indexed).
CREATE INDEX IF NOT EXISTS idx_slide_jobs_failure_stage
  ON slide_jobs (failure_stage)
  WHERE failure_stage IS NOT NULL;

COMMIT;

-- ---------------------------------------------------------------
-- ROLLBACK (manual, reverse order):
--   BEGIN;
--   SET search_path TO slidegen, public;
--   DROP INDEX IF EXISTS idx_slide_jobs_failure_stage;
--   ALTER TABLE slide_jobs
--     DROP CONSTRAINT IF EXISTS chk_slide_jobs_failure_stage,
--     DROP CONSTRAINT IF EXISTS chk_slide_jobs_stage;
--   ALTER TABLE slide_jobs
--     DROP COLUMN IF EXISTS failure_stage,
--     DROP COLUMN IF EXISTS last_error,
--     DROP COLUMN IF EXISTS timeout_at,
--     DROP COLUMN IF EXISTS max_attempts,
--     DROP COLUMN IF EXISTS attempt_count;
--   COMMIT;
-- ---------------------------------------------------------------
