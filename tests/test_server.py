"""Web app (`skoll serve`) and dashboard summary: offline, no scans are run."""
from __future__ import annotations

import json
import socket
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path

from skoll import report, server
from skoll.models import Item

CONFIG = """profiles:
  demo:
    sources: [rss]
    include: [exploit]
    focus_tags:
      recon: [recon]
"""


def item(source, tier, tags=()):
    return Item(source=source, source_id=source + tier, title="t", url="u",
                created_at=datetime(2026, 10, 12, tzinfo=timezone.utc),
                score=10, tier=tier, tags=list(tags))


class SummaryTest(unittest.TestCase):
    def test_header_has_run_marker_and_prompt_button(self):
        items = [item("github", "top", ["breakout"]), item("rss", "high"),
                 item("reddit", "mid", ["suspicious"])]
        page = report.build_html(items, "demo", "2026-10-14")
        header = page[page.index("<header"):page.index("</header>")]
        self.assertIn("<!--SKOLL_RUNBAR-->", header)
        self.assertIn('class="controls"', header)
        self.assertNotIn('class="kpis"', page)
        self.assertIn('data-open-doc="prompt"', page)
        self.assertNotIn('data-open-doc="digest"', page)

    def test_prompt_is_embedded_safely(self):
        it = item("github", "top")
        it.title = "</script><b>x"
        page = report.build_html([it], "demo", "2026-10-14")
        self.assertNotIn("</script><b>x", page)


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tmp = Path(self.tmp.name)
        (tmp / "config.yaml").write_text(CONFIG, encoding="utf-8")
        self._reports = report.REPORTS
        server.report_mod.REPORTS = tmp / "reports"
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        self.job = server.Job(str(tmp / "config.yaml"))
        self.httpd = ThreadingHTTPServer(
            ("127.0.0.1", self.port),
            server.make_handler(self.job, str(tmp / "config.yaml"), self.port))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        server.report_mod.REPORTS = self._reports
        self.tmp.cleanup()

    def call(self, path, data=None, headers=None):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(data).encode() if data is not None else None,
            headers=headers or {})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8")

    def test_empty_dashboard_has_run_bar(self):
        code, body = self.call("/")
        self.assertEqual(code, 200)
        self.assertIn('id="rb-run"', body)
        self.assertIn('<option value="recon">', body)
        self.assertIn('data-open-doc="prompt"', body)

    def test_old_design_report_is_skipped(self):
        d = server.report_mod.REPORTS / "demo" / "2026-10-01"
        d.mkdir(parents=True)
        old = '<html><header><h1>old design</h1></header></html>'
        (d / "report.html").write_text(old, encoding="utf-8")
        _, body = self.call("/")
        self.assertNotIn("old design", body)
        self.assertIn('id="rb-run"', body)

    def test_newest_current_report_is_served(self):
        base = server.report_mod.REPORTS / "demo"
        for day in ("2026-10-01", "2026-10-02"):
            (base / day).mkdir(parents=True)
        cur = report.build_html([item("rss", "high")], "demo", "2026-10-01")
        (base / "2026-10-01" / "report.html").write_text(cur, encoding="utf-8")
        (base / "2026-10-02" / "report.html").write_text("<html>stale</html>", encoding="utf-8")
        _, body = self.call("/")
        self.assertIn("2026-10-01", body)
        self.assertNotIn("stale", body)
        self.assertEqual(body.count('id="rb-run"'), 1)

    def test_status_idle(self):
        code, body = self.call("/api/status")
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["state"], "idle")

    def test_run_rejects_foreign_content_type_and_unknown_profile(self):
        code, _ = self.call("/api/run", {"profile": "demo"},
                            {"Content-Type": "text/plain"})
        self.assertEqual(code, 403)
        code, _ = self.call("/api/run", {"profile": "nope"},
                            {"Content-Type": "application/json"})
        self.assertEqual(code, 400)
        code, _ = self.call("/api/run", {"profile": "demo", "focus": "zzz"},
                            {"Content-Type": "application/json"})
        self.assertEqual(code, 400)

    def test_reports_are_not_served_statically(self):
        code, _ = self.call("/reports/demo/2026-10-01/report.html")
        self.assertEqual(code, 404)

    def test_foreign_host_header_is_refused(self):
        code, _ = self.call("/", headers={"Host": "evil.example"})
        self.assertEqual(code, 403)


if __name__ == "__main__":
    unittest.main()
