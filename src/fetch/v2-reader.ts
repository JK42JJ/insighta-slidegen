/**
 * Fetches and validates the v2 rich-summary row for a given YouTube video id.
 *
 * Gate conditions (ALL must be true — fail loud if any fails):
 *   1. template_version = 'v2'
 *   2. quality_flag     = 'pass'
 *   3. transcript_used  = true
 *
 * On gate failure the function throws a descriptive error so the caller
 * (orchestrator) can write a "gate_failed" status to slide_jobs and stop.
 * It does NOT silently fall back to v1 data.
 *
 * The fetched JSON is validated against V2SummarySchema (Zod) at runtime.
 * Any schema mismatch throws a ZodError, surfacing data-quality regressions
 * rather than propagating malformed data into the planner.
 */
import { PrismaClient } from '@prisma/client';
import { V2SummarySchema, type V2Summary } from '@/types/slide-manifest';

/**
 * Fetches the v2 rich-summary for a video and validates it.
 *
 * Algorithm:
 *   1. SELECT * FROM video_rich_summaries WHERE video_id = youtubeVideoId
 *   2. Assert template_version='v2', quality_flag='pass', transcript_used=true
 *   3. Parse with V2SummarySchema.parse() — throws ZodError on mismatch
 *   4. Return typed V2Summary
 *
 * @param youtubeVideoId - 11-character YouTube video id.
 * @param prisma - Prisma client instance (caller-injected for testability).
 * @returns Validated V2Summary.
 * @throws Error with message "V2_GATE_FAILED: ..." if gate conditions unmet.
 * @throws ZodError if row shape does not match V2SummarySchema.
 *
 * TODO: implement — use prisma.video_rich_summaries.findUnique({ where: { video_id } })
 *   then run the three gate assertions before calling V2SummarySchema.parse().
 */
export async function fetchV2(_youtubeVideoId: string, _prisma?: PrismaClient): Promise<V2Summary> {
  // TODO: SELECT * FROM video_rich_summaries WHERE video_id = _youtubeVideoId
  // Assert template_version='v2', quality_flag='pass', transcript_used=true.
  // Return V2SummarySchema.parse(row) — throws ZodError on shape mismatch.
  void V2SummarySchema; // referenced to keep import live until TODO is implemented
  throw new Error(
    'TODO: fetchV2 — query video_rich_summaries, assert v2/pass/transcript_used gate, zod-validate'
  );
}
