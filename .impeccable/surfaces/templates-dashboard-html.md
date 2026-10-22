---
version: 1
slug: "templates-dashboard-html"
primary_target: "templates/dashboard.html"
related_targets: ["templates/runbar.html","templates/theme.css"]
---

# Surface: Sköll dashboard (serve)

Scope: the local web app dashboard (`python -m skoll serve`), templates/dashboard.html + runbar.html + theme.css. Mode: Operate (daily scan triage). Audience: pentesters/red-teamers/AppSec reading the day's new tools top-down by score, then clicking through. Constraints: server-rendered Python templates, vanilla JS, no build step, no web fonts in the dated report.html (dashboard may self-host fonts), TR/EN, light+dark, WCAG AA, no horizontal scroll at 375px.

## Direction contract

THESIS: The daily scan printed as a dated security field bulletin — one dense, single-column broadsheet of what rose today, read top-down by score. It refuses the auto-fill grid of equal cards and the characterless system-font flatness that made the old dashboard read as a template.

OWN-WORLD: Warm near-black ground (#16130f) under a fine halftone tint; the only inks are one sun amber (#ffb000) and a cool federal blue (#2b4b8c) over paper-ink text (#ece4d2). Condensed poster display (Anton-class) for the wordmark and the score, set as a large amber overprint stamp; monospace (Spline Sans Mono-class) for every datum (repo, score, date, stars, stars/day); a workhorse grotesk (Archivo-class) for body. 1px hairline rules, no card shadows. Raise [from crouwel-grid-specimen]: the modular grid stays a visible, honest armature, cell-aligned, not hidden.

STORY: Open once a day, read down by score, catch the breakout (its amber ghost snapping into register) and the suspicious item (alarm red), click through — knowing at a glance what surfaced and how fast it is rising.

FIRST VIEWPORT: An amber-ruled masthead — SKÖLL wordmark + runes ᛋᚴᚢᛚ and the scan date/profile at left; source-segmented + tier-segmented filters and the amber Run button at right. Below, a single dense column of rows: a large amber score stamp, then repo name in mono with a clamped blurb and a meta line (source dot · focus tag · date), then stars/day and stars at the right. Raise [from ikeda-datamatics]: the feed is one aligned column at real tabular density with tabular figures, never loose cards. Raise [from rw-manual-acetate-tab-board]: a thin position+extent rail down the right fore-edge shows count and where you are, amber ticks marking Best-tier.

FORM: security riso bulletin (2600 / Phrack / DEF CON riso, overprint). Candidate 6 of 7 on the grounded list. seed:6a079945eb1f0562. Signature interaction: OVERPRINT REGISTER — breakout/new rows carry a 2–3px amber ghost of the repo name that snaps into register on hover/focus, `prefers-reduced-motion` disables the offset entirely (static, in-register). The first-reveal "1px settle" entrance is deliberately NOT shipped: a daily-scanned Operate tool stays calm, so the signature lives only in the breakout rest-ghost + its hover snap-to-register, not in a load-time animation. Motion grammar: short, mechanical, print-press (step/snap), never easing-float.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Open decisions
- Keep the runic wordmark; reinterpret the Norse sun/chase story through the riso world (user: identity stays, freely reinterpreted).
- Light theme must mirror the riso world as newsprint-ink, not cream (honor existing anti-reference).
- No shipping rasters planned (CSS/SVG only); if a halftone texture becomes an asset it carries provenance.
