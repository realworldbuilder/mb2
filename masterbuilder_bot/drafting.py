"""Turn a day's research into draft content.

Story selection happens FIRST, in masterbuilder_bot/triage.py: every item
gets a builder-interest score, near-duplicates collapse, and the top
stories get their full article text fetched. Drafting then assigns
stories by rank — the reading list curates the day's best five, each solo
X post takes one of the top stories, and the essay/content idea go deep
on the single best one.

Two engines:
  * LLM — via masterbuilder_bot.llm, which supports Anthropic (Claude),
    OpenAI, and any OpenAI-compatible endpoint (Ollama/LM Studio on the
    Mac mini). Brand voice files are fed into the prompt so the drafts
    sound like a builder who learned AI.
  * Template fallback — deterministic drafts built straight from the
    research items. Used when no provider is configured or the call
    fails, so the pipeline (and the smoke test) always completes.

Every draft is Markdown + YAML frontmatter, saved to drafts/YYYY-MM-DD/.
Source links live in the frontmatter; X-bound drafts keep them OUT of the
body (the X publisher posts them as a reply), while essays and content
ideas keep a sources footer in the body.
"""

from datetime import datetime
from pathlib import Path

from masterbuilder_bot import (config, continuity, knowledge, learning, llm,
                               media, storage, triage)
from masterbuilder_bot.logging_utils import log, log_error
from masterbuilder_bot.models import DraftMeta, ResearchItem, plan_slots

TYPE_INSTRUCTIONS = {
    "x_post": (
        "one standalone X story-post on the one story provided. A reader "
        "with ZERO prior context must come away knowing what happened, the "
        "scale of it, and why it matters — the post is the whole story, "
        "not a teaser. 500-900 characters total, written as 3-4 SHORT "
        "paragraphs separated by blank lines; each paragraph under 270 "
        "characters (it becomes one tweet when threaded). Paragraph 1 is "
        "the HOOK (per HOOK CRAFT). Middle paragraphs carry the context a "
        "newcomer needs: the background, the concrete numbers, what "
        "actually happened. Final paragraph twists the knife — the catch, "
        "cost, gap, or open question, straight from the research. Plain "
        "language, no manufactured opinion, no 'here's my take'. Stick to "
        "that single story"
    ),
    "reading_list": (
        "today's Masterbuilder Reading List as an X thread. Tweet 1 is the "
        "HOOK (per HOOK CRAFT): lead with the single wildest fact or number "
        "from today's five stories, twist the knife, then open the "
        "curiosity gap with a clear promise — e.g. '5 stories worth your "
        "time today ↓'. Do NOT open with 'The reading list — <date>'. Then "
        "ONE tweet per research item: a hook-grade first sentence on what "
        "happened (lead with the number or the weird detail, not the "
        "source's name), why a builder cares in a second short sentence, "
        "then the item's URL on its own line. Each tweet under 260 "
        "characters including the URL. If UPDATES CONTEXT is provided, "
        "close with ONE extra 'Still watching' tweet — one dry line per "
        "tracked story, dates and outcomes only. No opinions, no ranking "
        "commentary — the picks ARE the judgment"
    ),
    "reading_list_substack": (
        "the Masterbuilder Reading List as a Substack email — 400-800 "
        "words, markdown. TITLE (first line, as '# <title>'): a hook per "
        "HOOK CRAFT built on the day's wildest fact — never 'Reading List "
        "<date>'. Then a 2-3 sentence intro that pays the title off. Then "
        "one section per research item: a bold '## ' heading stating the "
        "story's key fact in plain words (not the source's headline), 2-4 "
        "dry sentences with the concrete numbers and why a builder cares, "
        "then the item's URL on its own line. If UPDATES CONTEXT is "
        "provided, close with a '## Still watching' section — one line "
        "per tracked story with its date and status. No manufactured "
        "takes; the picks ARE the judgment"
    ),
    "essay": (
        "one Masterbuilder Field Manual essay draft, 400-700 words, markdown "
        "headers allowed. The research below is today's TOP story — go deep "
        "on it using the source material: the constraint, the numbers, what "
        "broke, what it means for people who build. Field-first, no "
        "press-release tone"
    ),
    "content_idea": (
        "one meme / sticker / visual content idea rooted in the story "
        "provided (today's most cracked story): describe the image, the "
        "caption, and why builders would share it"
    ),
    # ---- continuity types: content that strings the days together ----
    "followup": (
        "one standalone X UPDATE post on a story we covered before — see "
        "ARC CONTEXT below. 400-800 characters as 2-4 short paragraphs "
        "(each under 270 characters — one tweet when threaded). Paragraph "
        "1 is the hook: what CHANGED — the new number or milestone. Then "
        "the callback with enough context to stand alone: what we flagged "
        "on <date>, the original key fact, and the delta between then and "
        "now — the delta IS the story. A reader who missed the original "
        "must still get the full picture. Facts only, numbers verbatim"
    ),
    "receipt": (
        "one standalone X post grading a dated claim — see ARC CONTEXT "
        "below. 300-700 characters as 2-3 short paragraphs (each under "
        "270 characters). Ledger style with full standalone context: the "
        "one-line background of the original story, what the source "
        "claimed (quoted close to verbatim), when they said it, when it "
        "was due, and what actually happened — delivered, slipped, or "
        "'deadline passed, no word we've seen'. No gloating, no takes — "
        "the calendar is the judgment"
    ),
    "record": (
        "one standalone X post on a record falling — see RECORD CONTEXT "
        "below. 300-700 characters as 2-3 short paragraphs (each under "
        "270 characters). Paragraph 1: the new mark, cold number. Then "
        "the previous record it beat (holder, value, date) plus enough "
        "context that a reader who never heard of the metric understands "
        "what was measured and why the jump matters. Two numbers "
        "colliding is the spine of the post"
    ),
    # ---- named weekly segments ----
    "demo_vs_dirt": (
        "this week's DEMO vs DIRT — the Monday segment. From today's "
        "research, pair the most polished claim or demo with the field "
        "reality that grounds it: a cost, a delay, a constraint, or a "
        "second story that undercuts it. Open the hook with 'Demo vs "
        "Dirt:'. Both sides must be sourced facts from the research — "
        "never invent the dirt. 400-900 characters as 2-4 short "
        "paragraphs (each under 270 characters — one tweet when "
        "threaded), with enough context that both sides stand alone"
    ),
    "still_standing": (
        "this week's STILL STANDING — the Wednesday segment on things that "
        "outlive their design life: infrastructure decades past spec, "
        "machines that refuse to die, maintenance that never ends. Pick "
        "the best endurance story in today's research; the age gap is the "
        "hook (years in service vs years designed for). One standalone "
        "story-post, 400-800 characters as 2-4 short paragraphs (each "
        "under 270 characters): the age-gap hook, then the context — what "
        "it was designed for, what it has endured, what keeps it going"
    ),
    "punch_list": (
        "THE PUNCH LIST — the Friday wrap essay (400-700 words, markdown "
        "headers allowed) walking this week's stories like a foreman walks "
        "a job. Use THE WEEK'S MATERIAL below: find the through-line if "
        "the week has one, call back to what we published, and close with "
        "the open items — what to watch next week. If there's no "
        "through-line, don't manufacture one: walk it story by story, "
        "concrete numbers, field-first"
    ),
}

TYPE_TITLES = {
    "x_post": "X post",
    "reading_list": "Reading list",
    "reading_list_substack": "Reading list digest",
    "essay": "Field Manual essay",
    "content_idea": "Content idea",
    "followup": "Update",
    "receipt": "Receipt",
    "record": "Record broken",
    "demo_vs_dirt": "Demo vs Dirt",
    "still_standing": "Still Standing",
    "punch_list": "The Punch List",
}

# Solo X story-posts: threaded by the publisher one paragraph per tweet,
# so every paragraph must fit a tweet and the total stays digestible.
X_SOLO_TYPES = ("x_post", "followup", "receipt", "record",
                "still_standing", "demo_vs_dirt")


def load_brand() -> dict[str, str]:
    """Read brand/persona.md, voice.md, rules.md, topics.md into a dict."""
    out = {}
    for name in ("persona", "voice", "rules", "topics"):
        path = config.BRAND_DIR / f"{name}.md"
        out[name] = path.read_text(encoding="utf-8") if path.exists() else ""
    return out


def _sources_footer(items: list[ResearchItem]) -> str:
    if not items:
        return "\n\n---\nSources: none (no research available today)"
    lines = [f"- [{i.title}]({i.url}) — {i.source}" for i in items]
    return "\n\n---\nSources:\n" + "\n".join(lines)


def _assign_items(ranked: list[ResearchItem], dtype: str, n: int) -> list[ResearchItem]:
    """Which stories does draft #n of this type get? `ranked` is triage
    output, best story first.

    - reading_list: the day's top 5 — it IS the judgment.
    - x_post #n: the n-th best story, so each of the top stories gets its
      own solo post (overlap with the reading list is fine — the list
      curates, the post goes deep).
    - essay / content_idea: the single best story, with its article text.
    """
    if not ranked:
        return []
    if dtype in ("reading_list", "reading_list_substack"):
        return ranked[:5]
    if dtype == "x_post":
        return [ranked[n % len(ranked)]]
    if dtype == "demo_vs_dirt":
        return ranked[:6]  # the model needs options to find a real pairing
    if dtype == "still_standing":
        return ranked[:8]
    if dtype == "punch_list":
        return ranked[:5]  # week context arrives separately via week_digest
    return [ranked[0]]


def _find_item(ranked: list[ResearchItem], url: str) -> list[ResearchItem]:
    return [i for i in ranked if i.url == url][:1]


def _special_context(dtype: str, payload: dict, day: str) -> str:
    """The extra prompt block for continuity drafts: the arc's history or
    the record that just fell. All of it is recorded fact — the drafter
    frames, it never invents."""
    if dtype in ("followup", "receipt"):
        arc = payload["arc"]
        p = arc.get("pending") or {}
        lines = [
            "ARC CONTEXT — this is a story we already covered:",
            f"- We published on {arc['opened']}: \"{arc.get('origin_head', '')[:280]}\"",
            f"- We were watching for: {arc.get('watch_for', '')}",
        ]
        if arc.get("claim"):
            lines.append(f"- The dated claim from the source: \"{arc['claim']}\""
                         + (f" (due {arc['due_date']})" if arc.get("due_date") else ""))
        if dtype == "receipt":
            lines.append(f"- Outcome on the due date: {p.get('outcome', 'no_news')}"
                         " (hit = delivered, miss = slipped/failed, no_news = "
                         "deadline passed with no confirmation in our research)")
        if p.get("title"):
            lines.append(f"- Today's development: {p['title']} — {p.get('note', '')}")
        return "\n".join(lines)
    if dtype == "record":
        e = payload["event"]
        r, prev = e["record"], e["record"].get("previous", {})
        return ("RECORD CONTEXT — a standing record just fell:\n"
                f"- Metric: {e['label']}\n"
                f"- New mark: {r['value']} {r['unit']} — {r['holder']} ({r['date']})\n"
                f"- Previous record: {prev.get('value')} {prev.get('unit', r['unit'])}"
                f" — {prev.get('holder', 'unknown')} ({prev.get('date', '?')})")
    if dtype == "punch_list":
        return continuity.week_digest(day)
    return ""


def _updates_digest(specials: list[dict]) -> str:
    """Continuity specials rendered as one prompt block for the reading
    list's 'Still watching' section. All recorded fact — the drafter
    frames, it never invents."""
    lines = []
    for s in specials:
        try:
            if s.get("dtype") in ("followup", "receipt"):
                arc = s["arc"]
                p = arc.get("pending") or {}
                line = (f"- We covered \"{arc['title']}\" on {arc['opened']} "
                        f"(watching for: {arc.get('watch_for', '')}).")
                if s["dtype"] == "receipt":
                    line += (f" The dated claim \"{arc.get('claim', '')}\" was due "
                             f"{arc.get('due_date', '?')}; outcome: "
                             f"{p.get('outcome', 'no_news')}.")
                if p.get("title"):
                    line += f" Today: {p['title']} — {p.get('note', '')}"
                if p.get("url"):
                    line += f" ({p['url']})"
                lines.append(line)
            elif s.get("dtype") == "record":
                e = s["event"]
                r, prev = e["record"], e["record"].get("previous", {})
                lines.append(
                    f"- RECORD FELL — {e['label']}: {r['value']} {r['unit']} "
                    f"({r['holder']}, {r['date']}); previous "
                    f"{prev.get('value')} {prev.get('unit', r['unit'])} "
                    f"({prev.get('holder', 'unknown')}, {prev.get('date', '?')}).")
        except Exception:  # noqa: BLE001 — a malformed special never blocks
            continue
    if not lines:
        return ""
    return ("UPDATES CONTEXT — stories we're already tracking moved today. "
            "Work these into the 'Still watching' section:\n" + "\n".join(lines))


def _streak_block(day: str) -> str:
    """Recurring names from the knowledge base, injected as selection
    guidance — a streak is a fact, not a take."""
    try:
        lines = knowledge.recurring_entities(day)
    except Exception:  # noqa: BLE001
        return ""
    if not lines:
        return ""
    return ("\n\nRECURRING NAMES (entities that keep showing up in the "
            "research):\n" + "\n".join(lines) +
            "\nIf today's story features one of them, say so factually "
            "('3rd appearance this month') — it signals the story is "
            "developing. Never force it.")


# ---------- LLM engine (Anthropic / OpenAI / local via llm.py) ----------

def _research_block(dtype: str, items: list[ResearchItem]) -> str:
    """Give the drafter real material: title, source, triage's key fact,
    the RSS summary, and — for single-story drafts — the fetched article
    text, so numbers come from the source instead of the model's
    imagination. The reading list skips article text (5 stories would
    blow the prompt) but keeps the key facts."""
    parts = []
    for i in items:
        lines = [f"- {i.title} ({i.url}) [{i.source}]"]
        if i.angle:
            lines.append(f"  Key fact: {i.angle}")
        if i.summary:
            lines.append(f"  Summary: {i.summary[:300]}")
        if i.fulltext and dtype != "reading_list":
            lines.append("  SOURCE MATERIAL (verbatim from the article):\n"
                         + i.fulltext[:2500])
        parts.append("\n".join(lines))
    return "\n".join(parts) or (
        "(no research items today — write something evergreen from the brand topics)"
    )


X_SOLO_MAX = 950  # total ceiling for a solo story-post (3-4 tweets)
X_PARA_MAX = 270  # each paragraph must fit one tweet, with headroom


def _paragraphs(body: str) -> list[str]:
    return [p.strip() for p in body.split("\n\n") if p.strip()]


def _fits_thread(body: str) -> bool:
    return (len(body) <= X_SOLO_MAX
            and all(len(p) <= X_PARA_MAX for p in _paragraphs(body)))


def _tighten_x_post(body: str) -> str:
    """One revision pass when a solo post breaks the thread format. If the
    edit fails or still doesn't fit, keep the original — William can trim
    in review and the X publisher clips rather than drops."""
    edited = llm.complete(
        system=("You edit X story-posts that publish as threads, one "
                "paragraph per tweet. Rewrite so EVERY paragraph is under "
                "270 characters and the whole post is under 950 — split "
                "long paragraphs at natural breaks or cut the weakest "
                "sentences. Keep the hook (first paragraph), every "
                "concrete number, and the paragraph order. Return only "
                "the edited post."),
        user=body,
        max_tokens=600,
    )
    if edited and len(edited) >= 60 and _fits_thread(edited):
        return edited
    return body


def _llm_draft(dtype: str, items: list[ResearchItem], brand: dict,
               day: str, extra_context: str = "") -> str | None:
    """Return draft body text, or None if no provider / call failed."""
    research_block = _research_block(dtype, items)

    if brand.get("persona"):
        identity = (
            "You are THE MASTER BUILDER — the voice of masterbuilder.ai. "
            "Stay in character:\n\n" + brand["persona"].strip() + "\n\n"
        )
    else:
        identity = (
            "You write draft content for the brand masterbuilder.ai.\n"
            "You sound like a builder who learned AI, not an AI pretending to "
            "know construction. Your beat is broad — AI in general, architecture, "
            "construction, robotics, space — but the lens is always the same: "
            "people who get their hands dirty building real things.\n\n"
        )
    system = identity + (
        "Hunt for the CRACKED story: the wild-but-true detail, the concrete "
        "number (span, load, tolerance, cost, days saved), the gap between "
        "the demo and the dirt, the thing a foreman would retell at lunch. "
        "Skip anything that reads like a press release.\n\n"
        "Never invent facts. Only reference facts that appear in the provided "
        "research items. NUMBERS RULE: every number you write (cost, span, "
        "date, count, percentage) must appear verbatim in the research below "
        "— if the source has no number, state the fact without one; never "
        "estimate. Never pretend to be a specific human. No engagement "
        "farming, no politics, no hype.\n\n"
        "HOOK CRAFT (Ship 30 method) — the first line has exactly two jobs: "
        "stop the scroll, then force the reader into the next line. Every "
        "word serves one of those two jobs or gets cut.\n"
        "- Be CLEAR, not clever. The hook must carry the WHO (who this is "
        "for), the WHAT (what happened), and the WHY (the stakes — money, "
        "time, risk, scale). Vague gets scrolled past; clever wordplay that "
        "costs clarity gets cut.\n"
        "- Open with ONE of these proven moves:\n"
        "  * Strong declarative sentence — the boldest true claim in the "
        "source, stated flat. 'The most dangerous dam in the world has been "
        "under repair for 40 years.'\n"
        "  * Moment in time — transport the reader. 'In 1984, engineers "
        "found the foundation dissolving.'\n"
        "  * Wild specific number stated cold — '50,000,000 subscribers in "
        "12 months.' Exact figures only, straight from the source.\n"
        "  * The weird, unique detail — the one fact nobody else would lead "
        "with, the thing a foreman would retell at lunch.\n"
        "  * Sharp contrast — two true facts that collide. 'Building the "
        "bridge took 4 years. Tearing down the old one is the harder job.'\n"
        "- TWIST THE KNIFE: after the opening fact, add the line that makes "
        "it matter — the catch, the cost, the gap, what happens if you "
        "ignore it. Pull it from the research, never invent it.\n"
        "- PAY THE HOOK OFF: the hook stops the scroll; the body must then "
        "deliver the whole story on its own — the background a newcomer "
        "needs, the numbers, why it matters. Never assume the reader saw "
        "an earlier post or knows the project. A hook with no payoff is "
        "clickbait; a post that needs the article to make sense is a "
        "teaser. Write neither.\n"
        "- Specificity IS the credibility: exact numbers, exact timeframes "
        "('over the last 12 months'), exact names. A hook with a real "
        "number beats a hook with an adjective every time.\n"
        "- For threads: tweet 1 must open a curiosity gap AND promise a "
        "clear payoff ('5 stories worth your time today. #3 is the wildest "
        "↓'). The reader should feel unfinished if they don't tap.\n"
        "- NEVER: open with a question, 'Did you know', or a colon-formula "
        "headline; promise what the body doesn't deliver; waste characters "
        "on words that neither stop the scroll nor earn the next line.\n"
        "- Facts stay real. The hook lives in framing, word order, and "
        "which detail leads — not in invented drama. Report, don't opine; "
        "let the reader form the take. Manufactured opinions read as AI; a "
        "hard fact framed sharply doesn't.\n\n"
        f"BRAND VOICE:\n{brand['voice']}\n\n"
        f"BRAND RULES:\n{brand['rules']}\n\n"
        f"BRAND TOPICS:\n{brand['topics']}"
    )

    # Learning loop: the character's own published positions, lessons
    # distilled from William's reviews + real engagement, and exemplar
    # posts that already earned approval/likes.
    ledger = learning.load_ledger()
    if ledger:
        system += ("\n\nALREADY COVERED — stories you've already published. "
                   "Don't repeat them unless today's research adds something "
                   "genuinely new (and then say what's new):\n" + ledger)
    lessons = learning.load_lessons()
    if lessons:
        system += ("\n\nVOICE LESSONS (learned from what got approved, rejected, "
                   "edited, and what the audience engaged with — follow these "
                   "over generic instincts):\n" + lessons)
    exemplars = learning.top_exemplars(3)
    if exemplars:
        shots = "\n\n".join(f"[{e['why']}]\n{e['text']}" for e in exemplars)
        system += ("\n\nEXEMPLARS — real posts that worked. Match their energy "
                   "and concreteness, don't copy their content:\n" + shots)
    system += _streak_block(day)
    url_rule = (
        "Include each item's URL exactly as given in the research.\n"
        if dtype in ("reading_list", "reading_list_substack") else
        "Do not include any URLs in the content — the source link is posted "
        "separately.\n"
    )
    context_block = f"\n{extra_context}\n" if extra_context else ""
    user = (
        f"Today's date: {day}\n\n"
        f"Today's research items:\n{research_block}\n"
        f"{context_block}\n"
        f"Write {TYPE_INSTRUCTIONS[dtype]}.\n"
        + url_rule +
        "Return ONLY the content itself, no preamble, no meta-commentary."
    )
    body = llm.complete(system, user, max_tokens=1500)
    if body and dtype in X_SOLO_TYPES and not _fits_thread(body):
        body = _tighten_x_post(body)
    return body


# ---------- template fallback engine ----------

def _one_liner(item: ResearchItem) -> str:
    """The driest factual line we can build without a model: triage's key
    fact if we have one, else the first sentence of the summary."""
    if item.angle:
        return item.angle.rstrip(".") + "."
    first = (item.summary or "").split(". ")[0].strip()
    if len(first) < 40:  # sentence split tripped on an abbreviation ("U.S.")
        first = (item.summary or "")[:180].strip()
    return (first.rstrip(".") + ".") if first else ""


def _template_draft(dtype: str, items: list[ResearchItem]) -> str:
    lead = items[0] if items else None

    if dtype == "x_post":
        if lead:
            # dry and factual — no manufactured sign-off lines
            return f"{lead.title.rstrip('.')}. {_one_liner(lead)}".strip()
        return (
            "No fresh signal today. Good day to walk the job, update the field "
            "manual, and fix one thing the schedule keeps hiding."
        )

    if dtype in ("reading_list", "reading_list_substack"):
        heading = "# " if dtype == "reading_list_substack" else ""
        lines = [f"{heading}The reading list — {storage.today()}."]
        for item in items[:5]:
            title = f"## {item.title.rstrip('.')}" if heading else item.title.rstrip(".")
            lines.append(f"{title}. {_one_liner(item)}\n{item.url}")
        if len(lines) == 1:
            lines.append("Nothing worth your time today (research run came up "
                         "empty). Back tomorrow.")
        return "\n\n".join(lines)

    if dtype == "essay":
        body = [
            "# Field Manual draft: today's signal",
            "",
            "The gap between AI demos and jobsite reality is where builders get "
            "burned. Here's today's research, read with muddy boots on.",
            "",
        ]
        for item in items[:5]:
            body += [f"## {item.title}", "", f"{item.summary or 'No summary pulled — read the source.'}", "", f"**Builder angle:** {item.why_it_matters_to_builders}", ""]
        body.append(
            "Genchi genbutsu — go see for yourself. Every link below is a "
            "primary source, not a hot take."
        )
        return "\n".join(body)

    if dtype == "content_idea":
        topic = lead.title if lead else "AI hype vs. jobsite reality"
        return (
            "Meme/sticker idea:\n\n"
            f"- Image: split-frame — left, a pristine AI keynote stage; right, a "
            "superintendent in the rain holding a tablet that actually works.\n"
            f"- Caption: \"boots and bits — {topic}\"\n"
            "- Why builders share it: it names the gap they live in every day."
        )

    # unknown/legacy type — plain factual note on the lead story
    if lead:
        return f"{lead.title}. {lead.why_it_matters_to_builders}"
    return "No research pulled today (offline or all sources failed). Check the Logs page."


def _template_special(dtype: str, payload: dict, items: list[ResearchItem],
                      day: str) -> str:
    """Deterministic fallback for continuity drafts — dry, factual, and
    honest about what the ledger knows."""
    if dtype in ("followup", "receipt"):
        arc = payload["arc"]
        p = arc.get("pending") or {}
        if dtype == "receipt":
            outcome = {"hit": "It happened.", "miss": "It slipped.",
                       "no_news": "Deadline passed. No word."}.get(
                           p.get("outcome", "no_news"), "Unclear.")
            claim = arc.get("claim") or arc["title"]
            return (f"On {arc['opened']} the source said: {claim} "
                    f"Due {arc.get('due_date', '?')}. {outcome}")
        note = p.get("note") or p.get("title", "there's movement")
        return (f"UPDATE — we flagged this on {arc['opened']}: "
                f"{arc['title']}. Today: {note}")
    if dtype == "record":
        e = payload["event"]
        r, prev = e["record"], e["record"].get("previous", {})
        return (f"New record — {e['label']}: {r['value']} {r['unit']} "
                f"({r['holder']}). Previous: {prev.get('value')} "
                f"{prev.get('unit', r['unit'])} ({prev.get('holder', 'unknown')}, "
                f"{prev.get('date', '?')}).")
    if dtype == "punch_list":
        return ("# The Punch List — week of " + day + "\n\n"
                + continuity.week_digest(day))
    # segments with no LLM fall back to a plain factual post
    return _template_draft("x_post", items)


# ---------- main entry ----------

def generate_drafts(day: str | None = None) -> tuple[list[Path], str]:
    """Generate the full daily draft set from research/<day>.json.

    Returns (paths, engine) where engine is 'llm:<provider>', 'template',
    or 'mixed' when some drafts fell back.
    """
    day = day or storage.today()
    ranked = triage.prepare(day)  # scored, deduped, best story first
    brand = load_brand()
    created_at = datetime.now().isoformat(timespec="seconds")

    # Continuity: followups/receipts from open arcs + today's broken record.
    # Reading-list model: they don't take slots — they become the "Still
    # watching" UPDATES block inside both reading list formats.
    specials: list[dict] = []
    try:
        specials = continuity.pending_specials(day)
        event = continuity.record_event(day)
        if event:
            specials.append({"dtype": "record", "event": event})
    except Exception as e:  # noqa: BLE001 — continuity never blocks drafting
        log_error(f"[drafting] continuity specials failed: {e}")
        specials = []
    updates_block = _updates_digest(specials)
    slots = plan_slots(day, specials)

    llm_count = 0
    paths: list[Path] = []
    index = 1
    counts: dict[str, int] = {}

    provider = llm.detect_provider()
    log("drafting", f"generating drafts for {day} from {len(ranked)} triaged stories "
                    f"({len(specials)} continuity specials; "
                    f"provider: {provider or 'none — templates'})")

    for slot in slots:
        payload = slot if isinstance(slot, dict) else None
        dtype = payload["dtype"] if payload else slot
        n = counts.get(dtype, 0)
        counts[dtype] = n + 1

        if payload and dtype in ("followup", "receipt"):
            arc = payload["arc"]
            picked = _find_item(ranked, (arc.get("pending") or {}).get("url", ""))
        elif payload and dtype == "record":
            picked = _find_item(ranked, payload["event"]["record"]["source_url"])
        else:
            picked = _assign_items(ranked, dtype, n)

        extra = _special_context(dtype, payload or {}, day)
        if dtype in ("reading_list", "reading_list_substack") and updates_block:
            extra = (extra + "\n\n" + updates_block).strip()
        body = _llm_draft(dtype, picked, brand, day, extra_context=extra)
        if body:
            llm_count += 1
        else:
            body = (_template_special(dtype, payload or {}, picked, day)
                    if payload or dtype == "punch_list"
                    else _template_draft(dtype, picked))
        if dtype in ("essay", "content_idea", "punch_list"):
            # X-bound types carry sources in frontmatter only — the X
            # publisher posts the links as a reply tweet.
            body += _sources_footer(picked)

        # frontmatter sources: today's items, plus — for continuity types —
        # the arc's original sources and our own earlier post, so the
        # receipt is clickable end to end.
        sources = [i.url for i in picked]
        arc_id = ""
        if payload and dtype in ("followup", "receipt"):
            arc = payload["arc"]
            arc_id = arc["id"]
            sources += [u for u in arc.get("source_urls", []) if u not in sources]
            origin = continuity.origin_post_url(arc)
            if origin:
                sources.append(origin)
        elif payload and dtype == "record":
            r = payload["event"]["record"]
            sources += [u for u in (r.get("source_url", ""),
                                    r.get("previous", {}).get("source_url", ""))
                        if u and u not in sources]

        title = f"{TYPE_TITLES[dtype]} {n + 1} — {day}"
        meta = DraftMeta(
            title=title,
            type=dtype,
            status="draft",
            created_at=created_at,
            sources=sources,
            # drafted from the real article = safest; headline-only or
            # unsourced evergreen deserve a harder look before approving
            risk_score=1 if picked and picked[0].fulltext else 2,
            usefulness_score=3,
            originality_score=3,
            arc_id=arc_id,
        )
        path = storage.save_draft(meta, body, day, index=index)
        paths.append(path)
        index += 1

        # image candidates (source photo + fact card) for X-bound drafts —
        # best-effort; a media failure just means a text-only post
        try:
            media.build_for_draft(path)
        except Exception as e:  # noqa: BLE001
            log_error(f"[drafting] media candidates failed for {path.name}: {e}")

        # mark the ledger so a re-run doesn't draft the same update twice
        try:
            if arc_id:
                continuity.mark_drafted(arc_id, path.name)
            elif payload and dtype == "record":
                continuity.mark_record_drafted(day, payload["event"]["category"])
        except Exception as e:  # noqa: BLE001
            log_error(f"[drafting] could not mark continuity ledger: {e}")

        # reading-list model: the specials were consumed by this draft's
        # "Still watching" section — mark them so a re-run doesn't repeat
        if dtype == "reading_list" and updates_block:
            for s in specials:
                try:
                    if s.get("dtype") in ("followup", "receipt"):
                        continuity.mark_drafted(s["arc"]["id"], path.name)
                    elif s.get("dtype") == "record":
                        continuity.mark_record_drafted(day, s["event"]["category"])
                except Exception as e:  # noqa: BLE001
                    log_error(f"[drafting] could not mark continuity ledger: {e}")

    if llm_count == len(paths):
        engine_used = f"llm:{provider}"
    elif llm_count == 0:
        engine_used = "template"
    else:
        engine_used = f"mixed ({llm_count}/{len(paths)} llm:{provider}, rest template)"
    log("drafting", f"saved {len(paths)} drafts to drafts/{day}/ (engine: {engine_used})")
    return paths, engine_used
