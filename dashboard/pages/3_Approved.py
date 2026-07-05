"""Approved page: dry-run posting preview. NEVER posts live in this version."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _shared import mode_banner  # noqa: E402

import streamlit as st  # noqa: E402

from masterbuilder_bot import config, posting, review, storage  # noqa: E402

st.set_page_config(page_title="Approved — Masterbuilder", page_icon="✅", layout="wide")
st.title("✅ Approved")
mode_banner()

if config.bot_mode() != config.APPROVED_POSTING:
    st.error("**Posting is disabled.** BOT_MODE is not `approved_posting` — every "
             "post attempt will be blocked by the safety rails. This is the safe "
             "default. Change it on the Settings page only when you're ready.")

approved = storage.list_approved()
if not approved:
    st.info("Nothing approved yet. Approve drafts on the Drafts page or in the CLI "
            "review queue.")
    st.stop()

summaries = [review.draft_summary(p) for p in approved]
labels = [f"{s['day']} · {s['type']} · {s['title']}" for s in summaries]
idx = st.selectbox("Approved item", range(len(labels)), format_func=lambda i: labels[i])
path = Path(summaries[idx]["path"])

preview = posting.build_preview(path)
st.subheader("Post preview")
st.code(preview["text"][:1000] or "(empty)", language=None)
st.caption(f"Sources: {len(preview['sources'])}")

st.divider()
st.subheader("Dry-run posting check")
st.caption("Runs every safety check a real post would run. Posts nothing — live "
           "X posting is a stub until you explicitly ask for it to be implemented.")

if st.button("🛫 Post to X (dry-run only)", type="primary"):
    result = posting.dry_run_post(path)
    for check, status in result["checks"].items():
        (st.success if status == "ok" else st.error)(f"{check}: {status}")
    if result["would_post"]:
        st.info("All checks passed. **Nothing was posted** — this version never "
                "posts live.")
    else:
        st.warning("This item would be blocked from posting.")
