#!/usr/bin/env python3
"""The daily pipeline: research -> draft -> summary.

Never approves. Never posts. Just gathers signal and writes drafts for
you to review.

Usage: python scripts/run_daily.py
"""

import _bootstrap  # noqa: F401

from masterbuilder_bot import config, storage
from masterbuilder_bot.drafting import generate_drafts
from masterbuilder_bot.knowledge import build_from_research, list_entities
from masterbuilder_bot.logging_utils import log
from masterbuilder_bot.research import run_daily_research


def main() -> int:
    day = storage.today()
    print(f"masterbuilder-bot daily run — {day} (mode: {config.bot_mode()})\n")

    print("[1/3] Research...")
    items, errors = run_daily_research(day)
    print(f"      {len(items)} items saved to research/{day}.json"
          + (f" ({len(errors)} source errors, see memory/runs.log)" if errors else ""))

    print("[2/3] Drafting...")
    paths, engine = generate_drafts(day)
    print(f"      {len(paths)} drafts saved (engine: {engine})")

    print("[3/3] Knowledge base...")
    new, updated = build_from_research(day)
    print(f"      {new} new entities, {updated} updated "
          f"({len(list_entities())} total in knowledge/)")

    log("setup", f"daily run complete: {len(items)} research items, "
                 f"{len(paths)} drafts, +{new}/{updated} knowledge entities")

    print("\n" + "=" * 60)
    print(f"Done. Drafts are in: drafts/{day}/")
    print("Nothing was approved. Nothing was posted.")
    print("Review with: python scripts/review_queue.py")
    print("Or the dashboard: python scripts/run_dashboard.py")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
