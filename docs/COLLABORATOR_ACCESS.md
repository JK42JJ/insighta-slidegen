# Collaborator Database Access (Least-Privilege)

How to give a collaborator access to work on `insighta-slidegen` **without** handing
over full control of the shared Insighta database.

## The problem

`insighta-slidegen` shares Insighta's Supabase database. The obvious credentials are
too powerful to share:

- **`SUPABASE_SERVICE_ROLE_KEY`** — bypasses Row-Level Security; full read/write to
  **every** Insighta table. **Never share it.**
- **Admin `DATABASE_URL` / `DIRECT_URL`** — connect as a privileged role; full SQL
  access. **Never share these.**

A collaborator only needs to:

- **read** a handful of Insighta tables (the v2 summary + video + caption data), and
- **read/write** the project's own `slide_*` tables.

## The model: a dedicated schema + a scoped role

All slide_* tables live in a dedicated **`slidegen`** Postgres schema (not `public`).
A dedicated login role **`slidegen_rw`**:

- **owns** the `slidegen` schema → full read/write **and** can run future slide_*
  migrations;
- has **`SELECT` only** on exactly six Insighta `public` tables:
  `video_rich_summaries`, `youtube_videos`, `video_captions`, `user_local_cards`,
  `user_video_states`, `recommendation_cache`;
- has **no access to anything else** — `auth`, `credentials`, `quota_*`, and every other
  table stay invisible.

This matches Insighta's **Service ≠ System** domain-separation rule and keeps grants
trivial: new slide_* tables created by the role are automatically owned by it, no extra
grant needed.

```
                    Insighta Supabase DB
 ┌───────────────────────────────────────────────────────────┐
 │  schema: public  (owned by insighta admin)                 │
 │    video_rich_summaries  ─┐                                │
 │    youtube_videos         │  SELECT only                   │
 │    video_captions         ├───────────────►  slidegen_rw   │
 │    user_local_cards       │                  (collaborator)│
 │    user_video_states      │                       │        │
 │    recommendation_cache  ─┘                       │ OWNS   │
 │    auth.* / credentials / quota_*  ── NO ACCESS   ▼        │
 │  schema: slidegen  (owned by slidegen_rw)                  │
 │    slide_decks / slide_slides / slide_figures /            │
 │    slide_keyframes / slide_caption_segments / slide_jobs   │
 │      └── full read + write + migrate                        │
 └───────────────────────────────────────────────────────────┘
```

## Setup (database admin / project owner)

Apply, **local-first then prod**, as a DB admin (`postgres` / `supabase_admin`):

```bash
# 1) Schema + slide_* tables
psql "$DIRECT_URL" -f prisma/migrations/slidegen-init/001_create_slide_tables.sql

# 2) Edit 002 to set a strong password (locally; never commit it), then apply:
#    in 002_slidegen_role_and_grants.sql replace <SET-A-STRONG-PASSWORD>
#    e.g. openssl rand -base64 32
psql "$DIRECT_URL" -f prisma/migrations/slidegen-init/002_slidegen_role_and_grants.sql
```

Verify (queries are at the bottom of `002_*.sql`): the role is not a superuser, has
exactly the six `public` SELECT grants, and owns the `slidegen` schema/tables.

## What to give the collaborator

A `.env` built around the **scoped role** — and nothing else:

```
DATABASE_URL = postgresql://slidegen_rw:<password>@<db-host>:5432/postgres
DIRECT_URL   = postgresql://slidegen_rw:<password>@<db-host>:5432/postgres
SUPABASE_URL = https://<ref>.supabase.co        # public value, OK to share
# SUPABASE_SERVICE_ROLE_KEY → DO NOT SHARE (slidegen uses Prisma/the role, not this key)
```

Notes:
- slidegen talks to the DB through **Prisma** (the connection string), so the
  collaborator does **not** need the service-role key for database work.
- **Supabase Storage** (asset uploads for generated slides) is the only thing that
  normally needs a Supabase key. Keep that on the owner/CV-service side, or scope it
  with a Storage bucket policy on `slidegen-assets` — do **not** hand out the
  service-role key for it.
- Use the **direct connection (port 5432)** for the scoped role. If you route through
  Supabase's pooler (port 6543), the username takes the `slidegen_rw.<project_ref>`
  tenant form — test it before sharing.
- Hand the connection string over a **secure channel**, never in chat or a committed file.

## Rotate / off-board

```sql
-- rotate the password
ALTER ROLE slidegen_rw PASSWORD '<new-secret>';

-- revoke one table
REVOKE SELECT ON public.<table> FROM slidegen_rw;

-- full off-board
REASSIGN OWNED BY slidegen_rw TO supabase_admin;
DROP OWNED BY slidegen_rw;
DROP ROLE slidegen_rw;
```
