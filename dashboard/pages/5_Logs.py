"""Logs page: memory/runs.log, newest first, filterable by category."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _shared import mode_banner  # noqa: E402

import streamlit as st  # noqa: E402

from masterbuilder_bot.logging_utils import CATEGORIES, read_log_lines  # noqa: E402

st.set_page_config(page_title="Logs — Masterbuilder", page_icon="📜", layout="wide")
st.title("📜 Logs")
mode_banner()

c1, c2 = st.columns([3, 1])
selected = c1.multiselect("Filter by category", list(CATEGORIES),
                          help="research / drafting / review / posting / error / ...")
if c2.button("🔄 Refresh", use_container_width=True):
    st.rerun()

lines = read_log_lines(newest_first=True)
if selected:
    lines = [ln for ln in lines if any(f"[{cat}]" in ln for cat in selected)]

st.caption(f"{len(lines)} log lines (newest first) — memory/runs.log")
if not lines:
    st.info("No log entries yet. Run the pipeline and come back.")
else:
    st.code("\n".join(lines[:500]), language=None)
    if len(lines) > 500:
        st.caption(f"Showing the newest 500 of {len(lines)} lines.")
