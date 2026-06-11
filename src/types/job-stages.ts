/**
 * A-pipeline job stages — the CHECK domain of slide_jobs.stage / failure_stage.
 *
 * Single source for TS consumers (no magic stage strings). MUST stay 1:1 with
 * the raw SQL DDL (prisma/migrations/slidegen-jobs-v2/001_slide_jobs_stage_v2.sql)
 * — enforced by job-stages.test.ts.
 *
 * ADR 0004 B-switch attribution families:
 *   detect / select / numerize → recognition family (failures argue for B: YOLO fine-tune)
 *   build / validate           → build family (failures argue for prompt/harness fixes)
 */
import { z } from 'zod';

export const JOB_STAGES = [
  'acquire',
  'keyframe',
  'detect',
  'select',
  'numerize',
  'build',
  'validate',
] as const;

export const JobStageSchema = z.enum(JOB_STAGES);
export type JobStage = z.infer<typeof JobStageSchema>;

/** slide_jobs.status domain (PR-G: timeout has NO status of its own —
 * it is status='error' + last_error=TIMEOUT_ERROR + failure_stage). */
export const JOB_STATUSES = ['queued', 'running', 'done', 'error'] as const;
export const JobStatusSchema = z.enum(JOB_STATUSES);
export type JobStatus = z.infer<typeof JobStatusSchema>;

/** ADR 0004: failures concentrated here argue for the B switch (YOLO fine-tune). */
export const RECOGNITION_STAGES = [
  'detect',
  'select',
  'numerize',
] as const satisfies readonly JobStage[];

/** ADR 0004: failures concentrated here argue for prompt/harness fixes, not B. */
export const BUILD_STAGES = ['build', 'validate'] as const satisfies readonly JobStage[];

/** ADR 0004 G2 gate: self-correction attempts ≤ 2.0 → default attempt budget per job. */
export const MAX_ATTEMPTS_DEFAULT = 2;

/** Timeout convention (PR-G decision): status stays the 4-value set; a timed-out
 * job is status='error' + last_error=TIMEOUT_ERROR + failure_stage set. */
export const TIMEOUT_ERROR = 'timeout';
