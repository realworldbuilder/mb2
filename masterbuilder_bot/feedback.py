"""Feedback log — the raw material the bot learns from.

Every review decision (approve / reject / edit) is appended to
memory/feedback.jsonl as one JSON line. Reasons are optional but gold:
"too hype", "great hook", "not concrete" teach the voice far faster
than the decision alone.

Nothing here ever blocks a review action — if logging fails, the
approve/reject still goes through and the error lands in runs.log.
"""

import json
from datetime import datetime
from pathlib import Path

from masterbuilder_bot import config
from masterbuilder_bot.logging_utils import log_error

# Quick-pick reasons shown in the dashboard. Extend freely — free text
# is always allowed too.
APPROVE_TAGS = ["great hook", "concrete numbers", "good story", "sounds like me"]
REJECT_TAGS = ["too hype", "not concrete", "sounds like AI", "wrong topic",
               "boring", "too long"]


def feedback_file() -> Path:
    return config.memory_dir() / "feedback.jsonl"


def log_event(action: str, path: Path, dtype: str = "", title: str = "",
              reason: str = "", body: str = "", extra: dict | None = None) -> None:
    """Append one feedback event. Never raises."""
    try:
        config.ensure_data_dirs()
        event = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "action": action,          # approved | rejected | edited
            "file": Path(path).name,
            "day": Path(path).parent.name,
            "type": dtype,
            "title": title,
            "reason": reason.strip(),
            # first 400 chars is enough for the learner to see the style
            "body_head": body.strip()[:400],
            **(extra or {}),
        }
        with feedback_file().open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception as e:  # noqa: BLE001 — feedback must never block review
        log_error(f"[feedback] could not log {action}: {e}")


def load_events(limit: int = 300) -> list[dict]:
    """Most recent events, oldest first (up to limit)."""
    path = feedback_file()
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events[-limit:]


def counts(events: list[dict] | None = None) -> dict:
    """Approve/reject/edit tallies, and reason frequency."""
    events = events if events is not None else load_events()
    out: dict = {"approved": 0, "rejected": 0, "edited": 0, "reasons": {}}
    for e in events:
        a = e.get("action", "")
        if a in out:
            out[a] += 1
        r = e.get("reason", "")
        if r:
            out["reasons"][r] = out["reasons"].get(r, 0) + 1
    return out
