/**
 * A1 (native table) + figure routing regression. table-kind figures with a
 * valid struct must become NATIVE pptx tables (editable, no raster);
 * empty/invalid structs fall back to the image path (an image beats a broken
 * empty table). Non-table figures stay on the image path. deck/ is consumed
 * via createRequire.
 */
import { createRequire } from 'node:module';
import { describe, expect, it } from 'vitest';

const require = createRequire(import.meta.url);
const { injectFigureSlides } = require('../deck/scripts/deck_recipes.js') as {
  injectFigureSlides: (
    plan: Array<[string, Record<string, unknown>]>,
    content: { figures?: Array<Record<string, unknown>> },
    figureAssets?: Record<string, string>,
    figureTables?: Record<string, { headers: unknown[]; rows: unknown[] }>
  ) => number;
};

const TABLE = {
  headers: ['A', 'B'],
  rows: [
    ['1', '2'],
    ['3', '4'],
  ],
};

function runInject(
  figures: Array<Record<string, unknown>>,
  assets: Record<string, string>,
  tables: Record<string, { headers: unknown[]; rows: unknown[] }>
): Array<[string, Record<string, unknown>]> {
  const plan: Array<[string, Record<string, unknown>]> = [
    ['cover', {}],
    ['closing', {}],
  ];
  injectFigureSlides(plan, { figures }, assets, tables);
  return plan;
}

const methods = (plan: Array<[string, Record<string, unknown>]>): string[] => plan.map((p) => p[0]);

describe('injectFigureSlides — A1 native-table routing', () => {
  it('routes a valid table-kind figure to figureTableSlide (native), not an image', () => {
    const plan = runInject(
      [{ figure_id: 'f1', kind: 'table', title: 'T', caption: 'c' }],
      { f1: '/tmp/f1.png' }, // an image exists, but native table must win
      { f1: TABLE }
    );
    expect(methods(plan)).toContain('figureTableSlide');
    expect(methods(plan)).not.toContain('figureSlide');
    const tableEntry = plan.find((p) => p[0] === 'figureTableSlide')![1];
    expect(tableEntry.headers).toEqual(TABLE.headers);
    expect(tableEntry.rows).toEqual(TABLE.rows);
  });

  it('falls back to the image when a table struct is empty/missing', () => {
    const empty = runInject(
      [{ figure_id: 'f1', kind: 'table', title: 'T' }],
      { f1: '/tmp/f1.png' },
      { f1: { headers: [], rows: [] } } // invalid → fallback
    );
    expect(methods(empty)).toContain('figureSlide');
    expect(methods(empty)).not.toContain('figureTableSlide');

    const missing = runInject([{ figure_id: 'f1', kind: 'table' }], { f1: '/tmp/f1.png' }, {});
    expect(methods(missing)).toContain('figureSlide');
  });

  it('non-table figures stay on the image path', () => {
    const plan = runInject(
      [{ figure_id: 'f1', kind: 'diagram', title: 'D' }],
      { f1: '/tmp/f1.png' },
      { f1: TABLE } // a table struct under this id is ignored for a diagram kind
    );
    expect(methods(plan)).toContain('figureSlide');
    expect(methods(plan)).not.toContain('figureTableSlide');
  });

  it('a table-kind figure with no image AND no struct places nothing (label-only)', () => {
    const plan = runInject([{ figure_id: 'f1', kind: 'table' }], {}, {});
    expect(methods(plan)).toEqual(['cover', 'closing']);
  });
});
