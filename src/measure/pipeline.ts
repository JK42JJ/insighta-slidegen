/**
 * PR-H2: the REAL measurement pipeline — the PipelineFn the ADR 0004 runner
 * injects when measuring V01…V10 against live endpoints.
 *
 * Mirrors the CLI pipeline (src/index.ts): fetch_v2 gate → CV service
 * (acquire…numerize on the Mac Mini, models on the GPU host) → deterministic
 * plan → slide_* persistence → vendored orchestrate self-correction loop.
 * Each run writes ONE slide_jobs row (createJob → enterJobStage →
 * completeJob/failJob) so failure_stage attribution lands in the DB too.
 *
 * Measurement-policy specifics (ADR 0004 / PR-H design):
 *   - videoId NEVER reaches reports/logs: every error message is sanitized
 *     (videoId occurrences → the anonymous index) BEFORE it leaves this module,
 *     and artifacts are keyed by index, not videoId.
 *   - INPUT-UNSUITABLE vs PIPELINE failure: a fetch_v2 gate miss (no v2 / gate
 *     fail) or an acquire error matching the dead-link patterns is prefixed
 *     INPUT_UNSUITABLE — the sample was bad, not the pipeline (V02…V10 are
 *     content-unverified by design).
 *   - LLM API ban: dev/test callers MUST inject runnerOptions.llm (stub);
 *     without it runOrchestrate itself refuses outside prod (fail-closed).
 */
import fs from 'node:fs';
import path from 'node:path';
import type { PrismaClient } from '@prisma/client';
import { CvExtractionError, extractFigures } from '@/cv/cv-client';
import {
  completeJob,
  createJob,
  enterJobStage,
  failJob,
  replaceFigures,
  replaceSlides,
  setDeckStatus,
  upsertDeck,
} from '@/db/slide-repo';
import { runOrchestrate, type RunnerOptions } from '@/deck/orchestrate-runner';
import { fetchV2 } from '@/fetch/v2-reader';
import { G3_CONF_THRESHOLD } from '@/measure/report';
import {
  StageFailureError,
  type PipelineFn,
  type SampleEntry,
  type VideoMeasurement,
} from '@/measure/runner';
import { planSlides } from '@/plan/slide-planner';

/** Report marker distinguishing bad samples from pipeline failures. */
export const INPUT_UNSUITABLE_PREFIX = 'INPUT_UNSUITABLE: ';

/**
 * Acquire-stage error texts that mean the VIDEO is gone/blocked (yt-dlp
 * phrasing), not that the pipeline broke. Matched case-insensitively.
 */
const INPUT_UNSUITABLE_PATTERNS: readonly RegExp[] = [
  /video unavailable/i,
  /private video/i,
  /members-only/i,
  /has been removed/i,
  /not available/i,
  /age[- ]restricted/i,
  /account .* terminated/i,
];

/** Default per-video CV budget — full acquire+CV on a long talk takes
 * minutes; the CLI may override via --cv-timeout-sec. */
const DEFAULT_CV_TIMEOUT_MS = 1_800_000;

export interface RealPipelineDeps {
  prisma: PrismaClient;
  /** Local dir for .pptx artifacts — keyed by INDEX (never videoId). */
  artifactsDir: string;
  /**
   * Observability: when set, the CV SERVICE writes its per-stage tree under
   * `<cvArtifactsRoot>/<index>` on the service host (Mac Mini). Pulling that
   * tree to the local review dir is an ops/follow-up step. Unset = no dump.
   */
  cvArtifactsRoot?: string;
  cvTimeoutMs?: number;
  /**
   * §4 existence experiment: skip the CV leg entirely and build from the v2
   * summary text alone (no figures). Produces the "LLM-only" arm to compare
   * against the figure-placing pipeline. Default false = full pipeline.
   */
  noCv?: boolean;
  /**
   * Config slice (mode + OpenRouter key). When absent, resolved from
   * src/config LAZILY at first run — keeps this module loadable in tests
   * without a full env (the config singleton parses process.env at import).
   */
  appConfig?: { SLIDEGEN_MODE: 'dev' | 'prod'; OPENROUTER_API_KEY?: string | undefined };
  /** Passed through to runOrchestrate (tests inject {llm, orchestrateImpl}). */
  runnerOptions?: RunnerOptions;
  // Test seams — default to the real implementations.
  fetchV2Impl?: typeof fetchV2;
  extractFiguresImpl?: typeof extractFigures;
  runOrchestrateImpl?: typeof runOrchestrate;
  planSlidesImpl?: typeof planSlides;
  repo?: {
    createJob: typeof createJob;
    enterJobStage: typeof enterJobStage;
    completeJob: typeof completeJob;
    failJob: typeof failJob;
    upsertDeck: typeof upsertDeck;
    replaceSlides: typeof replaceSlides;
    replaceFigures: typeof replaceFigures;
    setDeckStatus: typeof setDeckStatus;
  };
}

function isInputUnsuitable(message: string): boolean {
  return INPUT_UNSUITABLE_PATTERNS.some((pattern) => pattern.test(message));
}

/** G3 input: low-confidence ratio over figures that CARRY a confidence. */
function confDistribution(
  figures: Array<{ extraction_conf?: number | undefined }>
): VideoMeasurement['conf'] {
  const withConf = figures.filter((f) => f.extraction_conf !== undefined);
  return {
    belowThreshold: withConf.filter((f) => (f.extraction_conf ?? 1) < G3_CONF_THRESHOLD).length,
    total: withConf.length,
  };
}

/**
 * Builds the real PipelineFn. One call = one video end-to-end; throws are
 * caught by the runner and recorded as failed measurements (StageFailureError
 * carries the ADR 0004 stage).
 */
export function buildRealPipeline(deps: RealPipelineDeps): PipelineFn {
  const {
    prisma,
    artifactsDir,
    cvTimeoutMs = DEFAULT_CV_TIMEOUT_MS,
    runnerOptions = {},
    fetchV2Impl = fetchV2,
    extractFiguresImpl = extractFigures,
    runOrchestrateImpl = runOrchestrate,
    planSlidesImpl = planSlides,
    repo = {
      createJob,
      enterJobStage,
      completeJob,
      failJob,
      upsertDeck,
      replaceSlides,
      replaceFigures,
      setDeckStatus,
    },
  } = deps;

  return async (entry: SampleEntry): Promise<Omit<VideoMeasurement, 'index'>> => {
    const appConfig = deps.appConfig ?? (await import('@/config')).config;
    // videoId → index in every outbound message (PUBLIC-repo sample policy).
    const sanitize = (message: string): string => message.split(entry.videoId).join(entry.index);

    // 1. fetch_v2 gate — a miss means the SAMPLE lacks usable v2 input
    //    (no pipeline ran): no job row, INPUT_UNSUITABLE in the report.
    let summary: Awaited<ReturnType<typeof fetchV2>>;
    try {
      summary = await fetchV2Impl(entry.videoId, prisma);
    } catch (err) {
      throw new Error(`${INPUT_UNSUITABLE_PREFIX}fetch_v2 gate: ${sanitize(errText(err))}`);
    }

    const jobId = await repo.createJob({ videoId: entry.videoId }, prisma);

    // §4 LLM-only arm: skip CV entirely, build from v2 text with no figures.
    // The empty bundle (no charts/formulas) → no figureAssets → 0 figures
    // placed, isolating "what does the CV leg add?" against the full pipeline.
    const EMPTY_CV: Awaited<ReturnType<typeof extractFigures>> = {
      job_id: 'no-cv',
      figures: [],
      keyframe_count: 0,
      resources: {
        title: summary.core.one_liner,
        transcript: '',
        segments: summary.segments?.sections ?? [],
        figureLabels: [],
        formulas: [],
        charts: [],
      },
    };

    // 2. CV extraction (service runs acquire → … → numerize remotely).
    let cvResult: Awaited<ReturnType<typeof extractFigures>>;
    if (deps.noCv) {
      cvResult = EMPTY_CV;
    } else {
      try {
        await repo.enterJobStage(jobId, 'acquire', prisma, {
          timeoutAt: new Date(Date.now() + cvTimeoutMs),
        });
        const cvSections = (summary.segments?.sections ?? []).map((s, i) => ({
          index: i,
          from_sec: s.from_sec,
          to_sec: s.to_sec,
          title: s.title,
          summary: s.summary ?? undefined,
        }));
        cvResult = await extractFiguresImpl(
          {
            youtube_video_id: entry.videoId,
            sections: cvSections,
            mode: appConfig.SLIDEGEN_MODE,
            title: summary.core.one_liner,
            // Observability: the SERVICE writes the per-stage tree (its own
            // filesystem) keyed by the anonymous index — never the video id.
            ...(deps.cvArtifactsRoot
              ? {
                  artifacts_dir: `${deps.cvArtifactsRoot}/${entry.index}`,
                  artifact_index: entry.index,
                }
              : {}),
          },
          { timeoutMs: cvTimeoutMs }
        );
      } catch (err) {
        const stage = err instanceof CvExtractionError ? err.stage : null;
        const message = sanitize(errText(err));
        // DB CHECK needs a concrete stage; 'acquire' is the entry stage of the
        // CV leg. The REPORT keeps the honest null (manual attribution).
        await repo.failJob(jobId, stage ?? 'acquire', message, prisma).catch(() => undefined);
        if (stage === 'acquire' && isInputUnsuitable(message)) {
          throw new Error(`${INPUT_UNSUITABLE_PREFIX}${message}`);
        }
        if (stage) throw new StageFailureError(stage, message);
        throw new Error(message);
      }
    }

    const conf = confDistribution(cvResult.figures);

    // 3. plan + persist + deck build — the 'build' stage window.
    let deckId: string | undefined;
    const failBuild = async (err: unknown): Promise<never> => {
      const message = sanitize(errText(err));
      await repo.failJob(jobId, 'build', message, prisma).catch(() => undefined);
      if (deckId) {
        await repo.setDeckStatus(deckId, 'error', message, prisma).catch(() => undefined);
      }
      throw new StageFailureError('build', message);
    };

    let built: Awaited<ReturnType<typeof runOrchestrate>>;
    try {
      await repo.enterJobStage(jobId, 'build', prisma);
      const outline = planSlidesImpl(summary, cvResult.figures);
      deckId = (await repo.upsertDeck(outline, undefined, prisma)).deckId;
      await repo.replaceSlides(deckId, outline, prisma);
      await repo.replaceFigures(deckId, cvResult.figures, prisma);
      await repo.setDeckStatus(deckId, 'building', null, prisma);

      const artifactPath = path.join(artifactsDir, entry.index, 'deck.pptx');
      fs.mkdirSync(path.dirname(artifactPath), { recursive: true });
      built = await runOrchestrateImpl(cvResult.resources, artifactPath, appConfig, runnerOptions);
    } catch (err) {
      return failBuild(err);
    }

    // 4. validate verdict — the orchestrate loop already ran validate_deck
    //    with FAIL-feedback retries; !ok = died in 'validate'.
    if (!built.ok) {
      // G2 honesty: crashed orchestrate calls consumed LLM attempts too.
      const attempts = built.attempts + built.crashedAttempts;
      const message = `validate FAIL after ${attempts} attempts`;
      await repo
        .failJob(jobId, 'validate', message, prisma, { attemptCount: attempts })
        .catch(() => undefined);
      if (deckId) {
        await repo.setDeckStatus(deckId, 'error', message, prisma).catch(() => undefined);
      }
      return {
        validatePass: false,
        attempts,
        conf,
        failureStage: 'validate',
        error: message,
      };
    }

    await repo.completeJob(jobId, built.attempts + built.crashedAttempts, prisma);
    await repo.setDeckStatus(deckId, 'done', null, prisma).catch(() => undefined);
    return {
      validatePass: true,
      attempts: built.attempts + built.crashedAttempts,
      conf,
      failureStage: null,
    };
  };
}

function errText(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}
