/**
 * PR-F3 acceptance tests for the deck runner (src/deck/orchestrate-runner.ts).
 *
 * Build E2E — runs the REAL vendored chain (deck/scripts/orchestrate.js →
 * deck_recipes.js/pptxgenjs → validate_deck.py) with a scripted stub llm:
 * call 1 returns content that GENUINELY fails validate_deck (6 slides < 12),
 * the feedback loop re-asks with the FAIL report, call 2 returns content that
 * genuinely passes (14 slides). No network, no OpenRouter — the llm is a
 * local closure (LLM API ban).
 *
 * Also covered:
 *   - llm gating: the runner refuses BEFORE any vendored code runs when no
 *     llm can be constructed, and ALWAYS passes an explicit llm option, so
 *     the vendored callOpenRouter default parameter is structurally
 *     unreachable from this path.
 *   - chart-regen failure = label-only fallback (ADR 0003 P2), extended to
 *     the integrated runner path: resources reach orchestrate UNMODIFIED and
 *     raw-frame-free.
 *
 * Fixture: fixtures/recipe-howto-pass.json — the vendored reference howto
 * content (deck/references/recipe_example.js), synthetic demo material.
 * Requirements: python3 on PATH (validate_deck.py is stdlib-only) and the
 * vendored deck/ npm deps installed (pptxgenjs) — CI installs them in the
 * vitest job.
 */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterAll, describe, expect, it } from 'vitest';
import {
  buildLlm,
  normalizeDeckContent,
  regenCharts,
  runOrchestrate,
  vendoredValidatorPath,
  type ChartResource,
  type LlmFn,
  type LlmMessage,
  type OrchestrateFn,
  type OrchestrateOutcome,
  type OrchestrateResources,
  type RunnerConfig,
} from '@/deck/orchestrate-runner';
import passContent from './fixtures/recipe-howto-pass.json';

const DEV_CONFIG: RunnerConfig = { SLIDEGEN_MODE: 'dev' };

/** validate_deck.py default quality gate — mirrors the runner default. */
const MIN_SLIDES = 12;

/** A struct chart_regen cannot regenerate → must fall back to label-only. */
const UNSUPPORTED_CHART: ChartResource = {
  snapshot: 0,
  kind: 'chart',
  struct: { chart_type: 'pie3d-unsupported', series: [] },
  conf: 0.9,
  verification_status: 'pending',
};

/** Synthetic CV resources bundle (bundle.py RESOURCE_KEYS shape). */
function makeResources(): OrchestrateResources {
  return {
    title: 'Synthetic build E2E talk',
    transcript: 'synthetic transcript text',
    segments: [
      { index: 0, from_sec: 0, to_sec: 15, title: 'Intro', summary: 'synthetic intro' },
      { index: 1, from_sec: 15, to_sec: 30, title: 'Method', summary: 'synthetic method' },
    ],
    figureLabels: [{ snapshot: 0, ts: 15, kind: 'chart', note: 'synthetic chart hint' }],
    formulas: [
      { snapshot: 0, latex: 'y = ax + b', conf: 0.9, t: 15, verification_status: 'pending' },
    ],
    charts: [UNSUPPORTED_CHART],
  };
}

/**
 * FAIL-then-PASS scripted llm content. The FAIL variant keeps only one step
 * and drops the tools/pitfalls/troubleshoot/metrics sections → buildRecipe
 * produces 6 slides → validate_deck FAILs the [분량] (volume) check for real.
 */
const {
  tools: _tools,
  toolsTitle: _toolsTitle,
  toolsIntro: _toolsIntro,
  pitfalls: _pitfalls,
  troubleshoot: _troubleshoot,
  troubleshootTitle: _troubleshootTitle,
  metrics: _metrics,
  metricsTitle: _metricsTitle,
  ...failBase
} = passContent;
const failContent = { ...failBase, steps: passContent.steps.slice(0, 1) };

const tempDirs: string[] = [];

function makeOutPath(): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'slidegen-f3-e2e-'));
  tempDirs.push(dir);
  return path.join(dir, 'deck.pptx');
}

afterAll(() => {
  // Generated .pptx artifacts stay strictly in tmp — never in the repo.
  for (const dir of tempDirs) fs.rmSync(dir, { recursive: true, force: true });
});

describe('build E2E — stub llm FAIL → feedback → PASS → .pptx (real vendored chain)', () => {
  it(
    'self-corrects in exactly 2 llm calls and produces a validate_deck-PASSing deck',
    { timeout: 120_000 },
    async () => {
      const llmCalls: LlmMessage[][] = [];
      const scriptedLlm: LlmFn = (messages) => {
        llmCalls.push(messages.map((m) => ({ ...m })));
        const reply = llmCalls.length === 1 ? failContent : passContent;
        return Promise.resolve(JSON.stringify(reply));
      };

      const outPath = makeOutPath();
      const result = await runOrchestrate(makeResources(), outPath, DEV_CONFIG, {
        llm: scriptedLlm,
        // Scripted classification: routing must not consume an llm call.
        classify: () => Promise.resolve({ type: 'howto' }),
      });

      // (a) the llm was called EXACTLY 2 times (1 FAIL draft + 1 corrected).
      expect(llmCalls).toHaveLength(2);
      expect(result.ok).toBe(true);
      expect(result.attempts).toBe(2);

      // The feedback loop re-asked WITH the real validator FAIL report.
      const secondCall = llmCalls[1] ?? [];
      const feedback = secondCall.map((m) => m.content).join('\n');
      expect(feedback).toContain('RESULT: FAIL');
      expect(feedback).toContain('[분량]'); // volume check: 6 < 12 slides

      // (b) the .pptx artifact exists (in tmp only — never committed).
      expect(fs.existsSync(outPath)).toBe(true);

      // (c) an INDEPENDENT validate_deck.py re-run passes the quality gate.
      const report = execFileSync(
        'python3',
        [vendoredValidatorPath(), outPath, '--min-slides', String(MIN_SLIDES)],
        { encoding: 'utf8' }
      );
      expect(report).toContain('RESULT: PASS');

      // Integrated chart-regen: the unsupported struct stayed label-only.
      expect(result.chartAssets).toEqual([{ snapshot: 0, pngPath: null }]);
    }
  );
});

describe('llm gating — vendored callOpenRouter default is unreachable from the runner', () => {
  it('refuses BEFORE orchestrate when no llm is injected and config is dev', async () => {
    let orchestrateCalls = 0;
    const orchestrateSpy: OrchestrateFn = (_resources, out, _opts) => {
      orchestrateCalls += 1;
      const outcome: OrchestrateOutcome = { ok: true, type: 'howto', attempts: 1, out };
      return Promise.resolve(outcome);
    };
    await expect(
      runOrchestrate(makeResources(), makeOutPath(), DEV_CONFIG, {
        orchestrateImpl: orchestrateSpy,
      })
    ).rejects.toThrow(/refused to start/);
    expect(orchestrateCalls).toBe(0);
  });

  it('buildLlm throws in dev without an injected llm (fail-closed)', () => {
    expect(() => buildLlm(DEV_CONFIG)).toThrow(/orchestrate\(\) was NOT called/);
    // A prod key alone does not unlock dev either.
    expect(() => buildLlm({ SLIDEGEN_MODE: 'dev', OPENROUTER_API_KEY: 'sk-or-stub' })).toThrow(
      /refused to start/
    );
  });

  it('ALWAYS passes the injected llm to orchestrate (default param never engages)', async () => {
    let stubCalls = 0;
    const stub: LlmFn = () => {
      stubCalls += 1;
      return Promise.resolve('{}');
    };
    let receivedLlm: LlmFn | undefined;
    const impl: OrchestrateFn = (_resources, out, opts) => {
      receivedLlm = opts.llm;
      const outcome: OrchestrateOutcome = { ok: true, type: 'howto', attempts: 1, out };
      return Promise.resolve(outcome);
    };

    await runOrchestrate(makeResources(), makeOutPath(), DEV_CONFIG, {
      llm: stub,
      orchestrateImpl: impl,
    });
    // Behavior check: orchestrate received a defined llm whose replies come
    // from OUR injected stub (wrapped by the deterministic normalizer — so
    // identity is intentionally NOT the contract), never a vendored default.
    expect(receivedLlm).toBeDefined();
    await expect(receivedLlm!([{ role: 'user', content: 'ping' }])).resolves.toBe('{}');
    expect(stubCalls).toBe(1);
  });

  it('prod + OPENROUTER_API_KEY builds the prod-only closure without network', () => {
    const llm = buildLlm({ SLIDEGEN_MODE: 'prod', OPENROUTER_API_KEY: 'sk-or-stub' });
    expect(typeof llm).toBe('function');
  });

  it('an injected llm takes precedence over the prod closure', () => {
    const stub: LlmFn = () => Promise.resolve('');
    expect(buildLlm({ SLIDEGEN_MODE: 'prod', OPENROUTER_API_KEY: 'sk-or-stub' }, stub)).toBe(stub);
  });
});

describe('chart-regen pre-step — failure = label-only fallback (ADR 0003 P2)', () => {
  it('unsupported struct → pngPath null and NO png file written', () => {
    const dir = path.dirname(makeOutPath());
    const assets = regenCharts([UNSUPPORTED_CHART], dir);
    expect(assets).toEqual([{ snapshot: 0, pngPath: null }]);
    expect(fs.existsSync(path.join(dir, 'chart_0.png'))).toBe(false);
  });

  it('missing python runtime → pngPath null (crash-safe, never a raw frame)', () => {
    const dir = path.dirname(makeOutPath());
    const supported: ChartResource = {
      snapshot: 1,
      kind: 'chart',
      struct: {
        chart_type: 'line',
        axes: { x: 't', y: 'v' },
        series: [{ name: 's', points: [{ x: 0, y: 0 }] }],
      },
    };
    const assets = regenCharts([supported], dir, '/nonexistent/python-bin');
    expect(assets).toEqual([{ snapshot: 1, pngPath: null }]);
  });

  it('integrated path: resources reach orchestrate UNMODIFIED and raw-frame-free', async () => {
    let received: OrchestrateResources | undefined;
    const impl: OrchestrateFn = (resources, out, _opts) => {
      received = resources;
      const outcome: OrchestrateOutcome = { ok: true, type: 'howto', attempts: 1, out };
      return Promise.resolve(outcome);
    };

    const resources = makeResources();
    const result = await runOrchestrate(resources, makeOutPath(), DEV_CONFIG, {
      llm: () => Promise.resolve('{}'),
      orchestrateImpl: impl,
    });

    // Regen failed (unsupported struct) → label-only; orchestrate still got
    // the ORIGINAL bundle object — no png/raw-frame substitution happened.
    expect(result.chartAssets).toEqual([{ snapshot: 0, pngPath: null }]);
    expect(received).toBe(resources);

    // Structural raw-frame ban (extends PR-F2's bundle ban to this path):
    // nothing image-like may appear anywhere in the serialized resources.
    const serialized = JSON.stringify(received);
    for (const banned of ['.png', '.jpg', '.jpeg', 'data:image', 'png_path', 'png_url']) {
      expect(serialized).not.toContain(banned);
    }
  });
});

describe('builder-crash retry (vendored-loop escape — PR-H2 live finding)', () => {
  const RESOURCES = {
    title: 't',
    transcript: '',
    segments: [],
    figureLabels: [],
    formulas: [],
    charts: [],
  };

  it('retries ONE fresh conversation after a builder crash, reports crashedAttempts', async () => {
    let calls = 0;
    const orchestrateImpl = (async () => {
      calls += 1;
      if (calls === 1) throw new TypeError('stats.slice is not a function');
      return { ok: true, type: 'lecture', attempts: 2, out: '/tmp/deck.pptx' };
    }) as unknown as Parameters<typeof runOrchestrate>[3]['orchestrateImpl'];

    const result = await runOrchestrate(
      RESOURCES,
      '/tmp/slidegen-test-crash/deck.pptx',
      { SLIDEGEN_MODE: 'dev' },
      { llm: async () => '[]', orchestrateImpl }
    );
    expect(result.ok).toBe(true);
    expect(result.crashedAttempts).toBe(1);
    expect(calls).toBe(2);
  });

  it('rethrows after the retry budget is exhausted', async () => {
    const orchestrateImpl = (async () => {
      throw new TypeError('stats.slice is not a function');
    }) as unknown as Parameters<typeof runOrchestrate>[3]['orchestrateImpl'];

    await expect(
      runOrchestrate(
        RESOURCES,
        '/tmp/slidegen-test-crash/deck.pptx',
        { SLIDEGEN_MODE: 'dev' },
        { llm: async () => '[]', orchestrateImpl }
      )
    ).rejects.toThrow('stats.slice');
  });
});

describe('normalizeDeckContent — deterministic stat-shape repair (PR-H2)', () => {
  it('object-map metrics → [{label, value}] array', () => {
    const raw = JSON.stringify({ title: 't', metrics: { 다운로드: '300만', 별점: 4.8 } });
    const out = JSON.parse(normalizeDeckContent(raw)) as { metrics: unknown };
    expect(out.metrics).toEqual([
      { label: '다운로드', value: '300만' },
      { label: '별점', value: '4.8' },
    ]);
  });

  it('string entries inside a metrics array → {value, label} objects', () => {
    const raw = JSON.stringify({ metrics: ['300만 다운로드', { value: 4.8, label: '별점' }] });
    const out = JSON.parse(normalizeDeckContent(raw)) as { metrics: unknown };
    expect(out.metrics).toEqual([
      { value: '300만 다운로드', label: '' },
      { value: '4.8', label: '별점' },
    ]);
  });

  it('bare-string scores are dropped, valid arrays untouched, non-JSON passes through', () => {
    const dropped = JSON.parse(
      normalizeDeckContent(JSON.stringify({ scores: 'high' }))
    ) as Record<string, unknown>;
    expect(dropped).not.toHaveProperty('scores');

    const valid = JSON.stringify({ metrics: [{ value: '1', label: 'a' }] });
    expect(normalizeDeckContent(valid)).toBe(valid);

    expect(normalizeDeckContent('not json at all')).toBe('not json at all');
    const routing = JSON.stringify({ type: 'explainer' });
    expect(normalizeDeckContent(routing)).toBe(routing);
  });

  it('repairs fenced JSON replies too', () => {
    const raw = '```json\n{"metrics": {"속도": "3배"}}\n```';
    const out = JSON.parse(normalizeDeckContent(raw)) as { metrics: unknown };
    expect(out.metrics).toEqual([{ label: '속도', value: '3배' }]);
  });
});
