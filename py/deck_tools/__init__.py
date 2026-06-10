"""deck_tools — vendored insighta-visual-deck Python tools (ADR 0003 D7).

`validate_deck.py` and `figures.py` are byte-identical copies of
`deck/scripts/validate_deck.py` and `deck/scripts/figures.py` (vendored as-is,
no rewrites). The canonical run location is `deck/scripts/`; these copies make
the validator/figure logic importable from the Python layer and testable under
`py/tests/`.

`chart_regen.py` is FIRST-PARTY (not vendored): mode-B struct-JSON →
brand-styled matplotlib PNG (≥ 300 dpi), following the figures.py pattern.

Notes:
- `validate_deck` is stdlib-only and safe to import anywhere.
- `chart_regen` imports matplotlib (Agg) at module level — import it only
  where matplotlib is present (CI installs it via the CV-service deps).
- `figures` imports matplotlib/graphviz at module level and resolves its font
  dir relative to its own file (`../assets/fonts`) — import it only where
  those deps (and fonts) are present. Do NOT import it from this package
  __init__ (CI has neither dependency).
"""
