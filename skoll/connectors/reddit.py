"""Reddit connector via the public Atom/RSS feeds. No key.

Reddit now answers unauthenticated `.json` requests with HTTP 403, but the
`.rss` listings still work. They are rate limited hard (~1 request/minute
keyless), so all subreddits are fetched in ONE multireddit request
(`/r/a+b+c/new/.rss`). The feed carries no score/comment counts, so Reddit
items rank on keyword relevance only (no momentum).
"""
from __future__ import annotations

import calendar
import html
import re
import time
from datetime import datetime, timezone, timedelta

import feedparser

from .base import Connector, find_repo_url, http_get
from ..models import Item

BASE = "https://www.reddit.com"
MAX_WAIT = 65  # seconds we're willing to wait for a rate-limit reset


class RedditConnector(Connector):
    name = "reddit"

    def fetch(self) -> list[Item]:
        cfg = self.profile.get("reddit", {})
        subreddits = cfg.get("subreddits", [])
        if not subreddits:
            return []
        listing = cfg.get("listing", "new")          # new | hot | top
        limit = min(int(cfg.get("limit", 100)), 100)
        days = int(cfg.get("within_days", 7))
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        url = f"{BASE}/r/{'+'.join(subreddits)}/{listing}/.rss"
        params = {"limit": limit}
        if listing == "top":
            params["t"] = "week"
        text = self._get(url, params)
        if text is None:
            return []

        out: list[Item] = []
        seen_urls: set[str] = set()
        for entry in feedparser.parse(text).entries:
            created = _entry_date(entry)
            if created and created < cutoff:
                continue  # also drops ancient stickied posts in 'hot'
            permalink = entry.get("link", "")
            body = ""
            if entry.get("content"):
                body = entry["content"][0].get("value", "")
            sub = ((entry.get("tags") or [{}])[0].get("term")) or ""
            oid = (entry.get("id") or permalink).removeprefix("t3_")
            link = _external_link(body) or permalink
            if link in seen_urls:
                continue  # same link cross-posted to several subreddits
            seen_urls.add(link)
            out.append(Item(
                source="reddit",
                source_id=f"{sub}_{oid}",
                title=entry.get("title", "") or "",
                url=link,
                description=_clean_body(body)[:800],
                repo_url=find_repo_url(body),
                author=(entry.get("author") or "").removeprefix("/u/"),
                created_at=created,
                topics=[sub] if sub else [],
                raw={"subreddit": sub, "permalink": permalink},
            ))
        return out

    def _get(self, url: str, params: dict) -> str | None:
        for attempt in (1, 2):
            try:
                resp = http_get(url, params=params,
                                headers={"Accept": "application/atom+xml"})
            except Exception as e:  # noqa: BLE001
                print(f"  [reddit] request failed: {e}")
                return None
            if resp.status_code == 200:
                return resp.text
            if resp.status_code == 429 and attempt == 1:
                wait = _reset_seconds(resp)
                if wait <= MAX_WAIT:
                    print(f"  [reddit] rate limited, waiting {wait}s ...")
                    time.sleep(wait)
                    continue
            print(f"  [reddit] HTTP {resp.status_code} for {url}")
            return None
        return None


def _reset_seconds(resp) -> int:
    try:
        return int(float(resp.headers.get("x-ratelimit-reset", 60))) + 1
    except ValueError:
        return 61


def _entry_date(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc)
    return None


def _external_link(body: str) -> str:
    """Link posts carry the target URL in a '[link]' anchor."""
    m = re.search(r'<a href="([^"]+)">\[link\]</a>', body)
    if m and "reddit.com/" not in m.group(1):
        return m.group(1)
    return ""


def _clean_body(body: str) -> str:
    body = body.split("submitted by", 1)[0]  # drop the footer
    body = html.unescape(re.sub(r"<[^>]+>", " ", body))
    return re.sub(r"\s+", " ", body).strip()
