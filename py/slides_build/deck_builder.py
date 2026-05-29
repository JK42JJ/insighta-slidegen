"""
Google Slides deck builder.

Reads a SlideOutline manifest, creates a new Google Slides presentation,
and populates it slide-by-slide using the layouts module.

Entry point: build_deck(deck_id) — called by the TS orchestrator via subprocess:
    python -m slides_build.deck_builder --deck-id <uuid>

Output:
    Writes google_slides_id and google_slides_url back to slide_decks via
    a psql UPDATE (or via the TS orchestrator after stdout JSON response).

Pipeline inside build_deck():
    1. load_manifest(manifest_path(deck_id))           → SlideOutline
    2. auth.get_credentials()                           → credentials
    3. Slides API: presentations.create(title=...)      → presentation_id
    4. For each Slide in outline.slides:
         a. addSlide batchUpdate request
         b. layout-specific requests from layouts.py
         c. figure requests if slide.figures non-empty
    5. batchUpdate(presentation_id, all_requests)
    6. Print JSON: {"google_slides_id": ..., "google_slides_url": ...}
"""

from __future__ import annotations

import argparse
import json
import sys

from slides_build.manifest_io import load_manifest, manifest_path, SlideOutline
from slides_build import auth, layouts


def build_deck(deck_id: str) -> dict:
    """
    Build a Google Slides deck from a persisted SlideOutline manifest.

    Args:
        deck_id: UUID of the slide_decks row; used to locate the manifest file.

    Returns:
        Dict with keys: google_slides_id, google_slides_url.

    Raises:
        FileNotFoundError: if manifest does not exist.
        NotImplementedError: until fully implemented.

    TODO:
        1. load_manifest(manifest_path(deck_id)) → outline
        2. credentials = auth.get_credentials()
        3. service = auth.build_slides_service(credentials)
        4. presentation = service.presentations().create(body={"title": outline.slides[0].title or deck_id}).execute()
        5. presentation_id = presentation["presentationId"]
        6. Accumulate batchUpdate requests per slide using layouts.*_requests()
        7. service.presentations().batchUpdate(presentationId=presentation_id, body={"requests": all_requests}).execute()
        8. Return {"google_slides_id": presentation_id, "google_slides_url": f"https://docs.google.com/presentation/d/{presentation_id}"}
    """
    raise NotImplementedError(f"TODO: build_deck deck_id={deck_id}")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build Google Slides deck from manifest")
    p.add_argument("--deck-id", required=True, help="slide_decks UUID")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    result = build_deck(args.deck_id)
    print(json.dumps(result))
