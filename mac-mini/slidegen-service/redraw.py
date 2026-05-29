"""
Vector redraw module — 300 DPI true-vector output.

Operates on the ExtractedFigure list from figure_extract.py, which itself
runs on the ~12 selected keyframes (not the full ~80 candidate set).
Redraw runs after YOLO/OCR extraction — this is the final rendering stage.

For chart figures: uses matplotlib / plotly to reconstruct the chart from
extracted data points (scraped via OCR axis labels + digitise_chart()).
Output: SVG + PDF (via matplotlib savefig with backend='pdf').

For diagram figures: traces bitmap with potrace / Inkscape (subprocess call)
to produce SVG. Falls back to high-DPI PNG if vectorisation fails.

For equation figures: renders LaTeX string (from pix2tex) via matplotlib
mathtext or a LaTeX subprocess → SVG.

Entry: vector_redraw(figures) → list[RedrawnFigure]
"""

from __future__ import annotations

from dataclasses import dataclass

from figure_extract import ExtractedFigure


@dataclass
class RedrawnFigure:
    """Figure with optional vector outputs alongside original PNG."""
    original: ExtractedFigure
    vector_svg_path: str | None   # local path; None if vectorisation failed
    vector_pdf_path: str | None   # local path; None if vectorisation failed
    png_url: str                  # uploaded to Supabase Storage
    vector_svg_url: str | None
    vector_pdf_url: str | None


def vector_redraw(figures: list[ExtractedFigure]) -> list[RedrawnFigure]:
    """
    Attempt true-vector redraw for each extracted figure.

    Algorithm per figure:
        "chart"    → digitise_chart() → matplotlib reconstruct → savefig(format='svg'+'pdf')
        "diagram"  → potrace/Inkscape subprocess on PNG → SVG; cairosvg SVG→PDF
        "equation" → matplotlib mathtext.mathtext2png for preview;
                     pdflatex standalone doc for true-vector PDF
        others     → skip vector redraw, upload PNG as-is

    After redraw: upload PNG/SVG/PDF to Supabase Storage bucket.
    Return RedrawnFigure with public URLs.

    TODO: implement. Graceful degradation: if vectorisation subprocess fails,
    log warning and set vector_svg_path=None (PNG always present).
    """
    raise NotImplementedError("TODO: vector_redraw")
