"""Turn a day's research into draft content.

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

from masterbuilder_bot import config, learning, llm, storage
from masterbuilder_bot.logging_utils import log
from masterbuilder_bot.models import DRAFT_PLAN, DraftMeta, ResearchItem

TYPE_INSTRUCTIONS = {
    "x_post": (
        "one short X post, under 260 characters, taking a POSITION on the one "
        "story provided — an opinion with a spine, not a recap. First eight "
        "words: the most cracked concrete detail (a number, a failure, a wild "
        "spec). Then the part that's a take: what it means for people who "
        "build real things, what everyone's missing, or what you'd do "
        "differently. Stick to that single story"
    ),
    "x_thread": (
        "one X thread of 4-6 numbered tweets telling the ONE story provided "
        "like a jobsite war story. Tweet 1 is the hook: the wildest fact plus "
        "the outcome, withholding HOW it happened so the reader has to open "
        "the thread. Then walk the build/failure/fix, and end with what a "
        "hands-dirty builder should steal from it. Every tweet is about that "
        "same story — never pad the thread with other topics. Each tweet "
        "under 260 characters"
    ),
    "essay": (
        "one Masterbuilder Field Manual essay draft, 400-700 words, markdown "
        "headers allowed. Pick the single most interesting story in the "
        "research and go deep: the constraint, the numbers, what broke, what "
        "it means for people who build. Field-first, no press-release tone"
    ),
    "content_idea": (
        "one meme / sticker / visual content idea rooted in today's most "
        "cracked story: describe the image, the caption, and why builders "
        "would share it"
    ),
    "builder_signal": (
        "one daily 'builder signal' note: 3-5 bullets, each pairing one "
        "research item with the concrete so-what for builders, plus one "
        "'watch this' item. Rank by how cracked the story is, not how big "
        "the company is"
    ),
}

TYPE_TITLES = {
    "x_post": "X post",
    "x_thread": "X thread",
    "essay": "Field Manual essay",
    "content_idea": "Content idea",
    "builder_signal": "Builder signal",
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


PHYSICAL_TAGS = {"construction", "robotics", "space", "architecture", "design",
                 "hands-on", "hardware", "civil", "nasa", "deep-dive"}


def _pick_items(items: list[ResearchItem], k: int, offset: int) -> list[ResearchItem]:
    """Spread research across drafts: your review marks come first (useful >
    maybe > unreviewed), then physical-world stories beat pure-software ones.
    Rotate by offset so drafts don't all cite the same link."""
    ranked = sorted(
        items,
        key=lambda i: (
            {"useful": 0, "maybe": 1, "unreviewed": 2}.get(i.status, 3),
            0 if set(i.tags) & PHYSICAL_TAGS else 1,  # dirt beats software
        ),
    )
    ranked = [i for i in ranked if i.status != "ignore"]
    if not ranked:
        return []
    picked = [ranked[(offset + j) % len(ranked)] for j in range(min(k, len(ranked)))]
    return list({i.url: i for i in picked}.values())  # dedup, keep order


# ---------- LLM engine (Anthropic / OpenAI / local via llm.py) ----------

def _llm_draft(dtype: str, items: list[ResearchItem], brand: dict) -> str | None:
    """Return draft body text, or None if no provider / call failed."""
    research_block = "\n".join(
        f"- {i.title} ({i.url}) [{i.source}] — {i.summary[:200]}" for i in items
    ) or "(no research items today — write something evergreen from the brand topics)"

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
        "research items. Never pretend to be a specific human. No engagement "
        "farming, no politics, no hype.\n\n"
        "HOOK CRAFT — the first line has two jobs: stop the scroll, then "
        "earn the click/next line. Every word serves one of those or gets "
        "cut.\n"
        "- Open with ONE of: a strong declarative claim, a wild specific "
        "number, a moment in time ('In 2022, a crew...'), or the quiet "
        "opinion pros think but won't say out loud. NEVER open with a "
        "question, 'Did you know', or a colon-formula headline.\n"
        "- Clear beats clever. Concrete beats catchy.\n"
        "- Twist the knife: name the cost or pain (dollars, days, rework, "
        "risk) before the payoff.\n"
        "- A take is a position. Commit to what the story MEANS — what it "
        "changes on a jobsite, what everyone's missing, or where it will "
        "break. A neutral summary is a failed draft.\n\n"
        f"BRAND VOICE:\n{brand['voice']}\n\n"
        f"BRAND RULES:\n{brand['rules']}\n\n"
        f"BRAND TOPICS:\n{brand['topics']}"
    )

    # Learning loop: the character's own published positions, lessons
    # distilled from William's reviews + real engagement, and exemplar
    # posts that already earned approval/likes.
    ledger = learning.load_ledger()
    if ledger:
        system += ("\n\nYOUR TRACK RECORD — positions you have already "
                   "published. Never contradict them; when today's story "
                   "touches one, say so and push the take further. This is "
                   "how the character compounds:\n" + ledger)
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
    user = (
        f"Today's research items:\n{research_block}\n\n"
        f"Write {TYPE_INSTRUCTIONS[dtype]}.\n"
        "Do not include any URLs in the content — the source link is posted "
        "separately.\n"
        "Return ONLY the content itself, no preamble, no meta-commentary."
    )
    return llm.complete(system, user, max_tokens=1500)


# ---------- template fallback engine ----------

def _template_draft(dtype: str, items: list[ResearchItem]) -> str:
    lead = items[0] if items else None

    if dtype == "x_post":
        if lead:
            return (
                f"Current state check: {lead.title}.\n\n"
                f"Why it matters on site: {lead.why_it_matters_to_builders}\n\n"
                "Signal over noise. Read it, then build the thing."
            )
        return (
            "No fresh signal today. Good day to walk the job, update the field "
            "manual, and fix one thing the schedule keeps hiding."
        )

    if dtype == "x_thread":
        lines = ["1/ What builders should actually read today — boots and bits:"]
        for n, item in enumerate(items[:4], start=2):
            lines.append(f"{n}/ {item.title} — {item.why_it_matters_to_builders}")
        lines.append(f"{len(lines) + 1}/ Takeaway: pick ONE of these, test it on a real job, report back. Field manual grows one page at a time.")
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

    # builder_signal
    bullets = [f"- {i.title}: {i.why_it_matters_to_builders}" for i in items[:5]]
    if not bullets:
        bullets = ["- No research pulled today (offline or all sources failed). Check the Logs page."]
    watch = items[0].title if items else "tomorrow's research run"
    return (
        "Builder signal — daily note:\n\n"
        + "\n".join(bullets)
        + f"\n\nWatch this: {watch}"
    )


# ---------- main entry ----------

def generate_drafts(day: str | None = None) -> tuple[list[Path], str]:
    """Generate the full daily draft set from research/<day>.json.

    Returns (paths, engine) where engine is 'openai' or 'template'.
    """
    day = day or storage.today()
    items = storage.load_research(day)
    brand = load_brand()
    created_at = datetime.now().isoformat(timespec="seconds")

    engine_used = "template"
    paths: list[Path] = []
    index = 1

    provider = llm.detect_provider()
    log("drafting", f"generating drafts for {day} from {len(items)} research items "
                    f"(provider: {provider or 'none — templates'})")

    for dtype, count in DRAFT_PLAN:
        for n in range(count):
            # builder_signal is a multi-item roundup; everything else gets
            # exactly ONE story so drafts stay coherent (offset rotation
            # still gives each draft a different story).
            picked = _pick_items(items, k=3 if dtype == "builder_signal" else 1,
                                 offset=index)
            body = _llm_draft(dtype, picked, brand)
            if body:
                engine_used = f"llm:{provider}"
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
                risk_score=1 if picked else 2,  # unsourced evergreen = look harder
                usefulness_score=3,
                originality_score=3,
            )
            paths.append(storage.save_draft(meta, body, day, index=index))
            index += 1

    log("drafting", f"saved {len(paths)} drafts to drafts/{day}/ (engine: {engine_used})")
    return paths, engine_used
