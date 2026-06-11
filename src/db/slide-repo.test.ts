/**
 * slide_jobs recording tests (PR-H1).
 *
 * The fake PrismaClient is a Proxy that records every model property access —
 * the write-path rule test asserts the jobs functions touch ONLY slide_jobs
 * (slidegen-owned), never an insighta table.
 */
import { describe, expect, it } from 'vitest';
import type { PrismaClient } from '@prisma/client';
import {
  completeJob,
  createJob,
  enterJobStage,
  failJob,
  replaceFigures,
  replaceSlides,
  setDeckStatus,
  upsertDeck,
} from '@/db/slide-repo';
import { JOB_STAGES } from '@/types/job-stages';

interface RecordedCall {
  model: string;
  op: string;
  args: Record<string, unknown>;
}

function makeFakePrisma(): { prisma: PrismaClient; touched: Set<string>; calls: RecordedCall[] } {
  const touched = new Set<string>();
  const calls: RecordedCall[] = [];
  const prisma = new Proxy(
    {},
    {
      get(_target, model) {
        if (typeof model !== 'string') return undefined;
        return new Proxy(
          {},
          {
            get(_t, op) {
              if (typeof op !== 'string') return undefined;
              return (args: Record<string, unknown>) => {
                touched.add(model);
                calls.push({ model, op, args });
                return Promise.resolve({ id: 'job-uuid-1' });
              };
            },
          }
        );
      },
    }
  ) as unknown as PrismaClient;
  return { prisma, touched, calls };
}

describe('slide_jobs write path — slidegen tables only', () => {
  it('a full job lifecycle touches ONLY the slide_jobs model', async () => {
    const { prisma, touched } = makeFakePrisma();
    const jobId = await createJob({ videoId: 'synthvid001' }, prisma);
    await enterJobStage(jobId, 'detect', prisma);
    await completeJob(jobId, 2, prisma);
    await failJob(jobId, 'numerize', 'synthetic error', prisma);
    expect([...touched]).toEqual(['slide_jobs']);
  });
});

describe('createJob', () => {
  it('starts at the FIRST pipeline stage, queued', async () => {
    const { prisma, calls } = makeFakePrisma();
    const jobId = await createJob({ cardId: 'card-1', videoId: 'synthvid001' }, prisma);
    expect(jobId).toBe('job-uuid-1');
    expect(calls).toHaveLength(1);
    const call = calls[0];
    expect(call?.op).toBe('create');
    expect(call?.args['data']).toMatchObject({
      card_id: 'card-1',
      video_id: 'synthvid001',
      deck_id: null,
      stage: JOB_STAGES[0], // 'acquire'
      status: 'queued',
    });
  });
});

describe('enterJobStage', () => {
  it('sets stage + running and stamps the timeout deadline', async () => {
    const { prisma, calls } = makeFakePrisma();
    const deadline = new Date('2026-01-01T00:10:00Z');
    await enterJobStage('job-uuid-1', 'select', prisma, { timeoutAt: deadline });
    expect(calls[0]?.args['where']).toEqual({ id: 'job-uuid-1' });
    expect(calls[0]?.args['data']).toEqual({
      stage: 'select',
      status: 'running',
      timeout_at: deadline,
    });
  });

  it('clears timeout_at when no deadline is given', async () => {
    const { prisma, calls } = makeFakePrisma();
    await enterJobStage('job-uuid-1', 'build', prisma);
    expect(calls[0]?.args['data']).toMatchObject({ timeout_at: null });
  });
});

describe('completeJob / failJob — ADR 0004 attribution fields', () => {
  it('completeJob records attempt_count and clears timeout/error', async () => {
    const { prisma, calls } = makeFakePrisma();
    await completeJob('job-uuid-1', 2, prisma);
    expect(calls[0]?.args['data']).toEqual({
      status: 'done',
      attempt_count: 2,
      timeout_at: null,
      last_error: null,
    });
  });

  it('failJob pins failure_stage + last_error', async () => {
    const { prisma, calls } = makeFakePrisma();
    await failJob('job-uuid-1', 'detect', 'YOLO endpoint 5xx after retries', prisma, {
      attemptCount: 1,
    });
    expect(calls[0]?.args['data']).toEqual({
      status: 'error',
      failure_stage: 'detect',
      last_error: 'YOLO endpoint 5xx after retries',
      timeout_at: null,
      attempt_count: 1,
    });
  });

  it('failJob leaves attempt_count untouched when not provided', async () => {
    const { prisma, calls } = makeFakePrisma();
    await failJob('job-uuid-1', 'acquire', 'yt-dlp failed', prisma);
    expect(calls[0]?.args['data']).not.toHaveProperty('attempt_count');
  });
});

// ── PR-H2: deck persistence (formerly TODO stubs — found live at `build`) ────

function makeFakePrismaWithTx(): {
  prisma: PrismaClient;
  touched: Set<string>;
  calls: RecordedCall[];
} {
  const touched = new Set<string>();
  const calls: RecordedCall[] = [];
  const prisma = new Proxy(
    {},
    {
      get(_target, model) {
        if (typeof model !== 'string') return undefined;
        if (model === '$transaction') {
          return (ops: Promise<unknown>[]) => Promise.all(ops);
        }
        return new Proxy(
          {},
          {
            get(_t, op) {
              if (typeof op !== 'string') return undefined;
              return (args: Record<string, unknown>) => {
                touched.add(model);
                calls.push({ model, op, args });
                return Promise.resolve(op === 'findUnique' ? null : { id: 'deck-uuid-1' });
              };
            },
          }
        );
      },
    }
  ) as unknown as PrismaClient;
  return { prisma, touched, calls };
}

const OUTLINE = {
  video_id: 'synthvid001',
  lang: 'ko',
  generator_version: 'slidegen-v1',
  v2_fingerprint: 'f'.repeat(64),
  slides: [
    { position: 0, layout: 'cover', title: 'Synthetic Talk' },
    { position: 1, layout: 'section_header', title: 'Sec', section_ref: 0, body_json: { k: 1 } },
  ],
} as unknown as Parameters<typeof upsertDeck>[0];

describe('deck persistence write path — slidegen tables only', () => {
  it('upsert + replace + status touch ONLY slide_* models', async () => {
    const { prisma, touched } = makeFakePrismaWithTx();
    const { deckId, created } = await upsertDeck(OUTLINE, undefined, prisma);
    await replaceSlides(deckId, OUTLINE, prisma);
    await replaceFigures(
      deckId,
      [
        {
          cv_figure_id: 'f1',
          kind: 'chart',
          png_url: '/tmp/f1.png',
          verification_status: 'pending',
        } as Parameters<typeof replaceFigures>[1][number],
      ],
      prisma
    );
    await setDeckStatus(deckId, 'done', null, prisma);

    expect(created).toBe(true);
    expect([...touched].sort()).toEqual(['slide_decks', 'slide_figures', 'slide_slides']);
  });

  it('upserts on the (video_id, generator_version) unique key, status building', async () => {
    const { prisma, calls } = makeFakePrismaWithTx();
    await upsertDeck(OUTLINE, 'user-1', prisma);
    const upsert = calls.find((c) => c.op === 'upsert');
    expect(upsert?.model).toBe('slide_decks');
    const where = upsert?.args['where'] as Record<string, unknown>;
    expect(where['video_id_generator_version']).toEqual({
      video_id: 'synthvid001',
      generator_version: 'slidegen-v1',
    });
    const create = upsert?.args['create'] as Record<string, unknown>;
    expect(create['status']).toBe('building');
    expect(create['slide_count']).toBe(2);
  });

  it('replaceSlides detaches deck figures BEFORE deleting slides (FK order)', async () => {
    const { prisma, calls } = makeFakePrismaWithTx();
    await replaceSlides('deck-uuid-1', OUTLINE, prisma);
    const ops = calls.map((c) => `${c.model}.${c.op}`);
    expect(ops).toEqual([
      'slide_figures.updateMany',
      'slide_slides.deleteMany',
      'slide_slides.createMany',
    ]);
    const createMany = calls[2]!.args['data'] as Array<Record<string, unknown>>;
    expect(createMany).toHaveLength(2);
    expect(createMany[0]).toMatchObject({ deck_id: 'deck-uuid-1', position: 0, layout: 'cover' });
  });

  it('replaceFigures deletes then re-inserts deck figures', async () => {
    const { prisma, calls } = makeFakePrismaWithTx();
    await replaceFigures(
      'deck-uuid-1',
      [
        {
          cv_figure_id: 'f1',
          kind: 'equation',
          png_url: '/tmp/f1.png',
          extracted_latex: 'y = ax + b',
          extraction_conf: 0.4,
          verification_status: 'unverified',
        } as Parameters<typeof replaceFigures>[1][number],
      ],
      prisma
    );
    const ops = calls.map((c) => `${c.model}.${c.op}`);
    expect(ops).toEqual(['slide_figures.deleteMany', 'slide_figures.createMany']);
    const data = calls[1]!.args['data'] as Array<Record<string, unknown>>;
    expect(data[0]).toMatchObject({ kind: 'equation', verification_status: 'unverified' });
    // drift guard: these columns are NOT in the prod DDL yet — must stay out
    // of the INSERT until the raw-DDL follow-up lands.
    expect(data[0]).not.toHaveProperty('extracted_latex');
    expect(data[0]).not.toHaveProperty('bbox');
  });
});
