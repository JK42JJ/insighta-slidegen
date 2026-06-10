"""Stub of the DocLayout-YOLO FastAPI endpoint (contract §3).

Implements POST /detect and GET /health byte-for-byte as an httpx.MockTransport
handler, including the §3.4 error shape {"status", "code", "message"} and the
§3.2 request semantics (conf_threshold default LOW = over-detect, max_boxes).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import httpx

DEFAULT_TOKEN = "stub-yolo-token"
DEFAULT_MODEL_VERSION = "doclayout-yolo-stub-0001"
# §3.2 default: LOW threshold = over-detect (ADR 0002 D2, recall-first).
DEFAULT_CONF_THRESHOLD = 0.15
DEFAULT_MAX_BOXES = 50

# Default detections: pixel bboxes; `class` values are intentionally varied —
# including non-vocabulary ones — because class is ADVISORY ONLY (§3.4) and the
# client must carry every box through regardless of its class.
DEFAULT_BOXES = [
    {"bbox": {"x": 100, "y": 80, "w": 640, "h": 360}, "class": "table", "score": 0.82},
    {"bbox": {"x": 900, "y": 200, "w": 400, "h": 300}, "class": "figure", "score": 0.42},
    {"bbox": {"x": 60, "y": 700, "w": 800, "h": 120}, "class": "isolate_formula", "score": 0.2},
]


def yolo_error_body(status: int, code: str, message: str) -> dict:
    """§3.4 error shape."""
    return {"status": status, "code": code, "message": message}


@dataclass
class _ErrorStep:
    status: int
    body: dict


@dataclass
class YoloStub:
    """Scriptable in-process DocLayout-YOLO stub.

    Returns `boxes` filtered by the request's conf_threshold and capped at
    max_boxes (over-detect semantics are therefore observable: a lower
    threshold returns more boxes). `script_error(...)` queues failure steps.
    """

    token: str = DEFAULT_TOKEN
    model_version: str = DEFAULT_MODEL_VERSION
    image_w: int = 1920
    image_h: int = 1080
    boxes: list[dict] = field(default_factory=lambda: [dict(b) for b in DEFAULT_BOXES])
    requests: list[httpx.Request] = field(default_factory=list)
    _script: list[_ErrorStep] = field(default_factory=list)

    def script_error(self, status: int, code: str, message: str) -> None:
        self._script.append(_ErrorStep(status, yolo_error_body(status, code, message)))

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)

    def request_payloads(self) -> list[dict]:
        return [json.loads(r.content) for r in self.requests if r.content]

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)

        if request.headers.get("Authorization") != f"Bearer {self.token}":
            return httpx.Response(
                401, json=yolo_error_body(401, "unauthorized", "invalid bearer token")
            )

        if request.method == "GET" and request.url.path == "/health":
            return httpx.Response(
                200, json={"status": "ok", "model_version": self.model_version}
            )

        if request.method == "POST" and request.url.path == "/detect":
            if self._script:
                step = self._script.pop(0)
                return httpx.Response(step.status, json=step.body)
            payload = json.loads(request.content)
            image_url = payload.get("image_url")
            if not image_url:
                return httpx.Response(
                    422,
                    json=yolo_error_body(422, "missing_image_url", "image_url is required"),
                )
            conf = payload.get("conf_threshold", DEFAULT_CONF_THRESHOLD)
            max_boxes = payload.get("max_boxes", DEFAULT_MAX_BOXES)
            selected = [b for b in self.boxes if b["score"] >= conf][:max_boxes]
            return httpx.Response(
                200,
                json={
                    "image": {"w": self.image_w, "h": self.image_h},
                    "model_version": self.model_version,
                    "boxes": selected,
                },
            )

        return httpx.Response(404, json=yolo_error_body(404, "not_found", "no such route"))
