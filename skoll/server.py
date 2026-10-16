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
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from .config import (ConfigError, get_profile, list_profiles, load_config,
                     save_integrations, writable_path)
from .pipeline import run_profile
from . import report as report_mod
from . import integrations as integ

RUNBAR_MARK = "<!--SKOLL_RUNBAR-->"


def i18n_patch() -> str:
    """A served report embeds the i18n dictionary it was built with, which may
    predate web-app-only keys. Top the dictionary up (without overwriting)
    before i18n.js runs on DOMContentLoaded."""
    data = json.dumps(report_mod.I18N, ensure_ascii=False).replace("</", "<\\/")
    return (
        "<script>(function(){var D=window.SKOLL_I18N;if(!D)return;"
        f"var P={data};"
        "for(var l in P){D[l]=D[l]||{};for(var k in P[l])"
        "if(D[l][k]==null)D[l][k]=P[l][k];}"
        "})();</script>")


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
    """Newest main (non-focus, non-dry) dashboard for a profile. Reports from
    older versions (no Run bar marker, older design) are skipped."""
    base = report_mod.REPORTS / profile
    days = sorted(base.glob("*/report.html"), key=lambda p: p.parent.name)
    for path in reversed(days):
        with contextlib.suppress(OSError):
            if RUNBAR_MARK in path.read_text(encoding="utf-8"):
                return path
    return None


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
    opt = lambda v, label, sel=False: (  # noqa: E731
        f'<option value="{html.escape(v)}"{" selected" if sel else ""}>{html.escape(label)}</option>')
    # Only offer the profile dropdown when there's a real choice. With one
    # profile it's just noise, so carry the value in a hidden input instead.
    if len(names) > 1:
        profile_control = ('<select id="rb-profile" aria-label="Profile" '
                           'data-i18n-aria="app.profile">'
                           + "".join(opt(n, n, n == profile) for n in names)
                           + '</select>')
    else:
        profile_control = (f'<input type="hidden" id="rb-profile" '
                           f'value="{html.escape(profile, quote=True)}">')
    bar = (report_mod.TEMPLATES / "runbar.html").read_text(encoding="utf-8")
    bar = bar.replace("__PROFILE_CONTROL__", profile_control)
    href = "/weekly?profile=" + quote(profile, safe="") if profile else "/weekly"
    bar = bar.replace("__WEEKLY_HREF__", html.escape(href, quote=True))
    return page.replace(RUNBAR_MARK, i18n_patch() + bar, 1)


def latest_weekly_report(profile: str) -> Path | None:
    """Newest weekly dashboard on disk for a profile (by ISO-week folder name)."""
    base = report_mod.REPORTS / profile / "weekly"
    weeks = sorted(base.glob("*/report.html"), key=lambda p: p.parent.name)
    return weeks[-1] if weeks else None


# A back-link to the daily dashboard, injected into the weekly page's header so
# the two pages navigate to each other in the web app (static files don't have it).
def _weekly_backlink(profile: str) -> str:
    # i18n_patch tops up the embedded dictionary, so data-i18n localises even on a
    # weekly report built before this key existed. Styled like a control button so
    # it sits cleanly next to the TR|EN / theme controls.
    href = "/?profile=" + quote(profile, safe="") if profile else "/"
    return (i18n_patch() + f'<a class="weekly-back" href="{html.escape(href, quote=True)}" '
            f'data-i18n="app.dashboard" style="height:44px;display:inline-flex;'
            f'align-items:center;text-decoration:none;border:1px solid var(--border);'
            f'border-radius:12px;padding:0 16px;font-weight:600;white-space:nowrap">'
            f'← Dashboard</a>')


def render_weekly(config_path: str | None, profile: str | None) -> tuple[str, int]:
    """The newest weekly report for `profile` with a back-link to the dashboard,
    or a small placeholder when none has been generated yet."""
    cfg = load_config(config_path)
    names = list_profiles(cfg)
    profile = profile if profile in names else (names[0] if names else "")
    path = latest_weekly_report(profile) if profile else None
    back = _weekly_backlink(profile)
    if path:
        page = path.read_text(encoding="utf-8")
        # Put the back-link in the header's control group (TR|EN / theme), so it
        # lines up on the right instead of wrapping under the logo. Fall back to
        # the end of the header if that group isn't found.
        if 'class="weekly-back"' not in page:
            if '<div class="controls">' in page:
                page = page.replace('<div class="controls">',
                                    '<div class="controls">' + back, 1)
            else:
                page = page.replace("</header>", back + "</header>", 1)
        return page, 200
    hint = ("No weekly report yet for "
            f"<b>{html.escape(profile or '-')}</b>. Generate it with "
            "<code>python -m skoll weekly --profile "
            f"{html.escape(profile or '&lt;profile&gt;')}</code>.")
    body = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>Sköll weekly · {html.escape(profile or "")}</title>'
            f'<style>body{{margin:0;background:#0b0d12;color:#e6e9ef;'
            f'font:16px/1.6 -apple-system,Segoe UI,Roboto,sans-serif;'
            f'display:flex;min-height:100vh;align-items:center;justify-content:center}}'
            f'.box{{max-width:560px;padding:0 24px;text-align:center}}'
            f'a{{color:#f5a524}}code{{background:#1a202b;border-radius:6px;padding:2px 8px}}'
            f'</style></head><body><div class="box"><h1>🐺 Sköll weekly</h1>'
            f'<p>{hint}</p><p><a href="{html.escape(("/?profile=" + quote(profile, safe="")) if profile else "/")}">← Back to the dashboard</a></p>'
            f'</div></body></html>')
    return body, 200


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

        def _read_json(self) -> dict:
            n = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(n) or b"{}")

        def _telegram_from_body(self, data: dict) -> tuple[str, str]:
            """Token/chat from the form (unsaved) with a fall-back to config/env."""
            cfg = load_config(config_path)
            saved = integ.telegram_settings(cfg.get("integrations"))
            token = str(data.get("bot_token") or "").strip() or saved["bot_token"]
            chat = str(data.get("chat_id") or "").strip() or saved["chat_id"]
            return token, chat

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
            if path == "/weekly":
                try:
                    q = parse_qs(urlparse(self.path).query).get("profile", [None])[0]
                    body, code = render_weekly(config_path, q)
                    return self._send(code, body.encode("utf-8"),
                                      "text/html; charset=utf-8")
                except ConfigError as e:
                    return self._json({"error": str(e)}, 500)
            if path == "/api/status":
                return self._json(job.status())
            if path == "/api/integrations":
                try:
                    cfg = load_config(config_path)
                except ConfigError as e:
                    return self._json({"error": str(e)}, 500)
                return self._json({"telegram": integ.public_telegram(
                    cfg.get("integrations"))})
            self._json({"error": "not found"}, 404)

        def do_POST(self) -> None:  # noqa: N802
            if not self._host_ok() or self.headers.get("Content-Type", "") \
                    .split(";")[0] != "application/json":
                return self._json({"error": "forbidden"}, 403)
            path = urlparse(self.path).path
            try:
                data = self._read_json()
            except (ValueError, json.JSONDecodeError) as e:
                return self._json({"error": str(e)}, 400)
            if path == "/api/run":
                return self._post_run(data)
            if path == "/api/integrations":
                return self._post_integrations(data)
            if path == "/api/integrations/telegram/test":
                return self._post_telegram_test(data)
            if path == "/api/integrations/telegram/chats":
                return self._post_telegram_chats(data)
            if path == "/api/integrations/telegram/send":
                return self._post_telegram_send(data)
            self._json({"error": "not found"}, 404)

        def _post_run(self, data: dict) -> None:
            try:
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

        def _post_integrations(self, data: dict) -> None:
            try:
                dest = writable_path(config_path)
                cfg = load_config(dest)
                saved = integ.telegram_settings(cfg.get("integrations"), env=False)
                token = str(data.get("bot_token") or "").strip() or saved["bot_token"]
                chat = str(data.get("chat_id", saved["chat_id"]) or "").strip()
                try:
                    max_items = int(data.get("max_items", saved["max_items"]))
                except (TypeError, ValueError):
                    max_items = saved["max_items"]
                block = cfg.get("integrations") if isinstance(
                    cfg.get("integrations"), dict) else {}
                block = dict(block)
                block["telegram"] = {
                    "enabled": integ._as_bool(data.get("enabled"), saved["enabled"]),
                    "bot_token": token,
                    "chat_id": chat,
                    "send_on_run": integ._as_bool(
                        data.get("send_on_run"), saved["send_on_run"]),
                    "max_items": max(1, min(max_items, 50)),
                }
                save_integrations(dest, block)
            except (ConfigError, OSError, ValueError) as e:
                return self._json({"error": str(e)}, 400)
            self._json({"ok": True, "telegram": integ.public_telegram(block)})

        def _post_telegram_test(self, data: dict) -> None:
            token, chat = self._telegram_from_body(data)
            try:
                integ.send_test(token, chat)
            except integ.TelegramError as e:
                return self._json({"error": str(e)}, 400)
            self._json({"ok": True})

        def _post_telegram_chats(self, data: dict) -> None:
            token, _ = self._telegram_from_body(data)
            try:
                chats = integ.list_telegram_chats(token)
            except integ.TelegramError as e:
                return self._json({"error": str(e)}, 400)
            self._json({"ok": True, "chats": chats})

        def _post_telegram_send(self, data: dict) -> None:
            try:
                cfg = load_config(config_path)
                profile = str(data.get("profile") or "")
                if profile:
                    get_profile(cfg, profile)
                else:
                    names = list_profiles(cfg)
                    profile = names[0] if names else ""
                if not profile:
                    return self._json({"error": "no profile"}, 400)
                token, chat = self._telegram_from_body(data)
                n = integ.send_latest_digest(
                    cfg.get("integrations"), profile, token=token, chat_id=chat)
            except (ConfigError, integ.TelegramError) as e:
                return self._json({"error": str(e)}, 400)
            self._json({"ok": True, "sent": n})

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
