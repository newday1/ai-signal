"""On-demand YouTube transcript fetch for the "expand YT1" flow.

Daily digest ships YouTube channel subscriptions as raw metadata only
(payload.youtube). Full captions are fetched one video at a time after the
user explicitly asks to expand / 详细解释 YT1, YT2, etc.

Usage:
    python scripts/fetch_youtube_transcript.py --video-id <id>
    python scripts/fetch_youtube_transcript.py --link  "<watch or shorts url>"
    python scripts/fetch_youtube_transcript.py --title "<title substring>"
    # add --out FILE to write transcript to a file instead of stdout

Looks up metadata from ~/.ai-signal/payload/payload.json first, then
skill feeds/feed-youtube.json. Exit codes: 0 found, 2 no captions,
3 not found in payload/feed, 4 library missing / fetch failed hard.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
USER_DIR = Path.home() / ".ai-signal"
DEFAULT_PAYLOAD = USER_DIR / "payload" / "payload.json"
LOCAL_FEED = ROOT_DIR / "feeds" / "feed-youtube.json"

sys.path.insert(0, str(SCRIPT_DIR))
from feedback import record_feedback  # noqa: E402


def configure_stdio():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def log(msg: str) -> None:
    sys.stderr.write(msg + "\n")


def clean_text(text: str) -> str:
    return "".join(ch for ch in (text or "") if not 0xD800 <= ord(ch) <= 0xDFFF)


def norm(s: str | None) -> str:
    return (s or "").strip().lower()


def video_id_from_link(link: str | None) -> str | None:
    if not link:
        return None
    parsed = urlparse(link)
    if "youtube.com" in parsed.netloc:
        m = re.search(r"[?&]v=([a-zA-Z0-9_-]{11})", link)
        if m:
            return m.group(1)
        m = re.search(r"/(?:shorts|embed|live)/([a-zA-Z0-9_-]{11})", parsed.path)
        return m.group(1) if m else None
    if "youtu.be" in parsed.netloc:
        vid = parsed.path.strip("/")[:11]
        return vid if len(vid) == 11 else None
    return None


def detect_proxy() -> str:
    for key in ("SOCKS_PROXY", "HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "all_proxy"):
        value = (os.environ.get(key) or "").strip()
        if value:
            return value
    return ""


def load_json(path: Path) -> dict | list | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text("utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None


def collect_videos(paths: list[Path]) -> list[dict]:
    videos: list[dict] = []
    seen: set[str] = set()
    for path in paths:
        data = load_json(path)
        if not data:
            continue
        items = []
        if isinstance(data, dict):
            if isinstance(data.get("youtube"), list):
                items = data["youtube"]
            elif isinstance(data.get("videos"), list):
                items = data["videos"]
        elif isinstance(data, list):
            items = data
        for item in items:
            if not isinstance(item, dict):
                continue
            key = str(
                item.get("video_id")
                or item.get("id")
                or item.get("guid")
                or item.get("link")
                or ""
            )
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            videos.append(item)
    return videos


def match_video(videos: list[dict], video_id=None, title=None, link=None) -> dict | None:
    if video_id:
        vid = norm(video_id)
        for v in videos:
            candidates = [
                v.get("video_id"),
                v.get("id"),
                v.get("guid"),
                video_id_from_link(v.get("link")),
            ]
            if any(norm(c) == vid for c in candidates if c):
                return v
    if link:
        want = norm(link)
        want_id = video_id_from_link(link)
        for v in videos:
            if norm(v.get("link")) == want:
                return v
            if want_id and norm(video_id_from_link(v.get("link"))) == norm(want_id):
                return v
            if want_id and norm(v.get("video_id") or v.get("id")) == norm(want_id):
                return v
    if title:
        t = norm(title)
        for v in videos:
            if norm(v.get("title")) == t:
                return v
        for v in videos:
            et = norm(v.get("title"))
            if et and (t in et or et in t):
                return v
    return None


def fetch_captions(video_id: str) -> tuple[str | None, str | None]:
    """Return (text, error). Prefer English, then any available track."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return None, (
            "youtube-transcript-api is not installed; run: "
            "python -m pip install youtube-transcript-api"
        )

    kwargs = {}
    proxy = detect_proxy()
    if proxy:
        try:
            from youtube_transcript_api.proxies import GenericProxyConfig

            p = proxy.replace("socks5h://", "socks5://")
            kwargs["proxy_config"] = GenericProxyConfig(http_url=p, https_url=p)
        except Exception as exc:  # pragma: no cover - proxy optional
            log(f"⚠ proxy config ignored: {exc}")

    api = YouTubeTranscriptApi(**kwargs)

    # Prefer English tracks when present.
    try:
        segs = api.fetch(video_id, languages=["en", "en-US", "en-GB"])
        text = " ".join(getattr(s, "text", str(s)) for s in segs).strip()
        if len(text) > 50:
            return clean_text(text), None
    except Exception:
        pass

    # Fallback: first listable track (manual or generated).
    try:
        listing = api.list(video_id)
        for transcript in listing:
            try:
                segs = transcript.fetch()
                text = " ".join(getattr(s, "text", str(s)) for s in segs).strip()
                if len(text) > 50:
                    return clean_text(text), None
            except Exception:
                continue
        return None, "no usable caption track found"
    except Exception as exc:
        return None, str(exc)


def main() -> int:
    configure_stdio()
    ap = argparse.ArgumentParser(
        description="Fetch one YouTube transcript for YT expansion / podcast-style translation."
    )
    ap.add_argument("--video-id", help="YouTube video id (11 chars; from payload.youtube)")
    ap.add_argument("--title", help="video title or a substring of it")
    ap.add_argument("--link", help="watch / shorts / youtu.be URL")
    ap.add_argument("--payload", default=str(DEFAULT_PAYLOAD), help="path to payload.json")
    ap.add_argument("--out", help="write transcript here instead of stdout")
    args = ap.parse_args()

    if not (args.video_id or args.title or args.link):
        ap.error("give at least one of --video-id / --title / --link")

    paths = [Path(args.payload), LOCAL_FEED]
    videos = collect_videos(paths)
    video = match_video(videos, args.video_id, args.title, args.link)

    # Allow direct fetch when caller already has video_id/link even if not in payload.
    video_id = None
    meta = video or {}
    if video:
        video_id = (
            video.get("video_id")
            or video.get("id")
            or video.get("guid")
            or video_id_from_link(video.get("link"))
        )
        log(
            f"↪ matched 「{video.get('title')}」 "
            f"channel={video.get('channel')} video_id={video_id}"
        )
    else:
        video_id = args.video_id or video_id_from_link(args.link)
        if not video_id:
            log("✗ no video matched in payload/feed and no resolvable video id")
            if videos:
                log("  Available titles:")
                for v in videos[:30]:
                    log(
                        f"    [{v.get('video_id') or v.get('id')}] "
                        f"{v.get('channel')} | {v.get('title')}"
                    )
            return 3
        log(f"↪ no payload match; fetching by video_id={video_id}")

    text, err = fetch_captions(str(video_id))
    if not text:
        title = meta.get("title") or video_id
        log(f"✗ 「{title}」has no transcript — {err}")
        return 2 if err and "not installed" not in err else 4

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        log(f"✓ 「{meta.get('title') or video_id}」— {len(text)} chars → {args.out}")
    else:
        log(f"✓ 「{meta.get('title') or video_id}」— {len(text)} chars")
        sys.stdout.write(text)
        sys.stdout.write("\n")

    try:
        record_feedback(
            "expanded",
            kind="youtube",
            source=meta.get("channel", ""),
            item_id="",
            stable_id=str(video_id),
            note=meta.get("title") or str(video_id),
        )
    except OSError as exc:
        log(f"⚠ could not record local expansion feedback: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
