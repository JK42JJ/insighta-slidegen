import type { FigureRef } from '@/types/slide-manifest';

/**
 * ⑤ get-or-extract snapshot client (insighta-owned API; slidegen calls it).
 *
 * "Give me the figure snapshot(s) for video_id at these timestamps" — insighta
 * returns cached figures or numerizes (pod YOLO + Qwen) then caches. slidegen is
 * a READ-ONLY consumer of that cache. This is the interface the ④ Path1 branch
 * depends on; the real HTTP impl is wired when the insighta ⑤ contract lands.
 */
export interface SnapshotClient {
  getOrExtractSnapshot(videoId: string, tsList: number[]): Promise<FigureRef[]>;
}

/**
 * Skeleton stub: returns NO figures. Fail-closed — the consumer places nothing
 * rather than fabricating a figure. Swap for the real ⑤ HTTP client once the
 * insighta contract is fixed.
 */
export const stubSnapshotClient: SnapshotClient = {
  getOrExtractSnapshot(_videoId: string, _tsList: number[]): Promise<FigureRef[]> {
    return Promise.resolve([]);
  },
};
