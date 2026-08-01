import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "scripts"))

import youtube_feed


SAMPLE_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns:media="http://search.yahoo.com/mrss/"
      xmlns="http://www.w3.org/2005/Atom">
  <title>YouTube Video Feed</title>
  <entry>
    <id>yt:video:abcdefghijk</id>
    <yt:videoId>abcdefghijk</yt:videoId>
    <title>Episode One</title>
    <published>{pub1}</published>
    <link rel="alternate" href="https://www.youtube.com/watch?v=abcdefghijk"/>
    <media:group>
      <media:description>First episode description</media:description>
    </media:group>
  </entry>
  <entry>
    <id>yt:video:lmnopqrstuv</id>
    <yt:videoId>lmnopqrstuv</yt:videoId>
    <title>Old Episode</title>
    <published>{pub2}</published>
    <link rel="alternate" href="https://www.youtube.com/watch?v=lmnopqrstuv"/>
    <media:group>
      <media:description>Too old</media:description>
    </media:group>
  </entry>
</feed>
"""


class YouTubeParseTests(unittest.TestCase):
    def test_extract_channel_id_from_url(self):
        self.assertEqual(
            youtube_feed.extract_channel_id_from_url(
                "https://www.youtube.com/channel/UCtug5s_yTsIxz1pY9ipYcIA"
            ),
            "UCtug5s_yTsIxz1pY9ipYcIA",
        )

    def test_extract_channel_id_from_html(self):
        html = '<meta itemprop="channelId" content="UCtug5s_yTsIxz1pY9ipYcIA">'
        self.assertEqual(
            youtube_feed.extract_channel_id_from_html(html),
            "UCtug5s_yTsIxz1pY9ipYcIA",
        )
        html2 = '"channelId":"UCtug5s_yTsIxz1pY9ipYcIA","title":"Lenny"'
        self.assertEqual(
            youtube_feed.extract_channel_id_from_html(html2),
            "UCtug5s_yTsIxz1pY9ipYcIA",
        )

    def test_parse_youtube_atom(self):
        now = datetime.now(timezone.utc)
        xml = SAMPLE_ATOM.format(
            pub1=now.isoformat().replace("+00:00", "Z"),
            pub2=(now - timedelta(days=30)).isoformat().replace("+00:00", "Z"),
        )
        items = youtube_feed.parse_youtube_atom(xml)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["video_id"], "abcdefghijk")
        self.assertEqual(items[0]["title"], "Episode One")
        self.assertIn("First episode", items[0]["description"])
        self.assertTrue(items[0]["link"].endswith("abcdefghijk"))

    def test_fetch_channel_raw_filters_lookback_and_enriches(self):
        now = datetime.now(timezone.utc)
        xml = SAMPLE_ATOM.format(
            pub1=now.isoformat().replace("+00:00", "Z"),
            pub2=(now - timedelta(days=30)).isoformat().replace("+00:00", "Z"),
        )

        class FakeResp:
            def __init__(self, text, status=200):
                self.text = text
                self.status_code = status

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise RuntimeError("http error")

        class FakeClient:
            def get(self, url):
                if "feeds/videos.xml" in url:
                    return FakeResp(xml)
                return FakeResp("")

        channel = {
            "id": "lennys-podcast",
            "name": "Lenny's Podcast",
            "url": "https://www.youtube.com/@LennysPodcast",
            "channel_id": "UCtug5s_yTsIxz1pY9ipYcIA",
            "domain": "ai",
        }
        videos, err = youtube_feed.fetch_channel_raw(
            channel,
            lookback_hours=168,
            max_videos=None,
            client=FakeClient(),
        )
        self.assertIsNone(err)
        self.assertEqual(len(videos), 1)
        self.assertEqual(videos[0]["video_id"], "abcdefghijk")
        self.assertEqual(videos[0]["channel"], "Lenny's Podcast")
        self.assertEqual(videos[0]["youtube_channel_id"], "UCtug5s_yTsIxz1pY9ipYcIA")
        self.assertEqual(videos[0]["domain"], "ai")

    def test_max_videos_none_keeps_all_in_lookback(self):
        now = datetime.now(timezone.utc)
        # Two recent entries, both inside lookback
        xml = SAMPLE_ATOM.format(
            pub1=now.isoformat().replace("+00:00", "Z"),
            pub2=(now - timedelta(hours=12)).isoformat().replace("+00:00", "Z"),
        )

        class FakeResp:
            def __init__(self, text):
                self.text = text

            def raise_for_status(self):
                return None

        class FakeClient:
            def get(self, url):
                return FakeResp(xml)

        channel = {
            "id": "test",
            "name": "Test",
            "channel_id": "UCtug5s_yTsIxz1pY9ipYcIA",
            "domain": "ai",
        }
        unlimited, err = youtube_feed.fetch_channel_raw(
            channel, lookback_hours=168, max_videos=None, client=FakeClient()
        )
        capped, err2 = youtube_feed.fetch_channel_raw(
            channel, lookback_hours=168, max_videos=1, client=FakeClient()
        )
        self.assertIsNone(err)
        self.assertIsNone(err2)
        self.assertEqual(len(unlimited), 2)
        self.assertEqual(len(capped), 1)

    def test_normalize_max_videos_unlimited(self):
        self.assertIsNone(youtube_feed.normalize_max_videos(None))
        self.assertIsNone(youtube_feed.normalize_max_videos(0))
        self.assertIsNone(youtube_feed.normalize_max_videos("unlimited"))
        self.assertEqual(youtube_feed.normalize_max_videos(5), 5)

    def test_fetch_youtube_empty_channels(self):
        feed = youtube_feed.fetch_youtube({"youtube": {"channels": []}})
        self.assertEqual(feed["videos"], [])
        self.assertIsNone(feed["errors"])

    def test_resolve_prefers_explicit_channel_id(self):
        ch = {
            "url": "https://www.youtube.com/@LennysPodcast",
            "channel_id": "UCtug5s_yTsIxz1pY9ipYcIA",
        }
        self.assertEqual(
            youtube_feed.resolve_channel_id(ch, client=mock.Mock()),
            "UCtug5s_yTsIxz1pY9ipYcIA",
        )


if __name__ == "__main__":
    unittest.main()
