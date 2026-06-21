import { describe, it, expect } from 'vitest';

import type { BookIndex } from '@/consume/book-index';
import { bookIndexToResources } from '@/consume/book-index-to-resources';
import { consumeBookIndex } from '@/consume/consume-book-index';
import { stubSnapshotClient, type SnapshotClient } from '@/consume/snapshot-client';
import type { FigureRef } from '@/types/slide-manifest';

const book: BookIndex = {
  mandala_id: 'm1',
  center_goal: '중심 목표',
  segments: [
    {
      video_id: 'abcdefghijk',
      from_sec: 0,
      to_sec: 10,
      title: 'A',
      text: '본문 A',
      relevance_pct: 90,
      has_visual_structure: true,
    },
    {
      video_id: 'abcdefghijk',
      from_sec: 20,
      to_sec: 30,
      title: 'B',
      text: '본문 B',
      relevance_pct: 10,
      has_visual_structure: false,
    },
  ],
};

describe('bookIndexToResources (⑥ book-index → OrchestrateResources)', () => {
  it('text-only with stub ⑤: title=center_goal, segments mapped, charts/formulas empty', async () => {
    const planned = await consumeBookIndex(book, stubSnapshotClient);
    const r = bookIndexToResources(book, planned);

    expect(r.title).toBe('중심 목표');
    expect(r.segments).toHaveLength(2);
    expect(r.segments[0]).toMatchObject({ from_sec: 0, to_sec: 10, title: 'A', summary: '본문 A' });
    expect(r.charts).toEqual([]); // stub ⑤ → no figures → text-only deck still builds
    expect(r.formulas).toEqual([]);
    expect(r.transcript).toContain('본문 A');
  });

  it('maps equation figures (Path1) to formulas via extracted_latex', async () => {
    const eq: FigureRef = {
      cv_figure_id: 'e1',
      kind: 'equation',
      png_url: 'https://example.invalid/e.png',
      extracted_latex: 'y = ax + b',
      extraction_conf: 0.9,
      timestamp_sec: 5,
      verification_status: 'verified',
    };
    const client: SnapshotClient = { getOrExtractSnapshot: () => Promise.resolve([eq]) };
    const planned = await consumeBookIndex(book, client); // segment A is Path1 → gets [eq]
    const r = bookIndexToResources(book, planned);

    expect(r.formulas).toHaveLength(1);
    expect(r.formulas[0]).toMatchObject({ figure_id: 'e1', latex: 'y = ax + b' });
    expect(r.charts).toEqual([]); // equation → formula, not chart
  });
});
