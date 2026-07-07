#!/usr/bin/env python3
"""Smoke test: prove the wiring works and the safety rails hold.

Runs entirely offline and writes only to a temp directory (MB_DATA_DIR),
so it never touches your real research/drafts/approved content.

Usage: python scripts/smoke_test.py
"""

import os
import sys
import tempfile
from pathlib import Path

import _bootstrap  # noqa: F401
from _bootstrap import ROOT

PASS, FAIL = "  [PASS] ", "  [FAIL] "
results: list[bool] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    results.append(ok)
    print((PASS if ok else FAIL) + label + (f" — {detail}" if detail else ""))


def main() -> int:
    print(f"\nmasterbuilder-bot smoke test — {ROOT}\n")

    # Redirect all data writes to a throwaway dir BEFORE using the library.
    tmp = tempfile.mkdtemp(prefix="mb-smoke-")
    os.environ["MB_DATA_DIR"] = tmp
    os.environ["BOT_MODE"] = "draft_only"

    # 1. Repo folders exist
    for name in ["brand", "config", "research", "drafts", "approved", "posted",
                 "memory/rejected", "masterbuilder_bot", "dashboard/pages", "scripts"]:
        check(f"folder {name}/ exists", (ROOT / name).is_dir())

    # 2. Config loads
    try:
        from masterbuilder_bot import config
        from masterbuilder_bot.research import enabled_sources, load_sources

        data = load_sources()
        srcs = enabled_sources(data)
        check("config/sources.yaml loads", True, f"{len(srcs)} enabled sources")
        check("bot mode defaults to draft_only", config.bot_mode() == "draft_only")
    except Exception as e:  # noqa: BLE001
        check("config loads", False, f"{type(e).__name__}: {e}")
        return finish()

    # 3. Safety rails
    from masterbuilder_bot import safety, storage
    from masterbuilder_bot.models import DraftMeta

    config.ensure_data_dirs()
    meta = DraftMeta(title="smoke test draft", type="x_post",
                     created_at="2026-01-01T00:00:00", sources=["https://example.com"])
    draft_path = storage.save_draft(meta, "test body", day="2026-01-01", index=1)

    # 3a. draft_only mode blocks posting entirely
    try:
        safety.assert_post_allowed(draft_path)
        check("safety blocks posting in draft_only mode", False, "no error raised!")
    except safety.SafetyError:
        check("safety blocks posting in draft_only mode", True)

    # 3b. even in approved_posting mode, drafts/ is blocked
    os.environ["BOT_MODE"] = "approved_posting"
    try:
        safety.assert_post_allowed(draft_path)
        check("safety blocks posting from drafts/", False, "no error raised!")
    except safety.SafetyError:
        check("safety blocks posting from drafts/", True)

    # 3c. approved content passes the location check (mode already allowed)
    from masterbuilder_bot import review
    approved_path = review.approve(draft_path)
    try:
        safety.assert_post_allowed(approved_path)
        check("safety allows approved/ in approved_posting mode", True)
    except safety.SafetyError as e:
        check("safety allows approved/ in approved_posting mode", False, str(e))

    # 3c2. auto_posting mode also arms posting; unknown modes never do
    os.environ["BOT_MODE"] = "auto_posting"
    try:
        safety.assert_mode_allows_posting()
        check("auto_posting mode arms posting", True)
    except safety.SafetyError as e:
        check("auto_posting mode arms posting", False, str(e))
    os.environ["BOT_MODE"] = "approved_posting"

    # 3d. unsourced content is blocked
    try:
        safety.assert_content_safe("some claim", sources=[])
        check("safety blocks unsourced claims", False, "no error raised!")
    except safety.SafetyError:
        check("safety blocks unsourced claims", True)

    # 3e. files outside the data dirs can't be touched
    try:
        safety.assert_safe_to_delete(Path("/etc/hosts"))
        check("safety blocks file ops outside repo", False, "no error raised!")
    except safety.SafetyError:
        check("safety blocks file ops outside repo", True)

    os.environ["BOT_MODE"] = "draft_only"

    # 4. run_daily pipeline completes offline without posting
    try:
        import masterbuilder_bot.research as research_mod
        from masterbuilder_bot.drafting import generate_drafts

        # Force offline: no sources -> empty (but valid) research file.
        original = research_mod.enabled_sources
        research_mod.enabled_sources = lambda data=None: []
        try:
            items, errors = research_mod.run_daily_research(day="2026-01-01")
        finally:
            research_mod.enabled_sources = original

        check("research runs offline", storage.research_file("2026-01-01").exists(),
              f"{len(items)} items, {len(errors)} errors")

        from masterbuilder_bot.models import plan_slots
        expected = len(plan_slots("2026-01-01", []))
        paths, engine = generate_drafts(day="2026-01-01")
        check("drafting completes (template fallback ok)", len(paths) == expected,
              f"{len(paths)} drafts (expected {expected}), engine={engine}")
        check("nothing was posted", not storage.list_posted())

        # continuity: the approval above opened an arc (heuristic, offline),
        # the morning check survives, and Friday's plan swaps in the wrap
        from masterbuilder_bot import continuity
        check("approval opened a story arc", len(continuity.open_arcs()) >= 1,
              f"{len(continuity.open_arcs())} open arcs in memory/arcs.json")
        summary = continuity.check("2026-01-02")
        check("continuity morning check runs offline", isinstance(summary, dict),
              str(summary))
        plan = plan_slots("2026-01-05", [{"dtype": "followup"}])
        check("plan is the reading-list pair (specials take no slots)",
              plan == ["reading_list", "reading_list_substack"], str(plan))
        from masterbuilder_bot.drafting import _updates_digest
        digest = _updates_digest([{"dtype": "record", "event": {
            "label": "Test mark", "record": {"value": 1, "unit": "x",
                                             "holder": "t", "date": "2026-01-01",
                                             "previous": {}}}}])
        check("continuity specials render as Still-watching context",
              "RECORD FELL" in digest, digest[:60])

        from masterbuilder_bot import knowledge
        new, upd = knowledge.build_from_research(day="2026-01-01")
        check("knowledge build survives with no LLM", True, f"{new} new, {upd} updated")

        # media: the fact card renders offline (og:image + stat extraction
        # need the network/LLM and degrade to nothing, which is fine)
        from masterbuilder_bot import media
        card = media.stat_card("800 L/sec", "Seepage through Mosul Dam's "
                               "foundation a year after filling", "Field numbers",
                               Path(tmp) / "smoke-card.png")
        check("fact card renders", card.is_file() and card.stat().st_size > 10_000,
              f"{card.stat().st_size} bytes")
    except Exception as e:  # noqa: BLE001
        check("run_daily pipeline", False, f"{type(e).__name__}: {e}")

    # 5. Dashboard files exist
    for f in ["dashboard/app.py", "dashboard/pages/1_Research.py",
              "dashboard/pages/2_Drafts.py", "dashboard/pages/3_Approved.py",
              "dashboard/pages/4_Settings.py", "dashboard/pages/5_Logs.py"]:
        check(f"{f} exists", (ROOT / f).is_file())

    return finish()


def finish() -> int:
    passed, total = sum(results), len(results)
    print(f"\n{passed}/{total} checks passed.")
    if passed == total:
        print("Smoke test PASSED. The bot is wired correctly and the safety rails hold.")
        return 0
    print("Smoke test FAILED — see [FAIL] lines above.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
