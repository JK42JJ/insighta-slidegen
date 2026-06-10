/**
 * Fetches and validates the v2 rich-summary row for a given YouTube video id.
 *
 * Gate conditions (ALL must be true — fail loud if any fails):
 *   1. template_version = 'v2'
 *   2. quality_flag     = 'pass'
 *   3. transcript_used  = true
 *
 * On gate failure the function throws a descriptive "V2_GATE_FAILED: ..."
 * error so the caller (orchestrator) can write a "gate_failed" status to
 * slide_jobs and stop. It does NOT silently fall back to v1 data.
 *
 * The fetched row is validated against V2SummarySchema (Zod) at runtime.
 * Any schema mismatch on a consumed field (e.g. segments delivered as an
 * array instead of the real { sections, atoms } object) throws a ZodError,
 * surfacing data-quality regressions rather than propagating malformed data
 * into the planner. READ-ONLY access — this module never writes to insighta
 * tables.
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
 * @throws Error with message "V2_GATE_FAILED: ..." if the row is missing or
 *   any gate condition is unmet.
 * @throws ZodError if row shape does not match V2SummarySchema.
 */
export async function fetchV2(youtubeVideoId: string, prisma?: PrismaClient): Promise<V2Summary> {
  const client = prisma ?? new PrismaClient();

  const row = await client.video_rich_summaries.findUnique({
    where: { video_id: youtubeVideoId },
  });

  if (row === null) {
    throw new Error(
      `V2_GATE_FAILED: no video_rich_summaries row for video_id=${youtubeVideoId} — generate the v2 summary first`
    );
  }
  if (row.template_version !== 'v2') {
    throw new Error(
      `V2_GATE_FAILED: template_version='${row.template_version}' (expected 'v2') for video_id=${youtubeVideoId}`
    );
  }
  if (row.quality_flag !== 'pass') {
    throw new Error(
      `V2_GATE_FAILED: quality_flag='${row.quality_flag ?? 'null'}' (expected 'pass') for video_id=${youtubeVideoId}`
    );
  }
  if (row.transcript_used !== true) {
    throw new Error(
      `V2_GATE_FAILED: transcript_used=${String(row.transcript_used)} (expected true) for video_id=${youtubeVideoId}`
    );
  }

  return V2SummarySchema.parse(row);
}
