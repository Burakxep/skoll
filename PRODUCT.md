# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
Pentesters, red teamers, AppSec engineers and security-minded developers. They
open the dashboard once a day (or after a manual Run) to see which new or
rising tools surfaced since the last scan, then decide what to read, star or
try.

## Product Purpose
Sköll scans GitHub, Hacker News, Reddit and RSS every day without API keys,
scores each item with deterministic keyword + focus-tag + momentum rules, and
writes a dated report ("scan for <date>, found these"). Success is catching a
useful offensive-security tool days before it is widely known, with as little
reading as possible.

## Positioning
A local, keyless, reproducible scanner: relevance logic lives in code
(`skoll/scoring.py`), not in a prompt, so the same inputs give the same
ranking. An LLM is only used afterwards, on the generated `prompt.md`.

## Operating Context
- Daily CLI run (`python -m skoll run`) or the local web app
  (`python -m skoll serve`, 127.0.0.1 only) with a Run button.
- Output per day: `report.html` (single self-contained file), `digest.md`,
  `prompt.md`; plus a weekly trends page.
- Typical session: scan the top-scored cards, filter by source / score tier /
  tag, open the repo, copy the prompt for the semantic-analysis step.

## Capabilities and Constraints
- Server-rendered HTML from Python templates; vanilla JS, no build step, no
  frontend dependencies, no web fonts (reports must work offline as one file).
- TR / EN interface; light and dark themes.
- Score tiers: Best (`top`), Okay (`high`), Passed (`mid`), relative to each
  source's threshold.

## Brand Commitments
- Name: Sköll, the Norse wolf that chases the sun. Logo: wolf with a sun,
  runic wordmark `ᛋᚴᚢᛚ`.
- Accent: sun amber. Reserved for the primary action and the score.
- Voice: terse, factual, tool-like. No hype, no emoji.

## Evidence on Hand
Real scan data under `reports/` (local, not committed). Logo and favicon in
`templates/`. No testimonials or usage numbers exist; do not invent any.

## Product Principles
1. The score is the signal; everything else on the page supports reading it.
2. Reproducible over clever: what the UI shows must trace back to the scoring code.
3. One glance per card: source, date, score, name, one-line description.
4. Local and private by default; nothing leaves the machine.

## Accessibility & Inclusion
WCAG AA contrast in both themes, visible keyboard focus, 44px minimum touch
targets, no horizontal page scroll at 375px width.
