#!/usr/bin/env python3
"""Pull today's research from config/sources.yaml into research/YYYY-MM-DD.json.

Usage: python scripts/daily_research.py
"""

import _bootstrap  # noqa: F401

from masterbuilder_bot import storage
from masterbuilder_bot.research import run_daily_research


def main() -> int:
    items, errors = run_daily_research()
    print(f"Research run complete: {len(items)} items saved to "
          f"{storage.research_file()}")
    if errors:
        print(f"\n{len(errors)} source(s) failed (run continued anyway):")
        for e in errors:
            print(f"  - {e}")
        print("Details in memory/runs.log")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
