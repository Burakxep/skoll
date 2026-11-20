"""Watchlist cooldown: a below-bar near-miss that shows in the 'on the radar'
band is held back for a few days instead of resurfacing in every single run."""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from skoll import pipeline, report
from skoll.models import Item
from skoll.store import Store

PROFILE = {
    "include": ["pentest"], "exclude": [], "focus_tags": {},
    "_settings": {
        "score_threshold": {"github": 10, "default": 3},
        "min_relevance": 2.0, "max_items": 40,
        "watchlist": {"margin": 0.6, "cooldown_days": 3,
                      "max_per_source": {"github": 6}},
    },
}


def repo(name):
    # relevant ('pentest') but below the github bar (10): lands on the radar.
    return Item(source="github", source_id=name, title=name,
                url=f"https://x/{name}", description="pentest recon",
                stars=50, stars_per_day=20)


class StoreCooldownTest(unittest.TestCase):
    def test_cooldown_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Store(Path(tmp) / "t.db")
            s.mark_watchlisted("p", {"github:x/jsowl": 55}, day="2026-11-19")
            # next day: inside the 3-day window -> held, baseline stars returned
            self.assertEqual(
                s.watchlist_cooldown("p", ["github:x/jsowl"], "2026-11-20", 3),
                {"github:x/jsowl": 55})
            # gap == cooldown: served its time, free to reappear
            self.assertEqual(
                s.watchlist_cooldown("p", ["github:x/jsowl"], "2026-11-22", 3), {})
            # same day it was shown: never suppressed (same-day re-runs stay stable)
            self.assertEqual(
                s.watchlist_cooldown("p", ["github:x/jsowl"], "2026-11-19", 3), {})
            # cooldown 0 disables the feature
            self.assertEqual(
                s.watchlist_cooldown("p", ["github:x/jsowl"], "2026-11-20", 0), {})
            s.close()


class PipelineCooldownTest(unittest.TestCase):
    def run_with(self, items, tmp, **kw):
        fresh = [Item(**{**it.__dict__, "tags": [], "matched_keywords": []}) for it in items]
        with mock.patch.object(pipeline, "fetch_all", return_value=fresh), \
                mock.patch.object(report, "REPORTS", Path(tmp) / "reports"):
            return pipeline.run_profile("p", PROFILE, db_path=Path(tmp) / "t.db", **kw)

    def test_recent_radar_item_is_held_back(self):
        a, b = repo("x/a"), repo("x/b")
        with tempfile.TemporaryDirectory() as tmp:
            yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
            s = Store(Path(tmp) / "t.db")
            s.mark_watchlisted("p", {a.dedup_key: a.stars}, day=yesterday)  # shown yesterday
            s.close()

            res = self.run_with([a, b], tmp)
            keys = {it.dedup_key for it in res["watchlist"]}
            self.assertIn(b.dedup_key, keys)          # fresh near-miss shows
            self.assertNotIn(a.dedup_key, keys)       # yesterday's is held back

            # Same-day re-run: b was marked today, so it must stay (gap 0),
            # and a is still inside its cooldown.
            res2 = self.run_with([a, b], tmp)
            keys2 = {it.dedup_key for it in res2["watchlist"]}
            self.assertIn(b.dedup_key, keys2)
            self.assertNotIn(a.dedup_key, keys2)

    def test_surging_item_bypasses_cooldown(self):
        with tempfile.TemporaryDirectory() as tmp:
            yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
            s = Store(Path(tmp) / "t.db")
            s.mark_watchlisted("p", {"github:x/a": 50}, day=yesterday)  # shown at 50 stars
            s.close()

            hot = repo("x/a")
            hot.stars = 120  # more than doubled since yesterday -> breakout
            res = self.run_with([hot], tmp)
            keys = {it.dedup_key for it in res["watchlist"]}
            self.assertIn(hot.dedup_key, keys)  # surged past the cooldown, back on radar


if __name__ == "__main__":
    unittest.main()
