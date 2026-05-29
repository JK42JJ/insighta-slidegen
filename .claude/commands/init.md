---
allowed-tools: Bash(git:*), Bash(gh:*), Bash(tail:*), Bash(wc:*), Read, Grep, Glob, Agent, CronCreate, CronList
description: Session boot — load slidegen project context, resume last checkpoint, show status and relevant warnings
---

## Context
- Branch: !`git branch --show-current`
- Status: !`git status --short`

## Instructions

Fully restore project context at session start for **insighta-slidegen** — a standalone PUBLIC sub-project that turns a video card's v2 rich-summary into key-frame extraction + redrawn vector figures (300dpi) → Google Slides deck + true-vector PDF, driven by a Claude skill.

$ARGUMENTS can provide a domain hint: `/init cv-pipeline`, `/init slides`, `/init schema`, `/init infra`.
If no hint is given, auto-detect the domain from the current branch name and recent commits.

Memory dir (referenced consistently across all slidegen commands):
`~/.claude/projects/-Users-jeonhokim-cursor-insighta-slidegen/memory/`

> This is a PUBLIC repo. NEVER echo secrets, real EC2/Tailscale IPs, SG ids, real user/video ids, prod metrics, or cost numbers into output. Memory files may be referenced by path but their sensitive content stays in memory only.

### Phase 0: Project Knowledge load (highest priority, do not skip)

Load the minimum knowledge required to understand what slidegen is and how it runs. Skipping Phase 0 causes architecture misjudgement and regressions.

```
Read: docs/PROJECT_KNOWLEDGE.md   (if present)
Read: README.md
```

After reading, confirm the architecture facts:
- Compositor / orchestrator = TypeScript (`src/`).
- CV + figure redraw = Python (`py/` library + `mac-mini/slidegen-service/` long-running service).
- Persistence = Prisma + Supabase. Schema changes ship as **raw SQL DDL** (never rely on `prisma db push` alone — it can silent-fail).
- Output artifacts: Google Slides deck + true-vector PDF. Figures MUST be vector or ≥300dpi.

### Phase 1: Core Context Load (mandatory, parallel execution)

Read ALL of the following with the Read tool. NEVER skip any. If a file does not exist yet, note it and continue.

```
Read: ~/.claude/projects/-Users-jeonhokim-cursor-insighta-slidegen/memory/MEMORY.md
Read: ~/.claude/projects/-Users-jeonhokim-cursor-insighta-slidegen/memory/credentials.md
Read: ~/.claude/projects/-Users-jeonhokim-cursor-insighta-slidegen/memory/troubleshooting.md
Read: ~/.claude/projects/-Users-jeonhokim-cursor-insighta-slidegen/memory/project-structure.md
```

### Phase 2: Domain Detection & Load

**Domain detection logic** (priority order):
1. If $ARGUMENTS contains an explicit hint, use it.
2. Otherwise detect from branch name / recent commits:
   - `frame|extract|keyframe|opencv|cv` → **cv-pipeline**
   - `figure|redraw|vector|matplotlib|svg|dpi` → **cv-pipeline**
   - `slides|deck|gslides|pptx|pdf|layout` → **slides**
   - `prisma|schema|migration|supabase|db` → **schema**
   - `ci|deploy|ghcr|docker|infra|workflow` → **infra**
3. If detection fails → **general** (no additional loads).

**Domain-specific additional Reads** (only if the file exists):

| Domain | Additional files |
|--------|------------------|
| cv-pipeline | memory/architecture.md, docs/cv-pipeline.md |
| slides | memory/architecture.md, docs/slides-spec.md |
| schema | memory/architecture.md, prisma/schema.prisma |
| infra | memory/infrastructure.md, memory/project-structure.md |
| general | (none) |

### Phase 2.5: Pipeline-Native Status Scan

Scan the project's structural maturity (Glob/Grep in parallel):
1. `src/` → TS orchestrator entrypoints + REST/CLI surface; check structured error format (`{ status, code, message }`).
2. `py/` + `mac-mini/slidegen-service/` → Python module list; check the CV/redraw stages present.
3. `prisma/schema.prisma` + `prisma/migrations/` → models + raw-SQL DDL coverage.
4. `tests/` (TS) + `py/tests/` + `mac-mini/slidegen-service/tests/` → test file counts.
5. `tests/TEST.md` existence and freshness (if present).

**Introspection check**:
- TS orchestrator `/health` or CLI `--version` surface.
- slidegen-service health endpoint (if defined).

### Phase 3: Checkpoint Resume

checkpoint.md is cumulative and can be large. NEVER read the whole file.

```bash
tail -100 ~/.claude/projects/-Users-jeonhokim-cursor-insighta-slidegen/memory/checkpoint.md
```

From the output:
1. Find the last Checkpoint entry → understand previous work.
2. If a Pending Work section exists, surface incomplete tasks.

### Phase 4: Status Dashboard (parallel execution)

```bash
git log --oneline -5
git diff --stat
gh issue list --state open --json number,title,labels --jq '.[] | "#\(.number): \(.title)"'
gh run list --limit 3 --json status,conclusion,name,createdAt
gh pr list --json number,title,state
```

Extract:
- HEALTH: service status (TS orchestrator, slidegen-service if running locally).
- GIT: branch / commit state.
- CI/WORKFLOWS: GitHub Actions status (typecheck / lint / test / python / build).
- PRs / ISSUES: open counts.

### Phase 5: Troubleshooting Awareness (Regression Prevention)

Extract warnings relevant to the current domain from troubleshooting.md:
- cv-pipeline → "DPI", "raster", "frame dedupe", "figure redraw", "OpenCV version" related.
- slides → "Google Slides API", "vector PDF", "layout overflow", "font embed" related.
- schema → "Prisma", "raw DDL", "prisma db push silent fail", "Postgrest reload" related.
- infra → "GHCR", "docker build", "CI", "deploy" related.
- All domains → always include the "repeated mistakes prevention checklist".

**Regression Watchlist enforcement** — surface **ALL** LEVEL-2+ patterns from troubleshooting.md's "Regression Watchlist (LEVEL-2+)" section (no domain filter; the per-domain hints above are advisory for extra attention, never used to suppress entries).

```
### Pre-flight Checks (Regression Prevention)
⚠️ LEVEL-{N} Pattern: {name} (recurrence: {N})
- [ ] {check 1}
- [ ] {check 2}
→ Declare this checklist was reviewed before starting work.
```

Enforcement:
- Full watchlist every /init — do NOT omit on the basis of detected domain.
- LEVEL-3 patterns are also CLAUDE.md Hard Rules — get user confirmation before related work.
- A LEVEL-2 pattern that recurs after /retro confirmation auto-flags for LEVEL-3 promotion at next /save.

**PUBLIC essentials-only awareness** — this repo is public. If any open carryover item references committing operational runbooks, real ids, prod metrics, or secrets, surface it as a watchlist warning.

**SECURITY carryover blocking** — during Phase 6 Open-Requests scan, if any `wip`/`noted` carryover is tagged SECURITY (credential rotation / permission revoke / exposed secret cleanup) AND its carryover counter ≥ 3, output a 🚨 **BLOCKING** section **above** the "Ready" line:
```
SECURITY carryover <item> — (a) execute now / (b) defer to session end (counter N+1) / (c) formal defer with target date?
```
Do NOT declare "Ready" until answered. Detection keywords: `password|rotation|secret|credential|oauth|token`.

**Carryover cap blocking** — if any Improvement Target / Issue / carryover item has counter ≥ 10, output 🚨 **BLOCKING** above "Ready":
```
Carryover cap — <item> deferred N times: (a) close / (b) abandon / (c) redesign as new spec?
```
Do NOT declare "Ready" until decided. Record decisions in `retrospective.md` Rule Evolution Log.

**Rule K — D2 floor BLOCKING reception**:
- Read marker `~/.claude/projects/-Users-jeonhokim-cursor-insighta-slidegen/memory/.d2-blocking` (set by previous /save when `D2 ≤ 0.55`).
- If present, parse `{epoch, d2, reason}` and output 🚨 BLOCKING above "Ready":
  ```
  D2 = {d2} ≤ 0.55 floor at Epoch {epoch}.
  (a) re-confirm guessing-pattern fact-read pre-flight
  (b) which LEVEL-2+ pattern recurred? — grep troubleshooting.md then answer
  (c) cumulative user-frustration signal? — confirm ≥ 3
  1-line answer.
  ```
- Do NOT declare "Ready" until answered. After the answer: `rm` the marker AND append a row to `retrospective.md` Rule Evolution Log (date + epoch + answer). NOT optional — a preserved-but-answered marker is a process bug.

### Phase 6: Learning Review (Read stage of the self-improvement cycle)

**6a. Recent lessons** — read the `교훈`/`Lessons` field from the last 2-3 checkpoints; include domain-relevant ones in Warnings.

**6a-2. Execute Improvement Target immediately**:
```
Read: ~/.claude/projects/-Users-jeonhokim-cursor-insighta-slidegen/memory/session-log.md
```
- If the last row's Improvement Target ≠ "—":
  1. If actionable within 5 minutes → **execute now within Phase 6** (not just remind).
  2. After execution → "Previous target: {content} → DONE".
  3. If not actionable → "Previous target: {content} — apply when opportunity arises this session".

**Rule A.2 — IT carryover counter ≥ 3 BLOCKING**: scan the last 4 session-log rows + MEMORY.md. If an identical IT text appears unapplied in ≥ 3 sessions, output 🚨 BLOCKING above "Ready":
```
IT carryover '{text}' unapplied {N}× — (a) abandon / (b) redesign / (c) freeze with explicit trigger?
```
Counter ≥ 5 → AUTO-abandon (no question): drop it + log in retrospective.md, surface a single non-blocking notice.

**6a-3. Open Requests check**:
```bash
grep -E '\| (wip|noted) \|' ~/.claude/projects/-Users-jeonhokim-cursor-insighta-slidegen/memory/request-journal.md
```
Display matching items in the "Open Requests" section (omit if none).

**6b. Memory health** (max 3 lines): MEMORY.md `wc -l` (warn if 180+); unchecked items in the repeated-mistakes checklist; Pending Work stale 7+ days.

**6c. Eval history review**:
- Read `eval-scores.md`.
- Average of last 3 epochs → trend (improving/stagnant/declining).
- Identify weakest Dimension → focus area for this session.
- Display LEVEL-2+ pattern count; D2 volatility warning if variance > 0.5 across last 3 epochs.

**6d. Memory improvement history** — last entry in `retrospective.md` Rule Evolution Log; if no promotion for 30+ days → "NOTE: consider running /retro".

### Phase 7: Scheduled Jobs (auto-registration)

`CronList`, then `CronCreate` only the missing ones (recurring: true):

| Job | Cron | Interval | Notes |
|-----|------|----------|-------|
| `/retro` | `3 17 * * *` | Daily 17:03 | Daily retrospective |
| `/tidy` | `0 0 */7 * *` | Every 7 days | Issue/board sync |

Output above the Ready section:
```
### Scheduled Jobs
- /retro: {registered | already scheduled | failed: {reason}}
- /tidy:  {registered | already scheduled | failed: {reason}}
```
Note: CronCreate is session-scoped (auto-expires ~3 days); re-registered every /init.

### Output Format

```
## Session Boot Complete

**Branch**: {branch} | **Domain**: {detected domain}
**Last Checkpoint**: #{N} — {title} ({date})

### Recent Work
- {last checkpoint core 2-3 lines}
- {pending work if any}

### Git Status
- Last 3 commits: {oneline}
- Uncommitted: {count} files
- Open PRs: {list or "none"}

### Open Issues ({count})
{issue list — current domain filter}

### CI Status
{last 3 runs: typecheck / lint / test / python / build}

### Pipeline-Native Status (Phase 2.5)
- TS orchestrator: {entrypoints} (structured errors: {y/n})
- Python stages: cv-pipeline {present?}, figure-redraw {present?}, slidegen-service {present?}
- Prisma models: {N} (raw-DDL migrations: {N})
- Tests: TS {X}, py {Y}, slidegen-service {Z}
- TEST.md: {up-to-date/outdated/missing}

### Pre-flight Checks (Regression Prevention)
{LEVEL-2+ patterns per Phase 5 format; omit if none}

### Warnings (from troubleshooting.md)
- {1-3 domain-relevant warnings}

### Open Requests (Phase 6a-3)
{wip/noted table; omit if empty}

### Improvement Target (Phase 6a-2)
- Previous target: {...} {→ DONE if executed}
(omit if "—")

### Lessons from Recent Sessions (Phase 6a)
- {1-2 domain-relevant lessons}
(omit if none)

### Eval Trend (Phase 6c)
- Recent Epochs: {last 3}
- Trend: {improving/stagnant/declining} | Avg: {3-epoch MA}
- Weakest: D{N} ({name}) — {focus area}
- Regression Watchlist: {LEVEL-2+ count} active
- {D2 VOLATILE warning if variance > 0.5}
(if no Epoch data, output "No eval data yet")

### Scheduled Jobs
- /retro: {status}
- /tidy:  {status}

### Memory Health
- MEMORY.md: {line count}/200 {WARN if 180+}
- Last /retro: {date} {NOTE if 30d+}

### Ready
Domain [{domain}] context loaded. Awaiting work instructions.
```

### Cautions

- NEVER include credentials.md secret values in output (retain in memory only).
- NEVER echo real ids / prod IPs / cost numbers — PUBLIC repo.
- If a Read fails, warn and continue.
- Parallel strategy: Phase 0-2 as one Read batch; Phase 2.5-4 as the next Glob/Grep/Bash batch; Phase 5-6 analysis only.
- This command restores context + applies lessons. Do NOT modify code or start new work.

### Self-Improvement Cycle Summary

```
/save (Write)            /init (Read)               /retro (Analyze)
   │                        │                            │
   ├ record work            ├ Phase 0-4 restore          ├ session-log analysis
   ├ session-log row        ├ Phase 2.5 pipeline scan    ├ error-pattern discovery
   ├ extract lessons        ├ Phase 5 mistake warnings   ├ efficiency trends
   ├ Eval (2 decimal)       ├ Phase 6 apply lessons       └ improvements → user approval
   └ Improvement Target     └ Phase 6c load Eval
        └──── data accumulation ──→ next-session reminder ──→ verify application
```
