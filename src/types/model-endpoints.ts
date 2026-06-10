/**
 * Zod mirrors of the model-endpoint wire shapes.
 * Authority: docs/CONTRACT_model-endpoints.md v1.0 (§2.2 Qwen3-VL outputs,
 * §3.2/§3.3 DocLayout-YOLO detect). TS-side validation for the PR-F cv/
 * orchestration; cv-client.ts itself is untouched here (PR-F scope).
 *
 * Coordinates NEVER come from Qwen (§2.2, ADR 0002 D2): the VLM schemas strip
 * unknown keys (zod default), so any bbox/coordinate field in a Qwen response
 * is dropped at parse time. Box geometry belongs to YOLO alone.
 */
import { z } from 'zod';

// §3.2 request defaults (tuning knobs, not secrets — ADR 0002 D2 over-detect).
export const YOLO_DEFAULT_CONF_THRESHOLD = 0.15;
export const YOLO_DEFAULT_MAX_BOXES = 50;

// ----------------------------------------------------------------
// §2.2 — Qwen3-VL call-shape outputs (client-validated, JSON-only)
// ----------------------------------------------------------------

/** Mode A per-frame routing decision (ADR 0001 routing schema, unchanged). */
export const VlmRoutingDecisionSchema = z.object({
  is_slide: z.boolean(),
  contains_graph: z.boolean(),
  contains_equation: z.boolean(),
  frame_type: z.string(),
  summary_hint: z.string().nullable().optional(),
  confidence: z.number().min(0).max(1),
});

/** Mode B per-crop output — kind authority is Qwen, never YOLO's class (D2/D7). */
export const VlmCropClassificationSchema = z.object({
  kind: z.string(),
  struct: z.record(z.unknown()).default({}),
  confidence: z.number().min(0).max(1),
});

/** Mode C equation OCR → slide_figures.extracted_latex / extraction_conf. */
export const VlmEquationOcrSchema = z.object({
  latex: z.string(),
  confidence: z.number().min(0).max(1),
});

// ----------------------------------------------------------------
// §3 — DocLayout-YOLO detect
// ----------------------------------------------------------------

/** Source-frame PIXELS — same shape persisted to slide_figures.bbox (§3.3). */
export const YoloPixelBoxSchema = z.object({
  x: z.number(),
  y: z.number(),
  w: z.number(),
  h: z.number(),
});

/**
 * One detection. `class` is ADVISORY ONLY (§3.4) — it MUST NOT gate any
 * routing decision (log-only for ADR 0004 failure-attribution stats).
 */
export const YoloBoxSchema = z.object({
  bbox: YoloPixelBoxSchema,
  class: z.string(),
  score: z.number(),
});

/** POST /detect request body (§3.2). */
export const YoloDetectRequestSchema = z.object({
  image_url: z.string().url(),
  conf_threshold: z.number().min(0).max(1).default(YOLO_DEFAULT_CONF_THRESHOLD),
  max_boxes: z.number().int().positive().default(YOLO_DEFAULT_MAX_BOXES),
});

/** POST /detect response (§3.3). */
export const YoloDetectResponseSchema = z.object({
  image: z.object({ w: z.number().int(), h: z.number().int() }),
  model_version: z.string(),
  boxes: z.array(YoloBoxSchema),
});

/** GET /health response (§3.1). */
export const YoloHealthSchema = z.object({
  status: z.string(),
  model_version: z.string(),
});

/** §3.4 error shape — failures attribute to stage `detect` (ADR 0004 §4). */
export const YoloErrorSchema = z.object({
  status: z.number().int(),
  code: z.string(),
  message: z.string(),
});

export type VlmRoutingDecision = z.infer<typeof VlmRoutingDecisionSchema>;
export type VlmCropClassification = z.infer<typeof VlmCropClassificationSchema>;
export type VlmEquationOcr = z.infer<typeof VlmEquationOcrSchema>;
export type YoloPixelBox = z.infer<typeof YoloPixelBoxSchema>;
export type YoloBox = z.infer<typeof YoloBoxSchema>;
export type YoloDetectRequest = z.infer<typeof YoloDetectRequestSchema>;
export type YoloDetectResponse = z.infer<typeof YoloDetectResponseSchema>;
export type YoloHealth = z.infer<typeof YoloHealthSchema>;
export type YoloError = z.infer<typeof YoloErrorSchema>;
