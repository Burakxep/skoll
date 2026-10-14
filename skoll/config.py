"""Config loading. The whole tool is topic-agnostic: everything that makes a
profile 'cybersec' vs anything else lives in config.yaml, never in code."""
from __future__ import annotations

import os
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
    return prof


def list_profiles(config: dict[str, Any]) -> list[str]:
    return list(config.get("profiles", {}).keys())


def github_token() -> str | None:
    """Optional. Keyless works; a free token just raises rate limits."""
    return os.environ.get("GITHUB_TOKEN") or None
