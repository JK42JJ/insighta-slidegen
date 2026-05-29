---
name: retro
description: Analyze session-log data → discover patterns → generate concrete improvement suggestions
allowed-tools: Read, Edit, Write, Grep, Bash(wc:*)
---

Analyze structured data from the slidegen session-log to generate **concrete improvement suggestions**. After user approval, apply to memory/rules and record history in retrospective.md.

Memory dir: `~/.claude/projects/-Users-jeonhokim-cursor-insighta-slidegen/memory/`

## Execution Order

### Step 1: Load Data (parallel)

```
Read: ~/.claude/projects/-Users-jeonhokim-cursor-insighta-slidegen/memory/session-log.md
Read: ~/.claude/projects/-Users-jeonhokim-cursor-insighta-slidegen/memory/eval-scores.md
Read: ~/.claude/projects/-Users-jeonhokim-cursor-insighta-slidegen/memory/troubleshooting.md
Read: ~/.claude/projects/-Users-jeonhokim-cursor-insighta-slidegen/memory/work-efficiency.md
Read: ~/.claude/projects/-Users-jeonhokim-cursor-insighta-slidegen/memory/retrospective.md
```

### Step 2: Error Pattern Analysis

Extract sessions with Errors > 0:
- **Error frequency by stage**: cv-pipeline / slides / schema / infra.
- **Error → resolution session count** (1 session vs persisting).
- **Recurrence of patterns already in troubleshooting.md.**
- **Repeated patterns** (2+ errors in the same stage).

### Step 3: Efficiency Trend Analysis

- Avg modified files per session trend.
- Error-free session ratio trend.
- **Improvement Target application rate** = applied / (sessions with a target).

### Step 4: Eval Trend Analysis

From the Epoch Log: 3-epoch moving average per Dimension; weakest Dimension; stagnant Dimensions (same range 5+ epochs); D3 change trend.

### Step 4.5: Pipeline-Native Progress

- **Structured-error ratio**: TS/CLI surfaces returning `{ status, code, message }`.
- **Test coverage trend**: TS / py / slidegen-service file count change vs previous /retro.
- **Figure-quality trend**: share of figure outputs that are vector or ≥300dpi.
- **Schema-DDL discipline**: share of schema changes shipped with raw SQL DDL.
- **/verify pass rate** (if execution history exists), tracking the figure-DPI and PUBLIC essentials-only gates separately.

### Step 5: Generate Improvement Suggestions

- **Type A — Memory reinforcement**: e.g. "DPI-gate failures in 3/10 sessions → add a figure-export checklist to troubleshooting.md".
- **Type B — Rule strengthening**: e.g. "Improvement Target unapplied 3× → change the /init reminder approach".
- **Type C — Rule retirement**: e.g. "work-efficiency.md rule referenced 0× in 10 sessions → deletion candidate".
- **Lesson → verification rule promotion**: LEVEL-2 troubleshooting patterns that should become /verify gate items (the lesson-accumulation → automated-verification loop).

### Step 6: Output Results

```
## Retrospective Analysis (YYYY-MM-DD, {N} sessions)

### A. Error Patterns
| Stage | Error sessions | Ratio | Primary cause |
(if zero: "No errors to analyze")

### B. Efficiency Trends
- Avg modified files: {N}
- Error-free ratio: {X}%
- Improvement Target application rate: {Y}% ({applied}/{with target})

### C. Eval Trends
- Weakest Dimension: D{N} ({name}), 3-MA {score}
- Stagnant: {if any}
- Trajectory: {improving/stagnant/declining}

### D. Improvement Suggestions
| # | Type | Suggestion | Evidence | Target file |

### E. Pipeline-Native Progress
- Structured errors: {N}/{M} surfaces
- Tests: TS {X}, py {Y}, slidegen-service {Z}
- Figure quality (vector/≥300dpi): {pct}%
- Schema raw-DDL discipline: {pct}%
- /verify pass rate: figure-DPI {X}%, essentials-only {Y}% (if recorded)
- Lesson → /verify-gate promotion candidates: {N}
(if no data: "Initial scan not run — run /init first")

### F. Previous Suggestion Tracking
| # | Suggestion | Applied date | Effect |
(last 5 from retrospective.md)
```

### Step 7: Apply After User Approval

- Apply ONLY user-approved items to canonical sources.
- Record in `retrospective.md`: add a row to the "applied improvements" table + a row to the "Rule Evolution Log".
- **Lesson → /verify promotion**: add approved LEVEL-2 patterns as /verify gate items.

$ARGUMENTS: number of sessions to analyze (default: all rows, max 50).
