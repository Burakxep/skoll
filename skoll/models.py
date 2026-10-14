"""Shared data model. Every connector produces Items in this one shape."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Item:
    """A single discovered thing (repo, post, article) from any source."""

    source: str              # "github" | "hackernews" | "reddit" | "rss"
    source_id: str           # stable per-source id, used for dedup
    title: str
    url: str
    description: str = ""
    author: str = ""
    language: str = ""

    created_at: datetime | None = None   # when the thing was created/published
    updated_at: datetime | None = None   # last activity (push, edit)

    stars: int = 0
    stars_per_day: float = 0.0
    points: int = 0          # HN points / reddit upvotes
    comments: int = 0

    topics: list[str] = field(default_factory=list)
    readme_excerpt: str = ""
    repo_url: str = ""       # code repo a post/article links to (non-GitHub sources)

    # Filled in by scoring:
    score: float = 0.0
    tier: str = ""           # "top" | "high" | "mid", relative to source threshold
    tags: list[str] = field(default_factory=list)          # focus tags matched
    matched_keywords: list[str] = field(default_factory=list)

    # Filled in by the store:
    first_seen: datetime | None = None   # first date WE saw it

    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def dedup_key(self) -> str:
        return f"{self.source}:{self.source_id}"

    def to_row(self) -> dict[str, Any]:
        d = asdict(self)
        for k in ("created_at", "updated_at", "first_seen"):
            v = d.get(k)
            d[k] = v.isoformat() if isinstance(v, datetime) else None
        return d
