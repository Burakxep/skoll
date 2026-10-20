"""Ties it all together: fetch -> dedup -> score/filter -> report."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .connectors.github import GitHubConnector
from .connectors.hackernews import HackerNewsConnector
from .connectors.reddit import RedditConnector
from .connectors.rss import RSSConnector
from .models import Item
from .scoring import (detect_breakouts, is_relevant, rank_and_filter, score_item,
                      score_tier)
from .store import Store
from . import report as report_mod
from .integrations import notify_run

CONNECTORS = {
    "github": GitHubConnector,
    "hackernews": HackerNewsConnector,
    "reddit": RedditConnector,
    "rss": RSSConnector,
}


def fetch_all(profile: dict[str, Any]) -> list[Item]:
    """Fetch from every enabled source; a failing source is skipped."""
    enabled = profile.get("sources", list(CONNECTORS.keys()))
    raw: list[Item] = []
    for src in enabled:
        cls = CONNECTORS.get(src)
        if not cls:
            print(f"  [!] unknown source '{src}', skipping")
            continue
        print(f"  fetching {src} ...")
        try:
            got = cls(profile).fetch()
            print(f"    {len(got)} raw item(s)")
            raw.extend(got)
        except Exception as e:  # noqa: BLE001
            print(f"    [!] {src} failed: {e}")
    return raw


def record_relevant(store: Store, raw: list[Item], profile_name: str,
                    profile: dict[str, Any], reported: set[str]) -> list[Item]:
    """Snapshot every relevant item (not just reported ones) for weekly trends.
    Returns the relevant items."""
    for it in raw:
        if not hasattr(it, "_relevance"):  # don't redo (and reset tags of) ranked items
            score_item(it, profile)
    relevant = [it for it in raw if is_relevant(it, profile)]
    store.record_observations(relevant, profile_name, reported=reported)
    return relevant


def item_from_observation(row: Any) -> Item:
    """Rebuild a reported Item from its daily snapshot (no README/topics)."""
    created = row["created_at"]
    return Item(
        source=row["source"], source_id=row["dedup_key"].split(":", 1)[1],
        title=row["title"] or "", url=row["url"] or "",
        description=row["description"] or "", author=row["author"] or "",
        repo_url=row["repo_url"] or "",
        created_at=datetime.fromisoformat(created) if created else None,
        stars=row["stars"] or 0, stars_per_day=row["stars_per_day"] or 0.0,
        points=row["points"] or 0, comments=row["comments"] or 0,
        score=row["score"] or 0.0,
        tags=(row["tags"] or "").split(),
        matched_keywords=[k for k in (row["keywords"] or "").split(",") if k],
    )


def earlier_today(store: Store, profile_name: str, profile: dict[str, Any], *,
                  exclude: set[str], focus: str | None = None,
                  day: str | None = None) -> list[Item]:
    """Items reported by earlier runs today, so a re-run adds to the day's
    report instead of replacing it with only the newest finds."""
    day = day or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    settings = profile.get("_settings", {})
    out = []
    for row in store.reported_on(profile_name, day):
        if row["dedup_key"] in exclude:
            continue
        it = item_from_observation(row)
        if focus and focus not in it.tags:
            continue
        it.tier = score_tier(it.score, it.source, settings)
        out.append(it)
    return out


def run_profile(profile_name: str, profile: dict[str, Any], *,
                focus: str | None = None, db_path=None,
                dry_run: bool = False) -> dict:
    # 1. fetch from every enabled source
    raw = fetch_all(profile)

    # 2. dedup against history (items reported on earlier days)
    store = Store(db_path)
    if dry_run:
        fresh = raw
        print(f"  [dry-run] skipping dedup/history ({len(raw)} items)")
    else:
        fresh = store.filter_new(raw)
        print(f"  {len(fresh)} new (after dedup)")

    # 3. score + filter + rank
    ranked = rank_and_filter(fresh, profile, focus=focus)
    print(f"  {len(ranked)} passed filter")

    # 3b. breakouts: already-reported repos whose stars exploded since
    if not dry_run:
        fresh_keys = {it.dedup_key for it in fresh}
        old = [score_item(it, profile) for it in raw if it.dedup_key not in fresh_keys]
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        baselines = store.star_baselines(profile_name, [it.dedup_key for it in old], today)
        breakouts = detect_breakouts(old, baselines, profile, focus=focus)
        if breakouts:
            print(f"  {len(breakouts)} breakout(s): " + ", ".join(
                f"{it.title} {it.raw['breakout']['from']}->{it.stars} stars" for it in breakouts))
            ranked = sorted(ranked + breakouts, key=lambda x: x.score, reverse=True)

    # 4. record only what gets reported; the rest is re-scored tomorrow
    report_items = ranked
    if not dry_run:
        # Earlier runs today: read before recording this run's snapshot.
        earlier = earlier_today(store, profile_name, profile,
                                exclude={it.dedup_key for it in ranked}, focus=focus)
        for it in ranked:
            store.mark_seen(it, profile_name)
        # Snapshot for the weekly report (also items reported on earlier days,
        # so their star growth stays visible).
        record_relevant(store, raw, profile_name, profile,
                        reported={it.dedup_key for it in ranked})
        if earlier:
            report_items = sorted(ranked + earlier, key=lambda x: x.score, reverse=True)
            print(f"  + {len(earlier)} reported earlier today (kept in today's report)")
    store.close()

    # 5. reports (the whole day's findings, not just this run's)
    readme_top = profile.get("github", {}).get("fetch_readme_top", 5)
    paths = report_mod.write_reports(report_items, profile_name, readme_top=readme_top,
                                     focus=focus, dry_run=dry_run)
    if not dry_run:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        notify_run(profile.get("_integrations") or {}, ranked, profile_name, day)
    return {"ranked": ranked, "paths": paths, "counts": {
        "raw": len(raw), "fresh": len(fresh), "kept": len(ranked),
        "report": len(report_items)}}
