#!/bin/bash
# PreToolUse hook — block `git push` / `gh pr create` / `gh pr merge` unless a
# /verify PASS marker exists for the current HEAD.
#
# Enforces the inherited "Pre-push Verification" Hard Rule: a build/tsc/test
# pass is not enough — /verify must have confirmed the change actually works
# before it can reach a PR or remote.
#
# /verify writes the marker:  PASS <unix-ts> <commit-sha>  to $MARKER.
# Marker is valid for 10 minutes and must match the current HEAD sha.

set -euo pipefail

INPUT=$(cat 2>/dev/null || echo '{}')
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // ""' 2>/dev/null || echo "")

# Only gate on push/PR commands
if ! echo "$CMD" | grep -qE 'git push|gh pr create|gh pr merge'; then
  exit 0
fi

MARKER="/tmp/.slidegen-verify-pass"

if [ ! -f "$MARKER" ]; then
  echo "🚫 BLOCKED: push/PR attempted but /verify was not run."
  echo "Run /verify first (it writes $MARKER on PASS), then retry."
  exit 1
fi

MARKER_TS=$(awk '{print $2}' "$MARKER" 2>/dev/null || echo "0")
MARKER_SHA=$(awk '{print $3}' "$MARKER" 2>/dev/null || echo "none")
CURRENT_SHA=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
NOW=$(date +%s)

ELAPSED=$((NOW - MARKER_TS))
if [ "$ELAPSED" -gt 600 ]; then
  echo "🚫 BLOCKED: /verify result expired (${ELAPSED}s ago, max 600s). Run /verify again."
  exit 1
fi

if [ "$MARKER_SHA" != "$CURRENT_SHA" ]; then
  echo "🚫 BLOCKED: /verify ran on $(echo "$MARKER_SHA" | head -c 7) but HEAD is $(echo "$CURRENT_SHA" | head -c 7). Run /verify again."
  exit 1
fi

echo "✅ /verify PASS confirmed ($(echo "$CURRENT_SHA" | head -c 7), ${ELAPSED}s ago). Proceeding."
exit 0
