import { z } from 'zod';

/**
 * Book-index read contract (slidegen side — demo skeleton).
 *
 * The mandala "book-index" (insighta `mandala_books`, owned upstream) is the
 * completed-data SSOT. slidegen is a READ-ONLY consumer; this schema captures
 * ONLY the fields the ④ consumer needs to gate and branch. These shapes must be
 * reconciled with the insighta book-index / ⑤ contract when it lands — until
 * then this is the stub surface the skeleton wires against.
 */
export const BookIndexSegmentSchema = z.object({
  /** Source video (11-char youtube id) the segment's figure-moment lives in. */
  video_id: z.string().length(11),
  from_sec: z.number().nonnegative(),
  to_sec: z.number().nonnegative(),
  title: z.string(),
  /** Section body text — the Path2 (LLM-only) content when no figure is placed. */
  text: z.string(),
  /**
   * Per-(video, mandala) segment relevance (insighta ② signal, 0-100). The ④
   * gate input. Documented 0-100 upstream.
   */
  relevance_pct: z.number(),
  /**
   * Whether the segment carries a visual structure worth extracting a figure
   * for (chart/diagram/table/equation). insighta/CV marks this; the gate pairs
   * it with relevance to choose Path1 vs Path2.
   */
  has_visual_structure: z.boolean(),
});
export type BookIndexSegment = z.infer<typeof BookIndexSegmentSchema>;

export const BookIndexSchema = z.object({
  mandala_id: z.string(),
  center_goal: z.string(),
  segments: z.array(BookIndexSegmentSchema),
});
export type BookIndex = z.infer<typeof BookIndexSchema>;
