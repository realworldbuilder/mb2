#!/usr/bin/env python3
"""Build the public site and push docs/ to GitHub (Pages serves it).

Runs on the Mac mini after the daily pipeline. Publishes ONLY:
  * posts you approved (approved/)
  * directory entries with verified links (knowledge/, verified: true)
Drafts, research, and unverified entities never leave the machine.

Usage: python scripts/publish_site.py
"""

import subprocess

import _bootstrap  # noqa: F401
from _bootstrap import ROOT

from build_site import build  # noqa: E402


def run(*cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)


def main() -> int:
    posts, entities = build()
    print(f"Built: {posts} posts, {entities} verified entities.")

    if run("git", "status", "--porcelain", "docs").stdout.strip() == "":
        print("No site changes to publish.")
        return 0

    run("git", "add", "docs")
    commit = run("git", "commit", "-m",
                 f"site: rebuild — {posts} posts, {entities} directory entries\n\n"
                 "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>")
    if commit.returncode != 0:
        print(f"Commit failed:\n{commit.stderr}")
        return 1
    push = run("git", "push", "origin", "main")
    if push.returncode != 0:
        print(f"Push failed (site is built locally, will retry next run):\n{push.stderr}")
        return 1
    print("Published to GitHub Pages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
