"""POST /render-figure — CPU-only SVG render endpoint.

Covers:
  - diagram struct (flow) → svg non-null  (dot_required skip guard)
  - degenerate pie chart  → svg null      (unsupported chart_type)
  - table / equation kind → svg null      (rendered note-side)
  - exception in render_figure_svg is swallowed; endpoint returns {svg:null}

The endpoint calls deck_tools.svg_output.render_figure_svg directly (no
subprocess). app.py injects SLIDEGEN_PY_DIR (or a __file__-relative fallback)
onto sys.path at import time, so deck_tools is importable for all tests in
this file.
"""

import shutil

import pytest
from fastapi.testclient import TestClient

from app import app

HAS_DOT = shutil.which("dot") is not None
dot_required = pytest.mark.skipif(not HAS_DOT, reason="graphviz `dot` not installed")

client = TestClient(app)

# ── fixtures ──────────────────────────────────────────────────────────────────

FLOW_STRUCT = {
    "diagram_type": "flow",
    "nodes": [
        {"id": "A", "label": "Input"},
        {"id": "B", "label": "Process"},
        {"id": "C", "label": "Output"},
    ],
    "edges": [
        {"from": "A", "to": "B"},
        {"from": "B", "to": "C"},
    ],
}

CHART_PIE_DEGENERATE = {
    "chart_type": "pie",
    "axes": {"x": "", "y": ""},
    "series": [{"name": "share", "points": [{"x": "A", "y": 0.5}]}],
    "insight": "single slice",
}

CHART_LINE_VALID = {
    "chart_type": "line",
    "axes": {"x": "step", "y": "loss"},
    "series": [
        {
            "name": "train",
            "points": [{"x": 1, "y": 2.5}, {"x": 2, "y": 1.8}, {"x": 3, "y": 1.2}],
        }
    ],
}


# ── diagram ───────────────────────────────────────────────────────────────────


@dot_required
def test_diagram_flow_returns_svg():
    """A valid flow diagram struct must produce a non-null SVG string."""
    resp = client.post("/render-figure", json={"kind": "diagram", "struct": FLOW_STRUCT})
    assert resp.status_code == 200
    body = resp.json()
    assert body["svg"] is not None, "flow diagram must yield SVG"
    assert "<svg" in body["svg"]
    assert len(body["svg"]) > 200


# ── degenerate pie → null ─────────────────────────────────────────────────────


def test_chart_pie_degenerate_returns_null():
    """Pie is not in SUPPORTED_CHART_TYPES; endpoint must return {svg: null}."""
    resp = client.post("/render-figure", json={"kind": "chart", "struct": CHART_PIE_DEGENERATE})
    assert resp.status_code == 200
    assert resp.json()["svg"] is None


# ── table / equation (note-side) ──────────────────────────────────────────────


def test_table_kind_returns_null():
    """Tables are rendered note-side; endpoint must return {svg: null}."""
    resp = client.post(
        "/render-figure",
        json={"kind": "table", "struct": {"headers": ["A"], "rows": [["1"]]}},
    )
    assert resp.status_code == 200
    assert resp.json()["svg"] is None


def test_equation_kind_returns_null():
    """Equations are rendered note-side (KaTeX); endpoint must return {svg: null}."""
    resp = client.post(
        "/render-figure",
        json={"kind": "equation", "struct": {"latex": "E = mc^2"}},
    )
    assert resp.status_code == 200
    assert resp.json()["svg"] is None


# ── chart line (CPU-only, no dot required) ────────────────────────────────────


def test_chart_line_valid_returns_svg():
    """A valid line chart must produce a non-null SVG (matplotlib, no dot)."""
    resp = client.post("/render-figure", json={"kind": "chart", "struct": CHART_LINE_VALID})
    assert resp.status_code == 200
    body = resp.json()
    assert body["svg"] is not None, "valid line chart must yield SVG"
    assert "<svg" in body["svg"]


# ── fail-closed: exception inside render_figure_svg ──────────────────────────


def test_exception_in_render_returns_null(monkeypatch):
    """Any exception from render_figure_svg must be caught; endpoint returns {svg: null}."""
    import deck_tools.svg_output as svg_mod

    def _boom(kind, struct):
        raise RuntimeError("simulated render failure")

    monkeypatch.setattr(svg_mod, "render_figure_svg", _boom)
    resp = client.post("/render-figure", json={"kind": "chart", "struct": CHART_LINE_VALID})
    assert resp.status_code == 200
    assert resp.json()["svg"] is None
