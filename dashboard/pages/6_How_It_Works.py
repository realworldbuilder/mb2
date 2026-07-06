"""How It Works: a field manual for the bot itself.

Everything on this page is read live from the actual config — it can't
drift out of date.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _shared import mode_banner  # noqa: E402

import streamlit as st  # noqa: E402

from masterbuilder_bot import config, storage  # noqa: E402
from masterbuilder_bot.llm import llm_status  # noqa: E402
from masterbuilder_bot.models import DRAFT_PLAN  # noqa: E402
from masterbuilder_bot.research import enabled_sources, load_sources  # noqa: E402
from masterbuilder_bot.safety import MAX_POSTS_PER_DAY, MAX_POSTS_PER_RUN  # noqa: E402

st.set_page_config(page_title="How It Works — Masterbuilder", page_icon="🧭",
                   layout="wide")
st.title("🧭 How It Works")
st.caption("The field manual for the machine that writes the Field Manual.")
mode_banner()

# ---- live facts ---------------------------------------------------------------
data = load_sources()
sources = enabled_sources(data)
categories = sorted({s["category"] for s in sources})
llm = llm_status()
draft_count = sum(n for _, n in DRAFT_PLAN)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Enabled sources", len(sources), f"{len(categories)} beats")
c2.metric("Drafts per day", draft_count)
c3.metric("Writing engine", llm["provider"].split(" ")[0])
c4.metric("Daily run", "6:00 AM ET", "launchd on this Mac mini")

st.divider()

# ---- the pipeline ---------------------------------------------------------------
st.subheader("The pipeline — one loop, every morning")
st.code("""
 6:00 AM                                        you, with coffee
 ┌──────────┐    ┌──────────┐    ┌───────────┐    ┌──────────┐    ┌─────────┐
 │ RESEARCH │ →  │  DRAFT   │ →  │  REVIEW   │ →  │ APPROVED │ →  │ POSTED  │
 │ 19 feeds │    │ local AI │    │ (this     │    │ folder   │    │ (stub — │
 │ → 60     │    │ writes   │    │  dashboard│    │          │    │  never  │
 │ items    │    │ 10 drafts│    │  = you)   │    │          │    │  live)  │
 └──────────┘    └──────────┘    └─────┬─────┘    └──────────┘    └─────────┘
                                       │
                                       └→ rejected → memory/rejected/ (kept, never deleted)
""", language=None)

st.markdown(f"""
1. **Research** — the bot pulls RSS from **{len(sources)} sources** across
   **{len(categories)} beats** ({", ".join(c.replace("_", " ") for c in categories)}).
   Fairness is enforced at two levels: sources take turns within their beat,
   and beats take turns filling the day's list — so no loud feed or loud topic
   can flood the budget. A broken feed logs a warning and is skipped; it never
   kills the run. Result: `research/YYYY-MM-DD.json`.

2. **Draft** — the writing engine (currently **{llm["provider"]}**, model
   `{llm["model"]}` running on this Mac mini) reads the research plus your
   brand files and writes **{draft_count} drafts**: {", ".join(f"{n} {t}" for t, n in DRAFT_PLAN)}.
   Every draft carries YAML frontmatter (scores + sources). X-bound drafts
   are built from ONE story each and keep links out of the body — the X
   publisher posts the source link as a reply tweet. If the model is
   unreachable, deterministic template drafts keep the pipeline alive.
   Physical-world stories outrank pure-software ones.

3. **Review** — that's you, on the **Drafts** page (or `scripts/review_queue.py`
   in a terminal). Edit, approve, or reject. Marking research items
   **useful/ignore** on the Research page steers what gets drafted next time.

4. **Approve / Post** — approved drafts move to `approved/`. Posting is a
   **dry-run stub**: the Approved page runs every safety check a real post
   would run, and posts nothing. Live X posting doesn't exist until you
   explicitly ask for it to be built.

5. **Knowledge base** — after drafting, the same research gets mined for
   entities: companies, software, hardware, materials, GCs, subs, suppliers,
   manufacturers, projects. Each becomes a markdown file in `knowledge/`
   that accumulates mentions over time — the seed of the masterbuilder.ai
   directory. Browse it on the **Knowledge** page.
""")

st.divider()

# ---- where things live ---------------------------------------------------------
left, right = st.columns(2)

with left:
    st.subheader("Where everything lives")
    st.code(f"""{config.ROOT}/
├─ brand/            voice.md, topics.md, rules.md  ← the voice (editable in Settings)
├─ config/           sources.yaml                   ← what it reads (editable in Settings)
├─ research/         one JSON per day
├─ drafts/           one folder per day, 10 .md drafts
├─ approved/         what you blessed
├─ posted/           empty until live posting exists
├─ knowledge/        the directory — one .md per company/tool/material (Knowledge page)
├─ memory/
│   ├─ runs.log      every run, every error (Logs page)
│   └─ rejected/     rejected drafts, kept forever
├─ masterbuilder_bot/  the library (research, drafting, safety, llm...)
├─ scripts/          CLI versions of everything
└─ dashboard/        this app""", language=None)

    st.subheader("The three robots on this Mac mini")
    st.markdown("""
| launchd service | What it does | When |
|---|---|---|
| `ai.masterbuilder.bot` | research + drafts | daily, 6:00 AM ET |
| `ai.masterbuilder.dashboard` | this dashboard | always on (Tailscale only) |
| `ai.masterbuilder.ollama` | the local AI model | always on (localhost only) |

All three survive reboots and power failures. Sleep is disabled.
""")

with right:
    st.subheader("The safety rails (safety.py)")
    st.markdown(f"""
Hard checks — they raise errors, not warnings. Every posting path goes
through all of them:

- **Mode gate** — nothing posts unless `BOT_MODE=approved_posting`
  (currently: `{config.bot_mode()}`)
- **Location gate** — only `approved/` can post; `drafts/` is explicitly blocked
- **Source gate** — no sources in frontmatter → no post. No unsourced claims.
- **Cadence gate** — max {MAX_POSTS_PER_RUN} post per run, {MAX_POSTS_PER_DAY} per day. No spam.
- **Content gate** — banned-phrase list blocks engagement farming, ragebait,
  and anything impersonating a human
- **File gate** — the bot can't touch files outside its own data folders
- **No DMs** — there is no DM code at all
- **Secrets** — API keys are redacted from logs and never shown here
""")

    st.subheader("How the writing gets better")
    st.markdown("""
Three levers, strongest first:

1. **Mark research items** (Research page): `useful` items get drafted first,
   `ignore` items never get cited.
2. **Edit the brand files** (Settings page): `voice.md` is the strongest
   lever on tone; `topics.md` defines the "cracked story" filter.
3. **Swap the model** (`.env` on the mini): `LLM_MODEL=` any Ollama model, or
   set `ANTHROPIC_API_KEY` to use Claude — the strongest single upgrade.
""")

st.divider()
with st.expander("Currently enabled sources (live from config/sources.yaml)"):
    for cat in categories:
        names = [s["name"] for s in sources if s["category"] == cat]
        st.markdown(f"**{cat.replace('_', ' ')}** — " + " · ".join(names))
st.caption("Add any Substack: Settings → sources.yaml → url: https://NAME.substack.com/feed")
