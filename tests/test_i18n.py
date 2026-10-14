"""Every translation key used by the pages must exist in both languages."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
I18N = json.loads((ROOT / "templates" / "i18n.json").read_text(encoding="utf-8"))

PATTERNS = [
    r'data-i18n(?:-ph|-aria|-title)?="([\w.]+)"',     # templates
    r'\bi18n\(\s*["\']([\w.]+)["\']',                 # python helper
    r'\bt_en\(\s*["\']([\w.]+)["\']',
    r'skollT\(\s*"([\w.]+)"',                         # page JS
    r'\(\s*"(note\.\w+)"',                            # weekly note keys
    r'"((?:th|empty)\.\w+)"',                         # keys passed around as strings
]


def used_keys() -> set[str]:
    keys: set[str] = set()
    files = list((ROOT / "templates").glob("*.html")) + list((ROOT / "templates").glob("*.js")) \
        + list((ROOT / "skoll").glob("*.py"))
    for f in files:
        # skip comment lines (they show example keys)
        text = "\n".join(l for l in f.read_text(encoding="utf-8").splitlines()
                         if not l.lstrip().startswith(("//", "#")))
        for pat in PATTERNS:
            keys.update(re.findall(pat, text))
    return keys


class I18nTest(unittest.TestCase):
    def test_same_keys_in_both_languages(self):
        self.assertEqual(set(I18N["en"]) ^ set(I18N["tr"]), set())

    def test_every_used_key_is_defined(self):
        used = {k for k in used_keys() if not k.endswith(".")}  # dynamic prefixes
        self.assertGreater(len(used), 40)
        self.assertEqual(sorted(used - set(I18N["en"])), [])

    def test_dynamic_tier_keys(self):
        for t in ("top", "high", "mid"):
            self.assertIn(f"tier.{t}", I18N["en"])
            self.assertIn(f"legend.tier.{t}", I18N["en"])

    def test_placeholders_match(self):
        for key, en in I18N["en"].items():
            self.assertEqual(set(re.findall(r"\{(\w+)\}", en)),
                             set(re.findall(r"\{(\w+)\}", I18N["tr"][key])), key)


if __name__ == "__main__":
    unittest.main()
