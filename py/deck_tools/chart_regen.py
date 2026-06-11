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
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402  (backend must be set before pyplot)

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
    return str(out_path)


def _color(index: int) -> str:
    return SERIES_COLORS[index % len(SERIES_COLORS)]


def _draw_bar(ax, series: list[tuple[str, list, list]]) -> None:
    """Grouped bars; category labels come from each series' x values."""
    labels = [str(x) for x in series[0][1]]
    positions = range(len(labels))
    bar_width = BAR_GROUP_WIDTH / len(series)
    for i, (name, _xs, ys) in enumerate(series):
        offsets = [p + (i - (len(series) - 1) / 2) * bar_width for p in positions]
        ax.bar(offsets, ys[: len(labels)], width=bar_width, color=_color(i), zorder=3, label=name)
    ax.set_xticks(list(positions))
    ax.set_xticklabels(labels)


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

    Reads ONE JSON job from stdin: {"struct": <mode-B struct>, "out": "<png path>"}.
    Writes {"png": "<written path>"} on success, or {"png": null} when the
    struct is not regenerable — the caller then falls back to label-only,
    NEVER to a raw frame (ADR 0003 P2).
    """
    import json
    import sys

    job = json.load(sys.stdin)
    png = regenerate_chart(job.get("struct"), job["out"])
    json.dump({"png": png}, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
