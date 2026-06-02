"""Unit tests for vlm_router.py (pluggable local VLM router backend, ADR 0001)."""

from pathlib import Path

import pytest


def _candidates(n):
    from frames import FrameCandidate

    return [FrameCandidate(Path(f"/tmp/f_{i}.jpg"), float(i), 0, 0.8, False) for i in range(n)]


def test_mock_backend_one_dict_per_frame():
    """The mock backend returns one routing dict per candidate, in order."""
    from vlm_router import MockBackend

    candidates = _candidates(5)
    out = MockBackend().route(candidates)
    assert len(out) == 5
    assert all(isinstance(r, dict) for r in out)


def test_mock_backend_routing_contract():
    """Each routing dict carries the full ADR 0001 contract with valid types."""
    from vlm_router import VALID_FRAME_TYPES, MockBackend

    r = MockBackend().route(_candidates(1))[0]
    assert set(r) == {
        "is_slide",
        "contains_graph",
        "contains_equation",
        "frame_type",
        "summary_hint",
        "confidence",
    }
    assert isinstance(r["is_slide"], bool)
    assert r["frame_type"] in VALID_FRAME_TYPES
    assert 0.0 <= r["confidence"] <= 1.0


def test_mock_backend_deterministic():
    """The mock backend is reproducible (no randomness) for stable tests."""
    from vlm_router import MockBackend

    candidates = _candidates(4)
    assert MockBackend().route(candidates) == MockBackend().route(candidates)


def test_route_frames_empty():
    """route_frames short-circuits on empty input without a backend call."""
    from vlm_router import route_frames

    assert route_frames([]) == []


def test_get_backend_default_is_mock(monkeypatch):
    """Unset SLIDEGEN_VLM_BACKEND → mock (new env default = existing behavior)."""
    from vlm_router import ENV_BACKEND, MockBackend, get_backend

    monkeypatch.delenv(ENV_BACKEND, raising=False)
    assert isinstance(get_backend(), MockBackend)


def test_get_backend_env_selection(monkeypatch):
    """SLIDEGEN_VLM_BACKEND selects the backend (case-insensitive)."""
    from vlm_router import ENV_BACKEND, MLXBackend, TransformersBackend, get_backend

    monkeypatch.setenv(ENV_BACKEND, "transformers")
    assert isinstance(get_backend(), TransformersBackend)
    monkeypatch.setenv(ENV_BACKEND, "MLX")
    assert isinstance(get_backend(), MLXBackend)


def test_get_backend_unknown_raises(monkeypatch):
    """An unknown backend name fails loudly rather than silently no-op."""
    from vlm_router import ENV_BACKEND, get_backend

    monkeypatch.setenv(ENV_BACKEND, "gpt-vision-api")
    with pytest.raises(ValueError):
        get_backend()


def test_get_backend_model_override(monkeypatch):
    """SLIDEGEN_VLM_MODEL overrides the model (ADR D9 3B fallback)."""
    from vlm_router import ENV_MODEL, get_backend

    monkeypatch.setenv(ENV_MODEL, "qwen2.5-vl-3b-instruct")
    assert get_backend().model == "qwen2.5-vl-3b-instruct"


def test_parse_routing_response_array():
    """A clean JSON array parses to one normalized dict per candidate."""
    from vlm_router import parse_routing_response

    text = (
        '[{"is_slide": true, "contains_graph": true, "contains_equation": false, '
        '"frame_type": "chart", "summary_hint": "revenue", "confidence": 0.8}]'
    )
    out = parse_routing_response(text, _candidates(1))
    assert len(out) == 1
    assert out[0]["frame_type"] == "chart"
    assert out[0]["contains_graph"] is True


def test_parse_routing_response_tolerates_prose():
    """Leading/trailing prose around the JSON array is tolerated."""
    from vlm_router import parse_routing_response

    text = 'Here is the routing:\n[{"is_slide": false}]\nDone.'
    out = parse_routing_response(text, _candidates(1))
    assert out[0]["is_slide"] is False


def test_parse_routing_response_pads_and_truncates():
    """Result length always matches candidate count (pad short, truncate long)."""
    from vlm_router import parse_routing_response

    short = parse_routing_response("[]", _candidates(3))
    assert len(short) == 3
    assert all(r["is_slide"] is False for r in short)  # default-padded

    long = parse_routing_response(
        '[{"is_slide": true}, {"is_slide": true}, {"is_slide": true}]',
        _candidates(2),
    )
    assert len(long) == 2


def test_parse_routing_response_invalid_frame_type():
    """An out-of-vocabulary frame_type falls back to a valid default."""
    from vlm_router import VALID_FRAME_TYPES, parse_routing_response

    out = parse_routing_response('[{"frame_type": "meme"}]', _candidates(1))
    assert out[0]["frame_type"] in VALID_FRAME_TYPES


def test_parse_routing_response_no_array_raises():
    """A response with no JSON array raises rather than returning junk."""
    from vlm_router import parse_routing_response

    with pytest.raises(ValueError):
        parse_routing_response("no json here", _candidates(1))


def test_route_with_vlm_integration_via_mock(monkeypatch):
    """typing_select._route_with_vlm runs end-to-end on the real mock backend."""
    from vlm_router import ENV_BACKEND

    monkeypatch.setenv(ENV_BACKEND, "mock")
    from typing_select import RoutingMetadata, _route_with_vlm

    candidates = _candidates(3)
    routings = _route_with_vlm(candidates)
    assert len(routings) == 3
    assert all(isinstance(r, RoutingMetadata) for r in routings)


def test_select_keyframes_end_to_end_mock(monkeypatch):
    """select_keyframes works without patching _route_with_vlm (real mock path)."""
    from vlm_router import ENV_BACKEND

    monkeypatch.setenv(ENV_BACKEND, "mock")
    from typing_select import select_keyframes

    result = select_keyframes(_candidates(6), [])
    assert len(result) == 6  # mock marks all as slides
    assert all(s.frame_type for s in result)
