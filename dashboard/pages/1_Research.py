"""Research page: browse the day's research, mark items, regenerate drafts."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _shared import mode_banner  # noqa: E402

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from masterbuilder_bot import storage  # noqa: E402
from masterbuilder_bot.drafting import generate_drafts  # noqa: E402
from masterbuilder_bot.models import RESEARCH_STATUSES  # noqa: E402

st.set_page_config(page_title="Research — Masterbuilder", page_icon="🔍", layout="wide")
st.title("🔍 Research")
mode_banner()

days = storage.research_days()
if not days:
    st.info("No research yet. Run it from the Command Center home page, or: "
            "`python scripts/daily_research.py`")
    st.stop()

day = st.selectbox("Day", days, index=0)
items = storage.load_research(day)
if not items:
    st.info(f"research/{day}.json is empty.")
    st.stop()

# ---- filters -----------------------------------------------------------------
all_tags = sorted({t for i in items for t in i.tags})
all_sources = sorted({i.source for i in items})
f1, f2 = st.columns(2)
tag_filter = f1.multiselect("Filter by tag", all_tags)
source_filter = f2.multiselect("Filter by source", all_sources)

shown = [i for i in items
         if (not tag_filter or set(i.tags) & set(tag_filter))
         and (not source_filter or i.source in source_filter)]
st.caption(f"{len(shown)} of {len(items)} items")

# ---- editable table ----------------------------------------------------------
df = pd.DataFrame([{
    "title": i.title,
    "source": i.source,
    "tags": ", ".join(i.tags),
    "why_it_matters_to_builders": i.why_it_matters_to_builders,
    "url": i.url,
    "status": i.status,
} for i in shown])

edited = st.data_editor(
    df,
    use_container_width=True,
    hide_index=True,
    disabled=["title", "source", "tags", "why_it_matters_to_builders", "url"],
    column_config={
        "status": st.column_config.SelectboxColumn(
            "status", options=list(RESEARCH_STATUSES),
            help="useful / maybe / ignore — saved back into the JSON"),
        "url": st.column_config.LinkColumn("url"),
    },
)

c1, c2 = st.columns(2)
if c1.button("💾 Save marks", use_container_width=True):
    changes = {row["url"]: row["status"] for _, row in edited.iterrows()}
    n = storage.update_research_statuses(day, changes)
    st.success(f"Saved — {n} item(s) updated in research/{day}.json.")

if c2.button("✍️ Regenerate drafts from this research", use_container_width=True,
             help="Items marked 'useful' get picked first; 'ignore' is skipped."):
    changes = {row["url"]: row["status"] for _, row in edited.iterrows()}
    storage.update_research_statuses(day, changes)  # save marks first
    with st.spinner("Drafting..."):
        paths, engine = generate_drafts(day)
    st.success(f"{len(paths)} drafts regenerated for {day} (engine: {engine}). "
               "See the Drafts page.")
