"""Fetch raw YouTube channel listings from config/sources.json `youtube`.

Used by prepare_digest (daily digest path) and generate_feed (central runs).
Only pulls public Atom RSS metadata — no transcripts, no LLM.

Channel URLs may be:
  - https://www.youtube.com/@Handle
  - https://www.youtube.com/channel/UCxxxx
  - https://www.youtube.com/c/Name
  - https://www.youtube.com/user/Name

Optional per-channel `channel_id` (UC...) skips HTML resolution.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
FEEDS_DIR = ROOT_DIR / "feeds"
SOURCES_PATH = ROOT_DIR / "config" / "sources.json"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
ATOM = "http://www.w3.org/2005/Atom"
MEDIA = "http://search.yahoo.com/mrss/"
YT = "http://www.youtube.com/xml/schemas/2015"
CHANNEL_ID_RE = re.compile(r"(?:channel_id=|\"channelId\":\")(UC[\w-]{22})")
CHANNEL_PATH_RE = re.compile(r"/channel/(UC[\w-]{22})")


def configure_stdio():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def clean_text(text: str) -> str:
    return "".join(ch for ch in (text or "") if not 0xD800 <= ord(ch) <= 0xDFFF)


def load_sources(path: Path | None = None) -> dict:
    src = path or SOURCES_PATH
    with open(src, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def extract_channel_id_from_url(url: str) -> str | None:
    if not url:
        return None
    m = CHANNEL_PATH_RE.search(url)
    if m:
        return m.group(1)
    m = re.search(r"[?&]channel_id=(UC[\w-]{22})", url)
    if m:
        return m.group(1)
    return None


def extract_channel_id_from_html(html: str) -> str | None:
    if not html:
        return None
    m = re.search(
        r'<meta\s+itemprop=["\']channelId["\']\s+content=["\'](UC[\w-]{22})["\']',
        html,
        re.I,
    )
    if m:
        return m.group(1)
    m = CHANNEL_ID_RE.search(html)
    if m:
        return m.group(1)
    m = re.search(r'"externalId"\s*:\s*"(UC[\w-]{22})"', html)
    if m:
        return m.group(1)
    m = re.search(r'"browseId"\s*:\s*"(UC[\w-]{22})"', html)
    if m:
        return m.group(1)
    return None


def resolve_channel_id(channel: dict, client: httpx.Client | None = None) -> str:
    """Return UC… channel id from config field, URL path, or channel page HTML."""
    explicit = (channel.get("channel_id") or channel.get("youtube_channel_id") or "").strip()
    if explicit.startswith("UC") and len(explicit) >= 24:
        return explicit

    url = (channel.get("url") or "").strip()
    from_url = extract_channel_id_from_url(url)
    if from_url:
        return from_url

    if not url:
        raise ValueError("channel has no url or channel_id")

    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=30.0, follow_redirects=True, headers={"User-Agent": UA})
    try:
        resp = client.get(url)
        resp.raise_for_status()
        found = extract_channel_id_from_html(resp.text)
        if not found:
            # /videos tab sometimes exposes id more reliably
            videos_url = url.rstrip("/") + "/videos"
            resp2 = client.get(videos_url)
            if resp2.is_success:
                found = extract_channel_id_from_html(resp2.text)
        if not found:
            raise ValueError(f"could not resolve channel_id from {url}")
        return found
    finally:
        if owns_client:
            client.close()


def channel_rss_url(channel_id: str) -> str:
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


def parse_youtube_atom(xml_text: str) -> list[dict]:
    """Parse YouTube channel Atom feed into raw video dicts (no channel fields)."""
    root = ET.fromstring(xml_text)
    videos = []
    for entry in root.iter(f"{{{ATOM}}}entry"):
        title = clean_text((entry.findtext(f"{{{ATOM}}}title") or "").strip())
        vid_el = entry.find(f"{{{YT}}}videoId")
        video_id = (vid_el.text or "").strip() if vid_el is not None else ""
        if not video_id:
            entry_id = (entry.findtext(f"{{{ATOM}}}id") or "").strip()
            m = re.search(r"yt:video:([a-zA-Z0-9_-]{11})", entry_id)
            video_id = m.group(1) if m else ""

        pub_str = (entry.findtext(f"{{{ATOM}}}published") or "").strip()
        pub_date = None
        if pub_str:
            try:
                pub_date = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                if pub_date.tzinfo is None:
                    pub_date = pub_date.replace(tzinfo=timezone.utc)
                pub_date = pub_date.astimezone(timezone.utc)
            except ValueError:
                pub_date = None

        link = ""
        for link_el in entry.findall(f"{{{ATOM}}}link"):
            if link_el.get("rel") in (None, "alternate"):
                href = link_el.get("href") or ""
                if href:
                    link = href
                    break
        if not link and video_id:
            link = f"https://www.youtube.com/watch?v={video_id}"

        desc_el = entry.find(f"{{{MEDIA}}}group/{{{MEDIA}}}description")
        if desc_el is None:
            desc_el = entry.find(f"{{{ATOM}}}summary")
        description = clean_text((desc_el.text or "").strip() if desc_el is not None else "")

        if not video_id and not title:
            continue
        videos.append(
            {
                "video_id": video_id,
                "title": title,
                "link": link,
                "pub_date": pub_date.isoformat() if pub_date else None,
                "description": description[:2000],
            }
        )
    return videos


def _within_lookback(pub_date_iso: str | None, since: datetime) -> bool:
    if not pub_date_iso:
        return True  # keep if date unknown
    try:
        dt = datetime.fromisoformat(pub_date_iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt >= since
    except ValueError:
        return True


def normalize_max_videos(value) -> int | None:
    """Return a positive cap, or None for unlimited.

    null / missing / 0 / negative / "unlimited" → no cap (keep all that pass filters).
    """
    if value is None:
        return None
    if isinstance(value, str):
        raw = value.strip().lower()
        if raw in {"", "null", "none", "unlimited", "all", "inf", "infinite"}:
            return None
        try:
            value = int(raw)
        except ValueError:
            return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    return n


def fetch_channel_raw(
    channel: dict,
    *,
    lookback_hours: int,
    max_videos: int | None = None,
    client: httpx.Client | None = None,
) -> tuple[list[dict], str | None]:
    """Return (videos, error). Videos are raw metadata only.

    When max_videos is None, keep every item inside the lookback window
    (YouTube Atom RSS itself only returns recent uploads, typically ~15).
    """
    name = channel.get("name") or channel.get("id") or channel.get("url") or "?"
    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=30.0, follow_redirects=True, headers={"User-Agent": UA})
    try:
        try:
            yt_channel_id = resolve_channel_id(channel, client=client)
        except Exception as e:
            return [], f"{name}: resolve channel_id failed: {e}"

        rss = channel_rss_url(yt_channel_id)
        try:
            resp = client.get(rss)
            resp.raise_for_status()
            items = parse_youtube_atom(resp.text)
        except Exception as e:
            return [], f"{name}: RSS fetch failed: {e}"

        since = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
        filtered = [v for v in items if _within_lookback(v.get("pub_date"), since)]
        if max_videos is not None:
            filtered = filtered[: max_videos]

        domain = channel.get("domain") or "ai"
        channel_key = channel.get("id") or channel.get("name") or yt_channel_id
        channel_url = (channel.get("url") or "").strip() or f"https://www.youtube.com/channel/{yt_channel_id}"

        enriched = []
        for v in filtered:
            vid = v.get("video_id") or ""
            enriched.append(
                {
                    "id": vid or v.get("link") or v.get("title"),
                    "video_id": vid,
                    "guid": vid,
                    "title": v.get("title") or "",
                    "link": v.get("link") or (f"https://www.youtube.com/watch?v={vid}" if vid else ""),
                    "pub_date": v.get("pub_date"),
                    "description": v.get("description") or "",
                    "channel": name,
                    "channel_key": channel_key,
                    "channel_url": channel_url,
                    "youtube_channel_id": yt_channel_id,
                    "domain": domain,
                    "source": "youtube",
                }
            )
        return enriched, None
    finally:
        if owns_client:
            client.close()


def fetch_youtube(sources: dict | None = None, sources_path: Path | None = None) -> dict:
    """Fetch all configured YouTube channels. Returns feed dict with `videos`."""
    sources = sources if sources is not None else load_sources(sources_path)
    yt_cfg = sources.get("youtube") or {}
    channels = yt_cfg.get("channels") or []
    lookback = int(yt_cfg.get("lookback_hours") or 168)
    # Default unlimited: null / 0 / missing → no per-channel cap
    if "max_videos_per_channel" in yt_cfg:
        max_per = normalize_max_videos(yt_cfg.get("max_videos_per_channel"))
    else:
        max_per = None

    videos: list[dict] = []
    errors: list[str] = []
    if not channels:
        log("  ℹ️ youtube: no channels configured")
        return {
            "videos": [],
            "errors": None,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    with httpx.Client(timeout=30.0, follow_redirects=True, headers={"User-Agent": UA}) as client:
        for ch in channels:
            name = ch.get("name") or ch.get("id") or ch.get("url") or "?"
            log(f"  📥 YouTube {name}...")
            ch_lookback = int(ch.get("lookback_hours") or lookback)
            if "max_videos" in ch:
                ch_max = normalize_max_videos(ch.get("max_videos"))
            elif "max_videos_per_channel" in ch:
                ch_max = normalize_max_videos(ch.get("max_videos_per_channel"))
            else:
                ch_max = max_per
            found, err = fetch_channel_raw(
                ch,
                lookback_hours=ch_lookback,
                max_videos=ch_max,
                client=client,
            )
            if err:
                errors.append(err)
                log(f"    ⚠️ {err}")
                continue
            cap_label = "unlimited" if ch_max is None else f"max {ch_max}"
            log(f"    ✅ {len(found)} videos (lookback {ch_lookback}h, {cap_label})")
            videos.extend(found)

    # Dedup by video_id across channels, keep first (stable channel order)
    seen_ids: set[str] = set()
    unique: list[dict] = []
    for v in videos:
        key = v.get("video_id") or v.get("link") or v.get("title")
        if not key or key in seen_ids:
            continue
        seen_ids.add(key)
        unique.append(v)

    unique.sort(key=lambda v: v.get("pub_date") or "", reverse=True)
    return {
        "videos": unique,
        "errors": errors or None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def fetch_and_write_youtube(
    sources: dict | None = None,
    sources_path: Path | None = None,
    out_path: Path | None = None,
) -> dict:
    feed = fetch_youtube(sources=sources, sources_path=sources_path)
    path = out_path or (FEEDS_DIR / "feed-youtube.json")
    write_json(path, feed)
    log(f"✅ feed-youtube.json ({len(feed.get('videos') or [])} videos)")
    return feed


def main() -> None:
    configure_stdio()
    parser = argparse.ArgumentParser(description="Fetch raw YouTube channel feeds from sources.json")
    parser.add_argument(
        "--sources",
        type=str,
        default=str(SOURCES_PATH),
        help="Path to sources.json",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=str(FEEDS_DIR / "feed-youtube.json"),
        help="Output feed JSON path",
    )
    args = parser.parse_args()
    feed = fetch_and_write_youtube(
        sources_path=Path(args.sources),
        out_path=Path(args.out),
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "videos": len(feed.get("videos") or []),
                "errors": feed.get("errors"),
                "generated_at": feed.get("generated_at"),
                "out": args.out,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
