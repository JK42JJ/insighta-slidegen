# Archive — v1 design: single-video → one deck

**Status**: Archived / superseded scope (2026-06-15)
**Why this file exists**: the project's **output unit pivoted** from
*single-video → one deck* to **mandala (video-collection) → one deck**. This
document consolidates the v1 single-video design — scope, invariants, pipeline,
ADR decisions, output contract — into one place so the original scattered docs
can be read as one historical record. The originals are **kept** (each carries a
short scope-pivot banner pointing here); nothing was deleted.

> **Reuse vs retire.** The pivot is at the **output/aggregation level**, not the
> per-video CV internals. The per-video stages (frame extraction → region boxes →
> downsample → VLM select+classify → experts → figure regeneration) remain the
> building block a mandala-level deck is assembled from. What changes is the unit
> that maps to one `.pptx`: a *collection* of cards, not a single card. The new
> mandala→deck design is **TBD in a follow-up ADR (0006+)** and is not in this file.

---

## 1. Scope (v1, as it stood)

- **Card-level v1, "A baseline"**: one video card → one typed `.pptx` deck +
  Markdown appendix.
- **Mandala-level aggregation was explicitly deferred to v2** (PRD §scope;
  ADR 0003 scope) — that deferral is exactly what the 2026-06-15 pivot now pulls
  forward as the primary output unit.
- Training-free (no LoRA / no fine-tuning); zero-shot prompting only.
- DocLayout-YOLO fine-tuning and VLM LoRA are "B" work, gated behind measured
  A-quality gaps (ADR 0004 §4).

## 2. Design invariants (carried across every ADR — still apply per-video)

- **P1 — No agentic tool-calling by the VLM.** Deterministic code invokes
  YOLO / OCR / extractors; the VLM only answers content questions.
- **P2 — A snapshot is a data source, never the artifact.** Final figures are
  **regenerated** from extracted data (struct-JSON, LaTeX, OCR text); raw frame
  pixels are never pasted into the deck as the final figure.
- **P3 — The harness is the quality lever.** extract → build → validate →
  FAIL-feedback makes a mid-tier model converge to the same PASS bar; model
  strength is not the plan.
- **Vector-300dpi figure gate**: structures (tables/trees/flows/matrices) as
  native editable vector objects; data graphs as matplotlib PNG ≥ 300 dpi;
  equations as text/LaTeX-derived rendering — never a pasted raw frame.
- **LLM-API boundary**: bulk/offline dataset generation via API is banned in
  dev/test/CI; the prod service path may call the slide-content LLM
  (Claude Sonnet via OpenRouter) **only inside the deterministic harness**
  (injected, never agentic). `OPENROUTER_API_KEY` is prod-only, mode-gated.
- **DB**: writes go **only** to `slide_*` tables; all inherited Insighta tables
  are READ-ONLY. Schema changes ship as raw SQL DDL (no `prisma db push`).

## 3. The pipeline (single-video, stages 0–9)

```
0. Acquire     — Mac Mini residential-egress proxy: yt-dlp → S3 presigned (ADR 0003 D4)
1. Extract     — PySceneDetect (exact timecodes, interval filenames; recall-first over-extract)
2. Region box  — DocLayout-YOLO: WHERE only (boxes); class label NOT trusted
3. Downsample  — pHash near-dup merge (pre-YOLO) + CPU pre-select (post-YOLO, YOLO-box-gated)
4. Select+kind — Qwen3-VL ONE call/window (BGE-M3 chunks); WHAT authority; caption = context hint
5. Experts     — equation→OCR→LaTeX · text/table→PaddleOCR · chart/graph/diagram→Qwen3-VL struct-JSON · handwriting/photo→drop
6. Redraw      — regenerate figures as vector / ≥300dpi (never raw pixels)
7. Bundle      — deterministic resource bundle { title, transcript, segments, figureLabels, formulas, charts }
8. Slide-LLM   — harness only: content JSON (prod Sonnet via OpenRouter; dev stub/CC console)
9. Build       — buildRecipe (12–20 slides, no filler) → validate_deck v2 → FAIL feedback → .pptx + appendix.md
```

- Caption/transcript = **hint only, never keep/drop authority** (ADR 0002 D5).
- Time-provenance carried as an interval `[t_start, t_end]` through every stage
  (ADR 0002 D6), which is also what slices the per-crop caption.
- Deck-type fit: an arbitrary video is classified into one of **8 deck types**
  (explainer / howto / review / interview / news / listicle / story / talk) by a
  deterministic keyword heuristic, with an LLM tiebreak when confidence is low;
  each type has its own content schema (`deck/scripts/router.js`).

## 4. ADR decision record (single-video lineage)

| ADR | Date | Role | Key decisions (condensed) |
|---|---|---|---|
| **0001** — v1 frame selection + extraction | 2026-06-01 | *Superseded by 0002* | CLIP→local VLM (Qwen2.5-VL) routing (D1); DocLayout-YOLO boxes + UniMERNet equations (D4); synthesis stays in CC console, no script API (D5); vector-300dpi gate (D6); Google Slides + vector-PDF output (D7); local-first Apple Silicon (D9) |
| **0002** — pipeline v3 | 2026-06-09 | *Accepted CV design; amended by 0003* | PySceneDetect PRIMARY, Katna retired (D1); YOLO=WHERE / Qwen=WHAT (D2); CPU downsample before VLM (D3); select+classify merged into one Qwen3-VL call (D4); caption summary as context, no keep/drop (D5); interval time-provenance (D6); charts→Qwen3-VL struct-JSON (D7); prod=A100/RunPod async queue (D9) |
| **0003** — single-video MVP | 2026-06-10 | *Accepted; current output contract* | output = `.pptx` via vendored `insighta-visual-deck` chain (D1); prod slide-LLM inside harness, dev/test ban (D2); equation = Qwen3-VL OCR + conf gate, UniMERNet deferred (D3); acquire = residential-egress proxy (D4); recall-first keyframing invariant (D5); caption no-persist in `slide_*` (D6); vendor the deck chain (D7) |
| **0004** — A-quality gate + B triggers | 2026-06-10 | *Accepted; acceptance criteria* | 10-video measurement set; automated gates G1 validate PASS ≥9/10, G2 mean attempts ≤2.0, G3 conf<0.7 report-only, G4 0 missed slides; human H1 content / H2 numeric accuracy; **B work starts only when failures concentrate in detect/recognize** (not extract/build) |
| **0005** — resource-bundle section grouping | 2026-06-12 | *Proposed; doc-only* | additive `sections[]` view keyed on v2 section idx; frame↔section by interval-midpoint containment; orphan summaries/data kept (recall-first); boundary threshold measurement-gated; no raw caption / no frame pixels in the bundle |

Full text: `docs/adr/0001..0005`.

## 5. Output contract & deck chain (v1)

- **Output**: `.pptx` deck + `appendix.md`. Google Slides + true-vector PDF are a
  **deferred additive track** (`py/slides_build/` stubs retained).
- **Deck chain** (vendored, byte-stable, no TS rewrite — ADR 0003 D7): `deck/`
  CommonJS package — `router.js` (classify → extract prompt), `deck_recipes.js`
  / `deck_templates.js` / `slide_templates.js` (fixed layout), `orchestrate.js`
  (build → validate → FAIL feedback loop), `extract_resources.js`,
  `validate_deck.py` (structure / density / filler / overflow), `figures.py`.
- **The validate loop is a required pipeline stage**, not advisory: a deck that
  has not passed `validate_deck.py` does not leave the pipeline.

## 6. Source files this archive consolidates

| File | What it holds |
|---|---|
| `docs/adr/0001-pipeline-v1-frame-selection-and-extraction.md` | v1 VLM-routing decisions (superseded by 0002) |
| `docs/adr/0002-pipeline-v3-cpu-downsample-caption-context.md` | accepted CV pipeline v3 |
| `docs/adr/0003-mvp-pptx-output-and-prod-llm-extraction.md` | `.pptx` output + prod LLM boundary + acquire |
| `docs/adr/0004-a-quality-gate-and-b-transition-triggers.md` | A-quality gates + B triggers |
| `docs/adr/0005-resource-bundle-section-grouping.md` | section-grouped bundle (proposed) |
| `docs/architecture/slidegen-architecture.md` | component / run-location / `slide_*` tables / single-deck sequence |
| `docs/PRD.md` | full v1 spec (card-level; mandala deferred to v2) |
| `README.md` | stack / architecture / quick start (single-video) |

Implementation contracts still in force per-video (not banner-marked, linked for
completeness): `docs/CONTRACT_figure-manifest.md`,
`docs/CONTRACT_model-endpoints.md`, `docs/design/PR-A-figure-placement.md`,
`docs/design/roadmap2-diagram-renderer.md`, `deck/SKILL.md`.

---

## 7. What the mandala pivot changes (pointer only — design is TBD)

Out of scope for this archive; recorded here only so the boundary is explicit:

- **Unit**: one **mandala** (a curated collection of related video cards) → one
  deck, instead of one card → one deck.
- **Open questions for the follow-up ADR (0006+)**: how sections from N videos
  are merged/ordered into a single narrative; per-video vs cross-video dedup of
  figures; deck-type selection when the collection spans multiple genres;
  slide-budget allocation across videos; how the resource bundle (ADR 0005
  `sections[]`) extends to a multi-video grouping; reuse of the per-video CV
  output as the mandala builder's input.

These are **not decided here.** This file is the closed record of the
single-video design the pivot builds on top of.
