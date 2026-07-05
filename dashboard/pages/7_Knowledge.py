"""Knowledge page: the growing Masterbuilder directory.

Every company, tool, material, and player the research runs across —
auto-mined daily, browsable here, and stored as markdown+frontmatter
ready to become the directory section of masterbuilder.ai.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _shared import mode_banner  # noqa: E402

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from masterbuilder_bot import storage  # noqa: E402
from masterbuilder_bot.knowledge import (  # noqa: E402
    ENTITY_TYPES, build_from_research, knowledge_dir, list_entities, load_entity,
    reverify_all,
)

st.set_page_config(page_title="Knowledge — Masterbuilder", page_icon="📚", layout="wide")
st.title("📚 Knowledge Base")
st.caption("The Masterbuilder directory — every company, tool, material, and player "
           "the research crosses paths with. Grows automatically every morning.")
mode_banner()

all_entities = list_entities()
verified_count = sum(1 for e in all_entities if e["verified"])

# ---- stats ----------------------------------------------------------------------
today = storage.today()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Verified (in directory)", verified_count)
c2.metric("Unverified (quarantine)", len(all_entities) - verified_count)
c3.metric("Added today", sum(1 for e in all_entities if e["first_seen"] == today))
c4.metric("Types", len({e["type"] for e in all_entities}))

st.caption("Only **verified** entities — working official link, name confirmed on "
           "the page — get published to the masterbuilder.ai directory. Everything "
           "else waits in quarantine until a future mention verifies it.")

col_a, col_b = st.columns(2)
with col_a:
    with st.expander("⛏️ Mine today's research again"):
        st.caption("Re-runs entity extraction over today's research JSON. Your "
                   "notes in entity files are never touched.")
        if st.button("Mine today's research"):
            with st.spinner("Extracting + verifying with the local model — takes a few minutes..."):
                new, updated = build_from_research()
            st.success(f"{new} new, {updated} updated.")
            st.rerun()
with col_b:
    with st.expander("🔗 Re-verify all links"):
        st.caption("Re-checks every entity's link (and hunts for missing ones). "
                   "Dead links get demoted to quarantine.")
        if st.button("Re-verify everything"):
            with st.spinner("Checking links..."):
                ok, total = reverify_all()
            st.success(f"{ok}/{total} entities verified.")
            st.rerun()

show_quarantine = st.toggle("Show unverified (quarantine)", value=False)
entities = all_entities if show_quarantine else [e for e in all_entities if e["verified"]]

if not entities:
    st.info("No entities yet. They get mined automatically during the daily run, "
            "or use the button above.")
    st.stop()

st.divider()

# ---- browse ----------------------------------------------------------------------
f1, f2 = st.columns([2, 2])
query = f1.text_input("Search", placeholder="name or summary...")
type_filter = f2.multiselect("Type", sorted({e["type"] for e in entities}))

shown = [e for e in entities
         if (not type_filter or e["type"] in type_filter)
         and (not query or query.lower() in (e["name"] + " " + e["summary"]).lower())]
st.caption(f"{len(shown)} of {len(entities)} entities")

df = pd.DataFrame([{
    "name": e["name"], "verified": "✅" if e["verified"] else "—",
    "type": e["type"], "summary": e["summary"],
    "mentions": e["mention_count"], "first seen": e["first_seen"],
    "last seen": e["last_seen"], "url": e["url"],
} for e in shown])
st.dataframe(df, use_container_width=True, hide_index=True,
             column_config={"url": st.column_config.LinkColumn("url")})

st.divider()

# ---- entity detail ------------------------------------------------------------------
st.subheader("Entity detail")
slugs = {f"{e['name']} ({e['type']})": e["slug"] for e in shown}
if slugs:
    picked = st.selectbox("Open an entity", list(slugs.keys()))
    post = load_entity(slugs[picked])
    if post:
        left, right = st.columns([2, 3])
        with left:
            st.markdown(f"### {post.get('name')}")
            st.markdown(f"**Type:** {post.get('type')}  \n"
                        f"**Summary:** {post.get('summary') or '—'}  \n"
                        f"**Site:** {post.get('url') or '—'}  \n"
                        f"**First seen:** {post.get('first_seen')} · "
                        f"**Last seen:** {post.get('last_seen')} · "
                        f"**Mentions:** {post.get('mention_count')}")
            notes = st.text_area("Your notes (saved into the entity file — the bot "
                                 "never overwrites this)", post.content, height=180)
            if st.button("💾 Save notes"):
                post.content = notes
                import frontmatter as fm
                Path(knowledge_dir() / f"{slugs[picked]}.md").write_text(
                    fm.dumps(post), encoding="utf-8")
                st.success("Saved.")
        with right:
            st.markdown("**Mentions (newest last):**")
            for m in (post.get("mentions") or []):
                st.markdown(f"- {m.get('date')} — [{m.get('title')}]({m.get('url')}) "
                            f"· *{m.get('source')}*")

st.divider()
st.caption(f"Stored as markdown + YAML frontmatter in `{knowledge_dir()}` — "
           "one file per entity, ready to publish as the masterbuilder.ai directory.")
