"""Make the flat service module (app) importable in tests (mirrors the
mac-mini/slidegen-service conftest pattern — no editable install needed)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
