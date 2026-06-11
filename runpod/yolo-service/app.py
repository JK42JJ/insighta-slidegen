"""DocLayout-YOLO serving wrapper (CONTRACT_model-endpoints §3) — RunPod pod.

Endpoints (all Bearer-authenticated against $YOLO_KEY):
    POST /detect {image_url, conf_threshold?, max_boxes?}
        → fetch the presigned GET url → YOLOv10 inference →
          {"image": {"w", "h"}, "model_version", "boxes":
           [{"bbox": {"x", "y", "w", "h"}, "class", "score"}]}  (pixels)
    GET  /health → {"status": "ok", "model_version"}

Over-detection is intentional (§3.4): recall is the only unrecoverable
failure; the conf default is LOW (0.15) and `class` stays advisory-only —
Qwen cleans up false boxes downstream.

Run (see runpod/INSTALL.md):
    YOLO_KEY=... uvicorn app:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import base64
import io
import os
import re
import threading

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from PIL import Image
from pydantic import BaseModel, Field

MODEL_REPO = "juliozhao/DocLayout-YOLO-DocStructBench"
MODEL_FILE = "doclayout_yolo_docstructbench_imgsz1024.pt"
MODEL_VERSION = "doclayout-yolo-docstructbench-imgsz1024"
IMG_SIZE = 1024

# §3.4 over-detect default: LOW threshold on purpose; callers may override.
DEFAULT_CONF_THRESHOLD = 0.15
DEFAULT_MAX_BOXES = 50
FETCH_TIMEOUT_SEC = 30.0

# PR-H2: the CV service ships frames/crops as base64 data URLs (the same
# call shape vlm_router uses toward Qwen) — httpx cannot fetch the data:
# scheme, so it is decoded inline here. Presigned-GET migration for BOTH
# model paths (contract §4 strict) is a deferred follow-up.
DATA_URL_SCHEME = "data:"
DATA_URL_BASE64_MARKER = ";base64"


def _load_image_bytes(image_url: str) -> bytes:
    """Image bytes from a presigned GET url OR an inline base64 data url."""
    if image_url.startswith(DATA_URL_SCHEME):
        header, _, payload = image_url.partition(",")
        if DATA_URL_BASE64_MARKER not in header or not payload:
            raise ValueError("unsupported data url (expected ';base64,<payload>')")
        return base64.b64decode(payload)
    response = httpx.get(image_url, timeout=FETCH_TIMEOUT_SEC, follow_redirects=True)
    response.raise_for_status()
    return response.content

app = FastAPI(title="slidegen-yolo", version=MODEL_VERSION)

_model = None
_model_lock = threading.Lock()


def _get_model():
    """Lazy-load the model once (first request or warmup)."""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from doclayout_yolo import YOLOv10
                from huggingface_hub import hf_hub_download

                weights = hf_hub_download(repo_id=MODEL_REPO, filename=MODEL_FILE)
                _model = YOLOv10(weights)
    return _model


def _check_auth(authorization: str | None = Header(default=None)) -> None:
    expected = os.environ.get("YOLO_KEY", "")
    if not expected:
        raise HTTPException(status_code=500, detail="YOLO_KEY is not configured on the pod")
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="invalid bearer token")


class DetectRequest(BaseModel):
    image_url: str
    conf_threshold: float = Field(default=DEFAULT_CONF_THRESHOLD, ge=0.0, le=1.0)
    max_boxes: int = Field(default=DEFAULT_MAX_BOXES, ge=1)


@app.get("/health")
def health(_: None = Depends(_check_auth)) -> dict:
    return {"status": "ok", "model_version": MODEL_VERSION}


@app.post("/detect")
def detect(req: DetectRequest, _: None = Depends(_check_auth)) -> dict:
    # 1) Load the frame: presigned GET url (the pod NEVER holds AWS
    #    credentials — §4 backend-only presign issuance) or inline data url.
    try:
        image = Image.open(io.BytesIO(_load_image_bytes(req.image_url))).convert("RGB")
    except Exception as exc:  # noqa: BLE001 — single fetch boundary
        # Mask any url (presigned GET carries a signature) out of the detail.
        detail = re.sub(r"(https?|data):\S+", "<url>", str(exc))
        raise HTTPException(status_code=422, detail=f"image fetch failed: {detail}") from exc

    width, height = image.size

    # 2) Inference (px coords; xyxy → xywh).
    results = _get_model().predict(image, imgsz=IMG_SIZE, conf=req.conf_threshold, verbose=False)
    boxes: list[dict] = []
    if results:
        result = results[0]
        names = getattr(result, "names", {}) or {}
        for box in result.boxes:
            x1, y1, x2, y2 = (float(v) for v in box.xyxy[0].tolist())
            cls_id = int(box.cls[0].item())
            boxes.append(
                {
                    "bbox": {
                        "x": int(round(x1)),
                        "y": int(round(y1)),
                        "w": int(round(x2 - x1)),
                        "h": int(round(y2 - y1)),
                    },
                    "class": str(names.get(cls_id, cls_id)),
                    "score": round(float(box.conf[0].item()), 4),
                }
            )

    # 3) Highest-score first, capped (§3.3).
    boxes.sort(key=lambda b: b["score"], reverse=True)
    return {
        "image": {"w": width, "h": height},
        "model_version": MODEL_VERSION,
        "boxes": boxes[: req.max_boxes],
    }
