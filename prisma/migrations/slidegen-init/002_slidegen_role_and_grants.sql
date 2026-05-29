-- slidegen-init 002 — least-privilege collaborator role + grants
--
-- Implements the access model in docs/COLLABORATOR_ACCESS.md:
--   * a dedicated role `slidegen_rw` OWNS the `slidegen` schema (full read+write,
--     and can run future slide_* migrations);
--   * `slidegen_rw` has SELECT-ONLY on exactly the insighta public tables slidegen
--     consumes — and NO access to anything else (auth, credentials, quota_*, etc.).
--
-- WHO RUNS THIS: a database admin (postgres / supabase_admin), AFTER 001.
-- The collaborator is given a connection string using THIS role — NEVER the
-- service-role key or the admin DATABASE_URL/DIRECT_URL.
--
-- SECURITY:
--   * Replace <SET-A-STRONG-PASSWORD> with a freshly generated secret
--     (e.g. `openssl rand -base64 32`). Do this in your editor, locally.
--   * NEVER commit the real password. NEVER paste it into chat. Hand the final
--     connection string to the collaborator over a secure channel.
--
-- Apply procedure (local-first, then prod):
--   1. Run 001 first (creates `slidegen` schema + slide_* tables).
--   2. psql "$DIRECT_URL" -f 002_slidegen_role_and_grants.sql   (as admin)
--   3. Verify (see bottom of file).

BEGIN;

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
-- 2) Own the slidegen schema → full control of slide_* + future tables
-- ---------------------------------------------------------------
ALTER SCHEMA slidegen OWNER TO slidegen_rw;

-- Reassign tables created by admin in 001 to the role (so it can ALTER/DROP
-- them in future migrations, not just DML).
ALTER TABLE slidegen.slide_decks            OWNER TO slidegen_rw;
ALTER TABLE slidegen.slide_slides           OWNER TO slidegen_rw;
ALTER TABLE slidegen.slide_figures          OWNER TO slidegen_rw;
ALTER TABLE slidegen.slide_keyframes        OWNER TO slidegen_rw;
ALTER TABLE slidegen.slide_caption_segments OWNER TO slidegen_rw;
ALTER TABLE slidegen.slide_jobs             OWNER TO slidegen_rw;

-- ---------------------------------------------------------------
-- 3) READ-ONLY on exactly the insighta public tables slidegen consumes.
--    NOTHING else in public is granted → all other tables stay invisible.
-- ---------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO slidegen_rw;
-- PG15+: PUBLIC no longer has CREATE on public, but be explicit/defensive.
REVOKE CREATE ON SCHEMA public FROM slidegen_rw;

GRANT SELECT ON
  public.video_rich_summaries,
  public.youtube_videos,
  public.video_captions,
  public.user_local_cards,
  public.user_video_states,
  public.recommendation_cache
TO slidegen_rw;

-- ---------------------------------------------------------------
-- 4) Make the pgvector extension type usable (USAGE on types is granted to
--    PUBLIC by default, so this is usually a no-op; harmless to be explicit).
-- ---------------------------------------------------------------
-- (no-op placeholder; vector type usage is public)

COMMIT;

-- ---------------------------------------------------------------
-- VERIFY (run as admin):
--   -- role exists, not superuser:
--   SELECT rolname, rolsuper, rolcreatedb, rolcreaterole
--   FROM pg_roles WHERE rolname = 'slidegen_rw';
--
--   -- exactly the 6 public SELECT grants, nothing else in public:
--   SELECT table_schema, table_name, privilege_type
--   FROM information_schema.role_table_grants
--   WHERE grantee = 'slidegen_rw' AND table_schema = 'public'
--   ORDER BY table_name;
--
--   -- owns the slidegen schema + its tables:
--   SELECT n.nspname AS schema, c.relname AS table, pg_get_userbyid(c.relowner) AS owner
--   FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
--   WHERE n.nspname = 'slidegen' AND c.relkind = 'r';
-- ---------------------------------------------------------------

-- ---------------------------------------------------------------
-- ROTATE / REVOKE (ops notes):
--   Rotate password:  ALTER ROLE slidegen_rw PASSWORD '<new-secret>';
--   Revoke a table:   REVOKE SELECT ON public.<table> FROM slidegen_rw;
--   Off-board fully:  REASSIGN OWNED BY slidegen_rw TO supabase_admin;
--                     DROP OWNED BY slidegen_rw; DROP ROLE slidegen_rw;
-- ---------------------------------------------------------------
