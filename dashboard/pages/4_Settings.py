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
    new_mode = st.radio("Mode", [config.DRAFT_ONLY, config.APPROVED_POSTING],
                        index=0 if config.bot_mode() == config.DRAFT_ONLY else 1,
                        help="draft_only: the bot can never post. approved_posting: "
                             "posting checks are armed (live posting is still a "
                             "dry-run stub in this version).")

    if new_mode == config.APPROVED_POSTING and config.bot_mode() != new_mode:
        confirmed = st.checkbox(
            "I understand this arms the posting pipeline. Only approved/ content "
            "can ever be posted, and live posting stays a dry-run stub until I "
            "explicitly ask for it — but I'm choosing this deliberately.")
    else:
        confirmed = True

    if st.button("Apply mode", type="primary"):
        if new_mode == config.APPROVED_POSTING and not confirmed:
            st.error("Check the confirmation box first.")
        else:
            config.set_bot_mode(new_mode)
            log("setup", f"dashboard set BOT_MODE={new_mode}")
            st.success(f"BOT_MODE set to {new_mode} (written to .env).")
            st.rerun()
