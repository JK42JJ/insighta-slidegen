# Design — Mandala → Deck: Extraction & Assembly Architecture

**Status**: Design (direction; implementation deferred to per-stage PRs)
**Date**: 2026-06-16
**Decisions source**: [ADR 0006](../adr/0006-mandala-to-deck-aggregation.md) (output-unit pivot).
**Companion to**: [`mandala-to-deck-pipeline.md`](./mandala-to-deck-pipeline.md)
(this doc refines the *tooling* and *front-end* choices and adds the content model).

> **Goal restated.** One **mandala** (8 sectors × a variable, often large set of
> per-sector videos) → **one integrated deck draft**. The deck is built by
> **(1) consolidating the relevance-tagged summaries into a single mandala-level
> document**, then **(2) enriching it with figures regenerated from the source
> frames**, then **(3) a single placement LLM call** turning the document into a
> PPTX draft. The LLM is a placement helper only; it never invents object data and
> never builds the file itself (P1/P2, ADR 0003/0006).

---

## 1. Input structure (Insighta)

```
mandala
 ├─ sector 1 ─ videos[…]   (count is variable — NOT a constant)
 ├─ sector 2 ─ videos[…]
 └─ … 8 sectors
```

Each video carries a **detailed, caption-derived summary** split by **timestamp
window**, and **each window has a relevance %** expressing how related that window
is **to the mandala** (resolved this session: relevance is *per-window,
mandala-relative*, not a single per-video score).

**Implication.** Selection is already done by the data: we do **not** scan whole
videos to find slides. We go to the relevant windows. This deletes the old
single-video CV front-end (see §4).

---

## 2. Design principles

1. **Two pillars, text first.** Deck = a **text spine** (consolidated summaries) +
   a **figure enrichment layer** (CV). The text spine is the product and is built
   first; figures are added only where useful.
2. **Deterministic consolidation, single LLM call.** Merging/ranking/dedup across
   many videos is done with embeddings + code (deterministic). The LLM runs **once**
   at the end to produce the PPTX draft. Per-item LLM merging across a large video
   set would be a batch/bulk path and is banned (ADR 0003).
3. **Multi-user from the start.** This is a multi-user service, not a single-job
   tool. Heavy stages run behind an async queue with bounded workers; the
   extraction model runs as a warm (always-loaded) service.
4. **License-aware.** Prefer permissively licensed tools. AGPL components are
   acceptable for prototyping/measurement only and must be swapped before a
   closed-source commercial release (see §7).
5. **Write boundary.** Persistence writes to `slide_*` tables only; all Insighta
   tables are read-only sources.

---

## 3. Tooling decision & evaluation (measured this session)

### 3.1 MinerU evaluation (pipeline backend, CPU)

MinerU 3.3.1 `pipeline` backend = the integrated DocLayout-YOLO + UniMERNet +
PaddleOCR stack (no VLM). Run on a handful of real lecture slides
(`<sample lecture video>`), reading the actual output:

| Capability | Result |
|---|---|
| Body text OCR | ✅ clean (titles + labels) |
| Formula → LaTeX | ✅ correct on every tested slide |
| Table → structure | ✅ recovered as HTML with rowspan/colspan |
| Figure region detect + crop | ✅ region found and cropped |
| **Figure TYPE classification** | ❌ block is generic `image`; no diagram/chart/photo/lecturer label |
| Chart → data | ❌ cropped only; no axis/number extraction |
| Figure redraw / deck assembly | ❌ out of scope (MinerU extracts, it does not redraw or build slides) |

**Boundary:** MinerU pipeline can replace the hand-built per-stage extractors
(text/formula/table/figure-region). The **figure-type classification** and
**chart→data** gaps remain — that is the only part that still needs a VLM.

> Note: MinerU reads `pdf/image/docx/pptx/xlsx` as **input** and emits **Markdown +
> JSON**. It does **not** output PPTX. PPTX assembly is ours.

### 3.2 Division of labor

- **MinerU** = the cheap, deterministic extraction backbone (text, formula, table,
  figure region).
- **Qwen (VLM)** = handles only what MinerU cannot: **figure-type classification**
  and **chart→data** — and only on the **cropped regions** MinerU produced, never
  whole frames. Fewer + smaller inputs ⇒ faster, cheaper, less contention.

---

## 4. Front-end redesign (what the output-unit pivot deletes)

> **⚠ SUPERSEDED (2026-06-18).** The ffmpeg + OpenCV/SSIM "one clean frame per
> window" front-end below was measured to drop real slides (a topic-sized window
> holds many slides; one frame loses the rest). The figure front-end is now a
> **window-scoped V1 CV** chain (PySceneDetect → pHash, run inside each selected
> window) plus pre/post-MinerU gates. See the current SSOT:
> [`pipeline.md` §5](./pipeline.md). The table below is kept for history.

The old single-video front-end existed to *find slides in an unstructured video*.
With per-window relevance + timestamps, that job is gone.

| Old tool | Old purpose | New design | Why |
|---|---|---|---|
| PySceneDetect | scan whole video for transitions | **ffmpeg** (seek to window, grab frames) | location is known; no scan needed |
| pHash | mass near-dup removal | mostly dropped (a few frames only) | few targeted frames, not hundreds |
| pre-select heuristics | compress a large candidate pile | **OpenCV / SSIM** (pick the settled, sharp frame in a window) | the job shrinks to "pick one clean frame" |
| person/talking-head detector (`yolo11n`, AGPL) | drop lecturer frames | **byproduct of MinerU** (no content boxes ⇒ talking-head ⇒ drop) | reuse the extractor's result; removes an AGPL dependency |

The only residual front-end need: *given a target window, pick the cleanest slide
frame*. That is a light heuristic (frame-stability / sharpness), not a model. If
window timestamps turn out coarse, a window-scoped (not whole-video) mini scene
check can be added — to be decided by measurement.

---

## 5. Architecture (detailed pipeline)

```
INPUT ─ mandala_id
  │
══ FRONT-END: RESOLVE & SELECT ══
 [0] RESOLVE   mandala → 8 sectors → videos                 (BLOCKED: membership map)
       out: { sectors:[ {sector_id, videos:[vid…]} ×8 ] }
 [1] SELECT    per-window relevance %  ──< threshold──▶ trim / footnote
       out: per-sector windows [{vid, t0,t1, text, rel%}]   (source kept)
  │
  ├──────────────────────────────────────┐
  ▼                                       ▼  (only windows flagged needs_figure)
══ PILLAR 1: TEXT CONSOLIDATION ══     ══ PILLAR 2: FIGURE ENRICHMENT ══
 (spine · first · deterministic)        (later · only where useful)
 [2] EMBED   points → vectors            [F1] ffmpeg      window → N frames
     (BGE-M3 ✅MIT)                            (✅LGPL)
 [3] CLUSTER per sector by similarity     [F2] OpenCV/SSIM N → 1 clean frame
     dense (multi-video) → COMMON              (✅BSD)
     singleton/sparse   → DISTINCTIVE     [F3] MinerU (warm🔥)  text/LaTeX/
 [4] RANK & CAP                                table/figure-region
     common → merge; distinctive →             no content box ⇒ talking-head ⇒ DROP
     rank by rel%·importance, keep top-K   [F4] Qwen (queue⏳, crops only)
     (prevents distinctive-list explosion)     figure type + chart→data
 [5] CONSOLIDATE                                photo→exclude
     sector → { common:[merged],          [F5] redraw (P2: vector / ≥300dpi)
                distinctive:[{pt,source}] }     formula·table·chart→vector
     ★ consolidated_doc.json + preview.md        diagram = stub
  │                                       │  out: visual_objects[{vid,t,svg}]
  └──────────────────┬────────────────────┘
                     ▼
══ MERGE & DRAFT ══
 [6] INTEGRATE   join on (vid, window): consolidated_doc ⨝ visual_objects
       out: slides:[{sector, common/distinctive text, figures[], source}]
 [7] DRAFT       Sonnet, single injected harness call → PPTX draft (placement only)
 [8] BUILD       PPTX / Google Slides + true-vector PDF → write slide_* only
  │
OUTPUT ─ mandala deck (PPTX/Slides + vector PDF) + consolidated draft document
```

Legend: ✅ commercial-safe license · ⚠️ AGPL (F3 detectors — replace before
commercial) · 🔥 warm always-loaded service · ⏳ async queue + bounded workers ·
★ primary first deliverable.

---

## 6. Content model — "common core + distinctive" (the key requirement)

Across the many videos of a sector, the shared foundation overlaps but each video
adds something unique. The deck should **merge the common into one strong base and
surface the unique as value-add** — not naive dedup-and-discard.

```
sector N   (same shape for all 8)
 ├─ COMMON CORE      the shared "basics" said by multiple videos, merged into one
 └─ DISTINCTIVE      each video's unique point, kept separate, source-attributed
                     (when the video set is large, rank by relevance and keep top-K)
```

- **Splitting common vs distinctive = embedding clustering (deterministic).** Dense
  cluster ⇒ common; singleton ⇒ distinctive.
- **Wording the merge = the single end-of-pipeline LLM call**, never per-item.

Open tuning (measure on real data): the similarity threshold (too loose blurs
genuinely different points; too tight merges nothing) and the distinctive top-K cap.

---

## 7. Licensing summary (measured)

| Component | Role | License | Commercial closed-source SaaS |
|---|---|---|---|
| MinerU (framework) | orchestration | Apache-2.0 + thresholds (100M MAU / $20M mo) | ✅ free below thresholds |
| DocLayout-YOLO | layout detect (in MinerU) | **AGPL-3.0** (Ultralytics/YOLOv10 base) | ❌ |
| PDF-Extract-Kit (YOLOv8 MFD) | formula detect (in MinerU) | **AGPL-3.0** | ❌ |
| UniMERNet | formula → LaTeX | Apache-2.0 | ✅ |
| PaddleOCR | OCR + table | Apache-2.0 | ✅ |
| ffmpeg | frame grab | LGPL/GPL | ✅ |
| OpenCV / scikit-image | clean-frame pick | BSD/Apache | ✅ |
| BGE-M3 | embeddings | MIT | ✅ |
| Qwen (VLM) | figure classify / chart data | Apache-2.0 | ✅ |

**Key finding.** A permissive *framework* license does not save you: MinerU's
pipeline backend depends on **AGPL detection models** (layout + formula detection,
both Ultralytics-derived). For a closed-source commercial release these detectors
must be replaced with permissive alternatives, an Ultralytics enterprise license
purchased, or the service source opened. AGPL is fine for prototyping/measurement.

---

## 8. Cross-cutting

- **Multi-user**: F4 (Qwen) and [7] (LLM) run behind an async queue with bounded
  workers; F3 (MinerU) runs as a warm service (the measured cost was dominated by
  model load, not inference — load once, serve many).
- **LLM policy**: no bulk. Consolidation is deterministic/embedding-based; the LLM
  is a single injected harness call (dev: console / Write).
- **Figure quality gate (P2)**: figures are regenerated as vector or ≥300dpi, never
  pasted raw frames.
- **Write boundary**: `slide_*` tables only.

---

## 9. Build phases

| Phase | Work | Gate |
|---|---|---|
| 1 | Pillar 2 prototype F1–F4 on a single video's known timestamps (MinerU/Qwen e2e) | none (data-independent) |
| 2 | **Measure** on one real mandala: common overlap, distinctive count, relevance cut + similarity thresholds | needs sample mandala data |
| 3 | Pillar 1 consolidator [2–5] → [6] integrate → [7] draft (dev console) | Phase 2 |
| 4 | [F5] redraw (formula/table first) + figure merge | Phase 1/3 |
| 5 | Front-end [0/1] → full mandala e2e | membership map unblocked |
| 6 | Replace AGPL detectors (F3) with permissive alternatives | before commercial |

---

## 10. Open blockers & required measurements

- **BLOCKER — membership map** ([0] RESOLVE): the mandala→sector→video mapping lives
  in Insighta-core, not this repo's schema. Real-data mandala resolution is blocked
  until the data source is decided (DB introspection / colleague id list / synthetic
  fixtures).
- **Measure first** (Phase 2, highest value): is the common content genuinely
  overlapping? Does the distinctive list explode? What thresholds work? This single
  measurement decides whether consolidation is loose (list) or tight (semantic
  merge).
- **Measure** (front-end): timestamp precision — fine enough to pin a clean slide
  frame, or does a window-scoped mini scene check survive?
- **Risk** (defer until figures are added): text↔figure alignment — does the frame
  at a window actually show the figure the summary text refers to?

---

## 11. Summary

The deck's spine is a **deterministic, relevance-driven consolidation of the
mandala's summaries** using a **common-core + distinctive** content model; figures
are a **later enrichment layer** built with **MinerU (extraction) + Qwen
(figure-type/chart only, queued)**; the heavy single-video CV front-end is
**deleted** in favor of **ffmpeg + OpenCV/SSIM**; and a **single placement LLM call**
turns the consolidated document into a PPTX draft. The remaining gates are the
**membership-map blocker** and a **Phase-2 measurement** of overlap/thresholds, plus
the **AGPL detector replacement** required before a commercial release.
