"""Connections page: hook up X, LinkedIn, and Substack.

Paste keys here — they're written to .env on the Mac mini and never
displayed again (only 'set / not set'). Each platform has a Test button
that makes one cheap API call to prove the keys work.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _shared import mode_banner  # noqa: E402

import streamlit as st  # noqa: E402

from masterbuilder_bot import config, publishers  # noqa: E402

st.set_page_config(page_title="Connections — Masterbuilder", page_icon="🔌", layout="wide")
st.title("🔌 Connections")
st.caption("Paste keys once. They live in .env on the Mac mini, are never shown "
           "again, and never appear in logs.")
mode_banner()

status = publishers.status()


def key_field(env_key: str, label: str, is_secret: bool = True) -> None:
    """One paste-in field. Shows set/not-set, writes .env on save."""
    is_set = bool(os.environ.get(env_key, "").strip())
    cols = st.columns([3, 1])
    value = cols[0].text_input(
        f"{label} {'✅' if is_set else '❌'}",
        type="password" if is_secret else "default",
        key=f"in-{env_key}",
        placeholder="(already set — paste to replace)" if is_set else "paste here",
    )
    if cols[1].button("Save", key=f"save-{env_key}", use_container_width=True):
        if value.strip():
            config.set_env_key(env_key, value.strip())
            st.success(f"{env_key} saved to .env")
            st.rerun()
        else:
            st.warning("Nothing to save — the field is empty.")


def test_button(platform: str) -> None:
    if st.button(f"🧪 Test {status[platform]['label']} connection",
                 key=f"test-{platform}"):
        with st.spinner("Testing..."):
            result = publishers.get(platform).test()
        (st.success if result["ok"] else st.error)(result["detail"])


# ============================ X ====================================
st.header(("✅ " if status["x"]["configured"] else "❌ ") + "X (Twitter)")
with st.expander("How to get the 4 keys (~10 minutes, free)",
                 expanded=not status["x"]["configured"]):
    st.markdown("""
1. Go to **[developer.x.com](https://developer.x.com)** → sign in with the **@masterbuilder_ai** account → sign up for the **Free** tier.
2. In the developer portal, open your **Project → App → Settings → User authentication settings** → **Set up**: choose **Read and write** permissions, type **Web App**, and put `https://masterbuilder.ai` as the website / callback URL. Save.
3. Go to the app's **Keys and tokens** tab:
   - **API Key and Secret** → Generate → paste both below.
   - **Access Token and Secret** → Generate (it must say *"Created with Read and Write permissions"* — if not, regenerate after step 2) → paste both below.
4. Hit **Test** below. Done — the free tier covers ~500 posts/month; the bot caps itself at 5/day anyway.
""")
key_field("X_API_KEY", "API Key")
key_field("X_API_SECRET", "API Key Secret")
key_field("X_ACCESS_TOKEN", "Access Token")
key_field("X_ACCESS_TOKEN_SECRET", "Access Token Secret")
key_field("X_HANDLE", "Your handle (for post links, e.g. masterbuilder_ai)", is_secret=False)
test_button("x")

st.divider()

# ============================ LinkedIn =============================
st.header(("✅ " if status["linkedin"]["configured"] else "❌ ") + "LinkedIn")
with st.expander("How to get the token (~10 minutes, free)",
                 expanded=not status["linkedin"]["configured"]):
    st.markdown("""
1. Go to **[linkedin.com/developers](https://www.linkedin.com/developers/)** → **Create app** (name: *Masterbuilder*, attach it to your LinkedIn page — create a company page for masterbuilder.ai first if you don't have one; verify the app from the app's Settings tab).
2. In the app, open the **Products** tab → request **"Share on LinkedIn"** and **"Sign In with LinkedIn using OpenID Connect"** (both approve instantly).
3. Open the **Auth** tab → under *OAuth 2.0 tools* on the right, click **Token generator** → select scopes **openid, profile, w_member_social** → **Request access token** → approve → copy the token and paste it below.
4. Hit **Test**. ⚠️ LinkedIn tokens expire after **60 days** — when LinkedIn posting starts failing, redo step 3 (2 minutes).
""")
key_field("LINKEDIN_ACCESS_TOKEN", "Access Token")
test_button("linkedin")

st.divider()

# ============================ Substack =============================
st.header(("✅ " if status["substack"]["configured"] else "❌ ") + "Substack")
with st.expander("How to connect (~3 minutes)",
                 expanded=not status["substack"]["configured"]):
    st.markdown("""
1. If you don't have the publication yet: **[substack.com](https://substack.com)** → create one (e.g. *masterbuilder.substack.com*).
2. Your Substack login must be **email + password** (if you always used the emailed magic link: Substack → Settings → set a password).
3. Paste email, password, and the publication URL below, then hit **Test**.

Substack has no official API, so the bot logs in as you (community library). By default it only creates **drafts** on Substack — you press Publish there after a last look at the email preview. That's on purpose: essays email real subscribers.
""")
key_field("SUBSTACK_EMAIL", "Substack login email", is_secret=False)
key_field("SUBSTACK_PASSWORD", "Substack password")
key_field("SUBSTACK_PUBLICATION_URL",
          "Publication URL (e.g. https://masterbuilder.substack.com)", is_secret=False)
test_button("substack")

st.divider()
st.caption("After all three test green: Settings page → flip BOT_MODE to "
           "approved_posting → the Approved page grows live-post buttons. "
           "Approval-first never changes: nothing posts without your click.")
