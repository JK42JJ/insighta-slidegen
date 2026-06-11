#!/bin/bash
# PreToolUse hook — PUBLIC-repo guardian.
#
# This repo is PUBLIC. Before any `git commit` / `git push` / `gh pr create`,
# scan the staged diff for content that must never enter a public repo:
#   • likely secrets  : API-key patterns, PEM private-key blocks, bearer/JWT
#                        tokens, Google OAuth client secrets
#   • prod IPs        : known production IP literal(s)
#   • real video IDs  : 11-char YouTube IDs in non-fixture/non-test source
#
# On any hit the action is BLOCKED with the offending lines (key names only,
# never the secret value). Move real values into the gitignored .env, and put
# only synthetic IDs in fixtures/tests.
#
# Bypass (only after manual confirmation the hit is a false positive):
#   SLIDEGEN_ESSENTIALS_OK=1 <command>

set -u

# Self-location guard: hook cwd follows the Bash tool's cwd. If that cwd is
# OUTSIDE any git repo, anchor to this script's repo. When cwd IS inside a
# repo/worktree, stay put — the staged-diff check must run against the
# CALLER's index (a worktree's index differs from the main checkout's).
git rev-parse --git-dir >/dev/null 2>&1 || cd "$(dirname "$0")/../.." || exit 2

INPUT=$(cat 2>/dev/null || echo '{}')
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // ""' 2>/dev/null || echo "")

[ -z "$CMD" ] && exit 0

# Only gate on commit/push/PR-creating commands
if ! echo "$CMD" | grep -qE '\bgit[[:space:]]+commit\b|\bgit[[:space:]]+push\b|\bgh[[:space:]]+pr[[:space:]]+create\b'; then
  exit 0
fi

if [ "${SLIDEGEN_ESSENTIALS_OK:-0}" = "1" ]; then
  echo "✓ SLIDEGEN_ESSENTIALS_OK=1 set — public-repo essentials check skipped for this call."
  exit 0
fi

# Staged diff (added lines only). If nothing staged, fall back to all tracked
# changes vs HEAD so `git commit -a` style flows are still covered.
DIFF=$(git diff --cached -U0 2>/dev/null || echo "")
[ -z "$DIFF" ] && DIFF=$(git diff -U0 HEAD 2>/dev/null || echo "")
# Only added lines (start with '+', not the '+++' file header)
ADDED=$(echo "$DIFF" | grep -E '^\+' | grep -vE '^\+\+\+' || true)
[ -z "$ADDED" ] && exit 0

VIOLATIONS=""

add_v() { VIOLATIONS="${VIOLATIONS}$1"$'\n'; }

# 1) PEM private key block
if echo "$ADDED" | grep -qE 'BEGIN [A-Z ]*PRIVATE KEY'; then
  add_v "  • PEM private-key block detected (BEGIN ... PRIVATE KEY)"
fi

# 2) Common API-key / token prefixes (value redacted in report)
if echo "$ADDED" | grep -qE '(AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{20,}|ghp_[0-9A-Za-z]{20,}|xox[baprs]-[0-9A-Za-z-]{10,})'; then
  add_v "  • API-key/token literal detected (AWS/OpenAI/Google/GitHub/Slack prefix)"
fi

# 3) Supabase service-role / JWT-shaped token (3 base64 segments, long)
if echo "$ADDED" | grep -qE 'eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}'; then
  add_v "  • JWT-shaped token detected (eyJ........) — likely Supabase/OAuth"
fi

# 4) Secret assigned inline (KEY=<nonempty value>) for known secret names
if echo "$ADDED" | grep -qiE '(SERVICE_ROLE_KEY|CLIENT_SECRET|REFRESH_TOKEN|CV_SERVICE_TOKEN|GEMINI_API_KEY|API_KEY|SECRET|PASSWORD)[[:space:]]*[:=][[:space:]]*["'"'"']?[^"'"'"'[:space:]]{8,}'; then
  # Allow .env.example (key= with empty value) — those won't match the {8,} value requirement.
  add_v "  • Secret-named variable assigned a non-empty value (key shown, value omitted)"
fi

# 5) Known prod IP literal(s)
if echo "$ADDED" | grep -qE '44\.231\.152\.49'; then
  add_v "  • Production IP literal detected (44.231.152.49)"
fi

# 6) Real YouTube IDs in non-fixture/non-test source.
#    youtube ID = 11 chars [A-Za-z0-9_-]. Only flag changes to source files
#    that are NOT under tests/ or fixtures/ and NOT *.example / *.md.
FILES=$(git diff --cached --name-only 2>/dev/null || git diff --name-only HEAD 2>/dev/null || echo "")
SRC_FILES=$(echo "$FILES" | grep -E '\.(ts|tsx|js|py)$' | grep -vEi '(test|tests|fixture|fixtures|__tests__|mock|sample|example)' || true)
if [ -n "$SRC_FILES" ]; then
  for f in $SRC_FILES; do
    [ -f "$f" ] || continue
    # youtu.be/<id> or v=<id> or watch?v=<id> with an 11-char id
    if grep -qE '(youtu\.be/|[?&]v=|videoId["'"'"']?[[:space:]]*[:=][[:space:]]*["'"'"'])[A-Za-z0-9_-]{11}' "$f"; then
      add_v "  • Possible real YouTube video ID in non-fixture source: $f"
    fi
  done
fi

if [ -n "$VIOLATIONS" ]; then
  echo "🚫 BLOCKED: PUBLIC-repo essentials check found content that must not be committed." >&2
  echo "" >&2
  echo "$VIOLATIONS" >&2
  echo "Fix:" >&2
  echo "  - Move real secret values into the gitignored .env (never commit values)." >&2
  echo "  - Use only synthetic IDs in fixtures/tests; keep real IDs out of source." >&2
  echo "  - Remove prod IPs/hostnames; reference the private insighta repo for ops." >&2
  echo "" >&2
  echo "If this is a confirmed false positive:" >&2
  echo "  SLIDEGEN_ESSENTIALS_OK=1 <your command>" >&2
  # PreToolUse blocking code is 2 (1 is a non-blocking warning).
  exit 2
fi

exit 0
