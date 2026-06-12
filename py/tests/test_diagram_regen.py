"""Tests for deck_tools/diagram_regen.py — diagram/table struct → Graphviz PNG.

Requires the `dot` binary + python `graphviz` (CI installs graphviz). When dot
is absent the renderer returns None (label-only) — that path is asserted too.
"""

import shutil

import pytest

from deck_tools import diagram_regen
from deck_tools.diagram_regen import SUPPORTED_DIAGRAM_TYPES

HAS_DOT = shutil.which("dot") is not None
dot_required = pytest.mark.skipif(not HAS_DOT, reason="graphviz `dot` not installed")

FLOW = {
    "diagram_type": "flow",
    "nodes": [
        {"id": "a", "label": "수집"},
        {"id": "b", "label": "임베딩"},
        {"id": "c", "label": "검색"},
    ],
    "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c", "style": "dashed"}],
    "insight": "RAG 파이프라인 단계",
}
TREE = {
    "diagram_type": "tree",
    "nodes": [{"id": "r", "label": "Root"}, {"id": "x", "label": "A", "group": "L1"},
              {"id": "y", "label": "B", "group": "L1"}],
    "edges": [{"from": "r", "to": "x"}, {"from": "r", "to": "y"}],
}
TABLE = {"headers": ["항목", "값"], "rows": [["식비", "25만원"], ["교통", "10만원"]]}


@dot_required
def test_flow_diagram_renders(tmp_path):
    out = tmp_path / "flow.png"
    assert diagram_regen.regenerate_diagram(FLOW, out) == str(out)
    assert out.exists() and out.stat().st_size > 1000


@dot_required
def test_tree_with_groups_renders(tmp_path):
    out = tmp_path / "tree.png"
    assert diagram_regen.regenerate_diagram(TREE, out) == str(out)


@dot_required
def test_table_struct_renders(tmp_path):
    out = tmp_path / "table.png"
    assert diagram_regen.regenerate_diagram(TABLE, out) == str(out)


def test_unsupported_diagram_type_returns_none(tmp_path):
    bad_type = {"diagram_type": "mindmap_3d", "nodes": [{"id": "a"}]}
    assert diagram_regen.regenerate_diagram(bad_type, tmp_path / "x.png") is None
    assert diagram_regen.regenerate_diagram({}, tmp_path / "y.png") is None
    assert diagram_regen.regenerate_diagram("not a dict", tmp_path / "z.png") is None


def test_phantom_node_edge_rejected(tmp_path):
    """Gate (roadmap 2 §5): an edge to an undeclared node → None (hallucination)."""
    bad = {"diagram_type": "flow", "nodes": [{"id": "a", "label": "A"}],
           "edges": [{"from": "a", "to": "ghost"}]}
    assert diagram_regen.regenerate_diagram(bad, tmp_path / "bad.png") is None


def test_empty_nodes_rejected(tmp_path):
    assert diagram_regen.regenerate_diagram(
        {"diagram_type": "flow", "nodes": [], "edges": []}, tmp_path / "e.png"
    ) is None


def test_supported_types_cover_figlib_five():
    assert set(SUPPORTED_DIAGRAM_TYPES) == {"flow", "tree", "layered", "matrix", "swimlane"}


@dot_required
def test_cli_renders_diagram(tmp_path):
    import json
    import subprocess
    import sys
    from pathlib import Path

    out = tmp_path / "cli.png"
    proc = subprocess.run(
        [sys.executable, "-m", "deck_tools.diagram_regen"],
        input=json.dumps({"struct": FLOW, "out": str(out)}),
        capture_output=True, text=True, check=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert json.loads(proc.stdout) == {"png": str(out)}
    assert out.exists()
