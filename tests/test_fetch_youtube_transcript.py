import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "scripts"))

import fetch_youtube_transcript as fyt  # noqa: E402


class FetchYouTubeTranscriptTests(unittest.TestCase):
    def test_video_id_from_link(self):
        self.assertEqual(
            fyt.video_id_from_link("https://www.youtube.com/watch?v=abcdefghijk"),
            "abcdefghijk",
        )
        self.assertEqual(
            fyt.video_id_from_link("https://www.youtube.com/shorts/lmnopqrstuv"),
            "lmnopqrstuv",
        )
        self.assertEqual(
            fyt.video_id_from_link("https://youtu.be/zyxwvutsrqp"),
            "zyxwvutsrqp",
        )

    def test_match_video_by_id_title_link(self):
        videos = [
            {
                "video_id": "abc123DEF45",
                "title": "Frontier Labs say SLOW DOWN AI",
                "channel": "All-In Podcast",
                "link": "https://www.youtube.com/watch?v=abc123DEF45",
            },
            {
                "video_id": "xyz987ZYX65",
                "title": "Can AI Startups Still Compete",
                "channel": "No Priors",
                "link": "https://www.youtube.com/shorts/xyz987ZYX65",
            },
        ]
        self.assertEqual(
            fyt.match_video(videos, video_id="abc123DEF45")["channel"],
            "All-In Podcast",
        )
        self.assertEqual(
            fyt.match_video(videos, title="startups still")["video_id"],
            "xyz987ZYX65",
        )
        self.assertEqual(
            fyt.match_video(
                videos, link="https://youtu.be/abc123DEF45"
            )["title"],
            "Frontier Labs say SLOW DOWN AI",
        )

    def test_collect_videos_from_payload_and_feed(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = Path(tmp) / "payload.json"
            feed = Path(tmp) / "feed-youtube.json"
            payload.write_text(
                json.dumps(
                    {
                        "youtube": [
                            {
                                "video_id": "aaa111BBB22",
                                "title": "From payload",
                                "channel": "A",
                                "link": "https://www.youtube.com/watch?v=aaa111BBB22",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            feed.write_text(
                json.dumps(
                    {
                        "videos": [
                            {
                                "video_id": "aaa111BBB22",
                                "title": "Dup should skip",
                                "channel": "A",
                                "link": "https://www.youtube.com/watch?v=aaa111BBB22",
                            },
                            {
                                "video_id": "ccc333DDD44",
                                "title": "From feed only",
                                "channel": "B",
                                "link": "https://www.youtube.com/watch?v=ccc333DDD44",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            videos = fyt.collect_videos([payload, feed])
            self.assertEqual(len(videos), 2)
            self.assertEqual(videos[0]["title"], "From payload")
            self.assertEqual(videos[1]["title"], "From feed only")

    def test_main_writes_transcript_and_records_feedback(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = Path(tmp) / "payload.json"
            out = Path(tmp) / "t.txt"
            payload.write_text(
                json.dumps(
                    {
                        "youtube": [
                            {
                                "video_id": "vid11122233",
                                "title": "Test Episode",
                                "channel": "Lenny's Podcast",
                                "link": "https://www.youtube.com/watch?v=vid11122233",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(
                fyt, "fetch_captions", return_value=("hello transcript body " * 5, None)
            ), mock.patch.object(fyt, "record_feedback") as rf, mock.patch.object(
                sys, "argv", [
                    "fetch_youtube_transcript.py",
                    "--video-id",
                    "vid11122233",
                    "--payload",
                    str(payload),
                    "--out",
                    str(out),
                ]
            ):
                code = fyt.main()
            self.assertEqual(code, 0)
            self.assertTrue(out.is_file())
            self.assertIn("hello transcript", out.read_text(encoding="utf-8"))
            rf.assert_called_once()
            kwargs = rf.call_args.kwargs
            self.assertEqual(kwargs["kind"], "youtube")
            self.assertEqual(kwargs["stable_id"], "vid11122233")


if __name__ == "__main__":
    unittest.main()
