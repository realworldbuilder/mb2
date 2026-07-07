#!/usr/bin/env python3
"""The daily pipeline: research -> learn -> continuity -> draft -> knowledge.

Never approves. Never posts. Just gathers signal, updates what it has
learned from your reviews + real engagement, checks open story arcs and
records against the fresh research, and writes drafts for you to review.

Usage: python scripts/run_daily.py
"""

import _bootstrap  # noqa: F401

from masterbuilder_bot import config, continuity, learning, metrics, storage, triage
from masterbuilder_bot.drafting import generate_drafts
from masterbuilder_bot.knowledge import build_from_research, list_entities
from masterbuilder_bot.logging_utils import log, log_error
from masterbuilder_bot.research import run_daily_research


def main() -> int:
    day = storage.today()
    print(f"masterbuilder-bot daily run — {day} (mode: {config.bot_mode()})\n")

    print("[1/5] Research...")
    items, errors = run_daily_research(day)
    print(f"      {len(items)} items saved to research/{day}.json"
          + (f" ({len(errors)} source errors, see memory/runs.log)" if errors else ""))

    # Learning loop BEFORE drafting, so today's drafts use fresh lessons.
    # Both steps are best-effort — they never kill the pipeline.
    print("[2/5] Learning (metrics + voice lessons)...")
    try:
        m = metrics.collect()
        print(f"      X metrics: {m['detail']} "
              f"({m['updated']}/{m['tracked']} posts updated)")
    except Exception as e:  # noqa: BLE001
        log_error(f"[metrics] daily collect failed: {e}")
        print(f"      X metrics skipped ({e})")
    try:
        lessons = learning.rebuild()
        print(f"      voice lessons {'updated' if lessons else 'skipped (no signal yet)'}")
    except Exception as e:  # noqa: BLE001
        log_error(f"[learning] daily rebuild failed: {e}")
        print(f"      voice lessons skipped ({e})")

    # Continuity BEFORE drafting: triage scores the day (idempotent — the
    # results persist, so drafting's own prepare() is free), then open arcs
    # get matched against the fresh research and due receipts get graded.
    print("[3/5] Continuity (story arcs, receipts, records)...")
    try:
        triage.prepare(day)
        s = continuity.check(day)
        broken = continuity.update_records(day)
        print(f"      {s['matched']} arc match(es), {s['graded']} receipt(s) "
              f"graded, {broken} record(s) broken "
              f"({len(continuity.open_arcs())} arcs open)")
    except Exception as e:  # noqa: BLE001
        log_error(f"[continuity] daily check failed: {e}")
        print(f"      continuity skipped ({e})")

    print("[4/5] Drafting...")
    paths, engine = generate_drafts(day)
    print(f"      {len(paths)} drafts saved (engine: {engine})")

    print("[5/5] Knowledge base...")
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
