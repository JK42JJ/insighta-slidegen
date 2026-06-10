# Model Endpoints + S3 Handoff Contract

**Version**: 1.0-draft
**Status**: Draft (PR-E design input — owner infra decisions of 2026-06-11)
**Scope**: the wire contract between the orchestrating backend and the GPU
model-serving host, plus the S3 asset-handoff rules. This document is the
authority for the PR-E client implementations (`src/cv/`,
`mac-mini/slidegen-service/vlm_router.py` HTTP backend) and their stubs.
**Related**: [ADR 0002](./adr/0002-pipeline-v3-cpu-downsample-caption-context.md)
(CV stages, YOLO=WHERE / Qwen=WHAT), [ADR 0003](./adr/0003-mvp-pptx-output-and-prod-llm-extraction.md)
(D2 LLM boundary, D4 acquire proxy), [ADR 0004](./adr/0004-a-quality-gate-and-b-transition-triggers.md)
(failure-stage attribution), `CONTRACT_figure-manifest.md` (downstream figure
contract).

---

## 1. Topology

| Role | Host | Notes |
|---|---|---|
| Orchestrator / presign issuer | Backend app host (EC2) | the ONLY holder of S3 credentials |
| Qwen3-VL-8B serving | GPU host (RunPod) — **vLLM, OpenAI-compatible** | separate endpoint |
| DocLayout-YOLO serving | GPU host (RunPod) — **custom FastAPI** | separate endpoint |
| Acquire proxy + dev model serving | Mac Mini | mirrors the same API surface; dev/prod differ by URL only (ADR 0003 D4) |

Assets move exclusively via **S3 presigned URLs issued by the backend** (§4).
The GPU host receives URLs, never S3 credentials.

---

## 2. Qwen3-VL endpoint (vLLM, OpenAI-compatible)

### 2.1 Transport

- `POST {VLM_BASE_URL}/v1/chat/completions`
- Auth: `Authorization: Bearer {VLM_TOKEN}`
- Images are passed as OpenAI-style parts:
  `{"type": "image_url", "image_url": {"url": "<presigned S3 GET URL>"}}` —
  the serving host fetches the image itself (short-expiry URL, §4).
- `model`: from config (`SLIDEGEN_VLM_MODEL`); `temperature: 0` for all
  routing/classification calls; outputs are **JSON-only by prompt contract**,
  validated client-side (zod / pydantic) with **one re-ask retry** on parse
  failure, then hard error.

### 2.2 Usage modes (the only three sanctioned call shapes)

| Mode | Input | Output (JSON, client-validated) | Pipeline stage |
|---|---|---|---|
| **A — select + classify** | one batched call per BGE-M3 window: frame image parts in timestamp order + interval captions as companion text | per frame: `{is_slide, contains_graph, contains_equation, frame_type, summary_hint, confidence}` (ADR 0001 routing schema, unchanged) | stage 4 (ADR 0002 D4/D5) |
| **B — per-crop kind + struct-JSON** | one YOLO crop image + its `[t_start, t_end]` caption slice | `{kind, struct: {...chart/diagram/table structure...}, confidence}` — kind authority is Qwen, never YOLO's class (ADR 0002 D2/D7) | stage 5 |
| **C — equation OCR** | equation crop image | `{latex, confidence}` → `slide_figures.extracted_latex` / `extraction_conf`; low confidence flags, never silently embeds (ADR 0003 D3) | stage 5 |

**Coordinates never come from Qwen** (grounding hallucination — ADR 0002 D2).
Any bbox in a Qwen response is ignored.

### 2.3 Operational rules

- Timeout: per-call budget owned by the client (initial 120 s — tuning knob,
  not a secret); retries: max 2 with exponential backoff on 429/5xx/network;
  no retry on 4xx contract errors.
- Errors surface in OpenAI error-JSON shape; the client maps any failure to
  the job's failure attribution as stage `recognize` (mode B/C) or `keyframe`
  (mode A) per ADR 0004 §4.
- This endpoint serves a **self-hosted open-weights model** — calls are not
  LLM-API-ban scoped. The ban (ADR 0003 D2) governs Anthropic/OpenRouter only.

---

## 3. DocLayout-YOLO endpoint (custom FastAPI)

### 3.1 Transport

- `POST {YOLO_BASE_URL}/detect`
- Auth: `Authorization: Bearer {YOLO_TOKEN}`
- Health: `GET {YOLO_BASE_URL}/health` → `{"status":"ok","model_version":"..."}`

### 3.2 Request

```jsonc
{
  "image_url": "<presigned S3 GET URL>",   // required
  "conf_threshold": 0.15,                  // optional; default LOW = over-detect (ADR 0002 D2)
  "max_boxes": 50                          // optional guard
}
```

### 3.3 Response

```jsonc
{
  "image": { "w": 1920, "h": 1080 },
  "model_version": "doclayout-yolo-<...>",
  "boxes": [
    {
      "bbox": { "x": 0, "y": 0, "w": 0, "h": 0 },  // source-frame PIXELS — same shape persisted to slide_figures.bbox
      "class": "table",                            // ADVISORY ONLY — WHERE not WHAT (ADR 0002 D2); kind is decided by Qwen
      "score": 0.42
    }
  ]
}
```

### 3.4 Semantics

- **Over-detect by default**: recall (a missed box) is the only unrecoverable
  failure; Qwen cleans up false boxes downstream (ADR 0002 D2, recall-first
  ADR 0003 D5).
- `class` MUST NOT gate any routing decision; it may be logged for the
  ADR 0004 failure-attribution stats only.
- Errors: `{"status": <http>, "code": "<machine_code>", "message": "<human>"}`;
  failures attribute to stage `detect` (ADR 0004 §4).

---

## 4. S3 handoff

- **Single bucket**, prefix layout (all keyed by `job_id`):
  - `frames/{job_id}/…` — extracted keyframes (interval filenames per ADR 0002 D6)
  - `figures/{job_id}/…` — crops + redrawn figure assets
  - `artifacts/{job_id}/…` — decks, appendices, manifests
- **Presign issuer = the backend (EC2) ONLY.** The GPU host and the Mac Mini
  receive presigned URLs (GET for inputs, PUT for outputs) and hold **no S3
  credentials**.
- **Short expiry** (initial 15 min — tuning knob in config, not a secret).
  A long-running job re-requests fresh URLs from the backend rather than
  extending expiry.
- Bucket name and region live in backend config; they never appear in code or
  in this public repo's docs beyond the env key name.

---

## 5. Mode / backend gating (dev vs prod)

- `SLIDEGEN_VLM_BACKEND` (existing `vlm_router.py` pattern): unset → `mock`
  (default, no model, CI-safe). `http` = this contract's live endpoints —
  **opt-in only**. `mlx` remains the Mac-local option.
- **Dev defaults to mock/local; prod-only keys are never present in a dev/test
  `.env`** — config must refuse live-endpoint tokens when `SLIDEGEN_MODE=dev`
  unless the `http` backend was explicitly opted into (mirrors the
  `VISION_API_PROVIDER` / `OPENROUTER_API_KEY` gating, ADR 0003 D2).
- Env keys (NAMES only; values live in `.env` / GitHub Secrets — added to
  `.env.example` in the PR-E code change):
  `SLIDEGEN_VLM_BASE_URL`, `SLIDEGEN_VLM_TOKEN`, `SLIDEGEN_VLM_MODEL`,
  `SLIDEGEN_YOLO_BASE_URL`, `SLIDEGEN_YOLO_TOKEN`,
  `SLIDEGEN_S3_BUCKET` (backend only), `SLIDEGEN_PRESIGN_EXPIRY_SEC` (knob).

---

## 6. Conformance

- The PR-E stub servers implement §2/§3 byte-for-byte; client contract tests
  run against the stubs in CI (no GPU, no network).
- A **live smoke** (one frame through both endpoints) is a separate, opt-in
  verification step once endpoint URLs are provisioned — it is NOT a CI step.
- **Versioning**: this document carries the contract version; a breaking
  change bumps it and requires a consumer grep (TS `src/` + Python) before
  merge (Cross-Layer Propagation rule).

---

## 7. Out of scope

- Prompt contents for modes A/B/C (PR-F: bundle + orchestrate).
- Job/queue orchestration and failure-stage persistence columns (PR-G).
- Slide-content LLM (Sonnet via OpenRouter) — governed by ADR 0003 D2, not
  this contract.
