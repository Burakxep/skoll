"""Re-running the daily scan on the same day must not shrink the report."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from skoll import pipeline, report
from skoll.models import Item

PROFILE = {
    "include": ["exploit", "pentest"], "exclude": [],
    "focus_tags": {"redteam": ["c2", "implant"]},
    "_settings": {"score_threshold": 3.0, "min_relevance": 2.0,
                  "focus_min_hits": 1, "max_items": 40},
}


def repo(name, desc):
    return Item(source="github", source_id=name, title=name, url=f"https://x/{name}",
                description=desc, stars_per_day=5)


class RerunTest(unittest.TestCase):
    def run_with(self, items, tmp, **kw):
        fresh = [Item(**{**it.__dict__, "tags": [], "matched_keywords": []}) for it in items]
        with mock.patch.object(pipeline, "fetch_all", return_value=fresh), \
                mock.patch.object(report, "REPORTS", Path(tmp) / "reports"):
            return pipeline.run_profile("p", PROFILE, db_path=Path(tmp) / "t.db", **kw)

    def titles(self, path):
        return [l for l in path.read_text(encoding="utf-8").splitlines() if l.startswith("### ")]

    def test_second_run_keeps_first_runs_items(self):
        a, b = repo("x/a", "exploit pentest"), repo("x/b", "pentest exploit c2")
        c = repo("x/c", "new exploit pentest implant")
        with tempfile.TemporaryDirectory() as tmp:
            first = self.run_with([a, b], tmp)
            self.assertEqual(first["counts"]["report"], 2)
            second = self.run_with([a, b, c], tmp)
            self.assertEqual(second["counts"]["kept"], 1)        # only c is new
            self.assertEqual(second["counts"]["report"], 3)      # but report has all 3
            latest = Path(tmp) / "reports" / "p" / "latest.md"
            self.assertEqual(len(self.titles(latest)), 3)
            self.assertEqual(self.titles(second["paths"]["digest"]), self.titles(latest))

    def test_focus_rerun_only_adds_matching_earlier_items(self):
        a, b = repo("x/a", "exploit pentest"), repo("x/b", "pentest exploit c2")
        c = repo("x/c", "new exploit pentest implant")
        with tempfile.TemporaryDirectory() as tmp:
            self.run_with([a, b], tmp)
            res = self.run_with([a, b, c], tmp, focus="redteam")
            keys = sorted(it.source_id for it in res["ranked"])
            self.assertEqual(keys, ["x/c"])
            digest = res["paths"]["digest"].read_text(encoding="utf-8")
            self.assertIn("x/b", digest)       # earlier, tagged redteam
            self.assertNotIn("x/a](", digest)  # earlier, not redteam

    def test_dry_run_ignores_earlier_items(self):
        a, c = repo("x/a", "exploit pentest"), repo("x/c", "exploit pentest")
        with tempfile.TemporaryDirectory() as tmp:
            self.run_with([a], tmp)
            res = self.run_with([c], tmp, dry_run=True)
            self.assertEqual(res["counts"]["report"], 1)


if __name__ == "__main__":
    unittest.main()
