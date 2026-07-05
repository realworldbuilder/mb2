"""Performance page: what's working, what the bot has learned.

Three sections: engagement numbers per posted item, the feedback tally
from your reviews, and the current voice lessons (with a rebuild button).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _shared import mode_banner  # noqa: E402

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from masterbuilder_bot import feedback, learning, metrics  # noqa: E402
from masterbuilder_bot.publishers import x  # noqa: E402

st.set_page_config(page_title="Performance — Masterbuilder", page_icon="📈", layout="wide")
st.title("📈 Performance & Learning")
st.caption("The loop: you review → audience reacts → lessons update → "
           "tomorrow's drafts get better.")
mode_banner()

# ---- engagement ----------------------------------------------------------------
st.header("What the audience did")
rows = metrics.ranked()
if rows:
    df = pd.DataFrame(rows)[["day", "type", "score", "impressions", "likes",
                             "retweets", "replies", "bookmarks", "body_head"]]
    df = df.rename(columns={"body_head": "post"})
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.info("No engagement data yet — it appears after posts go live on X. "
            "(Metrics are pulled automatically once a day, or right now with "
            "the button below.)")

if st.button("🔄 Pull fresh X metrics now"):
    with st.spinner("Fetching (one batched API call)..."):
        result = metrics.collect()
    if result["updated"]:
        st.success(f"Updated {result['updated']} of {result['tracked']} tracked posts.")
        st.rerun()
    else:
        st.warning(f"Nothing updated — {result['detail']}.")
if not x.is_configured():
    st.caption("⚠️ X isn't connected yet (Connections page), so metrics can't be pulled.")

st.divider()

# ---- feedback tally ---------------------------------------------------------------
st.header("What you told it")
tallies = feedback.counts()
c1, c2, c3 = st.columns(3)
c1.metric("Approved", tallies["approved"])
c2.metric("Rejected", tallies["rejected"])
c3.metric("Edited", tallies["edited"])
if tallies["reasons"]:
    st.caption("Your most common reasons:")
    top = sorted(tallies["reasons"].items(), key=lambda kv: -kv[1])[:12]
    st.dataframe(pd.DataFrame(top, columns=["reason", "times"]),
                 hide_index=True)
else:
    st.caption("No reasons logged yet — the optional 'Why?' field on the Drafts "
               "page is what feeds this. Even one word helps.")

st.divider()

# ---- voice lessons ---------------------------------------------------------------
st.header("What it learned (voice lessons)")
st.caption("Injected into every drafting prompt. Rebuilds automatically after "
           "each daily run; rebuild manually after a review session to apply "
           "your feedback immediately.")
if st.button("🧠 Rebuild voice lessons now", type="primary"):
    with st.spinner("Distilling your feedback + engagement into lessons..."):
        learning.rebuild()
    st.success("Voice lessons updated — next drafts will use them.")
    st.rerun()

lessons = learning.load_lessons()
if lessons:
    st.markdown(lessons)
else:
    st.info("No lessons yet. They appear once you've approved/rejected a few "
            "drafts or posts have engagement numbers.")
