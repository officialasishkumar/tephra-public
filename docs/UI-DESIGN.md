# TEPHRA UI design spec: the Wall and the Desk

Version 3, 12 Oct 2026. Owner: lead product designer. Builders implement this document;
reviewers check the result against it. Where this spec and the code disagree, the spec wins until
it is changed here. Version 3 records the redesign ("The Story") of the Wall and the Desk: its
source and full rationale is `docs/UI-REDESIGN.md`, and the sections below describe both pages as
built from it (the Desk in 4.5-4.7 and 10.1-10.14). Version 3.1 (12 Oct 2026) adds crew (pilot)
reports of ash: the map layer (5.7), the story lines (7.6), Details › Crew reports of ash (7.20),
the flag in This flight (7.8) and, on the Desk, the "Report ash from a crew" form, the line on
affected drafts and the reason box (10.15). The backend is MODULES.md 5.19. Version 3.2 (13 Oct
2026) adds AI at work (7.21), the full overlay that shows the Duty Officer handing work to the
specialist helpers and a dispatcher deciding at the end, redesigns the Operator policy dialog
(7.18), and redesigns the Desk (10.16): one honesty band, Plan by hand as a summary and a list,
and a right pane that is never an empty box. Every AI word on both pages comes from
docs/UI-AI-QUIET.md (`aiStateOf()`), which wins where this document differs. Version 3.3 (13 Oct
2026, docs/UI-AI-QUIET.md 8.4 "Naming"): the AI is shown as one assistant, **TEPHRA Assistant**,
with skills named by job (the Duty Officer is shown as the Coordinator) and the Strata mark; "AI
helpers" is Details › TEPHRA Assistant, "AI at work" is TEPHRA Assistant at work, the Desk's "AI
today" sheet is the TEPHRA Assistant sheet, and the old "AI …" chip words and marks below read as
that section's table says. Version 3.4 (13 Oct 2026, 7.1 "Say it once, in the frame"): REPLAY is
said once, by one frame strip on the Wall and the Desk that also holds the disclaimer; the
stacked band and disclaimer bar, the Replay mode pill, the story's "Recorded" tag, the per-section
"recorded" pills, the board's own band and the Desk's per-card and per-review REPLAY tags are gone.

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
scratchpad (`…` = `<scratchpad>`):
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
4. **Honest by construction.** The disclaimer, the REPLAY label and the model label are layout,
   not decoration: they are always on screen and never collapse, scroll away or truncate. REPLAY
   is said once, in the frame strip (7.1), not again on every card and section. Credits
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
| Official ash area | Story tile "Ash up to FL500 · 50,000 ft"; the pink filled polygon with its label box "Official ash area · SFC–FL500 · until 1045Z / moving SE at 10 kt" | Story, map | The sentence and the pink shape |
| Where sources disagree | Story L2 "The sources disagree on where the ash is heading (135° apart)."; the direction rose at the vent; Details › Where the sources disagree | Story, map | The sentence and the two arrows |
| TEPHRA's area | The amber dashed outline drawn just outside the official edge with its tag "TEPHRA's estimate · same as official (AI off)"; the key row on the map "TEPHRA's estimate · never smaller than official" | Map, key | The amber dashes around the pink |
| Who is flying into it | Story hero "23 · RFA flights in or heading into TEPHRA's ash area · 19 inside now · 4 heading in"; amber planes with marching paths, one-line labels or a "23 RFA flights" cluster ("20 RFA flights here" when some planes sit outside it) | Story, map | The number and the amber planes |
| A human deciding | Story tile "Advisories 23 · to decide" (with "n for flights gone" when drafts outnumber the flights), the one notice when the AI could not draft ("Plan the 14 flights by hand on the Desk"), and the one filled button "Decide on the Desk →"; Details › Decisions | Story, Desk | The button |

A still frame of the story column explains itself (UI-REDESIGN R5, redesigned 13 Oct 2026):
`Anak Krakatau … as of 1030Z` / `Java / Bali · (Red alert) · (Recorded)` / the hero `23 RFA flights
in or heading into TEPHRA's ash area ⓘ` / `19 inside now · 4 heading in · Show them` / the tiles
`Ash up to FL500` `Airports closed 2 · WIHH · WIII` `Advisories 23 · to decide` / `[Decide on the
Desk →]` / `See the AI at work`.

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

The theme is **Basalt & Paper** (17 Oct 2026; the owner chose it over two other directions, with
grafts from both). Dark is warm basalt, light is paper and ink. Home, the demo's panels, onboarding,
the workspace, sign-in and the Guide follow the system or the reader's choice (`theme.js` writes
`data-theme` on `<html>`); the map stays on the night values in both themes (`.night`), and the Desk,
the Assistant page and the printable document's bar stay dark (`data-theme="dark"`, pinned by tests).
Rules the palette keeps:

- **Red is for real alarms only**: feeds, the database, the connection, server errors, the audit chain.
- **Solid = real and binding; dashed = an estimate, an example or something not connected**
  (TEPHRA's area, ILLUSTRATIVE, NO MODEL, EXAMPLE, SHADOW).
- **White on the map = the plan a dispatcher decides on**: the reroute, a closed airport, the picked
  flight, told apart by shape (a line with chevrons, a bar on a dark disc, a ring round a plane).
- **Violet is REPLAY only.** Amber is "TEPHRA flags this", never decoration and never the assistant.
- The volcano colour-code hues are the standard ones and never change.

Neutrals (dark set; the light set is in `tokens.css`, the paper `#f7f4ef` / ink `#1a1510`):

| Token | Dark | Light | Use |
|---|---|---|---|
| `--c-bg` | `#100e0c` | `#f7f4ef` | Page background, behind everything |
| `--c-surface-1` | `#171512` | `#fffefb` | Top bar, story column, Details drawer, footer, time bar, Desk header |
| `--c-surface-2` | `#1f1c19` | `#fbf9f5` | Cards, grid column heads, Desk cards |
| `--c-surface-3` | `#292622` | `#ede9e3` | Selected tab, hover, pressed tool |
| `--c-surface-glass` | `rgb(23 21 18 / .9)` + `--glass-blur` | `rgb(255 254 251 / .93)` | Panels floating over the map |
| `--c-scrim` | `rgb(8 6 4 / .72)` | `rgb(26 21 16 / .5)` | Behind dialogs and sheets |
| `--c-line-1` / `--c-line-2` | `#322e2a` / `#45403b` | `#e3dfd8` / `#d1cbc4` | Hairlines / panel borders |
| `--c-line-input` | `#847f7a` | `#7e7870` | Borders that identify a control (3.6:1 or better on every surface) |
| `--c-text-1` / `-2` / `-3` | `#f5f1ec` / `#cec8c1` / `#b3ada5` | `#1a1510` / `#4f4840` / `#686058` | Text (text-3 on surface-3: 6.8 dark, 5.1 light) |
| `--c-text-ink` | `#100e0c` | `#fffefb` | Text on bright fills |
| `--c-brand` | `#ffb000` | `#9b6a05` | The dashed brand tick under the wordmark and before the Home eyebrow; nothing else |

Data semantics (map and panels, one meaning each; dark values, the map keeps them in both themes):

| Token | Hex | Meaning | Text tint (dark) |
|---|---|---|---|
| `--c-official` | `#ff3d8b` magenta | Official, binding (SIGMET, VAA): solid | `--c-official-text` `#ff9cc4` |
| `--c-forecast` | `#ff3d8b` | Official forecast steps (+6/+12/+18 h): the official hue, dashed, no fill; its own token so it can be retuned alone | — |
| `--c-tephra` | `#ffb000` amber | TEPHRA flags this: its cautious area (dashed, never smaller), the RFA flights it finds entering, its timeline marks | `--c-tephra-text` `#ffc845` |
| `--c-observer` | `#a6dcff` glacier blue | Observatory: VONA, ground observer, drift arrow | `--c-observer-text` `#cbeaff` |
| `--c-crew` | `#e1c88b` parchment | Crew report caution area (operator policy A, not an official product): long dashes and a pin | `--c-crew-text` `#ecdcb0` |
| `--c-reroute` | `#f4f8fa` chalk white | The proposed reroute (dark casing, chevrons) and the picked-flight ring | `--c-reroute-text` |
| `--c-closed` | `#f4f8fa` | A closed airport in TEPHRA's plan: a white bar on a dark disc, a white "WIII closed" tag, a dashed radius. Never red | — |
| `--c-aircraft` | `#8a96a2` steel | Other airline aircraft (context) | — |
| `--c-map-context` = `--c-map-muted` = `--c-route` = `--c-aircraft-stale` | `#787671` | One context grey: FIR (dotted) and VAAC (dash-dot) lines, a usual route, a stale aircraft, code UNKNOWN, navaids; told apart by pattern and shape | — |
| `--c-code-green/yellow/orange/red` | `#2ec4a0` `#fff176` `#f2711c` `#e8273b` | Aviation colour code, only inside the eruption symbol with its letter, and next to the word. On paper a code dot gets a 1 px `--c-code-ring` | Print the word in `--c-text-1` |

Map-only (`--map-*`, never flipped): land `#14171c` (cool near-neutral) under a `--map-dot` `#9db4cc`
dot matrix at 30 %, water `#04060a`, coast, 2° grid and border in the dot tint at 28 %, 5 % and 22 %,
halo / casing `#05070a`, volcano label `--map-label` `#e2e8ee`, place, FIR and VAAC names
`--c-map-wordgrey` `#8b9db4` (6.5:1 on land), FIR with a valid SIGMET `--map-fir-active` `#c8c8d0`
(dotted, brighter), the flight-group back plane `#a26f00`, the plate edge `--map-plate-edge`.
`map.js` reads all of them with `readTokens()`; the hillshade highlight `#2f343b` and the 3D sky
`#0f1219` / `#1f242a` are literals matched to the land's hue.

Status (panels only; always shape + word; section 3.2):

| Token | Dark | Light | Meaning |
|---|---|---|---|
| `--c-ok` / `-bg` | `#4ade80` / `#0d2415` | `#15733a` / `#e3f2e4` | Feed OK, APPROVED |
| `--c-caution` / `-bg` | `#ffe566` / `#2a2306` | `#6f5c01` / `#f8f0c8` | CAUTION, a SERIOUS discrepancy (heavier edge), STALE feed, non-observation, night, a failed check |
| `--c-invalid` / `-bg` | `#ffe566` / `#2a2306` | `#6f5c01` / `#f8f0c8` | A form field or text that needs fixing: the caution triangle and the words, never red |
| `--c-serious` / `-bg` | `#ff7a6e` / `#2e100c` | `#8a1810` / `#fce8e4` | Real alarms only: a feed ERROR, the database, the connection, a server error, the audit chain |
| `--c-info` | `#b9b2a9` stone | `#5e574f` | INFO (harmless) discrepancy, estimated |
| `--c-off` | `#9a948d` | `#6e675f` | Feed off, never polled, SUPERSEDED, REJECTED, a declined airline |

Modes and decisions:

| Token | Dark | Use |
|---|---|---|
| `--c-replay` / `-text` / `-bg` / `-ink` | `#b794ff` / `#cdb6ff` / `#1d1430` / `#e3d6ff` | REPLAY only: the replay clock caption, the "From a replay" tag, the player and the timeline progress (its marks sit off the violet bar) |
| `--c-live-chip-bg` / `-text` | `#292622` / `#f5f1ec` | LIVE: a solid neutral chip; its dot is the data health (circle OK, diamond stale, octagon down) |
| `--c-shadow-chip-line` / `-text` | `#b3ada5` / `#cec8c1` | SHADOW: a dashed chip with a half disc, "Shadow · not for use" |
| `--c-illus-line` / `-text` | `#b3ada5` / `#f5f1ec` | ILLUSTRATIVE: a square mono stamp with a faint hatch; NO MODEL and EXAMPLE are dashed the same way |
| `--c-hypothesis-bg` | `#2b2620` | HYPOTHESIS banner background (text `--c-tephra-text`) |
| `--c-approve` / `-progress` / `-ink` | `#2fbf71` / `#7ef0b0` / `#04130a` | Approve button, its hold fill, its text (the Desk's action bar only) |
| `--c-reject` / `-ink` / `-text` | `#4a443e` / `#f5f1ec` / `#f5f1ec` | Reject, the Ask stop and the mic while recording: neutral stone, never red, distinct from the send white |
| `--c-ask*` | stone (`#cec8c1` ...) | The assistant has no colour of its own; amber never marks it |
| `--c-focus` | `#fbf8f3` (light `#1a1510`) | Focus ring (2 px, offset 2 px, 4 px halo `--focus-halo`) |

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
| Discrepancy | WARNING | `st-caution` | `--c-caution`, heavier edge (tone `warning`) | "SERIOUS" |
| Discrepancy | CAUTION | `st-caution` triangle with ! | `--c-caution` | "CAUTION" |
| Discrepancy | INFO | `st-info` circle with i | `--c-info` | "INFO" |
| Evidence | OBSERVED_SAT / OBSERVED_GROUND | `st-ok` | `--c-ok` | "Ash seen by satellite" / "Ash seen from the ground" |
| Evidence | ESTIMATED, NO_VA_EXPECTED, FORECAST_NOT_AVAILABLE | `st-info` | `--c-info` | section 11.3 |
| Evidence | NOT_OBSERVED, NOT_IDENTIFIABLE, NIGHT_BLIND | `st-caution` | `--c-caution` | section 11.3 |
| Evidence | STALE / UNKNOWN | `st-stale` / `st-off` | caution / off | section 11.3 |
| Advisory | DRAFT | `i-clock` | `--c-text-2` | "Awaiting dispatcher" |
| Advisory | APPROVED | `i-approved` circle-check | `--c-ok` | "Approved" |
| Advisory | EDITED | `i-approved` + `i-pencil` | `--c-ok` | "Approved with edits" |
| Advisory | REJECTED | `i-rejected` circle-x | `--c-text-2` (a decision, not an alarm) | "Rejected" |
| Advisory | SUPERSEDED | `i-superseded` dashed circle | `--c-off` | "Replaced by a newer draft" |
| Flight | inside the area now | `st-inside` ring with dot | `--c-tephra` | "INSIDE NOW" |
| Trace actor | code / gemini / adk / stub / human / system | `i-code` / `i-model` / `i-agent` / `st-never` / `i-user` / `i-system` | neutral; human `--c-ok` | "CODE" / "GEMINI" / "ADK" / "NO MODEL" / "HUMAN" / "SYSTEM" |
| Form | a field or text that needs fixing | `st-caution` | `--c-invalid` | the words, e.g. "Three letters, A to Z." |
| Form | offline or a server error on submit | `st-serious` | `--c-serious` (`.err--alarm`, `.msg--serious`) | what failed |
| Airport | closed in TEPHRA's plan | `st-closed` ring with bar | `--c-closed` | "WIII closed" / "Closed airport" |
| Check | a failed backtest check, cancelled flights, a FAIL scorecard | `st-caution` | `--c-caution` (tone `warning`) | the count and the words |
| Mode | LIVE / SHADOW / ILLUSTRATIVE, NO MODEL, EXAMPLE | health dot / half disc / none | solid neutral / dashed / dashed | "LIVE" / "Shadow · not for use" / the label |

### 3.3 Colour-vision and contrast evidence

Method: Machado et al. 2009 dichromacy matrices at severity 1.0, CIEDE2000 on the simulated
colours (`tools/cvd.py`), WCAG 2.2 ratios (`tools/contrast.py`), re-run on the Basalt & Paper
`tokens.css` on 17 Oct 2026 (the theme work's `final/CHECKS.md`; the navaid and active-FIR greys
re-checked after the map was applied).

Map colours, smallest CIEDE2000 across normal, protan, deutan and tritan vision (10 or more is
clearly distinct; under 10 a second channel must carry the difference, and does). Every pair that
includes a colour this theme chose is 10.5 or more apart; the only pairs under 10 are between the
fixed hues the owner keeps:

| Pair | normal | protan | deutan | tritan | min | Second channel |
|---|---|---|---|---|---|---|
| official `#ff3d8b` vs code GREEN `#2ec4a0` | 77.9 | 31.4 | 7.6 | 73.2 | **7.6** | polygon vs eruption symbol, letter G |
| official vs code ORANGE `#f2711c` | 35.2 | 39.5 | 20.2 | 8.1 | **8.1** | polygon vs symbol, letter O |
| code ORANGE vs code RED `#e8273b` | 22.3 | 20.2 | 10.6 | 9.3 | **9.3** | letters O/R, symbol size |
| crew `#e1c88b` vs code GREEN | 30.8 | 10.5 | 19.2 | 43.1 | **10.5** | long dashes and pin vs symbol |
| tephra `#ffb000` vs code ORANGE | 21.7 | 15.4 | 10.5 | 14.2 | **10.5** | dashed area vs symbol |
| crew vs code YELLOW `#fff176` | 13.2 | 12.4 | 11.1 | 10.8 | **10.8** | — |
| FIR with a SIGMET `#c8c8d0` vs nearest (every map colour) | | | | | **10.8** | dotted line |
| tephra vs code YELLOW | 20.7 | 13.2 | 10.9 | 20.2 | **10.9** | letter Y |
| tephra vs crew | 15.7 | 13.0 | 12.8 | 10.9 | **10.9** | short vs long dashes, pin |
| observer `#a6dcff` vs code GREEN | 28.9 | 28.2 | 22.3 | 12.0 | **12.0** | arrow vs symbol |
| aircraft `#8a96a2` vs code GREEN | 26.6 | 20.3 | 12.7 | 19.9 | **12.7** | plane vs symbol |
| official vs aircraft | 33.4 | 12.9 | 17.5 | 30.8 | **12.9** | — |
| observer vs REPLAY `#b794ff` | 22.1 | 17.3 | 13.9 | 28.9 | **13.9** | (text tints 11.8) |
| observer vs reroute / closed / picked `#f4f8fa` | 16.6 | 14.0 | 16.6 | 20.1 | **14.0** | — |
| official vs context grey `#787671` | 31.9 | 14.4 | 14.3 | 28.7 | **14.3** | — |
| reroute / closed / picked vs code YELLOW | 27.6 | 28.1 | 27.8 | 14.7 | **14.7** | — |
| aircraft vs context grey | 14.8 | 15.1 | 14.9 | 16.5 | **14.8** | — |

Same hex by design, told apart by shape: official = forecast (solid with fill vs dashed, no fill);
reroute = closed = picked ring (a line with chevrons, a bar on a disc, a ring round a plane); route =
stale = FIR = VAAC = navaid (one context grey: a thin line, a muted plane, dotted, dash-dot, a small
ring with its ident).

Contrast on the night basemap (land `#14171c` / water `#04060a`): official 5.38 / 6.08, tephra 9.80 /
11.07, observer 12.23 / 13.81, crew 10.98 / 12.39, aircraft 5.96 / 6.73, reroute and closed 16.81 /
18.98, REPLAY 7.44, context grey 3.96 / 4.47, code RED 4.09 / 4.62 (2.77 on land under protanopia, so
the eruption symbol keeps its dark outline and letter). Text on the map: 6.48 (place names) to 16.8
("WIII closed"); glass pills 16.2. Land vs water for video: a 14.5 code-value luma gap (it was 9.0).

Over satellite imagery (Ash RGB colours approximated from the EUMeTrain quick guide, composited at
the app's 0.55-0.75 opacities): the official and TEPHRA lines get a double casing while imagery is on
(`<id>-halo` 1.5 px `--map-halo` and `<id>-case` 1 px `--map-label` at 70 %); every one of 24 cases
then reaches 3:1 (worst 3.36). With the dark casing alone 5 of 24 fail. Re-check on real imagery.

Panels (WCAG, both themes; 204 of 204 pairs pass): text-3 on surface-3 6.77 dark / 5.10 light; the
input line on surface-3 3.80 / 3.61; focus on bg 18.2 / 16.5; REPLAY text on its chip 9.82 / 6.74;
reject ink on the stone fill 8.54 / 7.05; `--c-invalid` on its background 12.41 / 5.70. The light
brand tick on paper is 4.29 (a mark, 3 needed).

Status pairs under CVD that collide (always shape + word): caution vs code YELLOW 2.5 (protan; no
caution hue can sit 10 from both code YELLOW and TEPHRA amber and still read as caution, so caution is
always the triangle and the word, the code always a dot and the word); caution vs TEPHRA text 4.5
dark (deutan) and 0.9 on paper (protan), never in the same component; ok vs serious 5.3 (deutan);
serious vs caution and invalid 16.8 dark, 6.4 on paper (deutan).

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

The story's lead line (the Wall's largest text, the flights): 28 px at 1600 px and up, 24 at
1360-1599, 22 at 601-1359, 20 on a phone (`--story-size` in `wall.css`; `--fs-story` 24 px and
`--lh-story` 1.25 in `tokens.css`), semibold, the number in `--c-tephra-text`. The other story lines
are body size, `--story-body` 17 / 16 / 15 / 16 px, with quieter `--fs-2` sub-lines. Drawer section titles
`--fs-5`, drawer body `--fs-3`, key rows, trust line and Details rows `--fs-2` (`--fs-3` at 1920),
drawer group headers `--fs-1` caps; the story eyebrow is sentence case (name `--fs-4` bold, the rest
`--fs-2`). Map canvas labels are at least 12 px.

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
y 0    ┌─ frame strip 32: "◷ Replay · recorded feeds from 05 Sep 2026 · not live" ……… "ⓘ Decision support only - …" ┐
y 32   ├─ top bar 56: TEPHRA · sub-line · (Live) · Area ▾ ……… AI chip · Data chip · clock · Desk → ──────┤
y 88   ├─ story 460 ─────────────┬─ map 1460 (980 with Details open) ─────────────┬─ Details 480 (open) ─┤
       │ failure line (if any)   │ official label box (selected volcano)          │ (pushes the map;     │
       │ eyebrow · hero number   │ map key card (top left, folds to its bar)      │  the story stays)    │
       │ three fact tiles        │ pink area, amber dashed estimate, amber planes │                      │
       │ one notice (if any)     │ name-only labels for other volcanoes           │                      │
       │ [Decide on the Desk →]  │ pills bottom-left        Fit · Layers · ± ·  © │                      │
       │ See the AI at work      ├─ time bar 52: mode · scrubber · Forecast · ‹ › · History ───────────────┤
       │ All volcanoes + 3 rows  │                                                │                      │
       │ [☰ Details]             │                                                │                      │
y 1048 ├─ footer 32: RFA line · credits · Policy A · Help · About · Privacy ──────────────────────────────┤
```

- Rows: frame strip 32 (always: live it holds the disclaimer alone), bar 56, stage `1fr`, footer 32. Stage columns: story 460, map
  `minmax(0, 1fr)`, drawer 0 or 480 (animated over `--dur-4`, a cut under reduced motion). The map
  column is the map plus the 52 px time bar. A 24 px fade runs from the story column into the map.
- The story never scrolls at desktop widths in the Krakatau case: a fit pass (`fitStory()` in
  `wall/story.js`, review 2 item 4) raises `#story[data-fit]` from 0 to 8 until the content fits,
  each step tightening, never removing: 1 tighter rhythm; 2 the hero number smaller; 4 the tiles
  and the notice closer; 6 the other-volcanoes rows fold into "+ n more" (rows are given back while
  they still fit); 7 the Details button on one line (its sub-line stays in its tooltip); 8 the
  tightest rhythm and the smallest hero number. The map key is on the map (7.5). It re-runs when the story's words, the fonts or the column's own box
  change: a ResizeObserver on `#story` measures again once the column settles, because at
  1360-1599 px it comes back from under Details at the drawer's width and narrows while the stage
  animates (a pass on that render once left "+ 3 more" under the pinned button). Only if level 8
  still overflows does the column scroll (`.story--scrolls`, with the fade above the pinned
  button). Measured 13 Oct 2026 with the live state (AI paused, 14 flights, 3 closures, no airport
  plan): 1920x1080 and 1440x900 fit at level 0 with two other-volcano rows shown.
- Framing pads 48 px (7.4), max zoom 8.6.

### 4.2 Wall at 1440x900

Root 15 px. The same structure: story 400, map about 1040 x 732, the brand sub-line "Volcanic-ash
decision desk" shown (hidden under 1200 px), the zoom buttons hidden (wheel, pinch and keys still zoom), the footer's airline line
in full. Details takes the story column's place at 480 px (the map shrinks to about 960 px and is
never covered), with the story strip on top; the key stays on the map. The other-volcanoes
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
were fixed). Sticky (about 110 px, 13% of the screen): the frame strip in two short 12 px lines
("◷ Replay · recorded feeds from 05 Sep 2026 · not live", then the disclaimer; live, the disclaimer
alone), then the header in one row: brand, mode pill (live only), clock, "Desk →". Under it, not sticky,
`#phone-bar`: the native area picker ("Java / Bali · 2"), the AI chip and the Data chip (wall.js
moves these three nodes there on a phone and back at wider widths). Then: the failure line, the story card (20 px lines, full-width "Decide on
the Desk →"), the map (42vh, min 300; Fit and Layers as 40 px icons in a row; the time pill "⟲ 1030Z · Now
▾" bottom-left opens the full time bar as a bottom sheet), the map key as one folded bar, All
volcanoes with every row, "☰ Details" (a full-screen sheet below the header, with "‹ Details" and
Close), then the footer. A sticky bottom call to action "Decide on the Desk (23) →" (or "Open the
Desk" at secondary weight) shows only while the story's own button is out of view
(IntersectionObserver); the page has `padding-bottom: calc(56px + env(safe-area-inset-bottom))`.
Compare is not offered; 3D is in Map layers. The old phone tabs (`#ptabs`) are gone: their content
is in Details.

### 4.5 Desk at 390x844 (primary)

```
┌ sticky header ─────────────────────────────────┐
│ TEPHRA      [AI paused]  ● Connected      (AK) │ 48
│ REPLAY: recorded real feeds from 05 Sep 2026   │ one band, 40
│ Decision support only - fictional airline - …  │ (REPLAY line only in REPLAY)
├────────────────────────────────────────────────┤
│ Decide                                     ⋯   │
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
│ ┃ ⚠ Plan by hand · 23 flights         Why ›    │ │ when any (10.16), caution
│ ┃ No AI plan for these flights: AI paused …  │ │
│ ┃ 12 inside the ash now · 11 heading in      │ │
│ ┃ [ Show the 23 flights › ]                  │ │
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
  bottom hairline. On a phone the AI chip reads "AI on", "AI off", "AI paused" or "AI · 1
  problem" (the time is in its `aria-label` and shows above 420 px), and the connection is always
  a word.
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

Header full width: row 1 (48) brand left, then the AI chip ("AI paused · 0700Z real time",
10.16), "Connected" and the account button, under the frame strip (32, 7.1: the header's top row,
as on the Wall) with the violet REPLAY part on the left and the disclaimer on the right; the tab bar (48, four 148 px tabs with icon, word and
badge) under the header. Below: two
panes inside a 1280 max-width frame: Decide 420 wide on the left (the Next decision card, then the
compact rows; the selected row is outlined in `--c-line-input` with a 3 px left bar, and the Next
decision's button gets a ring when its draft is the one in the pane), the review pane on the right
(fluid, max 760) with "Why this advisory" open and the action bar at the pane's bottom. The most
urgent draft is selected on load. With no draft, the right pane holds the flights to plan by
hand (`#fail-pane`, 10.16) when there are any, else the idle pane (`#idle-pane`): what the Desk
waits for and where the other work is. Ask, Airports and Paperwork are one centred column, max
880.

## 5. Map symbology

Basemap: the night basemap (`wall/basemap.js`, 13 Oct 2026), shared by the Wall, the flow board
and the Desk map: OpenFreeMap `dark`, tuned after `load` (each call guarded with `map.getLayer`).
Land is a dot matrix: the style's `background` drawn with `land-dots` (an opaque 5 px tile, a soft
`--map-dot` dot at 30 % over `--map-land` `#14171c`), the sea `--map-water` `#04060a` over it, a
`coast` line (`--map-coast`) and a faint 2° `graticule` (`--map-grid`) under it. Roads, rail,
buildings, residential and wood land use, waterways and water names are hidden (none helps read
ash); parks and land cover at 0.12; country names in spaced capitals and city names in
`--map-label-minor` (6.5:1 on `--map-land`); suburbs and villages hidden; the board and the Desk keep
country names only. Map controls (`mapui.css`): one column of 40 px glass icon buttons, each naming
itself beside it on hover and focus: zoom, Fit, Satellite (infrared on or off), Compare, 3D and
Layers on the Wall (a phone keeps Fit and Layers); a pressed or open button is solid.

Airports (13 Oct 2026, `GET /api/airports` once): every catalogue airport a small `--c-text-2`
dot, its code from zoom 6; each airport the current airport plan closes a white ⊘ (17 Oct 2026, never red: a closure is
the plan, not an alarm): a `--c-closed` ring on a `--map-halo` disc (`airport-dot`) with the
`closed-airport` bar on top (`airport-closed-bar`), its closure radius (`Closure.radius_nm`) a
dashed `--c-closed` circle at 0.55 (dash [3,3], `closure-ring`) over a 4 % fill (`closure-area`),
its code in white beside it, from zoom 6.5 a white "WIII closed" tag. Above the ash fills, beneath
the planes; selecting a closed one opens Details › Airport closures. Map layers › Airports turns
them off; the map key adds "Closed airport" (`st-closed`, "TEPHRA's plan · dashed: its closure radius") while one is drawn; the full key in Help always lists it. If the
catalogue does not load, a caution pill says so and links Airport closures. The Desk map draws the
same closed-airport marks. The style's
`ne2_shaded` raster is added as `ne2-relief` under `water` with the terrain switch (saturation -1,
contrast 0.15, brightness-max 0.45, opacity 0.5, maxzoom 8); add
Mapterhorn `raster-dem` (`https://tiles.mapterhorn.com/{z}/{x}/{y}.webp`, terrarium, tileSize
512, maxzoom 12, attribution "© Mapterhorn") and a `hillshade` layer before `waterway` (minzoom
5, exaggeration 0.45, shadow `#000000`, highlight `#2f343b`, accent `--map-halo`). Handle
`styleimagemissing` with a 1x1 transparent image (the dark style asks for `circle-11`).

Layer order, bottom to top (all after the basemap unless noted):

| # | Layer id | Type | Source / filter | Paint and layout |
|---|---|---|---|---|
| 0 | `ne2-relief`, `hillshade` | raster, hillshade | style `ne2_shaded`; Mapterhorn `dem` | terrain shading inside the basemap (paragraph above); toggle "Terrain shading" in Layers |
| 1 | `gibs` | raster | GIBS (5.6) | inserted before `water_name`; opacity 0.6 (Air Mass 0.55); IR: saturation -1, contrast 0.2 |
| 2 | `so2` | raster | GIBS TROPOMI | before `water_name`; opacity 0.7 |
| 3 | `btd-<id>` | raster (image) | `overlays.btd[*]` corners | before `water_name`; opacity 0.75 |
| 4 | `fir-line` | line | `/static/data/firs.geojson` | `--map-fir` (the context grey), 1.2 px, dotted [1,2.5] |
| 5 | `fir-active` | line | FIRs named in a valid SIGMET id (`SIGMET:<FIR>:…`) | `--map-fir-active` `#c8c8d0`, 1.6 px, dotted [1,2] |
| 6 | `fir-label` | symbol | firs, minzoom 5 | line placement, spacing 700, `label` ("WAAF UJUNG PANDANG FIR"), Noto Sans Regular 12, letter-spacing 0.08, `--map-label-fir`, halo 1.5; FIR and VAAC lines are off by default (Map layers) |
| 7 | `vaac-line` | line | `/static/data/vaac_aor.geojson` | `--map-vaac`, 1.2 px, dash [6,3,1,3]; label "DARWIN VAAC" / "TOKYO VAAC" like FIRs |
| 8 | `navaid` | circle + symbol | `/static/data/navaids.geojson`, minzoom 8 | 3 px ring `--map-navaid` (the context grey); ident 12 px; off by default |
| 9 | `tephra-fill` | fill | cones, `part == cone` | `--c-tephra` 0.07 (dimmed 0.03) |
| 10 | `tephra-hatch` | fill | cones, `part == sector` | `fill-pattern` hatch image (section 5.2), opacity 1 (dimmed 0.4) |
| 10a | `crew-fill` | fill | `crew`, `feature == area` (5.7) | `--c-crew` 0.06; beneath every official layer |
| 10b | `crew-line` | line | `crew`, `feature == area` | `--c-crew` 1.4 px at z4, 2.2 px at z8, dash [6.5,2.7] (longer than TEPHRA's), opacity 0.95; beneath the official fills, so an official area is never covered |
| 10c | `route-line` | line | `routes`, `feature == line` (`WallSnapshot.routes`, plus `/api/routes/{origin}/{dest}` for the picked flight) | a flight's usual route, origin to destination (VRS standing data, not the filed flight plan), one line per pair of airports (both directions share it): `--c-route` (a muted cool neutral), 1.2 px at z3 and 1.5 px at z8, opacity 0.36 at z3 and 0.26 from z5; the picked flight's 1.8 / 2.2 px at 0.8 / 0.75, and while it is drawn the others step back to 0.16 / 0.13; great circle, round caps, no arrows, no animation. Inserted above the basemap's roads and borders and beneath its place names, so beneath every TEPHRA layer (crew areas, official areas, TEPHRA's line, the dashed path). Only the RFA flights in or heading in and the picked flight; Map layers "Flight routes" (on by default) |
| 10d | `route-end` | circle | `routes`, `feature == airport` | a filled `--c-route` dot (r 2.2 at z3, 3 at z8; the picked flight's 3 / 4) with a 1.2 px `--map-halo` ring, unlike the basemap's hollow town dots |
| 10e | `route-end-label` | symbol | `routes`, airports not of the picked flight | the code ("WIII", Noto Sans Regular 11, `--c-text-3`) in a small tag (`box-route`: dark fill, 1 px `--c-route` border at 0.5), so it reads as an airport, not a town name. Placed last: after every TEPHRA label, the place names and the invisible `route-avoid-*` copies of the planes and their rings, the eruption symbols, the entry markers, the dashed paths and the area outlines, so a code never sits under a plane or across an outline; it drops out instead |
| 10f | `route-end-label-sel` | symbol | `routes`, the picked flight's two airports | Noto Sans Bold 12, `--c-text-1`, tag `box-route-sel` (full `--c-route` border); always shown, drawn above the planes, placed just before the flight count (the count moves to another side and, when every side collides, is drawn anyway; the flight labels and other volcanoes' names give way), above or below the airport first; an invisible copy of the eruption symbols (`route-avoid-volcano-sel`) keeps it, and the count where it can, off them |
| 11 | `official-fill-now` | fill | official, step `now`, shown, `fill == true` (5.1) | `--c-official` 0.14 (dimmed 0.07) |
| 12-14 | `official-fill-f6/f12/f18` | fill | steps | 0.05 / 0.035 / 0.025 |
| 15 | `official-line-now` | line | step `now` | 2.6 px at z8 (1.6 at z4), solid, join round |
| 16-18 | `official-line-f6/f12/f18` | line | steps | 2 px dash [4,2] op 0.9; 1.8 px dash [2,2] op 0.75; 1.8 px dots [0.1,2] round cap op 0.6 |
| 19 | `tephra-line` | line | cones, `part == cone` | `--c-tephra` 2.6 px at z8 for the selected volcano, 1.4 px for the others, dash [3,2], `line-offset: -5` (outset), join round |
| 20 | `exposure-path` | line | exposures, `kind == path` | `--c-tephra` 2.4 px dash [1.5,1.5]; marching (5.4) |
| 21 | `exposure-entry` | circle | `kind == entry` and `minutes_to_entry > 0`, minzoom 8 | r 5, fill `--map-halo`, stroke `--c-tephra` 2.5 (no marker for a flight already inside); zoomed out the markers piled up on the area's edge |
| 21b | `exposure-entry-sel` | circle | same, and the picked flight's, maxzoom 8 | the same marker for the picked flight below zoom 8 |
| 21a | `crew-path` | line | `crew`, `feature == path` | a flagged flight's projected track into a crew area: `--c-crew` 1.8 px round dots [0.1,2.2]; follows "Flight paths into the area" |
| 22 | `exposure-entry-label` | symbol | same filter | "+12 MIN", Noto Sans Bold 13, `--c-tephra-text`, offset [0,-1.3] |
| 23 | `volcano-inactive` | symbol | `active == false` | hollow eruption icon 0.5, opacity 0.8; name from z7.5, 12 px `--map-label-minor` |
| 24 | `volcano-active` | symbol | `active == true` | eruption icon by code (5.3); name Noto Sans Bold 14 (16 selected), `--map-label`, halo 2; left out for a non-selected volcano whose area label already names it |
| 24a | `crew-pin` | symbol | `crew`, `feature == pin` | the canvas pin `crew-pin` (ivory, dark outline and centre), anchor bottom at the report position, allow overlap; above every area, under the planes and labels |
| 25 | `aircraft-icon` | symbol | aircraft that are not in or heading into TEPHRA's area, and the picked flight | SDF plane (5.3) |
| 25a | `exposed-icon` | symbol | `exposed-pts`, not clustered | the same plane for RFA flights in or heading in; six or more within 60 px are drawn as one `exposed-cluster` box instead (up to zoom 8). The picked flight is never clustered |
| 26 | `aircraft-picked` | circle | `picked` | r 17, stroke `--c-reroute` 2.5 (white = the plan; text-1 sat 9.0 from code YELLOW under tritanopia, the cool white 14.7), no fill: the only ring on the map. "Inside now" is said by the flight's label, not by a ring (a busy airport was a pile of circles); drawn beneath the group markers |
| 27 | `exposed-cluster` | symbol | `exposed-pts` (clustered: radius 60, min points 6, up to zoom 8) | the flight-group marker `ac-group-<n>` (images.js: an upright plane in `--c-tephra`, one in `--map-flight-back` behind it, the count in an amber badge at the top right; drawn on `styleimagemissing`), centred on the planes it stands for, allow overlap, labels give way to it; the click area adds 6 px on every side; a click zooms in. Map key: "Six or more RFA flights close together" (`lg-flight-group`) |
| 28 | `aircraft-label-exposed` | symbol | `exposed-pts`, not clustered, minzoom 6 | one line "RFA1225 · inside" / "RFA6178 · in 12 min", Bold 13, right of the plane, collides; the picked flight's (`aircraft-label-picked`) is placed before the other flight labels, after the group markers, on a free side of its plane |
| 29 | `aircraft-label` | symbol | not exposed, minzoom 7.5 | "GIA123 FL350", Regular 12, `--c-text-3`, optional |
| 30 | `official-step-label` | symbol | `official-labels`, kind `step` | "Forecast for 0000Z (+6 h)" while a forecast step is chosen; collides |
| 31 | `official-label` | symbol | `official-labels`, kind `name` | other volcanoes: the name only, 12 px `--c-official-text`, above the area's northern vertex; collides (sort key 10) |
| 31a | `crew-label` | symbol | `crew-labels` (5.7) | one line of haloed `--c-crew-text` text, no box, beside the pin on the side towards the middle of the map and nudged inside the canvas; moved beneath the volcano layers, so every other label (volcano names, flight labels and count, area labels) is placed first and wins |
| 31b | `aircraft-label-crew` | symbol | `aircraft`, `crew_only == true`, minzoom 6 | "RFA4538 · crew report" in `--c-crew-text`, one line, right of the plane, colliding |
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
| Picked | the viewer chose it on the map or in Flights heading in (7.8) | unchanged + `--c-reroute` ring, 2.5 px | unchanged | details in Details › This flight |
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
- Reroutes are drawn only for the picked flight, unless Map layers turns them all on: a white
  `--c-reroute` line on a 6 px dark casing with white chevrons along it (`reroute-chev`, the
  `chevron` SDF in `images.js`) that give its direction.
- One context grey (`--c-map-context` `#787671`) for FIR, VAAC, routes and navaids, told apart by
  pattern: FIR dotted, VAAC dash-dot, a route a thin solid line, a navaid a small ring.
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
| SO2 | `TROPOMI_L2_Sulfur_Dioxide_Total_Vertical_Column` | `GoogleMapsCompatible_Level6` | 6 | `YYYY-MM-DD` | "CONTEXT ONLY · SO2 (TROPOMI, daily) 25 Sep 2026 · SO2 is not ash, gases not modelled · Imagery: NASA GIBS · Contains modified Copernicus Sentinel data 2026" |

URL template: `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/{layer}/default/{time}/{matrix}/{z}/{y}/{x}.png`
(note `{y}` before `{x}`), `tileSize: 256`.

While satellite, SO2 or BTD imagery is on, the official and TEPHRA lines get a double casing
(17 Oct 2026, section 3.3): `<id>-halo` 1.5 px `--map-halo` next to the line and `<id>-case` a 1 px
`--map-label` hairline at 70 % outside it. Under a dashed line the casing is solid (a dashed casing
cannot follow MapLibre's dashes as the width changes with zoom).

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
- Label (`crew-label`): one short line, "Crew report · 47 min ago" ("Crew report · covered by
  official area" for a COVERED report), haloed text with no box, beside the pin on the side
  towards the middle of the map, nudged inside the canvas (`fitLabels`), colliding and placed
  last, so it never covers a volcano name, a flight label or an area label. The full label, band
  and flight are in Details › Crew reports of ash.
- Flagged flights: an RFA flight only a crew report flags (`crew_report` and not `exposed`;
  `crew_only` in `derive`) is an RFA plane in the crew colour, never a grey "other aircraft":
  large like the exposed planes, labelled "RFA4538 · crew report" from zoom 6
  (`aircraft-label-crew`), kept by the height filter, and listed in Details › Flights heading in
  under "n more RFA flights on the route of a crew report of ash", so This flight opens from
  there. A flight in TEPHRA's area keeps its amber plane. There is no ring. A flight that will
  enter later gets the dotted ivory path to its entry point (`crew-path`).
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

Since 16 Oct 2026 the Wall is the demo at `/demo`, and its frame is 7.32: the header assistant chip
(7.2), the Details drawer beside the story (7.19), the panel toggle, the phone page scroll with
its sticky call to action and the Details sheet are gone. The sections below still describe the
parts that stayed (the map, the story, every Details section, the dialogs).

The Wall is built as `docs/UI-REDESIGN.md` ("The Story") describes; this section records what was
built and where. The code is `index.html`, `wall.js` (state, stream, actions, keyboard, drawer
placement), `wall/story.js` (story column), `wall/details.js` (Details drawer), `wall/panels.js`
(top bar, footer, time bar, section builders, dialogs), `wall/ext.js` (satellite, notices, airport
plan, track record, AI helpers), `wall/duty.js`, `wall/controls.js` (layers, Help, About),
`wall/map.js` and `wall/ext-map.js` (the map), `wall/x-parts.js` (shared parts and `plainLine`).

Structure (R3): `body.wall` is a grid of four rows: the frame strip, the top bar, the stage and the
footer. The stage is a grid of three columns: the story (`#story`), the map column (`.mapcol`: the
map, then the slim time bar) and the drawer (`#details`, 0 px wide while closed). Nothing floats over
the map except its labels, the status pills (bottom-left), the map controls and the attribution
(bottom-right), and the compare labels in compare mode. The body never scrolls at 601 px and up;
the story column and the drawer scroll inside themselves.

### 7.1 The frame strip: REPLAY said once (13 Oct 2026)

**Removed 15 Oct 2026, at the owner's request.** The strip (`#frame` on the Wall and the Desk,
`.tn-strip` on Connect and the guide) is gone from every page, with its `--frame-px` and
`--dframe-h` offsets. REPLAY is now said by each page's title ("REPLAY - TEPHRA Wall"), the Wall's
clock ("Replay clock"), its time bar's replay mark and its status dot, and every modal's sr-only
description (`replayLine`, `replayModalWords`). The disclaimer's words stay in the server state and
About; the fictional airline is in the status line's tooltip. The rest of this section is the
record of what the strip was.

"Too many mentions of replay everywhere": a violet band stacked over a separate disclaimer bar, a
"Replay" mode pill, "Recorded" on the story, "recorded" pills on most Details sections, a second
band on the board, REPLAY tags on Desk cards and reviews. CLAUDE.md's "REPLAY is always labelled"
needs one label that is always visible, so the label is said once, in the frame.

`#frame` (`role="note"`, named by `stripLabel()`: "Replay notice and disclaimer" in REPLAY,
"Disclaimer" live), one slim strip above the top bar (32 px; 28 at
1280): on the left, in REPLAY only, `#replay-banner` (`.frame__replay`, the only violet: the
`i-replay` icon, "Replay · recorded feeds from 05 Sep 2026" in `#replay-banner-text`, then " · not
live"); on the right the info icon and `#disclaimer`, verbatim from `state.disclaimer`. Live, the
disclaimer alone. The words come from `replayWords()` (wall/x-parts.js), shared with the Desk; the
date is the recording's first day (UTC). The case title, and "switched automatically: no live
activity" when it was, are in the REPLAY part's tooltip and, for screen readers, in the sr-only
`#replay-banner-case`; About shows the case in words for touch screens.

On a phone the strip is sticky at the top in two short 12 px lines (the REPLAY part, then the
disclaimer), and the header sticks below it (`--frame-px`, measured by wall.js). The strip is never
covered or dimmed: the board, Help, About and the other dialogs open below it with their backdrop
starting there, and the phone Details sheet starts below the header. A modal makes the strip inert
for screen readers, so each modal (the board, `#dlg`, the Details sheet, the Desk's `#bsheet` and
`#display-dialog`) carries the strip's REPLAY words as sr-only text in its `aria-describedby`
(`describeReplay()` in wall/x-parts.js); live, none. Nothing visible is added.

The Desk's strip is the same strip (same classes, sizes, icon and words), the top row of its sticky
header above the brand row, so it reads as a label and never sits next to the tab bar (10.16).

Kept, because each says something the strip does not: the clock's "Replay clock · 5 Sep · UTC"
(which time you see); the time bar's replay icon with the time and "9% played" (the word "Replay"
went); `document.title` "REPLAY - TEPHRA Wall"; reasons ("Not in this recording.", "Off: no PVMBG
permission (replay only)", "No aircraft data in this recording."); Technical detail and
tooltips; Help, About and the glossary; and at data level documents, advisory and message headers
written by code, audit and outbound records. A record whose mode differs from what plays (a
replay record seen while live feeds play) keeps one tag, worded "From a replay" on both pages
(`dkFromReplay` on the Wall, `fromReplayChip` on the Desk): Details rows, feed rows, crew reports,
and on the Desk the Next decision, the review ("From a replay · Drafted while a replay played, not
from live feeds", for a replay draft opened from a link while live feeds play), Ask answers,
messages, notices, airport plans and crew reports. Decide lists only the drafts of the mode playing,
and a set-aside draft opened from a link never becomes the Next decision.
Before the Desk has read the state the mode is unknown and no tag shows. Nothing else in the main
views repeats the label.

### 7.2 Top bar

`header.cmdbar`, 56 px (48 at 1280), never clipped (`scrollWidth <= clientWidth` at every width in
R17.2). Left to right:
1. Brand "TEPHRA"; the sub-line "Volcanic-ash decision desk" only at 1600 px and up.
2. Mode pill `#mode-badge`: "Live" (green, live icon), "Replay" (violet, replay icon),
   "Connecting…".
3. Area picker: `#area-btn` "Java / Bali · 2 with ash ▾" (its name, "Area: Java / Bali · 2 with
   ash", is the aria-label; 17 Oct 2026) opens the menu `#regions`
   (`role="menu"`, `menuitemradio` rows "Halmahera · 2 with ash", "Kyushu · none", "All areas"; the
   current one checked; arrow keys, Home/End, Esc). Keys 1-9 still choose areas. On a phone the
   native `#region-select` replaces it ("Java / Bali · 2"). The counts come from one active list
   (the server's `active_volcano_ids` plus any situation card, by vent), the same list as "n with
   ash" in All volcanoes, so the picker and the story never disagree. Before the server's first
   tick an area with nothing yet reads "· reading…", never "· none".
4. Spacer.
5. Assistant chip `#ai-chip` (button) with `#model-chip` as its text and the Strata state mark:
   TEPHRA Assistant's one state from `aiStateOf()` (`wall/x-parts.js`, shared with the Desk and
   the board), "TEPHRA Assistant · on", "TEPHRA Assistant · paused", "TEPHRA
   Assistant · Recovery planner gave no result" or "TEPHRA Assistant · off (code only)" ("Assistant ·
   paused", "Assistant · 1 problem" at 420 px and less), never red and never a count of failed
   steps or a model id (docs/UI-AI-QUIET.md 8.4). A pause carries no reason and no time, in the
   chip or its tooltip ("TEPHRA Assistant is paused: see why in Details › TEPHRA Assistant."); the
   cause is said once, at Details › TEPHRA Assistant (docs/UI-AI-QUIET.md 8.6). It opens TEPHRA Assistant at work (7.21), as A
   does, which leads with the same words and links to Details › TEPHRA Assistant, the record of
   models, calls and causes.
6. Data chip `#feeds-chip`: "Data: 6 working · 5 off", worst first ("Data: 1 error · 5 working ·
   5 off", serious shape and border; "2 stale" in caution); "ok" for "working" below 1360 px. It
   opens Details › Data feeds.
7. Clock: `#clock-time` (fixed 9ch) and `#clock-sub` "11 Oct · UTC" or "Replay clock · 5 Sep" with
   an (i) "About replay" (`#clock-info`: feeds rebuilt from archives, the clock shows that day's
   time in UTC, not now); "Replay (i)" below 1360 px; "Stopped · …" while the stream is lost.
8. `#stale-chip` "Not updating since 10:31Z", only while the stream is lost.
9. "Desk →" (`.desk-link`, quiet outline, new tab). The filled button is in the story.

### 7.3 Footer

`footer.honesty`, one line (32 px; 28 at 1280): "RFA (Ring of Fire Air) is a fictional airline;
its flight numbers are proxies for real aircraft." ("RFA is a fictional airline." below 1360 px);
then "Map and data credits" (`#attribution`, opens About › Credits), "Policy A (illustrative)"
(`#policy-btn`), "Help" (`#help-btn`), "About" (`#about-btn`), "Privacy". The disclaimer is in the
frame strip (7.1), always on screen; on a phone the footer is the last thing on the page.

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

Moved onto the map on 13 Oct 2026 (user feedback: the key took a third of the story column).
`#legend` is a glass card on the map's top left at 601 px and up (248 px wide, `--z-map-overlay`),
listing what is drawn now, one short line per item (owner, 17 Oct 2026: "why you are saying never
smaller than official, binding, move it to info"): "Official ash area", "TEPHRA's estimate", "Crew
report area" (while one is drawn), "RFA flight in or heading in", "RFA flights close together",
"Forecast area (+6 h)", "Other aircraft", "Route" (while a route line is drawn), "Suggested
reroute", "Observatory's drift", "Where TEPHRA widened", "Satellite box", then "Full map key and
alert colours ›" (Help). The notes that used to sit under the labels ("binding", "never smaller
than official", "click to zoom in", "not RFA", "airport codes at the ends", "AI-read · supporting
only") are in the (i) beside "Map key" (one line per row, with "Full map key ›"), each row's
title tooltip and Help's full key. The card folds to its
bar, "Map key" with the first three swatches and a chevron (`aria-expanded`, `aria-controls`); it
starts folded at every width (13 Oct 2026: the map first, the key one click away), and a choice is
kept for the session. A fit
keeps the framed area clear of the open card (`safeInsets`, at most 40% of the map's width).
Compare mode moves it below the "A · official reports only" label. On a phone the same node sits
under the map as one 44 px bar. Help's full key is one column, two from 520 px. Swatches keep their
colours in forced-colours mode.

### 7.6 Story card, failure line, trust line, notes

The story (R5, `wall/story.js`), built by code from fields, about the selected volcano:
- Failure line `#fail-line` (only when something failed; red edge and the serious shape centred on
  each item's first line, `--fs-2` body type; at most two items, then "+ n more problems ›" to the
  Details section that holds the next). Plain words only, the failing part in bold: the raw
  reason (`RECOVERY AGENT ERROR: TimeoutError`, `budget_exhausted`) is the title of the item's
  words (not of the list item, so screen readers do not get it as the item's name) and stays
  under Technical detail in Details. The sources: the lost stream
  (`#lost-banner`, `role="alert"`), the Wall data not loading ("Could not load the Wall data: …
  Trying again in n s."), the map library not loading, a failing SIGMET, VAA, VONA or aircraft feed
  ("Aircraft data is failing. Showing the last good positions, from 10:20Z." — the time only from
  `last_success_at`) and the database failing. AI steps that did not run are not here
  (docs/UI-AI-QUIET.md Q3, Q4): the advisory line, the closure sub-line and Details say what is
  missing where it applies, in caution tone. A new failure is announced once (`role="alert"` on
  its first render only).
- Eyebrow, two rows in sentence case: the eruption symbol, `#volcano-name` (the page's h1, bold)
  and "as of 1030Z" right-aligned on the same row; under it, muted, the area, the alert colour as a
  small pill in words with a dot in the code colour ("Red alert"; "Alert colour not given" for
  UNKNOWN). REPLAY is said by the frame strip (7.1), not here.
- The story `#headline` (redesigned 13 Oct 2026 after "too cluttered": one big number, a row of
  facts, one notice, the lines about the sources; colour only for what is abnormal or the number
  to read first, ISA-101's high-performance HMI), replaced only when its words change:
  - the HYPOTHESIS banner first when it applies ("HYPOTHESIS: no valid official product. Only
    MONITOR or HOLD may be advised.");
  - the hero: the flights as a 64 px number in TEPHRA amber (72 px from 1600 px, 56 px at 1280
    and on a phone, smaller at fit levels 2 and 8) beside "RFA flights in or heading into TEPHRA's
    ash area ⓘ" (18 px semibold) and the quiet split "13 inside now · 1 heading in · Show them"
    ("Show them" opens Details › Flights heading in). The ⓘ (`aria-expanded`, `aria-controls`)
    opens the trust note `#trust` under the hero. At 0 the hero is the sentence "No RFA flight is
    seen heading into TEPHRA's ash area right now." with "Aircraft coverage here is patchy: an empty
    map is not an empty sky." (or "Aircraft data is failing/off: …");
  - up to three fact tiles, each a button to its Details section with the full sentence as its
    accessible name and title: "Ash up to FL500 · 50,000 ft" (or "Ash between FL100–FL500",
    What the official reports say); "Airports closed 3 · WARA · WIHH · WIII" (Airport closures;
    this volcano's closures, or the network's when the plan covers only others, with the scope
    and the plan's time in the title; the caution shape at the value when there is no airport
    plan; "re-planning the day…" with a spinner while code re-plans); "Advisories 12 · to decide"
    ("≥30" when the Wall's page of the 50 newest cannot hold them all, "to decide, 7 for flights
    gone" when some drafts' flights are not counted in the hero, "5 · decided · 4 approved, 1
    rejected", "0 · drafted", "? · unknown (database error)" in the serious tone; Decisions);
  - one notice, caution (`role="status"`, never red), when the AI's absence or a missing airport
    plan changes the dispatcher's work, said once for both: title "TEPHRA Assistant · paused" (no
    reason and no time: docs/UI-AI-QUIET.md 8.6), "Drafter gave no result (timed out)", "Waiting in
    line for TEPHRA Assistant", "Must-do flights left for the Desk" or "No airport plan"; then "No advisory drafts
    and no airport plan. Plan the 14 flights and the network by hand on the Desk." and one link,
    "Why ›" (Details › AI helpers) or, for a solver-only failure, "Airport closures ›";
  - the lines about the sources, one row each that opens Where the sources disagree: "The sources
    disagree on where the ash is heading, 135° apart." with "TEPHRA's estimate covers both."
    (WIDENED) or "TEPHRA's estimate has not been widened (AI off/AI waiting/AI unavailable)."; the
    SILENCE and CONFLICT lines.
- Crew report line (`crewLines()` in `wall/story.js`), a row after the source lines, at most
  one, for the selected volcano's ACTIVE crew areas only (a COVERED one adds nothing the
  official lines do not say): "Crew report of ash: 4 RFA flights on its route." with the pin (the
  flight numbers are in Details, one tap away), or "Crew report of ash outside the official area: …" with the
  caution shape when any of them is wholly or partly outside; with no flight flagged "Crew
  report of ash, reported 5 min ago." ("2 crew reports …" for more). The sentence is one button that opens Details › Crew reports of ash; there is
  no separate link, so "Decide on the Desk" keeps one line. A report near no active volcano
  never shows under another volcano's story: with no volcano selected it is the story's line;
  otherwise the All volcanoes list has the row "3 crew reports of ash elsewhere ›" (caution
  shape when outside) after the volcano rows, only when they all fit with room for it, else
  "+ 4 more · 3 crew reports" (the full list holds the row). The key row is "Crew report area"
  (one line).
- Re-planning: while the newest airport-plan step in the trace is "Closed airports changed: …,
  recovery agent started" and no plan has landed since (`ext.replanning`), the airports tile
  reads "re-planning the day…" with a spinner (the trace does not say which volcano closed them,
  so its title says "all volcanoes"), Details › Airport closures reads "3 airports (all volcanoes)
  · re-planning…" (caution) and its section opens with a spinner line. The Desk's Airports tab
  follows the same trace line.
- Buttons: the one filled button on the Wall, "Decide on the Desk →", linking to
  `/desk#review/{the DRAFT advisory of this volcano to decide first}` in the Desk's act-by order
  (`byActBy`, 10.17: the soonest act-by, keep watching and continue inside now last); the
  Desk opens that draft as its Next decision, so one flight is primary on both screens; with no
  draft it is the secondary "Open the Desk". Under it, quiet, "See the AI at work" (A) opens the
  board (7.21).
- Reading (`D.reading`): before the server's first tick, or while an active volcano in scope has
  no situation card yet, h1 the area, a spinner, "Reading the official reports…" and "TEPHRA has
  just started and is reading every feed for the first time. This takes up to a minute." (or "Ash is
  reported here. The summary appears when TEPHRA has read the reports, usually within a minute.").
  It is never "no ash" for something not yet read.
- Empty area (`D.regionEmpty`): h1 the area; "No ash reported near Kyushu right now." then "Ash
  elsewhere:" with a button per area that has ash ("Java / Bali · 1"). Nothing active anywhere: "No
  official ash report is in force in the watched regions right now." Connecting: the h1 "Connecting
  to TEPHRA…" with a spinner, no story line repeating it, and no numbers. Never "clear" or "safe".
- Trust note `#trust`, one tap from the hero's ⓘ: "TEPHRA's estimate is never smaller than the
  official area, which stays binding. AI can widen it, never shrink it." and "How TEPHRA built it
  ›" (Details › TEPHRA's estimate). The key's TEPHRA row says "never smaller than official" on
  screen at all times; the model ids are in AI at work and Details › AI helpers.
- All volcanoes: one quiet line, "5 volcanoes with ash · 23 RFA flights in or heading in · 26
  advisories waiting" (`#kpi-active`, `#kpi-exposed`, `#kpi-drafts` hold the numbers, in grey: the
  hero already carries the number to read; the dot ends each count, so a wrapped line never starts
  with one); at 0 flights it reads "no RFA flight seen heading in". Why a count is 0 is the notice's,
  said once.
- Story notes `#story-notes`: notes that are not map pills (the basemap note; the 150 km coverage
  note when the flight line has not said it).
- "☰ Details" (`#details-btn`) is sticky at the bottom of the story column from 601 px up, so the
  route to everything else is always on screen at 1280 and 1440; the fade above it shows only when
  the column really scrolls (after the fit pass). The fade spans the column's full width and the
  strip under the button is solid, so nothing scrolled under it shows a stray edge.
- The changed hero number gets a `--dur-5` glow (not under reduced motion). `#announce` speaks
  "{volcano}: {hero} {advisories} {notice}" at most once every 30 s, only when they change.

### 7.7 Map controls and status pills

Bottom-right, stacked by MapLibre: `#tools` (a custom control, one column of 40 px icon buttons,
`mapui.css`, each naming itself on hover and focus) with Fit (`data-tool="frame"`, F), Satellite
(`data-tool="sat-toggle"`, infrared on or off, I cycles the pictures), Compare (`data-tool="compare"`,
S), 3D (`data-tool="3d"`, D) and Layers (`data-tool="layers"`, L, opens Details › Map layers); the
three switches are pressed while on. Zoom +/- at every desktop width (the compass only in 3D), and
the attribution (`AttributionControl`, `compact: false`, 12 px: "OpenFreeMap © OpenMapTiles Data
from OpenStreetMap"). A phone keeps Fit and Layers in a row; pinch zooms. The flight filter,
one pill at the map's top centre: "All 72 · Inside 33 · Heading in 2" (counts of the RFA flights
in or heading into TEPHRA's area); Inside or Heading in leaves only those flights on the map, with
their paths, routes and labels (the picked flight always stays); kept for the session
(`tephra.wall.flights`). Bottom-left, `.map-pills`, only while true and one line each: `#ctx-label` (one
`.ctx-pill` per satellite, SO2 or BTD layer, never folded: "CONTEXT ONLY" and the caption wrap
together, the ✕ that turns the layer off sits beside them, and the GIBS scale, where one is
published, is inside the same pill; at most 520 px wide), and `#map-notes`: "Height filter FL180–FL350 hides 1 official
area and 4 flights · Reset", "Showing the official forecast for 0000Z (+6 h) · Back to now" or "No
official +12 h area in the current products · Back to now". More than three: "+n more map settings ·
Show". While History is open the pills and controls move up above it.

### 7.8 Details › Flights heading in, This flight

`#flights` (R8.3): the count sentence, the first 5 rows (plane, "RFA1225",
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
needs a written reason on the Desk, and "Crew reports of ash ›". For the reporting flight the
box reads "This flight's crew reported ash" with no entry line. An approved decision's reason
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

Amended 2026-10-13: the layout of these sections (and of 7.19's drawer) is now the Details kit in
`docs/UI-DETAILS-PANELS.md` sections 2-4 (header, tiles, rows, Technical detail last). The words
below still hold except where that document's table 5.3 replaces them (for example "AI on" as a
pill with the model ids as chips, failures grouped by cause, "Passed the checks" for ACCEPTED).

- Decisions (`#decisions`): "{state.draft_count} waiting · a approved · r rejected", "Approve on the
  Desk. Approved text goes only to TEPHRA's own outbound queue, never to an aircraft or any real
  system.", then the full list (folded).
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
  "From a replay" only on a replay feed while live plays (7.1), and "Technical detail" (last good
  time, records, feed key, the raw error);
  the database row last.
- Map layers (`#layers-pop`): the status ("satellite off"), "On the map" (official locked on;
  TEPHRA's estimate; crew report caution areas locked on; aircraft; other aircraft labels; flight paths; flight routes (on; the usual routes of the RFA flights
  heading in and of the picked flight); suggested reroutes (off by
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
REPLAY (the frame strip's REPLAY part, 7.1, and the clock's "Replay clock"); HYPOTHESIS (the banner
replaces L1); empty area and nothing active (7.6); 3D and compare (8.1, 8.2).

### 7.18 Operator policy

Redesigned 13 Oct 2026 (`wall/policy.js`, opened by "Policy A (illustrative)" in the footer and
from About). The old dialog led with a run of metadata joined by " · ", listed all values at once
under raw keys (`exposure.vertical_margin_ft`), let "2000" wrap away from "ft", ran each reason and
its citations into one paragraph, and left out the five crew report values (43 of 48 shown).

What it follows: progressive disclosure (Nielsen Norman Group, "Progressive Disclosure": show the
few things most people need first, keep the rest one clear step away, and no more than two
levels), and the WAI-ARIA tabs pattern (w3.org/WAI/ARIA/apg/patterns/tabs: a labelled `tablist`,
`aria-selected` and `aria-controls` on each tab, a `tabpanel` labelled by its tab, arrow keys,
Home and End between tabs, activation on focus because the panels show at once, `tabindex="0"`
on a panel whose first element is not focusable).

Four tabs, sticky at the top of the dialog body: Overview, Values (48), Sources (10), Trust order
(3).
- Overview: the sentence "Policy A: avoid every official ash area, with 2,000 ft above and below."
  (the margin from `exposure.vertical_margin_ft`); three chips: the status ("Illustrative, not an
  airline SRA", caution outline), "Version 2026.10.9", "Risk owner Flight Operations"; one line
  that it is an example no airline has reviewed; "The values that shape most advice" as six tiles
  (margin above and below the ash, distance kept from the ash, divert and hold times, the airport
  closure radius, the crew report radius), each opening that value in Values; "All 48 values ›";
  then two disclosures: "What the policy says in full" (the summary text and its three source
  chips) and "About this policy" (name, policy id, version, status, risk owner, safety risk
  assessment, the full content hash with its first 12 characters, the part every advisory
  records, in bold).
- Values: "Find a value" (filters by name, setting, value, reason and source; "12 of 48 values";
  "No value matches" with a hint), then the nine sections in reading order (Height margin, Flight
  plans, Reroutes, Alternate airports, Crew reports of ash, Airport plan, Fuel, Drafts, Duty
  Officer), each with one line on what its values decide. A row is a name a person reads and the
  value with its unit ("Distance kept from the ash · 20 NM", "Highest level proposed · FL410",
  "Width of a proposed level band · 20 FL (2,000 ft)", "Longest delay before cancelling · 360 min
  (6 h)", "$1,500"; a no-break space keeps a number with its unit). Opening a row (one at a time
  per section) shows the reason, the source chips (each opens its citation in Sources) and
  "Setting `exposure.vertical_margin_ft` · 2000 ft" for traceability. A block the page does not
  know yet still shows, under a heading made from its name.
- Sources: one card per citation: the full reference, the quotation exactly as published, "Used
  by" (the values, the policy text and the trust-order rules that cite it) and "Open the source".
- Trust order: the three rules, numbered, each with "Operator choice (illustrative)", "Applied by"
  and the code it names, and its source chip; above them the line that this is an operator choice
  under ICAO Doc 9974 2.4(d).

Words. The page shows the policy file's own words and changes none of their meaning: a reason
that opens "TEPHRA illustrative choice:" shows that as a tag and the rest as written; a
semicolon in a reason, the policy text or a trust-order rule is shown as a full stop with the next
word capitalised. The file itself is unchanged (version 2026.10.9, hash `51826941aff3`), so the
hash every advisory records stays the same. Quotations of the sources keep their own punctuation,
semicolons included, inside quotation marks.

Where each old piece went: the header's name, version, label, risk owner, SRA and hash → the
status and version chips and "About this policy"; the raw key → the row's name, and the key under
"Setting" in the open row; "2000 ft" → "2,000 ft" on one line; "Why this value" → the open row's
reason; its inline citation refs → source chips and the Sources tab; "Show all 43 values" → the
Values tab, now with all 48; "What the policy says in full" → the same disclosure on Overview;
"Source-trust order" → the Trust order tab; "Citations (n)" → the Sources tab. The Desk shows no
policy dialog (a draft's review shows only the policy id, version and hash it was made under), so
nothing changed there. `tests/test_wall_policy.py` checks that every value is shown once with a
readable name, the unit formats and that no reason keeps a semicolon.

### 7.19 The Details drawer

Amended 2026-10-13: index rows carry a status shape and stack the title over its live status, a
"Needs a look" card lists up to three serious or caution rows, the key pinned under the drawer at
601-1599 px folds to a 44 px "Map key" bar (`data-act="key-toggle"`), and the phone sheet's top
edge is measured on every render (`docs/UI-DETAILS-PANELS.md` 2.6).

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
area now"; a report entered in REPLAY says "From a replay" only while live feeds play (7.1); the label and a plain explanation (a dispatcher
enters it on the Desk; code draws the area; it flags flights, never shrinks or replaces an
official area, re-plans nothing and calls no model; a sulphur smell or haze alone is a routine
report with no area; a no-ash report never removes one); then one card per report, newest first,
with its record: the flight, the state with its shape and word (Active, Covered by official
area, Expired, Withdrawn, or the no-area wording), the age, "From a replay" (live only), for a
withdrawn or expired report what ended it ("Withdrawn by AK at 1052Z: Wrong position. It no
longer flags any flight."), the discrepancy line "Crew report outside the official area. Part of
it lies outside every valid official area, sideways or in height. A dispatcher can start a
message to the weather office and the VAAC on the Desk." (caution box), then Crew reported (cues in words), At (band,
observed time), Position (latitude and longitude, "ADS-B fix at 1039Z" or "typed by
dispatcher"), Near ("near Slamet (100 km)" or "no catalogued volcano"), Caution area (radius and
band), Wind stretch (the server's note), Valid (from, to, time left), Entered (who, when),
Remarks, Covered by (display only: the area and its flags stay), Flights flagged (active and
covered only, from the report's own `flagged`); no second paragraph repeats them; "Show on the
map" and "Open on the Desk ›" (`/desk#crew/<id>`); "Technical detail" with the report, position,
wind and covered-by ids and the policy. The section ends with "Report ash from a crew on the
Desk ›" (`/desk#crew-report`). The drawer's volcano picker is hidden here: the list is the same
for every volcano. The Wall is read-only: entering, withdrawing and the message are on the Desk.

### 7.21 TEPHRA Assistant at work (was "AI at work")

A full overlay (`<dialog id="board">`; `wall/board.js` for the logic, `wall/board-view.js` for the
page) that shows the assistant's work as it flows: real feeds on a map, code's checks, the
Coordinator, the model gate, the six skills and a person who decides. Opened by the assistant
chip, by "See TEPHRA Assistant at work" under the story's main button, by the button in Details ›
TEPHRA Assistant, by A, and by `/#ai-at-work` (the Desk's link; the hash is removed once read). It
covers the Wall below the frame strip and leaves the story and the map as they are underneath. The
approved prototype and its behaviour spec are kept outside the repo (the "assistant-flow-board"
notes); this section is the spec in the repo.

Why it exists. Globot, the Gemini 3 grand-prize winner, showed agent cards and a "Waiting for human
approval" step over scripted demo data (research/16). TEPHRA's assistant is real: the Coordinator
hands out jobs and every step is recorded. The board makes that readable in about five seconds and
lets a viewer feel the work move, and every moving thing is one real record.

The stage:
- **Map.** A live map of the region the Wall shows (`state.regions`): MapLibre on the night basemap
  (section 5, `wall/basemap.js`; land as a dot matrix, a thin coastline, country names only), framed
  on the region in the part the head, the panel and the dock leave free. Drag to move, scroll or
  pinch to zoom; the control column beside the panel (zoom, "Back to the whole area", Layers: ash
  areas, aircraft, airports, where feeds come from, aircraft feed coverage) is the Wall's (section
  5, `mapui.css`). The official cone is filled and edged in pink (it holds every valid product),
  each SIGMET and VAA inside it a faint line; TEPHRA's area where it is wider is amber, dashed; the
  aircraft feed's query circles, airports, the active volcanoes in their real colour code (the
  board's only red) and every aircraft. Selecting a plane, a volcano, an ash area or a feed opens one
  small card where it was selected (flight and real aircraft, level and speed, origin to
  destination, inside or minutes to entry; a volcano's colour code; a product's name and band; a
  feed's state and records), which follows the map. Effects read map positions every frame, so a
  particle in flight follows a pan. Every label sits on a plate, stays on the map, gives way to the
  labels placed before it (a name with no free place is left out) and is placed again as the map
  moves.
- **Beacons.** Each feed has a beacon where it comes from: VA SIGMET on the SIGMETs in force, VONA at
  MAGMA Bandung, Darwin and Tokyo VAAC and JMA pinned to the map's edge with an arrow and their
  distance, Himawari, the winds grid; METAR comes from the airports and ADS-B from the aircraft. A
  feed that is off is its name alone, dimmed; why is in its card.
- **Head.** The Strata mark by state, "TEPHRA Assistant · working / paused / off (code
  only) / Recovery planner gave no result" (`#board-status`), one sentence of what still holds
  (`#board-lede`; paused: "Code still reads every feed and checks every flight; jobs wait in line
  and must-do flights come straight to you.", with no quota, reset or slot words, UI-AI-QUIET 8.6;
  while the work queue did not load it says nothing about jobs in line), then "Why ›" while the
  assistant is paused or has trouble (it opens Details › TEPHRA Assistant, the one place that says
  the cause, UI-AI-QUIET 8.7), "Real now · Example: working normally", "?" (How this moves) and the close button.
- **Inside TEPHRA** (one glass panel, the pipeline as a drawn spine): Code checks (no AI) with feed
  reads and flight alerts at the playhead; the Coordinator with its last run ("not run 11:28:56" for
  a run the model refused, UI-AI-QUIET 8.7) and a button that opens
  its details; the model gate ("AI model · open", "Paused" with "4 jobs in line" and the tooltip
  "Why: Details › TEPHRA Assistant", "AI model · gave no result", or "No model · code templates")
  with the queue's waiting jobs parked in front as hollow rings (the gap above the gate grows so
  they never reach the Coordinator's words; no slot or reset time on the board, UI-AI-QUIET 8.6;
  a queue that did not load shows none: "Jobs in line: unknown, the work queue did not load"); the
  skill sheets name their model ("Model: gemini-3.5-flash-lite"), the calls are counted in Details
  › TEPHRA Assistant only; the six skills
  (Plume reader, Satellite reader, Flight planner, Drafter, Recovery planner, Paperwork drafter),
  each with "N in line", its newest step's time or "idle", and a button that opens its details (the
  `boardModel` card: state, newest result, model and calls, newest steps); "When you ask" for the
  Desk's skills; and **You decide**: the hero number (at the playhead), the run bars, "At the Desk
  now" with the Desk's other work (flights to plan by hand, SRA to sign, the airport plan, advisories
  to approve; no second must-do number while the hero says one), "Open the Desk →" and
  "Details › TEPHRA Assistant ›".
- **Dock.** A four-row log that folds what belongs together (flights flagged together, a run and its
  outcome, hand-outs to one skill, drafts reaching the Desk; "23× since 11:28:26" for repeats; a run's
  "N must-do to you" appears when its tokens land, as the hero changes), a one-line legend, "Every
  step in plain words", and the player. Rows are keyed: only a new row slides in.

Motion (`flowModel` in board.js, pure; tests in `tests/test_wall_board.py`). Only these move:
| Record | Motion |
|---|---|
| a POLL step, or a feed's `last_success_at` that moved on the `state` stream (one event for one read) | 3–9 particles from the feed's beacon (or the airports, or the winds grid) to Code checks, ripples at the source |
| aircraft positions read (the ADS-B read, or a run started by new positions) | a glint on every aircraft in view and one faint particle from among them to Code checks (the most frequent read gets the quietest motion) |
| an EXPOSURE step | a ring and a mono label on that aircraft, one particle to Code checks |
| "Duty Officer: N item(s) to dispatch" | N white tokens from Code checks to the Coordinator |
| "Duty Officer AI UNAVAILABLE (…); D …, M mandatory item(s) to the Desk" | the run's tokens knock at the closed gate, turn caution and drop down the code lane to You decide; the hero becomes M when they land |
| "Duty Officer left M mandatory item(s) undone" | M caution tokens down the code lane |
| "Duty Officer -> tool: …" | a token through the gate to that skill, whose dot lights. The line is written when the tool returns, so the board moves it to just before that skill's first step since the run began (at most 5 s; the log keeps the record's time); live, a hand-out whose work already moved is a log row only. A gate that is closed now opens while a recorded model hand-out passes |
| a skill's own step (PLUME, SATELLITE, PLANNER, DRAFTER, RECOVERY, DOCS) | its dot lights; DOCS and RECOVERY send a token to You decide; a real Plume reader reading sends an amber particle to the volcano; an error greys the dot (never red) |
| "RFA…: DRAFT … waiting for a dispatcher" (DESK, code) | a token from the Drafter to You decide |
| NOTICE, ASK, MESSAGES | the "When you ask" dot lights, a token to You decide |
A message no pattern knows is a log line with no motion. Every route keeps a faint afterglow for
about 3 s. Steps in the same second are staggered 160 ms.

The player. The playhead is the only source of state: seeking rebuilds the counters, log, hero and
run bars from every event at or before it, with no motion; playing fires each later event as it is
passed (8×, 30×, 60× or 120×, one button stepping through them; a quiet stretch runs up to 14×
faster and says so in the player's own line). The board never plays back on its own (owner, 15 Oct
2026: the presenter starts it): in REPLAY and live it opens at the newest step, the labelled Play
button plays back the window, and in REPLAY the player carries the one small word "Replay". A step
that arrives on the
stream animates at once (`flow.push` from the `trace` handler, `flow.pushRead` from `state`). The
play button then plays back the window. Steps the stream did not deliver (a reload after a lost
stream) are applied with no motion; while the stream is lost the board dims and says "Live updates
paused, reconnecting."

Example mode is labelled "Example · illustrative, not recorded. The assistant steps it shows did not
happen." Choosing it plays the window's recorded inputs from the start with the gate open; the hero
counts the drafts of the newest example run as they land and names that run. Its counts live in the
view and it writes nothing anywhere. Closing the board returns it to "Real now".

States and colour: working (gate open, the AI lane bright), paused (closed gate, waiting rings, the
code lane caution toward You decide, the time left counted on the real clock), trouble (the chip's
words, gate closed), off (gate "No model · code templates" drawn as a dashed bypass: the skills run
as code, no model is closed or called). Pink is official
products, blue the observatory, grey-blue weather, grey aircraft, white jobs, caution yellow only
must-do work going to a person, amber TEPHRA's estimate, violet only the player's "Replay". A
refused Coordinator run is never "Working" (board.js `isWorkLine`).

Reduced motion: nothing travels. Each step draws a still line from source to target for 1.8 s, the
player steps one real step (or same-second group) every 2.2 s, ripples and afterglow are off, and
the numbers still update. Accessibility: a native modal dialog, focus to the title on open and back
to the opener on close; the map, the canvases and the nodes are `aria-hidden`; "Every step in plain
words" and "?" open a dialog with the motion-to-record table and the full folded step list (the
steps up to the playhead bright); one polite live region (`#board-live`) speaks at most one row
every 10 s; the track is a `role="slider"` with "replay clock 11:40:38" as its value text, and ←/→
step between real steps, Home/End jump to the ends. At 760 px and below the parts stack and scroll,
the player is a solid bar across the bottom with a must-do chip that jumps to You decide (its label
says "–" as words, never 0, before the first run).

Performance: three canvases (the map redrawn only on a resize or a new snapshot; the rails, the spine,
gate and waiting rings, redrawn on a resize, a scroll or a change of state; the effects cleared and
drawn per frame only while something moves, the loop stops when nothing does and while the tab is
hidden), at most 160 particles, 90 afterglow routes and 40 tokens, no layout reads in the loop
(anchors are measured on resize and scroll), no DOM work per frame, and an update writes only the
words that changed. While the board is open the Wall under it is not drawn and its map's marching
paths stop.

### 7.22 The guide page (`/guide`, 13 Oct 2026)

The manual is a page of its own, so the Wall and the Desk show the situation and not the manual:
`guide.html` + `guide.js` + `guide.css`, built from the same builders the dialogs used
(`helpContent` and `aboutContent` in `wall/controls.js` with `{ page: true }`, `policyDialog` in
`wall/policy.js`): Read the map (3 steps, the full key, the words used, the keyboard), About TEPHRA
(what it is, safety limits, credits, acknowledgement) and the operator policy. The Wall's footer says
"Map and data credits", "Policy A (illustrative)" and "Guide", links that open its sections in a
new tab (the Wall keeps its place); "?", "Full map key and alert colours ›" and every Help or
policy button do the same. The guide's "Track record ›" opens the Wall at Details › Track record
(`/#track-record`).

### 7.23 The map's card (13 Oct 2026, `wall/pick.js`)

Selecting a plane, a volcano or an airport on the Wall map opens one small glass card at that point
(above it, or below it near the map's top edge), as a flight tracker does, with only what is needed
and one link: a plane: RFA flight and real callsign, level and ground speed, origin → destination,
inside or minutes to entry (caution and serious words), its advisory's state, "Flight details ›";
a volcano: its alert colour, the official band now, the RFA flights in or heading in, "This ash
area ›"; an airport: codes and name, "Closed until 1910Z" and why or "Open: no closure in the
airport plan", the longest runway, "Airport plan ›". A volcano's or an airport's card shows a photo when
one with a free licence exists (`wall/photo.js`): Wikidata's image of the volcano (Smithsonian
volcano number) or the airport (ICAO code), shown only when Wikimedia Commons reports public domain,
CC0, CC BY or CC BY-SA, with "Photo: <author> · <licence>" under it linked to its Commons page;
none found, no photo and nothing in its place. Planes get no photo. Selecting a plane still picks
it (ring, route, path). The card follows the map; Escape, its ✕ or a click on empty map closes it. Areas, reroutes
and crew reports still open their Details sections.

The side panel (story and Details) hides with a tab on the map's left edge for the whole map, and
the same tab brings it back; kept for the session (`tephra.wall.panel`); opening Details shows it
again; not on a phone.

### 7.24 TEPHRA Connect (`/connect`, 13-14 Oct 2026)

Folded into Onboard on 16 Oct 2026: /connect redirects; the dispatcher tools are the Desk's Data
connections.

Where an airline feeds its own data in, shown rather than explained. Connect's own accent is cyan
to violet (`#5eead4` to `#8b9bff`), for data arriving and nothing else; amber stays TEPHRA's area
and the flights in it, pink stays official.
- **Headline**: "Feed your flights. Watch them meet the ash."
- **The live map** (left): the night basemap with the ash areas and the active volcanoes; each
  pushed flight is a plane icon on its track that glides to its new position over the 5 s between
  pushes, with a short trail; amber when it is in or heading into the ash. It shows the flights
  updated in the last 60 s (the analysis keeps a position for 5 min) and frames them when they
  first arrive. Three numbers: positions / min, flights live, in the ash. Nothing arriving: a
  breathing orb, "No flights arriving" and "Try the sample feed".
- **Feed your data** (right), one card with three tabs. **Upload**: a drop zone for a JSON file,
  "Use TEPHRA's clock for the times" (on by default, for a file whose times are old such as the
  sample), "Sample file", "Paste JSON"; the answer as three numbers (taken, in the ash, refused)
  and the refusal reasons. **API**: one position as field chips with real values, "JSON Schema",
  "Get a key" (shown once with Copy), the push in curl, Python or JavaScript with the key filled
  in, and "Your connections" with Revoke (confirmed). **Sample**: one big play button, real flights
  from recorded ADS-B, its rate. Signed out, each tab asks for the name and Desk PIN in place.
- **Where your data goes** (under the map), one card per section with its count and what it
  became: positions -> "9 in the ash · drafts on the Desk"; flight plans -> "routes on the maps"
  or "24 to or from a closed airport"; pilot reports -> "5 flights flagged · caution areas". A card
  glows amber when its section is touching the ash or a closure. On the map, flight plans are
  dashed violet lines origin to destination (red when an airport on them is closed) and pilot
  reports their crew caution areas and pins. An upload's answer says the same per section
  ("Where it went"). On the Wall a flight with a pushed plan shows "WIII → WADD · RFA4259 flight
  plan" and "Lands at WIII: closed"; a pushed pilot report says "pushed by <connection> (Connect)".
- **The sample feed** is three kinds of real data: 40 real airline flights from recorded ADS-B
  (those whose callsign has a known route first, so each gets a flight plan with its real origin
  and destination), their flight plans with the first push and every minute, and a crew report
  of ash from a sample flight in the ash 15 s in and every 4 minutes. The downloadable sample
  file holds all three sections.
- **Sources** (under the map): each connection with a 5-minute sparkline and positions / min,
  glowing while it flows; the public feeds as chips with a state dot and their records.
- **Ticker**: one card per push (+40 positions, 12 in the ash, refused in red).
- **No stale first frame**: the page starts from `GET /api/connect/live` (the flights on the map
  now, each source's flow, the newest pushes), so a reload is complete; until it answers the
  numbers and sources shimmer, and no number shows that is not current. The flows refresh every
  10 s; the `push` event moves the planes and the ticker.

### 7.25 One product: the shared nav (14 Oct 2026, `topnav.css`)

Every page starts the same way, so moving between them nothing jumps: a 56 px bar at the top
(`.tn-bar`; the 32 px strip above it was removed on 15 Oct 2026, 7.1) that opens with the TEPHRA
mark (`.tn-home`, 132 px wide at 24 px from the left; it goes home) and the pill nav Demo · Desk · Onboard · Guide (16 Oct 2026; Onboard only where `onboard` is on, Your airline in its place once an airline is signed in (renamed from Workspace, owner, 17 Oct 2026); Assistant left the nav on 16 Oct 2026: `/assistant` is reached from the demo panel's pop-out link, the A key and the Guide) with the page you are
on filled. The gap after the mark and the nav's sizes are in px, as the pages' root font sizes
differ. Each page's own controls follow: the Wall's area, Assistant, data and clock (the Wall's old
"Connect" and "Desk →" header buttons are gone, the nav has both), the Desk's chips on the right,
Connect's clock badge, the guide's section links on the right. At 1100 px and wider the mark and the
nav sit at the same place on all four pages (measured at 1100, 1280 and 1440). Below 1280 the Wall's
Assistant chip shows its mark only (its name stays in the label); below 1100 the mark loses its
fixed width, the nav shows only the page you are on (and the Wall's Desk link) and the Wall's area
name shortens. The Desk hides the nav below 600 px.

### 7.26 The Wall's footer is a status line (14 Oct 2026)

The footer row (32 px) is a status line, inverted so it reads as its own strip: a light bar with
dark ink, the pairing of the nav's current page. It is written for a dispatcher, not a programmer:
plain words, no addresses or `key=value`. On the left: a dot for the state (green live, violet
replay, amber when updates stopped; its name on hover), the volcano in bold, then its official ash
areas and the view ("Flat map", "3D view", "Side-by-side compare"), "Policy A" (a link to the
guide's policy, its id and version in the tooltip) and "Credits" (a link to the guide's credits,
the full credit string in the tooltip; OpenStreetMap stays on the map). The fictional-airline note
is the facts' tooltip and stays in the strip on top. On the right: the keys, each also a button that
runs it: ? Guide, A Assistant, [ ] Volcano (from 1360 px), F Fit map, D 3D, S Compare, Esc Back. On a
phone the keys are hidden and the line wraps. (On 15 Oct the row was cut to ? and A; the owner
asked for the whole row back the same day.) The flights inside and heading in are not repeated
here: the story says them (each fact once). Privacy moved to the guide's foot (and the Desk's
sign-in).

Times a reader meets first say "10:32 UTC" (`utcTime`), not "1032Z": the story card ("Updated
10:32 UTC", its notes and the airport plan) and the time bar's clock.

### 7.27 TEPHRA Assistant is a page (15 Oct 2026)

"Let's not make this a dialog, make it a separate page." The board (7.21) is `/assistant`. Since
16 Oct 2026 it is not in the top nav: the demo panel's pop-out link (`#assist-page`), the A key and
the Guide reach it. The route serves the Wall's own page:
`page-mode.js`, a plain script in the head, sets `data-page="assistant"` before anything draws, so
the Wall never flashes; CSS then hides the Wall's stage and status line and puts `#board` in the
grid row under the shared header, and `wall.js` shows it with `show()` (never `showModal`, no close
button, no backdrop) and draws the header's chips and clock as on the Wall. The Wall's assistant
chip, its `A` key, the story's "See TEPHRA Assistant at work", the footer key and the Desk's links
all go to the page; `/#ai-at-work` redirects there. A Details link on the page opens the Wall at
that section (`/#details-<section>`). The Wall's own map is not started on this page.

It moves with your data: an airline's push through Connect (the `push` event, the sample feed
included) is a read of aircraft on the board, "Airline positions pushed: 40 positions", glinting
on the planes and flowing into Code checks, at most one every 15 s. The flights it brings are
checked on the next tick like any other, so the Coordinator, the skills and "You decide" fill as
their exposures arrive.

On desktop the title, the log with the player, and "Inside TEPHRA" are three glass cards over the
map. The board's height rules count the 56 px header (1016 and 896 px), and below 780 px of height
the panel keeps the decision and "Open the Desk" and drops the Desk's counts and the Details link.
Below 1280 px the nav's links sit 9 px apart so the Wall's header still fits at 1100.

### 7.28 The case strip folds, Connect draws at once (15 Oct 2026)

Folded into Onboard on 16 Oct 2026: /connect redirects; the dispatcher tools are the Desk's Data
connections.

The case strip (`wall/case.js`, `data/cases.json`) shows one line: what happened, with its two
numbers. "What went wrong ⌄" (or "What TEPHRA does" for a case with no disagreement) opens where
the reports disagreed, what TEPHRA does and "Sources ›"; it starts closed and the choice is kept
for the session (`tephra.wall.case`). The words read as plain English: "02:00 UTC", "three days
later", "fifty thousand feet" (a figure in words, as the video's voice-over says it).

Connect has no shimmer boxes. The map, the tabs and the sign-in draw as soon as `/api/state`,
`/api/desk/me` and `/api/connect/format` answer; the numbers show a muted dash until
`/api/connect/live` arrives; the sample file (built on request, about 2 s) fills the API tab's
example values when it arrives and holds nothing up.

Every page lists its entry script's whole static import graph as `<link rel="modulepreload">`
(`tests/test_modulepreload.py` names a missing line), so the modules load in one round trip
instead of one per import level.

### 7.29 The Guide is a tour with numbered screenshots (16 Oct 2026)

`/guide` opens with one lead sentence, the four honesty facts as chips and the case, then one step
per page (Wall, Assistant, Desk with a phone review, Connect): a heading, one line, "Open ›", and a
screenshot with 4-8 numbered marks beside a legend (a title of up to five words, one sentence).
Hover or focus on a mark lights its legend item and dims the rest, and back; a click pins it and
brings the other into view; Enlarge opens the shot in a `<dialog>` (Esc closes, focus returns).
Badges are 24 px dots in `--c-info`; an ash-area mark is a pin on the area. Try it is six link
cards; Map key, How it works, About and the policy fold under More with their old ids. The shots and
`data/guide-shots.json` come from `scripts/capture_guide_shots.mjs` against the stub replay.

### 7.30 A skill's sheet reads at a glance (16 Oct 2026)

The owner, on the old sheet: "I cannot differentiate what's going on quickly." Clicking a skill on
the Assistant board opens, in order:
- a state pill (Working pulses in `--c-info`, waiting and no result in caution) and what it does;
- three counts: in line, done, not accepted;
- the job it is working on, as a flight row;
- the queue, most urgent first, with minutes as a pill (15 min or less, or inside, in caution);
- the newest results, each with a badge: Done (check), Not accepted (triangle), Tool, Note.

A result's badge follows what it says before its trace level: a plan the checks refused is
"Not accepted" even when logged at info. Tool calls read as words ("Flight planner priced a
divert: 36 min, 1,512 kg fuel"); their JSON stays under Technical detail. The model id is one small
mono line in the footer, next to "Why ›" and "Every step ›".

### 7.31 Details cards read at a glance (16 Oct 2026)

The owner, on "Official ash area · binding": "awful UI here as well.. i can spot a lot of these
boxes in the website with awful UI". The Details cards follow 7.30's pattern through one glance kit
in `wall/dk.js` (`dkGlance`, `dkBand`, `dkMove`, `dkCountdown`, `dkSources`, `dkSteps`, `dkFact`,
`dkFoot`, `dkQuiet`; CSS `.gl-*`):
- **This ash area, official card**: a kind label in the area's pink, validity as a countdown pill
  (clock time in mono, time left; caution in the last hour); the band in big type beside a height bar
  (SFC–FL600 scale, the same on every card); movement as an arrow with the direction big and the
  speed under it ("not stated" in words, never drawn); "Drawn from" and "Issued by" become one row of
  chips, one per report (office code and number in mono, kind word, pink dot; the office's full name
  is the title and the screen-reader text); forecast steps as a timeline from Now; raw texts, "All
  reports ›" and Technical detail as quiet links in a footer. The "Official area in force" pill is
  gone: the card says it.
- **This ash area, TEPHRA's card** and **TEPHRA's estimate**: the same card in amber; "Never smaller
  than any valid official area" and "An estimate, not a forecast" stay.
- **What the official reports say**: each row leads with a kind tag (SIGMET · binding, VAA ·
  binding, VONA · supporting) in its map colour and the id in mono, then the band, an arrow and the
  validity; the age turns caution past 6 h. The legend and the per-kind age chips are gone; the
  summary sentence stays for screen readers. "Raw texts side by side (C)" is a quiet link; "Why TEPHRA
  shows <volcano>" a quiet disclosure.
- **Where the sources disagree**: the counts are said once, big (7.30's stat tiles); the pill says
  "Needs a look". A direction row shows the official and observatory arrows in their map colours and
  the angle between them.
- **This flight**: the flight in big mono beside its entry pill; level on the height bar, track as an
  arrow, speed, route; the drafted action is the one highlighted card with a state badge (never red)
  and "Open on the Desk ›".

Shapes are aria-hidden; the words beside them carry every fact. Colours come from tokens only.

### 7.32 Home and the demo (16 Oct 2026)

The owner's structure: "a fast Home at `/`, the Wall moved to `/demo` with a welcome dialog, a slim
story strip and the assistant in the right panel".

- **Home (`/`)**: one line on what TEPHRA is and two big choices, title only (16 Oct 2026: "no
  need to mention it here"), **Watch the demo** (filled, autofocus) and **Onboard your airline**
  (shown where `onboard` is on; "Your airline workspace" once signed in), with "Already onboarded?
  Sign in" under them. Behind them a volcanic sky (a token gradient with faint ash drifting,
  `home/ash.js`; still under reduced motion, stopped while the tab is hidden); beside them a
  picture of the five steps from `five-steps.js` on a flowing path that ends at an advisory card
  marked **Example** (no flight, an Approve shape that is not a control; one `role="img"` with a
  label, nothing focusable), one pulse travelling down it. Under 1024 px the steps are the small
  strip under the line. Neither carries data: the replay map, its live count and caption left Home
  on 17 Oct 2026 ("it looks repetitve to the map"). An old link to `/` with a query string or a
  hash lands on `/demo` with it.
- **Welcome dialog on `/demo`** (read in about three seconds): the Replay chip with the case, one
  short title, the five steps as numbered nodes joined by one line, by name only, from the same
  source as the Guide's words (`five-steps.js`; the Guide keeps their description lines), one quiet
  line of three short honesty facts (the full sentences are the dialog's screen-reader description
  and are said in About), then a small "Don't show again" and **Start the demo** (Enter or Esc
  start, with no visible key hint; **How it works** and **W** reopen it). `?intro=0`,
  `?shots=1`, `?present=1` and a Details, track-record or assistant hash skip it.
- **Left**: a slim story strip (volcano, colour code, RFA flights in or heading in, volcanoes with
  ash, advisories waiting, from the one `allCounts`); one click or **E** opens the full story.
- **Right**: one panel with two tabs, **Assistant** (on load) and **Details** (the old drawer), and a
  pinned foot with the one filled **Open the Desk** (under the Assistant tab only its button: the
  diagram's You decide says the rest). The Assistant tab ("can't we have this ui ux in the main
  demo page", 16 Oct 2026): the state line, the Inside TEPHRA diagram of `/assistant` (one
  renderer, `board-view.js` `mountInside`: Code checks with feed reads and flight alerts, the
  Coordinator with its jobs in line, each skill with its state, "When you ask", You decide with
  its count, reason and per-run bars, and "Nothing leaves TEPHRA until a dispatcher approves."
  since the foot's line is hidden under this tab), then **What happened**: the step log folded to
  its newest 3 rows with "Show all (N)". The replay player and its note line sit above the
  diagram, so "Replay · ..." shows on a 1366x768 laptop too; under 860 px of height the diagram
  tightens. Rows open Details. Under 900 px the
  panel is a bottom sheet (peek, half, full), the diagram first, one column.
- **Catch-up on arrival** (REPLAY only; "leave the replay speed alone and change what the panel
  does when a visitor arrives"): once the welcome dialog closes and the tab shows, the tab plays
  the newest full chain of recorded steps the page holds (feed reads, code checks, Coordinator,
  each skill, drafts at the Desk; with the budget closed, the must-do work passed to a person and
  no skill) in about 16 s, then follows the replay clock. A pulse runs from each feed's place on
  the map into Code checks, then node to node down the diagram; each pulse is one recorded step.
  Labelled "Replay · catching up: TEPHRA's last steps, fast", then "Replay · following the replay
  clock", with "Replay again"; before it starts the player reads "Replay · about to catch up".
  The step playing is said in words under the player and to a screen reader ("Replay, catching
  up: ..."); each skill row shows its state at that step (in line, running, done, no result), and
  You decide says what reached a person. The player stays at the top of the tab while it plays,
  and the tab scrolls each step's row into view. It waits, and holds between steps, while the tab
  is hidden, a dialog is open or the phone sheet only peeks (on a phone it starts when the sheet
  opens). No request, no model call, nothing written. When no chain is whole it plays what exists
  and the note says what is missing. Reduced motion: nothing travels, the highlight steps every
  2.2 s. `?shots=1` skips it.
- **Light theme**: the panels follow it; the map column stays on the night basemap.

Honesty placements: REPLAY in the page title, the "Replay clock", the welcome dialog's pill and
first line, the player ("Replay · catching up: TEPHRA's last steps, fast", "Replay · following
the replay clock", never a bare "paused") and every modal's screen-reader text; Home shows no
replay data, and its example card says Example. Ring of Fire Air is fictional: the welcome
dialog, About, the status line's "RFA (i)". Decision support
only, nothing sent to an aircraft: Home's footer and the welcome dialog. The AI state: the
Assistant tab bar's one status (7.35), with its (i). ILLUSTRATIVE: Details › How TEPHRA decided, beside "Operator
policy A".

### 7.33 Onboarding and the workspace (16 Oct 2026)

- **Onboarding (`/onboard`)**, account first (16 Oct 2026: "whats the need of writing this,
  first sign up"): a landing with a short title, the sign-up card (work email, password with Show,
  the decision-support tick, Create account, "Already have an account? Sign in", one privacy
  line) in the first column on a wide screen and first on a phone, what you provide in nine lines
  and one Not-built line; then the recovery code shown once (with answers an older version kept in
  this browser offered, "Use them" or "Discard", never moved in unasked);
  then one topic per page (Airline · Ash policy · Fleet · Network · Schedule and crews · Data
  feeds · People · Assistant · Review) with a step list, "Step 3 of 9 · Fleet" in words (the
  nine-segment bar is `aria-hidden`) and Back and Next, each saving the pages to the account
  (a small "Saved" mark; a failed save says why in the action bar and keeps what was typed).
  Next checks only the page it leaves. Signing in again resumes at the first unfinished page.
  Review lists each page's answers ("Not opened · default" for a page never opened, every page one
  tap away from Review) and **Submit for verification**. Signed in after submitting, the landing
  says "Your answers are submitted". An account never submitted is deleted after seven days
  without a save (privacy page).
- **Sign in (`/signin`)**: one card over the dimmed night map ("Sign in to your airline"); generic
  errors ("That email and password don't match"), the tries left when two or fewer remain and "Forgot
  password?" (the recovery code). No Desk link: the demo Desk is RFA's dispatcher only.
- **Your airline (`/workspace`, was "Workspace")**: the airline name and a lock with "Private to your airline" and the
  sign-up card's (i) (one shared sentence, `WHO_READS` in onboard/pages.js); the
  status is said once (the Overview's status card, else the header pill: Not submitted, Pending
  verification, Verified, Declined); while not submitted only Overview, with "Step n of 9";
  otherwise Overview, Your answers, Data feeds (the format and a dry run) and Assistant (the model
  choice). Sign out and Delete account live in the account menu. (Amended 17 Oct 2026, 7.36: the
  setup kit is gone; `/workspace/kit` answers 404.)
- **Desk**: the account menu's **Data connections** (Connect's dispatcher tools: keys, the sample
  feed, a file upload); visitors do not see it. The demo Desk is RFA's dispatcher only (owner, 17
  Oct 2026): it has no Airlines to verify.
- **TEPHRA staff (`/admin`)**: staff sign in with their own accounts and verify or decline each
  submitted airline (Review…: the answers, the hints, the private history, a note or a reason;
  it approves no policy and publishes nothing) or delete a declined one's record. With hosting
  off the page draws only the airlines (All, To verify, Verified, Declined), the onboarding count
  and the staff accounts; the free-tier tiles, Approve hosting, Suspend and the rest appear only
  with hosting on. Decline… asks again, with the reason, in its own step. Status words are the same
  with hosting on or off ("Pending" beside To verify; a decided row says "since <day>"). The nav
  pill is "Staff", the account button shows the staff member's name; "TEPHRA staff" is said by the
  page title, sign-in, the join page, the footer and the history ("Verified · TEPHRA staff
  (<name>)"); "operator" stays a code name.

Honesty placements: ILLUSTRATIVE on both Ash policy cards and Review's policy row; "Running your
airline on this site is not switched on yet." once on the onboarding landing and once on the workspace Overview (7.36), Policy B (its card), recovery for the airline's network, and password reset by email
(Review, sign in); NO MODEL on the Assistant card with no model; DRY RUN · NOTHING TAKEN IN on the
dry run; "Pending verification" as the status pill; Private on the landing card and the workspace
header; decision support only in the sign-up acknowledgement and its (i) (no page footer, 7.36);
Google's unpaid tier
may use what is sent, on the Gemini or Gemma card.

### 7.34 Basalt & Paper on the pages (17 Oct 2026)

The palette is in 3.1; what it changed on each page:

- **Every page:** the dashed brand tick (34x3 px, `--c-brand`) under the TEPHRA wordmark
  (`topnav.css`); Sign out is neutral, not red. Pinned-dark pages use `theme-color` `#100e0c`.
- **Home:** no amber or magenta glow; the headline's emphasis is an ink underline; the flow is one
  neutral dotted wire (`--c-line-input`, dash 2 6, no gradient) and its pulse is neutral; nine contour rings are drawn on the `#home-ash` canvas
  (`home/ash.js`, colours `--home-contour` / `--home-contour-index` from `.home__sky`); the same dashed
  rule stands over the headline (the eyebrow went, 7.36). The Example card's amber bar stays (it is TEPHRA's flag there).
- **Demo and the Wall:** the assistant's NO MODEL word is a dashed mono stamp; ILLUSTRATIVE is a
  square stamp with a faint hatch; TEPHRA's area label is dashed amber; LIVE is a solid neutral chip.
  A SERIOUS discrepancy, a failed backtest check, a FAIL scorecard and cancelled flights are caution
  with a heavier edge (dk tone `warning`), sorted after real alarms in "Needs a look"; a rejected
  advisory or plan is neutral. On a phone the open map key ends above the time pill and scrolls.
  The Satellite reader's box is cobalt `--c-sat` `#4088c4` with a dark casing (white is the plan;
  10.5 CIEDE2000 or more from every map colour in all four visions). The Inside TEPHRA catch-up
  pulses that start on the map take the night map's colours and their labels are night chips in both
  themes (`mapColours()`); the active step is a tint and the node ring, no edge bar. "Off" and "not
  read" pills are dashed (not connected); the real recovery code sits in a solid box.
- **Onboarding and the workspace:** every field error is `--c-invalid` with the filled caution
  triangle and the words; refused upload rows the same; only offline or a server error on submit is
  red (`.err--alarm`). A declined airline is neutral (`st-off`). Delete account is the stone fill.
- **The Desk** (dark): field errors, the text counter over the limit, a crew-report contradiction and
  a 422 "Correct these" panel are `--c-invalid` (`.msg--invalid`, `.panel--invalid`) with the triangle;
  "No plan found" and a scenario with no solution are caution; closures are the white ⊘
  (`.clo__icao` uses `st-closed`); flights inside the ash read in `--c-tephra-text`; Reject, cancel
  decisions, airline declined and "Desk switched off" (`.panel--off`, dashed) are neutral; the
  Coordinator brief and the assistant chip are neutral, never amber; the map key's "This flight"
  swatch is the white ring. Sign-in, Reject, crew-report, connection-name and 422 sign or reject
  errors are `--c-invalid` with the triangle; red stays for offline and the server. A lock-out is
  caution, visitor access off is neutral. A failed specialist call is caution. The assistant chip is
  dashed when off (code only), the fictional-airline and draft chips are dashed (examples), TEPHRA's
  area swatch and its label box on the map are broken (corners only). The picked plane is amber only
  when TEPHRA flags it, and the key says "TEPHRA's area" only while that area is drawn.
- **The printable document:** its paper colours are one `--paper-*` block in `doc.css` (the page is
  pinned dark for its bar); CRITICAL severity is caution with a 2 px edge.

### 7.35 Said once (17 Oct 2026)

The owner, looking at the demo: "don't say no model everywhere", "why are you putting tephra
assistant again after assistant tab", "you can hide this in a info icon or something, but current
there is too much text". One short line stays on screen; the explanation is one tap away.

- **The info button** (`tephra/web/wall/info.js`, one component for the demo, /assistant and the
  Desk; its look is `info.css`, loaded by `index.html` and `desk.html`): a real `<button>` (16 px
  glyph, 44 px hit area) with `aria-expanded`, `aria-controls` and a topic name ("About replay",
  never "More info"), described by an sr-only span holding the same words, so a screen reader
  hears them without opening it. The popover uses the browser's Popover API (top layer: no panel,
  map key or sticky header clips it), one open at a time; a tap outside, focus leaving it, Esc
  (focus back on the button, the page's own Esc not also fired) or a resize closes it; keys typed
  inside never reach the demo's shortcuts; a click on it never ticks a label it sits in, and a
  press on its own words keeps it open with focus on the button (only its links and buttons take
  focus). `face`
  makes a chip its own (i) (the Desk's REPLAY chip); `wireInfo()` wires an (i) written in the
  page's HTML (the Desk's sign-in card).
- **The AI state, once per screen** (`wall/x-parts.js stateLine`, shared by the demo's tab bar,
  the /assistant title and the Desk's header): nothing while the model is on; otherwise a dot and
  "AI off" (dashed), "AI paused" or "AI unavailable" with an (i): "Offline stub: no model is
  connected. Code checks still run, and code templates write the drafts." / "Code still reads
  every feed and checks every flight. Must-do flights come straight to you." / "<skill> gave no
  result. Nothing was put in its place; code still checks every flight." with "Why ›" (demo) or
  "Assistant details ›" (Desk). The screen-reader text keeps the state in every case. These three
  status words are the one place "AI" is a visible word besides the first-use line, About and the
  tooltips (the lead's decision A over the "AI" rule in CLAUDE.md, so "Assistant" is not repeated
  beside the Assistant tab). Gone: the "TEPHRA Assistant" heading row under the tab, the "NO
  MODEL · offline stub" stamp, "Code orders the jobs (no model)", the gate's "No model · code
  templates / Skills run as code, no model is called", the Desk idle pane's AI line and the off
  sheet's "no calls" line.
- **Per-item marks:** text a code template wrote carries the small "{ }" mark (`codeMark()`;
  tooltip and sr-only "Written by a code template", or "Ordered / Counted / Picked / Read by
  code"), never "NO MODEL" words or "(code only)" suffixes; AI-written text keeps its mark, so a
  day with the budget closed still tells the two apart. Server text, exported documents' labels
  and the raw lines under Technical detail are unchanged.
- **You decide:** the count and "advisories wait for you"; "Drafts wait at the Desk for a
  dispatcher. Nothing leaves TEPHRA until a dispatcher approves." is its (i) (the tab, /assistant,
  the Details foot).
- **The demo's status line:** "Policy A (i)" (illustrative values, not an airline SRA) and
  "RFA (i)" (the fictional airline), instead of hover-only titles.
- **Said once, also inside the sections (fix pass, 17 Oct):** Details › TEPHRA Assistant says the
  off state in its lead only (no pill, chip, title, quota tile or note, no per-skill "Model" line);
  Details sections and the /assistant skill sheets turn "(code only)" lines into the "{ }" mark
  (`templateText`), and the Coordinator's code brief, which only repeated its line, is not quoted;
  paused or in trouble, the gate and the Coordinator row say what waits, not the state again; with
  no model the band between the Coordinator and the skills closes up. The status and the page link
  sit beside the side panel's tablist, not inside it.
- **The Desk:** one REPLAY chip with its (i) (10.1); Ask says the stub once and keeps its sub-line
  in the title's (i); sign-in errors are one or two words (11.8). No "Decision support only" chip
  is added anywhere (the owner: "don't put this everywhere").

### 7.36 Said once on the site pages, onboarding and the workspace (17 Oct 2026)

The owner, on the footer "Decision support only. Not for operational use.": "don't put this
everywhere"; on the sign-up card's privacy note: "no need to put so much information, you can
always collapse it"; on the sign-up form: "why so much text after warning sign, keep it modular";
on the setup kit: "drop it"; and "nobody is going to read so much, don't overwhelm with
infomation". Every (i) on these pages is the one info button of 7.35 (`wall/info.js`, `info.css`).

- **No decision-support footer.** No page's chrome says "Decision support only" or "Not for
  operational use" (Home, Guide, Privacy, the demo, the Desk, onboarding, the workspace;
  `tests/test_footer_said_once.py`). It stays once where it matters: the demo's welcome dialog
  (its facts line), About › Safety limits (the Guide's About fold, anchor `#what-is-real`), the
  sign-up checkbox's (i), and Home's line ("a dispatcher approves"). Link previews, `og.svg`,
  generated documents and their labels keep their own words. No "Decision support only" chip is
  added anywhere.
- **Home:** the eyebrow went (the brand's dashed tick now stands over the line); "Already
  onboarded? Sign in to your workspace" became "Sign in" in the top bar (only while the server
  shows onboarding); the footer is Credits and Privacy, plus Guide below 1100 px where the top bar
  hides the nav. The headline, the two choices and the picture are unchanged; no replay or
  fictional-airline words on Home.
- **Guide:** the title "A volcanic-ash decision desk" and a 15-word lead; three chips (Fictional
  airline, Nothing sent to aircraft, Replay; each with its full sentence for screen readers) and
  "What is real?", which opens About at Safety limits; the five steps show names only (the lines
  are screen-reader text, `stepsList({ lines: "sr" })`); the case is one line and "What went
  wrong" now opens the rest on the Guide too. Tours: each legend shows titles; the one sentence
  shows on hover, focus or a tap (screen readers always hear it). Marks: the demo 5 (This case,
  TEPHRA Assistant and Decide on the Desk went), the Assistant 5 (Skills and Play merged), the
  Desk 4 (the tab bar and Ask went), the phone review 5 (Record went). Try it is five steps of
  five words or fewer. Every fold is closed: Map key and words, How it works (the eight-step flow
  went; the five steps say it), About and safety limits ("What TEPHRA is" went), Operator policy
  (illustrative), Credits (its own fold, still `#about-credits`), Run it on a laptop (the two
  commands and the Google Cloud line; the "Your airline" card went). The section nav is Start,
  Try it, Map key, About.
- **Privacy:** an "In short" box of five lines, then each section closed under its heading;
  `privacy.js` opens the one a link names (`/privacy#accounts`). The visitor's public name is said
  once, in the Desk section. The setup kit, its zip and the Ollama address are gone from the text.
- **Sign-up:** the privacy note is one line, a lock, "Private to your airline" and an (i) holding
  the full sentence and the Privacy link. "Work email" has no hint; the password label is
  "Password · 12+ characters" (the rule is also in `aria-describedby`). Errors are terse with the
  caution triangle ("Required", "Not an email", "12+ characters", "Tick to continue"), shown only
  once a typed field is left or on submit, never before; an empty submit focuses the first bad
  field and marks each. The tick reads "I understand TEPHRA is decision support only"; its (i)
  ("A person decides, and nothing is sent to an aircraft.") sits beside the label, outside it, so
  tapping the (i) never ticks the box and tapping the words still does. Server error words are
  unchanged. Sign-in and the recovery code page follow the same rules.
- **The onboarding pages:** one short line under each heading (10 words or fewer); what explained
  it sits in an (i) on the heading, a section, a label, a hint or a chip. The landing is the title,
  the sign-up card, a closed fold "What you will provide" (nine one-liners) and one line "Running
  your airline on this site is not switched on yet." The step shell is the step list, "Step n of
  9" and the Saved mark. The AI model cards (page 8 and the workspace's Assistant) are a title and
  one line; Gemini's line is "Your key · data use" with an (i) holding what TEPHRA sends (public
  ash feeds and the facts code writes), Google's unpaid-tier data use and the Privacy link, also read to screen readers on its radio before it is chosen.
- **The workspace:** the Overview says the status once (a pending track, "Verified." with an (i)
  saying verification checked who you are and approved no policy, or the declined reason), four
  one-line rows and "Running your airline on this site is not switched on yet." The status (i)
  stays on the line with the last word, and a model name keeps its "·" with it, so at 390 px no
  (i) or "·" is left alone at a line's end. On a phone the account chip shows only the ICAO code
  (the name stays for screen readers) rather than a cut name. Data feeds is a
  closed "The format" fold, one drop line and the DRY RUN stamp with its (i). If the account does
  not load, the onboarding landing says "Your account did not load" and why, never "Answers
  submitted".
- **The setup kit is gone** from the onboarding pages and the workspace (the kit preview, Download
  setup kit, its checklist, the made-in-your-browser chip, the Gemini key and Ollama address
  fields that only fed it, the fleet settings preview and "Sending for real"; `workspace/kit.js`
  and `zip.js` deleted, `.env.airline.example`, the kit's airline.env template, deleted), from README.md, docs/ONBOARDING.md (its file table and "Run your own
  TEPHRA"), the glossary, the Guide and Privacy. `tephra/web/kit/push.py` stays and is documented
  as the push tool; the own-fleet settings stay. The onboarding tour's screenshot is retaken once
  the onboarding pages settle.

### 7.37 Said once on the hosted airline pages (17 Oct 2026)

The rules of 7.35 and 7.36 on the pages of a hosted airline (`docs/HOSTED.md`; the feature
`hosted`, off on the deployed site). Every (i) is the one info button (`wall/info.js`, `info.css`).

- **State chip.** SHADOW and LIVE each carry one (i) beside the chip (no tooltip-only words):
  SHADOW "TEPHRA runs on your real flights; every draft says Shadow · not for use. Nothing is sent
  to aircraft."; LIVE "Switched to LIVE on … by …. Nothing is sent to aircraft.". Not started,
  suspended and "not updating" add none: the chip and the red line say it. At 480 px and less the
  map's header chip drops its clock (the time bar shows it), so the map header stays two rows.
- **No decision-support footer.** The space's footer is "Private to <name> and TEPHRA staff"; the
  console's is "TEPHRA staff only" and its (i). Every SHADOW stamp,
  `SHADOW - NOT FOR USE` line and Record SHADOW tag stays (`tests/test_shadow_stamp.py`).
- **AI state once.** Settings › Assistant says "On", "AI paused" or "AI unavailable" with its
  reason and one (i); "Not chosen" for a missing model; "Not built: Ollama on this site.". The
  map's Plume tails say "did not run", never a capitalised `AI UNAVAILABLE` beside the status.
  An airline with no usable model (no model, no key, an unreadable key) is its own state,
  `unavailable` (`aiStateOf`, from `BudgetView.unavailable`), never "on" or "On · 1 problem": the
  map's tab bar and the Desk's header say "AI unavailable", and the (i) gives the reason and
  "Fix it in Settings › Assistant."; Details › TEPHRA Assistant and the assistant sheet lead
  with "TEPHRA Assistant is unavailable."; its refused steps are part of the state, and a place
  without its draft says the skill "did not run". The Record says "Assistant step did not run"
  for such a step, "gave no result" only where a model answered with nothing usable. On the
  airline's Desk the status and its (i) move into the airline bar together.
- **The airline's own code.** An airline's pages name its code from the first paint, also in
  setup when no state ever arrives; the demo's fictional RFA marker is removed from its map, and
  the Desk's empty VAR list says how many of its flights are in the ash and that none has an
  advisory yet, never "none needed" while flights are inside.
- **Paperwork rows.** A SHADOW document or handover carries its stamp on its row in Paperwork,
  above the title, as the Desk's cards do, not only once opened.
- **Forms.** Hosted forms (`hosted.js` `checkedField`, the workspace go-live dialogs, join and the
  console) build on `onboard/form.js`: a label with its rule ("Name · 2-48 characters",
  "Password · 12+ characters"), terse errors ("Required", "Not an email", "2+ characters", "Not a
  Google AI Studio key", "Tick to continue", "Type RFB") shown after a typed field is left or on
  submit, in `--c-invalid` with the caution triangle. Action answers (`.hstatus`) are caution, not
  red; red stays for real alarms (a pause, a feed outage, a suspension, a broken record chain).
- **Uploader.** Feeds offers "Download uploader" and its (i) to every member, from
  `GET /a/<ICAO>/api/tenant/feeds/uploader`; with hosting on `/static/kit/` answers 404, checked
  on the path the static files resolve (`server.PageFiles`), so `//kit`, `./kit`, `x/../kit` and
  another case answer 404 too. With hosting off `/privacy` drops its parts between `<!-- hosted -->` and `<!-- /hosted -->`.
- **Workspace.** The go-live cards say one short line each, the rest behind an (i); the site-limit
  line shows until the airline has its space, then the places line beside Start says it. Once the
  space exists the workspace nav drops Data feeds and Assistant, and their addresses open the
  space's Feeds and Settings › Assistant. `infoTail` (`onboard/form.js`) keeps an (i) on the line of
  its last word at 390 px.

## 8. 3D, compare, the time bar and the height filter

### 8.1 3D mode (D)

`easeTo({ pitch: 55, bearing: -20, zoom: flat fit + 0.35, duration: --dur-camera-long })` (round 2: the old zoom-out showed half of Asia), enable drag-rotate with tilt (right-drag or Ctrl + drag turns and tilts, `pitchWithRotate: true`; two fingers on a touch screen; off again in 2D) and say so in a map pill ("3D, heights ×6: right-drag or Ctrl + drag to tilt and turn · Back to 2D"), set sky
(`sky-color #0b1220`, `horizon-color #1b2430`, `fog-color #07090d`, blends 0.6/0.6/0.8). Add, in
this order (extrusions share the depth buffer; inner first): `official-volume` (now-valid
official features, `--c-official`, opacity 0.45, base/height = `base_ft`/`top_ft` × 0.3048 × 6,
vertical gradient off), `tephra-volume` (cone part, `--c-tephra`, 0.14), aircraft lollipops (a
2.5 km box at `alt_baro_ft` ± 300 ft on a thin stem from the ground, amber for exposed, grey
otherwise; stems 0.55, boxes 0.95), and each RFA flight's path into the area (`exposures`, kind
`path`) as a 1.2 km band at its level ± 250 ft (± 500 ft for the picked flight), `--c-tephra` at 0.5:
track and level held, as the advisory says, so it is seen flying into the ash volume. No descent or
landing is drawn: TEPHRA has no planned profile. No 3D terrain while volumes are shown (it shifts levels). A
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
| `A` | AI at work (7.21) |
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

Row 1 (48): "TEPHRA" (700, letter-spaced) + "Desk" (text-3, hidden at 430 px and under); in
REPLAY the chip "REPLAY 1032Z" on the replay clock (`#mode-chip`, `desk/modechip.js`), which is its
own (i): feeds rebuilt from archives, the clock shows that day, Ring of Fire Air is fictional; the
AI status `#budget-chip` with `#model-chip` as its label (7.35): only the assistant mark while it
is on, otherwise a dot and "AI off", "AI paused" or "AI unavailable" with an (i) (the words of
`wall/x-parts.js stateLine`, plus "Assistant details ›"); its aria-label keeps the full state;
when the row would scroll sideways the connection words and gaps go first, then the wordmark and
REPLAY chip compact, then the AI (i), the status's dot and the REPLAY glyph, then the REPLAY clock;
the AI words go last, only on a row narrower than any phone (a 390 px phone reads "AI off"); never red; it
opens the TEPHRA Assistant sheet; the connection `#conn`, always a word with its shape: `st-ok` "Connected" (not
"Live", which under the REPLAY bar would read as live data), `st-stale` "Reconnecting…",
`st-serious` "Offline", `st-never` "Connecting…"; the account button (initials in a 32 px circle,
menu: "Signed in as AK · session ends 1830Z", "Display: LIVE" with "Change display…" (10.10), and
"Sign out"). Above that row, the header's top row, the frame strip (`#frame.frame`, `role="note"`,
the Wall's strip, 7.1): in REPLAY the violet REPLAY
part (`#replay-bar`: `i-replay`, "Replay · recorded feeds from 05 Sep 2026 · not live", the case
title and an automatic switch in its tooltip and `#replay-case`) on the left and the disclaimer on
the right with the info icon (14 px semibold text-1, 12 on a phone, wraps balanced, never
truncates); violet only on the REPLAY part; live, the disclaimer alone. On a phone the two are two
short lines. Sheets and dialogs open below the strip (`--dframe-h`, measured by desk.js) with their
backdrop starting there, so the strip is never covered or dimmed, while the brand row, the
assistant chip and the avatar are dimmed with the page (they cannot be used while a sheet is open). Cards, the
review, Ask answers, messages, notices, crew reports, airport plans and Paperwork rows carry no
REPLAY tag; a record from the other mode shows "From a replay" (`fromReplayChip`). `#net-banner` (offline, back online) under it. `state` is read from `GET /api/state`
at start and from `state` events; until then the static HTML disclaimer is shown.

Tabs `#tabbar` (R10.2, 10.17): Decide, Airports, Paperwork, Ask, a `role="tablist"` of
`role="tab"` buttons with `aria-selected`, each an icon and a word. The `data-tab` keys `queue`,
`ask`, `network`, `docs` and the `sessionStorage` key `tephra.desk.tab` are unchanged. Only Decide
has a badge (neutral, text-1 on surface-3): `waitingCount()`, the same number as Decide's count
line and the page title, and its `aria-label` and title say what it counts ("Decide, 30 waiting: 5
advisories · 23 flights to plan by hand · 1 airport plan · 1 document to sign").

### 10.2 Sign-in

Two panes, one screen (15 Oct 2026). At 900 px and up the view fills the height under the header
and the page does not scroll. The left pane says what the Desk is: the headline "TEPHRA drafts. A
person decides.", a small drawing (the official area inside TEPHRA's wider estimate, a flight
heading in), the safety line "Nothing reaches a real aircraft or system." and "Watch the demo,
no sign-in" (the three steps went on 17 Oct 2026). The right
pane is the card (max 420): title, `#login-pending`, the form message, then the ways in. Below
900 px the panes stack and the left one keeps only the headline, the safety line and the Wall link.

The title is "RFA dispatcher · demo" with one (i): "RFA is a fictional airline; you play its
dispatcher on a replay." (on live public feeds when the server runs LIVE). While `/api/state`
says `visitor_access`, two tabs
(`#login-tabs`, `role="tablist"`, arrow keys move) choose Visitor ("No PIN") or Dispatcher ("PIN");
the first choice is Visitor unless this browser has signed a dispatcher in before. Visitor: an
optional name and "Enter as a visitor →", then one line "Your decisions are public." with an
(i) (written in desk.html, wired by `wall/info.js wireInfo`): they go into the public record as
visitor:<your name>, and visitors cannot change the display or the feeds.
Without visitor access only the PIN form shows.

The PIN form: name (autocomplete `username`, 2-32 chars) and PIN (`current-password`, numeric
keyboard `inputmode="numeric"`), each with its icon inside the field, labels above, errors under
the field (`aria-describedby`), an on-screen PIN pad (hidden on a short computer screen with a
fine pointer, where the keyboard types the PIN), button "Sign in" (primary neutral), and the hint
"Your name goes on each decision in the public audit." with Privacy; "The PIN is never stored."
is the (i) beside the "Desk PIN" label.
Errors (11.8): bad PIN, too many attempts (button disabled with a countdown from the `Retry-After`
header), desk disabled, offline. A deep link waiting for a session shows "Sign in to review
RFA1225." above the ways in (`#login-pending`, the flight named from the public
`/api/advisories`; "Sign in to review this advisory." until it is known). On success: focus moves
to the Decide title and the hash resumes (10.14).

### 10.3 Decide (was Queue)

Title "Decide" (`#q-title`, 24) and a ⋯ button (`#q-more-btn`, `aria-label="More actions"`,
`aria-expanded`, Esc closes and returns focus, arrow keys move) holding "Report ash from a crew"
(`#crew-report-btn`, 10.15), "Paste a notice" (`#paste-notice`) and "Reload the lists"
(`#refresh`, spins while loading). Pull-to-refresh and the
refresh on every `advisory` event stay. Sort: the act-by order (10.17, `byActBy`), which replaces
"inside now first". 10.17 replaces items 1 and 3 below (the lead card and the deadline groups);
the rest stands. In order:

1. The Next decision card (`section.next`): eyebrow "NEXT DECISION" (`#drafts-title`), "1 of 23
   advisories · most urgent first" (`#q-count`), the breakdown "23 advisories · 3 messages · 2
   flights to plan by hand" (`#q-breakdown`, shown only with drafts and messages or hand work), then
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
2. `#fail-section`, when the AI left flights to a person: the Plan by hand card (10.16) with the
   cause once, the counts and "Show the 23 flights". It is never folded. The list opens in the
   right pane at 1100 px and up and as its own view on a phone.
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
   and the raw stub text. Must-do flights the Duty Officer did not hand out carry "Must do" in
   Plan by hand; any other must-do work stays in a caution box here (UI-AI-QUIET K92). A run that
   did not run reads "Duty Officer: no brief this run · its must-do flights are in Plan by hand"
   (the cause is said once, in the Plan by hand card).
5. `#closed` "Decided since 0955Z · 2" (10.17), a collapsed `<details>`.
6. `.qfoot`: "Approved text goes only to TEPHRA's own outbound queue. Nothing is sent to an aircraft
   or any real system."

States: loading (skeleton rows), empty ("No drafts waiting." + "A draft appears here when a
flight's projected track enters TEPHRA's estimated ash area. Last update 16:07:12Z.", or, while
flights wait to be planned by hand, "No drafts to approve." + "23 flights to plan by hand are
below."; one calm line inside the Next decision box, not a dashed box in a box), error
("Can't load drafts." + the reason + "Try again"), offline (10.9), a new draft (announced "New
draft: RFA4821, HOLD FL250, enters in 12 min").

### 10.4 Review sheet

Opens from the Next decision's button or a row (full screen on phones, the right pane at 1100 px
and up). Header: back "‹ Decide" (hidden in the pane), title "Review RFA1225" (`#s-title`),
"Version 1". The primary facts come first, above the action bar:

- closed or HYPOTHESIS banners when they apply; no REPLAY chip (the frame strip says it, 7.1),
  except a replay draft opened while live feeds play: "From a replay · Drafted while a replay
  played, not from live feeds";
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
  and the receipt line (10.17) is pinned above it. There is no bulk
  approval: the next draft needs its own hold or confirm. With no draft left the sheet closes and
  focus goes to the empty state.

### 10.6 Edit and approve

Sheet view "Edit RFA4821": textarea (Plex Mono 16, upper case as typed with
`autocapitalize="characters"` and a CSS `text-transform` preview; the value sent is what was
typed), 9 rows, counter "312 / 400" under it (caution at 380, and above 400 blocked in `--c-invalid` with the triangle: a form error, never red),
`aria-describedby` to the counter; "Show the drafted text" disclosure with the original body; a
note "Both versions are kept in the audit log. The header with sources and times is written by
code and cannot be edited." Primary "Approve edited text for RFA4821" (approve style, the same
hold-or-tap rule), secondary "Cancel". 422 shows `problems` under the field.

### 10.7 Reject

Sheet view "Reject RFA4821": reason textarea (required, 3-500 characters, counter), quick
reasons as chips that insert text and stay editable: "Flight already outside the area", "Level
already outside the ash band", "Duplicate of another draft", "Ash data look wrong";
note "The reason is recorded in the audit log. A rejected draft is not queued." Primary "Reject
draft for RFA4821" (the neutral filled button, never red, 10.17; tap only, no hold), secondary
"Cancel". "Reject…" in the review's bar is a neutral outline at the same width as "Edit text".

### 10.8 After a decision; conflict

- Decided stamp: on success the action bar shows, for 1200 ms, `i-approved` (40 px) +
  "Approved" (28 px 700 `--c-approve`; `i-rejected` + "Rejected" in `--c-reject-text`), the action
  and flight, and "AK · 1607Z · queued, not sent to any aircraft" (16 text-2), above a 3 px rule
  in the same colour. It is not interactive; it enters with a short scale-in that reduced motion
  drops (the 1200 ms hold stays). Then the sheet closes and the toast follows.
- Replaced by the receipt line (10.17, D3): the decision toast and its 15 s are gone; toasts stay
  for "Back online." and the session warning. Kept for the record:
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
REPLAY of {label}? Viewers see REPLAY in the strip at the top. The switch is recorded in the audit log under
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

- Reach (two taps): Decide › ⋯ › "Report ash from a crew"; the Wall links `/desk#crew-report`.
  There is no second button for it on the Decide tab.
- The Decide link `#crew-section`, shown only while there are reports: one line, "Crew reports of
  ash (3) · 2 with a caution area · 6 flights flagged" with "⚠ 2 outside the official area",
  closed until opened (the queue stays the tab's one primary thing). Open, it holds one row per
  report (short state word with its shape, "RFA6186 · FL280", "⚠ outside the official area ·
  reported 4 min ago · near Slamet (100 km)"); a row opens the record. Drafts of flagged flights
  are marked in the queue itself, not listed again here.
- The form (bottom sheet "Report ash from a crew"): the lead line; Flight (a select of the
  tracked RFA flights, airline callsigns only, "RFA4259 · BTK6401 · FL360", and "Another flight:
  type its callsign"); What the crew reported (toggle chips: Ash seen, Haze or dust in the cabin,
  St Elmo's fire, Engine signs, Sulphur smell, No ash seen) with the live result line ("Draws a
  crew report caution area of 60 NM around the position." for ash seen, St Elmo's fire, engine
  signs, or a sulphur smell with haze; "A sulphur smell alone is recorded as a routine report: no
  area is drawn. With haze or dust in the cabin it draws one." and the same for haze alone;
  "Recorded. A no-ash report never removes or shortens any
  area.", "'Ash seen' and 'No ash seen' cannot both be reported."); Reported level ("FL [350] to
  FL [ ]", the margin from the policy, "A report with no level is refused: TEPHRA never invents
  one."); Observed at (UTC) (Today / Yesterday with their dates on TEPHRA's clock, HHMM, "Now";
  a time later than TEPHRA's clock or older than the area lasts is refused under the field at
  once, "1159Z is later than TEPHRA's clock (1035Z): a crew report cannot be in the future.",
  and Position then says "Correct the time first", so no position is asked for; the fix lookup
  refuses such a time too); Position (after the flight and the time: "ADS-B fix of RFA4259 at 1046Z: 6.20S 109.40E, FL360.
  The report is placed at this fix." from `GET …/crew-reports/fix`, or the server's "No ADS-B fix
  of … within 90 s of …: type the position the crew reported" with latitude and longitude in
  degrees and N/S, E/W selects that start empty, marked "Typed by dispatcher"); Remarks
  (optional, 300). Numbers in hints come from `GET /api/policy` (`crew_reports`).
- Refusals: the page checks the empty and malformed fields and the time against TEPHRA's clock;
  the server checks everything again and lists every problem (422), the time before the position.
  Both show "Not recorded. Correct these and record it again:" at the top and each problem under its
  field (no flight, no cue, "A crew report needs the reported flight level or band; TEPHRA never
  invents one.", a time in the future or older than the area lasts, no position, a typed position
  when a fix exists). A position problem looks the fix up again.
- Recorded: the toast "Crew report recorded: RFA4259 · caution area drawn · 4 flights flagged.",
  then the record in the sheet with "Recorded under AK at 1047Z. The Wall shows it now; the
  audit log has the entry." and "Report another". Flights flagged comes from the report's own
  `flagged` (the server's answer), named from the picture's flags or the tracked flights, so it
  is right before the `crew` event arrives; the open record redraws on every new picture.
- A report's record (`openCrewReport`, from a row, "See the report" or `#crew/<id>`): the state,
  age, and "From a replay" only while live feeds play (7.1); the outside box ("Crew report outside the official area" with the
  server's `outside_detail` and "Pass the difference on to the weather office and the VAAC (EUR
  Doc 019 3.2.9 e)."); one line of what the area does now (active or covered: the label and that
  it flags flights; withdrawn: "Withdrawn by AK at 1052Z: Wrong position. Its area no longer
  flags any flight; the report and its audit entries are kept."; expired; no area); Crew
  reported, Level, Observed, Position, Near, Caution area, Wind stretch, Flights flagged (active
  and covered only), Covered by, Entered, Remarks; "Technical ids". Footer, stacked: "Start a
  message to the weather office and VAAC" (any report of ash not withdrawn; the main button when
  the report is outside) and "Withdraw (entry error)…".
- Withdraw: "Withdraw only an entry error: the wrong flight, position, time or level. The report
  and its audit entries are kept. A later "no ash" report is not a reason: it never removes an
  area." Reason required (3 to 500), quick reasons Wrong flight, Wrong position, Wrong time, Wrong
  level, Entered twice; "Withdraw report" (reject style); 409 "This report is already withdrawn."
  Done: "Withdrawn by AK: Wrong position. Any message started from it is withdrawn too."
- The message: `POST …/{id}/message` opens the message draft in the Paperwork sheet ("Message to
  the weather office and VAAC: crew report from RFA4259"): To (the MWO for the FIR, the VAAC),
  From, Subject ("CREW REPORT OF VOLCANIC ASH OUTSIDE THE PUBLISHED VA AREA"), the code-written
  text, what it rests on, and one Dispatcher signature line; nothing is sent. Paperwork lists it
  as "MSG". When its crew report is withdrawn the message is "WITHDRAWN: not to be sent" and
  cannot be signed.
- On drafts: a flagged flight's Next decision card and row carry "Crew report of ash on this
  route" ("This flight's crew reported ash" for the reporting flight; first caution). The review shows the crew box (dashed ivory edge): "Crew report of ash
  on this route", "RFA7554 is inside the crew report area now." (or enters in n min), one line per
  report with "See the report ›", and "Crew report caution area (operator policy A, not a VAA or
  SIGMET). A flag only: nothing was re-planned."
- The reason box: for Keep watching (MONITOR) or Continue (CONTINUE) on a flagged flight (every
  tracked flight is airborne), "Reason to keep watching on this route (required)" with "Recorded
  with the decision and in the audit log. The crew report stays on the Wall either way.", 12 to
  500 characters (`approvals.MIN_CREW_REASON_CHARS`). Until it is filled, the approve button is `aria-disabled`, its hint reads "A crew
  reported ash on this route: write the reason above before approving.", and a tap on it moves to
  the box with "Give a reason of at least 12 characters: a crew reported ash on this route." The
  confirm step repeats "Reason (crew report of ash on this route): …". The reason goes as `reason`
  with approve and with edit and approve (Edit shows the same boxes). A 422 `reason_required`
  (the server saw a flag the page had not drawn yet) opens the box with the server's words.
- Mode: the picture is of the current mode; a draft of the other mode is never matched to it.
  The queue itself lists only the drafts of the mode playing (as the server's `open_drafts`
  does); the others are counted under the Next decision header ("30 replay drafts set aside
  until that replay plays again").

### 10.16 Desk redesign, 13 Oct 2026: Plan by hand, one honesty band, a pane never empty

What was wrong, on the live site (REPLAY, Google had closed the day's free calls of the model
that plans and drafts): "Problems to acknowledge 50" as 50 near-identical red cards in the 420 px
column, each repeating the raw reason, "No substitute plan or template was made. Decide this
flight by hand." and a full-width "Mark handled…", while the Wall said 23 flights; cards stamped
"left undone at 1143Z" with the replay clock at 1045Z; a huge dashed right pane ("Choose an
advisory to review") with nothing to review; the REPLAY bar and the disclaimer on two rows;
trailing separators; raw codes in sentences. The 50 against 23 and the 1143Z were a data bug,
fixed in the backend (MODULES.md 4.4 and 5.7): a replay plays its recording again on every run,
failures of earlier runs and builds were never closed, and each new cone made a new failure for
the same flight. Now a flight has at most one open failure, and a run lists only its own.

This section was merged with docs/UI-AI-QUIET.md (K77-K85), which is the base for every AI word:
the header chip, the "AI today" sheet and the cause words come from `aiStateOf()` and are never
red. What this section adds is the layout: a summary and a list instead of 50 cards or a long
inline group, the list-detail panes and the bulk sheet.

What it follows: the list-detail layout (Android's canonical layouts,
developer.android.com/develop/ui/compose/layouts/adaptive/canonical-layouts: two panes when the
window is wide, one at a time on a phone, Back returns to the list), progressive disclosure
(7.18: the cause once, the flights in a scannable list, each flight's detail one tap away), and a
bulk action that keeps a person's decision behind every item: nothing is ticked for the
dispatcher, the confirm button counts what is ticked, and each flight is its own request and
its own audit entry.

The AI chip (`#budget-chip` with `#model-chip` as its label, `desk/budget.js`): the one state of
docs/UI-AI-QUIET.md 5.2 ("AI on", "AI paused · 0700Z real time", "AI on · 1 problem", "AI off";
since 8.4 and 8.6 "TEPHRA Assistant · on / paused / Drafter gave no result / off (code only)";
since 17 Oct 2026 the status of 7.35: nothing but the mark while on, "AI off / AI paused / AI
unavailable" with an (i) otherwise, a pause with no reason or time), caution for paused and trouble, never red. The sheet is the Desk's
one place that says why the assistant is paused and until when (UI-AI-QUIET 8.6). Its sheet, "AI today": the calm lead (UI-AI-QUIET
5.1), "What went wrong" by cause (each with its count, its times and what the dispatcher does
instead, the raw lines under Technical detail), "AI work waiting" (each job with "waits for AI
budget, next slot 0700Z real time"; since UI-AI-QUIET 8.7 "Waiting in line · 4", each job "waits
in line", or "waits for its slot (0700Z)" only when its slot is not the reset the lead already
says), "Calls today, per model" (what the model does, "1 of 450
calls" or "Closed", a bar, its state with a shape, the model id in small mono), "How the calls are
shared" (a disclosure: each lane's calls and the pacing sentence), "See the AI at work on the
Wall" (opens `/#ai-at-work` in a new tab), the count note and "As of …", in real time.

The honesty band: the REPLAY words on the left and the disclaimer on the right, one row from
600 px; on a phone two short lines (about 46 px instead of 58). Live, the disclaimer alone. Amended
the same day by 7.1: it is the Wall's frame strip (`#frame.frame`, same words, sizes and icon), the
top row of the header above the brand row, and only the REPLAY part is violet.

Plan by hand (`desk/failures.js`):
- The card on Decide (`#fail-section`, after the Next decision, UI-AI-QUIET K77), caution with a
  4 px left bar: "Plan by hand · 23 flights" and "Why ›" (opens AI today); the cause once ("No AI
  plan for these flights: AI paused until 0700Z real time. Nothing was substituted."), or one line
  per cause when causes differ; "12 inside the ash now · 11 heading in · 3 must do"; "Show the 23
  flights ›" (`aria-expanded`, `aria-controls="fail-pane"`; "Showing the flights ✓" while the list
  is open in the pane).
- The list (`#fail-pane`): the right pane at 1100 px and up (opened by itself when there is no
  draft to review), its own view on a phone ("‹ Decide", a history entry, so Back and Esc return
  to Decide with focus on the card's button). Title "Plan by hand · 23 flights"; the cause panel
  (caution: the cause once, "Decide each flight by hand, then mark it handled.", the raw reasons
  under Technical detail); "Mark several handled…" (only with two or more flights); then "Inside
  the ash now · 12" and "Heading in, soonest first · 11", one row per flight, must-do first: the
  RFA number (mono), "proxy for GIA616 · A320", "Must do" when the Duty Officer's newest run left
  it, the entry with its shape ("◉ inside now", "🕑 in 16 min"), "Anak Krakatau · since 1043Z" (and
  a short cause, such as "AI timed out", only when causes differ), and ›. One open failure per
  flight: the server keeps one, and the list keeps the newest.
- One flight (a row): the sheet "Plan RFA1701 by hand": Where, Aircraft (callsign, type, hex),
  Volcano, Since, What happened ("No AI plan for this flight: AI paused until 0700Z real time.
  Nothing was put in its place.", "Must do" when listed), the reason as recorded under Technical
  detail (with the model it would have used, the stage, failure id and cone), the quick notes and
  the note (optional, 500), and "Mark RFA1701 handled". Focus then goes to the next flight.
- Several flights: the sheet "Mark flights handled": "Tick each flight you have planned by hand.
  Each one is saved on its own, with the note below, under your name in the audit log."; "All 23
  flights" (tri-state) and a ticked list (none ticked to start, "Must do" marked); the note; "Mark 5 flights
  handled" ("Tick the flights you handled" while none is). It sends one request per flight
  ("Saving 3 of 5…"), marks each row "Saved" or "Not saved", and keeps the sheet open with the
  reasons when any failed.
- Announcements are one per batch (UI-AI-QUIET K84): "23 flights to plan by hand: AI paused until
  0700Z real time.", then only the change ("1 more flight to plan by hand."). Code closing a
  failure (a draft now waits for the flight, it left the area, the replay run ended, a newer
  failure for it) takes it off the list and is said in the same batch ("RFA1701 no longer needs
  planning by hand: an advisory draft now waits for it."). Nobody is recorded as handling it.

The right pane when nothing is open in it (`#idle-pane`, 1100 px and up): "Nothing waits for a
decision" (or "Choose an advisory to review", or "Plan by hand · 23 flights" with "Show the
flights" in the moment before the list opens), one line on the flights in or heading into the ash
("25 RFA flights are in or heading into the ash. A draft comes here once the AI has planned each
one."), the AI today sheet's calm lead, "Also waiting for you" (Airports: an airport plan,
Paperwork: documents to sign, each a link row), and "See the AI at work on the Wall".

Words: no semicolons in the Desk's own sentences; no trailing separators; no raw codes in
sentences (they stay under Technical detail).

Before → after, item by item:
1. 50 red cards repeating the same three lines → one caution card (the cause once) and a list of
   flights, one 56 px row each, grouped inside the ash and heading in; per-flight detail one tap
   away; "Mark several handled…" with a ticked list, one audit entry per flight.
2. 50 failures while the Wall said 23, "left undone at 1143Z" at 1045Z → the backend keeps one
   open failure per flight and lists only the replay run playing; `/api/duty` the same.
3. An empty dashed right pane and a cramped left column → the list of flights fills the right
   pane when there is no draft; otherwise the review, or a useful idle pane.
4. REPLAY and the disclaimer on two rows → one band.
5. "Anak Krakatau · left undone at 1143Z ·" → "Anak Krakatau · since 1043Z"; the reason as
   recorded → the cause in words, the code under Technical detail.

### 10.17 Desk redesign, 13 Oct 2026 (b): Decide as an inbox, a review that reads down

The build spec is `tephra-desk-redesign-spec-2026-10-13.md` (Inbox triage), ideas 1, 2, 3 and 5;
the naming (idea 4) was already in. Plan by hand (10.16) is kept as it is and is group 1 of the
inbox. This section wins over 10.1 to 10.8 where they differ.

**Act-by** (`format.js actBy`, `byActBy`; `byUrgency` is kept as its alias): a flight heading in
acts by its entry (drafted time + minutes to entry); a flight inside now whose draft changes it
(HOLD, CHANGE_LEVEL, REROUTE, DIVERT) acts now (its drafted time); inside now with MONITOR or
CONTINUE has no act-by and waits in Keep watching, inside longest first. Ties: the older draft.
Code sets this order; the Coordinator's order is only a note (its row stays on Decide).

**Decide**, in order: "Decide" and ⋯; one count line `#q-count`, "23 waiting · 3 due in 10 min"
(with hand work: "33 waiting · 23 flights to plan by hand · 10 drafts", parts that add up), the same number as
the badge and the page title (`waitingCount()`: advisories + flights to plan by hand + messages
+ airport plans + documents to sign); the drafts set aside from the other mode (`#q-breakdown`);
the receipt line on Decide when the last decision closed the review
(`#q-receipt`); "More urgent: RFA3001 · entry due now · Show" (`#q-newer`) when a more urgent
item arrived (the lead never swaps under the thumb); then:

0. The lead card (`#q-next`, the one card): "RFA1456 · MAS723" with the time cell; the action in
   plain words (16 600); "Anak Krakatau · now FL310 · entry due now" (the level now is ADS-B
   `alt_baro` from the Wall's aircraft layer, left out when the flight is not tracked); caution
   lines only when they apply (crew report, HYPOTHESIS, needs a careful read, sources stale, and
   "Drafted 12 min ago: entry time may have moved." past 10 min); the mark line; "Review RFA1456 ›"
   (filled neutral). No mono preview. At 1100 px and up the card is the selected row of the open
   review (left edge, no button).
1. Plan by hand (`#fail-section`, 10.16, unchanged). (The first-use line that followed it was
   removed on 13 Oct 2026, UI-AI-QUIET 8.4.)
2. BEFORE ENTRY · n (`#more-title`, `#cards`): one-line rows in act-by order, advisories and the
   messages for a flight still on this page; 5 rows, then "Show all n" (`#cards-all`). A message
   row shows its flight's time cell ("RFA1540 Crew briefing · EN 23 min"), the reason it sorts there.
3. KEEP WATCHING · n inside now (`#watch-section`): rows "RFA2408 · FL310 · Anak Krakatau ·
   inside"; 3 rows, then "Show all n" and "Review one by one ›".
4. OTHER DECISIONS · n (`#other-section`): the airport plan (`#plan-section`, "Airport plan · 3
   airports closed · to approve", opens Airports), each document to sign ("to sign", opens
   Paperwork), and messages not tied to a flight still on this page (`#msg-section`, "to approve",
   opens the message).
5. REPORTS · n (`#reports`): the crew reports, notices and Coordinator rows (`.qlinks`), in the row
   look (subject "Crew", "Notices", "Coordinator"; the words in 16; they open in place).
6. "DECIDED SINCE 0955Z · n ›" (`#closed-open`, the page-open time on the active clock), one row that
   opens the list in a sheet (newest first; a row opens the closed review); the footer sentence.

A row (`.irow`): subject (14 600), the action in plain words (16; it wraps, never cut), a caution
shape when one applies, a 6 px dot while new, the time cell, ›. Time cell: "now" or "3 min" in
caution at 10 min or less, "23 min" and "inside" in text-2, "to approve" / "to sign" for items with
no clock. One sentence for screen readers per row ("RFA9885, hold at FL140, enters in 3 minutes.
Review."). From 600 to 1099 px rows add callsign, volcano and "now FL…"; the 420 px list pane at
1100 px and up keeps them to the action and the time.

**Review** (`#sheet`): the top bar "‹ Decide · 1 of 20 advisories · Skip for now ›" (the position in the
act-by order of the advisories, which is all the review walks; "Skip for now" opens the next item, decides nothing and is not audited); "RFA1456 ·
MAS723 · v1"; the action as the sheet's h1 (`#s-title`, 24 600); the entry line once ("Entry due
now (est.)", caution at 10 min or less). CHECK BEFORE YOU APPROVE (`#why`): Level ("now FL310 →
hold at FL226"), Ash (band · volcano), Area (8 px swatches with words, ›), Sources ("7 · 5 official ·
newest 3 min", ›), Fuel, Route (with a 140 px sketch with no labels, hidden from screen readers:
the row says the route, ›). TEXT TO APPROVE: one box, the header code wrote folded to one line
("Header written by code · 15 lines ▸", dim, not editable; full in Record too), a hairline, the
body that is approved. The mark line. "Record · ids, policy, history, audit ›". Pages inside the
sheet (the bar stays): Sources (OFFICIAL / CONTEXT ONLY rows that open in place to the full id,
times, hash and link), Area (the words, the mode sentence, "TEPHRA's area is never smaller than the
official area."), Route, Record (ids, the proxy and hex, drafted-at and minutes to entry, the action
code, the fuel formula and cost note, drafted by and the validator notes, the policy, the full
header, History from `/api/audit`, "Ask TEPHRA about RFA1456 ›"). "Drafted from recorded feeds" left
the review: REPLAY is said by the frame strip (and the header line inside the approved text); a
replay draft opened while live feeds play carries "From a replay" in the review and on the lead
card (7.1).

**One decision bar**: the primary (Approve, green, advisories only; hold or tap-and-confirm), the
hint "Hold to approve, or tap to confirm." (offline: "Reconnect to approve"), then "Edit text" and
"Reject…" at equal width, both neutral outlines. Editing: "Stop editing" and "Reject…"; "Unchanged
from the draft…" shows only after an approve attempt. The confirm step: "Approve: hold RFA1456 at
FL226?", "Entry due now, est. 1008Z · version 1", the queued sentence. "Nothing is sent…" is said
twice per approval: the confirm and the stamp. On a phone the bar is pinned only when the first two
lines of the text to approve are above it when the review opens; otherwise (a short screen, a
reroute's sketch) it sits after the content (`.actions--after`), so the words always come before the
button. A reject is neutral everywhere, never red: the button, the stamp, the status in Decided
since and the conflict outcome. Reject reasons end with "Other…" (goes to the box); the counter is
in sans.

**Messages** (`openMessage`): a full-screen sheet on a phone; the review closes first (sheets never
stack; at 1100 px and up the review pane stays). The same decision bar, filled neutral (green stays
advisory-only): "Approve crew briefing (EN) for RFA1225", hold or tap for the confirm ("…? · Queued
under AK on TEPHRA's own outbound queue · nothing is sent to a passenger, crew member or
aircraft." · Approve now · Cancel), then "Edit text" and "Reject…". From the receipt: 3 taps.
The `sources` field on drafted messages (redesign spec, Phase 4) is not built: it changes the
approved template in three languages and the model's slots, so it waits for its own audited
change. Until then the body keeps "Source: …" and is shown exactly as it will be approved.

**Receipt line** (`#receipt`, D3): after the 1200 ms stamp the sheet opens the next item with
"✓ Approved: hold RFA1456 at FL226 · 1003Z · AK" pinned above it, "Draft crew briefing ›" (drafts
and opens the briefing) and "Audit ▸" (opens in place to the entry `/api/audit` lists for this
decision, or "Audit line not listed yet. It appears in Record when the server lists it.";
nothing is put in its place). Said once: "Approved: …. Next: RFA9885." No toast, no Undo.

**Header**: `#net-banner` moved out of the sticky header to the top of the view, so the header
never grows offline (94 px at 390 in every state, the frame strip included).

**Ask**: the conversation reads down, oldest first; the composer is pinned at the bottom above the
tab bar (sticky; the old static rule is gone); the newest answer scrolls into view above it and is
announced once, in full ("Answer: …", plus "Answered by TEPHRA Assistant." when a model answered);
the suggestions show only before the first question.

### 10.18 The night desk, 13 Oct 2026: one look with the board, and the map of the flight

The Desk takes the flow board's look, so the Wall, the board and the Desk read as one product:
- **Page.** The board's night: a faint dot matrix (`#9db4cc` at 9 %, 12 px) fading down the page,
  under a glass header.
- **Cards.** Every card (the review, the lead card, the airport plan, Paperwork's "Ready for you",
  panels, the sign-in) is the board's glass panel: a soft surface gradient, a 7 % hairline, an
  18 px radius and a deep shadow. Empty states stay dashed.
- **Tabs.** Decide · Airports · Paperwork. From 1100 px one pill under the header (the board's
  "Real now / Example" control); the chosen tab is filled. A phone keeps the bottom bar.
- **Ask's own colour.** Ask is indigo (`--c-ask` `#8b9bff` to `--c-ask-2` `#5ec8ff`), a hue
  nothing else on TEPHRA uses: the header button's gradient ring, the drawer's glow, top edge and
  border, its suggestions and its send button. Text on it passes AA (tokens.css).
- **Explainers live on the guide.** "How this works" folds left Details (13 Oct 2026): their words
  are the guide's "How each part works" (`wall/explain.js`); Details keeps the data folds.
- **Ask from anywhere.** Ask is not a tab: the header's Ask button opens a drawer at the right edge
  over whatever is open (a full-width sheet on a phone), the question box focused; Escape, its ✕
  or the button again closes it. "Ask about this flight" opens it with the review still open.
- **One panel** (1280 px and up): the map fills the page and one glass panel on the right holds
  Decide; a review (or Plan by hand) takes the panel's place with "‹ Decide", as on a phone (the
  phone's flow and Back run there; `isWide()` is 1100 to 1279 px only, where the two panes stay).
  The page does not scroll; the panel does.
- **The map of the flight** (`desk/map.js`, 1280 px and up). The
  night basemap with the ash (the official area filled, TEPHRA's wider area dashed), the active
  volcanoes, every aircraft (a flight with an open draft bright, others dim), every path into the
  ash (faint), and for the flight under review its amber ring, its card (flight, level, inside or
  minutes to entry), its path and the reroute its draft proposes (`--c-reroute`; never a reroute
  the draft does not propose), framed together with its volcano. Selecting
  a bright plane opens its review; any other plane shows its path and a card that says it has no
  open draft. The airports the airport plan closes are a white ⊘ (`--c-closed`, as on the Wall) with their closure
  radius (section 5). A draft whose aircraft the newest picture no longer holds says
  so on the map ("RFA1738: no current position in the newest picture"); nothing is guessed. Zoom
  and "Every flight in or heading in" are the shared control column; a key pill names the four
  marks. The aircraft and cones follow the stream; the paths are read again every minute.
  MapLibre loads only when the map shows (a phone never downloads it). Read-only: it changes no
  draft.
- **Less to read.** The sign-in says what the Desk is in two short sentences; the RFA line is in the
  frame strip and About; the first-use card is gone from both pages (UI-AI-QUIET 8.4).

## 11. Copy deck

Sentence case in prose; caps only for codes, aviation words and small caps labels. Hyphens in
the disclaimer exactly as `state.disclaimer` gives them.

### 11.1 Honesty labels (exact)

| Where | Text |
|---|---|
| Disclaimer | `Decision support only - fictional airline - not for operational use` (`state.disclaimer`): in documents, outbound text and link previews, never page chrome (7.36). On screen the fact is said once: the welcome dialog's facts line, About › Safety limits and the sign-up tick's (i) |
| REPLAY label (both pages, whole session, once: the frame strip, 7.1) | "Replay · recorded feeds from 23 Sep 2026 · not live" (`replayWords()`); `state.replay.banner` ("REPLAY: recorded real feeds from 23 Sep 2026") is its tooltip and the About line |
| Model label (both pages, always) | The AI's one state on both pages (`aiStateOf()`, docs/UI-AI-QUIET.md 5.2): "AI on", "AI paused · 0700Z", "AI on · 1 problem", "AI off" (the Wall's AI chip, the Desk's AI chip, AI at work); the model ids are in the Desk's AI today sheet, AI at work and Details › AI helpers |
| AI marking | "AI-drafted" (advisory body), "AI-written · {model}" (plume reading, satellite limits); with no model the Wall says "Written by code (AI off)" |
| Every satellite layer | "CONTEXT ONLY · {layer} {time} · not ash detection · Imagery: NASA GIBS · Himawari-9 data: JMA via NOAA" |
| SO2 layer | "CONTEXT ONLY · SO2 (TROPOMI, daily) {date} · SO2 is not ash, gases not modelled · Imagery: NASA GIBS · Contains modified Copernicus Sentinel data 2026" |
| BTD overlay | "Split-window BTD (computed by TEPHRA) · an indicator, not ash detection" |
| Airline | "Ring of Fire Air (RFA) is a fictional airline. RFA flight numbers are proxies for real aircraft." |
| Outbound | "Approved text goes only to TEPHRA's own outbound queue. Nothing is sent to an aircraft or any real system." |
| TEPHRA's area | On the Wall "TEPHRA's estimate" · "an estimate, not a forecast" · "never smaller than official" |
| SHADOW (hosted airline, page level) | The header chip "SHADOW" (dashed, half disc) and its (i) "TEPHRA runs on your real flights; every draft says Shadow · not for use. Nothing is sent to aircraft."; page titles `SHADOW · <Section> · RFB · TEPHRA` (`docs/HOSTED.md`) |
| Shadow · not for use (data level) | The `.stamp--shadow` on every draft card with `shadow`; the code-written `SHADOW - NOT FOR USE` line in advisory headers, outbound text, message and document headers (outside editable bodies); a `SHADOW` tag on record entries |
| LIVE + who and when | The chip's (i) "Switched to LIVE on … by …. Nothing is sent to aircraft."; the Switch to LIVE dialog ("TEPHRA still sends nothing to an aircraft or to any system." and its (i) "An approved advisory goes to your outbound list; a person passes it on."); the workspace card "Live since …, switched by …"; `OWN_DISCLAIMER` stays where it is |
| Not updating / Picture from | The state chip "LIVE · not updating since hh:mmZ" in red and the dimmed map with "Picture from hh:mmZ" when a running airline's last tick is over 150 s old |
| ILLUSTRATIVE (hosted policy) | Settings › Policy chip; the map status line "Policy vN · ILLUSTRATIVE"; inside each draft's record; the Switch to LIVE dialog's caution; an acceptance reads "recorded by the airline, TEPHRA does not check it" |
| AI unavailable (hosted) | Said once per screen, as on the demo: the airline map's and Desk's AI status ("AI off", "AI paused", "AI unavailable" and its (i)) and Settings › Assistant's state line ("AI unavailable · <reason>." and its (i)); each model step of an airline with no model, no key or an unreadable key says it did not run ("Plume reader did not run"), its raw `AI UNAVAILABLE: <reason>` one tap in (Technical detail, the record) |
| Paused (airline or site allowance) | A red line on every airline page ("Paused: <name>'s share of the site's free daily database allowance is used. Resumes 00:00 Pacific (07:00 UTC)."); the workspace card; the console's free-tier tile and notes |
| Satellite frames paused | The frames feed note when the month's airline uploads are used |
| Not built (hosted) | `docs/HOSTED.md` §6, each said where it applies; the workspace line "TEPHRA runs at most 3 airlines at once on this site." until the airline has its space, then the places line beside Start ("1 of 3 airline places in use") (the setup kit is dropped) |
| DRY RUN · NOTHING TAKEN IN | The dry-run card (`dryrun.js`, workspace and airline Feeds); "Checked, not taken in" on Feeds in setup |
| Private | The airline space's footer "Private to <name> and TEPHRA staff" |
| Unpaid-tier data use | Settings › Assistant: "Google may use what TEPHRA sends with a free-tier key." |
| Emails are not checked | The invite page ("Anyone with this link can join as <role> until <time>. Emails are not checked."); the People invite box |
| Verified ≠ approval | The workspace verification card: "It does not approve your policy or your use of TEPHRA." |
| TEPHRA staff only | The console's footer: "TEPHRA staff only" and its (i) "Each action on an airline goes into that airline's record." |

### 11.2 Mode words

| Mode | Short | Sentence |
|---|---|---|
| LIVE | "Live" (mode pill), "Live · 9 h back, 3 h ahead" (time bar) | "Live feeds" |
| REPLAY | "Replay clock · 5 Sep · UTC" (the mode pill is hidden: the strip says it) | the frame strip, once: "Replay · recorded feeds from 05 Sep 2026 · not live"; no "Recorded" on the story, no "recorded" tags; "From a replay" only on a record from the other mode |
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
polled yet". A replay feed shown while live feeds play: add the tag "From a replay" (7.1).

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
again", "Reload the lists", "Re-plan now", "Approve plan…", "Write the handover", "Draft SRA",
"Draft VAR". Tabs: "Decide", "Ask", "Airports", "Paperwork". Labels: "Version 1" (not "v1"),
"{ }" with the tooltip and screen-reader words "Written by a code template" (not "Template · NO
MODEL", 7.35), "AI calls today: 0 of 450",
"Pilot ash report (VAR)", "Ready for you", "from: flights heading in" (not "T01 exposed_flights"),
"TEPHRA's area" (not "hazard cone"). Per-item marks with the stub are the "{ }" code mark
("Written by a code template", or "Ordered / Counted / Picked / Read by code").

### 11.8 Desk messages

| Situation | Text |
|---|---|
| PIN empty | "Required" |
| Bad PIN (401 `bad_pin`) | "Wrong PIN" |
| Too many attempts (429) | "Too many attempts. Wait 10 minutes and try again." |
| Desk disabled (503) | "The Desk is switched off on this server (no Desk PIN is set)." |
| Name empty | "Required" |
| Name invalid (422) | "2–32 letters or digits" |
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
| Empty Decide list | "No advisories to review." / "A draft appears here when a flight's projected track enters TEPHRA's estimated ash area." (while the AI is paused: "The AI is paused (back in 6 h 30 min), so no new drafts are written until it is back.") |
| Plan by hand | "Plan by hand · 23 flights" / "No AI plan for these flights: AI paused until 0700Z real time. Nothing was substituted." |
| One flight marked handled | "RFA1701 marked handled. Recorded under AK." |
| Several marked handled | "5 flights marked handled. Each is recorded under AK." / "3 flights saved. Not saved: RFA1890 (it no longer exists)." |
| Code closed a failure | "RFA1701 no longer needs handling by hand: an advisory draft now waits for it." / "RFA1701 left the list: it is no longer in or heading into the ash." |
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
| Area label (map, Details, Desk) | "Crew report caution area (operator policy A, not a VAA or SIGMET)" (`CREW_AREA_LABEL`, whose semicolon the pages show as a comma: no page text carries a semicolon) |
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
(Details stays closed until opened on purpose). Every replay shot shows the frame strip's REPLAY
part; the disclaimer is in every frame. The opening uses the Krakatau window of UI-REDESIGN R2.2
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
  (tests and the spoken reply rely on it); on screen it is said once above the conversation
  ("Answers are code counts: the question is not read.", 7.35), not on each answer.
- Crew reports (5.7, 7.20, 10.15): the ivory `--c-crew` is not yet in the palette script's
  tables (3.3); the research's "stale" and "expired, needs review" steps are one EXPIRED state
  (listed for 24 h, not drawn); a report withdrawn or expired leaves the drafts it flagged as they
  are (no recheck card); the Wall's flights list shows the crew line only for flights heading into
  TEPHRA's area (a flagged flight outside it is reached from the map or Details › Crew reports).
- The decision receipt is one line pinned above the next review (`#receipt` in `#sheet-receipts`,
  10.17); it stays until the next decision or until the review is closed.

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
  (AI off): …"). Where a line sits beside its own code mark (the Coordinator brief on the Desk and
  in Details, the Why chain, the What happened log, "Why this plan"), `templateText()` drops the
  "(code only)" words and the "{ }" mark says it once (7.35). The raw line stays under Technical
  detail. Desk review › Why: TEPHRA area "Official
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
- Phone Details sheet: the backdrop is transparent, so the frame strip and header above the
  sheet stay at full contrast. Details index statuses wrap in their own column.
