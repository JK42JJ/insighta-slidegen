---
name: ship
description: "Commit → push → PR → merge → deploy verification one-step automation for insighta-slidegen (PUBLIC repo, GHCR image build)."
---

# /ship — One-step Ship to Production

Automated flow from commit to deploy verification for **insighta-slidegen** (`JK42JJ/insighta-slidegen`, PUBLIC, default branch `main`, CI = typecheck / lint / test / python / build, deploy = GHCR image build).

## Usage
```
/ship                          # Full flow (commit → deploy verification)
/ship --dry-run                # Pre-ship gate + pre-flight only, no changes
/ship --no-merge               # PR creation only (no auto-merge)
/ship --message "commit msg"   # Specify commit message
/ship --hotfix                 # Minimal pre-flight + urgent deploy
```

## Prerequisites

> The mandatory pre-ship gate (Phase 0) MUST pass before any push. There is no flag to skip it.

## Safety Guards (pre-Phase checks)

| Check | Behavior |
|-------|----------|
| Current branch == `main` | **Block** — ship from a feature branch via PR, never push to main directly |
| Pre-ship gate (Phase 0) fails | **Block** — secret/real-id/metric leak or conflict markers found |
| `.env` / credentials files staged | Exclude from staging + warn |
| 50+ uncommitted files | Warn + suggest split commits |
| Force push attempt | **Block** |
| CI failure | Abort auto-merge, output cause |
| Deploy (GHCR build) failure | Guide to rollback |

## Execution Flow

### Phase 0: Mandatory Pre-Ship Gate (BLOCKING — runs before everything)

This phase is non-skippable and runs even under `--hotfix`. It inherits two recurring failure classes worth preventing in a public, multi-branch repo.

**0a. PUBLIC essentials-only self-check (leak gate)** — invoke the `/verify` Step 2e logic over the full pending diff:
```bash
DIFF=$(git diff --staged; git diff)
LEAK=false
echo "$DIFF" | grep -nEi '(api[_-]?key|secret|password|passwd|token|bearer|private[_-]?key)[[:space:]]*[:=]' && LEAK=true
echo "$DIFF" | grep -nE '(AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|hf_[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)' && LEAK=true
echo "$DIFF" | grep -nE '\b100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.' && LEAK=true   # Tailscale
echo "$DIFF" | grep -nE '\bsg-[0-9a-f]{8,}\b' && LEAK=true                                # AWS SG
echo "$DIFF" | grep -nE '\b((25[0-5]|2[0-4][0-9]|1?[0-9]{1,2})\.){3}(25[0-5]|2[0-4][0-9]|1?[0-9]{1,2})\b' \
  | grep -vE '\b(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.|127\.0\.0\.1|0\.0\.0\.0)' && LEAK=true
echo "$DIFF" | grep -nEi '(\$[0-9]+(\.[0-9]+)?/?(day|mo|month|hr|hour)|burn rate|prod (latency|p95|p99))' && LEAK=true
[ "$LEAK" = "true" ] && { echo "🚫 SHIP BLOCKED — secret/real-id/prod-metric leak in diff"; exit 1; }
```

**0b. Cross-branch stash / conflict-marker audit** (recurring insighta failure class — stale stash pops and merge markers shipped):
```bash
# Warn on a non-empty stash — a cross-branch stash-pop can reintroduce conflicts.
git stash list && [ -n "$(git stash list)" ] && echo "⚠️ stash not empty — confirm nothing is owed before shipping"

# BLOCK on leftover conflict markers in tracked files.
if git grep -nE '^(<{7}|={7}|>{7})( |$)' -- ':!*.md' 2>/dev/null | grep -q .; then
  echo "🚫 SHIP BLOCKED — unresolved conflict markers found:"
  git grep -nE '^(<{7}|={7}|>{7})( |$)' -- ':!*.md'
  exit 1
fi
```

**0c. /verify gate** — run `/verify` (tsc strict / vitest / ruff / pytest / figure-DPI / schema raw-DDL / essentials-only). If `/verify` reports anything but PASS → abort. Confirm the marker:
```bash
[ -f /tmp/.slidegen-verify-pass ] && grep -q "$(git rev-parse HEAD)" /tmp/.slidegen-verify-pass \
  || { echo "🚫 /verify did not PASS for current HEAD"; exit 1; }
```

If `--dry-run`, output Phase 0 + Phase 1 results and exit.

### Phase 1: Pre-flight Verification

Parallel:
```bash
npm run typecheck                 # tsc --noEmit (strict)
npm run build                     # tsc build (skip if --hotfix)
ruff check py/ mac-mini/slidegen-service/ 2>/dev/null || true
git status -s ; git diff --stat
```
ANY failure → abort. `--hotfix`: typecheck only. (Figure-DPI / leak gates already enforced in Phase 0 via /verify.)

### Phase 1.5: Issue Tracking Verification

1. Classify `git diff --stat` changes into logical units.
2. `gh issue list --state all --limit 50 --json number,title,state` → map each unit.
3. Unmapped changes → suggest issue creation; `gh issue create` **after user confirmation**; close completed ones with a comment.
4. Reference issue numbers in the commit message (`Closes #N`).

### Phase 2: Smart Commit

1. Analyze `git diff --staged` + `git diff`.
2. Auto-generate a Conventional Commit message (`{type}({scope}): {subject}`); use `--message` if given.
3. Selective staging — **exclude** `.env*`, `credentials*`, `*.pem`, `*.key`, `backups/`, `test-results/`.
4. **User confirmation required** — show message + file list → commit only after approval.
5. Commit footer:
   ```
   {type}({scope}): {subject}

   Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
   ```

### Phase 3: Push

```bash
git push origin "$(git branch --show-current)"   # feature branch, never main directly
```
Push failure → analyze cause (conflict/auth) + abort.

### Phase 4: PR Creation

1. `gh pr list --base main --state open` → reuse existing PR if present.
2. Else create:
   ```bash
   gh pr create --base main \
     --title "{title from commit}" \
     --body "$(cat <<'EOF'
   ## Summary
   {auto-generated from diff}

   ## Pre-ship gate
   - PUBLIC essentials-only: ✅ pass
   - stash/conflict-marker audit: ✅ clean
   - /verify (tsc / vitest / ruff / pytest / figure-DPI / schema-DDL): ✅ pass

   ## Pre-flight
   - tsc (strict): ✅ | build: ✅ | files changed: {N}

   ## Test plan
   - [ ] CI pass (typecheck / lint / test / python / build)
   - [ ] GHCR image build + deploy verification

   🤖 Generated with [Claude Code](https://claude.com/claude-code)
   EOF
   )"
   ```
3. `--no-merge` → output PR URL and exit.

### Phase 5: CI Monitoring + Auto-merge

1. Watch the run (background where possible):
   ```bash
   gh run watch "$(gh run list --limit 1 --json databaseId --jq '.[0].databaseId')" --exit-status
   ```
2. CI pass → auto-merge:
   ```bash
   gh pr merge {PR_NUMBER} --squash --delete-branch
   ```
3. CI fail → output the failing job (typecheck / lint / test / python / build) + abort.

### Phase 6: Deploy Verification (GHCR image)

1. Watch the deploy workflow (image build + push to GHCR):
   ```bash
   gh run list --workflow deploy.yml --limit 1 --json status,conclusion,databaseId
   ```
2. Verify the image was published:
   ```bash
   gh api "/users/JK42JJ/packages/container/insighta-slidegen/versions" --jq '.[0].metadata.container.tags' 2>/dev/null \
     || echo "GHCR package not found — check deploy workflow"
   ```
3. Output:
   - Success: PR URL + merge commit + GHCR image tag.
   - Failure: deploy logs + rollback guidance (re-run deploy on the last green tag).

## Phase Exit Conditions

| Flag | Exit |
|------|------|
| `--dry-run` | after Phase 0 + Phase 1 |
| `--no-merge` | after Phase 4 |
| (default) | after Phase 6 |
| `--hotfix` | Phase 0 full (non-skippable) + Phase 1 tsc-only + full execution |

## Cautions

- **Phase 0 is non-skippable** — even `--hotfix` runs the leak gate + stash/conflict audit + /verify.
- **PUBLIC repo** — a leaked secret/id in pushed history cannot be undone by a later commit.
- **Ship from a feature branch via PR** — never push to `main` directly; CI runs on PR.
- **User confirmation required before committing** (no auto-commit).
- **On failure at ANY Phase, abort immediately** and summarize results so far.
