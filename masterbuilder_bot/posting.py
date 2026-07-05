"""Posting layer — routes approved content to its platform (X, LinkedIn,
Substack) through the safety rails. Live posting is real now, but every
path still goes over the rails first:

  * BOT_MODE must be approved_posting
  * the file must live under approved/ (never drafts/)
  * content must carry sources and pass phrase checks
  * cadence caps apply (no mass posting)
  * the platform must be explicitly configured (env keys present)

After a successful live post, the file's frontmatter records where it
went (posted_to / post_id / post_url / posted_at) and the file moves to
posted/<day>/ — that record is what the metrics collector reads.
"""

from datetime import datetime
from pathlib import Path

from masterbuilder_bot import config, publishers, safety, storage
from masterbuilder_bot.logging_utils import log


def build_preview(path: Path) -> dict:
    """What *would* be posted: text + sources + destination. Safe anytime."""
    post = storage.load_post(Path(path))
    dtype = post.get("type", "")
    return {
        "file": str(path),
        "title": post.get("title", ""),
        "type": dtype,
        "platform": publishers.platform_for(dtype),
        "text": post.content.strip(),
        "sources": post.get("sources", []) or [],
    }


def dry_run_post(path: Path, platform: str | None = None) -> dict:
    """Run every check a live post would run, post nothing, report."""
    path = Path(path)
    preview = build_preview(path)
    platform = platform or preview["platform"]
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
    if platform is None:
        checks["platform"] = "BLOCKED: this draft type has no publish destination"
    elif not publishers.get(platform).is_configured():
        missing = ", ".join(publishers.get(platform).missing_keys())
        checks["platform"] = f"BLOCKED: {platform} not configured (missing: {missing})"
    else:
        checks["platform"] = "ok"

    would_post = all(v == "ok" for v in checks.values())
    log("posting", f"dry-run {path.name} -> {platform}: "
                   f"{'WOULD POST' if would_post else 'blocked'}")
    return {**preview, "checks": checks, "would_post": would_post,
            "dry_run": True, "platform": platform}


def post_live(path: Path, platform: str | None = None) -> dict:
    """The one entry point for live posting.

    Raises SafetyError if any rail blocks. On publisher failure the file
    STAYS in approved/ so you can retry. On success it moves to posted/.
    """
    path = Path(path)

    # Hard gates first — these raise SafetyError and stop everything.
    safety.assert_post_allowed(path)
    preview = build_preview(path)
    safety.assert_content_safe(preview["text"], preview["sources"])
    safety.assert_cadence_ok(1)

    platform = platform or preview["platform"]
    if platform is None:
        raise safety.SafetyError(
            f"'{preview['type']}' drafts have no publish destination — "
            "they're internal content (use the text manually)."
        )
    pub = publishers.get(platform)
    if not pub.is_configured():
        raise safety.SafetyError(
            f"{platform} is not configured (missing: {', '.join(pub.missing_keys())}). "
            "Add the keys on the Connections page."
        )

    result = pub.publish(preview["text"], title=preview["title"],
                         sources=preview["sources"])
    if not result.get("ok"):
        # No file move on failure — retry later from approved/.
        log("posting", f"LIVE POST FAILED {path.name} -> {platform}: {result.get('detail')}")
        return {**preview, "dry_run": False, "posted": False, **result}

    # Record where it went, then archive to posted/<day>/.
    post = storage.load_post(path)
    post["posted_to"] = platform
    post["post_id"] = result.get("id", "")
    post["post_url"] = result.get("url", "")
    post["posted_at"] = datetime.now().isoformat(timespec="seconds")
    storage.save_post(path, post)
    dest = move_to_posted(path)
    log("posting", f"LIVE posted {dest.name} -> {platform} ({result.get('url', '')})")
    return {**preview, "dry_run": False, "posted": True,
            "posted_to": str(dest), **result}


def post_approved(path: Path, dry_run: bool = True, platform: str | None = None) -> dict:
    """Back-compat entry point: dry-run unless explicitly told otherwise."""
    if dry_run:
        return dry_run_post(Path(path), platform)
    return post_live(Path(path), platform)


def move_to_posted(path: Path) -> Path:
    """Archive a successfully posted file to posted/<day>/."""
    return storage.set_status_and_move(Path(path), "posted", config.posted_dir())
