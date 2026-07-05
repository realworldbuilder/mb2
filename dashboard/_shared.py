"""Shared helpers for all dashboard pages: sys.path bootstrap + tiny utils."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from masterbuilder_bot import config  # noqa: E402


def mode_banner() -> None:
    """Shown on every page: makes the posting state impossible to miss."""
    if config.bot_mode() == config.APPROVED_POSTING:
        st.warning("BOT_MODE = approved_posting — posting checks are armed "
                   "(actual posting is still a dry-run stub in this version).")
    else:
        st.info("BOT_MODE = draft_only — posting is disabled. Boots and bits, "
                "drafts only.")
