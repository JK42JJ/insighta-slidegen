/**
 * PR-H2 real-pipeline tests — ALL boundaries stubbed (LLM/vision API ban:
 * no live model, service, or DB call ever happens here).
 *
 * Pins the measurement policies:
 *   - fetch_v2 gate miss → INPUT_UNSUITABLE, no slide_jobs row
 *   - dead-link acquire error → INPUT_UNSUITABLE (sample bad ≠ pipeline broke)
 *   - CV stage failures → StageFailureError with the service stage + failJob
 *   - orchestrate !ok → failureStage 'validate' with attempts preserved
 *   - videoId NEVER survives into an error message (sanitized to the index)
 */
import { describe, expect, it } from 'vitest';
import { CvExtractionError, type extractFigures } from '@/cv/cv-client';
import type { fetchV2 } from '@/fetch/v2-reader';
import { buildRealPipeline, INPUT_UNSUITABLE_PREFIX } from '@/measure/pipeline';
import type { RealPipelineDeps } from '@/measure/pipeline';
import { StageFailureError } from '@/measure/runner';
import type { runOrchestrate } from '@/deck/orchestrate-runner';
import type { planSlides } from '@/plan/slide-planner';

const ENTRY = { index: 'V01', videoId: 'realvideo01' };

const SUMMARY = {
  core: { one_liner: 'Synthetic talk' },
  segments: {
    sections: [{ from_sec: 0, to_sec: 30, title: 'Sec', summary: 'text' }],
    atoms: [],
  },
} as unknown as Awaited<ReturnType<typeof fetchV2>>;

const CV_RESULT = {
  job_id: 'cv-job',
  figures: [
    { cv_figure_id: 'f1', kind: 'chart', png_url: '/tmp/f1.png', extraction_conf: 0.5 },
    { cv_figure_id: 'f2', kind: 'table', png_url: '/tmp/f2.png', extraction_conf: 0.9 },
    { cv_figure_id: 'f3', kind: 'keyframe', png_url: '/tmp/f3.png' },
  ],
  keyframe_count: 3,
  resources: {
    title: 't',
    transcript: '',
    segments: [],
    figureLabels: [],
    formulas: [],
    charts: [],
  },
} as unknown as Awaited<ReturnType<typeof extractFigures>>;

interface RepoLog {
  created: number;
  failures: Array<{ stage: string; error: string }>;
  completed: Array<{ attempts: number }>;
}

function stubRepo(log: RepoLog): NonNullable<RealPipelineDeps['repo']> {
  return {
    createJob: async () => {
      log.created += 1;
      return 'job-1';
    },
    enterJobStage: async () => undefined,
    completeJob: async (_id, attempts) => {
      log.completed.push({ attempts });
    },
    failJob: async (_id, stage, error) => {
      log.failures.push({ stage, error });
    },
    upsertDeck: async () => ({ deckId: 'deck-1', created: true }),
    replaceSlides: async () => undefined,
    replaceFigures: async () => undefined,
    setDeckStatus: async () => undefined,
  } as unknown as NonNullable<RealPipelineDeps['repo']>;
}

function makeDeps(log: RepoLog, overrides: Partial<RealPipelineDeps> = {}): RealPipelineDeps {
  return {
    prisma: {} as RealPipelineDeps['prisma'],
    artifactsDir: '/tmp/slidegen-measure-test',
    appConfig: { SLIDEGEN_MODE: 'dev' },
    fetchV2Impl: (async () => SUMMARY) as unknown as typeof fetchV2,
    extractFiguresImpl: (async () => CV_RESULT) as unknown as typeof extractFigures,
    planSlidesImpl: (() => ({
      slides: [],
      v2_fingerprint: 'fp',
    })) as unknown as typeof planSlides,
    runOrchestrateImpl: (async () => ({
      ok: true,
      type: 'lecture',
      attempts: 1,
      out: 'deck.pptx',
      chartAssets: [],
    })) as unknown as typeof runOrchestrate,
    repo: stubRepo(log),
    ...overrides,
  };
}

function freshLog(): RepoLog {
  return { created: 0, failures: [], completed: [] };
}

describe('buildRealPipeline', () => {
  it('happy path: PASS with attempts, conf over conf-carrying figures only', async () => {
    const log = freshLog();
    const result = await buildRealPipeline(makeDeps(log))(ENTRY);

    expect(result.validatePass).toBe(true);
    expect(result.attempts).toBe(1);
    expect(result.failureStage).toBeNull();
    // f1 (0.5) below 0.7, f2 (0.9) above, f3 carries no conf → 1/2
    expect(result.conf).toEqual({ belowThreshold: 1, total: 2 });
    expect(log.completed).toEqual([{ attempts: 1 }]);
    expect(log.failures).toHaveLength(0);
  });

  it('fetch_v2 gate miss → INPUT_UNSUITABLE and NO job row', async () => {
    const log = freshLog();
    const deps = makeDeps(log, {
      fetchV2Impl: (async () => {
        throw new Error('no v2 rich-summary for realvideo01');
      }) as unknown as typeof fetchV2,
    });

    const error = await buildRealPipeline(deps)(ENTRY).catch((err: unknown) => err as Error);
    expect((error as Error).message).toContain(INPUT_UNSUITABLE_PREFIX);
    expect((error as Error).message).not.toContain(ENTRY.videoId);
    expect((error as Error).message).toContain('V01');
    expect(log.created).toBe(0);
  });

  it('dead-link acquire failure → INPUT_UNSUITABLE, not a stage failure', async () => {
    const log = freshLog();
    const deps = makeDeps(log, {
      extractFiguresImpl: (async () => {
        throw new CvExtractionError('cv job failed: ERROR: Video unavailable', 'acquire');
      }) as unknown as typeof extractFigures,
    });

    const error = await buildRealPipeline(deps)(ENTRY).catch((err: unknown) => err as Error);
    expect(error).not.toBeInstanceOf(StageFailureError);
    expect((error as Error).message).toContain(INPUT_UNSUITABLE_PREFIX);
    // the DB row still records the acquire failure
    expect(log.failures).toEqual([
      { stage: 'acquire', error: 'cv job failed: ERROR: Video unavailable' },
    ]);
  });

  it('CV stage failure → StageFailureError with the service stage, sanitized', async () => {
    const log = freshLog();
    const deps = makeDeps(log, {
      extractFiguresImpl: (async () => {
        throw new CvExtractionError('cv job failed: select blew up on realvideo01', 'select');
      }) as unknown as typeof extractFigures,
    });

    const error = await buildRealPipeline(deps)(ENTRY).catch((err: unknown) => err);
    expect(error).toBeInstanceOf(StageFailureError);
    expect((error as StageFailureError).stage).toBe('select');
    expect((error as StageFailureError).message).not.toContain(ENTRY.videoId);
    expect((error as StageFailureError).message).toContain('V01');
    expect(log.failures[0]!.stage).toBe('select');
  });

  it('stage-less CV failure → plain Error (manual attribution), acquire pinned in DB', async () => {
    const log = freshLog();
    const deps = makeDeps(log, {
      extractFiguresImpl: (async () => {
        throw new CvExtractionError('cv job failed: bundle assembly crashed', null);
      }) as unknown as typeof extractFigures,
    });

    const error = await buildRealPipeline(deps)(ENTRY).catch((err: unknown) => err);
    expect(error).not.toBeInstanceOf(StageFailureError);
    expect(log.failures[0]!.stage).toBe('acquire');
  });

  it('orchestrate throw → StageFailureError(build)', async () => {
    const log = freshLog();
    const deps = makeDeps(log, {
      runOrchestrateImpl: (async () => {
        throw new Error('vendored orchestrate crashed');
      }) as unknown as typeof runOrchestrate,
    });

    const error = await buildRealPipeline(deps)(ENTRY).catch((err: unknown) => err);
    expect(error).toBeInstanceOf(StageFailureError);
    expect((error as StageFailureError).stage).toBe('build');
  });

  it('validate FAIL after the attempt budget → measurement, not throw', async () => {
    const log = freshLog();
    const deps = makeDeps(log, {
      runOrchestrateImpl: (async () => ({
        ok: false,
        type: 'lecture',
        attempts: 2,
        out: '',
        chartAssets: [],
      })) as unknown as typeof runOrchestrate,
    });

    const result = await buildRealPipeline(deps)(ENTRY);
    expect(result.validatePass).toBe(false);
    expect(result.failureStage).toBe('validate');
    expect(result.attempts).toBe(2);
    // conf still measured — the CV leg succeeded
    expect(result.conf).toEqual({ belowThreshold: 1, total: 2 });
    expect(log.failures[0]!.stage).toBe('validate');
  });
});
