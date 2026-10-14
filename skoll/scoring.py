"""Deterministic, keyword + metric based scoring. No LLM, no API key.

Two parts:
  1. keyword match  -> relevance (include adds, exclude kills/penalizes)
  2. structural     -> momentum (stars/day, recency, engagement)
Focus tags (redteam, recon, ...) are assigned from per-tag keyword sets.
"""
from __future__ import annotations

import math
import re
from typing import Any

from .models import Item


def _haystack(item: Item) -> str:
    parts = [item.title, item.description, item.readme_excerpt,
             " ".join(item.topics), item.language]
    return " ".join(p for p in parts if p).lower()


def _pattern(k: str) -> str:
    """Word-ish boundary match. Inner hyphens are flexible so "red-team" also
    matches "red team", "red_team" and "redteam" in prose, and a plain plural
    counts ("payload" matches "payloads"). A trailing hyphen makes a prefix
    ("awesome-" matches "awesome-foo")."""
    prefix = k.endswith("-")
    core = k.rstrip("-")
    body = r"[-_ ]?".join(re.escape(p) for p in core.split("-"))
    pattern = r"(?<![a-z0-9])" + body
    if prefix:
        return pattern + "-"
    plural = "s?" if core[-1].isalpha() else ""
    return pattern + plural + r"(?![a-z0-9])"


def _match(keywords: list[str], text: str) -> list[str]:
    hits = []
    for kw in keywords:
        k = kw.lower().strip()
        if not k.strip("-"):
            continue
        if re.search(_pattern(k), text):
            hits.append(kw)
    return hits


def score_item(item: Item, profile: dict[str, Any]) -> Item:
    text = _haystack(item)
    settings = profile.get("_settings", {})
    weights = settings.get("weights", {})

    include = profile.get("include", [])
    exclude = profile.get("exclude", [])
    focus_tags: dict[str, list[str]] = profile.get("focus_tags", {})

    inc_hits = _match(include, text)
    exc_hits = _match(exclude, text)

    # --- relevance ---
    relevance = len(inc_hits) * weights.get("include", 2.0)
    relevance -= len(exc_hits) * weights.get("exclude", 3.0)
    weak = {w.lower() for w in profile.get("weak_keywords", [])}

    # --- focus tags ---
    # A single keyword buried in prose ("recon" in a game-modding repo) is too
    # weak to label an item: a tag needs `focus_min_hits` distinct keywords,
    # or one hit in the curated fields (title / topics / subreddit / feed).
    curated = " ".join([item.title, " ".join(item.topics)]).lower()
    min_hits = settings.get("focus_min_hits", 2)
    tags: list[str] = []
    for tag, kws in (focus_tags or {}).items():
        tag_hits = _match(kws, text)
        if tag_hits:
            inc_hits.extend(k for k in tag_hits if k not in inc_hits)
            relevance += len(tag_hits) * weights.get("focus", 1.5)
            if len(tag_hits) >= min_hits or _match(tag_hits, curated):
                tags.append(tag)

    # Weak keywords ("reverse-engineering" also covers game mods and gadget
    # hacks) only count alongside a non-weak hit; alone they're worth nothing.
    if inc_hits and all(k.lower() in weak for k in inc_hits):
        relevance -= len(inc_hits) * weights.get("include", 2.0)

    # --- source signals (count as relevance) ---
    # A post/article that links a code repo is announcing a tool, and curated
    # sources (e.g. hand-picked research blogs) are on-topic by construction,
    # even when their prose misses the keyword lists.
    if item.repo_url and item.source != "github":
        relevance += weights.get("repo_link", 2.0)
    relevance += (settings.get("source_bonus") or {}).get(item.source, 0.0)

    # --- structural / momentum ---
    # Log-scaled, so momentum boosts a relevant item without letting a viral
    # repo with one incidental keyword outrank a dense on-topic match
    # (500 stars/day ~ 9 points, 10 stars/day ~ 3.5).
    def log(x: float) -> float:
        return math.log2(1 + max(x, 0))

    momentum = 0.0
    momentum += log(item.stars_per_day) * weights.get("stars_per_day", 1.0)
    momentum += log(item.stars / 10.0) * weights.get("stars", 0.5)
    momentum += log(item.points / 5.0) * weights.get("points", 0.5)
    momentum += log(item.comments / 5.0) * weights.get("comments", 0.3)

    item.matched_keywords = inc_hits
    item.tags = tags
    item.score = round(relevance + momentum, 2)
    item._exclude_hits = exc_hits  # type: ignore[attr-defined]
    item._relevance = round(relevance, 2)  # type: ignore[attr-defined]
    return item


def is_relevant(item: Item, profile: dict[str, Any]) -> bool:
    """On-topic gate, independent of momentum (call after score_item):
      - relevance must reach `min_relevance` on its own: momentum can rank a
        relevant item higher, but can't make a viral off-topic repo relevant
      - hard-drop if an exclude keyword hits and nothing strongly saves it
    The weekly trend report counts everything that passes this gate."""
    settings = profile.get("_settings", {})
    exc = getattr(item, "_exclude_hits", [])
    rel = getattr(item, "_relevance", 0.0)

    if rel <= 0 or rel < settings.get("min_relevance", 2.0):
        return False
    # Sources where only tool announcements are wanted (drops Q&A / chatter).
    if item.source in (settings.get("require_repo_link") or []) \
            and not item.repo_url:
        return False
    if exc and rel < settings.get("exclude_override", 4.0):
        return False
    return True


def source_threshold(source: str, settings: dict[str, Any]) -> float:
    threshold = settings.get("score_threshold", 3.0)
    if isinstance(threshold, dict):  # per source: GitHub carries star momentum
        threshold = threshold.get(source, threshold.get("default", 3.0))
    return float(threshold)


def score_tier(score: float, source: str, settings: dict[str, Any]) -> str:
    """Colour tier relative to the source's own threshold, since raw scores
    aren't comparable across sources (GitHub carries star momentum):
    >= top x threshold -> "top", >= high x -> "high", else "mid"."""
    tiers = {"top": 2.5, "high": 1.5, **(settings.get("score_tiers") or {})}
    thr = source_threshold(source, settings)
    ratio = score / thr if thr > 0 else 0.0
    if ratio >= tiers["top"]:
        return "top"
    if ratio >= tiers["high"]:
        return "high"
    return "mid"


def passes_filter(item: Item, profile: dict[str, Any]) -> bool:
    """Daily report gate: relevant AND above the per-source score threshold."""
    threshold = source_threshold(item.source, profile.get("_settings", {}))
    return is_relevant(item, profile) and item.score >= threshold


def rank_and_filter(items: list[Item], profile: dict[str, Any],
                    focus: str | None = None) -> list[Item]:
    scored = [score_item(it, profile) for it in items]
    kept = [it for it in scored if passes_filter(it, profile)]
    if focus:
        kept = [it for it in kept if focus in it.tags]
    kept.sort(key=lambda x: x.score, reverse=True)
    _flag_cve_clusters(kept, profile.get("_settings", {}))
    for it in kept:
        it.tier = score_tier(it.score, it.source, profile.get("_settings", {}))

    # Per-source quota first: Reddit/blog items have no star momentum, so in
    # one shared pool GitHub would take every slot.
    settings = profile.get("_settings", {})
    quotas: dict[str, int] = settings.get("max_per_source", {}) or {}
    used: dict[str, int] = {}
    capped = []
    for it in kept:
        n = used.get(it.source, 0)
        if it.source in quotas and n >= quotas[it.source]:
            continue
        used[it.source] = n + 1
        capped.append(it)

    # Overall safety cap so one noisy day can't explode the report.
    return capped[:settings.get("max_items", 60)]


_CVE = re.compile(r"cve-\d{4}-\d+", re.I)


def _flag_cve_clusters(items: list[Item], settings: dict[str, Any]) -> None:
    """Tag `suspicious` when one author pushes many CVE repos at once. Fake
    PoCs that ship malware typically come as a templated burst like this."""
    min_repos = settings.get("cve_cluster_min", 3)
    by_author: dict[str, list[Item]] = {}
    for it in items:
        if it.source == "github" and it.author \
                and _CVE.search(f"{it.title} {it.description}"):
            by_author.setdefault(it.author.lower(), []).append(it)
    for group in by_author.values():
        if len(group) >= min_repos:
            for it in group:
                if "suspicious" not in it.tags:
                    it.tags.append("suspicious")


# ---------------------------------------------------------------- breakouts
STATUS_TAGS = {"suspicious", "breakout"}  # flags, not focus categories


def detect_breakouts(items: list[Item], baselines: dict[str, tuple[str, int]],
                     profile: dict[str, Any], focus: str | None = None) -> list[Item]:
    """Already-reported GitHub repos whose stars exploded since they were last
    reported come back into the daily report, tagged "breakout".
    `items` must be scored; `baselines` maps dedup_key -> (day, stars)."""
    settings = profile.get("_settings", {})
    cfg = {"min_gain": 500, "ratio": 5.0, **(settings.get("breakout") or {})}
    out = []
    for it in items:
        base = baselines.get(it.dedup_key)
        if it.source != "github" or base is None or not is_relevant(it, profile):
            continue
        day, then = base
        if it.stars - then < cfg["min_gain"] or it.stars < cfg["ratio"] * max(then, 1):
            continue
        if focus and focus not in it.tags:
            continue
        if "breakout" not in it.tags:
            it.tags.append("breakout")
        it.raw["breakout"] = {"day": day, "from": then, "now": it.stars}
        it.tier = score_tier(it.score, it.source, settings)
        out.append(it)
    return out
