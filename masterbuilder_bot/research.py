"""Daily research: pull items from RSS feeds and simple web pages.

Every source is isolated — one bad feed logs a warning and is skipped,
it never kills the run. If everything fails (e.g., offline), we still
write a valid (possibly empty) research/YYYY-MM-DD.json.
"""

import yaml

from masterbuilder_bot import config, storage
from masterbuilder_bot.logging_utils import log, log_error
from masterbuilder_bot.models import ResearchItem

DEFAULT_TIMEOUT = 15
DEFAULT_MAX_PER_SOURCE = 5
DEFAULT_MAX_TOTAL = 40

USER_AGENT = "masterbuilder-bot/0.1 (local research agent)"


def load_sources() -> dict:
    """Parse config/sources.yaml. Raises if the file is missing/invalid —
    the config is the heart of the bot, so a broken one should be loud."""
    with open(config.SOURCES_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    data.setdefault("categories", {})
    data.setdefault("limits", {})
    return data


def enabled_sources(data: dict | None = None) -> list[dict]:
    """Flatten categories into a list of enabled sources, each tagged
    with its category name."""
    data = data or load_sources()
    out = []
    for category, sources in (data.get("categories") or {}).items():
        for src in sources or []:
            if src.get("enabled"):
                out.append({**src, "category": category})
    return out


def _fetch_rss(src: dict, limit: int, timeout: int) -> list[ResearchItem]:
    import feedparser
    import requests

    # Fetch the feed ourselves so the timeout is real — feedparser's own
    # URL fetching has none, and one dead feed used to hang the whole run.
    resp = requests.get(src["url"], timeout=timeout,
                        headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    if feed.get("bozo") and not feed.get("entries"):
        raise RuntimeError(f"feed error: {feed.get('bozo_exception', 'unparseable')}")
    items = []
    for entry in feed.entries[:limit]:
        title = (entry.get("title") or "").strip()
        url = (entry.get("link") or "").strip()
        if not title or not url:
            continue
        summary = _clean_html(entry.get("summary", ""))[:500]
        items.append(_make_item(src, title, url, summary))
    return items


def _fetch_web(src: dict, limit: int, timeout: int) -> list[ResearchItem]:
    """Very simple page scrape: grab headline-ish links. Best effort only —
    RSS is always preferred."""
    import requests
    from bs4 import BeautifulSoup

    resp = requests.get(src["url"], timeout=timeout, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    items, seen = [], set()
    for tag in soup.find_all(["h1", "h2", "h3"]):
        a = tag.find("a") or (tag.parent if tag.parent and tag.parent.name == "a" else None)
        if a is None or not a.get("href"):
            continue
        title = tag.get_text(" ", strip=True)
        url = requests.compat.urljoin(src["url"], a["href"])
        if len(title) < 15 or url in seen:
            continue
        seen.add(url)
        items.append(_make_item(src, title, url, ""))
        if len(items) >= limit:
            break
    return items


def _clean_html(html: str) -> str:
    from bs4 import BeautifulSoup

    return BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)


def _make_item(src: dict, title: str, url: str, summary: str) -> ResearchItem:
    category = src.get("category", "")
    tags = list(dict.fromkeys([*src.get("tags", []), category]))  # dedup, keep order
    return ResearchItem(
        title=title,
        url=url,
        source=src["name"],
        date_found=storage.today(),
        summary=summary,
        tags=[t for t in tags if t],
        why_it_matters_to_builders=_builder_angle(category),
        status="unreviewed",
    )


def _builder_angle(category: str) -> str:
    """Starter 'why it matters' line by category. The drafting step (and
    you, in the dashboard) sharpen this per item."""
    angles = {
        "ai_general": "Big AI move — translate it into what someone who builds real things does differently Monday.",
        "architecture_design": "Real project, real materials — look for the constraint that made it interesting.",
        "construction": "Field signal — schedules, trades, QA/QC, the stuff that actually sinks projects.",
        "robotics": "A machine doing real work. Watch which tasks get automated and what breaks.",
        "space": "Hard-hat frontier — extreme building: tolerances, logistics, and failure stories worth stealing from.",
        "hands_on_builders": "Someone got their hands dirty. Find the lesson a foreman would retell at lunch.",
    }
    return angles.get(category, "Possible builder angle — needs a human read.")


def run_daily_research(day: str | None = None) -> tuple[list[ResearchItem], list[str]]:
    """Fetch all enabled sources, save research/<day>.json.

    Returns (items, error_strings). Never raises on per-source failure.
    """
    data = load_sources()
    limits = data.get("limits") or {}
    per_source = int(limits.get("max_items_per_source", DEFAULT_MAX_PER_SOURCE))
    max_total = int(limits.get("max_items_total", DEFAULT_MAX_TOTAL))
    timeout = int(limits.get("fetch_timeout_seconds", DEFAULT_TIMEOUT))

    sources = enabled_sources(data)
    log("research", f"starting research run: {len(sources)} enabled sources")

    # per category: one list of items per source, kept separate so we can
    # give every source a fair turn (not just the ones listed first)
    by_category: dict[str, list[list[ResearchItem]]] = {}
    errors: list[str] = []
    seen_urls: set[str] = set()

    for src in sources:
        try:
            fetch = _fetch_rss if src.get("type") == "rss" else _fetch_web
            # per-source max_items overrides the global limit — use it to keep
            # high-volume generic feeds from drowning out the niche ones
            limit = int(src.get("max_items", per_source))
            items = fetch(src, limit, timeout)
            fresh = [i for i in items if i.url not in seen_urls]
            seen_urls.update(i.url for i in fresh)
            if fresh:
                by_category.setdefault(src.get("category", "other"), []).append(fresh)
            log("research", f"{src['name']}: {len(fresh)} items")
        except Exception as e:  # noqa: BLE001 — isolate every source failure
            msg = f"{src['name']} failed: {type(e).__name__}: {e}"
            errors.append(msg)
            log_error(f"[research] {msg}")

    def interleave(lists: list[list[ResearchItem]]) -> list[ResearchItem]:
        """Take one item from each list in turn until all are empty."""
        out: list[ResearchItem] = []
        while any(lists):
            for lst in lists:
                if lst:
                    out.append(lst.pop(0))
        return out

    # Fairness at both levels: sources take turns within their category,
    # then categories take turns filling the day's list — so neither a loud
    # feed nor a loud beat can flood the budget.
    all_items: list[ResearchItem] = []
    queues = [interleave(source_lists) for source_lists in by_category.values()]
    while queues and len(all_items) < max_total:
        for q in list(queues):
            if not q:
                queues.remove(q)
                continue
            all_items.append(q.pop(0))
            if len(all_items) >= max_total:
                break
    path = storage.save_research(all_items, day)
    log("research", f"saved {len(all_items)} items to {path.name} ({len(errors)} source errors)")
    return all_items, errors
