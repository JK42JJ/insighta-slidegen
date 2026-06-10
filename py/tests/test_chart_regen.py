"""Tests for deck_tools/chart_regen.py — struct-JSON → ≥300-dpi matplotlib PNG.

No network, no GPU; matplotlib Agg only. Unknown structs must return None
(the caller falls back to label-only — never to a raw frame, ADR 0003 P2).
"""

from PIL import Image

from deck_tools.chart_regen import FIGURE_DPI, SUPPORTED_CHART_TYPES, regenerate_chart

LINE_STRUCT = {
    "chart_type": "line",
    "axes": {"x": "epoch", "y": "loss"},
    "series": [
        {"name": "train", "points": [{"x": 1, "y": 0.9}, {"x": 2, "y": 0.5}, {"x": 3, "y": 0.3}]},
        {"name": "val", "points": [{"x": 1, "y": 1.0}, {"x": 2, "y": 0.7}, {"x": 3, "y": 0.6}]},
    ],
    "insight": "loss decreases over epochs",
}

BAR_STRUCT = {
    "chart_type": "bar",
    "axes": {"x": "provider", "y": "$/hour"},
    # Reference {"label","value"} point form (extract_resources.js CHART_TO_DATA).
    "series": [
        {"name": "", "points": [{"label": "A", "value": 0.04}, {"label": "B", "value": 0.36}]}
    ],
}

SCATTER_STRUCT = {
    "chart_type": "scatter",
    "series": [{"name": "data", "points": [{"x": 1, "y": 2}, {"x": 2, "y": 3}, {"x": 4, "y": 5}]}],
}


def test_line_chart_regenerates_at_300_dpi(tmp_path):
    out = tmp_path / "line.png"
    assert regenerate_chart(LINE_STRUCT, out) == str(out)
    assert out.exists()
    with Image.open(out) as image:
        dpi = image.info.get("dpi")
        assert dpi is not None
        # PNG stores dpi as integer pixels-per-meter (300 dpi → 11811 px/m →
        # 299.9994 on read-back); round() recovers the authored density.
        assert round(dpi[0]) >= FIGURE_DPI and round(dpi[1]) >= FIGURE_DPI
    assert FIGURE_DPI >= 300  # vector-300dpi quality gate (ADR 0003 D1)


def test_bar_chart_with_label_value_points(tmp_path):
    out = tmp_path / "bar.png"
    assert regenerate_chart(BAR_STRUCT, out) == str(out)
    assert out.exists()


def test_scatter_chart(tmp_path):
    out = tmp_path / "scatter.png"
    assert regenerate_chart(SCATTER_STRUCT, out) == str(out)
    assert out.exists()


def test_unknown_chart_type_returns_none(tmp_path):
    out = tmp_path / "nope.png"
    assert regenerate_chart({"chart_type": "pie3d-exploded", "series": []}, out) is None
    assert regenerate_chart({}, out) is None
    assert regenerate_chart("not a dict", out) is None
    assert not out.exists()


def test_struct_without_numeric_data_returns_none(tmp_path):
    out = tmp_path / "empty.png"
    assert regenerate_chart({"chart_type": "line", "series": []}, out) is None
    assert regenerate_chart({"chart_type": "line"}, out) is None
    assert (
        regenerate_chart(
            {"chart_type": "bar", "series": [{"points": [{"label": "A", "value": "n/a"}]}]}, out
        )
        is None
    )
    assert not out.exists()


def test_supported_kinds_are_the_mode_b_basic_set():
    assert SUPPORTED_CHART_TYPES == ("line", "bar", "scatter")
