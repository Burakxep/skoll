"""Offline tests for the weekly trend analysis."""
from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from skoll.models import Item
from skoll.store import Store
from skoll.weekly import analyze, merge_entries, windows

END = date(2026, 10, 14)


def item(key, created, tags=(), kws=(), source="github", stars=0, score=5.0):
    return Item(source=source, source_id=key, title=key, url=f"https://x/{key}",
                created_at=datetime(created.year, created.month, created.day,
                                    tzinfo=timezone.utc),
                tags=list(tags), matched_keywords=list(kws),
                stars=stars, score=score)


class WindowTest(unittest.TestCase):
    def test_rolling_windows(self):
        this, last = windows(END)
        self.assertEqual((this.start, this.end), (date(2026, 10, 8), END))
        self.assertEqual((last.start, last.end), (date(2026, 10, 1), date(2026, 10, 7)))


class AnalyzeTest(unittest.TestCase):
    def setUp(self):
        this_day, last_day, old = date(2026, 10, 12), date(2026, 10, 3), date(2026, 9, 1)
        items = [
            item("a", this_day, ["redteam"], ["c2", "evasion"]),
            item("b", this_day, ["redteam"], ["c2", "reverse-engineering"], score=9),
            item("c", this_day, ["recon"], ["osint", "reverse-engineering"]),
            item("d", last_day, ["redteam"], ["c2"]),
            item("e", last_day, ["recon"], ["osint"]),
            item("f", last_day, ["recon"], ["osint"]),
            item("g", old, ["redteam"], ["c2"]),          # outside both windows
        ]
        self.rep = analyze(merge_entries([], items), [], END,
                           weak_keywords=["reverse-engineering"])

    def trend(self, trends, name):
        return next(t for t in trends if t.name == name)

    def test_totals_and_tags(self):
        self.assertEqual((self.rep.total.this, self.rep.total.last), (3, 3))
        red = self.trend(self.rep.by_tag, "redteam")
        recon = self.trend(self.rep.by_tag, "recon")
        self.assertEqual((red.this, red.last, red.delta, red.pct), (2, 1, 1, 100))
        self.assertEqual((recon.this, recon.last, recon.pct), (1, 2, -50))

    def test_keywords(self):
        names = [t.name for t in self.rep.keywords]
        self.assertIn("c2", names)
        self.assertNotIn("reverse-engineering", names)   # weak keyword ignored
        self.assertEqual([t.name for t in self.rep.rising], ["c2"])
        self.assertEqual(self.rep.new_keywords, [])      # evasion only once

    def test_top_items_this_week_by_score(self):
        self.assertEqual(self.rep.top_items[0].key, "github:b")
        self.assertEqual(len(self.rep.top_items), 3)

    def test_week_id(self):
        self.assertEqual(self.rep.week_id, "2026-W42")


class PartialSourceTest(unittest.TestCase):
    def test_short_coverage_source_left_out_of_trends(self):
        items = [item("a", date(2026, 10, 3), ["redteam"]),
                 item("b", date(2026, 10, 12), ["redteam"]),
                 # reddit only reaches back 3 days -> not comparable
                 item("r1", date(2026, 10, 12), ["reversing"], source="reddit"),
                 item("r2", date(2026, 10, 13), ["reversing"], source="reddit")]
        rep = analyze(merge_entries([], items), [], END)
        self.assertEqual(rep.partial_sources, ["reddit"])
        self.assertEqual((rep.total.this, rep.total.last), (1, 1))
        self.assertNotIn("reversing", [t.name for t in rep.by_tag])
        self.assertEqual(len(rep.top_items), 3)          # still listed
        self.assertIn("reddit", [t.name for t in rep.by_source])


class StarGrowthTest(unittest.TestCase):
    def test_gainers_from_observations(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / "t.db")
            created = date(2026, 10, 9)
            store.record_observations([item("r", created, stars=10)], "p", day="2026-10-10")
            store.record_observations([item("r", created, stars=40),
                                       item("q", created, stars=5)], "p", day="2026-10-13")
            store.record_observations([item("q", created, stars=99)], "p", day="2026-09-01")
            rows = store.observations("p", "2026-10-01", "2026-10-14")
            store.close()
        rep = analyze(merge_entries(rows), rows, END)
        self.assertEqual(len(rep.gainers), 1)           # q seen on one day only
        g = rep.gainers[0]
        self.assertEqual((g.key, g.gain, g.days, g.per_day), ("github:r", 30, 3, 10.0))
        self.assertEqual(rep.history_days, 2)

    def test_reported_flag_sticks(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / "t.db")
            it = item("r", date(2026, 10, 9))
            store.record_observations([it], "p", reported={it.dedup_key}, day="2026-10-10")
            store.record_observations([it], "p", day="2026-10-10")   # rerun same day
            rows = store.observations("p", "2026-10-01", "2026-10-14")
            store.close()
        self.assertEqual(len(rows), 1)
        self.assertTrue(merge_entries(rows, [it])["github:r"].reported)


if __name__ == "__main__":
    unittest.main()
