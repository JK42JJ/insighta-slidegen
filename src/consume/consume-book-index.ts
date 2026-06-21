import type { BookIndex, BookIndexSegment } from '@/consume/book-index';
import type { SnapshotClient } from '@/consume/snapshot-client';
import { decidePath, RELEVANCE_THRESHOLD_PCT, type SlidePath } from '@/consume/relevance-gate';
import type { FigureRef } from '@/types/slide-manifest';

/** One book-index segment resolved to a path + (Path1) its figures. Bridge to ⑥. */
export interface PlannedSegment {
  segment: BookIndexSegment;
  path: SlidePath;
  /** Path1: ⑤ snapshot figures; Path2: always empty (text-only). */
  figures: FigureRef[];
}

export interface ConsumeOptions {
  thresholdPct?: number;
}

/**
 * ④ consumer: walk a mandala book-index, gate each segment, and for Path1
 * segments request the ⑤ snapshot (figures). Path2 segments carry no figures
 * (text-only). Returns the per-segment plan that ⑥ planSlides renders.
 *
 * Fail-closed: with the stub ⑤ client (no real extraction) a Path1 segment
 * simply yields 0 figures — the consumer never fabricates. Read-only on
 * insighta data; writes (deck/slides) happen downstream in ⑥/persistence.
 */
export async function consumeBookIndex(
  book: BookIndex,
  client: SnapshotClient,
  options: ConsumeOptions = {}
): Promise<PlannedSegment[]> {
  const thresholdPct = options.thresholdPct ?? RELEVANCE_THRESHOLD_PCT;
  const planned: PlannedSegment[] = [];
  for (const segment of book.segments) {
    const path = decidePath(segment, thresholdPct);
    let figures: FigureRef[] = [];
    if (path === 'path1_figure') {
      figures = await client.getOrExtractSnapshot(segment.video_id, [
        segment.from_sec,
        segment.to_sec,
      ]);
    }
    planned.push({ segment, path, figures });
  }
  return planned;
}
