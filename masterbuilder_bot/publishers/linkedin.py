"""LinkedIn publisher — posts to your personal feed via the v2 API.

Needs one env key: LINKEDIN_ACCESS_TOKEN — an OAuth token from a LinkedIn
developer app with the "Share on LinkedIn" and "Sign In with LinkedIn
using OpenID Connect" products enabled (scopes: openid profile w_member_social).

The author URN is resolved once from /v2/userinfo and cached in .env as
LINKEDIN_AUTHOR_URN, so posting costs a single API call.

Heads-up: LinkedIn member tokens expire after ~60 days. When posting
starts failing with 401, regenerate the token on the Connections page.
"""

import os

import requests

from masterbuilder_bot import config
from masterbuilder_bot.logging_utils import log, log_error

API = "https://api.linkedin.com/v2"
REQUIRED_KEYS = ("LINKEDIN_ACCESS_TOKEN",)
POST_LIMIT = 2900  # LinkedIn allows 3000 chars; keep margin


def missing_keys() -> list[str]:
    return [k for k in REQUIRED_KEYS if not os.environ.get(k, "").strip()]


def is_configured() -> bool:
    return not missing_keys()


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['LINKEDIN_ACCESS_TOKEN'].strip()}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }


def _author_urn() -> str:
    """urn:li:person:<id> — cached in .env after the first lookup."""
    cached = os.environ.get("LINKEDIN_AUTHOR_URN", "").strip()
    if cached:
        return cached
    r = requests.get(f"{API}/userinfo", headers=_headers(), timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"LinkedIn userinfo HTTP {r.status_code}: {r.text[:200]}")
    urn = f"urn:li:person:{r.json()['sub']}"
    config.set_env_key("LINKEDIN_AUTHOR_URN", urn)
    return urn


def test() -> dict:
    if not is_configured():
        return {"ok": False, "detail": f"missing keys: {', '.join(missing_keys())}"}
    try:
        r = requests.get(f"{API}/userinfo", headers=_headers(), timeout=20)
        if r.status_code == 200:
            data = r.json()
            config.set_env_key("LINKEDIN_AUTHOR_URN", f"urn:li:person:{data['sub']}")
            return {"ok": True, "detail": f"connected as {data.get('name', data['sub'])}"}
        if r.status_code == 401:
            return {"ok": False, "detail": "token expired or invalid (401) — "
                                           "regenerate it in the LinkedIn developer portal"}
        return {"ok": False, "detail": f"HTTP {r.status_code}: {r.text[:200]}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "detail": f"{type(e).__name__}: {e}"}


def publish(text: str, title: str = "", sources: list | None = None) -> dict:
    """Post text to the personal feed. First source link is appended so
    LinkedIn renders a preview card."""
    if not is_configured():
        return {"ok": False, "id": "", "url": "",
                "detail": f"LinkedIn not configured (missing: {', '.join(missing_keys())})"}
    body = text.strip()
    if sources and sources[0] not in body:
        body += f"\n\nSource: {sources[0]}"
    body = body[:POST_LIMIT]
    try:
        author = _author_urn()
        payload = {
            "author": author,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": body},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }
        r = requests.post(f"{API}/ugcPosts", json=payload, headers=_headers(), timeout=30)
        if r.status_code != 201:
            raise RuntimeError(f"LinkedIn HTTP {r.status_code}: {r.text[:300]}")
        post_id = r.headers.get("x-restli-id", "") or r.json().get("id", "")
        url = f"https://www.linkedin.com/feed/update/{post_id}/" if post_id else ""
        log("posting", f"posted to LinkedIn: {post_id}")
        return {"ok": True, "id": post_id, "url": url, "detail": "posted to LinkedIn"}
    except Exception as e:  # noqa: BLE001
        log_error(f"[posting] LinkedIn publish failed: {e}")
        return {"ok": False, "id": "", "url": "", "detail": str(e)}
