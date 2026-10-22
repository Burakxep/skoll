"""Produces three dated outputs per run, one folder per day:
  1. reports/<profile>/<date>/report.html - visual dashboard, filterable; its
     Analysis prompt button opens 3 in a panel (copy/download)
  2. reports/<profile>/<date>/digest.md   - human digest (compact, linkable)
  3. reports/<profile>/<date>/prompt.md   - ready-to-paste analysis prompt
A --focus run adds the tag to the names (report.redteam.html, ...) and a
dry run adds '.dry-run', so neither overwrites the day's main report.
reports/<profile>/latest.{md,prompt.md} point at the last real (non-dry) run.
Re-running on the same day re-writes the day's files with ALL of that day's
findings (earlier runs' items are rebuilt from the observations table).
Every output is dated and says "scan for <date>, found these".
"""
from __future__ import annotations

import base64
import html
import json
from datetime import datetime, timezone
from pathlib import Path

from .models import Item

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"
TEMPLATES = ROOT / "templates"


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _src_label(it: Item) -> str:
    return {"github": "GitHub", "hackernews": "HN",
            "reddit": "Reddit", "rss": "Blog"}.get(it.source, it.source)


def _metrics(it: Item) -> str:
    bits = []
    if it.source == "github":
        bits.append(f"⭐{it.stars}")
        if it.stars_per_day:
            bits.append(f"~{it.stars_per_day}/day")
        if it.language:
            bits.append(it.language)
    if it.points:
        bits.append(f"▲{it.points}")
    if it.comments:
        bits.append(f"💬{it.comments}")
    if it.created_at:
        bits.append(it.created_at.strftime("%Y-%m-%d"))
    return " · ".join(bits)


# ---------------------------------------------------------------- digest (md)
def build_digest(items: list[Item], profile_name: str, date: str) -> str:
    lines = [f"# Sköll — {profile_name} — {date}", ""]
    if not items:
        lines.append("_No new items passed the filter today._")
        return "\n".join(lines)
    lines.append(f"**{len(items)} new item(s) found on {date}.**")
    lines.append("")
    for i, it in enumerate(items, 1):
        tags = f" `{' '.join(it.tags)}`" if it.tags else ""
        lines.append(f"### {i}. [{it.title}]({it.url}) — {_src_label(it)}{tags}")
        lines.append(f"_{_metrics(it)} · score {it.score}_")
        if it.description:
            lines.append("")
            lines.append(it.description.strip()[:300])
        if it.repo_url:
            lines.append("")
            lines.append(f"repo: {it.repo_url}")
        if it.raw.get("breakout"):
            b = it.raw["breakout"]
            lines.append("")
            lines.append(f"**breakout:** reported {b['day']} with {b['from']:,}★, "
                         f"now {b['now']:,}★")
        if it.matched_keywords:
            lines.append("")
            lines.append(f"matched: {', '.join(it.matched_keywords[:10])}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------- prompt (md)
def build_prompt(items: list[Item], date: str, readme_top: int = 5) -> str:
    tpl = (TEMPLATES / "analysis_prompt.txt").read_text(encoding="utf-8")
    blocks = []
    for i, it in enumerate(items, 1):
        head = f"[{i}] {it.title} ({_src_label(it)}) {_metrics(it)}"
        desc = it.description.strip().replace("\n", " ")[:220]
        block = [head]
        if desc:
            block.append(f"    {desc}")
        block.append(f"    {it.url}")
        if it.repo_url and it.repo_url != it.url:
            block.append(f"    repo: {it.repo_url}")
        if it.matched_keywords:
            block.append(f"    matched: {', '.join(it.matched_keywords[:8])}")
        if it.tags:
            block.append(f"    tags: {', '.join(it.tags)}")
        if it.raw.get("breakout"):
            b = it.raw["breakout"]
            block.append(f"    breakout: first reported {b['day']} with {b['from']} stars, "
                         f"now {b['now']}")
        if i <= readme_top and it.readme_excerpt:
            block.append(f"    readme: {it.readme_excerpt[:400]}")
        blocks.append("\n".join(block))
    candidates = "\n\n".join(blocks) if blocks else "(none today)"
    return tpl.format(date=date, count=len(items), candidates=candidates)


# ---------------------------------------------------------------- html
_SOURCES = [("github", "GitHub"), ("reddit", "Reddit"),
            ("hackernews", "HN"), ("rss", "Blogs")]


# ---------------------------------------------------------------- i18n (TR|EN)
# Pages are rendered in English; i18n.js swaps text client-side using the same
# dictionary, embedded in the page.
I18N: dict[str, dict[str, str]] = json.loads(
    (TEMPLATES / "i18n.json").read_text(encoding="utf-8"))


def t_en(key: str, **vars) -> str:
    return I18N["en"].get(key, key).format(**{k: str(v) for k, v in vars.items()})


def i18n(key: str, tag: str = "span", cls: str = "", **vars) -> str:
    """An element showing the English text, tagged for the TR|EN switch."""
    attrs = f' class="{cls}"' if cls else ""
    if vars:
        data = json.dumps({k: str(v) for k, v in vars.items()}, ensure_ascii=False)
        attrs += f" data-vars='{html.escape(data, quote=True)}'"
    return (f'<{tag}{attrs} data-i18n="{key}">'
            f'{html.escape(t_en(key, **vars))}</{tag}>')


def head_js() -> str:
    """Language dictionary + switch + theme, inlined into <head>."""
    data = json.dumps(I18N, ensure_ascii=False).replace("</", "<\\/")
    js = "".join((TEMPLATES / f).read_text(encoding="utf-8")
                 for f in ("i18n.js", "theme.js"))
    return f"<script>window.SKOLL_I18N = {data};</script>\n<script>{js}</script>"


CONTROLS = """<div class="controls">
      <div class="settings">
        <button class="theme-btn" id="settings-btn" type="button" aria-haspopup="true" aria-expanded="false" aria-label="Settings" data-i18n-aria="settings.aria">
          <svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6.5h16M4 12h16M4 17.5h16"/><circle cx="9" cy="6.5" r="2.3"/><circle cx="16" cy="12" r="2.3"/><circle cx="8" cy="17.5" r="2.3"/></svg><span class="label" data-i18n="settings.label">Settings</span>
        </button>
        <div class="settings-pop" id="settings-pop" role="menu" hidden>
          <div class="set-row">
            <span class="set-lbl" data-i18n="app.integrations">Integrations</span>
            <button class="theme-btn" id="settings-telegram" type="button" hidden aria-haspopup="dialog" data-i18n-aria="app.integrations">
              <span class="integ-dot" id="settings-integ-dot" aria-hidden="true"></span>
              <span data-i18n="integ.telegram">Telegram</span>
            </button>
          </div>
          <div class="set-row">
            <span class="set-lbl" data-i18n="settings.lang">Language</span>
            <div class="lang" role="group" aria-label="Language" data-i18n-aria="lang.aria">
              <button class="lang-btn" type="button" data-lang="tr" aria-pressed="false">TR</button>
              <button class="lang-btn" type="button" data-lang="en" aria-pressed="true">EN</button>
            </div>
          </div>
          <div class="set-row">
            <span class="set-lbl" data-i18n="settings.theme">Theme</span>
            <button class="theme-btn" id="theme" type="button" aria-label="Toggle light/dark mode" data-i18n-aria="theme.aria">
              <span id="theme-icon" aria-hidden="true"></span><span class="label" id="theme-label">Theme</span>
            </button>
          </div>
        </div>
      </div>
    </div>"""


def score_badge(score: float, tier: str) -> str:
    tier = tier or "high"
    return (f'<span class="score {tier}" title="{html.escape(t_en("tier." + tier))}" '
            f'data-i18n-title="tier.{tier}">{score:g}</span>')


def tier_legend(clickable: bool = False) -> str:
    """Score-colour legend. On the dashboard each entry is a filter button
    (with a live count); on the weekly page it's a static key."""
    parts = []
    for t in ("top", "high", "mid"):
        title = (f'title="{html.escape(t_en("tier." + t))}" data-i18n-title="tier.{t}"')
        label = i18n("legend.tier." + t)
        if clickable:
            parts.append(f'<button type="button" class="tier-btn" data-tier="{t}" '
                         f'aria-pressed="false" {title}><span class="score {t}">'
                         f'{label}<span class="n"></span></span></button>')
        else:
            parts.append(f'<span><span class="score {t}" {title}>{label}</span></span>')
    role = 'role="group"' if clickable else 'role="note"'
    return (f'<div class="tier-legend" {role} aria-label="Score colours" '
            f'data-i18n-aria="legend.tier.aria">{"".join(parts)}</div>')


def page_fills() -> dict[str, str]:
    """Placeholders shared by every Sköll page."""
    return {
        "__THEME_CSS__": ((TEMPLATES / "fonts.css").read_text(encoding="utf-8")
                          + "\n" + (TEMPLATES / "theme.css").read_text(encoding="utf-8")),
        "__HEAD_JS__": head_js(),
        "__CONTROLS__": CONTROLS,
        "__FAVICON__": _data_uri(TEMPLATES / "favicon.png"),
        "__LOGO__": _data_uri(TEMPLATES / "logo-mark.png"),
        "__TIER_LEGEND__": tier_legend(),
    }


ACTIONS = ('<button class="theme-btn act-btn" type="button" data-open-doc="prompt" '
           'title="Create Prompt" data-i18n-title="btn.prompt" '
           'aria-label="Create Prompt" data-i18n-aria="btn.prompt">'
           '<svg class="ico" viewBox="0 0 24 24" aria-hidden="true">'
           '<path d="M5 3.5h9.5l4 4V20.5H5z"/><path d="M14 3.5V8h4.5"/>'
           '<path d="M8 12.5h8M8 16h5"/></svg>'
           '<span class="txt" data-i18n="btn.prompt">Create Prompt</span></button>')


def build_html(items: list[Item], profile_name: str, date: str,
               prompt: str | None = None) -> str:
    tpl = (TEMPLATES / "dashboard.html").read_text(encoding="utf-8")
    docs = json.dumps({
        "prompt": build_prompt(items, date) if prompt is None else prompt,
    }, ensure_ascii=False).replace("</", "<\\/")

    present = {it.source for it in items}
    tabs = ['<button class="tab" type="button" role="tab" data-src="all">'
            f'{i18n("tab.all")} <span class="n"></span></button>']
    for key, label in _SOURCES:
        if key in present:
            name = i18n("src.rss") if key == "rss" else label
            tabs.append(
                f'<button class="tab" type="button" role="tab" data-src="{key}">'
                f'<span class="dot" style="background:var(--{key})"></span>'
                f'{name} <span class="n"></span></button>')

    cards = "\n".join(_card(it) for it in items)
    # Fore-edge extent rail: one tick per item, amber for a Best-tier (top) hit.
    ticks = "".join(
        f'<span class="tick{" best" if it.tier == "top" else ""}"></span>' for it in items)
    rail = f'<span class="n">{len(items)}</span>{ticks}' if items else ""
    # Logo/favicon are embedded so the report stays a single file.
    fills = {
        **page_fills(),
        "__PROFILE__": html.escape(profile_name),
        "__DATE__": date,
        "__SUB__": i18n("daily.sub", profile=profile_name, date=date, count=len(items)),
        "__TIER_LEGEND__": tier_legend(clickable=True),
        "__TABS__": "".join(tabs),
        "__CARDS__": cards,
        "__RAIL__": rail,
        "__ACTIONS__": ACTIONS,
        "__DOCS__": docs,
    }
    for k, v in fills.items():
        tpl = tpl.replace(k, v)
    return tpl


def _data_uri(path: Path) -> str:
    try:
        data = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return ""  # a missing asset must not break the report
    return f"data:image/png;base64,{data}"


def _stats(it: Item) -> str:
    """Metric line as HTML (translatable units)."""
    bits = []
    if it.source == "github":
        bits.append(f"★ {it.stars:,}")
        if it.stars_per_day:
            bits.append(i18n("stat.perday", n=f"{it.stars_per_day:g}"))
        if it.language:
            bits.append(html.escape(it.language))
    if it.points:
        bits.append(f"▲ {it.points}")
    if it.comments:
        bits.append(i18n("stat.comments", n=it.comments))
    return " · ".join(bits)


_CHIP_CLASS = {"suspicious": " warn", "breakout": " boom"}


def _card(it: Item) -> str:
    e = html.escape
    date = it.created_at.strftime("%Y-%m-%d") if it.created_at else ""
    desc = it.description.strip()[:360] if it.description else ""
    text = " ".join([it.title, desc, " ".join(it.matched_keywords),
                     " ".join(it.tags), " ".join(it.topics)]).lower()
    chips = "".join(
        f'<button type="button" class="chip{_CHIP_CLASS.get(t, "")}" '
        f'data-tag="{e(t)}" title="Show only {e(t)}" data-i18n-title="card.chip" '
        f'data-vars=\'{e(json.dumps({"tag": t}))}\'>{e(t)}</button>'
        for t in it.tags)
    stats = _stats(it)
    repo = (f'<div class="repo">repo: <a href="{e(it.repo_url)}" target="_blank" '
            f'rel="noopener">{e(it.repo_url)}</a></div>'
            if it.repo_url and it.repo_url != it.url else "")
    boom = ""
    if it.raw.get("breakout"):
        b = it.raw["breakout"]
        boom = i18n("breakout.line", tag="div", cls="boom", day=b["day"],
                    **{"from": f"{b['from']:,}", "now": f"{b['now']:,}"})
    kw = (f'<div class="kw">{i18n("card.matched")} {e(", ".join(it.matched_keywords[:10]))}</div>'
          if it.matched_keywords else "")
    cls = "card" + "".join(f" {t}" for t in ("suspicious", "breakout") if t in it.tags)
    title = e(it.title)
    return f"""<article class="{cls}" data-source="{e(it.source)}" data-score="{it.score}" \
data-spd="{it.stars_per_day}" data-date="{date}" data-tier="{e(it.tier)}" data-tags="{e(' '.join(it.tags))}" \
data-text="{e(text)}">
  <div class="score-col">{score_badge(it.score, it.tier)}</div>
  <div class="main">
    <div class="line">
      <span class="src" lang="en"><span class="dot" style="background:var(--{e(it.source)})"></span>{_src_label(it)}</span>
      <span>{date}</span>
      {boom}
      {f'<div class="chips">{chips}</div>' if chips else ''}
    </div>
    <h2><a href="{e(it.url)}" target="_blank" rel="noopener" data-title="{title}">{title}</a></h2>
    {f'<p class="desc">{e(desc)}</p>' if desc else ''}
    {repo}
    {kw}
  </div>
  <div class="metric">{stats}</div>
</article>"""


# ---------------------------------------------------------------- orchestration
def write_reports(items: list[Item], profile_name: str,
                  readme_top: int = 5, date: str | None = None, *,
                  focus: str | None = None, dry_run: bool = False,
                  root: Path | None = None) -> dict[str, Path]:
    date = date or _today()
    profile_dir = (root or REPORTS) / profile_name
    out_dir = profile_dir / date
    out_dir.mkdir(parents=True, exist_ok=True)

    sfx = "".join(f".{p}" for p in (focus, "dry-run" if dry_run else None) if p)
    paths = {
        "html": out_dir / f"report{sfx}.html",
        "digest": out_dir / f"digest{sfx}.md",
        "prompt": out_dir / f"prompt{sfx}.md",
    }
    digest = build_digest(items, profile_name, date)
    prompt = build_prompt(items, date, readme_top)
    paths["html"].write_text(build_html(items, profile_name, date, prompt),
                             encoding="utf-8")
    paths["digest"].write_text(digest, encoding="utf-8")
    paths["prompt"].write_text(prompt, encoding="utf-8")

    # Stable 'latest' pointers for the Claude Code wrapper to read.
    # A dry run is a preview, so it never replaces them.
    if not dry_run:
        (profile_dir / "latest.prompt.md").write_text(prompt, encoding="utf-8")
        (profile_dir / "latest.md").write_text(digest, encoding="utf-8")
    return paths
