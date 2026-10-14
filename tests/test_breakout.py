"""Breakout rule: an already-reported repo whose stars exploded comes back."""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from skoll import pipeline, report
from skoll.models import Item
from skoll.scoring import detect_breakouts, score_item
from skoll.store import Store

PROFILE = {
    "include": ["exploit", "pentest"], "exclude": [],
    "focus_tags": {"redteam": ["c2"]},
    "_settings": {"score_threshold": 3.0, "min_relevance": 2.0, "focus_min_hits": 1,
                  "max_items": 40, "breakout": {"min_gain": 500, "ratio": 5}},
}


def repo(name, stars, desc="exploit pentest c2"):
    return Item(source="github", source_id=name, title=name, url=f"https://x/{name}",
                description=desc, stars=stars, stars_per_day=1)


def detect(stars, then):
    it = score_item(repo("x/X", stars), PROFILE)
    return detect_breakouts([it], {"github:x/X": ("2026-10-09", then)}, PROFILE)


class RuleTest(unittest.TestCase):
    def test_thresholds(self):
        self.assertEqual(len(detect(5000, 10)), 1)       # the X example
        self.assertEqual(len(detect(400, 10)), 0)        # gain < 500
        self.assertEqual(len(detect(4000, 1000)), 0)     # +3000 but only 4x
        self.assertEqual(len(detect(5000, 1000)), 1)     # +4000 and 5x

    def test_tag_and_details(self):
        (it,) = detect(5000, 10)
        self.assertIn("breakout", it.tags)
        self.assertEqual(it.raw["breakout"], {"day": "2026-10-09", "from": 10, "now": 5000})

    def test_needs_baseline_and_relevance(self):
        it = score_item(repo("x/X", 5000), PROFILE)
        self.assertEqual(detect_breakouts([it], {}, PROFILE), [])
        off = score_item(repo("x/Y", 5000, desc="a game engine"), PROFILE)
        self.assertEqual(detect_breakouts([off], {"github:x/Y": ("d", 10)}, PROFILE), [])

    def test_focus(self):
        it = score_item(repo("x/X", 5000, desc="exploit pentest"), PROFILE)  # no c2
        self.assertEqual(detect_breakouts([it], {"github:x/X": ("d", 10)}, PROFILE,
                                          focus="redteam"), [])


class BaselineTest(unittest.TestCase):
    def test_latest_reported_day_wins_and_today_excluded(self):
        with tempfile.TemporaryDirectory() as d:
            s = Store(Path(d) / "t.db")
            x = repo("x/X", 0)
            for day, stars, rep in (("2026-10-01", 10, True), ("2026-10-05", 300, False),
                                    ("2026-10-08", 5000, True), ("2026-10-14", 9000, True)):
                x.stars = stars
                s.record_observations([x], "p", reported={x.dedup_key} if rep else set(), day=day)
            y = repo("x/Y", 50)       # snapshot only, never reported -> earliest snapshot
            s.record_observations([y], "p", day="2026-10-03")
            y.stars = 80
            s.record_observations([y], "p", day="2026-10-04")
            b = s.star_baselines("p", ["github:x/X", "github:x/Y", "github:x/Z"], "2026-10-14")
            s.close()
        self.assertEqual(b, {"github:x/X": ("2026-10-08", 5000), "github:x/Y": ("2026-10-03", 50)})


class PipelineTest(unittest.TestCase):
    """The scenario from the question: X reported yesterday at 10 stars."""

    def run_with(self, items, tmp):
        fresh = [Item(**{**it.__dict__, "tags": [], "matched_keywords": [], "raw": {}})
                 for it in items]
        with mock.patch.object(pipeline, "fetch_all", return_value=fresh), \
                mock.patch.object(report, "REPORTS", Path(tmp) / "reports"):
            return pipeline.run_profile("p", PROFILE, db_path=Path(tmp) / "t.db")

    def test_x_comes_back_once_then_settles(self):
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        with tempfile.TemporaryDirectory() as tmp:
            s = Store(Path(tmp) / "t.db")
            x = score_item(repo("x/X", 10), PROFILE)
            s.mark_seen(x, "p")
            s.record_observations([x], "p", reported={x.dedup_key}, day=yesterday)
            s.close()

            res = self.run_with([repo("x/X", 5000)], tmp)
            (it,) = res["ranked"]
            self.assertIn("breakout", it.tags)
            digest = res["paths"]["digest"].read_text(encoding="utf-8")
            self.assertIn("**breakout:** reported", digest)
            self.assertIn("breakout:", res["paths"]["prompt"].read_text(encoding="utf-8"))
            html = res["paths"]["html"].read_text(encoding="utf-8")
            self.assertIn('class="card breakout"', html)

            again = self.run_with([repo("x/X", 5100)], tmp)       # re-run same day
            self.assertEqual(again["counts"]["report"], 1)        # not duplicated

    def test_no_breakout_when_growth_is_modest(self):
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        with tempfile.TemporaryDirectory() as tmp:
            s = Store(Path(tmp) / "t.db")
            x = score_item(repo("x/X", 10), PROFILE)
            s.mark_seen(x, "p")
            s.record_observations([x], "p", reported={x.dedup_key}, day=yesterday)
            s.close()
            res = self.run_with([repo("x/X", 300)], tmp)
            self.assertEqual(res["ranked"], [])


if __name__ == "__main__":
    unittest.main()
