"""Approve / reject / edit drafts. Used by both the CLI review queue and
the dashboard, so behavior is identical everywhere.

approve: drafts/<day>/x.md -> approved/<day>/x.md   (status: approved)
reject:  drafts/<day>/x.md -> memory/rejected/<day>/x.md (status: rejected)
"""

from pathlib import Path

from masterbuilder_bot import config, storage
from masterbuilder_bot.logging_utils import log


def approve(path: Path) -> Path:
    dest = storage.set_status_and_move(Path(path), "approved", config.approved_dir())
    log("review", f"approved {dest.name} -> {dest.parent}")
    return dest


def reject(path: Path) -> Path:
    dest = storage.set_status_and_move(Path(path), "rejected", config.rejected_dir())
    log("review", f"rejected {Path(path).name} -> {dest.parent}")
    return dest


def save_edit(path: Path, new_body: str) -> None:
    """Replace a draft's body, keeping its frontmatter."""
    post = storage.load_post(Path(path))
    post.content = new_body
    storage.save_post(Path(path), post)
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
