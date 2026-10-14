"""GitHub connector — the primary source.

Two strategies, union'ed:
  - 'new born'  : created:>cutoff  (genuinely new repos)
  - 'rising'    : pushed:>cutoff   (recently active repos that are still young)

Both are capped by `max_repo_age_days`, so long-established repos that are
merely popular (tens of thousands of stars, years old) never crowd out the
genuinely new ones.

Search results are sorted by stars and capped at `per_page`, which favours
older repos (more time to collect stars). So the 'new born' window is split
into `created_slice_days` slices queried separately: a 1-day-old repo only
competes with repos of its own week, not with 2-week-old ones.

Keyless works (10 search req/minute, 60 core req/hour). A free GITHUB_TOKEN
raises that to 30 search req/minute and 5000 core req/hour.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone, timedelta
from typing import Any

from .base import Connector, http_get
from ..config import github_token
from ..models import Item

API = "https://api.github.com"


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _stars_per_day(stars: int, created: datetime | None) -> float:
    if not created:
        return 0.0
    age_days = max((datetime.now(timezone.utc) - created).total_seconds() / 86400, 1.0)
    return round(stars / age_days, 2)


def created_slices(today, days: int, slice_days: int) -> list[tuple[str, str]]:
    """Split the last `days` days (ending today) into consecutive date ranges
    of `slice_days`, newest first, as (start, end) YYYY-MM-DD pairs."""
    out = []
    end = today
    first = today - timedelta(days=days - 1)
    while end >= first:
        start = max(end - timedelta(days=slice_days - 1), first)
        out.append((f"{start:%Y-%m-%d}", f"{end:%Y-%m-%d}"))
        end = start - timedelta(days=1)
    return out


def _reset_wait(resp) -> int | None:
    if resp.headers.get("x-ratelimit-remaining") != "0":
        return None  # a 403 that isn't rate limiting (e.g. abuse/blocked)
    try:
        reset = int(resp.headers.get("x-ratelimit-reset", "0"))
    except ValueError:
        return None
    return max(reset - int(time.time()), 0) + 1


class GitHubConnector(Connector):
    name = "github"

    def _headers(self) -> dict:
        h = {"Accept": "application/vnd.github+json"}
        tok = github_token()
        if tok:
            h["Authorization"] = f"Bearer {tok}"
        return h

    def fetch(self) -> list[Item]:
        cfg = self.profile.get("github", {})
        queries: list[str] = cfg.get("queries", [])
        if not queries:
            return []

        days = int(cfg.get("created_within_days", 14))
        min_stars = int(cfg.get("min_stars", 0))
        per_page = int(cfg.get("per_page", 30))
        readme_top = int(cfg.get("fetch_readme_top", 5))
        max_age = int(cfg.get("max_repo_age_days", 60))
        slice_days = int(cfg.get("created_slice_days", 7)) or days

        now = datetime.now(timezone.utc)
        cutoff = (now - timedelta(days=days)).strftime("%Y-%m-%d")
        age_cutoff = now - timedelta(days=max_age)

        filters = [f"created:{a}..{b}" for a, b in created_slices(now.date(), days, slice_days)]
        filters.append(f"pushed:>{cutoff} created:>{age_cutoff:%Y-%m-%d}")

        seen: dict[str, Item] = {}
        for q in queries:
            for f in filters:
                full_q = f"{q} {f}"
                if min_stars:
                    full_q += f" stars:>={min_stars}"
                for it in self._search(full_q, per_page):
                    seen.setdefault(it.source_id, it)  # first (created) wins

        # Safety net: never let an old repo through, whatever the query said.
        results = [it for it in seen.values()
                   if it.created_at and it.created_at >= age_cutoff]
        results.sort(key=lambda x: x.stars_per_day, reverse=True)

        # README excerpt only for the strongest handful (saves rate limit).
        for it in results[:readme_top]:
            it.readme_excerpt = self._readme_excerpt(it.source_id)

        return results

    def _search(self, query: str, per_page: int) -> list[Item]:
        params = {"q": query, "sort": "stars", "order": "desc",
                  "per_page": per_page}
        for attempt in (1, 2):
            try:
                resp = http_get(f"{API}/search/repositories",
                                headers=self._headers(), params=params)
            except Exception as e:  # noqa: BLE001
                print(f"  [github] request failed: {e}")
                return []
            if resp.status_code not in (403, 429):
                break
            # Search limit is per minute: wait for the reset once, then give up.
            wait = _reset_wait(resp)
            if attempt == 1 and wait is not None and wait <= 65:
                print(f"  [github] rate limited, waiting {wait}s ...")
                time.sleep(wait)
                continue
            print("  [github] rate limited. Set GITHUB_TOKEN to raise limits.")
            return []
        if resp.status_code != 200:
            print(f"  [github] HTTP {resp.status_code} for query: {query}")
            return []

        out = []
        for repo in resp.json().get("items", []):
            created = _parse_dt(repo.get("created_at"))
            stars = repo.get("stargazers_count", 0)
            out.append(Item(
                source="github",
                source_id=repo["full_name"],
                title=repo["full_name"],
                url=repo.get("html_url", ""),
                description=repo.get("description") or "",
                author=(repo.get("owner") or {}).get("login", ""),
                language=repo.get("language") or "",
                created_at=created,
                updated_at=_parse_dt(repo.get("pushed_at")),
                stars=stars,
                stars_per_day=_stars_per_day(stars, created),
                topics=repo.get("topics", []) or [],
                raw={"forks": repo.get("forks_count", 0),
                     "open_issues": repo.get("open_issues_count", 0)},
            ))
        return out

    def _readme_excerpt(self, full_name: str) -> str:
        try:
            resp = http_get(
                f"{API}/repos/{full_name}/readme",
                headers={**self._headers(), "Accept": "application/vnd.github.raw"},
            )
            if resp.status_code != 200:
                return ""
            text = resp.text
        except Exception:  # noqa: BLE001
            return ""

        # Strip markdown noise, grab first real paragraph.
        text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        text = re.sub(r"!\[.*?\]\(.*?\)", "", text)      # images
        text = re.sub(r"<[^>]+>", "", text)               # html tags/badges
        for block in text.split("\n\n"):
            line = block.strip()
            if len(line) > 60 and not line.startswith(("#", "[", "|", "-", "*")):
                return re.sub(r"\s+", " ", line)[:500]
        return ""
