"""Tests for bundle.py — orchestrate resource-bundle assembly (stage 7).

Shape authority: deck/scripts/extract_resources.js →
{ title, transcript, segments, figureLabels, formulas, charts }.
All ids/paths are synthetic (PUBLIC repo rule).
"""

import json
from pathlib import Path

from frames import FrameCandidate
from typing_select import SelectedFrame

from bundle import RESOURCE_KEYS, assemble_resources
from figure_extract import ExtractedFigure

# Synthetic local frame/crop paths — these strings must NEVER leak into the bundle.
FRAME_PATH = "/tmp/slidegen-test/frames/frame_0001.jpeg"
CROP_PATH = "/tmp/slidegen-test/crops/frame_0001_crop0.png"

SEGMENTS = [
    {"t": "00:00-01:00", "summary": "intro"},
    {"t": "01:00-02:30", "summary": "main concept"},
]


def make_frame(ts: float, frame_type: str = "chart", hint: str | None = "a synthetic hint"):
    return SelectedFrame(
        candidate=FrameCandidate(Path(FRAME_PATH), ts, 0, 0.9, True),
        contains_graph=True,
        contains_equation=False,
        frame_type=frame_type,
        summary_hint=hint,
        is_topic_aligned=False,
        nearest_topic_point=None,
        selection_score=0.9,
    )


def make_figure(
    kind: str,
    ts: int,
    *,
    latex: str | None = None,
    struct: dict | None = None,
    conf: float = 0.9,
    status: str = "pending",
) -> ExtractedFigure:
    return ExtractedFigure(
        cv_figure_id="fig0001",
        kind=kind,
        png_path=CROP_PATH if kind != "keyframe" else FRAME_PATH,
        caption=None,
        timestamp_sec=ts,
        extracted_latex=latex,
        bbox={"x": 1, "y": 2, "w": 3, "h": 4} if kind != "keyframe" else None,
        extraction_conf=conf,
        struct=struct,
        verification_status=status,
    )


def make_bundle(**overrides):
    kwargs = dict(
        title="Synthetic Video Title",
        transcript="synthetic transcript text",
        segments=SEGMENTS,
        selected_frames=[make_frame(10.0), make_frame(65.0, frame_type="diagram")],
        figures=[
            make_figure("chart", 10, struct={"chart_type": "line", "series": []}),
            make_figure("equation", 64, latex="E = mc^2", conf=0.95),
            make_figure("equation", 65, latex="\\sum_i x_i", conf=0.4, status="unverified"),
            make_figure("keyframe", 30),
        ],
    )
    kwargs.update(overrides)
    return assemble_resources(**kwargs)


# ── shape conformance with the orchestrate resources contract ─────────────────


def test_top_level_keys_match_orchestrate_contract_exactly():
    bundle = make_bundle()
    assert set(bundle) == set(RESOURCE_KEYS)
    assert RESOURCE_KEYS == ("title", "transcript", "segments", "figureLabels", "formulas", "charts")


def test_passthrough_fields():
    bundle = make_bundle()
    assert bundle["title"] == "Synthetic Video Title"
    assert bundle["transcript"] == "synthetic transcript text"
    assert bundle["segments"] == SEGMENTS  # carried verbatim


def test_figure_labels_are_text_entries_from_selected_frames():
    bundle = make_bundle()
    assert bundle["figureLabels"] == [
        {"snapshot": 0, "ts": 10.0, "kind": "chart", "note": "a synthetic hint"},
        {"snapshot": 1, "ts": 65.0, "kind": "diagram", "note": "a synthetic hint"},
    ]


def test_formulas_carry_latex_conf_t_and_flag():
    bundle = make_bundle()
    assert bundle["formulas"] == [
        # t=64 is nearest to the second selected frame (ts=65.0) → snapshot 1.
        {
            "figure_id": "fig0001",
            "snapshot": 1,
            "latex": "E = mc^2",
            "conf": 0.95,
            "t": 64,
            "verification_status": "pending",
        },
        {
            "figure_id": "fig0001",
            "snapshot": 1,
            "latex": "\\sum_i x_i",
            "conf": 0.4,
            "t": 65,
            "verification_status": "unverified",  # ADR 0004 G3 flag travels with the entry
        },
    ]


def test_charts_carry_struct_data():
    bundle = make_bundle()
    assert bundle["charts"] == [
        {
            "figure_id": "fig0001",
            "snapshot": 0,
            "kind": "chart",
            "struct": {"chart_type": "line", "series": []},
            "conf": 0.9,
            "t": 10,
            "verification_status": "pending",
        }
    ]


def test_bundle_is_json_serializable():
    json.dumps(make_bundle())


def test_empty_inputs_keep_the_shape():
    bundle = make_bundle(selected_frames=[], figures=[])
    assert set(bundle) == set(RESOURCE_KEYS)
    assert bundle["figureLabels"] == []
    assert bundle["formulas"] == []
    assert bundle["charts"] == []


# ── raw-frame ban (ADR 0003 P2/D1) — structural assertion ─────────────────────


def test_raw_frame_ban_no_image_paths_bytes_or_data_urls():
    """The bundle carries TEXT + DATA + LaTeX only. No frame/crop path, no
    data URL, no image bytes may appear anywhere in the serialized bundle —
    the only deck-embeddable bitmaps are matplotlib-REGENERATED PNGs."""
    serialized = json.dumps(make_bundle())
    assert FRAME_PATH not in serialized
    assert CROP_PATH not in serialized
    assert "png_path" not in serialized
    assert "data:image" not in serialized
    assert ".png" not in serialized
    assert ".jpeg" not in serialized
    assert ".jpg" not in serialized


def test_keyframe_and_dataless_figures_contribute_nothing():
    """`keyframe` rows and text/photo crops have no regenerable DATA — they
    must stay out of the bundle rather than falling back to raw pixels."""
    bundle = make_bundle(
        figures=[
            make_figure("keyframe", 30),
            make_figure("photo", 40, struct=None),
            make_figure("text", 50, struct={}),
        ]
    )
    assert bundle["formulas"] == []
    assert bundle["charts"] == []
