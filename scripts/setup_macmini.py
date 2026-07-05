#!/usr/bin/env python3
"""Setup check for a fresh machine (your Mac, later the Mac mini).

Read-only: reports what's missing, changes nothing.

Usage: python scripts/setup_macmini.py
"""

import os
import sys
from pathlib import Path

import _bootstrap  # noqa: F401
from _bootstrap import ROOT

OK, BAD, WARN = "  [ok] ", "  [!!] ", "  [--] "


def check_python() -> bool:
    v = sys.version_info
    good = v >= (3, 10)
    print((OK if good else BAD) + f"Python {v.major}.{v.minor}.{v.micro}"
          + ("" if good else " — need 3.10+"))
    return good


def check_folders() -> bool:
    needed = ["brand", "config", "research", "drafts", "approved", "posted",
              "memory", "memory/rejected", "scripts", "masterbuilder_bot", "dashboard"]
    all_good = True
    for name in needed:
        exists = (ROOT / name).is_dir()
        all_good &= exists
        print((OK if exists else BAD) + f"folder {name}/")
    return all_good


def check_env() -> bool:
    env = ROOT / ".env"
    if not env.exists():
        print(BAD + ".env missing — run: cp .env.example .env")
        return False
    print(OK + ".env exists")
    return True


def check_write_permissions() -> bool:
    all_good = True
    for name in ["research", "drafts", "approved", "posted", "memory"]:
        d = ROOT / name
        writable = d.is_dir() and os.access(d, os.W_OK)
        all_good &= writable
        if not writable:
            print(BAD + f"{name}/ not writable")
    if all_good:
        print(OK + "data folders writable")
    return all_good


def check_deps() -> bool:
    missing = []
    for mod in ["dotenv", "yaml", "requests", "bs4", "feedparser", "pydantic",
                "frontmatter", "pandas", "streamlit"]:
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        print(BAD + f"missing packages: {', '.join(missing)} — run: pip install -r requirements.txt")
        return False
    print(OK + "python dependencies installed")
    return True


def check_llm() -> None:
    # Never print key values — only whether they're set.
    try:
        from masterbuilder_bot import config
        from masterbuilder_bot.llm import llm_status

        status = llm_status()
        for key, is_set in config.secret_status().items():
            marker = OK if is_set else WARN
            print(marker + f"{key}: {'set' if is_set else 'not set'}")
        print(OK + f"LLM provider: {status['provider']} (model: {status['model']})")
        print(OK + f"BOT_MODE: {config.bot_mode()}")
    except ImportError:
        print(WARN + "can't check LLM config until dependencies are installed")


def main() -> int:
    print(f"\nmasterbuilder-bot setup check — {ROOT}\n")
    results = [check_python(), check_folders(), check_env(),
               check_write_permissions(), check_deps()]
    check_llm()

    print()
    if all(results):
        print("All checks passed. Next steps:")
        print("  1. python scripts/run_daily.py        # research + drafts")
        print("  2. python scripts/review_queue.py     # approve/reject in the terminal")
        print("  3. python scripts/run_dashboard.py    # Masterbuilder Command Center")
        return 0
    print("Some checks failed — fix the [!!] lines above, then re-run this script.")
    print("Typical fresh setup:")
    print("  python3 -m venv .venv && source .venv/bin/activate")
    print("  pip install -r requirements.txt")
    print("  cp .env.example .env   # then add your API key")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
