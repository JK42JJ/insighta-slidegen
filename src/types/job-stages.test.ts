/**
 * Cross-layer regression: the TS stage constants and the raw SQL DDL CHECK
 * domains must stay 1:1 (CLAUDE.md Cross-Layer Propagation — tsc PASS ≠
 * runtime safety; a drifted stage string would only fail at INSERT time).
 */
import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  BUILD_STAGES,
  JOB_STAGES,
  JobStageSchema,
  MAX_ATTEMPTS_DEFAULT,
  RECOGNITION_STAGES,
} from '@/types/job-stages';

const DDL_PATH = path.resolve(
  process.cwd(),
  'prisma/migrations/slidegen-jobs-v2/001_slide_jobs_stage_v2.sql'
);

/** Every `IN ('a', 'b', ...)` list inside the DDL's CHECK constraints. */
function ddlCheckLists(sql: string): string[][] {
  return [...sql.matchAll(/IN \(\s*([^)]+?)\s*\)/g)].map((m) =>
    (m[1] ?? '')
      .split(',')
      .map((s) => s.trim().replace(/^'|'$/g, ''))
      .filter(Boolean)
  );
}

describe('job stages — TS constants ↔ raw SQL DDL 1:1', () => {
  const ddl = fs.readFileSync(DDL_PATH, 'utf8');

  it('both DDL CHECK lists (stage, failure_stage) equal JOB_STAGES exactly', () => {
    const lists = ddlCheckLists(ddl);
    // chk_slide_jobs_stage + chk_slide_jobs_failure_stage
    expect(lists).toHaveLength(2);
    for (const list of lists) {
      expect(new Set(list)).toEqual(new Set(JOB_STAGES));
    }
  });

  it('DDL default max_attempts matches MAX_ATTEMPTS_DEFAULT (ADR 0004 G2)', () => {
    const match = ddl.match(/max_attempts\s+INTEGER\s+NOT NULL DEFAULT (\d+)/);
    expect(match).not.toBeNull();
    expect(Number(match?.[1])).toBe(MAX_ATTEMPTS_DEFAULT);
  });
});

describe('job stages — ADR 0004 attribution families', () => {
  it('recognition + build families partition into JOB_STAGES without overlap', () => {
    const families = [...RECOGNITION_STAGES, ...BUILD_STAGES];
    expect(new Set(families).size).toBe(families.length);
    for (const stage of families) {
      expect(JOB_STAGES).toContain(stage);
    }
  });

  it('families are exactly detect/select/numerize vs build/validate', () => {
    expect([...RECOGNITION_STAGES]).toEqual(['detect', 'select', 'numerize']);
    expect([...BUILD_STAGES]).toEqual(['build', 'validate']);
  });
});

describe('JobStageSchema', () => {
  it('accepts every v2 stage and rejects v1 stage strings', () => {
    for (const stage of JOB_STAGES) {
      expect(JobStageSchema.parse(stage)).toBe(stage);
    }
    for (const legacy of [
      'resolve',
      'fetch_v2',
      'cv_extract',
      'plan',
      'build_slides',
      'export_pdf',
    ]) {
      expect(JobStageSchema.safeParse(legacy).success).toBe(false);
    }
  });
});
