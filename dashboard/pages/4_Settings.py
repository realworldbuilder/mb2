"""Settings page: edit brand files + sources, view env status, toggle BOT_MODE.

Never displays or logs secret values — only whether they're set.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _shared import mode_banner  # noqa: E402

import streamlit as st  # noqa: E402
import yaml  # noqa: E402

from masterbuilder_bot import config  # noqa: E402
from masterbuilder_bot.llm import llm_status  # noqa: E402
from masterbuilder_bot.logging_utils import log  # noqa: E402

st.set_page_config(page_title="Settings — Masterbuilder", page_icon="⚙️", layout="wide")
st.title("⚙️ Settings")
mode_banner()

# ---- editable files -----------------------------------------------------------
EDITABLE = {
    "brand/persona.md": config.BRAND_DIR / "persona.md",
    "brand/voice.md": config.BRAND_DIR / "voice.md",
    "brand/topics.md": config.BRAND_DIR / "topics.md",
    "brand/rules.md": config.BRAND_DIR / "rules.md",
    "config/sources.yaml": config.SOURCES_FILE,
}

tabs = st.tabs(list(EDITABLE.keys()) + ["Environment & mode"])

for tab, (label, path) in zip(tabs, EDITABLE.items()):
    with tab:
        content = path.read_text(encoding="utf-8") if path.exists() else ""
        new = st.text_area(label, content, height=420, key=f"edit-{label}")
        if st.button(f"💾 Save {label}", key=f"save-{label}"):
            if label.endswith(".yaml"):
                try:
                    yaml.safe_load(new)  # don't save broken YAML
                except yaml.YAMLError as e:
                    st.error(f"Invalid YAML — not saved: {e}")
                    st.stop()
            path.write_text(new, encoding="utf-8")
            log("setup", f"dashboard edited {label}")
            st.success(f"Saved {label}.")

# ---- env status + mode toggle ---------------------------------------------------
with tabs[-1]:
    st.subheader(".env status (values never shown)")
    for key, is_set in config.secret_status().items():
        st.markdown(f"- `{key}`: {'✅ set' if is_set else '⬜ not set'}")

    llm = llm_status()
    st.markdown(f"- LLM provider: **{llm['provider']}** · model: `{llm['model']}`")
    st.markdown(f"- Current BOT_MODE: **`{config.bot_mode()}`**")

    st.divider()
    st.subheader("Bot mode")
    modes = [config.DRAFT_ONLY, config.APPROVED_POSTING, config.AUTO_POSTING]
    new_mode = st.radio(
        "Mode", modes,
        index=modes.index(config.bot_mode()) if config.bot_mode() in modes else 0,
        help="draft_only: the bot can never post. approved_posting: you "
             "approve AND click post per item. auto_posting: the daily run "
             "approves and posts the day's X drafts itself (daily cap 5, "
             "risk-gated; essays and content ideas always wait for you).")

    if new_mode != config.DRAFT_ONLY and config.bot_mode() != new_mode:
        confirmed = st.checkbox(
            "I understand this arms LIVE posting to real accounts"
            + (" — including fully automatic daily posts to X with no click "
               "from me" if new_mode == config.AUTO_POSTING else "")
            + ". Only approved/ content can ever be posted, caps and content "
              "rails stay on, and I'm choosing this deliberately.")
    else:
        confirmed = True

    if st.button("Apply mode", type="primary"):
        if new_mode != config.DRAFT_ONLY and not confirmed:
            st.error("Check the confirmation box first.")
        else:
            config.set_bot_mode(new_mode)
            log("setup", f"dashboard set BOT_MODE={new_mode}")
            st.success(f"BOT_MODE set to {new_mode} (written to .env).")
            st.rerun()
