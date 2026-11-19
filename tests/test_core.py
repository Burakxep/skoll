"""Offline tests for the deterministic core. Run: python -m unittest"""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import feedparser

from skoll.connectors.base import find_repo_url
from skoll.connectors.github import created_slices
from skoll.connectors.reddit import _clean_body, _entry_date, _external_link
from skoll.models import Item
from skoll.report import build_prompt, write_reports
from skoll.scoring import _match, rank_and_filter, score_item, watchlist_candidates
from skoll.store import Store

PROFILE = {
    "include": ["exploit", "pentest"],
    "exclude": ["newsletter"],
    "focus_tags": {"recon": ["recon", "osint", "subdomain"],
                   "redteam": ["c2", "implant"]},
    "_settings": {"score_threshold": 3.0, "min_relevance": 2.0,
                  "focus_min_hits": 2, "max_items": 40},
}


def repo(name, desc="", topics=(), spd=0.0, stars=0):
    return Item(source="github", source_id=name, title=name, url="u",
                description=desc, topics=list(topics),
                stars=stars, stars_per_day=spd)


class ScoringTest(unittest.TestCase):
    def test_momentum_cannot_carry_off_topic_repo(self):
        viral = repo("x/game-modder", "mod games: recon, art, audio", spd=500)
        self.assertEqual(rank_and_filter([viral], PROFILE), [])

    def test_single_include_hit_with_momentum_passes(self):
        it = repo("x/thing", "an exploit for CVE-2026-1", spd=10)
        self.assertEqual(rank_and_filter([it], PROFILE), [it])

    def test_single_prose_hit_gets_no_tag(self):
        it = score_item(repo("x/a", "pentest helper with recon notes"), PROFILE)
        self.assertNotIn("recon", it.tags)

    def test_two_hits_or_topic_hit_tags(self):
        two = score_item(repo("x/a", "osint and subdomain finder"), PROFILE)
        topic = score_item(repo("x/b", "a tool", topics=["c2"]), PROFILE)
        self.assertIn("recon", two.tags)
        self.assertIn("redteam", topic.tags)


    def test_per_source_quota(self):
        prof = {**PROFILE, "_settings": {**PROFILE["_settings"],
                "max_per_source": {"github": 1}}}
        hot = repo("x/a", "exploit pentest", spd=100)
        hot2 = repo("x/b", "exploit pentest", spd=50)
        post = Item(source="reddit", source_id="r1", title="new exploit",
                    url="u", description="pentest notes")
        self.assertEqual(rank_and_filter([hot, hot2, post], prof), [hot, post])


class SourceSignalTest(unittest.TestCase):
    PROF = {**PROFILE, "_settings": {**PROFILE["_settings"],
            "require_repo_link": ["reddit"], "source_bonus": {"rss": 3.0}}}

    def post(self, repo_url=""):
        return Item(source="reddit", source_id="r", title="my new exploit",
                    url="u", description="pentest tool", repo_url=repo_url)

    def test_reddit_requires_repo_link(self):
        self.assertEqual(rank_and_filter([self.post()], self.PROF), [])
        with_repo = self.post("https://github.com/a/b")
        self.assertEqual(rank_and_filter([with_repo], self.PROF), [with_repo])

    def test_rss_bonus_carries_keywordless_post(self):
        blog = Item(source="rss", source_id="b", title="Pre-auth chain", url="u")
        self.assertEqual(rank_and_filter([blog], self.PROF), [blog])
        self.assertEqual(rank_and_filter([blog], PROFILE), [])

    def test_find_repo_url(self):
        html = ('<a href="https://github.com/orgs/x/people">o</a> '
                '<a href="https://github.com/woldann/exoproc.git">r</a>')
        self.assertEqual(find_repo_url(html), "https://github.com/woldann/exoproc")
        self.assertEqual(find_repo_url("see https://gitlab.com/a/b."),
                         "https://gitlab.com/a/b")
        self.assertEqual(find_repo_url("https://github.com/user-only"), "")


class ThresholdTest(unittest.TestCase):
    PROF = {**PROFILE, "weak_keywords": ["reverse-engineering"],
            "include": PROFILE["include"] + ["reverse-engineering"],
            "focus_tags": {**PROFILE["focus_tags"], "reversing": ["decompiler"]},
            "_settings": {**PROFILE["_settings"],
                          "score_threshold": {"github": 10.0, "default": 3.0}}}

    def test_weak_keyword_alone_is_worthless(self):
        game = score_item(repo("x/skate", "reverse-engineering of a game"),
                          self.PROF)
        tool = score_item(repo("x/dc", "reverse-engineering decompiler"),
                          self.PROF)
        self.assertEqual(game._relevance, 0)
        self.assertEqual(tool._relevance, 3.5)

    def test_per_source_threshold(self):
        gh = repo("x/a", "exploit pentest", spd=1)          # ~5.5
        post = Item(source="reddit", source_id="r", title="exploit pentest",
                    url="u")                                 # 4.0
        self.assertEqual(rank_and_filter([gh, post], self.PROF), [post])

    def test_cve_cluster_flagged(self):
        burst = [Item(source="github", source_id=f"t/{i}", author="t",
                      title=f"t/CVE-2026-{i}-PoC", url="u",
                      description="exploit pentest", stars_per_day=50)
                 for i in range(3)]
        lone = Item(source="github", source_id="w/x", author="w",
                    title="w/CVE-2026-9", url="u",
                    description="exploit pentest", stars_per_day=50)
        out = rank_and_filter(burst + [lone], PROFILE)
        self.assertTrue(all("suspicious" in it.tags for it in burst))
        self.assertNotIn("suspicious", lone.tags)
        self.assertEqual(len(out), 4)


class WatchlistTest(unittest.TestCase):
    # Reddit items carry no momentum, so score == relevance: easy to place
    # exactly around a threshold. Reddit bar 8.0, margin 0.6 -> band [4.8, 8.0).
    PROF = {
        "include": ["exploit", "pentest", "rce", "cve"],
        "exclude": [],
        "focus_tags": {"redteam": ["c2", "implant"]},
        "weak_keywords": ["reverse-engineering"],
        "_settings": {"score_threshold": {"reddit": 8.0, "default": 3.0},
                      "min_relevance": 2.0, "focus_min_hits": 2,
                      "watchlist": {"margin": 0.6, "max": 15}},
    }

    def post(self, desc, sid="r"):
        it = Item(source="reddit", source_id=sid, title="t", url="u", description=desc)
        return score_item(it, self.PROF)

    def test_near_miss_lands_on_watchlist(self):
        near = self.post("exploit pentest rce")            # 3x2 = 6.0, in band
        out = watchlist_candidates([near], self.PROF)
        self.assertEqual([it.source_id for it in out], ["r"])
        self.assertIn("watchlist", near.tags)

    def test_too_far_below_is_excluded(self):
        low = self.post("exploit pentest")                 # 2x2 = 4.0 < 4.8
        self.assertEqual(watchlist_candidates([low], self.PROF), [])

    def test_above_bar_is_not_watchlist(self):
        good = self.post("exploit pentest rce cve")        # 4x2 = 8.0 >= 8
        self.assertEqual(watchlist_candidates([good], self.PROF), [])

    def test_source_bonus_alone_is_not_enough(self):
        prof = {**self.PROF, "_settings": {**self.PROF["_settings"],
                "source_bonus": {"rss": 6.0},
                "score_threshold": {"rss": 8.0, "default": 3.0}}}
        blog = score_item(Item(source="rss", source_id="b", title="t", url="u"), prof)
        self.assertEqual(blog.score, 6.0)                  # in band, but no keyword
        self.assertEqual(watchlist_candidates([blog], prof), [])

    def test_reported_items_are_excluded(self):
        near = self.post("exploit pentest rce")
        self.assertEqual(
            watchlist_candidates([near], self.PROF, exclude={near.dedup_key}), [])


class GitHubSliceTest(unittest.TestCase):
    def test_two_weekly_slices(self):
        from datetime import date
        self.assertEqual(created_slices(date(2026, 10, 14), 14, 7), [
            ("2026-10-08", "2026-10-14"), ("2026-10-01", "2026-10-07")])

    def test_uneven_slices(self):
        from datetime import date
        self.assertEqual(created_slices(date(2026, 10, 14), 10, 7), [
            ("2026-10-08", "2026-10-14"), ("2026-10-05", "2026-10-07")])


class TierTest(unittest.TestCase):
    def test_relative_to_source_threshold(self):
        from skoll.scoring import score_tier
        st = {"score_threshold": {"github": 10.0, "reddit": 4.0},
              "score_tiers": {"top": 2.5, "high": 1.5}}
        self.assertEqual(score_tier(25, "github", st), "top")
        self.assertEqual(score_tier(15, "github", st), "high")
        self.assertEqual(score_tier(12, "github", st), "mid")
        self.assertEqual(score_tier(11.5, "reddit", st), "top")   # 2.9x
        self.assertEqual(score_tier(6, "reddit", st), "high")


class MatchTest(unittest.TestCase):
    def test_hyphen_flexible(self):
        for text in ("a red team tool", "red_team kit", "redteam ops", "red-team"):
            self.assertEqual(_match(["red-team"], text), ["red-team"], text)
        self.assertEqual(_match(["red-team"], "shared teams"), [])

    def test_trailing_hyphen_is_prefix(self):
        self.assertEqual(_match(["awesome-"], "awesome-reverse-engineering"),
                         ["awesome-"])
        self.assertEqual(_match(["awesome-"], "an awesome tool"), [])

    def test_plural(self):
        self.assertEqual(_match(["payload"], "hidden payloads"), ["payload"])
        self.assertEqual(_match(["c2"], "c2s"), [])

    def test_whole_word(self):
        self.assertEqual(_match(["soc"], "socket library"), [])
        self.assertEqual(_match(["c2"], "a c2 framework"), ["c2"])


class StoreTest(unittest.TestCase):
    def test_only_reported_items_are_remembered(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / "t.db")
            a, b = repo("x/a"), repo("x/b")
            self.assertEqual(store.filter_new([a, b]), [a, b])
            store.mark_seen(a, "p")
            self.assertEqual(store.filter_new([a, b]), [b])
            store.close()


class SourceHealthTest(unittest.TestCase):
    def test_stale_source_is_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            s = Store(Path(d) / "h.db")
            s.record_source_counts("p", {"github": 10, "reddit": 0}, day="2026-11-15")
            for day in ("2026-11-16", "2026-11-17", "2026-11-18"):
                s.record_source_counts("p", {"github": 0, "reddit": 0}, day=day)
            stale = s.stale_sources("p", ["github", "reddit"], days=3, day="2026-11-18")
            self.assertEqual(stale, {"github": 3, "reddit": 3})  # last good / first record 11-15
            s.close()

    def test_healthy_and_unknown_not_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            s = Store(Path(d) / "h.db")
            s.record_source_counts("p", {"github": 5}, day="2026-11-17")
            s.record_source_counts("p", {"github": 0}, day="2026-11-18")   # gap 1 < 3
            self.assertEqual(s.stale_sources("p", ["github"], days=3, day="2026-11-18"), {})
            # a source with no record yet is skipped, not flagged
            self.assertEqual(s.stale_sources("p", ["rss"], days=3, day="2026-11-18"), {})
            s.close()

    def test_rerun_same_day_keeps_best_count(self):
        with tempfile.TemporaryDirectory() as d:
            s = Store(Path(d) / "h.db")
            s.record_source_counts("p", {"github": 0}, day="2026-11-18")
            s.record_source_counts("p", {"github": 7}, day="2026-11-18")  # later run recovered
            self.assertEqual(s.stale_sources("p", ["github"], days=1, day="2026-11-18"), {})
            s.close()


class ReportTest(unittest.TestCase):
    def test_day_folder_and_variants(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            write_reports([], "p", date="2026-10-14", root=root)
            write_reports([], "p", date="2026-10-14", root=root, focus="redteam")
            write_reports([], "p", date="2026-10-14", root=root, dry_run=True)
            day = root / "p" / "2026-10-14"
            self.assertEqual(sorted(f.name for f in day.iterdir()), [
                "digest.dry-run.md", "digest.md", "digest.redteam.md",
                "prompt.dry-run.md", "prompt.md", "prompt.redteam.md",
                "report.dry-run.html", "report.html", "report.redteam.html"])
            self.assertTrue((root / "p" / "latest.prompt.md").exists())

    def test_prompt_and_digest_carry_watchlist(self):
        main = [repo("x/a", "exploit pentest")]
        watch = repo("x/b", "exploit recon")
        watch.tags = ["watchlist"]
        prompt = build_prompt(main, "2026-10-14", watchlist=[watch])
        self.assertIn("WATCHLIST (1)", prompt)
        self.assertIn("[1]", prompt)       # main candidate
        self.assertIn("[2]", prompt)       # watchlist continues the numbering
        self.assertIn("x/b", prompt)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            write_reports(main, "p", date="2026-10-14", root=root, watchlist=[watch])
            digest = (root / "p" / "2026-10-14" / "digest.md").read_text()
            self.assertIn("On the radar (1)", digest)
            self.assertIn("x/b", digest)


ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><entry>
<author><name>/u/someone</name></author>
<category term="redteamsec" label="r/redteamsec"/>
<content type="html">&lt;div class="md"&gt;&lt;p&gt;New C2 &amp;amp; loader&lt;/p&gt;&lt;/div&gt; submitted by &lt;a href="https://www.reddit.com/user/someone"&gt; /u/someone &lt;/a&gt; &lt;span&gt;&lt;a href="https://example.com/tool"&gt;[link]&lt;/a&gt;&lt;/span&gt;</content>
<id>t3_abc</id><link href="https://www.reddit.com/r/redteamsec/comments/abc/x/"/>
<published>2026-10-13T05:28:00+00:00</published><title>x</title></entry></feed>"""


class RedditParseTest(unittest.TestCase):
    def test_entry_fields(self):
        e = feedparser.parse(ATOM).entries[0]
        body = e["content"][0]["value"]
        self.assertEqual(_external_link(body), "https://example.com/tool")
        self.assertEqual(_clean_body(body), "New C2 & loader")
        self.assertEqual(_entry_date(e),
                         datetime(2026, 10, 13, 5, 28, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
