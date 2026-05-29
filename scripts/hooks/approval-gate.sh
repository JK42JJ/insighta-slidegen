#!/bin/bash
# PreToolUse hook — require an explicit user-approval marker before
# irreversible remote actions: `gh pr merge` and force `git push`.
#
# Enforces the inherited "plan → approve → execute" Hard Rule for the actions
# that cannot be undone (public main merge, remote history rewrite). It adds a
# hard friction step so the irreversible action must be surfaced once more
# before it runs.
#
# Allowed forms (only after the user has typed explicit "ok"/"approved"/"merge"):
#   • SLIDEGEN_USER_OK=1 gh pr merge <N> --squash --delete-branch
#   • SLIDEGEN_USER_OK=1 git push --force-with-lease <remote> <branch>
# Plain (non-force) `git push` is NOT blocked here — verify-gate.sh handles that.
# Read-only `gh pr view / list / checks` are not blocked.

set -euo pipefail

INPUT=$(cat 2>/dev/null || echo '{}')
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // ""' 2>/dev/null || echo "")

# `gh pr merge <N>` — irreversible to public main
if echo "$CMD" | grep -qE '\bgh[[:space:]]+pr[[:space:]]+merge\b'; then
  if [ "${SLIDEGEN_USER_OK:-}" = "1" ]; then
    exit 0
  fi
  cat <<'EOF' >&2
🚫 BLOCKED: `gh pr merge` requires an explicit user-approval marker.

Re-run with the approval env, only after the user has typed an explicit
"ok" / "approved" / "merge" in chat for THIS specific PR:
  SLIDEGEN_USER_OK=1 gh pr merge <N> --squash --delete-branch
EOF
  exit 1
fi

# Force push — irreversible to remote history
if echo "$CMD" | grep -qE '\bgit[[:space:]]+push\b.*--force(-with-lease)?\b'; then
  if [ "${SLIDEGEN_USER_OK:-}" = "1" ]; then
    exit 0
  fi
  cat <<'EOF' >&2
🚫 BLOCKED: `git push --force` requires an explicit user-approval marker.

Re-run with (only after user explicit "ok"):
  SLIDEGEN_USER_OK=1 git push --force-with-lease <remote> <branch>
EOF
  exit 1
fi

exit 0
