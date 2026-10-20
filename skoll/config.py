"""Config loading. The whole tool is topic-agnostic: everything that makes a
profile 'cybersec' vs anything else lives in config.yaml, never in code."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config.yaml"
EXAMPLE_CONFIG = ROOT / "config.example.yaml"


class ConfigError(Exception):
    pass


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    path = Path(path) if path else DEFAULT_CONFIG
    if not path.exists():
        # Fall back to the example so a fresh clone still runs.
        if EXAMPLE_CONFIG.exists():
            path = EXAMPLE_CONFIG
        else:
            raise ConfigError(
                f"No config found. Copy config.example.yaml to config.yaml."
            )
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data


def writable_path(path: str | Path | None = None) -> Path:
    """File we may write secrets into. Never the committed example template."""
    requested = Path(path) if path else DEFAULT_CONFIG
    if EXAMPLE_CONFIG.exists() and requested.resolve() == EXAMPLE_CONFIG.resolve():
        requested = DEFAULT_CONFIG
    if not requested.exists():
        if EXAMPLE_CONFIG.exists():
            requested.write_text(EXAMPLE_CONFIG.read_text(encoding="utf-8"),
                                 encoding="utf-8")
        else:
            raise ConfigError("No config found to write.")
    return requested


def replace_top_level_key(text: str, key: str, value: Any,
                          comment: str = "") -> str:
    """Swap one top-level YAML mapping, leaving the rest of the file (and its
    comments) intact. Used so the Integrations UI doesn't rewrite keywords."""
    dumped = yaml.safe_dump({key: value}, sort_keys=False, allow_unicode=True)
    if not dumped.endswith("\n"):
        dumped += "\n"
    if comment:
        dumped = comment.rstrip() + "\n" + dumped
    pat = re.compile(rf"(?ms)^{re.escape(key)}:.*?(?=^[A-Za-z_]|\Z)")
    if pat.search(text):
        return pat.sub(dumped + "\n", text, count=1)
    return text.rstrip() + "\n\n" + dumped


def save_integrations(path: str | Path | None, integrations: dict[str, Any]) -> Path:
    dest = writable_path(path)
    text = dest.read_text(encoding="utf-8")
    dest.write_text(
        replace_top_level_key(text, "integrations", integrations),
        encoding="utf-8")
    return dest


def get_profile(config: dict[str, Any], name: str) -> dict[str, Any]:
    profiles = config.get("profiles", {})
    if name not in profiles:
        available = ", ".join(profiles) or "(none)"
        raise ConfigError(f"Profile '{name}' not found. Available: {available}")
    prof = dict(profiles[name])
    # Merge global exclude/settings into the profile for convenience.
    prof.setdefault("exclude", [])
    prof["exclude"] = list(config.get("global_exclude", [])) + list(prof["exclude"])
    prof["_settings"] = config.get("settings", {})
    prof["_integrations"] = config.get("integrations") or {}
    return prof


def list_profiles(config: dict[str, Any]) -> list[str]:
    return list(config.get("profiles", {}).keys())


def github_token() -> str | None:
    """Optional. Keyless works; a free token just raises rate limits."""
    return os.environ.get("GITHUB_TOKEN") or None
