"""Offline tests for the weekly report writers."""
from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from skoll.models import Item
from skoll.weekly import analyze, merge_entries
from skoll.weekly_report import _delta, notes, write_weekly_reports
from skoll.weekly import Trend

END = date(2026, 10, 14)


def item(key, day, tags=(), kws=(), source="github"):
    return Item(source=source, source_id=key, title=f"<b>{key}</b>", url=f"https://x/{key}",
                created_at=datetime(2026, 10, day, tzinfo=timezone.utc),
                tags=list(tags), matched_keywords=list(kws), score=5.0)


class WeeklyReportTest(unittest.TestCase):
    def setUp(self):
        items = [item("a", 12, ["redteam"], ["c2"]), item("b", 13, ["redteam"], ["c2"]),
                 item("c", 3, ["recon"], ["c2"]),
                 item("r", 13, ["reversing"], source="reddit")]
        self.rep = analyze(merge_entries([], items), [], END)

    def test_delta_format(self):
        self.assertEqual(_delta(Trend("x", 4, 2)), "+2 (+100%)")
        self.assertEqual(_delta(Trend("x", 3, 0)), "new")
        self.assertEqual(_delta(Trend("x", 1, 1)), "±0")

    def test_notes_flag_partial_and_star_history(self):
        text = " ".join(notes(self.rep))
        self.assertIn("Reddit", text)
        self.assertIn("Star growth", text)

    def test_writes_week_folder_without_leftover_placeholders(self):
        with tempfile.TemporaryDirectory() as d:
            paths = write_weekly_reports(self.rep, "p", root=Path(d))
            self.assertEqual(paths["html"].parent, Path(d) / "p" / "weekly" / "2026-W42")
            page = paths["html"].read_text(encoding="utf-8")
            self.assertNotIn("__", page)
            self.assertNotIn("<b>a</b>", page)                 # titles are escaped
            self.assertIn("&lt;b&gt;a&lt;/b&gt;", page)
            self.assertIn("redteam", paths["digest"].read_text(encoding="utf-8"))
            prompt = paths["prompt"].read_text(encoding="utf-8")
            self.assertIn("2026-W42", prompt)
            self.assertNotIn("{", prompt.split("--- CAVEATS ---")[1])  # all filled
            self.assertTrue((Path(d) / "p" / "latest-weekly.prompt.md").exists())


if __name__ == "__main__":
    unittest.main()
