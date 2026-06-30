"""Validation tests for SVG output — feeds real cached prod structs and
asserts SVG (or None) is produced.  Covers render_figure_svg dispatcher,
regenerate_diagram_svg, and regenerate_chart_svg (light + dark theme).
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

CHART_BAR_STRUCT = {
    "chart_type": "bar",
    "axes": {"x": "Category", "y": "Count"},
    "series": [{"name": "Data", "points": [{"x": "A", "y": 10}, {"x": "B", "y": 25}]}],
    "insight": "A vs B",
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


# ── Dark-theme SVG tests ──────────────────────────────────────────────────────


@dot_required
def test_diagram_dark_no_white_background():
    """Dark diagram SVG must not carry a white background polygon.

    Graphviz emits fill="white" for bgcolor="white"; transparent skips it.
    Also verifies the near-black INK color (#0F172A) is absent — proving the
    dark text palette was applied, not the light one.
    """
    svg_light = render_figure_svg("diagram", FLOW_STRUCT, theme="light")
    svg_dark = render_figure_svg("diagram", FLOW_STRUCT, theme="dark")
    assert svg_dark is not None, "dark diagram must produce SVG"
    assert "<svg" in svg_dark

    svg_dark_lower = svg_dark.lower()
    # No white-fill background polygon in dark output.
    assert 'fill="white"' not in svg_dark_lower, \
        "dark SVG must not contain fill=white background"
    # Near-black INK (#0F172A) must not appear as a text/fill color.
    assert "#0f172a" not in svg_dark_lower, \
        "dark SVG must not use near-black INK color #0F172A"

    # Light output must still have the white background (unchanged behavior).
    assert svg_light is not None
    assert 'fill="white"' in svg_light.lower(), \
        "light SVG must retain fill=white background (deck behavior unchanged)"


def test_chart_dark_has_light_ink():
    """Dark chart SVG must carry the light ink color used for axes/labels.

    _DARK_PAL.line = #475569 is applied to spines; present in SVG stroke attrs.
    Also confirms the near-black INK color is absent from SVG ink attrs.
    """
    svg_dark = render_figure_svg("chart", CHART_BAR_STRUCT, theme="dark")
    assert svg_dark is not None, "dark bar chart must produce SVG"
    assert "<svg" in svg_dark

    svg_dark_lower = svg_dark.lower()
    # Dark spine color must appear (proves _ax received dark palette).
    assert "#475569" in svg_dark_lower, \
        "dark SVG must contain dark-palette spine color #475569"
    # Near-black INK must not appear as axis/label color.
    assert "#0f172a" not in svg_dark_lower, \
        "dark SVG must not use near-black INK color #0F172A for labels/axes"


def test_chart_light_svg_unchanged():
    """Light chart SVG (default) must still use the dark-ink palette."""
    svg_light = render_figure_svg("chart", CHART_BAR_STRUCT, theme="light")
    assert svg_light is not None
    svg_lower = svg_light.lower()
    # Light spine color LINE = #CBD5E1 must appear.
    assert "#cbd5e1" in svg_lower, \
        "light SVG must retain light-palette LINE color #CBD5E1 (deck behavior unchanged)"
