"""
SlideOutline manifest I/O utilities.

Reads the JSON manifest written by the TS orchestrator (src/index.ts)
and validates it with Pydantic models mirroring the TS SlideOutline shape.

The manifest is produced by planSlides() and persisted to a temp file:
    /tmp/insighta-slidegen-<deck_id>-manifest.json

This module is the boundary between the TS orchestrator and the Python
deck builder; it must not call any Google APIs.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, field_validator


class FigureRef(BaseModel):
    cv_figure_id: str
    kind: str
    png_url: str
    vector_pdf_url: str | None = None
    vector_svg_url: str | None = None
    caption: str | None = None
    timestamp_sec: int | None = None
    atom_refs: list[int] | None = None
    extraction_conf: float | None = None


class Slide(BaseModel):
    position: int
    layout: str
    title: str | None = None
    body_json: dict | None = None
    notes: str | None = None
    section_ref: int | None = None
    figures: list[FigureRef] = []


class SlideOutline(BaseModel):
    video_id: str
    lang: str
    generator_version: str
    v2_fingerprint: str
    slides: list[Slide]

    @field_validator("video_id")
    @classmethod
    def video_id_length(cls, v: str) -> str:
        """YouTube video ids are exactly 11 characters."""
        if len(v) != 11:
            raise ValueError(f"video_id must be 11 chars, got {len(v)}")
        return v


def load_manifest(path: str | Path) -> SlideOutline:
    """
    Load and validate a SlideOutline manifest from a JSON file.

    Args:
        path: Filesystem path to the JSON manifest.

    Returns:
        Validated SlideOutline instance.

    Raises:
        FileNotFoundError: if path does not exist.
        pydantic.ValidationError: if JSON does not match SlideOutline schema.

    TODO: already importable (Pydantic model_validate handles the rest);
    no additional implementation needed beyond this parse call.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return SlideOutline.model_validate(data)


def manifest_path(deck_id: str) -> Path:
    """Return the canonical temp-file path for a deck manifest."""
    return Path(f"/tmp/insighta-slidegen-{deck_id}-manifest.json")
