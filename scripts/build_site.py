#!/usr/bin/env python3
"""Build the public masterbuilder.ai site into docs/ (GitHub Pages).

  docs/index.html            home: latest Field Manual posts + directory preview
  docs/posts/<slug>.html     one page per APPROVED post (drafts never publish)
  docs/directory/index.html  the directory — VERIFIED entities only, with links

Plain HTML + one stylesheet. No framework, no build chain — a builder can
read every line of this.

Usage: python scripts/build_site.py
"""

import datetime
import html
import os
import shutil

import _bootstrap  # noqa: F401
from _bootstrap import ROOT

import frontmatter  # noqa: E402
import markdown  # noqa: E402

from masterbuilder_bot import config, continuity, storage  # noqa: E402
from masterbuilder_bot.knowledge import list_entities  # noqa: E402

DOCS = ROOT / "docs"
SITE_NAME = "Masterbuilder Field Manual"
TAGLINE = "boots and bits — AI, architecture, construction, robotics, space, for people who build real things"
SITE_BASE = "https://realworldbuilder.github.io/mb2/"  # update when masterbuilder.ai DNS lands

# hand-drawn margin detail for the home page: running-bond coursing, one brick
# section-cut with redline hatch, architectural tick dimension below
HOME_FIG = """<figure class="detail-fig"><svg viewBox="0 0 220 130" xmlns="http://www.w3.org/2000/svg">
<defs><pattern id="hatch" width="6" height="6" patternTransform="rotate(45)"
patternUnits="userSpaceOnUse"><line x1="0" y1="0" x2="0" y2="6" stroke="var(--redline)"
stroke-width="1.1"/></pattern></defs>
<g stroke="currentColor" fill="none" stroke-width="1.2">
<rect x="20" y="12" width="55" height="16"/><rect x="79" y="12" width="55" height="16"/><rect x="138" y="12" width="55" height="16"/>
<rect x="20" y="32" width="27" height="16"/><rect x="51" y="32" width="55" height="16"/><rect x="110" y="32" width="55" height="16" fill="url(#hatch)"/><rect x="169" y="32" width="24" height="16"/>
<rect x="20" y="52" width="55" height="16"/><rect x="79" y="52" width="55" height="16"/><rect x="138" y="52" width="55" height="16"/>
<rect x="20" y="72" width="27" height="16"/><rect x="51" y="72" width="55" height="16"/><rect x="110" y="72" width="55" height="16"/><rect x="169" y="72" width="24" height="16"/>
<line x1="20" y1="94" x2="20" y2="114"/><line x1="193" y1="94" x2="193" y2="114"/>
<line x1="20" y1="108" x2="193" y2="108"/>
<line x1="15" y1="113" x2="25" y2="103" stroke="var(--redline)" stroke-width="1.6"/>
<line x1="188" y1="113" x2="198" y2="103" stroke="var(--redline)" stroke-width="1.6"/>
</g>
<text x="106" y="102" text-anchor="middle" font-size="9" fill="currentColor"
font-family="inherit" letter-spacing="1">2'-0&quot; NOM.</text>
</svg><figcaption>fig. 1 — typ. coursing detail · nts</figcaption></figure>"""


def stamp(top: str, sub: str) -> str:
    return f"<div class='stamp'>{top}<span>{sub}</span></div>"


# theme is applied in <head> before first paint so there's no flash, then the
# menu button flips it and remembers the choice. plain JS, no framework.
HEAD_JS = ("<script>document.documentElement.dataset.theme="
           "localStorage.getItem('mb-theme')||'dark';</script>")
MODE_JS = """<script>
(function () {
  var b = document.getElementById('mode'), h = document.documentElement;
  function label() { b.textContent = h.dataset.theme === 'light' ? 'dark mode' : 'light mode'; }
  b.onclick = function () {
    h.dataset.theme = h.dataset.theme === 'light' ? 'dark' : 'light';
    localStorage.setItem('mb-theme', h.dataset.theme);
    label();
  };
  label();
})();
</script>"""

CSS = """
/* blueprint: chalk-white line work on drafting-blue grid paper, redline accents.
   light mode = whiteprint: blue ink on vellum, toggled from the menu. */
:root { --paper:#0e2740; --ink:#dae7f3; --dim:#8aa7c2; --line:#3d5f80;
        --line-soft:#2b4964; --redline:#ff6b4a;
        --grid:rgba(214,230,245,.05); --grid-major:rgba(214,230,245,.11);
        --cell:#11293f; --sheet-bg:rgba(11,31,51,.62);
        --hover:rgba(214,230,245,.04); }
html[data-theme="light"] { --paper:#f1efe7; --ink:#22405e; --dim:#6d8196;
        --line:#9db2c4; --line-soft:#c9d5de; --redline:#d94a28;
        --grid:rgba(34,64,94,.07); --grid-major:rgba(34,64,94,.14);
        --cell:#e9e5d9; --sheet-bg:rgba(255,253,247,.6);
        --hover:rgba(34,64,94,.05); }
* { box-sizing:border-box; margin:0; }
body { background-color:var(--paper);
       background-image:
         linear-gradient(var(--grid-major) 1px, transparent 1px),
         linear-gradient(90deg, var(--grid-major) 1px, transparent 1px),
         linear-gradient(var(--grid) 1px, transparent 1px),
         linear-gradient(90deg, var(--grid) 1px, transparent 1px);
       background-size:60px 60px,60px 60px,12px 12px,12px 12px;
       color:var(--ink);
       font:15px/1.75 ui-monospace,'SF Mono',Menlo,Consolas,'Liberation Mono',monospace;
       padding:2.2rem 1.1rem 3rem; }
::selection { background:var(--redline); color:var(--paper); }
.sheet { max-width:920px; margin:0 auto; padding:1.5rem 1.7rem 2rem;
         border:2px solid var(--ink); outline:1px solid var(--line); outline-offset:5px;
         background:var(--sheet-bg); }
a { color:var(--ink); text-decoration:underline; text-decoration-style:dashed;
    text-decoration-color:var(--dim); text-underline-offset:3px; }
a:hover { color:var(--redline); text-decoration-color:var(--redline); }
.lbl { display:block; font-size:.6rem; letter-spacing:2px; text-transform:uppercase;
       color:var(--dim); }
header.site { display:flex; border:1px solid var(--ink); }
header.site .tb-main { flex:1; padding:.9rem 1.1rem; }
header.site h1 { font-size:1.1rem; letter-spacing:2.5px; text-transform:uppercase;
                 font-weight:normal; }
header.site h1 a, nav.plan a { color:var(--ink); text-decoration:none; }
header.site p.tagline { color:var(--dim); font-size:.75rem; margin-top:.35rem; }
.tb-side { border-left:1px solid var(--ink); display:grid; min-width:240px;
           grid-template-columns:1fr 1fr; gap:1px; background:var(--ink); }
.tb-side div { padding:.35rem .7rem; font-size:.74rem; background:var(--cell); }
nav.plan { border:1px solid var(--ink); border-top:none; padding:.5rem 1.1rem;
           margin-bottom:2.2rem; font-size:.72rem; letter-spacing:2px;
           text-transform:uppercase; display:flex; flex-wrap:wrap; gap:.4rem 1.8rem;
           align-items:baseline; }
nav.plan a::before, #mode::before { content:'\\25B8\\20 '; color:var(--redline); }
nav.plan a:hover { color:var(--redline); }
#mode { margin-left:auto; background:none; border:none; padding:0; color:var(--ink);
        font:inherit; letter-spacing:inherit; text-transform:inherit; cursor:pointer; }
#mode:hover { color:var(--redline); }
body { counter-reset:detail; }
h2 { margin:2.2rem 0 1rem; font-size:.92rem; font-weight:normal; text-transform:uppercase;
     letter-spacing:3px; border-bottom:1px dashed var(--line); padding-bottom:.5rem;
     clear:both; }
h2::before { counter-increment:detail; content:counter(detail);
             display:inline-flex; align-items:center; justify-content:center;
             width:1.6em; height:1.6em; border:1.5px solid var(--redline);
             border-radius:50%; margin-right:.65rem; font-size:.85em;
             color:var(--redline); vertical-align:-.35em; }
article h1 { font-size:1.45rem; line-height:1.35; margin-bottom:.4rem; font-weight:normal; }
article h2, article h3 { border:none; padding:0; margin:1.6rem 0 .6rem;
                         letter-spacing:1.5px; font-size:1rem; }
article h3::before { content:none; }
article p, article li { margin-bottom:.8rem; }
article blockquote { border-left:2px solid var(--redline); padding:.4rem 1rem .4rem 1rem;
                     color:var(--dim); margin-bottom:.8rem;
                     background:repeating-linear-gradient(45deg,
                       rgba(255,107,74,.05) 0 6px, transparent 6px 14px); }
article ul li::marker { color:var(--redline); content:'\\25B8  '; }
article pre { border:1px dashed var(--line); padding:.8rem 1rem; overflow-x:auto;
              margin-bottom:.8rem; font-size:.85em; }
.meta { color:var(--dim); font-size:.7rem; text-transform:uppercase;
        letter-spacing:1.5px; margin-bottom:1.5rem; }
.card { border:1px solid var(--line); padding:.9rem 1.1rem; margin-bottom:.9rem;
        position:relative; display:flow-root; }
.card.new::after { content:'\\0394\\20 LATEST ISSUE'; position:absolute; top:-1px; right:-1px;
                   border:1px solid var(--redline); color:var(--redline);
                   font-size:.58rem; letter-spacing:2px; padding:.12rem .5rem;
                   text-transform:uppercase; }
.card::before { content:''; position:absolute; top:-1px; left:-1px; width:9px; height:9px;
                border-top:2px solid var(--redline); border-left:2px solid var(--redline); }
.card:hover { border-color:var(--ink); }
.card h3 { font-size:.95rem; font-weight:normal; }
.card h3 a { text-decoration:none; }
.card h3 a:hover { text-decoration:underline; text-decoration-style:dashed; }
.card p { color:var(--dim); font-size:.68rem; margin:.35rem 0 0;
          text-transform:uppercase; letter-spacing:1.5px; }
table { width:100%; border-collapse:collapse; font-size:.82rem;
        border:1px solid var(--line); }
th, td { text-align:left; padding:.55rem .65rem; vertical-align:top; }
th { color:var(--dim); font-size:.65rem; text-transform:uppercase; letter-spacing:2px;
     font-weight:normal; border-bottom:2px solid var(--ink); }
td { border-bottom:1px solid var(--line-soft); }
tr:hover td { background:var(--hover); }
.type { color:var(--dim); font-size:.72rem; text-transform:uppercase; letter-spacing:1px; }
footer { margin-top:3rem; border:1px solid var(--ink); display:flex; flex-wrap:wrap;
         font-size:.78rem; }
footer div { padding:.45rem .9rem; flex:1 1 auto; }
footer div + div { border-left:1px solid var(--ink); }
ul.sources { font-size:.8rem; color:var(--dim); }
.stamp { float:right; transform:rotate(-6deg); border:3px double var(--redline);
         color:var(--redline); padding:.4rem 1rem; margin:.2rem 0 1rem 1.4rem;
         text-transform:uppercase; letter-spacing:3px; font-size:.82rem;
         text-align:center; line-height:1.5; opacity:.92; }
.stamp span { display:block; font-size:.55rem; letter-spacing:2.5px; }
.detail-fig { float:right; width:250px; margin:.3rem 0 1.2rem 1.5rem;
              border:1px solid var(--line); padding:.8rem .8rem .6rem;
              color:var(--ink); }
.detail-fig svg { width:100%; height:auto; display:block; }
.detail-fig figcaption { font-size:.6rem; color:var(--dim); text-transform:uppercase;
                         letter-spacing:1.5px; margin-top:.5rem; text-align:center; }
article.today { border:1px solid var(--line); padding:1rem 1.2rem 1.2rem;
                margin-bottom:1.2rem; background:var(--cell); }
article.today h2 .type { font-size:.68rem; margin-left:.6rem; }
.subscribe form { display:flex; gap:.5rem; margin-top:.6rem; flex-wrap:wrap; }
.subscribe input[type=email] { flex:1 1 14rem; background:var(--paper);
    color:var(--ink); border:1px solid var(--line); padding:.5rem .7rem;
    font:inherit; }
.subscribe input[type=email]:focus { outline:none; border-color:var(--ink); }
.subscribe button { background:var(--redline); color:#fff; border:none;
    padding:.5rem 1.1rem; font:inherit; text-transform:uppercase;
    letter-spacing:1px; font-size:.72rem; cursor:pointer; }
.subscribe button:hover { filter:brightness(1.1); }
@media (max-width:640px) {
  body { padding:1.2rem .6rem 2rem; }
  .sheet { padding:1rem .9rem 1.4rem; }
  header.site { flex-direction:column; }
  .tb-side { border-left:none; border-top:1px solid var(--ink); }
  .stamp { float:none; display:inline-block; margin:.2rem 0 1rem; }
  .detail-fig { float:none; margin:0 auto 1.4rem; }
  footer { flex-direction:column; }
  footer div + div { border-left:none; border-top:1px solid var(--ink); }
  table { display:block; overflow-x:auto; white-space:nowrap; }
  td { white-space:normal; min-width:9rem; }
  td.type { min-width:5rem; }
}
"""


# tiny inline-SVG favicon: chalk sheet border + redline brick on blueprint blue
FAVICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' "
           "viewBox='0 0 16 16'%3E%3Crect width='16' height='16' fill='%230e2740'/%3E"
           "%3Crect x='1.5' y='1.5' width='13' height='13' fill='none' "
           "stroke='%23dae7f3'/%3E%3Crect x='4' y='6.5' width='8' height='3.5' "
           "fill='%23ff6b4a'/%3E%3C/svg%3E")


def page(title: str, body: str, depth: int = 0, sheet: str = "A-001",
         prefix: str | None = None) -> str:
    prefix = ("../" * depth) if prefix is None else prefix
    issued = datetime.date.today().isoformat()
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="{html.escape(TAGLINE)}">
<title>{html.escape(title)} — {SITE_NAME}</title>
<link rel="icon" href="{FAVICON}">
{HEAD_JS}
<link rel="stylesheet" href="{prefix}style.css"></head><body>
<div class="sheet">
<header class="site">
  <div class="tb-main">
    <h1><a href="{prefix}index.html">🧱 {SITE_NAME}</a></h1>
    <p class="tagline">{TAGLINE}</p>
  </div>
  <div class="tb-side">
    <div><span class="lbl">project</span>masterbuilder.ai</div>
    <div><span class="lbl">sheet</span>{sheet}</div>
    <div><span class="lbl">issued</span>{issued}</div>
    <div><span class="lbl">scale</span>NTS</div>
  </div>
</header>
<nav class="plan"><a href="{prefix}index.html">field manual</a>
     <a href="{prefix}newsletter/index.html">weekly email</a>
     <a href="{prefix}directory/index.html">directory</a>
     <a href="{prefix}receipts/index.html">receipts</a>
     <a href="{prefix}records/index.html">records</a>
     <button id="mode" type="button">light mode</button></nav>
{body}
<footer>
  <div><span class="lbl">drawn by</span>the bot</div>
  <div><span class="lbl">checked by</span>a human</div>
  <div><span class="lbl">note</span>every claim links its source</div>
</footer>
</div>
{MODE_JS}
</body></html>"""


def subscribe_box(heading: str = "Get it by email") -> str:
    """Buttondown embed form. Renders only once BUTTONDOWN_USERNAME is set
    (Connections page) — before that the site simply has no subscribe box."""
    user = os.environ.get("BUTTONDOWN_USERNAME", "").strip()
    if not user:
        return ""
    action = f"https://buttondown.email/api/emails/embed-subscribe/{html.escape(user)}"
    return (f"<div class='card subscribe'><h3>{html.escape(heading)}</h3>"
            "<p class='meta'>The week's best stories, one email, Monday morning. "
            "No takes, no spam — the picks are the judgment.</p>"
            f"<form action='{action}' method='post' target='_blank'>"
            "<input type='email' name='email' placeholder='you@example.com' "
            "required aria-label='email address'> "
            "<button type='submit'>subscribe</button></form></div>")


def load_posts() -> list[dict]:
    posts = []
    for path in storage.list_approved():
        try:
            post = frontmatter.load(str(path))
        except Exception:  # noqa: BLE001
            continue
        posts.append({
            "slug": path.stem,
            "title": post.get("title", path.stem),
            "type": post.get("type", "post"),
            "date": path.parent.name,
            "sources": post.get("sources", []) or [],
            "body_html": markdown.markdown(post.content, extensions=["extra"]),
        })
    return sorted(posts, key=lambda p: p["date"], reverse=True)


def build() -> tuple[int, int]:
    if DOCS.exists():
        shutil.rmtree(DOCS)
    (DOCS / "posts").mkdir(parents=True)
    (DOCS / "directory").mkdir()
    (DOCS / "receipts").mkdir()
    (DOCS / "records").mkdir()
    (DOCS / "newsletter").mkdir()
    (DOCS / "style.css").write_text(CSS, encoding="utf-8")
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")

    posts = load_posts()
    entities = list_entities(verified_only=True)  # no bullshit: verified only

    # ---- post pages ----
    sheet_nums = {p["slug"]: f"A-{101 + i}" for i, p in
                  enumerate(sorted(posts, key=lambda x: (x["date"], x["slug"])))}
    for p in posts:
        sources = "".join(f'<li><a href="{html.escape(u)}">{html.escape(u)}</a></li>'
                          for u in p["sources"])
        body = (f"<article>{stamp('approved', 'by a human')}"
                f"<h1>{html.escape(p['title'])}</h1>"
                f"<p class='meta'>{p['date']} · {html.escape(p['type'])}</p>"
                f"{p['body_html']}"
                + (f"<h3>Sources</h3><ul class='sources'>{sources}</ul>" if sources else "")
                + "</article>")
        (DOCS / "posts" / f"{p['slug']}.html").write_text(
            page(p["title"], body, depth=1, sheet=sheet_nums[p["slug"]]),
            encoding="utf-8")

    # ---- directory (+ one dossier page per verified entity) ----
    for i, e in enumerate(sorted(entities, key=lambda x: x["name"].lower())):
        timeline = "".join(
            f"<li>{html.escape(str(m.get('date', '')))} — "
            f"<a href='{html.escape(str(m.get('url', '')))}'>"
            f"{html.escape(str(m.get('title', '')))}</a> · "
            f"<span class='type'>{html.escape(str(m.get('source', '')))}</span></li>"
            for m in reversed(e["mentions"]))
        dossier = (f"<article>{stamp('on file', 'the dossier')}"
                   f"<h1>{html.escape(e['name'])}</h1>"
                   f"<p class='meta'>{html.escape(e['type'])} · first seen "
                   f"{html.escape(e['first_seen'])} · {e['mention_count']} "
                   f"mention{'s' if e['mention_count'] != 1 else ''}</p>"
                   f"<p>{html.escape(e['summary'])}</p>"
                   f"<p><a href='{html.escape(e['url'])}'>official site ↗</a></p>"
                   "<h3>Every time they crossed the research desk</h3>"
                   f"<ul class='sources'>{timeline}</ul></article>")
        (DOCS / "directory" / f"{e['slug']}.html").write_text(
            page(e["name"], dossier, depth=1, sheet=f"D-{101 + i}"),
            encoding="utf-8")

    rows = "".join(
        f"<tr><td><a href='{html.escape(e['slug'])}.html'>{html.escape(e['name'])}</a></td>"
        f"<td class='type'>{html.escape(e['type'])}</td>"
        f"<td>{html.escape(e['summary'])}</td>"
        f"<td>{e['mention_count']}</td>"
        f"<td><a href='{html.escape(e['url'])}'>site ↗</a></td></tr>"
        for e in sorted(entities, key=lambda x: (x["type"], x["name"].lower())))
    directory_body = stamp("verified", "no bullshit") + (
        "<h2>The Directory</h2>"
        "<p class='meta'>Companies, software, hardware, materials, and players from "
        "the daily research. Only entities with a working, verified link are listed "
        "— no bullshit. Names open the dossier: every mention, dated.</p>"
        f"<table><tr><th>name</th><th>type</th><th>what it is</th><th>mentions</th><th>link</th></tr>{rows}</table>"
        if entities else
        "<h2>The Directory</h2><p class='meta'>Nothing verified yet — check back after "
        "the next research run.</p>")
    (DOCS / "directory" / "index.html").write_text(
        page("Directory", directory_body, depth=1, sheet="A-002"), encoding="utf-8")

    # ---- receipts: as-built vs as-promised ----
    arcs = continuity.load_arcs()
    receipts = [a for a in arcs if a.get("due_date")]
    watching = [a for a in continuity.open_arcs(arcs) if not a.get("due_date")]
    outcome_label = {"hit": "HIT — delivered", "miss": "MISS — slipped",
                     "no_news": "DUE — no word", "open": "pending",
                     "updated": "pending", "closed": "closed"}
    r_rows = "".join(
        f"<tr><td>{html.escape(a.get('claim') or a['title'])}"
        + (f" <a href='{html.escape(a['source_urls'][0])}'>[source]</a>"
           if a.get("source_urls") else "")
        + f"</td><td class='type'>{html.escape(a['opened'])}</td>"
        f"<td class='type'>{html.escape(a['due_date'])}</td>"
        f"<td class='type'>{html.escape(outcome_label.get(a['status'], a['status']))}</td></tr>"
        for a in sorted(receipts, key=lambda x: x["due_date"]))
    w_rows = "".join(
        f"<tr><td>{html.escape(a['title'])}</td>"
        f"<td>{html.escape(a.get('watch_for', ''))}</td>"
        f"<td class='type'>{html.escape(a['opened'])}</td></tr>"
        for a in sorted(watching, key=lambda x: x["opened"], reverse=True)[:30])
    hits = sum(1 for a in receipts if a["status"] == "hit")
    misses = sum(1 for a in receipts if a["status"] == "miss")
    receipts_body = stamp("as-built", "vs as-promised") + "<h2>The Receipts</h2>"
    if receipts:
        receipts_body += (
            f"<p class='meta'>{len(receipts)} dated claims on file · {hits} hit · "
            f"{misses} missed · the calendar keeps the score. Every claim is the "
            "source's own words — we just wrote down the date.</p>"
            f"<table><tr><th>the claim</th><th>said on</th><th>due</th>"
            f"<th>outcome</th></tr>{r_rows}</table>")
    else:
        receipts_body += (
            "<p class='meta'>No dated claims on file yet. When a company puts a "
            "date on a promise, it gets written down here — and graded when the "
            "date arrives.</p>")
    if w_rows:
        receipts_body += ("<h2>Currently Watching</h2>"
                          f"<table><tr><th>story</th><th>watching for</th>"
                          f"<th>since</th></tr>{w_rows}</table>")
    (DOCS / "receipts" / "index.html").write_text(
        page("Receipts", receipts_body, depth=1, sheet="A-003"), encoding="utf-8")

    # ---- records: the record set ----
    record_data = continuity.load_records()["records"]
    rec_rows = "".join(
        f"<tr><td>{html.escape(r['label'])}</td>"
        f"<td>{html.escape(str(r['value']))} {html.escape(r['unit'])}"
        f" <a href='{html.escape(r.get('source_url', ''))}'>[source]</a></td>"
        f"<td>{html.escape(r.get('holder', ''))}</td>"
        f"<td class='type'>{html.escape(r['date'])}</td>"
        f"<td class='type'>"
        + (f"{html.escape(str(r['previous'].get('value')))} "
           f"{html.escape(r['previous'].get('unit', ''))} — "
           f"{html.escape(r['previous'].get('holder', ''))} "
           f"({html.escape(r['previous'].get('date', ''))})"
           if r.get("previous") else "first on the books")
        + "</td></tr>"
        for r in sorted(record_data.values(), key=lambda x: x["date"], reverse=True))
    records_body = stamp("record set", "current holders") + "<h2>The Record Set</h2>"
    if record_data:
        records_body += (
            f"<p class='meta'>{len(record_data)} records tracked — hard numbers "
            "from the daily research, updated when they fall. Every mark links "
            "its source.</p>"
            f"<table><tr><th>record</th><th>current mark</th><th>holder</th>"
            f"<th>set</th><th>previous</th></tr>{rec_rows}</table>")
    else:
        records_body += (
            "<p class='meta'>The record book is open. Fastest, largest, longest, "
            "first-at-scale — when the research turns up a mark, it gets logged "
            "here, and beaten records keep their history.</p>")
    (DOCS / "records" / "index.html").write_text(
        page("Records", records_body, depth=1, sheet="A-004"), encoding="utf-8")

    # ---- newsletter archive: the weekly digests ----
    digests = [p for p in posts if p["type"] == "weekly_digest"]
    digest_cards = "".join(
        f"<div class='card{' new' if i == 0 else ''}'>"
        f"<h3><a href='../posts/{p['slug']}.html'>{html.escape(p['title'])}</a></h3>"
        f"<p>{p['date']}</p></div>"
        for i, p in enumerate(digests)) or (
            "<p class='meta'>The first weekly digest goes out Monday morning. "
            "Subscribe and it lands in your inbox.</p>")
    newsletter_body = (stamp("weekly", "monday morning")
                       + "<h2>The Weekly Reading List</h2>"
                       "<p class='meta'>Every Monday: the past week's best stories "
                       "from AI, architecture, construction, robotics, and space — "
                       "picked for people who build real things. Real numbers, "
                       "primary sources, no takes.</p>"
                       + subscribe_box() + digest_cards)
    (DOCS / "newsletter" / "index.html").write_text(
        page("Weekly email", newsletter_body, depth=1, sheet="A-005"),
        encoding="utf-8")

    # ---- home: today's reading list front and center ----
    latest_list = next((p for p in posts if p["type"] == "reading_list"), None)
    if latest_list:
        today_block = (
            f"<article class='today'>"
            f"<h2>Today's Reading List <span class='type'>{latest_list['date']}</span></h2>"
            f"{latest_list['body_html']}"
            f"<p class='meta'><a href='posts/{latest_list['slug']}.html'>"
            "permalink ↗</a></p></article>")
    else:
        today_block = ("<h2>Today's Reading List</h2><p class='meta'>First list "
                       "is in the works — the research desk runs every morning "
                       "at 6 AM.</p>")
    post_cards = "".join(
        f"<div class='card'>"
        f"<h3><a href='posts/{p['slug']}.html'>"
        f"{html.escape(p['title'])}</a></h3>"
        f"<p>{p['date']} · {html.escape(p['type'])}</p></div>"
        for p in posts[:20] if latest_list is None or p["slug"] != latest_list["slug"])
    home = (stamp("issued", "for construction")
            + today_block
            + subscribe_box("The weekly email")
            + (f"<h2>From the archive</h2>{HOME_FIG}{post_cards}" if post_cards
               else HOME_FIG)
            + f"<h2>Directory</h2><p class='meta'>{len(entities)} verified entries and "
            f"counting — <a href='directory/index.html'>browse the directory</a>.</p>"
            f"<h2>Ledgers</h2><p class='meta'>{len(receipts)} dated claims on "
            f"<a href='receipts/index.html'>the receipts</a> ({hits} hit, {misses} "
            f"missed) · {len(record_data)} marks in "
            f"<a href='records/index.html'>the record set</a>. The calendar keeps "
            "the score.</p>")
    (DOCS / "index.html").write_text(page("Home", home), encoding="utf-8")

    # ---- 404: served by GitHub Pages at any bad path, so links are absolute ----
    nf = (f"<article>{stamp('void', 'superseded')}<h1>Sheet not found</h1>"
          "<p class='meta'>RFI-001 · response required</p>"
          "<p>This detail was never drawn — or it got superseded in the last "
          f"revision. Head back to <a href='{SITE_BASE}index.html'>the field "
          "manual</a> and work from the current set.</p></article>")
    (DOCS / "404.html").write_text(
        page("Sheet not found", nf, sheet="RFI-001", prefix=SITE_BASE),
        encoding="utf-8")

    return len(posts), len(entities)


def main() -> int:
    posts, entities = build()
    print(f"Site built into docs/: {posts} posts, {entities} verified directory entries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
