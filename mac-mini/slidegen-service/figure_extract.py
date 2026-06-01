"""
Figure extraction, layout detection, and equation OCR on the selected keyframes.

This module operates ONLY on the keyframes produced by
typing_select.select_keyframes() — NOT on the full candidate set. Layout
detection and OCR belong here, not in the selection stage.

Routing is driven by the VLM router's flags on each SelectedFrame (ADR 0001):
    - contains_graph=True  → DocLayout-YOLO region detection + crop
    - contains_equation=True → UniMERNet equation → LaTeX

For figure-bearing frames:
    1. DocLayout-YOLO layout detection to locate chart/diagram/table regions.
    2. Crop the region bounding box (opencv); keep the bbox for provenance.
    3. Real-ESRGAN 4× upscale → 300-DPI-equivalent PNG (vector redraw happens
       downstream in redraw.py — the crop is an input, not the final figure).
    4. PaddleOCR for caption / label / axis text extraction.
    5. UniMERNet for equation frames → LaTeX (replaces pix2tex; ADR 0001).
    6. Persist to slidegen.slide_keyframes / slide_figures (no CLIP embedding).

For "title_card", "face", "b_roll": skip layout/OCR; write keyframe row only.

Entry: extract_figures(selected_frames, mode) → list[ExtractedFigure]
"""

from __future__ import annotations

from dataclasses import dataclass

from typing_select import SelectedFrame

# Document layout detector (graph/table region crop) — ADR 0001.
LAYOUT_MODEL = "doclayout-yolo"
# Equation OCR (region → LaTeX) — ADR 0001 (replaces pix2tex). Fallback: PP-FormulaNet.
EQUATION_OCR_MODEL = "unimernet"


@dataclass
class ExtractedFigure:
    """CV-processed figure ready for vector redraw + upload."""
    cv_figure_id: str          # hash of youtube_video_id + timestamp_sec
    kind: str                  # "chart" | "diagram" | "equation" | "table" | "screenshot" | "keyframe"
    png_path: str              # local path to 300-DPI crop PNG
    caption: str | None        # PaddleOCR text (axis labels / legends / body)
    timestamp_sec: int
    extracted_latex: str | None  # UniMERNet LaTeX for kind='equation' (ADR 0001)
    bbox: dict | None            # DocLayout-YOLO crop region {x,y,w,h}; None for whole-frame
    extraction_conf: float


def extract_figures(
    selected_frames: list[SelectedFrame],
    mode: str = "dev",
) -> list[ExtractedFigure]:
    """
    Run DocLayout-YOLO layout detection + UniMERNet equation OCR on the selected keyframes.

    Algorithm:
        1. For each SelectedFrame, route on its VLM flags (contains_graph /
           contains_equation) — no re-classification here.
        2. For contains_graph frames:
             a. DocLayout-YOLO region detection → bbox; crop (opencv).
             b. Real-ESRGAN 4× upscale → 300-DPI PNG.
             c. PaddleOCR → caption text (axis labels, legends, body).
        3. For contains_equation frames:
             a. DocLayout-YOLO / region crop of the equation.
             b. UniMERNet → LaTeX into extracted_latex (fallback: PP-FormulaNet).
        4. Non-figure frames (title_card/face/b_roll): kind='keyframe', no crop.
        5. Persist to slidegen.slide_figures / slide_keyframes (skip in dev if no
           DB URL) — NO clip_embedding (deprecated, ADR 0001).
        6. Return ExtractedFigure list (one entry per selected frame).

    No vision API (Gemini etc.) calls regardless of mode — local CV only.

    TODO (Phase 2 inference): implement using doclayout_yolo, opencv, real_esrgan,
          paddleocr, unimernet; mode='dev' skips DB write.
    """
    raise NotImplementedError("TODO: extract_figures (DocLayout-YOLO + UniMERNet)")
