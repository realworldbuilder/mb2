"""Approved page: dry-run check, then live posting to the item's platform.

Live posting only works when BOT_MODE=approved_posting AND the platform's
keys are set on the Connections page. Everything goes over the safety
rails; a failed post stays in approved/ so you can retry.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _shared import mode_banner  # noqa: E402

import streamlit as st  # noqa: E402

from masterbuilder_bot import config, posting, publishers, review, safety, storage  # noqa: E402

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
st.code(preview["text"][:1500] or "(empty)", language=None)
st.caption(f"Sources: {len(preview['sources'])}")

# ---- destination ---------------------------------------------------------------
default_platform = preview["platform"]
plat_status = publishers.status()

if default_platform is None:
    st.info(f"`{preview['type']}` is internal content (a visual brief) — it has no "
            "publish destination. Use the text wherever you make the visual.")
    st.stop()

options = list(publishers.PLATFORMS)
platform = st.selectbox(
    "Destination", options, index=options.index(default_platform),
    format_func=lambda p: plat_status[p]["label"]
              + ("" if plat_status[p]["configured"] else " — ⚠️ not connected"),
)
if not plat_status[platform]["configured"]:
    st.warning(f"**{plat_status[platform]['label']} isn't connected yet.** "
               f"Missing: `{', '.join(plat_status[platform]['missing'])}` — "
               "add them on the **Connections** page.")
if platform == "substack":
    st.caption("Substack posting creates a **draft on Substack** — you review the "
               "email preview there and hit Publish yourself. (Set "
               "SUBSTACK_AUTO_PUBLISH=true on Connections to skip that gate.)")

st.divider()
c1, c2 = st.columns(2)

# ---- dry run --------------------------------------------------------------------
if c1.button("🛫 Dry-run all safety checks", use_container_width=True):
    result = posting.dry_run_post(path, platform)
    for check, status in result["checks"].items():
        (st.success if status == "ok" else st.error)(f"{check}: {status}")
    if result["would_post"]:
        st.info("All checks passed. Nothing was posted — use the live button when ready.")
    st.session_state[f"dryrun-ok-{path}"] = result["would_post"]

# ---- live post (two-step: button arms, checkbox confirms) ------------------------
live_ready = (config.bot_mode() == config.APPROVED_POSTING
              and plat_status[platform]["configured"])
confirm = c2.checkbox(f"Yes, really post this to {plat_status[platform]['label']}",
                      key=f"confirm-{path}")
if c2.button(f"🚀 POST LIVE to {plat_status[platform]['label']}",
             type="primary", use_container_width=True,
             disabled=not (live_ready and confirm)):
    try:
        with st.spinner(f"Posting to {plat_status[platform]['label']}..."):
            result = posting.post_live(path, platform)
        if result.get("posted"):
            st.success(f"**Posted.** {result.get('detail', '')}")
            if result.get("url"):
                st.markdown(f"➡️ [Open the post]({result['url']})")
            st.balloons()
            st.rerun()
        else:
            st.error(f"Publish failed (file stays in approved/, retry anytime): "
                     f"{result.get('detail', 'unknown error')}")
    except safety.SafetyError as e:
        st.error(f"Blocked by safety rails: {e}")
if not live_ready:
    c2.caption("Live posting needs BOT_MODE=approved_posting (Settings) and the "
               "platform connected (Connections).")
