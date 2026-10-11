# TEPHRA UI design spec: the Wall and the Desk

Version 2, 10 Oct 2026. Owner: lead product designer. Builders implement this document;
reviewers check the result against it. Where this spec and the code disagree, the spec wins until
it is changed here.

What this covers: the Wall (`/`, `index.html` + `wall.js` + `wall.css`) and the Desk
(`/desk`, `desk.html` + `desk.js` + `desk.css`). Shared assets that already exist and must be
used as they are:

| Asset | Path | Notes |
|---|---|---|
| Design tokens and fonts | `tephra/web/tokens.css` | Link it before the page's own CSS. Every colour, size, space, radius, shadow and duration below is a custom property there. |
| Fonts | `tephra/web/fonts/` | IBM Plex Sans (variable, 400-700) and IBM Plex Mono (400, 500); latin and latin-ext; `OFL.txt`. |
| Icons | `tephra/web/icons.svg` | One sprite, 72 symbols, referenced as `<svg class="icon" aria-hidden="true"><use href="/static/icons.svg#i-check"></use></svg>`. Colour comes from CSS `color`. |
| Map context data | `tephra/web/data/` | `firs.geojson`, `vaac_aor.geojson`, `land_apac.geojson`, `navaids.geojson`; see its `README.md`. |
| Credits | `tephra/web/THIRD_PARTY.md` | Every third-party asset and service, with the credit the page must show. |
| CSP | `CONTENT_SECURITY_POLICY` in `tephra/api/server.py` | Already allows GIBS, Mapterhorn and the two pinned unpkg packages. |

Reference renders and a working reference implementation (not product code) are in the session
scratchpad (`…` = `<scratch>`):
`…/ui/lead/ref/` (`index.html`, `wall-ref.mjs`, `wall-ref.css`, `desk.html`, `desk-ref.mjs`,
`desk-ref.css`, saved `/api/wall` responses in `data/`). They run under the same CSP and show every
map technique in this spec working on MapLibre 4.7.1 with real TEPHRA data. Copy ideas, not
files. Renders, all in `…/screens/v2/`:

| File | Shows |
|---|---|
| `ref-wall-1920-semeru.png` | 25 Sep replay, OFFICIAL mode (stub): official box at the arrow tip, TEPHRA box stacked, rose, grid, disagreements, timeline with the lag bracket |
| `ref-wall-1920-widened-illustrative.png` | The same with an illustrative WIDENED sector (stamped): hatch north over the observatory drift |
| `ref-wall-1920-java-kanlaon.png` | `java-live-20261010` replay: two real flights inside Kanlaon's area, flights dock with draft status, level ticks |
| `ref-wall-1440-semeru.png`, `ref-wall-1280-semeru.png`, `ref-wall-390-semeru.png` | The smaller Wall grids |
| `ref-desk-390-queue.png`, `-review`, `-hold`, `-confirm`, `-reject`, `-conflict`, `-offline`, `-toast`; `ref-desk-375-review.png`; `ref-desk-1440.png` | Desk states with the real `java-live` drafts |

The "before" screenshots of the current pages are `…/screens/v2/before-*.png`.

Contents: 1 Principles · 2 The story in one glance · 3 Tokens · 4 Layout grids · 5 Map
symbology · 6 Direction-mismatch rose · 7 Wall components · 8 3D, compare, timeline, level
filter · 9 Keyboard · 10 Desk · 11 Copy deck · 12 Accessibility · 13 Data rules · 14 Video
shot list · 15 Open issues.

---

## 1. Principles

1. **One story, five beats, one glance.** Every Wall state must answer, in this order: where is
   the official ash; where do the sources disagree; what area does TEPHRA plan around; who is
   flying into it; what did a human decide. Section 2 maps each beat to the one element that
   carries it. Anything that does not serve a beat is quiet (grey, thin, small) or hidden.
2. **One meaning per colour, everywhere.** Magenta is official and binding. Amber is TEPHRA (its
   area, the flights it finds entering it). Sky blue is the observatory (VONA, ground
   observer). Violet is REPLAY and nothing else. Status colours (green, yellow, red, grey) appear
   only in panels, never on the map, and always with a shape and a word.
3. **Never colour alone.** Every coloured mark has a second channel: line style (solid official,
   dashed TEPHRA, dashed observatory arrow), a shape (status symbols, eruption symbol), a letter
   (G/Y/O/R/U in the volcano symbol) or a word. The colour-vision tables in section 3.3 are the
   evidence; keep them true.
4. **Honest by construction.** The disclaimer, the REPLAY banner, the model label and every
   credit are layout, not decoration: they are always on screen and never collapse, scroll away
   or truncate. TEPHRA's output is "cautious area", "estimate", "hypothesis", "advisory draft";
   never "forecast", "warning", "detection" or "release". Satellite and SO2 layers say "context
   only" on screen.
5. **Official stays on top of meaning.** The official area cannot be switched off on the main
   map (it is binding); TEPHRA's outline is drawn just outside it so the eye reads "contains".
   Anything that hides an official polygon (the level filter) says so in a chip while it does.
6. **Calm.** Dark, matte surfaces; hairlines; one accent per element; no gradients except the
   map vignette; motion only when something changes (a new flight, a decision), three pulses at
   most, nothing loops except the slow march of exposure paths, and none of it under
   `prefers-reduced-motion`.
7. **Readable at two metres and in a 1080p video.** At 1920x1080 the key numbers are 24-40 px,
   body text 16 px, map labels 14-16 px with a 2 px halo, nothing meaningful below 12 px.
8. **Text comes from the data.** Feed and model text is inserted with `textContent` only. Code
   may compose labels from fields (section 13); it never invents a time, a number or a place.
9. **A human decides, visibly.** The Desk names the outcome on every button, asks once (hold or
   tap-and-confirm), never queues a decision offline, and shows the audit line after.

## 2. The story in one glance

| Beat | Carried by (Wall) | Where | Must read at 2 m |
|---|---|---|---|
| Official ash area | Magenta filled polygon, solid 2.6 px edge, VAG-style label box "SIGMET WAAF 12 + VAA DARWIN 2026/1098 · SFC–FL150 · MOV SE 10 KT · until 1720Z (50 min)" | Map | The box and the magenta shape |
| Where sources disagree | The direction rose at the vent (magenta official arrow vs sky dashed observatory arrow, "135° apart"); the flagged cell in the sources grid; the CAUTION card | Map and rail | The two arrows and the angle |
| TEPHRA's cautious area | Amber dashed outline drawn 5 px outside the official edge; amber hatch where the model widened it; label "TEPHRA CAUTIOUS AREA · SFC–FL150 / OFFICIAL 100% (NO MODEL)" | Map | The amber dashes around the magenta |
| Who is flying into it | Amber aircraft with a marching path to an entry ring labelled "+12 MIN"; the flights dock | Map | Amber planes and minutes |
| A human deciding | Flights dock and Decisions list: "Approved by AK · 16:07Z" with a check; the Desk's named buttons | Map dock, rail, phone | The check or cross and the name |

The headline pill on the map (section 7.6) repeats all five in one line, so a still frame of
the Wall explains itself: `SEMERU · ⚠ Direction disagreement 135° · TEPHRA area widened · 2
flights entering · 1 approved`.

Reference renders: `ref-wall-1920-semeru.png` (OFFICIAL mode, the 25 Sep replay as it is today)
and `ref-wall-1920-widened-illustrative.png` (WIDENED, with an illustrative sector, stamped as
such).

## 3. Design tokens

All values are custom properties in `tephra/web/tokens.css`. Use the property, not the hex. The
Wall reads the map colours at start-up:

```js
const css = getComputedStyle(document.documentElement);
const tok = (name) => css.getPropertyValue(name).trim();   // MapLibre takes the hex string
const C = { official: tok("--c-official"), tephra: tok("--c-tephra"), observer: tok("--c-observer"), /* … */ };
```

Only hex tokens go to MapLibre. Do not pass `rgb(… / …)` strings to paint properties.

### 3.1 Colour roles

Neutrals (cool blue-black; the UI is dark only, `color-scheme: dark`, on both pages):

| Token | Hex | Use |
|---|---|---|
| `--c-bg` | `#05080c` | Page background, behind everything |
| `--c-surface-1` | `#0a1017` | Command bar, rail, honesty strip, Desk header |
| `--c-surface-2` | `#0f1720` | Cards, grid column heads, Desk cards |
| `--c-surface-3` | `#16212c` | Selected tab, hover, pressed tool |
| `--c-surface-glass` | `rgb(10 16 23 / .88)` + `--glass-blur` | Panels floating over the map |
| `--c-scrim` | `rgb(2 4 8 / .72)` | Behind dialogs and sheets |
| `--c-line-1` | `#1c2834` | Hairline dividers |
| `--c-line-2` | `#2b3a4a` | Panel borders |
| `--c-line-input` | `#5b7086` | Borders that identify a control (3.2:1 or better on every surface) |
| `--c-text-1` | `#eaf1f7` | Primary text |
| `--c-text-2` | `#b6c3d0` | Secondary text |
| `--c-text-3` | `#93a3b5` | Tertiary text, labels of values (6.3:1 on the lightest surface) |
| `--c-text-ink` | `#05080c` | Text on bright fills (amber chip, magenta chip) |

Data semantics (map and panels, one meaning each):

| Token | Hex | Meaning | Text tint (on dark) |
|---|---|---|---|
| `--c-official` | `#ff3d8b` magenta | Official, binding (SIGMET, VAA) | `--c-official-text` `#ff9cc4` |
| `--c-tephra` | `#ffb000` amber | TEPHRA: its cautious area; flights it finds entering; its timeline marks | `--c-tephra-text` `#ffc845` |
| `--c-observer` | `#38bdf8` sky | Observatory: VONA, ground observer, drift arrow | `--c-observer-text` `#7dd3fc` |
| `--c-aircraft` | `#aab4be` | Other airline aircraft (context) | — |
| `--c-aircraft-stale` | `#7a8796` | Aircraft position older than 60 s | — |
| `--c-code-green/yellow/orange/red/unknown` | `#2ec4a0` `#fff176` `#f2711c` `#e8273b` `#8a96a3` | Aviation colour code, only inside the eruption symbol with its letter, and next to the word | Print the word in `--c-text-1`, never in the code colour |

Map-only (`--map-*`): land `#0c0c0c` (OpenFreeMap's own), water `#0b1a2a` (override), label
halo `#05070a`, volcano label `#d5dee7`, FIR line `#56697e`, FIR with a valid SIGMET
`#8aa2bb`, VAAC boundary `#7d8fa3`, navaid `#8fa0b2`. Label colours (contrast on land
`#0c0c0c`): `--map-label-minor` `#7d8a97` (basemap place names, inactive volcano names, 5.6:1),
`--map-label-fir` `#7f92a6` (FIR names, 6.1:1), `--map-label-vaac` `#8a9bb0` (VAAC names,
6.9:1); other aircraft labels use `--c-text-3` (7.6:1). `map.js` reads all of them with
`readTokens()`, so no map label colour is a literal any more.

Status (panels only; always shape + word; section 3.2):

| Token | Hex | Background token | Meaning |
|---|---|---|---|
| `--c-ok` | `#4ade80` | `--c-ok-bg` `#0b2416` | Feed OK, LIVE, APPROVED |
| `--c-caution` | `#ffe566` | `--c-caution-bg` `#2a2205` | CAUTION discrepancy, STALE feed, non-observation, night |
| `--c-serious` | `#ff7a6e` | `--c-serious-bg` `#2d0f0c` | SERIOUS discrepancy (backend severity WARNING), feed ERROR, REJECTED |
| `--c-info` | `#9db4cc` | — | INFO (harmless) discrepancy, estimated |
| `--c-off` | `#7a8796` | — | Feed off (DISABLED), never polled, SUPERSEDED |

Modes and decisions:

| Token | Hex | Use |
|---|---|---|
| `--c-replay` / `--c-replay-text` / `--c-replay-bg` / `--c-replay-ink` | `#b794ff` / `#cdb6ff` / `#1c1233` / `#e3d6ff` | REPLAY banner, REPLAY badge, replay clock caption, timeline progress |
| `--c-hypothesis-bg` | `#2b1d00` | HYPOTHESIS banner background (text `--c-tephra-text`) |
| `--c-approve` / `--c-approve-progress` / `--c-approve-ink` | `#2fbf71` / `#7ef0b0` / `#04130a` | Approve button, its hold fill, its text |
| `--c-reject` / `--c-reject-ink` / `--c-reject-text` | `#c9302c` / `#fff` / `#ff7a6e` | Final reject button, outline reject button text |
| `--c-focus` | `#f5f9fc` | Focus ring (2 px, offset 2 px, dark 4 px halo `--focus-halo`) |

`prefers-contrast: more` lifts text-2/text-3, the lines and the glass opacity (in `tokens.css`).

### 3.2 Status semantics: shape + colour + word

Shapes are sprite symbols (16x16, cut-out marks, one colour from `color`). Never show the shape
without the word on first use in a view; a repeated shape in a dense list may carry the word in
its `aria-label` and a tooltip.

| Concept | Value | Symbol | Colour | Word on screen |
|---|---|---|---|---|
| Feed | OK | `st-ok` filled circle | `--c-ok` | "OK" |
| Feed | STALE | `st-stale` diamond with bar | `--c-caution` | "Stale" |
| Feed | ERROR | `st-serious` octagon with ! | `--c-serious` | "Error" |
| Feed | DISABLED | `st-off` ring | `--c-off` | "Off" |
| Feed | NEVER | `st-never` dashed ring | `--c-off` | "Not polled yet" |
| Discrepancy | WARNING | `st-serious` | `--c-serious` | "SERIOUS" |
| Discrepancy | CAUTION | `st-caution` triangle with ! | `--c-caution` | "CAUTION" |
| Discrepancy | INFO | `st-info` circle with i | `--c-info` | "INFO" |
| Evidence | OBSERVED_SAT / OBSERVED_GROUND | `st-ok` | `--c-ok` | "Ash seen by satellite" / "Ash seen from the ground" |
| Evidence | ESTIMATED, NO_VA_EXPECTED, FORECAST_NOT_AVAILABLE | `st-info` | `--c-info` | section 11.3 |
| Evidence | NOT_OBSERVED, NOT_IDENTIFIABLE, NIGHT_BLIND | `st-caution` | `--c-caution` | section 11.3 |
| Evidence | STALE / UNKNOWN | `st-stale` / `st-off` | caution / off | section 11.3 |
| Advisory | DRAFT | `i-clock` | `--c-text-2` | "Awaiting dispatcher" |
| Advisory | APPROVED | `i-approved` circle-check | `--c-ok` | "Approved" |
| Advisory | EDITED | `i-approved` + `i-pencil` | `--c-ok` | "Approved with edits" |
| Advisory | REJECTED | `i-rejected` circle-x | `--c-serious` | "Rejected" |
| Advisory | SUPERSEDED | `i-superseded` dashed circle | `--c-off` | "Replaced by a newer draft" |
| Flight | inside the area now | `st-inside` ring with dot | `--c-tephra` | "INSIDE NOW" |
| Trace actor | code / gemini / adk / stub / human / system | `i-code` / `i-model` / `i-agent` / `st-never` / `i-user` / `i-system` | neutral; human `--c-ok` | "CODE" / "GEMINI" / "ADK" / "NO MODEL" / "HUMAN" / "SYSTEM" |

### 3.3 Colour-vision and contrast evidence

Method: Machado et al. 2009 dichromacy matrices at severity 1.0, CIEDE2000 on the simulated
colours (the research team's `cvd.py`), WCAG 2.2 contrast ratios. Script and full output:
`…/scratchpad/ui/lead/tools/palette_check.py`, `…/ui/lead/palette_report.md`.

Map colours, smallest CIEDE2000 across normal, protan, deutan and tritan vision (10 or more is
clearly distinct; under 10 means a second channel must carry the difference, and does):

| Pair | normal | protan | deutan | tritan | min | Second channel |
|---|---|---|---|---|---|---|
| official `#ff3d8b` vs tephra `#ffb000` | 54.5 | 46.5 | 25.7 | 20.8 | **20.8** | also solid vs dashed |
| official vs observer `#38bdf8` | 63.2 | 24.8 | 33.7 | 82.4 | **24.8** | solid vs dashed arrow |
| tephra vs observer | 56.0 | 52.8 | 57.5 | 52.5 | **52.5** | — |
| tephra vs aircraft `#aab4be` | 36.5 | 34.5 | 36.2 | 32.3 | **32.3** | size, label |
| observer vs aircraft | 18.0 | 15.2 | 17.1 | 18.4 | **15.2** | arrow vs plane shape |
| tephra vs code ORANGE `#f2711c` | 21.7 | 15.5 | 10.6 | 14.2 | **10.6** | letter O in the symbol |
| tephra vs code YELLOW `#fff176` | 20.7 | 13.2 | 10.9 | 20.1 | **10.9** | letter Y |
| code ORANGE vs code RED `#e8273b` | 22.3 | 20.0 | 10.6 | 9.3 | **9.3** | letters O/R, symbol size |
| official vs code ORANGE | 35.2 | 39.5 | 20.3 | 8.0 | **8.0** | eruption symbol vs polygon |
| official vs code GREEN `#2ec4a0` | 77.9 | 31.4 | 7.3 | 73.2 | **7.3** | eruption symbol vs polygon |
| observer vs code GREEN | 30.7 | 32.4 | 26.3 | 6.0 | **6.0** | arrow vs symbol, letter G |

Basemap: the research's water override raises land/sea CIEDE2000 from 4.2 to 10.5. Contrast
against land / water: official 5.86 / 5.26, tephra 10.68 / 9.59, observer 9.13 / 8.20, aircraft
9.30 / 8.35, code RED 4.46 / 4.00, FIR line 3.46 / 3.11 (all ≥ 3:1 for graphics).

Panel text (WCAG ratio, worst surface `--c-surface-3`): text-1 14.3, text-2 9.1, text-3 6.3,
official-text 8.4, tephra-text 10.6, observer-text 9.8, ok 9.4, caution (`#ffe566`) 12.9,
serious 6.4, info 7.6, replay-text 9.1. `--c-off` (4.45 on surface-3) is used for shapes and on
surface-1/2 only (5.2/4.9). Fills with text: approve 8.0, approve hold fill 13.6, reject 5.3,
replay banner 13.0, caution banner 12.5, hypothesis banner 10.6, serious banner 8.9, amber chip
11.0, magenta chip 6.0. Control borders `--c-line-input` 3.2-3.9:1; focus ring 15-19:1.

Status pairs under CVD that collide (always shape + word): ok vs serious 5.3 (deutan), caution vs
tephra 8.8 (deutan with `#ffe566`; the earlier `#f5d04a` was 4.9 and was dropped), ok vs caution
8.2.

### 3.4 Typography

Families: `--font-sans` IBM Plex Sans (UI text, big numbers; its digits are tabular, and
`font-variant-numeric: tabular-nums` is set anyway), `--font-mono` IBM Plex Mono (raw feed text,
codes, times in tables, hashes, flight levels in grids). Map labels use OpenFreeMap's Noto Sans
(`["Noto Sans Bold"]`, `["Noto Sans Regular"]`): MapLibre 4.7.1 needs PBF glyphs and Plex has
none on our host. Preload the Sans latin file:
`<link rel="preload" href="/static/fonts/ibm-plex-sans-var-latin.woff2" as="font" type="font/woff2" crossorigin>`.

| Token | Size | Wall use (1920) | Desk use |
|---|---|---|---|
| `--fs-1` | 12 px (`max(12px, 0.75rem)`) | Hashes, attribution, caps labels (600, +0.08em, upper case) | Hashes, fine print |
| `--fs-2` | 14 px | Secondary text, grid cells, trace lines | Labels of values, hints |
| `--fs-3` | 16 px | Body, tabs | Body |
| `--fs-4` | 18 px | Headline pill, area band | Entry time |
| `--fs-5` | 20 px | — | Card action |
| `--fs-6` | 24 px | Volcano name, KPIs, wordmark | Flight number, sheet title |
| `--fs-7` | 32 px | Clock | Minutes to entry |
| `--fs-8` | 40 px | (one hero number per screen at most) | — |

Weights 400/500/600/700. Line heights `--lh-tight` 1.15 (numbers), `--lh-snug` 1.3 (UI),
`--lh-body` 1.5 (paragraphs, advisory text). Root size: the Wall sets `html { font-size: 16px }`
at 1600 px wide and up, 15 px from 1360 to 1599, 14 px below 1360, and 16 px again at 600 px and
below; the Desk keeps 16 px and respects browser zoom. Type floor: `--fs-1` is
`max(12px, 0.75rem)`, because 0.75rem alone is 11.25 px at the 15 px root and 10.5 px at the
14 px root. `wall.css` has no literal size under 12 px (the old 11.5 px INFO summary and the
11 px "must" tag now use `--fs-1`). The map's own symbol labels (`text-size` 11 in `map.js`)
are canvas text, not CSS, and are not covered by this floor yet. Places that got wider when
the floor came in and need a look at 1280x720 and 1440x900: the comparison grid cells at 1359
and below (`.cmp__cell` drops to `--fs-1` in a 72 px label column), the tool tile labels in the
76 px column, the level-filter thumb ("FL350" in a 52 px pill), the timeline hour labels and the
compact rail tab labels (`.xtab__label`).

### 3.5 Space, radii, elevation, stacking, motion

- Space: 4 px grid, `--sp-1` 4 … `--sp-16` 64 (rem, so the Wall scales with its root size).
- Radii: `--radius-xs` 2, `-sm` 4 (chips, inputs), `-md` 8 (buttons, cards), `-lg` 12 (floating
  map panels, sheets on desktop), `-xl` 16 (phone sheets), `-pill`.
- Elevation: e0 flat surfaces; e1 `--shadow-1` (rail, bars); e2 `--shadow-2` + glass (map
  panels); e3 `--shadow-3` + `--c-scrim` (dialogs, sheets). On dark UI the border carries most of
  the edge; never use white glows.
- Stacking (`--z-*`): map overlays 10, panels 20, sticky bars 30, banners 40, popovers 50,
  dialogs 60, toasts 70, skip links 80.
- Motion: `--dur-1` 80 ms (press), `-2` 140 ms (hover, focus, chip), `-3` 220 ms (expand, row
  insert), `-4` 360 ms (sheet, dialog), `-5` 600 ms (decision stamp, changed value highlight),
  `--dur-camera` 1600 ms (fly to a volcano or flight), `--dur-camera-long` 2600 ms (story
  framing, 3D tilt), `--dur-pulse` 1600 ms per ring (three rings, then still), `--dur-hold`
  1200 ms (hold to approve). Easing: `--ease-standard` (0.2, 0, 0, 1), `--ease-enter`
  (0, 0, 0, 1), `--ease-exit` (0.3, 0, 1, 1). Under `prefers-reduced-motion: reduce` every
  duration except `--dur-hold` is 0 (in `tokens.css`): camera moves become `jumpTo`, pulses and
  marching paths are still, slide-ins are cuts. Read the media query in JS too (MapLibre
  animations do not read CSS). Wall controls (buttons, chips, segmented controls, region
  buttons, tools, tabs, flight rows, timeline marks and step buttons) ease background, colour,
  border and shadow
  over `--dur-2` on hover; on press they take a `--c-line-1` fill within `--dur-1`, plus a 0.97
  scale only when motion is allowed. Every duration in `wall.css` is a token (the old
  `--dur-quick` fallback, which ignored reduced motion, is gone).
- Tap targets: `--tap-min` 44 px (contract), `--tap-comfort` 48 px (Desk primary actions).

## 4. Layout grids

Dimensions are CSS px at the named viewport. "Inset" is the gap between a floating map panel and
the map edge.

### 4.1 Wall at 1920x1080 (the video frame)

```
y 0    ┌──────────────────────────── REPLAY banner 40 (REPLAY only) ────────────────────────────┐
y 40   ├──────────────────────────────── command bar 64 ───────────────────────────────────────┤
y 104  ├──────────────────── map 1280 ─────────────────────┬────────── rail 640 ───────────────┤
       │ legend 296 │ headline pill (≤ 844)  │  tools 76  │ volcano tabs 56                     │
       │ (≤ 360 h)  │                        │  (272 h)   │ volcano head 72                     │
       │            │                        │            │ What the sources say  ~300          │
       │            │     framed story       │  levels 76 │ Where they disagree  ≤ 240 (scroll) │
       │            │   (vent, areas, rose,  │  (420 h)   │ TEPHRA cautious area  ~150          │
       │            │    flights, paths)     │            │ Decisions             rest (scroll) │
       │ trace dock 600 x 132    flights dock 440 x ≤260   zoom 3x30│                           │
       │ timeline (full width − 32) x 96                            │                           │
y 1048 ├──────────────────────────────── honesty strip 32 ──────────────────────────────────────┤
y 1080 └─────────────────────────────────────────────────────────────────────────────────────────┘
```

- Rows: banner 40 (0 in LIVE), command bar 64, stage `1fr`, honesty strip 32. The body never
  scrolls (`overflow: hidden`); the rail and docks scroll inside.
- Stage columns: map `minmax(0, 1fr)`, rail 640 (560 at 1600-1799).
- Map insets 16. Legend top-left 296 wide. Headline pill from x = 296 + 32 to the tools
  column. Tools column top-right, 76 wide, five 52 px tiles. Level filter under the tools
  (top 304, track sized by the height rule in 4.2). Zoom and compass (MapLibre
  `NavigationControl`, restyled) sit just left of the level filter, level with its top, so they
  never share its column. Trace dock bottom-left, flights dock bottom-right left of the tool
  column, both 12 px above the timeline. Timeline 96 tall, inset 16 on all sides.
- Camera framing (`fitBounds`) pads for the panels: top 120, left legend width + 60, right 140,
  bottom timeline + docks + 40. Max zoom 8.6 when framing.

### 4.2 Wall at 1440x900

Root 15 px. Banner 36, command bar 56, strip 30, rail 500, inset 16, timeline 100, legend 260
(collapsed to a "Legend" button by default below 1600 px, except on a viewer's first visit, when
it starts open at every width (7.5); it opens over the map). Tools column
keeps icons and short labels; the region buttons drop their key hints; the command bar drops
the brand subtitle and the "FEEDS" caption, KPI values step down to 20 px and the clock to 24 px.
The flights dock is 360 wide and shows 3 flights then "+N"; the trace dock takes the remaining
width (at least 320) and shows its 2 latest lines (time, actor chip, message; the stage column is
dropped); T expands it.
Rail: tabs 52, head 64, sources grid ~270 (cells may wrap to two lines), disagreements ≤ 200,
area ~130, decisions rest.

The MapLibre zoom control is hidden at 1599 px and below (wheel and keys still zoom); from
1600 px it sits left of the level filter (4.1).

Height rule (every width from 1360 px): laptops are short (1366x768 and 1536x864 leave a map
pane of about 535 to 610 px), so the level track is sized from the map pane, never from the
window. `panels.renderLevels` works out the room under the tools column:
available = pane height − filter top (inset + 5 tiles + 24) − (timeline + inset + dock gap) −
the filter's measured height without its track − 8, and the track is min(270, available). When
that is under 140 px it adds `body.levels-pop`: the filter becomes the 4.3 popover (the "Levels"
tool shows; the filter opens beside the tools column, its track sized to the pane). The rule runs
again on resize and whenever the map pane changes height (the REPLAY or lost-stream banner
showing or wrapping), and on every render, so compare labels and new state are covered.

### 4.3 Wall at 1280x720

Root 14 px. Banner 32 (one line; the case label is hidden, still in the banner's tooltip and the
About dialog), command bar 48 (wordmark, mode badge, region menu button instead of three
buttons, clock, model chip, feeds chip, Desk icon button with label "Desk"), strip 28, rail 440,
inset 12, timeline 84. Tools column becomes icon-only (40 px tiles with tooltips and
`aria-label`s). The level filter collapses to a "Levels" tool that opens it as a popover. The
headline pill is hidden; the rail head carries the verdict (7.6) under the volcano name as a
wrapped sentence, never clipped (the discrepancy, the area mode, "N RFA (fictional) flights
entering", "N approved", led by "Recorded:" in REPLAY), then the area's second line; left out
in HYPOTHESIS, where the rail head already shows the hypothesis banner). The MapLibre zoom control is hidden (keys and
wheel still zoom). Trace dock: 1 line, expands on T. Flights dock: 300 wide with one-line rows, or
a pill "✈ 2 entering · first in 12 min" that expands when more than two flights enter. Rail: tabs 44, head 56, sources
grid compact (rows Seen, Height, Movement; Valid and Colour code move into the column head
tooltip), disagreements show CAUTION/SERIOUS items and one "Harmless (n)" line, area ~90,
decisions scroll.

### 4.4 Wall at 390x844 (phone width; usable, not the target)

Single column, page scrolls:
1. REPLAY banner, two lines allowed (48).
2. Command bar, two rows (88): row 1 wordmark, mode badge, clock; row 2 model chip, feeds chip,
   "Desk" link.
3. Verdict block (`#verdict`, `role="status"`), full width above the map: the volcano with its
   colour symbol (and "RECORDED" in REPLAY), then the two verdict lines of 7.6 wrapped in full
   (14 px), or the HYPOTHESIS line on the hypothesis tint. The rail head does not repeat them
   at this width. Hidden with no volcano selected.
4. Map, `height: 46vh` (min 320). Overlays: headline hidden; a "Legend" button top-left; tools as
   a horizontal row of three icon buttons top-right (Frame, Layers, 3D); the level presets and
   satellite live in the Layers sheet; swipe compare is not offered under 600 px (a swipe on a
   390 px map adds little); the timeline becomes one line under the map
   ("REPLAY · 25 SEP 16:30Z · 58%"). Map label boxes drop to 12 px and the rose to 78 px arrows.
5. A tab bar (sticky under the map, 48): Brief · Sources · Flights · Trace.
6. Tab panels (sections 7.11-7.14 stacked). The sources grid becomes one card per source
   (SIGMET, VAA, VONA), rendered by a phone branch in `panels.js`, not by CSS alone: the column
   head, then label and value rows (Seen at, Height, Movement, Valid, Colour code) with values
   wrapping in full, never clamped or left in a tooltip, then the hash and "Raw text". A flagged
   value keeps its caution ring and shape. Long verbatim fields (VAA info source and remarks,
   VONA activity and cloud height) are never grid rows at any width: they render as full-width
   quoted lines under the grid or cards, headed by their source kind ("VAA · VAAC",
   "VONA · observatory").
   Text floor at phone width: 12 px (`--fs-1`); no rule sets a smaller size.
7. Honesty strip fixed to the bottom, two lines (40); add `padding-bottom` to the page so it never
   covers content.

### 4.5 Desk at 390x844 (primary)

```
┌ sticky header ─────────────────────────────────┐
│ TEPHRA Desk   [NO MODEL] [● Live]   [AK ▾]  48 │
│ REPLAY: recorded real feeds from 23 Sep 2026 28│  (REPLAY only)
│ Decision support only - fictional airline -    │
│ not for operational use                     32 │
├────────────────────────────────────────────────┤
│ Drafts awaiting decision      2 waiting        │
│ ┌ card ──────────────────────────────────────┐ │
│ │ RFA4821  GIA208 · A320        ENTERS IN    │ │
│ │ HOLD FL250                       12 MIN    │ │
│ │ Krakatau · area OFFICIAL · drafted 2 min   │ │
│ │ [REPLAY] [Template · NO MODEL]             │ │
│ └────────────────────────────────────────────┘ │
│ ...                                            │
└────────────────────────────────────────────────┘
```

- Gutters 16. Max content width 600 (centred above 632 px). Header sticky, `--c-surface-1`,
  bottom hairline. It is 108 px tall in REPLAY, 80 in LIVE. Cards 12 apart, padding 16, radius 12.
- Review sheet: full screen (`<dialog>` in modal mode), its own sticky header (back, title,
  version) and a sticky action bar at the bottom (primary 56 + secondary row 48 + 16 padding +
  safe-area inset). The page header stays visible above the sheet: the sheet starts below it
  (the disclaimer and REPLAY banner never disappear).

### 4.6 Desk at 375x667

Same structure. Header text sizes step down one (the disclaimer is 12 px, still never
truncated). Card padding 12. Action bar: primary 52, secondary 44. The sheet body scrolls in
the space left (about 400 px); the action bar never covers the last row (bottom padding equal
to the bar height).

### 4.7 Desk at 1440x900

Header full width: row 1 (48) brand left, model chip, connection and account right; the REPLAY bar
(28) and the disclaimer row (24) under it, full width. Below: two panes inside a 1280 max-width
frame: queue
420 wide on the left (cards stacked, the selected one outlined in `--c-line-input` with a 3 px
left bar), review pane on the right (fluid, max 760) showing the selected draft as the
check-answers list with the action bar sticky at its bottom. The first card is selected on
load. No modal sheet at this width.

## 5. Map symbology

Basemap: OpenFreeMap `dark`, tuned after `load` (each call guarded with `map.getLayer`):
`water` fill `--map-water`; `landuse_park` fill-opacity 0.35; `place_city`, `place_city_large`,
`place_town` text colour `--map-label-minor` (`#7d8a97`); add the style's `ne2_shaded` raster as `ne2-relief` under
`water` (saturation -1, contrast 0.15, brightness-max 0.45, opacity 0.5, maxzoom 8); add
Mapterhorn `raster-dem` (`https://tiles.mapterhorn.com/{z}/{x}/{y}.webp`, terrarium, tileSize
512, maxzoom 12, attribution "© Mapterhorn") and a `hillshade` layer before `waterway` (minzoom
5, exaggeration 0.45, shadow `#000000`, highlight `#2a3442`, accent `#05070a`). Handle
`styleimagemissing` with a 1x1 transparent image (the dark style asks for `circle-11`).

Layer order, bottom to top (all after the basemap unless noted):

| # | Layer id | Type | Source / filter | Paint and layout |
|---|---|---|---|---|
| 0 | `ne2-relief`, `hillshade` | raster, hillshade | style `ne2_shaded`; Mapterhorn `dem` | terrain shading inside the basemap (paragraph above); toggle "Terrain shading" in Layers |
| 1 | `gibs` | raster | GIBS (5.6) | inserted before `water_name`; opacity 0.6 (Air Mass 0.55); IR: saturation -1, contrast 0.2 |
| 2 | `so2` | raster | GIBS TROPOMI | before `water_name`; opacity 0.7 |
| 3 | `btd-<id>` | raster (image) | `overlays.btd[*]` corners | before `water_name`; opacity 0.75 |
| 4 | `fir-line` | line | `/static/data/firs.geojson` | `--map-fir`, 1 px |
| 5 | `fir-active` | line | FIRs named in a valid SIGMET id (`SIGMET:<FIR>:…`) | `--map-fir-active`, 1.6 px |
| 6 | `fir-label` | symbol | firs, minzoom 5 | line placement, spacing 700, `label` ("WAAF UJUNG PANDANG FIR"), Noto Sans Regular 11, letter-spacing 0.08, `#7f92a6`, halo 1.5 |
| 7 | `vaac-line` | line | `/static/data/vaac_aor.geojson` | `--map-vaac`, 1.2 px, dash [6,3,1,3]; label "DARWIN VAAC" / "TOKYO VAAC" like FIRs |
| 8 | `navaid` | circle + symbol | `/static/data/navaids.geojson`, minzoom 8 | 3 px ring `--map-navaid`; ident 11 px; off by default |
| 9 | `tephra-fill` | fill | cones, `part == cone` | `--c-tephra` 0.07 (dimmed 0.03) |
| 10 | `tephra-hatch` | fill | cones, `part == sector` | `fill-pattern` hatch image (section 5.2), opacity 1 (dimmed 0.4) |
| 11 | `official-fill-now` | fill | official, step `now`, shown, `fill == true` (5.1) | `--c-official` 0.14 (dimmed 0.07) |
| 12-14 | `official-fill-f6/f12/f18` | fill | steps | 0.05 / 0.035 / 0.025 |
| 15 | `official-line-now` | line | step `now` | 2.6 px at z8 (1.6 at z4), solid, join round |
| 16-18 | `official-line-f6/f12/f18` | line | steps | 2 px dash [4,2] op 0.9; 1.8 px dash [2,2] op 0.75; 1.8 px dots [0.1,2] round cap op 0.6 |
| 19 | `tephra-line` | line | cones, `part == cone` | `--c-tephra` 2.6 px at z8, dash [3,2], `line-offset: -5` (outset), join round |
| 20 | `exposure-path` | line | exposures, `kind == path` | `--c-tephra` 2.4 px dash [1.5,1.5]; marching (5.4) |
| 21 | `exposure-entry` | circle | `kind == entry` and `minutes_to_entry > 0` | r 6, fill `--map-halo`, stroke `--c-tephra` 2.5 (no ring for a flight already inside) |
| 22 | `exposure-entry-label` | symbol | same filter | "+12 MIN", Noto Sans Bold 13, `--c-tephra-text`, offset [0,-1.3] |
| 23 | `volcano-inactive` | symbol | `active == false` | hollow eruption icon 0.5, opacity 0.8; name from z7.5, 11 px `--map-label-minor` |
| 24 | `volcano-active` | symbol | `active == true` | eruption icon by code (5.3); name Noto Sans Bold 14 (16 selected), `--map-label`, halo 2 |
| 25 | `aircraft-icon` | symbol | aircraft | SDF plane (5.3) |
| 26 | `aircraft-inside` | circle | `inside` | r 18, stroke `--c-tephra` 2, no fill |
| 27 | `aircraft-label-exposed` | symbol | `exposed` | two lines (5.3), Bold 14, allow overlap |
| 28 | `aircraft-label` | symbol | not exposed, minzoom 7.5 | "GIA123 FL350", Regular 11, `--c-text-3`, optional |
| 29 | `official-label` | symbol | `official-labels` point source (5.1) | stretchable box `box-official`, `icon-text-fit: both`, padding [5,9,5,9], two-line `format`, data-driven `text-anchor` and `text-offset`, icon and text allow overlap |
| 30 | `tephra-label` | symbol | `area-labels` point source (5.2) | box `box-tephra`, same style, stacked against the official box |
| 31 | `rose-*` | line, circle, symbol | `rose` source (section 6) | above all labels so it wins collisions |

`dim` is true for features of volcanoes other than the selected one: they stay visible at
reduced opacity (official areas are never hidden on the main map).

### 5.1 Official products and labels

- `step` from `OfficialFeatureProps.layer`: `SIGMET` and `OBS` → `now`; `FCST+6H` → `f6`;
  `FCST+12H` → `f12`; `FCST+18H` → `f18`. One layer per step because `line-dasharray` is not
  data-driven in 4.7.1.
- Shown by default: every feature with `valid_from ≤ state.now ≤ valid_to` (so SIGMET, OBS and,
  most of the time, the +6 h step whose window is its forecast time ± 3 h). The "Forecast steps"
  control (Layers panel and the timeline) shows +6/+12/+18 together or one at a time; expired
  features never draw.
- Fill without double counting: translucent fills compound where polygons overlap, and the
  Indonesian offices copy Darwin's polygon, so the client sets `fill` on each now-valid feature:
  `true` for the latest valid SIGMET per FIR and volcano (an office's latest SIGMET replaces its
  earlier ones, as in the discrepancy finder), `true` for VAA OBS features only when the volcano has
  no valid SIGMET, `false` otherwise. Every feature still draws its outline.
- Label (`official-labels`, a point source the client computes): **one box per volcano** for the
  official area valid now. Line 1 (`--c-official-text`): product names, SIGMET first, joined
  with " + " ("SIGMET WAAF 12 + VAA DARWIN 2026/1098"); the VAA name is its `label` without the
  trailing `EST`/`OBS`. Line 2 (`--c-text-1`, scale 0.9): band "SFC–FL150", then for the
  selected volcano the movement from the SIGMET (or VAA) card's `display_fields.Movement`, then
  "until 1720Z (50 min)" from the SIGMET `valid_to`, recomputed every 15 s. Anchor: just beyond the
  tip of the official arrow when the rose is shown (section 6; `text-anchor` from the bearing,
  limited to `top`, `top-left`, `top-right`, `bottom`, `bottom-left`, `bottom-right`); otherwise the
  centroid of the SIGMET (or OBS) polygon's vertices with anchor `top`; if that centroid lies within
  25 km of the vent (circular SIGMETs centred on the volcano), the polygon's northernmost vertex
  with anchor `bottom` (the box sits above the area, clear of the vent). Other volcanoes' boxes are
  12 px, line 2 is the band only.
- After framing (7.4), if the label stack would cross a panel or the map edge, pan the camera by the
  overlap (`panBy`) so the whole stack is visible.
- Forecast-step labels appear only when the steps view is on: plain text "+6 h · 1700Z"
  (forecast time = `valid_from + 3 h`), 12 px, `--c-official-text`, at the step polygon's centroid.
- The stretchable box: a 36x36 canvas at pixel ratio 2, fill `rgba(8,12,18,.92)`, 3 px border in
  the role colour, radius 6, registered with `stretchX: [[9,27]]`, `stretchY: [[9,27]]`,
  `content: [9,9,27,27]` (reference: `labelBox()` in `wall-ref.mjs`).

### 5.2 TEPHRA's cautious area

- Outline `tephra-line`: amber dash [3,2], `line-offset: -5` so it sits just outside the official
  edge when the two coincide (OFFICIAL mode) and reads "contains" (research shot-coincident).
  Legend note: "drawn just outside the area it contains".
- Fill 0.07 under the official fill. Where the model widened it (`part == sector` exists, modes
  WIDENED and HYPOTHESIS) the sector gets a 45° amber hatch: a 24x24 canvas at ratio 2, three
  3 px lines at alpha 0.55, added with `addImage` and used as `fill-pattern`.
- Label (`area-labels` point source): an amber-bordered box stacked against the selected volcano's
  official box: same anchor point and `text-anchor`, `text-offset` 3.1 em further away from the
  point (below the official box when it hangs below its anchor, above it otherwise), so the two read
  in order (official, then TEPHRA) and never cover each other, the vent or the rose. Line 1
  `--c-tephra-text` "TEPHRA CAUTIOUS AREA · SFC–FL150" (cone base/top), line 2 `--c-text-1` the
  cone's `label` verbatim ("OFFICIAL 100% (NO MODEL)", "WIDENED 62%"). With no official box
  (HYPOTHESIS), it sits at the area's southernmost vertex with anchor `top`.
- HYPOTHESIS (no valid official product): the whole area is hatched (cone = sector), the label
  line 2 is "HYPOTHESIS 40% · MONITOR OR HOLD ONLY", the headline pill turns into the
  hypothesis banner style (`--c-hypothesis-bg`, `st-caution`, "HYPOTHESIS: no valid official
  product. MONITOR or HOLD only."), and the rail area card says the same (section 7.13).

### 5.3 Volcanoes and aircraft

- Eruption symbol (ICAO/WMO, as the VAACs draw it): trapezoid, three rays, base dot, drawn on a
  64x64 canvas at ratio 2 with a 5 px dark outline, filled with the code colour and the letter
  G/Y/O/R/U in Plex Sans 700 at 19 px (reference `eruptionIcon()`). Size by level: RED 1.0,
  ORANGE 0.92, YELLOW 0.84, GREEN 0.76, UNKNOWN 0.76. Inactive catalogue volcanoes: hollow grey
  trapezoid, no rays, no letter, 0.5.
- Selected volcano: a 46 px ring HTML marker (`.pulse`, 1.5 px `--c-text-1` at 85%) plus three
  expanding rings (`--dur-pulse`, CSS animation, iteration count 3) when it becomes selected or
  when a new discrepancy appears; still under reduced motion. Its name label goes on the side
  opposite the rose arrows' mean bearing (`text-anchor` and `text-offset` are data-driven).
- Aircraft: one white SDF image from the Material Symbols `flight` path (north-up), rasterised on
  a 96x96 canvas with 16 px padding and converted with `alphaToSdf` (radius 16, cutoff 0.25),
  added with `{ sdf: true, pixelRatio: 2 }` (research snippet; `map.loadImage` cannot load data:
  or SVG under this CSP). `icon-rotate` = `track_deg`, rotation alignment `map`, allow overlap.
  States:

| State | Rule | Icon | Size | Label |
|---|---|---|---|---|
| Normal | `exposed == false` | `--c-aircraft`, halo `--map-halo` 1.5 | 0.3 at z3, 0.42 at z6, 0.5 from z8 (thinned when zoomed out) | from z7.5: callsign (or hex) + level, 11 px grey |
| Exposed | `exposed == true` | `--c-tephra` | 0.7 | always: line 1 `--c-tephra-text` "RFA4821 · GIA208" (proxy · callsign), line 2 `--c-text-1` "FL350 · 12 MIN"; Bold 14 |
| Inside now | exposed and `minutes_to_entry == 0` | `--c-tephra` + ring r 18 | 0.7 | line 2 "FL350 · INSIDE NOW" |
| Picked | the viewer chose it on the map or in the flights dock (7.8) | unchanged + `--c-text-1` ring r 23, 2.5 px | unchanged | unchanged; details in the flights dock |
| Stale | `state.now − observed_at > 60 s` | `--c-aircraft-stale`, opacity 0.55 | as above | append " · 2 MIN OLD" |
| Level unknown | `alt_baro_ft == null` | as above | | "level unknown"; never hidden by the level filter |
| Decided | an advisory for this flight is APPROVED/EDITED/REJECTED | unchanged | | line 2 appends " · HOLD approved" / " · rejected" (from the advisory) |

### 5.4 Exposure paths

Amber dashed line from the aircraft to its entry point, entry ring with "+12 MIN". The dashes
march toward the entry (cycle the 14-step `line-dasharray` set from the research snippet every
60 ms with `setPaintProperty`; pause while `document.hidden`; still under reduced motion). Only
this layer animates continuously.

### 5.5 Context layers

- FIR outlines always on (thin, quiet), labelled "approximate" in the legend's context line and
  in About. The FIR containing a valid SIGMET is brighter: that explains why a SIGMET stops at a
  line.
- VAAC boundary on; navaids off by default (Layers panel); airports are not drawn (no data
  contract for them on the Wall).
- ADS-B coverage note: when the aircraft layer is on and no aircraft feature lies within 150 km
  of the selected volcano, show the map note in 7.6 and the flights dock text in 7.8. An empty map
  is never presented as an empty sky.

### 5.6 Satellite and SO2 context (GIBS)

| Layer | GIBS identifier | Matrix set | Max zoom | TIME | Label (always on screen while shown) |
|---|---|---|---|---|---|
| Infrared | `Himawari_AHI_Band13_Clean_Infrared` | `GoogleMapsCompatible_Level6` | 6 | 10-min slot (below) | "CONTEXT ONLY · Himawari-9 infrared (band 13) 1620Z · not ash detection · Imagery: NASA GIBS · Himawari-9 data: JMA via NOAA" |
| Visible | `Himawari_AHI_Band3_Red_Visible_1km` | `GoogleMapsCompatible_Level7` | 7 | 10-min slot | same, "visible (band 3), daylight only" |
| Air mass | `Himawari_AHI_Air_Mass` | `GoogleMapsCompatible_Level6` | 6 | 10-min slot | same, "Air Mass RGB" |
| SO2 | `TROPOMI_L2_Sulfur_Dioxide_Total_Vertical_Column` | `GoogleMapsCompatible_Level6` | 6 | `YYYY-MM-DD` | "CONTEXT ONLY · SO2 (TROPOMI, daily) 25 Sep 2026 · SO2 is not ash; gases not modelled · Imagery: NASA GIBS · Contains modified Copernicus Sentinel data 2026" |

URL template: `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/{layer}/default/{time}/{matrix}/{z}/{y}/{x}.png`
(note `{y}` before `{x}`), `tileSize: 256`.

TIME follows TEPHRA's active clock, never the browser's:

```js
function gibsTime(nowIso, mode) {              // nowIso = state.now (or the last heartbeat now)
  let t = Math.floor((Date.parse(nowIso) - (mode === "LIVE" ? 3600e3 : 0)) / 600e3) * 600e3;
  const d = new Date(t);                        // GIBS lags 40-50 min live; skip 0240Z and 1440Z
  if (d.getUTCMinutes() === 40 && (d.getUTCHours() === 2 || d.getUTCHours() === 14)) t -= 600e3;
  return new Date(t).toISOString().slice(0, 19) + "Z";
}
const so2Date = (nowIso, mode) =>
  new Date(Date.parse(nowIso) - (mode === "LIVE" ? 86400e3 : 7 * 3600e3)).toISOString().slice(0, 10);
```

When the slot changes (check on every `state` and `heartbeat`), replace the source's tiles
(`source.setTiles([...])`; if unavailable, remove and re-add source and layer at the same
position). If tiles 404 (gaps), step back one slot at a time, at most six, then show "No
Himawari frame near 1620Z" in the label. The label shows the slot actually requested. One
satellite layer at a time (radio group); SO2 is a separate checkbox. Both off by default.

Scale strip: under the CONTEXT ONLY line, only for the layers whose GIBS entry publishes a
colour-map legend: infrared band 13 (`Clean_Longwave_Infrared_Window_Band`, °C) and SO2
(`OMI_SO2_Lower_Troposphere`, DU). The Wall fetches `colormaps/v1.3/<name>.xml` from GIBS at run
time and draws the legend entries, `minLabel`, `maxLabel` and the labelled entries; the caption
names the colour map title and units and "NASA GIBS colour map". The infrared strip applies the
map's own filter (saturation -1, contrast 0.2, as MapLibre computes them) and says "drawn in
grey, as on the map". Visible and Air Mass RGB have no published legend, so no scale is drawn
for them. While loading: "Scale loading from NASA GIBS…"; on failure: "Scale unavailable: the
NASA GIBS colour map did not load. No scale is shown in its place." (retried after 5 min). No
strip when the label says "No Himawari frame near …".

The BTD overlay from `overlays.btd` keeps its own caption and is labelled "Split-window BTD
(computed by TEPHRA) · an indicator, not ash detection · Himawari-9 data: JMA via NOAA".

## 6. The direction-mismatch rose

Shown for the selected volcano when it has a `DIRECTION_MISMATCH` discrepancy with
`aspect == "direction"`. Drawn as MapLibre layers (not an HTML marker), so its labels take part
in collision handling and it tilts correctly in 3D.

Inputs (all code-written by the backend):
- Vent: the volcano feature's coordinates.
- Bearings: parse the 16-point compass word from each value in `discrepancy.values` with
  `/\b(NNE|ENE|ESE|SSE|SSW|WSW|WNW|NNW|NE|SE|SW|NW|N|E|S|W)\b/` → index × 22.5°. Keys starting
  `VONA:` are the observatory; `SIGMET:` and `VAA:` keys are the official movement (they agree
  when the backend has grouped them). Values look like `MOV SE 10KT` and `moving N`. If either
  bearing does not parse, draw no rose; the rail card still explains the discrepancy.
- The angle: `discrepancy.magnitude` (degrees), printed as given, rounded.

Geometry, rebuilt on `zoomend` so it keeps a constant screen size (512 px tiles):
`mpp = 78271.517 × cos(lat) / 2^zoom`; arrow length 120 px, start radius 16 px (clears the
eruption symbol), arc radius 52 px, angle label at arc radius + 30 px on the bisector.

| Part | Style |
|---|---|
| Official arrow | `--c-official` 3.4 px solid line on an 8 px `--map-halo` casing; SDF arrowhead (triangle, 64 px canvas) rotated by bearing, `--c-official`, halo 1.5 |
| Observatory arrow | `--c-observer` 3.4 px dashed [2, 1.6] on the same casing; same arrowhead in `--c-observer` |
| Arc | `--c-text-1` 1.6 px on a 5 px casing, the shorter way between the bearings |
| Angle label | box with a white border, Noto Sans Bold 17, `--c-text-1`: "135° apart" |
| Observatory label | at the arrow tip, variable anchor (left, right, top, bottom), two lines: "OBSERVATORY · N" (`--c-observer-text`) / "VONA 1629Z · ground observer · night" (`--c-text-2`, 0.85). "night" when the local solar hour at the vent (UTC hours + lon/15) is before 06 or from 18. |
| Official label | the official area box itself (5.1), anchored just beyond the official arrow's tip, anchor chosen from the bearing (SE → `top-left`), so the arrow points at the box that names the movement |
| Drift probe | when the same discrepancy set has `aspect == "polygon"`: a 5 px ring (`--c-observer` stroke) 15 km along the observatory bearing (the backend's probe distance). It sits visibly outside the magenta edge. |

Legend rows: "Official movement" (`lg-arrow-official`) and "Observatory drift"
(`lg-arrow-observer`). Never call either arrow right or wrong; the rail card says "TEPHRA's
area covers both" only when the cone mode is WIDENED and the sector contains the observatory
bearing.

## 7. Wall components

Every component lists its states. "Stale" means the stream is lost (7.17) or the data are older
than their cadence allows; "replay" means `state.mode == "REPLAY"`.

### 7.1 REPLAY banner

Full-width band above the command bar, `role="status"`, never dismissible, present for the whole
REPLAY session and absent in LIVE. Background `--c-replay-bg` with a 120 px band of 135°
stripes at the left (`repeating-linear-gradient`, violet at 16%), 2 px bottom border
`--c-replay`. Content: `i-replay` icon, a solid violet tag "REPLAY" (ink `#120a24`), the text
`state.replay.banner` verbatim at 18 px semibold, then "· " + `state.replay.label` in
`--c-replay-text` (hidden below 1360 px, kept in `title`). If `state.replay.auto` is true, add
"· switched automatically: no live activity". The document title is prefixed "REPLAY - ".
The banner's text is written only when it changes, so a screen reader announces it once and not
on every render. The same rule holds for the stream-lost banner (`role="alert"`) and the
headline pill (`role="status"`, 7.6).

### 7.2 Command bar

Left to right: wordmark "TEPHRA" (24 px, 700, letter-spacing 0.18em) and subtitle "Volcanic-ash
decision desk" (14 px, text-3); mode badge; region presets; spacer; KPIs; model chip; feeds
chip; clock; "Open Desk" link.

- Mode badge (32 tall pill): LIVE = `--c-ok-bg` fill, `--c-ok` border and text, `i-live` icon,
  "LIVE"; REPLAY = solid `--c-replay`, ink `#120a24`, `i-replay`, "REPLAY"; before the first
  state = neutral outline "CONNECTING".
- Region presets: a segmented control (pill group) of `state.regions`, each button "1 Java /
  Bali" with the key hint in a `kbd`, the name, and a count badge of active volcanoes inside its
  bbox (hidden when 0). `aria-pressed` on the current one: a `--c-line-2` fill with a 1.5 px
  `--c-text-2` ring (10:1 text), the same selected look as every `.seg` segmented control. Fly
  to the region with `--dur-camera`.
- KPIs: first the hero, "RFA (fictional) flights entering" (`exposed_count` over all volcanoes,
  said in its tooltip; value 32 px, 24 px below 1600 px, over a caps label that may wrap to two
  lines). It is `--c-tephra-text` amber only when above 0. At 0 it shows "—" in text-3, never
  "0", "none" or "clear", with the tooltip "No RFA (fictional) flight seen entering. Receiver
  coverage is patchy: an empty map is not an empty sky." Then "Active"
  (`active_volcano_ids.length`) and "Drafts" (`draft_count`); value 24 px over a 12 px caps
  label. The KPIs are hidden at 1359 px and below, where the verdict (7.6) carries the count.
- Model chip: `state.llm.label` in Plex Mono 500. Stub: dashed border, `i-code` icon, "NO MODEL".
  Gemini: solid border, `i-model` icon, the model id ("gemini-3.8-flash"). Tooltip with NO MODEL
  reuses the area outcome wording (11.5): "NO MODEL: official products only. Text that a model
  would write comes from code templates; nothing on screen was written by a model." With a
  model: "Steps that call a model are marked AI-drafted. Times, ids and hashes are always
  written by code." The Desk chip and its NO MODEL marks use the same words; no screen calls
  the stub a test mode.
- Feeds chip: caps "FEEDS" then counts by status with their shapes, worst first ("● 3 OK · ○ 6
  off", "⬢ 1 error"). It opens the feed health dialog (7.16). The chip never turns red as a
  whole; only the ERROR count does.
- Clock: `HH:MM:SSZ` (32 px, 600, tabular) from the active clock, ticking locally between
  heartbeats; under it "25 SEP · REPLAY CLOCK · UTC" (violet) or "10 OCT · UTC". The timeline's
  window line and hour axis carry the tooltip "Times ending in Z are UTC".
- Open Desk: outlined button with `i-dispatcher`, opens `/desk` in a new tab (`rel="noopener"`).
- States: loading (all values "–", badge "CONNECTING"), stale (clock caption "STREAM LOST ·
  last 16:07:12Z" in caution, the badge keeps the mode), replay (as above).

### 7.3 Honesty strip

Bottom row, always visible, never truncated on the left part: `i-info` (info colour), the
disclaimer `state.disclaimer` verbatim in 14 px semibold text-1 (the same text is in the HTML
before JS runs), "RFA flight numbers are proxies for real aircraft." in text-3, then on the right
the attribution line (12 px, text-3, may ellipsize only at 1280 and below; full text in About):
"OpenFreeMap © OpenMapTiles · Data © OpenStreetMap contributors · © Mapterhorn · Aircraft:
adsb.lol (ODbL 1.0) · Himawari-9 data: JMA via NOAA · FIR and VAAC lines: NOAA/NWS AWC
(approximate)" plus, while a GIBS layer is on, "· Imagery: NASA GIBS" (and "· Contains modified
Copernicus Sentinel data 2026" for SO2), plus "· Weather data by Open-Meteo.com" (a link) when a
wind value is visible. Then, once `state.policy` is known, the short "Policy A · illustrative"
button (its title gives the policy id, version and label), which opens the operator policy panel
(7.18); that button is hidden at 600 px and below, where the About dialog's link is the way in.
After it come the "Help" button (7.3a) and the "About and credits" button. MapLibre's own attribution control
is not added (`attributionControl: false`); this strip replaces it and must keep every credit
the style and sources declare.

About dialog: what TEPHRA is (three sentences), the honesty statements (decision support only;
the airline is fictional; nothing is sent anywhere; REPLAY is recorded data; TEPHRA's area is an
estimate, never a forecast), the full GIBS acknowledgement, the credits table from
`THIRD_PARTY.md`, an "Operator policy" heading with the button "Open the operator policy"
(focus returns to About when the panel closes), and a Help section whose
button opens the Help dialog (7.3a). The honesty list
also says "SO2 is not ash. Volcanic gases may also be undesirable to fly through; TEPHRA does not
model them."

### 7.3a Help and glossary

For a viewer who does not work in aviation. A visible "Help" button in the honesty strip, next to
"About and credits" and in the same style, opens the shared dialog titled "Help"; the `?` key and
the button in About open the same dialog. It is visible at every width. The strings live in
`tephra/web/wall/glossary.js`; the dialog has three parts, in this order:

1. "How to read this screen", six short lines: the map shows the official ash areas and TEPHRA's
   cautious area, never smaller than the official one; the right rail compares what each source
   says and lists where they disagree; the flight list shows aircraft heading into an area; the
   Desk is where a person approves or rejects each advisory, and nothing is sent to a real
   system; REPLAY means recorded or reconstructed data, not live; times end in Z, which is UTC.
2. "Glossary", a definition list: SIGMET; VAA and VAAC; VONA; FIR; FL; Z; ADS-B (a gap in
   coverage is not an empty sky); RFA proxy flight; NO MODEL; REPLAY and reconstructed; Affected
   area; Policy A (illustrative). Every acronym the Wall shows has an entry. The entries never call
   TEPHRA's own output binding, a forecast or a warning.
3. "Keyboard shortcuts", the table from section 9 and the single-key toggle.

First-look card: at the top of the rail brief (Brief tab on a phone), a small surface-2 card:
"New here? Pink is the official ash area, which is binding. Amber is TEPHRA's cautious area, an
estimate never smaller than the official one. Times ending in Z are UTC. RFA (Ring of Fire Air)
is a fictional airline." with two link buttons, "Help and glossary" (opens this dialog) and "Got
it, hide this" (sets `introDismissed` in the per-viewer prefs; with storage blocked it returns
next visit). Never shown in presentation layout. It is not a map overlay: the legend, the trace
dock and the flights dock already hold the map's corners.

### 7.4 Map container and camera

- `new maplibregl.Map({ container, style, maxPitch: 70, attributionControl: false, dragRotate:
  false, pitchWithRotate: false, fadeDuration: 150, preserveDrawingBuffer })`; enable
  drag-rotate only in 3D. `preserveDrawingBuffer` is true only when the URL carries `?shots=1`
  (both the main and the compare map); present mode and everyday use do not pay for it. It keeps
  automated screenshots honest: browsers that throttle `requestAnimationFrame` (headless runs,
  background windows) otherwise capture a stale or empty canvas. Screenshot scripts load the Wall
  with `?shots=1` (for example `/?shots=1&present=1`). Expose the map read-only for tooling as
  `window.__tephra = { map }`; screenshot scripts call `window.__tephra.map.redraw()` before
  capturing.
- Map sources are sent with `setData` only when their derived data changed: the map keeps the
  last JSON string sent to each source and compares the derived FeatureCollection, never the
  store object. The 15 s timer still runs derive and the map update through this check, so an
  official area expires or becomes valid on time with no new event.
- The map element is focusable (`tabindex="0"`, `aria-label="Map. Arrow keys pan, plus and minus
  zoom."`) and keeps MapLibre's keyboard handler.
- First view: select the top-priority volcano (7.10) and frame it (4.1 padding), instantly. After
  that, the camera moves only when the user asks (region, Frame, a flight, a volcano tab) or when
  a new flight enters the selected volcano's area (fly to fit it, once per flight).
- Vignette: a non-interactive overlay `radial-gradient(ellipse 75% 70% at 50% 46%, transparent
  62%, rgb(2 4 8 / .5) 100%)`.
- Readiness: set `document.body.dataset.mapReady = "true"` once `map.areTilesLoaded()` after the
  first framing (do not wait for `idle`; animated images stop it firing). The video operator and
  the critics' screenshots wait for it.
- Re-frame on container resize (`ResizeObserver`), not only on load.
- Popups: click (or Enter on a focused feature list item) opens a dark popup (glass, 320 wide)
  with the feature's facts as a definition list; never hover-only. Official: label, kind,
  layer, band, valid from–to with countdown, source id, a "Show raw text" button (opens 7.15).
  TEPHRA area: mode, confidence, band, label, valid to, "never smaller than the official area".
  Aircraft: proxy, callsign, hex, type, level (baro and selected), ground speed, track, observed
  age, exposure line, advisory status. Volcano: name, code word with symbol, active reasons.

### 7.5 Legend

Glass panel top-left, caps title "LEGEND". It starts open on a viewer's first visit at every
width (a `visited` flag in the per-viewer prefs; with storage blocked every visit counts as the
first); afterwards the viewer's own open or closed choice holds, or, before any choice, it is open
at 1600 px and up. With `?present=1` it never opens on its own. Rows of a 26 px sprite swatch +
text (14 px): Official
ash area · binding; Official forecast · +6 h dashed (only when a step polygon is drawn); TEPHRA
cautious area · never smaller (drawn just outside what it contains); Widened by the model
(only when a sector exists); Official movement; Observatory drift (only with a rose); Flight
entering the area; Other airline flight; then a full-width row of the five eruption symbols with
"Aviation colour code, lowest to highest: green, yellow, orange, red; grey means unknown"; then a
context line "FIR and VAAC lines approximate". Rows appear only when the thing is on the map.
Collapsible (L). Folded, it keeps a mini key under the "LEGEND" button: up to three 18 px
swatches with one word each, stacked so the folded panel stays narrow: "Official" (always),
"TEPHRA" (when the cautious area is drawn) and "Entering" (when a flight enters), under the same
conditions as the full rows. It is never lowered below 1600 px to open by default: open, it
would cover a quarter of the map at 1440 px and squeeze the headline. States: loading
(skeleton rows), 3D (adds "Heights ×6"), compare (adds the A/B meaning), context layer on (adds
its legend image or scale).

### 7.6 Headline pill and map notes

The verdict. At the top of the map, between the legend and the tools, 18 px semibold, glass:
`[eruption symbol] SEMERU · ⚠ Direction disagreement 135° · TEPHRA area widened · 2 RFA
(fictional) flights entering · 1 approved`. Parts are present only when true: the discrepancy part uses the highest
severity's shape and word ("SERIOUS: a VAA says no ash while another source saw it" for
CONFLICT); the area part is "TEPHRA area = official", "TEPHRA area widened" or "HYPOTHESIS:
MONITOR or HOLD only"; flights "0 RFA (fictional) flights entering" stays (it is information;
every count of RFA flights says the airline is fictional); decisions appear after the first
decision. In REPLAY a violet "RECORDED" tag leads the line.

A second line (14 px, text-2, wraps) says what the area means, from the area card's mode line:
"Same as the official area: TEPHRA adds nothing." or "Official area plus the observatory's
drift, never smaller." When the area is OFFICIAL and no model accepted a reading, it appends the
outcome text (11.5), so "TEPHRA area = official" never reads as a model endorsing the official
area: with the stub "… TEPHRA adds nothing. NO MODEL: official products only."; likewise "AI
unavailable: …", "No model call needed: …" or "Plume read queued …". HYPOTHESIS keeps its own
single line.

The same two lines are the verdict at every width: at 1359 px and below the rail head carries
them under the volcano name, wrapped in full (line 1 starts "Recorded:" in REPLAY); at phone
width a block above the map carries them (4.4). Below it, map notes (same pill style, 14 px, text-2) when needed:
"No aircraft seen within 150 km of Semeru in the open ADS-B feed. Receiver coverage is patchy
here: an empty map is not an empty sky." · "Level filter FL180–FL550 hides 1 official area and
2 flights" (caution, with a "Reset" link that returns the filter to All) · "No official +12 h
area for Semeru in the current products." (when the forecast step chosen on the timeline has no
official polygon for the selected volcano; with All chosen, only when none of +6, +12 and +18 h
has one; worded from the data, because a VAA saying NOT AVBL, one saying NO VA EXP and a polygon
that did not parse all look the same here; no other step is drawn in its place) · "Basemap
offline: simplified coastline (Natural Earth)".

### 7.7 Tools column

Vertical glass column top-right, five 52 px tiles (icon 20 px over an 11 px label): Frame (F),
3D (D, `aria-pressed`), Compare (S, `aria-pressed`), Satellite (I; label shows "Satellite",
"Infrared", "Visible", "Air mass"), Layers (L). Pressed state: `--c-surface-3` with a 1.5 px
amber inset ring. Every tile has `aria-keyshortcuts` and a tooltip with its key.

Layers panel (popover from the Layers tile, 320 wide, `role="dialog"`): groups with headings:
Hazard (Official ash area · always on, shown checked and disabled with "binding"; Official
forecast steps: Now / +6 h / +12 h / +18 h / All (radio); TEPHRA cautious area; Disagreement
markers), Traffic (Aircraft; Exposure paths; Other aircraft labels), Context (FIR and VAAC lines;
Navaids; Terrain shading), Satellite context (radio Off / Infrared / Visible / Air mass, each with
"context only"; checkbox SO2 "context only · SO2 is not ash. Volcanic gases may also be
undesirable to fly through; TEPHRA does not model them."), Levels (the filter, section 8.4). Changes apply at once;
the choice persists in `localStorage`.

### 7.8 Flights dock

Glass panel bottom-right of the map (440 wide at 1920, left of the tools column, 12 px above the
timeline). Title row: caps "FLIGHTS ENTERING TEPHRA'S AREA" + count. Rows (56 tall), sorted
inside-now first, then minutes ascending: amber plane icon rotated by track · "RFA4821" (18 px
600) · "GIA208 · A320 · FL350" (14 px text-2) · right-aligned "12 MIN" (24 px 600 tephra-text)
or the `st-inside` shape and "INSIDE NOW" · an advisory status line under it (section 3.2 shape +
"HOLD drafted · awaiting dispatcher" / "Approved by AK · 1607Z" / "Rejected by AK · 1608Z").
Activating a row flies to the flight and opens its popup. States: loading (two skeleton rows);
empty (one line: "No flight is projected to enter TEPHRA's area." plus the coverage note when
5.5 applies, or "No aircraft data in this recording." when ADS-B is not OK); replay (rows tagged
"recorded"); stale aircraft (row text dimmed, "position 2 min old"); more than 4 rows (the dock
scrolls, title shows "4 of 7").

Picked flight: clicking an aircraft on the map (or its entry ring) or activating a row picks
that flight. It stays picked until "Clear" or Esc: a white ring on the map (5.3), the row marked
(`aria-current`, a white left edge) and a "Selected" block at the foot of the dock: the RFA
number; "RFA is a fictional airline · stands in for ADS-B GIA208, hex 8A0123"; "Entry (est.)"
("In 12 min", "Inside TEPHRA's area now" or "Not projected to enter TEPHRA's area"); for an
entering flight, "Basis: Code projection from the last position, if track, speed and level are
held"; level (and selected level), speed and track, position age; and the advisory status line.
No clock time is derived from the minutes. When the flight is no longer in the data the block
says so: "Hidden by the level filter FL180–FL550. Reset" or "No current position for this flight
in the aircraft data."

### 7.9 Trace dock

Glass panel bottom-left of the map (600 wide, 132 tall with four lines at 1920; T expands it to
fourteen lines, about 360 tall, over the map). Header: caps "REASONING TRACE", the count ("49
steps"), a toggle "This volcano / All" (default: the selected volcano plus lines with no volcano),
and the hint "T expand". Each line: time (mono 12, text-3), stage (11 px caps, text-2), the actor
chip (3.2: CODE, GEMINI, ADK, NO MODEL, HUMAN, SYSTEM), the message (14 px; one line with an
ellipsis when collapsed, full text in its `title`; wrapped when expanded). `warn` and `error`
lines start with the caution or serious shape. New lines slide in from the bottom (`--dur-3`);
the list keeps the last 200 (contract); it follows the newest line unless the user has scrolled
up, then a "New steps" button appears. `role="log"`, `aria-live="off"`. States: loading (two
skeleton lines), empty ("No steps yet."), stale (dimmed, header "paused at 16:07:12Z").

### 7.10 Volcano tabs (rail)

`role="tablist"`; each tab: eruption symbol in the code colour, the name, then badges: the
count of CAUTION and SERIOUS discrepancies with the worst shape, and the exposed-flight count
with a plane. Sort: exposed count, then worst severity, then discrepancy count, then name. The
first tab is selected on load. Arrow keys move between tabs; Enter selects and frames.
Selecting changes the rail, the headline, the rose and the dimming. Overflow scrolls
horizontally with fade edges. States: empty (no tabs; the rail shows the empty-region state in 7.17), stale (tabs
keep their data, greyed badges).

### 7.11 Volcano head

Name (24 px 600), a code chip (eruption symbol + the code word in caps), "as of 1630Z" (mono,
text-3) on the right; under it `active_reasons` joined with " · " (14 px text-3). In HYPOTHESIS,
the hypothesis banner sits under the head (7.13).

### 7.12 Sources side by side (comparison grid)

Section title caps "WHAT THE SOURCES SAY", aside "Official products are binding". A
`role="table"` grid: a 92 px row-label column, then **SIGMET, VAA, a 1 px divider, VONA** (the
two official products together, the observatory apart; the data order SIGMET, VONA, VAA is only
the order the cards arrive in).

Column head (`--c-surface-2`, 3 px top bar magenta for SIGMET and VAA, sky for VONA, dashed grey
when missing): kind caps "SIGMET · binding", "VAA · VAAC", "VONA · observatory", with a plain second line under
each in 12 px text-3 ("met office warning for the airspace", "ash advisory centre", "volcano
observatory notice"; also on a missing card); title (14 px
600, wraps to two lines; VONA shows "VONA 1629Z"); issued time and age "1120Z · 5 h 10 min ago"
(mono 12); the evidence chip (3.2); for VONA, a day/night line "Night at the vent · 00:01 local
solar" (caution colour at night). A `stale` card adds the `st-stale` chip "Stale: last good copy
14 min old" (from `stale_age_s`).

Rows and the value each column shows (mono 14, 500):

| Row | SIGMET | VAA | VONA |
|---|---|---|---|
| Seen at | the LAG discrepancy's value for this source if present ("OBS 1100Z"), else `display_fields.Observed` | LAG value, else "EST"/"OBS" from `Observation` | LAG value, else the time part of `Issued` |
| Height | `Band` | `Band` | `Cloud top` without the metres in brackets ("14,685 FT AMSL"); full text in the cell's title |
| Movement | the direction discrepancy's value for this source ("MOV SE 10KT"), else `Movement` | same | the direction discrepancy's value ("moving N"), else `Movement` |
| Valid | "until 1720Z" from `valid_to` | "next by 1720Z" from `Next advisory` | — |
| Colour code | — | `Colour code` ("NOT GIVEN") | `Colour code` |

Cells wrap to two lines, then ellipsize with the full value in `title` ("NOT STATED/NOT
IDENTIFIABLE" must stay readable). Footer row: `#sha256_short` (mono 12, text-3) and an
`i-raw-text` button "Raw text" that opens
7.15 at that column. Flagging: a cell whose source is cited by a CAUTION or SERIOUS discrepancy
for the matching aspect (direction or polygon → Movement; top or base → Height; ash_observed →
Seen at; presence → the column head) gets `--c-caution-bg`, a 1.5 px caution inset ring, the
`st-caution` shape and caution text; the VONA movement cell is flagged, the official ones are
not (they agree with each other). Unflagged VONA movement text is `--c-observer-text`.

States: missing card (dashed column: "None in force" head; one cell spanning the rows with
`missing_note` and "Absence is not evidence of no ash."; when `missing_reason` is not
`NONE_SEEN` the head instead reads "Not read", "Not recorded" or "Feed down" in grey with the
`st-off` shape, and the raw-text panel (7.15) uses the same head); loading (skeleton cells); replay (no
change: the times are the recorded ones); stale (card chip as above); hypothesis (SIGMET and VAA
columns are missing or expired; the head says "No valid official product").

### 7.13 Where they disagree; TEPHRA cautious area

**Disagreements.** Caps title "WHERE THEY DISAGREE", aside "2 to check · 2 harmless". CAUTION
and SERIOUS items as cards (`--c-caution-bg` gradient, caution border with a solid 4 px left
edge; serious uses `--c-serious-bg` and the serious colour): left column (132 px) the severity
shape (18 px) and word (14 px bold caps, one step above the INFO rows), and the kind label under it
(section 11.4); right column the plain-English headline (16 px 600), the code `summary` verbatim
(14 px text-2), and for direction items an explainer line built from the values: "Official area
moves **SE**. Observatory reports ash moving **N**. 135° apart." (the two words in their role
colours). A "Show on map" text button frames the vent with the rose. INFO items collapse into
compact rows (14 px headline + the summary in 12 px text-3), and when there are more than two
they collapse into one row "Harmless (3): LAG · ENVELOPE · NOT OBSERVED" that expands. Each card
with evidence NOT_OBSERVED, NOT_IDENTIFIABLE or NIGHT_BLIND adds an INFO row "NOT OBSERVED ·
{kind} could not see the ash. Not evidence of no ash; it never shrinks TEPHRA's area or weakens
an advisory." Empty: "No differences found between the products in force." Loading: two
skeleton rows. New item: inserted with `--dur-3`, highlighted for `--dur-5`, announced politely.

**TEPHRA cautious area card.** Caps title "TEPHRA CAUTIOUS AREA", aside "an estimate, not a
forecast". Card with a 1 px dashed amber border: mode chip (solid amber, ink text: OFFICIAL,
WIDENED, HYPOTHESIS), the band in mono 18 tephra-text, the cone `label` in mono; one sentence by
mode (section 11.2); a facts list: Rule "Never smaller than any valid official polygon"; Read by
"`state.llm.label` · outcome text" (11.5); Valid until; Confidence (WIDENED and HYPOTHESIS only,
"62% in the widening"). With a Gemini assessment, add "How the model read it" (collapsed by
default): each `disagreements_explained` reading with the source it leaned on and why, the
`rationale` and `uncertainty_notes`, all marked "AI-written" with `i-model` and inserted with
`textContent`. HYPOTHESIS adds the banner: `--c-hypothesis-bg`, `st-caution`, "HYPOTHESIS: no
valid official product for Semeru. TEPHRA's area is a hypothesis built from the observatory
report. Advisories are limited to MONITOR or HOLD." States: no cone ("No TEPHRA area yet for
this volcano."), fallback outcome ("Model output rejected by the validators: official products
only" with `st-info`), replay (unchanged), stale (dim).

### 7.14 Decisions list (rail)

Caps title "DECISIONS", aside "Approve on the Desk · nothing is sent anywhere". Newest first,
up to 20: status shape and word (3.2), "RFA4821 · HOLD FL250", actor and time "AK · 1607Z" (from
`decided_by` without the `desk:` prefix, `decided_at`), reject reason in quotes (text-2,
`textContent`), "edited" marker for EDITED. DRAFT items show "Awaiting dispatcher · drafted 2 min
ago". A decision arriving over SSE gets a one-time stamp (scale 0.96→1 and a `--c-ok` or
`--c-serious` left bar fading over `--dur-5`) and a polite announcement "AK approved HOLD FL250
for RFA4821". Empty: "No advisories yet. A draft appears when a flight's projected track enters
TEPHRA's area."

### 7.15 Sources side by side dialog (C)

`<dialog>` 90vw × 80vh, three columns in the grid's order with the full `raw_text` in Plex Mono
14 (pre-wrap), the source id, issued, fetched, `#sha256_short`, a link to the source URL
(`safeExternalUrl`, `rel="noopener noreferrer"`, opens a new tab), and the card's
`extra_source_ids` as a list. Close with Esc or the button; focus returns to the opener.

### 7.16 Feed health dialog

Table: Feed (label from 11.6), Status (shape + word), Age (on the active clock), Last good
(UTC), Records, Note (`last_error` verbatim, `textContent`, wraps). A "recorded" tag for replay
feeds. The worst status sorts first. Refreshed by `feeds` and `state` events.

### 7.17 Global Wall states

| State | Trigger | What shows |
|---|---|---|
| Loading | before `/api/wall` answers | Static HTML already shows the honesty strip text and the wordmark. Map area: basemap as it loads; panels show skeleton bars (no shimmer under reduced motion); the badge says CONNECTING. |
| Error | `/api/wall` fails | Map note (serious): "Can't reach TEPHRA. Retrying in 5 s…" with a "Retry now" button; panels keep skeletons; retry every 5 s. |
| Stream lost | no SSE event (heartbeat included) for 45 s, or `EventSource` error | Caution banner under the command bar: "Live updates lost at 16:07:12Z. Showing the last data received; reconnecting…"; the map gets a 15% dark scrim and a "STALE VIEW" chip next to the clock. On reconnect, re-fetch `/api/wall` and announce "Live updates restored." A 503 `too_many_streams` says "Too many screens are following TEPHRA right now. Retrying in 30 s." |
| Replay | `state.mode == REPLAY` | 7.1 banner, badge, violet clock caption, "recorded" tags, timeline in replay form. |
| Hypothesis | any active volcano's cone mode HYPOTHESIS | Its tab badge `st-caution` "H"; area card banner; headline; map hatch and label. |
| Empty region | no active volcano in the current region | Rail: "No active volcano in Java / Bali." + the definition of active + buttons for regions that have some ("Halmahera · 2 active"). Map stays usable. |
| Basemap failed | style error or not loaded in 8 s | `setStyle` with a minimal style: background `--map-water`, `land_apac.geojson` fill `#15181c`, coast line `#2a3442`; re-add TEPHRA layers without text layers that need glyphs except labels drawn as HTML markers; note "Basemap offline: simplified coastline (Natural Earth)". |

### 7.18 Operator policy panel

A dialog (up to 960 px wide) opened from the footer button or the About dialog (7.3). It
fetches `GET /api/policy` with an 8 s timeout; when the request fails, times out or returns no
policy, the dialog says only "The operator policy could not be loaded." Contents, in order:

- the title line: title, version and label ("ILLUSTRATIVE, not an airline SRA");
- a muted line "Values are illustrative and have not been reviewed by an airline dispatcher.";
- a muted line with the risk owner, the SRA reference ("none (illustrative)") and the first 12
  characters of the content hash;
- the Policy A summary text;
- "Values": a table of name, value with unit, why this value (the source and the refs of its
  citations) and block;
- "Source-trust order (what the code does today)": a muted line "Operator choice. Doc 9974 asks
  the operator to resolve conflicts among its sources (2.4(d)).", then each rule's text with a
  muted "Applied by:" and its `enforced_by`;
- "Citations": each ref, the quoted text and a "Source" link that opens in a new tab.

The Desk review sheet (10.4) shows the policy each draft was made under.

## 8. 3D, compare, the timeline and the level filter

### 8.1 3D mode (D)

`easeTo({ pitch: 60, bearing: -20, duration: --dur-camera-long })`, enable drag-rotate, set sky
(`sky-color #0b1220`, `horizon-color #1b2430`, `fog-color #07090d`, blends 0.6/0.6/0.8). Add, in
this order (extrusions share the depth buffer; inner first): `official-volume` (now-valid
official features, `--c-official`, opacity 0.45, base/height = `base_ft`/`top_ft` × 0.3048 × 6,
vertical gradient off), `tephra-volume` (cone part, `--c-tephra`, 0.14), aircraft lollipops (a
2.5 km box at `alt_baro_ft` ± 300 ft on a thin stem from the ground, amber for exposed, grey
otherwise; stems 0.55, boxes 0.95). No 3D terrain while volumes are shown (it shifts levels). A
legend row "3D view · heights ×6" appears and the headline appends "3D, heights ×6". Exit with D
or Esc: pitch 0, bearing 0, remove the volumes. Decisions are never made in 3D: the Desk is 2D
text. Under reduced motion, `jumpTo`.

### 8.2 Swipe compare (S)

Load `https://unpkg.com/@maplibre/maplibre-gl-compare@0.5.0/dist/maplibre-gl-compare.js` (defer,
after MapLibre) and its CSS. On S: create a second map in a sibling container with the same
style, camera and context layers; it shows official areas, volcanoes and all aircraft in the
normal grey (exposure is TEPHRA's computation). The main map keeps everything. Then
`new maplibregl.Compare(before, after, wrapper, { mousemove: false, orientation: "vertical" })`.
Fixed top labels: left "A · OFFICIAL PRODUCTS ONLY", right "B · WITH TEPHRA'S CAUTIOUS AREA"
(glass pills). The handle: 44 px circle, `--c-text-1` ring, `i-swipe` icon, focusable
(`role="slider"`, `aria-valuenow` = percent): ← / → move it 5%, Home/End to the edges. Remove the
second map on exit (S or Esc); never keep two maps alive.

### 8.3 Replay timeline

A glass bar across the bottom of the map. It never changes TEPHRA's clock (there is no seek API);
the playhead follows `state.now`.

- Left block (210 px): REPLAY: violet "REPLAY" with `i-replay`, the window "23 SEP 1200Z → 27
  SEP 0600Z", a 4 px progress bar (`(now − recorded_from) / (recorded_to − recorded_from)`) and
  "58% through the recording". LIVE: "LIVE" and "Last 9 h and next 3 h".
- Lane labels (92 px): Official · Observatory · TEPHRA.
- Track: the window `[now − 9 h, now + 3 h]`, hour ticks "16Z" (mono 10). Lanes:
  - Official: for the selected volcano's SIGMET and VAA cards, a bar from `valid_from` to
    `valid_to` (magenta at 55%) and an issue marker at `issued_at` (`st-stale` diamond for SIGMET,
    `st-ok` circle for VAA, magenta).
  - Observatory: one marker per VONA: the card's `source_id` (filled) and each
    `extra_source_ids` entry (hollow), times parsed from the id (`…T1540Z`).
  - TEPHRA: a caution triangle at each DISCREPANCY trace event for the volcano; an amber plane
    at each EXPOSURE event; a green check or red cross at each decision (`decided_at`).
  - The lag: when a LAG discrepancy exists, a bracket between the two observation times parsed
    from its values, labelled "lag 5 h 29 min" (from `magnitude`).
- NOW: a 2 px white line with the active time in a dark tag.
- Markers are buttons (roving tabindex; ← / → between markers), 28 px wide and as tall as the
  lane pitch (lane height + 4 px, at most 28 px); activating one selects the matching column or
  item in the rail and frames it; tooltips name the product and time. The chosen marker keeps a
  ring (`aria-current`).
- "‹ Previous" and "Next ›" buttons at the top of the right block step through the markers in
  time order and act as a click on the marker (and announce its title). With no marker chosen,
  Previous goes to the latest marker at or before NOW and Next to the first after it; at either
  end the button is `aria-disabled`. They move the choice, never TEPHRA's clock.
- States: loading (empty axis), LIVE (no progress bar), no events (axis only), stale (dimmed,
  playhead frozen with "last update 16:07Z").
- The official validity bar is `--c-official` at 0.7 opacity (3.3:1 against the panel). Stale
  panels (timeline, trace dock) dim to 0.8 opacity, which keeps text-3 at about 5.1:1 and text-2
  at about 7.1:1; stale volcano-tab badges are greyed and dimmed to 0.8.

Forecast steps control: in the Layers panel and as a small segmented control at the right end
of the timeline: Now · +6 h · +12 h · +18 h · All (`aria-pressed`). Choosing a step shows that
VAA step's polygon and dims the rest; it is a view of the official forecast, not a TEPHRA
forecast.

### 8.4 Flight-level filter

A vertical instrument under the tools column (76 wide): caps "LEVELS", a readout ("All",
"FL180–FL550"), a track up to 270 px tall (the height rule in 4.2) from SFC (bottom) to FL550 (top) with scale ticks SFC, FL060, FL180,
FL350, FL550, each with a visible label left of the track (mono, at least 12 px, text-2; the box
is 44 px wider than the tools column to hold them; FL060's label is left out when the track is
under 150 px), and on the track: the official band of the selected volcano
(magenta bar, left), TEPHRA's band (amber dashed bar, right), and one tick per aircraft at its
`alt_baro_ft` (amber 3 px for exposed, grey 2 px for others; at most 60). This mini profile
answers "who is in the band" at a glance (the 2D twin of 3D).

Two thumbs (40x18 white labels "FL550", "SFC"), each `role="slider"` with
`aria-valuemin/max/now` in feet and `aria-valuetext` "FL180": ↑/↓ 10 FL, PgUp/PgDn 50 FL,
Home/End to the limits; pointer drag; a click on the track moves the nearer thumb. Presets
under it: "All", "Hazard" (the selected cone's base–top), and in the Layers panel also
"≤FL180" and "≥FL180" (Tokyo's split). Effect: official and TEPHRA features whose `[base_ft,
top_ft]` misses the range draw at 15% (never removed); aircraft outside the range are hidden
unless exposed (exposed aircraft are never hidden) or their level is unknown. While the filter is
not "All", the map note "Level filter FL180–FL550 hides 1 official area and 2 flights" shows
(caution colour) with a "Reset" link back to All.

## 9. Keyboard

Single-key shortcuts work when focus is not in a text field and no modifier is held; they can be
switched off in the help dialog (WCAG 2.1.4, stored in `localStorage`). `?` opens the help
dialog (7.3a), which lists all of them after the reading guide and the glossary. Every shortcut
has a visible control too.

| Key | Action |
|---|---|
| `1` `2` `3` | Region presets (in `state.regions` order) |
| `[` / `]` | Previous / next active volcano |
| `F` | Frame the selected volcano (official + TEPHRA area + entering flights) |
| `D` | 3D on/off |
| `S` | Swipe compare on/off |
| `C` | Sources side by side (raw texts) |
| `I` | Satellite context: off → infrared → visible → air mass → off |
| `O` | SO2 context on/off |
| `B` | BTD indicator on/off |
| `L` | Legend and layers |
| `T` | Expand or collapse the trace dock |
| `H` | Focus the level filter |
| `?` | Help: how to read the screen, glossary, shortcuts |
| `Esc` | Close the dialog, popup or popover; collapse the trace; clear the picked flight; leave compare or 3D |

Focus order on the Wall: skip links ("Skip to map", "Skip to situation brief", "Skip to
decisions") → command bar → map → map tools → level filter → trace dock → flights dock →
timeline → rail (tabs, then sections) → honesty strip. Focus is always visible (3.1 focus ring);
on the map canvas the ring is drawn on the container. Dialogs trap focus and return it on close.
The Desk has no single-key shortcuts at all: no key press ever approves or rejects.

## 10. The Desk

Dark only (`color-scheme: dark`, the same tokens). Phone first. Every Desk request sends
`X-Tephra-Desk: 1` (MODULES.md 5.9) and JSON bodies with `Content-Type: application/json`; every
decision sends the `version` the dispatcher saw.

### 10.1 Header (always)

Row 1 (48): "TEPHRA" (700, letter-spaced) + "Desk" (text-3); model chip (7.2, compact); the
connection chip: `st-ok` "Connected" (SSE open; title "Connected to the TEPHRA server (updates
stream in)"; not "Live", which under the REPLAY bar would read as live data), `st-stale`
"Reconnecting" (caution), `st-serious` "Offline" (serious); the account button (initials in a 32 px circle, menu: "Signed in as AK ·
session ends 1830Z", "Display: LIVE" with "Change display…" (10.10), and "Sign out"). Row 2 (REPLAY only, 28): violet bar `i-replay` +
`state.replay.banner`. Row 3: the disclaimer, 12 px semibold text-1, wraps, never truncates.
`state` is read from `GET /api/state` at start and from `state` events; until then the static
HTML disclaimer is shown.

### 10.2 Sign-in

Centred card (max 400): title "Dispatcher sign-in" (24), hint "Your name is recorded on every
decision. The PIN is never stored on this phone." Name field (autocomplete `username`, 2-32
chars) and PIN (`current-password`, numeric keyboard `inputmode="numeric"`), 48 px tall, 16 px
text, labels above, errors under the field (`aria-describedby`), button "Sign in" (primary
neutral: `--c-text-1` fill with ink text, 48 tall, full width). Errors (11.8): bad PIN, too many
attempts (button disabled with a countdown from the `Retry-After` header), desk disabled,
offline. On success: focus moves to the queue title.

### 10.3 Queue

Title "Drafts awaiting decision" (24) with "2 waiting" and "Most urgent first"; a quiet
"Refresh" icon button (also refreshes on every `advisory` event). Sort: inside now first, then
`minutes_to_entry`, then `created_at`. Each card is one `<button>` (whole card tappable, ≥ 44
tall, in practice ~150):

- Row 1: "RFA4821" (24 600) + "GIA208 · A320" (14 text-2); right: "ENTERS IN" caps over
  "12 MIN" (32 600 tephra-text), or the `st-inside` shape and "INSIDE NOW" (tephra-text).
- Row 2: the action (20 600 text-1): "HOLD FL250", "CHANGE LEVEL FL300–FL340", "DIVERT WARR",
  "MONITOR", "CONTINUE" (from the advisory fields, 11.7).
- Row 3 (14 text-2): "Krakatau · TEPHRA area OFFICIAL (NO MODEL) · drafted 2 min ago".
- Row 4 tags: the area chip with a visible "AREA" key ("AREA OFFICIAL 100%", so the percentage
  is not read as certainty), "REPLAY" (violet), "AI-drafted" (`i-model`, when `llm_backend` is
  gemini) or "NO MODEL" (dashed; "Template · NO MODEL" in the review), "HYPOTHESIS" (amber), "Needs a careful read" (caution, when
  `validation_notes` contains NEEDS_HUMAN), "Sources stale" (caution, when any source is stale),
  "Drafted 12 min ago: entry time may have moved" (caution, draft age > 10 min).

States: loading (three skeleton cards), empty ("No drafts waiting." + "A draft appears here when
a flight's projected track enters TEPHRA's cautious area. Last update 16:07:12Z."), error ("Can't
load drafts." + the reason + "Try again"), offline (10.9), replay (tags), a new draft (inserted at
its place, highlighted for `--dur-5`, announced "New draft: RFA4821, HOLD FL250, enters in 12
min").

### 10.4 Review sheet (check answers)

Opens from a card (full screen on phones, the right pane at 1440). Header: back "‹ Drafts",
title "Review RFA4821", "v1" (mono). Body: a summary list (GOV.UK check-answers pattern), label
column 120 px (14 text-3), values 16-18 px. The advisory text comes third, right after the
action, so the words being queued share the screen with the Approve button (16 px mono, line
height 1.5):

| Row | Value |
|---|---|
| Flight | "RFA4821 · proxy for ADS-B GIA208 (hex 8A04C1) · A320" |
| Action | "HOLD at FL250" (24 600) |
| Entry | "Enters TEPHRA's area in 12 min (as drafted at 1607Z)" or "INSIDE NOW" |
| TEPHRA area | "OFFICIAL 100% (NO MODEL)" or "WIDENED 62%"; HYPOTHESIS adds the hypothesis banner |
| Fuel and time | `fuel_line` in mono ("HOLD 20 MIN x 42 KG/MIN = 840 KG") + "simple TEPHRA formula, not airline tables" |
| Advisory text | the final body in a mono block (pre-wrap), with "Edit text" as the row's change link |
| Cost note | `cost_note`; the row is left out when it repeats `fuel_line` |
| Sources | each `sources[]`: feed, source id, "issued 251120Z · fetched 251600Z", `#sha256_short`, "stale" when true; binding (SIGMET) first; a `winds` source line ends with the link "Weather data by Open-Meteo.com" (CC BY 4.0 requires it next to the data) |
| Drafted by | "Gemini 3.5 Flash-Lite · AI-drafted" or "Template · NO MODEL" (from `llm_backend`, `model_id`), and the validator notes if any (caution box for NEEDS_HUMAN) |
| Operator policy | the policy the draft was made under, "RFA-POLICY-A v2026.10.8" in mono, followed by " #" and `policy_hash` only when the draft carries one; fine text "Illustrative values, not an airline SRA; not reviewed by an airline dispatcher". Left out when the draft has no `policy_version`. |
| Header | the code-rendered `header` in a collapsed `<details>` "Advisory header (written by code)" |

Action bar (sticky bottom): primary approve (10.5), then a row with "Edit text" (outline,
`--c-line-input`) and "Reject…" (outline, `--c-reject-text` text and border). Under the primary:
"Hold to approve, or tap for a confirmation step. Queues this text on TEPHRA's own outbound
queue; nothing is sent to an aircraft." (12 text-3) from 1100 px wide; on phones and tablets
only "Hold to approve, or tap to confirm." (the queue sentence is in the confirmation step), and
the action and flight in the approve label never break inside ("FL300–" / "FL340"). At 1440 the
review pane is a column with its own scroll area (`max-height: calc(100dvh − header − 32px)`), its body
scrolls and the action bar stays at the pane's bottom.

### 10.5 Approve: hold to confirm, or tap to confirm

The primary button names the outcome: "Approve HOLD FL250 for RFA4821" (`--c-approve` fill,
`--c-approve-ink`, 56 tall, radius 12, 18 px 600, `i-check`).

- Press and hold (pointer): a fill (`--c-approve-progress`) sweeps left to right over
  `--dur-hold` (1200 ms, linear, kept under reduced motion as essential feedback). At full, the
  label changes to "Release to approve". Releasing inside the button approves (the up-event
  completes it, WCAG 2.5.2). Sliding off or `pointercancel` cancels and resets. Releasing early
  (250-1200 ms) cancels with the hint "Keep holding to approve, or tap for a confirmation step."
- Tap (release under 250 ms), Enter or Space, and any assistive technology click: open the
  inline confirmation in place of the action bar: "Approve HOLD FL250 for RFA4821?" (20 600),
  the queue sentence, and two buttons "Approve now" (approve style) and "Back" (outline). This is
  the single-pointer alternative (2.5.7) and the confirmation step (3.3.4).
- While sending: the button shows a spinner and "Approving…", all decision buttons are
  disabled. Success: the sheet closes, the card leaves the queue (`--dur-3`), a toast (11.8)
  with the audit line, focus moves to the next card (or the empty state).

### 10.6 Edit and approve

Sheet view "Edit RFA4821": textarea (Plex Mono 16, upper case as typed with
`autocapitalize="characters"` and a CSS `text-transform` preview; the value sent is what was
typed), 9 rows, counter "312 / 400" under it (caution at 380, serious and blocked above 400),
`aria-describedby` to the counter; "Show the drafted text" disclosure with the original body; a
note "Both versions are kept in the audit log. The header with sources and times is written by
code and cannot be edited." Primary "Approve edited text for RFA4821" (approve style, the same
hold-or-tap rule), secondary "Cancel". 422 shows `problems` under the field.

### 10.7 Reject

Sheet view "Reject RFA4821": reason textarea (required, 3-500 characters, counter), quick
reasons as chips that insert text and stay editable: "Flight already clear of the area", "Level
already outside the hazard band", "Duplicate of another advisory", "Hazard data look wrong";
note "The reason is recorded in the audit log. A rejected draft is not queued." Primary "Reject
advisory for RFA4821" (`--c-reject` fill, white text, `i-x`; tap only, no hold), secondary
"Cancel".

### 10.8 After a decision; conflict

- Decided stamp: on success the action bar shows, for 1200 ms, `i-approved` (40 px) +
  "Approved" (28 px 700 `--c-approve`; `i-rejected` + "Rejected" in `--c-reject-text`), the action
  and flight, and "AK · 1607Z · queued, not sent to any aircraft" (16 text-2), above a 3 px rule
  in the same colour. It is not interactive; it enters with a short scale-in that reduced motion
  drops (the 1200 ms hold stays). Then the sheet closes and the toast follows.
- Toast (bottom, 6 s, `role="status"`, persists while focused; title 18 px 600; at most 40vh tall
  on phones): approved "Approved: HOLD FL250
  for RFA4821 · queued 1607Z under AK. Not sent to any aircraft."; edited "Approved with your
  edits: RFA4821 · both versions are in the audit log."; rejected "Rejected: RFA4821 · reason
  recorded."
- Audit line: under the toast text, first "AUDIT APPROVED desk:AK 1607Z" from `GET
  /api/audit?advisory_id=…` (newest entry; mono 14 500, `--c-approve` or `--c-reject-text`),
  then the first two `SRC` lines of the advisory header (feed, id, issued, fetched, `#hash`; mono
  12 text-2). This is the video's "audit line with feed times and
  hashes".
- 409 `version_conflict`: the sheet switches to "This advisory changed while you were reviewing
  it." with a two-column diff "You saw (v1)" / "Now (v2)" for Status, Action, Entry and Text
  (changed values highlighted with a caution bar and the word "changed"), using `current` from
  the error body. If `current.status` is DRAFT: "Review the new version" (primary neutral). If
  terminal: "AK approved it at 1607Z" (or "TEPHRA replaced it with a newer draft at 1606Z" for
  SUPERSEDED) and "Back to drafts". The outcome comes before the diff, in a panel with the status
  shape and word; the version chip reads "v1 → v2"; the Now status cell carries the status shape;
  identical text shows once as "Same text".
- 409 `invalid_transition`: "This advisory is no longer a draft." + who/when + "Back to drafts".
- 404: "This advisory no longer exists." + "Back to drafts".

### 10.9 Offline, session, wake lock

- Offline (`navigator.onLine` false, a fetch network error, or SSE down for 10 s): a serious
  banner under the header with `i-offline`: "You're offline. Can't approve right now: reconnect
  to decide. Drafts stay readable." All decision buttons are `aria-disabled="true"` with that
  sentence as their description. Never queue a decision for later. On reconnect: re-fetch the
  queue, banner "Back online." for 3 s.
- Session: 401 on any call → the sign-in view with "Your session has ended. Sign in again to
  decide." and the open draft kept selected after sign-in. Five minutes before
  `expires_at`, a caution toast "Your session ends at 1830Z."
- Wake lock: after sign-in, while the document is visible and at least one draft waits, call
  `navigator.wakeLock.request("screen")`; release when the queue empties; re-acquire on
  `visibilitychange`. Silent if unsupported.

### 10.10 Display mode (operator, account menu)

`POST /api/mode` switches what every screen shows, so it lives in the account menu, never on the
queue: "Display: LIVE" or "Display: REPLAY · {case label}", and a "Change display…" item that
opens a sheet listing "Live feeds" and each case from `GET /api/replays` (label, window
"23 SEP 1200Z → 27 SEP 0600Z", record count). Choosing one asks once: "Switch every screen to
REPLAY of {label}? Viewers see the REPLAY banner. The switch is recorded in the audit log under
your name." with "Switch to replay" / "Cancel" (or "Switch to live feeds"). Errors: 404 "That
recording is not on this server.", 409 "No recording is available." The new `state` event updates
both pages; the Desk shows a toast "Display switched to REPLAY by AK."

## 11. Copy deck

Sentence case in prose; caps only for codes, aviation words and small caps labels. Hyphens in
the disclaimer exactly as `state.disclaimer` gives them.

### 11.1 Honesty labels (exact)

| Where | Text |
|---|---|
| Disclaimer (both pages, always) | `Decision support only - fictional airline - not for operational use` (from `state.disclaimer`; the HTML ships the same text) |
| REPLAY banner (both pages, whole session) | `state.replay.banner`, e.g. "REPLAY: recorded real feeds from 23 Sep 2026" |
| Model label (both pages, always) | `state.llm.label`: "NO MODEL" for the stub, else the model id |
| AI marking | "AI-drafted" (advisory body), "AI-written" (plume reading); stub: "Template · NO MODEL" |
| Every satellite layer | "CONTEXT ONLY · {layer} {time} · not ash detection · Imagery: NASA GIBS · Himawari-9 data: JMA via NOAA" |
| SO2 layer | "CONTEXT ONLY · SO2 (TROPOMI, daily) {date} · SO2 is not ash; gases not modelled · Imagery: NASA GIBS · Contains modified Copernicus Sentinel data 2026" |
| BTD overlay | "Split-window BTD (computed by TEPHRA) · an indicator, not ash detection" |
| Airline | "Ring of Fire Air (RFA) is a fictional airline. RFA flight numbers are proxies for real aircraft." |
| Outbound | "Approved text goes only to TEPHRA's own outbound queue. Nothing is sent to an aircraft or any real system." |
| TEPHRA's area | "TEPHRA cautious area" · "an estimate, not a forecast" · "never smaller than the official area" |

### 11.2 Mode words

| Mode | Short | Sentence |
|---|---|---|
| LIVE | LIVE | "Live feeds" |
| REPLAY | REPLAY | the banner; "recorded" on tags |
| OFFICIAL (cone) | "TEPHRA area = official" | "Same as the official area: TEPHRA adds nothing." |
| WIDENED | "TEPHRA area widened" | "Official area plus the observatory's drift, never smaller." |
| HYPOTHESIS | "HYPOTHESIS: MONITOR or HOLD only" | "No valid official product: a hypothesis. Only MONITOR or HOLD may be advised." |

### 11.3 Evidence states

| State | Chip | Long form (tooltip, popup) |
|---|---|---|
| OBSERVED_SAT | Ash seen by satellite | The product reports ash identified in satellite data. |
| OBSERVED_GROUND | Ash seen from the ground | A ground observer reported ash. |
| ESTIMATED | Position estimated | The VAAC estimated the ash position. |
| NOT_IDENTIFIABLE | Not identifiable | Ash could not be identified (cloud or night). Not evidence of no ash. |
| NOT_OBSERVED | Not observed | The observer did not see ash. Not evidence of no ash. |
| NIGHT_BLIND | Night: observer blind | Night-time: the observer cannot see ash. Not evidence of no ash. |
| NO_VA_EXPECTED | No ash expected | The VAAC says no ash is expected. |
| FORECAST_NOT_AVAILABLE | No forecast | The VAAC gave no forecast. |
| STALE | Older than 6 h | This report describes an earlier puff. |
| UNKNOWN | Unknown | The product does not say. |

### 11.4 Discrepancy kinds: label, headline, explanation

| Kind / aspect | Kind label | Headline | Explanation line |
|---|---|---|---|
| DIRECTION_MISMATCH / direction | DIRECTION | The sources send the ash different ways | "Official area moves {SE}. Observatory reports ash moving {N}. {135}° apart." |
| DIRECTION_MISMATCH / polygon | DIRECTION OUTSIDE | The observatory's drift leaves the official area | "A point 15 km along the observatory's drift is outside the official polygon." + WIDENED: "TEPHRA's area covers it." / OFFICIAL: "TEPHRA has not widened the area (NO MODEL)." |
| LAG | LAG | One source is older than the other | "Usual: official products are reissued every few hours, so they trail the observatory." |
| ENVELOPE | ENVELOPE | The observed height sits inside the official band | "Harmless: the heights agree within the official band." |
| HEIGHT_MISMATCH | HEIGHT | The sources report different heights | "One source puts the ash outside the official band." |
| SILENCE | SILENCE | No VAA answers a reported eruption | "Ash was reported and no VAA has followed. Silence is not evidence of no ash." |
| CONFLICT | CONFLICT | A VAA says no ash while another source saw it | "A no-ash VAA was in force when another product observed ash after it." |

Severity words: INFO, CAUTION, SERIOUS (the backend's WARNING is shown as SERIOUS so nothing on
screen reads as a TEPHRA warning). The code `summary` is always shown verbatim under the
headline.

### 11.5 TEPHRA area outcome text

| `assessment.outcome` | Text |
|---|---|
| STUB | "NO MODEL: official products only" |
| ACCEPTED | "Gemini reading accepted by the validators" |
| REPAIRED | "Accepted after one repair" |
| MODEL_FAILED | "AI unavailable: official products only, nothing assessed beyond them" |
| OFFICIAL_ONLY | "No model call needed: official products only" |
| PENDING | "Plume read queued for the Duty Officer: official products only until it runs" |

### 11.6 Feed names and status wording

Names: sigmet "VA SIGMET (AWC)", vona "VONA (MAGMA)", vaac_tokyo "VAA Tokyo", vaac_darwin "VAA
Darwin", taf "TAF", metar "METAR", adsb "ADS-B (adsb.lol)", winds "Winds (Open-Meteo)", frames
"Satellite frames", hsd "Himawari split window". Status lines: OK "OK · updated 27 s ago"; STALE
"Stale · last good 14 min ago · showing the last good copy"; ERROR "Error · last good 2 h ago"
(or "never") + the error; DISABLED "Off" + the reason verbatim (the VONA feed's status word is
"Off: no PVMBG permission (replay only)", so it is not read as the operator policy); NEVER "Not
polled yet". Replay: add the tag "recorded".

### 11.7 Action words (Desk and Wall)

From the advisory: CHANGE_LEVEL "CHANGE LEVEL FL300–FL340" (from `change_level_fl_min/max`), HOLD
"HOLD FL250" (`hold_fl`), DIVERT "DIVERT WARR" (`alternate_icao`), MONITOR "MONITOR", CONTINUE
"CONTINUE". Buttons: "Approve {action} for {proxy}", "Approve edited text for {proxy}", "Reject
advisory for {proxy}", "Edit text", "Reject…", "Approve now", "Back", "Back to drafts", "Review
the new version", "Sign in", "Sign out", "Try again", "Refresh".

### 11.8 Desk messages

| Situation | Text |
|---|---|
| Bad PIN (401 `bad_pin`) | "That PIN is not right. Check it and try again." |
| Too many attempts (429) | "Too many attempts. Wait 10 minutes and try again." |
| Desk disabled (503) | "The Desk is switched off on this server (no Desk PIN is set)." |
| Name invalid (422) | "Use 2 to 32 letters, digits, spaces or . ' - _" |
| Session ended (401) | "Your session has ended. Sign in again to decide." |
| Offline | "You're offline. Can't approve right now: reconnect to decide. Drafts stay readable." |
| Conflict (409) | "This advisory changed while you were reviewing it." |
| Not a draft | "This advisory is no longer a draft." |
| Gone (404) | "This advisory no longer exists." |
| Edit invalid (422) | "Check the text: {problems}" |
| Reject reason short | "Give a reason of at least 3 characters." |
| Approved | "Approved: {action} for {proxy} · queued {HHMM}Z under {name}. Not sent to any aircraft." |
| Edited | "Approved with your edits: {proxy} · both versions are in the audit log." |
| Rejected | "Rejected: {proxy} · reason recorded." |
| Empty queue | "No drafts waiting." / "A draft appears here when a flight's projected track enters TEPHRA's cautious area." |

### 11.9 Never on screen

"Forecast", "warning", "alert" or "dispatch release" for TEPHRA output; "detected", "detection"
or "sees ash" for any satellite, SO2 or BTD layer; "Gemini found the ash"; "no traffic" for an
empty ADS-B map; "the observatory was right" or "the official area was wrong"; "sent to the
aircraft"; any staff name from MAGMA pages; anything implying NASA, NOAA, JMA, BoM, USGS, PVMBG
or DGCA endorse TEPHRA.

## 12. Accessibility

- Contrast: section 3.3 (text ≥ 4.5:1, graphics and control borders ≥ 3:1, focus ring ≥ 3:1
  against both neighbours via the dark halo).
- Colour never alone: section 1 principle 3 and the tables in 3.2 and 5.
- Keyboard: every function reachable without a pointer (section 9); no keyboard trap; visible
  focus everywhere; dialogs trap and restore focus; `aria-keyshortcuts` on controls.
- Semantics: landmarks (`header`, `main`, `aside`, `footer`, `nav` for regions), `h1` per page
  (the Wall's is the volcano name, the Desk's the queue or sheet title), tables for the grid and
  feed health, `role="tablist"` for volcano tabs, `role="log"` with `aria-live="off"` for the
  trace, one polite live region for announcements (new draft, decision, stream lost/restored,
  new disagreement). Never announce every trace line.
- Map: features are also reachable as lists (rail, flights dock, timeline); popups open on
  click or Enter, never on hover only.
- Motion: section 3.5; no flashing; nothing loops except the exposure paths (static under
  reduced motion).
- Targets: 44 px minimum on the Desk and for every Wall control; 48 for Desk primaries.
- Text: resizable to 200% on the Desk without loss (cards reflow; the action bar stays); the Wall
  is a fixed-viewport display and must stay usable at 1280x720.
- Forced colours: icons use `currentColor`; borders exist on every control so they survive
  `forced-colors: active`. `wall.css` ends with a `forced-colors: active` block: selected
  segments, region buttons, tools, tabs and phone tabs use `SelectedItem` / `SelectedItemText`
  (their normal fill and inset ring are dropped in that mode); borderless controls and chips get a
  `CanvasText` border; flagged grid cells, the selected extension card and the Duty Officer card
  get an outline in place of their inset shadow; the focus ring uses `Highlight`; and the data
  swatches (legend, colour-code symbols, level bands, timeline marks and bars, meters) keep their
  own colours (`forced-color-adjust: none`) so the key still matches the map canvas, which the
  mode does not recolour. Each of those swatches also has its shape.

## 13. Data rules (what the UI computes)

All inputs are MODULES.md section 8 shapes. Nothing below calls a model or invents a value.

| Value | Rule |
|---|---|
| Active clock | `state.now` (and heartbeat `now`); tick locally from `performance.now()` between events; never the browser clock for anything shown |
| Valid now | `valid_from ≤ now ≤ valid_to` |
| Step | from `layer` (5.1) |
| Forecast step time | `valid_from + 3 h` |
| Countdown | `valid_to − now`, "1 h 13 min", refreshed every 15 s |
| Ages | `now − issued_at` / `observed_at` / `created_at`; "27 s", "14 min", "2 h 5 min" |
| Aircraft stale | `now − observed_at > 60 s` |
| Inside now | `exposed && minutes_to_entry == 0` |
| Night at the vent | local solar hour `(UTC h + UTC min/60 + lon/15) mod 24` < 6 or ≥ 18 |
| Direction bearings | compass regex on `discrepancy.values` (section 6) |
| VONA times | from the id suffix `YYYYMMDDTHHMMZ` |
| FIR with a SIGMET | the second field of `SIGMET:<FIR>:<series>:<time>` |
| Region of a volcano | its point inside `region.bbox` |
| Priority of volcanoes | exposed count, worst severity, discrepancy count, name |
| Flight ↔ advisory | `advisory.flight_id == "<hex>:<volcano_id>"`; aircraft props carry `hex` and `volcano_id` |
| Official area label | grouped per volcano (5.1); SIGMET and VAA polygons are compared by the backend, not the client |
| Official fill | latest valid SIGMET per FIR and volcano; VAA OBS only where no SIGMET is valid (5.1) |
| Label stack | official box at the arrow tip / centroid / northern vertex; TEPHRA box stacked 3.1 em beyond it (5.1, 5.2) |
| GIBS time | section 5.6 |

## 14. Video shot list

The storyboard is `docs/PITCH.md` (rows as of 10 Oct). Record the Wall at 1920x1080, browser
zoom 100%, `prefers-reduced-motion` off, after `body[data-map-ready="true"]`. Every replay shot
shows the REPLAY banner; the disclaimer strip is in every frame. Captions that are not TEPHRA
data (news stills, the sounding) are added in the edit, not drawn by the UI.

| PITCH row | UI state needed | How to get it |
|---|---|---|
| 0:00–0:15 hook (stills) | none | edit only |
| 0:15–0:30 Wall over Java: SIGMET box; SIGMET, VONA, VAA side by side | Semeru selected, OFFICIAL area box visible, sources grid fully visible, legend open, no satellite layer | Replay `semeru-20260923`, `TEPHRA_REPLAY_START=2026-09-25T16:00:00Z`, stub LLM; region 1 (the 1554Z VONA is already in) |
| 0:30–0:55 badges LAG, ENVELOPE, NOT OBSERVED, DIRECTION OUTSIDE; VONA "north, ground observer, night"; SIGMET "MOV SE" | Rose visible ("135° apart"); VONA column head with "Night at the vent"; disagreement list with CAUTION cards and the harmless row expanded; headline pill | Same replay. NOT OBSERVED appears only if a VONA in the window carries a non-observation; if none, the line says LAG and ENVELOPE and the voice-over must not name NOT OBSERVED |
| 0:55–1:20 trace streams; Plume Reader's card; cautious area over the official box covering both directions | Trace dock expanded (T); TEPHRA area card with "How the model read it" open; map in WIDENED mode with the hatch over the north drift | Needs a Gemini-backed run (`TEPHRA_LLM=gemini`, key in env) so the cone is WIDENED. With the stub the cone stays OFFICIAL and the shot shows "TEPHRA area = official"; do not fake it. The sounding caption is an edit overlay. Optional beat: S (compare) dragged from A to B |
| 1:20–1:50 Jakarta and Krakatau: CGK traffic through the band; two flights turn amber; drafts appear | Region Java / Bali framed on Krakatau; aircraft layer; level filter showing ticks crossing the band (H, preset "Hazard"); flights dock with minutes; Decisions list showing DRAFT; optional D (3D) for 5 s | Live by day if a Krakatau SIGMET is open, else replay `java-live-20261010` (labelled) |
| 1:50–2:15 phone: approve one, reject one; audit line | Desk at 390x844: queue with two cards; hold-to-approve on one (show the fill), reject the other with a quick reason; toast with the audit line; then the Wall's Decisions list and flights dock showing "Approved by …" and "Rejected by …" | Same run as the previous row; sign in with a dispatcher name (not a real person's) |
| 2:15–2:30 evaluation slide | none | deck |

Credits that must be legible when their source is on screen are in the honesty strip and the
context label (section 7.3, 5.6).

## 15. Open issues and notes for builders

- The CSP (MODULES.md 8.1 and `server.py`) allows GIBS and Mapterhorn for images and fetches,
  and scripts only from the two pinned unpkg packages; any other script host is refused.
- MODULES.md 5.9 says "Right rail: the three source cards side by side"; this spec keeps them side
  by side as one comparison grid (SIGMET, VAA | VONA). The data contract is unchanged.
- In the `semeru-20260923` replay the ADS-B feed reports ERROR ("not recorded in replay case")
  instead of DISABLED; the feeds chip will show "1 error" until the backend reports it as off.
- The stub plume reader always returns OFFICIAL, so WIDENED and HYPOTHESIS can only be shown with
  Gemini (or a future code-only cautious union). Build and test those states with the
  `?demo=widened` and `?demo=hypothesis` technique in the reference implementation (stamped
  "illustrative"), never in the product.
- `GET /api/replays` and `POST /api/mode` are in the contract (8.2, 8.5); the Desk uses them only
  in the account menu (10.10). The Wall never switches modes.
- Static `.geojson` files are served as `application/octet-stream`; MapLibre parses them fine.
- In the `java-live-20261010` replay the two exposed flights are inside Kanlaon's area (Philippines)
  at 06:20Z, and Kanlaon's TEPHRA band reads SFC–FL600 because the VAA top is "NOT STATED"; the
  Wall shows what the data say. The Krakatau traffic beat needs the replay at a time when CGK
  traffic crosses the SFC/FL060 band; find it by scrubbing `TEPHRA_REPLAY_START` before recording.
- MapLibre's `map.loadImage` cannot load data: or SVG under this CSP (research): every map image
  here (SDF plane, SDF arrowhead, eruption symbols, label boxes, hatch) is drawn on a canvas and
  added with `addImage`.
