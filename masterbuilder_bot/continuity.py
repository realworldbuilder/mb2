"""Continuity: the cross-day memory that strings content together.

The old pipeline woke up every morning with amnesia — every draft was a
one-off fact-drop. This module gives it a memory, so stories can GO
somewhere: callbacks, graded promises, broken records.

Two ledgers, both JSON in memory/:

  arcs.json    — story arcs. Every APPROVED story post registers an arc:
                 what we covered, what to watch for next, and — when the
                 source itself states a dated promise — the claim and its
                 due date (that arc is a "receipt"). Each morning check()
                 matches fresh research against open arcs (-> followup
                 drafts: "We flagged this on <date>. Here's what
                 happened.") and grades receipts whose date has arrived
                 (hit / miss / no_news — the calendar keeps the score).
  records.json — running records ("fastest humanoid half-marathon").
                 update_records() extracts quantified record claims from
                 the day's top stories; when one beats the standing mark,
                 drafting gets a record-broken story that cites the old
                 record. New categories register silently — a record with
                 no predecessor isn't a story yet.

No opinions live here. An arc watches what the SOURCE said; a receipt
grades the source's own dated claim; a record is a number. Reporting.

Everything is best-effort: no LLM -> heuristic or skip; a failure never
blocks review or the daily pipeline.
"""

import json
import re
from pathlib import Path

from masterbuilder_bot import config, llm, storage
from masterbuilder_bot.logging_utils import log, log_error
from masterbuilder_bot.models import ResearchItem

MAX_OPEN_ARCS = 40       # beyond this, the oldest quiet arcs get closed
ARC_STALE_DAYS = 90      # an arc with no updates for this long is dead
MAX_SPECIALS = 2         # followup/receipt drafts per day (they replace x_posts)
MATCH_TOP_N = 15         # research items considered for arc matching
RECORD_TOP_N = 10        # research items scanned for record claims

# Draft types whose approval means "we covered this story" — they open arcs.
# reading_list curates 5 stories, content_idea is a visual brief, and the
# continuity types themselves (followup/receipt/record/punch_list) report on
# existing arcs — none of those should spawn new ones.
ARC_SOURCE_TYPES = {"x_post", "essay", "demo_vs_dirt", "still_standing"}


def arcs_file() -> Path:
    return config.memory_dir() / "arcs.json"


def records_file() -> Path:
    return config.memory_dir() / "records.json"


# ---------- JSON helpers (models love fences and prose) ----------

def _json_between(text: str, open_ch: str, close_ch: str):
    start, end = text.find(open_ch), text.rfind(close_ch)
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001 — a corrupt ledger never kills the run
        log_error(f"[continuity] could not read {path.name}: {e}")
        return default


def _save_json(path: Path, data) -> None:
    config.ensure_data_dirs()
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                    encoding="utf-8")


# ---------- arcs ----------

def load_arcs() -> list[dict]:
    return _load_json(arcs_file(), [])


def save_arcs(arcs: list[dict]) -> None:
    _save_json(arcs_file(), arcs)


def open_arcs(arcs: list[dict] | None = None) -> list[dict]:
    arcs = load_arcs() if arcs is None else arcs
    return [a for a in arcs if a.get("status") in ("open", "updated")]


_EXTRACT_ARC_SYSTEM = (
    "You keep the story-arc ledger for masterbuilder.ai — reporting for "
    "people who build real things. Given a post we just published, decide "
    "what a beat reporter would WATCH FOR next in this story.\n"
    "Return ONLY a JSON object, no prose, no fences:\n"
    '{"title": "short arc name, under 60 chars, names the specific project/'
    'company/thing", '
    '"watch_for": "one concrete line: what future news would advance THIS story", '
    '"claim": "the dated promise/schedule stated in the post, quoted close to '
    'verbatim, or null if the post contains none", '
    '"due_date": "YYYY-MM-DD or null", '
    '"entities": ["named companies/projects in the story"]}\n'
    "due_date rules: ONLY when the post itself states a real timeframe for the "
    "claim. Convert quarters/months to their last day (Q3 2026 -> 2026-09-30, "
    "March 2027 -> 2027-03-31). Vague ('soon', 'coming years') -> null. "
    "Never invent a claim — most posts have none, and null is the right answer."
)


def _heuristic_arc(body: str) -> dict:
    first = next((ln.strip() for ln in body.splitlines() if ln.strip()), "story")
    return {"title": first[:60], "watch_for": "further developments on this story",
            "claim": None, "due_date": None, "entities": []}


def register_from_approval(path: Path) -> dict | None:
    """Open an arc for a just-approved story post. Called from review.approve
    — William's approval IS the signal that a story is worth tracking.
    Never raises; returns the new arc or None."""
    try:
        post = storage.load_post(Path(path))
        dtype = post.get("type", "")
        if dtype not in ARC_SOURCE_TYPES:
            return None
        body = post.content.strip()
        sources = [str(u) for u in (post.get("sources") or [])]
        day = Path(path).parent.name

        arcs = load_arcs()
        # one arc per story: a shared source URL means we already track it
        tracked = {u for a in open_arcs(arcs) for u in a.get("source_urls", [])}
        if sources and any(u in tracked for u in sources):
            return None

        raw = llm.complete(
            _EXTRACT_ARC_SYSTEM,
            f"Published {day}:\n\n{body[:1500]}\n\nSources: {', '.join(sources)}",
            max_tokens=400,
        )
        ext = _json_between(raw, "{", "}") if raw else None
        if not isinstance(ext, dict) or not str(ext.get("watch_for", "")).strip():
            ext = _heuristic_arc(body)

        title = str(ext.get("title") or "")[:60] or _heuristic_arc(body)["title"]
        due = str(ext.get("due_date") or "") or None
        if due and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", due):
            due = None
        arc = {
            "id": f"arc-{day}-{storage.slugify(title)[:40]}",
            "title": title,
            "opened": day,
            "origin_post": Path(path).name,
            "origin_head": body[:300],
            "source_urls": sources,
            "entities": [str(e)[:80] for e in (ext.get("entities") or [])][:5],
            "watch_for": str(ext.get("watch_for", ""))[:200],
            "claim": (str(ext["claim"])[:300] if ext.get("claim") else None),
            "due_date": due,
            "status": "open",
            "updates": [],
            "pending": None,
        }
        if any(a["id"] == arc["id"] for a in arcs):
            arc["id"] += f"-{len(arcs)}"
        arcs.append(arc)
        # keep the ledger honest-sized: close the oldest quiet arcs
        extra = len(open_arcs(arcs)) - MAX_OPEN_ARCS
        if extra > 0:
            for a in sorted(open_arcs(arcs), key=lambda x: x["opened"])[:extra]:
                if not a.get("due_date"):  # never silently drop a receipt
                    a["status"] = "closed"
        save_arcs(arcs)
        kind = "receipt" if arc["due_date"] else "watch"
        log("continuity", f"arc opened ({kind}): {arc['title']}"
                          + (f" — due {arc['due_date']}" if arc["due_date"] else ""))
        return arc
    except Exception as e:  # noqa: BLE001 — never block a review action
        log_error(f"[continuity] register_from_approval failed: {e}")
        return None


_MATCH_SYSTEM = (
    "You match today's news items to open story arcs we are tracking.\n"
    "Match ONLY when the item clearly advances the SAME story — the same "
    "project, company, machine, or claim — not merely the same topic. "
    "'Another humanoid robot' does NOT advance a specific robot's arc.\n"
    "Return ONLY a JSON array, no prose:\n"
    '[{"arc": "<arc id>", "item": <item number>, "note": "one factual line: '
    'what changed since we covered it"}]\n'
    "Return [] when nothing genuinely matches — that is the usual answer."
)

_GRADE_SYSTEM = (
    "You grade a dated claim against a news item. Reply with EXACTLY one "
    "word:\n"
    "hit   — the item shows the claim came true (on time or close)\n"
    "miss  — the item shows it slipped, was cancelled, or failed\n"
    "unclear — the item does not settle it"
)


def _title_tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 3}


def _heuristic_matches(arcs: list[dict], items: list[ResearchItem]) -> list[dict]:
    """No-LLM fallback: two shared meaningful title words, or a named
    entity plus one shared word. Conservative — a wrong followup costs
    more than a missed one, and the LLM does the real matching online."""
    out = []
    for a in arcs:
        ttoks = _title_tokens(a["title"])
        etoks = {t for e in a.get("entities", []) for t in _title_tokens(e)}
        for n, i in enumerate(items):
            itoks = _title_tokens(i.title)
            shared = ttoks & itoks
            if len(shared) >= 2 or (etoks & itoks and shared):
                out.append({"arc": a["id"], "item": n,
                            "note": i.angle or i.title[:120]})
                break
    return out


def check(day: str | None = None) -> dict:
    """The morning continuity pass: close stale arcs, match fresh research
    against open arcs (-> pending followups), grade due receipts. Persists
    everything into arcs.json; drafting picks the results up via
    pending_specials(). Best-effort, never raises."""
    day = day or storage.today()
    summary = {"matched": 0, "graded": 0, "closed": 0}
    try:
        arcs = load_arcs()
        live = open_arcs(arcs)
        if not arcs:
            return summary

        # stale pruning — a quiet arc eventually stops being a story
        for a in live:
            last = max([u["date"] for u in a.get("updates", [])] + [a["opened"]])
            if not a.get("due_date") and (_days_between(last, day) > ARC_STALE_DAYS):
                a["status"] = "closed"
                summary["closed"] += 1
        live = open_arcs(arcs)

        items = sorted(storage.load_research(day),
                       key=lambda i: -i.interest_score)[:MATCH_TOP_N]
        # never "match" an arc to its own origin coverage
        seen_urls = {u for a in live for u in
                     a.get("source_urls", []) + [x["url"] for x in a.get("updates", [])]}
        items = [i for i in items if i.url not in seen_urls]

        matches: list[dict] = []
        if live and items:
            arc_lines = "\n".join(f"{a['id']} | {a['title']} | watching: "
                                  f"{a['watch_for']}" for a in live)
            item_lines = "\n".join(f"{n}. {i.title} — {i.angle or i.summary[:150]}"
                                   for n, i in enumerate(items))
            raw = llm.complete(_MATCH_SYSTEM,
                               f"OPEN ARCS:\n{arc_lines}\n\nTODAY'S ITEMS:\n{item_lines}",
                               max_tokens=600)
            parsed = _json_between(raw, "[", "]") if raw else None
            if isinstance(parsed, list):
                matches = [m for m in parsed if isinstance(m, dict)]
            elif raw is None:
                matches = _heuristic_matches(live, items)

        by_id = {a["id"]: a for a in live}
        for m in matches:
            a = by_id.get(str(m.get("arc", "")))
            n = m.get("item")
            if not a or a.get("pending") or not isinstance(n, int) \
                    or not (0 <= n < len(items)):
                continue
            item = items[n]
            a["pending"] = {"kind": "followup", "day": day, "url": item.url,
                            "title": item.title,
                            "note": str(m.get("note", ""))[:200], "drafted": False}
            summary["matched"] += 1

        # receipts: the calendar keeps the score
        for a in live:
            if not a.get("due_date") or a.get("graded") or a["due_date"] > day:
                continue
            outcome, p = "no_news", a.get("pending") or {}
            if p.get("kind") == "followup":  # today's match may settle it
                word = llm.complete(
                    _GRADE_SYSTEM,
                    f"Claim (made {a['opened']}): {a.get('claim') or a['title']}\n"
                    f"Due: {a['due_date']}\nNews item: {p['title']} — {p['note']}",
                    max_tokens=10)
                w = (word or "").strip().lower()
                outcome = w if w in ("hit", "miss") else "no_news"
            a["graded"] = day
            a["status"] = outcome
            a["pending"] = {"kind": "receipt", "day": day, "outcome": outcome,
                            "url": p.get("url", ""), "title": p.get("title", ""),
                            "note": p.get("note", ""), "drafted": False}
            summary["graded"] += 1

        save_arcs(arcs)
        log("continuity", f"check {day}: {summary['matched']} arc matches, "
                          f"{summary['graded']} receipts graded, "
                          f"{summary['closed']} stale arcs closed "
                          f"({len(open_arcs(arcs))} open)")
    except Exception as e:  # noqa: BLE001 — continuity never kills the pipeline
        log_error(f"[continuity] check failed: {e}")
    return summary


def _days_between(a: str, b: str) -> int:
    from datetime import date
    try:
        return abs((date.fromisoformat(b) - date.fromisoformat(a)).days)
    except ValueError:
        return 0


def pending_specials(day: str | None = None) -> list[dict]:
    """What drafting should write today instead of generic x_posts:
    [{"dtype": "receipt"|"followup", "arc": {...}}], receipts first
    (they're dated), then oldest arcs. Capped at MAX_SPECIALS."""
    day = day or storage.today()
    out = []
    for a in load_arcs():
        p = a.get("pending") or {}
        if p and p.get("day") == day and not p.get("drafted"):
            out.append({"dtype": "receipt" if p["kind"] == "receipt" else "followup",
                        "arc": a})
    out.sort(key=lambda s: (s["dtype"] != "receipt", s["arc"]["opened"]))
    return out[:MAX_SPECIALS]


def mark_drafted(arc_id: str, draft_name: str) -> None:
    """Record that the pending followup/receipt got its draft written."""
    arcs = load_arcs()
    for a in arcs:
        if a["id"] != arc_id or not a.get("pending"):
            continue
        p = a["pending"]
        p["drafted"] = True
        a["updates"] = a.get("updates", []) + [{
            "date": p["day"], "url": p.get("url", ""),
            "note": p.get("note", "") or p.get("outcome", ""),
            "draft": draft_name}]
        if p["kind"] == "followup":
            a["status"] = "updated"
    save_arcs(arcs)


def origin_post_url(arc: dict) -> str:
    """The live URL of the arc's original post, if it got published — so a
    followup's reply tweet can cite our own earlier coverage. Receipts you
    can click."""
    name = arc.get("origin_post", "")
    if not name:
        return ""
    for path in storage.list_posted():
        if path.name == name:
            try:
                return str(storage.load_post(path).get("post_url", "") or "")
            except Exception:  # noqa: BLE001
                return ""
    return ""


def close_arc(arc_id: str) -> bool:
    """Manual close from the dashboard."""
    arcs = load_arcs()
    for a in arcs:
        if a["id"] == arc_id:
            a["status"] = "closed"
            a["pending"] = None
            save_arcs(arcs)
            return True
    return False


# ---------- records ----------

def load_records() -> dict:
    data = _load_json(records_file(), {})
    data.setdefault("records", {})
    data.setdefault("events", [])
    return data


_RECORD_SYSTEM = (
    "You track measurable records for masterbuilder.ai — quantified feats "
    "in AI, construction, robotics, and space.\n"
    "From the news items, extract every RECORD CLAIM: a superlative with a "
    "number, stated in the item itself (fastest, largest, longest, tallest, "
    "first at a stated scale). Skip funding rounds, stock prices, and "
    "unquantified boasts.\n"
    "Return ONLY a JSON array, no prose:\n"
    '[{"category": "short metric label, e.g. \'Humanoid half-marathon time\'", '
    '"value": <number>, "unit": "minutes/meters/GPUs/...", '
    '"holder": "who or what set it", "direction": "max" or "min" (is bigger '
    'or smaller better for this metric), "item": <item number>}]\n'
    "REUSE an existing category label when it is the same metric — that is "
    "how records get broken. Return [] when there are none (most days)."
)


def update_records(day: str | None = None) -> int:
    """Scan the day's top stories for record claims; register new
    categories silently, and stage a 'record broken' event when a standing
    mark falls. Returns the number of new broken-record events."""
    day = day or storage.today()
    broken = 0
    try:
        if llm.detect_provider() is None:
            return 0  # records need real extraction; no guessing
        items = sorted(storage.load_research(day),
                       key=lambda i: -i.interest_score)[:RECORD_TOP_N]
        if not items:
            return 0
        data = load_records()
        existing = ", ".join(r["label"] for r in data["records"].values()) or "(none yet)"
        listing = "\n".join(f"{n}. {i.title} — {i.angle or i.summary[:150]}"
                            for n, i in enumerate(items))
        raw = llm.complete(_RECORD_SYSTEM,
                           f"EXISTING CATEGORIES: {existing}\n\nITEMS:\n{listing}",
                           max_tokens=500)
        claims = _json_between(raw, "[", "]") if raw else None
        if not isinstance(claims, list):
            return 0

        for c in claims:
            try:
                label = str(c["category"]).strip()[:80]
                value = float(c["value"])
                n = c.get("item")
                item = items[n] if isinstance(n, int) and 0 <= n < len(items) else items[0]
                slug = storage.slugify(label, max_len=60)
                direction = "min" if str(c.get("direction", "max")).lower() == "min" else "max"
                entry = {"label": label, "value": value,
                         "unit": str(c.get("unit", ""))[:30],
                         "direction": direction,
                         "holder": str(c.get("holder", ""))[:120],
                         "date": day, "source_url": item.url}
                old = data["records"].get(slug)
                if old is None:
                    data["records"][slug] = entry  # silent: no predecessor, no story
                    continue
                beats = (value > old["value"] if old.get("direction", "max") == "max"
                         else value < old["value"])
                if beats and item.url != old.get("source_url"):
                    entry["direction"] = old.get("direction", direction)
                    entry["previous"] = {k: old.get(k, "") for k in
                                         ("value", "unit", "holder", "date",
                                          "source_url")}
                    data["records"][slug] = entry
                    data["events"].append({"day": day, "category": slug,
                                           "label": label, "record": entry,
                                           "drafted": False})
                    broken += 1
            except (KeyError, TypeError, ValueError):
                continue

        _save_json(records_file(), data)
        if broken:
            log("continuity", f"records: {broken} record(s) broken on {day}")
    except Exception as e:  # noqa: BLE001
        log_error(f"[continuity] update_records failed: {e}")
    return broken


def record_event(day: str | None = None) -> dict | None:
    """Today's first undrafted broken-record event (at most one fires/day)."""
    day = day or storage.today()
    for e in load_records()["events"]:
        if e["day"] == day and not e.get("drafted"):
            return e
    return None


def mark_record_drafted(day: str, category: str) -> None:
    data = load_records()
    for e in data["events"]:
        if e["day"] == day and e["category"] == category:
            e["drafted"] = True
    _save_json(records_file(), data)


# ---------- the week, for Friday's Punch List ----------

def week_digest(day: str | None = None) -> str:
    """The week's raw material: top stories per research day (newest last)
    plus what we published. Feeds the punch_list draft."""
    day = day or storage.today()
    days = sorted(d for d in storage.research_days() if d <= day)[-5:]
    lines = []
    for d in days:
        top = sorted(storage.load_research(d), key=lambda i: -i.interest_score)[:3]
        for i in top:
            lines.append(f"- {d}: {i.title} — {i.angle or i.summary[:120]}"
                         f" ({i.url})")
    published = []
    for path in storage.list_posted() + storage.list_approved():
        if path.parent.name in days:
            try:
                published.append(
                    "- " + storage.load_post(path).content.strip().splitlines()[0][:140])
            except Exception:  # noqa: BLE001
                continue
    out = "THE WEEK'S TOP STORIES:\n" + ("\n".join(lines) or "(no research this week)")
    if published:
        out += "\n\nWHAT WE PUBLISHED THIS WEEK:\n" + "\n".join(published[:10])
    return out
