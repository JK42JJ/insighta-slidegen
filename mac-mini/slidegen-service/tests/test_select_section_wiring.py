"""v2 section-summary → Qwen select wiring tests (PR-F1).

Proves, at two layers, that the v2 rich-summary section text reaches the
mode-A select+classify call (CONTRACT_model-endpoints §2.2) as grounding
context (ADR 0002 D4/D5):

    1. Wire-level   — through the stub transport, the mode-A request payload's
                      text part CONTAINS the exact section summary string for
                      the window being routed.
    2. Behavioral   — a scripted stub LLM whose selection DEPENDS on the
                      captions text yields a different selection for the SAME
                      frame set with vs without summaries — so a frames-only
                      regression would fail this suite.

Per ADR 0002 D5 the text is a HINT for the model's grounding only: the code
under test never keeps/drops a frame based on section text, and every
candidate is always routed (no-overlap candidates get a no-context window).

All fixtures are synthetic (PUBLIC repo — no real video IDs / hosts).
"""

import json

import httpx
from stubs.vlm_stub import VlmStub

# Synthetic section text (fixtures only — never real user-video content).
INTRO_TITLE = "Intro"
INTRO_SUMMARY = "Synthetic intro: derivation of the toy loss function."
METHOD_TITLE = "Method"
METHOD_SUMMARY = "Synthetic method: ablation table comparing optimizer variants."

# Marker token the caption-aware stub keys its selection on (behavioral test).
MARKER = "SYNTH-ABLATION-TABLE"

FAKE_JPEG_BYTES = b"\xff\xd8\xff\xe0fakejpegbytes"


def _sections():
    """Two synthetic v2 sections, as app.py's Section.model_dump() dicts."""
    return [
        {
            "index": 0,
            "from_sec": 0.0,
            "to_sec": 10.0,
            "title": INTRO_TITLE,
            "summary": INTRO_SUMMARY,
        },
        {
            "index": 1,
            "from_sec": 10.0,
            "to_sec": 20.0,
            "title": METHOD_TITLE,
            "summary": METHOD_SUMMARY,
        },
    ]


def _frames(tmp_path, timestamps):
    """Real (fake-byte) frame files so HttpBackend can data-URL them."""
    from frames import FrameCandidate

    candidates = []
    for i, t in enumerate(timestamps):
        path = tmp_path / f"frame_{i:04d}.jpg"
        path.write_bytes(FAKE_JPEG_BYTES)
        candidates.append(FrameCandidate(path, float(t), 0, 0.8, False))
    return candidates


def _http_backend(stub: VlmStub):
    """An HttpBackend wired to the in-process stub transport (no network)."""
    from model_clients import VlmHttpClient
    from vlm_router import HttpBackend

    client = VlmHttpClient(
        "http://vlm.stub.invalid",
        stub.token,
        stub.model,
        transport=stub.transport(),
        backoff_base_sec=0.0,
        sleep=lambda _s: None,
    )
    return HttpBackend(client=client)


def _texts_of(payload) -> str:
    parts = payload["messages"][0]["content"]
    return " ".join(p["text"] for p in parts if p["type"] == "text")


def _image_count(payload) -> int:
    parts = payload["messages"][0]["content"]
    return sum(1 for p in parts if p["type"] == "image_url")


# ── Layer 1: wire-level — summary string reaches the mode-A payload ──────────


def test_select_request_carries_section_summaries(tmp_path, monkeypatch):
    """The mode-A request for each window carries THAT window's section
    summary verbatim as a text part — and not the other window's."""
    import vlm_router
    from typing_select import select_keyframes

    stub = VlmStub()
    stub.script_content(
        '[{"is_slide": true}, {"is_slide": true}]',  # window 1: frames @2s, @5s
        '[{"is_slide": true}]',  # window 2: frame @15s
    )
    backend = _http_backend(stub)
    monkeypatch.setattr(vlm_router, "get_backend", lambda *a, **k: backend)

    candidates = _frames(tmp_path, [2.0, 5.0, 15.0])
    result = select_keyframes(candidates, [], sections=_sections())
    assert len(result) == 3  # selection itself is the model's call, not the text's

    payloads = stub.request_payloads()
    assert len(payloads) == 2  # one batched call per section window (ADR 0002 D4)
    assert [_image_count(p) for p in payloads] == [2, 1]

    # Window 1 (Intro, [0-10s]) carries the Intro text — exactly, and only it.
    assert INTRO_SUMMARY in _texts_of(payloads[0])
    assert f"[0-10s] {INTRO_TITLE}: {INTRO_SUMMARY}" in _texts_of(payloads[0])
    assert METHOD_SUMMARY not in _texts_of(payloads[0])

    # Window 2 (Method, [10-20s]) carries the Method text — and only it.
    assert METHOD_SUMMARY in _texts_of(payloads[1])
    assert INTRO_SUMMARY not in _texts_of(payloads[1])


def test_select_request_without_sections_has_no_summary_text(tmp_path, monkeypatch):
    """Default (sections=None) keeps the previous wire shape: a single call
    whose only text part is the routing prompt — no companion text."""
    import vlm_router
    from typing_select import select_keyframes
    from vlm_router import build_routing_prompt

    stub = VlmStub()
    stub.script_content('[{"is_slide": true}, {"is_slide": true}]')
    backend = _http_backend(stub)
    monkeypatch.setattr(vlm_router, "get_backend", lambda *a, **k: backend)

    candidates = _frames(tmp_path, [2.0, 15.0])
    select_keyframes(candidates, [])

    payloads = stub.request_payloads()
    assert len(payloads) == 1
    parts = payloads[0]["messages"][0]["content"]
    text_parts = [p["text"] for p in parts if p["type"] == "text"]
    assert text_parts == [build_routing_prompt(2)]


# ── Layer 2: behavioral regression-block — selection depends on the text ─────


class CaptionAwareVlmStub(VlmStub):
    """A scripted stub LLM whose selection DEPENDS on the captions text.

    It marks is_slide=true for a window's frames only when the window's
    companion text mentions MARKER — emulating a model that needs the section
    summary to recognize the frames as knowledge-bearing. A frames-only
    request (no summaries) therefore selects nothing.
    """

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        payload = json.loads(request.content)
        parts = payload["messages"][0]["content"]
        n_images = sum(1 for p in parts if p["type"] == "image_url")
        window_text = " ".join(p["text"] for p in parts if p["type"] == "text")
        is_slide = MARKER in window_text
        body = json.dumps(
            [{"is_slide": is_slide, "frame_type": "table", "confidence": 0.9}]
            * n_images
        )
        return httpx.Response(200, json=self._completion(body))


def test_selection_changes_with_vs_without_summaries(tmp_path, monkeypatch):
    """The SAME frame set yields different selections with vs without the
    section summaries — proving the summaries actually ground the select call
    (a frames-only wiring regression would make both runs identical)."""
    import vlm_router
    from typing_select import select_keyframes

    marker_sections = [
        {
            "index": 0,
            "from_sec": 0.0,
            "to_sec": 10.0,
            "title": INTRO_TITLE,
            "summary": "Synthetic intro with no figures.",
        },
        {
            "index": 1,
            "from_sec": 10.0,
            "to_sec": 20.0,
            "title": METHOD_TITLE,
            "summary": f"Synthetic method section showing the {MARKER} results.",
        },
    ]
    candidates = _frames(tmp_path, [2.0, 5.0, 15.0])  # identical in both runs

    def run(sections_arg):
        backend = _http_backend(CaptionAwareVlmStub())
        monkeypatch.setattr(vlm_router, "get_backend", lambda *a, **k: backend)
        return select_keyframes(candidates, [], sections=sections_arg)

    with_summaries = run(marker_sections)
    without_summaries = run(None)

    # With summaries: the Method window's frame is recognized and selected.
    assert [s.candidate.timestamp_sec for s in with_summaries] == [15.0]
    # Without summaries: nothing selected — frames-only would fail this suite.
    assert without_summaries == []
    assert with_summaries != without_summaries


# ── Windowing unit tests (grouping + hint format + hint-never-gates) ─────────


def test_window_candidates_groups_by_section_overlap(tmp_path):
    """Candidates group into one window per best-overlapping section, with
    original input order preserved inside each window."""
    from typing_select import _window_candidates

    candidates = _frames(tmp_path, [2.0, 15.0, 5.0])
    windows = _window_candidates(candidates, _sections())

    by_text = {text: indices for text, indices in windows}
    assert by_text[f"[0-10s] {INTRO_TITLE}: {INTRO_SUMMARY}"] == [0, 2]
    assert by_text[f"[10-20s] {METHOD_TITLE}: {METHOD_SUMMARY}"] == [1]


def test_window_candidates_no_overlap_still_routes(tmp_path):
    """A candidate overlapping NO section is still routed (no-context window):
    section text can never gate a frame out of the pipeline (ADR 0002 D5)."""
    from typing_select import _window_candidates

    candidates = _frames(tmp_path, [2.0, 99.0])  # 99s is outside both sections
    windows = _window_candidates(candidates, _sections())

    routed = sorted(i for _, indices in windows for i in indices)
    assert routed == [0, 1]
    assert any(text is None and indices == [1] for text, indices in windows)


def test_window_candidates_without_sections_single_window(tmp_path):
    """sections=None / [] → one no-context window (existing behavior)."""
    from typing_select import _window_candidates

    candidates = _frames(tmp_path, [2.0, 15.0])
    assert _window_candidates(candidates, None) == [(None, [0, 1])]
    assert _window_candidates(candidates, []) == [(None, [0, 1])]


def test_format_section_hint_with_and_without_summary():
    from typing_select import SectionContext, format_section_hint

    full = SectionContext(0, 0.0, 90.5, "Synthetic Title", "synthetic summary")
    assert format_section_hint(full) == "[0-90.5s] Synthetic Title: synthetic summary"

    title_only = SectionContext(1, 90.5, 120.0, "Outro", None)
    assert format_section_hint(title_only) == "[90.5-120s] Outro"


def test_section_context_accepts_model_dump_dicts():
    """app.py passes Section.model_dump() dicts — coercion keeps the text."""
    from typing_select import _coerce_section

    section = _coerce_section(
        {"index": 1, "from_sec": 10.0, "to_sec": 20.0, "title": "T", "summary": "S"}
    )
    assert (section.index, section.title, section.summary) == (1, "T", "S")

    minimal = _coerce_section({"from_sec": 0.0, "to_sec": 5.0})
    assert (minimal.title, minimal.summary) == ("", None)


def test_select_keyframes_existing_callsites_still_compile():
    """The pre-PR-F1 3-arg call shape keeps working (defaulted sections)."""
    from typing_select import select_keyframes

    assert select_keyframes([], [], "dev") == []


def test_mock_backend_accepts_captions_text():
    """Local backends accept (and may ignore) captions_text — protocol parity."""
    from pathlib import Path

    from frames import FrameCandidate
    from vlm_router import MockBackend

    candidates = [FrameCandidate(Path("/tmp/f_0.jpg"), 0.0, 0, 0.8, False)]
    with_text = MockBackend().route(candidates, "[0-10s] Intro: synthetic")
    without_text = MockBackend().route(candidates)
    assert with_text == without_text  # mock ignores the hint (never a gate)
