# Onboarding — Clone & Start with Claude Code

A step-by-step guide for a new contributor to clone `insighta-slidegen` and start
working with **Claude Code**. Follow the steps top to bottom. Most commands are
copy-paste ready.

> **Shortcut:** You can hand this file to Claude Code directly — open the repo in
> Claude Code and say: *"Read `docs/ONBOARDING.md` and set up the project."* It
> will run the steps below for you, then you continue with the slash-command workflow
> in [Step 7](#step-7--work-with-claude-code).

> **Project status:** v1 is a **scaffold** — the CV pipeline, Google Slides build, and
> vector-PDF compositor are typed **stubs** (they compile and the tests pass, but the
> real logic is not yet implemented). The first real task is the architecture research
> in **Issue #1**. So "starting the project" means: set up the dev environment, then
> implement features via the Claude Code workflow.

---

## What this project does (1 paragraph)

`insighta-slidegen` turns an Insighta video card's **v2 rich-summary** into journal-grade
slides: it selects ~12 key frames from the video, redraws figures (charts/tables/formulas)
as **vector @300dpi**, and builds a **Google Slides** deck plus a **true-vector PDF**.
It reads Insighta's Supabase **read-only** and writes only its own `slide_*` tables.
See [`docs/PRD.md`](./PRD.md) for the full design (the frame-selection pipeline is a
**DRAFT** pending the Issue #1 research).

---

## Prerequisites

| Tool | Version | Why | Install |
|------|---------|-----|---------|
| **git** | any recent | clone | https://git-scm.com |
| **Node.js** | **20.x** | TS orchestrator | https://nodejs.org or `nvm install 20` |
| **npm** | ≥ 9 | JS deps | ships with Node |
| **Python** | **≥ 3.11** | Slides builder (`py/`) + CV service (`mac-mini/`) | https://python.org or `pyenv` |
| **Claude Code** | latest | the workflow (slash commands) | https://claude.com/claude-code |
| **gh** (GitHub CLI) | optional | PRs / issues | https://cli.github.com |
| **psql** | optional | apply DB DDL | Postgres client |
| **Docker** | optional | run the CV service container | https://docker.com |

You do **NOT** need your own Supabase or any local database. The owner gives you a
**scoped database connection string** (the `slidegen_rw` role) that has read-only access
to Insighta content + read/write on the `slidegen` schema only — see
[`docs/COLLABORATOR_ACCESS.md`](./COLLABORATOR_ACCESS.md).

You will need, **from the project owner** (these are NOT in the repo — it is public):
- The **`slidegen_rw` connection strings** (`DATABASE_URL`, `DIRECT_URL`, `SUPABASE_URL`).
  These point at the shared DB through a least-privilege role — **not** the service-role key.
- Google OAuth client id/secret (only when building a real deck — Slides + Drive API).
- CV service URL + token (only if you run the Mac Mini CV pipeline).

---

## Step 1 — Clone

```bash
git clone https://github.com/JK42JJ/insighta-slidegen.git
cd insighta-slidegen
```

## Step 2 — Install JavaScript deps + generate the Prisma client

```bash
npm install
npm run prisma:generate
```

## Step 3 — Set up Python (optional unless you touch Slides/CV)

The Slides builder lives in `py/`; the CV pipeline lives in `mac-mini/slidegen-service/`.

```bash
# Slides + vector-PDF builder
cd py
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cd ..

# CV service (heavy: CLIP/YOLO/OCR — only if you work on frame extraction)
# cd mac-mini/slidegen-service
# python3 -m venv .venv && source .venv/bin/activate
# pip install -r requirements.txt
# cd ../..
```

## Step 4 — Configure environment

```bash
cp .env.example .env
```

Open `.env`. Paste the **three lines the owner gave you** (the `slidegen_rw` scoped
role). They look like this (the owner fills in the real `<...>` values — do not guess them):

```
DATABASE_URL="postgresql://slidegen_rw.<PROJECT_REF>:<PASSWORD>@<POOLER_HOST>:6543/postgres?pgbouncer=true"
DIRECT_URL="postgresql://slidegen_rw.<PROJECT_REF>:<PASSWORD>@<POOLER_HOST>:5432/postgres"
SUPABASE_URL="https://<PROJECT_REF>.supabase.co"
```

Notes:
- **Do NOT set `SUPABASE_SERVICE_ROLE_KEY`** — slidegen connects via Prisma (the
  connection string above), so you never need it. (Asset/Storage uploads stay owner-side.)
- **Keep `SLIDEGEN_MODE=dev`.**
- **Leave `VISION_API_PROVIDER` and `GEMINI_API_KEY` blank** — they are **prod-only**;
  setting them in dev triggers real API calls/billing (forbidden by the project rules).
- `SLIDEGEN_CV_SERVICE_URL` / `SLIDEGEN_CV_SERVICE_TOKEN` — leave as-is unless you run the
  CV service (default port `8077`).
- `GOOGLE_OAUTH_*` — only needed to build a real deck (Step 8b).

`.env` is gitignored — **never commit it**.

## Step 5 — Database (nothing to do as a collaborator)

The `slide_*` tables (in a dedicated **`slidegen`** schema) and the scoped `slidegen_rw`
role are **already provisioned on the shared database by the owner**. With the connection
strings from Step 4, you are ready — **you do not run any DB setup**, and you do not need
a local database.

What your access allows (and nothing else):

```
read-only   →  public.video_rich_summaries / youtube_videos / video_captions
read+write  →  slidegen.slide_*  (your project's own tables)
no access   →  user data, auth, secrets, everything else
```

Quick check (optional):
```bash
npx prisma db execute --stdin <<< "select count(*) from video_rich_summaries;"
```

> **Owner only** (provisioning / schema changes): apply
> `prisma/migrations/slidegen-init/001_*.sql` then `002_*.sql` via the Supabase SQL
> Editor, and see [`docs/COLLABORATOR_ACCESS.md`](./COLLABORATOR_ACCESS.md). `prisma db
> push` is **banned** (silent-fail on Supabase) — always raw SQL, local-first.

## Step 6 — Verify the setup

```bash
npm run typecheck     # tsc --noEmit (must pass)
npm test              # vitest
cd py && pytest && cd ..   # python tests (if you set up the venv)
```

All three should pass on a clean clone.

---

## Step 7 — Work with Claude Code

Open the repo folder in Claude Code (CLI, desktop, or IDE extension). The project ships
its own rules and workflow:

- **`CLAUDE.md`** — project rules (auto-loaded by Claude Code). Inherits Insighta's Hard
  Rules: *plan → approve → execute*, `.env` immutable, DB local-first + raw SQL DDL,
  no LLM API outside the prod path, and the **public-repo essentials-only** rule.
- **Slash commands** (`.claude/commands/`): `/init`, `/work`, `/save`, `/verify`,
  `/tidy`, `/retro`, `/status`.
- **Skills** (`.claude/skills/`): `/ship` (commit → PR → merge → deploy-verify) and
  `/slidegen` (build a deck from a card/video).

**Start every session with `/init`** — it boots project context and shows status:

```
/init
```

Typical loop:
```
/init      # boot context
/work      # pick a unit of work, plan, execute
/verify    # pre-push gate (typecheck + tests + DPI gate + public-leak self-check)
/ship      # commit → PR → merge → CI verify
/save      # record progress + lessons to project memory
```

Notes for a fresh clone:
- **Project memory** lives outside the repo (`~/.claude/projects/<your-repo-path>/memory/`)
  and is **per-machine** — yours starts empty. `/init` and `/save` build it up over time.
  The shared rules are all in the committed `CLAUDE.md`, so you are not missing context.
- **Safety hooks** (in `scripts/hooks/`) are committed but their wiring file
  (`.claude/settings.local.json`) is gitignored. To enable them, create
  `.claude/settings.local.json` with:

  ```json
  {
    "hooks": {
      "PreToolUse": [
        {
          "matcher": "Bash",
          "hooks": [
            { "type": "command", "command": "bash scripts/hooks/essentials-check.sh", "timeout": 10 },
            { "type": "command", "command": "bash scripts/hooks/verify-gate.sh", "timeout": 10 },
            { "type": "command", "command": "bash scripts/hooks/approval-gate.sh", "timeout": 5 },
            { "type": "command", "command": "bash scripts/hooks/git-rm-guard.sh", "timeout": 5 }
          ]
        }
      ]
    }
  }
  ```
  These guard against leaking secrets to this **public** repo, pushing unverified code,
  merging without approval, and deleting protected files. Recommended but optional.

---

## Step 8 — First tasks

**8a. Pick up the research (recommended first task).**
Issue **#1** asks to validate the DRAFT frame-selection architecture and survey OSS
alternatives. In Claude Code:
```
/work
```
and point it at Issue #1, or read [`docs/PRD.md`](./PRD.md) §5.2 (the DRAFT pipeline).

**8b. Build a real deck (once features are implemented).**
```
/slidegen --video <YOUTUBE_VIDEO_ID>
# or
/slidegen --card <CARD_ID>
```
This requires the CV service running and Google OAuth configured.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `tsc` cannot find `@prisma/client` types | run `npm run prisma:generate` first |
| `@/...` import not resolved | ensure you ran `npm install`; the `@/*` alias maps to `src/*` |
| `prisma db push` "succeeds" but tables missing | **do not use `db push`** — apply the raw SQL in Step 5 |
| accidental API call / billing in dev | confirm `SLIDEGEN_MODE=dev` and `VISION_API_PROVIDER` is blank |
| CV calls fail locally | the CV service (`mac-mini/slidegen-service/`) must be running, or leave `SLIDEGEN_CV_SERVICE_URL` unset and work on non-CV parts |
| commit blocked by a hook | the essentials/verify/approval/git-rm guard fired — read its message; it is protecting the public repo |

---

## Conventions (please read before your first PR)

- **English only** in code, commits, PRs, and issues (public repo).
- **No secrets, no real user/video ids, no internal IPs/metrics** in any committed file
  (the `essentials-check.sh` hook enforces this).
- **Plan → approve → execute**: agree on the change before side-effects.
- **DB**: local-first, raw SQL DDL (never `prisma db push`); after DDL run
  `NOTIFY pgrst, 'reload schema'`.
- Run **`/verify`** before pushing; ship via **`/ship`**.

Welcome aboard. Start with `/init`.
