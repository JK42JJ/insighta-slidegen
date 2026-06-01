import { describe, it, expect } from 'vitest';
import { LAYOUT_MAP } from '@/plan/templates';

describe('Templates — LAYOUT_MAP', () => {
  it('모든 layout 키가 LAYOUT_MAP에 정의됨', () => {
    const expectedLayouts = [
      'cover',
      'section_intro',
      'key_points',
      'qa_pair',
      'figure_full',
      'figure_caption',
      'timeline',
      'summary',
      'blank',
    ];

    expectedLayouts.forEach((layout) => {
      expect(LAYOUT_MAP).toHaveProperty(layout);
    });
  });

  it('각 layout의 primarySource가 정의됨', () => {
    Object.values(LAYOUT_MAP).forEach((fieldMap) => {
      expect(fieldMap.primarySource).toBeDefined();
      expect(typeof fieldMap.primarySource).toBe('string');
    });
  });

  it('figure 레이아웃의 figureAspect가 유효함', () => {
    const figureLayouts = [
      LAYOUT_MAP.figure_full,
      LAYOUT_MAP.figure_caption,
    ];

    figureLayouts.forEach((layout) => {
      if (layout.zones.figureAspect) {
        expect(['16:9', '4:3', '1:1']).toContain(
          layout.zones.figureAspect
        );
      }
    });
  });

  it('key_points와 summary의 maxItems가 정의됨', () => {
    expect(LAYOUT_MAP.key_points.maxItems).toBeDefined();
    expect(LAYOUT_MAP.summary.maxItems).toBeDefined();
    expect(LAYOUT_MAP.key_points.maxItems).toBeGreaterThan(0);
    expect(LAYOUT_MAP.summary.maxItems).toBeGreaterThan(0);
  });
});
