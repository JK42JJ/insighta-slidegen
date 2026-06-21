---
name: verify
description: "Pre-push verification gate — MUST pass before git push or PR creation. Prevents broken/leaky code from shipping in this PUBLIC repo."
allowed-tools: Bash(npm:*), Bash(npx:*), Bash(python3:*), Bash(ruff:*), Bash(pytest:*), Bash(git:*), Bash(file:*), Bash(grep:*), Bash(identify:*), Read, Grep, Glob
---

# /verify — Mandatory pre-push verification gate

**WHY**: this is a PUBLIC repo with a multi-language pipeline (TS orchestrator + Python CV/figure-redraw) that produces print-quality artifacts. Pushing unverified code risks (a) broken builds, (b) **rasterized / low-DPI figures** that violate the 300dpi/vector contract, and (c) **leaking secrets / real ids / prod metrics** into a public history that can never be fully scrubbed.

**RULE**: changes MUST NOT be pushed until `/verify` reports PASS. No exceptions, no "it's a simple change".

## When to run

Run `/verify` before every `git push` / `gh pr create` / `gh pr merge`. `/ship` invokes the same gates as a mandatory pre-ship step.

## Execution

### Step 1: Detect scope

```bash
CHANGED=$(git diff --name-only origin/main...HEAD 2>/dev/null || git diff --name-only HEAD~1)
echo "$CHANGED"
```

Classify (a change set can match several):
- `src/` (TS) → **TS** scope
- `py/` or `mac-mini/slidegen-service/` → **PYTHON** scope
- generated figure assets (`*.svg`, `*.pdf`, `*.png` under output/figure dirs) → **FIGURE** scope
- `prisma/` → **SCHEMA** scope
- only docs/configs → **SKIP** (auto-pass), but the leak gate (Step 2e) still runs

### Step 2: Run checks

#### 2a. TS checks (TS scope)

```bash
npm run typecheck        # tsc --noEmit (strict)
npm run lint             # eslint (.eslintrc prettier/prettier:error catches prettier too) — mirrors CI's lint job (PR #41)
npm run test             # vitest
npm run build            # tsc build
```
All must exit 0.

> **`npm run lint` only — `format:check` is intentionally excluded (CI-mirror principle).** CI's lint job runs `npm run lint` and nothing else; the `prettier/prettier: error` rule in `.eslintrc.json` makes eslint flag prettier diffs inside that one command. Adding a separate `npm run format:check` here would diverge local `/verify` from CI again (the exact PR #41 round-trip this gate exists to prevent).

#### 2b. Python checks (PYTHON scope)

```bash
ruff check py/ mac-mini/slidegen-service/
[ -d py/tests ] && pytest py/tests -q
[ -d mac-mini/slidegen-service/tests ] && pytest mac-mini/slidegen-service/tests -q
```
ruff must report 0 errors; pytest must exit 0 where a tests dir exists.

#### 2c. Figure DPI gate (FIGURE scope — CRITICAL)

Every generated figure asset must be **vector (SVG/PDF)** OR a raster at **≥300dpi**. A rasterized low-DPI figure silently degrades the deck/PDF.

```bash
FIG_PASS=true
for f in $(echo "$CHANGED" | grep -Ei '\.(svg|pdf|png|jpg|jpeg|tiff)$'); do
  [ -f "$f" ] || continue
  case "$f" in
    *.svg)
      echo "✅ $f → vector (SVG)";;
    *.pdf)
      # A figure PDF must contain vector ops, not a single embedded image.
      if grep -qaE '/(Type[[:space:]]*/Page|Font|XObject[[:space:]]*<<[^>]*\/Subtype[[:space:]]*\/Form)' "$f" 2>/dev/null; then
        echo "✅ $f → vector (PDF)"
      else
        echo "⚠️  $f → PDF vector-content unverified — manual check required"; FIG_PASS=false
      fi;;
    *)
      # Raster: require ≥300 dpi. Prefer ImageMagick `identify`; fall back to `file`.
      DPI=$(identify -format '%x' "$f" 2>/dev/null | grep -oE '^[0-9]+' || echo 0)
      if [ "${DPI:-0}" -ge 300 ]; then
        echo "✅ $f → raster ${DPI}dpi"
      else
        echo "❌ $f → raster ${DPI:-unknown}dpi (< 300) — redraw as vector or re-export ≥300dpi"
        FIG_PASS=false
      fi;;
  esac
done
[ "$FIG_PASS" = "false" ] && { echo "🚫 FIGURE DPI GATE FAILED"; exit 1; }
```

#### 2d. Schema gate (SCHEMA scope) — BLOCK on `prisma db push`

`prisma db push` can silent-fail on Supabase (auth-schema ownership) and drop new columns/tables while reporting success. Schema changes MUST ship as raw SQL DDL.

```bash
# BLOCK if the change set or scripts invoke `prisma db push`.
if git diff origin/main...HEAD 2>/dev/null | grep -qE 'prisma\s+db\s+push' \
   || grep -rqE 'prisma\s+db\s+push' src/ scripts/ package.json 2>/dev/null; then
  echo "🚫 'prisma db push' detected — schema changes MUST be raw SQL DDL under prisma/migrations/"
  exit 1
fi
# Require a raw SQL DDL file when prisma/schema.prisma changed.
if echo "$CHANGED" | grep -q 'prisma/schema.prisma'; then
  if ! echo "$CHANGED" | grep -qE 'prisma/migrations/.*\.sql$'; then
    echo "🚫 schema.prisma changed but no raw SQL DDL under prisma/migrations/*.sql"
    exit 1
  fi
  echo "✅ schema change ships with raw SQL DDL"
fi
```

#### 2e. PUBLIC essentials-only self-check (ALWAYS — first-class gate) — BLOCK on leak

Grep the staged diff for content that must never enter public history.

```bash
DIFF=$(git diff --staged; git diff)
LEAK=false

# Secrets / tokens / keys
echo "$DIFF" | grep -nEi '(api[_-]?key|secret|password|passwd|token|bearer|private[_-]?key)[[:space:]]*[:=]' \
  && { echo "❌ possible secret"; LEAK=true; }
echo "$DIFF" | grep -nE '(AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|hf_[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)' \
  && { echo "❌ key/credential pattern"; LEAK=true; }

# Real infra: public IPs (allow private RFC1918 ranges in examples), Tailscale 100.x, SG ids
echo "$DIFF" | grep -nE '\b((25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])\.){3}(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])\b' \
  | grep -vE '\b(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.|127\.0\.0\.1|0\.0\.0\.0)' \
  && { echo "❌ real-looking IP"; LEAK=true; }
echo "$DIFF" | grep -nE '\b100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.' && { echo "❌ Tailscale 100.x IP"; LEAK=true; }
echo "$DIFF" | grep -nE '\bsg-[0-9a-f]{8,}\b' && { echo "❌ AWS security-group id"; LEAK=true; }

# Prod metrics / cost numbers in non-test files
echo "$DIFF" | grep -nEi '(\$[0-9]+(\.[0-9]+)?/?(day|mo|month|hr|hour)|burn rate|prod (latency|p95|p99)|[0-9,]+ (rows|videos|users) in prod)' \
  && { echo "❌ prod metric / cost number"; LEAK=true; }

[ "$LEAK" = "true" ] && { echo "🚫 PUBLIC ESSENTIALS-ONLY GATE FAILED — remove the above before pushing"; exit 1; }
echo "✅ no secrets / real ids / prod metrics in diff"
```

(If a match is a legitimate placeholder — e.g. `API_KEY=` in `.env.example` with an empty value — confirm it is a redacted example before overriding, and prefer obviously-fake values like `xxx`.)

### Step 3: Write result marker

```bash
echo "PASS $(date +%s) $(git rev-parse HEAD)" > /tmp/.slidegen-verify-pass
```

### Step 4: Report

```
## /verify Report

**Scope**: {TS | PYTHON | FIGURE | SCHEMA | SKIP (+leak gate)}
**Commit**: {short hash} | **Branch**: {branch}

| Check | Result | Duration |
|-------|--------|----------|
| tsc --noEmit (strict) | {PASS/FAIL/SKIP} | {N}s |
| eslint + prettier (npm run lint) | {PASS/FAIL/SKIP} | {N}s |
| vitest | {PASS/FAIL/SKIP} | {N}s |
| tsc build | {PASS/FAIL/SKIP} | {N}s |
| ruff | {PASS/FAIL/SKIP} | {N}s |
| pytest | {PASS/FAIL/SKIP} | {N}s |
| figure DPI gate | {PASS/FAIL/SKIP} | {N}s |
| schema raw-DDL gate | {PASS/FAIL/SKIP} | {N}s |
| PUBLIC essentials-only | {PASS/FAIL} | {N}s |

**Verdict: {✅ PASS — safe to push | 🚫 FAIL — DO NOT push}**

{if FAIL: failing check + error excerpt}
{if PASS: "All gates passed. You may proceed with git push / gh pr create."}
```

## Hard rules (enforced by this skill)

1. **Figure assets → DPI/vector gate is MANDATORY.** A raster < 300dpi fails the build.
2. **`prisma db push` is BLOCKED.** Schema changes ship as raw SQL DDL under `prisma/migrations/`.
3. **PUBLIC essentials-only gate is non-negotiable.** Any secret / real id / prod IP / cost number → FAIL. A public-repo leak cannot be undone by a later commit.
4. **"Simple change" is not an excuse to skip.**
5. **If `/verify` fails, DO NOT push.** Fix the issue; never `--no-verify`.
6. **After PASS, do not edit code before pushing.** If you edit, run `/verify` again.
