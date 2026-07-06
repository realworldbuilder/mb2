"""Shared helpers for all dashboard pages: sys.path bootstrap, the
drawing-set style (grey "working set" counterpart to the public site's
blueprint), and the mode strip every page shows.

Every page already calls mode_banner(), so injecting the style there
themes the whole dashboard without touching each page.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from masterbuilder_bot import config  # noqa: E402

# Same drawing language as scripts/build_site.py, different paper:
# the site is chalk on drafting-blue; the backend is chalk on graphite —
# the working set in the site office, not the issued set.
STYLE = """
<style>
:root { --paper:#17191d; --ink:#d6dade; --dim:#8b939e; --line:#3a4048;
        --line-soft:#2a2f36; --redline:#ff6b4a; --cell:#1d2025;
        --grid:rgba(214,218,222,.035); --grid-major:rgba(214,218,222,.08); }

.stApp {
  background-color:var(--paper);
  background-image:
    linear-gradient(var(--grid-major) 1px, transparent 1px),
    linear-gradient(90deg, var(--grid-major) 1px, transparent 1px),
    linear-gradient(var(--grid) 1px, transparent 1px),
    linear-gradient(90deg, var(--grid) 1px, transparent 1px);
  background-size:60px 60px,60px 60px,12px 12px,12px 12px;
}
html, body, .stApp, .stApp * { font-family:ui-monospace,'SF Mono',Menlo,
  Consolas,'Liberation Mono',monospace !important; }
/* the monospace override must NOT hit Streamlit's icon ligatures, or the
   chevrons render as raw text like "keyboard_double_arrow_right" */
[data-testid="stIconMaterial"], [class*="material-symbols"],
span[translate="no"] {
  font-family:'Material Symbols Rounded' !important; }
::selection { background:var(--redline); color:var(--paper); }

/* long URLs (sources lists) must wrap, not overlap */
.stMarkdown, .stMarkdown p, .stMarkdown li { overflow-wrap:anywhere; }

/* the sheet: main content gets the drawing border */
.block-container { border:2px solid var(--ink); outline:1px solid var(--line);
  outline-offset:5px; background:rgba(20,22,26,.72); margin:2.2rem auto 2rem;
  padding:2.2rem 2.4rem 2.6rem !important; max-width:1200px; }
header[data-testid="stHeader"] { background:transparent; }
#MainMenu, footer { visibility:hidden; }

h1, h2, h3 { text-transform:uppercase; letter-spacing:2.5px;
  font-weight:400 !important; color:var(--ink); }
h1 { font-size:1.3rem !important; }
h2 { font-size:1rem !important; border-bottom:1px dashed var(--line);
  padding-bottom:.5rem; }
h3 { font-size:.9rem !important; }
p, li, label, .stMarkdown { color:var(--ink); }
small, .stCaption, [data-testid="stCaptionContainer"] { color:var(--dim) !important;
  text-transform:uppercase; letter-spacing:1.2px; font-size:.72rem !important; }
a { color:var(--ink); text-decoration:underline; text-decoration-style:dashed;
  text-decoration-color:var(--dim); text-underline-offset:3px; }
a:hover { color:var(--redline); text-decoration-color:var(--redline); }
hr { border:none; border-top:1px dashed var(--line); }

/* sidebar = title-block edge of the sheet */
[data-testid="stSidebar"] { background:var(--cell);
  border-right:2px solid var(--ink); }
[data-testid="stSidebar"] a, [data-testid="stSidebar"] span {
  text-transform:uppercase; letter-spacing:1.5px; font-size:.78rem !important; }
[data-testid="stSidebarNav"] a:hover span { color:var(--redline) !important; }

/* buttons: drawing-set boxes with a redline corner tick */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button,
[data-testid="stPageLink"] a {
  background:transparent; border:1px solid var(--ink); border-radius:0;
  color:var(--ink); text-transform:uppercase; letter-spacing:1.6px;
  font-size:.74rem; position:relative; }
.stButton > button:hover, .stDownloadButton > button:hover,
.stFormSubmitButton > button:hover, [data-testid="stPageLink"] a:hover {
  border-color:var(--redline); color:var(--redline); background:rgba(255,107,74,.06); }
.stButton > button[kind="primary"] { border:1px solid var(--redline);
  color:var(--redline); background:rgba(255,107,74,.08); }

/* metrics: dimension boxes */
[data-testid="stMetric"] { border:1px solid var(--line); padding:.7rem .9rem;
  position:relative; background:var(--cell); }
[data-testid="stMetric"]::before { content:''; position:absolute; top:-1px;
  left:-1px; width:9px; height:9px; border-top:2px solid var(--redline);
  border-left:2px solid var(--redline); }
[data-testid="stMetricLabel"] { text-transform:uppercase; letter-spacing:1.5px;
  color:var(--dim) !important; font-size:.66rem !important; }
[data-testid="stMetricValue"] { color:var(--ink); font-size:1.3rem !important;
  overflow-wrap:anywhere; }

/* inputs, selects, textareas: cells on the sheet */
.stTextInput input, .stTextArea textarea, .stSelectbox [data-baseweb],
.stMultiSelect [data-baseweb], .stNumberInput input {
  background:var(--cell) !important; border-radius:0 !important;
  color:var(--ink) !important; }
.stTextArea textarea { border:1px dashed var(--line) !important; }

/* alerts: field notes */
[data-testid="stAlert"] { border:1px dashed var(--line); border-radius:0;
  background:var(--cell); }

/* expanders: detail callouts */
[data-testid="stExpander"] { border:1px solid var(--line) !important;
  border-radius:0 !important; background:var(--cell); }
[data-testid="stExpander"] summary { text-transform:uppercase;
  letter-spacing:1.5px; font-size:.76rem; }

/* tabs */
[data-baseweb="tab-list"] { border-bottom:1px dashed var(--line); gap:1.4rem; }
[data-baseweb="tab"] { text-transform:uppercase; letter-spacing:1.5px;
  font-size:.74rem; background:transparent !important; }
[aria-selected="true"][data-baseweb="tab"] { color:var(--redline) !important; }

[data-testid="stDataFrame"] { border:1px solid var(--line); }

/* the mode strip (rendered by mode_banner) */
.mb-mode { border:1px solid var(--ink); display:flex; flex-wrap:wrap;
  font-size:.72rem; margin:0 0 1.4rem; text-transform:uppercase;
  letter-spacing:1.6px; }
.mb-mode > div { padding:.42rem .85rem; border-right:1px solid var(--line); }
.mb-mode > div:last-child { border-right:none; }
.mb-mode .lbl { color:var(--dim); margin-right:.55rem; font-size:.62rem;
  letter-spacing:2px; }
.mb-mode .armed { color:var(--redline); }

/* rubber stamp */
.mb-stamp { float:right; transform:rotate(-6deg); border:3px double var(--redline);
  color:var(--redline); padding:.32rem .85rem; margin:.1rem 0 .8rem 1.2rem;
  text-transform:uppercase; letter-spacing:3px; font-size:.74rem;
  text-align:center; line-height:1.45; opacity:.92; }
.mb-stamp span { display:block; font-size:.5rem; letter-spacing:2.5px; }

/* title block header (home page) */
.mb-head { display:flex; border:1px solid var(--ink); margin-bottom:1.1rem; }
.mb-head .tb-main { flex:1; padding:.85rem 1.05rem; }
.mb-head h1 { font-size:1.05rem; letter-spacing:2.5px; text-transform:uppercase;
  margin:0; }
.mb-head p { color:var(--dim); font-size:.7rem; margin:.3rem 0 0;
  text-transform:uppercase; letter-spacing:1.4px; }
.mb-head .tb-side { border-left:1px solid var(--ink); display:grid;
  min-width:250px; grid-template-columns:1fr 1fr; gap:1px; background:var(--ink); }
.mb-head .tb-side div { padding:.32rem .65rem; font-size:.68rem;
  background:var(--cell); }
.mb-head .lbl { display:block; font-size:.54rem; letter-spacing:2px;
  text-transform:uppercase; color:var(--dim); }

/* the pipeline */
.mb-pipe { display:flex; align-items:stretch; gap:0; margin:.4rem 0 1.2rem;
  flex-wrap:wrap; }
.mb-stage { flex:1 1 120px; border:1px solid var(--ink); padding:.7rem .8rem .6rem;
  position:relative; background:var(--cell); min-width:118px; }
.mb-stage::before { content:''; position:absolute; top:-1px; left:-1px;
  width:9px; height:9px; border-top:2px solid var(--redline);
  border-left:2px solid var(--redline); }
.mb-stage .num { font-size:.56rem; color:var(--dim); letter-spacing:2px; }
.mb-stage .name { display:block; font-size:.72rem; letter-spacing:2px;
  text-transform:uppercase; margin:.1rem 0 .35rem; }
.mb-stage .val { display:block; font-size:1.5rem; line-height:1.1;
  color:var(--ink); }
.mb-stage .val.hot { color:var(--redline); }
.mb-stage .sub { display:block; font-size:.6rem; color:var(--dim);
  text-transform:uppercase; letter-spacing:1.4px; margin-top:.25rem; }
.mb-arrow { display:flex; align-items:center; padding:0 .45rem;
  color:var(--redline); font-size:1.1rem; }
@media (max-width:900px) { .mb-arrow { display:none; } .mb-pipe { gap:.5rem; } }
</style>
"""


def inject_style() -> None:
    st.markdown(STYLE, unsafe_allow_html=True)


def mode_banner() -> None:
    """Every page calls this: injects the working-set style, then renders
    the mode strip so the posting state is impossible to miss."""
    inject_style()
    armed = config.bot_mode() == config.APPROVED_POSTING
    mode_html = (
        "<div class='mb-mode'>"
        f"<div><span class='lbl'>set</span>working set — backend</div>"
        f"<div><span class='lbl'>mode</span>"
        + ("<span class='armed'>approved_posting — live posting armed, "
           "one click per post</span>" if armed else
           "draft_only — posting disabled")
        + "</div>"
        "<div><span class='lbl'>rule</span>draft first · approval second · "
        "posting last</div>"
        "</div>"
    )
    st.markdown(mode_html, unsafe_allow_html=True)
