# Design — Slidegen Pipeline (Total + CV), SSOT

**Status**: Design (consolidated direction; per-stage implementation status tagged inline)
**Date**: 2026-06-18 (rev. 2026-06-19 — figure front-end = restore V1 preselect, select-before-extract; supersedes standalone [P] + F4-lite)
**Scope**: Mandala (video collection) → one deck. Combines the *total* pipeline
and the *CV figure* sub-pipeline in one place to avoid the doc drift that left
[`mandala-deck-architecture.md`](./mandala-deck-architecture.md) §4/§5 stale.
**Decisions source**: [ADR 0006](../adr/0006-mandala-to-deck-aggregation.md) (output-unit pivot),
[ADR 0003](../adr/0003-mvp-pptx-output-and-prod-llm-extraction.md) (output/LLM),
[ADR 0002](../adr/0002-pipeline-v3-cpu-downsample-caption-context.md) (CV).

> Status legend: **[Built]** runnable · **[Designed]** specced, not built ·
> **[Stub]** code stub (throws/empty) · **[Deferred]** intentionally postponed ·
> **[Blocked]** waiting on data/grant · **[Upstream]** lives in the parent
> insighta repo, not here.
>
> Sample videos in this doc are referred to by neutral labels (no real YouTube
> ids — PUBLIC repo rule). "Sample A" = a talking-head vlog (a person on camera
> throughout, effectively no slides). "Sample B" = a slide-deck lecture (~49 min).

---

## 1. Philosophy (three rules)

1. **Text is the body, figures are enrichment.** Pillar 1 (text consolidation)
   comes first and carries the deck; Pillar 2 (figures) is added only where
   useful.
2. **Deterministic consolidation + a single LLM call.** Merging / ranking / dedup
   are embeddings + code. The LLM is invoked **once at the end** (placement).
   Per-item LLM = bulk = forbidden (ADR 0003).
3. **Selection precedes extraction.** The auto-generated rich-summary already
   carries `content_type`, per-section `relevance_pct`, and timestamps — so we do
   not run a whole-video "find the slides" CV front-end; we process only the
   selected windows.

---

## 2. Total pipeline [U] → [8]

```
[Upstream]  parent insighta repo (NOT this repo)
  [U] create mandala -> auto-search videos -> auto-generate v2 rich-summary
      (membership map + per-video summary are produced here)

------------------------------ THIS REPO ------------------------------
  [0] RESOLVE   mandala_id -> sector -> videos[]            [Blocked] membership read-grant
  [1] FETCH     per video: fetchV2 (read summary + v2/pass gate)   [Built]  src/fetch/v2-reader.ts
  [2] ROUTE     summary content_type + section cues               [Designed]
                  -> needs_figure per section (text-only vs +figure)
        |--------------------------------|
        v (all videos' text)             v (needs_figure sections only)
  [3] PILLAR 1  text consolidation (first)   [4] PILLAR 2  figure enrichment
       embed (BGE-M3) -> cluster ->            window-scoped CV sub-pipeline
       common-core / distinctive ->            (see section 5)
       rank/cap -> consolidated_doc            [Built] F1,F2,F3
       [Designed] (multi-video)                [Designed-port] S(preselect) · [Designed] F2g · [Deferred] F4 · [Stub] F5
        |---------------------|
                              v
  [5] INTEGRATE  consolidated_doc (text) (X) figures (by timestamp/section)
                 + cross-video figure dedup                  [Designed]
  [6] PLAN       buildNarrativePlan + planSlides -> ordered slides
                 (figure slots ONLY where figures exist)     [Stub] src/plan/narrative.ts, slide-planner.ts
  [7] DRAFT      single injected LLM (Sonnet, prod-only) = placement only   [Designed] (partly in orchestrate)
  [8] BUILD      pptx -> validate_deck -> persist slide_*     [Built] runOrchestrate, slide-repo
                 (true-vector PDF = deferred additive track)
```

### Per-stage status

| Stage | Role | Status | Where |
|---|---|---|---|
| [U] summary generation | mandala + search + rich-summary | **[Upstream]** | parent insighta |
| [0] resolve | mandala_id → videos | **[Blocked]** | needs membership read-grant |
| [1] fetch | read + gate v2 summary | **[Built]** | `src/fetch/v2-reader.ts` |
| [2] route | text-only vs +figure | **[Designed]** | (this session) |
| [3] Pillar 1 | text consolidation (multi-video) | **[Designed]** | `v2/pillar1_text/*` PLANs |
| [4] Pillar 2 | figure extraction | mixed (see §5) | `v2/pillar2_figure_cv/` |
| [5] integrate | join text + figures | **[Designed]** | — |
| [6] plan | narrative → slides | **[Stub]** (throws TODO) | `src/plan/narrative.ts`, `slide-planner.ts` |
| [7] draft | single placement LLM | **[Designed]** | partly `src/deck/orchestrate-runner.ts` |
| [8] build | pptx + validate + persist | **[Built]** | `src/deck/`, `src/db/slide-repo.ts` |

> Honest gap: [U][1][8] exist and [4] is largely built, but the **product body
> [6] (text spine) is a stub that throws** — so no deck is produced yet. The
> text spine is the priority, not more figure CV.

---

## 3. Routing — text-only vs +figure (the automation)

Decision unit = **window/section** (a video can be slides up front, Q&A later).
Cheapest signal first; the deck design is the final safety net.

1. **`content_type` coarse prior** (per video, free): vlog/interview/podcast →
   text-only side; lecture/tutorial/presentation → figure side; else ambiguous.
2. **Section text cues** (per section, free, deterministic): scan
   `summary` + `key_points` + atom text for visual references (graph/chart/table/
   equation/formula/diagram + LaTeX/number density) → `needs_figure`.
3. **CV probe** (ambiguous only): sample a few frames, run the F4-lite check,
   measure figure density → tiebreak. Reserved for the gray zone, not every video.
4. **Safety net** (already designed): the narrative slots figure slides *only*
   where CV produced real figures (§6 [6]). So a wrong "extract" decision costs
   only compute, and a wrong "text-only" decision loses figures but text still
   carries content → **routing only needs to be approximately right.**

> Note: the rich-summary atom `type` vocabulary is `fact | argument | tip |
> other` (see `src/types/slide-manifest.ts`) — there is **no** structured
> formula/table/figure flag. So routing is text-inference today. The cleanest
> long-term fix is for the **upstream** summary generator to emit a per-section
> `visual_aids` flag; then routing is exact and free.

---

## 4. Pillar 1 — text consolidation (the body)

Across all videos' summaries in the mandala:

```
section/atom points -> embed (BGE-M3) -> cluster (per sector)
  -> dense cluster   = COMMON CORE     (overlap merged)
  -> singleton       = DISTINCTIVE     (unique, source-attributed)
  -> rank & cap by relevance_pct -> consolidated_doc.json
```

Deterministic (no LLM). **[Designed]**, not built. Phase-2 measurement (does
common actually overlap? does distinctive explode? threshold?) needs real
mandala data and is the highest-value unknown — gated on [0].

---

## 5. Pillar 2 — CV figure sub-pipeline (window-scoped)

```
  [2] ROUTE  needs_figure=true sections {vid, t0, t1, rel%}
                         |
  === before MinerU (cheap dedup) =============================
  [F1] PySceneDetect   window-range decode (360p) -> scene multi-sample keyframes   [Built]
                         v
  [F2] pHash dedup     merge adjacent near-dups in-window -> distinct K            [Built]
                         v
  [F2g] global dedup   merge non-adjacent / cross-window dups + rel% cap           [Designed]
                         v
  === SELECT before extract (V1 preselect front-end, restored) ================
  [S]  preselect       DocLayout-YOLO content boxes (text/eq/table/diagram)        [Designed-port]
                       + COMBINE person gate (content-box-aware):
                         DROP if person-dominant (>=0.18) AND NOT strong-figure
                                AND no substantial text/eq/table (>=2% area)
                         KEEP if a real slide region (diagram >=0.80 OR text >=2%)
                       => only "explanation" frames survive; lecturers dropped,
                          portrait/diagram slides kept (the V1 combine rule)
  === MinerU (object extraction, on [S] survivors only) =======================
  [F3] MinerU (warm)   text / equation->LaTeX / table->HTML / figure-crop          [Built]
                       runs ONLY on selected frames -> fewer frames = lower cost
                       (+ content==0 -> empty-frame DROP, a residual byproduct)
                         v
  [F4]  Qwen figure-type + chart->data (precise)                                   [Deferred]
                         v
  [F5]  redraw         equations/tables/charts -> vector / >=300 dpi (no raw crop) [Stub]
                         v
            extractions.json  ->  [5] INTEGRATE
```

### Stage settings (ported verbatim from the validated v1 front-end; only resolution changed)

| Stage | Tool (license) | Key settings | Status |
|---|---|---|---|
| F1 | PySceneDetect (BSD) | threshold=8 · min_scene=2s · sample_step=2.5s · cap=10 · long_gap=20s · keyframe end−0.4s · **360p** · download-truncation guard | **[Built]** |
| F2 | pHash / OpenCV (BSD) | hamming=8 bits · 32→8 DCT (64-bit) · rep = last frame in group · group-index naming | **[Built]** |
| F2g | same pHash, all-pairs | non-adjacent global merge + rel%-weighted top-K cap | **[Designed]** |
| **S** (preselect) | DocLayout-YOLO (⚠ AGPL) + yolo11n COCO (local) | layout-only pass (~0.63 s/frame) · FIGURE_CONF_KEEP=0.80 · MIN_TEXT_AREA_FRAC=0.02 · PERSON_FRAC=0.18 + `has_strong_figure` portrait-trap guard · COMBINE rule | **[Designed-port]** — V1 `v1/ts_preselect/preselect.py`, validated |
| F3 | MinerU pipeline backend (⚠ bundles AGPL detectors) | warm = model loaded once · lang · runs on **[S] survivors only** | **[Built]** |
| ~~F4-lite~~ | — | **superseded by [S]** (selection is content-box-aware up front); keep at most as optional defense-in-depth | **[Superseded]** |
| ~~P~~ (standalone 0.50) | — | **superseded by [S]** — the V1 combine gate replaces the weak standalone person-fraction cut | **[Superseded]** |
| F4 | Qwen VLM (Apache) | figure type + chart→data | **[Deferred]** |
| F5 | matplotlib etc. | equations/tables/charts first | **[Stub]** |

### `runs/` layout (stage-first)

```
runs/<video_id>/
  F1_pyscenedetect/<window>/   scene multi-sample keyframes
  F2_phash/<window>/           distinct slides + report.json
  F3_mineru/<window>/<slide>/  MinerU md/json/images
  batch_summary.json           per-window overview (+ dropped_person)
  extractions.json             unified hand-off to [5]
```

---

## 6. Figure gate — two layers (select before extract)

| Gate | Position | Catches | Role / limit |
|---|---|---|---|
| `needs_figure` | entry (from summary) | whole talking-head / text-only sections | coarse net; a whole vlog ends here, never reaches CV |
| **[S]** preselect | before MinerU | lecturer / person-dominant frames with no slide content | authoritative keep/drop; keeps any frame with a real slide region |
| F3 `content==0` | MinerU byproduct | genuinely empty survivors | residual safety only; not the primary gate |

**Why the precise gate moved *before* MinerU.** The person-vs-slide decision
needs an "is there explanation content?" signal — and DocLayout-YOLO (the V1
preselect detector) already produces that signal (text/eq/table/diagram boxes)
in one cheap layout-only pass, *without* running MinerU. So the V1 COMBINE rule
— drop a person-dominant frame ONLY when it has no strong figure AND no
substantial text — runs up front. This is why a separate after-MinerU person
check (the former F4-lite) is no longer needed: selection already had the
content signal, so it is **superseded by [S]**.

**Empirical basis.** The V1 preselect front-end was validated on a lecture CV
regression run: diagram/figure slides were KEPT while talking-head / lecturer
frames were DROPPED by the combine gate (a low-confidence diagram slide is
rescued by the area-based strong-figure rule; a lecturer showing only an edge
caption is dropped). MinerU then runs only on the survivors → fewer frames,
lower cost (select-before-extract).

> Note: DocLayout-YOLO is AGPL (see §8 licensing); the same detector is bundled
> inside MinerU, so running it once up front for *selection* (layout-only) does
> not change the licensing posture — it is already AGPL via MinerU.

---

## 7. Build order (priority)

1. **[6] Text spine** (`buildNarrativePlan` + `planSlides`) — the body; resolves
   the throwing stubs. Deterministic, no LLM, no data blocker (testable with the
   v2 fixture). The figure-optional safety net comes for free.
2. **[2] Routing** — summary-driven text-only vs +figure (slots into the spine).
3. **[3] Pillar 1 consolidation** (multi-video) — needs real mandala data ([0]).
4. **[5] Integrate** + finish figures ([4]: restore the **[S] preselect**
   front-end (V1 `preselect.py` — DocLayout-YOLO content boxes + combine person
   gate, run before MinerU = select-before-extract) + F2g global dedup; [F5]
   redraw). [S] supersedes the standalone [P] cut and the after-MinerU F4-lite.
5. **[0] membership read-grant** (owner decision).

---

## 8. Guardrails (all stages)

- **No bulk LLM** — consolidation is embeddings/code; the LLM is one call at [7].
  `OPENROUTER_API_KEY` is prod-only.
- **Write boundary** — `slide_*` tables only; insighta tables are read-only.
- **Figure quality gate (ADR 0003 P2)** — figures are *regenerated* from
  extracted data (vector / ≥300 dpi); pasting a raw crop fails the gate.
- **Licensing** — MinerU's pipeline backend bundles AGPL detectors
  (DocLayout-YOLO, YOLOv8 MFD); replace before any closed-source commercial
  release. UniMERNet/PaddleOCR (Apache), PySceneDetect/OpenCV (BSD), BGE-M3
  (MIT), Qwen (Apache) are safe.
- **PUBLIC repo** — no credentials, prod IPs, real user/video ids (only synthetic
  ids in fixtures), or internal prod metrics.

---

## 9. Dev measurements (local CPU, sample-class videos — not prod metrics)

| Item | Value |
|---|---|
| PySceneDetect @360p, ~49-min video | ~75 s (decode-bound; threshold-independent) |
| MinerU cold → warm | ~40 s/frame → ~1.5 s/frame (≈26× — the lever is model-load-once, not GPU) |
| [P] calibration | Sample A (vlog) max person-fraction ≈ 0.68; Sample B (slides) max ≈ 0.35 → cut 0.50 drops 18/188 vlog frames, **0/269** slide frames |
| standalone [P] e2e on Sample A (pure vlog) | 188 distinct → P removes 18 → MinerU 170 → F3 drops 2 → **168 remain** → the standalone [P] (0.50, no content signal) is insufficient for a pure vlog. This motivates **restoring the V1 [S] preselect combine gate** (content-box-aware, drops the residual lecturers) + the `needs_figure` entry gate (a pure vlog should not reach CV at all) |

---

## 10. Doc map

| For | See |
|---|---|
| **This SSOT (total + CV, current)** | this file |
| Output-unit pivot decision | [ADR 0006](../adr/0006-mandala-to-deck-aggregation.md) (Proposed) |
| Mandala→deck architecture & content model | [`mandala-deck-architecture.md`](./mandala-deck-architecture.md) (⚠ its §4/§5 figure front-end is **superseded** by §5 here) |
| Two-branch execution plan | [`mandala-to-deck-pipeline.md`](./mandala-to-deck-pipeline.md) |
| CV pipeline ADR (CPU/caption-context) | [ADR 0002](../adr/0002-pipeline-v3-cpu-downsample-caption-context.md) |
| Output / LLM boundary | [ADR 0003](../adr/0003-mvp-pptx-output-and-prod-llm-extraction.md) |
| v1 single-video design (archived) | [`../archive/v1-single-video-per-deck.md`](../archive/v1-single-video-per-deck.md) |
