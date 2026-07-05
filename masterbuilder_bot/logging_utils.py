"""Append-only run log at memory/runs.log. Secrets are redacted on write.

Line format:
    2026-07-05T06:00:01 [research] pulled 14 items from 6 sources
Categories used: research, drafting, review, posting, dashboard, setup, error
"""

from datetime import datetime

from masterbuilder_bot import config
from masterbuilder_bot.safety import redact_secrets

CATEGORIES = ("research", "drafting", "review", "posting", "dashboard", "setup", "error")


def log(category: str, message: str) -> None:
    config.memory_dir().mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().isoformat(timespec="seconds")
    line = f"{stamp} [{category}] {redact_secrets(message)}\n"
    with open(config.runs_log_file(), "a", encoding="utf-8") as f:
        f.write(line)


def log_error(message: str) -> None:
    log("error", message)


def read_log_lines(newest_first: bool = True) -> list[str]:
    path = config.runs_log_file()
    if not path.exists():
        return []
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return list(reversed(lines)) if newest_first else lines
