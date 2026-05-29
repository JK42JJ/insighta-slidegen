-- slidegen-init 002 — least-privilege collaborator role + grants
--
-- Creates a scoped login role `slidegen_rw` that can:
--   * read/write all tables in the `slidegen` schema (its own domain), and
--   * SELECT-only on the three insighta CONTENT tables it needs.
-- It has NO access to user-data tables, auth, credentials, or anything else.
--
-- WHO RUNS THIS: a DB admin, AFTER 001. Easiest path:
--   Supabase Dashboard → SQL Editor → paste this file → Run.
--   (Replace <SET-A-STRONG-PASSWORD> first — e.g. `openssl rand -hex 32`.)
--
-- NOTE (Supabase): this uses plain GRANTs (no ALTER ... OWNER / role-membership),
-- which the SQL Editor handles reliably. Trade-off: slidegen_rw is NOT the table
-- owner, so future slide_* schema changes (ALTER/DROP) are run by an admin; the
-- collaborator's day-to-day row read/write is fully covered. New tables the role
-- creates itself (it has CREATE on the schema) are owned by it.
--
-- SECURITY: never commit the real password; never paste it in chat. Hand the
-- final connection string to the collaborator over a secure channel.
--
-- All statements are idempotent / safe to re-run.

-- ---------------------------------------------------------------
-- 1) Dedicated login role (no superuser, no createdb/createrole)
-- ---------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'slidegen_rw') THEN
    CREATE ROLE slidegen_rw LOGIN PASSWORD '<SET-A-STRONG-PASSWORD>';
  END IF;
END
$$;

-- ---------------------------------------------------------------
-- 2) Full read/write on the slidegen schema (the role's own domain)
-- ---------------------------------------------------------------
GRANT USAGE, CREATE ON SCHEMA slidegen TO slidegen_rw;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA slidegen TO slidegen_rw;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA slidegen TO slidegen_rw;

-- Future tables/sequences created in slidegen are auto-granted to the role.
ALTER DEFAULT PRIVILEGES IN SCHEMA slidegen
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO slidegen_rw;
ALTER DEFAULT PRIVILEGES IN SCHEMA slidegen
  GRANT USAGE, SELECT ON SEQUENCES TO slidegen_rw;

-- ---------------------------------------------------------------
-- 3) READ-ONLY on the three insighta CONTENT tables slidegen consumes.
--    User-data tables (user_local_cards / user_video_states /
--    recommendation_cache) are intentionally NOT granted — so a leaked
--    credential exposes zero user data. Add them later only if the
--    `--card <id>` resolution path is needed.
-- ---------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO slidegen_rw;
GRANT SELECT ON
  public.video_rich_summaries,
  public.youtube_videos,
  public.video_captions
TO slidegen_rw;

-- ---------------------------------------------------------------
-- VERIFY (run as admin):
--   SELECT table_schema, table_name, privilege_type
--   FROM information_schema.role_table_grants
--   WHERE grantee = 'slidegen_rw'
--   ORDER BY table_schema, table_name;
--   -- expect: slidegen.slide_* → SELECT/INSERT/UPDATE/DELETE
--   --         public (3 content tables) → SELECT only
--
-- ROTATE / OFF-BOARD:
--   ALTER ROLE slidegen_rw PASSWORD '<new-secret>';      -- rotate
--   REVOKE SELECT ON public.<table> FROM slidegen_rw;    -- revoke a read
--   DROP OWNED BY slidegen_rw; DROP ROLE slidegen_rw;    -- full off-board
-- ---------------------------------------------------------------
