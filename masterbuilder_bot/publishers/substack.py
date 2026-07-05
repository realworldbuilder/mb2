"""Substack publisher — creates a draft on your Substack (default) or
publishes directly if SUBSTACK_AUTO_PUBLISH=true.

Substack has NO official API. This uses the community `python-substack`
library, which logs in with your normal Substack email + password. That
means:
  * env keys: SUBSTACK_EMAIL, SUBSTACK_PASSWORD, SUBSTACK_PUBLICATION_URL
    (e.g. https://masterbuilder.substack.com)
  * default behavior is DRAFT-ONLY — the essay lands in your Substack
    drafts, you eyeball the email preview and hit Publish there. That's
    one more approval gate on the platform where mistakes email people.
  * if Substack changes their internal API or challenges the login
    (captcha), publishing fails loudly and the file stays in approved/.
"""

import os
import re

from masterbuilder_bot.logging_utils import log, log_error

REQUIRED_KEYS = ("SUBSTACK_EMAIL", "SUBSTACK_PASSWORD", "SUBSTACK_PUBLICATION_URL")


def missing_keys() -> list[str]:
    return [k for k in REQUIRED_KEYS if not os.environ.get(k, "").strip()]


def is_configured() -> bool:
    return not missing_keys()


def auto_publish() -> bool:
    return os.environ.get("SUBSTACK_AUTO_PUBLISH", "").strip().lower() in ("1", "true", "yes")


def _api():
    from substack import Api  # import here: optional dependency

    return Api(
        email=os.environ["SUBSTACK_EMAIL"].strip(),
        password=os.environ["SUBSTACK_PASSWORD"].strip(),
        publication_url=os.environ["SUBSTACK_PUBLICATION_URL"].strip(),
    )


def test() -> dict:
    if not is_configured():
        return {"ok": False, "detail": f"missing keys: {', '.join(missing_keys())}"}
    try:
        api = _api()
        user_id = api.get_user_id()
        return {"ok": True, "detail": f"logged in (user id {user_id})"}
    except ImportError:
        return {"ok": False, "detail": "python-substack not installed — "
                                       "run: pip install python-substack"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "detail": f"{type(e).__name__}: {e} "
                                       "(wrong password, or Substack challenged the login)"}


def _md_inline(text: str) -> str:
    """Strip markdown inline markers Substack would show literally."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"\1", text)
    text = re.sub(r"\[(.+?)\]\((\S+?)\)", r"\1 (\2)", text)  # links: keep both
    return text


def _md_to_blocks(markdown: str) -> list[dict]:
    """Cheap markdown -> Substack draft blocks. Headers and paragraphs;
    bullet lines become bulleted paragraphs. Good enough for a draft you
    polish in Substack's editor."""
    blocks: list[dict] = []
    for para in re.split(r"\n\s*\n", markdown.strip()):
        para = para.strip()
        if not para:
            continue
        if para.startswith("### "):
            blocks.append({"type": "heading-three", "content": _md_inline(para[4:])})
        elif para.startswith("## "):
            blocks.append({"type": "heading-two", "content": _md_inline(para[3:])})
        elif para.startswith("# "):
            blocks.append({"type": "heading-two", "content": _md_inline(para[2:])})
        elif para == "---":
            continue
        elif all(line.lstrip().startswith(("- ", "* ")) for line in para.splitlines()):
            bullets = "\n".join("• " + _md_inline(line.lstrip()[2:])
                                for line in para.splitlines())
            blocks.append({"type": "paragraph", "content": bullets})
        else:
            blocks.append({"type": "paragraph",
                           "content": _md_inline(para.replace("\n", " "))})
    return blocks or [{"type": "paragraph", "content": markdown.strip()[:5000]}]


def _title_from(text: str, fallback: str) -> tuple[str, str]:
    """(title, remaining_body): first '# ' header becomes the post title."""
    lines = text.strip().splitlines()
    if lines and lines[0].startswith("# "):
        return lines[0][2:].strip(), "\n".join(lines[1:]).strip()
    return fallback, text


def publish(text: str, title: str = "", sources: list | None = None) -> dict:
    """Create a Substack draft (or publish, if SUBSTACK_AUTO_PUBLISH)."""
    if not is_configured():
        return {"ok": False, "id": "", "url": "",
                "detail": f"Substack not configured (missing: {', '.join(missing_keys())})"}
    try:
        from substack.post import Post

        api = _api()
        post_title, body = _title_from(text, title or "Field Manual note")
        post = Post(title=post_title,
                    subtitle="boots and bits — from the Masterbuilder Field Manual",
                    user_id=api.get_user_id())
        for block in _md_to_blocks(body):
            post.add(block)
        draft = api.post_draft(post.get_draft())
        draft_id = draft.get("id", "")
        pub = os.environ["SUBSTACK_PUBLICATION_URL"].strip().rstrip("/")

        if auto_publish():
            api.prepublish_draft(draft_id)
            published = api.publish_draft(draft_id)
            slug = published.get("slug", "")
            url = f"{pub}/p/{slug}" if slug else pub
            log("posting", f"published to Substack: {url}")
            return {"ok": True, "id": str(draft_id), "url": url,
                    "detail": "published on Substack"}

        url = f"{pub}/publish/post/{draft_id}"
        log("posting", f"created Substack draft {draft_id}")
        return {"ok": True, "id": str(draft_id), "url": url,
                "detail": "Substack DRAFT created — open it, check the preview, hit Publish"}
    except ImportError:
        return {"ok": False, "id": "", "url": "",
                "detail": "python-substack not installed — run: pip install python-substack"}
    except Exception as e:  # noqa: BLE001
        log_error(f"[posting] Substack publish failed: {e}")
        return {"ok": False, "id": "", "url": "", "detail": str(e)}
