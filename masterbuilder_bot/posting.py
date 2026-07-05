"""Posting layer. In this version it is a DRY-RUN STUB — post_to_x_live()
is a placeholder that never touches the network.

Every path through here goes over the safety rails first:
  * BOT_MODE must be approved_posting
  * the file must live under approved/ (never drafts/)
  * content must carry sources and pass phrase checks
  * cadence caps apply (no mass posting)
"""

from pathlib import Path

from masterbuilder_bot import config, safety, storage
from masterbuilder_bot.logging_utils import log


def build_preview(path: Path) -> dict:
    """What *would* be posted: text + sources. Safe to call anytime."""
    post = storage.load_post(Path(path))
    return {
        "file": str(path),
        "title": post.get("title", ""),
        "type": post.get("type", ""),
        "text": post.content.strip(),
        "sources": post.get("sources", []) or [],
    }


def dry_run_post(path: Path) -> dict:
    """Run every check a live post would run, post nothing, report."""
    path = Path(path)
    preview = build_preview(path)
    checks = {}
    try:
        safety.assert_mode_allows_posting()
        checks["mode"] = "ok"
    except safety.SafetyError as e:
        checks["mode"] = f"BLOCKED: {e}"
    try:
        safety.assert_path_is_approved(path)
        checks["location"] = "ok"
    except safety.SafetyError as e:
        checks["location"] = f"BLOCKED: {e}"
    try:
        safety.assert_content_safe(preview["text"], preview["sources"])
        checks["content"] = "ok"
    except safety.SafetyError as e:
        checks["content"] = f"BLOCKED: {e}"
    try:
        safety.assert_cadence_ok(1)
        checks["cadence"] = "ok"
    except safety.SafetyError as e:
        checks["cadence"] = f"BLOCKED: {e}"

    would_post = all(v == "ok" for v in checks.values())
    log("posting", f"dry-run {path.name}: {'WOULD POST' if would_post else 'blocked'} ({checks})")
    return {**preview, "checks": checks, "would_post": would_post, "dry_run": True}


def post_to_x_live(path: Path) -> dict:
    """PLACEHOLDER for real X posting. Intentionally not implemented.

    When William explicitly asks for live posting, this is where the X API
    call goes (tweepy or requests-oauthlib using the X_* env keys). Until
    then it refuses, loudly.
    """
    raise NotImplementedError(
        "Live X posting is not implemented yet — this is the dry-run/stub "
        "version by design. Ask for the live-posting upgrade explicitly."
    )


def post_approved(path: Path, dry_run: bool = True) -> dict:
    """The one entry point for posting. Dry-run unless explicitly told not
    to be — and even then, live posting is a stub that raises."""
    path = Path(path)

    # Hard gates first — these raise SafetyError and stop everything.
    safety.assert_post_allowed(path)
    preview = build_preview(path)
    safety.assert_content_safe(preview["text"], preview["sources"])
    safety.assert_cadence_ok(1)

    if dry_run:
        return dry_run_post(path)

    result = post_to_x_live(path)  # raises NotImplementedError today
    dest = move_to_posted(path)
    log("posting", f"posted {path.name}, archived to {dest}")
    return {**preview, "posted_to": str(dest), "dry_run": False, **result}


def move_to_posted(path: Path) -> Path:
    """Archive a successfully posted file to posted/<day>/."""
    return storage.set_status_and_move(Path(path), "posted", config.posted_dir())
