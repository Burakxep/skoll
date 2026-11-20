"""Ties it all together: fetch -> dedup -> score/filter -> report."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from .connectors.github import GitHubConnector
from .connectors.hackernews import HackerNewsConnector
from .connectors.reddit import RedditConnector
from .connectors.rss import RSSConnector
from .models import Item
from .scoring import (detect_breakouts, is_relevant, rank_and_filter, score_item,
                      score_tier, watchlist_candidates)
from .store import Store
from . import report as report_mod
from .integrations import notify_run

CONNECTORS = {
    "github": GitHubConnector,
    "hackernews": HackerNewsConnector,
    "reddit": RedditConnector,
    "rss": RSSConnector,
}


def dedup_by_key(items: list[Item]) -> list[Item]:
    """Collapse items that share a dedup_key within a single fetch — the same
    arXiv paper matching several query feeds, or the same repo returned by
    several GitHub queries. Keeps the first occurrence."""
    seen: set[str] = set()
    out: list[Item] = []
    for it in items:
        if it.dedup_key in seen:
            continue
        seen.add(it.dedup_key)
        out.append(it)
    return out


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
    # 1. fetch from every enabled source (collapsing within-run duplicates:
    # one paper/repo can match several query feeds or GitHub queries)
    raw = dedup_by_key(fetch_all(profile))

    # 2. dedup against history (items reported on earlier days)
    store = Store(db_path)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
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
        baselines = store.star_baselines(profile_name, [it.dedup_key for it in old], today)
        breakouts = detect_breakouts(old, baselines, profile, focus=focus)
        if breakouts:
            print(f"  {len(breakouts)} breakout(s): " + ", ".join(
                f"{it.title} {it.raw['breakout']['from']}->{it.stars} stars" for it in breakouts))
            ranked = sorted(ranked + breakouts, key=lambda x: x.score, reverse=True)

    # 4. record only what gets reported; the rest is re-scored tomorrow
    report_items = ranked
    stale: dict[str, int] = {}
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

        # source-health canary: record today's per-source raw counts, then flag
        # any enabled source that has returned nothing for too many days (a feed
        # or API that silently goes dead, the way reddit did).
        enabled = profile.get("sources", list(CONNECTORS.keys()))
        src_counts = Counter(it.source for it in raw)
        store.record_source_counts(
            profile_name, {s: src_counts.get(s, 0) for s in enabled})
        health_days = int((profile.get("_settings") or {}).get("health_days", 3) or 0)
        if health_days:
            stale = store.stale_sources(profile_name, enabled, days=health_days)
        for src, gap in stale.items():
            print(f"  ⚠ source health: '{src}' has returned 0 items for "
                  f"{gap} day(s) — the connector may be broken")

    # 4b. watchlist: relevant near-misses just below the bar. Because below-bar
    # items are never marked reported (so a riser can still graduate), without a
    # cooldown the same near-miss resurfaces in the "on the radar" band every
    # single run. Hold a candidate back for `watchlist.cooldown_days` days after
    # it last appeared, so the band rotates instead of repeating yesterday's list.
    reported_keys = {it.dedup_key for it in report_items}
    wl_cfg = (profile.get("_settings") or {}).get("watchlist") or {}
    cooldown = int(wl_cfg.get("cooldown_days", 3) or 0)
    held = store.watchlist_cooldown(
        profile_name, [it.dedup_key for it in fresh], today, cooldown)

    # Surge override: a held near-miss still comes back if its stars have jumped
    # since it last showed (gained >= resurface_gain, or multiplied by
    # >= resurface_ratio) — a breakout shouldn't be muted by the cooldown.
    surge_gain = int(wl_cfg.get("resurface_gain", 25) or 0)
    surge_ratio = float(wl_cfg.get("resurface_ratio", 2.0) or 0)
    by_key = {it.dedup_key: it for it in fresh}
    cool: set[str] = set()
    surged = 0
    for key, base in held.items():
        it = by_key.get(key)
        if it is not None and (
                (surge_gain and it.stars - base >= surge_gain) or
                (surge_ratio and it.stars >= surge_ratio * max(base, 1))):
            surged += 1  # grew enough to earn its way back onto the radar
            continue
        cool.add(key)

    watch = watchlist_candidates(fresh, profile, focus=focus,
                                 exclude=reported_keys | cool)
    if not dry_run:
        store.mark_watchlisted(
            profile_name, {it.dedup_key: it.stars for it in watch}, today)
    store.close()
    if cool:
        print(f"  {len(cool)} watchlist near-miss(es) held back (cooldown {cooldown}d)")
    if surged:
        print(f"  {surged} held item(s) resurfaced (surged since last shown)")
    if watch:
        print(f"  {len(watch)} on the radar (watchlist, below bar)")

    # 5. reports (the whole day's findings, not just this run's)
    readme_top = profile.get("github", {}).get("fetch_readme_top", 5)
    prompt_focus = (profile.get("_settings") or {}).get("prompt_focus", "")
    paths = report_mod.write_reports(report_items, profile_name, readme_top=readme_top,
                                     focus=focus, dry_run=dry_run, watchlist=watch,
                                     extra=prompt_focus)
    if not dry_run:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        notify_run(profile.get("_integrations") or {}, ranked, profile_name, day,
                   health=stale)
    return {"ranked": ranked, "watchlist": watch, "stale_sources": stale,
            "paths": paths, "counts": {
                "raw": len(raw), "fresh": len(fresh), "kept": len(ranked),
                "report": len(report_items), "watch": len(watch)}}
