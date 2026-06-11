/**
 * Measurement runner + report tests (PR-H1). All pipelines are STUBS —
 * no live model/LLM call exists anywhere in this module (LLM API ban).
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterAll, describe, expect, it } from 'vitest';
import {
  loadSampleSet,
  runMeasurement,
  StageFailureError,
  type PipelineFn,
  type SampleEntry,
  type VideoMeasurement,
} from '@/measure/runner';
import {
  G2_MAX_AVG_ATTEMPTS,
  generateReport,
  pickManualReviewSamples,
  rollupFailureFamilies,
} from '@/measure/report';

const SAMPLES: SampleEntry[] = [
  { index: 'V01', videoId: 'synthvid001' },
  { index: 'V02', videoId: 'synthvid002' },
  { index: 'V03', videoId: 'synthvid003' },
  { index: 'V04', videoId: 'synthvid004' },
];

function ok(attempts: number, below = 0, total = 4): Omit<VideoMeasurement, 'index'> {
  return {
    validatePass: true,
    attempts,
    conf: { belowThreshold: below, total },
    failureStage: null,
  };
}

const tempDirs: string[] = [];
afterAll(() => {
  for (const dir of tempDirs) fs.rmSync(dir, { recursive: true, force: true });
});

describe('loadSampleSet', () => {
  it('parses a valid external sample file and rejects duplicates', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'prh-samples-'));
    tempDirs.push(dir);
    const file = path.join(dir, 'samples.json');
    fs.writeFileSync(file, JSON.stringify(SAMPLES));
    expect(loadSampleSet(file)).toEqual(SAMPLES);

    fs.writeFileSync(file, JSON.stringify([SAMPLES[0], SAMPLES[0]]));
    expect(() => loadSampleSet(file)).toThrow(/duplicate index/);
  });
});

describe('runMeasurement', () => {
  it('collects per-video results and attributes failures via StageFailureError', async () => {
    const pipeline: PipelineFn = (entry) => {
      if (entry.index === 'V02') {
        return Promise.reject(new StageFailureError('detect', 'YOLO 5xx after retries'));
      }
      if (entry.index === 'V04') {
        return Promise.reject(new Error('unattributed crash'));
      }
      return Promise.resolve(ok(entry.index === 'V03' ? 2 : 1));
    };

    const results = await runMeasurement(SAMPLES, pipeline);
    expect(results).toHaveLength(4);
    expect(results[0]).toMatchObject({ index: 'V01', validatePass: true, attempts: 1 });
    expect(results[1]).toMatchObject({
      index: 'V02',
      validatePass: false,
      failureStage: 'detect',
      error: 'YOLO 5xx after retries',
    });
    expect(results[3]).toMatchObject({ index: 'V04', failureStage: null });

    // PUBLIC rule: a failure record never leaks the videoId.
    expect(JSON.stringify(results)).not.toContain('synthvid002');
  });
});

describe('rollupFailureFamilies', () => {
  it('rolls recognition/build/other families per ADR 0004', () => {
    const ms: VideoMeasurement[] = [
      { index: 'V01', ...ok(1) },
      { index: 'V02', ...ok(1), failureStage: 'detect' },
      { index: 'V03', ...ok(1), failureStage: 'numerize' },
      { index: 'V04', ...ok(1), failureStage: 'validate' },
      { index: 'V05', ...ok(1), failureStage: 'acquire' },
    ];
    expect(rollupFailureFamilies(ms)).toEqual({
      recognition: 2,
      build: 1,
      other: 1,
      none: 1,
    });
  });
});

describe('generateReport', () => {
  it('computes G1/G2/G3 and renders gates, rollup, G4 checklist, H1–H3 blanks', async () => {
    const pipeline: PipelineFn = (entry) =>
      entry.index === 'V02'
        ? Promise.reject(new StageFailureError('select', 'routing failed'))
        : Promise.resolve(ok(2, 1, 5));
    const results = await runMeasurement(SAMPLES, pipeline);
    const report = generateReport(results);

    // G1: 3/4 = 75% < 90% → FAIL verdict appears.
    expect(report).toContain('| G1 validate PASS | 3/4 (75.0%) | ≥ 90% | ❌ FAIL |');
    // G2: completed runs all used 2 attempts → 2.00 ≤ 2.0 PASS.
    expect(G2_MAX_AVG_ATTEMPTS).toBe(2.0);
    expect(report).toContain('| G2 avg attempts | 2.00 | ≤ 2.0 | ✅ PASS |');
    // G3 report-only ratio over completed figures: 3/15.
    expect(report).toContain('| G3 conf < 0.7 | 3/15 (20.0%) | report-only | — |');
    // Family rollup: the select failure lands in recognition.
    expect(report).toContain('| recognition | detect/select/numerize | 1 |');
    // G4 deterministic picks: first + middle (V01, V03).
    expect(pickManualReviewSamples(results)).toEqual(['V01', 'V03']);
    expect(report).toContain('### V01');
    expect(report).toContain('### V03');
    // H1–H3 blank rows for every video.
    for (const sample of SAMPLES) {
      expect(report).toContain(`| ${sample.index} |  |  |  |  |`);
    }
    // PUBLIC rule: no videoId ever reaches the report.
    expect(report).not.toContain('synthvid');
  });
});
