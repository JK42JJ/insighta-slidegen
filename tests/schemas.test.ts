import { describe, it, expect } from 'vitest';
import { V2SummarySchema } from '@/types/slide-manifest';

describe('V2SummarySchema', () => {
  it('유효한 최소 v2 요약을 파싱함', () => {
    const data = {
      video_id: '12345678abc',
      template_version: 'v2' as const,
      quality_flag: 'pass' as const,
      transcript_used: true,
    };

    const result = V2SummarySchema.parse(data);
    expect(result.video_id).toBe('12345678abc');
    expect(result.template_version).toBe('v2');
  });

  it('잘못된 template_version 거부', () => {
    const data = {
      video_id: '12345ABCDE',
      template_version: 'v1',
      quality_flag: 'pass',
      transcript_used: true,
    };

    expect(() => V2SummarySchema.parse(data)).toThrow();
  });

  it('quality_flag가 pass가 아니면 거부', () => {
    const data = {
      video_id: '12345ABCDE',
      template_version: 'v2' as const,
      quality_flag: 'fail',
      transcript_used: true,
    };

    expect(() => V2SummarySchema.parse(data)).toThrow();
  });

  it('transcript_used가 false면 거부', () => {
    const data = {
      video_id: '12345ABCDE',
      template_version: 'v2' as const,
      quality_flag: 'pass' as const,
      transcript_used: false,
    };

    expect(() => V2SummarySchema.parse(data)).toThrow();
  });

  it('video_id 길이가 11자 아니면 거부', () => {
    const data = {
      video_id: 'SHORT',
      template_version: 'v2' as const,
      quality_flag: 'pass' as const,
      transcript_used: true,
    };

    expect(() => V2SummarySchema.parse(data)).toThrow('exactly 11');
  });

  it('core, segments, analysis 필드를 포함할 수 있음', () => {
    const data = {
      video_id: '12345678abc',
      template_version: 'v2' as const,
      quality_flag: 'pass' as const,
      transcript_used: true,
      core: {
        title: '테스트 제목',
        one_liner: '한 줄 설명',
        key_concepts: ['개념1', '개념2'],
      },
      segments: [
        {
          from_sec: 0,
          to_sec: 60,
          title: '섹션 제목',
          summary: '섹션 요약',
          relevance_pct: 85,
          key_points: ['포인트1', '포인트2'],
        },
      ],
    };

    const result = V2SummarySchema.parse(data);
    expect(result.core?.title).toBe('테스트 제목');
    expect(result.segments).toHaveLength(1);
    expect(result.segments?.[0].title).toBe('섹션 제목');
  });

  it('segments의 relevance_pct 범위 검증', () => {
    const data = {
      video_id: '12345678abc',
      template_version: 'v2' as const,
      quality_flag: 'pass' as const,
      transcript_used: true,
      segments: [
        {
          from_sec: 0,
          to_sec: 60,
          title: '섹션',
          summary: '요약',
          relevance_pct: 150,
          key_points: [],
        },
      ],
    };

    expect(() => V2SummarySchema.parse(data)).toThrow();
  });

  it('segments 필수 필드 검증', () => {
    const data = {
      video_id: '12345678abc',
      template_version: 'v2' as const,
      quality_flag: 'pass' as const,
      transcript_used: true,
      segments: [
        {
          from_sec: 0,
          to_sec: 60,
          title: '섹션',
          // summary 누락
          relevance_pct: 50,
          key_points: [],
        },
      ],
    };

    expect(() => V2SummarySchema.parse(data)).toThrow();
  });
});
