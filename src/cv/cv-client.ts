/**
 * Client for the Mac Mini CV microservice (mac-mini/slidegen-service/).
 *
 * Pipeline the service runs (canonical order, per app.py docstring):
 *   1. acquire      — download video frames
 *   2. frames       — Katna wide-net extraction (~80 candidate frames)
 *   3. captions     — BGE-M3 caption embedding + topic-change point detection
 *   4. select       — CLIP embed + pgvector cosine dedup aligned to topic points → ~12 frames
 *   5. figure_extract — YOLO layout + OCR on selected ~12 only
 *   6. redraw       — vector redraw 300 DPI SVG/PDF
 *
 * keyframe_count in CvGenerateResult reflects the ~12 selected frames, NOT the ~80 candidates.
 * Selection is embedding-distance based (CLIP cosine distance + BGE-M3 topic alignment).
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
import type { FigureRef } from '@/types/slide-manifest';

export interface CvGenerateRequest {
  youtube_video_id: string;
  sections: Array<{
    index: number;
    from_sec: number;
    to_sec: number;
  }>;
  mode: 'dev' | 'prod';
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
 *   5. Return figures array.
 *
 * @param _request - Video id + section list for frame extraction.
 * @returns Validated figure list (~12 selected keyframes with figure data).
 * @throws Error on service error, timeout (default 300s), or schema mismatch.
 *
 * TODO: implement — use fetch(); add exponential backoff on transient 5xx.
 */
export async function extractFigures(_request: CvGenerateRequest): Promise<FigureRef[]> {
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
