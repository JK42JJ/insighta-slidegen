/**
 * Narrative sequencing rules for slide ordering.
 *
 * This module decides the *order* of slide types for a given V2Summary.
 * It is deterministic (no LLM) and operates on structural features of the
 * summary (segments.sections count, figure count, segments.atoms count, etc.).
 *
 * Field paths follow the REAL v2 shape (see slide-manifest.ts mirror notes):
 * `segments` is an object `{ sections, atoms }`, `core` has no title/qa_pairs,
 * and atoms live in `segments.atoms` (not in `analysis`).
 *
 * Narrative arc (default, v1 generator):
 *   1. cover           — always first (core.one_liner + analysis.core_argument)
 *   2. timeline        — when segments.sections.length >= TIMELINE_MIN_SECTIONS
 *                        (overview before diving in)
 *   3. [per section]   — for each segments.sections[i]:
 *        a. section_intro  — section title + summary
 *        b. key_points     — section key_points[].text (skip if < MIN_KEY_POINTS items)
 *        c. figure_*       — any CV figures whose timestamp_sec falls in section range
 *   4. atom_highlight×N — segments.atoms with type in HIGHLIGHT_ATOM_TYPES
 *                         ('fact' / 'tip'), max MAX_ATOM_HIGHLIGHTS
 *                         (replaces the former qa_pair steps — core.qa_pairs
 *                         does not exist in the real v2 shape; lora.qa_pairs
 *                         is not consumed by the MVP planner)
 *   5. summary          — analysis.key_concepts[].term
 *
 * Deviation rules:
 *   - Fewer than 2 sections: skip timeline, go cover → section_intro... → summary.
 *   - No figures from CV: skip all figure_* slides.
 *   - mandala_relevance_pct < LOW_RELEVANCE_THRESHOLD: append a
 *     relevance-disclaimer blank slide.
 */
import type { V2Summary, V2Section, V2Atom } from '@/types/slide-manifest';

/** Minimum section count before a timeline overview slide is worth adding. */
export const TIMELINE_MIN_SECTIONS = 3;
/** Minimum key_points entries for a section to earn a key_points slide. */
export const MIN_KEY_POINTS = 2;
/** Atom types promoted to standalone atom_highlight slides. */
export const HIGHLIGHT_ATOM_TYPES: readonly string[] = ['fact', 'tip'];
/** Maximum number of atom_highlight slides per deck. */
export const MAX_ATOM_HIGHLIGHTS = 4;
/** Below this mandala_relevance_pct, append a relevance-disclaimer slide. */
export const LOW_RELEVANCE_THRESHOLD = 30;

export interface NarrativePlan {
  /** Ordered list of step descriptors; slide-planner maps these to Slide objects. */
  steps: NarrativeStep[];
}

export type NarrativeStep =
  | { type: 'cover' }
  | { type: 'timeline' }
  | { type: 'section_intro'; sectionIndex: number; section: V2Section }
  | { type: 'key_points'; sectionIndex: number; section: V2Section }
  | { type: 'figure_slot'; sectionIndex: number; figureIndex: number }
  | { type: 'atom_highlight'; atomIndex: number; atom: V2Atom }
  | { type: 'summary' }
  | { type: 'blank'; reason: string };

/**
 * Builds the narrative step sequence from a validated V2Summary.
 *
 * @param summary - Validated V2Summary (already gate-checked by fetchV2).
 * @param figureCount - Number of CV figures available for this video.
 * @returns Ordered NarrativePlan; slide-planner converts steps to Slide objects.
 *
 * Algorithm (see module docstring for full arc):
 *   1. Push cover step.
 *   2. If (segments?.sections ?? []).length >= TIMELINE_MIN_SECTIONS push timeline.
 *   3. For each section: section_intro, conditionally key_points,
 *      conditionally figure_slot.
 *   4. For each segments.atoms entry with type in HIGHLIGHT_ATOM_TYPES
 *      (max MAX_ATOM_HIGHLIGHTS): atom_highlight step.
 *   5. Push summary.
 *   6. If mandala_relevance_pct < LOW_RELEVANCE_THRESHOLD: push blank("low_relevance").
 *
 * TODO: implement the sequencing logic.
 */
export function buildNarrativePlan(_summary: V2Summary, _figureCount: number): NarrativePlan {
  // TODO: implement deterministic narrative arc (see module docstring for full arc)
  throw new Error('TODO: buildNarrativePlan — implement deterministic narrative arc');
}
