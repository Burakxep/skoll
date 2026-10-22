---
name: Sköll
description: Daily security field bulletin — a riso broadsheet of the tools that rose today, read top-down by score.
colors:
  ground: "#16130f"
  surface: "#1d1813"
  surface-2: "#272016"
  border: "#352d20"
  ink: "#ece4d2"
  muted: "#a2957c"
  sun: "#ffb000"
  sun-soft: "rgba(255, 176, 0, .15)"
  on-sun: "#1a1206"
  stamp-bg: "#ffb000"
  stamp-ink: "#1a1206"
  ink-blue: "#7aa2f7"
  warn: "#ff5f63"
  warn-soft: "rgba(255, 95, 99, .15)"
  halftone: "rgba(190, 174, 140, .11)"
  source-github: "#a3acbb"
  source-reddit: "#ff6a3d"
  source-hackernews: "#7aa2f7"
  source-rss: "#3ccfa4"
  light-ground: "#d7d7d0"
  light-surface: "#e9e8e1"
  light-surface-2: "#dedcd3"
  light-border: "#bebbb0"
  light-ink: "#1a1712"
  light-muted: "#5c5647"
  light-sun: "#8a5600"
  light-stamp-bg: "#e0920f"
  light-stamp-ink: "#241400"
  light-ink-blue: "#2b4b8c"
  light-warn: "#c23236"
typography:
  display:
    fontFamily: "'Skoll Display', 'Arial Narrow', system-ui, sans-serif"
    fontSize: "40px"
    fontWeight: 400
    lineHeight: 1
    letterSpacing: "0.5px"
  score:
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "24px"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "-0.5px"
  repo:
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "16px"
    fontWeight: 600
    lineHeight: 1.35
  body:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.55
  data:
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "12px"
    fontWeight: 500
    lineHeight: 1.7
  meta:
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "11.5px"
    fontWeight: 600
    letterSpacing: "0.3px"
rounded:
  none: "0"
  dot: "50%"
spacing:
  xs: "6px"
  sm: "10px"
  md: "12px"
  lg: "16px"
  xl: "18px"
  gutter: "20px"
components:
  score-stamp:
    textColor: "{colors.sun}"
    typography: "{typography.score}"
    rounded: "{rounded.none}"
  score-stamp-top:
    backgroundColor: "{colors.stamp-bg}"
    textColor: "{colors.stamp-ink}"
    typography: "{typography.score}"
    rounded: "{rounded.none}"
  score-stamp-high:
    backgroundColor: "{colors.sun-soft}"
    textColor: "{colors.sun}"
    typography: "{typography.score}"
    rounded: "{rounded.none}"
  score-stamp-mid:
    textColor: "{colors.muted}"
    typography: "{typography.score}"
    rounded: "{rounded.none}"
  button-run:
    backgroundColor: "{colors.stamp-bg}"
    textColor: "{colors.stamp-ink}"
    rounded: "{rounded.none}"
    height: "44px"
    padding: "0 18px"
  tab:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    height: "38px"
    padding: "0 14px"
  tab-selected:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.ground}"
    rounded: "{rounded.none}"
    height: "38px"
    padding: "0 14px"
  chip:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.ink-blue}"
    rounded: "{rounded.none}"
    padding: "2px 9px"
  chip-selected:
    backgroundColor: "{colors.ink-blue}"
    textColor: "{colors.ground}"
    rounded: "{rounded.none}"
    padding: "2px 9px"
  input-search:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    height: "38px"
    padding: "0 12px"
---

# Design System: Sköll

## Overview

**Creative North Star: "The Field Bulletin."** The daily scan printed as a
dated security broadsheet — one dense, single-column sheet of what rose today,
read top-down by score. It is a riso press artifact (the 2600 / Phrack / DEF CON
overprint lineage): a warm near-black paper ground under a fine halftone tint,
two inks only, and a visible modular grid left honest as armature rather than
hidden behind cards.

Mode: **Operate.** Density, scanability and keyboard use outrank expression. The
page refuses two things on purpose: the auto-fill grid of equal cards, and the
characterless system-font flatness that made the prior dashboard read as a
template. In their place: one aligned column at real tabular density, every
datum in monospace, and a condensed poster face carrying the one voice that
matters — the SKÖLL masthead wordmark — while the score joins the monospace data
spine, stamped into an amber box.

Dark is the default; light is a cool newsprint, never cream (the prior cream +
terracotta anti-reference is still honored). The brand lives in precise press
details — the amber wordmark and runic mark, the amber score stamp, the
fore-edge extent rail, and the overprint-register ghost on breakout rows.

**Key Characteristics:**
- Warm near-black riso ground (#16130f) under a 5px halftone dot tint.
- Exactly two inks: sun amber and cool blue, over paper-ink text.
- Square everything (0 radius); 1px hairline rules form a visible column grid.
- One dense bulletin column, never a card grid; a fore-edge rail shows extent.
- Poster display (Anton) for the SKÖLL wordmark only; every datum, the score
  included, is monospace with tabular figures.
- Signature: OVERPRINT REGISTER — the breakout row's amber ghost snaps home.

## Colors

A warm two-ink press palette: paper-ink text on a near-black ground, with one
sun amber and one cool blue as the only chromatic inks. Source dots are data
color, held off both inks.

### Primary
- **Sun Amber** (#ffb000 dark / #8a5600 light): the sun the wolf chases — the
  single signal ink. It carries the top-tier score stamp fill (`--stamp-bg`
  #ffb000 / #e0920f), the Run button, the breakout overprint ghost, the
  fore-edge rail (count + Best-tier ticks), the 3px masthead rule, the **SKÖLL
  wordmark** (`h1`), link hover, and focus rings. Text on amber is **Stamp Ink**
  (#1a1206 / #241400) for AA contrast.

### Secondary
- **Cool Blue** (#7aa2f7 dark / #2b4b8c light): the second riso ink. Reserved
  for focus-tag chips — chip text at rest, full fill when the tag is the active
  filter. It is also the Hacker News source dot. It never touches the score or
  the primary action.

### Neutral
- **Ground** (#16130f dark / #d7d7d0 light): the paper. Carries the halftone
  dot tint (`--halftone` rgba(190,174,140,.11) / rgba(40,33,20,.09)).
- **Surface / Surface-2** (#1d1813 · #272016 dark / #e9e8e1 · #dedcd3 light):
  controls and chip rest fill; surface is also the row hover wash.
- **Border** (#352d20 dark / #bebbb0 light): every 1px hairline — row rules,
  the column armature, control strokes, the rail.
- **Ink** (#ece4d2 dark / #1a1712 light): body and heading text; `--wolf`
  mirrors it. Doubles as the inverted *plate* behind pressed toggles.
- **Muted** (#a2957c dark / #5c5647 light): meta lines, dates, mid-tier scores,
  placeholders, the sub-headline, and the runic wordmark beside the masthead.

### Tertiary
- **Alarm Red** (#ff5f63 dark / #c23236 light, soft fills `--warn-soft`): a
  suspicious item only. It recolors that row's score stamp and warning chip; it
  is never decorative.
- **Source dots** (8px circles, data not accent): GitHub grey #a3acbb, Reddit
  red-orange #ff6a3d, Hacker News blue #7aa2f7, RSS green #3ccfa4 (dark theme).

### Named Rules
**The Two Inks Rule.** The world runs on exactly two chromatic inks — sun amber
and cool blue — over paper, ground and border neutrals. Amber is the signal
(score stamp top tier, wordmark, Run, breakout, rail, masthead rule, focus);
blue is the focus-tag chip. Alarm red is an exception reserved for a suspicious
finding. A third decorative hue is a hierarchy problem, not a color problem.

**The Inverted-Plate Rule.** A selected or pressed UI toggle — a source tab,
a language button — reverses to an **Ink** plate with **Ground** text, not
amber. Amber is signal; the plate reversal is UI state. (Note: browser text
selection, caret and `accent-color` *are* amber — the shipped build diverges
here from the direction contract, which named an ink-plate selection; the build
wins and is recorded as-is.)

## Typography

**Display Font:** Anton, self-hosted as `"Skoll Display"` (fallback
`"Arial Narrow", system-ui, sans-serif`), embedded as a base64 woff2 data URI so
the dated report stays a single offline file with no web-font fetch.
**Body Font:** system sans (`system-ui, -apple-system, 'Segoe UI', Roboto`).
**Data/Mono Font:** system mono (`ui-monospace, SFMono-Regular, Menlo, Consolas`).

**Character:** A single condensed poster word — SKÖLL — rules a quiet
system-sans body and a monospace spine that carries everything a pentester would
read as data, the score loudest among them. The tension between the one poster
wordmark and the dense tabular feed is the voice.

### Hierarchy
- **Display** (Anton 400, 40px → 34px mobile, line 1 + 5px padding-top, +0.5px,
  uppercase, **amber**): the SKÖLL masthead wordmark only.
- **Score** (mono 700, 24px → 26px mobile, line 1, −0.5px, tabular-nums): the
  score, set in the data face and seated in an amber stamp box in the left
  column of every row.
- **Repo** (mono 600, 16px, 1.35): the `owner/repo` title — the primary line of
  a bulletin row. `overflow-wrap: anywhere`.
- **Body** (system sans 400, 15px base / 13.5px desc, 1.55): descriptions,
  clamped to 3 lines, max 76ch.
- **Data** (mono 500, 12px, tabular-nums): stars/day, stars, dates, counts, the
  rail count.
- **Meta** (mono 600, 11.5px, +0.3px): the source · tag · date meta line and
  source names; tier-legend and chips sit at this size.
- **Runes** (mono 400, 16px, +5px tracking, **muted**): the `ᛋᚴᚢᛚ` mark beside
  the amber wordmark.

### Named Rules
**The Mono-Datum Rule.** Anything a pentester would copy, compare or sort —
repo name, score, date, stars, stars/day, matched keywords, source name — is
monospace with tabular figures. The score is a datum, not a poster element.
Prose (descriptions) is the only system-sans text on a row.

**The One-Voice Display Rule.** The Anton display face is spent on exactly one
thing: the SKÖLL masthead wordmark. It never sets the score, a section header, a
button, or a label. The score belongs to the mono data spine inside its amber
box; the stamp box earns the loudness, not the letterforms. Uppercase belongs to
the poster wordmark, not to UI labels (no tracked-out caps labels, no "WORD —"
headings).

## Layout

- Container max 1240px, 20px gutter (16px under 640px). No horizontal page
  scroll at 375px.
- **Masthead:** a flex row ending in a 3px amber bottom rule — logo + amber
  wordmark + muted runes and the scan subtitle at left; the Run bar, Create
  Prompt and Settings at right.
- **Sticky toolbar** under the masthead (1px bottom rule): source tabs at left;
  search + sort at right; a status line ("Showing N of M") and the clickable
  tier legend on the row below.
- **The sheet** is a flexbox of two parts: the bulletin column (`flex: 1`) and a
  46px fore-edge **extent rail** (`flex: none`, sticky) at the right with a 1px
  left rule. The rail is hidden under 640px.
- **Bulletin row** is a 3-column grid `92px 1fr auto`: score stamp | main | right
  metric, gap 0, with a 1px hairline down each interior column boundary (the
  `.main` and `.metric` left borders) so the grid reads as a visible armature,
  not just row separators. Rows are separated by 1px bottom rules; the first row
  gets a top rule too.
- Under 640px the grid collapses to `62px 1fr`; the metric column drops to a
  full-width left-aligned line beneath, the stamp grows to 26px, and the tabs
  scroll horizontally inside their own row (never the page).
- Spacing rhythm is small and press-tight: 6px dot gaps, 7px row stack, 10–12px
  control gaps, 16px row padding, 18px column padding, 20px gutter.

## Elevation & Depth

Flat by default. Depth comes from the halftone-tinted paper, tone steps
(ground → surface → surface-2) and 1px hairline rules — never from shadows on
content. Bulletin rows, the stamp, chips and the rail are all shadowless; a row
"lifts" only as a tonal hover wash (`--surface`). The one halftone layer is a
5px radial-dot `background-image` on the body, the riso paper grain.

Shadows appear only on genuinely floating layers that sit above the sheet.

### Shadow Vocabulary
- **Overlay** (`box-shadow: 0 10px 30px rgba(0, 0, 0, .40)`): the settings
  popover, the Run menu, and the prompt slide-over panel only.

### Named Rules
**The Flat-Sheet Rule.** Anything that is part of the sheet is flat — depth is
tone + hairline. A drop shadow is a claim that an element floats above the page;
only menus and the slide-over may make that claim.

## Shapes

Square by doctrine: `border-radius: 0` everywhere — the stamp, buttons, chips,
tabs, inputs, menus, the panel. The only curve in the system is the 8px source
**dot** (`border-radius: 50%`). No pills, no rounded cards, no soft corners.
Form is carried by the 1px hairline grid and the ruled masthead, not by radius.
Icons are 1em stroked SVG (`stroke-width 1.8`, square caps, miter joins) — the
mechanical, drafting-square line of the press world; never glyph/emoji icons.

## Components

### Score stamp (signature)
- **Character:** the brightest mark on every row — a bold mono score seated in an
  amber box; the number reads as sortable data, the box carries the loudness.
- **Shape:** square (0 radius), centered in the 92px left column, mono 700 24px
  tabular (26px mobile), −0.5px tracking.
- **Tiers:** *Best* (`top`) — solid amber fill (`--stamp-bg`), stamp-ink glyphs.
  *Okay* (`high`) — amber glyphs on a `--sun-soft` tint, 1.5px amber border.
  *Passed* (`mid`) — muted glyphs, border-color rule. Default — amber glyphs,
  1.5px amber outline.
- **Suspicious:** the stamp itself turns Alarm red (red glyphs + red border,
  transparent fill); the signature carries the warning, no extra badge.

### Run button (primary / split)
- **Shape:** square, 44px tall, amber fill (`--stamp-bg`), stamp-ink text,
  weight 700. A caret segment (40px) divided by a 1px inner rule
  (`rgba(0,0,0,.28)`) opens a Run / Dry-run menu.
- **Focus:** 2px **Ink** outline, 2px offset (the fg plate, so the ring reads on
  amber), never an amber-on-amber ring.
- **The One Action Rule.** Amber fill on a control means "run the scan." No
  other button is filled amber; secondary controls are surface + hairline.

### Source tabs
- Quiet buttons (surface fill, 1px border, 38px) with a source dot + name +
  mono count. Hover: border goes to Ink. **Selected:** inverted Ink plate,
  Ground text (not amber). Disabled: 0.4 opacity.

### Tier legend (filter)
- The score-color legend doubles as a tier filter. Each button is a small score
  chip (tier swatch + mono count). Pressed: 1.5px Ink outline; when filtering,
  unpressed tiers drop to 0.4 opacity. Focus: 2px amber ring.

### Focus-tag chips
- **Character:** the cool-blue ink's home. Surface-2 fill, Cool Blue mono text,
  transparent border, square. Hover: blue border. **Active filter** (`.on`):
  solid Cool Blue fill, Ground text. Breakout chip (`.boom`): amber fill;
  warning chip (`.warn`): red soft-fill + red border.

### Bulletin row (card)
- Not a container — a 3-column grid row with 1px rules and no background at rest;
  hover washes to `--surface`. Keeps the `.card` data-contract the JS targets.
  Row: stamp | (source·tag·date meta line, mono repo `<h2>`, clamped description)
  | right-aligned stars/day + stars metric. Suspicious rows recolor the stamp to
  Alarm red; breakout rows carry the overprint ghost.

### Overprint register (signature interaction)
- A breakout row's repo title prints a 3px/2.5px-offset amber ghost
  (`h2 a::before`, `opacity .6`, `z-index -1`) behind it. On hover/focus the
  ghost snaps into register (left/top → 0, opacity → 0) via `steps(3)` — a
  mechanical print-press snap, never an eased float. `prefers-reduced-motion`
  holds the title permanently in register (no offset, no transition).

### Inputs
- Search (260px, 38px) and the mono sort select (38px): surface fill, 1px
  border, square, muted placeholder. Focus: 2px amber ring, 1px offset. The sort
  control gets an amber border + amber text when a non-default sort is active.

### Fore-edge extent rail
- A 46px sticky column on the sheet's right fore edge with a 1px left rule: a
  mono amber total count at top, then one tick per row — 13px grey ticks, 22px
  amber ticks for Best-tier items — a position/extent gauge, hidden on mobile.

### Settings & language
- Settings is a square hairline button opening an Overlay popover holding the
  Language segmented control (TR/EN), the Theme toggle, and the Telegram
  integration controls. Pressed language: inverted Ink plate, Ground text. Theme
  toggle swaps a stroked sun/moon SVG.

## Do's and Don'ts

### Do:
- **Do** keep amber to signal — score stamp (top), wordmark, Run, breakout,
  rail, masthead rule, focus rings (The Two Inks Rule).
- **Do** set every datum (repo, score, date, stars, counts, keywords) in
  monospace with tabular figures; the score is a datum in an amber box.
- **Do** keep corners square (0 radius); the only circle is the 8px source dot.
- **Do** convey depth with tone + 1px hairlines; reserve the Overlay shadow for
  floating menus and the slide-over.
- **Do** leave the column grid visible as an honest armature (interior hairlines).
- **Do** default to dark; render light as cool newsprint.

### Don't:
- **Don't** use the Anton display face for anything but the SKÖLL wordmark —
  not the score, not headers, not labels.
- **Don't** fill a second control amber, or introduce a third decorative hue.
- **Don't** put a shadow on a bulletin row, stamp, chip or the rail.
- **Don't** fall back to an auto-fill grid of equal cards; the sheet is one
  dense aligned column.
- **Don't** use a cream background or terracotta accent in either theme.
- **Don't** use ALL-CAPS UI labels, "WORD —" headings, or glyph/emoji icons.
- **Don't** let any row cause horizontal page scroll at 375px.
