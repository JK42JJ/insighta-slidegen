"""In-process stub servers for the model-endpoint contract tests (contract §6).

These implement docs/CONTRACT_model-endpoints.md §2 (Qwen3-VL vLLM,
OpenAI-compatible) and §3 (DocLayout-YOLO FastAPI) byte-for-byte as
httpx.MockTransport handlers: no sockets, no GPU, no network — CI-safe.
"""
