# CLAUDE.md — context for Claude Code working in this repo

Read `SPEC.md` for the full design rationale. Quick orientation:

## What this is
Sköll (the Norse wolf that chases the sun): a daily, keyless scanner that finds
new/rising security tools from GitHub + Hacker News + Reddit + RSS, scores them
by keyword + momentum, and writes dated reports. Built to catch new
offensive-security tooling early.

## Architecture (don't move logic into prompts)
- `skoll/connectors/*` — one file per source, all return `Item` (see `models.py`).
- `skoll/scoring.py` — deterministic keyword + focus-tag + momentum scoring.
  **All relevance logic lives here, never in an LLM prompt**, so runs are
  reproducible and testable.
- `skoll/store.py` — SQLite dedup + "first seen" history (only reported items
  are recorded, so below-threshold items get re-scored on later runs).
- `skoll/report.py` — builds `reports/<profile>/<date>/{report.html,digest.md,prompt.md}`.
- `skoll/pipeline.py` — fetch → dedup → score → report (+ daily snapshots).
- `skoll/server.py` — `python -m skoll serve`: stdlib localhost web app. Serves the
  dashboard with a Run bar (`templates/runbar.html`, injected at the
  `<!--SKOLL_RUNBAR-->` marker) that runs `pipeline.run_profile` in a thread.
  No relevance logic here; keep it a thin wrapper around the pipeline.
- `skoll/weekly.py` / `weekly_report.py` — this week vs last week trends.
- `skoll/banner.py` — the ASCII wolf+sun banner printed on run.
- `config.yaml` — the only place topic/source/keyword config lives (gitignored;
  `config.example.yaml` is the committed template).

## Running
```
pip install -r requirements.txt
cp config.example.yaml config.yaml      # first time
python -m skoll run --profile cybersec  # daily run
python -m skoll run --profile cybersec --focus redteam
python -m skoll check --profile cybersec   # dry-run, no history writes
python -m skoll serve                     # local web app: dashboard with a Run button in the header
python -m skoll add-source --profile cybersec --subreddit redteamsec
python -m skoll weekly --profile cybersec   # weekly trends (--no-fetch: offline)
python -m unittest                        # offline tests (incl. tests/test_server.py)
```
Optional: `export GITHUB_TOKEN=...` (free PAT, public-repo read) to raise GitHub
rate limits. Nothing else needs a key.

## The daily semantic-analysis step (this is the point)
After a run, **read `reports/<profile>/latest.prompt.md` and answer it inline** —
you are the LLM layer, so the user does NOT paste it anywhere. Produce the
per-candidate analysis (what it is, why it matters for offensive security,
maturity, priority) and a top-3 shortlist.

## Conventions
- No new runtime dependencies without reason (requests, feedparser, PyYAML only).
- Every report is dated; keep the "scan for <date>, found these" framing.
- Keep connectors failure-tolerant: a dead source must not crash a run.
- Don't commit `config.yaml`, `data/`, or `reports/` (see `.gitignore`).

## Weekly step
After `python -m skoll weekly --profile <p>`, read
`reports/<profile>/latest-weekly.prompt.md` and answer it inline the same way:
top trends backed by the numbers, heating/cooling categories, watchlist.
Respect the caveats it lists (partial sources, missing star history).
