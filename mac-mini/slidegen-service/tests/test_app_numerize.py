"""POST /numerize (⑤ get-or-extract COMPUTE adapter) — maps ExtractedFigure
struct/latex into the cache-row shape and builds acquire sections from ts.

Patches the acquire boundary + CV stages so the test exercises the adapter
mapping only (no yt-dlp, no pod). The real end-to-end run is a live smoke.
"""
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def client(monkeypatch, tmp_path):
    import app as app_module
    from figure_extract import ExtractedFigure

    captured: dict = {}

    def fake_download(video_id, sections, output_root="/tmp/slidegen-frames"):
        captured["sections"] = sections
        d = tmp_path / video_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "video.mp4").write_bytes(b"x")
        return d

    monkeypatch.setattr(app_module, "download_frames", fake_download)
    monkeypatch.setattr(app_module, "extract_candidates", lambda *a, **k: [])
    monkeypatch.setattr(app_module, "preselect_candidates", lambda c, **k: c)
    monkeypatch.setattr(app_module, "detect_topic_changes", lambda *a, **k: [])
    monkeypatch.setattr(app_module, "select_keyframes", lambda *a, **k: [])
    monkeypatch.setattr(app_module, "_build_extraction_clients", lambda: (object(), object()))

    figs = [
        ExtractedFigure(
            cv_figure_id="f1",
            kind="diagram",
            png_path="/t/c1.png",
            caption=None,
            timestamp_sec=42,
            extracted_latex=None,
            bbox=None,
            extraction_conf=0.9,
            struct={"diagram_type": "flow", "nodes": [{"id": "n1"}], "edges": []},
            verification_status="unverified",
        ),
        ExtractedFigure(
            cv_figure_id="f2",
            kind="equation",
            png_path="/t/c2.png",
            caption=None,
            timestamp_sec=43,
            extracted_latex="y = ax + b",
            bbox=None,
            extraction_conf=0.95,
            struct=None,
            verification_status="verified",
        ),
    ]
    monkeypatch.setattr(app_module, "cv_extract_figures", lambda *a, **k: figs)
    return TestClient(app_module.app), captured


def test_numerize_maps_struct_and_latex_to_cache_shape(client):
    cli, captured = client
    r = cli.post("/numerize", json={"video_id": "abcdefghijk", "ts": [42], "mode": "dev"})
    assert r.status_code == 200
    figures = r.json()["figures"]
    assert len(figures) == 2

    diagram = figures[0]
    assert diagram["kind"] == "diagram"
    assert diagram["ts_sec"] == 42
    assert diagram["struct"]["diagram_type"] == "flow"
    assert diagram["latex"] is None
    assert diagram["asset_path"] == "/t/c1.png"
    assert diagram["verification_status"] == "unverified"

    equation = figures[1]
    assert equation["kind"] == "equation"
    assert equation["latex"] == "y = ax + b"
    assert equation["struct"] is None


def test_numerize_builds_sections_window_from_ts(client):
    cli, captured = client
    cli.post("/numerize", json={"video_id": "abcdefghijk", "ts": [42, 5], "mode": "dev"})
    secs = captured["sections"]
    assert secs[0] == {"index": 0, "from_sec": 32.0, "to_sec": 52.0}  # 42 ± 10
    assert secs[1] == {"index": 1, "from_sec": 0.0, "to_sec": 15.0}  # 5 ± 10, clamped at 0
