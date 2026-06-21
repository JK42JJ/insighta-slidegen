import { describe, it, expect } from 'vitest';

import { mapMandalaBookJson } from '@/consume/mandala-book-mapper';

// Synthetic book_json mirroring the prod shape (NO real ids/text — PUBLIC repo).
const bookJson = {
  mandala_title: '데모 만다라',
  mandala_id: 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
  schema_version: 1,
  chapters: [
    { ch: 0, title: 'Ch0', intro: 'i', sections: [] }, // empty → no segment
    {
      ch: 1,
      title: 'Ch1',
      sections: [
        {
          title: 'S1',
          narrative: '본문 내용 하나',
          qa: [],
          atoms: [
            { vid: 'abcdefghijk', type: 'fact', seg_ref: 0, text: 'a', ts: 30 },
            { vid: 'abcdefghijk', type: 'tip', seg_ref: 0, text: 'b', ts: 12 },
          ],
        },
      ],
    },
    {
      ch: 2,
      title: 'Ch2',
      sections: [
        { title: '', narrative: '본문 둘', atoms: [{ vid: 'lmnopqrstuv', ts: 5 }] }, // title falls back to chapter
        { title: 'Empty', narrative: '   ', atoms: [{ vid: 'lmnopqrstuv', ts: 9 }] }, // empty narrative → skip
        { title: 'NoVid', narrative: '본문 셋', atoms: [{ vid: 'short', ts: 1 }] }, // bad vid len → skip
      ],
    },
  ],
};

describe('mapMandalaBookJson (insighta book_json → slidegen BookIndex)', () => {
  it('maps center_goal + flattens sections; skips empty/no-vid (fail-closed)', () => {
    const book = mapMandalaBookJson(bookJson);

    expect(book.center_goal).toBe('데모 만다라');
    // 2 valid segments: Ch1/S1 and Ch2 first section; the empty-narrative and
    // bad-vid sections are skipped, the empty chapter contributes none.
    expect(book.segments).toHaveLength(2);

    expect(book.segments[0]).toMatchObject({
      video_id: 'abcdefghijk',
      title: 'S1',
      text: '본문 내용 하나',
      from_sec: 12, // min(ts)
      to_sec: 30, // max(ts)
      has_visual_structure: false,
    });
    // section with empty title falls back to the chapter title
    expect(book.segments[1]).toMatchObject({
      title: 'Ch2',
      text: '본문 둘',
      video_id: 'lmnopqrstuv',
    });
  });

  it('empty / malformed book_json → empty mandala, no throw (fail-closed)', () => {
    expect(mapMandalaBookJson({}).segments).toEqual([]);
    expect(mapMandalaBookJson(null).center_goal).toBe('Untitled mandala');
  });
});
