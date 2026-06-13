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

### 🚨 LLM API BULK ban — no batch dataset generation via API + prod boundary (ADR 0003)
- **BULK is the line** (owner clarification 2026-06-13): **batch dataset
  generation via API is banned** — direct Anthropic (Messages + Batch) or
  OpenRouter calls that process MANY items offline (e.g. backfilling figures /
  summaries across a corpus of videos) are forbidden in dev, test, CI, and
  experiments. At-scale generation must run as a **service-triggered prod path**,
  never an offline batch.
- **Single-shot validation/test calls ARE allowed** — a 1–2 call lossless /
  serving-parity / availability check is NOT bulk and is permitted (supersedes
  the old "no 'just 1' / 'sample' exemption" wording). Use a standalone
  validation script (construct the client directly), not the config-gated app.
- **Prod service path (ADR 0003 D2)**: the deployed pipeline may call the
  slide-content LLM (Claude Sonnet via OpenRouter) **only inside the
  deterministic harness** (extract → buildRecipe → validate → FAIL feedback).
  The LLM is **injected**; it never gets agentic tool use and never writes code.
- `OPENROUTER_API_KEY` is **prod-only** (like the vision keys): never in a
  dev/test `.env`, never in CI. Config must refuse it when `SLIDEGEN_MODE=dev`.
- **Dev/test slide-planning runs in the CC console via the Write tool**
  (stub / console-authored content-JSON fixtures) — NOT via an LLM API call
  from a script.
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

### 🔐 PR merge — standing delegation to CC (amended 2026-06-11)
- **Standing owner delegation** (2026-06-11): Claude Code merges its own PRs
  **autonomously** when ALL of the following hold:
  1. the PR was authored/driven by CC in-session (or explicitly handed to CC),
  2. all required CI checks are green,
  3. the `/verify` gate passed for the work,
  4. immediately after each merge, **report the merge commit SHA** (audit).
- **Colleague-authored PRs are NOT covered** — they still require the owner's
  explicit nod (delegation covers CC's own pipeline, not other people's code).
- Still **ABSOLUTELY banned**: the `--auto` flag, enabling GitHub auto-merge,
  and merges executed from background/watch/scheduled tasks — those remain
  **read-only** (watch → report → stop).
- Mechanics: `approval-gate.sh` requires the `SLIDEGEN_USER_OK=1` marker on
  merge commands; the standing delegation is the user approval it asks for —
  the per-merge marker keeps each merge deliberate and auditable.
- Other side effects (deploy, DDL apply) remain under plan→approve→execute.
- (History: PR #15 — CC merged on an inferred go-ahead → absolute ban (PR #16)
  → per-PR-number mechanism (2026-06-10) → standing delegation once CC was
  both implementing and verifying and per-number round-trips became the
  bottleneck (owner, 2026-06-11). CI + /verify + SHA audit + the colleague-PR
  carve-out contain the risk.)

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
- Figures are **regenerated from extracted data**, never pasted raw frames.
  A snapshot is a data source, not the artifact (ADR 0003 P2).
- Quality gate before shipping a figure: structures (tables/trees/flows) as
  native editable vector objects; rasterized embeds (e.g. matplotlib data
  graphs) must be **≥ 300 dpi**; equations as text/LaTeX-derived rendering. A
  screenshot-only or sub-300-dpi figure fails the gate (ADR 0003 D1).

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

### 🌳 Worktree Collaboration Pattern (MANDATORY — pre-work gate)
- **ALL repo work happens in a dedicated worktree. NO EXCEPTION.** Working in
  the main checkout (repo root) — even on a feature branch — is a VIOLATION.
  The repo root stays parked on `main` (READ-ONLY), always clean.
- **Pre-work gate — run BEFORE the first Write/Edit/commit of ANY repo change:**
  1. `git worktree list` → confirm the working dir is `.claude/worktrees/<feature>`,
     NOT the repo root. If at the repo root → STOP and create a worktree first.
  2. Branch only off **fresh `origin/main`**: `git checkout main && git pull --ff-only`
     BEFORE `EnterWorktree` / `git worktree add`. Never branch off a stale local branch.
  3. Never commit directly to `main`.
- **Pull-before-work (conflict prevention):**
  - Session start: `git checkout main && git pull --ff-only origin main` so the
    base is current before branching.
  - During work: `git fetch origin` frequently; if `origin/main` moved,
    `git rebase origin/main` (rebase, NOT merge — no merge commits in history).
  - Before PR: rebase the feature branch on the latest `origin/main` so conflicts
    surface locally, not in CI.
- **Worktree lifecycle:**
  1. `/work` or `/init` auto-creates a new worktree (off fresh main) for the task.
  2. Feature work happens in isolation (separate `src/`, `py/`, dependencies).
  3. Commit + push to the feature branch.
  4. Create PR, get review, merge to main.
  5. `ExitWorktree --keep` to preserve work; `--remove` if abandoned.
  6. **After merge: delete the local feature branch AND remove its worktree.**
     Stale branches/worktrees are a known confusion source — clean them every time.
- **Conflict avoidance:**
  - Different features → different worktrees (no contention on files).
  - Same file / same lines → coordinate via Issue/PR before starting; one waits,
    then rebases on the merged result.
- **Anti-pattern (caused a 2026-06-01 incident):** editing files in the repo root
  on a `feature/*` branch that was already merged and 11+ commits behind
  `origin/main`. Local main was never pulled. Result: stale base + risk of
  clobbering colleague fixes on the same files. The pre-work gate above blocks this.

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
