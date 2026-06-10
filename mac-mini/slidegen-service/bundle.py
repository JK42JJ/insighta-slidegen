"""
Resource-bundle assembly — deterministic stage 7 (ADR 0003 §3).

Assembles the resources object that `deck/scripts/orchestrate.js` consumes
UNMODIFIED. The shape authority is the vendored reference
`deck/scripts/extract_resources.js` (preserved unused — its Pix2Text path is
superseded by ADR 0003 D3: MVP equations come from Qwen OCR mode C via
figure_extract.py):

    { title, transcript, segments, figureLabels, formulas, charts }

Raw-frame ban (ADR 0003 P2 / D1): a snapshot is a data source, never the
artifact. This bundle therefore carries only

    - TEXT  — figureLabels (frame summary hints + timestamps), segments,
    - DATA  — charts (mode-B struct-JSON),
    - LaTeX — formulas (mode-C OCR output),

and NEVER raw frame image bytes, data URLs, or local frame/crop paths as
deck-embeddable assets. The only deck-embeddable bitmaps in the pipeline are
matplotlib-REGENERATED PNGs (py/deck_tools/chart_regen.py, ≥ 300 dpi).

Confidence travels with every extracted entry (`conf` +
`verification_status`) so low-confidence figures stay visibly flagged
downstream (ADR 0003 D3; ADR 0004 G3 — report-only, conf < 0.7).

Pure function, JSON-serializable output, no I/O, no DB writes.
"""

from __future__ import annotations

from figure_extract import EQUATION_KIND, KEYFRAME_KIND, ExtractedFigure
from typing_select import SelectedFrame

# Top-level keys of the orchestrate resources contract (extract_resources.js).
RESOURCE_KEYS = ("title", "transcript", "segments", "figureLabels", "formulas", "charts")


def assemble_resources(
    *,
    title: str,
    transcript: str,
    segments: list[dict],
    selected_frames: list[SelectedFrame],
    figures: list[ExtractedFigure],
) -> dict:
    """
    Build the orchestrate resources object.

    Args:
        title / transcript / segments: v2-section passthrough (plain dicts —
            segment shaping is upstream's concern; carried verbatim).
        selected_frames: typing_select output → `figureLabels` TEXT entries
            (snapshot index, timestamp, frame type, summary hint).
        figures: figure_extract output → `formulas` (LaTeX) and `charts`
            (struct-JSON). `keyframe` entries contribute nothing — they have
            no extracted DATA and their pixels are banned from the bundle.

    Returns a dict with exactly RESOURCE_KEYS, JSON-serializable.
    """
    figure_labels = [
        {
            "snapshot": index,
            "ts": float(frame.candidate.timestamp_sec),
            "kind": frame.frame_type,
            "note": frame.summary_hint,
        }
        for index, frame in enumerate(selected_frames)
    ]

    formulas: list[dict] = []
    charts: list[dict] = []
    for figure in figures:
        if figure.kind == KEYFRAME_KIND:
            continue
        snapshot = _nearest_snapshot(figure, selected_frames)
        if figure.kind == EQUATION_KIND and figure.extracted_latex is not None:
            formulas.append(
                {
                    "snapshot": snapshot,
                    "latex": figure.extracted_latex,
                    "conf": figure.extraction_conf,
                    "t": figure.timestamp_sec,
                    "verification_status": figure.verification_status,
                }
            )
        elif figure.struct:
            charts.append(
                {
                    "snapshot": snapshot,
                    "kind": figure.kind,
                    "struct": figure.struct,
                    "conf": figure.extraction_conf,
                    "t": figure.timestamp_sec,
                    "verification_status": figure.verification_status,
                }
            )
        # Figures with neither LaTeX nor struct (e.g. kind=text/photo) carry
        # no regenerable DATA — they stay out of the bundle entirely rather
        # than falling back to raw pixels (ADR 0003 P2).

    return {
        "title": title,
        "transcript": transcript,
        "segments": segments,
        "figureLabels": figure_labels,
        "formulas": formulas,
        "charts": charts,
    }


def _nearest_snapshot(figure: ExtractedFigure, frames: list[SelectedFrame]) -> int | None:
    """Snapshot index of the selected frame nearest in time to the figure."""
    if not frames:
        return None
    return min(
        range(len(frames)),
        key=lambda i: abs(frames[i].candidate.timestamp_sec - figure.timestamp_sec),
    )
