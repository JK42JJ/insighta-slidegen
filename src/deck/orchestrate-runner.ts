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
  formulas: FormulaResource[];
  charts: ChartResource[];
}

/** One mode-B chart entry of the resources bundle (bundle.py shape). */
export interface ChartResource {
  /** PR-A: stable key matching the regenerated asset to the LLM's figureRef. */
  figure_id?: string;
  snapshot?: number | null;
  kind: string;
  struct: unknown;
  conf?: number;
  t?: number;
  verification_status?: string;
}

/** One mode-C formula entry (bundle.py shape — LaTeX, no struct). */
export interface FormulaResource {
  figure_id?: string;
  snapshot?: number | null;
  latex: string;
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
    /** PR-A §1b: {figure_id → regenerated PNG path} the recipe places by ref. */
    figureAssets?: Record<string, string>;
    /** A1: {figure_id → {headers, rows}} for table-kind figures rendered as
     * NATIVE pptx tables (editable) instead of a raster; invalid structs are
     * absent so the recipe falls back to the image. */
    figureTables?: Record<string, { headers: unknown[]; rows: unknown[] }>;
  }
) => Promise<OrchestrateOutcome>;

/** Chart-regen pre-step result: pngPath=null means LABEL-ONLY fallback. */
export interface ChartAsset {
  /** figure_id key (PR-A) — links this asset to the LLM's figureRef. */
  figureId: string | null;
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

// ── A3: keep the on-slide diagram font legible at the figure's placed size ───
// The figure slot in figureSlide (slide_templates.js) and these MUST agree.
const FIGURE_DPI = 300;
const FIGURE_SLOT_W_IN = 12.09; // CW (content width)
const FIGURE_SLOT_H_IN = 4.7; // figureSlide slot height (with caption)
const FIGURE_MAX_SCALE_UP = 1.6; // matches _fitContain's _MAX_FIGURE_SCALE_UP
const DIAGRAM_BASE_FONT_PT = 11; // diagram_regen node fontsize at font_scale=1
const DIAGRAM_MIN_EFF_PT = 10; // floor for the on-slide font
const DIAGRAM_MAX_FONT_SCALE = 2.0; // bound the bump (graphviz coupling damps it)

/** PNG intrinsic size from the IHDR (offset 16/20, big-endian). null on a
 * non-PNG / short read. Mirrors slide_templates.js `_pngSize`. */
function pngSize(p: string): { w: number; h: number } | null {
  try {
    const fd = fs.openSync(p, 'r');
    const buf = Buffer.alloc(24);
    fs.readSync(fd, buf, 0, 24, 0);
    fs.closeSync(fd);
    if (buf.toString('ascii', 1, 4) !== 'PNG') return null;
    const w = buf.readUInt32BE(16);
    const h = buf.readUInt32BE(20);
    return w > 0 && h > 0 ? { w, h } : null;
  } catch {
    return null;
  }
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
  pythonBin: string = DEFAULT_PYTHON_BIN,
  formulas: FormulaResource[] = []
): ChartAsset[] {
  const py = path.join(findRepoRoot(), 'py');
  // module: chart_regen (matplotlib data charts + equations) OR diagram_regen
  // (Graphviz structure: diagram/table — roadmap 2). Routed by kind.
  const run = (module: string, job: object, outPng: string): string | null => {
    try {
      const stdout = execFileSync(pythonBin, ['-m', module], {
        cwd: py,
        input: JSON.stringify({ ...job, out: outPng }),
        encoding: 'utf8',
      });
      return (JSON.parse(stdout) as { png: string | null }).png;
    } catch {
      return null;
    }
  };
  /**
   * A3 font lower bound (diagram/table only): render once, then if the figure
   * will be scaled DOWN so far that its on-slide font drops below the floor,
   * re-render with a bumped font_scale. Graphviz couples font↔layout (a bigger
   * font grows the graph, which then downscales more), so the bump is damped —
   * bounded by DIAGRAM_MAX_FONT_SCALE and accepted as a best-effort nudge, not
   * exact targeting. The scale-UP (oversized) case is handled at placement by
   * _fitContain's cap, so it needs no re-render here.
   */
  const renderDiagram = (struct: unknown, outPng: string): string | null => {
    const first = run('deck_tools.diagram_regen', { struct }, outPng);
    if (!first) return null;
    const dim = pngSize(first);
    if (!dim) return first;
    const scale = Math.min(
      FIGURE_SLOT_W_IN / (dim.w / FIGURE_DPI),
      FIGURE_SLOT_H_IN / (dim.h / FIGURE_DPI),
      FIGURE_MAX_SCALE_UP
    );
    const effFont = DIAGRAM_BASE_FONT_PT * scale;
    if (effFont >= DIAGRAM_MIN_EFF_PT) return first;
    const fontScale = Math.min(DIAGRAM_MAX_FONT_SCALE, DIAGRAM_MIN_EFF_PT / effFont);
    return run('deck_tools.diagram_regen', { struct, font_scale: fontScale }, outPng) ?? first;
  };
  // Data charts (line/bar/scatter) → chart_regen; diagram/table → diagram_regen.
  // Either failing returns null → label-only (never a raw frame, ADR 0003 P2).
  const STRUCTURE_KINDS = new Set(['diagram', 'table']);
  const chartAssets = charts.map((chart, index) => {
    const out = path.join(artifactsDir, `chart_${index}.png`);
    const pngPath = STRUCTURE_KINDS.has(chart.kind)
      ? renderDiagram(chart.struct, out)
      : run('deck_tools.chart_regen', { struct: chart.struct }, out);
    return { figureId: chart.figure_id ?? null, snapshot: chart.snapshot ?? null, pngPath };
  });
  // §1b: equations render too (mode C → mathtext PNG), same figure_id keying.
  const formulaAssets = formulas.map((formula, index) => ({
    figureId: formula.figure_id ?? null,
    snapshot: formula.snapshot ?? null,
    pngPath: run(
      'deck_tools.chart_regen',
      { kind: 'equation', latex: formula.latex },
      path.join(artifactsDir, `eq_${index}.png`)
    ),
  }));
  return [...chartAssets, ...formulaAssets];
}

/** {figure_id → pngPath} for assets that rendered (PR-A §1b placement map). */
export function buildFigureAssets(assets: ChartAsset[]): Record<string, string> {
  const map: Record<string, string> = {};
  for (const a of assets) {
    if (a.figureId && a.pngPath) map[a.figureId] = a.pngPath;
  }
  return map;
}

/**
 * A1: {figure_id → {headers, rows}} for table-kind charts carrying a valid
 * struct. The recipe renders these as NATIVE pptx tables (editable, no raster);
 * a table with no headers or no rows is omitted, so injectFigureSlides falls
 * back to the diagram_regen PNG (an image beats a broken empty table).
 */
export function buildFigureTables(
  charts: ChartResource[]
): Record<string, { headers: unknown[]; rows: unknown[] }> {
  const map: Record<string, { headers: unknown[]; rows: unknown[] }> = {};
  for (const c of charts) {
    if (c.kind !== 'table' || !c.figure_id) continue;
    const s = c.struct as { headers?: unknown; rows?: unknown } | null;
    if (
      s &&
      Array.isArray(s.headers) &&
      s.headers.length > 0 &&
      Array.isArray(s.rows) &&
      s.rows.length > 0
    ) {
      map[c.figure_id] = { headers: s.headers, rows: s.rows };
    }
  }
  return map;
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

  // 2. chart+equation regen pre-step (failure → label-only, never raw frames).
  const chartAssets = regenCharts(
    resources.charts ?? [],
    path.dirname(outPath),
    options.pythonBin,
    resources.formulas ?? []
  );
  const figureAssets = buildFigureAssets(chartAssets);
  // A1: table-kind figures render as native pptx tables; invalid structs fall
  // back to the PNG already in figureAssets.
  const figureTables = buildFigureTables(resources.charts ?? []);

  // 3. vendored self-correction loop, llm explicitly injected. A builder
  //    crash escapes the vendored loop (only JSON-parse failures feed back),
  //    so it is retried here with a fresh conversation.
  const orchestrate = options.orchestrateImpl ?? loadVendoredOrchestrate();
  const orchestrateOpts = {
    llm,
    minSlides: options.minSlides ?? DEFAULT_MIN_SLIDES,
    figureAssets, // §1b: recipe places by figure_id; empty map = all label-only
    figureTables, // A1: native-table route for table-kind figures
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
