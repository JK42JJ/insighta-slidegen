"""svg_output — dispatcher for inline SVG rendering (diagram / chart).

Table and equation figures are handled note-side as HTML / KaTeX; both return
None here so callers can treat all four kinds uniformly.
"""
from __future__ import annotations


def render_figure_svg(kind: str, struct: dict) -> str | None:
    """Render a mode-B figure struct to an inline SVG string.

    Args:
        kind: 'diagram' | 'chart' | 'table' | 'equation'.
              'table' and 'equation' return None (rendered note-side).
        struct: mode-B figure struct produced by figure_extract.

    Returns:
        Self-contained SVG string, or None when kind is unsupported or the
        struct is degenerate / unrenderable (fail-closed, ADR 0003 P2).
    """
    if kind == "diagram":
        from deck_tools.diagram_regen import regenerate_diagram_svg

        return regenerate_diagram_svg(struct)
    if kind == "chart":
        from deck_tools.chart_regen import regenerate_chart_svg

        return regenerate_chart_svg(struct)
    # 'table' and 'equation' are rendered note-side (HTML / KaTeX).
    return None
