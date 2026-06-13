"""chart_regen — mode-B struct-JSON → brand-styled matplotlib PNG (≥ 300 dpi).

First-party module (NOT vendored) following the `deck/scripts/figures.py`
brand pattern: Insighta palette constants, transparent background, `_ax()`
spine/tick cleanup, high-dpi savefig.

Pipeline role (ADR 0003 P2/D1): the regenerated PNG produced here is the ONLY
deck-embeddable bitmap kind in the pipeline. A raw frame crop is a data
source, never the artifact — when a struct is unknown or unusable this module
returns None and the caller falls back to a label-only slide, NEVER to a raw
frame image.

Input struct (mode B of CONTRACT_model-endpoints §2.2, produced by
mac-mini/slidegen-service/figure_extract.py):

    {
      "chart_type": "line" | "bar" | "scatter",
      "axes": {"x": "", "y": ""},
      "series": [{"name": "", "points": [{"x": 0, "y": 0}]}],
      "insight": "one sentence"
    }

Bar-chart points may also use the reference {"label": "", "value": 0} form
(extract_resources.js CHART_TO_DATA shape).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402  (backend must be set before pyplot)
from matplotlib import font_manager  # noqa: E402

# ── Korean glyph support (invariant 8 parity with diagram_regen) ─────────────
# matplotlib's default DejaVu Sans renders Hangul as □ (the V02 live run showed
# tofu in chart axis labels). diagram_regen forces NanumGothic for the Graphviz
# (dot) path; the matplotlib path needs the same guarantee. matplotlib keeps its
# OWN font cache (not fontconfig), so registering the bundled TTF with the
# font_manager and setting it as the default family is enough — no fc-cache step
# (unlike diagram_regen, whose dot binary reads fontconfig). Best-effort: a
# missing asset degrades to the matplotlib default rather than crashing.
_KOREAN_FONT_FAMILY = "NanumGothic"


def _install_matplotlib_korean_font() -> bool:
    """Register the bundled NanumGothic with matplotlib and make it the default
    family so Korean axis labels/titles render. Idempotent; returns True when a
    Korean-capable family is active."""
    assets = Path(__file__).parent / "assets"
    regular = assets / "NanumGothic.ttf"
    if not regular.exists():
        return False
    try:
        for ttf in (regular, assets / "NanumGothic-Bold.ttf"):
            if ttf.exists():
                font_manager.fontManager.addfont(str(ttf))
        plt.rcParams["font.family"] = _KOREAN_FONT_FAMILY
        # ASCII hyphen for minus so negative ticks don't render as □ (the
        # Unicode minus glyph is absent from NanumGothic).
        plt.rcParams["axes.unicode_minus"] = False
        return True
    except Exception:  # noqa: BLE001 — font setup must never block rendering
        return False


_install_matplotlib_korean_font()

# ── Insighta palette (deck/scripts/figures.py — brand constants) ─────────────
INK = "#0F172A"
MUT = "#475569"
FAINT = "#94A3B8"
LINE = "#CBD5E1"
PRIMARY = "#2563EB"
CAT = {  # (main, tint, deep)
    "blue": ("#2563EB", "#EFF4FF", "#1D4ED8"),
    "emerald": ("#059669", "#ECFDF5", "#047857"),
    "violet": ("#7C3AED", "#F5F0FF", "#6D28D9"),
    "amber": ("#D97706", "#FFF7ED", "#B45309"),
    "rose": ("#E11D48", "#FFF1F4", "#BE123C"),
    "slate": ("#475569", "#F1F5F9", "#334155"),
}
# Series colors cycle through the categorical mains, brand order.
SERIES_COLORS = [CAT[k][0] for k in ("blue", "emerald", "violet", "amber", "rose", "slate")]

# Vector-300dpi quality gate (ADR 0003 D1): rasterized deck embeds are ≥ 300 dpi.
FIGURE_DPI = 300
DEFAULT_FIGSIZE = (5.6, 3.6)  # matches the figures.py teaching-chart default

SUPPORTED_CHART_TYPES = ("line", "bar", "scatter")

# Grouped-bar layout: total fraction of each category slot occupied by bars.
BAR_GROUP_WIDTH = 0.72

# §2b (academic-report-builder dense-recipe 5): a single-series bar chart whose
# largest value dwarfs the smallest by this factor gets a broken-axis 2-panel
# treatment so the small bars stay visible. Tuning knob, not a secret.
BROKEN_AXIS_RATIO = 12.0
# §2e / invariant 11 self-check: a regenerated PNG carrying almost no ink is a
# rendering failure (blank/near-blank) — reject it so the caller falls back to
# label-only rather than embedding an empty figure. Fraction of non-background
# pixels below which the render is considered empty.
MIN_INK_FRACTION = 0.002


def _ax(figsize: tuple[float, float] = DEFAULT_FIGSIZE):
    """Transparent-background axes with brand spines/ticks (figures.py `_ax`)."""
    fig, ax = plt.subplots(figsize=figsize, dpi=FIGURE_DPI)
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color(LINE)
    ax.spines["bottom"].set_color(LINE)
    ax.tick_params(colors=MUT, labelsize=9)
    return fig, ax


def regenerate_chart(struct: dict, out_path: str | os.PathLike) -> str | None:
    """Regenerate a chart PNG from a mode-B struct.

    Returns the written PNG path, or None when the struct is not a supported
    chart shape (the caller falls back to label-only — never to a raw frame).
    """
    if not isinstance(struct, dict):
        return None
    chart_type = struct.get("chart_type")
    if chart_type not in SUPPORTED_CHART_TYPES:
        return None
    series = _normalize_series(struct.get("series"))
    if not series:
        return None

    # §2b: extreme single-series bar spread → broken-axis 2-panel render.
    if chart_type == "bar" and _needs_broken_axis(series):
        return _regenerate_bar_broken(struct, series, out_path)

    fig, ax = _ax()
    try:
        if chart_type == "bar":
            _draw_bar(ax, series)
        elif chart_type == "scatter":
            for i, (name, xs, ys) in enumerate(series):
                ax.scatter(xs, ys, s=26, color=_color(i), alpha=0.8, zorder=3, label=name)
        else:  # line
            for i, (name, xs, ys) in enumerate(series):
                ax.plot(xs, ys, color=_color(i), lw=2.4, zorder=3, label=name)

        axes = struct.get("axes") or {}
        if axes.get("x"):
            ax.set_xlabel(str(axes["x"]), fontsize=10, color=INK)
        if axes.get("y"):
            ax.set_ylabel(str(axes["y"]), fontsize=10, color=INK)
        if struct.get("insight"):
            ax.set_title(str(struct["insight"]), fontsize=10.5, color=INK, pad=8)
        if any(name for name, _xs, _ys in series):
            ax.legend(frameon=False, fontsize=9)

        plt.tight_layout(pad=0.4)
        fig.savefig(out_path, transparent=True, bbox_inches="tight", dpi=FIGURE_DPI)
    finally:
        plt.close(fig)

    # §2e / invariant 11 — quality floor: a near-empty render is a failure.
    # Reject it so the caller degrades to label-only (never an empty figure).
    if not _has_enough_ink(out_path):
        try:
            os.remove(out_path)
        except OSError:
            pass
        return None
    return str(out_path)


def _color(index: int) -> str:
    return SERIES_COLORS[index % len(SERIES_COLORS)]


def _value_label(value: float) -> str:
    """§2c quality floor: bars carry their numeric value, not a bare shape."""
    if value == int(value):
        return str(int(value))
    return f"{value:.4g}"


def _draw_bar(ax, series: list[tuple[str, list, list]]) -> None:
    """Grouped bars; category labels come from each series' x values.

    §2c: every bar is annotated with its value (a labelled-only bar is
    'unfinished' per invariant 11). Single-series charts with an extreme
    value spread get a broken-axis panel via _draw_bar_broken instead.
    """
    labels = [str(x) for x in series[0][1]]
    positions = range(len(labels))
    bar_width = BAR_GROUP_WIDTH / len(series)
    for i, (name, _xs, ys) in enumerate(series):
        offsets = [p + (i - (len(series) - 1) / 2) * bar_width for p in positions]
        heights = ys[: len(labels)]
        bars = ax.bar(offsets, heights, width=bar_width, color=_color(i), zorder=3, label=name)
        ax.bar_label(
            bars, labels=[_value_label(v) for v in heights], padding=2, fontsize=8, color=MUT
        )
    ax.set_xticks(list(positions))
    ax.set_xticklabels(labels)


def _needs_broken_axis(series: list[tuple[str, list, list]]) -> bool:
    """Single-series bar with an extreme max/min spread (§2b trigger)."""
    if len(series) != 1:
        return False
    ys = [v for v in series[0][2] if v > 0]
    if len(ys) < 2:
        return False
    return max(ys) / min(ys) >= BROKEN_AXIS_RATIO


def _regenerate_bar_broken(
    struct: dict, series: list[tuple[str, list, list]], out_path: str | os.PathLike
) -> str | None:
    """Broken-axis 2-panel bar (§2b / dense-recipe 5): top = full range, bottom
    = zoomed to the small values, so an extreme spread keeps every bar visible.
    Bars are matplotlib `Rectangle`s via ax.bar (NO FancyBboxPatch rounding —
    rounding is read in data coords and crushes narrow bars; v3 failure mode)."""
    name, xs, ys = series[0]
    labels = [str(x) for x in xs]
    heights = ys[: len(labels)]
    positions = list(range(len(labels)))
    small_max = sorted(v for v in heights if v > 0)[len(heights) // 2] * 2  # ~median band

    fig, (ax_top, ax_bot) = plt.subplots(
        2, 1, figsize=(DEFAULT_FIGSIZE[0], DEFAULT_FIGSIZE[1] * 1.25), dpi=FIGURE_DPI, sharex=True
    )
    for axp in (ax_top, ax_bot):
        axp.patch.set_alpha(0)
        for spine in ("top", "right"):
            axp.spines[spine].set_visible(False)
        axp.spines["left"].set_color(LINE)
        axp.spines["bottom"].set_color(LINE)
        axp.tick_params(colors=MUT, labelsize=9)
    fig.patch.set_alpha(0)
    try:
        for axp in (ax_top, ax_bot):
            bars = axp.bar(positions, heights, width=BAR_GROUP_WIDTH, color=_color(0), zorder=3)
            axp.bar_label(
                bars, labels=[_value_label(v) for v in heights], padding=2, fontsize=8, color=MUT
            )
        ax_top.set_ylim(0, max(heights) * 1.12)  # full range
        ax_bot.set_ylim(0, small_max)  # zoomed band
        ax_top.spines["bottom"].set_visible(False)
        ax_top.tick_params(bottom=False)
        ax_bot.set_xticks(positions)
        ax_bot.set_xticklabels(labels)
        axes = struct.get("axes") or {}
        if axes.get("y"):
            ax_bot.set_ylabel(str(axes["y"]), fontsize=10, color=INK)
        if axes.get("x"):
            ax_bot.set_xlabel(str(axes["x"]), fontsize=10, color=INK)
        if struct.get("insight"):
            ax_top.set_title(str(struct["insight"]), fontsize=10.5, color=INK, pad=8)
        plt.tight_layout(pad=0.4)
        fig.savefig(out_path, transparent=True, bbox_inches="tight", dpi=FIGURE_DPI)
    finally:
        plt.close(fig)
    if not _has_enough_ink(out_path):
        try:
            os.remove(out_path)
        except OSError:
            pass
        return None
    return str(out_path)


def regenerate_equation(latex: str, out_path: str | os.PathLike) -> str | None:
    """§2d: render an OCR'd LaTeX string to a brand PNG via matplotlib mathtext.

    Pure-text rendering (no pdflatex dependency) — covers the common
    inline/display math the equation OCR emits. Returns None when the string
    is empty or mathtext cannot parse it (caller falls back to label-only;
    low-confidence equations are flagged upstream, never silently embedded —
    ADR 0003 D3)."""
    if not isinstance(latex, str) or not latex.strip():
        return None
    body = latex.strip().strip("$")
    fig = plt.figure(figsize=(6.0, 1.6), dpi=FIGURE_DPI)
    fig.patch.set_alpha(0)
    try:
        fig.text(0.5, 0.5, f"${body}$", fontsize=24, color=INK, ha="center", va="center")
        fig.savefig(out_path, transparent=True, bbox_inches="tight", dpi=FIGURE_DPI)
    except (ValueError, RuntimeError):
        # mathtext parse failure → label-only fallback.
        plt.close(fig)
        return None
    finally:
        plt.close(fig)
    if not _has_enough_ink(out_path):
        try:
            os.remove(out_path)
        except OSError:
            pass
        return None
    return str(out_path)


def _has_enough_ink(out_path: str | os.PathLike) -> bool:
    """§2e self-check: True if the PNG has more than MIN_INK_FRACTION
    non-transparent pixels. Guards against blank/near-blank renders."""
    try:
        from PIL import Image

        with Image.open(out_path) as img:
            alpha = img.convert("RGBA").getchannel("A")
            hist = alpha.histogram()
            total = sum(hist)
            if total == 0:
                return False
            opaque = sum(hist[16:])  # alpha > ~6% counts as ink
            return opaque / total >= MIN_INK_FRACTION
    except Exception:  # noqa: BLE001 — a check failure must not block rendering
        return True


def _normalize_series(raw: Any) -> list[tuple[str, list, list]]:
    """Coerce mode-B series into (name, xs, ys[float]) triples.

    Accepts points as {"x", "y"} or the reference {"label", "value"} form.
    Returns [] when nothing numeric remains (→ caller gets None).
    """
    if not isinstance(raw, list):
        return []
    out: list[tuple[str, list, list]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        xs: list = []
        ys: list[float] = []
        for point in entry.get("points") or []:
            if not isinstance(point, dict):
                continue
            x = point.get("x", point.get("label"))
            y = point.get("y", point.get("value"))
            try:
                ys.append(float(y))
            except (TypeError, ValueError):
                continue
            xs.append(x)
        if ys:
            out.append((str(entry.get("name") or ""), xs, ys))
    return out


def main() -> int:
    """CLI entry for the node deck runner pre-step (PR-F3).

    Reads ONE JSON job from stdin. Two job kinds:
      chart:    {"struct": <mode-B struct>, "out": "<png>"}
      equation: {"kind": "equation", "latex": "<latex>", "out": "<png>"}
    Writes {"png": "<written path>"} on success, or {"png": null} when not
    regenerable — the caller then falls back to label-only, NEVER to a raw
    frame (ADR 0003 P2).
    """
    import json
    import sys

    job = json.load(sys.stdin)
    if job.get("kind") == "equation":
        png = regenerate_equation(job.get("latex") or "", job["out"])
    else:
        png = regenerate_chart(job.get("struct"), job["out"])
    json.dump({"png": png}, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
