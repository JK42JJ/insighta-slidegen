"""
True-vector PDF compositor.

Produces a PDF where:
  - Text elements use embedded fonts (no rasterisation).
  - Vector figures (SVG / EPS from CV service) are embedded as PDF XObjects.
  - Raster fallback (PNG) is used only when no vector source is available.

Two output tracks:
  - Raster PDF: PNG figures at 300 DPI (rasterised Google Slides export equivalent).
  - True-vector PDF: LaTeX / reportlab SVG→PDF path with actual vector geometry.

Entry point: compose_pdf(deck_id, vector=True) — called by TS orchestrator:
    python -m slides_build.pdf_vector_compositor --deck-id <uuid> [--raster]

Output:
    Writes PDF bytes to Supabase Storage (SUPABASE_STORAGE_BUCKET env var).
    Prints JSON: {"pdf_url": ..., "vector_pdf_url": ...}

Implementation strategy for true-vector track:
    reportlab approach — svglib.svg2rlg() to convert CV SVGs to ReportLab
    graphics, then canvas.drawInlineImage / renderPDF.draw() for placement.
    Fallback: LaTeX (pdflatex + includegraphics) when SVG is unavailable.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from slides_build.manifest_io import load_manifest, manifest_path, SlideOutline


def compose_pdf(deck_id: str, vector: bool = True) -> dict:
    """
    Compose a PDF for the given deck.

    Args:
        deck_id: UUID of the slide_decks row.
        vector:  If True produce true-vector PDF; if False produce 300-DPI raster PDF.

    Returns:
        Dict with keys: pdf_url, vector_pdf_url (None when vector=False).

    TODO:
        1. load_manifest(manifest_path(deck_id)) → outline
        2. For each slide in outline.slides:
             a. Render title + body_json text onto reportlab canvas.
             b. If slide.figures: for each figure, prefer vector_svg_url
                (svglib.svg2rlg → renderPDF.draw) else insert png_url at 300 DPI.
        3. canvas.save() → bytes
        4. Upload to Supabase Storage bucket under key f"decks/{deck_id}/deck.pdf"
           or f"decks/{deck_id}/deck-vector.pdf".
        5. Return signed URLs or public URLs.
    """
    raise NotImplementedError(f"TODO: compose_pdf deck_id={deck_id} vector={vector}")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Compose PDF from SlideOutline manifest")
    p.add_argument("--deck-id", required=True, help="slide_decks UUID")
    p.add_argument("--raster", action="store_true", help="produce raster PDF instead of vector")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    result = compose_pdf(args.deck_id, vector=not args.raster)
    print(json.dumps(result))
