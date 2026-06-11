/**
 * ADR 0004 quality-gate report generator (PR-H1) — prh-report.md.
 *
 * Automatic metrics: G1 (validate PASS rate), G2 (avg self-correction
 * attempts), G3 (low-confidence extraction ratio, report-only) and the
 * failure_stage family rollup that feeds the B-switch judgement. G4 is a
 * manual checklist; H1–H3 are blank scoring columns James fills in.
 */
import { BUILD_STAGES, RECOGNITION_STAGES, type JobStage } from '@/types/job-stages';
import type { VideoMeasurement } from '@/measure/runner';

// ── ADR 0004 gates ────────────────────────────────────────────────────────────
/** G1: validate PASS ratio gate (≥ 9/10 on the 10-video sample). */
export const G1_MIN_PASS_RATIO = 0.9;
/** G2: average validate self-correction attempts gate. */
export const G2_MAX_AVG_ATTEMPTS = 2.0;
/** G3: extraction-confidence reporting threshold (report-only, NOT a gate). */
export const G3_CONF_THRESHOLD = 0.7;
/** G4: manual keyframe-recall spot checks (2 videos, zero misses). */
export const G4_MANUAL_SAMPLE_COUNT = 2;

export interface FamilyRollup {
  recognition: number;
  build: number;
  other: number;
  none: number;
}

/** failure_stage family rollup (ADR 0004): recognition vs build vs other. */
export function rollupFailureFamilies(measurements: VideoMeasurement[]): FamilyRollup {
  const rollup: FamilyRollup = { recognition: 0, build: 0, other: 0, none: 0 };
  const recognition = new Set<JobStage>(RECOGNITION_STAGES);
  const build = new Set<JobStage>(BUILD_STAGES);
  for (const m of measurements) {
    if (m.failureStage === null) rollup.none += 1;
    else if (recognition.has(m.failureStage)) rollup.recognition += 1;
    else if (build.has(m.failureStage)) rollup.build += 1;
    else rollup.other += 1;
  }
  return rollup;
}

/** G4 spot-check picks — deterministic (first + middle) for reproducibility. */
export function pickManualReviewSamples(measurements: VideoMeasurement[]): string[] {
  if (measurements.length === 0) return [];
  const picks = new Set<number>([0, Math.floor(measurements.length / 2)]);
  return [...picks].map((i) => measurements[i]?.index ?? '').filter(Boolean);
}

function ratio(numerator: number, denominator: number): string {
  if (denominator === 0) return 'n/a';
  return `${((numerator / denominator) * 100).toFixed(1)}%`;
}

function gateMark(pass: boolean): string {
  return pass ? '✅ PASS' : '❌ FAIL';
}

/** Renders prh-report.md. Indexes only — videoIds never reach the report. */
export function generateReport(measurements: VideoMeasurement[]): string {
  const total = measurements.length;
  const passes = measurements.filter((m) => m.validatePass).length;
  const completed = measurements.filter((m) => m.failureStage === null && !m.error);
  const avgAttempts =
    completed.length > 0 ? completed.reduce((sum, m) => sum + m.attempts, 0) / completed.length : 0;
  const confBelow = measurements.reduce((sum, m) => sum + m.conf.belowThreshold, 0);
  const confTotal = measurements.reduce((sum, m) => sum + m.conf.total, 0);
  const rollup = rollupFailureFamilies(measurements);
  const manualPicks = pickManualReviewSamples(measurements);

  const g1Pass = total > 0 && passes / total >= G1_MIN_PASS_RATIO;
  const g2Pass = completed.length > 0 && avgAttempts <= G2_MAX_AVG_ATTEMPTS;

  const lines: string[] = [];
  lines.push('# PR-H — ADR 0004 quality measurement report');
  lines.push('');
  lines.push(`Sample size: ${total} (indexes only — video ids tracked externally)`);
  lines.push('');

  lines.push('## Gates (automatic)');
  lines.push('');
  lines.push('| Gate | Value | Threshold | Verdict |');
  lines.push('|------|-------|-----------|---------|');
  lines.push(
    `| G1 validate PASS | ${passes}/${total} (${ratio(passes, total)}) | ≥ ${G1_MIN_PASS_RATIO * 100}% | ${gateMark(g1Pass)} |`
  );
  lines.push(
    `| G2 avg attempts | ${avgAttempts.toFixed(2)} | ≤ ${G2_MAX_AVG_ATTEMPTS.toFixed(1)} | ${gateMark(g2Pass)} |`
  );
  lines.push(
    `| G3 conf < ${G3_CONF_THRESHOLD} | ${confBelow}/${confTotal} (${ratio(confBelow, confTotal)}) | report-only | — |`
  );
  lines.push('');

  lines.push('## Per-video results');
  lines.push('');
  lines.push('| Index | validate | attempts | conf<0.7 | failure_stage | error |');
  lines.push('|-------|----------|----------|----------|---------------|-------|');
  for (const m of measurements) {
    lines.push(
      `| ${m.index} | ${m.validatePass ? 'PASS' : 'FAIL'} | ${m.attempts} | ` +
        `${m.conf.belowThreshold}/${m.conf.total} | ${m.failureStage ?? '—'} | ${m.error ?? '—'} |`
    );
  }
  lines.push('');

  lines.push('## failure_stage family rollup (ADR 0004 → B-switch judgement)');
  lines.push('');
  lines.push('| Family | Stages | Failures |');
  lines.push('|--------|--------|----------|');
  lines.push(`| recognition | ${RECOGNITION_STAGES.join('/')} | ${rollup.recognition} |`);
  lines.push(`| build | ${BUILD_STAGES.join('/')} | ${rollup.build} |`);
  lines.push(`| other | acquire/keyframe | ${rollup.other} |`);
  lines.push(`| (no failure) | — | ${rollup.none} |`);
  lines.push('');
  lines.push(
    '> B-switch rule (ADR 0004): consider the YOLO fine-tune track (B) ONLY when ' +
      'failures concentrate in the recognition family; build-family failures call ' +
      'for prompt/harness fixes instead.'
  );
  lines.push('');

  lines.push(`## G4 — manual keyframe recall spot check (${G4_MANUAL_SAMPLE_COUNT} videos)`);
  lines.push('');
  lines.push(`Deterministic picks: ${manualPicks.join(', ') || '(none)'}`);
  lines.push('');
  lines.push('Per pick, scrub the source video decile-by-decile and confirm every');
  lines.push('teaching visual (chart / table / diagram / equation) was captured.');
  lines.push('');
  for (const pick of manualPicks) {
    lines.push(`### ${pick}`);
    lines.push('');
    lines.push('| Decile | Teaching visual present? | Captured? | Miss noted |');
    lines.push('|--------|--------------------------|-----------|------------|');
    for (let d = 1; d <= 10; d += 1) {
      lines.push(`| ${d} |  |  |  |`);
    }
    lines.push('');
    lines.push('Misses found: ___ (gate: 0)');
    lines.push('');
  }

  lines.push('## H1–H3 — James scoring (1–5 per video)');
  lines.push('');
  lines.push('| Index | H1 content match | H2 figure numeric accuracy | H3 overall | Notes |');
  lines.push('|-------|------------------|----------------------------|------------|-------|');
  for (const m of measurements) {
    lines.push(`| ${m.index} |  |  |  |  |`);
  }
  lines.push('');

  return lines.join('\n');
}
