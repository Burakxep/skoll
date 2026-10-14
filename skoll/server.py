"""Local web app: `python -m skoll serve` -> http://127.0.0.1:8765

Serves the normal dashboard (report.html) with a Run bar added to its header.
Clicking Run starts the same pipeline as `skoll run` in a background thread,
shows its log, then reloads the page with the freshly written report.
Stdlib only, bound to localhost.
"""
from __future__ import annotations

import contextlib
import html
import json
import re
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .config import ConfigError, get_profile, list_profiles, load_config
from .pipeline import run_profile
from . import report as report_mod

RUNBAR_MARK = "<!--SKOLL_RUNBAR-->"


class _Log:
    """File-like that collects what the pipeline prints."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self._buf = ""
        self._lock = threading.Lock()

    def write(self, s: str) -> int:
        with self._lock:
            self._buf += s
            *done, self._buf = self._buf.split("\n")
            self.lines.extend(done)
        return len(s)

    def flush(self) -> None:
        pass

    def snapshot(self) -> list[str]:
        with self._lock:
            return self.lines + ([self._buf] if self._buf else [])


class Job:
    """One scan at a time; state is polled by the page."""

    def __init__(self, config_path: str | None) -> None:
        self.config_path = config_path
        self.lock = threading.Lock()
        self.state = "idle"          # idle | running | done | error
        self.log = _Log()
        self.report: Path | None = None   # file written by the last finished run
        self.report_profile = ""
        self.error = ""
        self.counts: dict = {}

    def start(self, profile: str, focus: str | None, dry_run: bool) -> bool:
        with self.lock:
            if self.state == "running":
                return False
            self.state, self.log, self.report, self.error, self.counts = \
                "running", _Log(), None, "", {}
        threading.Thread(target=self._run, args=(profile, focus, dry_run),
                         daemon=True).start()
        return True

    def _run(self, profile: str, focus: str | None, dry_run: bool) -> None:
        try:
            config = load_config(self.config_path)
            prof = get_profile(config, profile)
            with contextlib.redirect_stdout(self.log):
                print(f"Running profile '{profile}'"
                      + (f" (focus={focus})" if focus else "")
                      + (" [dry run]" if dry_run else ""))
                res = run_profile(profile, prof, focus=focus, dry_run=dry_run)
            self.counts = res["counts"]
            self.report, self.report_profile = Path(res["paths"]["html"]), profile
            self.state = "done"
        except Exception as e:  # noqa: BLE001 - surfaced to the page
            self.error = f"{type(e).__name__}: {e}"
            self.log.write("\n" + traceback.format_exc())
            self.state = "error"

    def status(self) -> dict:
        return {"state": self.state, "log": self.log.snapshot()[-200:],
                "error": self.error, "counts": self.counts}


def latest_report(profile: str) -> Path | None:
    """Newest main (non-focus, non-dry) dashboard for a profile."""
    base = report_mod.REPORTS / profile
    days = sorted(base.glob("*/report.html"), key=lambda p: p.parent.name)
    return days[-1] if days else None


def render_page(job: Job, config_path: str | None, profile: str | None) -> str:
    """The dashboard of `profile` (this server's last run, else the newest file
    on disk, else an empty one) with the Run bar injected into its header."""
    cfg = load_config(config_path)
    names = list_profiles(cfg)
    profile = profile if profile in names else (names[0] if names else "")
    path = job.report if job.report and job.report_profile == profile         and job.report.exists() else latest_report(profile)
    if path:
        page = path.read_text(encoding="utf-8")
    else:
        page = report_mod.build_html([], profile, report_mod._today())
    tags = focus_tags(cfg["profiles"][profile]) if profile else []
    opt = lambda v, label, sel=False: (  # noqa: E731
        f'<option value="{html.escape(v)}"{" selected" if sel else ""}>{html.escape(label)}</option>')
    bar = (report_mod.TEMPLATES / "runbar.html").read_text(encoding="utf-8")
    bar = bar.replace("__PROFILES__", "".join(opt(n, n, n == profile) for n in names))
    bar = bar.replace("__FOCUS__", "".join(opt(t, t) for t in tags))
    if RUNBAR_MARK in page:
        return page.replace(RUNBAR_MARK, bar, 1)
    # Report written by an older version (buttons in the header, no marker):
    # move them next to the Run bar so it matches the current layout.
    page = re.sub(r'<button class="act-btn".*?</button>', "", page, flags=re.S)
    row = f'<div class="actionbar">{bar}<span class="grow"></span>{report_mod.ACTIONS}</div>'
    return page.replace("</header>", row + "</header>", 1)


def focus_tags(profile: dict) -> list[str]:
    tags = profile.get("focus_tags")
    if tags is None:
        tags = profile.get("scoring", {}).get("focus_tags", {})
    return list(tags) if isinstance(tags, dict) else []


def make_handler(job: Job, config_path: str | None, port: int):
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a) -> None:  # keep the terminal quiet
            pass

        # -- helpers
        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code: int = 200) -> None:
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")

        def _host_ok(self) -> bool:  # blocks DNS-rebinding style access
            return self.headers.get("Host", "") in allowed_hosts

        # -- routes
        def do_GET(self) -> None:  # noqa: N802
            if not self._host_ok():
                return self._json({"error": "bad host"}, 403)
            path = urlparse(self.path).path
            if path == "/":
                try:
                    q = parse_qs(urlparse(self.path).query).get("profile", [None])[0]
                    return self._send(200, render_page(job, config_path, q).encode("utf-8"),
                                      "text/html; charset=utf-8")
                except ConfigError as e:
                    return self._json({"error": str(e)}, 500)
            if path == "/api/status":
                return self._json(job.status())
            self._json({"error": "not found"}, 404)

        def do_POST(self) -> None:  # noqa: N802
            if not self._host_ok() or self.headers.get("Content-Type", "") \
                    .split(";")[0] != "application/json":
                return self._json({"error": "forbidden"}, 403)
            if urlparse(self.path).path != "/api/run":
                return self._json({"error": "not found"}, 404)
            try:
                n = int(self.headers.get("Content-Length", "0"))
                data = json.loads(self.rfile.read(n) or b"{}")
                cfg = load_config(config_path)
                profile = str(data.get("profile", ""))
                get_profile(cfg, profile)
                focus = data.get("focus") or None
                if focus is not None and focus not in focus_tags(cfg["profiles"][profile]):
                    return self._json({"error": f"unknown focus '{focus}'"}, 400)
            except (ValueError, ConfigError) as e:
                return self._json({"error": str(e)}, 400)
            if not job.start(profile, focus, bool(data.get("dry_run"))):
                return self._json({"error": "a scan is already running"}, 409)
            self._json({"ok": True})

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8765, config_path: str | None = None,
          open_browser: bool = True) -> None:
    job = Job(config_path)
    httpd = ThreadingHTTPServer((host, port), make_handler(job, config_path, port))
    url = f"http://127.0.0.1:{port}"
    print(f"Sköll web app: {url}   (Ctrl+C to stop)")
    if open_browser:
        import webbrowser
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        httpd.server_close()
