#!/usr/bin/env python3
"""Post an APPROVED item to X. DRY-RUN ONLY in this version.

Hard rules enforced by masterbuilder_bot.safety:
  * Refuses to run unless BOT_MODE=approved_posting.
  * Refuses to post anything not in approved/ (drafts/ is explicitly blocked).
  * Live posting is a stub (post_to_x_live raises NotImplementedError).

Usage:
  python scripts/post_x.py --file approved/2026-07-05/01-x_post-something.md
  python scripts/post_x.py --file <path> --dry-run       (explicit, same as default)
"""

import argparse
from pathlib import Path

import _bootstrap  # noqa: F401

from masterbuilder_bot import config, posting
from masterbuilder_bot.safety import SafetyError, assert_mode_allows_posting


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, help="path to an approved .md file")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="dry-run (always on in this version)")
    args = parser.parse_args()

    # Gate 1: mode. This refuses in draft_only before anything else happens.
    try:
        assert_mode_allows_posting()
    except SafetyError as e:
        print(f"BLOCKED: {e}")
        return 1

    path = Path(args.file)
    try:
        result = posting.post_approved(path, dry_run=True)  # live posting not implemented
    except SafetyError as e:
        print(f"BLOCKED: {e}")
        return 1
    except NotImplementedError as e:
        print(f"NOT IMPLEMENTED: {e}")
        return 1

    print("=" * 60)
    print("DRY RUN — nothing was posted to X.")
    print("=" * 60)
    print(f"Title: {result['title']}")
    print(f"Would post:\n\n{result['text'][:500]}\n")
    print(f"Sources: {len(result['sources'])}")
    for check, status in result["checks"].items():
        print(f"  {check}: {status}")
    if result["would_post"]:
        print("\nAll checks passed. When live posting is implemented (and you've "
              "asked for it explicitly), this item would be posted and moved to posted/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
