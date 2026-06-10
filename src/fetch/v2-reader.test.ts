/**
 * Unit tests for fetchV2 — v2 gate + Zod validation.
 *
 * Prisma is mocked as a plain object (no DB connection): fetchV2 takes a
 * caller-injected client and only calls video_rich_summaries.findUnique.
 * Fixture: synthetic row in v2-summary.fixture.ts (no real YouTube ids).
 */
import { describe, expect, it, vi } from 'vitest';
import { ZodError } from 'zod';
import type { PrismaClient } from '@prisma/client';
import { fetchV2 } from '@/fetch/v2-reader';
import { SYNTHETIC_VIDEO_ID, makeV2Row } from '@/types/v2-summary.fixture';

/** Minimal prisma mock — only the surface fetchV2 touches. */
function mockPrisma(row: Record<string, unknown> | null): PrismaClient {
  return {
    video_rich_summaries: {
      findUnique: vi.fn().mockResolvedValue(row),
    },
  } as unknown as PrismaClient;
}

describe('fetchV2', () => {
  it('returns the validated summary on the happy path', async () => {
    const prisma = mockPrisma(makeV2Row());

    const summary = await fetchV2(SYNTHETIC_VIDEO_ID, prisma);

    expect(summary.video_id).toBe(SYNTHETIC_VIDEO_ID);
    expect(summary.segments?.sections).toHaveLength(3);
    expect(summary.segments?.atoms?.[2]?.type).toBe('tip');
    const findUnique = (prisma as unknown as { video_rich_summaries: { findUnique: unknown } })
      .video_rich_summaries.findUnique;
    expect(findUnique).toHaveBeenCalledWith({ where: { video_id: SYNTHETIC_VIDEO_ID } });
  });

  it('throws V2_GATE_FAILED when no row exists', async () => {
    await expect(fetchV2(SYNTHETIC_VIDEO_ID, mockPrisma(null))).rejects.toThrow(
      /^V2_GATE_FAILED: no video_rich_summaries row/
    );
  });

  it('throws V2_GATE_FAILED when template_version is not v2', async () => {
    const prisma = mockPrisma(makeV2Row({ template_version: 'v1' }));
    await expect(fetchV2(SYNTHETIC_VIDEO_ID, prisma)).rejects.toThrow(
      /^V2_GATE_FAILED: template_version='v1'/
    );
  });

  it('throws V2_GATE_FAILED when quality_flag is not pass', async () => {
    const prisma = mockPrisma(makeV2Row({ quality_flag: 'low' }));
    await expect(fetchV2(SYNTHETIC_VIDEO_ID, prisma)).rejects.toThrow(
      /^V2_GATE_FAILED: quality_flag='low'/
    );
  });

  it('throws V2_GATE_FAILED when transcript_used is false', async () => {
    const prisma = mockPrisma(makeV2Row({ transcript_used: false }));
    await expect(fetchV2(SYNTHETIC_VIDEO_ID, prisma)).rejects.toThrow(
      /^V2_GATE_FAILED: transcript_used=false/
    );
  });

  it('throws ZodError on consumed-field shape mismatch (segments as array)', async () => {
    const prisma = mockPrisma(
      makeV2Row({ segments: [{ from_sec: 0, to_sec: 10, title: 'x', relevance_pct: 50 }] })
    );
    await expect(fetchV2(SYNTHETIC_VIDEO_ID, prisma)).rejects.toThrow(ZodError);
  });
});
