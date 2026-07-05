#!/usr/bin/env python3
"""Launch the Masterbuilder Command Center (Streamlit dashboard).

Local-only by default: binds to localhost. To reach it from another
machine on your Tailscale/local network, see the README (Mac mini
dashboard notes) — do NOT expose it to the public internet.

Usage: python scripts/run_dashboard.py
"""

import subprocess
import sys

import _bootstrap  # noqa: F401
from _bootstrap import ROOT


def main() -> int:
    app = ROOT / "dashboard" / "app.py"
    cmd = [
        sys.executable, "-m", "streamlit", "run", str(app),
        "--server.address", "localhost",
        "--server.port", "8501",
        "--browser.gatherUsageStats", "false",
    ]
    print("Starting Masterbuilder Command Center at http://localhost:8501")
    print("(Ctrl+C to stop)")
    return subprocess.call(cmd, cwd=str(ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
