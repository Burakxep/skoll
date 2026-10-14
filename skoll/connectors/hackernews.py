"""Hacker News connector via the Algolia API. Fully free, no key."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

from .base import Connector, find_repo_url, http_get
from ..models import Item

API = "https://hn.algolia.com/api/v1/search_by_date"


class HackerNewsConnector(Connector):
    name = "hackernews"

    def fetch(self) -> list[Item]:
        cfg = self.profile.get("hackernews", {})
        queries = cfg.get("queries", self.profile.get("include", [])[:5])
        days = int(cfg.get("within_days", 7))
        min_points = int(cfg.get("min_points", 5))
        cutoff = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())

        out: dict[str, Item] = {}
        for q in queries:
            try:
                resp = http_get(API, params={
                    "query": q, "tags": "story",
                    "numericFilters": f"created_at_i>{cutoff},points>={min_points}",
                    "hitsPerPage": 30,
                })
                if resp.status_code != 200:
                    continue
                hits = resp.json().get("hits", [])
            except Exception as e:  # noqa: BLE001
                print(f"  [hn] request failed: {e}")
                continue

            for h in hits:
                oid = str(h.get("objectID"))
                url = h.get("url") or f"https://news.ycombinator.com/item?id={oid}"
                created = None
                if h.get("created_at_i"):
                    created = datetime.fromtimestamp(h["created_at_i"], tz=timezone.utc)
                out.setdefault(oid, Item(
                    source="hackernews",
                    source_id=oid,
                    title=h.get("title") or "",
                    url=url,
                    description=h.get("story_text") or "",
                    repo_url=find_repo_url(h.get("url") or "",
                                           h.get("story_text") or ""),
                    author=h.get("author") or "",
                    created_at=created,
                    points=h.get("points", 0),
                    comments=h.get("num_comments", 0),
                    raw={"hn_url": f"https://news.ycombinator.com/item?id={oid}"},
                ))
        return list(out.values())
