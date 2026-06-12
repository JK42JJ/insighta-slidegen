# ADR 0005 — Resource-bundle section grouping (additive section view)

**Status**: Proposed (design direction only — no code/schema change in this ADR)
**Date**: 2026-06-12
**Extends**: [ADR 0003](./0003-mvp-pptx-output-and-prod-llm-extraction.md) §3 stage 7 (resource
bundle) and D7 (vendored deck chain, byte-stable). **Builds on the already-shipped
flat bundle** `mac-mini/slidegen-service/bundle.py:assemble_resources` (landed in
PR-F3).
**Depends on**: [ADR 0004](./0004-a-quality-gate-and-b-transition-triggers.md) §4
(stage failure attribution — `extract`) and §5 (threshold governance —
measurement-before-tuning) for the boundary-attribution threshold (D4 below).

---

## 1. Context

Stage 7 of the MVP pipeline (ADR 0003 §3) is **already implemented and shipped**:
`assemble_resources()` produces the resource bundle that the vendored
`deck/scripts/orchestrate.js` consumes **unmodified** (ADR 0003 D7). Its shape is
**flat** — exactly the six keys the vendored consumer expects:

```
{ title, transcript, segments, figureLabels, formulas, charts }
```

In this shipped design:

- `segments` is the v2 section array, **passed through verbatim**.
- `figureLabels`, `formulas`, `charts` are **flat arrays** (not grouped by section).
- A figure attaches to a frame by `_nearest_snapshot` — the selected frame
  **nearest in time** (`abs(frame.ts − figure.ts)`), with **no notion of which
  v2 section the figure belongs to**.

This ADR records a forward design: make the bundle's **organising unit the v2
section**, so the slide-content LLM (ADR 0003 D2 harness) receives resources
**grouped per section** rather than as flat pools it must re-associate itself.
Crucially, this is positioned as an **additive view**, not a replacement of the
flat shape — see §3.

### Preconditions (re-verified 2026-06-12 — both already satisfied)

Two dependencies were historically tracked as blockers for any bundle-schema
work. Re-reading the repo on fresh `main` shows **both have landed**:

- **v2 mirror (PR-B)** — *DONE* (PR #17, `aadeeae`). `src/types/slide-manifest.ts`
  carries the correct v2 shape: `segments = { sections[], atoms[] }`, with each
  section exposing `idx`, `from_sec`, `to_sec`, `title`, `summary`,
  `relevance_pct`, `key_points[]`. The bundle's section fields can therefore be
  **confirmed now** against the real shape (no "defer to PR-B").
- **Frame time-provenance port** — *DONE*. `mac-mini/slidegen-service/frames.py`
  emits the ADR 0002 D6 interval (`t_start`/`t_end`, filename
  `keyframe_{idx}_[MMmSSs-MMmSSs].jpeg`), so the frame→section time match (D2b
  below) operates on repo code, not scratch-only.

The **real precondition** for the section view is therefore not a missing type
or a missing time field — it is the additive implementation in `bundle.py`
itself, shipped in a separate PR (§7).

---

## 2. The two pairings the code completes before the LLM sees the bundle

The section view exists so the **LLM only places content, never re-derives
associations**. Deterministic code (ADR 0003 P1/P3) performs both pairings up
front:

### D2a — summary ↔ section (by index, no time math)
Each v2 section's narrative (`summary` / `key_points`) is attributed to that
section by its `idx`. This is a direct structural join; no timestamp arithmetic.

### D2b — frame / extracted-data ↔ section (by frame-interval midpoint)
Each selected frame carries `[t_start, t_end]` (ADR 0002 D6). Its **midpoint**
`(t_start + t_end) / 2` is tested for containment in a section's
`[from_sec, to_sec]`; the frame (and its extracted formulas/charts) is attributed
to the section whose range contains the midpoint.

- **Midpoint, not overlap-length.** Comparing overlap durations across sections
  is more complex and produces boundary double-counting (a frame straddling a cut
  lands in two sections). The midpoint is a single point → exactly one section,
  no double-count, trivially deterministic.
- **One frame = one slide candidate** (fixed), which resolves the frame↔section
  relation to many-to-one and keeps the per-section figure lists clean.
- This **supersedes `_nearest_snapshot`'s nearest-in-time attribution** *for the
  additive section view*. The flat `figureLabels/formulas/charts` arrays and
  their existing `snapshot` back-references are unchanged (§3).

---

## 3. Decision D1 — additive `sections[]`, flat keys byte-stable

`bundle.py` gains an **additive** top-level field; the six flat keys are
**unchanged** so `orchestrate.js` keeps consuming the bundle byte-for-byte
(ADR 0003 D7 — no vendored rewrite):

```
{
  title, transcript, segments, figureLabels, formulas, charts,   // unchanged (D7)
  deck_meta:  { title, channel, duration, summary_digest },      // additive
  sections: [                                                     // additive
    { section_ref,            // v2 section idx
      summary_excerpt,        // section narrative (refined; NOT raw caption — §5)
      figureLabels[],         // frames whose midpoint ∈ [from_sec,to_sec]
      formulas[],             // mode-C LaTeX for those frames
      charts[] },             // mode-B struct-JSON for those frames
    ...
  ]
}
```

The `sections[]` view is a **regrouping of the same data already in the flat
arrays** (same entries, indexed by section), not new content. A consumer that
ignores `sections[]` (today's `orchestrate.js`) is unaffected; a consumer that
reads it gets the per-section organisation for free. The ADR therefore neither
forks the contract nor touches the vendored chain.

---

## 4. Decision D3 — orphan handling (recall-first; never drop)

The two pairings can leave either side unmatched. Both are **kept** — dropping
content would violate the recall-first invariant (ADR 0003 D5):

- **Summary present, no frame/data** → a **text-only section** (narrative carried,
  no figure).
- **Frame/data present, no summary** → a **data-only section**; its title is
  generated by the LLM from the `summary_digest` context (not invented blind).

A section with neither is simply absent. Nothing is silently discarded.

---

## 5. Decision D4 — boundary threshold is measurement-gated

Midpoint containment (D2b) is the **fixed base rule**. The handling of the small
minority of frames whose interval straddles a section cut (e.g. a tolerance band,
or a tie when a midpoint falls exactly on a boundary) gets an **initial value
only**; the final threshold is set **after** the ADR 0004 measurement gate, per
the inherited measurement-before-tuning rule (ADR 0004 §5). No boundary constant
is frozen in this ADR.

---

## 6. Constraints (carried, must not be violated)

- **No raw caption in the bundle.** Only `summary_excerpt` (refined) and the v2
  section narrative travel; raw transcript text is runtime in-memory only
  (ADR 0003 D6 — caption no-persist).
- **No frame pixels to the LLM.** The section view carries TEXT
  (`figureLabels`/`summary_excerpt`), LaTeX (`formulas`), and struct-JSON
  (`charts`) only — never crop image bytes, data URLs, or local paths
  (ADR 0003 P2; already enforced by `bundle.py`).
- **LLM outputs content JSON only.** It places per-section content; it does not
  emit PPTX or code (ADR 0003 P1).

---

## 7. Relationship to existing code & phasing

| Item | State |
|---|---|
| `bundle.py:assemble_resources` (flat) | **shipped** (PR-F3) — kept; `sections[]` added additively |
| `_nearest_snapshot` (nearest-time) | retained for the flat arrays; superseded by midpoint **only** inside the section view |
| v2 mirror (`slide-manifest.ts`) | **done** (PR #17) — section fields available now |
| `frames.py` interval provenance | **done** — `[t_start,t_end]` available now |
| Implementation of `sections[]` + midpoint join + orphan branches | **separate PR** (not this ADR) |

This ADR is **doc-only**: no code, schema, or vendored-asset change. The
implementation PR (additive `sections[]` in `bundle.py` + section-attribution
helper + orphan branches, with a unit test on the midpoint join and both orphan
cases) lands independently and carries its own verification.

---

## 8. Rejected (with reason)

| Proposed | Rejected because |
|---|---|
| Replace the flat bundle shape with a section-only shape | breaks the vendored `orchestrate.js` consumer; violates ADR 0003 D7 (byte-stable). Additive view achieves grouping without the break (D1) |
| Attribute frames to sections by overlap-length | boundary double-counting + more complex than a midpoint, with no accuracy gain at slide granularity (D2b) |
| Drop orphan summaries / orphan data | violates recall-first (ADR 0003 D5); orphans become text-only / data-only sections instead (D3) |
| Freeze the boundary tolerance now | unmeasured tuning constant; deferred to the ADR 0004 gate (D4) |
| Put raw caption text in the bundle for better LLM context | ADR 0003 D6 caption no-persist; `summary_excerpt` only (§6) |
