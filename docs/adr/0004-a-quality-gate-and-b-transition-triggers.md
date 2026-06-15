# ADR 0004 — A-quality verification gate + B-transition triggers

> **🔀 Scope pivot (2026-06-15): single-video → deck is now an intermediate.** The
> project's output unit moved to **mandala (video-collection) → one deck**. This
> doc records the v1 single-video design, retained for history/reuse (per-video CV
> stages still apply). Consolidated archive:
> [`docs/archive/v1-single-video-per-deck.md`](../archive/v1-single-video-per-deck.md).

**Status**: Accepted
**Date**: 2026-06-10
**Extends**: [ADR 0003](./0003-mvp-pptx-output-and-prod-llm-extraction.md) — defines
the acceptance criteria for its §5 **PR-H** (dev-path E2E / A-quality check) and
the only sanctioned trigger for starting **"B"** work (DocLayout-YOLO
fine-tuning, UniMERNet deployment), which ADR 0003 scopes out of the MVP.
**Source**: architect-provided criteria (2026-06-10, team-shared). Thresholds
below are **initial values** — adjustable only with measurement evidence
(measurement-before-tuning, inherited rule).

---

## 1. Measurement set

**10 sample videos**, type-diverse with an **explainer/howto-heavy** mix and
**1–2 equation-bearing** videos (so the D3 confidence-gated equation path gets
exercised).

> PUBLIC-repo note: the concrete sample list contains real video ids and is
> therefore **never committed here** — it lives outside the repo (private
> tracking). Committed fixtures use synthetic ids only.

---

## 2. Automated gates (aggregated from `slide_jobs` / pipeline artifacts)

| # | Gate | Threshold (initial) | Notes |
|---|------|--------------------|-------|
| **G1** | `validate_deck` final PASS rate (self-correction loop included) | **≥ 9/10** | the harness's end-to-end success measure |
| **G2** | Self-correction attempts, mean per deck | **≤ 2.0** | persistently high attempts signal extraction-quality problems upstream, not validator strictness |
| **G3** | Figure `extraction_conf` low-confidence share | record with initial threshold **conf < 0.7** | **distribution report only — NOT a gate**; feeds the D3 (UniMERNet) decision |
| **G4** | Keyframe recall — manual cross-check on 2 of the 10 samples | **0 missed** major source slides | verifies the recall-first invariant (ADR 0003 D5); **G4 is also the PR-D acceptance criterion** |

**Queryability requirement (binds PR-G column design)**: these metrics must be
computable by plain admin SQL over `slide_*`. PR-G's raw SQL DDL must therefore
include at least:

- `slide_jobs.attempts int` (self-correction loop count for build/validate stages),
- `slide_jobs.failure_stage varchar` — failure attribution enum:
  `keyframe | detect | recognize | extract | build` (see §4),
- a per-deck validate-attempt count (on `slide_decks` or derivable from
  `slide_jobs` rows).

`slide_figures.extraction_conf` already exists and serves G3 as-is.

---

## 3. Human review (owner-scored, per sample)

| # | Item | Measure |
|---|------|---------|
| **H1** | Content accuracy | count of deck claims inconsistent with the video's claims |
| **H2** | Figure numeric accuracy | count of numeric errors in redrawn charts vs the source |
| **H3** | Overall score | owner's scoring scheme |

---

## 4. B-transition trigger (the core rule — prevents over-investing in B)

Every pipeline failure recorded during the measurement run **must be attributed
to a stage**:

```
keyframe   — wrong/missed frame selection (recall/coverage)
detect     — DocLayout-YOLO region box missing/wrong (WHERE)
recognize  — equation/chart/table content misread (Qwen3-VL OCR / struct-JSON)
extract    — resource-bundle → content-JSON quality (LLM extraction)
build      — recipe/template/validator-loop behavior
```

- **B work (YOLO fine-tuning, UniMERNet deployment) starts ONLY when measured
  failures concentrate in `detect` / `recognize`.**
- Failures concentrated in `extract` / `build` are **prompt/recipe fixes**, not
  model work — starting B on them is misdiagnosis.
- An unattributed "quality is bad" verdict is **not actionable evidence** for
  any decision.

---

## 5. Threshold governance

`9/10`, `≤ 2.0`, and `conf < 0.7` are starting points, not constants of nature.
Any adjustment ships **with the measurement that motivated it** (inherited
measurement-before-tuning rule). The G3 share is explicitly non-gating until
the first distribution is seen.
