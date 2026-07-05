"""The Masterbuilder knowledge base: a growing local wiki/directory.

Every daily research run gets mined for entities — companies, software,
hardware, building materials, contractors, suppliers, manufacturers,
projects — and each one becomes (or updates) a markdown file in knowledge/:

    knowledge/<slug>.md
        ---
        name / type / summary / url / tags
        first_seen / last_seen / mention_count
        mentions: [{date, title, url, source}, ...]
        ---
        (free-form notes — yours to edit, never overwritten by the bot)

Markdown + YAML frontmatter on purpose: it drops straight into a static
site generator when masterbuilder.ai goes live. The bot only ever touches
frontmatter fields it owns; the body below the frontmatter is human turf.

Extraction uses the same LLM layer as drafting. No provider configured ->
the step skips gracefully and the pipeline continues.
"""

import json
import re
from pathlib import Path
from urllib.parse import urlparse

import frontmatter

from masterbuilder_bot import config, llm, storage
from masterbuilder_bot.logging_utils import log, log_error
from masterbuilder_bot.models import ResearchItem

ENTITY_TYPES = [
    "company", "software", "hardware", "material", "gc", "subcontractor",
    "supplier", "manufacturer", "organization", "project", "robot", "other",
]

BATCH_SIZE = 6  # research items per LLM extraction call (small = more thorough)
MAX_MENTIONS_KEPT = 50  # per entity, newest kept


def knowledge_dir() -> Path:
    return config.data_home() / "knowledge"


# ---------- extraction -----------------------------------------------------------

_EXTRACT_SYSTEM = (
    "You build an industry directory for the construction/AI world. From the "
    "research items, extract EVERY entity that appears BY NAME — in titles OR "
    "summaries. Be exhaustive, not selective: companies, startups, software "
    "products, AI models, hardware, robots, building materials, GCs, "
    "subcontractors, suppliers, manufacturers, agencies (NASA, ESA, OSHA...), "
    "architecture/engineering firms, and named projects or buildings.\n"
    "Most items name 1-3 entities. If you return fewer entities than there "
    "are items, you almost certainly missed some — reread and include them.\n"
    "ONLY skip: people's names, publications/news outlets, and unnamed "
    "generic concepts.\n\n"
    "Return ONLY a JSON array, no prose, no markdown fences. Each element:\n"
    '{"name": "official name", "type": "<one of: ' + ", ".join(ENTITY_TYPES) + '>", '
    '"summary": "one factual sentence on what it is/does", '
    '"url": "official website if you are confident, else empty string", '
    '"from_item": <index of the research item it appeared in>}\n'
    'If unsure of the type use "other". Return [] only if truly none.\n'
    "url rules: ONLY the entity's own official homepage (like https://avride.ai). "
    "NEVER a news article URL, never the URL of the research item itself. "
    "Not sure? Empty string.\n"
    "name rules: must be a specific proper name. NEVER generic descriptions "
    '("humanoid", "a Korean skincare brand"), never governments or '
    "administrations, never people."
)

# ---- junk filters — the model still slips sometimes; code gets the last word ----

_JUNK_NAME_RE = re.compile(
    r"administration|government|ministry|white house|congress|senate|the pentagon",
    re.IGNORECASE)

_GENERIC_WORDS = {
    "humanoid", "robot", "robots", "drone", "drones", "ai", "llm", "llms",
    "startup", "startups", "chatbot", "satellite", "rocket", "crane", "excavator",
}

_GENERIC_TAILS = ("brand", "company", "firm", "startup", "manufacturer",
                  "supplier", "vendor", "agency", "contractor", "developer")

# words that describe rather than name — "Korean skincare brand" is all
# descriptors + a generic tail, so it's a description, not an entity
_DESCRIPTOR_WORDS = {
    "korean", "chinese", "japanese", "american", "european", "german", "french",
    "british", "canadian", "australian", "new", "york", "based", "skincare",
    "robotics", "construction", "ai", "tech", "software", "hardware", "building",
    "concrete", "steel", "timber", "modular", "housing", "architecture", "design",
    "space", "aerospace", "engineering", "electric", "solar", "smart", "local",
}


def _is_junk_name(name: str) -> bool:
    n = name.strip()
    lowered = n.lower()
    if len(n) < 3 or _JUNK_NAME_RE.search(n):
        return True
    if lowered in _GENERIC_WORDS:
        return True
    if lowered.startswith(("a ", "an ", "the ")):
        n = n.split(None, 1)[1] if " " in n else n
        lowered = n.lower()
    # generic tail + nothing but descriptor words before it = a description
    words = lowered.split()
    if words[-1] in _GENERIC_TAILS:
        preceding = [w for w in words[:-1] if w.isalpha()]
        if not preceding or all(w in _DESCRIPTOR_WORDS or w in _GENERIC_TAILS
                                for w in preceding):
            return True
    return False


def _domain(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def _official_url(url: str, article_url: str) -> str:
    """Keep a URL only if it isn't the article (or the article's site)."""
    if not url or not url.startswith("http"):
        return ""
    if _domain(url) == _domain(article_url):
        return ""  # that's the news site, not the entity's homepage
    return url


def _parse_entities(text: str) -> list[dict]:
    """Best-effort JSON array parse — models love to add fences and prose."""
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end <= start:
        return []
    try:
        raw = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return []
    out = []
    for e in raw:
        if not isinstance(e, dict) or not str(e.get("name", "")).strip():
            continue
        etype = str(e.get("type", "other")).lower().strip()
        out.append({
            "name": str(e["name"]).strip()[:120],
            "type": etype if etype in ENTITY_TYPES else "other",
            "summary": str(e.get("summary", "")).strip()[:300],
            "url": str(e.get("url", "")).strip()[:300],
            "from_item": e.get("from_item"),
        })
    return out


def extract_entities(items: list[ResearchItem]) -> list[tuple[dict, ResearchItem]]:
    """LLM-extract entities from research items. Returns (entity, source_item)
    pairs. Empty list if no LLM provider is configured."""
    if llm.detect_provider() is None:
        log("research", "knowledge: no LLM provider — skipping entity extraction")
        return []

    pairs: list[tuple[dict, ResearchItem]] = []
    for batch_start in range(0, len(items), BATCH_SIZE):
        batch = items[batch_start:batch_start + BATCH_SIZE]
        listing = "\n".join(
            f"[{n}] {i.title} ({i.url}) — {i.summary[:150]}"
            for n, i in enumerate(batch)
        )
        text = llm.complete(_EXTRACT_SYSTEM, f"Research items:\n{listing}",
                            max_tokens=1800)
        if not text:
            continue
        for ent in _parse_entities(text):
            idx = ent.pop("from_item", None)
            src = batch[idx] if isinstance(idx, int) and 0 <= idx < len(batch) else batch[0]
            if _is_junk_name(ent["name"]):
                log("research", f"knowledge: filtered junk entity '{ent['name']}'")
                continue
            ent["url"] = _official_url(ent["url"], src.url)
            pairs.append((ent, src))
    return pairs


# ---------- storage ---------------------------------------------------------------

def entity_path(name: str) -> Path:
    return knowledge_dir() / f"{storage.slugify(name, max_len=60)}.md"


def upsert_entity(ent: dict, item: ResearchItem) -> str:
    """Create or update an entity file. Returns 'new' or 'updated'.

    The bot owns the frontmatter; any body text below it is never touched.
    """
    knowledge_dir().mkdir(parents=True, exist_ok=True)
    path = entity_path(ent["name"])
    today = storage.today()
    mention = {"date": today, "title": item.title[:150], "url": item.url,
               "source": item.source}

    if path.exists():
        post = frontmatter.load(str(path))
        status = "updated"
        mentions = post.get("mentions", []) or []
        if not any(m.get("url") == item.url for m in mentions):
            mentions.append(mention)
        post["mentions"] = mentions[-MAX_MENTIONS_KEPT:]
        post["mention_count"] = len(post["mentions"])
        post["last_seen"] = today
        if not post.get("summary") and ent["summary"]:
            post["summary"] = ent["summary"]
        if not post.get("url") and ent["url"]:
            post["url"] = ent["url"]
    else:
        post = frontmatter.Post(
            "",  # body is yours — the bot never writes below the frontmatter
            name=ent["name"], type=ent["type"], summary=ent["summary"],
            url=ent["url"], first_seen=today, last_seen=today,
            mention_count=1, mentions=[mention],
        )
        status = "new"

    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    return status


def build_from_research(day: str | None = None) -> tuple[int, int]:
    """Mine a day's research into the knowledge base. Returns (new, updated)."""
    day = day or storage.today()
    items = storage.load_research(day)
    if not items:
        return 0, 0

    pairs = extract_entities(items)
    new = updated = 0
    seen: set[str] = set()
    for ent, item in pairs:
        key = storage.slugify(ent["name"])
        if not key:
            continue
        try:
            result = upsert_entity(ent, item)
            if key not in seen:
                new += result == "new"
                updated += result == "updated"
                seen.add(key)
        except Exception as e:  # noqa: BLE001 — one bad entity never kills the run
            log_error(f"[knowledge] failed to save '{ent['name']}': {e}")

    log("research", f"knowledge base: {new} new entities, {updated} updated "
                    f"({len(list_entities())} total)")
    return new, updated


# ---------- reading (dashboard) -----------------------------------------------------

def list_entities() -> list[dict]:
    """All entities' frontmatter, newest-seen first. Never raises."""
    d = knowledge_dir()
    if not d.exists():
        return []
    out = []
    for p in d.glob("*.md"):
        try:
            post = frontmatter.load(str(p))
            out.append({
                "slug": p.stem,
                "path": str(p),
                "name": post.get("name", p.stem),
                "type": post.get("type", "other"),
                "summary": post.get("summary", ""),
                "url": post.get("url", ""),
                "first_seen": str(post.get("first_seen", "")),
                "last_seen": str(post.get("last_seen", "")),
                "mention_count": post.get("mention_count", 0),
            })
        except Exception:  # noqa: BLE001
            continue
    return sorted(out, key=lambda e: (e["last_seen"], e["mention_count"]), reverse=True)


def load_entity(slug: str) -> frontmatter.Post | None:
    p = knowledge_dir() / f"{re.sub(r'[^a-z0-9-]', '', slug)}.md"
    return frontmatter.load(str(p)) if p.exists() else None
