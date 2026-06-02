"""Pluggable backend for the local VLM router (ADR 0001).

The merged Phase-2 scaffold (`typing_select.py`) hardcoded an MLX-only runtime,
which cannot run off Apple Silicon — the Windows dev box is torch-CPU-only (no
MLX), so the router could not be exercised at all there. This module adds a
backend selected by the SLIDEGEN_VLM_BACKEND env var:

    mock         (default) — deterministic, no model, no GPU. dev / CI / Windows.
    transformers           — HuggingFace transformers (CUDA or CPU). Kaggle GPU
                             eval sandbox; also a non-Apple prod option.
    mlx                    — mlx_vlm on Apple Silicon. prod + Mac eval (ADR D9).

`new env default = existing behavior`: unset → mock, so nothing runs a heavy
model unless explicitly opted in. The LLM-API ban is upheld — every backend is
a local open-weights model, never an API call.

Each backend returns one routing dict per input frame, in input order, matching
the ADR 0001 routing JSON contract:

    {is_slide, contains_graph, contains_equation, frame_type, summary_hint, confidence}

`typing_select._route_with_vlm` maps these onto RoutingMetadata. Keeping the
backend output as plain dicts avoids a circular import with typing_select.
"""

from __future__ import annotations

import json
import os
import re
from typing import Protocol

from frames import FrameCandidate

# Backend + model selection (tuning knobs, not secrets — safe to print / public).
ENV_BACKEND = "SLIDEGEN_VLM_BACKEND"
ENV_MODEL = "SLIDEGEN_VLM_MODEL"
DEFAULT_BACKEND = "mock"
# 7B default; 3B is the memory fallback (ADR 0001 D9) via SLIDEGEN_VLM_MODEL.
DEFAULT_MODEL = "qwen2.5-vl-7b-instruct"

# Allowed frame_type values (mirrors RoutingMetadata.frame_type in typing_select).
VALID_FRAME_TYPES = ("title_card", "diagram", "chart", "table", "face", "b_roll")
_FALLBACK_FRAME_TYPE = "b_roll"

# Zero-shot routing prompt (ADR 0001: training-free v1, JSON-only output).
ROUTING_PROMPT = (
    "You route video keyframes for a slide-generation pipeline. You are given "
    "candidate frames in timestamp order. For EACH frame, in the same order, "
    "decide whether it is a knowledge-bearing slide and describe its content. "
    "Return ONLY a JSON array of exactly {n} objects, no prose. Each object: "
    '{{"is_slide": bool, "contains_graph": bool, "contains_equation": bool, '
    '"frame_type": one of '
    '"title_card"|"diagram"|"chart"|"table"|"face"|"b_roll", '
    '"summary_hint": short string, "confidence": float 0..1}}.'
)


class VLMRouterBackend(Protocol):
    """A backend that routes candidate frames to per-frame routing dicts."""

    def route(self, candidates: list[FrameCandidate]) -> list[dict]:
        ...


def _normalize(raw: dict, candidate: FrameCandidate) -> dict:
    """Coerce a raw routing object into the canonical contract (defensive)."""
    frame_type = str(raw.get("frame_type", _FALLBACK_FRAME_TYPE))
    if frame_type not in VALID_FRAME_TYPES:
        frame_type = _FALLBACK_FRAME_TYPE
    summary_hint = raw.get("summary_hint")
    return {
        "is_slide": bool(raw.get("is_slide", False)),
        "contains_graph": bool(raw.get("contains_graph", False)),
        "contains_equation": bool(raw.get("contains_equation", False)),
        "frame_type": frame_type,
        "summary_hint": None if summary_hint is None else str(summary_hint),
        "confidence": float(raw.get("confidence", 0.0)),
    }


def build_routing_prompt(n: int) -> str:
    """Build the zero-shot routing prompt for n frames."""
    return ROUTING_PROMPT.format(n=n)


def parse_routing_response(text: str, candidates: list[FrameCandidate]) -> list[dict]:
    """Parse a model's JSON-array response into one normalized dict per candidate.

    Tolerates leading/trailing prose by extracting the first JSON array. Pads
    with a non-slide default and truncates so the result length always matches
    the candidate count (one routing decision per input frame, in order).
    """
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        raise ValueError("VLM router response contained no JSON array")
    parsed = json.loads(match.group(0))
    if not isinstance(parsed, list):
        raise ValueError("VLM router response JSON was not an array")

    out: list[dict] = []
    for i, candidate in enumerate(candidates):
        raw = parsed[i] if i < len(parsed) and isinstance(parsed[i], dict) else {}
        out.append(_normalize(raw, candidate))
    return out


class MockBackend:
    """Deterministic, model-free backend for dev / CI / non-Apple hosts.

    Marks every candidate as a slide (so the dev pipeline produces output) with
    rotating, reproducible routing metadata. No randomness — stable for tests.
    """

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.model = model

    def route(self, candidates: list[FrameCandidate]) -> list[dict]:
        out: list[dict] = []
        for i, candidate in enumerate(candidates):
            out.append(
                _normalize(
                    {
                        "is_slide": True,
                        "contains_graph": i % 3 == 0,
                        "contains_equation": i % 5 == 0,
                        "frame_type": VALID_FRAME_TYPES[i % len(VALID_FRAME_TYPES)],
                        "summary_hint": f"mock slide at {candidate.timestamp_sec:.0f}s",
                        "confidence": 0.9,
                    },
                    candidate,
                )
            )
        return out


class TransformersBackend:
    """HuggingFace transformers backend (CUDA or CPU) — Kaggle GPU eval sandbox.

    Lazy-imports transformers so the dependency is only required when this
    backend is explicitly selected. Not exercised on the (CPU-only) CI runner;
    covered there by the mock backend.
    """

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.model = model
        self._model = None
        self._processor = None

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        from transformers import AutoModelForVision2Seq, AutoProcessor

        self._processor = AutoProcessor.from_pretrained(self.model)
        self._model = AutoModelForVision2Seq.from_pretrained(
            self.model, device_map="auto"
        )

    def route(self, candidates: list[FrameCandidate]) -> list[dict]:
        if not candidates:
            return []
        from PIL import Image

        self._ensure_loaded()
        images = [Image.open(c.path).convert("RGB") for c in candidates]
        prompt = build_routing_prompt(len(candidates))
        messages = [
            {
                "role": "user",
                "content": [{"type": "image"} for _ in images]
                + [{"type": "text", "text": prompt}],
            }
        ]
        chat = self._processor.apply_chat_template(
            messages, add_generation_prompt=True
        )
        inputs = self._processor(text=chat, images=images, return_tensors="pt").to(
            self._model.device
        )
        generated = self._model.generate(**inputs, max_new_tokens=2048)
        text = self._processor.batch_decode(generated, skip_special_tokens=True)[0]
        return parse_routing_response(text, candidates)


class MLXBackend:
    """mlx_vlm backend on Apple Silicon — prod + Mac eval (ADR 0001 D9).

    Lazy-imports mlx_vlm (Apple-Silicon-only; skipped on Linux/Windows CI).
    """

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.model = model
        self._model = None
        self._processor = None

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        from mlx_vlm import load

        self._model, self._processor = load(self.model)

    def route(self, candidates: list[FrameCandidate]) -> list[dict]:
        if not candidates:
            return []
        from mlx_vlm import generate

        self._ensure_loaded()
        prompt = build_routing_prompt(len(candidates))
        text = generate(
            self._model,
            self._processor,
            prompt,
            [str(c.path) for c in candidates],
            max_tokens=2048,
            verbose=False,
        )
        return parse_routing_response(text, candidates)


_BACKENDS = {
    "mock": MockBackend,
    "transformers": TransformersBackend,
    "mlx": MLXBackend,
}


def get_backend(
    name: str | None = None, model: str | None = None
) -> VLMRouterBackend:
    """Construct the configured router backend.

    name  — defaults to $SLIDEGEN_VLM_BACKEND, else "mock".
    model — defaults to $SLIDEGEN_VLM_MODEL, else DEFAULT_MODEL.
    """
    name = (name or os.environ.get(ENV_BACKEND, DEFAULT_BACKEND)).lower()
    model = model or os.environ.get(ENV_MODEL, DEFAULT_MODEL)
    try:
        backend_cls = _BACKENDS[name]
    except KeyError as e:
        raise ValueError(
            f"Unknown VLM backend '{name}'. Valid: {sorted(_BACKENDS)}"
        ) from e
    return backend_cls(model)


def route_frames(candidates: list[FrameCandidate]) -> list[dict]:
    """Route candidates via the configured backend. Returns [] for no input."""
    if not candidates:
        return []
    return get_backend().route(candidates)
