# PRD: insighta-slidegen

**Version**: 0.1 (design)
**Status**: Pre-implementation — schema + skeleton phase
**Scope**: Card-level deck generation (v1). Mandala-level aggregation is deferred to v2.

---

## Table of Contents

1. [Purpose, Background, and Goals](#1-purpose-background-and-goals)
2. [User Scenarios](#2-user-scenarios)
3. [System Architecture](#3-system-architecture)
4. [v2 Rich-Summary to Slide Mapping Spec](#4-v2-rich-summary-to-slide-mapping-spec)
5. [CV Pipeline Detail](#5-cv-pipeline-detail)
6. [Figure Extraction and Redraw](#6-figure-extraction-and-redraw)
7. [Output Generation](#7-output-generation)
8. [Data Model](#8-data-model)
9. [Claude Skill Spec](#9-claude-skill-spec)
10. [Hard Rule Inheritance Matrix](#10-hard-rule-inheritance-matrix)
11. [Quality and Evaluation](#11-quality-and-evaluation)
12. [Risks and Gaps](#12-risks-and-gaps)
13. [Roadmap](#13-roadmap)

---

## 1. Purpose, Background, and Goals

### 1.1 Background

Insighta captures video knowledge at the card level: each card represents a YouTube video that a user has saved into their mandala learning grid. The v2 rich-summary pipeline already extracts structured knowledge from each video — core argument, key concepts, timestamped sections, atoms (facts, definitions, formulas, tables, figures), and Q&A pairs.

That structured knowledge today lives only in the database. It is not portable. A user who wants to share, teach, review, or publish the distilled content of a video must reconstruct it manually.

insighta-slidegen closes that gap: it reads the v2 rich-summary for a given card, runs a computer-vision pipeline against the video frames, redraws any figures and charts to journal-grade vector quality, and assembles a ready-to-share slide deck in Google Slides format (plus a true-vector PDF track).

### 1.2 Goals

**Primary goal (v1)**: Given a single Insighta card (video), produce a verifiable, journal-grade slide deck that faithfully represents the video's v2 rich-summary without introducing data hallucinations.

**Secondary goal (v2, deferred)**: Aggregate across all cards in a mandala cell or entire mandala to produce a curriculum-level overview deck.

### 1.3 Non-Goals

- Re-summarizing or re-analyzing video content with an LLM (the v2 rich-summary is the sole content source).
- Storing raw video files or full transcript text beyond the in-memory processing window.
- Generating slide content that is not traceable to a specific v2 atom, section, or field.

### 1.4 Measurable Success Metrics

| Metric | Target | Gate |
|---|---|---|
| Raster PNG DPI | 300 dpi minimum | Hard gate: deck not published below threshold |
| Vector figure coverage | >= 80% of redrawn figures have both PNG-300dpi and SVG/PDF | Soft warning below 70% |
| Chart numeric MAE | <= 5% of axis range for extracted chart data points | Evaluated on golden set of 50 chart frames |
| Chart numeric MAPE | <= 8% across golden set | Evaluated on same set |
| Table cell F1 | >= 0.90 on golden set of 30 tables | Compared against manual ground truth |
| Formula LaTeX edit-distance | Normalized edit distance <= 0.15 on golden set of 40 formulas | pix2tex output vs manual LaTeX |
| Verification-status distribution | `verified` >= 60%, `unverified` <= 15%, `dropped` <= 25% of figure slots | Measured per deck, reported in manifest |
| Figure data-fidelity (human review) | >= 90% of `verified` figures rated "faithful" by a human reviewer | Spot-check on first 20 decks |
| End-to-end deck build latency (p95) | <= 8 minutes on Mac Mini M4 for a 60-minute video | Measured via job telemetry |

---

## 2. User Scenarios

### 2.1 Scenario A: Single Card to Deck

A user has saved a video card in their Insighta mandala. The v2 rich-summary for that card has been generated and is stored in `video_rich_summaries`. The user clicks "Generate Slides" on the card.

1. The orchestrator reads the card's `video_id` via the card-to-video join path.
2. It fetches the full v2 rich-summary record for that `video_id`.
3. It invokes the Claude skill, which plans the deck layout and issues tasks to the CV pipeline on the Mac Mini CV host.
4. The CV pipeline acquires frames (memory-only, never persisted), scores and selects them, extracts figures, and redraws them at 300 dpi.
5. Assets are uploaded to Supabase Storage (signed URLs).
6. The slide planner assembles the deck in Google Slides via the API.
7. The orchestrator writes the `slide_decks` and `slide_figures` records to the slidegen Supabase tables.
8. The user receives a link to the Google Slides deck and a download link for the vector PDF.

### 2.2 Scenario B: Regeneration After v2 Update

The v2 rich-summary for a card is updated (template version bump or quality re-run). The user or a cron job triggers a deck regeneration. The system detects the version mismatch via `generator_version` in `slide_decks` and rebuilds.

### 2.3 Scenario C: Mandala-Level Deck (Deferred — v2)

A user selects an entire mandala cell and requests a "curriculum overview" deck. The system aggregates the section-level content across all cards in the cell, deduplicate overlapping concepts via embedding similarity, and produces a multi-video narrative deck. Out of scope for v1.

---

## 3. System Architecture

### 3.1 Component Overview

```
┌────────────────────────────────────────────────────────────────────┐
│  Insighta App (prod / local dev)                                   │
│                                                                    │
│  ┌──────────────┐    card trigger    ┌──────────────────────────┐  │
│  │  Frontend    │ ─────────────────► │  slidegen orchestrator   │  │
│  │  (card UI)   │                   │  (Node.js / TypeScript)  │  │
│  └──────────────┘                   └───────────┬──────────────┘  │
│                                                 │                  │
│                                    ┌────────────▼─────────────┐   │
│                                    │  Claude skill             │   │
│                                    │  (deck planner / layout  │   │
│                                    │   + figure task issuer)   │   │
│                                    └────────────┬─────────────┘   │
└────────────────────────────────────────────────┼────────────────┘
                                                  │ HTTP (bearer)
                              ┌───────────────────▼──────────────────┐
                              │  Mac Mini CV host                     │
                              │  (Python / FastAPI)                   │
                              │                                       │
                              │  ┌──────────────────────────────────┐ │
                              │  │  yt-dlp (memory-only stream)     │ │
                              │  │  Katna frame extractor (~80)     │ │
                              │  │  CLIP image embeddings (512d)    │ │
                              │  │  BGE-M3 caption embeddings       │ │
                              │  │  pgvector cosine dedup (→~12)    │ │
                              │  │  YOLO layout detector (post-sel) │ │
                              │  │  PaddleOCR + Tesseract OCR        │ │
                              │  │  pix2tex formula extractor       │ │
                              │  │  matplotlib / plotly redrawn     │ │
                              │  │  LaTeX / dvisvgm formula render  │ │
                              │  │  native table renderer           │ │
                              │  └──────────────────────────────────┘ │
                              │                                       │
                              │  Outputs: figure-manifest JSON +      │
                              │  300dpi PNG + vector PDF/SVG assets   │
                              └──────────────────────┬───────────────┘
                                                     │ upload
                              ┌──────────────────────▼───────────────┐
                              │  Supabase Storage (signed URLs)       │
                              │  slidegen bucket                      │
                              └──────────────────────┬───────────────┘
                                                     │
                              ┌──────────────────────▼───────────────┐
                              │  Google Slides API                    │
                              │  batchUpdate + createImage            │
                              │  + Drive export → raster PDF          │
                              └──────────────────────────────────────┘
```

### 3.2 Run-Location Table

| Stage | Run Location | Notes |
|---|---|---|
| Card trigger / orchestration | Insighta prod server (or local dev) | TypeScript / Node.js |
| Claude skill (deck planning) | Insighta prod server | Calls Claude via prod-service path only |
| v2 rich-summary fetch | Insighta prod server | READ-ONLY Supabase query |
| yt-dlp video stream | Mac Mini CV host | Memory-only, never written to disk |
| Frame extraction — candidate pool (~80) | Mac Mini CV host | Katna (primary) + optional PySceneDetect reinforcement + forced grabs |
| Frame selection — semantic dedup (→~12) | Mac Mini CV host | CLIP 512d + BGE-M3 caption embeddings + pgvector cosine distance |
| YOLO layout detection | Mac Mini CV host | Local model, MPS-accelerated; runs on the ~12 selected frames only |
| CLIP image embedding | Mac Mini CV host | Local model, MPS-accelerated |
| BGE-M3 caption embedding | Mac Mini CV host | Local model, MPS-accelerated |
| OCR (PaddleOCR + Tesseract) | Mac Mini CV host | Local, no external API |
| pix2tex formula extraction | Mac Mini CV host | Local |
| Figure redraw (matplotlib/plotly/LaTeX) | Mac Mini CV host | Local renderers |
| Vision API fallback (0.55 <= c < 0.85) | Prod service path ONLY | Gemini Vision; never in dev/test |
| Figure-manifest + asset upload | Mac Mini CV host -> Supabase Storage | Bearer-auth upload |
| Google Slides assembly | Insighta prod server | OAuth user token; createImage from public URL |
| slide_* DB writes | Insighta prod server | Raw SQL DDL; own tables in Supabase |
| PDF (raster track) | Google Drive export | Via Slides API export endpoint |
| PDF (vector track) | Insighta prod server or Mac Mini | LaTeX/reportlab compositor |

---

## 4. v2 Rich-Summary to Slide Mapping Spec

### 4.1 Layout Taxonomy

| Layout ID | Source Fields | Description |
|---|---|---|
| `TITLE` | `core.one_liner`, `core.domain`, `core.depth_level`, `core.target_audience` | Opening slide; one slide per deck |
| `AGENDA` | `segments.sections[].title` (all) | Section list with relevance bars; one slide per deck |
| `CORE_ARGUMENT` | `analysis.core_argument`, `analysis.bias_signals`, `analysis.prerequisites` | Central thesis; one slide per deck |
| `SECTION_CONTENT` | `segments.sections[i]` | One slide per section; includes summary, key_points, attached figure(s) |
| `CONCEPT` | `analysis.key_concepts[]` | One slide per concept or grouped (max 4 per slide) |
| `ENTITY_INDEX` | `analysis.entities[]` | Reference index; grouped by entity type |
| `ACTIONABLES` | `analysis.actionables[]` | One slide; bulleted action list |
| `PREREQS_BIAS` | `analysis.prerequisites`, `analysis.bias_signals` | Combined caveat slide |
| `QA` | `lora.qa_pairs[]` | Selected Q&A pairs; grouped by `level` |
| `FIGURE_FULL` | Figures whose scoring places them as standalone content | Full-bleed figure slide; caption from atom or section context |

### 4.2 Deck Assembly Order

```
TITLE
AGENDA
CORE_ARGUMENT
SECTION_CONTENT × N          (ordered by sections[].from_sec ascending)
  └── FIGURE_FULL inserts     (inserted immediately after their parent SECTION_CONTENT)
CONCEPT × M                  (ordered by appearance order in key_concepts[])
ENTITY_INDEX
ACTIONABLES
PREREQS_BIAS
QA × K                       (ordered: foundational → intermediate → advanced)
```

### 4.3 Relevance Trimming and Ordering Rules

1. Sections with `relevance_pct < 20` are collapsed to a single bullet in the AGENDA slide and do not receive a SECTION_CONTENT slide (unless they contain a figure-type atom).
2. Sections are ordered by `from_sec` (ascending chronological), not by relevance_pct, to preserve narrative flow.
3. `key_concepts` retain all entries. If count > 12, they are split into multiple CONCEPT slides (max 4 per slide).
4. `lora.qa_pairs` are filtered to a maximum of 8 pairs. Selection priority: `level == "advanced"` first (max 3), then `level == "intermediate"` (max 3), then `level == "foundational"` (max 2).
5. If `mandala_fit.mandala_relevance_pct < 30`, a one-line note is appended to the CORE_ARGUMENT speaker notes indicating low mandala alignment.

### 4.4 Figure Attachment by Timestamp Window

Each `segments.sections[i]` has `from_sec` and `to_sec`. Figures extracted from the CV pipeline carry a `timestamp_sec` field. A figure is attached to section `i` if:

```
sections[i].from_sec <= figure.timestamp_sec < sections[i].to_sec
```

If a figure's timestamp falls outside all section windows (e.g., intro/outro), it is attached to the nearest section by `abs(timestamp_sec - section.from_sec)`.

Figures with `verification_status == "dropped"` are never attached. Figures with `verification_status == "unverified"` are attached with a visible "unverified" watermark on the slide.

---

## 5. CV Pipeline Detail

### 5.1 Video Acquisition

- Tool: `yt-dlp` with `--no-part --no-cache-dir`.
- Stream: piped directly to the frame extractor process via stdout; never written to disk.
- Format: best available video stream (no audio required); target resolution >= 720p.
- Memory budget: the stream buffer is bounded; frames are extracted and the buffer released.
- Duration source: `youtube_videos.duration_seconds` from the Insighta DB, used for per-section budget computation.

### 5.2 Frame Extraction and Selection (80 candidates → ~12 final frames)

> **STATUS: DRAFT HYPOTHESIS (v1).** The Katna → CLIP → BGE-M3(captions) → pgvector-distance → ~12 pipeline below is the **initial working hypothesis**, not the locked architecture. The effective frame-selection architecture will be **finalized through research** (model choice, dedup thresholds, caption-alignment method, whether Katna/PySceneDetect/other is the best extractor). Treat thresholds and tool choices here as starting points to validate, not commitments.

The goal is to produce approximately 12 final frames — one per distinct topic the video genuinely covers — each carrying its original source timestamp for click-to-jump navigation.

**Step 1 — Katna: candidate extraction (~80 frames)**

Katna scans the full video stream and generously grabs every point where the screen appears to have changed (~80 frames for a 50-minute video). This is deliberately not precise — the intent is to cast a wide net. The pool contains real key frames alongside junk: animation/transition effects and duplicate scenes captured at slightly different moments.

Katna is the primary candidate extractor. PySceneDetect may optionally be run in parallel as reinforcement (providing additional scene-boundary candidates to merge into the pool), but Katna's output is the driver.

Forced grabs are added on top: for each `key_points[].timestamp_sec` and each `atoms[].timestamp_sec` within a section window, the frame at that exact second is added to the candidate pool regardless of what Katna detected.

**Step 2 — CLIP: frames to semantic vectors**

Each of the ~80 candidate frames is passed through CLIP, producing a 512-dimensional semantic vector per frame. This allows the pipeline to compare frames by meaning: "these two are basically the same slide" (near-identical vectors) versus "this is completely different content" (distant vectors). The same slide captured at two slightly different moments yields near-identical CLIP vectors.

**Step 3 — BGE-M3: caption text to semantic vectors (parallel)**

Video frames alone are insufficient — the moment a speaker says "this is the most important part today" lives in the captions, not in the screen content. In parallel with Step 2, the video captions are chunked and embedded with **BGE-M3** (a dedicated text embedding model, ~1024-dimensional) to independently detect topic-change points in the transcript.

Note on models: BGE-M3 is a TEXT model (new to this stack). CLIP handles image content; BGE-M3 handles caption text. Their vector spaces are separate and complementary — they are not mixed or compared directly.

**Step 4 — Selection via pgvector distance (the core dedup step)**

Iterate over the ~80 candidate frames and judge each: "Is this frame semantically different enough from the frames already selected?" The mechanism is greedy cosine-distance deduplication:

1. Start with an empty selected set.
2. For each candidate frame (ordered by timestamp), compute its CLIP vector's cosine distance against every already-selected frame's CLIP vector using pgvector.
3. If the minimum distance to any already-selected frame is below the dedup threshold → discard (duplicate or near-duplicate scene).
4. If the frame is sufficiently new → add to the selected set.
5. Simultaneously align against the BGE-M3 caption topic-change points: a frame that is both visually new (CLIP distance passes) AND coincides with a detected caption topic change is treated as a definite key frame regardless of any tie-breaking criteria.

This compare-and-judge logic reuses the same embedding-distance approach as Insighta's card-filtering pipeline (similar vs. different by cosine distance). pgvector stores the accumulated selected-set vectors and performs the distance computation.

Frame type (from the downstream layout detection step applied to selected frames) and sharpness quality (Laplacian variance) may be used as tie-breakers when multiple candidates are near the dedup threshold, but distance-based deduplication is the primary selection mechanism.

**Result: ~12 final frames**

Duplicates and meaningless transitions are filtered out. The remaining frames correspond to the number of distinct topics the video genuinely covers (~12 for a typical 50–60 minute lecture). Each frame carries its source `timestamp_sec` for click-to-jump.

One-line summary: Katna grabs many, CLIP + BGE-M3 filter by meaning, pgvector compares, the remainder equals the real topic count.

---

## 6. Figure Extraction and Redraw

This stage runs on the ~12 frames selected by the pipeline in Section 5. Frame selection (Katna/CLIP/BGE-M3/pgvector, 80→12) is fully complete before this stage begins. YOLO layout detection and OCR are not part of the selection process; they operate here, on the already-selected frames, to classify and extract figure content for redrawing.

**YOLO layout detection** classifies each selected frame into one of:

| frame_type | Examples |
|---|---|
| `slide_text` | Text-heavy presentation slide |
| `figure_chart` | Bar, line, scatter, pie charts |
| `figure_diagram` | Architecture diagrams, flowcharts |
| `figure_table` | Tabular data |
| `figure_formula` | Mathematical expressions |
| `whiteboard` | Handwritten derivations |
| `face_talking` | Presenter face, no content |
| `transition` | Residual transition frame (rare after selection dedup) |
| `unknown` | Anything else |

Frames classified as `figure_chart`, `figure_table`, `figure_formula`, `figure_diagram`, or `whiteboard` proceed through the extraction and redraw sub-stages below.

### 6.1 OCR Layer

Two OCR engines run in parallel on figure-type frames:

- **PaddleOCR**: optimized for dense mixed-language text (including CJK).
- **Tesseract**: used as cross-check; configured for the source video's detected language.

Cross-check reconciliation: if both engines agree on a text block (normalized edit distance < 0.10), the block is marked `ocr_consensus = true`. Disagreements are flagged for the confidence gate.

### 6.2 Chart Axis-Calibration and Data Extraction

For `figure_chart` frames:

1. Detect axis lines via Hough transform.
2. Identify tick marks and labels (OCR).
3. Map pixel coordinates of data points / bar tops to axis-calibrated values.
4. Output: `{x_label, y_label, series[]{name, data_points[]{x, y}}}`.

Extraction confidence `c_chart` is the fraction of data point pixel-to-value mappings that pass internal consistency checks (monotonic axis, label parseable as number/date).

### 6.3 Table Structure Recognition (TSR)

For `figure_table` frames:

1. Detect grid lines; infer cell boundaries.
2. OCR each cell.
3. Output: `{headers[], rows[][], merged_cells[]}`.

Confidence `c_table` is cell-level F1 estimated via cross-OCR agreement on cell content.

### 6.4 Formula Extraction

For `figure_formula` and whiteboard-formula regions:

1. `pix2tex` produces a LaTeX string from the cropped region.
2. The LaTeX string is rendered back to an image via a lightweight TeX renderer.
3. SSIM between the re-rendered image and the original crop is computed as the self-check score.

`c_formula = SSIM(rendered, original_crop)`

### 6.5 Confidence Gate and Processing Paths

| Confidence | Path | Action |
|---|---|---|
| `c >= 0.85` | `verified` | Proceed to redraw; mark `verification_status = "verified"` |
| `0.55 <= c < 0.85` | `unverified` (dev) / `vision_fallback` (prod service) | Dev: apply super-res crop, mark `unverified`. Prod: send cropped region to vision API (Gemini Vision); reconcile with local extraction; mark `verified` if agreement, `unverified` otherwise |
| `c < 0.55` | `dropped` | Do not redraw; do not include in slide. Log reason. |

**Critical**: the vision API path is NEVER executed in dev/test environments. The `SLIDEGEN_ENV` environment variable gates this path; the default is `dev`.

### 6.6 Redraw Renderers

| Figure kind | Renderer | Output formats |
|---|---|---|
| Charts (bar, line, scatter, pie) | matplotlib (primary) or plotly (interactive export) | 300dpi PNG + vector PDF + SVG |
| Architecture / flow diagrams | mermaid (from LLM-structured diagram spec derived from OCR text) or graphviz | SVG + PDF |
| Tables | Python `tabulate` + LaTeX `booktabs` | 300dpi PNG + PDF |
| Mathematical formulas | LaTeX compilation + `dvisvgm` | SVG + PDF |
| Diagrams with mixed content | Combination of above, composited | 300dpi PNG + SVG (best-effort) |

All redrawn outputs target a minimum 300 dpi raster and a lossless vector representation where the figure type supports it.

### 6.7 Data Hallucination Mitigation

This is a first-class concern. The following rules are enforced:

1. **No redraw below tau_low**: if `c < 0.55`, the figure is dropped entirely rather than redrawn with potentially wrong data.
2. **Provenance fields**: every redrawn figure carries `source_atom_refs[]` linking back to the specific v2 atom or section, and `extraction_confidence` numeric value.
3. **Internal consistency gates**: for charts, the redrawn series values must fall within the extracted axis range. Any data point outside this range causes the figure to be downgraded to `unverified`.
4. **Human-in-loop publish gate**: a deck cannot be marked `status = "published"` without a human reviewer setting `human_approved = true` in `slide_decks`. The UI exposes a review queue for this.
5. **No LLM data interpolation**: the redraw renderer receives only the extracted structured data. It is not permitted to infer or fill missing data points.

---

## 7. Output Generation

### 7.1 Two-Track PDF

**Track 1 — Raster PDF**: exported from Google Slides via the Drive API export endpoint (`mimeType=application/pdf`). This is a raster PDF; text is not selectable.

**Track 2 — True-Vector PDF**: produced by a Python compositor (LaTeX or reportlab, TBD in implementation phase). The compositor:
- Reads the deck manifest.
- Lays out text from v2 fields using a configurable LaTeX class or reportlab stylesheet.
- Embeds the vector SVG/PDF figure assets directly (no rasterization).
- Produces a PDF in which text is selectable and figures are resolution-independent.

The two tracks are stored as separate assets in Supabase Storage and linked via `slide_decks.raster_pdf_url` and `slide_decks.vector_pdf_url`.

### 7.2 Google Slides Generation

- API: Google Slides `batchUpdate`.
- Image embedding: `createImage` request using a publicly accessible or short-lived signed URL pointing to the 300dpi PNG asset in Supabase Storage or Google Drive.
- Speaker notes: populated per slide from the corresponding v2 field (section summary, concept definition, Q&A answer).
- Presentation title: `core.one_liner`.
- Slide master / theme: a neutral, journal-style master with no brand elements.
- Drive export: after creation, the deck is exported to PDF via `drive.files.export`.

### 7.3 Asset Hosting

Assets (300dpi PNGs, SVGs, vector PDFs) are uploaded to the `slidegen` bucket in the project's Supabase Storage instance.

For the `createImage` call to Google Slides, the asset URL must be publicly accessible or the image must be base64-embedded. The implementation should prefer:
1. A short-lived (15-minute) signed URL from Supabase Storage — sufficient for the `batchUpdate` call.
2. Alternatively, upload the PNG to a temporary Google Drive folder associated with the user's OAuth session, and use the Drive URL directly.

**Copyright note**: redrawn figures derive from video content. The redraw step transforms raw video frames into new vector representations using extracted data. This is not the same as reproducing the original copyrighted frame. However, the system should include a standard attribution note in speaker notes: "Figure redrawn from video content. Original video: [video title] by [channel name]."

### 7.4 OAuth and Token Management

- Authentication: Google OAuth 2.0 (user's own account).
- Scopes required: `https://www.googleapis.com/auth/presentations`, `https://www.googleapis.com/auth/drive.file`.
- Token storage: user refresh token stored encrypted in the `slide_oauth_tokens` table. Access tokens are derived at runtime and never persisted.
- Token expiry: Google refresh tokens issued under a project in "Testing" status expire after 7 days. This is a known gap (see Risks and Gaps section). Before GA, the OAuth app must be verified.

---

## 8. Data Model

### 8.1 Tables Overview

All tables are in the `public` schema of the slidegen Supabase project (separate from the Insighta read-only DB). Schema changes are applied via raw SQL DDL files in `prisma/migrations/<feature>/NNN_*.sql`. `prisma db push` is never used (see Hard Rule inheritance below).

After any DDL `ALTER`, execute: `NOTIFY pgrst, 'reload schema'` followed by a PostgREST container restart (local) or Supabase Dashboard API reload (prod).

| Table | Purpose |
|---|---|
| `slide_decks` | One row per (video_id, generator_version) deck. Tracks status, asset URLs, human approval. |
| `slide_figures` | One row per extracted/redrawn figure. FK to `slide_decks`. Stores verification_status, confidence, asset URLs. |
| `slide_oauth_tokens` | Per-user Google OAuth refresh tokens, encrypted at rest. |
| `slide_job_log` | Append-only log of deck build jobs: stages, durations, error details. |

### 8.2 DDL Sketch

```sql
-- slide_decks: PK is (video_id, generator_version) to avoid one-deck-per-video trap
CREATE TABLE slide_decks (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id            VARCHAR(11)  NOT NULL,
    generator_version   VARCHAR(32)  NOT NULL,
    status              VARCHAR(32)  NOT NULL DEFAULT 'pending',
    human_approved      BOOLEAN      NOT NULL DEFAULT FALSE,
    slides_url          TEXT,
    raster_pdf_url      TEXT,
    vector_pdf_url      TEXT,
    figure_count        INTEGER,
    verified_count      INTEGER,
    unverified_count    INTEGER,
    dropped_count       INTEGER,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (video_id, generator_version)
);

-- slide_figures: one row per figure in the manifest
CREATE TABLE slide_figures (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deck_id             UUID         NOT NULL REFERENCES slide_decks(id) ON DELETE CASCADE,
    figure_id           VARCHAR(128) NOT NULL,
    kind                VARCHAR(32)  NOT NULL,   -- 'redrawn' | 'keyframe'
    frame_type          VARCHAR(32),
    timestamp_sec       FLOAT,
    extraction_confidence FLOAT,
    verification_status VARCHAR(32)  NOT NULL,   -- 'verified' | 'unverified' | 'dropped'
    png_300dpi_url      TEXT,
    vector_pdf_url      TEXT,
    vector_svg_url      TEXT,
    caption             TEXT,
    source_atom_refs    JSONB,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- slide_oauth_tokens: encrypted refresh tokens
CREATE TABLE slide_oauth_tokens (
    user_id             UUID         PRIMARY KEY,
    encrypted_token     TEXT         NOT NULL,
    scope               TEXT,
    expires_at          TIMESTAMPTZ,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- slide_job_log: append-only telemetry
CREATE TABLE slide_job_log (
    id                  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    deck_id             UUID         REFERENCES slide_decks(id),
    video_id            VARCHAR(11),
    stage               VARCHAR(64)  NOT NULL,
    status              VARCHAR(32)  NOT NULL,
    duration_ms         INTEGER,
    error_detail        JSONB,
    logged_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
```

---

## 9. Claude Skill Spec

The Claude skill (`slidegen-planner`) is invoked by the orchestrator after the v2 rich-summary is fetched and before the CV pipeline is dispatched. Its responsibilities:

| Responsibility | Input | Output |
|---|---|---|
| Deck layout planning | v2 rich-summary JSON | Ordered list of `{slide_index, layout_id, source_fields[], speaker_notes}` |
| Figure task issuance | Per-section atom list + section windows | Per-figure CV task spec: `{task_id, section_index, frame_window, atom_ref, figure_type_hint}` |
| Relevance trimming | `sections[].relevance_pct` | Boolean per section: include/collapse |
| Q&A selection | `lora.qa_pairs[]` | Selected pair indices and ordering |
| Caption generation | Atom text + section context | Short caption string (no hallucination of data values) |

**Hard constraints on the Claude skill**:
- Must not generate or modify any numeric data values (chart values, table cell values, formula coefficients). These must be passed through from the CV extraction pipeline unchanged.
- Must not call any external API during the planning phase.
- Operates entirely on the structured v2 JSON passed to it; no video access.

---

## 10. Hard Rule Inheritance Matrix

The following rules from the parent Insighta project are inherited unconditionally by insighta-slidegen.

| Rule | Applies To | Detail |
|---|---|---|
| LLM API ban (no Anthropic/OpenRouter outside prod-service) | All scripts, tests, dev tooling | The vision API fallback (Gemini Vision) runs only in the prod service path, gated by `SLIDEGEN_ENV != "dev"`. Any test that attempts to call a vision API will fail CI. |
| Plan -> Approve -> Execute | All side-effect operations (DB writes, API calls, file writes) | No automated action proceeds without an explicit orchestrator approval step. |
| `prisma db push` silent-fail ban | Schema migration | All DDL changes must be raw SQL files in `prisma/migrations/`. After DDL, `NOTIFY pgrst, 'reload schema'` is mandatory. Verification: `\d slide_*` on both local and prod before marking migration complete. |
| `.env` immutable | Environment configuration | `.env` files are never modified by scripts. Secrets are injected via CLI inlining or CI secrets. |
| PUBLIC repo essentials-only | Everything committed to this repo | No secret values, no real user IDs (use fixtures), no prod IP addresses in prose, no cost figures, no personal operational runbooks. |
| DB work order (local before prod) | All schema and data changes | Local DB first; prod only after local verified. |
| "Done" = Prod Verified | Completion criteria | Build pass is not done. Prod end-to-end verification is done. |

---

## 11. Quality and Evaluation

### 11.1 DPI Gate

Before a deck is assembled into Google Slides, every PNG asset in the figure manifest is checked for DPI metadata. Any asset below 300 dpi is rejected and the figure is downgraded to `unverified`.

Implementation: `PIL.Image.info["dpi"]` check in the asset upload step on the Mac Mini CV host.

### 11.2 Golden Set Evaluation

A golden evaluation set is maintained in `tests/golden/`. It contains:
- 50 chart frames with manually annotated data series (for MAE/MAPE evaluation).
- 30 table frames with manually annotated cell content (for F1 evaluation).
- 40 formula images with manually written LaTeX ground truth (for edit-distance evaluation).

Evaluation runs are executed offline (not in CI) and results are logged to `tests/golden/results/`.

### 11.3 Verification-Status Distribution Targets

After a deck build, the job log records:
- `verified_count`, `unverified_count`, `dropped_count`.

If `unverified_count / total_figures > 0.15`, the build is flagged for human review before the deck can be published.

### 11.4 Human-in-Loop Publish Gate

A deck reaches `status = "published"` only via an explicit `human_approved = true` write by an authorized user. The orchestrator exposes a review endpoint that presents each `unverified` figure alongside its source crop and the redrawn output. The reviewer can approve, reject, or re-trigger extraction on a per-figure basis.

---

## 12. Risks and Gaps

| Risk | Severity | Mitigation |
|---|---|---|
| Chart extraction reliability: pix2tex and axis-calibration produce low confidence for stylized or low-contrast charts. High `c < 0.55` rate drives up `dropped` figures. | High | Tune confidence thresholds on golden set; consider chart-specific fine-tuned model on Mac Mini as v1.1 improvement. |
| CLIP domain gap + BGE-M3 multilingual coverage: CLIP was trained predominantly on English-captioned images; performance on Korean or mixed-language lecture slides may degrade. BGE-M3 is a new model in this stack and its behavior on Korean technical captions has not yet been benchmarked. | Medium | Evaluate a multilingual-CLIP variant (e.g., M-CLIP) on a Korean-video golden set. Benchmark BGE-M3 topic-boundary precision on a sample of Korean lectures. Monitor dedup threshold sensitivity per language. |
| Vision API fallback cost: the `0.55 <= c < 0.85` bucket in prod triggers Gemini Vision calls. At scale, this could become expensive. | Medium | Monitor the unverified-rate distribution per video genre. Set a hard cap (e.g., max 5 vision API calls per deck) with remainder forced to `unverified`. |
| Formula OCR brittleness: pix2tex performs poorly on handwritten formulas and non-standard notation. | Medium | The SSIM self-check catches most failures and drops them. Consider a second pass with a different extractor in v1.1. |
| Redraw copyright: redrawing a chart does not automatically clear copyright. The underlying data may be copyrighted. | Medium | Include attribution in speaker notes. Add a legal disclaimer to the deck cover slide. Do not redistribute decks publicly without user confirmation. |
| Transcript-timestamp drift: `key_points[].timestamp_sec` values in v2 may drift from the actual video frame due to transcript alignment errors. This is now doubly relevant: forced-grab timestamps must align to real frames, and BGE-M3 caption topic-change points depend on accurate caption timing. | Medium | Add a +-3s search window around forced-grab timestamps. Log the actual frame timestamp vs the v2 timestamp. Validate BGE-M3 topic-change boundaries against section `from_sec`/`to_sec` windows. |
| OAuth token 7-day expiry (Testing status): users must re-authenticate frequently during development. | Low (dev) / Mitigated at GA | Document re-auth flow clearly. Before GA, submit OAuth app for verification. |
| v2 schema drift: if `video_rich_summaries` columns or JSON field names change, the fetch step silently misreads fields. | Medium | At fetch time, apply a Zod schema validation against the v2 contract. Fail loud (throw, log) on validation failure rather than proceeding with partial data. |
| Public-URL asset exposure: assets uploaded to Supabase Storage as public URLs are world-readable. | Medium | Use short-lived signed URLs (15-minute TTL) for the Google Slides `createImage` call. After deck creation, revoke or let the signed URL expire. The permanent asset URL is a private signed URL accessible only to the deck owner. |
| Copyright of video frames as keyframe (non-redrawn) assets: even a single keyframe from a copyrighted video embedded in a slide is a reproduction. | High | Keyframe slides are marked `kind = "keyframe"` in the manifest. The UI warns users before exporting a deck that contains keyframes. The vector PDF track never embeds keyframes. |
| One-deck-per-video PK trap: if `slide_decks` uses `video_id` as the sole PK, it is impossible to rebuild a deck after a v2 template version update. | Resolved | The PK is `(video_id, generator_version)` per the DDL above. |
| Google Slides cannot embed vector: `createImage` accepts raster only. The SVG/PDF assets are not embeddable via the Slides API. | By design / Resolved | This is why the two-track PDF exists. Vector assets are only in Track 2. Google Slides hosts the 300dpi PNG track; the vector PDF compositor produces Track 2 independently. |

---

## 13. Roadmap

### v1 — Card-Level Foundation (Current Phase)

| Milestone | Deliverable | Status |
|---|---|---|
| v1.0 | Design docs + DB schema DDL + project skeleton (TS orchestrator + Python service stubs) | In progress |
| v1.1 | CV pipeline: yt-dlp stream + Katna extraction + CLIP semantic vectors + BGE-M3 caption embeddings + pgvector dedup selection (local, Mac Mini) | Planned |
| v1.2 | Figure extraction: OCR + axis calibration + pix2tex + SSIM self-check | Planned |
| v1.3 | Figure redraw: matplotlib/plotly/LaTeX/booktabs renderers + confidence gate | Planned |
| v1.4 | Google Slides wiring: batchUpdate + createImage + OAuth + Drive export | Planned |
| v1.5 | Vector PDF compositor (LaTeX or reportlab) | Planned |
| v1.6 | Human-in-loop review UI + publish gate | Planned |
| v1.7 | Golden-set evaluation harness + CI integration | Planned |

### v2 — Mandala-Level Aggregation (Deferred)

- Multi-card concept deduplication via embedding similarity.
- Cross-video narrative deck assembly.
- Shared figure library across cards in the same mandala cell.
