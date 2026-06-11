/**
 * CLI entry point for insighta-slidegen.
 *
 * Usage:
 *   slidegen build --card  <card-uuid>   # resolve card → video, then build
 *   slidegen build --video <yt-video-id> # build from 11-char youtube id directly
 *
 * Pipeline sequence (each step writes a slide_jobs row):
 *   1. resolve    — resolveCardToVideo (if --card) or identity (if --video)
 *   2. fetch_v2   — fetchV2 with v2/pass/transcript_used gate
 *   3. cv_extract — extractFigures via Mac Mini CV service (figures + resources)
 *   4. plan       — planSlides (deterministic, no LLM)
 *   5. persist    — upsertDeck + replaceSlides + replaceFigures
 *   6. deck_build — runOrchestrate (PR-F3): chart-regen pre-step + vendored
 *                   orchestrate self-correction loop → .pptx artifact.
 *                   Minimal DB scope here (status only) — artifact upload and
 *                   full persistence land in PR-G.
 *
 * Hard rules:
 *   - No LLM API calls at any stage in dev (CLAUDE.md §LLM API 호출 금지).
 *     The deck runner REFUSES to start without an llm: prod constructs the
 *     OpenRouter closure from config (prod-only key); dev/test must inject a
 *     stub — so this CLI is fail-closed in dev (no silent API path exists).
 *   - config is loaded once at startup; never read process.env inline.
 *   - plan→approve→execute: logs SlideOutline, pauses unless --yes.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { parseArgs } from 'util';
import { PrismaClient } from '@prisma/client';
import { config } from '@/config';
import { resolveCardToVideo } from '@/resolve/card-to-video';
import { fetchV2 } from '@/fetch/v2-reader';
import { extractFigures } from '@/cv/cv-client';
import { runOrchestrate } from '@/deck/orchestrate-runner';
import { planSlides } from '@/plan/slide-planner';
import { upsertDeck, replaceSlides, replaceFigures, setDeckStatus } from '@/db/slide-repo';

async function main(): Promise<void> {
  const { values } = parseArgs({
    args: process.argv.slice(2),
    options: {
      card: { type: 'string' },
      video: { type: 'string' },
      yes: { type: 'boolean', default: false },
      lang: { type: 'string' },
    },
    allowPositionals: true,
  });

  const prisma = new PrismaClient();
  let deckId: string | undefined;

  try {
    // Step 1: resolve to youtube video id
    let youtubeVideoId: string;
    if (values.card !== undefined) {
      const resolved = await resolveCardToVideo(values.card, undefined, prisma);
      youtubeVideoId = resolved.youtubeVideoId;
    } else if (values.video !== undefined) {
      youtubeVideoId = values.video;
    } else {
      console.error('Error: provide --card <uuid> or --video <yt-id>');
      process.exit(1);
      return; // unreachable; narrows type for the compiler
    }

    // Step 2: fetch + gate v2 summary
    const summary = await fetchV2(youtubeVideoId, prisma);

    // Step 3: CV figure extraction
    // segments is an OBJECT { sections, atoms } (real v2 shape) — and both
    // the column and sections may be null/absent on transcript-less rows.
    // title/summary travel along as the Qwen select call's grounding text
    // (ADR 0002 D5: caption/summary = HINT for selection, never a keep/drop gate).
    const cvSections = (summary.segments?.sections ?? []).map((s, i) => ({
      index: i,
      from_sec: s.from_sec,
      to_sec: s.to_sec,
      title: s.title,
      summary: s.summary ?? undefined,
    }));
    const cvResult = await extractFigures({
      youtube_video_id: youtubeVideoId,
      sections: cvSections,
      mode: config.SLIDEGEN_MODE,
      title: summary.core.one_liner,
    });
    const figures = cvResult.figures;

    // Step 4: deterministic slide plan
    const outline = planSlides(summary, figures, values.lang);
    console.log(`[plan] ${outline.slides.length} slides, fingerprint=${outline.v2_fingerprint}`);

    // Step 5: persist
    const upsertResult = await upsertDeck(outline, undefined, prisma);
    deckId = upsertResult.deckId;
    await replaceSlides(deckId, outline, prisma);
    await replaceFigures(deckId, figures, prisma);

    // Step 6: deck build (PR-F3) — chart-regen pre-step, then the vendored
    // orchestrate FAIL→feedback→PASS loop on the CV resources bundle.
    // The artifact stays a local path for now; upload + slide_jobs/slide_decks
    // artifact persistence is PR-G scope.
    await setDeckStatus(deckId, 'building', null, prisma);
    const artifactPath = path.join(os.tmpdir(), 'slidegen-artifacts', deckId, 'deck.pptx');
    fs.mkdirSync(path.dirname(artifactPath), { recursive: true });
    // No injected llm here: in prod, runOrchestrate builds the OpenRouter
    // closure from config; in dev it throws BEFORE any vendored code runs
    // (LLM API ban — dev deck builds happen via the CC-console skill instead).
    const built = await runOrchestrate(cvResult.resources, artifactPath, config);
    if (!built.ok) {
      throw new Error(
        `deck build failed validation after ${built.attempts} attempts:\n${built.report ?? ''}`
      );
    }
    await setDeckStatus(deckId, 'done', null, prisma);
    console.log(
      `[done] deckId=${deckId} artifact=${artifactPath} ` +
        `(type=${built.type}, attempts=${built.attempts})`
    );
  } catch (err) {
    if (deckId !== undefined) {
      // Best-effort status update; ignore secondary errors
      await setDeckStatus(deckId, 'error', String(err), prisma).catch(() => undefined);
    }
    console.error('[error]', err);
    process.exit(1);
  } finally {
    await prisma.$disconnect();
  }
}

void main();
