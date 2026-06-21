import { describe, it, expect } from 'vitest';

import type { BookIndex } from '@/consume/book-index';
import { consumeBookIndex } from '@/consume/consume-book-index';
import { stubSnapshotClient, type SnapshotClient } from '@/consume/snapshot-client';
import type { FigureRef } from '@/types/slide-manifest';

const book: BookIndex = {
  mandala_id: 'm1',
  center_goal: 'goal',
  segments: [
    // path1: relevant + visual
    {
      video_id: 'abcdefghijk',
      from_sec: 0,
      to_sec: 10,
      title: 'A',
      text: 'a',
      relevance_pct: 90,
      has_visual_structure: true,
    },
    // path2: low relevance
    {
      video_id: 'abcdefghijk',
      from_sec: 20,
      to_sec: 30,
      title: 'B',
      text: 'b',
      relevance_pct: 10,
      has_visual_structure: true,
    },
    // path2: no visual structure
    {
      video_id: 'abcdefghijk',
      from_sec: 40,
      to_sec: 50,
      title: 'C',
      text: 'c',
      relevance_pct: 99,
      has_visual_structure: false,
    },
  ],
};

const FIG: FigureRef = {
  cv_figure_id: 'f1',
  kind: 'diagram',
  png_url: 'https://example.invalid/f.png',
  verification_status: 'pending',
};

describe('consumeBookIndex (④ consumer)', () => {
  it('routes each segment by the gate; only Path1 calls ⑤', async () => {
    const calls: Array<[string, number[]]> = [];
    const client: SnapshotClient = {
      getOrExtractSnapshot: (videoId, tsList) => {
        calls.push([videoId, tsList]);
        return Promise.resolve([FIG]);
      },
    };
    const out = await consumeBookIndex(book, client);

    expect(out.map((p) => p.path)).toEqual(['path1_figure', 'path2_text', 'path2_text']);
    expect(calls).toEqual([['abcdefghijk', [0, 10]]]); // only the path1 segment hit ⑤
    expect(out[0].figures).toEqual([FIG]);
    expect(out[1].figures).toEqual([]);
    expect(out[2].figures).toEqual([]);
  });

  it('stub ⑤ client yields 0 figures (fail-closed, no fabrication)', async () => {
    const out = await consumeBookIndex(book, stubSnapshotClient);
    expect(out[0].path).toBe('path1_figure');
    expect(out[0].figures).toEqual([]); // stub returns nothing
  });
});
