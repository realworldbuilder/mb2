#!/usr/bin/env python3
"""Build the public masterbuilder.ai site into docs/ (GitHub Pages).

  docs/index.html            home: latest Field Manual posts + directory preview
  docs/posts/<slug>.html     one page per APPROVED post (drafts never publish)
  docs/directory/index.html  the directory — VERIFIED entities only, with links

Plain HTML + one stylesheet. No framework, no build chain — a builder can
read every line of this.

Usage: python scripts/build_site.py
"""

import html
import shutil

import _bootstrap  # noqa: F401
from _bootstrap import ROOT

import frontmatter  # noqa: E402
import markdown  # noqa: E402

from masterbuilder_bot import config, storage  # noqa: E402
from masterbuilder_bot.knowledge import list_entities  # noqa: E402

DOCS = ROOT / "docs"
SITE_NAME = "Masterbuilder Field Manual"
TAGLINE = "boots and bits — AI, architecture, construction, robotics, space, for people who build real things"

CSS = """
/* blueprint: chalk-white line work on drafting-blue grid paper, redline accents */
:root { --paper:#0e2740; --ink:#dae7f3; --dim:#8aa7c2; --line:#3d5f80;
        --line-soft:#2b4964; --redline:#ff6b4a;
        --grid:rgba(214,230,245,.05); --grid-major:rgba(214,230,245,.11); }
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
         background:rgba(11,31,51,.62); }
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
.tb-side { border-left:1px solid var(--ink); display:flex; flex-direction:column;
           min-width:170px; }
.tb-side div { padding:.4rem .8rem; flex:1; font-size:.78rem; }
.tb-side div + div { border-top:1px solid var(--ink); }
nav.plan { border:1px solid var(--ink); border-top:none; padding:.5rem 1.1rem;
           margin-bottom:2.2rem; font-size:.72rem; letter-spacing:2px;
           text-transform:uppercase; }
nav.plan a { margin-right:1.8rem; }
nav.plan a::before { content:'\\25B8 '; color:var(--redline); }
nav.plan a:hover { color:var(--redline); }
h2 { margin:2.2rem 0 1rem; font-size:.92rem; font-weight:normal; text-transform:uppercase;
     letter-spacing:3px; border-bottom:1px dashed var(--line); padding-bottom:.5rem; }
h2::before { content:''; display:inline-block; width:.6rem; height:.6rem;
             border:1.5px solid var(--redline); transform:rotate(45deg);
             margin-right:.65rem; }
article h1 { font-size:1.45rem; line-height:1.35; margin-bottom:.4rem; font-weight:normal; }
article h2, article h3 { border:none; padding:0; margin:1.6rem 0 .6rem;
                         letter-spacing:1.5px; font-size:1rem; }
article h3::before { content:none; }
article p, article li { margin-bottom:.8rem; }
article blockquote { border-left:2px solid var(--redline); padding-left:1rem;
                     color:var(--dim); margin-bottom:.8rem; }
article pre { border:1px dashed var(--line); padding:.8rem 1rem; overflow-x:auto;
              margin-bottom:.8rem; font-size:.85em; }
.meta { color:var(--dim); font-size:.7rem; text-transform:uppercase;
        letter-spacing:1.5px; margin-bottom:1.5rem; }
.card { border:1px solid var(--line); padding:.9rem 1.1rem; margin-bottom:.9rem;
        position:relative; }
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
tr:hover td { background:rgba(214,230,245,.04); }
.type { color:var(--dim); font-size:.72rem; text-transform:uppercase; letter-spacing:1px; }
footer { margin-top:3rem; border:1px solid var(--ink); display:flex; flex-wrap:wrap;
         font-size:.78rem; }
footer div { padding:.45rem .9rem; flex:1 1 auto; }
footer div + div { border-left:1px solid var(--ink); }
ul.sources { font-size:.8rem; color:var(--dim); }
@media (max-width:640px) {
  body { padding:1.2rem .6rem 2rem; }
  .sheet { padding:1rem .9rem 1.4rem; }
  header.site { flex-direction:column; }
  .tb-side { border-left:none; border-top:1px solid var(--ink); flex-direction:row; }
  .tb-side div + div { border-top:none; border-left:1px solid var(--ink); }
  footer { flex-direction:column; }
  footer div + div { border-left:none; border-top:1px solid var(--ink); }
  table { display:block; overflow-x:auto; white-space:nowrap; }
  td { white-space:normal; min-width:9rem; }
  td.type { min-width:5rem; }
}
"""


def page(title: str, body: str, depth: int = 0, sheet: str = "A-001") -> str:
    prefix = "../" * depth
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} — {SITE_NAME}</title>
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
  </div>
</header>
<nav class="plan"><a href="{prefix}index.html">field manual</a>
     <a href="{prefix}directory/index.html">directory</a></nav>
{body}
<footer>
  <div><span class="lbl">drawn by</span>the bot</div>
  <div><span class="lbl">checked by</span>a human</div>
  <div><span class="lbl">note</span>every claim links its source</div>
</footer>
</div>
</body></html>"""


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
        body = (f"<article><h1>{html.escape(p['title'])}</h1>"
                f"<p class='meta'>{p['date']} · {html.escape(p['type'])}</p>"
                f"{p['body_html']}"
                + (f"<h3>Sources</h3><ul class='sources'>{sources}</ul>" if sources else "")
                + "</article>")
        (DOCS / "posts" / f"{p['slug']}.html").write_text(
            page(p["title"], body, depth=1, sheet=sheet_nums[p["slug"]]),
            encoding="utf-8")

    # ---- directory ----
    rows = "".join(
        f"<tr><td><a href='{html.escape(e['url'])}'>{html.escape(e['name'])}</a></td>"
        f"<td class='type'>{html.escape(e['type'])}</td>"
        f"<td>{html.escape(e['summary'])}</td>"
        f"<td>{e['mention_count']}</td></tr>"
        for e in sorted(entities, key=lambda x: (x["type"], x["name"].lower())))
    directory_body = (
        "<h2>The Directory</h2>"
        "<p class='meta'>Companies, software, hardware, materials, and players from "
        "the daily research. Only entities with a working, verified link are listed "
        "— no bullshit.</p>"
        f"<table><tr><th>name</th><th>type</th><th>what it is</th><th>mentions</th></tr>{rows}</table>"
        if entities else
        "<h2>The Directory</h2><p class='meta'>Nothing verified yet — check back after "
        "the next research run.</p>")
    (DOCS / "directory" / "index.html").write_text(
        page("Directory", directory_body, depth=1, sheet="A-002"), encoding="utf-8")

    # ---- home ----
    post_cards = "".join(
        f"<div class='card'><h3><a href='posts/{p['slug']}.html'>"
        f"{html.escape(p['title'])}</a></h3>"
        f"<p>{p['date']} · {html.escape(p['type'])}</p></div>"
        for p in posts[:20]) or ("<p class='meta'>First posts are in the approval "
                                 "queue. The field manual is coming.</p>")
    home = (f"<h2>Latest from the Field Manual</h2>{post_cards}"
            f"<h2>Directory</h2><p class='meta'>{len(entities)} verified entries and "
            f"counting — <a href='directory/index.html'>browse the directory</a>.</p>")
    (DOCS / "index.html").write_text(page("Home", home), encoding="utf-8")

    return len(posts), len(entities)


def main() -> int:
    posts, entities = build()
    print(f"Site built into docs/: {posts} posts, {entities} verified directory entries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
