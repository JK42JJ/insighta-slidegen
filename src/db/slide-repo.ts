/**
 * Repository layer for slide_* tables (write path).
 * All reads of insighta-owned tables go through fetch/ and resolve/ modules.
 *
 * Upsert semantics:
 *   slide_decks  — upsert on (video_id, generator_version) unique constraint.
 *   slide_slides — delete-then-insert for a given deck_id (full rebuild).
 *   slide_figures — delete-then-insert for a given deck_id.
 *   slide_jobs   — one row per pipeline run; stage advances in place and
 *                  failures pin failure_stage (ADR 0004 attribution, PR-H1).
 */
import { PrismaClient } from '@prisma/client';
import type { SlideOutline, FigureRef } from '@/types/slide-manifest';
import { JOB_STAGES, JOB_STATUSES, type JobStage, type JobStatus } from '@/types/job-stages';

export interface UpsertDeckResult {
  deckId: string;
  created: boolean;
}

/**
 * Upserts a slide_decks row from a SlideOutline.
 *
 * Algorithm:
 *   1. prisma.slide_decks.upsert({ where: { uq_slide_decks_video_version }, ... })
 *   2. Return deckId + whether the row was newly created.
 *
 * @param outline - Planner output containing video_id, generator_version, fingerprint.
 * @param userId  - Optional: stored for per-user deck queries.
 * @param prisma  - Prisma client instance.
 *
 * TODO: implement upsert on unique constraint (video_id, generator_version).
 * Set status='building', clear error, store v2_fingerprint.
 */
export async function upsertDeck(
  _outline: SlideOutline,
  _userId: string | undefined,
  _prisma: PrismaClient
): Promise<UpsertDeckResult> {
  throw new Error('TODO: upsertDeck — prisma.slide_decks.upsert on (video_id, generator_version)');
}

/**
 * Replaces all slide_slides rows for a deck (delete + re-insert).
 *
 * @param _deckId  - UUID of the parent slide_decks row.
 * @param _outline - Planner output containing ordered slides array.
 * @param _prisma  - Prisma client instance.
 *
 * TODO: wrap in prisma.$transaction([deleteMany, createMany]).
 */
export async function replaceSlides(
  _deckId: string,
  _outline: SlideOutline,
  _prisma: PrismaClient
): Promise<void> {
  throw new Error('TODO: replaceSlides — deleteMany + createMany within a transaction');
}

/**
 * Replaces slide_figures rows for a deck (delete + re-insert).
 *
 * @param _deckId  - UUID of the parent slide_decks row.
 * @param _figures - FigureRef list from CV client or existing DB cache.
 * @param _prisma  - Prisma client instance.
 *
 * TODO: implement.
 */
export async function replaceFigures(
  _deckId: string,
  _figures: FigureRef[],
  _prisma: PrismaClient
): Promise<void> {
  throw new Error('TODO: replaceFigures — deleteMany + createMany');
}

/**
 * Updates status and error fields of a slide_decks row.
 * Called by the orchestrator after each pipeline stage completes or fails.
 *
 * @param _deckId - UUID of the target slide_decks row.
 * @param _status - New status string ("building" | "done" | "error" | ...).
 * @param _error  - Error message to store, or null to clear.
 * @param _prisma - Prisma client instance.
 *
 * TODO: implement prisma.slide_decks.update.
 */
export async function setDeckStatus(
  _deckId: string,
  _status: string,
  _error: string | null,
  _prisma: PrismaClient
): Promise<void> {
  throw new Error('TODO: setDeckStatus — prisma.slide_decks.update');
}

// ── slide_jobs recording (PR-H1; columns from slidegen-jobs-v2 DDL) ──────────
//
// One slide_jobs row per pipeline run: `stage` always holds the CURRENT
// stage, `failure_stage` pins the stage a failed run died in (ADR 0004
// failure attribution → B-switch judgement), `attempt_count` counts the
// validate self-correction loop (ADR 0004 G2 gate: avg ≤ 2.0).
//
// Timeout convention (PR-G decision): status stays the 4-value set; a
// timed-out job is status='error' + last_error='timeout' + failure_stage.

const STATUS_QUEUED: JobStatus = JOB_STATUSES[0];
const STATUS_RUNNING: JobStatus = JOB_STATUSES[1];
const STATUS_DONE: JobStatus = JOB_STATUSES[2];
const STATUS_ERROR: JobStatus = JOB_STATUSES[3];

export interface CreateJobInput {
  cardId?: string;
  videoId?: string;
  deckId?: string;
}

/** Creates the job row at the first pipeline stage (queued). Returns job id. */
export async function createJob(input: CreateJobInput, prisma: PrismaClient): Promise<string> {
  const row = await prisma.slide_jobs.create({
    data: {
      card_id: input.cardId ?? null,
      video_id: input.videoId ?? null,
      deck_id: input.deckId ?? null,
      stage: JOB_STAGES[0],
      status: STATUS_QUEUED,
    },
    select: { id: true },
  });
  return row.id;
}

/**
 * Marks the job as running stage `stage`. The orchestrator stamps the stage
 * deadline here; a watcher treats (now > timeout_at AND status='running') as
 * a timeout.
 */
export async function enterJobStage(
  jobId: string,
  stage: JobStage,
  prisma: PrismaClient,
  opts?: { timeoutAt?: Date }
): Promise<void> {
  await prisma.slide_jobs.update({
    where: { id: jobId },
    data: { stage, status: STATUS_RUNNING, timeout_at: opts?.timeoutAt ?? null },
  });
}

/** Marks the run done; records the validate-loop attempt count (ADR 0004 G2). */
export async function completeJob(
  jobId: string,
  attemptCount: number,
  prisma: PrismaClient
): Promise<void> {
  await prisma.slide_jobs.update({
    where: { id: jobId },
    data: {
      status: STATUS_DONE,
      attempt_count: attemptCount,
      timeout_at: null,
      last_error: null,
    },
  });
}

/**
 * Marks the run failed and PINS the failing stage (ADR 0004 attribution).
 * `failureStage` is CHECK-constrained to the v2 stage set in the DB.
 */
export async function failJob(
  jobId: string,
  failureStage: JobStage,
  lastError: string,
  prisma: PrismaClient,
  opts?: { attemptCount?: number }
): Promise<void> {
  await prisma.slide_jobs.update({
    where: { id: jobId },
    data: {
      status: STATUS_ERROR,
      failure_stage: failureStage,
      last_error: lastError,
      timeout_at: null,
      ...(opts?.attemptCount !== undefined ? { attempt_count: opts.attemptCount } : {}),
    },
  });
}
