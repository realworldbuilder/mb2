#!/usr/bin/env python3
"""Mine a day's research into the knowledge base (knowledge/*.md).

Runs automatically as part of run_daily.py — this script is for re-running
extraction manually (e.g. after adding sources or switching models).

Usage: python scripts/build_knowledge.py [--day YYYY-MM-DD]
"""

import argparse

import _bootstrap  # noqa: F401

from masterbuilder_bot import storage
from masterbuilder_bot.knowledge import build_from_research, list_entities


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day", default=None, help="date to mine (default: today)")
    args = parser.parse_args()

    day = args.day or storage.today()
    print(f"Mining research/{day}.json into the knowledge base...")
    new, updated = build_from_research(day)
    total = len(list_entities())
    print(f"Done: {new} new entities, {updated} updated — {total} total in knowledge/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
