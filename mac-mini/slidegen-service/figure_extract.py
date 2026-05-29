"""
Figure extraction, layout detection, and OCR on the ~12 selected keyframes.

This module operates ONLY on the already-selected keyframes produced by
typing_select.select_keyframes() — NOT on the full ~80 candidate set.
YOLO layout detection and OCR belong here, not in the selection stage.

For frames classified as "diagram", "chart", or "equation":
    1. YOLO layout detection (ultralytics YOLOv8) to locate figure regions.
    2. Crop the figure bounding box (opencv).
    3. Real-ESRGAN 4× upscale → 300 DPI equivalent PNG.
    4. PaddleOCR for caption / label / axis text extraction.
    5. pix2tex for equation frames (LaTeX transcription from OCR).
    6. Generate CLIP embedding for the cropped figure region.
    7. Persist to slide_keyframes (update is_selected=True row) via Supabase client.

For "title_card", "face", "b_roll": skip YOLO/OCR; write keyframe row only.

Entry: extract_figures(selected_frames, mode) → list[ExtractedFigure]
"""

from __future__ import annotations

from dataclasses import dataclass

from typing_select import SelectedFrame


@dataclass
class ExtractedFigure:
    """CV-processed figure ready for upload."""
    cv_figure_id: str         # hash of youtube_video_id + timestamp_sec
    kind: str                 # "chart" | "diagram" | "equation" | "table" | "screenshot" | "keyframe"
    png_path: str             # local path to 300-DPI PNG
    caption: str | None
    timestamp_sec: int
    clip_embedding: list[float] | None
    extraction_conf: float


def extract_figures(
    selected_frames: list[SelectedFrame],
    mode: str = "dev",
) -> list[ExtractedFigure]:
    """
    Run YOLO layout detection + OCR on the ~12 selected keyframes.

    Algorithm:
        1. For each SelectedFrame, classify frame_type via YOLO bounding-box
           detection (ultralytics YOLOv8 trained on document layouts).
        2. Filter for figure-bearing types: diagram, chart, equation, table.
        3. For each figure-bearing frame:
             a. YOLO bbox crop (opencv).
             b. Real-ESRGAN 4× upscale → 300-DPI JPEG/PNG.
             c. PaddleOCR → caption text (axis labels, legends, text body).
             d. pix2tex if frame_type='equation' → LaTeX string in caption field.
             e. CLIP encode cropped region → clip_embedding (512-dim, ViT-B/32).
             f. Write / update slide_keyframes row (skip in dev if no DB URL).
        4. Non-figure frames: write keyframe row with kind='keyframe', no crop.
        5. Return ExtractedFigure list (one entry per selected frame).

    No vision API (Gemini etc.) calls regardless of mode — CV only.

    TODO: implement using ultralytics, opencv, real_esrgan, paddleocr, pix2tex,
          open_clip; mode='dev' skips DB write.
    """
    raise NotImplementedError("TODO: extract_figures")
