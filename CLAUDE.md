# insighta-slidegen — Project Rules

> **Inherits Insighta Hard Rules.** This is a PUBLIC sub-project of Insighta.
> The general engineering Hard Rules below are inherited from the private
> `insighta` repo (Testing, Code Style, Cross-Layer Propagation,
> plan→approve→execute, `.env` immutable, DB work order, `prisma db push`
> silent-fail handling). Insighta-internal operational specifics (prod IPs,
> security groups, SSH topology, credentials locations, incident detail) are
> intentionally **not** carried into this public repo.
>
> For shared ops/infra detail, see the **private `insighta` repo**.

## Project memory (for /init)

Session memory + lessons live OUTSIDE this repo (not committed):
- `~/.claude/projects/-Users-jeonhokim-cursor-insighta-slidegen/memory/`

Load on every session start (`/init`): `MEMORY.md`, `work-efficiency.md`,
`troubleshooting.md`, `project-slidegen.md`.

---

## SLIDEGEN DELTAS (project-specific rules — read first)

### 🔓 PUBLIC repo — essentials-only self-check (BEFORE EVERY commit)
- This repo is **PUBLIC**. Only ship: code, Prisma schema, raw SQL DDL,
  tests/fixtures, IaC, and neutral contributor docs.
- **Never commit**: credentials or secret values, ops runbooks, internal
  performance/cost metrics, real user-video IDs (only synthetic IDs in
  fixtures), prod IP addresses / hostnames / security-group IDs, personal
  Claude Code config paths, or user quotes.
- Run the self-check before `git add`: scan the staged diff for API-key
  patterns, PEM blocks, tokens, prod IPs, and real YouTube IDs in non-fixture
  code. The `scripts/hooks/essentials-check.sh` PreToolUse hook enforces this
  on push/PR, but the human/agent must self-check on every commit.

### 🗄️ Insighta DB is READ-ONLY here — writes only to `slide_*`
- Treat all inherited Insighta tables (`youtube_videos`, `video_rich_summaries`,
  `video_captions`, …) as **read-only sources**. Never INSERT/UPDATE/DELETE them.
- This project may write **only** to its own tables: `slide_decks`,
  `slide_slides`, `slide_figures`, `slide_keyframes`, `slide_jobs`.
- Any write path touching a non-`slide_*` table is a bug — block it.

### 🚨 LLM API call ban (inherited VERBATIM — no exceptions)
- **Direct Anthropic API calls are banned** (Messages + Batch).
- **OpenRouter API calls are banned.**
- These APIs are **production-service only**. Dataset generation, experiments,
  and tests must NOT call them. No "credit check", "small test", "just 1",
  or "sample" exemptions.
- **Slide-planning reasoning runs in the CC console via the Write tool**, using
  Claude's own knowledge — NOT via an LLM API call from a script.
- The **only** sanctioned vision API usage is the **prod-only** fallback
  (`VISION_API_PROVIDER` set, `SLIDEGEN_MODE=prod`) when the Mac Mini CV
  service is unavailable. Dev/test paths are **local-first** (Mac Mini CV
  service) and must never set the prod-only vision keys.
- Violation → end the session immediately.

### ✅ plan → approve → execute (inherited)
- Present a plan (file paths + diff summary + rollback) before any side-effect
  action (Write, Edit, git, gh, install, docker). Execute only after explicit
  user approval ("ok" / "해" / "approved"). Proposal/question forms are not
  approval. Read-only commands (`ls`, `grep`, `git status`) need no plan.

### 🧱 DB work order — local-first + raw SQL DDL (NO `prisma db push`)
- **Local → production order. No exceptions.**
- **Do NOT use `prisma db push`** for schema changes (it silent-fails on the
  Supabase auth-schema ownership issue and can drop new tables/columns while
  reporting success). Ship schema changes as **raw SQL DDL** committed under
  `prisma/migrations/<feature>/NNN_*.sql`, applied to local first, then prod.
- After any `ALTER TABLE` / new column, **reload PostgREST schema**:
  `psql "$DATABASE_URL" -c "NOTIFY pgrst, 'reload schema'"` (local), or the
  Supabase Dashboard → Settings → API → "Reload schema" (prod). Verify the new
  column is queryable before declaring done.
- Verify the real DB state (`\d <table>`) after applying — do NOT assume the
  Prisma schema and the DB are in sync.

### 🎨 Figures: vector-300dpi quality gate
- Figures are **redrawn as native vector graphics**, not screenshots.
- Quality gate before shipping a figure: the figure must be true vector
  (selectable/scalable) and rasterized embeds must be **≥ 300 dpi**. A
  screenshot-only or sub-300-dpi figure fails the gate.

---

## Inherited GENERAL Hard Rules

### `.env` immutable
- **Never modify/replace/delete** `.env`, `.env.local`, `.env.production`.
- Inject env for one-off prod-mode runs via **CLI inline injection only**:
  ```bash
  DATABASE_URL=... DIRECT_URL=... npx tsx src/<script>.ts
  ```
- Do NOT do file-swap patterns (`cp prod.env .env` → run → restore) — risk of loss.
- `.env.example` is the only committed env file; it holds key names, never values.

### DB work order (general)
- Local → production order. New tables must be reflected in the Prisma schema
  (for type generation) **and** shipped as raw SQL DDL (see SLIDEGEN DELTAS).
- Never INSERT test/seed data directly into prod.
- Read the actual DB URL from your local `.env` — never guess/type it.

### `prisma db push` silent-fail handling
- On Supabase, `prisma db push` can silent-fail (auth-schema ownership),
  dropping new public tables/columns while returning "success".
- Required checklist for any new column/table PR (any miss = do not ship):
  1. Provide raw SQL DDL under `prisma/migrations/<feature>/NNN_*.sql`.
  2. Verify locally with `\d <table>` that all new columns exist.
  3. Verify on prod with `psql "$DIRECT_URL" -c "\d <table>"`.
  4. On mismatch, apply the raw SQL DDL manually to local + prod.
  5. Re-verify before deploy.

### Cross-Layer Propagation
- Dependent features must be reviewed/modified/tested together.
- Edit order: DB → types → converter → service → orchestrator → output.
- When changing a persisted shape (storage version bump, Prisma field drop,
  API response shape), `grep` for **ALL consumers** of the removed/renamed
  field before merging. tsc passing ≠ runtime safety.
- After edits: `tsc --noEmit` + build + functional verification.

### Testing
- New function/route → at least 1 unit test. Bug fix → 1 regression test.
- Never delete/skip existing tests; if a test fails, fix the code.
- TS: place tests alongside the layer they cover; Python: `py/tests/`.
- New write path → test that it only targets `slide_*` tables.

### Code Style
- No magic numbers → named constants. No 3+-level relative imports → `@/` alias.
- No hardcoded business config via raw `process.env[...]` in logic → use a
  central config module (zod-validated).
- New env default = "existing behavior" (unset = no-op) so flags roll back
  without code revert.
- Tuning knobs (weights, thresholds, TTLs, feature flags) are **not secrets** —
  keep them in code defaults / compose env / runtime config, never in secret
  stores. 2-question test: (1) safe to print to stdout? (2) safe in a public
  PR? Both yes → not a secret.

### Fact-read before guessing
- Before diagnosing/fixing/scripting, **read the actual source** (file, config,
  schema) at least once. Do not write code from memory, error messages, or
  patterns alone.
- For visual/UI mismatch reports, the first action is to read the relevant
  file/className — not a hypothesis ("cache?", "reload?").
- For numeric tuning (timeout/retry/TTL/limit), require one measurement before
  shipping the bump.

### 🌳 Worktree Collaboration Pattern
- **Always use git worktrees for concurrent feature work** (isolated directories, no context switching).
- **main branch is READ-ONLY**: never commit directly to main. All work → feature branch in a worktree.
- **Worktree lifecycle**:
  1. `/work` or `/init` auto-creates a new worktree for the current task
  2. Feature work happens in isolation (separate `src/`, `py/`, dependencies)
  3. Commit + push to feature branch
  4. Create PR, get review, merge to main
  5. `ExitWorktree --keep` to preserve work; `--remove` if abandoned
- **Concurrent workflows**:
  - You: worktree-A (feature/x) → PR pending review
  - Collaborator: worktree-B (feature/y) → independent development
  - Both pull origin/main frequently (`git fetch`) to stay current
- **Conflict avoidance**:
  - Different features → different worktrees (no contention on files)
  - Same file edits → coordinate via PR review, not parallel worktrees
  - Main stays clean → rebase feature branches on origin/main before PR

---

## "Done" = verified
- A build passing is **not** done. "Done" = the actual behavior verified
  (locally for dev features; prod-path verified before claiming prod-done).
- Never persist user data in component state only — DB → API → hook → UI.

## Ops detail
- This public repo intentionally omits prod infra topology, SSH access
  procedures, security-group config, and credential locations.
- **See the private `insighta` repo** (and its `memory/credentials.md`) for
  all shared ops/infra detail. Slidegen secret locations are indexed in this
  project's (non-public) `memory/credentials.md` pointer file.
