"""Buttondown publisher — sends the weekly digest as an email newsletter.

Buttondown (buttondown.com) has a real, official REST API and a free
tier (up to 100 subscribers), which makes it the zero-effort email
spine: one API key in .env and the Monday digest mails itself.

  * env keys: BUTTONDOWN_API_KEY (secret),
    BUTTONDOWN_USERNAME (your buttondown.com/<username> — used for the
    subscribe form on the site; optional for sending)
  * default behavior is SEND — the digest is list-curation, not opinion,
    and the whole point is zero touch. Set BUTTONDOWN_DRAFT_ONLY=true to
    have emails land as Buttondown drafts you trigger by hand instead.
  * body is markdown; Buttondown renders it natively.
"""

import os

from masterbuilder_bot.logging_utils import log, log_error

API_BASE = "https://api.buttondown.email/v1"

REQUIRED_KEYS = ("BUTTONDOWN_API_KEY",)


def missing_keys() -> list[str]:
    return [k for k in REQUIRED_KEYS if not os.environ.get(k, "").strip()]


def is_configured() -> bool:
    return not missing_keys()


def draft_only() -> bool:
    return os.environ.get("BUTTONDOWN_DRAFT_ONLY", "").strip().lower() in ("1", "true", "yes")


def username() -> str:
    return os.environ.get("BUTTONDOWN_USERNAME", "").strip()


def _headers() -> dict:
    return {"Authorization": f"Token {os.environ['BUTTONDOWN_API_KEY'].strip()}"}


def test() -> dict:
    if not is_configured():
        return {"ok": False, "detail": f"missing keys: {', '.join(missing_keys())}"}
    import requests

    try:
        resp = requests.get(f"{API_BASE}/subscribers", headers=_headers(),
                            params={"page_size": 1}, timeout=15)
        resp.raise_for_status()
        count = resp.json().get("count", 0)
        return {"ok": True, "detail": f"connected ({count} subscriber(s))"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "detail": f"{type(e).__name__}: {e}"}


def _title_from(text: str, fallback: str) -> tuple[str, str]:
    """(subject, remaining_body): first '# ' header becomes the subject."""
    lines = text.strip().splitlines()
    if lines and lines[0].startswith("# "):
        return lines[0][2:].strip(), "\n".join(lines[1:]).strip()
    return fallback, text


def publish(text: str, title: str = "", sources: list | None = None) -> dict:
    """Send (or draft) the email. Body goes as markdown."""
    if not is_configured():
        return {"ok": False, "id": "", "url": "",
                "detail": f"Buttondown not configured (missing: {', '.join(missing_keys())})"}
    import requests

    subject, body = _title_from(text, title or "The weekly reading list")
    payload = {"subject": subject, "body": body}
    if draft_only():
        payload["status"] = "draft"
    try:
        resp = requests.post(f"{API_BASE}/emails", headers=_headers(),
                             json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        email_id = str(data.get("id", ""))
        url = data.get("absolute_url", "") or f"https://buttondown.com/emails/{email_id}"
        what = "DRAFT created on Buttondown" if draft_only() else "emailed to subscribers"
        log("posting", f"Buttondown: {what} — {subject}")
        return {"ok": True, "id": email_id, "url": url, "detail": what}
    except requests.HTTPError as e:
        detail = f"Buttondown API {e.response.status_code}: {e.response.text[:300]}"
        log_error(f"[posting] {detail}")
        return {"ok": False, "id": "", "url": "", "detail": detail}
    except Exception as e:  # noqa: BLE001
        log_error(f"[posting] Buttondown publish failed: {e}")
        return {"ok": False, "id": "", "url": "", "detail": str(e)}
