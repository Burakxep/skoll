"""Outbound notifications (Telegram first). Config lives under `integrations:`
in config.yaml. A failing integration must not crash a run, same as a dead
source. No extra dependencies: Bot API over `requests`.
"""
from __future__ import annotations

import html
import os
from typing import Any

import requests

from .models import Item
from . import report as report_mod

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
TG_LIMIT = 4096
DEFAULT_TELEGRAM = {
    "enabled": False,
    "bot_token": "",
    "chat_id": "",
    "send_on_run": True,
    "max_items": 20,
}


class TelegramError(Exception):
    """Safe to print: never includes the bot token."""


def _as_bool(v: Any, default: bool = False) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return bool(v)
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "on"):
        return True
    if s in ("0", "false", "no", "off", ""):
        return False
    return default


def telegram_settings(integrations: dict[str, Any] | None, *,
                      env: bool = True) -> dict[str, Any]:
    """Merged Telegram config. `env=False` reads only the file (for saves)."""
    raw = dict(DEFAULT_TELEGRAM)
    block = (integrations or {}).get("telegram") or {}
    if isinstance(block, dict):
        raw.update(block)
    token = str(raw.get("bot_token") or "").strip()
    chat = str(raw.get("chat_id") or "").strip()
    if env:
        token = (os.environ.get("TELEGRAM_BOT_TOKEN") or token).strip()
        chat = (os.environ.get("TELEGRAM_CHAT_ID") or chat).strip()
    try:
        max_items = int(raw.get("max_items") or 20)
    except (TypeError, ValueError):
        max_items = 20
    return {
        "enabled": _as_bool(raw.get("enabled"), False),
        "bot_token": token,
        "chat_id": chat,
        "send_on_run": _as_bool(raw.get("send_on_run"), True),
        "max_items": max(1, min(max_items, 50)),
    }


def public_telegram(integrations: dict[str, Any] | None) -> dict[str, Any]:
    """JSON-safe view for the web app: never includes the token."""
    tg = telegram_settings(integrations)
    return {
        "enabled": tg["enabled"],
        "chat_id": tg["chat_id"],
        "send_on_run": tg["send_on_run"],
        "max_items": tg["max_items"],
        "bot_token_set": bool(tg["bot_token"]),
        "configured": bool(tg["bot_token"] and tg["chat_id"]),
    }


def _src_label(source: str) -> str:
    return {"github": "GitHub", "hackernews": "HN",
            "reddit": "Reddit", "rss": "Blog"}.get(source, source)


def _h(s: str) -> str:
    return html.escape(s or "", quote=True)


def format_telegram_messages(items: list[Item], profile: str, date: str,
                             max_items: int = 20) -> list[str]:
    """HTML messages, each under Telegram's 4096-char cap."""
    n = len(items)
    shown = items[:max_items]
    head = (f"<b>🐺 Sköll · {_h(profile)} · {_h(date)}</b>\n"
            f"{n} new item(s)" +
            (f" · showing {len(shown)}" if n > len(shown) else ""))
    if not shown:
        return [head + "\nNo new items passed the filter."]
    lines: list[str] = []
    for i, it in enumerate(shown, 1):
        title = _h((it.title or "").strip() or it.url or "(untitled)")
        url = (it.url or "").strip()
        name = f'<a href="{_h(url)}">{title}</a>' if url else title
        extra = []
        if it.source == "github" and it.stars:
            extra.append(f"⭐{it.stars}")
        if it.stars_per_day:
            extra.append(f"~{it.stars_per_day:g}/d")
        if "breakout" in it.tags:
            extra.append("breakout")
        if "suspicious" in it.tags:
            extra.append("⚠ suspicious")
        meta = " · ".join([_src_label(it.source), *extra])
        lines.append(f"{i}. {name} · {meta}")
    if n > len(shown):
        lines.append(f"…and {n - len(shown)} more")
    chunks: list[str] = []
    buf = head
    for line in lines:
        nxt = buf + "\n" + line
        if len(nxt) > TG_LIMIT:
            chunks.append(buf)
            buf = line
        else:
            buf = nxt
    if buf:
        chunks.append(buf)
    # A single over-long line (huge title/url) still has to fit.
    out = []
    for c in chunks:
        if len(c) <= TG_LIMIT:
            out.append(c)
        else:
            out.append(c[: TG_LIMIT - 1] + "…")
    return out


def telegram_call(token: str, method: str,
                  payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """POST to Bot API. Errors never include the token."""
    if not token:
        raise TelegramError("missing bot token")
    url = TELEGRAM_API.format(token=token, method=method)
    try:
        r = requests.post(url, json=payload or {}, timeout=20)
        data = r.json()
    except TelegramError:
        raise
    except Exception as e:  # noqa: BLE001
        raise TelegramError(f"network: {type(e).__name__}") from e
    if not isinstance(data, dict) or not data.get("ok"):
        desc = ""
        if isinstance(data, dict):
            desc = str(data.get("description") or "")
        raise TelegramError(desc or f"HTTP {getattr(r, 'status_code', '?')}")
    return data


def send_telegram_messages(token: str, chat_id: str, texts: list[str]) -> int:
    if not token:
        raise TelegramError("missing bot token")
    if not chat_id:
        raise TelegramError("missing chat id")
    sent = 0
    for text in texts:
        telegram_call(token, "sendMessage", {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        })
        sent += 1
    return sent


def list_telegram_chats(token: str) -> list[dict[str, str]]:
    """Recent chats that messaged the bot (user must /start first)."""
    data = telegram_call(token, "getUpdates", {"timeout": 0})
    chats: dict[str, dict[str, str]] = {}
    for upd in data.get("result") or []:
        if not isinstance(upd, dict):
            continue
        for key in ("message", "edited_message", "channel_post",
                    "my_chat_member", "chat_member"):
            node = upd.get(key) or {}
            chat = node.get("chat") if isinstance(node, dict) else None
            if not isinstance(chat, dict) or chat.get("id") is None:
                continue
            cid = str(chat["id"])
            name = (chat.get("title")
                    or " ".join(x for x in (chat.get("first_name"),
                                            chat.get("last_name")) if x)
                    or chat.get("username")
                    or cid)
            chats[cid] = {"id": cid, "type": str(chat.get("type") or ""),
                          "title": str(name)}
    return list(chats.values())


def send_test(token: str, chat_id: str) -> None:
    send_telegram_messages(token, chat_id, [
        "<b>🐺 Sköll</b>\nTelegram is connected. New scan items will land here."])


def send_latest_digest(integrations: dict[str, Any] | None, profile: str,
                       token: str = "", chat_id: str = "") -> int:
    """Push the last real run's digest.md (plain text), for the Send button."""
    tg = telegram_settings(integrations)
    token = (token or tg["bot_token"]).strip()
    chat_id = (chat_id or tg["chat_id"]).strip()
    if not token or not chat_id:
        raise TelegramError("set bot token and chat id first")
    path = report_mod.REPORTS / profile / "latest.md"
    if not path.exists():
        raise TelegramError("no report yet — run a scan first")
    text = path.read_text(encoding="utf-8").strip() or "(empty digest)"
    chunks, buf = [], ""
    for line in text.splitlines():
        nxt = (buf + "\n" + line) if buf else line
        if len(nxt) > TG_LIMIT:
            if buf:
                chunks.append(buf)
            buf = line if len(line) <= TG_LIMIT else line[: TG_LIMIT - 1] + "…"
        else:
            buf = nxt
    if buf:
        chunks.append(buf)
    sent = 0
    for chunk in chunks:
        telegram_call(token, "sendMessage", {
            "chat_id": chat_id, "text": chunk,
            "disable_web_page_preview": True,
        })
        sent += 1
    return sent


def notify_run(integrations: dict[str, Any] | None, items: list[Item],
               profile: str, date: str) -> None:
    """Called after a real (non-dry) scan. Failures are printed, not raised."""
    tg = telegram_settings(integrations)
    if not tg["enabled"] or not tg["send_on_run"]:
        return
    if not tg["bot_token"] or not tg["chat_id"]:
        print("  [!] telegram enabled but bot_token/chat_id missing")
        return
    try:
        msgs = format_telegram_messages(items, profile, date, tg["max_items"])
        n = send_telegram_messages(tg["bot_token"], tg["chat_id"], msgs)
        print(f"  telegram: {n} message(s) sent ({len(items)} item(s))")
    except Exception as e:  # noqa: BLE001
        print(f"  [!] telegram failed: {e}")
