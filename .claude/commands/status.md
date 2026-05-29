---
allowed-tools: Bash(gh:*), Bash(git:*), Read
description: Show slidegen project status — open issues, CI, deploy, and current progress
---

## Instructions

Display a concise project status dashboard for **insighta-slidegen** (PUBLIC repo, `JK42JJ/insighta-slidegen`, default branch `main`).

1. **Git Status**:
   - Current branch, uncommitted changes count
   - Last commit: `git log --oneline -1`

2. **Issue Progress**:
   - `gh issue list --state open --json number,title --jq 'length'` (open)
   - `gh issue list --state closed --json number,title --jq 'length'` (closed)
   - Show progress: closed / total
   - Group open issues by pipeline stage label if present (cv-pipeline / slides / schema / infra)

3. **CI/CD Status**:
   - `gh run list --limit 3 --json status,conclusion,name,createdAt`
   - Surface the per-job state (typecheck / lint / test / python / build) of the latest run

4. **Open PRs**:
   - `gh pr list --json number,title,state`

5. **Pipeline Stage**: Infer the active stage from open issues + recent commits (cv-pipeline / slides / schema / infra).

6. **Blockers**: Check for `blocked` labeled issues.

Format output as a clean table/summary. Keep it concise. Do NOT echo secrets or real ids (PUBLIC repo).
