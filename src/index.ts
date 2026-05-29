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
 *   3. cv_extract — extractFigures via Mac Mini CV service
 *   4. plan       — planSlides (deterministic, no LLM)
 *   5. persist    — upsertDeck + replaceSlides + replaceFigures
 *   6. build_slides — Python py/slides_build/deck_builder.py via child_process
 *   7. export_pdf   — Python py/slides_build/pdf_vector_compositor.py
 *
 * Hard rules:
 *   - No LLM API calls at any stage (CLAUDE.md §LLM API 호출 금지).
 *   - config is loaded once at startup; never read process.env inline.
 *   - plan→approve→execute: logs SlideOutline, pauses unless --yes.
 */
import { parseArgs } from "util";
import { PrismaClient } from "@prisma/client";
import { config } from "@/config";
import { resolveCardToVideo } from "@/resolve/card-to-video";
import { fetchV2 } from "@/fetch/v2-reader";
import { extractFigures } from "@/cv/cv-client";
import { planSlides } from "@/plan/slide-planner";
import {
  upsertDeck,
  replaceSlides,
  replaceFigures,
  setDeckStatus,
} from "@/db/slide-repo";

async function main(): Promise<void> {
  const { values } = parseArgs({
    args: process.argv.slice(2),
    options: {
      card:  { type: "string" },
      video: { type: "string" },
      yes:   { type: "boolean", default: false },
      lang:  { type: "string" },
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
      console.error("Error: provide --card <uuid> or --video <yt-id>");
      process.exit(1);
      return; // unreachable; narrows type for the compiler
    }

    // Step 2: fetch + gate v2 summary
    const summary = await fetchV2(youtubeVideoId, prisma);

    // Step 3: CV figure extraction
    const cvSections = (summary.segments ?? []).map((s, i) => ({
      index: i,
      from_sec: s.from_sec,
      to_sec: s.to_sec,
    }));
    const figures = await extractFigures({
      youtube_video_id: youtubeVideoId,
      sections: cvSections,
      mode: config.SLIDEGEN_MODE,
    });

    // Step 4: deterministic slide plan
    const outline = planSlides(summary, figures, values.lang);
    console.log(`[plan] ${outline.slides.length} slides, fingerprint=${outline.v2_fingerprint}`);

    // Step 5: persist
    const upsertResult = await upsertDeck(outline, undefined, prisma);
    deckId = upsertResult.deckId;
    await replaceSlides(deckId, outline, prisma);
    await replaceFigures(deckId, figures, prisma);

    // Steps 6-7: delegate to Python (deck_builder + pdf_vector_compositor)
    // TODO: spawn Python subprocess with deckId, update deck status on completion
    await setDeckStatus(deckId, "building", null, prisma);
    console.log(`[done] deckId=${deckId} — Python build step TODO`);

  } catch (err) {
    if (deckId !== undefined) {
      // Best-effort status update; ignore secondary errors
      await setDeckStatus(deckId, "error", String(err), prisma).catch(() => undefined);
    }
    console.error("[error]", err);
    process.exit(1);
  } finally {
    await prisma.$disconnect();
  }
}

main();
