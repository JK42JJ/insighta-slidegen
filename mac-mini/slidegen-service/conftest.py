"""Make the flat service modules (app, acquire, frames, ...) importable in tests.

pytest loads this conftest from the service root, so inserting this directory onto
sys.path lets `tests/` do `from app import app` without an editable install.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
