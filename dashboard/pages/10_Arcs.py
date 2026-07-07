"""Arcs page: the continuity ledgers — story arcs, receipts, records.

Read-mostly. Arcs open themselves when you approve a story, get matched
against fresh research every morning, and turn into UPDATE / receipt
drafts on their own. The only button here is "close arc" for stories
you're done tracking.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _shared import mode_banner  # noqa: E402

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from masterbuilder_bot import continuity, storage  # noqa: E402

st.set_page_config(page_title="Arcs — Masterbuilder", page_icon="🧵", layout="wide")
st.title("🧵 Story Arcs & Ledgers")
st.caption("The bot's cross-day memory: what it's tracking, which dated claims "
           "are on the clock, and which records stand. Arcs open automatically "
           "when you approve a story — followups and receipts draft themselves "
           "when the news moves.")
mode_banner()

arcs = continuity.load_arcs()
open_ = continuity.open_arcs(arcs)
receipts = [a for a in arcs if a.get("due_date")]
records = continuity.load_records()["records"]
today = storage.today()

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Open arcs", len(open_))
c2.metric("Receipts on the clock",
          sum(1 for a in receipts if a["status"] in ("open", "updated")))
c3.metric("Hits", sum(1 for a in receipts if a["status"] == "hit"))
c4.metric("Misses", sum(1 for a in receipts if a["status"] == "miss"))
c5.metric("Records tracked", len(records))

if not arcs and not records:
    st.info("Nothing tracked yet. Approve a story draft and the bot opens an arc "
            "for it — from then on it watches the research for developments.")
    st.stop()

st.divider()

# ---- open arcs -------------------------------------------------------------------
st.subheader("Open arcs — what the bot is watching")
if open_:
    df = pd.DataFrame([{
        "opened": a["opened"],
        "story": a["title"],
        "watching for": a.get("watch_for", ""),
        "due": a.get("due_date") or "—",
        "updates": len(a.get("updates", [])),
        "status": a["status"],
    } for a in sorted(open_, key=lambda x: x["opened"], reverse=True)])
    st.dataframe(df, use_container_width=True, hide_index=True)

    with st.expander("🔍 Arc detail / close an arc"):
        titles = {f"{a['opened']} — {a['title']}": a["id"] for a in open_}
        picked = st.selectbox("Arc", list(titles.keys()))
        arc = next(a for a in open_ if a["id"] == titles[picked])
        st.markdown(f"**Watching for:** {arc.get('watch_for', '—')}  \n"
                    f"**Claim:** {arc.get('claim') or '—'}"
                    + (f" (due {arc['due_date']})" if arc.get("due_date") else ""))
        if arc.get("origin_head"):
            st.markdown(f"> {arc['origin_head']}")
        for u in arc.get("updates", []):
            st.markdown(f"- {u['date']} — {u.get('note', '')} "
                        + (f"[link]({u['url']})" if u.get("url") else ""))
        if st.button("Close this arc (stop tracking)"):
            continuity.close_arc(arc["id"])
            st.success("Closed.")
            st.rerun()
else:
    st.caption("No open arcs. Approve a story and one opens itself.")

# ---- receipts --------------------------------------------------------------------
st.divider()
st.subheader("Receipts — dated claims, graded by the calendar")
if receipts:
    df = pd.DataFrame([{
        "claim": (a.get("claim") or a["title"])[:120],
        "said on": a["opened"],
        "due": a["due_date"],
        "outcome": {"open": "⏳ pending", "updated": "⏳ pending",
                    "hit": "✅ hit", "miss": "❌ miss",
                    "no_news": "🤷 due, no word", "closed": "closed"
                    }.get(a["status"], a["status"]),
    } for a in sorted(receipts, key=lambda x: x["due_date"])])
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.caption("No dated claims on file yet. When a source puts a date on a "
               "promise, the bot writes it down here.")

# ---- records ---------------------------------------------------------------------
st.divider()
st.subheader("The record set")
if records:
    df = pd.DataFrame([{
        "record": r["label"],
        "mark": f"{r['value']} {r['unit']}",
        "holder": r.get("holder", ""),
        "set": r["date"],
        "previous": (f"{r['previous'].get('value')} {r['previous'].get('unit', '')} — "
                     f"{r['previous'].get('holder', '')}"
                     if r.get("previous") else "first on the books"),
        "source": r.get("source_url", ""),
    } for r in sorted(records.values(), key=lambda x: x["date"], reverse=True)])
    st.dataframe(df, use_container_width=True, hide_index=True,
                 column_config={"source": st.column_config.LinkColumn("source")})
else:
    st.caption("The record book is open — marks get logged as the research "
               "turns them up, and broken records keep their history.")

st.divider()
st.caption(f"Ledgers live in `{continuity.arcs_file()}` and "
           f"`{continuity.records_file()}` — plain JSON, yours to edit. "
           f"Today is {today}; the morning run does the matching and grading.")
