"""Masterbuilder Command Center — home page.

Run via: python scripts/run_dashboard.py  (localhost only)
"""

import streamlit as st

from _shared import mode_banner  # noqa: I001 — bootstraps sys.path first

from masterbuilder_bot import config, storage
from masterbuilder_bot.drafting import generate_drafts
from masterbuilder_bot.llm import llm_status
from masterbuilder_bot.logging_utils import read_log_lines
from masterbuilder_bot.research import run_daily_research

st.set_page_config(page_title="Masterbuilder Command Center", page_icon="🧱",
                   layout="wide")

st.title("🧱 Masterbuilder Command Center")
st.caption("boots and bits · draft first, approval second, posting last")
mode_banner()

# ---- status cards -----------------------------------------------------------
day = storage.today()
research_items = storage.load_research(day)
drafts = storage.list_drafts(day)
approved = storage.list_approved()

last_research = "never"
for line in read_log_lines():
    if "[research]" in line and "saved" in line:
        last_research = line.split(" ")[0]
        break

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Last research run", last_research.split("T")[-1] if "T" in last_research else last_research,
          last_research.split("T")[0] if "T" in last_research else None)
c2.metric("Research items today", len(research_items))
c3.metric("Drafts today", len(drafts))
c4.metric("Approved (all time)", len(approved))
c5.metric("BOT_MODE", config.bot_mode())

llm = llm_status()
st.caption(f"LLM: **{llm['provider']}** · model: `{llm['model']}`"
           + (f" · base_url: `{llm['base_url']}`" if llm["base_url"] != "-" else ""))

st.divider()

# ---- big buttons -------------------------------------------------------------
st.subheader("Run the bot")
b1, b2, b3, b4 = st.columns(4)

if b1.button("🔍 Run Daily Research", use_container_width=True):
    with st.spinner("Pulling sources... (can take a minute)"):
        items, errors = run_daily_research()
    st.success(f"{len(items)} research items saved.")
    if errors:
        st.warning(f"{len(errors)} sources failed (run continued): "
                   + "; ".join(errors[:3]))
    st.rerun()

if b2.button("✍️ Generate Drafts", use_container_width=True):
    with st.spinner("Drafting..."):
        paths, engine = generate_drafts()
    st.success(f"{len(paths)} drafts generated (engine: {engine}).")
    st.rerun()

if b3.button("🚀 Run Full Daily Pipeline", use_container_width=True):
    with st.spinner("Research + drafting..."):
        items, errors = run_daily_research()
        paths, engine = generate_drafts()
    st.success(f"{len(items)} research items → {len(paths)} drafts (engine: {engine}). "
               "Nothing approved, nothing posted.")
    st.rerun()

if b4.button("📋 Open Review Queue", use_container_width=True):
    st.switch_page("pages/2_Drafts.py")

st.divider()
st.caption("Pages: **Research** (mark useful/ignore) · **Drafts** (edit/approve/reject) · "
           "**Approved** (dry-run preview) · **Settings** (brand + sources + mode) · "
           "**Logs** (runs.log)")
