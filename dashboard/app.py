"""Masterbuilder Command Center — home page: the pipeline, as a drawing.

Run via: python scripts/run_dashboard.py  (localhost only)
"""

from datetime import date

import streamlit as st

from _shared import mode_banner  # noqa: I001 — bootstraps sys.path first

from masterbuilder_bot import config, learning, storage
from masterbuilder_bot.drafting import generate_drafts
from masterbuilder_bot.llm import llm_status
from masterbuilder_bot.logging_utils import read_log_lines
from masterbuilder_bot.research import run_daily_research

st.set_page_config(page_title="Masterbuilder Command Center", page_icon="🧱",
                   layout="wide")
mode_banner()

# ---- title block --------------------------------------------------------------
llm = llm_status()
st.markdown(f"""
<div class='mb-stamp'>backend<span>not for publication</span></div>
<div class='mb-head'>
  <div class='tb-main'>
    <h1>🧱 Masterbuilder Command Center</h1>
    <p>boots and bits · the working set behind the field manual</p>
  </div>
  <div class='tb-side'>
    <div><span class='lbl'>project</span>masterbuilder.ai</div>
    <div><span class='lbl'>sheet</span>WS-001</div>
    <div><span class='lbl'>issued</span>{date.today().isoformat()}</div>
    <div><span class='lbl'>engine</span>{llm['provider']} · {llm['model']}</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ---- the pipeline ---------------------------------------------------------------
day = storage.today()
research_items = storage.load_research(day)
drafts = storage.list_drafts(day)
pending = 0
for p in drafts:
    try:
        if storage.load_post(p).get("status", "draft") == "draft":
            pending += 1
    except Exception:  # noqa: BLE001
        pending += 1
approved = storage.list_approved()
posted = storage.list_posted()
ledger = learning.load_ledger()
takes = sum(1 for ln in ledger.splitlines() if ln.lstrip().startswith("- "))

last_research = "never"
for line in read_log_lines():
    if "[research]" in line and "saved" in line:
        last_research = line.split(" ")[0]
        break
research_sub = ("ran " + last_research.split("T")[-1][:5]
                if "T" in last_research else last_research)


def stage(num: str, name: str, val, sub: str, hot: bool = False) -> str:
    cls = "val hot" if hot else "val"
    return (f"<div class='mb-stage'><span class='num'>{num}</span>"
            f"<span class='name'>{name}</span>"
            f"<span class='{cls}'>{val}</span>"
            f"<span class='sub'>{sub}</span></div>")


st.markdown(
    "<div class='mb-pipe'>"
    + stage("01", "Research", len(research_items), research_sub)
    + "<div class='mb-arrow'>▸</div>"
    + stage("02", "Draft", len(drafts), "drafts today")
    + "<div class='mb-arrow'>▸</div>"
    + stage("03", "Review", pending, "await your call", hot=pending > 0)
    + "<div class='mb-arrow'>▸</div>"
    + stage("04", "Approved", len(approved), "ready to post")
    + "<div class='mb-arrow'>▸</div>"
    + stage("05", "Posted", len(posted), "live, all time")
    + "<div class='mb-arrow'>▸</div>"
    + stage("06", "Learn", takes, "takes on record")
    + "</div>",
    unsafe_allow_html=True,
)

# one link under each stage, aligned with the boxes above
l1, l2, l3, l4, l5, l6 = st.columns(6)
l1.page_link("pages/1_Research.py", label="open research", icon="🔍")
l2.page_link("pages/2_Drafts.py", label="open drafts", icon="✍️")
l3.page_link("pages/2_Drafts.py", label="review queue", icon="📋")
l4.page_link("pages/3_Approved.py", label="open approved", icon="🚀")
l5.page_link("pages/9_Performance.py", label="performance", icon="📈")
l6.page_link("pages/9_Performance.py", label="voice lessons", icon="🧠")

st.divider()

# ---- run the bot ----------------------------------------------------------------
st.subheader("Run the bot")
b1, b2, b3 = st.columns(3)

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

st.caption("the 6 AM run does all of this on its own — these buttons are for "
           "impatient mornings")
