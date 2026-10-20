"""Telegram integration: formatting, config edits, notify — no network."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skoll.config import replace_top_level_key, save_integrations
from skoll.integrations import (
    TelegramError, format_telegram_messages, notify_run, public_telegram,
    telegram_settings,
)
from skoll.models import Item


def item(title="tool", url="https://example.com/t", source="github", **kw):
    return Item(source=source, source_id=title, title=title, url=url, **kw)


class SettingsTest(unittest.TestCase):
    def test_defaults_disabled(self):
        tg = telegram_settings({})
        self.assertFalse(tg["enabled"])
        self.assertFalse(public_telegram({})["configured"])

    def test_env_overrides_file(self):
        integ = {"telegram": {"bot_token": "file", "chat_id": "1"}}
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "env",
                                     "TELEGRAM_CHAT_ID": "99"}):
            tg = telegram_settings(integ)
        self.assertEqual(tg["bot_token"], "env")
        self.assertEqual(tg["chat_id"], "99")
        file_only = telegram_settings(integ, env=False)
        self.assertEqual(file_only["bot_token"], "file")

    def test_public_view_hides_token(self):
        pub = public_telegram({"telegram": {
            "enabled": True, "bot_token": "secret", "chat_id": "42"}})
        self.assertTrue(pub["bot_token_set"])
        self.assertTrue(pub["configured"])
        self.assertNotIn("secret", str(pub))
        self.assertNotIn("bot_token", pub)


class FormatTest(unittest.TestCase):
    def test_html_escapes_title(self):
        msgs = format_telegram_messages(
            [item("<script>x</script>", url="https://ex.com/?q=1&y=2")],
            "cybersec", "2026-10-16")
        self.assertEqual(len(msgs), 1)
        self.assertIn("&lt;script&gt;", msgs[0])
        self.assertNotIn("<script>", msgs[0])
        self.assertIn("🐺 Sköll", msgs[0])
        self.assertIn("cybersec", msgs[0])

    def test_empty_run(self):
        msg = format_telegram_messages([], "p", "2026-10-16")[0]
        self.assertIn("No new items", msg)

    def test_caps_and_splits(self):
        items = [item(f"repo-{i}", url=f"https://github.com/a/{i}", stars=i)
                 for i in range(8)]
        msgs = format_telegram_messages(items, "p", "2026-10-16", max_items=3)
        blob = "\n".join(msgs)
        self.assertIn("showing 3", blob)
        self.assertIn("…and 5 more", blob)
        self.assertNotIn("repo-7", blob)
        for m in msgs:
            self.assertLessEqual(len(m), 4096)


class NotifyTest(unittest.TestCase):
    def test_disabled_is_a_no_op(self):
        with patch("skoll.integrations.telegram_call") as call:
            notify_run({}, [item()], "p", "2026-10-16")
            notify_run({"telegram": {"enabled": False, "bot_token": "t",
                                     "chat_id": "1"}}, [item()], "p", "2026-10-16")
        call.assert_not_called()

    def test_failure_does_not_raise(self):
        integ = {"telegram": {"enabled": True, "bot_token": "t", "chat_id": "1"}}
        with patch("skoll.integrations.send_telegram_messages",
                   side_effect=TelegramError("boom")):
            notify_run(integ, [item()], "p", "2026-10-16")  # must not raise


class YamlEditTest(unittest.TestCase):
    def test_replace_keeps_other_comments(self):
        src = ("# keep me\nsettings:\n  x: 1\n\n# noise\n"
               "profiles:\n  a:\n    sources: [rss]\n")
        out = replace_top_level_key(src, "integrations", {
            "telegram": {"enabled": True, "bot_token": "tok", "chat_id": "9"}})
        self.assertIn("# keep me", out)
        self.assertIn("# noise", out)
        self.assertIn("profiles:", out)
        self.assertIn("bot_token: tok", out)

    def test_save_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text("profiles:\n  a:\n    sources: [rss]\n", encoding="utf-8")
            save_integrations(path, {"telegram": {
                "enabled": True, "bot_token": "abc", "chat_id": "-1",
                "send_on_run": True, "max_items": 5}})
            text = path.read_text(encoding="utf-8")
            self.assertIn("profiles:", text)
            self.assertIn("bot_token: abc", text)


if __name__ == "__main__":
    unittest.main()
