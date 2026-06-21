import { describe, it, expect } from 'vitest';

import type { BookIndexSegment } from '@/consume/book-index';
import { decidePath, RELEVANCE_THRESHOLD_PCT } from '@/consume/relevance-gate';

const seg = (over: Partial<BookIndexSegment>): BookIndexSegment => ({
  video_id: 'abcdefghijk',
  from_sec: 0,
  to_sec: 10,
  title: 't',
  text: 'b',
  relevance_pct: 80,
  has_visual_structure: true,
  ...over,
});

describe('decidePath (④ relevance gate)', () => {
  it('Path1 when relevance >= threshold AND has visual structure', () => {
    expect(decidePath(seg({ relevance_pct: 80, has_visual_structure: true }))).toBe('path1_figure');
  });

  it('Path2 when relevance below threshold', () => {
    expect(decidePath(seg({ relevance_pct: 30, has_visual_structure: true }))).toBe('path2_text');
  });

  it('Path2 when no visual structure even if highly relevant', () => {
    expect(decidePath(seg({ relevance_pct: 95, has_visual_structure: false }))).toBe('path2_text');
  });

  it('boundary: exactly at threshold + visual structure → Path1', () => {
    expect(
      decidePath(seg({ relevance_pct: RELEVANCE_THRESHOLD_PCT, has_visual_structure: true }))
    ).toBe('path1_figure');
  });

  it('honors a custom threshold override', () => {
    expect(decidePath(seg({ relevance_pct: 50, has_visual_structure: true }), 40)).toBe(
      'path1_figure'
    );
  });
});
