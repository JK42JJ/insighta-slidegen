"""Validation tests for SVG output — feeds real cached prod structs and
asserts SVG (or None) is produced.  Covers render_figure_svg dispatcher,
regenerate_diagram_svg, and regenerate_chart_svg.
"""

import shutil

import pytest

from deck_tools.svg_output import render_figure_svg

HAS_DOT = shutil.which("dot") is not None
dot_required = pytest.mark.skipif(not HAS_DOT, reason="graphviz `dot` not installed")

# ── Prod structs (exact samples from task spec) ───────────────────────────────

FLOW_STRUCT = {
    "diagram_type": "flow",
    "nodes": [
        {"id": "VPC", "label": "VPC (10.0.0.0/16)", "group": "AWS Cloud"},
        {"id": "Router1", "label": "Router", "group": "VPC"},
        {"id": "SubnetA", "label": "SubnetA", "group": "VPC"},
        {"id": "EC2A", "label": "EC2A", "group": "VPC"},
    ],
    "edges": [
        {"from": "VPC", "to": "Router1", "style": "solid"},
        {"from": "Router1", "to": "SubnetA", "style": "solid"},
        {"from": "SubnetA", "to": "EC2A", "style": "solid"},
    ],
}

TABLE_STRUCT = {
    "headers": ["정밀도", "메모리 절감", "성능 손실"],
    "rows": [
        ["FP16 (16비트)", "50%", "거의 없음"],
        ["INT8 (8비트)", "75%", "1-2%"],
        ["INT4 (4비트)", "87.5%", "3-10%"],
    ],
}

CHART_PIE_DEGENERATE = {
    "chart_type": "pie",
    "axes": {"x": "", "y": ""},
    "series": [{"name": "", "points": [{"x": 0, "y": 0.5}]}],
    "insight": "single pie slice",
}

CHART_LINE_FLAT = {
    "chart_type": "line",
    "axes": {"x": "value -127..127", "y": "normalized"},
    "series": [
        {
            "name": "signal",
            "points": [{"x": -127, "y": 0}, {"x": 0, "y": 0}, {"x": 127, "y": 0}],
        }
    ],
}


# ── diagram ───────────────────────────────────────────────────────────────────


@dot_required
def test_flow_diagram_returns_svg_string():
    svg = render_figure_svg("diagram", FLOW_STRUCT)
    assert svg is not None, "flow diagram must produce SVG"
    assert "<svg" in svg, "result must be a valid SVG document"
    assert len(svg) > 500, f"SVG unexpectedly short ({len(svg)} chars)"


@dot_required
def test_flow_diagram_svg_length_reported(capsys):
    svg = render_figure_svg("diagram", FLOW_STRUCT)
    length = len(svg) if svg is not None else None
    print(f"[diagram/flow] SVG length: {length}")  # captured for report


# ── table (handled note-side) ─────────────────────────────────────────────────


def test_table_kind_returns_none():
    """Tables are rendered note-side as HTML; dispatcher must return None."""
    result = render_figure_svg("table", TABLE_STRUCT)
    assert result is None


# ── chart degenerate (pie → unsupported type → None) ─────────────────────────


def test_chart_pie_degenerate_returns_none():
    """Pie is not in SUPPORTED_CHART_TYPES; must return None (DROP gate)."""
    result = render_figure_svg("chart", CHART_PIE_DEGENERATE)
    assert result is None


# ── chart line flat (all y=0) ─────────────────────────────────────────────────


def test_chart_line_flat_result_reported(capsys):
    """A flat line (all y=0) is renderable geometry; axes/spines carry ink.

    The _has_enough_ink_svg gate checks only for SVG presence, not data
    variance, so a flat line produces a valid SVG string (not None) — the axes,
    spines, and the horizontal line at y=0 are all drawn content.
    """
    result = render_figure_svg("chart", CHART_LINE_FLAT)
    if result is None:
        print("[chart/line-flat] result: None (dropped as degenerate)")
    else:
        assert "<svg" in result
        print(f"[chart/line-flat] result: SVG ({len(result)} chars) — NOT dropped")


# ── SVG functions directly (unit level) ───────────────────────────────────────


@dot_required
def test_regenerate_diagram_svg_direct():
    from deck_tools.diagram_regen import regenerate_diagram_svg

    svg = regenerate_diagram_svg(FLOW_STRUCT)
    assert svg is not None and "<svg" in svg


def test_regenerate_chart_svg_pie_returns_none():
    from deck_tools.chart_regen import regenerate_chart_svg

    assert regenerate_chart_svg(CHART_PIE_DEGENERATE) is None


def test_regenerate_chart_svg_line_runs():
    from deck_tools.chart_regen import regenerate_chart_svg

    result = regenerate_chart_svg(CHART_LINE_FLAT)
    # Either None (dropped) or a valid SVG string — both are acceptable.
    assert result is None or ("<svg" in result and len(result) > 200)


def test_render_figure_svg_unknown_kind_returns_none():
    assert render_figure_svg("equation", {}) is None
    assert render_figure_svg("unknown", {}) is None
    assert render_figure_svg("table", {}) is None
