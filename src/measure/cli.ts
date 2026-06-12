/**
 * ADR 0004 measurement CLI (PR-H2).
 *
 * Usage:
 *   npm run measure -- --samples /path/to/sample-set.json \
 *     [--out prh-report.md] [--artifacts /tmp/slidegen-measure] \
 *     [--cv-timeout-sec 1800]
 *
 * The sample-set file lives OUTSIDE the repo (real videoIds — PUBLIC-repo
 * policy); stdout, the report, and the measurements JSON carry the anonymous
 * indexes (V01…) only. Prod run shape (keys CLI-inline injected, never in a
 * dev .env):
 *   SLIDEGEN_MODE=prod DATABASE_URL=… OPENROUTER_API_KEY=… \
 *   SLIDEGEN_VLM_BACKEND=http SLIDEGEN_VLM_BASE_URL=… SLIDEGEN_VLM_TOKEN=… \
 *   SLIDEGEN_VLM_MODEL=… SLIDEGEN_YOLO_BASE_URL=… SLIDEGEN_YOLO_TOKEN=… \
 *   SLIDEGEN_CV_SERVICE_URL=… npm run measure -- --samples …
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { parseArgs } from 'util';
import { PrismaClient } from '@prisma/client';
import { buildRealPipeline } from '@/measure/pipeline';
import { generateReport } from '@/measure/report';
import { loadSampleSet, runMeasurement } from '@/measure/runner';

const DEFAULT_REPORT_PATH = 'prh-report.md';
const DEFAULT_CV_TIMEOUT_SEC = 1_800;
const MS_PER_SEC = 1_000;

async function main(): Promise<void> {
  const { values } = parseArgs({
    args: process.argv.slice(2),
    options: {
      samples: { type: 'string' },
      out: { type: 'string', default: DEFAULT_REPORT_PATH },
      artifacts: { type: 'string' },
      'cv-artifacts': { type: 'string' },
      'cv-timeout-sec': { type: 'string' },
    },
  });

  if (!values.samples) {
    console.error('Error: --samples <path> is required (external, non-committed sample-set JSON)');
    process.exit(1);
    return;
  }
  const artifactsDir = values.artifacts ?? path.join(os.tmpdir(), 'slidegen-measure');
  const cvTimeoutMs = Number(values['cv-timeout-sec'] ?? DEFAULT_CV_TIMEOUT_SEC) * MS_PER_SEC;

  const samples = loadSampleSet(values.samples);
  console.log(`[measure] ${samples.length} samples, artifacts → ${artifactsDir}`);

  const prisma = new PrismaClient();
  try {
    const pipeline = buildRealPipeline({
      prisma,
      artifactsDir,
      cvTimeoutMs,
      // Service-side per-stage artifact tree (Mac Mini path). Review pull is ops.
      ...(values['cv-artifacts'] ? { cvArtifactsRoot: values['cv-artifacts'] } : {}),
    });
    const measurements = await runMeasurement(samples, async (entry) => {
      // Index only — the videoId never reaches stdout (pipeline errors are
      // already sanitized by buildRealPipeline before they surface here).
      console.log(`[measure] ${entry.index} start`);
      try {
        const result = await pipeline(entry);
        console.log(
          `[measure] ${entry.index} done: validate=${result.validatePass ? 'PASS' : 'FAIL'} ` +
            `attempts=${result.attempts} failure_stage=${result.failureStage ?? '—'}`
        );
        return result;
      } catch (err) {
        console.log(`[measure] ${entry.index} FAILED: ${err instanceof Error ? err.message : err}`);
        throw err;
      }
    });

    const report = generateReport(measurements);
    fs.writeFileSync(values.out, report);
    const measurementsPath = `${values.out.replace(/\.md$/, '')}-measurements.json`;
    fs.writeFileSync(measurementsPath, JSON.stringify(measurements, null, 2));
    console.log(`[measure] report → ${values.out}, raw → ${measurementsPath}`);
  } finally {
    await prisma.$disconnect();
  }
}

void main().catch((err) => {
  console.error('[measure] fatal:', err instanceof Error ? err.message : err);
  process.exit(1);
});
