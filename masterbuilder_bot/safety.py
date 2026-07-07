"""Hard safety rails. Everything here raises SafetyError — no warnings,
no "probably fine". If a check fails, the action does not happen.

The rules, in plain English:
  1. No posting unless BOT_MODE is approved_posting or auto_posting.
  2. No posting from drafts/ — only from approved/.
  3. No mass posting (per-run and per-day caps).
  4. No DMs. The bot has no DM code and never will without you adding it.
  5. No deleting files outside this repo's data folders.
  6. No unsourced factual claims (posts must carry sources).
  7. No pretending to be a human.
  8. No engagement farming, political ragebait, or spam cadence.
  9. No secrets in dashboard or logs (see redact_secrets).
"""

import os
from pathlib import Path

from masterbuilder_bot import config

MAX_POSTS_PER_RUN = 1  # one approved post per invocation, on purpose
MAX_POSTS_PER_DAY = 5

# Lowercase substrings that mark engagement farming, DM behavior, or
# ragebait. Extend this list as you learn what slips through.
BANNED_PHRASES = [
    "dm me",
    "dm us",
    "check your dms",
    "follow for follow",
    "like and retweet",
    "rt if you agree",
    "retweet if",
    "tag a friend",
    "you won't believe",
    "wake up sheeple",
    "the radical left",
    "the radical right",
]

# Phrases that read as the bot pretending to be William / a human.
IMPERSONATION_PHRASES = [
    "as a human",
    "i swung a hammer this morning",
    "speaking as william",
]


class SafetyError(Exception):
    """Raised when an action would break a hard rule."""


def redact_secrets(text: str) -> str:
    """Replace any secret value that appears in text with [REDACTED]."""
    for key in config.SECRET_KEYS:
        value = os.environ.get(key, "").strip()
        if value and value in text:
            text = text.replace(value, f"[REDACTED:{key}]")
    return text


def assert_mode_allows_posting() -> None:
    mode = config.bot_mode()
    if mode not in (config.APPROVED_POSTING, config.AUTO_POSTING):
        raise SafetyError(
            f"BOT_MODE is '{mode}'. Posting requires BOT_MODE=approved_posting "
            "or auto_posting. Nothing was posted."
        )


def assert_path_is_approved(path: Path) -> None:
    """The file must live under approved/ — never drafts/ or anywhere else."""
    path = Path(path).resolve()
    approved = config.approved_dir().resolve()
    drafts = config.drafts_dir().resolve()

    if path.is_relative_to(drafts):
        raise SafetyError(
            f"{path.name} is in drafts/. The bot never posts from drafts. "
            "Approve it first (review queue or dashboard)."
        )
    if not path.is_relative_to(approved):
        raise SafetyError(
            f"{path} is not under approved/. Only approved content can be posted."
        )
    if not path.exists():
        raise SafetyError(f"{path} does not exist.")


def assert_post_allowed(path: Path) -> None:
    """Full gate for a live post: mode + location."""
    assert_mode_allows_posting()
    assert_path_is_approved(path)


def assert_content_safe(text: str, sources: list) -> None:
    """Content-level checks: sources present, no banned patterns."""
    if not sources:
        raise SafetyError(
            "Post has no sources in its frontmatter. "
            "No unsourced factual claims — add sources or reject the draft."
        )
    lowered = text.lower()
    for phrase in BANNED_PHRASES:
        if phrase in lowered:
            raise SafetyError(f"Banned phrase in content: '{phrase}'. Not posting.")
    for phrase in IMPERSONATION_PHRASES:
        if phrase in lowered:
            raise SafetyError(
                f"Content pretends to be a human ('{phrase}'). Not posting."
            )


def assert_cadence_ok(planned_count: int = 1) -> None:
    """No mass posting, no spam cadence."""
    if planned_count > MAX_POSTS_PER_RUN:
        raise SafetyError(
            f"Tried to post {planned_count} items in one run "
            f"(max {MAX_POSTS_PER_RUN}). No mass posting."
        )
    posted_today = 0
    from masterbuilder_bot import storage  # local import to avoid cycles

    day_dir = config.posted_dir() / storage.today()
    if day_dir.exists():
        posted_today = len(list(day_dir.glob("*.md")))
    if posted_today + planned_count > MAX_POSTS_PER_DAY:
        raise SafetyError(
            f"Already posted {posted_today} today (daily cap {MAX_POSTS_PER_DAY}). "
            "Spam cadence blocked."
        )


def assert_safe_to_delete(path: Path) -> None:
    """Files may only ever be removed/moved within this project's data dirs."""
    path = Path(path).resolve()
    home = config.data_home().resolve()
    if not path.is_relative_to(home):
        raise SafetyError(f"Refusing to touch {path} — outside the project.")
    allowed = [d.resolve() for d in config.data_dirs()]
    if not any(path.is_relative_to(d) for d in allowed):
        raise SafetyError(
            f"Refusing to delete/move {path} — not inside a bot data folder."
        )
