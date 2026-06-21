import type { BookIndexSegment } from '@/consume/book-index';

/**
 * Demo-fixed relevance threshold (percent). A segment is figure-eligible only
 * at/above this AND when it carries a visual structure. Tuning is post-demo
 * (§6); a named constant (not a magic number), overridable per call.
 */
export const RELEVANCE_THRESHOLD_PCT = 60;

export type SlidePath = 'path1_figure' | 'path2_text';

/**
 * ④ gate: high relevance + visual structure → Path1 (request a ⑤ snapshot);
 * otherwise → Path2 (LLM-only text). Pure function.
 */
export function decidePath(
  segment: BookIndexSegment,
  thresholdPct: number = RELEVANCE_THRESHOLD_PCT
): SlidePath {
  return segment.relevance_pct >= thresholdPct && segment.has_visual_structure
    ? 'path1_figure'
    : 'path2_text';
}
