"""Weekly trend analysis: this week vs the previous week.

Two signals, both deterministic:
  1. Cohort trend - relevant items grouped by CREATION date (last 7 days vs
     the 7 before), counted per source, focus tag and keyword. Works from the
     very first run because the sources already cover ~14 days.
  2. Star growth - GitHub repos observed on several days this week (from the
     daily `observations` snapshots); gets better the more days are recorded.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

from .models import Item
from .store import Store


# ---------------------------------------------------------------- model
@dataclass
class Window:
    start: date
    end: date  # inclusive

    def __contains__(self, d: date | None) -> bool:
        return d is not None and self.start <= d <= self.end

    @property
    def label(self) -> str:
        return f"{self.start:%Y-%m-%d} → {self.end:%Y-%m-%d}"


@dataclass
class Entry:
    """One relevant item, flattened from either a fresh Item or a DB row."""
    key: str
    source: str
    title: str
    url: str
    created: date | None
    score: float = 0.0
    stars: int = 0
    author: str = ""
    description: str = ""
    repo_url: str = ""
    tags: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    reported: bool = False
    tier: str = ""


@dataclass
class Trend:
    name: str
    this: int
    last: int

    @property
    def delta(self) -> int:
        return self.this - self.last

    @property
    def pct(self) -> float | None:
        """Percent change; None when last week was zero (new this week)."""
        return None if self.last == 0 else round(100.0 * self.delta / self.last)


@dataclass
class Gainer:
    key: str
    title: str
    url: str
    first_stars: int
    last_stars: int
    days: int

    @property
    def gain(self) -> int:
        return self.last_stars - self.first_stars

    @property
    def per_day(self) -> float:
        return round(self.gain / self.days, 1) if self.days else 0.0


@dataclass
class WeeklyReport:
    this: Window
    last: Window
    total: Trend
    by_source: list[Trend]
    by_tag: list[Trend]
    keywords: list[Trend]          # most active this week
    rising: list[Trend]            # biggest increase vs last week
    new_keywords: list[Trend]      # absent last week
    gainers: list[Gainer]
    top_items: list[Entry]
    history_days: int              # distinct days with observations (last 14)
    partial_sources: list[str] = field(default_factory=list)  # not compared

    @property
    def week_id(self) -> str:
        y, w, _ = self.this.end.isocalendar()
        return f"{y}-W{w:02d}"


# ---------------------------------------------------------------- windows
def windows(end: date) -> tuple[Window, Window]:
    """Rolling 7-day windows ending at `end`: (this week, previous week)."""
    this = Window(end - timedelta(days=6), end)
    last = Window(end - timedelta(days=13), end - timedelta(days=7))
    return this, last


# ---------------------------------------------------------------- entries
def _to_date(v: Any) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return datetime.fromisoformat(str(v)).date()
    except ValueError:
        return None


def entry_from_item(it: Item) -> Entry:
    return Entry(key=it.dedup_key, source=it.source, title=it.title, url=it.url,
                 created=_to_date(it.created_at), score=it.score, stars=it.stars,
                 author=it.author, description=it.description,
                 repo_url=it.repo_url, tags=list(it.tags),
                 keywords=list(it.matched_keywords))


def entry_from_row(row: Any) -> Entry:
    return Entry(key=row["dedup_key"], source=row["source"] or "",
                 title=row["title"] or "", url=row["url"] or "",
                 created=_to_date(row["created_at"]), score=row["score"] or 0.0,
                 stars=row["stars"] or 0, author=row["author"] or "",
                 description=row["description"] or "",
                 repo_url=row["repo_url"] or "",
                 tags=(row["tags"] or "").split(),
                 keywords=[k for k in (row["keywords"] or "").split(",") if k],
                 reported=bool(row["reported"]))


def merge_entries(rows: Iterable[Any], items: Iterable[Item] = ()) -> dict[str, Entry]:
    """Latest snapshot per item: DB rows oldest→newest, then today's fresh items
    on top. Reported-ness sticks once any snapshot says so."""
    out: dict[str, Entry] = {}
    for row in rows:
        e = entry_from_row(row)
        prev = out.get(e.key)
        e.reported = e.reported or bool(prev and prev.reported)
        out[e.key] = e
    for it in items:
        e = entry_from_item(it)
        prev = out.get(e.key)
        e.reported = bool(prev and prev.reported)
        out[e.key] = e
    return out


# ---------------------------------------------------------------- analysis
def _trends(this: Counter, last: Counter) -> list[Trend]:
    return [Trend(k, this.get(k, 0), last.get(k, 0)) for k in set(this) | set(last)]


def _count(entries: Iterable[Entry], window: Window, attr: str) -> Counter:
    c: Counter = Counter()
    for e in entries:
        if e.created in window:
            v = getattr(e, attr)
            c.update(v if isinstance(v, list) else [v])
    return c


def star_gainers(rows: Iterable[Any], window: Window, top: int = 10) -> list[Gainer]:
    """GitHub repos with the most stars gained between their first and last
    observation inside `window` (needs >= 2 observed days)."""
    first: dict[str, Any] = {}
    last: dict[str, Any] = {}
    for row in rows:  # oldest first
        d = _to_date(row["day"])
        if row["source"] != "github" or d not in window:
            continue
        first.setdefault(row["dedup_key"], row)
        last[row["dedup_key"]] = row
    out = []
    for key, a in first.items():
        b = last[key]
        days = (_to_date(b["day"]) - _to_date(a["day"])).days
        if days >= 1:
            out.append(Gainer(key, b["title"] or key, b["url"] or "",
                              a["stars"] or 0, b["stars"] or 0, days))
    out = [g for g in out if g.gain > 0]
    out.sort(key=lambda g: (g.gain, g.per_day), reverse=True)
    return out[:top]


def partial_sources(entries: Iterable[Entry], last_w: Window,
                    slack_days: int = 2) -> list[str]:
    """Sources whose data doesn't reach back to the start of last week, e.g.
    Reddit's RSS only spans a few days. Comparing them would fake a surge."""
    oldest: dict[str, date] = {}
    for e in entries:
        if e.created:
            oldest[e.source] = min(e.created, oldest.get(e.source, e.created))
    limit = last_w.start + timedelta(days=slack_days)
    return sorted(s for s, d in oldest.items() if d > limit)


def analyze(entries: dict[str, Entry], rows: list[Any], end: date, *,
            weak_keywords: Iterable[str] = (), top_n: int = 15,
            min_keyword_count: int = 2) -> WeeklyReport:
    this_w, last_w = windows(end)
    every = list(entries.values())
    partial = partial_sources(every, last_w)
    # Trend counts only use sources that cover both weeks; top items use all.
    vals = [e for e in every if e.source not in partial]

    total = Trend("total",
                  sum(1 for e in vals if e.created in this_w),
                  sum(1 for e in vals if e.created in last_w))

    by_source = _trends(_count(every, this_w, "source"), _count(every, last_w, "source"))
    by_source.sort(key=lambda t: (-t.this, t.name))

    from .scoring import STATUS_TAGS  # flags like suspicious/breakout aren't categories
    by_tag = [t for t in _trends(_count(vals, this_w, "tags"), _count(vals, last_w, "tags"))
              if t.name not in STATUS_TAGS]
    by_tag.sort(key=lambda t: (-t.this, -t.delta, t.name))

    # Weak keywords (e.g. reverse-engineering) are too broad to be a trend.
    weak = {w.lower() for w in weak_keywords}
    kw = [t for t in _trends(_count(vals, this_w, "keywords"),
                             _count(vals, last_w, "keywords"))
          if t.name.lower() not in weak]
    keywords = sorted((t for t in kw if t.this >= min_keyword_count),
                      key=lambda t: (-t.this, -t.delta, t.name))[:top_n]
    rising = sorted((t for t in kw if t.delta > 0 and t.last > 0
                     and t.this >= min_keyword_count),
                    key=lambda t: (-t.delta, -t.this, t.name))[:top_n]
    new_keywords = sorted((t for t in kw if t.last == 0
                           and t.this >= min_keyword_count),
                          key=lambda t: (-t.this, t.name))[:top_n]

    top_items = sorted((e for e in every if e.created in this_w),
                       key=lambda e: e.score, reverse=True)[:top_n]

    history_days = len({r["day"] for r in rows
                        if _to_date(r["day"]) in Window(last_w.start, this_w.end)})

    return WeeklyReport(this=this_w, last=last_w, total=total,
                        by_source=by_source, by_tag=by_tag, keywords=keywords,
                        rising=rising, new_keywords=new_keywords,
                        gainers=star_gainers(rows, this_w),
                        top_items=top_items, history_days=history_days,
                        partial_sources=partial)


# ---------------------------------------------------------------- orchestration
def collect(profile_name: str, profile: dict[str, Any], *,
            end: date | None = None, fetch: bool = True,
            db_path=None) -> WeeklyReport:
    """Fetch today's items (unless fetch=False), snapshot them, then analyze
    the last 14 days of fresh + recorded data."""
    from .pipeline import fetch_all, record_relevant  # avoid import cycle

    end = end or datetime.now(timezone.utc).date()
    _, last_w = windows(end)
    store = Store(db_path)
    try:
        items: list[Item] = []
        if fetch:
            items = record_relevant(store, fetch_all(profile), profile_name,
                                    profile, reported=set())
        rows = store.observations(profile_name, f"{last_w.start:%Y-%m-%d}",
                                  f"{end:%Y-%m-%d}")
        entries = merge_entries(rows, items)
        for e in entries.values():
            e.reported = e.reported or store.was_reported(e.key)
    finally:
        store.close()
    from .scoring import score_tier
    for e in entries.values():
        e.tier = score_tier(e.score, e.source, profile.get("_settings", {}))
    return analyze(entries, rows, end,
                   weak_keywords=profile.get("weak_keywords", []))

