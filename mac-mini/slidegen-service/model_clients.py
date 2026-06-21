"""HTTP clients for the GPU model-serving endpoints.

Authority: docs/CONTRACT_model-endpoints.md v1.0 (referenced below as "§n").

    VlmHttpClient  — Qwen3-VL behind vLLM, OpenAI-compatible chat.completions (§2).
                     The three sanctioned call shapes (§2.2) map to methods:
                       A — select_and_classify()  (stage 4, per BGE-M3 window)
                       B — classify_crop()        (stage 5, per YOLO crop)
                       C — equation_ocr()         (stage 5, equation crop)
    YoloHttpClient — DocLayout-YOLO custom FastAPI: POST /detect + GET /health (§3).

Both endpoints serve **self-hosted open-weights models** — these calls are NOT
LLM-API-ban scoped; the ban (ADR 0003 D2) governs Anthropic/OpenRouter only
(§2.3). Prompt CONTENTS for modes A/B/C are PR-F scope (§7) — callers pass the
prompt in; this module owns only the wire contract.

Gating (§5): `from_env()` refuses live-endpoint tokens when SLIDEGEN_MODE=dev
(the default) unless SLIDEGEN_VLM_BACKEND=http was explicitly opted into —
mirrors the VISION_API_PROVIDER gating in src/config/index.ts. Tests construct
clients directly against in-process stubs (httpx.MockTransport): no env, no
network, no GPU (§6).

Coordinates NEVER come from Qwen (grounding hallucination, ADR 0002 D2 / §2.2):
the pydantic response models use extra="ignore", so any bbox/coordinate key in
a Qwen response is silently dropped. Box geometry is YOLO's job alone.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from collections.abc import Callable, Mapping
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

# ── Env key names (§5 — NAMES only; values live in .env / GitHub Secrets) ────
ENV_MODE = "SLIDEGEN_MODE"
ENV_VLM_BACKEND = "SLIDEGEN_VLM_BACKEND"  # mirrors vlm_router.ENV_BACKEND (no import: avoids cycle)
ENV_VLM_BASE_URL = "SLIDEGEN_VLM_BASE_URL"
ENV_VLM_TOKEN = "SLIDEGEN_VLM_TOKEN"
ENV_VLM_MODEL = "SLIDEGEN_VLM_MODEL"
ENV_YOLO_BASE_URL = "SLIDEGEN_YOLO_BASE_URL"
ENV_YOLO_TOKEN = "SLIDEGEN_YOLO_TOKEN"
# Per-call read budget override (seconds) — tuning knob, not a secret.
# PR-H2 live measurement: mode-A windows on the serving host exceeded the
# 120 s default (read timeout after 3 attempts) before window chunking; the
# knob lets ops match the budget to the host without a code change.
ENV_VLM_TIMEOUT_SEC = "SLIDEGEN_VLM_TIMEOUT_SEC"

# Backend name that opts into live HTTP endpoints (§5); anything else = no live calls.
HTTP_BACKEND_NAME = "http"
# Unset SLIDEGEN_MODE is dev (fail-closed): live tokens are refused by default.
DEFAULT_MODE = "dev"

# ── Operational defaults (§2.3 / §3.2 — tuning knobs, not secrets) ───────────
DEFAULT_TIMEOUT_SEC = 120.0  # §2.3 initial per-call budget
MAX_RETRIES = 2  # §2.3 max retries on 429/5xx/network
BACKOFF_BASE_SEC = 1.0  # exponential backoff: BACKOFF_BASE_SEC * 2**attempt
STATUS_TOO_MANY_REQUESTS = 429
STATUS_SERVER_ERROR_MIN = 500

DEFAULT_CONF_THRESHOLD = 0.15  # §3.2 LOW default = over-detect (ADR 0002 D2, recall-first)
DEFAULT_MAX_BOXES = 50  # §3.2 optional guard

ROUTING_TEMPERATURE = 0.0  # §2.1 — temperature 0 for ALL routing/classification calls
# Completion ceiling (PR-H2 live finding): with no max_tokens the server may
# generate to max-model-len — a runaway struct measured >300 s/call on the
# serving GPU (read-timeout x3 killed the video). 4096 covers every §2.2 mode
# reply with slack; a truncated runaway becomes a CONTRACT error, which the
# per-crop skip absorbs. Tuning knob, not a secret.
MAX_COMPLETION_TOKENS = 4096
# OpenAI/vLLM finish_reason when generation hit max_tokens (= the output was
# TRUNCATED, not a clean stop). A truncated reply is a distinct failure mode
# from genuine non-JSON garbage: it warrants a fail-closed partial salvage of
# the complete prefix, NOT a re-ask (which re-truncates identically). §2.1.
FINISH_REASON_LENGTH = "length"
# §1 topology: Qwen3-VL-8B is the contract serving model (vlm_router keeps its
# own local-backend default; this applies to from_env() construction only).
DEFAULT_VLM_MODEL = "qwen3-vl-8b-instruct"

# ── ADR 0004 §4 failure-stage attribution (§2.3 / §3.4) ──────────────────────
STAGE_KEYFRAME = "keyframe"  # mode A failures
STAGE_RECOGNIZE = "recognize"  # mode B/C failures
STAGE_DETECT = "detect"  # YOLO failures

# One re-ask retry on JSON parse/validation failure, then hard error (§2.1).
# Generic corrective instruction — NOT a mode prompt (those are PR-F scope, §7).
REASK_PROMPT = (
    "Your previous reply was not the required JSON or did not match the "
    "expected shape. Reply again with ONLY the JSON — no prose, no code fences."
)


# ── Errors ────────────────────────────────────────────────────────────────────
class LiveConfigRefusedError(RuntimeError):
    """Live-endpoint config present in dev mode without explicit http opt-in (§5)."""


class ModelEndpointError(RuntimeError):
    """A model-endpoint call failed; carries ADR 0004 §4 stage attribution."""

    def __init__(
        self,
        message: str,
        *,
        stage: str,
        status: int | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.status = status
        self.code = code


class VlmContractError(ModelEndpointError):
    """Qwen output failed the JSON contract even after the single re-ask (§2.1)."""


# ── Response models (client-side validation, §2.1 / §3.3) ─────────────────────
class RoutingDecision(BaseModel):
    """Mode A per-frame output (ADR 0001 routing schema, unchanged — §2.2).

    extra="ignore" drops any bbox/coordinate key Qwen may emit (§2.2: ignored).
    Lenient defaults mirror vlm_router._normalize so a sparse-but-valid object
    routes as a conservative non-slide instead of failing the whole window.
    """

    model_config = ConfigDict(extra="ignore")

    is_slide: bool = False
    contains_graph: bool = False
    contains_equation: bool = False
    frame_type: str = "b_roll"
    summary_hint: str | None = None
    confidence: float = 0.0


class CropClassification(BaseModel):
    """Mode B output: kind authority is Qwen, never YOLO's class (§2.2, ADR 0002 D2/D7)."""

    model_config = ConfigDict(extra="ignore")

    kind: str
    struct: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0


class EquationOcr(BaseModel):
    """Mode C output → slide_figures.extracted_latex / extraction_conf (§2.2, ADR 0003 D3)."""

    model_config = ConfigDict(extra="ignore")

    latex: str
    confidence: float = 0.0


class PixelBox(BaseModel):
    """Source-frame PIXELS — same shape persisted to slide_figures.bbox (§3.3)."""

    x: float
    y: float
    w: float
    h: float


class DetectedBox(BaseModel):
    """One YOLO detection. `class` is ADVISORY ONLY — WHERE not WHAT (§3.3/§3.4).

    The client carries it through untouched (logging/ADR 0004 stats only) and
    MUST NOT branch on it; `kind` is decided by Qwen in mode B.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    bbox: PixelBox
    cls: str = Field(alias="class")
    score: float


class ImageSize(BaseModel):
    w: int
    h: int


class DetectResponse(BaseModel):
    """POST /detect response (§3.3)."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    image: ImageSize
    model_version: str
    boxes: list[DetectedBox]


class HealthResponse(BaseModel):
    """GET /health response (§3.1)."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    status: str
    model_version: str


# ── §5 gating ─────────────────────────────────────────────────────────────────
def assert_live_config_allowed(env: Mapping[str, str] | None = None) -> None:
    """Refuse live-endpoint tokens in dev mode without explicit http opt-in (§5).

    Mirrors the VISION_API_PROVIDER gating in src/config/index.ts: dev defaults
    to mock/local, prod-only keys must never activate from a dev/test `.env`.
    """
    env = os.environ if env is None else env
    mode = env.get(ENV_MODE, DEFAULT_MODE)
    opted_in = env.get(ENV_VLM_BACKEND, "").lower() == HTTP_BACKEND_NAME
    if mode == "prod" or opted_in:
        return
    live_keys = [key for key in (ENV_VLM_TOKEN, ENV_YOLO_TOKEN) if env.get(key)]
    if live_keys:
        raise LiveConfigRefusedError(
            f"live model-endpoint token(s) {live_keys} are set but {ENV_MODE}="
            f"{mode} without {ENV_VLM_BACKEND}={HTTP_BACKEND_NAME} opt-in — "
            "live endpoints are prod/opt-in only (CONTRACT_model-endpoints §5)"
        )


# ── Shared transport helpers ──────────────────────────────────────────────────
def _request_with_retry(
    http: httpx.Client,
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    json_body: dict | None,
    stage: str,
    parse_error: Callable[[httpx.Response], tuple[str | None, str | None]],
    max_retries: int,
    backoff_base_sec: float,
    sleep: Callable[[float], None],
) -> httpx.Response:
    """§2.3/§3.4 retry policy: max retries with exponential backoff on
    429/5xx/network; NO retry on other 4xx contract errors."""
    attempt = 0
    while True:
        try:
            response = http.request(method, url, headers=headers, json=json_body)
        except httpx.HTTPError as exc:
            if attempt >= max_retries:
                raise ModelEndpointError(
                    f"{method} {url} network failure after {attempt + 1} attempt(s): {exc}",
                    stage=stage,
                ) from exc
        else:
            if response.status_code < 400:
                return response
            retryable = (
                response.status_code == STATUS_TOO_MANY_REQUESTS
                or response.status_code >= STATUS_SERVER_ERROR_MIN
            )
            if not retryable or attempt >= max_retries:
                code, message = parse_error(response)
                detail = f" [{code}] {message}" if (code or message) else ""
                raise ModelEndpointError(
                    f"{method} {url} -> HTTP {response.status_code}{detail}",
                    stage=stage,
                    status=response.status_code,
                    code=code,
                )
        sleep(backoff_base_sec * 2**attempt)
        attempt += 1


def _openai_error(response: httpx.Response) -> tuple[str | None, str | None]:
    """Extract (code, message) from the OpenAI error-JSON shape (§2.3)."""
    try:
        err = response.json().get("error") or {}
        return err.get("code"), err.get("message")
    except (ValueError, AttributeError):
        return None, response.text[:200]


def _yolo_error(response: httpx.Response) -> tuple[str | None, str | None]:
    """Extract (code, message) from the YOLO error shape (§3.4)."""
    try:
        body = response.json()
        return body.get("code"), body.get("message")
    except (ValueError, AttributeError):
        return None, response.text[:200]


def _loads_json(text: str) -> Any:
    """Strict JSON parse, tolerating only a markdown code fence around the JSON."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def _salvage_truncated_json(text: str) -> Any | None:
    """Recover the largest VALID prefix of a TRUNCATED JSON document.

    Fail-closed (ADR 0003 D3): only complete, already-emitted elements are
    kept. The incomplete trailing token is discarded and the still-open
    containers are closed around what remains — no value is invented or
    interpolated. Cut points are restricted to positions right after a closed
    ``}``/``]`` (a complete object/array element), so a half-written object or
    a possibly-truncated bare scalar (e.g. a number cut mid-digits) is never
    admitted. ``"``/``]``/``}`` inside string literals are ignored (escape
    aware). Returns the parsed object/array, or None when nothing complete can
    be recovered (caller then drops the crop — never a silent total skip).
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned).strip()
    stack: list[str] = []
    in_string = False
    escape = False
    best_cut = -1
    best_stack: list[str] = []
    for i, ch in enumerate(cleaned):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if not stack:
                break  # malformed nesting — keep the best boundary so far
            stack.pop()
            best_cut = i + 1  # boundary just after a complete element
            best_stack = stack.copy()  # containers still open at that boundary
    if best_cut == -1:
        return None
    closers = "".join("}" if c == "{" else "]" for c in reversed(best_stack))
    try:
        return json.loads(cleaned[:best_cut] + closers)
    except ValueError:
        return None


def _warn_salvage(stage: str, salvaged: Any) -> None:
    """Emit a non-fatal stderr line marking a SALVAGED truncation (distinct
    from a skip). With the reorder (confidence precedes struct, figure_extract),
    a salvaged truncation usually keeps a real confidence that clears the floor;
    the count of recovered array elements is the recoverability signal."""
    kind = salvaged.get("kind") if isinstance(salvaged, dict) else None
    struct = salvaged.get("struct") if isinstance(salvaged, dict) else None
    counts = ""
    if isinstance(struct, dict):
        sized = [f"{k}={len(v)}" for k, v in struct.items() if isinstance(v, list)]
        if sized:
            counts = " " + " ".join(sized)
    has_conf = isinstance(salvaged, dict) and "confidence" in salvaged
    conf_note = "present" if has_conf else "absent→0.0 (will fail conf floor)"
    sys.stderr.write(
        f"model_clients: salvaged truncated JSON (stage={stage} kind={kind}"
        f"{counts}); confidence {conf_note}\n"
    )


# ── Salvage over-generation guard (R3 fail-closed, 2026-06-21) ───────────────
# A truncated reply that salvages into an implausibly large/asymmetric graph, or
# whose node ids are a sequential placeholder run (Q2273, Q2274, …), is model
# OVER-GENERATION (hallucinated structure), not real data — drop it. The #49
# salvage guarantees JSON STRUCTURE only; it cannot tell real content from a
# confident hallucination, so this guard closes that fail-closed hole. A healthy
# figure fits well under MAX_COMPLETION_TOKENS, so these bounds only ever apply
# to already-abnormal truncated output. (R3 V0–V3 2026-06-21: 174–198 nodes /
# 0 edges, or 24 nodes / 169 edges with sequential "Q2273…" ids — all fabricated.)
SALVAGE_MAX_NODES = 30  # real teaching diagrams sit well under this
SALVAGE_MAX_EDGES = 40  # bounding nodes shifted over-gen to edges (V3) — bound both
SALVAGE_SEQ_ID_RUN = 6  # >= this many consecutive <prefix><int> ids = placeholder


def _has_sequential_id_run(ids: list[str], k: int) -> bool:
    """True if any common-prefix group has >= k consecutive integer suffixes
    (e.g. Q2273, Q2274, …, Q2278 = a fabricated sequential placeholder run)."""
    groups: dict[str, list[int]] = {}
    for raw in ids:
        m = re.match(r"^(.*?)(\d+)$", raw)
        if m:
            groups.setdefault(m.group(1), []).append(int(m.group(2)))
    for nums in groups.values():
        ordered = sorted(set(nums))
        run = best = 1
        for a, b in zip(ordered, ordered[1:]):
            run = run + 1 if b == a + 1 else 1
            best = max(best, run)
        if best >= k:
            return True
    return False


def _salvage_looks_overgenerated(salvaged: Any) -> bool:
    """Over-generation / hallucination signals on a SALVAGED diagram struct (R3).
    True → caller drops the crop instead of resurrecting a hallucination. Scoped
    to diagram nodes/edges (the demonstrated failure mode)."""
    if not isinstance(salvaged, dict):
        return False
    struct = salvaged.get("struct")
    if not isinstance(struct, dict):
        return False
    nodes = struct.get("nodes") if isinstance(struct.get("nodes"), list) else []
    edges = struct.get("edges") if isinstance(struct.get("edges"), list) else []
    if len(nodes) > SALVAGE_MAX_NODES or len(edges) > SALVAGE_MAX_EDGES:
        return True
    ids = [str(n.get("id")) for n in nodes if isinstance(n, dict) and n.get("id") is not None]
    return _has_sequential_id_run(ids, SALVAGE_SEQ_ID_RUN)


def _warn_overgen(stage: str, salvaged: Any) -> None:
    """Stderr line marking a salvaged-but-DROPPED truncation: the recovered
    struct tripped the over-generation guard (hallucination) → not returned."""
    struct = salvaged.get("struct") if isinstance(salvaged, dict) else {}
    struct = struct if isinstance(struct, dict) else {}
    n = len(struct.get("nodes")) if isinstance(struct.get("nodes"), list) else 0
    e = len(struct.get("edges")) if isinstance(struct.get("edges"), list) else 0
    sys.stderr.write(
        f"model_clients: salvaged truncation DROPPED as over-generation "
        f"(stage={stage} nodes={n} edges={e}) — hallucinated structure, not real data\n"
    )


# ── Qwen3-VL client (§2) ─────────────────────────────────────────────────────
class VlmHttpClient:
    """Qwen3-VL behind vLLM — OpenAI-compatible chat.completions (§2).

    Images are passed as `image_url` parts (presigned S3 GET URLs in prod, §4;
    the serving host fetches them itself). All calls run at temperature 0 and
    are JSON-only by prompt contract, validated client-side with ONE re-ask
    retry on parse failure, then hard error (§2.1).
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        model: str = DEFAULT_VLM_MODEL,
        *,
        timeout_sec: float = DEFAULT_TIMEOUT_SEC,
        max_retries: int = MAX_RETRIES,
        backoff_base_sec: float = BACKOFF_BASE_SEC,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._headers = {"Authorization": f"Bearer {token}"}
        self._max_retries = max_retries
        self._backoff_base_sec = backoff_base_sec
        self._sleep = sleep
        self._http = httpx.Client(
            base_url=self.base_url, timeout=timeout_sec, transport=transport
        )

    @classmethod
    def from_env(
        cls, env: Mapping[str, str] | None = None, **kwargs: Any
    ) -> "VlmHttpClient":
        """Construct from §5 env keys; enforces the dev-mode live-config refusal."""
        env = os.environ if env is None else env
        assert_live_config_allowed(env)
        base_url = env.get(ENV_VLM_BASE_URL)
        if not base_url:
            raise LiveConfigRefusedError(f"{ENV_VLM_BASE_URL} is not set")
        model = kwargs.pop("model", None) or env.get(ENV_VLM_MODEL) or DEFAULT_VLM_MODEL
        if "timeout_sec" not in kwargs and env.get(ENV_VLM_TIMEOUT_SEC):
            kwargs["timeout_sec"] = float(env[ENV_VLM_TIMEOUT_SEC])
        return cls(base_url, env.get(ENV_VLM_TOKEN, ""), model, **kwargs)

    def close(self) -> None:
        self._http.close()

    # — Mode A: select + classify (one batched call per BGE-M3 window, §2.2) —
    def select_and_classify(
        self,
        image_urls: list[str],
        prompt: str,
        captions_text: str | None = None,
    ) -> list[dict]:
        """One routing dict per frame, in input order (ADR 0001 schema).

        Failure attribution: stage `keyframe` (§2.3 / ADR 0004 §4).
        """
        parts: list[dict] = [
            {"type": "image_url", "image_url": {"url": url}} for url in image_urls
        ]
        if captions_text:
            parts.append({"type": "text", "text": captions_text})
        parts.append({"type": "text", "text": prompt})

        expected = len(image_urls)

        def parse(text: str) -> list[dict]:
            data = _loads_json(text)
            if not isinstance(data, list):
                raise ValueError("mode A output must be a JSON array")
            if len(data) != expected:
                raise ValueError(
                    f"mode A output must have one object per frame "
                    f"(expected {expected}, got {len(data)})"
                )
            return [RoutingDecision.model_validate(obj).model_dump() for obj in data]

        return self._chat_json(parts, stage=STAGE_KEYFRAME, parse=parse)

    # — Mode B: per-crop kind + struct-JSON (§2.2) —
    def classify_crop(
        self,
        image_url: str,
        prompt: str,
        caption_slice: str | None = None,
    ) -> dict:
        """{kind, struct, confidence} for one YOLO crop. kind authority is Qwen,
        never YOLO's class (ADR 0002 D2/D7). Stage: `recognize`."""
        parts: list[dict] = [{"type": "image_url", "image_url": {"url": image_url}}]
        if caption_slice:
            parts.append({"type": "text", "text": caption_slice})
        parts.append({"type": "text", "text": prompt})

        def parse(text: str) -> dict:
            return CropClassification.model_validate(_loads_json(text)).model_dump()

        return self._chat_json(parts, stage=STAGE_RECOGNIZE, parse=parse)

    # — Mode C: equation OCR (§2.2) —
    def equation_ocr(self, image_url: str, prompt: str) -> dict:
        """{latex, confidence} for an equation crop. Low confidence FLAGS, never
        silently embeds (ADR 0003 D3) — flagging is the caller's job; this
        client only validates and returns. Stage: `recognize`."""
        parts = [
            {"type": "image_url", "image_url": {"url": image_url}},
            {"type": "text", "text": prompt},
        ]

        def parse(text: str) -> dict:
            return EquationOcr.model_validate(_loads_json(text)).model_dump()

        return self._chat_json(parts, stage=STAGE_RECOGNIZE, parse=parse)

    # — internals —
    def _chat_json(
        self, parts: list[dict], *, stage: str, parse: Callable[[str], Any]
    ) -> Any:
        messages = [{"role": "user", "content": parts}]
        text, finish_reason = self._completion_text(messages, stage=stage)
        try:
            return parse(text)
        except (ValueError, ValidationError) as first_error:
            # Truncation (max_tokens hit → finish_reason == "length") is NOT a
            # re-ask candidate: a re-ask re-truncates identically (1080p cycle,
            # 2026-06-13). Attempt a fail-closed salvage of the complete prefix
            # instead; if nothing complete can be recovered, the crop is
            # dropped (caller skip) — never a silent total loss.
            if finish_reason == FINISH_REASON_LENGTH:
                salvaged = _salvage_truncated_json(text)
                if salvaged is not None:
                    if _salvage_looks_overgenerated(salvaged):
                        # Structurally salvageable but the content is model
                        # over-generation (R3): drop it — never resurrect a
                        # hallucination (closes the #49 fail-closed hole).
                        _warn_overgen(stage, salvaged)
                    else:
                        try:
                            result = parse(json.dumps(salvaged))
                        except (ValueError, ValidationError):
                            result = None
                        if result is not None:
                            _warn_salvage(stage, salvaged)
                            return result
                raise VlmContractError(
                    "VLM output truncated (finish_reason=length) and not "
                    "salvageable into the contract (or salvage dropped as "
                    f"over-generation): {first_error}",
                    stage=stage,
                ) from first_error
            # Non-truncation parse/validation failure: ONE re-ask retry, then
            # hard error (§2.1).
            reask_messages = messages + [
                {"role": "assistant", "content": text},
                {"role": "user", "content": REASK_PROMPT},
            ]
            reask_text, _ = self._completion_text(reask_messages, stage=stage)
            try:
                return parse(reask_text)
            except (ValueError, ValidationError) as second_error:
                raise VlmContractError(
                    f"VLM output failed the JSON contract after one re-ask: {second_error}",
                    stage=stage,
                ) from first_error

    def _completion_text(
        self, messages: list[dict], *, stage: str
    ) -> tuple[str, str | None]:
        payload = {
            "model": self.model,
            "temperature": ROUTING_TEMPERATURE,  # §2.1 — always 0
            "max_tokens": MAX_COMPLETION_TOKENS,  # runaway-generation ceiling
            "messages": messages,
        }
        response = _request_with_retry(
            self._http,
            "POST",
            "/v1/chat/completions",
            headers=self._headers,
            json_body=payload,
            stage=stage,
            parse_error=_openai_error,
            max_retries=self._max_retries,
            backoff_base_sec=self._backoff_base_sec,
            sleep=self._sleep,
        )
        data = response.json()
        try:
            choice = data["choices"][0]
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise VlmContractError(
                f"malformed chat.completions envelope: {exc}", stage=stage
            ) from exc
        if not isinstance(content, str):
            raise VlmContractError(
                "chat.completions message content was not a string", stage=stage
            )
        finish_reason = choice.get("finish_reason") if isinstance(choice, dict) else None
        return content, finish_reason


# ── DocLayout-YOLO client (§3) ───────────────────────────────────────────────
class YoloHttpClient:
    """DocLayout-YOLO custom FastAPI: POST /detect + GET /health (§3).

    Over-detect by default (LOW conf threshold): recall is the only
    unrecoverable failure; Qwen cleans up false boxes downstream (§3.4).
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout_sec: float = DEFAULT_TIMEOUT_SEC,
        max_retries: int = MAX_RETRIES,
        backoff_base_sec: float = BACKOFF_BASE_SEC,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"}
        self._max_retries = max_retries
        self._backoff_base_sec = backoff_base_sec
        self._sleep = sleep
        self._http = httpx.Client(
            base_url=self.base_url, timeout=timeout_sec, transport=transport
        )

    @classmethod
    def from_env(
        cls, env: Mapping[str, str] | None = None, **kwargs: Any
    ) -> "YoloHttpClient":
        """Construct from §5 env keys; enforces the dev-mode live-config refusal."""
        env = os.environ if env is None else env
        assert_live_config_allowed(env)
        base_url = env.get(ENV_YOLO_BASE_URL)
        if not base_url:
            raise LiveConfigRefusedError(f"{ENV_YOLO_BASE_URL} is not set")
        return cls(base_url, env.get(ENV_YOLO_TOKEN, ""), **kwargs)

    def close(self) -> None:
        self._http.close()

    def detect(
        self,
        image_url: str,
        conf_threshold: float = DEFAULT_CONF_THRESHOLD,
        max_boxes: int = DEFAULT_MAX_BOXES,
    ) -> DetectResponse:
        """POST /detect (§3.2/§3.3). Boxes are returned exactly as detected —
        `class` is advisory-only and never gates anything here (§3.4).
        Failure attribution: stage `detect`."""
        payload = {
            "image_url": image_url,
            "conf_threshold": conf_threshold,
            "max_boxes": max_boxes,
        }
        response = self._request("POST", "/detect", json_body=payload)
        try:
            return DetectResponse.model_validate(response.json())
        except (ValidationError, ValueError) as exc:
            raise ModelEndpointError(
                f"YOLO /detect response failed contract validation: {exc}",
                stage=STAGE_DETECT,
            ) from exc

    def health(self) -> HealthResponse:
        """GET /health (§3.1)."""
        response = self._request("GET", "/health", json_body=None)
        try:
            return HealthResponse.model_validate(response.json())
        except (ValidationError, ValueError) as exc:
            raise ModelEndpointError(
                f"YOLO /health response failed contract validation: {exc}",
                stage=STAGE_DETECT,
            ) from exc

    def _request(
        self, method: str, url: str, *, json_body: dict | None
    ) -> httpx.Response:
        return _request_with_retry(
            self._http,
            method,
            url,
            headers=self._headers,
            json_body=json_body,
            stage=STAGE_DETECT,
            parse_error=_yolo_error,
            max_retries=self._max_retries,
            backoff_base_sec=self._backoff_base_sec,
            sleep=self._sleep,
        )
