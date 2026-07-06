"""X (Twitter) publisher — OAuth 1.0a user context, API v2.

Needs four env keys from a (free-tier) X developer app with Read+Write
permissions: X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET.

Free tier limits (2026): ~500 tweet writes/month, ~100 reads/month.
Our cadence caps (5 posts/day max) stay comfortably inside that.

publish() handles both single posts and threads: a body whose paragraphs
start with "1/", "2/" ... is posted as a reply chain. Source links are
never part of the main post — they go in a final reply tweet.
"""

import os
import re

import requests

from masterbuilder_bot.logging_utils import log, log_error

API = "https://api.x.com/2"
REQUIRED_KEYS = ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET")
TWEET_LIMIT = 280


def missing_keys() -> list[str]:
    return [k for k in REQUIRED_KEYS if not os.environ.get(k, "").strip()]


def is_configured() -> bool:
    return not missing_keys()


def _auth():
    from requests_oauthlib import OAuth1

    return OAuth1(
        os.environ["X_API_KEY"].strip(),
        os.environ["X_API_SECRET"].strip(),
        os.environ["X_ACCESS_TOKEN"].strip(),
        os.environ["X_ACCESS_TOKEN_SECRET"].strip(),
    )


def test() -> dict:
    """GET /users/me — confirms the four keys actually work together."""
    if not is_configured():
        return {"ok": False, "detail": f"missing keys: {', '.join(missing_keys())}"}
    try:
        r = requests.get(f"{API}/users/me", auth=_auth(), timeout=20)
        if r.status_code == 200:
            handle = r.json().get("data", {}).get("username", "?")
            return {"ok": True, "detail": f"connected as @{handle}"}
        return {"ok": False, "detail": f"HTTP {r.status_code}: {r.text[:200]}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "detail": f"{type(e).__name__}: {e}"}


def split_thread(text: str) -> list[str]:
    """Split a draft body into tweets.

    Numbered paragraphs ("1/ ...", "2/ ...") become one tweet each.
    Anything else that fits 280 chars is a single tweet. Longer content
    (e.g. a builder_signal's bullets) is packed into a thread: paragraphs
    and bullet lines are greedily grouped into <=280-char tweets. Any
    still-over-long tweet is cut at the last sentence/word boundary —
    the review step already saw the text.
    """
    text = text.strip()
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    numbered = [p for p in paras if re.match(r"^\d+\s*/", p)]
    if len(numbered) >= 2:
        return [_clip(t) for t in numbered]
    if len(text) <= TWEET_LIMIT:
        return [text]

    # Pack paragraphs (and bullet lines within them) into tweet-sized chunks.
    units: list[str] = []
    for p in paras:
        lines = p.splitlines()
        if all(ln.lstrip().startswith(("- ", "* ", "• ")) for ln in lines):
            units.extend(ln.strip() for ln in lines)
        else:
            units.append(p.replace("\n", " "))
    tweets, current = [], ""
    for u in units:
        candidate = f"{current}\n\n{u}" if current else u
        if len(candidate) <= TWEET_LIMIT:
            current = candidate
        else:
            if current:
                tweets.append(current)
            current = u
    if current:
        tweets.append(current)
    return [_clip(t) for t in tweets]


def _clip(tweet: str) -> str:
    if len(tweet) <= TWEET_LIMIT:
        return tweet
    cut = tweet[: TWEET_LIMIT - 1]
    for sep in (". ", "! ", "? ", " "):
        i = cut.rfind(sep)
        if i > 100:
            return cut[: i + 1].strip() + ("" if sep != " " else "…")
    return cut.strip() + "…"


def _strip_sources_footer(text: str) -> str:
    """Drop a trailing '---\nSources:' footer (older drafts embedded links
    in the body; links now go in the sources reply instead)."""
    return re.split(r"\n\s*---\s*\nSources:", text)[0].strip()


def _sources_tweets(sources: list) -> list[str]:
    """Format source links as reply tweet(s), chunked to fit 280 chars."""
    urls = [str(u).strip() for u in sources if str(u).strip()]
    if not urls:
        return []
    label = "Source:" if len(urls) == 1 else "Sources:"
    tweets, current = [], label
    for u in urls:
        candidate = f"{current}\n{u}"
        if len(candidate) <= TWEET_LIMIT:
            current = candidate
        else:
            tweets.append(current)
            current = u
    tweets.append(current)
    return tweets


def _post_one(text: str, reply_to: str | None = None) -> dict:
    payload: dict = {"text": text}
    if reply_to:
        payload["reply"] = {"in_reply_to_tweet_id": reply_to}
    r = requests.post(f"{API}/tweets", json=payload, auth=_auth(), timeout=30)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"X API HTTP {r.status_code}: {r.text[:300]}")
    return r.json()["data"]


def publish(text: str, title: str = "", sources: list | None = None) -> dict:
    """Post a single tweet or a thread, then the source links as a final
    reply tweet. Returns {ok, id, url, detail}.

    The id/url returned is the FIRST tweet (the one metrics track).
    """
    if not is_configured():
        return {"ok": False, "id": "", "url": "",
                "detail": f"X not configured (missing: {', '.join(missing_keys())})"}
    body = _strip_sources_footer(text)
    tweets = split_thread(body)
    # reading lists carry their links inline — only reply with links the
    # body doesn't already contain
    source_tweets = _sources_tweets([u for u in (sources or []) if str(u) not in body])
    try:
        first = _post_one(tweets[0])
        prev_id = first["id"]
        for t in tweets[1:] + source_tweets:
            prev_id = _post_one(t, reply_to=prev_id)["id"]
        handle = os.environ.get("X_HANDLE", "").strip().lstrip("@") or "i"
        url = f"https://x.com/{handle}/status/{first['id']}"
        detail = f"posted {len(tweets)} tweet(s)"
        if source_tweets:
            detail += " + sources reply"
        log("posting", f"posted to X: {detail}, id {first['id']}")
        return {"ok": True, "id": first["id"], "url": url, "detail": detail}
    except Exception as e:  # noqa: BLE001
        log_error(f"[posting] X publish failed: {e}")
        return {"ok": False, "id": "", "url": "", "detail": str(e)}


def fetch_metrics(tweet_ids: list[str]) -> dict:
    """Batched public metrics for up to 100 tweets in ONE read request
    (free tier gives ~100 reads/month — one batched call a day is plenty).

    Returns {tweet_id: {"impressions", "likes", "retweets", "replies",
    "quotes", "bookmarks"}}. Missing/deleted tweets are simply absent.
    """
    if not is_configured() or not tweet_ids:
        return {}
    out: dict = {}
    try:
        r = requests.get(
            f"{API}/tweets",
            params={"ids": ",".join(tweet_ids[:100]),
                    "tweet.fields": "public_metrics"},
            auth=_auth(), timeout=30,
        )
        if r.status_code != 200:
            log_error(f"[metrics] X read failed HTTP {r.status_code}: {r.text[:200]}")
            return {}
        for t in r.json().get("data", []):
            m = t.get("public_metrics", {})
            out[t["id"]] = {
                "impressions": m.get("impression_count", 0),
                "likes": m.get("like_count", 0),
                "retweets": m.get("retweet_count", 0) + m.get("quote_count", 0),
                "replies": m.get("reply_count", 0),
                "bookmarks": m.get("bookmark_count", 0),
            }
    except Exception as e:  # noqa: BLE001
        log_error(f"[metrics] X fetch failed: {e}")
    return out
