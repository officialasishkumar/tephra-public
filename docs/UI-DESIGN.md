# TEPHRA UI design spec: the Wall and the Desk

Version 3, 12 Oct 2026. Owner: lead product designer. Builders implement this document;
reviewers check the result against it. Where this spec and the code disagree, the spec wins until
it is changed here. Version 3 records the redesign ("The Story") of the Wall and the Desk: its
source and full rationale is `docs/UI-REDESIGN.md`, and the sections below describe both pages as
built from it (the Desk in 4.5-4.7 and 10.1-10.14). Version 3.1 (12 Oct 2026) adds crew (pilot)
reports of ash: the map layer (5.7), the story lines (7.6), Details › Crew reports of ash (7.20),
the flag in This flight (7.8) and, on the Desk, the "Report ash from a crew" form, the line on
affected drafts and the reason box (10.15). The backend is MODULES.md 5.19.

What this covers: the Wall (`/`, `index.html` + `wall.js` + `wall/*.js` + `wall.css`) and the Desk
(`/desk`, `desk.html` + `desk.js` + `desk.css`). Shared assets that already exist and must be
used as they are:

| Asset | Path | Notes |
|---|---|---|
| Design tokens and fonts | `tephra/web/tokens.css` | Link it before the page's own CSS. Every colour, size, space, radius, shadow and duration below is a custom property there. |
| Fonts | `tephra/web/fonts/` | IBM Plex Sans (variable, 400-700) and IBM Plex Mono (400, 500); latin and latin-ext; `OFL.txt`. |
| Icons | `tephra/web/icons.svg` | One sprite (the redesign added `i-more`, the ⋯ menu), referenced as `<svg class="icon" aria-hidden="true"><use href="/static/icons.svg#i-check"></use></svg>`. Colour comes from CSS `color`. |
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
symbology (5.7 Crew report caution areas) · 6 Direction-mismatch rose · 7 Wall components (7.19
Details drawer, 7.20 Crew reports of ash) · 8 3D, compare, time bar, height filter · 9 Keyboard ·
10 Desk (10.11 Ask, 10.12 Airports, 10.13 Paperwork, 10.14 Deep link, 10.15 Crew reports) · 11
Copy deck · 12 Accessibility · 13 Data rules · 14 Video shot list · 15 Open issues.

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
4. **Honest by construction.** The disclaimer, the REPLAY banner and the model label are layout,
   not decoration: they are always on screen and never collapse, scroll away or truncate. Credits
   are always reachable (the footer's "Map and data credits", About › Credits, the drawer's end),
   and the OpenStreetMap credit is always visible on the map. TEPHRA's output is "cautious area", "estimate", "hypothesis", "advisory draft";
   never "forecast", "warning", "detection" or "release". Satellite and SO2 layers say "context
   only" on screen.
5. **Official stays on top of meaning.** The official area cannot be switched off on the main
   map (it is binding); TEPHRA's outline is drawn just outside it so the eye reads "contains".
   Anything that hides an official polygon (the level filter) says so in a chip while it does.
6. **Calm.** Dark, matte surfaces; hairlines; one accent per element; no gradients except the
   map vignette; motion only when something changes (a new flight, a decision), three pulses at
   most, nothing loops except the slow march of exposure paths, and none of it under
   `prefers-reduced-motion`.
7. **Readable at two metres and in a 1080p video.** At 1920x1080 the story lines are 28 px, body
   text 16 px, map labels 12-16 px with a 2 px halo, nothing below 12 px, map canvas labels
   included.
8. **Text comes from the data.** Feed and model text is inserted with `textContent` only. Code
   may compose labels from fields (section 13); it never invents a time, a number or a place.
9. **A human decides, visibly.** The Desk names the outcome on every button, asks once (hold or
   tap-and-confirm), never queues a decision offline, and shows the audit line after.
10. **One primary thing per screen.** The Wall's is the story and its one filled button, "Decide on
   the Desk →"; each Details section opens on its summary.
11. **Summary first, detail on demand; nothing deleted.** Everything the Wall showed before the
   redesign is still reachable, at most two taps away, behind a "Show all", "Technical detail" or a
   Details row with its live status (UI-REDESIGN R11 is the inventory; `tests/test_ui_inventory.py`
   keeps it true).
12. **Nothing floats over the map except map controls, status pills and labels.**

## 2. The story in one glance

| Beat | Carried by (Wall) | Where | Must read at 2 m |
|---|---|---|---|
| Official ash area | Story L1 "Official reports put the ash up to 50,000 ft (FL500)."; the pink filled polygon with its label box "Official ash area · SFC–FL500 · until 1045Z / moving SE at 10 kt" | Story, map | The sentence and the pink shape |
| Where sources disagree | Story L2 "The sources disagree on where the ash is heading (135° apart)."; the direction rose at the vent; Details › Where the sources disagree | Story, map | The sentence and the two arrows |
| TEPHRA's area | The amber dashed outline drawn just outside the official edge with its tag "TEPHRA's estimate · same as official (AI off)"; the key row "TEPHRA's estimate · never smaller than official" | Map, key | The amber dashes around the pink |
| Who is flying into it | Story L4 "23 flights of RFA, our fictional airline, are in or heading into TEPHRA's estimated ash area."; amber planes with marching paths, one-line labels or a "23 RFA flights" cluster ("20 RFA flights here" when some planes sit outside it) | Story, map | The number and the amber planes |
| A human deciding | Story L5 "23 advisories wait for a dispatcher." (plus a small note "n of them are for flights no longer seen heading in." when drafts outnumber the flights) and the one filled button "Decide on the Desk →"; Details › Decisions | Story, Desk | The button |

A still frame of the story column explains itself (UI-REDESIGN R5): `ANAK KRAKATAU · JAVA / BALI ·
ALERT RED · as of 1030Z` / `Recorded Official reports put the ash up to 50,000 ft (FL500).` / `Ash
closes 2 RFA airports: WIHH, WIII.` / `23 flights of RFA, our fictional airline, are in or heading
into TEPHRA's estimated ash area.` / `23 advisories wait for a dispatcher.` /
`[Decide on the Desk →]`.

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
| `--c-surface-1` | `#0a1017` | Top bar, story column, Details drawer, footer, time bar, Desk header |
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
| `--c-crew` | `#e8dcc6` warm ivory | Crew report caution area (operator policy A, not an official product): its long-dashed outline, pin, label box, the ring on a flagged plane, the Desk's crew box | `--c-crew-text` `#f2e9d8`; `--c-crew-soft` for the Desk and Wall flag boxes |
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

Redesign pairs (R13.2, WCAG ratios): `--c-cta-ink` on `--c-cta` (the "Decide on the Desk" button)
17.6:1; story text `--c-text-1` on `--c-surface-1` 16.8:1 and `--c-text-2` 10.6:1; map pills
(`--c-text-1` on `--c-surface-glass` composited over land `#0c0c0c` 16.8:1, water 16.6:1, a pink
official fill 15.1:1, even pure white 12.2:1); the failure line's text on `--c-serious-bg` 15.5:1 and
its `--c-serious` edge 7.0:1 against that fill; the Details index's serious status `--c-serious` on
`--c-surface-1` 7.5:1; amber index status `--c-tephra-text` on `--c-surface-1` 12.4:1.

Crew colour (5.7): `--c-crew` is far lighter than the official magenta, TEPHRA's amber and the
observatory's sky blue, so it separates from them by lightness in every vision type; it is
always drawn with a second channel too (long dashes [4,3] and the pin, never a fill alone).
The palette script has not been run on it yet (15).

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
| `--fs-4` | 18 px | Dialog leads, area band | Entry time |
| `--fs-5` | 20 px | — | Card action |
| `--fs-6` | 24 px | Volcano name, KPIs, wordmark | Flight number, sheet title |
| `--fs-7` | 32 px | Clock | Minutes to entry |
| `--fs-8` | 40 px | (one hero number per screen at most) | — |

Story lines (the Wall's largest text): 28 px at 1600 px and up, 24 at 1360-1599, 22 at 601-1359,
20 on a phone (`--story-size` in `wall.css`; `--fs-story` 24 px and `--lh-story` 1.25 in
`tokens.css`), semibold for the flight-count line, medium for the others. Drawer section titles
`--fs-5`, drawer body `--fs-3`, key rows, trust line and Details rows `--fs-2` (`--fs-3` at 1920),
eyebrow and drawer group headers `--fs-1` caps. Map canvas labels are at least 12 px.

Weights 400/500/600/700. Line heights `--lh-tight` 1.15 (numbers), `--lh-snug` 1.3 (UI),
`--lh-body` 1.5 (paragraphs, advisory text). Root size: the Wall sets `html { font-size: 16px }`
at 1600 px wide and up, 15 px from 1360 to 1599, 14 px below 1360, and 16 px again at 600 px and
below; the Desk keeps 16 px and respects browser zoom. Type floor: `--fs-1` is
`max(12px, 0.75rem)`, because 0.75rem alone is 11.25 px at the 15 px root and 10.5 px at the
14 px root. `wall.css` has no literal size under 12 px, and every map `text-size` (`map.js`,
`ext-map.js`) is at least 12; `tests/test_ui_inventory.py` checks both.

### 3.5 Space, radii, elevation, stacking, motion

- Space: 4 px grid, `--sp-1` 4 … `--sp-16` 64 (rem, so the Wall scales with its root size).
- Radii: `--radius-xs` 2, `-sm` 4 (chips, inputs), `-md` 8 (buttons, cards), `-lg` 12 (floating
  map panels, sheets on desktop), `-xl` 16 (phone sheets), `-pill`.
- Elevation: e0 flat surfaces; e1 `--shadow-1` (story, drawer, bars); e2 `--shadow-2` + glass (map
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
  border and shadow over `--dur-2` on hover; on press they take a `--c-line-1` fill within `--dur-1`, plus a 0.97
  scale only when motion is allowed. Every duration in `wall.css` is a token (the old
  `--dur-quick` fallback, which ignored reduced motion, is gone).
- Redesign motion: the Details drawer's column slides open over `--dur-4` with `--ease-enter` (a
  cut under reduced motion); a changed flight count in the story gets a `--dur-5` highlight (none
  under reduced motion).
- Tap targets: `--tap-min` 44 px (contract), `--tap-comfort` 48 px (Desk primary actions and the
  Wall's "Decide on the Desk").

## 4. Layout grids

Dimensions are CSS px at the named viewport. The Wall's layout tokens (`--band-h`, `--bar-h`,
`--story-w`, `--drawer-w`, `--time-h`, `--foot-h`, `--story-size`) are set per width on `:root` in
`wall.css` (UI-REDESIGN R4).

### 4.1 Wall at 1920x1080 (the video frame)

```
y 0    ┌─ REPLAY band 32 (REPLAY only): "REPLAY: recorded real feeds from 05 Sep 2026 · not live · {case}" ─┐
y 32   ├─ top bar 56: TEPHRA · sub-line · Replay · Area ▾ ……… AI chip · Data chip · clock · Desk → ────────┤
y 88   ├─ story 460 ─────────────┬─ map 1460 (980 with Details open) ─────────────┬─ Details 480 (open) ─┤
       │ failure line (if any)   │ official label box (selected volcano)          │ (pushes the map;     │
       │ eyebrow · story lines   │ pink area, amber dashed estimate, amber planes │  the story stays)    │
       │ trust line              │ name-only labels for other volcanoes           │                      │
       │ [Decide on the Desk →]  │ pills bottom-left        Fit · Layers · ± ·  © │                      │
       │ key (two columns)       ├─ time bar 52: mode · scrubber · Forecast · ‹ › · History ───────────────┤
       │ All volcanoes + 3 rows  │                                                │                      │
       │ [☰ Details]             │                                                │                      │
y 1048 ├─ footer 32: disclaimer · RFA line · credits · Policy A · Help · About · Privacy ──────────────────┤
```

- Rows: band 32 (0 in LIVE), bar 56, stage `1fr`, footer 32. Stage columns: story 460, map
  `minmax(0, 1fr)`, drawer 0 or 480 (animated over `--dur-4`, a cut under reduced motion). The map
  column is the map plus the 52 px time bar. A 24 px fade runs from the story column into the map.
- The story never scrolls at desktop widths in the Krakatau case: a fit pass (`fitStory()` in
  `wall/story.js`, review 2 item 4) raises `#story[data-fit]` from 0 to 8 until the content fits,
  each step tightening, never removing: 1 tighter rhythm; 2 lines 2 px smaller; 3 the key in two
  columns (its "binding" and "never smaller" stay); 4 lines 4 px smaller; 5 "Show the n flights"
  beside the button; 6 the other-volcanoes rows fold into "+ n more" (rows are given back while
  they still fit); 7 the Details button on one line (its sub-line stays in its tooltip); 8 the
  tightest rhythm. It re-runs when the story's words, the window size or the fonts change. Only if
  level 8 still overflows does the column scroll (`.story--scrolls`, with the fade above the
  pinned button). Measured in REPLAY: 1920 level 1–2, 1440 level 5–6, 1280x720 level 8, all with
  no scroll; LIVE: 1920 and 1440 level 0–3, 1280 level 8.
- Framing pads 48 px (7.4), max zoom 8.6.

### 4.2 Wall at 1440x900

Root 15 px. The same structure: story 400, map about 1040 x 732, story lines 24 px, the brand
sub-line hidden, the zoom buttons hidden (wheel, pinch and keys still zoom), the footer's airline line
in full. Details takes the story column's place at 480 px (the map shrinks to about 960 px and is
never covered), with the story strip on top and the key pinned at the bottom. The other-volcanoes
list shows 2 rows (fewer if the fit pass needs the room). The time bar (48) keeps every control; in a
map column under 1080 px it drops the "Forecast:" word but keeps "‹ Previous" and "Next ›" in words
(R4.2, R7.1); under 960 px (1280, or Details open) they become 44 px icon buttons with labels and
tooltips.

### 4.3 Wall at 1280x720

Root 14 px. Band 28 (case label hidden; still in the tooltip, About and Data feeds), bar 48 (AI chip
"AI: off", Data chip short form "Data: 6 ok · 5 off", clock sub-line "Replay · UTC"), story 360, lines
22 px, map about 920 x 600, time bar 44, footer 28 ("RFA is a fictional airline."). Map controls are
icon-only. Details takes the left column at 440 px (map about 840 px), with the sources as cards. The
other-volcanoes list shows 1 row.

### 4.4 Wall at 390x844 (phone)

One column that scrolls; the document is exactly 390 px wide (`overflow-x: clip` after the causes
were fixed). Sticky (about 120 px, 14% of the screen): the REPLAY band on one line ("REPLAY: recorded
05 Sep 2026 · not live", `#replay-banner-short`; the full words stay in its title), then the header
in two rows: brand, mode pill, clock, "Desk →"; the disclaimer line (12 px). Under it, not sticky,
`#phone-bar`: the native area picker ("Java / Bali · 2"), the AI chip and the Data chip (wall.js
moves these three nodes there on a phone and back at wider widths). Then: the failure line, the story card (20 px lines, full-width "Decide on
the Desk →"), the map (42vh, min 300; Fit and Layers 40 px with words; the time pill "⟲ 1030Z · Now
▾" bottom-left opens the full time bar as a bottom sheet), the key strip, the trust line, All
volcanoes with every row, "☰ Details" (a full-screen sheet below the header, with "‹ Details" and
Close), then the footer. A sticky bottom call to action "Decide on the Desk (23) →" (or "Open the
Desk" at secondary weight) shows only while the story's own button is out of view
(IntersectionObserver); the page has `padding-bottom: calc(56px + env(safe-area-inset-bottom))`.
Compare is not offered; 3D is in Map layers. The old phone tabs (`#ptabs`) are gone: their content
is in Details.

### 4.5 Desk at 390x844 (primary)

```
┌ sticky header ─────────────────────────────────┐
│ TEPHRA  [AI: off] [AI 0/450] ● Connected  (AK) │ 48
│ REPLAY: recorded real feeds from 05 Sep 2026   │ 28 (REPLAY only)
│ Decision support only - fictional airline -    │
│ not for operational use                        │ 32
├────────────────────────────────────────────────┤
│ Decide                                     ⋯   │
│ [problems to acknowledge, red, when any]       │
│ ┌ NEXT DECISION ─────────────────────────────┐ │
│ │ 1 of 23 advisories · most urgent first     │ │
│ │ 23 advisories · 3 messages · 2 problems    │ │ (only when it adds to the line above)
│ │ RFA1225               (◉ Inside the ash now)│ │
│ │ proxy for GIA616 · A320                    │ │
│ │ 👁 Keep watching (MONITOR)                  │ │ 20 600
│ │ Anak Krakatau · ash SFC–FL500 · drafted 4 m│ │
│ │ RFA1225 ANAK KRAKATAU VA HAZARD …  (3 lines)│ │ mono
│ │ {} Written by a code template (AI off). …  │ │
│ │ 7 sources · newest 3 min ago               │ │
│ │ [ Review RFA1225 › ]                       │ │ neutral filled, 48
│ └────────────────────────────────────────────┘ │
│ 22 more waiting                                │
│ RFA1530   inside now                      ⚠ ›  │ 52, two lines
│           Keep watching                        │
│ …                                              │
│ ⇄ Airport plan waiting: 3 airports closed, … › │ one-line links
│ ✉ Messages to approve (3) ›                    │
│ ▤ Notices (4) ›                                │
│ ◎ Duty Officer (AI off): 3 flights need a …  › │
│ › Decided while this page was open (2)         │ collapsed
├────────────────────────────────────────────────┤
│  Decide(28)    Ask    Airports(1)  Paperwork(1)│ 56, bottom tab bar
└────────────────────────────────────────────────┘
```

- Gutters 16. Max content width 600 (centred above 632 px). Header sticky, `--c-surface-1`,
  bottom hairline. On a phone the model chip reads "AI: off" (the full "AI: off · code only" is its
  `aria-label` and shows from 521 px), the budget chip "AI 0/450" (full words from 761 px), and the
  connection is always a word.
- One primary thing: the Next decision card (`--c-surface-2`, radius 12, padding 16, the only
  filled button on the tab). The other drafts are one-line rows (hairlines, no boxes).
- Review sheet: full screen under the page header, its own sticky header ("‹ Decide", "Review
  RFA1225", "Version 1") and the fixed action bar at the bottom; the body keeps a bottom padding
  equal to the bar height. The tab bar gives way to the action bar while a review is open.

### 4.6 Desk at 375x667

Same structure. Header text sizes step down one (the disclaimer is 12 px, still never
truncated). Card padding 12. Action bar: primary 52, secondary 44. The sheet body scrolls in
the space left (about 400 px); the action bar never covers the last row (bottom padding equal
to the bar height).

### 4.7 Desk at 1440x900

Header full width: row 1 (48) brand left, then "AI: off · code only", "AI calls today: 0 of 450",
"Connected" and the account button; the REPLAY bar (28) and the disclaimer row (24) under it, full
width; the tab bar (48, four 148 px tabs with icon, word and badge) under the header. Below: two
panes inside a 1280 max-width frame: Decide 420 wide on the left (the Next decision card, then the
compact rows; the selected row is outlined in `--c-line-input` with a 3 px left bar, and the Next
decision's button gets a ring when its draft is the one in the pane), the review pane on the right
(fluid, max 760) with "Why this advisory" open and the action bar at the pane's bottom. The most
urgent draft is selected on load. `.sheet-idle` ("Choose an advisory to review") shows while
nothing is selected. Ask, Airports and Paperwork are one centred column, max 880.

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
| 6 | `fir-label` | symbol | firs, minzoom 5 | line placement, spacing 700, `label` ("WAAF UJUNG PANDANG FIR"), Noto Sans Regular 12, letter-spacing 0.08, `#7f92a6`, halo 1.5; FIR and VAAC lines are off by default (Map layers) |
| 7 | `vaac-line` | line | `/static/data/vaac_aor.geojson` | `--map-vaac`, 1.2 px, dash [6,3,1,3]; label "DARWIN VAAC" / "TOKYO VAAC" like FIRs |
| 8 | `navaid` | circle + symbol | `/static/data/navaids.geojson`, minzoom 8 | 3 px ring `--map-navaid`; ident 12 px; off by default |
| 9 | `tephra-fill` | fill | cones, `part == cone` | `--c-tephra` 0.07 (dimmed 0.03) |
| 10 | `tephra-hatch` | fill | cones, `part == sector` | `fill-pattern` hatch image (section 5.2), opacity 1 (dimmed 0.4) |
| 10a | `crew-fill` | fill | `crew`, `feature == area` (5.7) | `--c-crew` 0.06; beneath every official layer |
| 10b | `crew-line` | line | `crew`, `feature == area` | `--c-crew` 1.4 px at z4, 2.2 px at z8, dash [4,3], opacity 0.95; beneath the official fills, so an official area is never covered |
| 11 | `official-fill-now` | fill | official, step `now`, shown, `fill == true` (5.1) | `--c-official` 0.14 (dimmed 0.07) |
| 12-14 | `official-fill-f6/f12/f18` | fill | steps | 0.05 / 0.035 / 0.025 |
| 15 | `official-line-now` | line | step `now` | 2.6 px at z8 (1.6 at z4), solid, join round |
| 16-18 | `official-line-f6/f12/f18` | line | steps | 2 px dash [4,2] op 0.9; 1.8 px dash [2,2] op 0.75; 1.8 px dots [0.1,2] round cap op 0.6 |
| 19 | `tephra-line` | line | cones, `part == cone` | `--c-tephra` 2.6 px at z8 for the selected volcano, 1.4 px for the others, dash [3,2], `line-offset: -5` (outset), join round |
| 20 | `exposure-path` | line | exposures, `kind == path` | `--c-tephra` 2.4 px dash [1.5,1.5]; marching (5.4) |
| 21 | `exposure-entry` | circle | `kind == entry` and `minutes_to_entry > 0` | r 6, fill `--map-halo`, stroke `--c-tephra` 2.5 (no ring for a flight already inside) |
| 21a | `crew-path` | line | `crew`, `feature == path` | a flagged flight's projected track into a crew area: `--c-crew` 1.8 px round dots [0.1,2.2]; follows "Flight paths into the area" |
| 22 | `exposure-entry-label` | symbol | same filter | "+12 MIN", Noto Sans Bold 13, `--c-tephra-text`, offset [0,-1.3] |
| 23 | `volcano-inactive` | symbol | `active == false` | hollow eruption icon 0.5, opacity 0.8; name from z7.5, 12 px `--map-label-minor` |
| 24 | `volcano-active` | symbol | `active == true` | eruption icon by code (5.3); name Noto Sans Bold 14 (16 selected), `--map-label`, halo 2; left out for a non-selected volcano whose area label already names it |
| 24a | `crew-pin` | symbol | `crew`, `feature == pin` | the canvas pin `crew-pin` (ivory, dark outline and centre), anchor bottom at the report position, allow overlap; above every area, under the planes and labels |
| 25 | `aircraft-icon` | symbol | aircraft | SDF plane (5.3); every plane is always drawn |
| 26 | `aircraft-inside` | circle | `inside`, minzoom 6 | r 18, stroke `--c-tephra` 2, no fill |
| 26a | `aircraft-crew` | circle | `crew_report == true`, minzoom 4 | r 28, stroke `--c-crew` 1.8, no fill: outside the inside-now (18) and picked (23) rings |
| 27 | `exposed-cluster` | symbol | `exposed-pts` (clustered: radius 60, min points 6) | `box-tephra` with "8 RFA flights", or "20 RFA flights here" when some exposed planes are outside the cluster (the text field is rebuilt when the total changes); beside its centre (variable anchor left, right, bottom-left, top-left, radial offset 2.2; right first when the planes are within 180 px of the right edge), so it never sits on the vent; moved above the forecast-step and other-volcano labels so those give way to it; 44 px hit area; a click zooms in |
| 28 | `aircraft-label-exposed` | symbol | `exposed-pts`, not clustered, minzoom 6 | one line "RFA1225 · inside" / "RFA6178 · in 12 min", Bold 13, right of the plane, collides |
| 29 | `aircraft-label` | symbol | not exposed, minzoom 7.5 | "GIA123 FL350", Regular 12, `--c-text-3`, optional |
| 30 | `official-step-label` | symbol | `official-labels`, kind `step` | "Forecast for 0000Z (+6 h)" while a forecast step is chosen; collides |
| 31 | `official-label` | symbol | `official-labels`, kind `name` | other volcanoes: the name only, 12 px `--c-official-text`, above the area's northern vertex; collides (sort key 10) |
| 31a | `crew-label` | symbol | `crew-labels` (5.7) | box `box-crew`, two lines, beside the pin and nudged inside the canvas; collides and sits below the flight count, so the count, TEPHRA's tag and the official labels win |
| 32 | `tephra-label` | symbol | `area-labels` (5.2) | box `box-tephra`, one line, collides (sort key 5) |
| 33 | `official-label-selected` | symbol | `official-labels`, kind `box` | the selected volcano's box `box-official`, two lines (5.1), the only layer with `text-allow-overlap: true` (sort key 0): never hidden |
| 34 | `rose-*` | line, circle, symbol | `rose` source (section 6) | above the labels; the angle box collides like the others |

Other volcanoes' official areas are drawn at 0.6 of the fill and 0.85 of the edge (`fade`,
`lfade`); official areas are never hidden on the main map (the height filter fades them to 0.15 and a
map pill says so).

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
- Label (`official-labels`, a point source the client computes; UI-REDESIGN R6.3): for the
  selected volcano one box, line 1 (`--c-official-text`) "Official ash area · SFC–FL150 · until
  1720Z" (band over every valid official area, `valid_to` of the latest SIGMET, else the VAA), line 2
  (`--c-text-1`, scale 0.9) the movement in plain words ("moving SE at 10 kt", from the SIGMET or VAA
  card; left out when not given). Product ids are not on the map: they are in Details › This ash
  area and What the official reports say. Every other volcano gets its name only (12 px, no box). Anchor: just beyond the
  tip of the official arrow when the rose is shown (section 6; `text-anchor` from the bearing,
  limited to `top`, `top-left`, `top-right`, `bottom`, `bottom-left`, `bottom-right`); otherwise the
  centroid of the SIGMET (or OBS) polygon's vertices with anchor `top`; if that centroid lies within
  25 km of the vent (circular SIGMETs centred on the volcano), the polygon's northernmost vertex
  with anchor `bottom` (the box sits above the area, clear of the vent).
- After framing (7.4), if the selected official box would cross a map pill, a control or the map
  edge, pan the camera by the overlap (`panBy`) so it is visible.
- Forecast-step labels appear only while a forecast step is chosen: "Forecast for 1700Z (+6 h)"
  (forecast time = `valid_from + 3 h`), 13 px, `--c-official-text`. One label per step, however
  many products forecast it: at the step's vertex farthest from the vent, reading inward (anchor
  from the vent-to-tip direction, so it never hangs off the map edge). Under "All" the steps are
  placed +6, +12, +18 and each keeps 250 km from the labels already placed.
- Exposure entry labels ("in 12 min", lowercase) only from zoom 8; zoomed out the cluster speaks.
- Boolean properties in style expressions are read as `["==", ["get", k], true]`, so a missing
  property is false, never a null that MapLibre warns about.
- The stretchable box: a 36x36 canvas at pixel ratio 2, fill `rgba(8,12,18,.92)`, 3 px border in
  the role colour, radius 6, registered with `stretchX: [[9,27]]`, `stretchY: [[9,27]]`,
  `content: [9,9,27,27]` (reference: `labelBox()` in `wall-ref.mjs`).

### 5.2 TEPHRA's cautious area

- Outline `tephra-line`: amber dash [3,2], `line-offset: -5` so it sits just outside the official
  edge when the two coincide (OFFICIAL mode) and reads "contains" (research shot-coincident).
  Key row: "TEPHRA's estimate · never smaller than official".
- Fill 0.07 under the official fill. Where the model widened it (`part == sector` exists, modes
  WIDENED and HYPOTHESIS) the sector gets a 45° amber hatch: a 24x24 canvas at ratio 2, three
  3 px lines at alpha 0.55, added with `addImage` and used as `fill-pattern`.
- Label (`area-labels` point source; R6.3): one amber-bordered line on the edge opposite the
  official box, at the cone vertex farthest from it, reading inward (so it stays over the map):
  "TEPHRA's estimate · same as official (AI off)" (OFFICIAL with the stub; without "(AI off)" with a
  model), "TEPHRA's estimate · wider than official" (WIDENED) or "TEPHRA's estimate · hypothesis".
  It collides (sort key 5): if it drops out, the key row still explains the dashed line. The cone's
  raw `label` ("OFFICIAL 100% (NO MODEL)") is under Technical detail in Details.
- HYPOTHESIS (no valid official product): the whole area is hatched (cone = sector), the story's
  first line is the hypothesis banner ("HYPOTHESIS: no valid official product. Only MONITOR or HOLD
  may be advised."), and Details › TEPHRA's estimate says the same.

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
| Exposed | `exposed == true` | `--c-tephra` | 0.7 | from z6: one line `--c-tephra-text` "RFA4821 · in 12 min", Bold 13, right of the plane; six or more within 60 px merge into a "n RFA flights" box (row 27) |
| Inside now | exposed and `minutes_to_entry == 0` | `--c-tephra` + ring r 18 from z6 | 0.7 | "RFA4821 · inside" |
| Picked | the viewer chose it on the map or in Flights heading in (7.8) | unchanged + `--c-text-1` ring r 23, 2.5 px | unchanged | details in Details › This flight |
| Stale | `state.now − observed_at > 60 s` | `--c-aircraft-stale`, opacity 0.55 | as above | the age is in This flight and the flights list |
| Level unknown | `alt_baro_ft == null` | as above | | "level unknown" in This flight; never hidden by the height filter |
| Decided | an advisory for this flight is APPROVED/EDITED/REJECTED | unchanged | | the decision is in This flight, the flights list and Decisions |

### 5.4 Exposure paths

Amber dashed line from the aircraft to its entry point, entry ring with "+12 MIN". The dashes
march toward the entry (cycle the 14-step `line-dasharray` set from the research snippet every
60 ms with `setPaintProperty`; pause while `document.hidden`; still under reduced motion). Only
this layer animates continuously.

### 5.5 Context layers

- FIR and VAAC outlines are off by default (Map layers), "approximate" in Map layers, Help and
  About. When on, the FIR containing a valid SIGMET is brighter: that explains why a SIGMET stops at
  a line. Navaids off by default; airports are not drawn (no data contract for them on the Wall).
- Reroutes are drawn only for the picked flight, unless Map layers turns them all on.
- ADS-B coverage: when no RFA flight is heading in, the story says "Aircraft coverage here is
  patchy: an empty map is not an empty sky." (or that aircraft data is failing or off); the 150 km
  coverage note goes to the story notes when the flight line has not said it. An empty map is never
  presented as an empty sky.

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

### 5.7 Crew report caution areas

A crew (pilot) report of ash that a dispatcher entered on the Desk (10.15, MODULES.md 5.19) is
drawn from `WallSnapshot.crew` and the `crew` stream event, which carry the whole picture of the
current mode. Every word and number comes from the server's code-written fields; the Wall only
joins them. The area is operator policy A, not a VAA or SIGMET, so it is ranked under every
official area on the map, in the story and in Details.

- Area (`crew-fill`, `crew-line`): a faint ivory fill and long ivory dashes, beneath the official
  fills and lines (rows 10a, 10b). It never covers, shrinks or replaces an official area and the
  official area cannot be switched off. It is drawn for ACTIVE and COVERED reports; EXPIRED,
  WITHDRAWN and no-area (routine or no-ash) reports are listed in Details, never drawn. There is
  no fade with age: the age is a number in words ("reported 47 min ago").
- Pin (`crew-pin`): at the report position (the ADS-B fix or the typed position), drawn on top
  of every area so the report is not lost under them.
- Label (`crew-label`): line 1 "Crew report caution area · reported 47 min ago" (`--c-crew-text`),
  line 2 "RFA6186 · FL260–FL300 · operator policy A; not a VAA or SIGMET" (the area's band, the
  reporting flight), or "… · covered by official area" for a COVERED report. Beside the pin,
  nudged inside the canvas (`fitLabels`), colliding; it gives way to the flight count.
- Flagged flights: a flight whose projected track crosses an active area (`crew_report` on its
  aircraft feature) gets an ivory ring (`aircraft-crew`, r 28); a flight that will enter later
  gets the dotted ivory path to its entry point (`crew-path`).
- Clicks: the pin, label, outline, fill or path opens Details › Crew reports of ash with that
  report marked (`ui.details.vid`). Framing (7.4) includes the crew areas named after the
  selected volcano. "Show on the map" in Details fits one area (`WallMap.flyToCrew`; on a phone
  it closes the sheet first).
- Compare (8.2): the "official only" side does not draw crew areas; they are not official. 3D
  (8.1): the outline stays on the ground; there is no crew volume.
- Map layers (7.14): "Crew report caution areas · always on · operator policy A, not a VAA or
  SIGMET" (locked, like the official area).

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
  bearing does not parse, draw no rose; the Details card still explains the discrepancy.
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

Key row: "Observatory's reported drift" (`lg-arrow-observer`); Help's full key also lists "Official
movement" (`lg-arrow-official`). Never call either arrow right or wrong; the disagreement card says "TEPHRA's
area covers both" only when the cone mode is WIDENED and the sector contains the observatory
bearing.

## 7. Wall components

The Wall is built as `docs/UI-REDESIGN.md` ("The Story") describes; this section records what was
built and where. The code is `index.html`, `wall.js` (state, stream, actions, keyboard, drawer
placement), `wall/story.js` (story column), `wall/details.js` (Details drawer), `wall/panels.js`
(top bar, footer, time bar, section builders, dialogs), `wall/ext.js` (satellite, notices, airport
plan, track record, AI helpers), `wall/duty.js`, `wall/controls.js` (layers, Help, About),
`wall/map.js` and `wall/ext-map.js` (the map), `wall/x-parts.js` (shared parts and `plainLine`).

Structure (R3): `body.wall` is a grid of four rows: the REPLAY band, the top bar, the stage and the
footer. The stage is a grid of three columns: the story (`#story`), the map column (`.mapcol`: the
map, then the slim time bar) and the drawer (`#details`, 0 px wide while closed). Nothing floats over
the map except its labels, the status pills (bottom-left), the map controls and the attribution
(bottom-right), and the compare labels in compare mode. The body never scrolls at 601 px and up;
the story column and the drawer scroll inside themselves.

### 7.1 REPLAY band

`#replay-banner` (violet, 32 px; 28 px at 1280; one line on a phone, sticky there, showing the short
`#replay-banner-short` "REPLAY: recorded 05 Sep 2026" instead of the full words): the REPLAY icon,
`state.replay.banner` verbatim, " · not live", then " · {case label}" (and " · switched
automatically: no live activity" when the switch was automatic). At 1280 the case label is hidden
and stays in the band's tooltip, About and Details › Data feeds. `role="status"`: written only when
the words change.

### 7.2 Top bar

`header.cmdbar`, 56 px (48 at 1280), never clipped (`scrollWidth <= clientWidth` at every width in
R17.2). Left to right:
1. Brand "TEPHRA"; the sub-line "Volcanic-ash decision desk" only at 1600 px and up.
2. Mode pill `#mode-badge`: "Live" (green, live icon), "Replay" (violet, replay icon),
   "Connecting…".
3. Area picker: `#area-btn` "Area: Java / Bali · 2 with ash ▾" opens the menu `#regions`
   (`role="menu"`, `menuitemradio` rows "Halmahera · 2 with ash", "Kyushu · none", "All areas"; the
   current one checked; arrow keys, Home/End, Esc). Keys 1-9 still choose areas. On a phone the
   native `#region-select` replaces it ("Java / Bali · 2"). The counts come from one active list
   (the server's `active_volcano_ids` plus any situation card, by vent), the same list as "n with
   ash" in All volcanoes, so the picker and the story never disagree. Before the server's first
   tick an area with nothing yet reads "· reading…", never "· none".
4. Spacer.
5. AI chip `#ai-chip` (button) with `#model-chip` as its text: "AI: off · code only" (stub; "AI:
   off" at 1280 and on a phone) or "AI: on · {state.llm.label}", plus a red "· 2 failed" with the
   serious shape when AI steps failed. Title: "No AI model is connected. Code does every step;
   code templates write the text." It opens Details › AI helpers.
6. Data chip `#feeds-chip`: "Data: 6 working · 5 off", worst first ("Data: 1 error · 5 working ·
   5 off", serious shape and border; "2 stale" in caution); "ok" for "working" below 1360 px. It
   opens Details › Data feeds.
7. Clock: `#clock-time` (fixed 9ch) and `#clock-sub` "11 Oct · UTC" or "Replay clock · 5 Sep · UTC"
   ("UTC" / "Replay · UTC" below 1360 px; "Stopped · …" while the stream is lost).
8. `#stale-chip` "Not updating since 10:31Z", only while the stream is lost.
9. "Desk →" (`.desk-link`, quiet outline, new tab). The filled button is in the story.

### 7.3 Footer

`footer.honesty`, one line (32 px; 28 at 1280): the info icon and `#disclaimer` (from
`state.disclaimer`); "RFA (Ring of Fire Air) is a fictional airline; its flight numbers are proxies
for real aircraft." ("RFA is a fictional airline." below 1360 px); then "Map and data credits"
(`#attribution`, opens About › Credits), "Policy A (illustrative)" (`#policy-btn`), "Help"
(`#help-btn`), "About" (`#about-btn`), "Privacy". On a phone the disclaimer line moves (the node is
re-parented) into the sticky header (`#phone-honesty`), so it is always visible without a fixed
footer covering content; the rest of the footer is the last thing on the page.

### 7.3a Help (`?`)

Help (`controls.helpContent`): "Read the map in 3 steps" (pink = the official ash area, binding;
amber dashes = TEPHRA's estimate, never smaller; amber planes = flights of RFA, our fictional
airline; a person approves every advisory on the Desk), a short list (the story and Details, nothing
is sent anywhere, REPLAY, Z = UTC), "Full map key" (every key row with its swatch, "Alert colour:
green, yellow, orange, red; grey = not given", "FIR and VAAC lines are approximate", context-only
layers), "Words used here" (the glossary, with Alert colour, Estimate, Advisory, Dispatcher, Proxy
flight and SO2 added), and "Keyboard" (section 9) with the shortcut switch (WCAG 2.1.4). The key's
"Full map key and alert colours ›" opens Help at the full key. Every dialog (`.dlg`) has
`overflow: hidden` and only `.dlg__body` scrolls (`position: relative`, `overscroll-behavior:
contain`), so an absolutely placed `sr-only` caption can no longer stretch the dialog and let the
wheel scroll its header away. Under 600 px the glossary stacks each term above its meaning.

### 7.4 Map container and camera

The map fills `.map-pane`. Framing (`WallMap.frame`) pads 48 px on every side (56 at the bottom and
the controls' width on the right), max zoom 8.6; nothing else is avoided because no panel sits on
the map. After a frame, `keepLabelsInView` pans so the selected official label clears the pills and
controls. Clicks (R6.5): a polygon (official or TEPHRA) opens Details › This ash area for its
volcano; a plane (or its entry ring, or its reroute) picks the flight and opens Details › This
flight; a vent selects its volcano; a flight cluster zooms in (`getClusterExpansionZoom`, `jumpTo`
under reduced motion). There are no MapLibre popups. Keyboard users reach the same views through the
flight list and the sources section. The camera re-frames when the selected volcano changes (also
when it changes because an area was chosen and its first volcano arrived later).

### 7.5 Key block

`#legend` is a fixed list in the story column (R5.5), never a floating panel, listing what is drawn
now: "Official ash area · binding", "TEPHRA's estimate · never smaller than official", "Crew report
caution area · operator policy, not a VAA or SIGMET" (while one is drawn), "RFA flight in
or heading in", "Official forecast area (+6 h)", "Other aircraft (not RFA)", "Suggested reroute",
"Observatory's reported drift", "Where TEPHRA widened the area", "Box marked on the satellite picture ·
supporting only", then the link "Full map key and alert colours ›" (Help). At 1600 px and up it runs
in two columns. From 601 to 1599 px, while Details is open, the same node is moved to the bottom of
the drawer as a compact strip; on a phone it is the strip under the map. Swatches keep their colours
in forced-colours mode.

### 7.6 Story card, failure line, trust line, notes

The story (R5, `wall/story.js`), built by code from fields, about the selected volcano:
- Failure line `#fail-line` (only when something failed; red edge and the serious shape; at most two
  items, then "+ n more problems ›" to the Details section that holds the next): the lost stream
  (`#lost-banner`, `role="alert"`), the Wall data not loading ("Could not load the Wall data: …
  Trying again in n s."), the map library not loading, a failing SIGMET, VAA, VONA or aircraft feed
  ("Aircraft data is failing. Showing the last good positions, from 10:20Z." — the time only from
  `last_success_at`), the database failing, an airport plan with no plan ("no plan found, the
  solver did not finish in time…", R2.6), a satellite reading or the Duty Officer with AI
  unavailable, and the count of failed AI steps. A new failure is announced once (`role="alert"` on
  its first render only).
- Eyebrow: the eruption symbol, `#volcano-name` (the page's h1), " · {area} · alert {Red}" ("alert
  colour not given" for UNKNOWN), and "as of 1030Z". A no-break space sits before each "·", so a
  wrapped line never starts with a dot.
- Lines `#headline` (28/24/22/20 px by width), replaced only when their words change: in REPLAY a
  "Recorded" tag first; L1 "Official reports put the ash up to 50,000 ft (FL500)." (or "between …
  and …"; the HYPOTHESIS banner replaces it: "HYPOTHESIS: no valid official product. Only MONITOR or
  HOLD may be advised."); L2 "The sources disagree on where the ash is heading (135° apart)." with
  "TEPHRA's estimate covers both." (WIDENED) or "TEPHRA's estimate has not been widened (AI off)."
  (OFFICIAL, stub); SILENCE and CONFLICT lines; L3 "Ash from Anak Krakatau closes 2 RFA airports:
  WIHH, WIII (3 across all volcanoes)." (the current plan's closures whose source ids are this
  volcano's official products or cone; the all-volcano total is added when it differs, so every
  count states its scope, G8; the plan's time in the title); L4 "23 flights of RFA, our fictional airline, are in or heading into TEPHRA's
  estimated ash area." or, at 0, "No RFA flight is seen heading into TEPHRA's area right now." with
  "Aircraft coverage here is patchy: an empty map is not an empty sky." (or "Aircraft data is
  failing/off: …"); L5 "30 advisories wait for a dispatcher." (advisories, never "n of their":
  a draft can outlive its flight's exposure; "At least 30 …" when the Wall's page of the 50 newest
  advisories cannot hold them all), followed by the small note "7 of them are for flights no longer
  seen heading in." when some drafts' flights are not among the flights counted in L4; "All n
  advisories are decided: a approved, r rejected.", "Their advisories are not drafted yet." or
  "Advisory count unknown (database error)."
- Crew report lines (`crewLines()` in `wall/story.js`), after the flights, one size down, at most
  two: with a pin, "Crew report of ash on the route of 4 RFA flights: RFA7554, RFA4090, RFA8094
  and 1 more." or, with no flight flagged, "Crew report of ash near Slamet (100 km), reported 5
  min ago: no RFA flight is seen crossing its caution area." ("(no catalogued volcano)" in place
  of the place when none is within 300 km); with the caution shape, "Crew report outside the
  official area: RFA4259, reported 1 min ago (+1 more)." The reports counted are the selected
  volcano's plus any report near no active volcano (none catalogued, or a quiet one), so a
  report is never lost from the story; with no volcano selected the lines still show. A
  "Crew reports" link beside "Show the n flights" opens Details › Crew reports of ash.
- Re-planning: while the newest airport-plan step in the trace is "Closed airports changed: …;
  recovery agent started" and no plan has landed since (`ext.replanning`), L3 is "Ash closes 3 RFA
  airports (all volcanoes): WARA, WIHH, WIII. Re-planning the day's flights…" (the trace does not
  say which volcano closed them, so the line says its scope), Details › Airport closures reads "3
  airports (all volcanoes) · re-planning…" (caution) and its section opens with a spinner line
  instead of "No RFA airport is closed". With a plan, the row reads "2 from Anak Krakatau, 3 across
  all volcanoes · plan waiting". The Desk's Airports tab follows the same trace line (section 16).
- Buttons: the one filled button on the Wall, "Decide on the Desk →", linking to
  `/desk#review/{the most urgent DRAFT advisory of this volcano}` in the Desk's own urgency order
  (`byUrgency`: inside now first, then the soonest entry on the clock, then the oldest draft); the
  Desk opens that draft as its Next decision, so one flight is primary on both screens; with no
  draft it is the secondary "Open the Desk". "Show the n flights" opens
  Details › Flights heading in (hidden at 0).
- Reading (`D.reading`): before the server's first tick, or while an active volcano in scope has
  no situation card yet, h1 the area, a spinner, "Reading the official reports…" and "TEPHRA has
  just started and is reading every feed for the first time. This takes up to a minute." (or "Ash is
  reported here. The summary appears when TEPHRA has read the reports, usually within a minute.").
  It is never "no ash" for something not yet read.
- Empty area (`D.regionEmpty`): h1 the area; "No ash reported near Kyushu right now." then "Ash
  elsewhere:" with a button per area that has ash ("Java / Bali · 1"). Nothing active anywhere: "No
  official ash report is in force in the watched regions right now." Connecting: "Connecting to
  TEPHRA…" with a spinner and no numbers. Never "clear" or "safe".
- Trust line `#trust`: "AI: off · code built this summary from the official reports" or "AI: on
  ({label}) · it can widen TEPHRA's estimate, never shrink the official area" (the second
  always-visible model state). It sits inside the story card, right under the lines it describes
  and above the button, so it is on screen at every width (R0.2.5).
- All volcanoes: one comma-separated sentence, "5 volcanoes with ash, 23 RFA flights in or heading
  in, 26 advisories waiting" (`#kpi-active`, `#kpi-exposed`, `#kpi-drafts` hold the numbers); at 0
  flights it reads "no RFA flight seen heading in", never "– RFA flights" or a line that starts
  with a "·".
- Story notes `#story-notes`: notes that are not map pills (the basemap note; the 150 km coverage
  note when the flight line has not said it).
- "☰ Details" (`#details-btn`) is sticky at the bottom of the story column from 601 px up, so the
  route to everything else is always on screen at 1280 and 1440; the fade above it shows only when
  the column really scrolls (after the fit pass).
- The changed flight count gets a `--dur-5` highlight (not under reduced motion). `#announce` speaks
  "{volcano}: {L4} {L5}" at most once every 30 s, only when the volcano, the flight count or the
  waiting count changes.

### 7.7 Map controls and status pills

Bottom-right, stacked by MapLibre: `#tools` (a custom control) with "Fit" (`data-tool="frame"`, F)
and "Layers" (`data-tool="layers"`, L, opens Details › Map layers), zoom +/- at 1600 px and up (the
compass only in 3D), and the attribution (`AttributionControl`, `compact: false`, 12 px:
"OpenFreeMap © OpenMapTiles Data from OpenStreetMap"). Icon-only below 1360 px; 40 px icon and word
on a phone. Bottom-left, `.map-pills`, only while true and one line each: `#ctx-label` (one
`.ctx-pill` per satellite, SO2 or BTD layer, never folded: "CONTEXT ONLY" and the caption wrap
together, the ✕ that turns the layer off sits beside them, and the GIBS scale, where one is
published, is inside the same pill; at most 520 px wide), and `#map-notes`: "Height filter FL180–FL350 hides 1 official
area and 4 flights · Reset", "Showing the official forecast for 0000Z (+6 h) · Back to now" or "No
official +12 h area in the current products · Back to now". More than three: "+n more map settings ·
Show". While History is open the pills and controls move up above it.

### 7.8 Details › Flights heading in, This flight

`#flights` (R8.3): the count sentence and the RECORDED tag, the first 5 rows (plane, "RFA1225",
"proxy for GIA616 · FL310", "inside now" or "in 12 min, est.", the advisory status when one is
loaded), then "All n" (`<details>`), the RFA and coverage note, and "+n heading in at Semeru" links.
A row picks the flight (white ring on the map), flies to it and opens This flight: the proxy and
the real callsign and hex, the estimated entry and its basis, level (and selected level), speed and
track, position age, the drafted action and its decision, "Open on the Desk ›"
(`/desk#review/{id}`), and the suggested reroute when there is one. "Clear" (or Esc) unpicks it. A flight a crew report
flags gets the box "Crew report of ash on this route" (ivory dashed edge, pin): "RFA7554 is inside
the crew report area now." or "… enters the crew report area in 9 min if track and level are
held.", each report it crosses in one line ("RFA4259 reported ash seen, engine signs at FL360,
reported 1 min ago · Active"), the policy line and that approving Keep watching or Continue
needs a written reason on the Desk, and "Crew reports of ash ›". An approved decision's reason
shows as "Reason given: …". The flights list row carries "Crew report of ash on this route"
with the pin.

### 7.9 Details › How TEPHRA decided

`#trace` (`role="log"`, `aria-live="off"`): "This volcano / Everything", then plain lines
(`plainLine`, R12.7), newest first, 14 shown and "Show all (n)"; each line has its time, "· by code"
/ "· by an AI helper" / "· AI off" (`actorWords`: with the stub backend an `adk` or `gemini` step
says "AI off", never "by an AI helper"), and "Technical detail" with the stage, the actor chip and
the raw message. Plain wordings include the stub plume estimate ("Plume estimate by code (AI off):
same as the official area, SFC–FL150, confidence 100%"), the cone line, "nothing to check and no
RFA flight within 250 NM", "{volcano} is active. Reports: …", "{feed}: n new or changed records",
the SRA draft line ("Safety risk assessment draft for Java / Bali: evidence by code, 4 narrative
boxes by a code template (AI off). Not an approved SRA.") and the no-plan line. Lines with no plain wording are shown verbatim, never paraphrased. Human decisions
composed from advisory events are merged in (stage DESK).

### 7.10 Other volcanoes

`#volcano-tabs` is a list of buttons in the story's "All volcanoes" block (`<dl class="kpis">`:
`#kpi-active` with ash · `#kpi-exposed` RFA flights in or heading in (– at 0, amber above 0, its
title and aria-label kept) · `#kpi-drafts` advisories waiting): "{symbol} Semeru · 1 flight · 1 thing
to check ›", priority order, the selected volcano left out; 3 rows at 1920, 2 at 1440, 1 at 1280,
all on a phone, then "+ n more" (expands in place). `[` and `]` step through volcanoes. The drawer
header has the same volcanoes in a switcher (`#details-volcano`).

### 7.11 Details › What the official reports say

`#brief` hosts it: "2 official reports name Anak Krakatau. Official reports are binding.", "Why
Anak Krakatau is on the Wall (n)" (the `active_reasons`, folded), then one card per source (SIGMET
(airspace warning) · binding, VAA (ash advisory), VONA (volcano observatory notice); pink or blue top
edge; title, age, evidence chip, day or night at the vent, stale line) with rows Seen, Height,
Movement, Valid, Alert colour (plain words: "seen 1010Z", "estimated", "moving W at 30 kt", "not
given"; codes stay mono; flagged cells keep the caution ring and shape) and "Raw text"; then "Raw texts
side by side (C)", "What they say in their own words" (VAA info source and remarks, VONA activity and
cloud height, folded) and "Technical ids" (source ids and hashes, folded). Cards are used at every
drawer width, so no column is cut off.

### 7.12 Details › Where the sources disagree, TEPHRA's estimate

Disagree: "2 to check · 12 minor" or "Nothing that needs checking (12 minor differences)", the
CAUTION and SERIOUS cards (unchanged builders, "Show on the map" for a direction mismatch), then
"Minor differences (n)" folded (INFO items and the "could not see the ash" rows). Estimate: the
outcome sentence ("Same as the official area (AI off, nothing added)."), the note that it is an
estimate, drawn amber dashed, never smaller; Rule, Heights, Read by, Valid until (and Confidence when
widened), "Technical detail" (mode, label, cone id), and "How the model read it" (model runs only).

### 7.13 Details › Decisions, Airport closures, Notices, Satellite picture, Track record, AI helpers

- Decisions (`#decisions`): "{state.draft_count} waiting · a approved · r rejected", "Approve on the
  Desk · nothing is sent anywhere…", then the full list (folded).
- Airport closures (`#xpanel`, `recovery`): "WIII, WIHH closed by ash SFC/FL500 within 20 NM · Plan
  waiting on the Desk: cancel 47, delay 29, $893,032", or the solver wording (R2.6) in a red box
  with the raw string under "Technical detail"; the as-of time and who planned it; then
  "Per-airport reasons, scenarios and numbers" (closures with "Full reason and sources", blocked /
  can still change / can't change, the chosen scenario, the scenario table, why, risks, decision).
  Dollar amounts use `Intl.NumberFormat` ("$62,525").
- Notices: the count and newest notice, its card, then "All notices and their claims".
- Satellite picture: per reading, "Ash visible?", "Gas (SO2, not ash)", "Cloud in the way" (yes, no,
  "can't tell"), "Ash marked on the picture" (none or n boxes) and "Read by" (code stub (AI off) or
  the model id); "Show the picture" folds the frame with its boxes, the limits quote and the JMA
  colour key. AI unavailable stays a red box with the reason; nothing is put in its place.
- Track record: the caveat "Later official areas are not ash truth.", the two coverage bars per arm,
  "The Gemini arm has not been run…", then "Every number, check and case" (tiles, the safety-floor
  and future-data chips, the per-case table, caveats).
- AI helpers: "AI off: code does every step…", the Duty Officer line ("Duty Officer (AI off): handed
  out 3 jobs in urgency order"), failures in red first, "AI calls today: 0 of 450" (the lite tier,
  the same tier and words as the Desk's budget chip; both tiers are under "Model budget"), then
  "Delegation, every helper and the budget" (the Duty Officer card and delegation diagram, every
  helper with its state, the budget tiers).

### 7.14 Details › Timeline history, Height filter, Data feeds, Map layers

- Timeline history (`#history`): the lag in words, the note that a lag is usual, "Show History on
  the time bar", the forecast-step note, and the events newest first with their times.
- Height filter (`#levels`): "Showing: All heights", the vertical double slider (track fixed at
  270 px, labels SFC FL060 FL180 FL350 FL550, the official and TEPHRA bands, aircraft ticks), a key,
  and the presets All, Hazard, ≤FL180, ≥FL180. Arrow keys, Page keys, Home/End and drag.
- Data feeds (`#feeds`): one row per feed (R12.8 names), the status word with its shape, the age,
  "recorded" in REPLAY, and "Technical detail" (last good time, records, feed key, the raw error);
  the database row last.
- Map layers (`#layers-pop`): the status ("satellite off"), "On the map" (official locked on;
  TEPHRA's estimate; crew report caution areas locked on; aircraft; other aircraft labels; flight paths; suggested reroutes (off by
  default: only the picked flight's reroute is drawn); satellite boxes; disagreement arrows; FIR and
  VAAC lines (off by default); navaids; terrain), "Height filter ›", then "Satellite pictures, 3D and
  compare" (Off, Infrared, Visible, Air mass, "Next picture" `data-tool="sat"` with `#sat-state`, SO2,
  BTD, View 2D/3D `data-tool="3d"`, "Compare" `data-tool="compare"`, not on a phone).

### 7.15 Sources side by side dialog (C)

Unchanged: three columns of raw text with source id, issued, fetched and hash; opened by C and by
"Raw text".

### 7.16 Data feeds

The feed health dialog became Details › Data feeds (7.14); the Data chip opens it.

### 7.17 Global Wall states

Connecting (story "Connecting to TEPHRA…", mode pill "Connecting…", no numbers); load error (the
failure line only, retried every 5 s with a countdown; never a cached story); stream lost (the
failure line, `#stale-chip`, the clock stops, a light scrim on the map, the time bar dims);
REPLAY (the band, the mode pill, "Recorded" on the story, "recorded" tags); HYPOTHESIS (the banner
replaces L1); empty area and nothing active (7.6); 3D and compare (8.1, 8.2).

### 7.18 Operator policy

Summary first (R9.3): "Policy A (illustrative): avoid every official ash area, with 2,000 ft above
and below. Not reviewed by an airline." (the margin from `exposure.vertical_margin_ft`), the
policy id, version, risk owner, SRA and hash, then folded: the full summary text, "Show all n
values" (every block that has values, grouped), the source-trust order, the citations.

### 7.19 The Details drawer

`#details` (`<aside role="region" aria-labelledby="details-title">`, `wall/details.js`), opened by
`#details-btn` ("☰ Details · Sources, timeline, how TEPHRA decided, AI, data feeds"), the chips, the
key, map clicks and the shortcuts. Placement (R8.1): at 1600 px and up a 480 px column that pushes
the map (the story stays); from 601 to 1599 px it takes the story column's place at 480 px (440 at
1280) with the story strip `#story-strip` ("‹ Story · Anak Krakatau · 23 flights · 23 waiting ·
Desk →") on top and the key pinned at the bottom; at 600 px and below it is moved into the dialog
`#details-sheet` (`showModal`) that starts below the sticky header. The header has "‹ Details" (in
a section), the title `#details-title` (h2, focused on open), the volcano switcher and Close. The
index `#xtabs` (`role="list"`) has four groups (The ash, with "Crew reports of ash" after Notices;
The flights; Time and height; Behind the scenes), each row a button with its live status in words (serious and caution rows carry their
shape); rows keep `data-xtab` for the old rail panel ids (brief, sat, notices, recovery, proof,
ai), and `setRail(id)` opens the matching section. Sections re-render in place on new data,
keeping scroll, focus (`data-focus`) and open `<details>`. Esc: section → index → closed, focus
back to the opener. The state (`tephra.wall.details`: a section key, "index" or "closed") is kept in
`sessionStorage` (wrapped in try/catch), never in presentation (`?present=1`, P) or screenshot
(`?shots=1`) runs. The drawer ends with the full attribution string `#drawer-attrib`.

### 7.20 Details › Crew reports of ash

Section key `crew`, host `#crew`, group The ash. Index status: "2 active · 6 flights flagged · 2
outside the official area" (caution shape while any report is outside), "1 report, none active",
or "none in the last 24 h". The section: "3 crew reports in the last 24 hours · 1 with a caution
area now" with the "recorded" tag in REPLAY; the label and a plain explanation (a dispatcher
enters it on the Desk; code draws the area; it flags flights, never shrinks or replaces an
official area, re-plans nothing and calls no model; a sulphur smell alone is a routine report
with no area; a no-ash report never removes one); then one card per report, newest first,
with its full record: the flight, the state with its shape and word (Active, Covered by official
area, Expired, Withdrawn, or the no-area wording), the age, "entered in REPLAY", the discrepancy
line "Crew report outside the official area. A dispatcher can start a message to the weather
office and the VAAC on the Desk." (caution box), then Crew reported (cues in words), At (band,
observed time), Position (latitude and longitude, "ADS-B fix at 1039Z" or "typed by
dispatcher"), Near ("near Slamet (100 km)" or "no catalogued volcano"), Caution area (radius and
band), Wind stretch (the server's note), Valid (from, to, time left), Entered (who, when),
Remarks, Covered by (display only: the area and its flags stay), Withdrawn (who, when, reason),
Flights flagged; the server's summary sentence; "Show on the map" and "Open on the Desk ›"
(`/desk#crew/<id>`); "Technical detail" with the report, position, wind and covered-by ids and
the policy. The section ends with "Report ash from a crew on the Desk ›" (`/desk#crew-report`).
The Wall is read-only: entering, withdrawing and the VAR are on the Desk.

## 8. 3D, compare, the time bar and the height filter

### 8.1 3D mode (D)

`easeTo({ pitch: 55, bearing: -20, zoom: flat fit + 0.35, duration: --dur-camera-long })` (round 2: the old zoom-out showed half of Asia), enable drag-rotate, set sky
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

### 8.3 The time bar

`#timeline` (`wall/panels.renderTimeline`), slim and always visible under the map (52/48/44 px). It
never changes TEPHRA's clock (there is no seek API). Left to right:
1. Mode and window: "Live · 9 h back, 3 h ahead", or "Replay · 1030Z · 9% of 1030Z–1930Z" (with the
   dates when the window spans more than 20 h) and a progress bar (`role="progressbar"`,
   `aria-valuetext` "9% of the recording").
2. The scrubber: one 8 px track over the last 9 h and the next 3 h, the now-line, hour labels and
   the event marks (official reports, observatory notices, TEPHRA's disagreements, flights and
   decisions), focusable with ← / →; choosing one opens its Details section and frames the map.
3. "Forecast: [Now] +6 h +12 h +18 h All" (`aria-pressed`; 44 px targets).
4. "‹ Previous" and "Next ›" (disabled at the ends with the reason in the title, "No earlier
   event").
5. "History ▴" (`aria-expanded`): the bar grows upward over the map (the only thing that ever
   does, on this explicit action) with three lanes, "When each source last reported": Official
   (with each product's validity bar), Observatory, TEPHRA; the marks move there. The lag bracket's
   words sit above the lanes ("lag 2 h 0 min between the observatory and the official reports"),
   never on the now-line. Esc or "History ▾" closes it; 3D closes it. The map's pills and controls
   move up while it is open.

On a phone the bar is the time pill on the map and opens as a bottom sheet.

### 8.4 Height filter

The filter lives in Details › Height filter (7.14) with a fixed 270 px track; the old height rule
(sizing the track from the map pane, `body.levels-pop`) is gone. While it hides anything a map pill
says so, with "Reset" (7.7). H opens the section and focuses the top thumb.

## 9. Keyboard

Single-key shortcuts work when focus is not in a text field and no modifier is held; they can be
switched off in Help (WCAG 2.1.4, stored in `localStorage`). Every shortcut has a visible control
too, and controls carry `aria-keyshortcuts`.

| Key | Action |
|---|---|
| `1`-`9` | Choose an area (in `state.regions` order) |
| `[` / `]` | Previous / next volcano; the area follows |
| `F` | Fit the selected volcano |
| `D` | 3D on/off |
| `S` | Compare on/off (not on a phone) |
| `C` | Sources side by side (raw texts) |
| `I` / `O` / `B` | Satellite picture cycle / SO2 / BTD on and off; each shows its map pill |
| `L` | Details › Map layers (again: close) |
| `T` | Details › How TEPHRA decided |
| `H` | Details › Height filter, focus on the top thumb |
| `P` | Presentation layout (keeps Details closed) |
| `?` | Help |
| `Esc` | Close the dialog or menu → the section → the Details index → close Details → collapse History → clear the picked flight → leave compare → leave 3D |

Focus order on the Wall: skip links ("Skip to the story", "Skip to map", "Skip to details") → top
bar → story column (failure line, story, buttons, key, other volcanoes, Details) → map → map
controls → time bar → drawer (when open) → footer. Focus is always visible. Opening Details moves
focus to its title; a section to its title; "‹ Details" back to the row it came from; closing back to
the opener. The area menu and the History overlay take Esc. Dialogs and the phone Details sheet trap
focus and return it on close. The Desk has no single-key shortcuts: no key press ever approves or
rejects.

## 10. The Desk

Dark only (`color-scheme: dark`, the same tokens). Phone first. Every Desk request sends
`X-Tephra-Desk: 1` (MODULES.md 5.9) and JSON bodies with `Content-Type: application/json`; every
decision sends the `version` the dispatcher saw.

### 10.1 Header (always)

Row 1 (48): "TEPHRA" (700, letter-spaced) + "Desk" (text-3, hidden at 430 px and under); the model
chip `#model-chip` "AI: off · code only" (dashed, `i-code`) or "AI: on · {state.llm.label}"
(`i-model`), with the exact label and the old sentence ("NO MODEL: official products only…") in
its title; the budget chip `#budget-chip` "AI calls today: 0 of 450" (phone "AI 0/450", the
`aria-label` always full; it opens the per-tier budget sheet); the connection `#conn`, always a
word with its shape: `st-ok` "Connected" (not "Live", which under the REPLAY bar would read as
live data), `st-stale` "Reconnecting…", `st-serious` "Offline", `st-never` "Connecting…"; the
account button (initials in a 32 px circle, menu: "Signed in as AK · session ends 1830Z",
"Display: LIVE" with "Change display…" (10.10), and "Sign out"). Row 2 (REPLAY only, 28): violet
bar `i-replay` + `state.replay.banner`. Row 3: the disclaimer, 12 px semibold text-1, wraps,
never truncates. `#net-banner` (offline, back online) under it. `state` is read from `GET
/api/state` at start and from `state` events; until then the static HTML disclaimer is shown.

Tabs `#tabbar` (R10.2): Decide, Ask, Airports, Paperwork, each an icon and a word with a 12 px
count badge. The `data-tab` keys `queue`, `ask`, `network`, `docs` and the `sessionStorage` key
`tephra.desk.tab` are unchanged. Decide's badge counts advisories + messages + open problems, and
its `aria-label` and title say so ("Decide, 28 waiting: 23 advisories · 3 messages · 2 problems to
acknowledge"); Airports counts plans waiting; Paperwork counts documents to sign.

### 10.2 Sign-in

Centred card (max 400): title "Dispatcher sign-in" (24), hint "Your name is recorded on every
decision. The PIN is never stored on this phone." Name field (autocomplete `username`, 2-32
chars) and PIN (`current-password`, numeric keyboard `inputmode="numeric"`), 48 px tall, 16 px
text, labels above, errors under the field (`aria-describedby`), button "Sign in" (primary
neutral: `--c-text-1` fill with ink text, 48 tall, full width). Errors (11.8): bad PIN, too many
attempts (button disabled with a countdown from the `Retry-After` header), desk disabled,
offline. A deep link waiting for a session shows "Sign in to review RFA1225." above the form
(`#login-pending`, the flight named from the public `/api/advisories`; "Sign in to review this
advisory." until it is known). On success: focus moves to the Decide title and the hash resumes
(10.14).

### 10.3 Decide (was Queue)

Title "Decide" (`#q-title`, 24) and a ⋯ button (`#q-more-btn`, `aria-label="More actions"`,
`aria-expanded`, Esc closes and returns focus, arrow keys move) holding "Report ash from a crew"
(`#crew-report-btn`, 10.15), "Paste a notice" (`#paste-notice`) and "Refresh the lists"
(`#refresh`, spins while loading). Pull-to-refresh and the
refresh on every `advisory` event stay. Sort: inside now first, then entry time, then
`created_at`. In order:

1. `#fail-section` "Problems to acknowledge" (red, count): AI failures, each with "Mark handled…".
   Failures are never folded, so they sit above the Next decision.
2. The Next decision card (`section.next`): eyebrow "NEXT DECISION" (`#drafts-title`), "1 of 23
   advisories · most urgent first" (`#q-count`), the breakdown "23 advisories · 3 messages · 2
   problems to acknowledge" (`#q-breakdown`, shown only when there are messages or problems), then
   the draft in `#q-next`: flight (24 600) and "proxy for GIA616 · A320"; the entry pill (shape +
   words: "Inside the ash now", "Enters in 12 min (est.)", "Entry was due 3 min ago (est.)"); the
   action in plain words with the ICAO word in brackets (20 600, 11.7); "Anak Krakatau · ash
   SFC–FL500 · drafted 4 min ago"; the advisory text (mono, 3 lines); "Written by a code template
   (AI off). Check the sources first." (or "Drafted by AI ({model}). …"); "7 sources · newest 3 min
   ago"; caution chips only when they apply ("Crew report of ash on this route" with the pin, first;
   HYPOTHESIS, "Needs a careful read", "Sources stale", "Drafted 12 min ago: entry time may have
   moved"); and the one filled button "Review RFA1225 ›".
   The area, model and REPLAY chips left the cards: the model and REPLAY are in the header, the area
   is in the review's Why.
   - The card does not swap under the dispatcher's thumb: when a more urgent draft arrives, the
     line "1 draft is more urgent · Show the most urgent" (`#q-newer`, caution) appears and the link
     moves the card (and, at 1100 px and up, the review pane) to it.
   - The draft open in the review is the Next decision: a deep link from the Wall or a tapped row
     puts it in the card, with its place in the order ("5 of 41 advisories · most urgent first").
   - At 1100 px and up, while a draft is open in the right pane (`.desk[data-view="review"]`), the
     card folds to its row: flight, entry pill, action and caution chips; the meta line, advisory
     text, writer line and sources line are hidden (they are in the pane), and the "Review" button
     is hidden when the pane already shows this draft. One advisory is never shown twice at equal
     weight.
3. "{22} more waiting" (`#more-title`) and `#cards`: one row per other draft, two lines: flight |
   "inside now" / "enters in 9 min" over "Keep watching" | a caution mark: its shape and a short
   word ("crew report", "16 min old", "sources stale", "read carefully", "hypothesis", "+1" for more; the full
   words in the title and for screen readers), never a bare icon | ›. A new row is highlighted for
   `--dur-5` and tagged "New" for two minutes. Only the first 5 rows show, then "Show all n"
   (`#cards-all`), so the one-line links below stay near the top; the selected row is never
   hidden.
4. One-line links (`.qlinks`): first the crew reports (`#crew-section`, 10.15); then "Airport plan waiting: 3 airports closed (all volcanoes), cancel 133 ›"
   (`#plan-section`, opens Airports); "Messages to approve (3) ›" (`#msg-section`) and "Notices (4) ›"
   (`#notice-section`), which open in place to today's cards and rows; "Duty Officer (AI off): 25
   items put in order of urgency · latest run 1035Z ›" (`#duty-section`), which opens in place to the outcome chip, the
   summary, "Do first" (priorities with "Must do" tags; with AI off the code reason is said once in
   the heading, "Do first · in urgency order (AI off)", not under every item), "Watch", "Delegated
   to", "Deferred", and under "Technical detail" the run line (model, turns, offered, trigger, time)
   and the raw stub text. Must-do items the Duty Officer did not
   hand out are a failure: that red box stays visible while the brief is folded, and the line
   reads "Duty Officer (AI off): 1 must-do item not handed out".
5. `#closed` "Decided while this page was open (2)", a collapsed `<details>`.
6. `.qfoot`: "Approved text goes only to TEPHRA's own outbound queue. Nothing is sent to an aircraft
   or any real system."

States: loading (skeleton rows), empty ("No drafts waiting." + "A draft appears here when a
flight's projected track enters TEPHRA's estimated ash area. Last update 16:07:12Z."), error
("Can't load drafts." + the reason + "Try again"), offline (10.9), a new draft (announced "New
draft: RFA4821, HOLD FL250, enters in 12 min").

### 10.4 Review sheet

Opens from the Next decision's button or a row (full screen on phones, the right pane at 1100 px
and up). Header: back "‹ Decide" (hidden in the pane), title "Review RFA1225" (`#s-title`),
"Version 1". The primary facts come first, above the action bar:

- closed or HYPOTHESIS banners when they apply; the REPLAY chip "Drafted from recorded feeds";
- "RFA1225" + "Proxy for ADS-B GIA616 (hex 8A01DE) · A320";
- the action, large: "Keep watching (MONITOR)" (24 600);
- the entry ("Inside the ash now" with "Inside TEPHRA's estimated area when drafted at 1030Z", or
  "Enters in 12 min (est.)" with the drafted minutes); it updates with the countdown;
- a caution box when the validator flagged the text ("Needs a careful read: …") or a source is
  stale ("Some sources are stale.");
- for a flight a crew report flags, the crew box and, for Keep watching or Continue, the reason
  box (10.15);
- "ADVISORY TEXT" and the text being queued (16 px mono);
- "Written by a code template (AI off). Check the sources first." / "Drafted by AI ({model}). …" /
  "Edited by a dispatcher from …";
- "7 sources · newest 3 min ago · Show ›" (Show opens Why and scrolls to the evidence).

Then "Why this advisory" (`<details id="why">`, open at 1100 px and up, closed on a phone; its
open state survives re-renders), a summary list with:

| Row | Value |
|---|---|
| Evidence | one chip per `sources[]`, binding first, each named by its product from `source_id`: "SIGMET WIIF 15 · issued 3 min ago · #6a6a3adb", "SIGMET WIIF 15 (area 2) …", "VAA Darwin 2026/176 …", "VONA Anak Krakatau …". Never merged by hash: four SIGMETs from one fetch stay four chips. With no `source_id` the chip shows the feed name and its time; no id is invented. Then "Times, links and full ids (7)": feed, source id, issued and fetched times, `#sha256_short`, "stale", the public link, and "Weather data by Open-Meteo.com" for winds |
| Route | for a reroute: the sketch, extra distance, time and fuel, the route string, "Turn points are coordinates only" |
| TEPHRA area | the area chip ("OFFICIAL 100%", "WIDENED 62%", "HYPOTHESIS … · MONITOR or HOLD only") + the mode sentence |
| Hazard band | "SFC–FL500" + "TEPHRA's estimated area, vertical extent" |
| Fuel and time | `fuel_line` in mono + "Simple TEPHRA formula, not airline tables" |
| Cost note | left out when it repeats `fuel_line` |
| Drafted by | "Written by a code template (AI off)" or "{model} · AI-drafted", the fine print, validator notes |
| Operator policy | "RFA-POLICY-A v… #hash" + "Illustrative values, not an airline SRA; not reviewed by an airline dispatcher" |
| Header | "Advisory header (written by code)", collapsed |
| History | "History (audit log)", collapsed, loaded on open |

and "Ask TEPHRA about RFA1225" at its foot. The duplicate "Edit text" link under the text is gone:
the bar's "Edit text" button is the only one.

Action bar (fixed at the bottom on a phone, at the pane's bottom at 1100 px and up): the primary
approve (10.5); "Hold to approve, or tap to confirm. Nothing is sent to an aircraft." under it; then
"Edit text" and "Reject…" at equal weight. Approve green appears only here (R13.3).

### 10.5 Approve: hold to confirm, or tap to confirm

The primary button names the outcome in plain words (R12.10): "Approve: keep watching RFA1225",
"Approve: hold RFA1225 at FL250", "Approve: divert RFA1225 to WARR", "Approve: change level for
RFA1225", "Approve: continue RFA1225", "Approve: reroute RFA1225"; the ICAO word stays in the action
line above (`--c-approve` fill, `--c-approve-ink`, 56 tall, radius 12, 18 px 600, `i-check`).

- Press and hold (pointer): a fill (`--c-approve-progress`) sweeps left to right over
  `--dur-hold` (1200 ms, linear, kept under reduced motion as essential feedback). At full, the
  label changes to "Release to approve". Releasing inside the button approves (the up-event
  completes it, WCAG 2.5.2). Sliding off or `pointercancel` cancels and resets. Releasing early
  (250-1200 ms) cancels with the hint "Keep holding to approve, or tap for a confirmation step."
- Tap (release under 250 ms), Enter or Space, and any assistive technology click: open the
  inline confirmation in place of the action bar: "Approve: hold RFA4821 at FL250?" (20 600),
  then flight, action, entry time and version (14 500 mono text-1, updates with the countdown):
  "RFA4821 · Hold at FL250 (HOLD) · enters in 12 min, est. 1619Z if track and level are held ·
  version 2", or "… · inside the area since 1607Z · version 2" (computed by code from `created_at`
  and `minutes_to_entry`), "Queued under AK on TEPHRA's own outbound queue · nothing is sent to an
  aircraft.", and two buttons "Approve now" (approve style) and
  "Cancel" (outline; returns to the action bar, nothing is decided). This is the single-pointer
  alternative (2.5.7) and the confirmation step (3.3.4). There is no swipe-to-act.
- While sending: the button shows a spinner and "Approving…", all decision buttons are
  disabled. Success: the decided stamp, then the sheet moves on to the next draft (on a phone too)
  and the toast (11.8) carries the audit line and "Next: RFA1530 · inside now". There is no bulk
  approval: the next draft needs its own hold or confirm. With no draft left the sheet closes and
  focus goes to the empty state.

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
- Toast (bottom, 15 s for a decision toast so the receipt can be read, 6 s for other toasts, `role="status"`, persists while focused; title 16 px 600; at most 40vh tall
  on phones): approved "Approved: HOLD FL250
  for RFA4821 · queued 1607Z under AK. Not sent to any aircraft."; edited "Approved with your
  edits: RFA4821 · both versions are in the audit log."; rejected "Rejected: RFA4821 · reason
  recorded."
- Under the receipt, "Next: RFA1530 · inside now" (14 text-2). The machine text folds under
  "Technical detail" (`details.toast__tech`), so the toast is two or three short lines and does not
  cover the next draft's advisory text on a phone.
- Audit line, inside "Technical detail": first "AUDIT APPROVED desk:AK 1607Z" from `GET
  /api/audit?advisory_id=…` (the entry whose action matches the decision, never another entry
  in its place; mono 14 500, `--c-approve` or `--c-reject-text`; when none is listed yet the toast
  says "Audit entry not listed yet: see History under Decided while this page was open.", and
  "Can't load the audit line: …" when the request fails),
  then the first two `SRC` lines of the advisory header (feed, id, issued, fetched, `#hash`; mono
  12 text-2). This is the video's "audit line with feed times and
  hashes".
- 409 `version_conflict`: the sheet switches to "This advisory changed while you were reviewing
  it." with a two-column diff "You saw (version 1)" / "Now (version 2)" for Status, Action, Entry and Text
  (changed values highlighted with a caution bar and the word "changed"), using `current` from
  the error body. If `current.status` is DRAFT: "Review the new version" (primary neutral). If
  terminal: "AK approved it at 1607Z" (or "TEPHRA replaced it with a newer draft at 1606Z" for
  SUPERSEDED) and "Back to Decide". The outcome comes before the diff, in a panel with the status
  shape and word; the version chip reads "Version 1 → 2"; the Now status cell carries the status shape;
  identical text shows once as "Same text".
- 409 `invalid_transition`: "This advisory is no longer a draft." + who/when + "Back to Decide".
- 404: "This advisory no longer exists." + "Back to Decide". The deep-link toast with the same
  words (R10.3) is about the Decide list: it is dismissed when another tab is chosen.
- At 1100 px and up the review pane uses `overflow: clip` (not `hidden`), so a script's
  `scrollIntoView` cannot scroll the pane's header and body out of view.

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

### 10.11 Ask (R10.5)

Title "Ask TEPHRA" (`#ask-title`). The composer is the primary thing and sits first: the question
field ("Type a question…"), mic (push to talk) and send, the flight context chip when Ask was
opened from a review ("About RFA1225 ×"), and "Read-only: Ask never changes an advisory, a plan or
a message." Under it the five suggested questions as wrapping chips and "English, Bahasa Indonesia
or Japanese." The decorative speech-bubble art is gone. Answers follow, newest first, each
exchange in its own block (question bubble, then the answer card). An answer card shows the
answer, then its claims (kind, text, and one chip per evidence item in words: "from: flights
heading in", "from: TEPHRA's area", "from: data feeds"…; a chip opens the verbatim tool result),
then "How I answered" (collapsed: the raw tool ids such as "T01 exposed_flights (flights heading
in)", the validator, the model, the human gate), follow-ups, and a foot with Listen, the model chip,
the language chip and REPLAY. With the stub, the code-written answer reads "AI off: this answer is
a code count, not a reading of your question. Flights projected to enter TEPHRA's area: 22." (the
API text still starts "NO MODEL", which tests and the spoken reply rely on); a model's answer is
always shown exactly as written. Refusals: "Not in the evidence I have" + what was checked. When an answer (or a failure card) lands in the lower half of the screen it is scrolled to just under the sticky header, so on a phone it never arrives below the fold.

### 10.12 Airports (R10.6, was Network recovery)

Title "Airport plan" (`#net-title`) and a ⋯ menu (`#net-more-btn`) with "Re-plan now" (`data-run`;
"Plan now" with no plan; busy "Re-planning…"). One decision card first (`.plan`):

```
AIRPORT PLAN  ◷ Waiting for your decision
Ash closes 3 RFA airports: WARA, WIHH, WIII.             20 600
Plan: cancel 47 flights, delay 29, swap 8 · 12,057 passengers
Estimated cost $893,032                                   24 600
[Fictional airline RFA · synthetic schedule] [Recorded]
Planned 1030Z by code · version 1 · explained by: AI off  14 text-3
[ ✓ Approve plan… ]   [ ✕ Reject… ]                        inside the card, not sticky
```

Approve plan is the neutral filled button (approve green is only in the advisory review); it opens
the confirm sheet "Approve the airport plan?": "Plan: Closure as forecast", one sentence "Cancels 47
flights, delays 29 and swaps aircraft on 8 · 12,057 passengers affected · estimated cost $893,032."
(no caps tiles), the queue note and the green button; the sheet is as tall as its content
(`.bsheet { height: fit-content }`). Approved: "Approved by AK at 1031Z · queued, not
sent anywhere" + "Draft crew and passenger messages". Rejected: who, when and the reason.

Then disclosures, in order (open state kept across re-renders): "Closed airports (3)" (per airport
"WARA · 05 SEP 0530Z to 06 SEP 0230Z · ash SFC/FL150 within 20 NM · 2 official products", then
"Full reason and sources"); "Other plans compared (3)" (scenario cards "Closure as forecast",
"Closure +180 min", "Closure +360 min" with cost, cancelled, delayed, swapped, delay, passengers,
ferry legs, "Recommended", and "Best plan found (43 s)" / "Plan found, not proven best (37 s)" /
"solver gave no answer after 43 s"; a failed one reads "No plan found: the solver did not finish in
time"; tapping a card shows its flights and opens Flight by flight; stacked on a phone); "Why this
plan" (the rationale under its AI chip; the stub's sentence in plain words with its raw text under
"Technical detail"); "Flight by flight (79)"; "Numbers" (a two-column table: Flights blocked,
Passengers blocked, Can still change, Can't change (already departed), In the air and at risk as a
wrapped list of flight ids); "Earlier plans (n)". Then "Decision support only. Approving a plan
queues it on TEPHRA's own outbound queue; nothing is sent to an airline system."

- No plan (R2.6): the status reads "No plan found", the card's sentence is "No plan found: the
  solver did not finish in time. A dispatcher must plan the network by hand." (or "… no plan fits
  the closures …"), the raw string is under "Technical detail", there is no Approve button, and
  "Other plans compared" opens by default. `planProblem()` in `desk/network.js` mirrors the Wall's.
- No closures: "No RFA airport is closed by ash right now." + "Last checked 1031Z." and the
  fictional-airline chip.
- In progress: "Re-planning for WARA, WIHH, WIII…" with a spinner (`aria-busy`).

### 10.13 Paperwork (R10.7, was Docs)

Title "Paperwork" (`#docs-title`) and the chip "DRAFT · not an approved document · fictional
airline". Primary: "Ready for you (n)" (`#doc-list`): the drafts waiting for a signature ("SRA ·
SRA draft: Java / Bali · 0 of 3 signed · drafted 05 SEP 1030Z · recorded ›"), and a handover brief
that waits for its read-back; "Nothing waits for your signature. Start a document below." when
empty; signed documents in a collapsed "Signed (n)". Then "Start a document" and three starters,
one line each, that open in place:

- "Hand over the shift" (WEST and I-PASS): incoming dispatcher, outgoing (signed in), "Last 4 h /
  8 h / 12 h", "Write the handover"; the latest brief, its read-back and "Printable page".
- "Safety risk assessment (SRA)": one region select, regions with an active volcano first and
  marked "(active volcano)", and "Draft SRA".
- "Pilot ash reports (VAR): 12 flights": one row per flight in or heading into TEPHRA's area now
  ("RFA1225 · Anak Krakatau · Keep watching" + "Draft VAR"). The set is the Wall's: the exposed
  planes of the `/api/wall` snapshot and the `aircraft` stream event (`app.exposedIds`), matched to
  each flight's newest advisory that code has not replaced, so the count equals the Wall's flight
  count and every row is one the server accepts. Until the aircraft layer is read: "Pilot ash
  reports (VAR)" with "Reading the flights in or heading into the ash…"; with none, "None needed: no
  RFA flight is in or heading into an ash area."

A failed draft shows its reason inside its starter (opened). Opening a document is unchanged (the
wide sheet with sign lines and the printable page).

### 10.14 Deep link and the 3 taps (R10.3)

`/desk#review/{advisory_id}` selects that draft; `#tab/{queue|ask|network|docs}` switches tab;
`#crew-report` opens the crew report form and `#crew/{CR-id}` one report's record (both wait for
the crew picture, then clear the hash); an empty hash shows the saved tab. The hash is only a pointer: it never skips the session check, the
hold or the confirm step, and it is cleared once used. Signed in: Decide opens with that draft's
review (the right pane at 1100 px and up, the full-screen sheet on a phone). Signed out: the sign-in
names the flight and the hash resumes after sign-in. No longer a draft: the toast "This advisory is
no longer a draft." and Decide with the next decision selected; unknown id (no audit entries): "This
advisory no longer exists." The Wall's "Decide on the Desk →" opens the link, so the 3 taps are:
"Decide on the Desk", "Approve: …" (hold, or tap), "Approve now".

### 10.15 Crew reports of ash (`desk/crew.js`)

A dispatcher enters what a crew reported; code draws the area (MODULES.md 5.19). Nothing is sent,
nothing is re-planned and no model is called. A report is refused rather than completed with a
guess.

- Reach (two taps at most): Decide › ⋯ › "Report ash from a crew"; with no report yet, the first
  one-line link is "Report ash from a crew · a pilot saw ash, smelled sulphur or had engine signs ›"
  (one tap); the Wall links `/desk#crew-report`.
- The Decide link `#crew-section`: "Crew reports of ash (3) · 2 with a caution area · 6 flights
  flagged" with "⚠ 2 outside the official area"; it opens in place (open by default while a report
  is outside or a draft is flagged) to "Drafts for flagged flights (4). Keep watching or Continue
  needs a written reason:" with one chip per draft ("RFA7554 · Keep watching: reason needed", "RFA5275 · Hold at FL250")
  that opens its review; one row per report (short state word with its shape, "RFA6186 · FL280",
  "reported 4 min ago · near Slamet (100 km)"); under each outside report the caution box "Crew
  report outside the official area: RFA6186, reported 4 min ago." with "No valid official area
  meets it, sideways or in height. Pass the difference on to the weather office and the VAAC."
  and "Start a message to the weather office and VAAC" (the VAR draft, below); and the button
  "Report ash from a crew".
- The form (bottom sheet "Report ash from a crew"): the lead line; Flight (a select of the
  tracked RFA flights, airline callsigns only, "RFA4259 · BTK6401 · FL360", and "Another flight:
  type its callsign"); What the crew reported (toggle chips: Ash seen, Haze or dust in the cabin,
  St Elmo's fire, Engine signs, Sulphur smell, No ash seen) with the live result line ("Draws a
  crew report caution area of 60 NM around the position.", "A sulphur smell alone is recorded as
  a routine report: no area is drawn.", "Recorded. A no-ash report never removes or shortens any
  area.", "'Ash seen' and 'No ash seen' cannot both be reported."); Reported level ("FL [350] to
  FL [ ]", the margin from the policy, "A report with no level is refused: TEPHRA never invents
  one."); Observed at (UTC) (Today / Yesterday with their dates on TEPHRA's clock, HHMM, "Now");
  Position (after the flight and the time: "ADS-B fix of RFA4259 at 1046Z: 6.20S 109.40E, FL360.
  The report is placed at this fix." from `GET …/crew-reports/fix`, or the server's "No ADS-B fix
  of … within 90 s of …: type the position the crew reported" with latitude and longitude in
  degrees and N/S, E/W selects that start empty, marked "Typed by dispatcher"); Remarks
  (optional, 300). Numbers in hints come from `GET /api/policy` (`crew_reports`).
- Refusals: the page checks only the empty and malformed fields; the server checks the rest and
  lists every problem (422). Both show "Not recorded …" at the top and each problem under its
  field (no flight, no cue, "A crew report needs the reported flight level or band; TEPHRA never
  invents one.", a time in the future or older than the area lasts, no position, a typed position
  when a fix exists). A position problem looks the fix up again.
- Recorded: the toast "Crew report recorded: RFA4259 · caution area drawn · 4 flights flagged.",
  then the record in the sheet with "Recorded under AK at 1047Z. The Wall shows it now; the
  audit log has the entry." and "Report another".
- A report's record (`openCrewReport`, from a row, "See the report" or `#crew/<id>`): the state,
  age and REPLAY chip; the outside box when it applies; the label line; Crew reported, Level,
  Observed, Position, Near, Caution area, Wind stretch, Flights flagged, Covered by, Entered,
  Remarks, Withdrawn; the server's summary; "Technical ids". Footer: "Draft the VAR (weather
  office and VAAC)" (when no outside box already offers it) and "Withdraw (entry error)…".
- Withdraw: "Withdraw only an entry error: the wrong flight, position, time or level. The report
  and its audit entries are kept. A later "no ash" report is not a reason: it never removes an
  area." Reason required (3 to 500), quick reasons Wrong flight, Wrong position, Wrong time, Wrong
  level, Entered twice; "Withdraw report" (reject style); 409 "This report is already withdrawn."
- The VAR: `POST …/{id}/var` opens the VAR draft in the Paperwork sheet ("Volcanic activity
  report: RFA4259 / Slamet", "CREW REPORT ENTERED BY A DISPATCHER - NOT FROM A FEED"); a person
  completes and signs it; nothing is sent.
- On drafts: a flagged flight's Next decision card and row carry "Crew report of ash on this
  route" (first caution). The review shows the crew box (dashed ivory edge): "Crew report of ash
  on this route", "RFA7554 is inside the crew report area now." (or enters in n min), one line per
  report with "See the report ›", and "Crew report caution area (operator policy A; not a VAA or
  SIGMET). A flag only: nothing was re-planned."
- The reason box: for Keep watching (MONITOR) or Continue (CONTINUE) on a flagged flight (every
  tracked flight is airborne), "Reason to keep watching on this route (required)" with "Recorded
  with the decision and in the audit log. The crew report stays on the Wall either way.", 3 to 500
  characters. Until it is filled, the approve button is `aria-disabled`, its hint reads "A crew
  reported ash on this route: write the reason above before approving.", and a tap on it moves to
  the box with "Give a reason of at least 3 characters: a crew reported ash on this route." The
  confirm step repeats "Reason (crew report of ash on this route): …". The reason goes as `reason`
  with approve and with edit and approve (Edit shows the same boxes). A 422 `reason_required`
  (the server saw a flag the page had not drawn yet) opens the box with the server's words.
- Mode: the picture is of the current mode; a draft of the other mode is never matched to it.

## 11. Copy deck

Sentence case in prose; caps only for codes, aviation words and small caps labels. Hyphens in
the disclaimer exactly as `state.disclaimer` gives them.

### 11.1 Honesty labels (exact)

| Where | Text |
|---|---|
| Disclaimer (both pages, always) | `Decision support only - fictional airline - not for operational use` (from `state.disclaimer`; the HTML ships the same text) |
| REPLAY banner (both pages, whole session) | `state.replay.banner`, e.g. "REPLAY: recorded real feeds from 23 Sep 2026" |
| Model label (both pages, always) | The AI chip "AI: off · code only" / "AI: on · {state.llm.label}" on both pages (the Desk's `#model-chip`, "AI: off" on a phone with the full words in its `aria-label`), and the Wall story's trust line; the exact `state.llm.label` stays in the chip's title and Details › AI helpers |
| AI marking | "AI-drafted" (advisory body), "AI-written · {model}" (plume reading, satellite limits); with no model the Wall says "Written by code (AI off)" |
| Every satellite layer | "CONTEXT ONLY · {layer} {time} · not ash detection · Imagery: NASA GIBS · Himawari-9 data: JMA via NOAA" |
| SO2 layer | "CONTEXT ONLY · SO2 (TROPOMI, daily) {date} · SO2 is not ash; gases not modelled · Imagery: NASA GIBS · Contains modified Copernicus Sentinel data 2026" |
| BTD overlay | "Split-window BTD (computed by TEPHRA) · an indicator, not ash detection" |
| Airline | "Ring of Fire Air (RFA) is a fictional airline. RFA flight numbers are proxies for real aircraft." |
| Outbound | "Approved text goes only to TEPHRA's own outbound queue. Nothing is sent to an aircraft or any real system." |
| TEPHRA's area | On the Wall "TEPHRA's estimate" · "an estimate, not a forecast" · "never smaller than official" |

### 11.2 Mode words

| Mode | Short | Sentence |
|---|---|---|
| LIVE | "Live" (mode pill), "Live · 9 h back, 3 h ahead" (time bar) | "Live feeds" |
| REPLAY | "Replay" (mode pill), "Replay clock · 5 Sep · UTC" | the band + " · not live"; "Recorded" on the story; "recorded" on tags |
| OFFICIAL (cone) | "TEPHRA's estimate · same as official (AI off)" | "Same as the official area (AI off, nothing added)." |
| WIDENED | "TEPHRA's estimate · wider than official" | "The official area plus the observatory's drift, never smaller." |
| HYPOTHESIS | "TEPHRA's estimate · hypothesis" | "HYPOTHESIS: no valid official product. Only MONITOR or HOLD may be advised." |
| Area picker | "Area: Halmahera · 2 with ash" / "Kyushu · none" / "All areas" | |
| Stale | "Not updating since 10:31Z" | "Lost the live connection at 10:31Z. Reconnecting…" |

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
| STUB | "AI off: official reports only" (the estimate's outcome sentence: "Same as the official area (AI off, nothing added).") |
| ACCEPTED | "Gemini reading accepted by the validators" |
| REPAIRED | "Accepted after one repair" |
| MODEL_FAILED | "AI unavailable: official products only, nothing assessed beyond them" |
| OFFICIAL_ONLY | "No model call needed: official products only" |
| PENDING | "Plume read queued for the Duty Officer: official products only until it runs" |

### 11.6 Feed names and status wording

Names: sigmet "VA SIGMET (AWC)", vona "VONA (MAGMA)", vaac_tokyo "VAA Tokyo", vaac_darwin "VAA
Darwin", taf "TAF", metar "METAR", adsb "Aircraft data (adsb.lol)", winds "Winds (Open-Meteo)",
frames "Satellite pictures", hsd "Himawari raw processing", jma_volcano "JMA volcano reports". Raw
errors go under "Technical detail". Status lines: OK "Working · updated 27 s ago"; STALE
"Stale · last good 14 min ago · showing the last good copy"; ERROR "Error · last good 2 h ago"
(or "never") + the error; DISABLED "Off" + the reason verbatim (the VONA feed's status word is
"Off: no PVMBG permission (replay only)", so it is not read as the operator policy); NEVER "Not
polled yet". Replay: add the tag "recorded".

### 11.7 Action words (Desk and Wall)

From the advisory, plain words first and the ICAO word in brackets (R12.10): MONITOR "Keep watching
(MONITOR)", HOLD "Hold at FL250 (HOLD)" (`hold_fl`), DIVERT "Divert to WARR (DIVERT)"
(`alternate_icao`), CHANGE_LEVEL "Change level to FL300–FL340 (CHANGE LEVEL)"
(`change_level_fl_min/max`), CONTINUE "Continue (CONTINUE)", REROUTE "Reroute right of the area,
+12 min (REROUTE)". Rows use the plain part alone ("Keep watching"). The advisory text, the toast
receipt ("Approved: MONITOR for RFA1225 · …") and the audit keep the ICAO words. Entry: "Inside the
ash now", "Enters in 12 min (est.)". Buttons: "Approve: keep watching {proxy}" (10.5), "Approve
edited text for {proxy}", "Reject advisory for {proxy}", "Review {proxy}", "Edit text", "Reject…",
"Approve now", "Cancel", "Back to Decide", "Review the new version", "Sign in", "Sign out", "Try
again", "Refresh the lists", "Re-plan now", "Approve plan…", "Write the handover", "Draft SRA",
"Draft VAR". Tabs: "Decide", "Ask", "Airports", "Paperwork". Labels: "Version 1" (not "v1"),
"Written by a code template (AI off)" (not "Template · NO MODEL"), "AI calls today: 0 of 450",
"Pilot ash report (VAR)", "Ready for you", "from: flights heading in" (not "T01 exposed_flights"),
"TEPHRA's area" (not "hazard cone"). Per-item AI chips read "AI off · code" with the stub (title
"NO MODEL: …").

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
| Empty Decide list | "No drafts waiting." / "A draft appears here when a flight's projected track enters TEPHRA's estimated ash area." |
| Deep link, signed out | "Sign in to review {proxy}." |
| Newer draft while reading | "1 draft is more urgent · Show the most urgent" |
| No plan (solver) | "No plan found: the solver did not finish in time. A dispatcher must plan the network by hand." |
| No closures | "No RFA airport is closed by ash right now." + "Last checked {HHMM}Z." |

### 11.9 Never on screen

"Forecast", "warning", "alert" or "dispatch release" for TEPHRA output; "detected", "detection"
or "sees ash" for any satellite, SO2 or BTD layer; "Gemini found the ash"; "no traffic" for an
empty ADS-B map; "the observatory was right" or "the official area was wrong"; "sent to the
aircraft"; any staff name from MAGMA pages; anything implying NASA, NOAA, JMA, BoM, USGS, PVMBG
or DGCA endorse TEPHRA. Added by the redesign (UI-REDESIGN R12.9): "clear", "safe", "all fine", "no
traffic", or "0" for an unseen count; "must avoid" (Policy A is illustrative); "AI unavailable" for a
solver result; "The AI could not tell" while AI is off; any paraphrase of an unknown trace line;
"deduplicated" for evidence.

### 11.10 Crew reports (exact)

| Where | Text |
|---|---|
| Area label (map, Details, Desk) | "Crew report caution area (operator policy A; not a VAA or SIGMET)" (`CREW_AREA_LABEL`) |
| Flag line | "Crew report of ash on this route" (`CREW_FLAG_LINE`) |
| Discrepancy | "Crew report outside the official area" (`CREW_OUTSIDE_LINE`) |
| Age | "reported 47 min ago" (server `age_text`) |
| States | "Active", "Covered by official area", "Expired", "Withdrawn", "Routine report, no area (sulphur smell only)", "No ash seen: no area, and it removes nothing" |
| Position | "ADS-B fix at 1039Z" / "typed by dispatcher" |
| No volcano | "no catalogued volcano" |
| Offer | "Start a message to the weather office and VAAC" |

Never: "danger area", "closed", "confirmed ash" or "ash cleared" for a crew report; never a crew
report presented as a VAA, SIGMET or TEPHRA's estimate.

## 12. Accessibility

As `docs/UI-REDESIGN.md` R15, built on the Wall as follows (the Desk keeps its own rules in 10):
1. Keyboard: every function without a pointer (section 9); no trap except dialogs and the phone
   sheet, which trap and restore.
2. Focus: always visible (`--focus-ring`, `--focus-offset`, `--focus-halo`, on every control and the
   map container); drawer and section changes move focus to the new heading and return it.
3. 12 px floor: `--fs-1` is `max(12px, 0.75rem)`; `wall.css` has no literal size under 12 px and every
   map `text-size` is at least 12 (`tests/test_ui_inventory.py` checks both).
4. Contrast: text ≥ 4.5:1 (≥ 3:1 at 24 px or 18.66 px bold), control borders and swatches ≥ 3:1;
   new pairs are in 3.3; `prefers-contrast: more` works through the tokens.
5. Colour never alone: key rows pair colour with line style, failures with the serious shape and
   words, status chips have a shape, selected states have a ring or a check.
6. Live regions: `#announce` (polite) speaks a story change at most every 30 s and only when the
   volcano, the flight count or the waiting count changes; a new failure is `role="alert"` once;
   trace lines are never announced (`role="log"`, `aria-live="off"`); the lost-stream line keeps
   `role="alert"`.
7. Semantics: `header`, `main` (story, map, time bar), `aside#details` (`role="region"`), `footer`;
   one h1 (the volcano name, or the area, or "Watched regions"); the area picker is a menu button
   (`aria-haspopup="menu"`, arrow keys, Esc); the Details index is a list of buttons; tables for the
   credits, policy, scenarios and backtest.
8. Reduced motion: every token duration is 0 except `--dur-hold`; the camera and cluster expansion
   use `jumpTo`, exposure paths are still, no pulses, no drawer slide, no count highlight.
9. Targets: 44 px for every Wall control (Details rows 48, time bar steps and buttons 44, map
   controls 44 and 40 on a phone, area menu rows 44); the time bar's event marks are 28 px (dense
   track) and are also reachable as Timeline history rows.
10. Zoom and reflow: at 200% the Wall's viewport falls into the phone or 1280 layout and nothing is
    lost.
11. Forced colours: `wall.css` ends with a `forced-colors: active` block: selected segments, menu
    rows, chips and the Details button use `SelectedItem`; borderless controls, rows, pills and the
    failure line get a `CanvasText` border; flagged cells and the picked flight get an outline; the
    swatches keep their colours (`forced-color-adjust: none`).
12. Language: plain words first, the ICAO code in brackets or mono after; every acronym shown has a
    glossary entry.

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
| Region of a volcano | the first region whose `bbox` contains the vent, else none ("All areas") |
| Area scope (R2.1) | derived on every render, never stored: `inRegion` = situations whose vent is in the chosen area; the selected volcano is the chosen one if it is in scope, else the first in scope; `regionEmpty` = an area is chosen and nothing is in it. Choosing a volcano sets the area to its region. On the first load an empty server region with ash elsewhere moves to the region of the top-priority volcano; in REPLAY the first case volcano (`state.replay.volcano_ids`) with a situation is chosen. A debug guard logs "region invariant" if the area count and the empty story ever disagree |
| Story counts | per selected volcano (`volcano_id`); the "All volcanoes" line is global |
| Waiting advisories | the server's `draft_count` for the global count; per volcano, DRAFT advisories among the 50 loaded ("at least" when that page cannot hold them all) |
| Closures for a volcano | the current (not superseded) recovery plan's closures whose `source_ids` include the volcano's official product or cone ids |
| Extension data | recovery, notices, budget and backtest reload 2 s after an SSE `state` with a new `last_tick`, with the 60 s poll as a backstop; numbers drawn from them carry their as-of time |
| Plain lines | `plainLine()` in `wall/x-parts.js`: a fixed table of patterns; unknown lines verbatim |
| Deep link | "Decide on the Desk" goes to `/desk#review/{id}` of the volcano's most urgent DRAFT (inside now, then the soonest entry); the Desk resolves it (UI-REDESIGN R10.3) |
| Priority of volcanoes | exposed count, worst severity, discrepancy count, name |
| Flight ↔ advisory | `advisory.flight_id == "<hex>:<volcano_id>"`; aircraft props carry `hex` and `volcano_id` |
| Official area label | grouped per volcano (5.1); SIGMET and VAA polygons are compared by the backend, not the client |
| Official fill | latest valid SIGMET per FIR and volcano; VAA OBS only where no SIGMET is valid (5.1) |
| Labels | official box at the arrow tip / southern vertex / northern vertex (circles on the vent); TEPHRA tag at the cone vertex farthest from it (5.1, 5.2) |
| GIBS time | section 5.6 |
| Crew picture | `WallSnapshot.crew` and the `crew` event, replaced whole; reports newest first; drawn when ACTIVE or COVERED; the server writes every state, age, place and summary word (5.7, 7.20) |
| Crew flag on a draft | `CrewPicture.flags[].hex == advisory.hex`, the draft in the current mode (10.15) |
| Reason needed | a crew flag and `action` MONITOR or CONTINUE (server `REASON_ACTIONS`) |
| Crew in the story | reports naming the selected volcano, plus reports near no active volcano (7.6) |

## 14. Video shot list

The storyboard is `docs/PITCH.md` (rows as of 10 Oct). Record the Wall at 1920x1080, browser
zoom 100%, `prefers-reduced-motion` off, after `body[data-map-ready="true"]`, with `?present=1`
(Details stays closed until opened on purpose). Every replay shot shows the REPLAY band; the
disclaimer is in every frame. The opening uses the Krakatau window of UI-REDESIGN R2.2
(`TEPHRA_REPLAY_CASE=anak-krakatau-20260905`, `TEPHRA_REPLAY_START=2026-09-05T10:30:00Z`,
`TEPHRA_REPLAY_END=2026-09-05T19:30:00Z`): the Wall opens on Anak Krakatau with flights and
advisories, and the story card carries the beat. For the disagreement beat open Details › What the
official reports say and Where the sources disagree; for the trace beat Details › How TEPHRA
decided; the decision beat is the story's "Decide on the Desk →" and the Desk's 3-tap flow. The key
block is always in the story column (there is no legend to open). Rows below that name the old
headline pill, legend, docks or rail map to the story card, the key and the Details sections. Captions that are not TEPHRA
data (news stills, the sounding) are added in the edit, not drawn by the UI.

| PITCH row | UI state needed | How to get it |
|---|---|---|
| 0:00–0:15 hook (stills) | none | edit only |
| 0:15–0:30 Wall over Java: SIGMET box; SIGMET, VONA, VAA side by side | Semeru selected, official label box visible, Details › What the official reports say open (the three source cards), no satellite layer | Replay `semeru-20260923`, `TEPHRA_REPLAY_START=2026-09-25T16:00:00Z`, stub LLM; region 1 (the 1554Z VONA is already in) |
| 0:30–0:55 badges LAG, ENVELOPE, NOT OBSERVED, DIRECTION OUTSIDE; VONA "north, ground observer, night"; SIGMET "MOV SE" | Rose visible ("135° apart"); VONA column head with "Night at the vent"; Details › Where the sources disagree with the CAUTION card and "Minor differences" open; story line L2 | Same replay. NOT OBSERVED appears only if a VONA in the window carries a non-observation; if none, the line says LAG and ENVELOPE and the voice-over must not name NOT OBSERVED |
| 0:55–1:20 trace streams; Plume Reader's card; cautious area over the official box covering both directions | Trace dock expanded (T); TEPHRA area card with "How the model read it" open; map in WIDENED mode with the hatch over the north drift | Needs a Gemini-backed run (`TEPHRA_LLM=gemini`, key in env) so the cone is WIDENED. With the stub the cone stays OFFICIAL and the shot shows "TEPHRA area = official"; do not fake it. The sounding caption is an edit overlay. Optional beat: S (compare) dragged from A to B |
| 1:20–1:50 Jakarta and Krakatau: CGK traffic through the band; two flights turn amber; drafts appear | Region Java / Bali framed on Krakatau; aircraft layer; Details › Height filter showing ticks crossing the band (H, preset "Hazard"); story L4 and L5, Details › Flights heading in with minutes; Details › Decisions showing waiting; optional D (3D) for 5 s | Live by day if a Krakatau SIGMET is open, else replay `java-live-20261010` (labelled) |
| 1:50–2:15 phone: approve one, reject one; audit line | Desk at 390x844: queue with two cards; hold-to-approve on one (show the fill), reject the other with a quick reason; toast with the audit line; then the Wall's Details › Decisions and This flight showing "Approved by …" and "Rejected by …" | Same run as the previous row; sign in with a dispatcher name (not a real person's) |
| 2:15–2:30 evaluation slide | none | deck |

Credits that must be legible when their source is on screen are in the honesty strip and the
context label (section 7.3, 5.6).

## 15. Open issues and notes for builders

- Redesign (UI-REDESIGN R19): the recovery agent still writes "NO FEASIBLE PLAN FOR THE PUBLISHED
  CLOSURE (UNKNOWN)" into `run.problems`; the Wall shows it as "No plan found: the solver did not
  finish in time…" and keeps the raw string under "Technical detail" (`planProblem()` in
  `wall/x-parts.js`). Changing the backend string is left for later.
- `ReplayInfo.volcano_ids` (additive) carries the case manifest's volcanoes; the Wall opens a
  replay on the first one with a situation.
- The stub keeps the cone OFFICIAL, so the story's L2 reads "TEPHRA's estimate has not been widened
  (AI off)" in every stub shot.
- When the basemap style fails, the map still falls back to the Natural Earth coastline (credited in
  About) and the story says so in its notes; UI-REDESIGN R14.4 asks for no fallback tiles and a
  failure line ("The map could not load: …"), which the Wall shows only when the map library itself
  does not load. Decide before the video whether to drop the coastline.
- `scripts/ui_check.mjs` is the R17.2 screenshot and DOM pass (not in CI); `tests/test_ui_inventory.py`
  is the R17.1 "nothing deleted" test (in CI), with the Desk checks (ids, tab keys and labels, no
  text under 12 px in `desk.css` and `doc.css`, no native `append` of a null in `desk/duty.js`, no
  bulk approval).
- The Desk shows the same solver wording as the Wall from its own `planProblem()` in
  `desk/network.js`; the Ask stub's "NO MODEL: this is the offline stub…" sentence stays in the API
  (tests and the spoken reply rely on it) and is put in plain words only on screen, and only for
  the stub's code-written text.
- Crew reports (5.7, 7.20, 10.15): the ivory `--c-crew` is not yet in the palette script's
  tables (3.3); the research's "stale" and "expired, needs review" steps are one EXPIRED state
  (listed for 24 h, not drawn); a report withdrawn or expired leaves the drafts it flagged as they
  are (no recheck card); the Wall's flights list shows the crew line only for flights heading into
  TEPHRA's area (a flagged flight outside it is reached from the map or Details › Crew reports).
- The decision receipt stays 15 s. On a phone it sits in the review sheet's flow under the sheet
  head (`#sheet-receipts`), so it pushes the next draft down instead of covering it; at 1440 it is
  the usual toast under the queue column.

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

## 16. Review round 2 (what changed and why)

Every count states its scope, the same words on both screens, and no raw code text sits in
primary text. In short:
- Desk › Airports before the first plan: while the trace says the closed airports changed and no
  newer plan exists (`noteTrace()` / `replanInProgress()` in `desk/network.js`, fed by `/api/wall`'s
  trace and the `trace` stream event), it says "Re-planning for WARA, WIHH, WIII…" and "Ash closes 3
  RFA airports (all volcanoes): …", never "No RFA airport is closed". Plan leads and the Decide link
  say "(all volcanoes)".
- Report counts: Details › What the official reports say names kinds, not a number ("The newest
  SIGMET and VAA (official, binding) and the observatory's VONA (supporting) name Anak Krakatau. One
  card per kind below, the newest of each."); its index row reads "newest SIGMET, VAA and VONA · 2
  min ago"; the reasons list says "Why TEPHRA shows Anak Krakatau: 8 reasons"; the Desk says "7
  sources on this draft (5 official)". This ash area says "Drawn from 2 SIGMETs (airspace warnings),
  the newest per office + 1 VAA (ash advisory)" (a VAA's layers count once).
- This ash area: forecast steps once each at their own time ("+6 h (1310Z) · +12 h (1910Z) · +18 h
  (0110Z)"); issuers in words with the code kept ("Jakarta airspace office (WIIF), SIGMET · Darwin
  ash advisory centre (VAAC), VAA"; an office not in the short list keeps its code only); product
  ids under "Technical ids".
- Plain words (`plainLine()` in `wall/x-parts.js`, now also used by `desk/duty.js`): the Duty
  Officer's stub brief, its "urgency order" reason (said once above the list), the recovery stub's
  rationale ("Planned by code (AI off): this plan cancels 47 flights and delays 29. It affects
  12,057 passengers and costs about $893,032."), and any other "NO MODEL: …" line ("Written by code
  (AI off): …"). The raw line stays under Technical detail. Desk review › Why: TEPHRA area "Official
  area only" / "Wider than the official area · 80% confidence" / "HYPOTHESIS · MONITOR or HOLD only"
  (mode code and confidence in the tooltip); the cost note in sentence case (the original in the
  tooltip); Drafted by "AI off: built from the official reports only…". Wall flight and decision
  lines: "Drafted: Keep watching (MONITOR) · waiting for a dispatcher".
- Sources grid: "FCST" reads "forecast, not seen"; an empty cell says why in the same words in every
  column ("not given", "not in a SIGMET", "no end time stated"); alert colours in words ("Red").
- Desk Next decision follows the open review: a deep link or a tapped row puts that draft in the
  card; "4 drafts are more urgent · Show the most urgent" opens the most urgent one in the review.
- Desk Escape steps back one level (confirm bar → decide bar, Reject or Edit → review, even from
  inside the text box), then on a phone closes the sheet.
- Duty Officer one-liner on the Desk keeps one noun: "25 items put in order of urgency · latest run
  1035Z" (or "3 jobs handed out · …").
- Map labels: the selected official box, forecast-step labels and TEPHRA's tag are nudged inside the
  canvas after every move (`fitLabels()` in `wall/map.js`) and wrap at 16 em on a phone; in compare
  mode each side's labels stay on their side of the divider; the flight-count bubble opens left near
  the right edge and reads "20 RFA flights here" when some flights sit outside it; active volcano
  names near a side edge open inwards.
- 3D: the camera zooms in 0.35 from the flat fit and tilts to 55°, so the areas stay as large as in
  the flat view (it zoomed out before).
- Time bar: "1030Z · 0% played" with the recording's span in the tooltip, the progress bar's
  value text and the History head ("9 h back, 3 h ahead · Recording 1030Z–1930Z, 0% played"), so the
  12 h axis never sits beside a second time scale.
- Help › Full map key: "Suggested reroute" and "Box marked on the satellite picture" (no ICAO-form
  note, no "AI-marked" while AI is off). Track record: "generated 11 OCT 1515Z" (one Z).
- Phone Details sheet: the backdrop is transparent, so the band, header and disclaimer above the
  sheet stay at full contrast. Details index statuses wrap in their own column.
