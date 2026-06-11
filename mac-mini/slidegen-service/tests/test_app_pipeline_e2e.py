"""Full-pipeline E2E for app._run_pipeline with scripted mock yolo/vlm (PR-F3).

Runs a SYNTHETIC video through the REAL FastAPI surface (TestClient:
POST /slides/generate → GET /slides/status → GET /slides/result) and asserts
the 5-step data chain in the result:

    ① the wide-net candidate set covers every timeline decile (recall-first,
       ADR 0003 D5)
    ② YOLO boxes (WHERE) are present on the extracted figures
    ③ selection is grounded in the v2 section summaries — the PR-F1
       marker-token pattern, extended to the integrated path: the SAME video
       yields a different selection with vs without the marker summary
    ④ formulas/charts carry extraction conf; low-conf entries are flagged
       `unverified` (never silently embedded — ADR 0003 D3 / ADR 0004 G3)
    ⑤ the resources bundle has exactly the orchestrate contract shape
       {title, transcript, segments, figureLabels, formulas, charts}

plus the integrated raw-frame ban (ADR 0003 P2): no frame/crop path, data URL
or image bytes anywhere in the serialized resources bundle.

Only the ACQUIRE boundary is faked (no yt-dlp/network): a synthetic
cv2-generated video is dropped where acquire would put it. Everything from
frames.extract_candidates onward is the real code under scripted model stubs.

All fixtures are synthetic (PUBLIC repo rule — no real video IDs).
"""

import json

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")
pytest.importorskip("scenedetect")

from fastapi.testclient import TestClient  # noqa: E402

from bundle import RESOURCE_KEYS  # noqa: E402

# Synthetic 11-char id (fixture only — never a real YouTube id).
SYNTH_VIDEO_ID = "synthvid001"
SYNTH_TITLE = "Synthetic Talk Title"
SYNTH_TRANSCRIPT = "synthetic transcript text"

# Marker token the caption-aware routing stub keys its selection on
# (PR-F1 pattern — test_select_section_wiring.py).
MARKER = "SYNTH-ABLATION-TABLE"

# Synthetic video geometry: 10 noise scenes × 3s = 30s → one cut per decile.
FPS = 10
FRAME_SIZE = (320, 240)  # (w, h)
N_SCENES = 10
SCENE_SEC = 3.0
DURATION_SEC = N_SCENES * SCENE_SEC
NUM_DECILES = 10

# Section split: [0, 15) has no marker; [15, 30) carries it (when enabled).
SECTION_SPLIT_SEC = 15.0

LOW_OCR_CONF = 0.4  # < figure_extract.LOW_CONF_THRESHOLD → must be flagged
CHART_CONF = 0.9

CHART_STRUCT = {
    "chart_type": "line",
    "axes": {"x": "epoch", "y": "loss"},
    "series": [{"name": "train", "points": [{"x": 1, "y": 0.9}, {"x": 2, "y": 0.4}]}],
    "insight": "synthetic loss decreases",
}


def _write_video(path) -> None:
    """Write the synthetic scene video as video.mp4 (one cut per decile)."""
    w, h = FRAME_SIZE
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (w, h))
    if not writer.isOpened():
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), FPS, (w, h))
    if not writer.isOpened():
        pytest.skip("OpenCV build cannot write video.mp4")
    for scene in range(N_SCENES):
        frame = np.random.RandomState(42 + scene).randint(0, 256, (h, w, 3), dtype=np.uint8)
        for _ in range(int(round(SCENE_SEC * FPS))):
            writer.write(frame)
    writer.release()


class MarkerRoutingBackend:
    """Scripted select-stage VLM: keeps a window's frames ONLY when the
    window's section text mentions MARKER (PR-F1 behavioral pattern), and
    flags them contains_graph so they enter the crop pipeline."""

    def route(self, candidates, captions_text=None):
        keep = bool(captions_text) and MARKER in captions_text
        return [
            {
                "is_slide": keep,
                "contains_graph": keep,
                "contains_equation": False,
                "frame_type": "chart",
                "summary_hint": f"synthetic slide at {c.timestamp_sec:.0f}s",
                "confidence": 0.9,
            }
            for c in candidates
        ]


class ScriptedYolo:
    """Scripted detector (WHERE): two boxes per flagged frame — one chart
    region and one equation region. `class` stays advisory-only."""

    def __init__(self):
        self.calls = 0

    def detect(self, image_url: str):
        from model_clients import DetectResponse

        self.calls += 1
        w, h = FRAME_SIZE
        return DetectResponse.model_validate(
            {
                "image": {"w": w, "h": h},
                "model_version": "scripted-yolo",
                "boxes": [
                    {"bbox": {"x": 10, "y": 10, "w": 120, "h": 80}, "class": "figure", "score": 0.8},
                    {
                        "bbox": {"x": 150, "y": 120, "w": 100, "h": 40},
                        "class": "isolate_formula",
                        "score": 0.3,
                    },
                ],
            }
        )


class ScriptedVlm:
    """Scripted mode-B/C VLM (WHAT): box 1 of each frame → high-conf chart;
    box 2 → equation, whose mode-C OCR returns LOW conf (must be flagged)."""

    def __init__(self):
        self.classify_calls = 0
        self.ocr_calls = 0

    def classify_crop(self, image_url, prompt, caption_slice=None):
        self.classify_calls += 1
        if self.classify_calls % 2 == 1:
            return {"kind": "chart", "struct": CHART_STRUCT, "confidence": CHART_CONF}
        return {"kind": "equation", "struct": {}, "confidence": 0.8}

    def equation_ocr(self, image_url, prompt):
        self.ocr_calls += 1
        return {"latex": "\\sum_i x_i", "confidence": LOW_OCR_CONF}


def _sections(marker: bool) -> list[dict]:
    method_summary = (
        f"Synthetic method section showing the {MARKER} results."
        if marker
        else "Synthetic method section with plain narration."
    )
    return [
        {
            "index": 0,
            "from_sec": 0.0,
            "to_sec": SECTION_SPLIT_SEC,
            "title": "Intro",
            "summary": "Synthetic intro with no figures.",
        },
        {
            "index": 1,
            "from_sec": SECTION_SPLIT_SEC,
            "to_sec": DURATION_SEC,
            "title": "Method",
            "summary": method_summary,
        },
    ]


@pytest.fixture
def pipeline(monkeypatch, tmp_path):
    """Patch the acquire boundary + model backends; return a job runner."""
    import app as app_module
    import vlm_router

    # 1) acquire boundary: drop a synthetic video where acquire would.
    def fake_download_frames(youtube_video_id, sections, output_root="/tmp/slidegen-frames"):
        frames_dir = tmp_path / "acquired" / youtube_video_id
        frames_dir.mkdir(parents=True, exist_ok=True)
        video_path = frames_dir / "video.mp4"
        if not video_path.exists():
            _write_video(video_path)
        return frames_dir

    monkeypatch.setattr(app_module, "download_frames", fake_download_frames)

    # 2) spy on the wide net so decile coverage (①) is assertable.
    spies = {"yolo": ScriptedYolo(), "vlm": ScriptedVlm(), "candidates": None}
    real_extract_candidates = app_module.extract_candidates

    def candidates_spy(video_path, *args, **kwargs):
        out = real_extract_candidates(video_path, *args, **kwargs)
        spies["candidates"] = out
        return out

    monkeypatch.setattr(app_module, "extract_candidates", candidates_spy)

    # 3) scripted select-stage routing (③) + scripted yolo/vlm (②/④).
    monkeypatch.setattr(vlm_router, "get_backend", lambda *a, **k: MarkerRoutingBackend())
    monkeypatch.setattr(
        app_module, "_build_extraction_clients", lambda: (spies["yolo"], spies["vlm"])
    )

    client = TestClient(app_module.app)

    def run(marker: bool) -> dict:
        response = client.post(
            "/slides/generate",
            json={
                "youtube_video_id": SYNTH_VIDEO_ID,
                "sections": _sections(marker),
                "mode": "dev",
                "title": SYNTH_TITLE,
                "transcript": SYNTH_TRANSCRIPT,
            },
        )
        assert response.status_code == 200
        job_id = response.json()["job_id"]

        status = client.get("/slides/status", params={"job_id": job_id}).json()
        assert status["status"] == "done", f"pipeline failed: {status.get('error')}"
        assert status["progress_pct"] == 100.0

        return client.get("/slides/result", params={"job_id": job_id}).json()

    return type("Pipeline", (), {"run": staticmethod(run), "spies": spies})


def test_full_pipeline_five_step_data_chain(pipeline):
    result = pipeline.run(marker=True)
    resources = result["resources"]

    # ① wide-net candidate set covers every timeline decile (recall-first).
    candidates = pipeline.spies["candidates"]
    assert candidates, "extract_candidates produced no candidates"
    assert {c.section_index for c in candidates} == set(range(NUM_DECILES))

    # ② YOLO boxes present: every chart/equation figure carries its crop bbox.
    assert pipeline.spies["yolo"].calls > 0
    cropped = [f for f in result["figures"] if f["kind"] in ("chart", "equation")]
    assert cropped, "no cropped figures were extracted"
    for figure in cropped:
        assert figure["bbox"] is not None
        assert set(figure["bbox"]) == {"x", "y", "w", "h"}

    # ③ selection grounded in section summaries: only frames of the
    # marker-carrying Method window ([15, 30)s) were selected.
    labels = resources["figureLabels"]
    assert labels, "marker run selected no frames"
    assert all(label["ts"] >= SECTION_SPLIT_SEC for label in labels)
    assert result["keyframe_count"] == len(labels)

    # ④ formulas/charts carry conf; low-conf entries are flagged unverified.
    assert resources["charts"] and resources["formulas"]
    for chart in resources["charts"]:
        assert chart["conf"] == CHART_CONF
        assert chart["verification_status"] == "pending"
        assert chart["struct"] == CHART_STRUCT
    for formula in resources["formulas"]:
        assert formula["conf"] == LOW_OCR_CONF  # < 0.7
        assert formula["verification_status"] == "unverified"
        assert formula["latex"] == "\\sum_i x_i"

    # ⑤ bundle shape == the exact orchestrate resources contract.
    assert set(resources) == set(RESOURCE_KEYS)
    assert resources["title"] == SYNTH_TITLE
    assert resources["transcript"] == SYNTH_TRANSCRIPT
    assert resources["segments"] == _sections(marker=True)


def test_resources_uphold_raw_frame_ban_on_integrated_path(pipeline):
    """ADR 0003 P2 extended to the integrated path: the serialized bundle
    carries TEXT + DATA + LaTeX only — never frame/crop paths, data URLs or
    image bytes (extends the PR-F2 structural ban test)."""
    serialized = json.dumps(pipeline.run(marker=True)["resources"])
    for banned in (".png", ".jpeg", ".jpg", "data:image", "png_path", "/tmp/"):
        assert banned not in serialized


def test_selection_changes_with_vs_without_marker_summary(pipeline):
    """③ behavioral regression-block (PR-F1 marker pattern, integrated): the
    SAME synthetic video yields a different selection when the section
    summaries change — a frames-only wiring regression would make both runs
    identical."""
    with_marker = pipeline.run(marker=True)
    without_marker = pipeline.run(marker=False)

    assert with_marker["resources"]["figureLabels"] != []
    assert without_marker["resources"]["figureLabels"] == []
    assert without_marker["resources"]["charts"] == []
    assert without_marker["resources"]["formulas"] == []
    assert without_marker["keyframe_count"] == 0
    assert with_marker["keyframe_count"] > 0
