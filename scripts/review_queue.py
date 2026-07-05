#!/usr/bin/env python3
"""CLI review queue: view, approve, reject, or edit drafts.

Approved  -> approved/YYYY-MM-DD/
Rejected  -> memory/rejected/YYYY-MM-DD/

Usage: python scripts/review_queue.py
"""

import os
import subprocess

import _bootstrap  # noqa: F401

from masterbuilder_bot import review, storage


def show_list(paths) -> None:
    print()
    if not paths:
        print("  (no drafts waiting — run `python scripts/run_daily.py` first)")
    for n, p in enumerate(paths, 1):
        s = review.draft_summary(p)
        print(f"  [{n}] {s['day']} | {s['type']:<14} | risk {s['risk_score']} | {s['title']}")
    print()


def pick(paths, raw: str):
    try:
        n = int(raw)
        if 1 <= n <= len(paths):
            return paths[n - 1]
    except ValueError:
        pass
    print("  Invalid number.")
    return None


def view(path) -> None:
    s = review.draft_summary(path)
    print("\n" + "=" * 70)
    print(f"{s['title']}  [{s['type']}]  risk={s['risk_score']} "
          f"useful={s['usefulness_score']} original={s['originality_score']}")
    print("=" * 70)
    print(storage.load_post(path).content)
    print("=" * 70 + "\n")


def edit(path) -> None:
    editor = os.environ.get("EDITOR", "nano")
    subprocess.run([editor, str(path)])
    print(f"  Saved (whatever {editor} wrote).")


def main() -> int:
    while True:
        drafts = storage.list_drafts()
        show_list(drafts)
        print("  v <n> view | a <n> approve | r <n> reject | e <n> edit | l list approved | q quit")
        try:
            raw = input("review> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not raw:
            continue
        cmd, _, arg = raw.partition(" ")
        cmd = cmd.lower()

        if cmd == "q":
            return 0
        if cmd == "l":
            approved = storage.list_approved()
            print("\n  Approved:")
            if not approved:
                print("    (none yet)")
            for p in approved:
                print(f"    - {p.parent.name}/{p.name}")
            continue
        if cmd in ("v", "a", "r", "e"):
            if not drafts:
                continue
            path = pick(drafts, arg)
            if path is None:
                continue
            if cmd == "v":
                view(path)
            elif cmd == "a":
                dest = review.approve(path)
                print(f"  Approved -> {dest}")
            elif cmd == "r":
                dest = review.reject(path)
                print(f"  Rejected -> {dest}")
            elif cmd == "e":
                edit(path)
        else:
            print("  Unknown command.")


if __name__ == "__main__":
    raise SystemExit(main())
