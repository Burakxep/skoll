"""RSS / blog connector via feedparser. Fully free, no key.
This is the 'blogs & release feeds' source: Project Zero, PortSwigger Research,
SpecterOps, release feeds, etc."""
from __future__ import annotations

import calendar
import html
import re
from datetime import datetime, timezone, timedelta

import feedparser

from .base import Connector, find_repo_url
from ..models import Item


class RSSConnector(Connector):
    name = "rss"

    def fetch(self) -> list[Item]:
        cfg = self.profile.get("rss", {})
        feeds = cfg.get("feeds", [])
        days = int(cfg.get("within_days", 14))
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        out: list[Item] = []
        for feed_url in feeds:
            try:
                parsed = feedparser.parse(feed_url)
            except Exception as e:  # noqa: BLE001
                print(f"  [rss] {feed_url} failed: {e}")
                continue

            source_title = (parsed.feed.get("title") if parsed.feed else "") or feed_url
            for entry in parsed.entries:
                created = _entry_date(entry)
                if created and created < cutoff:
                    continue
                link = entry.get("link", "")
                if not link:
                    continue
                summary_html = entry.get("summary", "") or ""
                content_html = " ".join(c.get("value", "")
                                        for c in entry.get("content", []) or [])
                summary = _strip_html(summary_html)[:800]
                out.append(Item(
                    source="rss",
                    source_id=entry.get("id", link),
                    title=entry.get("title", "") or "",
                    url=link,
                    description=summary,
                    repo_url=find_repo_url(summary_html, content_html),
                    author=entry.get("author", "") or source_title,
                    created_at=created,
                    topics=[source_title],
                    raw={"feed": feed_url, "feed_title": source_title},
                ))
        return out


def _entry_date(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc)
    return None


def _strip_html(text: str) -> str:
    # Some feeds double-escape ("&lt;p&gt;"): unescape, strip tags, unescape.
    text = re.sub(r"<[^>]+>", " ", html.unescape(text))
    return re.sub(r"\s+", " ", html.unescape(text)).strip()
