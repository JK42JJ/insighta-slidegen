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
import sys
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

# ── deck_tools sys.path injection ─────────────────────────────────────────────
# render_figure_svg (deck_tools.svg_output) lives in the py/ package which is
# NOT installed in the service venv — it is a co-located sibling directory.
# Direct import (Python→Python) is used here instead of the subprocess path
# that build_deck_service.js uses: that JS→Python boundary requires execFileSync
# because Node.js cannot import Python natively.  For this Python FastAPI
# service, a direct import is simpler, faster, and avoids a shell round-trip.
# SLIDEGEN_PY_DIR (same env var deck_build_job.py uses) is the preferred source;
# the Path(__file__) fallback keeps the dev/test environment working without
# the variable set.
_py_dir_env = os.environ.get("SLIDEGEN_PY_DIR", "")
_PY_DIR = Path(_py_dir_env) if _py_dir_env else Path(__file__).parent.parent.parent / "py"
if str(_PY_DIR) not in sys.path and _PY_DIR.is_dir():
    sys.path.insert(0, str(_PY_DIR))

from acquire import download_frames
from frames import extract_candidates
from preselect import preselect_candidates
from captions import detect_topic_changes
from typing_select import SelectedFrame, select_keyframes
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
# ⑤ get-or-extract COMPUTE contract (insighta numerize-client calls this)
# ----------------------------------------------------------------

# ± window (sec) acquired around each requested timestamp for the figure scan.
NUMERIZE_WINDOW_SEC = 10.0
# Cap on candidate frames numerized per request. YOLO over-detects (~15-20 boxes
# per content slide) and each box is a Qwen call, so a tight frame cap keeps the
# synchronous call within the demo timeout while still covering the windows.
NUMERIZE_MAX_FRAMES = 4


class NumerizeRequest(BaseModel):
    """insighta ⑤ numerize-client request: figure data for a video at timestamps."""

    video_id: str
    ts: list[int]
    mode: str = "prod"


class NumerizeFigure(BaseModel):
    """One extracted figure's DATA (not a rendered asset) — the ⑤ cache row shape."""

    kind: str
    ts_sec: int | None = None
    struct: dict | None = None
    latex: str | None = None
    asset_path: str | None = None
    verification_status: str = "pending"


class NumerizeResponse(BaseModel):
    figures: list[NumerizeFigure]


# ── /render-figure ────────────────────────────────────────────────────────────

class RenderFigureRequest(BaseModel):
    """CPU-only SVG render request: figure kind + mode-B struct."""

    kind: str
    struct: dict


class RenderFigureResponse(BaseModel):
    """Inline SVG string, or null when the struct is unrenderable."""

    svg: str | None


# ----------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    """Returns service health and active mode. Always 200 when server is up."""
    return {"status": "ok", "mode": SLIDEGEN_MODE}


@app.post("/render-figure", response_model=RenderFigureResponse)
def render_figure(req: RenderFigureRequest) -> RenderFigureResponse:
    """CPU-only: render a mode-B figure struct to an inline SVG string.

    Calls deck_tools.svg_output.render_figure_svg (graphviz dot + matplotlib;
    no GPU, no vLLM, no YOLO).  Fail-closed: any exception → {svg: null} so
    the note path is never crashed by a bad struct.

    Returns:
        {svg: "<SVG string>"}  for diagram/chart with renderable struct.
        {svg: null}            for table/equation (rendered note-side) or on
                               any degenerate/unsupported struct or error.
    """
    try:
        from deck_tools.svg_output import render_figure_svg  # noqa: PLC0415

        svg = render_figure_svg(req.kind, req.struct)
        return RenderFigureResponse(svg=svg)
    except Exception as exc:  # noqa: BLE001 — fail-closed, never 500-crash the note path
        sys.stderr.write(f"render_figure error kind={req.kind!r}: {exc!r}\n")
        return RenderFigureResponse(svg=None)


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


@app.post("/numerize", response_model=NumerizeResponse)
def numerize(req: NumerizeRequest) -> NumerizeResponse:
    """⑤ get-or-extract COMPUTE: {video_id, ts:[]} → figures with struct/latex.

    Synchronous adapter for the insighta ⑤ contract. Acquires a short window
    around each ts, then runs the SAME CV pipeline as /slides/generate
    (acquire → frames → preselect → select → YOLO + Qwen numerize) and returns
    per-figure EXTRACTED DATA (struct / latex). insighta ⑤ persists these to its
    video_figure_snapshots cache — slidegen never writes that table (slide_* only).
    Fail-closed: figure_extract's gates drop non-figures, so only real figures
    (chart/diagram/table/equation/keyframe) are returned; nothing is fabricated.
    """
    if req.mode == "prod" and SLIDEGEN_MODE == "dev":
        raise HTTPException(
            status_code=400, detail="Vision API disabled in dev mode (SLIDEGEN_MODE=dev)"
        )
    sections = [
        {
            "index": i,
            "from_sec": max(0.0, float(t) - NUMERIZE_WINDOW_SEC),
            "to_sec": float(t) + NUMERIZE_WINDOW_SEC,
        }
        for i, t in enumerate(req.ts)
    ]
    frames_dir = download_frames(req.video_id, sections)
    candidates = extract_candidates(frames_dir / "video.mp4")
    yolo, vlm = _build_extraction_clients()
    gated = preselect_candidates(candidates, yolo=yolo)
    candidates = gated if gated else candidates
    # extract_candidates scans the WHOLE video; ⑤ only wants figures near the
    # requested timestamps. Restrict to candidates inside a requested window, then
    # cap the count — without this, the select-bypass below YOLO+Qwens every frame
    # of the video (~18 boxes each) and a dense talk blows past the sync timeout.
    windows = [(s["from_sec"], s["to_sec"]) for s in sections]
    in_window = [c for c in candidates if any(lo <= c.timestamp_sec <= hi for lo, hi in windows)]
    # Figure-RANKED pick (not chronological first-N): rank by figure-box count desc
    # (preselect attached it from the same YOLO pass — no extra detect), ts asc to
    # break ties. The first-N pick grabbed section-intro text/title slides → kind=text
    # → 0 figures; ranking surfaces the figure-bearing frames in the window instead.
    # CP505 — NO whole-video fallback. If no figure-candidate falls in the requested
    # windows, return 0 figures (honest "no figure near these ts"). The prior
    # `in_window or candidates` returned the best figure from ANYWHERE in the video
    # (e.g. ts=619 for a request at 228-420) → a wrong-segment figure poisoned the
    # SHARED video_figure_snapshots base cache (note/deck/newsletter all consume it).
    # ts fidelity > recall: caller's requested ts is trusted (subtitle-grounded).
    candidates = sorted(
        in_window,
        key=lambda c: (-getattr(c, "fig_box_count", 0), c.timestamp_sec),
    )[:NUMERIZE_MAX_FRAMES]
    # ⑤ COMPUTE bypasses typing_select.select_keyframes: on a figure-rich video
    # select flagged 0 figure-bearing frames (its VLM mode-A routing dropped real
    # tables/diagrams — root-cause is a select backlog item). /numerize's job is
    # to EXTRACT figures from the requested windows, so flag EVERY candidate and
    # let extract_figures' own quality gates do the rejecting — conf floor +
    # struct consistency + the R3 over-generation guard. Fail-closed is preserved:
    # a non-figure crop still gets dropped (text/ui_badge reject), nothing fabricated.
    selected = [
        SelectedFrame(
            candidate=c,
            contains_graph=True,
            contains_equation=True,
            frame_type="figure",
            summary_hint=None,
            is_topic_aligned=False,
            nearest_topic_point=None,
            selection_score=1.0,
        )
        for c in candidates
    ]
    figures = cv_extract_figures(selected, yolo=yolo, vlm=vlm, out_dir=frames_dir / "crops")
    return NumerizeResponse(
        figures=[
            NumerizeFigure(
                kind=f.kind,
                ts_sec=f.timestamp_sec,
                struct=f.struct,
                latex=f.extracted_latex,
                asset_path=f.png_path,
                verification_status=f.verification_status,
            )
            for f in figures
        ]
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

        # Step 2b: preselect (cheap content-box prefilter, select-before-extract).
        # Drop candidates with NO real slide content via a cheap DocLayout-YOLO
        # pass BEFORE the (expensive) VLM router, so it runs on fewer frames.
        # Reuses the SAME yolo client as figure_extract (built once here). Stage
        # stays "keyframe". Recall-first starve-guard: if the gate would empty the
        # set (e.g. a detector failure storm), keep all candidates and let the VLM
        # router decide. The content-box gate has no person sub-gate (no detector
        # in this service); the VLM router makes the person-vs-slide fine call.
        yolo, vlm = _build_extraction_clients()
        before = len(candidates)
        gated = preselect_candidates(candidates, yolo=yolo)
        candidates = gated if gated else candidates
        sys.stderr.write(
            f"preselect: {before} -> {len(candidates)} candidates "
            f"({before - len(candidates)} dropped)\n"
        )

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
        # selected frames only. Reuses the yolo+vlm clients built at step 2b
        # (env-gated: http opt-in → live contract endpoints; default → mocks).
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


# ----------------------------------------------------------------
# ⑤ numerize ASYNC JOB — sync /numerize는 60s 안에 불가(단일 ts≈148s, cv_extract
# Qwen VLM이 본질 비용). /slides/* job 패턴을 미러해 60s 벽을 우회(client가 poll).
# ----------------------------------------------------------------
import numerize_job

numerize_job.register(
    app, _build_extraction_clients, cv_extract_figures, StatusResponse, NumerizeFigure, SLIDEGEN_MODE
)


# ----------------------------------------------------------------
# 덱 빌드 ASYNC JOB — book_json → .pptx (결정성 규칙 매퍼, LLM auto-route 0,
# fail-closed). insighta D build-call의 타깃. build_deck_service.js를 subprocess.
# ----------------------------------------------------------------
import deck_build_job

deck_build_job.register(app, StatusResponse)
