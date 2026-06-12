"""
insighta-slidegen CV microservice — FastAPI :8077

Endpoints:
    GET  /health              → {"status": "ok", "mode": "dev"|"prod"}
    POST /slides/generate     → {"job_id": "..."}
    GET  /slides/status       → {"job_id": ..., "status": ..., "progress_pct": ...}
    GET  /slides/result       → {"job_id": ..., "figures": [...], "keyframe_count": ...,
                                  "resources": {title, transcript, segments,
                                                figureLabels, formulas, charts}}

Mode gate (SLIDEGEN_MODE env var):
    dev  — vision API (Gemini etc.) hard-disabled. Only local CV runs.
           Returns placeholder figures so the TS pipeline can be tested end-to-end.
    prod — full pipeline including optional vision API fallback enabled.

Pipeline (per job) — canonical order (PR-F3 integration):
    1. acquire.py        → download video + extract raw frames for requested sections
    2. frames.py         → PySceneDetect wide-net extraction (~200 candidates)
                           + pHash/time-even CPU downsample (~60) — ADR 0002 D1/D3
    3. captions.py       → load captions, BGE-M3 embed segments, detect topic-change points
    4. typing_select.py  → local VLM router selects ~12-20 keyframes, grounded by
                           the v2 section summaries (HINT only — ADR 0002 D4/D5)
    5. figure_extract.py → YOLO crop + Qwen numerization on the selected frames only
    6. bundle.py         → orchestrate resources bundle (ADR 0003 §3) — stored on
                           the job and returned in /slides/result `resources`

Jobs run in a background thread pool; /slides/status polls the in-memory
job store until done or error.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from acquire import download_frames
from frames import extract_candidates
from captions import detect_topic_changes
from typing_select import select_keyframes
from figure_extract import ExtractedFigure, extract_figures as cv_extract_figures
from bundle import assemble_resources
from observability import StageArtifactSink
from redraw import vector_redraw  # noqa: F401

app = FastAPI(title="insighta-slidegen-cv", version="0.1.0")

SLIDEGEN_MODE = os.environ.get("SLIDEGEN_MODE", "dev")

# In-memory job store — replace with Redis or Supabase for multi-worker prod.
_jobs: dict[str, dict[str, Any]] = {}

# ── ADR 0004 §4 failure-stage attribution (PR-H2) ────────────────────────────
# slide_jobs.stage / failure_stage CHECK domain — MUST stay 1:1 with
# src/types/job-stages.ts and the slidegen-jobs-v2 DDL.
FAILURE_STAGES = {"acquire", "keyframe", "detect", "select", "numerize", "build", "validate"}
# model_clients raises mode-B/C failures as stage="recognize" (§2.3); the DDL
# stage name for that family is "numerize".
STAGE_ALIASES = {"recognize": "numerize"}


def _normalize_failure_stage(exc: Exception, fallback: str | None) -> str | None:
    """Stage a failed run died in: the exception's own attribution
    (ModelEndpointError.stage) wins over the pipeline-step fallback; anything
    outside the DDL domain degrades to None (manual attribution)."""
    raw = getattr(exc, "stage", None) or fallback
    raw = STAGE_ALIASES.get(raw, raw)
    return raw if raw in FAILURE_STAGES else None


# ----------------------------------------------------------------
# Request / Response models
# ----------------------------------------------------------------

class Section(BaseModel):
    index: int
    from_sec: float
    to_sec: float
    # v2 rich-summary section text — grounding input for the Qwen select call
    # (ADR 0002 D5: HINT only, never a keep/drop gate). Defaults = back-compat
    # with callers that send time bounds only.
    title: str = ""
    summary: str | None = None


class GenerateRequest(BaseModel):
    youtube_video_id: str
    sections: list[Section]
    mode: str = "dev"
    # v2 passthrough for the orchestrate resources bundle (bundle.py). Defaults
    # keep pre-PR-F3 callers (time bounds only) working unchanged.
    title: str = ""
    transcript: str = ""
    # Observability: when set, each CV stage dumps its decisions/data here for
    # review. `artifact_index` is the ANONYMOUS label (e.g. "V02") — the real
    # youtube_video_id is never written to the tree (PUBLIC-repo rule). Unset =
    # no dump (existing behavior).
    artifacts_dir: str | None = None
    artifact_index: str = "V00"


class GenerateResponse(BaseModel):
    job_id: str


class StatusResponse(BaseModel):
    job_id: str
    status: str
    progress_pct: float
    error: str | None = None
    # Stage the job is currently running (None until started) — lets the
    # polling client attribute a TIMEOUT to the stage it died in (PR-G
    # timeout convention).
    stage: str | None = None
    # ADR 0004 §4: stage a FAILED job died in (None unless status='error',
    # or when the failure is outside the stage domain — manual attribution).
    failure_stage: str | None = None


class FigureResult(BaseModel):
    cv_figure_id: str
    kind: str
    png_url: str
    vector_pdf_url: str | None = None
    vector_svg_url: str | None = None
    caption: str | None = None
    timestamp_sec: int | None = None
    extraction_conf: float | None = None
    # YOLO crop region in source-frame pixels (slide_figures.bbox shape);
    # None for whole-frame `keyframe` rows.
    bbox: dict | None = None
    # 'unverified' iff extraction_conf < figure_extract.LOW_CONF_THRESHOLD
    # (ADR 0003 D3 / ADR 0004 G3 — flagged, never silently embedded).
    verification_status: str = "pending"


class ResultResponse(BaseModel):
    job_id: str
    figures: list[FigureResult]
    keyframe_count: int
    # Orchestrate resources bundle (bundle.RESOURCE_KEYS shape, JSON-safe):
    # {title, transcript, segments, figureLabels, formulas, charts}.
    # Consumed UNMODIFIED by deck/scripts/orchestrate.js via the node runner.
    resources: dict[str, Any] = Field(default_factory=dict)


# ----------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    """Returns service health and active mode. Always 200 when server is up."""
    return {"status": "ok", "mode": SLIDEGEN_MODE}


@app.post("/slides/generate", response_model=GenerateResponse)
def slides_generate(req: GenerateRequest, background_tasks: BackgroundTasks) -> GenerateResponse:
    """
    Submit a CV extraction job.

    Rejects vision API usage when mode='dev' (hard gate — see module docstring).

    TODO: validate youtube_video_id (11 chars), enforce dev mode gate,
    enqueue _run_pipeline as a background task.
    """
    if req.mode == "prod" and SLIDEGEN_MODE == "dev":
        raise HTTPException(
            status_code=400,
            detail="Vision API disabled in dev mode (SLIDEGEN_MODE=dev)"
        )
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "status": "queued",
        "progress_pct": 0.0,
        "figures": [],
        "keyframe_count": 0,
        "resources": {},
    }
    background_tasks.add_task(_run_pipeline, job_id, req)
    return GenerateResponse(job_id=job_id)


@app.get("/slides/status", response_model=StatusResponse)
def slides_status(job_id: str) -> StatusResponse:
    """Return current job status. 404 if job_id unknown."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"job_id {job_id} not found")
    return StatusResponse(
        job_id=job_id,
        status=job["status"],
        progress_pct=job["progress_pct"],
        error=job.get("error"),
        stage=job.get("stage"),
        failure_stage=job.get("failure_stage"),
    )


@app.get("/slides/result", response_model=ResultResponse)
def slides_result(job_id: str) -> ResultResponse:
    """Return figures once job status='done'. 404 / 409 otherwise."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"job_id {job_id} not found")
    if job["status"] != "done":
        raise HTTPException(status_code=409, detail=f"job not done (status={job['status']})")
    return ResultResponse(
        job_id=job_id,
        figures=[FigureResult(**f) for f in job["figures"]],
        keyframe_count=job["keyframe_count"],
        resources=job.get("resources", {}),
    )


# ----------------------------------------------------------------
# Stage-5 extraction clients (composition root — §5 gating lives here)
# ----------------------------------------------------------------

# Whole-frame mock "detection" box: deliberately larger than any real frame so
# figure_extract._clamp_bbox reduces it to the full image (no model needed).
MOCK_BOX_SPAN = 100_000
MOCK_DETECTOR_VERSION = "mock-yolo-0"
MOCK_VLM_CONFIDENCE = 0.9


class MockYoloClient:
    """Deterministic in-service detector stub — dev/CI default (no model).

    Follows the vlm_router.MockBackend pattern: stable output so the dev
    pipeline produces figures without a GPU or network. Duck-types
    YoloHttpClient (`.detect(image_url) -> DetectResponse`).
    """

    def detect(self, image_url: str):
        from model_clients import DetectResponse

        return DetectResponse.model_validate(
            {
                "image": {"w": MOCK_BOX_SPAN, "h": MOCK_BOX_SPAN},
                "model_version": MOCK_DETECTOR_VERSION,
                "boxes": [
                    {
                        "bbox": {"x": 0, "y": 0, "w": MOCK_BOX_SPAN, "h": MOCK_BOX_SPAN},
                        "class": "figure",
                        "score": MOCK_VLM_CONFIDENCE,
                    }
                ],
            }
        )


class MockVlmClient:
    """Deterministic mode-B/C stub — dev/CI default (vlm_router mock pattern).

    Returns a chart_regen-regenerable line-chart struct (mode B) and a fixed
    LaTeX string (mode C). Duck-types VlmHttpClient's §2.2 methods.
    """

    def classify_crop(
        self, image_url: str, prompt: str, caption_slice: str | None = None
    ) -> dict:
        return {
            "kind": "chart",
            "struct": {
                "chart_type": "line",
                "axes": {"x": "t", "y": "value"},
                "series": [{"name": "mock", "points": [{"x": 0, "y": 0}, {"x": 1, "y": 1}]}],
                "insight": "mock chart (dev placeholder)",
            },
            "confidence": MOCK_VLM_CONFIDENCE,
        }

    def equation_ocr(self, image_url: str, prompt: str) -> dict:
        return {"latex": "y = ax + b", "confidence": MOCK_VLM_CONFIDENCE}


def _build_extraction_clients() -> tuple[Any, Any]:
    """(yolo, vlm) clients for figure_extract — chosen by env (§5 gating).

    SLIDEGEN_VLM_BACKEND=http (explicit opt-in) → live contract clients via
    from_env(), which enforces the dev-mode live-config refusal
    (CONTRACT_model-endpoints §5). Anything else → the deterministic
    in-service mocks above (dev/CI default: no model, no network).
    """
    if os.environ.get("SLIDEGEN_VLM_BACKEND", "").lower() == "http":
        from model_clients import VlmHttpClient, YoloHttpClient

        return YoloHttpClient.from_env(), VlmHttpClient.from_env()
    return MockYoloClient(), MockVlmClient()


def _figure_dict(figure: ExtractedFigure) -> dict:
    """ExtractedFigure → FigureResult-shaped dict for the job store.

    png_url carries the LOCAL crop path in dev — a data source, never a deck
    asset (ADR 0003 P2); presigned upload URLs are the prod orchestrator's
    job (PR-G).
    """
    return {
        "cv_figure_id": figure.cv_figure_id,
        "kind": figure.kind,
        "png_url": figure.png_path,
        "vector_pdf_url": None,
        "vector_svg_url": None,
        "caption": figure.caption,
        "timestamp_sec": figure.timestamp_sec,
        "extraction_conf": figure.extraction_conf,
        "bbox": figure.bbox,
        "verification_status": figure.verification_status,
    }


# ----------------------------------------------------------------
# Background pipeline
# ----------------------------------------------------------------

def _run_pipeline(job_id: str, req: GenerateRequest) -> None:
    """
    Execute the full CV pipeline for a job.

    Steps (each updates _jobs[job_id]["progress_pct"]):
        15%  acquire.download_frames(youtube_video_id, sections)
        30%  frames.extract_candidates(video_path)          → ~60 FrameCandidate
        45%  captions.detect_topic_changes(youtube_video_id) → topic-change points (BGE-M3)
        65%  typing_select.select_keyframes(..., sections=...) → 12-20 SelectedFrame
        80%  figure_extract.extract_figures(selected, yolo=, vlm=) → crops + struct/LaTeX
        95%  bundle.assemble_resources(...) → orchestrate resources bundle
        100% Done — figures + keyframe_count + resources on the job

    On exception: set status='error', error=str(e).
    """
    # ADR 0004 fallback attribution: which DDL stage each pipeline step maps
    # to. A raised ModelEndpointError overrides this with its own .stage.
    stage: str | None = "acquire"
    sink = StageArtifactSink(req.artifacts_dir, req.artifact_index)
    try:
        _jobs[job_id]["status"] = "running"
        _jobs[job_id]["stage"] = stage

        # Step 1: acquire (15%) — download video + extract JPEG frames
        sections = [s.model_dump() for s in req.sections]
        frames_dir = download_frames(req.youtube_video_id, sections)
        _jobs[job_id]["progress_pct"] = 15.0
        stage = "keyframe"
        _jobs[job_id]["stage"] = stage

        # Step 2: frames (30%) — PySceneDetect wide net → CPU downsample (~60).
        # NOTE: acquire does not expose the source's expected duration yet, so
        # the frames.py duration-validation gate stays opt-in (None = skipped).
        # Wire expected_duration_sec= here once acquire returns it.
        video_path = frames_dir / "video.mp4"
        candidates = extract_candidates(video_path)
        _jobs[job_id]["progress_pct"] = 30.0

        # Step 3: captions (45%) — BGE-M3 topic-change detection
        topic_points = detect_topic_changes(req.youtube_video_id, req.mode)
        _jobs[job_id]["progress_pct"] = 45.0
        stage = "select"
        _jobs[job_id]["stage"] = stage

        # Step 4: typing_select (65%) — VLM-routed selection, grounded by the
        # v2 section text (HINT only, never a keep/drop gate — ADR 0002 D5).
        selected = select_keyframes(
            candidates,
            topic_points,
            req.mode,
            sections=sections,
            youtube_video_id=req.youtube_video_id,
        )
        _jobs[job_id]["progress_pct"] = 65.0
        # 01-keyframes / 03-select: candidate count + per-frame routing decision.
        sink.keyframes(len(candidates), selected)
        stage = "numerize"
        _jobs[job_id]["stage"] = stage

        # Step 5: figure_extract (80%) — YOLO crop + Qwen numerization on the
        # selected frames only. Clients are env-gated (http opt-in → live
        # contract endpoints; default → in-service mocks).
        yolo, vlm = _build_extraction_clients()
        figures = cv_extract_figures(
            selected, yolo=yolo, vlm=vlm, out_dir=frames_dir / "crops"
        )
        _jobs[job_id]["progress_pct"] = 80.0
        # 02-detect / 04-numerize: YOLO boxes + struct/LaTeX per figure.
        sink.detect_and_numerize(figures)
        sink.write_manifest()
        # bundle is resource assembly, not a model stage — a failure there is
        # outside the DDL stage domain (None → manual attribution).
        stage = None
        _jobs[job_id]["stage"] = stage

        # Step 6: bundle (95%) — orchestrate resources (TEXT/DATA/LaTeX only;
        # raw frame pixels are banned from the bundle — ADR 0003 P2).
        resources = assemble_resources(
            title=req.title,
            transcript=req.transcript,
            segments=sections,
            selected_frames=selected,
            figures=figures,
        )
        _jobs[job_id]["progress_pct"] = 95.0

        _jobs[job_id].update({
            "status": "done",
            "progress_pct": 100.0,
            "figures": [_figure_dict(f) for f in figures],
            # The ~12-20 SELECTED keyframes — not the ~60 candidates.
            "keyframe_count": len(selected),
            "resources": resources,
        })

    except Exception as exc:
        _jobs[job_id].update({
            "status": "error",
            "error": str(exc),
            "failure_stage": _normalize_failure_stage(exc, stage),
            "progress_pct": 0.0,
        })
