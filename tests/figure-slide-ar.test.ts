/**
 * Regression (V02 after-run): figureSlide stretched every figure to the slot
 * box (AR 11.25 → 2.75) because pptxgenjs `sizing:{type:"contain"}` did not
 * preserve aspect ratio. figureSlide now computes the contain box from the
 * PNG's intrinsic size. These tests pin the AR-preserving geometry on the
 * vendored helper directly (deck/ is consumed via createRequire).
 */
import { createRequire } from 'node:module';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterAll, describe, expect, it } from 'vitest';

const require = createRequire(import.meta.url);
const { _fitContain, _pngSize } = require('../deck/scripts/slide_templates.js') as {
  _fitContain: (
    img: string,
    x: number,
    y: number,
    maxW: number,
    maxH: number
  ) => { x: number; y: number; w: number; h: number };
  _pngSize: (p: string) => { w: number; h: number } | null;
};

/** Write a 24-byte stub carrying a valid PNG signature + IHDR width/height —
 * _pngSize only reads the first 24 bytes, so a full PNG is unnecessary. */
function stubPng(w: number, h: number): string {
  const buf = Buffer.alloc(24);
  Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]).copy(buf, 0); // sig
  buf.write('IHDR', 12, 'ascii');
  buf.writeUInt32BE(w, 16);
  buf.writeUInt32BE(h, 20);
  const p = path.join(os.tmpdir(), `ar-${w}x${h}-${Math.round(w * h)}.png`);
  fs.writeFileSync(p, buf);
  return p;
}

const SLOT = { x: 0.62, y: 1.62, w: 12.09, h: 4.7 };
const made: string[] = [];
const png = (w: number, h: number): string => {
  const p = stubPng(w, h);
  made.push(p);
  return p;
};

afterAll(() => made.forEach((p) => fs.existsSync(p) && fs.unlinkSync(p)));

const arOf = (b: { w: number; h: number }): number => b.w / b.h;

describe('figureSlide _fitContain — aspect-ratio preservation', () => {
  it('reads PNG intrinsic size from the IHDR', () => {
    expect(_pngSize(png(2000, 400))).toEqual({ w: 2000, h: 400 });
  });

  it('a wide figure (AR 11.25) keeps its AR — the exact V02 stretch bug', () => {
    const box = _fitContain(png(7437, 661), SLOT.x, SLOT.y, SLOT.w, SLOT.h);
    expect(arOf(box)).toBeCloseTo(7437 / 661, 1); // NOT the slot AR 2.57
    expect(box.w).toBeLessThanOrEqual(SLOT.w + 1e-9);
    expect(box.h).toBeLessThanOrEqual(SLOT.h + 1e-9);
  });

  it('width-bound figure (under the scale-up cap) fills the width and centers vertically', () => {
    // native 8in wide → scale 12.09/8 = 1.51× < 1.6 cap, so it fills the width.
    const box = _fitContain(png(2400, 800), SLOT.x, SLOT.y, SLOT.w, SLOT.h);
    expect(box.w).toBeCloseTo(SLOT.w, 5);
    expect(box.y).toBeGreaterThan(SLOT.y); // letterboxed (centered) in the slot
    expect(arOf(box)).toBeCloseTo(2400 / 800, 1);
  });

  it('tall figure (under the cap) is height-bound and centers horizontally', () => {
    // native 3.33in tall → scale 4.7/3.33 = 1.41× < 1.6 cap, so it fills height.
    const box = _fitContain(png(450, 1000), SLOT.x, SLOT.y, SLOT.w, SLOT.h);
    expect(box.h).toBeCloseTo(SLOT.h, 5);
    expect(box.x).toBeGreaterThan(SLOT.x);
    expect(arOf(box)).toBeCloseTo(0.45, 2);
  });

  it('A3: a small figure is NOT enlarged past 1.6× native (font upper bound)', () => {
    // native 3×2in → would scale ~2.35× to fill the slot; capped to 1.6×.
    const W = 900,
      H = 600;
    const box = _fitContain(png(W, H), SLOT.x, SLOT.y, SLOT.w, SLOT.h);
    const scale = box.w / (W / 300);
    expect(scale).toBeLessThanOrEqual(1.6 + 1e-9);
    expect(scale).toBeCloseTo(1.6, 2); // hit the cap, not the slot
    expect(arOf(box)).toBeCloseTo(W / H, 2); // AR still preserved
    expect(box.x).toBeGreaterThan(SLOT.x); // centered (letterbox both axes)
    expect(box.y).toBeGreaterThan(SLOT.y);
  });

  it('falls back to filling the slot when the size is unreadable', () => {
    const box = _fitContain('/tmp/not-a-real-file.png', SLOT.x, SLOT.y, SLOT.w, SLOT.h);
    expect(box).toEqual({ x: SLOT.x, y: SLOT.y, w: SLOT.w, h: SLOT.h });
  });
});
