/**
 * Unit tests for the V2 rich-summary Zod mirror (V2SummarySchema).
 *
 * The mirror must accept REAL v2 rows (lenient on non-consumed fields) and
 * fail loud only on gate fields + consumed-field shape violations.
 * Fixture: synthetic row in v2-summary.fixture.ts (no real YouTube ids).
 */
import { describe, expect, it } from 'vitest';
import { V2SummarySchema } from '@/types/slide-manifest';
import { SYNTHETIC_VIDEO_ID, makeV2Row } from '@/types/v2-summary.fixture';

describe('V2SummarySchema', () => {
  it('parses a realistic v2 row (happy path)', () => {
    const parsed = V2SummarySchema.parse(makeV2Row());

    expect(parsed.video_id).toBe(SYNTHETIC_VIDEO_ID);
    expect(parsed.template_version).toBe('v2');
    expect(parsed.core.one_liner).toBe('Spaced repetition basics');
    expect(parsed.segments?.sections).toHaveLength(3);
    expect(parsed.segments?.sections?.[0]?.key_points?.[0]?.text).toBe(
      'Memory decays exponentially without review'
    );
    expect(parsed.segments?.atoms).toHaveLength(3);
    expect(parsed.segments?.atoms?.[0]?.type).toBe('fact');
    expect(parsed.analysis.entities).toHaveLength(3);
    expect(parsed.analysis.key_concepts?.[0]?.term).toBe('Spaced repetition');
  });

  it('parses when segments column is null or absent (transcript-less rows)', () => {
    expect(() => V2SummarySchema.parse(makeV2Row({ segments: null }))).not.toThrow();

    const noSegments = makeV2Row();
    delete noSegments['segments'];
    expect(() => V2SummarySchema.parse(noSegments)).not.toThrow();
  });

  it('passes through non-consumed analysis fields without strict typing', () => {
    const parsed = V2SummarySchema.parse(makeV2Row());
    // actionables / mandala_fit / bias_signals are not strictly typed but
    // must survive the parse (.passthrough()).
    const analysis = parsed.analysis as Record<string, unknown>;
    expect(analysis['actionables']).toHaveLength(3);
    expect(analysis['bias_signals']).toMatchObject({ has_ad: false });
  });

  it('rejects segments delivered as an ARRAY (legacy/wrong mirror shape)', () => {
    const row = makeV2Row({
      segments: [{ from_sec: 0, to_sec: 10, title: 'x', relevance_pct: 50 }],
    });
    expect(() => V2SummarySchema.parse(row)).toThrow();
  });

  it('rejects a section missing a consumed field (title)', () => {
    const row = makeV2Row({
      segments: { sections: [{ from_sec: 0, to_sec: 10, relevance_pct: 50 }], atoms: [] },
    });
    expect(() => V2SummarySchema.parse(row)).toThrow();
  });

  it('rejects core missing one_liner (consumed-field fail-loud)', () => {
    const row = makeV2Row({
      core: {
        domain: 'learning',
        depth_level: 'beginner',
        content_type: 'tutorial',
        target_audience: 'anyone',
      },
    });
    expect(() => V2SummarySchema.parse(row)).toThrow();
  });

  it('rejects gate-field violations', () => {
    expect(() => V2SummarySchema.parse(makeV2Row({ template_version: 'v1' }))).toThrow();
    expect(() => V2SummarySchema.parse(makeV2Row({ quality_flag: 'low' }))).toThrow();
    expect(() => V2SummarySchema.parse(makeV2Row({ transcript_used: false }))).toThrow();
    expect(() => V2SummarySchema.parse(makeV2Row({ video_id: 'short' }))).toThrow();
  });
});
