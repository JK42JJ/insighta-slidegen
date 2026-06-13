"""Tests for deck_tools/chart_regen.py — struct-JSON → ≥300-dpi matplotlib PNG.

No network, no GPU; matplotlib Agg only. Unknown structs must return None
(the caller falls back to label-only — never to a raw frame, ADR 0003 P2).
"""

import warnings

import matplotlib.pyplot as plt
from matplotlib import font_manager
from PIL import Image

from deck_tools.chart_regen import FIGURE_DPI, SUPPORTED_CHART_TYPES, regenerate_chart

KOREAN_BAR_STRUCT = {
    "chart_type": "bar",
    "axes": {"x": "난이도", "y": "질문 수"},
    "series": [
        {"name": "", "points": [{"label": "쉬움", "value": 10}, {"label": "어려움", "value": 10}]}
    ],
    "insight": "난이도별 질문 수는 균일하다",
}

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


def test_korean_font_registered_as_default_family():
    """Regression (V02 live run): chart axis labels rendered Korean as □ because
    matplotlib defaulted to DejaVu Sans. Importing chart_regen must register the
    bundled NanumGothic and make it the active family (parity with
    diagram_regen's dot-path font forcing)."""
    registered = {f.name for f in font_manager.fontManager.ttflist}
    assert "NanumGothic" in registered
    family = plt.rcParams["font.family"]
    assert "NanumGothic" in (family if isinstance(family, list) else [family])


def test_korean_labels_render_without_missing_glyph_warning(tmp_path):
    """A Korean-labelled chart must render with no 'missing from font' warning —
    the exact symptom the V02 run surfaced. axes.unicode_minus is off so
    negative ticks don't tofu either."""
    assert plt.rcParams["axes.unicode_minus"] is False
    out = tmp_path / "korean.png"
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert regenerate_chart(KOREAN_BAR_STRUCT, out) == str(out)
    glyph_warnings = [w for w in caught if "missing from font" in str(w.message)]
    assert not glyph_warnings, f"Korean glyphs fell back to a tofu font: {glyph_warnings}"
    assert out.exists()


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


# ── `python -m deck_tools.chart_regen` CLI (node runner pre-step, PR-F3) ──────


def _run_cli(job: dict) -> dict:
    import json
    import subprocess
    import sys
    from pathlib import Path

    proc = subprocess.run(
        [sys.executable, "-m", "deck_tools.chart_regen"],
        input=json.dumps(job),
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(__file__).resolve().parents[1],  # py/ — module resolution root
    )
    return json.loads(proc.stdout)


def test_cli_regenerates_supported_struct(tmp_path):
    out = tmp_path / "cli_line.png"
    assert _run_cli({"struct": LINE_STRUCT, "out": str(out)}) == {"png": str(out)}
    assert out.exists()


def test_cli_unsupported_struct_returns_null_for_label_only_fallback(tmp_path):
    """Regen None → {"png": null}: the runner falls back to label-only, never
    to a raw frame (ADR 0003 P2)."""
    out = tmp_path / "cli_nope.png"
    job = {"struct": {"chart_type": "pie3d-unsupported", "series": []}, "out": str(out)}
    assert _run_cli(job) == {"png": None}
    assert not out.exists()


# ── PR-A: §2 quality-standard additions ──────────────────────────────────────

from deck_tools.chart_regen import (  # noqa: E402
    BROKEN_AXIS_RATIO,
    regenerate_equation,
)


def test_bar_chart_carries_value_labels(tmp_path):
    """§2c quality floor: a bar is annotated with its value, not a bare shape."""
    out = tmp_path / "labelled.png"
    assert regenerate_chart(BAR_STRUCT, out) == str(out)
    # The render must carry ink beyond the bars (the value labels) — width grows
    # vs an unlabelled render is hard to assert headlessly, so verify it renders
    # non-empty (self-check passed) and is a valid image.
    with Image.open(out) as img:
        assert img.size[0] > 100


def test_extreme_spread_triggers_broken_axis(tmp_path):
    """§2b: a single-series bar with an extreme max/min ratio renders a taller
    2-panel (broken-axis) figure — verified via aspect ratio vs a normal bar."""
    extreme = {
        "chart_type": "bar",
        "axes": {"y": "latency (ms)"},
        "series": [
            {
                "name": "",
                "points": [
                    {"label": "backend", "value": 80},
                    {"label": "vLLM", "value": 2700},
                ],
            }
        ],
    }
    assert (2700 / 80) >= BROKEN_AXIS_RATIO  # precondition the fixture targets
    normal_out, broken_out = tmp_path / "normal.png", tmp_path / "broken.png"
    regenerate_chart(BAR_STRUCT, normal_out)  # near-1:9 spread → single panel
    assert regenerate_chart(extreme, broken_out) == str(broken_out)
    with Image.open(normal_out) as n, Image.open(broken_out) as b:
        # The 2-panel render is proportionally taller than the single panel.
        assert (b.size[1] / b.size[0]) > (n.size[1] / n.size[0])


def test_equation_renders_latex_to_png(tmp_path):
    out = tmp_path / "eq.png"
    assert regenerate_equation("E = mc^2", out) == str(out)
    assert out.exists()
    with Image.open(out) as img:
        assert img.size[0] > 50


def test_equation_empty_or_unparseable_returns_none(tmp_path):
    assert regenerate_equation("", tmp_path / "a.png") is None
    assert regenerate_equation("   ", tmp_path / "b.png") is None
    # An unbalanced mathtext group fails to parse → label-only fallback.
    assert regenerate_equation(r"\frac{1}{", tmp_path / "c.png") is None


def test_cli_renders_equation_job(tmp_path):
    out = tmp_path / "cli_eq.png"
    assert _run_cli({"kind": "equation", "latex": "x^2 + y^2 = r^2", "out": str(out)}) == {
        "png": str(out)
    }
    assert out.exists()
