"""Stub of the Qwen3-VL vLLM endpoint (contract §2) — OpenAI-compatible surface.

Implements POST /v1/chat/completions byte-for-byte as an httpx.MockTransport
handler. Tests script the assistant content (including malformed JSON for the
re-ask path) and HTTP failures (429 / 5xx / 4xx in OpenAI error-JSON shape).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import httpx

DEFAULT_TOKEN = "stub-vlm-token"
DEFAULT_MODEL = "qwen3-vl-8b-instruct"
CHAT_COMPLETIONS_PATH = "/v1/chat/completions"


def openai_error_body(message: str, *, code: str, err_type: str = "invalid_request_error") -> dict:
    """OpenAI error-JSON shape (§2.3)."""
    return {"error": {"message": message, "type": err_type, "code": code, "param": None}}


@dataclass
class _StatusStep:
    status: int
    body: dict


@dataclass
class VlmStub:
    """Scriptable in-process vLLM stub.

    `script_content(...)` queues assistant message contents (returned 200, one
    per request, in order). `script_status(...)` queues an HTTP failure step.
    With an empty script, the stub returns an empty JSON array content "[]".
    """

    token: str = DEFAULT_TOKEN
    model: str = DEFAULT_MODEL
    requests: list[httpx.Request] = field(default_factory=list)
    _script: list = field(default_factory=list)

    def script_content(self, *contents: str) -> None:
        self._script.extend(contents)

    def script_status(self, status: int, body: dict | None = None) -> None:
        if body is None:
            body = openai_error_body(f"stubbed HTTP {status}", code=f"http_{status}")
        self._script.append(_StatusStep(status, body))

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)

    # — request bodies recorded for assertions —
    def request_payloads(self) -> list[dict]:
        return [json.loads(r.content) for r in self.requests]

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)

        if request.url.path != CHAT_COMPLETIONS_PATH or request.method != "POST":
            return httpx.Response(
                404, json=openai_error_body("not found", code="not_found")
            )
        if request.headers.get("Authorization") != f"Bearer {self.token}":
            return httpx.Response(
                401, json=openai_error_body("invalid bearer token", code="invalid_api_key")
            )

        payload = json.loads(request.content)
        # §2.1: temperature MUST be 0 for all routing/classification calls.
        if payload.get("temperature") != 0:
            return httpx.Response(
                400,
                json=openai_error_body(
                    "temperature must be 0 for routing/classification calls (§2.1)",
                    code="temperature_not_zero",
                ),
            )
        if not payload.get("model") or not payload.get("messages"):
            return httpx.Response(
                400, json=openai_error_body("model and messages are required", code="bad_request")
            )

        step = self._script.pop(0) if self._script else "[]"
        if isinstance(step, _StatusStep):
            return httpx.Response(step.status, json=step.body)
        return httpx.Response(200, json=self._completion(step))

    def _completion(self, content: str) -> dict:
        """A minimal-but-complete OpenAI chat.completion envelope."""
        return {
            "id": "chatcmpl-stub-0001",
            "object": "chat.completion",
            "created": 0,
            "model": self.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }
