/**
 * Repository layer for slide_* tables (write path).
 * All reads of insighta-owned tables go through fetch/ and resolve/ modules.
 *
 * Upsert semantics:
 *   slide_decks  — upsert on (video_id, generator_version) unique constraint.
 *   slide_slides — delete-then-insert for a given deck_id (full rebuild).
 *   slide_figures — delete-then-insert for a given deck_id.
 */
import { PrismaClient } from '@prisma/client';
import type { SlideOutline, FigureRef } from '@/types/slide-manifest';

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
