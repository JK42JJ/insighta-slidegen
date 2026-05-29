/**
 * Deterministic v2 → SlideOutline planner (no LLM calls).
 *
 * Orchestration order:
 *   1. buildNarrativePlan(summary, figures.length) → NarrativePlan
 *   2. For each NarrativeStep, look up LAYOUT_MAP to pick layout
 *   3. Hydrate body_json from the appropriate v2 fields
 *   4. Attach FigureRef entries from the provided figures list
 *   5. Compute v2_fingerprint = SHA-256(video_id + template_version + generator_version)
 *   6. Return SlideOutline
 *
 * The planner is a pure function (no DB access); all I/O happens in the
 * orchestrator (src/index.ts). This keeps the planner unit-testable.
 */
import crypto from "crypto";
import { LAYOUT_MAP } from "@/plan/templates";
import { buildNarrativePlan } from "@/plan/narrative";
import type { V2Summary, FigureRef, SlideOutline, Slide } from "@/types/slide-manifest";

const GENERATOR_VERSION = "slidegen-v1";

/**
 * Converts a V2Summary + CV figures into a fully typed SlideOutline.
 *
 * @param summary - Gate-validated V2Summary from fetchV2().
 * @param figures - CV-extracted figures from cvClient or slide_figures DB cache.
 * @param lang - Output language tag (default: summary.source_language ?? "ko").
 * @returns SlideOutline ready for persistence and Google Slides build.
 *
 * TODO: implement — call buildNarrativePlan(), iterate steps, call hydrateSlide().
 * Use LAYOUT_MAP[step.type or derived layout] to pick body_json structure.
 * Attach figures to figure_slot steps by matching timestamp_sec into section range.
 */
export function planSlides(
  summary: V2Summary,
  _figures: FigureRef[],
  lang?: string
): SlideOutline {
  const resolvedLang = lang ?? summary.source_language ?? "ko";
  const fingerprint = computeFingerprint(
    summary.video_id,
    summary.template_version,
    GENERATOR_VERSION
  );

  // TODO: implement — call buildNarrativePlan(summary, _figures.length),
  // iterate NarrativePlan.steps, use LAYOUT_MAP to pick layout per step.
  void buildNarrativePlan;
  void LAYOUT_MAP;

  const slides: Slide[] = []; // TODO: populate from narrative steps

  return {
    video_id: summary.video_id,
    lang: resolvedLang,
    generator_version: GENERATOR_VERSION,
    v2_fingerprint: fingerprint,
    slides,
  };
}

/**
 * SHA-256 fingerprint for stale-deck detection.
 * Recompute when v2 data is re-generated; mismatch → rebuild deck.
 */
function computeFingerprint(
  videoId: string,
  templateVersion: string,
  generatorVersion: string
): string {
  return crypto
    .createHash("sha256")
    .update(`${videoId}:${templateVersion}:${generatorVersion}`)
    .digest("hex");
}
