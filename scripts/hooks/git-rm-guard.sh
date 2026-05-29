#!/bin/bash
# PreToolUse hook — blocks destructive deletion patterns on protected paths.
#
# Rationale: `git rm <file>` (without --cached) deletes the file from BOTH git
# tracking AND local disk. Running it on docs / hooks / migrations can destroy
# local working files that are expensive or impossible to recreate. This hook
# forces the safe `git rm --cached` untrack pattern and protects key paths from
# bare `rm` / `find -delete`.
#
# Decision tree:
#   1. `git rm`:
#        a. with `--cached` → ALLOW (untrack only, disk preserved)
#        b. without `--cached` → BLOCK (would destroy disk)
#      (early-exit — do NOT also evaluate as bare `rm`)
#   2. `rm` token followed by a PROTECTED path → BLOCK
#   3. `find <protected> ... -delete` → BLOCK
#   4. Else → ALLOW
#
# Protected paths: docs/, .claude/{commands,hooks,skills,agents},
#   scripts/hooks/, prisma/migrations/
#
# Bypass: prefix command with `SLIDEGEN_GIT_RM_OK=1` (one-shot, env-scoped).

set -u

INPUT=$(cat 2>/dev/null || echo '{}')
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // ""' 2>/dev/null || echo "")

[ -z "$CMD" ] && exit 0

if [ "${SLIDEGEN_GIT_RM_OK:-0}" = "1" ]; then
  echo "✓ SLIDEGEN_GIT_RM_OK=1 set — git/rm command allowed for this call."
  exit 0
fi

PROTECTED_RE='(docs/|\.claude/(commands|hooks|skills|agents)|scripts/hooks/|prisma/migrations/)'

# === Case 1: git rm — early decision (allow if --cached, block otherwise) ===
if echo "$CMD" | grep -qE '(^|[[:space:];&|])git[[:space:]]+rm($|[[:space:]])'; then
  if echo "$CMD" | grep -qE '(^|[[:space:]])--cached($|[[:space:]])'; then
    exit 0
  fi
  echo "🚫 BLOCKED: 'git rm' without '--cached' deletes the file from local disk too."
  echo ""
  echo "  - To untrack from git WITHOUT deleting from disk:"
  echo "      git rm --cached <path>"
  echo "  - To exclude from future commits, add to .gitignore."
  echo ""
  echo "If you genuinely need to delete from disk too:"
  echo "  SLIDEGEN_GIT_RM_OK=1 git rm <path>   # one-shot bypass"
  exit 1
fi

# === Case 2: bare `rm` on protected path ===
if echo "$CMD" | grep -qE "(^|[[:space:];&|])rm([[:space:]]+-[a-zA-Z]+)*[[:space:]]+[^[:space:];&|]*${PROTECTED_RE}"; then
  echo "🚫 BLOCKED: 'rm' on protected path."
  echo ""
  echo "Protected: docs/, .claude/{commands,hooks,skills,agents}, scripts/hooks/, prisma/migrations/"
  echo ""
  echo "If genuinely necessary, get user approval, then:"
  echo "  SLIDEGEN_GIT_RM_OK=1 rm <path>"
  exit 1
fi

# === Case 3: find -delete on protected path ===
if echo "$CMD" | grep -qE "find[[:space:]]+[^[:space:]]*${PROTECTED_RE}" && \
   echo "$CMD" | grep -qE -- '-delete([[:space:]]|$|;|\|)'; then
  echo "🚫 BLOCKED: 'find ... -delete' on protected path."
  echo "Same rules as 'rm' on protected paths above."
  exit 1
fi

exit 0
