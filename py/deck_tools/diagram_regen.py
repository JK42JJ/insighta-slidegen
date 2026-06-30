"""diagram_regen — mode-B diagram/table struct → Graphviz-laid-out PNG.

First-party renderer (NOT vendored) following the academic-report-builder
figlib INVARIANTS (roadmap 2 design): box-and-arrow diagrams use Graphviz
auto-layout, never matplotlib coordinate placement (which overlaps by hand).
chart_regen (matplotlib) covers DATA charts; this covers STRUCTURE (flow /
tree / layered / matrix / table) — the V02-family figures chart_regen could
not render (16 numerized, only 3 were data-charts).

Input struct (mode B, produced by figure_extract):

    diagram: {"diagram_type": "flow"|"tree"|"layered"|"matrix"|"swimlane",
              "nodes": [{"id","label","group"?}], "edges": [{"from","to","style"?}],
              "insight": ""}
    table:   {"headers": [...], "rows": [[...], ...]}

A struct that is unknown/unusable, or any render failure, returns None — the
caller falls back to label-only, NEVER to a raw frame (ADR 0003 P2).

Korean labels: Graphviz routes fonts through fontconfig, so the bundled
NanumGothic TTF must be installed (install_korean_font) BEFORE rendering —
matplotlib's addfont is not enough for dot (invariant 8).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

# ── Insighta brand palette (deck/scripts/figures.py parity) ──────────────────
FONT = "NanumGothic"
INK = "#0F172A"
# Dark-theme SVG overrides (FE note card path only; PNG deck path always light).
_D_INK = "#E2E8F0"   # primary text on dark
_D_EDGE = "#64748B"  # edges / lines
_D_FILL = "#1E293B"  # node body fill
PALETTE = {
    "blue": ("#2563EB", "#EFF4FF"),
    "emerald": ("#059669", "#ECFDF5"),
    "violet": ("#7C3AED", "#F5F0FF"),
    "amber": ("#D97706", "#FFF7ED"),
    "slate": ("#475569", "#F1F5F9"),
    "rose": ("#E11D48", "#FFF1F4"),
}
_CYCLE = ["blue", "emerald", "violet", "amber", "slate", "rose"]

FIGURE_DPI = 300
SUPPORTED_DIAGRAM_TYPES = ("flow", "tree", "layered", "matrix", "swimlane")
# Same ink self-check floor as chart_regen (blank render → label-only).
MIN_INK_FRACTION = 0.002
# Density gate: diagrams with fewer real nodes than this carry almost no
# structural information and render crudely ("정확하거나 없거나").
MIN_DIAGRAM_NODES = 3
# Adaptive-theme sentinel: FE string-replaces this with currentColor so SVG
# text/lines inherit the page's text color on both dark and light backgrounds.
# #808080 is also a tolerable mid-grey fallback when a swap ever misses.
_AUTO_INK = "#808080"

_FONT_INSTALLED = False


def install_korean_font(regular_ttf: str | os.PathLike | None = None) -> bool:
    """Install NanumGothic into ~/.fonts + refresh fontconfig (invariant 8).

    Graphviz HTML/text labels render Korean as □ without this. Idempotent;
    returns True if a font is in place. Best-effort — a failure degrades to
    Latin-only labels rather than crashing the render."""
    global _FONT_INSTALLED
    if _FONT_INSTALLED:
        return True
    ttf = Path(regular_ttf) if regular_ttf else Path(__file__).parent / "assets" / "NanumGothic.ttf"
    if not ttf.exists():
        return False
    try:
        dest = Path.home() / ".fonts"
        dest.mkdir(parents=True, exist_ok=True)
        target = dest / ttf.name
        if not target.exists():
            shutil.copy(ttf, target)
        if shutil.which("fc-cache"):
            subprocess.run(["fc-cache", "-f", str(dest)], capture_output=True, timeout=30)
        _FONT_INSTALLED = True
        return True
    except Exception:  # noqa: BLE001 — font install must never block rendering
        return False


def _color(index: int) -> tuple[str, str]:
    return PALETTE[_CYCLE[index % len(_CYCLE)]]


def _have_dot() -> bool:
    return shutil.which("dot") is not None


def regenerate_diagram(
    struct: dict, out_path: str | os.PathLike, font_scale: float = 1.0
) -> str | None:
    """Render a diagram/table struct to a PNG. None when unrenderable
    (caller falls back to label-only — never a raw frame, ADR 0003 P2).

    A3: font_scale multiplies all font sizes so the node deck runner can keep
    the on-slide font legible at the figure's final placed size."""
    if not isinstance(struct, dict) or not _have_dot():
        return None
    install_korean_font()
    try:
        import graphviz
    except ImportError:
        return None

    # table struct → mapping-style grid; diagram struct → typed layout.
    if "headers" in struct and "rows" in struct:
        g = _render_table(graphviz, struct)
    else:
        dtype = struct.get("diagram_type")
        if dtype not in SUPPORTED_DIAGRAM_TYPES:
            return None
        nodes = struct.get("nodes") or []
        if not _nodes_edges_consistent(nodes, struct.get("edges") or []):
            return None
        g = _render_diagram(graphviz, dtype, nodes, struct.get("edges") or [], font_scale)
    if g is None:
        return None

    base = str(out_path)[:-4] if str(out_path).endswith(".png") else str(out_path)
    try:
        g.render(base, format="png", cleanup=True)
    except Exception:  # noqa: BLE001 — dot render boundary
        return None
    png = base + ".png"
    if not _has_enough_ink(png):
        try:
            os.remove(png)
        except OSError:
            pass
        return None
    return png


def _nodes_edges_consistent(nodes: list, edges: list) -> bool:
    """Gate (roadmap 2 §5): every edge endpoint must be a declared node, and
    there must be at least one node. Catches numerize hallucinations that
    reference phantom nodes."""
    if not nodes:
        return False
    ids = {str(n.get("id")) for n in nodes if isinstance(n, dict) and n.get("id") is not None}
    if not ids:
        return False
    for e in edges:
        if not isinstance(e, dict):
            return False
        if str(e.get("from")) not in ids or str(e.get("to")) not in ids:
            return False
    return True


def _base(graphviz, name: str, rankdir: str = "TB", font_scale: float = 1.0, theme: str = "light"):
    g = graphviz.Digraph(name, format="png")
    if theme == "dark":
        bg = "transparent"
        edge_c = _D_EDGE
        default_node_stroke = INK
    elif theme == "auto":
        # Transparent bg; sentinel ink so FE can swap to currentColor.
        bg = "transparent"
        edge_c = _AUTO_INK
        default_node_stroke = _AUTO_INK
    else:
        bg = "white"
        edge_c = "#334155"
        default_node_stroke = INK
    g.attr(rankdir=rankdir, bgcolor=bg, fontname=FONT, pad="0.3",
           nodesep="0.4", ranksep="0.5", dpi=str(FIGURE_DPI))
    g.attr("node", shape="box", style="rounded,filled", fontname=FONT,
           fontsize=str(round(11 * font_scale, 1)), margin="0.18,0.12",
           penwidth="1.6", color=default_node_stroke)
    g.attr("edge", fontname=FONT, fontsize=str(round(9 * font_scale, 1)),
           color=edge_c, penwidth="1.6")
    return g


def _render_diagram(graphviz, dtype: str, nodes: list, edges: list, font_scale: float = 1.0, theme: str = "light"):
    # flow / swimlane lay left→right; tree / layered top→bottom; matrix grid.
    # A2: the insight/title is NOT drawn on the graph — the slide template
    # renders it as editable text (figureSlide title + caption). Only the
    # diagram itself belongs in the raster.
    rankdir = "LR" if dtype in ("flow", "swimlane") else "TB"
    g = _base(graphviz, dtype, rankdir=rankdir, font_scale=font_scale, theme=theme)
    # Resolve per-theme ink color for node text.
    if theme == "dark":
        node_fc = _D_INK
    elif theme == "auto":
        node_fc = _AUTO_INK  # sentinel; FE swaps to currentColor
    else:
        node_fc = INK
    # group → cluster (layered/swimlane); ungrouped → flat.
    groups: dict[str, list] = {}
    for i, n in enumerate(nodes):
        gid = str(n.get("group", ""))
        groups.setdefault(gid, []).append((i, n))
    for ci, (gid, members) in enumerate(groups.items()):
        ec, fc = _color(ci)
        # Auto: transparent fill so the page background shows through; accent
        # border (ec) is kept — accent colors are visible on both themes.
        if theme == "dark":
            node_fill = _D_FILL
        elif theme == "auto":
            node_fill = "transparent"
        else:
            node_fill = fc
        if gid:
            # Cluster border keeps accent; cluster label text uses theme ink.
            if theme == "dark":
                cluster_fc = _D_INK
            elif theme == "auto":
                cluster_fc = _AUTO_INK
            else:
                cluster_fc = ec
            with g.subgraph(name=f"cluster_{ci}") as c:
                c.attr(label=gid, style="rounded,dashed", color=ec, fontcolor=cluster_fc,
                       fontname=FONT, fontsize=str(round(12 * font_scale, 1)),
                       margin="12", labelloc="b")
                for i, n in members:
                    c.node(str(n["id"]), str(n.get("label", n["id"])),
                           color=ec, fillcolor=node_fill, fontcolor=node_fc)
        else:
            for i, n in members:
                ec2, fc2 = _color(i)
                if theme == "dark":
                    fill2 = _D_FILL
                elif theme == "auto":
                    fill2 = "transparent"
                else:
                    fill2 = fc2
                g.node(str(n["id"]), str(n.get("label", n["id"])),
                       color=ec2, fillcolor=fill2, fontcolor=node_fc)
    for e in edges:
        kw = {}
        if e.get("style"):
            kw["style"] = str(e["style"])
        g.edge(str(e["from"]), str(e["to"]), **kw)
    return g


def _render_table(graphviz, struct: dict, theme: str = "light"):
    headers = [str(h) for h in (struct.get("headers") or [])]
    rows = struct.get("rows") or []
    if not headers or not rows:
        return None
    g = graphviz.Digraph("table", format="png")
    if theme == "dark":
        g.attr(bgcolor="transparent", dpi=str(FIGURE_DPI), fontname=FONT, fontcolor=_D_INK)
    elif theme == "auto":
        # Transparent bg; sentinel ink for body cell text; FE swaps to currentColor.
        # Header cells keep accent BGCOLOR + white FONT — visible on both themes.
        g.attr(bgcolor="transparent", dpi=str(FIGURE_DPI), fontname=FONT, fontcolor=_AUTO_INK)
    else:
        g.attr(bgcolor="white", dpi=str(FIGURE_DPI), fontname=FONT)
    ec, _ = PALETTE["slate"]
    # Header row: accent bg with white text — readable on both themes.
    th = "".join(
        f'<TD BGCOLOR="{ec}"><FONT COLOR="white"><B>{_esc(h)}</B></FONT></TD>' for h in headers
    )
    trs = [f"<TR>{th}</TR>"]
    for r in rows:
        cells = [str(c) for c in (r if isinstance(r, list) else [r])][: len(headers)]
        cells += [""] * (len(headers) - len(cells))
        trs.append("<TR>" + "".join(f"<TD>{_esc(c)}</TD>" for c in cells) + "</TR>")
    rows_html = "".join(trs)
    label = (
        '<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="6">'
        f"{rows_html}</TABLE>>"
    )
    g.node("t", label, shape="plaintext", fontname=FONT)
    return g


def _esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _has_enough_ink(out_path: str | os.PathLike) -> bool:
    """Blank-render guard (chart_regen parity)."""
    try:
        from PIL import Image

        with Image.open(out_path) as img:
            gray = img.convert("L")
            hist = gray.histogram()
            total = sum(hist)
            if total == 0:
                return False
            non_white = sum(hist[:248])  # darker-than-near-white pixels
            return non_white / total >= MIN_INK_FRACTION
    except Exception:  # noqa: BLE001 — check failure must not block rendering
        return True


def regenerate_diagram_svg(struct: dict, font_scale: float = 1.0, theme: str = "light") -> str | None:
    """Render a diagram/table struct to an inline SVG string.

    Same fail-closed gates as regenerate_diagram (unusable struct / dot absent →
    None). Calls g.pipe(format="svg") — no file written.

    Args:
        theme: 'light' (default, dark ink on white — deck/PNG path), 'dark'
               (light ink on transparent — FE note card), or 'auto' (adaptive:
               transparent bg + #808080 sentinel ink; FE swaps to currentColor
               so one SVG works on both dark and light page backgrounds).
    """
    if not isinstance(struct, dict) or not _have_dot():
        return None
    install_korean_font()
    try:
        import graphviz
    except ImportError:
        return None

    if "headers" in struct and "rows" in struct:
        g = _render_table(graphviz, struct, theme=theme)
    else:
        dtype = struct.get("diagram_type")
        if dtype not in SUPPORTED_DIAGRAM_TYPES:
            return None
        nodes = struct.get("nodes") or []
        if not _nodes_edges_consistent(nodes, struct.get("edges") or []):
            return None
        # Density gate: trivially sparse diagrams carry almost no structural
        # information ("정확하거나 없거나"). Count real nodes (phantom-filtered).
        real_node_count = sum(
            1 for n in nodes if isinstance(n, dict) and n.get("id") is not None
        )
        if real_node_count < MIN_DIAGRAM_NODES:
            return None
        g = _render_diagram(graphviz, dtype, nodes, struct.get("edges") or [], font_scale, theme=theme)
    if g is None:
        return None

    try:
        svg = g.pipe(format="svg").decode("utf-8")
    except Exception:  # noqa: BLE001 — dot render boundary
        return None
    return svg if "<svg" in svg else None


def main() -> int:
    """CLI for the node deck runner. stdin job:
        {"struct": <diagram|table struct>, "out": "<png>", "font_scale": <float>}
    → {"png": "<path>"} or {"png": null} (label-only fallback). font_scale
    defaults to 1.0 (A3 — the runner sizes it to the figure's placement)."""
    import json
    import sys

    job = json.load(sys.stdin)
    png = regenerate_diagram(
        job.get("struct"), job["out"], float(job.get("font_scale", 1.0))
    )
    json.dump({"png": png}, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
