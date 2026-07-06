"""Triage: pick the day's best stories BEFORE drafting.

This is the editor's desk. Research pulls ~40 headlines; drafting should
only ever see the ones worth a builder's time. Order of signal:

  1. William's review marks — useful > maybe > unreviewed; ignore is dropped.
  2. LLM interest score (0-10) through the builder lens: concrete numbers,
     physical-world work, the gap between the demo and the dirt.
  3. Heuristic fallback (physical tags, numbers in the title, press-release
     smell) when no LLM is configured or the call fails.

It also collapses near-duplicate stories (same event from two outlets) and
fetches full article text for the top stories, so drafts are written from
real material instead of a headline and a 200-character RSS blurb — the
single biggest reason drafts used to invent numbers.

Scores, angles, and fetched text are persisted back into the day's
research JSON, so re-drafting from the dashboard doesn't re-pay for triage.
"""

import re

from masterbuilder_bot import llm, storage
from masterbuilder_bot.logging_utils import log, log_error
from masterbuilder_bot.models import ResearchItem

USER_AGENT = "masterbuilder-bot/0.1 (local research agent)"
SCORE_BATCH = 12          # items per LLM scoring call — small enough for local models
ENRICH_TOP_N = 8          # how many top stories get their article text fetched
FULLTEXT_CHARS = 4000     # cap per article

PHYSICAL_TAGS = {"construction", "robotics", "space", "architecture", "design",
                 "hands-on", "hardware", "civil", "nasa", "deep-dive", "contech"}

_PRESS_RELEASE_WORDS = ("announc", "unveil", "partners with", "partnership",
                        "launches", "opinion", "why you", "how to", "top 10",
                        "the best ")

SCORE_SYSTEM = (
    "You are the editor for masterbuilder.ai — content for people who build "
    "real things (AI, construction, robotics, space, architecture).\n"
    "Score each numbered story 0-10 for how interesting AND useful it is to "
    "an actual builder:\n"
    "  9-10 = wild but true: a concrete number, cost, failure, or spec a "
    "foreman would retell at lunch\n"
    "  6-8  = solid field signal: a real project, real machine, real "
    "constraint, real money\n"
    "  3-5  = relevant industry news, but no meat\n"
    "  0-2  = press release, opinion piece, listicle, consumer-tech fluff\n"
    "Physical-world stories beat pure-software ones. Primary reporting beats "
    "commentary about it.\n\n"
    "Reply with EXACTLY one line per story, in this format and nothing else:\n"
    "<story number> | <score> | <the single most concrete fact in the story, "
    "under 15 words, or 'none stated'>"
)

_SCORE_LINE = re.compile(r"^\s*(\d+)\s*[|:.\-]\s*(\d{1,2})\s*[|:.\-]?\s*(.*)$")


# ---------- scoring ----------

def _is_physical(item: ResearchItem) -> bool:
    """Substring match so 'construction-tech' or 'construction_technology'
    still counts as construction — tag spellings drift with the config."""
    return any(phys in tag.lower() for tag in item.tags for phys in PHYSICAL_TAGS)


def _heuristic_score(item: ResearchItem) -> int:
    """No-LLM fallback: crude but directionally right."""
    score = 5
    if _is_physical(item):
        score += 2
    if re.search(r"\d", item.title):
        score += 1
    lower = item.title.lower()
    if any(w in lower for w in _PRESS_RELEASE_WORDS):
        score -= 2
    if "?" in item.title:
        score -= 1
    return max(0, min(10, score))


def _llm_score_batch(batch: list[ResearchItem]) -> dict[int, tuple[int, str]]:
    """One scoring call for up to SCORE_BATCH items.
    Returns {position-in-batch: (score, key_fact)} for every line that parses."""
    numbered = "\n".join(
        f"{j + 1}. {i.title} [{i.source}] — {i.summary[:250]}"
        for j, i in enumerate(batch)
    )
    text = llm.complete(SCORE_SYSTEM, numbered, max_tokens=800)
    if not text:
        return {}
    out: dict[int, tuple[int, str]] = {}
    for line in text.splitlines():
        m = _SCORE_LINE.match(line.strip())
        if not m:
            continue
        idx = int(m.group(1)) - 1
        if 0 <= idx < len(batch):
            score = max(0, min(10, int(m.group(2))))
            fact = m.group(3).strip().strip('"')
            if fact.lower() in ("none stated", "none", "-", ""):
                fact = ""
            out[idx] = (score, fact)
    return out


def score_items(items: list[ResearchItem]) -> int:
    """Fill in interest_score/angle for items that don't have one yet.
    Returns how many were scored by the LLM (vs. heuristic)."""
    need = [i for i in items if i.interest_score < 0]
    llm_scored = 0
    for start in range(0, len(need), SCORE_BATCH):
        batch = need[start:start + SCORE_BATCH]
        scored = _llm_score_batch(batch)
        for j, item in enumerate(batch):
            if j in scored:
                item.interest_score, fact = scored[j]
                if fact:
                    item.angle = fact
                llm_scored += 1
            else:
                item.interest_score = _heuristic_score(item)
    return llm_scored


# ---------- duplicate collapse ----------

def _title_words(title: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", title.lower()) if len(w) > 3}


def _dedup(ranked: list[ResearchItem]) -> list[ResearchItem]:
    """Drop near-duplicate stories (same event covered by two outlets),
    keeping the higher-ranked one. Title-word overlap is cheap and enough."""
    kept: list[ResearchItem] = []
    for item in ranked:
        words = _title_words(item.title)
        dup = False
        for prev in kept:
            pwords = _title_words(prev.title)
            union = words | pwords
            if union and len(words & pwords) / len(union) >= 0.6:
                dup = True
                break
        if not dup:
            kept.append(item)
    return kept


# ---------- article text ----------

def enrich(items: list[ResearchItem], top_n: int = ENRICH_TOP_N,
           timeout: int = 15) -> int:
    """Fetch full article text for the top stories so the drafter has real
    material (the actual numbers, the actual quotes). Best effort — a dead
    page just means that story keeps only its RSS summary."""
    import requests
    from bs4 import BeautifulSoup

    fetched = 0
    for item in items[:top_n]:
        if item.fulltext:
            continue
        try:
            resp = requests.get(item.url, timeout=timeout,
                                headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "header", "footer",
                             "aside", "form", "figure"]):
                tag.decompose()
            node = soup.find("article") or soup.find("main") or soup.body or soup
            paras = [p.get_text(" ", strip=True) for p in node.find_all("p")]
            text = "\n".join(p for p in paras if len(p) > 60)
            if text:
                item.fulltext = text[:FULLTEXT_CHARS]
                fetched += 1
        except Exception as e:  # noqa: BLE001 — one dead page never kills triage
            log_error(f"[triage] fetch failed for {item.url}: {type(e).__name__}: {e}")
    return fetched


# ---------- main entry ----------

def rank(items: list[ResearchItem]) -> list[ResearchItem]:
    """Best story first. Review marks dominate, then interest score."""
    live = [i for i in items if i.status != "ignore"]
    order = {"useful": 0, "maybe": 1}
    ranked = sorted(live, key=lambda i: (order.get(i.status, 2), -i.interest_score))
    return _dedup(ranked)


def prepare(day: str | None = None) -> list[ResearchItem]:
    """Score + rank + enrich the day's research; persist results.
    Returns the ranked list drafting should use. Idempotent — already-scored
    items and already-fetched articles are skipped."""
    day = day or storage.today()
    items = storage.load_research(day)
    if not items:
        return []
    llm_scored = score_items(items)
    ranked = rank(items)
    fetched = enrich(ranked)
    storage.save_research(items, day)  # ranked shares the same objects
    log("triage", f"{len(items)} items -> {len(ranked)} after review marks + dedup "
                  f"({llm_scored} LLM-scored, {fetched} articles fetched); "
                  f"top story: {ranked[0].title[:80] if ranked else 'n/a'}")
    return ranked
