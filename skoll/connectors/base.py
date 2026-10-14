"""Connector base + shared HTTP helper."""
from __future__ import annotations

import re
from typing import Any

import requests

from ..models import Item

from .. import __url__, __version__

USER_AGENT = f"skoll/{__version__} (+{__url__})"
TIMEOUT = 20


def http_get(url: str, *, headers: dict | None = None,
             params: dict | None = None) -> requests.Response:
    h = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        h.update(headers)
    resp = requests.get(url, headers=h, params=params, timeout=TIMEOUT)
    return resp


_REPO = re.compile(
    r"https?://(?:www\.)?(github\.com|gitlab\.com|codeberg\.org)"
    r"/([\w.-]+)/([\w.-]+)", re.I)
# github.com/<these>/... are site pages, not repos
_NOT_OWNERS = {"orgs", "features", "sponsors", "topics", "marketplace",
               "settings", "about", "login", "search", "apps", "collections",
               "trending", "user-attachments", "notifications", "explore",
               "pricing", "enterprise", "security", "site", "readme"}


def find_repo_url(*texts: str) -> str:
    """First code-repository link (GitHub/GitLab/Codeberg) in the given text
    or HTML, normalized to https://host/owner/repo. '' if none."""
    for text in texts:
        for host, owner, repo in _REPO.findall(text or ""):
            if owner.lower() in _NOT_OWNERS:
                continue
            repo = repo.rstrip(".").removesuffix(".git")
            if repo:
                return f"https://{host.lower()}/{owner}/{repo}"
    return ""


class Connector:
    name = "base"

    def __init__(self, profile: dict[str, Any]):
        self.profile = profile

    def fetch(self) -> list[Item]:
        raise NotImplementedError
