# Figure Manifest Contract

**Version**: 1.0
**Status**: Design
**Producer**: Mac Mini CV host (`mac-mini/slidegen-service/`)
**Consumer**: Insighta prod server, slidegen-orchestrator (`src/modules/slidegen/`)

---

## Table of Contents

1. [Overview](#1-overview)
2. [Per-Figure Entry Schema](#2-per-figure-entry-schema)
3. [Per-Deck Manifest Shape](#3-per-deck-manifest-shape)
4. [Field Semantics and Invariants](#4-field-semantics-and-invariants)
5. [Versioning Rule](#5-versioning-rule)
6. [Example Manifest](#6-example-manifest)
7. [Consumer Validation Checklist](#7-consumer-validation-checklist)

---

## 1. Overview

After completing a CV task for a given video and deck request, the Mac Mini CV host serializes all extracted and redrawn figures into a single JSON document: the **figure manifest**. The orchestrator on the Insighta prod server retrieves this document via the CV service's `/cv-tasks/{task_id}/manifest` endpoint and uses it to:

1. Write one `slide_figures` row per figure entry.
2. Attach figures to their corresponding slide via the timestamp-to-section mapping.
3. Gate publishing on the verification-status distribution.

The manifest is the sole handoff artifact between the CV pipeline and the slide planner. Neither side may proceed on assumptions not expressed in this document.

---

## 2. Per-Figure Entry Schema

Each element of `manifest.figures[]` conforms to the following schema.

```jsonc
{
  // ── Identity ──────────────────────────────────────────────────────────
  "figure_id": "VIDEOID0001_s02_figure_chart_001",
  // Stable identifier. Format: "{video_id}_{section_tag}_{frame_type}_{seq}"
  // section_tag: "s{zero-padded index}" e.g. "s02" for sections[2]
  // seq: 001-based counter within the section/frame-type bucket
  // MUST be unique within the manifest.

  "kind": "redrawn",
  // Enum: "redrawn" | "keyframe"
  // "redrawn": the figure was extracted and re-rendered (chart, table, formula, diagram).
  // "keyframe": the frame is included as a raster image without redraw.

  // ── Source location ────────────────────────────────────────────────────
  "timestamp_sec": 342.7,
  // Float. The video timestamp of the source frame in seconds.
  // May be null ONLY for synthesized figures (e.g. a table composed from multiple frames).

  "section_index": 2,
  // Integer. Zero-based index into v2 segments.sections[].
  // The consumer uses this for slide attachment; timestamp-to-section math is
  // cross-checked server-side but section_index is authoritative.

  "frame_type": "figure_chart",
  // YOLO-assigned frame type (determined in the figure-extraction stage, after
  // frame selection is complete). Enum:
  //   "figure_chart" | "figure_diagram" | "figure_table" | "figure_formula"
  //   | "slide_text" | "whiteboard" | "face_talking" | "transition" | "unknown"

  // ── Extraction quality ─────────────────────────────────────────────────
  "extraction_confidence": 0.91,
  // Float in [0.0, 1.0].
  // Computed as:
  //   charts:   fraction of data point mappings passing internal consistency gate
  //   tables:   cross-OCR cell-level agreement ratio (PaddleOCR vs Tesseract)
  //   formulas: SSIM(re-rendered LaTeX, original crop)
  //   keyframe: always 1.0 (no extraction, no uncertainty)
  //   diagram:  OCR cross-check agreement on text nodes

  "verification_status": "verified",
  // Enum: "verified" | "unverified" | "dropped"
  // "verified":   extraction_confidence >= 0.85; redrawn assets fully populated.
  // "unverified": 0.55 <= confidence < 0.85. PNG only; vector assets are null.
  //               In prod-service path: vision API reconciliation was attempted.
  //               In dev path: super-res crop applied; no vision API.
  // "dropped":    confidence < 0.55. All asset URLs are null. Slide planner skips.
  // MUST be one of the three values above. Null is a contract violation.

  "drop_reason": null,
  // String or null.
  // Required when verification_status == "dropped". Describes why.
  // Example values: "confidence_below_threshold" | "ocr_consensus_failed"
  //   | "axis_calibration_failed" | "ssim_too_low" | "no_axis_labels"
  // Null for verified and unverified figures.

  // ── Asset URLs ─────────────────────────────────────────────────────────
  "png_300dpi_url": "https://storage.example.com/slidegen/VIDEOID0001/fig_s02_001.png",
  // Short-lived signed URL (15-minute TTL) to the 300dpi PNG in Supabase Storage.
  // MUST be non-null for "verified" and "unverified" figures.
  // MUST be null for "dropped" figures.

  "vector_pdf_url": "https://storage.example.com/slidegen/VIDEOID0001/fig_s02_001.pdf",
  // Signed URL to the vector PDF asset.
  // MUST be non-null for "verified" AND kind == "redrawn".
  // MUST be null for "unverified", "dropped", and kind == "keyframe".

  "vector_svg_url": "https://storage.example.com/slidegen/VIDEOID0001/fig_s02_001.svg",
  // Signed URL to the SVG asset.
  // Same population rules as vector_pdf_url.

  // ── Semantic content ───────────────────────────────────────────────────
  "caption": "Revenue by quarter, 2019–2023",
  // Short string (max 200 chars). Drafted by the Claude skill from atom text
  // + section context. MUST NOT contain numeric values not present in
  // source_extraction_data (hallucination guard).
  // May be null if no caption could be drafted.

  "source_atom_refs": ["VIDEOID0001_atoms_12", "VIDEOID0001_atoms_13"],
  // Array of strings. Each entry is an atom identifier in the format
  // "{video_id}_atoms_{index}" pointing to segments.atoms[index] in the v2
  // rich-summary for this video.
  // MUST be non-empty for kind == "redrawn".
  // May be empty for kind == "keyframe".

  // ── Extracted structured data (for verified redrawn figures) ───────────
  "source_extraction_data": {
    // Present for verified + redrawn figures. Null for keyframes and dropped.
    // Shape varies by frame_type:

    // For figure_chart:
    "chart_type": "bar",       // bar | line | scatter | pie | histogram | area | unknown
    "x_label": "Quarter",
    "y_label": "Revenue (USD M)",
    "series": [
      {
        "name": "North America",
        "data_points": [
          { "x": "Q1 2019", "y": 142.3 },
          { "x": "Q2 2019", "y": 155.1 }
        ]
      }
    ],

    // For figure_table:
    // "headers": ["Product", "Units", "Revenue"],
    // "rows": [["Widget A", "1200", "48000"], ["Widget B", "800", "36000"]],
    // "merged_cells": [],

    // For figure_formula:
    // "latex": "\\hat{y} = \\beta_0 + \\beta_1 x + \\epsilon",
    // "ssim_score": 0.91,

    // For figure_diagram:
    // "diagram_source": "graph TD\n  A --> B\n  B --> C",
    // "diagram_format": "mermaid"   // mermaid | graphviz | unknown
  },

  // ── Redraw metadata ────────────────────────────────────────────────────
  "redraw_renderer": "matplotlib",
  // The renderer used. Enum:
  //   "matplotlib" | "plotly" | "latex_dvisvgm" | "booktabs" | "mermaid"
  //   | "graphviz" | "none" (for keyframes)
  // null if dropped.

  "redraw_renderer_version": "3.8.2"
  // Semver string of the renderer library. For auditability.
  // null if dropped or keyframe.
}
```

---

## 3. Per-Deck Manifest Shape

```jsonc
{
  "schema_version": "1.0",
  // REQUIRED. Semver string. Consumer MUST reject if unsupported.
  // Current supported versions: ["1.0"]

  "manifest_id": "550e8400-e29b-41d4-a716-446655440000",
  // UUID. Unique ID for this manifest document. Used for idempotent re-consumption.

  "video_id": "VIDEOID0001",
  // 11-character YouTube video ID (fixture example).

  "task_id": "task_abc123",
  // The CV task ID issued by the orchestrator. Used for correlation.

  "generator_version": "v1.0.0",
  // The slidegen generator version that requested this CV task.
  // Must match the generator_version in the corresponding slide_decks row.

  "produced_at": "2025-11-01T09:14:33Z",
  // ISO 8601 UTC timestamp of manifest production on the Mac Mini CV host.

  "pipeline_durations_ms": {
    // Telemetry. Each stage duration in milliseconds. Used for job log.
    // frame_extraction: Katna + forced grabs (~80 candidates)
    // frame_selection:  CLIP + BGE-M3 embedding + pgvector cosine dedup (→ ~12 frames)
    // figure_extraction: YOLO layout + OCR + axis-calibration + pix2tex (on ~12 selected frames)
    "frame_extraction":   12400,
    "frame_selection":     4100,
    "figure_extraction":  18700,
    "figure_redraw":      31200,
    "asset_upload":        6300
  },

  "summary": {
    // Aggregate counts. MUST match the actual figures[] array contents.
    "total":      14,
    "verified":    9,
    "unverified":  3,
    "dropped":     2,
    "redrawn":    10,
    "keyframes":   4
  },

  "figures": [
    // Array of figure entry objects (schema in section 2).
    // Ordered by timestamp_sec ascending (nulls last).
    // Length MUST equal summary.total.
  ]
}
```

---

## 4. Field Semantics and Invariants

The following invariants MUST hold in every valid manifest. The consumer validates all of them and rejects the manifest (fails loud, logs to `slide_job_log`) if any is violated.

| # | Invariant |
|---|---|
| 1 | `schema_version` is present and its value is in the consumer's supported-versions list. |
| 2 | `figures[].figure_id` is unique within the manifest (no duplicates). |
| 3 | `figures[].verification_status` is exactly one of `"verified"`, `"unverified"`, `"dropped"`. Null or any other value is a contract violation. |
| 4 | `figures[].png_300dpi_url` is non-null if and only if `verification_status != "dropped"`. |
| 5 | `figures[].vector_pdf_url` and `figures[].vector_svg_url` are non-null if and only if `verification_status == "verified"` AND `kind == "redrawn"`. |
| 6 | `figures[].drop_reason` is non-null if and only if `verification_status == "dropped"`. |
| 7 | `figures[].source_atom_refs` is a non-empty array for all entries where `kind == "redrawn"`. |
| 8 | `figures[].source_extraction_data` is non-null for all entries where `verification_status == "verified"` AND `kind == "redrawn"`. |
| 9 | `summary.total` equals `len(figures)`. |
| 10 | `summary.verified + summary.unverified + summary.dropped == summary.total`. |
| 11 | `summary.redrawn + summary.keyframes == summary.total`. |
| 12 | No figure entry with `verification_status == "dropped"` has any non-null asset URL. |

---

## 5. Versioning Rule

### Schema Version Lifecycle

| Schema version | Status | Supported by consumer |
|---|---|---|
| `1.0` | Current | Yes |

### Version Bump Policy

A new manifest schema version MUST be issued when any of the following changes:

- A field is added that the consumer must handle differently (not just ignored extra fields).
- A field is removed or renamed.
- The semantics of an existing field change (e.g., a status enum value is renamed).
- The structure of `source_extraction_data` for any `frame_type` changes in a breaking way.

**Minor additive changes** (new optional fields that the consumer can safely ignore) do NOT require a version bump. The consumer MUST ignore unknown fields.

### Migration Path

When a new schema version is introduced:

1. The Mac Mini CV service is updated to produce the new version.
2. The consumer (orchestrator) is updated to accept both the old and new version.
3. After all in-flight tasks have completed, support for the old version is removed from the consumer.
4. The old version is moved to the "deprecated" column in the table above.

No manifest with a deprecated schema version will be accepted by the consumer. The CV service MUST NOT be deployed with a newer schema version until the consumer has been updated.

### Contract Version vs Generator Version

- `schema_version` in the manifest refers to the manifest document format (this contract).
- `generator_version` refers to the slidegen application version that requested the CV task.

These are independent. A manifest with schema version `1.0` can be produced for generator version `v1.0.0`, `v1.1.0`, or `v2.0.0`. The schema version only changes when the manifest format itself changes.

---

## 6. Example Manifest

The following is a minimal valid manifest for a video with two figures. Video and content references use fixture values (not real IDs or data).

```json
{
  "schema_version": "1.0",
  "manifest_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "video_id": "VIDEOID0001",
  "task_id": "task_demo_001",
  "generator_version": "v1.0.0",
  "produced_at": "2025-11-01T09:14:33Z",
  "pipeline_durations_ms": {
    "frame_extraction": 11200,
    "frame_selection": 3800,
    "figure_extraction": 9400,
    "figure_redraw": 14600,
    "asset_upload": 4100
  },
  "summary": {
    "total": 3,
    "verified": 2,
    "unverified": 0,
    "dropped": 1,
    "redrawn": 2,
    "keyframes": 1
  },
  "figures": [
    {
      "figure_id": "VIDEOID0001_s01_figure_chart_001",
      "kind": "redrawn",
      "timestamp_sec": 183.4,
      "section_index": 1,
      "frame_type": "figure_chart",
      "extraction_confidence": 0.93,
      "verification_status": "verified",
      "drop_reason": null,
      "png_300dpi_url": "https://storage.example.com/slidegen/VIDEOID0001/s01_chart_001.png",
      "vector_pdf_url": "https://storage.example.com/slidegen/VIDEOID0001/s01_chart_001.pdf",
      "vector_svg_url": "https://storage.example.com/slidegen/VIDEOID0001/s01_chart_001.svg",
      "caption": "Market share by segment, 2020–2024",
      "source_atom_refs": ["VIDEOID0001_atoms_7"],
      "source_extraction_data": {
        "chart_type": "bar",
        "x_label": "Year",
        "y_label": "Market share (%)",
        "series": [
          {
            "name": "Segment A",
            "data_points": [
              { "x": "2020", "y": 34.2 },
              { "x": "2021", "y": 36.1 },
              { "x": "2022", "y": 38.7 }
            ]
          }
        ]
      },
      "redraw_renderer": "matplotlib",
      "redraw_renderer_version": "3.8.2"
    },
    {
      "figure_id": "VIDEOID0001_s02_slide_text_001",
      "kind": "keyframe",
      "timestamp_sec": 312.0,
      "section_index": 2,
      "frame_type": "slide_text",
      "extraction_confidence": 1.0,
      "verification_status": "verified",
      "drop_reason": null,
      "png_300dpi_url": "https://storage.example.com/slidegen/VIDEOID0001/s02_keyframe_001.png",
      "vector_pdf_url": null,
      "vector_svg_url": null,
      "caption": null,
      "source_atom_refs": [],
      "source_extraction_data": null,
      "redraw_renderer": "none",
      "redraw_renderer_version": null
    },
    {
      "figure_id": "VIDEOID0001_s03_figure_formula_001",
      "kind": "redrawn",
      "timestamp_sec": 487.9,
      "section_index": 3,
      "frame_type": "figure_formula",
      "extraction_confidence": 0.41,
      "verification_status": "dropped",
      "drop_reason": "ssim_too_low",
      "png_300dpi_url": null,
      "vector_pdf_url": null,
      "vector_svg_url": null,
      "caption": null,
      "source_atom_refs": ["VIDEOID0001_atoms_22"],
      "source_extraction_data": null,
      "redraw_renderer": null,
      "redraw_renderer_version": null
    }
  ]
}
```

---

## 7. Consumer Validation Checklist

The orchestrator MUST perform all of the following checks before writing `slide_figures` rows or proceeding to Google Slides assembly.

```
[ ] 1. Parse manifest JSON. On parse error: fail the job with stage="manifest_parse", log error_detail.

[ ] 2. Check schema_version in supported-versions list.
        On mismatch: fail with stage="manifest_version_check".

[ ] 3. Check manifest_id not already processed (idempotency).
        If already processed: skip re-write; return existing deck_id.

[ ] 4. Check summary.total == len(figures).
        On mismatch: fail with stage="manifest_summary_check".

[ ] 5. Check summary.verified + summary.unverified + summary.dropped == summary.total.
        On mismatch: fail with stage="manifest_summary_check".

[ ] 6. For each figure:
        a. verification_status is one of {"verified","unverified","dropped"}.
        b. png_300dpi_url non-null iff verification_status != "dropped".
        c. vector_pdf_url and vector_svg_url non-null iff verified AND redrawn.
        d. drop_reason non-null iff dropped.
        e. source_atom_refs non-empty iff kind == "redrawn".
        f. figure_id unique within manifest.
        On any violation: log warning per figure, downgrade that figure to "dropped"
        and continue (do not fail the entire manifest).

[ ] 7. Check unverified rate:
        if summary.unverified / summary.total > 0.15:
            flag deck for human review before publishing.

[ ] 8. Check DPI of each PNG:
        Retrieve asset (or trust the CV service assertion via a "dpi" field if added in a future version).
        On DPI < 300: downgrade figure to "unverified", log warning.

[ ] 9. Write slide_figures rows. On DB write error: fail with stage="db_write".

[  ] 10. Proceed to slide assembly only after all validations pass or individual
         figures are downgraded. Never proceed on a completely failed manifest.
```
