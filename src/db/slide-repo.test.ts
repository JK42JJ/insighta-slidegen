/**
 * slide_jobs recording tests (PR-H1).
 *
 * The fake PrismaClient is a Proxy that records every model property access —
 * the write-path rule test asserts the jobs functions touch ONLY slide_jobs
 * (slidegen-owned), never an insighta table.
 */
import { describe, expect, it } from 'vitest';
import type { PrismaClient } from '@prisma/client';
import { completeJob, createJob, enterJobStage, failJob } from '@/db/slide-repo';
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
