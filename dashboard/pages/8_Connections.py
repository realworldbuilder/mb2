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

from masterbuilder_bot import config, llm, publishers  # noqa: E402

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


# ==================== Writing engine (Claude) ======================
_llm = llm.llm_status()
_on_claude = _llm["provider"] == "anthropic"
st.header(("✅ " if _on_claude else "🧠 ") + "Writing engine — Claude")
st.caption(f"Currently writing with: **{_llm['provider']} / {_llm['model']}**. "
           "This is the brain behind every draft — the single biggest "
           "quality upgrade is switching it from the local model to Claude.")
with st.expander("How to get an Anthropic API key (~3 minutes)",
                 expanded=not _on_claude):
    st.markdown("""
1. Go to **[console.anthropic.com](https://console.anthropic.com)** → sign in (create an account if needed).
2. **Settings → Billing** → add a card and a few dollars of credit — a full day of drafts costs pennies.
3. **Settings → API keys** → **Create key** → copy it (starts with `sk-ant-`).
4. Paste it below and hit **Save & switch to Claude**. Done — same persona, same rules, much better writer.
""")
_cols = st.columns([3, 1])
_key = _cols[0].text_input(
    f"Anthropic API key {'✅' if os.environ.get('ANTHROPIC_API_KEY', '').strip() else '❌'}",
    type="password", key="in-ANTHROPIC_API_KEY",
    placeholder="(already set — paste to replace)"
    if os.environ.get("ANTHROPIC_API_KEY", "").strip() else "sk-ant-...",
)
if _cols[1].button("Save & switch to Claude", key="save-anthropic",
                   use_container_width=True):
    if _key.strip():
        config.set_env_key("ANTHROPIC_API_KEY", _key.strip())
        config.set_env_key("LLM_PROVIDER", "anthropic")
        config.set_env_key("LLM_MODEL", "claude-sonnet-5")
        st.success("Saved — drafts now write with Claude (claude-sonnet-5).")
        st.rerun()
    else:
        st.warning("Nothing to save — the field is empty.")
_tc1, _tc2 = st.columns(2)
if _tc1.button("🧪 Test writing engine", key="test-llm"):
    with st.spinner("Asking the model for one sentence..."):
        out = llm.complete("You are the masterbuilder.ai drafting engine.",
                           "Reply with one short sentence proving you're alive.",
                           max_tokens=60)
    (st.success if out else st.error)(
        out or "No reply — check the key/provider (Logs page has details).")
if _on_claude and _tc2.button("↩️ Switch back to local model (free)", key="llm-local"):
    config.set_env_key("LLM_PROVIDER", "openai_compatible")
    config.set_env_key("LLM_MODEL", "qwen2.5:14b")
    st.success("Back on the local model (qwen2.5:14b via Ollama).")
    st.rerun()

st.divider()

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
st.header("⏸️ LinkedIn — off by choice")
st.caption("You decided not to auto-post to your personal profile "
           "(builder signals go to X as threads instead). Nothing routes "
           "here, so no keys are needed.")
with st.expander("If you ever change your mind"):
    st.markdown("""
The plumbing is still installed. Two ways back in:
- **Personal profile**: create an app at **[linkedin.com/developers](https://www.linkedin.com/developers/)**, request *Share on LinkedIn* + *Sign In with LinkedIn using OpenID Connect*, generate a token (scopes: openid, profile, w_member_social) and paste it below. ⚠️ tokens expire every 60 days.
- **Company page instead of you**: needs a masterbuilder.ai company page and LinkedIn's *Community Management API* approval (a form, takes days). Ask Claude to wire it when approved.
""")
    key_field("LINKEDIN_ACCESS_TOKEN", "Access Token (only if re-enabling)")
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
