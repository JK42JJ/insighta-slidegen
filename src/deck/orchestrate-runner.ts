/**
 * Node runner glue (PR-F3): CV resources bundle → optional chart-regen
 * pre-step → vendored deck/scripts/orchestrate.js self-correction loop →
 * .pptx artifact.
 *
 * Hard guarantees enforced here (LLM API ban):
 *   - `orchestrate(...)` is ALWAYS called with an explicitly constructed
 *     `llm` option — the vendored `callOpenRouter` default is structurally
 *     unreachable from this path. `buildLlm` throws BEFORE the vendored
 *     module is even loaded when no llm can be constructed.
 *   - The OpenRouter closure is built ONLY in prod (SLIDEGEN_MODE=prod with
 *     config.OPENROUTER_API_KEY — itself refused by src/config in dev).
 *     Dev/test callers must inject a stub llm.
 *   - Chart-regen failure (struct unsupported / python missing / crash) →
 *     the chart stays LABEL-ONLY: pngPath=null, never a raw frame
 *     (ADR 0003 P2 — the regenerated matplotlib PNG is the only
 *     deck-embeddable bitmap kind in the pipeline).
 *
 * The vendored deck/ chain is byte-stable (ADR 0003 D7) and is consumed
 * as-is via createRequire — never modified.
 */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';

/** Orchestrate quality gate: minimum slide count (validate_deck.py default). */
const DEFAULT_MIN_SLIDES = 12;
/** OpenRouter chat completions endpoint (prod-only closure). */
const OPENROUTER_URL = 'https://openrouter.ai/api/v1/chat/completions';
/** Default model for the prod OpenRouter closure (vendored orchestrate parity). */
const DEFAULT_OPENROUTER_MODEL = 'anthropic/claude-sonnet-4';
/** Max completion tokens for one extraction reply (vendored orchestrate parity). */
const DEFAULT_MAX_TOKENS = 8000;
/** Default python executable for the chart-regen pre-step. */
const DEFAULT_PYTHON_BIN = 'python3';
/** Upward search depth when locating the repo root from cwd. */
const REPO_ROOT_SEARCH_DEPTH = 6;

/** The orchestrate resources contract — produced UNMODIFIED by the CV service. */
export interface OrchestrateResources {
  title: string;
  transcript: string;
  segments: unknown[];
  figureLabels: unknown[];
  formulas: unknown[];
  charts: ChartResource[];
}

/** One mode-B chart entry of the resources bundle (bundle.py shape). */
export interface ChartResource {
  snapshot?: number | null;
  kind: string;
  struct: unknown;
  conf?: number;
  t?: number;
  verification_status?: string;
}

export interface LlmMessage {
  role: string;
  content: string;
}

/** Injected LLM: OpenAI-style messages[] → assistant text. */
export type LlmFn = (messages: LlmMessage[]) => Promise<string>;

/** Optional classifier override (bypasses the vendored route() heuristics). */
export type ClassifyFn = (resources: OrchestrateResources) => Promise<{ type: string }>;

/** Vendored orchestrate() outcome shape (deck/scripts/orchestrate.js). */
export interface OrchestrateOutcome {
  ok: boolean;
  type: string;
  attempts: number;
  out: string;
  routedFrom?: string;
  report?: string;
}

export type OrchestrateFn = (
  resources: OrchestrateResources,
  outPath: string,
  opts: {
    llm: LlmFn;
    minSlides: number;
    link?: string;
    classify?: ClassifyFn;
  }
) => Promise<OrchestrateOutcome>;

/** Chart-regen pre-step result: pngPath=null means LABEL-ONLY fallback. */
export interface ChartAsset {
  snapshot: number | null;
  pngPath: string | null;
}

export interface RunnerResult extends OrchestrateOutcome {
  chartAssets: ChartAsset[];
  /**
   * orchestrate() calls that died on a BUILDER crash (template render on
   * malformed LLM content) and were retried with a fresh conversation. The
   * vendored loop feeds back JSON-parse failures but lets builder exceptions
   * escape — and deck/ is byte-stable (ADR 0003 D7), so the retry lives
   * HERE. Each crash consumed ≥1 LLM content attempt (counted as 1 for G2).
   */
  crashedAttempts: number;
}

/** Fresh-conversation retries after a builder crash (vendored-loop escape). */
const BUILD_CRASH_RETRIES = 1;

// ── Deterministic content normalization (PR-H2 live finding) ─────────────────
// Sonnet repeatedly emits `metrics`/`scores` as an OBJECT MAP (or strings)
// where the vendored kpis template requires [{value, unit?, label}] — and a
// builder crash escapes the vendored feedback loop. The harness normalizes
// the LLM text BEFORE the vendored parser sees it (deck/ stays byte-stable,
// ADR 0003 D7). Faithful transforms only — nothing is invented.

/** Recipe keys the kpis template renders as stat arrays. */
const STAT_ARRAY_KEYS = ['metrics', 'scores'] as const;

function coerceStatEntry(entry: unknown): Record<string, unknown> | null {
  if (typeof entry === 'string') return { value: entry, label: '' };
  if (typeof entry === 'number') return { value: String(entry), label: '' };
  if (typeof entry === 'object' && entry !== null && !Array.isArray(entry)) {
    const record = entry as Record<string, unknown>;
    if (record['value'] !== undefined) {
      return { ...record, value: String(record['value']) };
    }
    // {label: value}-shaped single pair → one stat
    const pairs = Object.entries(record);
    if (pairs.length === 1 && typeof pairs[0]![1] !== 'object') {
      return { label: pairs[0]![0], value: String(pairs[0]![1]) };
    }
  }
  return null;
}

/** Normalize fragile stat fields of a content JSON; non-JSON passes through. */
export function normalizeDeckContent(raw: string): string {
  const candidates = [raw.trim()];
  const fenced = /```(?:json)?\s*([\s\S]*?)```/.exec(raw);
  if (fenced?.[1]) candidates.push(fenced[1].trim());
  const first = raw.indexOf('{');
  const last = raw.lastIndexOf('}');
  if (first >= 0 && last > first) candidates.push(raw.slice(first, last + 1));

  for (const candidate of candidates) {
    let parsed: unknown;
    try {
      parsed = JSON.parse(candidate);
    } catch {
      continue;
    }
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return raw;
    const content = parsed as Record<string, unknown>;
    let changed = false;
    for (const key of STAT_ARRAY_KEYS) {
      const value = content[key];
      if (value === undefined || value === null) continue;
      if (Array.isArray(value)) {
        const coerced = value.map(coerceStatEntry).filter((v) => v !== null);
        if (coerced.length !== value.length || coerced.some((v, i) => v !== value[i])) {
          if (coerced.length > 0) content[key] = coerced;
          else delete content[key];
          changed = true;
        }
        continue;
      }
      if (typeof value === 'object') {
        // object map {label: value, ...} → [{label, value}]
        content[key] = Object.entries(value as Record<string, unknown>)
          .filter(([, v]) => typeof v !== 'object')
          .map(([label, v]) => ({ label, value: String(v) }));
        changed = true;
        continue;
      }
      // bare string/number — not renderable as a stat row
      delete content[key];
      changed = true;
    }
    return changed ? JSON.stringify(content) : raw;
  }
  return raw;
}

/** Wrap an llm so every reply passes the deterministic normalizer. */
function withContentNormalizer(llm: LlmFn): LlmFn {
  return async (messages: LlmMessage[]): Promise<string> =>
    normalizeDeckContent(await llm(messages));
}

export interface RunnerOptions {
  /** Injected llm (REQUIRED in dev/test; prod may rely on OPENROUTER_API_KEY). */
  llm?: LlmFn;
  /** Optional classifier override (avoids llm-based routing). */
  classify?: ClassifyFn;
  minSlides?: number;
  link?: string;
  pythonBin?: string;
  /** Test seam — defaults to the vendored deck/scripts/orchestrate.js. */
  orchestrateImpl?: OrchestrateFn;
}

/** Minimal config slice the runner needs (subset of src/config Config). */
export interface RunnerConfig {
  SLIDEGEN_MODE: 'dev' | 'prod';
  OPENROUTER_API_KEY?: string | undefined;
}

/**
 * Construct the llm the runner will inject into orchestrate().
 *
 * Resolution order — fail-closed:
 *   1. an explicitly injected llm (dev/test stubs, prod overrides), else
 *   2. prod + OPENROUTER_API_KEY → the prod-only OpenRouter closure, else
 *   3. THROW. The refusal happens BEFORE orchestrate() (or any vendored
 *      code) runs, so the vendored callOpenRouter default is unreachable.
 */
export function buildLlm(config: RunnerConfig, injected?: LlmFn): LlmFn {
  if (injected) return injected;
  if (config.SLIDEGEN_MODE === 'prod' && config.OPENROUTER_API_KEY) {
    return openRouterLlm(config.OPENROUTER_API_KEY);
  }
  throw new Error(
    'deck runner refused to start: no llm injected and no prod OpenRouter config. ' +
      'Dev/test must inject a stub llm (LLM API ban); prod requires SLIDEGEN_MODE=prod ' +
      'with OPENROUTER_API_KEY. orchestrate() was NOT called.'
  );
}

/** PROD-ONLY OpenRouter closure (mirrors the vendored callOpenRouter shape). */
function openRouterLlm(apiKey: string, model: string = DEFAULT_OPENROUTER_MODEL): LlmFn {
  return async (messages: LlmMessage[]): Promise<string> => {
    const response = await fetch(OPENROUTER_URL, {
      method: 'POST',
      headers: { 'content-type': 'application/json', authorization: `Bearer ${apiKey}` },
      body: JSON.stringify({ model, max_tokens: DEFAULT_MAX_TOKENS, messages }),
    });
    const data = (await response.json()) as {
      choices?: Array<{ message?: { content?: string } }>;
    };
    return data.choices?.[0]?.message?.content ?? '';
  };
}

/**
 * Chart-regen pre-step: mode-B struct → brand matplotlib PNG (≥ 300 dpi) via
 * `python -m deck_tools.chart_regen`. ANY failure (unsupported struct, regen
 * None, missing python/matplotlib, crash) yields pngPath=null — the chart
 * stays label-only; a raw frame is never substituted (ADR 0003 P2).
 */
export function regenCharts(
  charts: ChartResource[],
  artifactsDir: string,
  pythonBin: string = DEFAULT_PYTHON_BIN
): ChartAsset[] {
  return charts.map((chart, index) => {
    const outPng = path.join(artifactsDir, `chart_${index}.png`);
    try {
      const stdout = execFileSync(pythonBin, ['-m', 'deck_tools.chart_regen'], {
        cwd: path.join(findRepoRoot(), 'py'),
        input: JSON.stringify({ struct: chart.struct, out: outPng }),
        encoding: 'utf8',
      });
      const parsed = JSON.parse(stdout) as { png: string | null };
      return { snapshot: chart.snapshot ?? null, pngPath: parsed.png };
    } catch {
      return { snapshot: chart.snapshot ?? null, pngPath: null };
    }
  });
}

/**
 * Run the full deck-build step: chart-regen pre-step, then the vendored
 * orchestrate() FAIL→feedback→PASS loop with the ALWAYS-injected llm.
 */
export async function runOrchestrate(
  resources: OrchestrateResources,
  outPath: string,
  config: RunnerConfig,
  options: RunnerOptions = {}
): Promise<RunnerResult> {
  // 1. llm FIRST — the refusal path must trigger before any vendored code.
  //    Every reply passes the deterministic stat-shape normalizer.
  const llm = withContentNormalizer(buildLlm(config, options.llm));

  // 2. chart-regen pre-step (failure → label-only, never raw frames).
  const chartAssets = regenCharts(
    resources.charts ?? [],
    path.dirname(outPath),
    options.pythonBin
  );

  // 3. vendored self-correction loop, llm explicitly injected. A builder
  //    crash escapes the vendored loop (only JSON-parse failures feed back),
  //    so it is retried here with a fresh conversation.
  const orchestrate = options.orchestrateImpl ?? loadVendoredOrchestrate();
  const orchestrateOpts = {
    llm,
    minSlides: options.minSlides ?? DEFAULT_MIN_SLIDES,
    ...(options.link !== undefined ? { link: options.link } : {}),
    ...(options.classify !== undefined ? { classify: options.classify } : {}),
  };
  let crashedAttempts = 0;
  for (;;) {
    try {
      const outcome = await orchestrate(resources, outPath, orchestrateOpts);
      return { ...outcome, chartAssets, crashedAttempts };
    } catch (err) {
      crashedAttempts += 1;
      if (crashedAttempts > BUILD_CRASH_RETRIES) throw err;
    }
  }
}

/** Absolute path of deck/scripts/orchestrate.js, found from the repo root. */
export function vendoredOrchestratePath(): string {
  return path.join(findRepoRoot(), 'deck', 'scripts', 'orchestrate.js');
}

/** Absolute path of deck/scripts/validate_deck.py (for independent re-checks). */
export function vendoredValidatorPath(): string {
  return path.join(findRepoRoot(), 'deck', 'scripts', 'validate_deck.py');
}

function loadVendoredOrchestrate(): OrchestrateFn {
  const modulePath = vendoredOrchestratePath();
  const requireVendored = createRequire(modulePath);
  const vendored = requireVendored(modulePath) as { orchestrate: OrchestrateFn };
  return vendored.orchestrate;
}

/**
 * Locate the repo root (the directory containing deck/scripts/orchestrate.js)
 * by walking up from cwd. Works for the compiled CLI (run from the repo root)
 * and for vitest (also run from the repo root) without relying on __dirname,
 * which is unavailable under the ESM test transform.
 */
function findRepoRoot(start: string = process.cwd()): string {
  let dir = path.resolve(start);
  for (let depth = 0; depth < REPO_ROOT_SEARCH_DEPTH; depth++) {
    if (fs.existsSync(path.join(dir, 'deck', 'scripts', 'orchestrate.js'))) {
      return dir;
    }
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  throw new Error(
    `could not locate the repo root (deck/scripts/orchestrate.js) from ${start}`
  );
}
