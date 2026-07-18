"""Platform publishers: X, LinkedIn, Substack.

Each publisher module exposes:
    is_configured() -> bool          # are the env keys present?
    missing_keys()  -> list[str]     # which env keys still need values
    test()          -> dict          # cheap live check: {"ok": bool, "detail": str}
    publish(text, title, sources) -> dict   # {"ok", "url", "id", "detail"}

Routing: each draft type has a home platform. content_idea stays
internal (it's a visual brief, not a post).
"""

from masterbuilder_bot.publishers import buttondown, linkedin, substack, x

PLATFORMS = {
    "x": x,
    "linkedin": linkedin,
    "substack": substack,
    "buttondown": buttondown,
}

# Where each draft type gets published by default.
# Newsletter-first model (2026-07-18): the daily reading list publishes
# to the SITE only (platform None — build_site renders approved/), the
# Monday weekly_digest goes out as email via Buttondown. X auto-posting
# is retired — the API costs money and buries link posts; the x module
# stays wired for a possible manual/paid future.
# LinkedIn is wired but OFF by William's choice (2026-07-05).
PLATFORM_FOR_TYPE = {
    "reading_list": None,       # site-only: approved/ -> build_site
    "weekly_digest": "buttondown",
    "content_idea": None,
    # legacy types (no longer generated, may exist in approved/):
    "x_post": None,
    "reading_list_substack": "substack",
    "essay": "substack",
    "followup": None,
    "receipt": None,
    "record": None,
    "demo_vs_dirt": None,
    "still_standing": None,
    "punch_list": "substack",
    "x_thread": None,
    "builder_signal": None,
}

PLATFORM_LABELS = {
    "x": "X (Twitter)",
    "linkedin": "LinkedIn",
    "substack": "Substack",
    "buttondown": "Buttondown (email)",
}


def platform_for(dtype: str) -> str | None:
    return PLATFORM_FOR_TYPE.get(dtype)


def get(platform: str):
    if platform not in PLATFORMS:
        raise ValueError(f"unknown platform: {platform!r} (know: {list(PLATFORMS)})")
    return PLATFORMS[platform]


def status() -> dict:
    """Configured yes/no per platform, for the dashboard. No secrets."""
    return {
        name: {
            "configured": mod.is_configured(),
            "missing": mod.missing_keys(),
            "label": PLATFORM_LABELS[name],
        }
        for name, mod in PLATFORMS.items()
    }
