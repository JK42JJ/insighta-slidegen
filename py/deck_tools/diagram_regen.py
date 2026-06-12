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
from typing import Any

# ── Insighta brand palette (deck/scripts/figures.py parity) ──────────────────
FONT = "NanumGothic"
INK = "#0F172A"
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


def regenerate_diagram(struct: dict, out_path: str | os.PathLike) -> str | None:
    """Render a diagram/table struct to a PNG. None when unrenderable
    (caller falls back to label-only — never a raw frame, ADR 0003 P2)."""
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
        g = _render_diagram(
            graphviz, dtype, nodes, struct.get("edges") or [], struct.get("insight")
        )
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


def _base(graphviz, name: str, rankdir: str = "TB"):
    g = graphviz.Digraph(name, format="png")
    g.attr(rankdir=rankdir, bgcolor="white", fontname=FONT, pad="0.3",
           nodesep="0.4", ranksep="0.5", dpi=str(FIGURE_DPI))
    g.attr("node", shape="box", style="rounded,filled", fontname=FONT,
           fontsize="11", margin="0.18,0.12", penwidth="1.6", color=INK)
    g.attr("edge", fontname=FONT, fontsize="9", color="#334155", penwidth="1.6")
    return g


def _render_diagram(graphviz, dtype: str, nodes: list, edges: list, insight: Any):
    # flow / swimlane lay left→right; tree / layered top→bottom; matrix grid.
    rankdir = "LR" if dtype in ("flow", "swimlane") else "TB"
    g = _base(graphviz, dtype, rankdir=rankdir)
    if insight:
        g.attr(label=str(insight) + "\n", labelloc="t", fontsize="13", fontname=FONT)
    # group → cluster (layered/swimlane); ungrouped → flat.
    groups: dict[str, list] = {}
    for i, n in enumerate(nodes):
        gid = str(n.get("group", ""))
        groups.setdefault(gid, []).append((i, n))
    for ci, (gid, members) in enumerate(groups.items()):
        ec, fc = _color(ci)
        if gid:
            with g.subgraph(name=f"cluster_{ci}") as c:
                c.attr(label=gid, style="rounded,dashed", color=ec, fontcolor=ec,
                       fontname=FONT, fontsize="12", margin="12", labelloc="b")
                for i, n in members:
                    c.node(str(n["id"]), str(n.get("label", n["id"])),
                           color=ec, fillcolor=fc, fontcolor=INK)
        else:
            for i, n in members:
                ec2, fc2 = _color(i)
                g.node(str(n["id"]), str(n.get("label", n["id"])),
                       color=ec2, fillcolor=fc2, fontcolor=INK)
    for e in edges:
        kw = {}
        if e.get("style"):
            kw["style"] = str(e["style"])
        g.edge(str(e["from"]), str(e["to"]), **kw)
    return g


def _render_table(graphviz, struct: dict):
    headers = [str(h) for h in (struct.get("headers") or [])]
    rows = struct.get("rows") or []
    if not headers or not rows:
        return None
    g = graphviz.Digraph("table", format="png")
    g.attr(bgcolor="white", dpi=str(FIGURE_DPI), fontname=FONT)
    ec, _ = PALETTE["slate"]
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


def main() -> int:
    """CLI for the node deck runner. stdin job:
        {"struct": <diagram|table struct>, "out": "<png>"}
    → {"png": "<path>"} or {"png": null} (label-only fallback)."""
    import json
    import sys

    job = json.load(sys.stdin)
    png = regenerate_diagram(job.get("struct"), job["out"])
    json.dump({"png": png}, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
