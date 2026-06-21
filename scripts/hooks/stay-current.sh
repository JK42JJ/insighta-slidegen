#!/bin/sh
# lefthook pre-push "stay-current" check (extracted from lefthook.yml).
#
# WHY A FILE: lefthook wraps an inline `run:` block as `sh -c "<script>"`. On
# Windows Git-Bash the inner double quotes of the echo lines collide with that
# outer `-c "..."` quoting, so the push aborts with
#   sh: -c: line N: syntax error: unexpected end of file
# even when the branch is up to date (the real check passes). Calling a script
# file keeps the `-c` argument quote-free, so it runs on every platform.
#
# Behavior: fetch origin (read-only); BLOCK a push of local main that is behind
# origin/main; WARN (don't block) a feature branch that is behind (the GitHub
# ruleset enforces up-to-date at merge time).
git fetch origin --quiet 2>/dev/null || true
BEHIND=$(git rev-list --count HEAD..origin/main 2>/dev/null || echo 0)
BR=$(git branch --show-current)
if [ "${BEHIND:-0}" -gt 0 ]; then
  if [ "$BR" = "main" ]; then
    echo "[blocked] push blocked - local main is ${BEHIND} commit(s) behind origin/main."
    echo "   Run: git pull --ff-only origin main   then push again."
    exit 1
  else
    echo "[warn] '${BR}' is ${BEHIND} commit(s) behind origin/main - rebase before opening/updating the PR"
    echo "   (merge requires the branch to be up to date)."
  fi
fi
