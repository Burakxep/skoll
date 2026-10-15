# Sköll — Specification & Design Decisions

This file captures every design decision made while planning the tool, so a
fresh Claude Code session (or any contributor) has full context without the
original chat.

## Goal
A daily scanner that discovers new/rising security tools and content **early**
(the "catch REA-like tools in their first 1-2 weeks" use case), filters out
noise, and produces a dated report plus a ready-to-paste analysis prompt.

## Core principles
1. **No API key required.** Everything runs on free, public, keyless access.
   An optional free `GITHUB_TOKEN` only raises rate limits.
2. **Deterministic core, LLM on top.** The Python core does fetching, dedup,
   keyword/metric scoring and reporting — all reproducible, testable, free.
   Semantic interpretation is NOT built in; it happens by pasting the generated
   `prompt.md` into an LLM (or, in Claude Code, by `/skoll` reading the digest).
3. **Topic-agnostic.** Nothing about "cybersec" is hardcoded. A profile = keyword
   lists + sources, all in `config.yaml`. Add crypto/devops/llm profiles freely.

## Sources (decided)
- **GitHub** (primary): Search API, two strategies union'ed — `created:>cutoff`
  (new-born repos) and `pushed:>cutoff` (rising/active repos), both capped by
  `max_repo_age_days` so old-but-popular repos never crowd the report. Computes
  stars/day momentum. Fetches README first paragraph for the top N only.
- **Hacker News**: Algolia API, free, no key.
- **Reddit**: public Atom/RSS listings, no key. Reddit 403s keyless `.json` and
  allows ~1 RSS request/min, so all subreddits go in ONE multireddit request
  (`/r/a+b/new/.rss`). RSS has no upvote counts → Reddit items score on
  keywords only. OAuth later if richer metrics are needed.
- **RSS/blogs**: feedparser over a feed list (Project Zero, PortSwigger Research,
  SpecterOps, Outflank, Assetnote, TrustedSec, watchTowr, IncludeSecurity).
- **X/Twitter**: deliberately EXCLUDED for now (API too expensive/restricted).

## Filtering & scoring (decided)
- `include` keywords add relevance; `exclude` (+ `global_exclude`) penalize/drop.
- **Focus tags**: a repo can get several (redteam, recon, mobile, appsec,
  blueteam, purpleteam). `redteam` and `recon` are the fullest keyword sets, per
  priority. Filter a report to one with `--focus redteam`.
- `weak_keywords` (e.g. reverse-engineering) only count next to another hit;
  a `reversing` focus tag (disassembler, decompiler, ghidra, ...) separates
  RE tooling from game-mod / gadget-hack posts. Keywords also match plurals.
- Score colours (`score_tiers`): there is no fixed max score (relevance grows
  with keyword hits, momentum is log-scaled), and GitHub scores run higher
  than momentum-less sources. So tiers are relative to the item's SOURCE
  threshold: >= 2.5x top, >= 1.5x strong, else passed.
- One author with >= `cve_cluster_min` CVE repos in a run gets tagged
  `suspicious` (templated fake-PoC bursts); the analysis prompt calls it out.
- **No fixed item count.** A per-source score threshold (`score_threshold`:
  GitHub 10 since it carries star momentum, HN 8, Reddit/RSS 4) decides inclusion (2 good items =>
  2 shown, 15 => 15). A `max_items` safety cap prevents runaway days.
- Structural momentum: stars/day, total stars, HN points, comments — log-scaled,
  so it boosts relevant items but can't carry an off-topic viral repo.
  `min_relevance` gates on keywords alone; a focus tag needs `focus_min_hits`
  keywords or a hit in title/topics.
- `max_per_source` quotas so momentum-less sources (Reddit, blogs) still get
  slots next to GitHub.
- Source signals (count as relevance): a non-GitHub item linking a GitHub/
  GitLab/Codeberg repo gets `weights.repo_link`; `require_repo_link: [reddit]`
  drops Reddit posts without one (Q&A/chatter). `source_bonus.rss` lifts the
  curated blogs whose prose rarely hits the keyword lists.
- **Breakout** (`breakout: {min_gain, ratio}`): dedup normally hides an item
  forever once reported. An already-reported GitHub repo comes back (tagged
  `breakout`, outside the per-source quotas) when, versus the stars it had on
  the LAST day it was reported, it gained >= min_gain (500) AND reached
  >= ratio (5x). Baseline = latest reported snapshot before today, so it
  resurfaces once per explosion, not daily. Rule: `scoring.detect_breakouts`.
- Dedup records only items that were actually REPORTED; below-threshold items
  are re-scored on later runs so late risers can still surface.

## Outputs (decided) — all dated, "scan for <date>, found these"
One folder per day: `reports/<profile>/<date>/`
1. `report.html` — visual dashboard (`templates/dashboard.html`; logo cropped from `skoll_logo.png` into `templates/logo-mark.png` + `favicon.png`, embedded as data URIs):
   **Analysis prompt button** in the header that opens prompt.md in a slide-over panel (copy + download),
   light/dark theme, source tabs with counts, category (focus tag) menu + clickable tag chips, search, sort by score/date/stars-per-day.
2. `digest.md` — human digest (still written to disk; the dashboard's cards
   show the same items, so its panel only offers prompt.md).
3. `prompt.md` — paste-ready analysis prompt (English),
   includes README excerpt for the top 5 candidates.
`--focus X` runs write `report.X.html` etc. and dry runs `*.dry-run.*` beside
them, so neither overwrites the day's main report. Real runs also write
`reports/<profile>/latest.prompt.md` / `latest.md` for the Claude Code wrapper
(dry runs never touch them). A second real run on the same day merges: the
day's report = items reported by earlier runs today (from `observations`,
`reported=1`) + this run's new finds, so re-running never shrinks it.

## Web app (`skoll/server.py`)
`python -m skoll serve` starts a stdlib-only server on 127.0.0.1:8765. It serves
the normal dashboard (same UI, theme and language as report.html) with a Run bar
(`templates/runbar.html`) injected at the `<!--SKOLL_RUNBAR-->` marker in the
header: profile / dry-run + **Run** + a **Weekly** link. Run POSTs `/api/run`,
the page polls `/api/status` for the log, then reloads with the new report. One
scan at a time; Host-header and JSON-content-type checks guard against
DNS-rebinding/CSRF. Static report.html files (opened from disk) don't show the
bar. The bar sits in the header row beside the TR|EN / theme controls, so the
served page looks like report.html. Reports from older versions (no marker) are
skipped; with none left the server shows an empty dashboard until the first Run.
There is no focus or category selector: filtering is done by clicking the tag
chips on the cards.

`GET /weekly[?profile=]` serves the newest weekly report on disk (the same
`reports/<profile>/weekly/<week>/report.html` that `skoll weekly` writes) with a
**← Dashboard** back-link added to its header, so the daily and weekly pages
navigate to each other in the same tab. When no weekly report exists yet it
serves a small placeholder pointing at `skoll weekly`. The server only reads
these files; it does not (yet) regenerate the weekly report — that stays a job
for the `weekly` command. The Weekly link and back-link use static labels (no
`data-i18n`), because a served report may embed an older i18n dictionary.

## Weekly trends (`skoll/weekly.py`)
- Every real daily run snapshots ALL relevant items (not only reported ones)
  into the `observations` table: stars, score, tags, keywords per day.
- Weekly = rolling last 7 days vs the 7 before (ISO week of the end date as id).
  1. Cohort trend by CREATION date per source / focus tag / keyword. Works from
     the first run since sources cover ~14 days (HN `within_days: 14`).
     Sources whose data doesn't reach last week (Reddit RSS: a few days) are
     auto-detected as partial and left out of the comparison until daily
     snapshots fill the gap; their items still appear in the top list.
  2. Star growth from observations (repo seen on >= 2 days this week).
- Weak keywords are excluded from keyword trends.
- Known bias: GitHub search returns the top `per_page` repos by stars, which
  favours older repos; raise `per_page` (max 100) for a fairer cohort.

## Dashboard language (TR|EN)
Both HTML pages (daily + weekly) have a TR|EN switch next to the theme button,
remembered per browser (default: browser language). Pages are rendered in
English; `templates/i18n.json` is the single dictionary, embedded in the page
and applied by `templates/i18n.js`. Only UI text is translated (not repo
titles/descriptions); digest.md / prompt.md stay English. `tests/test_i18n.py`
fails if a key is missing in either language.

## User-extensible
- Edit `config.yaml` directly, OR use `skoll add-source` to add a subreddit /
  feed / github query without hand-editing YAML.

## Workflow in Claude Code (the intended daily use)
`python -m skoll run --profile cybersec` → then have Claude read
`reports/cybersec/latest.prompt.md` and produce the semantic analysis inline.
No copy-paste, no API key: Claude Code itself is the LLM layer.

## Deliberately deferred (future phases)
- LLM provider abstraction (Together/OpenAI/Ollama) for fully-automated semantic
  pass, if the paste/`/skoll` flow ever feels slow.
- Notification driver abstraction (Slack/Discord/Telegram), à la trendFinder.
- Keyword → source discovery ("give me the best subreddits for X").
- Reddit OAuth, scheduled automation (cron/launchd).

## Reference
Conceptual cousin: github.com/ericciarla/trendFinder — but that one REQUIRES
Firecrawl + X API + an LLM API key. This tool is the dependency-free, security-
focused version: free RSS instead of Firecrawl, structural scoring + paste-prompt
instead of a mandatory LLM key.
