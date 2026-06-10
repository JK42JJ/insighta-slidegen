"""Make tests/-local helper packages (stubs/) importable regardless of the
pytest import mode or invocation directory (CI runs from the repo root)."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
