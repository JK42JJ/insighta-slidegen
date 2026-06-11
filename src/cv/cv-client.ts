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
import { config } from '@/config';
import type { OrchestrateResources } from '@/deck/orchestrate-runner';
import type { FigureRef } from '@/types/slide-manifest';

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

/**
 * Submits a generate job to the CV service and polls until done.
 *
 * The service selects ~12 keyframes (not all ~80 candidates) via CLIP
 * embedding-distance dedup + BGE-M3 caption topic alignment.
 * result.keyframe_count reflects the ~12 selected frames.
 *
 * Algorithm:
 *   1. POST /slides/generate with CvGenerateRequest JSON body.
 *      Header: Authorization: Bearer SLIDEGEN_CV_SERVICE_TOKEN.
 *   2. Poll GET /slides/status?job_id={id} every 2s until status='done'|'error'.
 *   3. GET /slides/result?job_id={id} → CvGenerateResult.
 *   4. Validate each FigureRef with FigureRefSchema.
 *   5. Return the full result (figures + keyframe_count + resources bundle).
 *
 * @param _request - Video id + section list for frame extraction.
 * @returns Full CV result: validated figures (~12 selected keyframes) plus the
 *          orchestrate resources bundle for the deck runner (PR-F3).
 * @throws Error on service error, timeout (default 300s), or schema mismatch.
 *
 * TODO: implement — use fetch(); add exponential backoff on transient 5xx.
 */
export async function extractFigures(_request: CvGenerateRequest): Promise<CvGenerateResult> {
  // config accessed at runtime for SLIDEGEN_CV_SERVICE_URL + TOKEN
  void config;
  throw new Error(
    'TODO: extractFigures — POST /slides/generate, poll /slides/status, GET /slides/result'
  );
}

/**
 * Health-checks the CV service. Returns true if /health responds 200.
 * Used by the orchestrator to decide whether to skip CV in dev with no service.
 *
 * TODO: implement — GET config.SLIDEGEN_CV_SERVICE_URL + "/health".
 */
export async function isCvServiceHealthy(): Promise<boolean> {
  void config;
  throw new Error('TODO: isCvServiceHealthy — GET /health');
}
