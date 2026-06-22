"""⑤ numerize ASYNC JOB — sync /numerize는 60s 안에 불가(단일 ts=148s, cv_extract
Qwen VLM ~137s가 본질 비용). /slides/* job 패턴을 미러해 60s 벽을 우회한다.
client(insighta numerize-client)는 POST → poll(status) → result.

본문은 기존 numerize()와 100% 동일한 CV 파이프라인 — 결정성·fail-closed·게이트·
select-bypass 전부 불변. job 래퍼 + progress(acquire/extract_candidates/cv_extract)만 추가.

배포(app.py 2줄):
    import numerize_job
    numerize_job.register(app, _build_extraction_clients, cv_extract_figures,
                          StatusResponse, NumerizeFigure, SLIDEGEN_MODE)
"""
import uuid
from fastapi import HTTPException, BackgroundTasks
from pydantic import BaseModel

from acquire import download_frames
from frames import extract_candidates
from preselect import preselect_candidates
from typing_select import SelectedFrame

NUMERIZE_WINDOW_SEC = 10.0
NUMERIZE_MAX_FRAMES = 4
_numerize_jobs: dict[str, dict] = {}


class NumerizeJobRequest(BaseModel):
    video_id: str
    ts: list[int]
    mode: str = "prod"


class NumerizeJobResponse(BaseModel):
    job_id: str


def run_numerize(job_id: str, req: NumerizeJobRequest, build_clients, cv_extract) -> None:
    """기존 numerize() 본문 + 단계별 progress. 예외는 failure_stage로 귀속(fail-closed)."""
    job = _numerize_jobs[job_id]
    try:
        job.update(status="running", stage="acquire", progress_pct=5.0)
        sections = [
            {"index": i,
             "from_sec": max(0.0, float(t) - NUMERIZE_WINDOW_SEC),
             "to_sec": float(t) + NUMERIZE_WINDOW_SEC}
            for i, t in enumerate(req.ts)
        ]
        frames_dir = download_frames(req.video_id, sections)

        job.update(stage="extract_candidates", progress_pct=20.0)
        candidates = extract_candidates(frames_dir / "video.mp4")
        yolo, vlm = build_clients()
        gated = preselect_candidates(candidates, yolo=yolo)
        candidates = gated if gated else candidates
        windows = [(s["from_sec"], s["to_sec"]) for s in sections]
        in_window = [c for c in candidates if any(lo <= c.timestamp_sec <= hi for lo, hi in windows)]
        candidates = (in_window or candidates)[:NUMERIZE_MAX_FRAMES]

        job.update(stage="cv_extract", progress_pct=40.0)
        selected = [
            SelectedFrame(candidate=c, contains_graph=True, contains_equation=True,
                          frame_type="figure", summary_hint=None, is_topic_aligned=False,
                          nearest_topic_point=None, selection_score=1.0)
            for c in candidates
        ]
        figures = cv_extract(selected, yolo=yolo, vlm=vlm, out_dir=frames_dir / "crops")
        job.update(status="done", stage="done", progress_pct=100.0, figures=[
            {"kind": f.kind, "ts_sec": f.timestamp_sec, "struct": f.struct,
             "latex": f.extracted_latex, "asset_path": f.png_path,
             "verification_status": f.verification_status}
            for f in figures
        ])
    except Exception as e:  # fail-closed: 단계 귀속 + 에러 메시지(잘라서)
        job.update(status="error", failure_stage=job.get("stage"), error=str(e)[:300])


def register(app, build_clients, cv_extract, StatusResponse, NumerizeFigure, slidegen_mode):
    @app.post("/numerize/job", response_model=NumerizeJobResponse)
    def numerize_job(req: NumerizeJobRequest, background_tasks: BackgroundTasks):
        if req.mode == "prod" and slidegen_mode == "dev":
            raise HTTPException(status_code=400,
                                detail="Vision API disabled in dev mode (SLIDEGEN_MODE=dev)")
        job_id = str(uuid.uuid4())
        _numerize_jobs[job_id] = {"status": "queued", "progress_pct": 0.0,
                                  "stage": "queued", "figures": []}
        background_tasks.add_task(run_numerize, job_id, req, build_clients, cv_extract)
        return NumerizeJobResponse(job_id=job_id)

    @app.get("/numerize/job/status", response_model=StatusResponse)
    def numerize_job_status(job_id: str):
        job = _numerize_jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"job_id {job_id} not found")
        return StatusResponse(job_id=job_id, status=job["status"], progress_pct=job["progress_pct"],
                              error=job.get("error"), stage=job.get("stage"),
                              failure_stage=job.get("failure_stage"))

    @app.get("/numerize/job/result")
    def numerize_job_result(job_id: str):
        job = _numerize_jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"job_id {job_id} not found")
        if job["status"] != "done":
            raise HTTPException(status_code=409, detail=f"job not done (status={job['status']})")
        return {"job_id": job_id, "figures": [NumerizeFigure(**f).model_dump() for f in job["figures"]]}
