"""Engagement metrics for posted content — the 'did it work' half of the
learning loop.

collect() finds everything in posted/ that went to X, fetches public
metrics in ONE batched API call (free tier friendly: ~30 reads/month at
one call per day), and stores the latest numbers in memory/metrics.json:

    { "<tweet_id>": { "file", "day", "type", "title", "body_head",
                       "impressions", "likes", ..., "fetched_at" } }

LinkedIn and Substack don't expose per-post stats to normal API access,
so for those the loop learns from your approve/reject/edit feedback only.
"""

import json
from datetime import datetime
from pathlib import Path

from masterbuilder_bot import config, storage
from masterbuilder_bot.logging_utils import log
from masterbuilder_bot.publishers import x

MAX_TRACKED = 100  # one batched X read handles 100 ids


def metrics_file() -> Path:
    return config.memory_dir() / "metrics.json"


def load() -> dict:
    path = metrics_file()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save(data: dict) -> None:
    config.ensure_data_dirs()
    metrics_file().write_text(json.dumps(data, indent=2, ensure_ascii=False),
                              encoding="utf-8")


def _posted_x_items() -> list[dict]:
    """Newest-first X posts from posted/, up to MAX_TRACKED."""
    items = []
    for path in storage.list_posted():  # newest day first
        try:
            post = storage.load_post(path)
        except Exception:  # noqa: BLE001
            continue
        if post.get("posted_to") == "x" and post.get("post_id"):
            items.append({
                "id": str(post["post_id"]),
                "file": path.name,
                "day": path.parent.name,
                "type": post.get("type", ""),
                "title": post.get("title", ""),
                "body_head": post.content.strip()[:280],
            })
        if len(items) >= MAX_TRACKED:
            break
    return items


def collect() -> dict:
    """Fetch fresh metrics for tracked posts. Returns {updated: n, tracked: n}."""
    items = _posted_x_items()
    if not items:
        return {"updated": 0, "tracked": 0, "detail": "nothing posted to X yet"}
    if not x.is_configured():
        return {"updated": 0, "tracked": len(items), "detail": "X keys not set"}

    fresh = x.fetch_metrics([i["id"] for i in items])
    data = load()
    now = datetime.now().isoformat(timespec="seconds")
    for item in items:
        if item["id"] in fresh:
            data[item["id"]] = {**item, **fresh[item["id"]], "fetched_at": now}
    _save(data)
    log("metrics", f"collected metrics for {len(fresh)}/{len(items)} X posts")
    return {"updated": len(fresh), "tracked": len(items), "detail": "ok"}


def score(m: dict) -> float:
    """One engagement number per post. Interactions beat raw impressions;
    weights are rough on purpose — ranking is all we need."""
    return (m.get("likes", 0) * 3 + m.get("retweets", 0) * 5
            + m.get("replies", 0) * 4 + m.get("bookmarks", 0) * 4
            + m.get("impressions", 0) * 0.01)


def ranked() -> list[dict]:
    """All tracked posts, best first, with their score attached."""
    rows = [{**m, "id": tid, "score": round(score(m), 1)}
            for tid, m in load().items()]
    return sorted(rows, key=lambda r: r["score"], reverse=True)
