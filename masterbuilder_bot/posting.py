"""Posting layer — routes approved content to its platform (X, LinkedIn,
Substack) through the safety rails. Live posting is real now, but every
path still goes over the rails first:

  * BOT_MODE must be approved_posting
  * the file must live under approved/ (never drafts/)
  * content must carry sources and pass phrase checks
  * cadence caps apply (no mass posting)
  * the platform must be explicitly configured (env keys present)

After a successful live post, the file's frontmatter records where it
went (posted_to / post_id / post_url / posted_at) and the file moves to
posted/<day>/ — that record is what the metrics collector reads.
"""

from datetime import datetime
from pathlib import Path

from masterbuilder_bot import config, publishers, safety, storage
from masterbuilder_bot.logging_utils import log


def build_preview(path: Path) -> dict:
    """What *would* be posted: text + sources + destination. Safe anytime."""
    post = storage.load_post(Path(path))
    dtype = post.get("type", "")
    return {
        "file": str(path),
        "title": post.get("title", ""),
        "type": dtype,
        "platform": publishers.platform_for(dtype),
        "text": post.content.strip(),
        "sources": post.get("sources", []) or [],
        "media": post.get("media_choice", "") or "",
    }


def dry_run_post(path: Path, platform: str | None = None) -> dict:
    """Run every check a live post would run, post nothing, report."""
    path = Path(path)
    preview = build_preview(path)
    platform = platform or preview["platform"]
    checks = {}
    try:
        safety.assert_mode_allows_posting()
        checks["mode"] = "ok"
    except safety.SafetyError as e:
        checks["mode"] = f"BLOCKED: {e}"
    try:
        safety.assert_path_is_approved(path)
        checks["location"] = "ok"
    except safety.SafetyError as e:
        checks["location"] = f"BLOCKED: {e}"
    try:
        safety.assert_content_safe(preview["text"], preview["sources"])
        checks["content"] = "ok"
    except safety.SafetyError as e:
        checks["content"] = f"BLOCKED: {e}"
    try:
        safety.assert_cadence_ok(1)
        checks["cadence"] = "ok"
    except safety.SafetyError as e:
        checks["cadence"] = f"BLOCKED: {e}"
    if platform is None:
        checks["platform"] = "BLOCKED: this draft type has no publish destination"
    elif not publishers.get(platform).is_configured():
        missing = ", ".join(publishers.get(platform).missing_keys())
        checks["platform"] = f"BLOCKED: {platform} not configured (missing: {missing})"
    else:
        checks["platform"] = "ok"

    would_post = all(v == "ok" for v in checks.values())
    log("posting", f"dry-run {path.name} -> {platform}: "
                   f"{'WOULD POST' if would_post else 'blocked'}")
    return {**preview, "checks": checks, "would_post": would_post,
            "dry_run": True, "platform": platform}


def post_live(path: Path, platform: str | None = None) -> dict:
    """The one entry point for live posting.

    Raises SafetyError if any rail blocks. On publisher failure the file
    STAYS in approved/ so you can retry. On success it moves to posted/.
    """
    path = Path(path)

    # Hard gates first — these raise SafetyError and stop everything.
    safety.assert_post_allowed(path)
    preview = build_preview(path)
    safety.assert_content_safe(preview["text"], preview["sources"])
    safety.assert_cadence_ok(1)

    platform = platform or preview["platform"]
    if platform is None:
        raise safety.SafetyError(
            f"'{preview['type']}' drafts have no publish destination — "
            "they're internal content (use the text manually)."
        )
    pub = publishers.get(platform)
    if not pub.is_configured():
        raise safety.SafetyError(
            f"{platform} is not configured (missing: {', '.join(pub.missing_keys())}). "
            "Add the keys on the Connections page."
        )

    # attach the reviewed image (X only; other platforms stay text)
    kwargs = {}
    if platform == "x" and preview.get("media"):
        from masterbuilder_bot import media
        img = media.resolve(preview["media"])
        if img.exists():
            kwargs["media_path"] = str(img)

    result = pub.publish(preview["text"], title=preview["title"],
                         sources=preview["sources"], **kwargs)
    if not result.get("ok"):
        # No file move on failure — retry later from approved/.
        log("posting", f"LIVE POST FAILED {path.name} -> {platform}: {result.get('detail')}")
        return {**preview, "dry_run": False, "posted": False, **result}

    # Record where it went, then archive to posted/<day>/.
    post = storage.load_post(path)
    post["posted_to"] = platform
    post["post_id"] = result.get("id", "")
    post["post_url"] = result.get("url", "")
    post["posted_at"] = datetime.now().isoformat(timespec="seconds")
    storage.save_post(path, post)
    dest = move_to_posted(path)
    log("posting", f"LIVE posted {dest.name} -> {platform} ({result.get('url', '')})")
    return {**preview, "dry_run": False, "posted": True,
            "posted_to": str(dest), **result}


def post_approved(path: Path, dry_run: bool = True, platform: str | None = None) -> dict:
    """Back-compat entry point: dry-run unless explicitly told otherwise."""
    if dry_run:
        return dry_run_post(Path(path), platform)
    return post_live(Path(path), platform)


def move_to_posted(path: Path) -> Path:
    """Archive a successfully posted file to posted/<day>/."""
    return storage.set_status_and_move(Path(path), "posted", config.posted_dir())


# Auto mode never touches drafts the triage pipeline itself flagged as
# deserving a hard human look.
AUTO_POST_MAX_RISK = 2


def auto_post_day(day: str | None = None) -> list[dict]:
    """BOT_MODE=auto_posting: approve and post the day's X- and
    Substack-bound drafts, in slot order, through every rail a manual
    post goes through.

    Approval here is the real review.approve — it logs feedback, opens
    continuity arcs, and carries the fact card along — so an auto-posted
    story behaves exactly like one William clicked. The daily cadence cap
    (safety.MAX_POSTS_PER_DAY) is the hard ceiling; higher-risk drafts,
    non-X types, and anything the rails reject stay in the queue for
    manual review. Returns one result dict per draft considered."""
    from masterbuilder_bot import publishers as pubs
    from masterbuilder_bot import review

    day = day or storage.today()
    results: list[dict] = []
    if config.bot_mode() != config.AUTO_POSTING:
        log("posting", "auto_post_day called but BOT_MODE != auto_posting — no-op")
        return results

    # X posts publicly; Substack is draft-first (the publisher creates a
    # Substack draft unless SUBSTACK_AUTO_PUBLISH is set), so both are
    # safe to automate. An unconfigured platform just leaves drafts alone.
    auto_platforms = tuple(p for p in ("x", "substack")
                           if pubs.get(p).is_configured())

    # Retry pass first: approved posts (any day) that never made it out —
    # a prior run's publisher failure (API credits, outage) leaves them
    # here. Stale ones you no longer want must be rejected/removed from
    # approved/, otherwise they ship as soon as the platform recovers.
    retries = [p for p in storage.list_approved()
               if pubs.platform_for(storage.load_post(p).get("type", "")) in auto_platforms
               and not storage.load_post(p).get("post_id")]
    todo: list[tuple[Path, bool]] = ([(p, True) for p in retries]
                                     + [(p, False) for p in sorted(storage.list_drafts(day))])

    for path, already_approved in todo:
        post = storage.load_post(path)
        dtype = post.get("type", "")
        if pubs.platform_for(dtype) not in auto_platforms:
            continue
        entry = {"file": path.name, "type": dtype}
        if not already_approved and int(post.get("risk_score", 1) or 1) > AUTO_POST_MAX_RISK:
            entry.update(posted=False, detail="risk_score too high — left for manual review")
            results.append(entry)
            continue
        # content rail first, BEFORE approving — a draft that can't post
        # stays a draft for manual attention, not an orphan in approved/
        try:
            safety.assert_content_safe(post.content.strip(),
                                       post.get("sources", []) or [])
        except safety.SafetyError as e:
            entry.update(posted=False, detail=f"content blocked: {e}")
            results.append(entry)
            continue
        # cadence rail: once today's cap is hit, everything left waits
        try:
            safety.assert_cadence_ok(1)
        except safety.SafetyError as e:
            entry.update(posted=False, detail=f"cadence: {e}")
            results.append(entry)
            log("posting", f"auto-post stopped at {path.name}: {e}")
            break
        try:
            approved = (path if already_approved else
                        review.approve(path, reason="auto-posted (BOT_MODE=auto_posting)"))
            result = post_live(approved)
            entry.update(posted=bool(result.get("posted")),
                         url=result.get("url", ""), detail=result.get("detail", ""))
        except Exception as e:  # noqa: BLE001
            entry.update(posted=False, detail=f"error: {e}")
        results.append(entry)

    posted_n = sum(1 for r in results if r.get("posted"))
    log("posting", f"auto-post {day}: {posted_n} posted, "
                   f"{len(results) - posted_n} skipped/blocked")
    return results
