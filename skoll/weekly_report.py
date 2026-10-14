"""Writes the weekly outputs, one folder per ISO week:
  reports/<profile>/weekly/<YYYY-Www>/report.html - visual trend report
  reports/<profile>/weekly/<YYYY-Www>/digest.md   - markdown summary
  reports/<profile>/weekly/<YYYY-Www>/prompt.md   - analysis prompt
plus reports/<profile>/latest-weekly.prompt.md for the Claude Code step.
Re-running in the same week overwrites that week's files.
"""
from __future__ import annotations

import html
from pathlib import Path

from .report import REPORTS, TEMPLATES, _CHIP_CLASS, i18n, page_fills, score_badge, t_en
from .weekly import Entry, Trend, WeeklyReport

_LABELS = {"github": "GitHub", "hackernews": "HN", "reddit": "Reddit", "rss": "Blogs"}


def _label(source: str) -> str:
    return _LABELS.get(source, source)


def _delta(t: Trend) -> str:
    if t.last == 0 and t.this > 0:
        return "new"
    if t.delta == 0:
        return "±0"
    pct = f" ({t.pct:+d}%)" if t.pct is not None else ""
    return f"{t.delta:+d}{pct}"


def note_keys(rep: WeeklyReport) -> list[tuple[str, dict]]:
    """Caveats shown on every output, so nobody over-reads the numbers.
    As (i18n key, vars) so the HTML can switch language."""
    out: list[tuple[str, dict]] = []
    if rep.partial_sources:
        out.append(("note.partial",
                    {"names": ", ".join(_label(s) for s in rep.partial_sources)}))
    if not rep.gainers:
        out.append(("note.stars", {"days": rep.history_days}))
    if any(t.name == "github" for t in rep.by_source):
        out.append(("note.minstars", {}))
    if rep.total.this + rep.total.last < 20:
        out.append(("note.small", {}))
    return out


def notes(rep: WeeklyReport) -> list[str]:
    """The caveats in English (markdown digest and LLM prompt)."""
    return [t_en(k, **v) for k, v in note_keys(rep)]


# ---------------------------------------------------------------- markdown
def build_weekly_digest(rep: WeeklyReport, profile_name: str) -> str:
    L = [f"# Sköll weekly — {profile_name} — {rep.week_id}",
         f"_This week {rep.this.label} vs last week {rep.last.label}_", ""]
    for n in notes(rep):
        L.append(f"> {n}")
    L += ["", f"**New relevant items:** {rep.total.this} this week, "
          f"{rep.total.last} last week ({_delta(rep.total)}).", ""]

    L += ["## Sources", "| source | this week | last week | change |", "|---|---:|---:|---:|"]
    for t in rep.by_source:
        part = " (partial)" if t.name in rep.partial_sources else ""
        L.append(f"| {_label(t.name)}{part} | {t.this} | {t.last} | {_delta(t)} |")

    L += ["", "## Categories", "| category | this week | last week | change |",
          "|---|---:|---:|---:|"]
    for t in rep.by_tag:
        L.append(f"| {t.name} | {t.this} | {t.last} | {_delta(t)} |")

    for title, trends in (("Rising keywords", rep.rising),
                          ("New keywords", rep.new_keywords),
                          ("Most active keywords", rep.keywords)):
        L += ["", f"## {title}"]
        L += [f"- {t.name}: {t.this} (last week {t.last}, {_delta(t)})" for t in trends] \
            or ["_none_"]

    L += ["", "## Fastest-growing repos"]
    L += [f"- [{g.title}]({g.url}): +{g.gain} stars in {g.days} day(s) "
          f"(~{g.per_day}/day, now {g.last_stars})" for g in rep.gainers] \
        or ["_not enough daily snapshots yet_"]

    L += ["", "## Top new items this week"]
    for i, e in enumerate(rep.top_items, 1):
        tags = f" `{' '.join(e.tags)}`" if e.tags else ""
        seen = " · in a daily report" if e.reported else ""
        L.append(f"{i}. [{e.title}]({e.url}) — {_label(e.source)}{tags} · "
                 f"score {e.score:g}{seen}")
    return "\n".join(L) + "\n"


def build_weekly_prompt(rep: WeeklyReport) -> str:
    tpl = (TEMPLATES / "weekly_prompt.txt").read_text(encoding="utf-8")

    def lines(trends: list[Trend]) -> str:
        return "\n".join(f"{t.name}: {t.this} / {t.last} / {_delta(t)}"
                         for t in trends) or "(none)"

    totals = [f"all compared sources: {rep.total.this} / {rep.total.last} / {_delta(rep.total)}"]
    totals += [f"{_label(t.name)}{' (partial, not compared)' if t.name in rep.partial_sources else ''}: "
               f"{t.this} / {t.last}" for t in rep.by_source]
    gainers = "\n".join(f"{g.title}: +{g.gain} stars in {g.days} day(s), now {g.last_stars} "
                        f"({g.url})" for g in rep.gainers) or "(not enough daily snapshots yet)"
    items = []
    for i, e in enumerate(rep.top_items, 1):
        block = [f"[{i}] {e.title} ({_label(e.source)}) score {e.score:g}"
                 + (f" tags: {', '.join(e.tags)}" if e.tags else "")]
        desc = e.description.strip().replace("\n", " ")[:200]
        if desc:
            block.append(f"    {desc}")
        block.append(f"    {e.url}")
        if e.repo_url and e.repo_url != e.url:
            block.append(f"    repo: {e.repo_url}")
        items.append("\n".join(block))

    return tpl.format(
        week=rep.week_id, this_range=rep.this.label, last_range=rep.last.label,
        notes="\n".join(f"- {n}" for n in notes(rep)) or "(none)",
        totals="\n".join(totals), tags=lines(rep.by_tag),
        rising=lines(rep.rising), new=lines(rep.new_keywords),
        gainers=gainers, items="\n\n".join(items) or "(none)")


# ---------------------------------------------------------------- html
def _delta_html(t: Trend) -> str:
    if t.last == 0 and t.this > 0:
        return i18n("delta.new", cls="newbadge")
    cls = "up" if t.delta > 0 else "down" if t.delta < 0 else "flat"
    return f'<span class="{cls}">{html.escape(_delta(t))}</span>'


def _trend_table(title_key: str, trends: list[Trend], empty_key: str) -> str:
    if not trends:
        return i18n(title_key, tag="h3", cls="hint") + i18n(empty_key, tag="p", cls="empty")
    rows = "".join(f"<tr><td>{html.escape(t.name)}</td><td class='num'>{t.this}</td>"
                   f"<td class='num'>{t.last}</td><td class='num'>{_delta_html(t)}</td></tr>"
                   for t in trends)
    head = (i18n(title_key, tag="th") + i18n("th.this", tag="th", cls="num")
            + i18n("th.last", tag="th", cls="num") + i18n("th.change", tag="th", cls="num"))
    return f"<table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>"


def _item_html(e: Entry) -> str:
    x = html.escape
    chips = "".join(f'<span class="chip{_CHIP_CLASS.get(t, "")}">{x(t)}</span>'
                    for t in e.tags)
    seen = i18n("item.seen", cls="seen") if e.reported else ""
    created = f"<span>{e.created:%Y-%m-%d}</span>" if e.created else ""
    return f"""<div class="item">
  <a href="{x(e.url)}" target="_blank" rel="noopener">{x(e.title)}</a>
  {score_badge(e.score, e.tier)}
  <div class="meta"><span class="src" lang="en"><span class="dot" style="background:var(--{x(e.source)})"></span>{_label(e.source)}</span>{created}{chips}{seen}</div>
</div>"""


def build_weekly_html(rep: WeeklyReport, profile_name: str) -> str:
    x = html.escape
    tpl = (TEMPLATES / "weekly.html").read_text(encoding="utf-8")

    keys = note_keys(rep)
    notes_html = ("<section><div class='panel notes'><ul>"
                  + "".join(i18n(k, tag="li", **v) for k, v in keys)
                  + "</ul></div></section>") if keys else ""

    stats = [f"""<div class="panel stat">{i18n("stat.allsrc", tag="div", cls="label")}
  <div class="value">{rep.total.this}</div>
  <div class="prev">{i18n("stat.lastweek", n=rep.total.last)} · {_delta_html(rep.total)}</div></div>"""]
    for t in rep.by_source:
        partial = t.name in rep.partial_sources
        prev = (i18n("stat.partial") if partial
                else f'{i18n("stat.lastweek", n=t.last)} · {_delta_html(t)}')
        stats.append(f"""<div class="panel stat{' partial' if partial else ''}">
  <div class="label"><span class="dot" style="background:var(--{x(t.name)})"></span>{i18n("src.rss") if t.name == "rss" else _label(t.name)}</div>
  <div class="value">{t.this}</div><div class="prev">{prev}</div></div>""")

    peak = max([max(t.this, t.last) for t in rep.by_tag] or [1]) or 1
    bars = "".join(f"""<div class="bar-row">
  <div class="bar-name">{x(t.name)}</div>
  <div class="bar-pair">
    <div class="bar this" style="width:{100 * t.this / peak:.1f}%" title="this week: {t.this}"></div>
    <div class="bar last" style="width:{100 * t.last / peak:.1f}%" title="last week: {t.last}"></div>
  </div>
  <div class="bar-nums">{t.this} / {t.last} · {_delta_html(t)}</div>
</div>""" for t in rep.by_tag) or i18n("empty.tags", tag="p", cls="empty")

    if rep.gainers:
        rows = "".join(f"<tr><td><a href='{x(g.url)}' target='_blank' rel='noopener'>{x(g.title)}</a></td>"
                       f"<td class='num up'>+{g.gain}</td><td class='num'>{i18n('unit.days', n=g.days)}</td>"
                       f"<td class='num'>{i18n('stat.perday', n=g.per_day)}</td><td class='num'>★ {g.last_stars}</td></tr>"
                       for g in rep.gainers)
        head = (i18n("th.repo", tag="th") + "".join(
            i18n(k, tag="th", cls="num") for k in ("th.gained", "th.over", "th.rate", "th.now")))
        gainers = f"<table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>"
    else:
        gainers = i18n("empty.gain", tag="p", cls="empty", days=rep.history_days)

    fills = {
        **page_fills(),
        "__PROFILE__": x(profile_name),
        "__WEEK__": rep.week_id,
        "__SUB__": i18n("weekly.sub", profile=profile_name, week=rep.week_id,
                        this=rep.this.label, last=rep.last.label),
        "__NOTES__": notes_html,
        "__STATS__": "".join(stats),
        "__TAGS__": bars,
        "__RISING__": _trend_table("th.rising", rep.rising, "empty.rising"),
        "__NEW__": _trend_table("th.new", rep.new_keywords, "empty.new"),
        "__ACTIVE__": _trend_table("th.active", rep.keywords, "empty.active"),
        "__GAINERS__": gainers,
        "__ITEMS__": "".join(_item_html(e) for e in rep.top_items)
                     or i18n("empty.items", tag="p", cls="empty"),
    }
    for k, v in fills.items():
        tpl = tpl.replace(k, v)
    return tpl


# ---------------------------------------------------------------- orchestration
def write_weekly_reports(rep: WeeklyReport, profile_name: str, *,
                         root: Path | None = None) -> dict[str, Path]:
    profile_dir = (root or REPORTS) / profile_name
    out_dir = profile_dir / "weekly" / rep.week_id
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt = build_weekly_prompt(rep)
    paths = {"html": out_dir / "report.html", "digest": out_dir / "digest.md",
             "prompt": out_dir / "prompt.md"}
    paths["html"].write_text(build_weekly_html(rep, profile_name), encoding="utf-8")
    paths["digest"].write_text(build_weekly_digest(rep, profile_name), encoding="utf-8")
    paths["prompt"].write_text(prompt, encoding="utf-8")
    (profile_dir / "latest-weekly.prompt.md").write_text(prompt, encoding="utf-8")
    return paths
