"""Images for X-bound drafts — real source photos and branded fact cards.

Two candidate types per draft, both honest:

  * source photo — the article's own og:image, downloaded and normalized.
    A real photo of the real thing. Rights vary by source (government
    agencies are public domain, most publications are not), so it never
    ships without William seeing it at review.
  * fact card — a typographic card rendered locally with Pillow from the
    draft's own strongest number. No stock, no AI art, no invented data:
    the stat comes out of the draft body, which came out of the research.

Candidates land in drafts/<day>/media/ and are recorded in the draft's
frontmatter (media_candidates + media_choice). The Drafts page shows
thumbnails with an attach-or-none picker; whatever media_choice points
at when the post goes live is uploaded and attached to tweet 1 by the X
publisher. Everything here is best-effort — a failure never blocks
drafting, it just means a text-only post.
"""

import json
import re
from io import BytesIO
from pathlib import Path

from masterbuilder_bot import config, llm, publishers, storage
from masterbuilder_bot.logging_utils import log, log_error

MEDIA_DIRNAME = "media"

# og:image downloads: skip icons/trackers, keep uploads under X's 5 MB cap.
MIN_W, MIN_H = 400, 250
MAX_WIDTH = 1600
MAX_DOWNLOAD_BYTES = 12 * 1024 * 1024
_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                     "AppleWebKit/537.36 masterbuilder-bot/1.0"}

_OG_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)(?::src)?["\']'
    r'[^>]+content=["\']([^"\']+)["\']', re.I)
_OG_RE_REV = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+'
    r'(?:property|name)=["\'](?:og:image|twitter:image)(?::src)?["\']', re.I)

# Card palette — same dark field as the dashboard, one accent.
_BG = (15, 19, 23)
_FG = (242, 244, 246)
_MUTED = (185, 194, 204)
_DIM = (107, 116, 128)
_ACCENT = (245, 185, 66)
CARD_W, CARD_H = 1600, 900

_FONT_PATHS = (
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/SFNS.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)


def _font(size: int):
    from PIL import ImageFont

    for p in _FONT_PATHS:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:  # noqa: BLE001
                continue
    return ImageFont.load_default(size)


def media_dir(day: str) -> Path:
    d = config.drafts_dir() / day / MEDIA_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _rel(path: Path) -> str:
    """Store paths relative to the data home so drafts stay portable."""
    return str(Path(path).resolve().relative_to(config.data_home().resolve()))


def resolve(rel_path: str) -> Path:
    return config.data_home() / rel_path


# ---------- candidate 1: the article's own image ----------

def og_image_url(article_url: str) -> str | None:
    import requests

    r = requests.get(article_url, headers=_UA, timeout=20)
    if r.status_code != 200:
        return None
    m = _OG_RE.search(r.text) or _OG_RE_REV.search(r.text)
    return m.group(1).strip() if m else None


def fetch_source_image(article_url: str, dest: Path) -> Path | None:
    """og:image -> normalized JPEG at dest, or None if there's no usable
    image (missing tag, icon-sized, not actually an image)."""
    import requests
    from PIL import Image

    img_url = og_image_url(article_url)
    if not img_url:
        return None
    r = requests.get(img_url, headers=_UA, timeout=30)
    if r.status_code != 200 or len(r.content) > MAX_DOWNLOAD_BYTES:
        return None
    img = Image.open(BytesIO(r.content))
    img.load()
    if img.width < MIN_W or img.height < MIN_H:
        return None
    if img.mode != "RGB":
        img = img.convert("RGB")
    if img.width > MAX_WIDTH:
        img = img.resize((MAX_WIDTH, round(img.height * MAX_WIDTH / img.width)))
    img.save(dest, "JPEG", quality=88)
    return dest


# ---------- candidate 2: the fact card ----------

_STAT_SYSTEM = (
    "You pull the single most scroll-stopping statistic out of a post for "
    "a typographic stat card. Reply with ONLY JSON:\n"
    '{"stat": "<the number with its unit, under 24 characters, e.g. '
    '\'800 L/sec\' or \'50:26\'>", "context": "<one plain line saying what '
    "the number is, under 90 characters>\"}\n"
    "Rules: the stat must appear in the post verbatim (you may only "
    "reformat units). Pick the number a stranger would stop for, not the "
    "biggest one. If the post has no number worth a card, reply with the "
    "single word NONE."
)


def extract_stat(body: str) -> dict | None:
    raw = llm.complete(_STAT_SYSTEM, body, max_tokens=150)
    if not raw or "NONE" in raw[:20].upper():
        return None
    try:
        spec = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        return None
    stat = str(spec.get("stat", "")).strip()
    context = str(spec.get("context", "")).strip()
    if not stat or not context:
        return None
    return {"stat": stat[:32], "context": context[:110]}


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        cand = f"{cur} {w}".strip()
        if draw.textlength(cand, font=font) <= max_w:
            cur = cand
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def stat_card(stat: str, context: str, kicker: str, dest: Path) -> Path:
    """Render the branded fact card: kicker, huge stat, context line,
    wordmark. Pure typography — nothing to get wrong."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (CARD_W, CARD_H), _BG)
    d = ImageDraw.Draw(img)
    margin = 110
    text_w = CARD_W - 2 * margin

    d.rectangle([margin, 96, margin + 220, 104], fill=_ACCENT)
    d.text((margin, 136), kicker.upper(), font=_font(38), fill=_DIM)

    # the stat autosizes down until it fits on one line
    size = 300
    while size > 80 and d.textlength(stat, font=_font(size)) > text_w:
        size -= 20
    stat_font = _font(size)
    d.text((margin, 300), stat, font=stat_font, fill=_FG)

    ctx_font = _font(52)
    y = 300 + size + 70
    for line in _wrap(d, context, ctx_font, text_w)[:3]:
        d.text((margin, y), line, font=ctx_font, fill=_MUTED)
        y += 68

    d.text((margin, CARD_H - 90), "masterbuilder.ai", font=_font(36), fill=_DIM)
    img.save(dest, "PNG")
    return dest


# ---------- per-draft entry point ----------

def build_for_draft(path: Path) -> list[str]:
    """Generate image candidates for one draft and record them in its
    frontmatter. Returns the candidate list (relative paths). X-bound
    types only; never raises."""
    path = Path(path)
    post = storage.load_post(path)
    dtype = post.get("type", "")
    if publishers.platform_for(dtype) != "x":
        return []
    day = path.parent.name
    stem = path.stem
    out = media_dir(day)
    candidates: list[str] = []

    sources = [str(u) for u in (post.get("sources") or []) if str(u).strip()]
    if sources:
        try:
            got = fetch_source_image(sources[0], out / f"{stem}-source.jpg")
            if got:
                candidates.append(_rel(got))
        except Exception as e:  # noqa: BLE001
            log_error(f"[media] source image failed for {path.name}: {e}")

    try:
        spec = extract_stat(post.content)
        if spec:
            kicker = {"receipt": "The receipt", "record": "Record set",
                      "followup": "Update"}.get(dtype, "Field numbers")
            got = stat_card(spec["stat"], spec["context"], kicker,
                            out / f"{stem}-card.png")
            candidates.append(_rel(got))
    except Exception as e:  # noqa: BLE001
        log_error(f"[media] fact card failed for {path.name}: {e}")

    post["media_candidates"] = candidates
    # default: the real photo when there is one, else the card — William
    # can flip to the other candidate or to none at review
    post["media_choice"] = candidates[0] if candidates else ""
    storage.save_post(path, post)
    if candidates:
        log("media", f"{path.name}: {len(candidates)} image candidate(s)")
    return candidates


def on_review_move(dest: Path, keep: bool) -> None:
    """Called after a draft moves out of drafts/ (approve or reject).

    approve (keep=True): the chosen image moves next to the post under
    approved/<day>/media/ and unchosen candidates are deleted.
    reject (keep=False): all candidates are deleted.
    Never raises — worst case a post publishes text-only."""
    try:
        post = storage.load_post(Path(dest))
        cands = [c for c in (post.get("media_candidates") or []) if c]
        choice = post.get("media_choice", "") or ""
        kept_rel = ""
        for c in cands:
            src = resolve(c)
            if keep and c == choice and src.exists():
                new_dir = Path(dest).parent / MEDIA_DIRNAME
                new_dir.mkdir(parents=True, exist_ok=True)
                new_path = new_dir / src.name
                src.replace(new_path)
                kept_rel = _rel(new_path)
            elif src.exists():
                src.unlink()
        post["media_candidates"] = [kept_rel] if kept_rel else []
        post["media_choice"] = kept_rel
        storage.save_post(Path(dest), post)
    except Exception as e:  # noqa: BLE001
        log_error(f"[media] move on review failed for {dest}: {e}")
