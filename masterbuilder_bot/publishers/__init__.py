"""Platform publishers: X, LinkedIn, Substack.

Each publisher module exposes:
    is_configured() -> bool          # are the env keys present?
    missing_keys()  -> list[str]     # which env keys still need values
    test()          -> dict          # cheap live check: {"ok": bool, "detail": str}
    publish(text, title, sources) -> dict   # {"ok", "url", "id", "detail"}

Routing: each draft type has a home platform. content_idea stays
internal (it's a visual brief, not a post).
"""

from masterbuilder_bot.publishers import linkedin, substack, x

PLATFORMS = {
    "x": x,
    "linkedin": linkedin,
    "substack": substack,
}

# Where each draft type gets published by default.
# LinkedIn is wired but OFF by William's choice (2026-07-05): he doesn't
# want automated posts on his personal profile. builder_signal goes to X
# as a thread instead. Re-enable by mapping a type back to "linkedin".
PLATFORM_FOR_TYPE = {
    "x_post": "x",
    "x_thread": "x",
    "essay": "substack",
    "builder_signal": "x",
    "content_idea": None,
}

PLATFORM_LABELS = {
    "x": "X (Twitter)",
    "linkedin": "LinkedIn",
    "substack": "Substack",
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
