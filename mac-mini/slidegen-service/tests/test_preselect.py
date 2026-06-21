"""
preselect (content-box prefilter) tests — the cheap [S] gate that runs the
DocLayout-YOLO detect client over the candidates and drops frames with no real
slide content BEFORE the VLM router (select-before-extract).

The yolo client is a tiny in-process fake returning a scripted DetectResponse
per call (in candidate order) — no httpx/model. Candidate paths point at 1-byte
stub files because preselect data-URL-encodes the bytes (the detector's reported
image size, not the file, drives the area math).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from frames import FrameCandidate
from preselect import has_real_content, preselect_candidates

FRAME_W = 1000
FRAME_H = 1000
FRAME_AREA = FRAME_W * FRAME_H


def _resp(boxes: list[dict]) -> dict:
    return {
        "image": {"w": FRAME_W, "h": FRAME_H},
        "model_version": "fake-yolo-0",
        "boxes": boxes,
    }


def _box(cls: str, w: int, h: int, score: float, x: int = 0, y: int = 0) -> dict:
    return {"bbox": {"x": x, "y": y, "w": w, "h": h}, "class": cls, "score": score}


# Box presets (frame area = 1_000_000; MIN_TEXT_AREA_FRAC=0.02 → 20_000 px²).
SUBSTANTIAL_TEXT = [_box("plain text", 300, 200, 0.5)]          # 60_000 ≥ 20_000 → keep
STRONG_FIGURE = [_box("figure", 400, 400, 0.90)]               # diagram ≥ 0.80 → keep
LECTURER_ONLY = [_box("figure", 300, 300, 0.42)]              # low-conf, small, 1 box → drop
EMPTY: list[dict] = []                                          # no boxes → drop
TINY_TEXT_SLIVER = [_box("plain text", 100, 80, 0.5)]         # 8_000 < 20_000 → drop
CHROME_ONLY = [_box("abandon", 900, 60, 0.7)]                 # 'drop' kind only → drop
LARGE_DIAGRAM_RESCUE = [_box("figure", 600, 600, 0.40), _box("plain text", 80, 60, 0.5)]


class _FakeYolo:
    """Returns a scripted DetectResponse per .detect() call, in candidate order."""

    def __init__(self, responses: list[dict], *, raise_on: set[int] | None = None) -> None:
        self._responses = responses
        self._raise_on = raise_on or set()
        self.calls = 0

    def detect(self, image_url: str):
        from model_clients import DetectResponse

        i = self.calls
        self.calls += 1
        if i in self._raise_on:
            raise RuntimeError("simulated detect failure")
        return DetectResponse.model_validate(self._responses[i])


def _candidate(tmp_path: Path, name: str, ts: float) -> FrameCandidate:
    p = tmp_path / f"{name}.jpg"
    p.write_bytes(b"x")  # _image_data_url only base64-encodes the bytes
    return FrameCandidate(
        path=p, timestamp_sec=ts, section_index=0, quality_score=0.5, is_scene_boundary=False
    )


# ── has_real_content unit cases ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "boxes, expected",
    [
        (SUBSTANTIAL_TEXT, True),
        (STRONG_FIGURE, True),
        (LARGE_DIAGRAM_RESCUE, True),
        (LECTURER_ONLY, False),
        (EMPTY, False),
        (TINY_TEXT_SLIVER, False),
        (CHROME_ONLY, False),
    ],
)
def test_has_real_content(boxes: list[dict], expected: bool) -> None:
    from model_clients import DetectResponse

    resp = DetectResponse.model_validate(_resp(boxes))
    assert has_real_content(resp.boxes, float(FRAME_AREA)) is expected


# ── preselect_candidates end-to-end (fake yolo) ──────────────────────────────


def test_preselect_keeps_content_drops_empty(tmp_path: Path) -> None:
    cands = [
        _candidate(tmp_path, "content", 1.0),
        _candidate(tmp_path, "empty", 2.0),
        _candidate(tmp_path, "lecturer", 3.0),
        _candidate(tmp_path, "figure", 4.0),
    ]
    yolo = _FakeYolo([_resp(SUBSTANTIAL_TEXT), _resp(EMPTY), _resp(LECTURER_ONLY), _resp(STRONG_FIGURE)])

    kept = preselect_candidates(cands, yolo=yolo)

    assert [c.timestamp_sec for c in kept] == [1.0, 4.0]  # content + strong figure
    assert yolo.calls == 4  # detected every candidate


def test_preselect_keeps_on_detect_error(tmp_path: Path) -> None:
    """Recall-first: a detect failure KEEPS the frame (the VLM router still vets it)."""
    cands = [_candidate(tmp_path, "ok", 1.0), _candidate(tmp_path, "boom", 2.0)]
    yolo = _FakeYolo([_resp(EMPTY), _resp(EMPTY)], raise_on={1})

    kept = preselect_candidates(cands, yolo=yolo)

    assert [c.timestamp_sec for c in kept] == [2.0]  # 'ok' dropped (empty), 'boom' kept (error)


def test_preselect_empty_input() -> None:
    assert preselect_candidates([], yolo=_FakeYolo([])) == []
