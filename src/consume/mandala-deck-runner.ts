/**
 * One-off integration runner (demo smoke): a prod mandala `book_json` FILE →
 * slidegen ④ consume → ⑥ OrchestrateResources → runOrchestrate(prod Sonnet) →
 * `.pptx`. ⑤ is stubbed ([]) → Path2 text-only. This is a reproducible BRIDGE
 * (not the deferred resolve/select/integrate pipeline) for the demo deck.
 *
 * Usage (Stage 3, prod-injected — secrets via CLI inline only, never .env):
 *   SLIDEGEN_MODE=prod OPENROUTER_API_KEY=… \
 *     npx tsx src/consume/mandala-deck-runner.ts <book_json_file> [out.pptx]
 *
 * Reads book_json from a FILE dumped read-only from prod — no DB at runtime, no
 * slide_* writes (pure .pptx artifact). fail-closed: an empty/bad book yields an
 * empty resources input; orchestrate never fabricates content.
 */
import fs from 'node:fs';
import path from 'node:path';

import { bookIndexToResources } from '@/consume/book-index-to-resources';
import { consumeBookIndex } from '@/consume/consume-book-index';
import { mapMandalaBookJson } from '@/consume/mandala-book-mapper';
import { stubSnapshotClient } from '@/consume/snapshot-client';
import { runOrchestrate, type RunnerConfig } from '@/deck/orchestrate-runner';

async function main(): Promise<void> {
  const bookFile = process.argv[2];
  if (!bookFile) {
    throw new Error('usage: mandala-deck-runner <book_json_file> [out.pptx]');
  }
  const bookJson: unknown = JSON.parse(fs.readFileSync(bookFile, 'utf8'));

  const book = mapMandalaBookJson(bookJson);
  const planned = await consumeBookIndex(book, stubSnapshotClient); // ⑤ stub → Path2 text-only
  const resources = bookIndexToResources(book, planned);

  const outPath = process.argv[3] ?? path.join('/tmp/slidegen-demo', book.mandala_id, 'deck.pptx');
  fs.mkdirSync(path.dirname(outPath), { recursive: true });

  const config: RunnerConfig = {
    SLIDEGEN_MODE: process.env['SLIDEGEN_MODE'] === 'prod' ? 'prod' : 'dev',
    OPENROUTER_API_KEY: process.env['OPENROUTER_API_KEY'],
  };

  const path1 = planned.filter((p) => p.path === 'path1_figure').length;
  const path2 = planned.filter((p) => p.path === 'path2_text').length;
  console.log(
    `[mandala-deck] "${book.center_goal}" — ${book.segments.length} segments ` +
      `(${path1} path1 / ${path2} path2) → ${outPath}`
  );

  const result = await runOrchestrate(resources, outPath, config, {});

  const bytes = fs.existsSync(outPath) ? fs.statSync(outPath).size : 0;
  console.log(`[mandala-deck] ok=${result.ok} attempts=${result.attempts} type=${result.type}`);
  console.log(`[mandala-deck] .pptx: ${outPath} (${bytes} bytes)`);
  if (!result.ok || bytes === 0) process.exitCode = 1;
}

void main().catch((err) => {
  console.error('[mandala-deck] FAILED:', err);
  process.exitCode = 1;
});
