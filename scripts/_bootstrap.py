"""Make `masterbuilder_bot` importable when scripts run as
`python scripts/foo.py` from the repo root (no install needed)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
