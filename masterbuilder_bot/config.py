"""Paths, environment, and bot mode. One place for all of it, no magic.

Data directories (research/, drafts/, approved/, posted/, memory/) can be
redirected with the MB_DATA_DIR env var — the smoke test uses that so it
never pollutes your real content. Brand and config files always live in
the repo.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
load_dotenv(ENV_FILE)

BRAND_DIR = ROOT / "brand"
CONFIG_DIR = ROOT / "config"
SOURCES_FILE = CONFIG_DIR / "sources.yaml"
DASHBOARD_DIR = ROOT / "dashboard"

DRAFT_ONLY = "draft_only"
APPROVED_POSTING = "approved_posting"
VALID_MODES = (DRAFT_ONLY, APPROVED_POSTING)

# Names of env vars that hold secrets. Their VALUES must never appear in
# logs or in the dashboard. Only "set / not set" may be shown.
SECRET_KEYS = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "X_API_KEY",
    "X_API_SECRET",
    "X_ACCESS_TOKEN",
    "X_ACCESS_TOKEN_SECRET",
    "LINKEDIN_ACCESS_TOKEN",
    "SUBSTACK_PASSWORD",
)

# Non-secret settings the Connections page may read/write in .env.
SETTING_KEYS = (
    "SUBSTACK_EMAIL",
    "SUBSTACK_PUBLICATION_URL",
    "SUBSTACK_AUTO_PUBLISH",
    "LINKEDIN_AUTHOR_URN",
    "X_HANDLE",
)


def data_home() -> Path:
    return Path(os.environ.get("MB_DATA_DIR", str(ROOT)))


def research_dir() -> Path:
    return data_home() / "research"


def drafts_dir() -> Path:
    return data_home() / "drafts"


def approved_dir() -> Path:
    return data_home() / "approved"


def posted_dir() -> Path:
    return data_home() / "posted"


def memory_dir() -> Path:
    return data_home() / "memory"


def rejected_dir() -> Path:
    return memory_dir() / "rejected"


def runs_log_file() -> Path:
    return memory_dir() / "runs.log"


def data_dirs() -> list[Path]:
    return [
        research_dir(),
        drafts_dir(),
        approved_dir(),
        posted_dir(),
        memory_dir(),
        rejected_dir(),
    ]


def ensure_data_dirs() -> None:
    for d in data_dirs():
        d.mkdir(parents=True, exist_ok=True)


def bot_mode() -> str:
    """Current mode. Anything unrecognized falls back to draft_only."""
    mode = os.environ.get("BOT_MODE", DRAFT_ONLY).strip()
    return mode if mode in VALID_MODES else DRAFT_ONLY


def brand_name() -> str:
    return os.environ.get("BRAND_NAME", "masterbuilder.ai")


def timezone_name() -> str:
    return os.environ.get("TIMEZONE", "America/New_York")


def openai_key_set() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY", "").strip())


def secret_status() -> dict:
    """True/False per secret. Never returns the values themselves."""
    return {k: bool(os.environ.get(k, "").strip()) for k in SECRET_KEYS}


def set_env_key(key: str, value: str) -> None:
    """Rewrite one KEY=value line in .env (creating it if missing).

    Only known keys may be written — BOT_MODE, secrets, and settings —
    so the dashboard can never scribble arbitrary lines into .env.
    Only that one line is touched; everything else stays exactly as it is.
    """
    allowed = ("BOT_MODE",) + SECRET_KEYS + SETTING_KEYS
    if key not in allowed:
        raise ValueError(f"refusing to write unknown env key: {key!r}")
    value = value.strip()
    if "\n" in value:
        raise ValueError(f"invalid value for {key}: newlines not allowed")

    lines: list[str] = []
    if ENV_FILE.exists():
        lines = ENV_FILE.read_text().splitlines()

    replaced = False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            replaced = True
            break
    if not replaced:
        lines.append(f"{key}={value}")

    ENV_FILE.write_text("\n".join(lines) + "\n")
    os.environ[key] = value


def set_bot_mode(mode: str) -> None:
    """Rewrite BOT_MODE in .env (creating the line if missing)."""
    if mode not in VALID_MODES:
        raise ValueError(f"invalid mode: {mode!r} (valid: {VALID_MODES})")
    set_env_key("BOT_MODE", mode)
