"""Contract tests for model_clients.py against in-process stubs.

Authority: docs/CONTRACT_model-endpoints.md v1.0 — §2 (Qwen3-VL vLLM),
§3 (DocLayout-YOLO), §5 (gating), §6 (stubs, no GPU / no network in CI).
"""

import json

import pytest
from stubs.vlm_stub import VlmStub
from stubs.yolo_stub import YoloStub

# A fake presigned-URL placeholder (no real bucket/host — PUBLIC repo rule).
IMG = "https://example.invalid/frames/job-0001/frame_0001.jpg?X-Amz-Signature=stub"


def make_vlm_client(stub: VlmStub, **kwargs):
    from model_clients import VlmHttpClient

    return VlmHttpClient(
        "http://vlm.stub.invalid",
        stub.token,
        stub.model,
        transport=stub.transport(),
        backoff_base_sec=0.0,
        sleep=lambda _s: None,
        **kwargs,
    )


def make_yolo_client(stub: YoloStub, **kwargs):
    from model_clients import YoloHttpClient

    return YoloHttpClient(
        "http://yolo.stub.invalid",
        stub.token,
        transport=stub.transport(),
        backoff_base_sec=0.0,
        sleep=lambda _s: None,
        **kwargs,
    )


# ── §2.2 mode A — select + classify ──────────────────────────────────────────


def test_mode_a_happy_path():
    stub = VlmStub()
    stub.script_content(
        json.dumps(
            [
                {
                    "is_slide": True,
                    "contains_graph": True,
                    "contains_equation": False,
                    "frame_type": "chart",
                    "summary_hint": "revenue trend",
                    "confidence": 0.9,
                },
                {"is_slide": False, "frame_type": "face", "confidence": 0.7},
            ]
        )
    )
    client = make_vlm_client(stub)
    out = client.select_and_classify([IMG, IMG], "route these frames", "caption text")

    assert len(out) == 2
    assert out[0] == {
        "is_slide": True,
        "contains_graph": True,
        "contains_equation": False,
        "frame_type": "chart",
        "summary_hint": "revenue trend",
        "confidence": 0.9,
    }
    assert out[1]["is_slide"] is False  # lenient defaults fill missing fields


def test_mode_a_request_shape():
    """§2.1: image_url parts, temperature 0, model from config, bearer auth."""
    stub = VlmStub()
    stub.script_content('[{"is_slide": true}]')
    client = make_vlm_client(stub)
    client.select_and_classify([IMG], "prompt text", captions_text="captions here")

    request = stub.requests[0]
    assert request.headers["Authorization"] == f"Bearer {stub.token}"
    payload = stub.request_payloads()[0]
    assert payload["temperature"] == 0
    assert payload["model"] == stub.model
    parts = payload["messages"][0]["content"]
    image_parts = [p for p in parts if p["type"] == "image_url"]
    text_parts = [p for p in parts if p["type"] == "text"]
    assert image_parts == [{"type": "image_url", "image_url": {"url": IMG}}]
    assert [p["text"] for p in text_parts] == ["captions here", "prompt text"]


def test_mode_a_ignores_qwen_coordinates():
    """§2.2: any bbox/coordinate in a Qwen response is ignored (never emitted)."""
    stub = VlmStub()
    stub.script_content(
        '[{"is_slide": true, "frame_type": "diagram", "confidence": 0.8, '
        '"bbox": [10, 20, 30, 40], "coordinates": {"x": 1, "y": 2}}]'
    )
    client = make_vlm_client(stub)
    out = client.select_and_classify([IMG], "prompt")
    assert "bbox" not in out[0]
    assert "coordinates" not in out[0]
    assert set(out[0]) == {
        "is_slide",
        "contains_graph",
        "contains_equation",
        "frame_type",
        "summary_hint",
        "confidence",
    }


def test_mode_a_count_mismatch_triggers_reask():
    """One object per frame is part of the shape contract — mismatch → re-ask."""
    stub = VlmStub()
    stub.script_content(
        '[{"is_slide": true}]',  # 1 object for 2 frames → re-ask
        '[{"is_slide": true}, {"is_slide": false}]',
    )
    client = make_vlm_client(stub)
    out = client.select_and_classify([IMG, IMG], "prompt")
    assert len(stub.requests) == 2
    assert [o["is_slide"] for o in out] == [True, False]


# ── §2.2 mode B — per-crop kind + struct-JSON ────────────────────────────────


def test_mode_b_happy_path():
    stub = VlmStub()
    stub.script_content(
        json.dumps(
            {
                "kind": "chart",
                "struct": {"chart_type": "line", "series": [{"name": "a", "points": []}]},
                "confidence": 0.85,
            }
        )
    )
    client = make_vlm_client(stub)
    out = client.classify_crop(IMG, "classify this crop", caption_slice="[12.0, 18.5] talking about revenue")
    assert out["kind"] == "chart"
    assert out["struct"]["chart_type"] == "line"
    assert out["confidence"] == 0.85

    parts = stub.request_payloads()[0]["messages"][0]["content"]
    assert [p["type"] for p in parts] == ["image_url", "text", "text"]


# ── §2.2 mode C — equation OCR ───────────────────────────────────────────────


def test_mode_c_happy_path():
    stub = VlmStub()
    stub.script_content('{"latex": "E = mc^2", "confidence": 0.95}')
    client = make_vlm_client(stub)
    out = client.equation_ocr(IMG, "transcribe to LaTeX")
    assert out == {"latex": "E = mc^2", "confidence": 0.95}


def test_mode_c_low_confidence_is_returned_not_hidden():
    """ADR 0003 D3: low confidence FLAGS downstream — the client must surface it."""
    stub = VlmStub()
    stub.script_content('{"latex": "\\\\sum_i x_i", "confidence": 0.2}')
    client = make_vlm_client(stub)
    assert client.equation_ocr(IMG, "transcribe")["confidence"] == 0.2


# ── §2.1 — JSON-only + ONE re-ask retry, then hard error ─────────────────────


def test_malformed_json_then_valid_on_reask():
    stub = VlmStub()
    stub.script_content("Sure! The equation is E = mc^2.", '{"latex": "E = mc^2"}')
    client = make_vlm_client(stub)
    out = client.equation_ocr(IMG, "transcribe")
    assert out["latex"] == "E = mc^2"
    assert len(stub.requests) == 2

    # The re-ask carries the bad reply + a corrective user turn.
    reask_messages = stub.request_payloads()[1]["messages"]
    assert reask_messages[1]["role"] == "assistant"
    assert reask_messages[1]["content"] == "Sure! The equation is E = mc^2."
    assert reask_messages[2]["role"] == "user"


def test_malformed_json_twice_is_hard_error():
    from model_clients import STAGE_RECOGNIZE, VlmContractError

    stub = VlmStub()
    stub.script_content("not json", "still not json")
    client = make_vlm_client(stub)
    with pytest.raises(VlmContractError) as excinfo:
        client.equation_ocr(IMG, "transcribe")
    assert len(stub.requests) == 2  # exactly ONE re-ask, then hard error
    assert excinfo.value.stage == STAGE_RECOGNIZE


def test_code_fenced_json_is_tolerated():
    stub = VlmStub()
    stub.script_content('```json\n{"latex": "x^2"}\n```')
    client = make_vlm_client(stub)
    assert client.equation_ocr(IMG, "transcribe")["latex"] == "x^2"
    assert len(stub.requests) == 1  # no re-ask needed


# ── §2.3 — retry/backoff + failure attribution ───────────────────────────────


def test_vlm_429_is_retried_then_succeeds():
    stub = VlmStub()
    stub.script_status(429)
    stub.script_content('{"latex": "x"}')
    client = make_vlm_client(stub)
    assert client.equation_ocr(IMG, "transcribe")["latex"] == "x"
    assert len(stub.requests) == 2


def test_vlm_5xx_exhausts_retries():
    from model_clients import MAX_RETRIES, ModelEndpointError

    stub = VlmStub()
    for _ in range(MAX_RETRIES + 1):
        stub.script_status(500)
    client = make_vlm_client(stub)
    with pytest.raises(ModelEndpointError) as excinfo:
        client.equation_ocr(IMG, "transcribe")
    assert len(stub.requests) == MAX_RETRIES + 1
    assert excinfo.value.status == 500


def test_vlm_4xx_is_not_retried():
    from model_clients import ModelEndpointError

    stub = VlmStub()
    stub.script_status(400)
    client = make_vlm_client(stub)
    with pytest.raises(ModelEndpointError) as excinfo:
        client.equation_ocr(IMG, "transcribe")
    assert len(stub.requests) == 1  # §2.3: no retry on 4xx contract errors
    assert excinfo.value.status == 400
    assert excinfo.value.code == "http_400"  # OpenAI error-JSON code surfaced


def test_vlm_backoff_is_exponential():
    from model_clients import MAX_RETRIES

    sleeps: list[float] = []
    stub = VlmStub()
    for _ in range(MAX_RETRIES + 1):
        stub.script_status(503)
    from model_clients import ModelEndpointError, VlmHttpClient

    client = VlmHttpClient(
        "http://vlm.stub.invalid",
        stub.token,
        stub.model,
        transport=stub.transport(),
        backoff_base_sec=1.0,
        sleep=sleeps.append,
    )
    with pytest.raises(ModelEndpointError):
        client.equation_ocr(IMG, "transcribe")
    assert sleeps == [1.0, 2.0]  # base * 2**attempt


def test_stage_attribution_mode_a_is_keyframe():
    """§2.3 / ADR 0004 §4: mode A failures attribute to stage `keyframe`."""
    from model_clients import STAGE_KEYFRAME, ModelEndpointError

    stub = VlmStub()
    stub.script_status(400)
    client = make_vlm_client(stub)
    with pytest.raises(ModelEndpointError) as excinfo:
        client.select_and_classify([IMG], "prompt")
    assert excinfo.value.stage == STAGE_KEYFRAME


def test_stage_attribution_mode_b_is_recognize():
    from model_clients import STAGE_RECOGNIZE, ModelEndpointError

    stub = VlmStub()
    stub.script_status(400)
    client = make_vlm_client(stub)
    with pytest.raises(ModelEndpointError) as excinfo:
        client.classify_crop(IMG, "prompt")
    assert excinfo.value.stage == STAGE_RECOGNIZE


# ── §3 — DocLayout-YOLO ──────────────────────────────────────────────────────


def test_yolo_detect_happy_path():
    stub = YoloStub()
    client = make_yolo_client(stub)
    result = client.detect(IMG)

    assert result.image.w == 1920 and result.image.h == 1080
    assert result.model_version == stub.model_version
    assert len(result.boxes) == 3  # default LOW threshold → over-detect (all boxes)
    box = result.boxes[0]
    assert (box.bbox.x, box.bbox.y, box.bbox.w, box.bbox.h) == (100, 80, 640, 360)
    assert box.score == 0.82


def test_yolo_detect_sends_over_detect_defaults():
    """§3.2: conf_threshold defaults LOW (0.15) and max_boxes to 50."""
    from model_clients import DEFAULT_CONF_THRESHOLD, DEFAULT_MAX_BOXES

    stub = YoloStub()
    client = make_yolo_client(stub)
    client.detect(IMG)
    payload = stub.request_payloads()[0]
    assert payload == {
        "image_url": IMG,
        "conf_threshold": DEFAULT_CONF_THRESHOLD,
        "max_boxes": DEFAULT_MAX_BOXES,
    }
    assert DEFAULT_CONF_THRESHOLD == 0.15
    assert DEFAULT_MAX_BOXES == 50


def test_yolo_higher_threshold_drops_low_score_boxes():
    """Over-detect is observable: raising the threshold loses recall."""
    stub = YoloStub()
    client = make_yolo_client(stub)
    assert len(client.detect(IMG, conf_threshold=0.5).boxes) == 1
    assert len(client.detect(IMG).boxes) == 3


def test_yolo_class_is_advisory_passthrough():
    """§3.4: class MUST NOT gate anything — every box survives, any class value,
    carried through verbatim (kind is decided by Qwen in mode B)."""
    stub = YoloStub()
    client = make_yolo_client(stub)
    boxes = client.detect(IMG).boxes
    assert [b.cls for b in boxes] == ["table", "figure", "isolate_formula"]


def test_yolo_health():
    stub = YoloStub()
    client = make_yolo_client(stub)
    health = client.health()
    assert health.status == "ok"
    assert health.model_version == stub.model_version


def test_yolo_error_shape_and_no_4xx_retry():
    from model_clients import STAGE_DETECT, ModelEndpointError

    stub = YoloStub()
    stub.script_error(422, "missing_image_url", "image_url is required")
    client = make_yolo_client(stub)
    with pytest.raises(ModelEndpointError) as excinfo:
        client.detect(IMG)
    assert len(stub.requests) == 1  # §3.4 4xx → no retry
    assert excinfo.value.status == 422
    assert excinfo.value.code == "missing_image_url"
    assert excinfo.value.stage == STAGE_DETECT  # ADR 0004 §4


def test_yolo_429_is_retried():
    stub = YoloStub()
    stub.script_error(429, "rate_limited", "slow down")
    client = make_yolo_client(stub)
    result = client.detect(IMG)
    assert len(stub.requests) == 2
    assert len(result.boxes) == 3


def test_yolo_5xx_exhausts_retries():
    from model_clients import MAX_RETRIES, ModelEndpointError

    stub = YoloStub()
    for _ in range(MAX_RETRIES + 1):
        stub.script_error(503, "overloaded", "gpu busy")
    client = make_yolo_client(stub)
    with pytest.raises(ModelEndpointError) as excinfo:
        client.detect(IMG)
    assert len(stub.requests) == MAX_RETRIES + 1
    assert excinfo.value.code == "overloaded"


def test_yolo_malformed_response_fails_validation():
    from model_clients import ModelEndpointError

    stub = YoloStub()
    stub.boxes = [{"bbox": {"x": 1}, "class": "table", "score": 0.9}]  # bbox missing y/w/h
    client = make_yolo_client(stub)
    with pytest.raises(ModelEndpointError):
        client.detect(IMG)


# ── §5 — dev-mode live-config refusal (mirrors VISION_API_PROVIDER gating) ───


def _live_env(**overrides):
    env = {
        "SLIDEGEN_VLM_BASE_URL": "https://vlm.example.invalid",
        "SLIDEGEN_VLM_TOKEN": "live-token",
        "SLIDEGEN_YOLO_BASE_URL": "https://yolo.example.invalid",
        "SLIDEGEN_YOLO_TOKEN": "live-token",
    }
    env.update(overrides)
    return env


def test_from_env_refuses_live_tokens_in_dev():
    from model_clients import LiveConfigRefusedError, VlmHttpClient, YoloHttpClient

    env = _live_env()  # SLIDEGEN_MODE unset → dev (fail-closed), no opt-in
    with pytest.raises(LiveConfigRefusedError):
        VlmHttpClient.from_env(env)
    with pytest.raises(LiveConfigRefusedError):
        YoloHttpClient.from_env(env)


def test_from_env_refuses_explicit_dev_mode():
    from model_clients import LiveConfigRefusedError, VlmHttpClient

    with pytest.raises(LiveConfigRefusedError):
        VlmHttpClient.from_env(_live_env(SLIDEGEN_MODE="dev"))


def test_from_env_allows_explicit_http_opt_in():
    from model_clients import VlmHttpClient, YoloHttpClient

    env = _live_env(SLIDEGEN_MODE="dev", SLIDEGEN_VLM_BACKEND="http")
    vlm = VlmHttpClient.from_env(env)
    yolo = YoloHttpClient.from_env(env)
    assert vlm.base_url == "https://vlm.example.invalid"
    assert yolo.base_url == "https://yolo.example.invalid"
    vlm.close()
    yolo.close()


def test_from_env_allows_prod_mode():
    from model_clients import DEFAULT_VLM_MODEL, VlmHttpClient

    client = VlmHttpClient.from_env(_live_env(SLIDEGEN_MODE="prod"))
    assert client.model == DEFAULT_VLM_MODEL
    client.close()


def test_from_env_requires_base_url():
    from model_clients import LiveConfigRefusedError, VlmHttpClient

    with pytest.raises(LiveConfigRefusedError):
        VlmHttpClient.from_env({"SLIDEGEN_MODE": "prod"})


def test_from_env_model_from_env_key():
    from model_clients import VlmHttpClient

    env = _live_env(SLIDEGEN_MODE="prod", SLIDEGEN_VLM_MODEL="qwen3-vl-custom")
    client = VlmHttpClient.from_env(env)
    assert client.model == "qwen3-vl-custom"
    client.close()


# ── vlm_router `http` backend (call shape A) ─────────────────────────────────


def test_get_backend_http_selection(monkeypatch):
    from vlm_router import ENV_BACKEND, HttpBackend, get_backend

    monkeypatch.setenv(ENV_BACKEND, "http")
    assert isinstance(get_backend(), HttpBackend)


def test_default_backend_still_mock(monkeypatch):
    """New env default = existing behavior: unset → mock, never http."""
    from vlm_router import ENV_BACKEND, MockBackend, get_backend

    monkeypatch.delenv(ENV_BACKEND, raising=False)
    assert isinstance(get_backend(), MockBackend)


def test_http_backend_routes_via_stub(tmp_path):
    from frames import FrameCandidate
    from vlm_router import VALID_FRAME_TYPES, HttpBackend

    frame = tmp_path / "frame_0001.jpg"
    frame.write_bytes(b"\xff\xd8\xff\xe0fakejpegbytes")

    stub = VlmStub()
    stub.script_content(
        '[{"is_slide": true, "contains_graph": true, "frame_type": "chart", '
        '"summary_hint": "loss curve", "confidence": 0.88}]'
    )
    backend = HttpBackend(client=make_vlm_client(stub))
    out = backend.route([FrameCandidate(frame, 12.0, 0, 0.9, True)])

    assert len(out) == 1
    assert out[0]["is_slide"] is True
    assert out[0]["frame_type"] in VALID_FRAME_TYPES

    # Local frames travel as data URLs inside standard image_url parts (§2.1).
    parts = stub.request_payloads()[0]["messages"][0]["content"]
    image_parts = [p for p in parts if p["type"] == "image_url"]
    assert len(image_parts) == 1
    assert image_parts[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_http_backend_normalizes_bad_frame_type(tmp_path):
    """Out-of-vocabulary frame_type from the endpoint falls back via _normalize."""
    from frames import FrameCandidate
    from vlm_router import HttpBackend

    frame = tmp_path / "frame_0002.png"
    frame.write_bytes(b"\x89PNGfake")

    stub = VlmStub()
    stub.script_content('[{"is_slide": true, "frame_type": "meme"}]')
    backend = HttpBackend(client=make_vlm_client(stub))
    out = backend.route([FrameCandidate(frame, 3.0, 0, 0.5, False)])
    assert out[0]["frame_type"] == "b_roll"


def test_http_backend_empty_input_no_calls():
    from vlm_router import HttpBackend

    backend = HttpBackend()  # no client constructed — would raise if touched
    assert backend.route([]) == []


def test_from_env_reads_timeout_knob():
    """PR-H2: SLIDEGEN_VLM_TIMEOUT_SEC overrides the 120 s default read budget
    (mode-A windows measured >120 s on the serving host)."""
    from model_clients import DEFAULT_TIMEOUT_SEC, VlmHttpClient

    env = _live_env(SLIDEGEN_MODE="prod", SLIDEGEN_VLM_TIMEOUT_SEC="300")
    vlm = VlmHttpClient.from_env(env)
    assert vlm._http.timeout.read == 300.0
    vlm.close()

    env_default = _live_env(SLIDEGEN_MODE="prod")
    vlm_default = VlmHttpClient.from_env(env_default)
    assert vlm_default._http.timeout.read == DEFAULT_TIMEOUT_SEC
    vlm_default.close()
