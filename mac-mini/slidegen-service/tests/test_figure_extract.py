"""Tests for figure_extract.py — YOLO crop → Qwen numerization (stage 5).

All model traffic goes through the in-process contract stubs
(httpx.MockTransport — no network, no GPU). Frame images are synthetic
numpy/cv2 fixtures; ids and paths are synthetic (PUBLIC repo rule).
"""

import json

import cv2
import numpy as np
import pytest
from stubs.vlm_stub import VlmStub
from stubs.yolo_stub import YoloStub

from frames import FrameCandidate
from typing_select import SelectedFrame

FRAME_W, FRAME_H = 320, 180

CHART_REPLY = json.dumps(
    {
        "kind": "chart",
        "struct": {
            "chart_type": "line",
            "axes": {"x": "epoch", "y": "loss"},
            "series": [{"name": "train", "points": [{"x": 1, "y": 0.9}, {"x": 2, "y": 0.5}]}],
            "insight": "loss decreases",
        },
        "confidence": 0.9,
    }
)


def make_vlm_client(stub: VlmStub):
    from model_clients import VlmHttpClient

    return VlmHttpClient(
        "http://vlm.stub.invalid",
        stub.token,
        stub.model,
        transport=stub.transport(),
        backoff_base_sec=0.0,
        sleep=lambda _s: None,
    )


def make_yolo_client(stub: YoloStub):
    from model_clients import YoloHttpClient

    return YoloHttpClient(
        "http://yolo.stub.invalid",
        stub.token,
        transport=stub.transport(),
        backoff_base_sec=0.0,
        sleep=lambda _s: None,
    )


def make_frame(
    tmp_path,
    *,
    name="frame_0001",
    timestamp=12.0,
    contains_graph=False,
    contains_equation=False,
    frame_type="chart",
    summary_hint="synthetic slide",
) -> SelectedFrame:
    path = tmp_path / f"{name}.jpeg"
    image = np.full((FRAME_H, FRAME_W, 3), 200, dtype=np.uint8)
    cv2.imwrite(str(path), image)
    return SelectedFrame(
        candidate=FrameCandidate(path, timestamp, 0, 0.9, True),
        contains_graph=contains_graph,
        contains_equation=contains_equation,
        frame_type=frame_type,
        summary_hint=summary_hint,
        is_topic_aligned=False,
        nearest_topic_point=None,
        selection_score=0.88,
    )


def make_yolo_stub(boxes: list[dict]) -> YoloStub:
    return YoloStub(image_w=FRAME_W, image_h=FRAME_H, boxes=boxes)


def run_extract(frames, yolo_stub, vlm_stub, tmp_path):
    from figure_extract import extract_figures

    return extract_figures(
        frames,
        yolo=make_yolo_client(yolo_stub),
        vlm=make_vlm_client(vlm_stub),
        out_dir=tmp_path / "crops",
    )


# ── happy path: graph frame → YOLO box → mode-B chart struct ─────────────────


def test_chart_happy_path(tmp_path):
    yolo = make_yolo_stub([{"bbox": {"x": 40, "y": 30, "w": 120, "h": 80}, "class": "figure", "score": 0.8}])
    vlm = VlmStub()
    vlm.script_content(CHART_REPLY)

    frame = make_frame(tmp_path, contains_graph=True)
    figures = run_extract([frame], yolo, vlm, tmp_path)

    assert len(figures) == 1
    fig = figures[0]
    assert fig.kind == "chart"
    assert fig.struct["chart_type"] == "line"
    assert fig.extracted_latex is None
    assert fig.extraction_conf == 0.9
    assert fig.verification_status == "pending"
    assert fig.timestamp_sec == 12
    assert fig.bbox == {"x": 40, "y": 30, "w": 120, "h": 80}
    # The crop PNG exists and has the bbox dimensions (data source, not deck asset).
    crop = cv2.imread(fig.png_path)
    assert crop.shape[:2] == (80, 120)


def test_crop_travels_as_data_url_with_interval_caption_slice(tmp_path):
    yolo = make_yolo_stub([{"bbox": {"x": 0, "y": 0, "w": 50, "h": 50}, "class": "figure", "score": 0.5}])
    vlm = VlmStub()
    vlm.script_content(CHART_REPLY)

    frame = make_frame(tmp_path, contains_graph=True, summary_hint="revenue trend")
    run_extract([frame], yolo, vlm, tmp_path)

    parts = vlm.request_payloads()[0]["messages"][0]["content"]
    image_parts = [p for p in parts if p["type"] == "image_url"]
    assert image_parts[0]["image_url"]["url"].startswith("data:image/png;base64,")
    text_parts = [p["text"] for p in parts if p["type"] == "text"]
    assert text_parts[0] == "[12.0, 12.0] revenue trend"  # caption slice: interval + hint


# ── equation path: mode B says equation → mode C OCR → LaTeX ─────────────────


def test_equation_routes_to_mode_c_ocr(tmp_path):
    yolo = make_yolo_stub([{"bbox": {"x": 10, "y": 10, "w": 100, "h": 40}, "class": "plain_text", "score": 0.4}])
    vlm = VlmStub()
    vlm.script_content(
        '{"kind": "equation", "struct": {}, "confidence": 0.6}',
        '{"latex": "E = mc^2", "confidence": 0.95}',
    )

    frame = make_frame(tmp_path, contains_equation=True, frame_type="diagram")
    figures = run_extract([frame], yolo, vlm, tmp_path)

    assert len(figures) == 1
    fig = figures[0]
    assert fig.kind == "equation"
    assert fig.extracted_latex == "E = mc^2"
    assert fig.extraction_conf == 0.95  # mode-C OCR confidence, not mode-B's
    assert fig.struct is None
    assert fig.verification_status == "pending"
    assert len(vlm.requests) == 2  # one mode-B call + one mode-C call


# ── ADR 0004 G3 conf gate: conf < 0.7 → unverified, never silently embedded ──


def test_low_confidence_is_flagged_unverified(tmp_path):
    from figure_extract import LOW_CONF_THRESHOLD

    assert LOW_CONF_THRESHOLD == 0.7  # ADR 0004 G3 initial threshold

    yolo = make_yolo_stub([{"bbox": {"x": 0, "y": 0, "w": 60, "h": 60}, "class": "figure", "score": 0.9}])
    vlm = VlmStub()
    vlm.script_content('{"kind": "chart", "struct": {"chart_type": "bar"}, "confidence": 0.5}')

    figures = run_extract([make_frame(tmp_path, contains_graph=True)], yolo, vlm, tmp_path)
    assert figures[0].verification_status == "unverified"
    # The figure is still RETURNED (flagged, not dropped — report-only gate).
    assert figures[0].struct == {"chart_type": "bar"}


def test_low_confidence_equation_is_flagged(tmp_path):
    yolo = make_yolo_stub([{"bbox": {"x": 0, "y": 0, "w": 60, "h": 30}, "class": "formula", "score": 0.9}])
    vlm = VlmStub()
    vlm.script_content(
        '{"kind": "equation", "struct": {}, "confidence": 0.9}',
        '{"latex": "\\\\sum_i x_i", "confidence": 0.3}',
    )

    figures = run_extract([make_frame(tmp_path, contains_equation=True)], yolo, vlm, tmp_path)
    assert figures[0].verification_status == "unverified"
    assert figures[0].extracted_latex == "\\sum_i x_i"  # flagged, never hidden


# ── YOLO class NEVER gates (advisory only, §3.4 / ADR 0002 D2) ───────────────


def test_yolo_class_never_gates_kind(tmp_path):
    """A box labelled `isolate_formula` by YOLO still becomes a chart when
    Qwen's mode-B decision says chart — class is WHERE-stage advisory only."""
    yolo = make_yolo_stub(
        [{"bbox": {"x": 5, "y": 5, "w": 80, "h": 60}, "class": "isolate_formula", "score": 0.2}]
    )
    vlm = VlmStub()
    vlm.script_content(CHART_REPLY)

    figures = run_extract([make_frame(tmp_path, contains_graph=True)], yolo, vlm, tmp_path)
    assert figures[0].kind == "chart"
    assert figures[0].extracted_latex is None  # mode C was never invoked
    assert len(vlm.requests) == 1


def test_unknown_yolo_class_is_still_processed(tmp_path):
    yolo = make_yolo_stub(
        [{"bbox": {"x": 5, "y": 5, "w": 80, "h": 60}, "class": "abandon", "score": 0.2}]
    )
    vlm = VlmStub()
    vlm.script_content('{"kind": "table", "struct": {"headers": ["a"], "rows": [["1"]]}, "confidence": 0.8}')

    figures = run_extract([make_frame(tmp_path, contains_graph=True)], yolo, vlm, tmp_path)
    assert figures[0].kind == "table"
    assert figures[0].struct == {"headers": ["a"], "rows": [["1"]]}


# ── bbox clamp ────────────────────────────────────────────────────────────────


def test_bbox_is_clamped_to_image_bounds(tmp_path):
    yolo = make_yolo_stub(
        [{"bbox": {"x": 280, "y": 150, "w": 200, "h": 100}, "class": "figure", "score": 0.7}]
    )
    vlm = VlmStub()
    vlm.script_content(CHART_REPLY)

    figures = run_extract([make_frame(tmp_path, contains_graph=True)], yolo, vlm, tmp_path)
    fig = figures[0]
    assert fig.bbox == {"x": 280, "y": 150, "w": FRAME_W - 280, "h": FRAME_H - 150}
    crop = cv2.imread(fig.png_path)
    assert crop.shape[:2] == (FRAME_H - 150, FRAME_W - 280)


def test_fully_out_of_bounds_box_is_skipped(tmp_path):
    yolo = make_yolo_stub(
        [{"bbox": {"x": 5000, "y": 5000, "w": 100, "h": 100}, "class": "figure", "score": 0.7}]
    )
    vlm = VlmStub()  # would 400 on an unexpected call — none should happen

    figures = run_extract([make_frame(tmp_path, contains_graph=True)], yolo, vlm, tmp_path)
    assert figures == []
    assert len(vlm.requests) == 0


# ── routing flags: unflagged frames skip detection entirely ───────────────────


def test_unflagged_frame_becomes_keyframe_without_model_calls(tmp_path):
    yolo = make_yolo_stub([])
    vlm = VlmStub()

    frame = make_frame(tmp_path, frame_type="face")
    figures = run_extract([frame], yolo, vlm, tmp_path)

    assert len(figures) == 1
    assert figures[0].kind == "keyframe"
    assert figures[0].bbox is None
    assert figures[0].struct is None
    assert len(yolo.requests) == 0
    assert len(vlm.requests) == 0


# ── ADR 0004 §4 stage attribution on failures ─────────────────────────────────


def test_yolo_failure_attributes_to_detect_stage(tmp_path):
    from model_clients import STAGE_DETECT, ModelEndpointError

    yolo = make_yolo_stub([])
    yolo.script_error(422, "bad_image", "cannot decode image")
    vlm = VlmStub()

    with pytest.raises(ModelEndpointError) as excinfo:
        run_extract([make_frame(tmp_path, contains_graph=True)], yolo, vlm, tmp_path)
    assert excinfo.value.stage == STAGE_DETECT


def test_vlm_failure_attributes_to_recognize_stage(tmp_path):
    from model_clients import STAGE_RECOGNIZE, ModelEndpointError

    yolo = make_yolo_stub([{"bbox": {"x": 0, "y": 0, "w": 50, "h": 50}, "class": "figure", "score": 0.5}])
    vlm = VlmStub()
    vlm.script_status(400)

    with pytest.raises(ModelEndpointError) as excinfo:
        run_extract([make_frame(tmp_path, contains_graph=True)], yolo, vlm, tmp_path)
    assert excinfo.value.stage == STAGE_RECOGNIZE


# ── multi-frame / multi-box ───────────────────────────────────────────────────


def test_multiple_boxes_yield_multiple_figures(tmp_path):
    yolo = make_yolo_stub(
        [
            {"bbox": {"x": 0, "y": 0, "w": 100, "h": 80}, "class": "figure", "score": 0.8},
            {"bbox": {"x": 150, "y": 50, "w": 100, "h": 80}, "class": "table", "score": 0.3},
        ]
    )
    vlm = VlmStub()
    vlm.script_content(
        CHART_REPLY,
        '{"kind": "diagram", "struct": {"nodes": ["a", "b"]}, "confidence": 0.75}',
    )

    figures = run_extract([make_frame(tmp_path, contains_graph=True)], yolo, vlm, tmp_path)
    assert [f.kind for f in figures] == ["chart", "diagram"]
    assert figures[0].cv_figure_id != figures[1].cv_figure_id
