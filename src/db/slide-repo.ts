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
import { Prisma, PrismaClient } from '@prisma/client';
import type { SlideOutline, FigureRef } from '@/types/slide-manifest';
import { JOB_STAGES, JOB_STATUSES, type JobStage, type JobStatus } from '@/types/job-stages';

export interface UpsertDeckResult {
  deckId: string;
  created: boolean;
}

/** Nullable Json column input: absent/null → SQL NULL, else the value. */
function jsonOrDbNull(value: unknown): Prisma.InputJsonValue | typeof Prisma.DbNull {
  return value === undefined || value === null ? Prisma.DbNull : (value as Prisma.InputJsonValue);
}

/**
 * Upserts a slide_decks row from a SlideOutline (PR-H2).
 *
 * Upsert key: the (video_id, generator_version) unique constraint — a re-run
 * of the same video/generator rebuilds the SAME deck row (status back to
 * 'building', error cleared, fingerprint refreshed).
 */
export async function upsertDeck(
  outline: SlideOutline,
  userId: string | undefined,
  prisma: PrismaClient
): Promise<UpsertDeckResult> {
  const uniqueWhere = {
    video_id_generator_version: {
      video_id: outline.video_id,
      generator_version: outline.generator_version,
    },
  };
  const existing = await prisma.slide_decks.findUnique({
    where: uniqueWhere,
    select: { id: true },
  });
  const row = await prisma.slide_decks.upsert({
    where: uniqueWhere,
    create: {
      video_id: outline.video_id,
      lang: outline.lang,
      generator_version: outline.generator_version,
      v2_fingerprint: outline.v2_fingerprint,
      status: 'building',
      slide_count: outline.slides.length,
      user_id: userId ?? null,
    },
    update: {
      lang: outline.lang,
      v2_fingerprint: outline.v2_fingerprint,
      status: 'building',
      slide_count: outline.slides.length,
      error: null,
      ...(userId !== undefined ? { user_id: userId } : {}),
    },
    select: { id: true },
  });
  return { deckId: row.id, created: existing === null };
}

/**
 * Replaces all slide_slides rows for a deck (full rebuild, one transaction).
 *
 * slide_figures.slide_id references slides — detach deck figures from slides
 * FIRST so the delete cannot hit the FK. Per-slide figure linkage is a later
 * concern; figures live at deck level (replaceFigures).
 */
export async function replaceSlides(
  deckId: string,
  outline: SlideOutline,
  prisma: PrismaClient
): Promise<void> {
  await prisma.$transaction([
    prisma.slide_figures.updateMany({
      where: { deck_id: deckId },
      data: { slide_id: null },
    }),
    prisma.slide_slides.deleteMany({ where: { deck_id: deckId } }),
    prisma.slide_slides.createMany({
      data: outline.slides.map((slide) => ({
        deck_id: deckId,
        position: slide.position,
        layout: slide.layout,
        title: slide.title ?? null,
        body_json: jsonOrDbNull(slide.body_json),
        notes: slide.notes ?? null,
        section_ref: slide.section_ref ?? null,
      })),
    }),
  ]);
}

/**
 * Replaces slide_figures rows for a deck (delete + re-insert, one transaction).
 */
export async function replaceFigures(
  deckId: string,
  figures: FigureRef[],
  prisma: PrismaClient
): Promise<void> {
  await prisma.$transaction([
    prisma.slide_figures.deleteMany({ where: { deck_id: deckId } }),
    prisma.slide_figures.createMany({
      // extracted_latex / bbox are in the Prisma mirror but NOT in the prod
      // DDL (drift verified 2026-06-11 — same family as slide_keyframes'
      // routing-metadata columns). Until the raw-DDL follow-up lands, write
      // only the columns that exist; the bundle still carries LaTeX/bbox to
      // the deck build.
      data: figures.map((figure) => ({
        deck_id: deckId,
        cv_figure_id: figure.cv_figure_id,
        kind: figure.kind,
        png_url: figure.png_url,
        vector_pdf_url: figure.vector_pdf_url ?? null,
        vector_svg_url: figure.vector_svg_url ?? null,
        caption: figure.caption ?? null,
        timestamp_sec: figure.timestamp_sec ?? null,
        atom_refs: jsonOrDbNull(figure.atom_refs),
        verification_status: figure.verification_status,
        extraction_conf: figure.extraction_conf ?? null,
      })),
    }),
  ]);
}

/**
 * Updates status and error fields of a slide_decks row.
 * Called by the orchestrator after each pipeline stage completes or fails.
 */
export async function setDeckStatus(
  deckId: string,
  status: string,
  error: string | null,
  prisma: PrismaClient
): Promise<void> {
  await prisma.slide_decks.update({
    where: { id: deckId },
    data: { status, error },
  });
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
