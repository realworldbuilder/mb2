"""Pydantic models for research items and draft metadata."""

from typing import List

from pydantic import BaseModel, Field

# Research item statuses the dashboard can set.
RESEARCH_STATUSES = ("unreviewed", "useful", "maybe", "ignore")

# Draft types generated each day, and how many of each.
# Direction (2026-07-05): report what's happening + curate — no
# manufactured takes. The daily reading list is the flagship.
DRAFT_PLAN = [
    ("x_post", 4),
    ("reading_list", 1),
    ("essay", 1),
    ("content_idea", 1),
]

DRAFT_TYPES = [t for t, _ in DRAFT_PLAN]

# Named weekly segments (date.weekday(): Mon=0). demo_vs_dirt and
# still_standing replace an x_post slot; punch_list replaces the essay
# with the Friday wrap. Changing a segment's day is a one-line edit here.
WEEKLY_SEGMENTS = {0: "demo_vs_dirt", 2: "still_standing", 4: "punch_list"}

# Continuity draft types (followup/receipt/record) also replace x_post
# slots — see plan_slots(). At least one fresh x_post always survives.
CONTINUITY_TYPES = ("followup", "receipt", "record")


def plan_slots(day: str, specials: list) -> list:
    """The day's draft plan as a flat slot list.

    `specials` come from masterbuilder_bot.continuity (dicts with a
    "dtype" key: followup / receipt / record). They replace x_post slots
    from the front — continuity content leads the review queue — but
    never the last one, so every day keeps at least one fresh solo post.
    Weekday segments take one more x_post slot (or the essay slot, for
    Friday's punch_list).
    """
    from datetime import date

    try:
        weekday = date.fromisoformat(day).weekday()
    except ValueError:
        weekday = -1
    segment = WEEKLY_SEGMENTS.get(weekday)

    slots: list = ["x_post"] * 4
    if segment and segment != "punch_list":
        slots[-1] = segment
    cap = sum(1 for s in slots if s == "x_post") - 1
    for i, special in enumerate(specials[:max(0, cap)]):
        slots[i] = special

    essay = "punch_list" if segment == "punch_list" else "essay"
    return slots + ["reading_list", essay, "content_idea"]


class ResearchItem(BaseModel):
    title: str
    url: str
    source: str
    date_found: str
    summary: str = ""
    tags: List[str] = Field(default_factory=list)
    why_it_matters_to_builders: str = ""
    status: str = "unreviewed"
    # Filled by triage (masterbuilder_bot/triage.py); -1 = not scored yet.
    interest_score: int = -1  # 0-10 "would a builder care" score
    angle: str = ""  # the single most concrete fact, per triage
    fulltext: str = ""  # fetched article text (top stories only)


class DraftMeta(BaseModel):
    title: str
    type: str
    status: str = "draft"
    created_at: str
    sources: List[str] = Field(default_factory=list)
    risk_score: int = 1  # 1 = safe, 5 = do not post without a hard look
    usefulness_score: int = 3  # 1 = fluff, 5 = a builder saves real time
    originality_score: int = 3  # 1 = everyone said this, 5 = only us
    arc_id: str = ""  # continuity: which story arc a followup/receipt serves
