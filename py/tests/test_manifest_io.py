"""
Trivial passing tests for manifest_io.py.
These verify that imports work and the Pydantic model validates fixture data.
"""

import json
import tempfile
from pathlib import Path

import pytest

from slides_build.manifest_io import SlideOutline, load_manifest, manifest_path


FIXTURE_MANIFEST = {
    "video_id": "dQw4w9WgXcQ",
    "lang": "en",
    "generator_version": "slidegen-v1",
    "v2_fingerprint": "a" * 64,
    "slides": [
        {
            "position": 0,
            "layout": "cover",
            "title": "Test Video",
            "body_json": None,
            "notes": None,
            "section_ref": None,
            "figures": [],
        }
    ],
}


def test_slide_outline_model_validates_fixture():
    """SlideOutline.model_validate should accept the fixture without error."""
    outline = SlideOutline.model_validate(FIXTURE_MANIFEST)
    assert outline.video_id == "dQw4w9WgXcQ"
    assert len(outline.slides) == 1
    assert outline.slides[0].layout == "cover"


def test_load_manifest_roundtrip(tmp_path: Path):
    """load_manifest should read and parse a JSON file on disk."""
    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text(json.dumps(FIXTURE_MANIFEST), encoding="utf-8")

    outline = load_manifest(manifest_file)
    assert outline.generator_version == "slidegen-v1"
    assert outline.v2_fingerprint == "a" * 64


def test_manifest_path_format():
    """manifest_path should return a Path containing the deck id."""
    deck_id = "550e8400-e29b-41d4-a716-446655440000"
    p = manifest_path(deck_id)
    assert deck_id in str(p)
    assert str(p).endswith(".json")


def test_video_id_length_validation():
    """SlideOutline should reject video_id that is not 11 chars."""
    bad = {**FIXTURE_MANIFEST, "video_id": "tooshort"}
    with pytest.raises(Exception):
        SlideOutline.model_validate(bad)
