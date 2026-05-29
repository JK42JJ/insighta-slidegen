---
name: tidy
description: GitHub Issues + Project board sync — detect mismatches, fix status, update MEMORY.md
allowed-tools: Bash(gh:*), Bash(python3:*), Read, Edit, Grep, Bash(wc:*)
---

Synchronize GitHub Issues and the slidegen Project board, then update the GitHub Issues section in the slidegen MEMORY.md.

Memory dir: `~/.claude/projects/-Users-jeonhokim-cursor-insighta-slidegen/memory/`
Repo: `JK42JJ/insighta-slidegen` (PUBLIC). Default branch: `main`.

Usage: `/tidy [scope?]`
- omitted: full sync (Issues + board + MEMORY.md)
- `issues`: Issues cleanup only (stale detection, close candidates)
- `board`: Project board sync only
- `memory`: MEMORY.md Issues section update only

## Core Principles

> Issue/Board status MUST reflect the actual code state.
> Issues whose work merged MUST be closed + Done.
> **NEVER auto-close without user confirmation.** Board status changes (Done↔Todo↔In Progress) are non-destructive and may auto-fix.

## Execution Order

### Phase 1: Gather Current State (parallel)

```bash
# 1a. Open issues
gh issue list --state open --json number,title,labels,milestone --jq '.[] | "#\(.number): \(.title) [\(.labels | map(.name) | join(","))]"'

# 1b. Recently closed (7d)
gh issue list --state closed --json number,title,closedAt --jq '.[] | "#\(.number): \(.title) (\(.closedAt))"' -L 20

# 1c. Project board items + status  (set PROJECT_NUMBER for the slidegen board)
# gh project item-list <PROJECT_NUMBER> --owner JK42JJ --format json -L 50

# 1d. Issue numbers referenced in recent commits
git log --oneline -20 | grep -oP '#\d+' | sort -u

# 1e. Open PRs
gh pr list --json number,title,state,labels

# 1f. Milestones
gh api repos/JK42JJ/insighta-slidegen/milestones?state=all --jq '.[] | "#\(.number): \(.title) (\(.state)) open:\(.open_issues) closed:\(.closed_issues)"'

# 1g. Open issues without milestone
gh issue list --state open --json number,title,milestone --jq '.[] | select(.milestone == null) | "#\(.number): \(.title) [NO MILESTONE]"'
```

> The slidegen Project board number / field ids are not hardcoded here. Resolve them once via `gh project list --owner JK42JJ` and the board's field-list, and record them in `memory/project-structure.md` (NOT in this public command file).

### Phase 2: Mismatch Detection

| # | Pattern | Detection | Action |
|---|---------|-----------|--------|
| M1 | Issue closed + Board ≠ Done | state=closed, status≠Done | Board → Done (auto, non-destructive) |
| M2 | Issue open + Board Done | state=open, status=Done | Close candidate (confirm) |
| M3 | Commit references #N + Issue open | git log has `(#N)`, Issue open | Close candidate (confirm) |
| M4 | Issue open + 30d+ no activity | no comments/commits | Stale warning |
| M5 | Open Issue not on Board | not registered | Board-add candidate |
| M6 | Issue missing Milestone | no milestone | Assign Milestone |
| M7 | Completed Milestone not closed | all subs closed, milestone open | Close Milestone |

### Phase 2.5: Pipeline-Native Gap Analysis

From `/init` Phase 2.5 results:
- **Under-tested stages**: changed code in `src/` / `py/` / `mac-mini/slidegen-service/` with no matching tests → suggest a test issue.
- **Non-standardized errors**: TS/CLI surfaces not returning structured errors → suggest an issue.
- **Figure-quality debt**: any figure path producing raster < 300dpi → suggest a redraw-to-vector issue.
- **/retro improvement items** → verify Issue mapping against retrospective.md.

Suggest a `pipeline-native` label for gaps.

### Phase 3: Output Fix Plan (request confirmation)

```
## GitHub Tidy Report

### Mismatches Found ({count})
| # | Type | Issue | Current | Expected | Action |

### Pipeline-Native Gaps ({count})
| # | Type | Target | Suggestion |
(omit if none)

### Stale Issues (30d+)
- #{N}: {title} — last activity {date}

### Board Coverage
- Open issues on board: {N}/{M}
- Missing from board: {list}

Auto-fix? (y/n, or specify numbers for selective fixes)
```

### Phase 4: Execute Fixes (after confirmation)

- **M1** (Board → Done): `gh project item-edit ...` set Status=Done + Completed date. (Auto-allowed.)
- **M2/M3** (close): `gh issue close {N} --reason completed [--comment "Completed in {hash}"]` + Completed date on board.
- **M5** (add to board): `gh project item-add <PROJECT_NUMBER> --owner JK42JJ --url <issue-url>` + Start date.
- **M6** (milestone): `gh issue edit {N} --milestone "{name}"`.
- **M7** (close milestone): `gh api repos/JK42JJ/insighta-slidegen/milestones/{N} -X PATCH -f state=closed`.

Date-field ids are board-specific; read them from `memory/project-structure.md`.

### Phase 5: Sync MEMORY.md

1. Read `MEMORY.md`. 2. Find the `## GitHub Issues` section. 3. Update milestone/phase markers. 4. Remove closed, add new open issues. 5. Enforce 200-line limit.

### Phase 6: Output Summary

```
## Tidy Complete

### Actions Taken
- Board updated: {N} | Issues closed: {N} | Added to board: {N} | Milestones: {N} assigned, {N} closed
- MEMORY.md: {updated/no change}

### Current State
- Open issues: {N} | On board: {done}/{total} Done | Stale (30d+): {N}

### Pipeline-Native Gaps
- Issues suggested: {N}
(if none: "No gaps detected")

### Next Tidy
- {1-2 items to check next}
```

## Cautions

- **NEVER auto-close** — M2/M3 are candidates requiring confirmation.
- **NEVER close Epics** — manually closed even when all sub-issues complete.
- **Board status changes are safe** — M1 may auto-fix.
- **MEMORY.md 200-line limit** — compress by removing closed-issue rows.
- **Date fields required** — set Completed (close/Done) or Start (board-add).
- **PUBLIC repo** — never paste secrets/real ids into issue bodies or comments.
- `/save` does not call `/tidy`; run independently. `/save` Step 4 advises running it when Issue status changes.
