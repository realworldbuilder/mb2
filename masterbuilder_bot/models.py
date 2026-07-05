"""Pydantic models for research items and draft metadata."""

from typing import List

from pydantic import BaseModel, Field

# Research item statuses the dashboard can set.
RESEARCH_STATUSES = ("unreviewed", "useful", "maybe", "ignore")

# Draft types generated each day, and how many of each.
DRAFT_PLAN = [
    ("x_post", 5),
    ("x_thread", 2),
    ("essay", 1),
    ("content_idea", 1),
    ("builder_signal", 1),
]

DRAFT_TYPES = [t for t, _ in DRAFT_PLAN]


class ResearchItem(BaseModel):
    title: str
    url: str
    source: str
    date_found: str
    summary: str = ""
    tags: List[str] = Field(default_factory=list)
    why_it_matters_to_builders: str = ""
    status: str = "unreviewed"


class DraftMeta(BaseModel):
    title: str
    type: str
    status: str = "draft"
    created_at: str
    sources: List[str] = Field(default_factory=list)
    risk_score: int = 1  # 1 = safe, 5 = do not post without a hard look
    usefulness_score: int = 3  # 1 = fluff, 5 = a builder saves real time
    originality_score: int = 3  # 1 = everyone said this, 5 = only us
