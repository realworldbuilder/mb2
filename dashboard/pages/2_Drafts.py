"""Drafts page: view, edit, approve, reject."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _shared import mode_banner  # noqa: E402

import streamlit as st  # noqa: E402

from masterbuilder_bot import feedback, media, review, storage  # noqa: E402

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

# ---- image (attaches to tweet 1) ------------------------------------------------
candidates = [c for c in (post.get("media_candidates") or []) if c]
if candidates:
    st.caption("Image — attaches to the first tweet. Source photos need a "
               "rights sanity-check (gov sources are public domain).")
    cols = st.columns(len(candidates))
    for c, col in zip(candidates, cols):
        img_path = media.resolve(c)
        if img_path.exists():
            label = "source photo" if c.endswith("-source.jpg") else "fact card"
            col.image(str(img_path), caption=label, use_container_width=True)
    options = candidates + [""]
    labels_map = {c: ("source photo" if c.endswith("-source.jpg") else "fact card")
                  for c in candidates} | {"": "no image"}
    current = post.get("media_choice", "") or ""
    choice = st.radio("Attach", options,
                      index=options.index(current) if current in options else len(options) - 1,
                      format_func=lambda o: labels_map[o],
                      horizontal=True, key=f"media-{selected['path']}")
    if choice != current:
        post["media_choice"] = choice
        storage.save_post(path, post)

# ---- edit ----------------------------------------------------------------------
body = st.text_area("Draft body (Markdown)", post.content, height=400,
                    key=f"body-{selected['path']}")

# ---- feedback (optional, teaches the voice) ------------------------------------
tags = st.multiselect(
    "Why? (optional — every reason makes tomorrow's drafts better)",
    feedback.APPROVE_TAGS + feedback.REJECT_TAGS,
    key=f"tags-{selected['path']}",
)
note = st.text_input("Or say it your way", key=f"note-{selected['path']}",
                     placeholder="e.g. hook is weak, bury the company name, more numbers")
reason = "; ".join(tags + ([note.strip()] if note.strip() else []))

e1, e2, e3 = st.columns(3)
if e1.button("💾 Save changes", use_container_width=True):
    review.save_edit(path, body)
    st.success("Saved. (Your edits teach the voice too.)")

if e2.button("✅ Approve", use_container_width=True, type="primary"):
    review.save_edit(path, body)  # keep any unsaved edits
    dest = review.approve(path, reason=reason)
    st.success(f"Approved → {dest.parent.name}/{dest.name}")
    st.rerun()

if e3.button("🗑️ Reject", use_container_width=True):
    dest = review.reject(path, reason=reason)
    st.info(f"Rejected → memory/rejected/{dest.parent.name}/{dest.name}")
    st.rerun()

st.divider()
with st.expander("Preview rendered Markdown"):
    st.markdown(body)
