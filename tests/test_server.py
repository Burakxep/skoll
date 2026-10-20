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
        self.assertIn('id="rb-profile"', body)             # profile value carried
        self.assertNotIn('<select id="rb-profile"', body)  # hidden for a single profile
        self.assertNotIn('id="rb-focus"', body)            # focus selector removed
        self.assertNotIn('id="cat"', body)                 # category menu removed
        self.assertIn('data-open-doc="prompt"', body)
        self.assertIn('id="rb-integ"', body)
        self.assertIn('id="integ-panel"', body)
        self.assertIn('data-i18n="app.integrations"', body)

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

    def test_profile_dropdown_returns_with_multiple_profiles(self):
        cfg = Path(self.tmp.name) / "multi.yaml"
        cfg.write_text("profiles:\n  a:\n    sources: [rss]\n"
                       "  b:\n    sources: [rss]\n", encoding="utf-8")
        page = server.render_page(server.Job(str(cfg)), str(cfg), "a")
        self.assertIn('<select id="rb-profile"', page)
        self.assertIn('<option value="a"', page)
        self.assertIn('<option value="b"', page)

    def test_dashboard_links_to_weekly(self):
        _, body = self.call("/")
        self.assertIn('class="weekly"', body)
        self.assertIn('href="/weekly?profile=demo"', body)
        self.assertNotIn("__WEEKLY_HREF__", body)

    def test_weekly_placeholder_when_none(self):
        code, body = self.call("/weekly")
        self.assertEqual(code, 200)
        self.assertIn("No weekly report yet", body)
        self.assertIn('href="/?profile=demo"', body)

    def test_weekly_report_is_served_with_backlink(self):
        d = server.report_mod.REPORTS / "demo" / "weekly" / "2026-W42"
        d.mkdir(parents=True)
        (d / "report.html").write_text(
            "<html><header>weekly body</header></html>", encoding="utf-8")
        code, body = self.call("/weekly?profile=demo")
        self.assertEqual(code, 200)
        self.assertIn("weekly body", body)
        self.assertIn('class="weekly-back"', body)
        self.assertIn('href="/?profile=demo"', body)

    def test_weekly_refuses_foreign_host(self):
        code, _ = self.call("/weekly", headers={"Host": "evil.example"})
        self.assertEqual(code, 403)

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

    def test_integrations_get_hides_token(self):
        cfg = Path(self.tmp.name) / "config.yaml"
        cfg.write_text(cfg.read_text(encoding="utf-8") + (
            "\nintegrations:\n  telegram:\n    enabled: true\n"
            "    bot_token: SECRET\n    chat_id: '42'\n"), encoding="utf-8")
        code, body = self.call("/api/integrations")
        self.assertEqual(code, 200)
        data = json.loads(body)["telegram"]
        self.assertTrue(data["configured"])
        self.assertTrue(data["enabled"])
        self.assertEqual(data["chat_id"], "42")
        self.assertNotIn("SECRET", body)
        self.assertNotIn("bot_token", data)

    def test_integrations_save_keeps_existing_token(self):
        cfg = Path(self.tmp.name) / "config.yaml"
        self.call("/api/integrations", {
            "enabled": True, "bot_token": "tok1", "chat_id": "7",
            "send_on_run": True, "max_items": 8,
        }, {"Content-Type": "application/json"})
        code, body = self.call("/api/integrations", {
            "enabled": True, "chat_id": "8", "send_on_run": False, "max_items": 3,
        }, {"Content-Type": "application/json"})
        self.assertEqual(code, 200)
        self.assertIn("tok1", cfg.read_text(encoding="utf-8"))
        self.assertEqual(json.loads(body)["telegram"]["chat_id"], "8")
        self.assertFalse(json.loads(body)["telegram"]["send_on_run"])

    def test_telegram_test_requires_token(self):
        code, body = self.call("/api/integrations/telegram/test", {},
                               {"Content-Type": "application/json"})
        self.assertEqual(code, 400)
        self.assertIn("token", json.loads(body)["error"].lower())


if __name__ == "__main__":
    unittest.main()
