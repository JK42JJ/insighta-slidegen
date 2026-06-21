/**
 * §4 integration gate (demo critical path): a mandala book-index falls through
 * to a real .pptx.
 *
 * book-index → consumeBookIndex (stub ⑤ → 0 figures = Path2 text-only) →
 * bookIndexToResources → runOrchestrate(resources, STUB llm) → real vendored
 * deck/scripts/orchestrate.js → pptxgenjs → .pptx on disk.
 *
 * The llm is a SCRIPTED stub returning the vendored howto reference recipe — NO
 * OpenRouter, NO network (LLM API ban honored). The demo-day deck uses the
 * prod OpenRouter Sonnet harness (ADR 0003 D2) instead of this stub. Runs the
 * REAL vendored chain, so it needs deck/ deps + python3 (CI installs both).
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { afterAll, describe, expect, it } from 'vitest';

import type { BookIndex } from '@/consume/book-index';
import { bookIndexToResources } from '@/consume/book-index-to-resources';
import { consumeBookIndex } from '@/consume/consume-book-index';
import { stubSnapshotClient } from '@/consume/snapshot-client';
import { runOrchestrate, type LlmFn, type RunnerConfig } from '@/deck/orchestrate-runner';

import passContent from '../deck/fixtures/recipe-howto-pass.json';

const DEV_CONFIG: RunnerConfig = { SLIDEGEN_MODE: 'dev' };

const tempDirs: string[] = [];
afterAll(() => {
  for (const dir of tempDirs) fs.rmSync(dir, { recursive: true, force: true });
});

const demoBook: BookIndex = {
  mandala_id: 'demo',
  center_goal: '데모 만다라',
  segments: [
    {
      video_id: 'abcdefghijk',
      from_sec: 0,
      to_sec: 15,
      title: 'Intro',
      text: 'intro section text',
      relevance_pct: 80,
      has_visual_structure: false,
    },
    {
      video_id: 'abcdefghijk',
      from_sec: 15,
      to_sec: 30,
      title: 'Method',
      text: 'method section text',
      relevance_pct: 40,
      has_visual_structure: false,
    },
  ],
};

describe('⑥ e2e — book-index → OrchestrateResources → .pptx (stub llm, real vendored chain)', () => {
  it(
    'a mandala book-index produces a real .pptx (Path2 text-only, stub ⑤)',
    { timeout: 120_000 },
    async () => {
      const planned = await consumeBookIndex(demoBook, stubSnapshotClient); // all Path2, 0 figures
      const resources = bookIndexToResources(demoBook, planned);

      // Scripted stub: returns the vendored PASSing recipe — no OpenRouter.
      const stubLlm: LlmFn = () => Promise.resolve(JSON.stringify(passContent));

      const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'slidegen-bookindex-e2e-'));
      tempDirs.push(dir);
      const outPath = path.join(dir, 'deck.pptx');

      const result = await runOrchestrate(resources, outPath, DEV_CONFIG, {
        llm: stubLlm,
        classify: () => Promise.resolve({ type: 'howto' }),
      });

      expect(result.ok).toBe(true);
      expect(fs.existsSync(outPath)).toBe(true); // book-index → .pptx falls out
      expect(fs.statSync(outPath).size).toBeGreaterThan(0); // real bytes, not an empty file
    }
  );
});
