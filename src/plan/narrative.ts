/**
 * Narrative sequencing rules for slide ordering.
 *
 * This module decides the *order* of slide types for a given V2Summary.
 * It is deterministic (no LLM) and operates on structural features of the
 * summary (segment count, figure count, qa_pairs count, etc.).
 *
 * Narrative arc (default, v1 generator):
 *   1. cover          — always first (core.title + one_liner)
 *   2. timeline       — when segments.length >= 3 (overview before diving in)
 *   3. [per section]  — for each segment:
 *        a. section_intro  — segment title + summary
 *        b. key_points     — segment key_points (skip if < 2 items)
 *        c. figure_*       — any CV figures whose timestamp_sec falls in segment range
 *   4. qa_pair×N      — core.qa_pairs (max 4)
 *   5. summary        — core.key_concepts
 *
 * Deviation rules:
 *   - Fewer than 2 segments: skip timeline, go cover → section_intro... → summary.
 *   - No figures from CV: skip all figure_* slides.
 *   - mandala_relevance_pct < 30: append a relevance-disclaimer blank slide.
 */
import type { V2Summary, V2Section } from "@/types/slide-manifest";

export interface NarrativePlan {
  /** Ordered list of step descriptors; slide-planner maps these to Slide objects. */
  steps: NarrativeStep[];
}

export type NarrativeStep =
  | { type: "cover" }
  | { type: "timeline" }
  | { type: "section_intro"; sectionIndex: number; section: V2Section }
  | { type: "key_points"; sectionIndex: number; section: V2Section }
  | { type: "figure_slot"; sectionIndex: number; figureIndex: number }
  | { type: "qa_pair"; qaIndex: number }
  | { type: "summary" }
  | { type: "blank"; reason: string };

/**
 * Builds the narrative step sequence from a validated V2Summary.
 *
 * @param summary - Validated V2Summary (already gate-checked by fetchV2).
 * @param figureCount - Number of CV figures available for this video.
 * @returns Ordered NarrativePlan; slide-planner converts steps to Slide objects.
 *
 * Algorithm (see module docstring for full arc):
 *   1. Push cover step.
 *   2. If segments.length >= 3 push timeline.
 *   3. For each segment: section_intro, conditionally key_points, conditionally figure_slot.
 *   4. For each qa_pair (max 4): qa_pair step.
 *   5. Push summary.
 *   6. If mandala_relevance_pct < 30: push blank("low_relevance").
 *
 * TODO: implement the sequencing logic.
 */
export function buildNarrativePlan(
  _summary: V2Summary,
  _figureCount: number
): NarrativePlan {
  // TODO: implement deterministic narrative arc (see module docstring for full arc)
  throw new Error("TODO: buildNarrativePlan — implement deterministic narrative arc");
}
