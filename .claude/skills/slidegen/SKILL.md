---
name: slidegen
description: >
  Generate a Google Slides deck + true-vector PDF from a card's v2 rich-summary.
  Deterministic pipeline (no LLM API calls): v2 gate → CV frame extraction →
  slide plan → Google Slides build → PDF export. Write path: slide_* tables only.
  insighta Supabase is READ-ONLY from this skill.
---

# slidegen — Slide Deck Generator Skill

## Purpose

Convert an Insighta card (or bare YouTube video id) into a shareable presentation:
- A Google Slides deck with layout-typed slides derived from the v2 rich-summary structure.
- A raster PDF (300 DPI) and a true-vector PDF (SVG/ReportLab compositor).
- CV-extracted figures redrawn as vector assets where possible.

No LLM API calls at any stage (CLAUDE.md §LLM API 호출 금지).
Deterministic plan from v2 data structure only.

## Trigger

```
/slidegen --card <card-uuid>
/slidegen --video <youtube-video-id-11char>
```

Optional flags:
- `--lang <ko|en>` — override output language (default: summary.source_language ?? "ko")
- `--yes`          — skip interactive plan approval, execute immediately

## Inputs

| Input | Source | Required |
|-------|--------|----------|
| Card UUID or YouTube video id | CLI arg | One of the two |
| v2 rich-summary row | insighta Supabase (READ-ONLY) | Required — gate fails if v1/pending |
| CV figures | Mac Mini slidegen-service :8077 | Required in prod; placeholder in dev |
| Google OAuth token | ~/.cache/insighta-slidegen/google_token.json | Required for Slides build |

## Execution

### Phase 0: Pre-flight checks

```bash
# Verify CV service is up (dev: localhost:8077, prod: Tailscale)
curl -s $SLIDEGEN_CV_SERVICE_URL/health | jq .

# Verify insighta DB reachable (read-only SELECT)
psql "$DIRECT_URL" -c "SELECT 1 FROM video_rich_summaries LIMIT 1"
```

If CV service is unreachable in dev mode: warn user, offer to continue with placeholder figures.
Hard-stop if DB is unreachable.

### Phase 1: Resolve

If `--card`: call `resolveCardToVideo(cardId)` in `src/resolve/card-to-video.ts`.
Join path: user_video_states.video_id (UUID) → youtube_videos.youtube_video_id (VARCHAR 11).

If `--video`: use the provided 11-char id directly (verify length == 11).

### Phase 2: Fetch v2 (fail-loud gate)

Call `fetchV2(youtubeVideoId)` in `src/fetch/v2-reader.ts`.

Gate — ALL conditions must be true or throw `V2_GATE_FAILED`:
- `template_version = 'v2'`
- `quality_flag = 'pass'`
- `transcript_used = true`

On gate failure: write `status='gate_failed'` to slide_jobs, surface human-readable error.

### Phase 3: CV Figure Extraction

Call `extractFigures(request)` in `src/cv/cv-client.ts`:
1. POST `/slides/generate` to Mac Mini service with section time ranges from `segments[]`.
2. Poll `/slides/status?job_id=...` every 2s (timeout 300s).
3. GET `/slides/result?job_id=...` → `FigureRef[]`.

Dev mode: CV service returns placeholder figures (no vision API).
Prod mode: CV service runs full pipeline with optional vision API fallback (Gemini).

### Phase 4: Deterministic Slide Plan (plan → approve → execute)

Call `planSlides(summary, figures, lang)` in `src/plan/slide-planner.ts`.

Narrative arc (deterministic, from templates.ts + narrative.ts):
1. cover slide
2. timeline (if segments.length >= 3)
3. Per segment: section_intro → key_points → figure_slot(s)
4. QA pairs (max 4)
5. summary slide
6. blank("low_relevance") if mandala_relevance_pct < 30

**plan → approve → execute rule**: Log the SlideOutline JSON to console.
Unless `--yes` was passed, prompt user for confirmation before proceeding.

### Phase 5: Persist

Write to slide_* tables (NOT insighta tables):
1. `upsertDeck(outline)` — upsert on (video_id, generator_version), status='building'
2. `replaceSlides(deckId, outline)` — delete + re-insert slide_slides
3. `replaceFigures(deckId, figures)` — delete + re-insert slide_figures

Write slide_jobs rows at each stage transition.

### Phase 6: Google Slides Build

Spawn Python subprocess:
```bash
python -m slides_build.deck_builder --deck-id <deckId>
```

`deck_builder.py` calls the Google Slides API batchUpdate, returns JSON with
`google_slides_id` and `google_slides_url`.

Update `slide_decks.google_slides_id` and `google_slides_url`.

### Phase 7: PDF Export

Spawn Python subprocess:
```bash
python -m slides_build.pdf_vector_compositor --deck-id <deckId>
# For raster track:
python -m slides_build.pdf_vector_compositor --deck-id <deckId> --raster
```

Returns `{"pdf_url": ..., "vector_pdf_url": ...}`.
Update `slide_decks.pdf_url` and `vector_pdf_url`.

### Phase 8: Return

Update `slide_decks.status='done'`.

Return to user:
```
[slidegen] Done.
  Google Slides: https://docs.google.com/presentation/d/<id>
  Vector PDF:    https://<supabase-storage-url>/decks/<deck_id>/deck-vector.pdf
  Raster PDF:    https://<supabase-storage-url>/decks/<deck_id>/deck.pdf
  slide_decks.id: <uuid>
```

## Blast Radius

| Target | Access | Notes |
|--------|--------|-------|
| insighta Supabase | READ-ONLY | SELECT on video_rich_summaries, youtube_videos, video_captions |
| slide_* tables (slidegen Supabase) | READ + WRITE | upsert/delete on slide_decks, slide_slides, slide_figures, slide_keyframes, slide_jobs |
| Google Slides / Drive | WRITE | Creates new presentation; never modifies existing ones |
| Supabase Storage | WRITE | Uploads PNG/SVG/PDF to SUPABASE_STORAGE_BUCKET |
| Mac Mini CV service | POST :8077 | Downloads YouTube video; CV extraction |
| LLM API (Anthropic/OpenRouter) | NONE | Hard-disabled per CLAUDE.md §LLM API 호출 금지 |
| .env files | NONE | Config via src/config/index.ts zod schema only |
| prisma db push | NONE | DDL applied via raw SQL in prisma/migrations/slidegen-init/ |

## Error Handling

| Stage | Error | Action |
|-------|-------|--------|
| resolve | card not found | throw, write slide_jobs stage=resolve status=error |
| fetch_v2 | gate failed (v1/pending/no_transcript) | throw V2_GATE_FAILED, surface to user |
| cv_extract | service unreachable | dev: continue with placeholder; prod: abort |
| build_slides | Google API error | write error to slide_decks.error, status=error |
| export_pdf | reportlab/latex error | log warning, skip vector track, write raster-only |

## Hard Rule References

- No LLM API calls (CLAUDE.md §LLM API 호출 금지, 2026-04-15 재정 손실 사고)
- No .env modification (CLAUDE.md §.env 불변)
- No prisma db push (CLAUDE.md §prisma db push Silent Fail 대응)
- Local-first then prod for DDL (CLAUDE.md §DB Work Order)
- plan → approve → execute before any write (CLAUDE.md §계획 → 승인 → 실행)

## Related Artifacts

| Artifact | Path |
|----------|------|
| TS orchestrator entry | `src/index.ts` |
| Config (zod) | `src/config/index.ts` |
| Types | `src/types/slide-manifest.ts` |
| Card resolver | `src/resolve/card-to-video.ts` |
| V2 reader | `src/fetch/v2-reader.ts` |
| Slide planner | `src/plan/slide-planner.ts` |
| DB repo | `src/db/slide-repo.ts` |
| CV client | `src/cv/cv-client.ts` |
| Google Slides build | `py/slides_build/deck_builder.py` |
| True-vector PDF | `py/slides_build/pdf_vector_compositor.py` |
| CV microservice | `mac-mini/slidegen-service/app.py` |
| Prisma schema | `prisma/schema.prisma` |
| DDL migration | `prisma/migrations/slidegen-init/001_create_slide_tables.sql` |
