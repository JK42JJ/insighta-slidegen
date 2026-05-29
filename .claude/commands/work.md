---
name: work
description: Select optimal work unit → plan → execute. Core execution step of the /init ↔ /save cycle, adapted to slidegen stages.
allowed-tools: Bash(gh:*), Bash(git:*), Bash(npm:*), Bash(npx:*), Bash(python3:*), Read, Write, Edit, Grep, Glob, Agent, Bash(tail:*), Bash(wc:*)
---

Based on the context restored by `/init`, select the highest-ROI work unit, plan it, then execute. Adapted to the slidegen pipeline: **v2 rich-summary → key-frame extraction → vector figure redraw → Google Slides + true-vector PDF**.

Usage: `/work [target?]`
- target omitted: auto-select optimal work unit
- target specified: `#42` (issue), `pending` (incomplete work), `eval:D2` (Eval weakness), `fix:XXX` (bug), `stage:cv-pipeline` / `stage:slides` / `stage:schema` (pipeline stage focus)

## Core Principles

> `/work` selects and executes the highest-ROI work unit.
> Split if too large, bundle if too small.
> **NEVER write code without a plan, and NEVER touch a file before plan → user approval (plan → approve → execute gate).**

## Execution Order

### Phase 0: Sync to latest main (WIP-safe)

Stay current with collaborators. **Always fetch; only pull/switch when the working tree is CLEAN** (protects WIP + stashes). A new work branch MUST be cut from up-to-date main.

```bash
git fetch origin --quiet
if [ -z "$(git status --porcelain)" ]; then
  if git switch main 2>/dev/null && git pull --ff-only origin main 2>/dev/null; then
    echo "✓ main synced to origin/main — branch new work from here"
  else
    echo "⚠️ could not ff-only pull main (diverged?) — resolve manually before branching"
  fi
else
  echo "⚠️ working tree not clean — auto-sync skipped. Commit/stash, then pull main before creating a work branch."
fi
```

### Phase 1: Gather Work Candidates (parallel)

```bash
# 1a. GitHub open issues
gh issue list --state open --json number,title,labels,body --jq '.[] | "#\(.number): \(.title) [\(.labels | map(.name) | join(","))]"'

# 1b. Pending Work (last entry in checkpoint.md)
tail -30 ~/.claude/projects/-Users-jeonhokim-cursor-insighta-slidegen/memory/checkpoint.md

# 1c. Incomplete work on current branch + stash audit
git status --short
git stash list
```

Additional Reads (if needed): `eval-scores.md` (weakest Dimension), `troubleshooting.md` (unchecked items).

### Phase 2: Priority Scoring

| Criterion | Weight | Description |
|-----------|--------|-------------|
| **Impact** | 0.35 | User value, effect on pipeline output quality |
| **Urgency** | 0.25 | Time sensitivity, blocker, uncommitted state |
| **Readiness** | 0.25 | Dependencies met, inputs/tools ready |
| **Eval Alignment** | 0.15 | Contribution to weakest Eval Dimension |

**Priority Score** = Impact×0.35 + Urgency×0.25 + Readiness×0.25 + Eval×0.15

Auto-boost: uncommitted on current branch → +2 Urgency; explicit `$ARGUMENTS` target → rank 1; Pending Work "commit+PR needed" → +2 Urgency; weakest-Eval-aligned → +1 Eval.

### Phase 3: Work Unit Sizing

| Size | Threshold | Action |
|------|-----------|--------|
| Too Large | >20 files, >3h | split into sub-tasks (one per /work) |
| Just Right | 5-15 files, 1-2h | proceed |
| Too Small | <3 files, <15min | bundle with related work |

Split strategy: split on AC checklist; each sub-task independently buildable/testable; execute only the first sub-task this session.

### Phase 4: Generate Execution Plan

```
## Work Plan: {title}

**Source**: {Issue #N / Pending / Eval:D{N} / User Request}
**Stage**: {cv-pipeline | slides | schema | infra | general}
**Priority Score**: {score} (I:{n} U:{n} R:{n} E:{n})
**Estimated Files**: {N} modified/created

### Steps
1. {step}: {file list}
2. ...

### Verification (stage-aware)
- [ ] `npm run typecheck` (tsc --noEmit strict) pass
- [ ] `npm run build` pass
- [ ] `npm run test` (vitest) pass
- [ ] (python touched) `ruff check` + `pytest` pass
- [ ] (figure output touched) every generated figure asset is vector OR ≥300dpi
- [ ] (schema touched) raw SQL DDL written under prisma/migrations/ (NOT prisma db push)

### Rollback
- {how to revert: git restore / branch reset}

### Risks
- {risk}: {mitigation}
```

Mandatory references when planning: `project-structure.md` (verify target dirs), `architecture.md` (follow existing patterns), the target Issue body (AC, technical notes, dependencies).

### Phase 5: User Confirmation (plan → approve gate)

Output the plan and **wait for explicit user approval** ("go", "ok", "approved"). Proposal/question forms ("how about?", "shall I?") are NOT execution triggers.

```
## Work Selection

### Candidate List (top 3)
| # | Work | Stage | Priority | I | U | R | E |
|---|------|-------|----------|---|---|---|---|
| 1 | {selected} | {stage} | {score} | {n} | {n} | {n} | {n} |
| 2 | ... |
| 3 | ... |

### Selected: {rank 1}
{Phase 4 plan}

Proceed? (or specify a number for a different item)
```

### Phase 6: Execute (only after approval)

Execution principles:
1. Step-by-step in plan order.
2. Verify first: typecheck/build (and ruff/pytest if python) after each Step.
3. Follow `work-efficiency.md`: dedicated tools, Agent delegation, parallel where independent.
4. Reference `project-structure.md` to verify file paths.
5. Mid-save: if 10+ files modified, intermediate `git add` + status output.

**Pipeline-stage checklist**:

cv-pipeline (frame extraction / figure redraw):
- [ ] Frame extraction is deterministic / dedup logic covered by a test.
- [ ] **Figure output is vector (SVG/PDF) or raster ≥300dpi** — verify the actual asset, not just exit 0.
- [ ] No hardcoded video/user ids in fixtures (PUBLIC repo).

slides (deck / PDF):
- [ ] Google Slides API calls return structured errors, not silent failures.
- [ ] PDF export preserves vectors (true-vector, not rasterized).
- [ ] Layout overflow handled for long summaries.

schema:
- [ ] Schema change includes a **raw SQL DDL file** under `prisma/migrations/`.
- [ ] After ALTER, plan Postgrest schema reload step.
- [ ] No test/seed data committed.

Common:
- [ ] `npm run typecheck` pass.
- [ ] Tests written for new functionality.
- [ ] Output verification: do NOT trust exit 0 — verify the actual produced artifact (frame file, figure DPI, deck/PDF, DB row).

**Agent delegation**:
| Condition | Approach |
|-----------|----------|
| 2+ independent stages (e.g. cv + slides) | Agent parallel spawn |
| Tests need writing | test-runner agent |
| TS + Python simultaneous changes | parallel agents |
| Single file modification | direct execution |

### Phase 7: Completion Report

```
## Work Complete: {title}

### Results
- Files: {N} modified, {N} created
- Build: {typecheck + build result}
- Tests: {vitest / pytest result if run}
- Artifacts: {figure DPI / deck / PDF verification if applicable}

### Verification Checklist
- [x] typecheck
- [x] build
- [x] {stage-specific items}

### Next Steps
- [ ] Run `/verify` before pushing
- [ ] Run `/save` recommended
- {1-2 next work candidates}
```

## Special Modes

- `$ARGUMENTS` = `pending` → top-priority Pending Work; uncommitted auto-prioritized.
- `$ARGUMENTS` = `eval:D{N}` → improve weakest Eval Dimension (D1 memory reinforcement / D2 troubleshooting review / D3 lesson depth / D4 memory hygiene / D5 efficiency rules).
- `$ARGUMENTS` = `#N` → select that Issue; skip Phase 2, start at Phase 3.
- `$ARGUMENTS` = `fix:description` → bug-fix mode: search → fix → verify + regression test.
- `$ARGUMENTS` = `stage:cv-pipeline|slides|schema` → focus a pipeline stage; stage checklist enforced.
- `$ARGUMENTS` = `test` → test writing/reinforcement; coverage gap → add tests → update TEST.md.

## Cautions

- **NEVER write code without a plan + user approval** (plan → approve → execute gate).
- **MUST reference project-structure.md** to verify paths.
- **MUST reference credentials.md** for secret/API-key work — never guess secret names.
- **Stop immediately on build failure**; do NOT proceed.
- **NEVER exceed work scope** — no out-of-plan "improvements".
- **PUBLIC repo**: no real ids / secrets / prod metrics in code or fixtures.
- Verify with real software (actual figure render, real Slides/PDF export, real DB), minimize mocks.
