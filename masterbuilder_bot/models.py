"""Pydantic models for research items and draft metadata."""

from typing import List

from pydantic import BaseModel, Field

# Research item statuses the dashboard can set.
RESEARCH_STATUSES = ("unreviewed", "useful", "maybe", "ignore")

# Draft types generated each day, and how many of each.
# Direction (2026-07-18): newsletter-first. One daily reading list that
# publishes to the site, plus a Monday weekly digest that goes out as
# email — the best of the past week, not a rehash of every day. The
# picks are the judgment. Continuity (arcs/receipts/records) feeds a
# "Still watching" section INSIDE both formats.
DRAFT_PLAN = [
    ("reading_list", 1),
]

DRAFT_TYPES = [t for t, _ in DRAFT_PLAN] + ["weekly_digest"]

# Continuity dtypes produced by masterbuilder_bot.continuity — no longer
# separate drafts; they become the UPDATES block in the reading list.
CONTINUITY_TYPES = ("followup", "receipt", "record")


def plan_slots(day: str, specials: list) -> list:
    """The day's draft plan as a flat slot list.

    Newsletter model: the daily reading list every day; on Mondays a
    weekly_digest slot joins it (the week's best, emailed). `specials`
    (continuity followups/receipts/records) don't take slots — drafting
    folds them into the list as a "Still watching" section. The
    signature keeps the specials arg so callers don't care.
    """
    from datetime import date

    slots = [t for t, count in DRAFT_PLAN for _ in range(count)]
    if date.fromisoformat(day).weekday() == 0:  # Monday
        slots.append("weekly_digest")
    return slots


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
    # images (masterbuilder_bot/media.py): candidate files relative to the
    # data home; media_choice is what actually attaches to tweet 1 ("" = none)
    media_candidates: List[str] = Field(default_factory=list)
    media_choice: str = ""
