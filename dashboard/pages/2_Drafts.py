"""Drafts page: view, edit, approve, reject."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _shared import mode_banner  # noqa: E402

import streamlit as st  # noqa: E402

from masterbuilder_bot import review, storage  # noqa: E402

st.set_page_config(page_title="Drafts — Masterbuilder", page_icon="✍️", layout="wide")
st.title("✍️ Drafts")
mode_banner()

drafts = storage.list_drafts()
if not drafts:
    st.info("No drafts waiting. Generate some from the Command Center home page.")
    st.stop()

summaries = [review.draft_summary(p) for p in drafts]
labels = [f"{s['day']} · {s['type']} · {s['title']}" for s in summaries]
idx = st.selectbox("Draft", range(len(labels)), format_func=lambda i: labels[i])
selected = summaries[idx]
path = Path(selected["path"])
post = storage.load_post(path)

# ---- scores + sources ---------------------------------------------------------
c1, c2, c3, c4 = st.columns(4)
c1.metric("Risk", selected["risk_score"])
c2.metric("Usefulness", selected["usefulness_score"])
c3.metric("Originality", selected["originality_score"])
c4.metric("Created", str(selected["created_at"]).split("T")[0])

if selected["sources"]:
    with st.expander(f"Sources ({len(selected['sources'])})", expanded=False):
        for url in selected["sources"]:
            st.markdown(f"- {url}")
else:
    st.warning("This draft has NO sources — it can never pass the posting safety check.")

# ---- edit ----------------------------------------------------------------------
body = st.text_area("Draft body (Markdown)", post.content, height=400,
                    key=f"body-{selected['path']}")

e1, e2, e3 = st.columns(3)
if e1.button("💾 Save changes", use_container_width=True):
    review.save_edit(path, body)
    st.success("Saved.")

if e2.button("✅ Approve", use_container_width=True, type="primary"):
    review.save_edit(path, body)  # keep any unsaved edits
    dest = review.approve(path)
    st.success(f"Approved → {dest.parent.name}/{dest.name}")
    st.rerun()

if e3.button("🗑️ Reject", use_container_width=True):
    dest = review.reject(path)
    st.info(f"Rejected → memory/rejected/{dest.parent.name}/{dest.name}")
    st.rerun()

st.divider()
with st.expander("Preview rendered Markdown"):
    st.markdown(body)
