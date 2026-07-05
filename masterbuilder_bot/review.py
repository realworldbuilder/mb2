"""Approve / reject / edit drafts. Used by both the CLI review queue and
the dashboard, so behavior is identical everywhere.

approve: drafts/<day>/x.md -> approved/<day>/x.md   (status: approved)
reject:  drafts/<day>/x.md -> memory/rejected/<day>/x.md (status: rejected)

Every decision is also logged to memory/feedback.jsonl (see feedback.py)
— that log is what the voice learns from, so passing a short reason
("too hype", "great hook") makes future drafts better.
"""

from pathlib import Path

from masterbuilder_bot import config, feedback, storage
from masterbuilder_bot.logging_utils import log


def _meta(path: Path) -> tuple[str, str, str]:
    """(type, title, body) for feedback logging. Never raises."""
    try:
        post = storage.load_post(Path(path))
        return post.get("type", ""), post.get("title", ""), post.content
    except Exception:  # noqa: BLE001
        return "", "", ""


def approve(path: Path, reason: str = "") -> Path:
    dtype, title, body = _meta(path)
    dest = storage.set_status_and_move(Path(path), "approved", config.approved_dir())
    feedback.log_event("approved", dest, dtype, title, reason, body)
    log("review", f"approved {dest.name} -> {dest.parent}")
    return dest


def reject(path: Path, reason: str = "") -> Path:
    dtype, title, body = _meta(path)
    dest = storage.set_status_and_move(Path(path), "rejected", config.rejected_dir())
    feedback.log_event("rejected", dest, dtype, title, reason, body)
    log("review", f"rejected {Path(path).name} -> {dest.parent}")
    return dest


def save_edit(path: Path, new_body: str) -> None:
    """Replace a draft's body, keeping its frontmatter.

    Logs before/after heads to feedback — your edits are the strongest
    voice signal there is.
    """
    post = storage.load_post(Path(path))
    old_body = post.content
    if new_body.strip() == old_body.strip():
        return  # nothing changed, nothing to log
    post.content = new_body
    storage.save_post(Path(path), post)
    feedback.log_event(
        "edited", path, post.get("type", ""), post.get("title", ""),
        body=new_body, extra={"before_head": old_body.strip()[:400]},
    )
    log("review", f"edited {Path(path).name}")


def draft_summary(path: Path) -> dict:
    """Frontmatter + preview for list views. Never raises on a bad file."""
    path = Path(path)
    try:
        post = storage.load_post(path)
        return {
            "path": str(path),
            "name": path.name,
            "day": path.parent.name,
            "title": post.get("title", path.stem),
            "type": post.get("type", "?"),
            "status": post.get("status", "?"),
            "created_at": post.get("created_at", ""),
            "sources": post.get("sources", []) or [],
            "risk_score": post.get("risk_score", "?"),
            "usefulness_score": post.get("usefulness_score", "?"),
            "originality_score": post.get("originality_score", "?"),
            "preview": post.content.strip().splitlines()[0][:120] if post.content.strip() else "",
        }
    except Exception as e:  # noqa: BLE001
        return {"path": str(path), "name": path.name, "day": path.parent.name,
                "title": f"(unreadable: {e})", "type": "?", "status": "?",
                "created_at": "", "sources": [], "risk_score": "?",
                "usefulness_score": "?", "originality_score": "?", "preview": ""}
