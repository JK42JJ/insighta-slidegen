/**
 * Client for the Mac Mini CV microservice (mac-mini/slidegen-service/).
 *
 * Pipeline the service runs (canonical order, per app.py docstring — PR-F3):
 *   1. acquire      — download video frames
 *   2. frames       — PySceneDetect wide-net extraction + CPU downsample (~60 candidates)
 *   3. captions     — BGE-M3 caption embedding + topic-change point detection
 *   4. typing_select — local VLM router selects ~12-20 keyframes (section text = HINT)
 *   5. figure_extract — YOLO crop + Qwen numerization on the selected frames only
 *   6. bundle       — orchestrate resources bundle, returned in /slides/result
 *
 * keyframe_count in CvGenerateResult reflects the ~12-20 SELECTED frames, NOT
 * the ~60 candidates.
 *
 * Mode gate (mirrors parent transcript-client pattern):
 *   - SLIDEGEN_MODE=dev  → CV service at SLIDEGEN_CV_SERVICE_URL (localhost:8077).
 *                          Vision API hard-disabled; service returns placeholder figures.
 *   - SLIDEGEN_MODE=prod → same URL (Tailscale or internal); service runs full CV
 *                          pipeline with optional vision API fallback enabled.
 *
 * No direct vision API calls happen here; this client only speaks to the
 * FastAPI service which owns that decision.
 */
import { z } from 'zod';
import type { OrchestrateResources } from '@/deck/orchestrate-runner';
import { JobStageSchema, type JobStage } from '@/types/job-stages';
import { FigureRefSchema, type FigureRef } from '@/types/slide-manifest';

export interface CvGenerateRequest {
  youtube_video_id: string;
  sections: Array<{
    index: number;
    from_sec: number;
    to_sec: number;
    /** v2 section title — grounding text for the Qwen select call (ADR 0002 D5). */
    title: string;
    /**
     * v2 section summary — companion text for mode A select+classify
     * (CONTRACT_model-endpoints §2.2). HINT only, never a keep/drop gate.
     */
    summary?: string;
  }>;
  mode: 'dev' | 'prod';
  /**
   * v2 passthrough for the orchestrate resources bundle (bundle.py, PR-F3).
   * Optional: omitting them keeps pre-F3 callers working (service defaults '').
   */
  title?: string;
  transcript?: string;
}

export interface CvJobStatus {
  job_id: string;
  status: 'queued' | 'running' | 'done' | 'error';
  progress_pct: number;
  error?: string;
}

export interface CvGenerateResult {
  job_id: string;
  figures: FigureRef[];
  keyframe_count: number;
  /**
   * Orchestrate resources bundle (PR-F3 ResultResponse sync — bundle.py
   * RESOURCE_KEYS shape): {title, transcript, segments, figureLabels,
   * formulas, charts}. Consumed UNMODIFIED by deck/scripts/orchestrate.js via
   * the node runner (src/deck/orchestrate-runner.ts). TEXT/DATA/LaTeX only —
   * raw frame pixels are banned from this bundle (ADR 0003 P2).
   */
  resources: OrchestrateResources;
}

// ── PR-H2 wiring ──────────────────────────────────────────────────────────────

/** Poll cadence for GET /slides/status (per the PR-H1 client design). */
const POLL_INTERVAL_MS = 2_000;
/** Default overall budget; real prod runs pass a larger opts.timeoutMs
 * (acquire alone can take minutes on a long video). */
const DEFAULT_TIMEOUT_MS = 300_000;
/** Transient 5xx / network-throw retry budget for the submit call (§2.3 mirror). */
const SUBMIT_RETRIES = 2;
/** Consecutive status-poll failures tolerated before giving up (a long CV job
 * must survive a brief network blip — observed live on the tailnet). */
const POLL_FAILURE_TOLERANCE = 5;

function errMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/**
 * A CV-service job failure with ADR 0004 stage attribution. `stage` is the
 * service-reported failure_stage (or last-seen running stage on timeout);
 * null = outside the stage domain → manual attribution in the report.
 */
export class CvExtractionError extends Error {
  constructor(
    message: string,
    public readonly stage: JobStage | null
  ) {
    super(message);
    this.name = 'CvExtractionError';
  }
}

// Transport-boundary schemas (the service is trusted code but crosses a
// network boundary — validate shape, fail loud on drift).
const GenerateResponseSchema = z.object({ job_id: z.string().min(1) });

const StatusResponseSchema = z.object({
  job_id: z.string(),
  status: z.enum(['queued', 'running', 'done', 'error']),
  progress_pct: z.number(),
  error: z.string().nullable().optional(),
  stage: z.string().nullable().optional(),
  failure_stage: z.string().nullable().optional(),
});

/**
 * png_url relaxation: the service returns LOCAL crop paths until the
 * presigned artifact-upload step lands (deferred §4 follow-up) — a bare path
 * fails FigureRefSchema's `.url()`, so the transport boundary accepts any
 * non-empty string and keeps the rest of the contract strict. The service
 * also emits explicit nulls where the schema says "absent" — accepted here.
 */
const WireFigureSchema = FigureRefSchema.extend({
  png_url: z.string().min(1),
  vector_pdf_url: z.string().nullable().optional(),
  vector_svg_url: z.string().nullable().optional(),
  caption: z.string().nullable().optional(),
  timestamp_sec: z.number().int().nullable().optional(),
  extraction_conf: z.number().min(0).max(1).nullable().optional(),
});

const ResultResponseSchema = z.object({
  job_id: z.string(),
  figures: z.array(WireFigureSchema),
  keyframe_count: z.number().int().nonnegative(),
  resources: z
    .object({
      title: z.string(),
      transcript: z.string(),
      segments: z.array(z.unknown()),
      figureLabels: z.array(z.unknown()),
      formulas: z.array(z.unknown()),
      charts: z.array(z.unknown()),
    })
    .passthrough(),
});

export interface CvClientOptions {
  /** Overall submit→done budget. Default 300 s; measurement runs pass more. */
  timeoutMs?: number;
  pollIntervalMs?: number;
  /**
   * Endpoint override. When absent, resolved from src/config LAZILY at call
   * time — modules importing this client stay loadable without a full env
   * (the config singleton parses process.env at import; see config tests).
   */
  serviceUrl?: string;
  serviceToken?: string;
  /** Test seams. */
  fetchImpl?: typeof fetch;
  sleep?: (ms: number) => Promise<void>;
  now?: () => number;
}

function defaultSleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function resolveEndpoint(
  options: Pick<CvClientOptions, 'serviceUrl' | 'serviceToken'>
): Promise<{ base: string; token: string }> {
  if (options.serviceUrl !== undefined) {
    return { base: options.serviceUrl.replace(/\/$/, ''), token: options.serviceToken ?? '' };
  }
  const { config } = await import('@/config');
  return {
    base: config.SLIDEGEN_CV_SERVICE_URL.replace(/\/$/, ''),
    token: config.SLIDEGEN_CV_SERVICE_TOKEN,
  };
}

function authHeaders(token: string): Record<string, string> {
  const headers: Record<string, string> = { 'content-type': 'application/json' };
  if (token) {
    headers['authorization'] = `Bearer ${token}`;
  }
  return headers;
}

/** Service stage string → JobStage (anything off-domain degrades to null). */
function parseStage(raw: string | null | undefined): JobStage | null {
  return JobStageSchema.safeParse(raw).data ?? null;
}

/**
 * Submits a generate job to the CV service and polls until done.
 *
 * Algorithm:
 *   1. POST /slides/generate with CvGenerateRequest JSON body
 *      (Authorization: Bearer SLIDEGEN_CV_SERVICE_TOKEN; 5xx retried).
 *   2. Poll GET /slides/status?job_id={id} every 2s until status='done'|'error'.
 *   3. GET /slides/result?job_id={id} → CvGenerateResult.
 *   4. Validate figures (wire-relaxed FigureRef) + resources bundle shape.
 *
 * @throws CvExtractionError carrying the ADR 0004 failure stage on job error
 *         or timeout (stage = service failure_stage / last-seen stage).
 */
export async function extractFigures(
  request: CvGenerateRequest,
  options: CvClientOptions = {}
): Promise<CvGenerateResult> {
  const { base, token } = await resolveEndpoint(options);
  const headers = authHeaders(token);
  const fetchImpl = options.fetchImpl ?? fetch;
  const sleep = options.sleep ?? defaultSleep;
  const now = options.now ?? Date.now;
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const pollIntervalMs = options.pollIntervalMs ?? POLL_INTERVAL_MS;

  // 1. submit (transient 5xx AND thrown network errors retried — a Tailscale
  //    blip killed two runs live; 4xx still fails immediately)
  let submitResponse: Response | undefined;
  let lastNetworkError: unknown;
  for (let attempt = 0; attempt <= SUBMIT_RETRIES; attempt++) {
    try {
      submitResponse = await fetchImpl(`${base}/slides/generate`, {
        method: 'POST',
        headers,
        body: JSON.stringify(request),
      });
      if (submitResponse.status < 500) break;
    } catch (err) {
      lastNetworkError = err;
      submitResponse = undefined;
    }
    if (attempt < SUBMIT_RETRIES) await sleep(pollIntervalMs);
  }
  if (!submitResponse || !submitResponse.ok) {
    const detail = submitResponse
      ? `HTTP ${submitResponse.status}`
      : `network error: ${errMessage(lastNetworkError)}`;
    throw new CvExtractionError(`cv service generate failed: ${detail}`, null);
  }
  const { job_id: jobId } = GenerateResponseSchema.parse(await submitResponse.json());

  // 2. poll until done/error/timeout — transient poll failures (network throw
  //    or non-2xx) tolerate up to POLL_FAILURE_TOLERANCE in a row.
  const deadline = now() + timeoutMs;
  let lastSeenStage: JobStage | null = null;
  let consecutivePollFailures = 0;
  for (;;) {
    let status: z.infer<typeof StatusResponseSchema>;
    try {
      const statusResponse = await fetchImpl(
        `${base}/slides/status?job_id=${encodeURIComponent(jobId)}`,
        { headers }
      );
      if (!statusResponse.ok) {
        throw new Error(`HTTP ${statusResponse.status}`);
      }
      status = StatusResponseSchema.parse(await statusResponse.json());
      consecutivePollFailures = 0;
    } catch (err) {
      consecutivePollFailures += 1;
      if (consecutivePollFailures > POLL_FAILURE_TOLERANCE) {
        throw new CvExtractionError(
          `cv service status failed ${consecutivePollFailures}x: ${errMessage(err)}`,
          lastSeenStage
        );
      }
      if (now() >= deadline) {
        throw new CvExtractionError(`cv job timeout after ${timeoutMs}ms`, lastSeenStage);
      }
      await sleep(pollIntervalMs);
      continue;
    }
    lastSeenStage = parseStage(status.stage) ?? lastSeenStage;

    if (status.status === 'done') break;
    if (status.status === 'error') {
      throw new CvExtractionError(
        `cv job failed: ${status.error ?? 'unknown error'}`,
        parseStage(status.failure_stage) ?? lastSeenStage
      );
    }
    if (now() >= deadline) {
      // PR-G timeout convention: attribute to the stage the job died in.
      throw new CvExtractionError(`cv job timeout after ${timeoutMs}ms`, lastSeenStage);
    }
    await sleep(pollIntervalMs);
  }

  // 3. result
  const resultResponse = await fetchImpl(
    `${base}/slides/result?job_id=${encodeURIComponent(jobId)}`,
    { headers }
  );
  if (!resultResponse.ok) {
    throw new CvExtractionError(`cv service result failed: HTTP ${resultResponse.status}`, null);
  }
  const parsed = ResultResponseSchema.parse(await resultResponse.json());
  // Normalize the service's explicit nulls to the FigureRef optional shape
  // (downstream consumers expect absent, not null).
  const figures: FigureRef[] = parsed.figures.map((f) => ({
    ...f,
    vector_pdf_url: f.vector_pdf_url ?? undefined,
    vector_svg_url: f.vector_svg_url ?? undefined,
    caption: f.caption ?? undefined,
    timestamp_sec: f.timestamp_sec ?? undefined,
    extraction_conf: f.extraction_conf ?? undefined,
  }));
  return {
    job_id: parsed.job_id,
    figures,
    keyframe_count: parsed.keyframe_count,
    resources: parsed.resources as unknown as OrchestrateResources,
  };
}

/**
 * Health-checks the CV service. Returns true if /health responds 200.
 * Used by the orchestrator to decide whether to skip CV in dev with no service.
 */
export async function isCvServiceHealthy(
  fetchImpl: typeof fetch = fetch,
  serviceUrl?: string
): Promise<boolean> {
  try {
    const { base } = await resolveEndpoint({ serviceUrl });
    const response = await fetchImpl(`${base}/health`);
    return response.ok;
  } catch {
    return false;
  }
}
