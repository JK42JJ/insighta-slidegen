/**
 * PR-H2 cv-client unit tests — submit → poll → result against a scripted
 * fetch (no network, no live service: LLM/vision API ban).
 */
import { describe, expect, it } from 'vitest';
import { CvExtractionError, extractFigures, isCvServiceHealthy } from '@/cv/cv-client';
import type { CvGenerateRequest } from '@/cv/cv-client';

const REQUEST: CvGenerateRequest = {
  youtube_video_id: 'synthvid001',
  sections: [{ index: 0, from_sec: 0, to_sec: 30, title: 'Synthetic section' }],
  mode: 'dev',
  title: 'Synthetic Talk',
};

const RESOURCES = {
  title: 'Synthetic Talk',
  transcript: 'synthetic transcript',
  segments: [],
  figureLabels: [],
  formulas: [],
  charts: [],
};

const WIRE_FIGURE = {
  cv_figure_id: 'fig-001',
  kind: 'chart',
  // Local crop path on purpose — the wire relaxation under test.
  png_url: '/tmp/slidegen/crops/fig-001.png',
  vector_pdf_url: null,
  vector_svg_url: null,
  caption: null,
  timestamp_sec: 12,
  extraction_conf: 0.55,
  bbox: { x: 1, y: 2, w: 30, h: 40 },
  verification_status: 'unverified',
};

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

/** Scripted fetch: pops one canned response per call, records the calls. */
function scriptedFetch(responses: Response[]): {
  fetchImpl: typeof fetch;
  calls: Array<{ url: string; init?: RequestInit }>;
} {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  const queue = [...responses];
  const fetchImpl = (async (url: unknown, init?: RequestInit) => {
    calls.push({ url: String(url), init });
    const next = queue.shift();
    if (!next) throw new Error('scripted fetch exhausted');
    return next;
  }) as typeof fetch;
  return { fetchImpl, calls };
}

const noSleep = async (): Promise<void> => undefined;

describe('extractFigures', () => {
  it('runs submit → poll → result and normalizes wire nulls', async () => {
    const { fetchImpl, calls } = scriptedFetch([
      jsonResponse({ job_id: 'job-1' }),
      jsonResponse({ job_id: 'job-1', status: 'running', progress_pct: 30, stage: 'keyframe' }),
      jsonResponse({ job_id: 'job-1', status: 'done', progress_pct: 100, stage: null }),
      jsonResponse({
        job_id: 'job-1',
        figures: [WIRE_FIGURE],
        keyframe_count: 12,
        resources: RESOURCES,
      }),
    ]);

    const result = await extractFigures(REQUEST, {
      fetchImpl,
      sleep: noSleep,
      serviceUrl: 'http://cv.test',
    });

    expect(result.job_id).toBe('job-1');
    expect(result.keyframe_count).toBe(12);
    expect(result.figures).toHaveLength(1);
    const figure = result.figures[0]!;
    expect(figure.png_url).toBe(WIRE_FIGURE.png_url);
    // explicit nulls → absent (FigureRef optional shape)
    expect(figure.caption).toBeUndefined();
    expect(figure.vector_pdf_url).toBeUndefined();
    expect(figure.extraction_conf).toBe(0.55);
    expect(result.resources.title).toBe('Synthetic Talk');

    expect(calls[0]!.url).toContain('/slides/generate');
    expect(calls[1]!.url).toContain('/slides/status?job_id=job-1');
    expect(calls[3]!.url).toContain('/slides/result?job_id=job-1');
  });

  it('maps a job error to CvExtractionError with the service failure_stage', async () => {
    const { fetchImpl } = scriptedFetch([
      jsonResponse({ job_id: 'job-2' }),
      jsonResponse({
        job_id: 'job-2',
        status: 'error',
        progress_pct: 0,
        error: 'select blew up',
        stage: 'select',
        failure_stage: 'select',
      }),
    ]);

    const error = await extractFigures(REQUEST, {
      fetchImpl,
      sleep: noSleep,
      serviceUrl: 'http://cv.test',
    }).catch((err: unknown) => err);
    expect(error).toBeInstanceOf(CvExtractionError);
    expect((error as CvExtractionError).stage).toBe('select');
    expect((error as CvExtractionError).message).toContain('select blew up');
  });

  it('degrades an off-domain failure_stage to the last-seen stage', async () => {
    const { fetchImpl } = scriptedFetch([
      jsonResponse({ job_id: 'job-3' }),
      jsonResponse({ job_id: 'job-3', status: 'running', progress_pct: 50, stage: 'select' }),
      jsonResponse({
        job_id: 'job-3',
        status: 'error',
        progress_pct: 0,
        error: 'bundle assembly failed',
        stage: null,
        failure_stage: 'not-a-stage',
      }),
    ]);

    const error = await extractFigures(REQUEST, {
      fetchImpl,
      sleep: noSleep,
      serviceUrl: 'http://cv.test',
    }).catch((err: unknown) => err);
    expect((error as CvExtractionError).stage).toBe('select');
  });

  it('attributes a timeout to the stage the job died in (PR-G convention)', async () => {
    const running = (): Response =>
      jsonResponse({ job_id: 'job-4', status: 'running', progress_pct: 10, stage: 'acquire' });
    const { fetchImpl } = scriptedFetch([jsonResponse({ job_id: 'job-4' }), running(), running()]);

    let clock = 0;
    const error = await extractFigures(REQUEST, {
      fetchImpl,
      sleep: noSleep,
      serviceUrl: 'http://cv.test',
      timeoutMs: 10,
      now: () => {
        clock += 6;
        return clock;
      },
    }).catch((err: unknown) => err);

    expect(error).toBeInstanceOf(CvExtractionError);
    expect((error as CvExtractionError).message).toContain('timeout');
    expect((error as CvExtractionError).stage).toBe('acquire');
  });

  it('retries the submit on transient 5xx, then succeeds', async () => {
    const { fetchImpl, calls } = scriptedFetch([
      jsonResponse({ detail: 'boom' }, 503),
      jsonResponse({ job_id: 'job-5' }),
      jsonResponse({ job_id: 'job-5', status: 'done', progress_pct: 100 }),
      jsonResponse({ job_id: 'job-5', figures: [], keyframe_count: 0, resources: RESOURCES }),
    ]);

    const result = await extractFigures(REQUEST, {
      fetchImpl,
      sleep: noSleep,
      serviceUrl: 'http://cv.test',
    });
    expect(result.job_id).toBe('job-5');
    expect(calls.filter((c) => c.url.includes('/slides/generate'))).toHaveLength(2);
  });

  it('fails immediately on a 4xx submit (no retry)', async () => {
    const { fetchImpl, calls } = scriptedFetch([jsonResponse({ detail: 'bad request' }, 400)]);
    const error = await extractFigures(REQUEST, {
      fetchImpl,
      sleep: noSleep,
      serviceUrl: 'http://cv.test',
    }).catch((err: unknown) => err);
    expect(error).toBeInstanceOf(CvExtractionError);
    expect((error as CvExtractionError).message).toContain('HTTP 400');
    expect(calls).toHaveLength(1);
  });
});

describe('isCvServiceHealthy', () => {
  it('true on 200, false on non-2xx, false on network error', async () => {
    const url = 'http://cv.test';
    await expect(
      isCvServiceHealthy((async () => jsonResponse({})) as typeof fetch, url)
    ).resolves.toBe(true);
    await expect(
      isCvServiceHealthy((async () => jsonResponse({}, 500)) as typeof fetch, url)
    ).resolves.toBe(false);
    await expect(
      isCvServiceHealthy(
        (async () => {
          throw new Error('ECONNREFUSED');
        }) as typeof fetch,
        url
      )
    ).resolves.toBe(false);
  });
});

describe('transient-network tolerance (live tailnet blip)', () => {
  it('retries a thrown network error on submit, then succeeds', async () => {
    let calls = 0;
    const responses = [
      jsonResponse({ job_id: 'job-n1' }),
      jsonResponse({ job_id: 'job-n1', status: 'done', progress_pct: 100 }),
      jsonResponse({ job_id: 'job-n1', figures: [], keyframe_count: 0, resources: RESOURCES }),
    ];
    const fetchImpl = (async () => {
      calls += 1;
      if (calls === 1) throw new TypeError('fetch failed');
      return responses.shift()!;
    }) as typeof fetch;

    const result = await extractFigures(REQUEST, {
      fetchImpl,
      sleep: noSleep,
      serviceUrl: 'http://cv.test',
    });
    expect(result.job_id).toBe('job-n1');
  });

  it('tolerates poll blips up to the tolerance, then keeps polling to done', async () => {
    let polls = 0;
    const fetchImpl = (async (url: unknown) => {
      const u = String(url);
      if (u.includes('/slides/generate')) return jsonResponse({ job_id: 'job-n2' });
      if (u.includes('/slides/status')) {
        polls += 1;
        if (polls <= 3) throw new TypeError('fetch failed');
        return jsonResponse({ job_id: 'job-n2', status: 'done', progress_pct: 100 });
      }
      return jsonResponse({
        job_id: 'job-n2',
        figures: [],
        keyframe_count: 0,
        resources: RESOURCES,
      });
    }) as typeof fetch;

    const result = await extractFigures(REQUEST, {
      fetchImpl,
      sleep: noSleep,
      serviceUrl: 'http://cv.test',
    });
    expect(result.job_id).toBe('job-n2');
    expect(polls).toBe(4);
  });

  it('gives up after sustained poll failure with the last-seen stage', async () => {
    const fetchImpl = (async (url: unknown) => {
      const u = String(url);
      if (u.includes('/slides/generate')) return jsonResponse({ job_id: 'job-n3' });
      throw new TypeError('fetch failed');
    }) as typeof fetch;

    const error = await extractFigures(REQUEST, {
      fetchImpl,
      sleep: noSleep,
      serviceUrl: 'http://cv.test',
    }).catch((err: unknown) => err);
    expect(error).toBeInstanceOf(CvExtractionError);
    expect((error as CvExtractionError).message).toContain('status failed 6x');
  });
});
