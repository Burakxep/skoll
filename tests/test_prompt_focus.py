"""settings.prompt_focus injects optional per-profile guidance into the analysis
prompt, without touching the committed template (so it stays generic)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from skoll import report
from skoll.models import Item


def repo(name):
    return Item(source="github", source_id=name, title=name,
                url=f"https://x/{name}", description="exploit toolkit")


class PromptFocusTest(unittest.TestCase):
    def test_default_prompt_has_no_guidance_block(self):
        p = report.build_prompt([repo("x/a")], "2026-11-20")
        self.assertNotIn("Profile-specific guidance", p)
        self.assertIn("--- CANDIDATES (1) ---", p)  # template still renders

    def test_focus_text_is_injected(self):
        focus = "Audience: the example team; be terse."
        p = report.build_prompt([repo("x/a")], "2026-11-20", extra=focus)
        self.assertIn("Profile-specific guidance", p)
        self.assertIn(focus, p)
        # sits above the candidate list, as guidance rather than data
        self.assertLess(p.index(focus), p.index("--- CANDIDATES"))

    def test_blank_focus_is_ignored(self):
        p = report.build_prompt([repo("x/a")], "2026-11-20", extra="   \n  ")
        self.assertNotIn("Profile-specific guidance", p)

    def test_end_to_end_through_write_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = report.write_reports(
                [repo("x/a")], "p", root=Path(tmp),
                extra="Audience: the example team.")
            self.assertIn("Audience: the example team.",
                          paths["prompt"].read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
