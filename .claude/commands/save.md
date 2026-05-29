---
name: save
description: Auto-record session progress to slidegen memory + extract lessons + memory self-improvement + Session Eval
allowed-tools: Read, Edit, Write, Bash(git:*), Bash(tail:*), Bash(wc:*), Bash(npm:*), Bash(npx:*), Bash(chmod:*), Grep
---

Record this session's work to the slidegen memory dir, extract lessons, auto-improve related memory files, and run the Session Eval.

Memory dir: `~/.claude/projects/-Users-jeonhokim-cursor-insighta-slidegen/memory/`

Usage: `/save [title]` — if title omitted, auto-generate from git log.

## Performance: Background Execution

/save can block the user for several minutes. When the user calls `/save`:
1. Launch this whole command as a background Agent (`run_in_background: true`).
2. Respond immediately: "Recording the session in the background — continue working."
3. The background agent runs all steps autonomously and notifies on completion.

**Exception**: if the user explicitly asks to wait, run in foreground.

## Core Principles

> `/save` is the **Write stage of the learning cycle** — each checkpoint should make memory files incrementally more useful for the next `/init`.

## Execution Order

### Step 0: Ensure memory file permissions

```bash
chmod +x ~/.claude/projects/-Users-jeonhokim-cursor-insighta-slidegen/memory/* 2>/dev/null || true
```

### Step 1: Gather Information (parallel)

- `git log --oneline` (commits since last checkpoint)
- `git diff --stat` (uncommitted changes)
- `git status` (untracked files)
- Read current `checkpoint.md` (last checkpoint number + last commit hash)
- Read current `MEMORY.md`
- **Recall ALL work this session** (regardless of git tracking).
- **Recall ALL user requests** — code-changing AND record-only (issues to file, future directives, external URLs/resources). Track even across mid-session context compaction.

Paths:
- checkpoint.md: `~/.claude/projects/-Users-jeonhokim-cursor-insighta-slidegen/memory/checkpoint.md`
- MEMORY.md: `~/.claude/projects/-Users-jeonhokim-cursor-insighta-slidegen/memory/MEMORY.md`
- session-log.md: `~/.claude/projects/-Users-jeonhokim-cursor-insighta-slidegen/memory/session-log.md`

Target only commits after the last checkpoint's hash.

### Step 1.5: PUBLIC essentials-only self-check (first-class step)

Before recording anything, scan this session's git-tracked changes for content that must NOT land in a public repo. This mirrors the /verify and /ship leak gate.

```bash
git diff --staged ; git diff
```
Scan the diff for:
- secrets / tokens / API keys / passwords
- real EC2 / Tailscale IPs, security-group ids
- real user ids / video ids
- prod metrics / cost numbers / internal incident detail

If any leak is found in tracked files: **STOP**, report the file + line, and instruct the user to remove it before continuing the save. (Memory files outside the repo may hold sensitive context; the gate is for repo-tracked changes only.)

### Step 2: Update checkpoint.md

- New entry = last Checkpoint number + 1:
  ```
  ### Checkpoint N: {title} (COMPLETED — {YYYY-MM-DD})
  - **Commit**: `{hash}` — `{message}` ("uncommitted" if none)
  - **Local-only changes**: {non-tracked changes, if any}
  - **Files**: {summary of changed files}
  - **Changes**: {key changes, 2-5 lines}
  - **Stage**: {cv-pipeline | slides | schema | infra | general}
  - **Build/Verify**: {typecheck/build/test/ruff/pytest + figure-DPI/leak gate results}
  - **Lessons**: {what was learned}
  - **Improvement Target**: {1 specific action for next session}
  - **User Requests**: {requests not completed as code}
  ```
- Uncommitted changes → add to Pending Work section. Check off completed Pending items.

**User Requests rules**: record only unexecuted/partial requests + preserve external resources (URLs/docs) with summaries. Format: `{request} → {Issue #N / Pending / not reflected}`. If all done as code → "none".

**Improvement Target rules**: 1 concrete action completable in 5 minutes (no vague "verify/check"). Format: "{file/tool}: {specific action}". Simple session → "—".

**checkpoint.md rotation (Rule C — enforced)**: when entry count ≥ 21, MOVE the 10 oldest entries to `checkpoint-archive.md` BEFORE writing the new entry. Always retain Pending Work. No skip/defer.

### Step 2a: Append session-log.md row

```
| {N+1} | {date} | {branch} | {stage} | {files} | {new} | {errors} | {lessons} | {build} | {key action} | {improvement target} | {open reqs} |
```
- Files: `{M}M+{N}N`. Errors/Lessons: counts. Build: pass/fail/N/A. Open Reqs: count + brief content of record-only requests.

### Step 2b: Update request-journal.md

Path: `~/.claude/projects/-Users-jeonhokim-cursor-insighta-slidegen/memory/request-journal.md`
1. `tail -30 request-journal.md` → does today's date section exist?
2. If not, add a new date H3 at top (below Legend).
3. Add rows for ALL session requests (full list from Step 1).

Rules (≤30s): Summary ≤40 chars (verb + target); Category ∈ {feature, bugfix, design, backlog, research, meta}; Status ∈ {done, issue, noted, wip, cancelled}; Ref = commit/Issue/CP; sequential # per date. 200-line cap → delete oldest `done` items first.

### Step 2c: Update TEST.md (if present)

If test-related changes occurred or tests were run: capture `npm run typecheck` / `npm run lint` / `npm run test` and `ruff`/`pytest` results; update `tests/TEST.md` sections + last-updated date. Skip if TEST.md absent.

### Step 3: Extract Lessons

Review the session from 4 angles; skip any that don't apply.

#### 3a. Error patterns → troubleshooting.md (with Regression Counter)
1. Does this session's error match an existing pattern?
2. **Existing recurs**: increment `recurrence`; escalation:
   - recurrence=1 → LEVEL-1 (record only)
   - recurrence=2 → LEVEL-2 → add to init.md Phase 5 Pre-flight + troubleshooting.md "Regression Watchlist (LEVEL-2+)"
   - recurrence≥3 → LEVEL-3 → add a Hard Rule to CLAUDE.md (user confirmation required)
3. **New**: header `[LEVEL-1, recurrence: 1]`.
4. De-escalation: D2=1.00 for 5 epochs → LEVEL-3→2; 10 epochs → 2→1; LEVEL-1 + D2=1.00 for 5 → remove from watchlist.

#### 3b. Efficiency patterns → work-efficiency.md
#### 3c. Architecture decisions → architecture.md
#### 3d. Rule violations/gaps → CLAUDE.md improvement candidates

(3b-3d: Read → check duplicates → add if new.)

### Step 4: Memory Hygiene Check

1. Check off resolved known issues. 2. Update Issues table status. 3. Fix stale info. 4. Enforce 200-line limit on MEMORY.md. 5. Advise `/tidy` if GitHub Issue status changed.

**Rule B — compression auto-trigger**: `wc -l` on `work-efficiency.md` and `architecture.md`. Single-session over-cap (work-efficiency > 1800 OR architecture > 1900) → spawn a 5-minute compression sub-task within this /save run:
1. Identify oldest 3-5 CP-tagged sections in the over-cap file.
2. Move full bodies to `<file>-archive.md`; replace with one-line summaries linking to archive.
3. Re-measure; if reduction < 100 lines OR still over cap → mark for manual deep-compression, escalate to next /retro.
4. Record SUCCESS/PARTIAL in MEMORY.md footer.

### Step 5: Update MEMORY.md

Replace the "Recent work" section with this session's date + content. Enforce 200-line limit.

### Step 6: Session Eval (v3 — Regression Multiplier)

Read `eval-scores.md`, then score this session **strictly** across 5 Dimensions (0.00–1.00, **2 decimals**):
- **D1 Context Retention** — count of memory re-lookups (mandatory code exploration not penalized).
- **D2 Error Prevention** — troubleshooting pattern recurrence × Regression Multiplier (recurrence=1 ×1.0, =2 ×0.7, ≥3 ×0.5).
- **D3 Improvement Action** — previous Improvement Target applied + new improvement discovery.
- **D4 Memory Hygiene** — stale corrections, line-count compliance.
- **D5 Work Efficiency** — parallelism, Agent delegation, dedicated-tool rate.

Eval = average of valid items. Append a row to the Epoch Log; analyze vs previous Epoch; update Trend Analysis if 5+ epochs.

**Rule K — D2 floor BLOCKING marker**:
- If this Epoch `D2 ≤ 0.55` → write `~/.claude/projects/-Users-jeonhokim-cursor-insighta-slidegen/memory/.d2-blocking` = `{"epoch":"{N}","d2":"{score}","reason":"{1-line cause}"}`.
- Soft early-warning `0.55 < D2 ≤ 0.60`: no marker, but emit a Footer note in Step 7: `"D2 = {score} early-warning (floor 0.55). Watch {weakest sub-pattern}."`
- Next /init reads the marker; after the user answers it, the marker is `rm`'d and logged in retrospective.md (handled in /init).

### Step 7: Output Summary

```
## Checkpoint #{N}: {title}

### Record
- {changes summary 2-3 lines}
- MEMORY.md: {updated or not}
- PUBLIC essentials-only self-check: {PASS / leak found at {file}:{line}}
- Uncommitted: {warning if any}

### Lessons Applied
| Target file | Change | Rationale |
|-------------|--------|-----------|
(if none: "No new lessons extracted this session")

### User Requests (unexecuted/partial)
| Request | Status | Notes |
(if all done as code: "All user requests completed as code changes")

### Improvement Target
> {next-session action}

### Session Eval (Epoch {N})
| D1 | D2 | D3 | D4 | D5 | **Eval** |
|----|----|----|----|----|----------|
| {..} | {..} | {..} | {..} | {..} | **{avg}** |
- vs Previous: {Δ} | {largest-change Dimension}
- Lowest: D{N} ({score}) — {one-line direction}

### Memory Health
- troubleshooting.md: {count} patterns (+{N})
- Stale fixed: {N}
- MEMORY.md: {line count}/200
- request-journal.md: +{N} (total {T})
- session-log.md: {rows} sessions

### Context Usage
- Used: {N}K / {total}K ({percent}%)
- {if >80%: "⚠️ context low — consider /clear"}
```

### Step 8: Context Usage Report

Run `/context` (or equivalent) last and append the result (see Step 7 format).

If $ARGUMENTS provided, use as the checkpoint title; else auto-generate from commit messages.

## Lesson Worthiness Criteria

Add a lesson when it is: **Reproducible** (can recur), **Non-obvious** (project-specific), **Actionable** ("next time do X"), **Verified** (actually confirmed this session).

Do NOT add: one-off mistakes, duplicates of recorded patterns, speculation/unverified hypotheses.
