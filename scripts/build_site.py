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
:root { --bg:#14120f; --panel:#1d1a16; --ink:#e8e2d5; --dim:#9a917f;
        --accent:#e0763a; --line:#33302a; }
* { box-sizing:border-box; margin:0; }
body { background:var(--bg); color:var(--ink); font:17px/1.65 Georgia,'Times New Roman',serif;
       max-width:880px; margin:0 auto; padding:2rem 1.2rem 4rem; }
a { color:var(--accent); text-decoration:none; } a:hover { text-decoration:underline; }
header.site { border-bottom:2px solid var(--accent); padding-bottom:1rem; margin-bottom:2rem; }
header.site h1 { font-size:1.6rem; letter-spacing:.5px; }
header.site h1 a { color:var(--ink); }
header.site p { color:var(--dim); font-size:.95rem; }
nav a { margin-right:1.2rem; font-variant:small-caps; letter-spacing:1px; }
h2 { margin:2rem 0 .8rem; font-size:1.25rem; border-left:4px solid var(--accent); padding-left:.6rem; }
article h1 { font-size:1.7rem; margin-bottom:.3rem; }
article h2, article h3 { border:none; padding:0; margin:1.4rem 0 .5rem; }
article p, article li { margin-bottom:.8rem; }
.meta { color:var(--dim); font-size:.85rem; margin-bottom:1.5rem; }
.card { background:var(--panel); border:1px solid var(--line); border-radius:8px;
        padding:1rem 1.2rem; margin-bottom:1rem; }
.card h3 { font-size:1.05rem; } .card p { color:var(--dim); font-size:.92rem; margin:.3rem 0 0; }
table { width:100%; border-collapse:collapse; font-size:.92rem; }
th, td { text-align:left; padding:.55rem .6rem; border-bottom:1px solid var(--line); vertical-align:top; }
th { color:var(--dim); font-variant:small-caps; letter-spacing:1px; font-weight:normal; }
.type { color:var(--dim); font-size:.8rem; text-transform:uppercase; letter-spacing:1px; }
footer { margin-top:3rem; padding-top:1rem; border-top:1px solid var(--line);
         color:var(--dim); font-size:.85rem; }
ul.sources { font-size:.85rem; color:var(--dim); }
"""


def page(title: str, body: str, depth: int = 0) -> str:
    prefix = "../" * depth
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} — {SITE_NAME}</title>
<link rel="stylesheet" href="{prefix}style.css"></head><body>
<header class="site">
  <h1><a href="{prefix}index.html">🧱 {SITE_NAME}</a></h1>
  <p>{TAGLINE}</p>
  <nav><a href="{prefix}index.html">field manual</a>
       <a href="{prefix}directory/index.html">directory</a></nav>
</header>
{body}
<footer>masterbuilder.ai — drafted by the bot, approved by a human. Every claim links its source.</footer>
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
    for p in posts:
        sources = "".join(f'<li><a href="{html.escape(u)}">{html.escape(u)}</a></li>'
                          for u in p["sources"])
        body = (f"<article><h1>{html.escape(p['title'])}</h1>"
                f"<p class='meta'>{p['date']} · {html.escape(p['type'])}</p>"
                f"{p['body_html']}"
                + (f"<h3>Sources</h3><ul class='sources'>{sources}</ul>" if sources else "")
                + "</article>")
        (DOCS / "posts" / f"{p['slug']}.html").write_text(
            page(p["title"], body, depth=1), encoding="utf-8")

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
        page("Directory", directory_body, depth=1), encoding="utf-8")

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
