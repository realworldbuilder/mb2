"""All file I/O for research JSON and markdown drafts with frontmatter.

Layout (everything dated):
    research/YYYY-MM-DD.json
    drafts/YYYY-MM-DD/NN-type-slug.md
    approved/YYYY-MM-DD/...
    posted/YYYY-MM-DD/...
    memory/rejected/YYYY-MM-DD/...
"""

import json
import re
from datetime import date
from pathlib import Path

import frontmatter

from masterbuilder_bot import config, safety
from masterbuilder_bot.models import DraftMeta, ResearchItem


def today() -> str:
    return date.today().isoformat()


def slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len] or "untitled"


# ---------- research ----------

def research_file(day: str | None = None) -> Path:
    return config.research_dir() / f"{day or today()}.json"


def save_research(items: list[ResearchItem], day: str | None = None) -> Path:
    config.ensure_data_dirs()
    path = research_file(day)
    path.write_text(
        json.dumps([i.model_dump() for i in items], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def load_research(day: str | None = None) -> list[ResearchItem]:
    path = research_file(day)
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [ResearchItem(**item) for item in raw]


def research_days() -> list[str]:
    d = config.research_dir()
    if not d.exists():
        return []
    return sorted((p.stem for p in d.glob("*.json")), reverse=True)


def update_research_statuses(day: str, url_to_status: dict) -> int:
    """Write review marks (useful/maybe/ignore) back into the day's JSON."""
    items = load_research(day)
    changed = 0
    for item in items:
        new = url_to_status.get(item.url)
        if new and new != item.status:
            item.status = new
            changed += 1
    if changed:
        save_research(items, day)
    return changed


# ---------- drafts / approved / posted / rejected ----------

def day_dir(root: Path, day: str | None = None) -> Path:
    return root / (day or today())


def save_draft(meta: DraftMeta, body: str, day: str | None = None,
               index: int = 0) -> Path:
    config.ensure_data_dirs()
    d = day_dir(config.drafts_dir(), day)
    d.mkdir(parents=True, exist_ok=True)
    name = f"{index:02d}-{meta.type}-{slugify(meta.title)}.md"
    post = frontmatter.Post(body, **meta.model_dump())
    path = d / name
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    return path


def load_post(path: Path) -> frontmatter.Post:
    return frontmatter.load(str(path))


def save_post(path: Path, post: frontmatter.Post) -> None:
    Path(path).write_text(frontmatter.dumps(post), encoding="utf-8")


def list_markdown(root: Path, day: str | None = None) -> list[Path]:
    """All .md files under root (one day, or every day, newest day first)."""
    if not root.exists():
        return []
    if day:
        d = root / day
        return sorted(d.glob("*.md")) if d.exists() else []
    files: list[Path] = []
    for sub in sorted(root.iterdir(), reverse=True):
        if sub.is_dir():
            files.extend(sorted(sub.glob("*.md")))
    return files


def list_drafts(day: str | None = None) -> list[Path]:
    return list_markdown(config.drafts_dir(), day)


def list_approved(day: str | None = None) -> list[Path]:
    return list_markdown(config.approved_dir(), day)


def list_posted(day: str | None = None) -> list[Path]:
    return list_markdown(config.posted_dir(), day)


def content_days(root: Path) -> list[str]:
    if not root.exists():
        return []
    return sorted((p.name for p in root.iterdir() if p.is_dir()), reverse=True)


def set_status_and_move(path: Path, new_status: str, dest_root: Path) -> Path:
    """Update frontmatter status and move the file to dest_root/<same day>/.

    Guarded by safety.assert_safe_to_delete so nothing outside the bot's
    data folders can ever be moved or removed.
    """
    path = Path(path)
    safety.assert_safe_to_delete(path)
    post = load_post(path)
    post["status"] = new_status
    day = path.parent.name  # drafts/<day>/<file>
    dest_dir = dest_root / day
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / path.name
    dest.write_text(frontmatter.dumps(post), encoding="utf-8")
    path.unlink()
    return dest
