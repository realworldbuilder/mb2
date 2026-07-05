#!/usr/bin/env python3
"""Generate the daily draft set from today's research JSON + brand files.

Produces in drafts/YYYY-MM-DD/:
  5 short X posts, 2 X threads, 1 Field Manual essay,
  1 meme/content idea, 1 builder-signal note.

Usage: python scripts/draft_posts.py [--day YYYY-MM-DD]
"""

import argparse

import _bootstrap  # noqa: F401

from masterbuilder_bot import storage
from masterbuilder_bot.drafting import generate_drafts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day", default=None, help="date to draft for (default: today)")
    args = parser.parse_args()

    day = args.day or storage.today()
    if not storage.load_research(day):
        print(f"Note: no research found for {day} — drafts will be evergreen/empty-sourced.")
        print("Run `python scripts/daily_research.py` first for sourced drafts.\n")

    paths, engine = generate_drafts(day)
    print(f"Generated {len(paths)} drafts (engine: {engine}) in drafts/{day}/:")
    for p in paths:
        print(f"  - {p.name}")
    if engine == "template":
        print("\n(OPENAI_API_KEY not set or API unavailable — used template drafts. "
              "They're rough on purpose: edit them in the review queue or dashboard.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
