"""ASCII banner printed on run, ffuf-style."""
from __future__ import annotations

import os
import sys

from . import __version__

# Wolf chasing the sun. Sköll — the Norse wolf that pursues the sun across the sky.
_ART = r"""
       \   |   /                       /\   /\
        \  |  /                       //\\_//\\
     '---( @ )---'                    \_     _/
        /  |  \                        / . . \      __
       /   |   \                       \  ^  /     /  \
                                       |_____|    /    \
       ___ _  _____ _    _            /       \__/     |
      / __| |/ / _ \ |  | |          /                 |
      \__ \ ' < (_) | |__| |__      /   /\       /\    |
      |___/_|\_\___/____|____|      (___/  \_____/  \___/
       the wolf that chases the sun
"""

# Fallback for very narrow / no-color terminals.
_PLAIN = r"""
  ___ _  _____ _    _
 / __| |/ / _ \ |  | |
 \__ \ ' < (_) | |__| |__
 |___/_|\_\___/____|____|  SKOLL
 the wolf that chases the sun
"""


def _supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def banner(tagline: str = "") -> str:
    art = _ART if sys.stdout.isatty() else _PLAIN
    line = f"\n{art}\n       v{__version__}"
    if tagline:
        line += f"  ::  {tagline}"
    if _supports_color():
        # amber/orange, matching the chased sun
        line = f"\033[38;5;214m{line}\033[0m"
    return line + "\n"


def print_banner(tagline: str = "") -> None:
    print(banner(tagline))
