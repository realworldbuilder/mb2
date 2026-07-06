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

from masterbuilder_bot import config, learning, llm, storage, triage
from masterbuilder_bot.logging_utils import log
from masterbuilder_bot.models import DRAFT_PLAN, DraftMeta, ResearchItem

TYPE_INSTRUCTIONS = {
    "x_post": (
        "one short X post, under 260 characters, on the one story provided. "
        "Structure: HOOK line first (per HOOK CRAFT — declarative claim, "
        "moment in time, cold number, weird detail, or contrast), then the "
        "knife twist — the catch, cost, or gap that makes it matter, taken "
        "straight from the research. Plain language, no manufactured "
        "opinion, no 'here's my take'. Stick to that single story"
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
        "characters including the URL. No opinions, no ranking commentary "
        "— the picks ARE the judgment"
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
}

TYPE_TITLES = {
    "x_post": "X post",
    "reading_list": "Reading list",
    "essay": "Field Manual essay",
    "content_idea": "Content idea",
}


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
    if dtype == "reading_list":
        return ranked[:5]
    if dtype == "x_post":
        return [ranked[n % len(ranked)]]
    return [ranked[0]]


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


X_POST_MAX = 260  # solo posts must fit in one tweet, with headroom


def _tighten_x_post(body: str) -> str:
    """One revision pass when a solo post runs long. If the edit fails or
    is still long, keep the original — William can trim in review and the
    X publisher would thread it rather than clip it."""
    edited = llm.complete(
        system=("You tighten X posts. Cut the text to UNDER 260 characters. "
                "Keep every concrete number and the hook (the opening line); "
                "cut adjectives, asides, and the weakest sentence. Return "
                "only the edited post."),
        user=body,
        max_tokens=300,
    )
    if edited and len(edited) <= X_POST_MAX and len(edited) >= 60:
        return edited
    return body


def _llm_draft(dtype: str, items: list[ResearchItem], brand: dict,
               day: str) -> str | None:
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
    url_rule = (
        "Include each item's URL exactly as given in the research.\n"
        if dtype == "reading_list" else
        "Do not include any URLs in the content — the source link is posted "
        "separately.\n"
    )
    user = (
        f"Today's date: {day}\n\n"
        f"Today's research items:\n{research_block}\n\n"
        f"Write {TYPE_INSTRUCTIONS[dtype]}.\n"
        + url_rule +
        "Return ONLY the content itself, no preamble, no meta-commentary."
    )
    body = llm.complete(system, user, max_tokens=1500)
    if body and dtype == "x_post" and len(body) > X_POST_MAX:
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

    if dtype == "reading_list":
        lines = [f"The reading list — {storage.today()}."]
        for item in items[:5]:
            lines.append(f"{item.title.rstrip('.')}. {_one_liner(item)}\n{item.url}")
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

    llm_count = 0
    paths: list[Path] = []
    index = 1

    provider = llm.detect_provider()
    log("drafting", f"generating drafts for {day} from {len(ranked)} triaged stories "
                    f"(provider: {provider or 'none — templates'})")

    for dtype, count in DRAFT_PLAN:
        for n in range(count):
            picked = _assign_items(ranked, dtype, n)
            body = _llm_draft(dtype, picked, brand, day)
            if body:
                llm_count += 1
            else:
                body = _template_draft(dtype, picked)
            if dtype in ("essay", "content_idea"):
                # X-bound types carry sources in frontmatter only — the X
                # publisher posts the links as a reply tweet.
                body += _sources_footer(picked)

            title = f"{TYPE_TITLES[dtype]} {n + 1} — {day}"
            meta = DraftMeta(
                title=title,
                type=dtype,
                status="draft",
                created_at=created_at,
                sources=[i.url for i in picked],
                # drafted from the real article = safest; headline-only or
                # unsourced evergreen deserve a harder look before approving
                risk_score=1 if picked and picked[0].fulltext else 2,
                usefulness_score=3,
                originality_score=3,
            )
            paths.append(storage.save_draft(meta, body, day, index=index))
            index += 1

    if llm_count == len(paths):
        engine_used = f"llm:{provider}"
    elif llm_count == 0:
        engine_used = "template"
    else:
        engine_used = f"mixed ({llm_count}/{len(paths)} llm:{provider}, rest template)"
    log("drafting", f"saved {len(paths)} drafts to drafts/{day}/ (engine: {engine_used})")
    return paths, engine_used
