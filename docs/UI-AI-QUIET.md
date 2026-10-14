# AI, quietly: one home for AI health, consequences at the place

Status: design decision, 2026-10-13, branch `ai-quiet` from `main` eefe8a3. Built 2026-10-13 (section 8).
Section 8.6 ("Say the cause once", branch `quiet-quota`) amends the paused words of 1.1, 5 and 8.4.
It amends `docs/UI-REDESIGN.md` G2, R3.1, R5.6 and R5.7, and `docs/UI-DETAILS-PANELS.md` (the AI
helpers, Decisions, Airport closures and Trace sections). Where this document and those disagree,
this one wins, and the implementation commit amends them.

The user's words: "there is too much mention of AI and its failure statuses everywhere, can we
make it better".

Evidence: the 104-entry inventory of AI mentions (Wall story, map, Details, Desk) built from the
live JSON with the shots in `<scratch>/quiet-shots/` (`inv/wall-1440.png`,
`inv/wall-390.png`, `dinv/*.png`, `mapinv-*.png`, `desk-*.png`; method in
`quiet-shots/desk-inv.mjs`). The state to design against: today's free Gemini quota is used up.
`gemini-3.5-flash-lite` (every step except the Plume Reader and speech) is closed until 0700Z, and
the Duty Officer was refused on every tick from 1046Z to 1102Z. That **one** cause is reported as
"28 failed" in the top bar, a red story banner, "+ 1 more problem", a red "Needs a look" row, 4 of
the first 6 trace rows, and 28 identical 300 px cards on the Desk. The recovery planner's older
TimeoutError is a second, separate cause.

---

## 1. The principle

> **AI is a tool, not the story. TEPHRA shows AI health in one home, and everywhere else says
> only what the dispatcher must now do differently, at the place where it applies, once, in
> amber or neutral and never in red.**

Six rules follow from it. Every decision in section 3 cites one.

| Rule | What it means |
|---|---|
| **Q1 One home** | Wall: the top-bar AI chip, which opens Details › AI helpers. Desk: the header AI chip, which opens the AI sheet. Model ids, budgets, lanes, pacing, per-step counts, raw reasons and failure histories live **only** there, plus each place's own Technical detail and the audit log. |
| **Q2 One state, not N failures** | The AI is in exactly one state: **on**, **paused** (quota used up, with the reset time), **trouble** (n causes) or **off** (stub). Failures are counted **by cause** (helper + reason class), never by step or tick. 28 refusals with one reason are "1 cause". |
| **Q3 Consequence at the place** | When something the dispatcher acts on lacks its AI part (an advisory, an airport plan, an area estimate, a notice, a document, a message, an answer), **that place** says what is missing and what to do, with a short marker: `AI paused`, `AI waiting` or `AI unavailable`. A "Why ›" link goes to the cause in the AI home. The consequence is said once per place, not once per tick, and never in a separate banner. |
| **Q4 Red is for the picture** | The red/serious tone, `role=alert` and the story's problem banner (`#fail-line`) are kept for things that threaten the picture: feeds, the database, the live connection, the map, page load, and the hazard itself. AI uses **caution** (a dispatcher must do something by hand) or **neutral** (information). AI text never sits above the story's lead. |
| **Q5 Attribution is a mark, not prose** | One small mark set used on both Wall and Desk: `AI-written`, `AI-read`, `AI-chosen`, and `Code (AI off)` for the stub. A mark appears only where a model actually produced the content (a model id is present and the outcome is ACCEPTED or REPAIRED). The model id goes in the mark's `title` and `aria-label` and in the AI home or audit log, never in the visible main view. |
| **Q6 Honesty is fixed** | Everything in section 2 stays exactly as true as today, and in five places more true (section 4). |

### 1.1 Canonical words (one vocabulary, Wall and Desk)

| Situation | Short marker (chips, tags, rows) | Sentence form |
|---|---|---|
| Quota used up, live budget shows the model closed | `AI paused · 0700Z` | "AI paused until 0700Z (today's free AI quota is used up)." |
| Quota used up, time unknown (recorded run and no live budget closure) | `AI paused` | "AI paused (today's free AI quota was used up)." |
| A step is queued for a later budget slot | `AI waiting` | "Waiting for AI: next slot 0700Z." |
| A step failed for another reason (timeout, failed checks, error) | `AI unavailable` | "AI unavailable ({why}): nothing was put in its place." `{why}` is one of: *timed out*, *the answer failed the code's checks*, *the AI stopped with an error*, *the AI could not answer*. |
| Stub backend | `AI off` | "AI off: code only." |
| Content a model wrote / read / chose | `AI-written` / `AI-read` / `AI-chosen` | no sentence: the mark only |

These replace the mixed words found in the inventory ("used up", "closed", "spent", "OUT",
"could not run", "did not dispatch", "Failed", "28 failed"). `AI paused` is the plain-words form of
rule 9's `AI UNAVAILABLE: budget_exhausted`; the raw string stays one tap in under Technical detail
(rule 9 is about what the step reports, and it still reports exactly that).

The reset time comes **only** from the current `/api/budget` (`resets_at`, with the model marked
`closed: true` now). It is a statement about now, on the real UTC clock, so it is shown in REPLAY
too. It is never derived from a recorded failure's replay-clock time. A recorded run whose model
is open again now says `AI paused` with no time in its history row.

### 1.2 One derived state

A single pure function per page derives the state, so that every place uses the same words:

- Wall: `aiState(D, store)` in `tephra/web/wall/x-parts.js`, replacing the per-place use of
  `failureCount`, `aiStopClause` and `reopensAt`.
- Desk: `aiState(budget, failures, llm)` in `tephra/web/desk/ui.js`, with the same rules.

It returns `{ kind: "on"|"paused"|"trouble"|"off", until: "0700Z"|null, causes: [{ key, helper,
reasonClass, steps, first, last, raw, consequence, link }], waiting: [{ job, slot }] }`.

- `paused` when the lite model (the default for every helper except the Plume Reader and speech)
  is closed in the live budget, or when the newest Duty Officer run's reason is `budget_exhausted`
  or a 429 / `RESOURCE_EXHAUSTED` quota error.
- `trouble` when there is at least one non-budget cause in the newest trace window **or** the
  newest airport plan is `AI_UNAVAILABLE` (so an older recovery timeout is still counted; it is
  outside the newest 100 trace steps today).
- `causes` are grouped by `stage + reasonClass`, never by the rendered sentence. That merges trace
  rows 1 and 4, which split today only because "1 job" and "N jobs" read differently.
- In `paused`, a budget cause is part of the state and is not counted again as trouble. With both,
  the chip reads `AI paused · 0700Z`, and the AI home lists the other cause under "Also".

---

## 2. Honesty that must survive (checked in section 6)

1. **Rule 9 at the place.** Every step that did not run still says so where its output would have
   been: `AI unavailable` or `AI paused` / `AI waiting`, with "nothing was put in its place" in the
   sentence form or the Why. Nothing is substituted. No canned text, no template, no stand-in plan.
2. **Pinned strings** (`tests/test_ui_inventory.py` `HONESTY`) stay visible:
   "Decision support only - fictional airline - not for operational use", "CONTEXT ONLY",
   "HYPOTHESIS", "never smaller", "Approved text goes only to TEPHRA's own outbound queue", "RFA",
   "fictional". "never smaller" is visible on the default Wall in **two** places after this change:
   the map key ("never smaller than official") and the trust line (section 3, W17).
3. **"Never shrink the official area"** stays in the AI home header, the AI chip's tooltip and the
   map key; the trust line keeps the same meaning in "never smaller" words.
4. **REPLAY** labels (banner, mode badge, clock sub, eyebrow "Recorded", the Desk's `REPLAY`
   chips) are not touched by this spec. (Since 13 Oct 2026, UI-DESIGN 7.1: REPLAY is said once, in
   the frame strip; the clock sub stays, the others went.)
5. **Feed, database, connection, map and load failures** keep the red banner, `role=alert` on
   `#lost-banner`, the red Data chip on ERROR, and their order (worst first).
6. **Nothing is deleted.** Every piece of information in the inventory is kept: it is moved, merged
   or put one tap in. The decision table names the new location for each.
7. **Every pinned id and class stays** (`ai-chip`, `model-chip`, `trust`, `fail-line`, `fail-list`,
   `lost-banner`, `phone-bar`, Desk `model-chip`, `budget-chip`, `fail-section`, `duty-section`,
   `q-breakdown`, `announcer`, …). Nodes may be re-parented, as R11 already allows.

---

## 3. Decision table (every inventory entry)

Legend: **Keep** · **Merge into X** · **Move to Y** · **Reword to "…"** · **Quiet** (tone or size
only). `{n}`, `{until}`, `{why}` are filled by code. Inventory entries are numbered in the order
received.

### 3.1 Wall: top bar and story (`index.html`, `wall/panels.js`, `wall/story.js`)

| # | Mention (today) | Decision | Rule |
|---|---|---|---|
| W1 | AI chip visible: "AI on" + red badge "28 failed" | **Reword + Quiet.** The chip shows the one state, with no count badge: `AI on` · `AI paused · 0700Z` · `AI on · 1 problem` · `AI off`. Tone: neutral for on/off, caution dot (`--c-caution`) for paused/trouble. Never red. `.ai-chip__fail` is re-used as the state suffix span (`· 0700Z`, `· 1 problem`) and loses its red style. With today's data: **`AI paused · 0700Z`**. | Q1 Q2 Q4 |
| W2 | Chip tooltip with model ids, "never shrink", "28 AI steps failed…" | **Reword** to: "AI paused until 0700Z: today's free AI quota is used up. Queued work runs then. AI can widen TEPHRA's estimate, never shrink the official area. Open AI helpers for models and today's calls." The model ids move to the AI home (they are already there). "nothing was put in their place" moves into the AI home lead (W64). On: "AI on. It can widen TEPHRA's estimate, never shrink the official area. AI-written parts are marked." | Q1 Q5 |
| W3 | Chip aria-label with both model ids and the count | **Reword** to "AI paused until 0700Z. Opens Details, AI helpers." / "AI on. Opens Details, AI helpers." / "AI on, 1 problem. Opens …" / "AI off, code only. Opens …". No model ids. | Q1 Q5 |
| W4 | Stub variant "AI off" + tooltip | **Keep** the word `AI off`. Tooltip: "AI off: no model is connected. Code does every step; code templates write the text." (unchanged). | Q2 |
| W5 | Static chip "AI: –" before the first data | **Reword** to "AI ·" with aria "AI helpers, connecting". 12 px min; same width as the final chip so the bar does not jump. | Q1 |
| W6 | Phone bar "AI on 28 failed" | **Merge into** the W1 state: `AI paused` (the time is dropped below 420 px to fit, and stays in the aria-label). The freed width lets the Data chip show "5 off" again at 390 px. | Q2 Q4 |
| W7 | Data chip "Data: 6 working · 5 off" | **Keep** unchanged (not AI). Its red ERROR tone stays the loudest chip in the bar. | §2.5 |
| W8 | Banner item 1 "Airport plan: the recovery planner timed out, so a dispatcher must plan by hand." | **Move to** the closure sub-line (W15). Removed from `storyFailures`. The raw reason moves to the sub-line link's `title` and to Details › Airport closures › Technical detail (already there). | Q3 Q4 |
| W9 | Banner item 2 "Duty Officer could not run: today's AI calls are used up." | **Move to** the advisory line (W14) as its consequence. Removed from `storyFailures`. The cause moves to the AI home (W64, W67, W68). | Q3 Q4 |
| W10 | Banner item 3 "28 AI steps failed" behind "+ 1 more problem ›" | **Merge into** the AI home ("What went wrong · 1 cause · 28 steps"). Removed from `storyFailures`; the "+ n more problems" link now counts only non-AI problems. | Q2 Q4 |
| W11 | Satellite banner variant "Satellite reader could not run: …" | **Move to** Details › Satellite picture (row + index row in neutral tone). Never in the banner: the satellite picture is supporting only. | Q3 Q4 |
| W12 | Banner footprint: 92 px red box, fit level 8 of 8, "+ 4 more" fold | **Result of W8-W11:** with no feed/DB/connection failure the banner is **hidden** (`#fail-line` stays in the DOM). Target: the story column fits at level 6 or lower at 1440x900 and the other-volcano rows are not folded (checked in §6). | Q4 |
| W13 | Eyebrow "… Red alert · Recorded · as of 1101Z" | **Keep** (REPLAY label). | §2.4 |
| W14 | Advisory line "Their advisories are not drafted yet." | **Reword by state** (caution tone, with a "Why ›" link to Details › AI helpers › What went wrong): paused: **"No advisory drafts: AI paused until 0700Z. Plan the {n} flights by hand on the Desk."** · AI unavailable: "No advisory drafts: AI unavailable ({why}). Plan the {n} flights by hand on the Desk." · queued: "Advisories not drafted yet: waiting for AI, next slot {until}." · AI fine and running: "Their advisories are not drafted yet." (unchanged). `{n}` is the count the story already uses for "Show the {n} flights". DB variant "Advisory count unknown (database error)." **Keep**. | Q3 |
| W15 | Closure fact sub-line "3 across all volcanoes · airport plan as of 1031Z" | **Reword** when the newest plan is `AI_UNAVAILABLE`: "3 across all volcanoes · **No airport plan (AI unavailable): plan the network by hand ›**" (caution; link to Details › Airport closures; `title` = the raw reason). Solver-only failures (code, not AI) use the same slot: "No airport plan (no plan fits the closures): plan the network by hand ›". "Re-planning the day's flights… · started HHMMZ" **Keep**. | Q3 |
| W16 | Disagreement sub-line "TEPHRA's estimate has not been widened (AI off)." | **Keep**, and **extend** to the live outcomes, which have no wording today: PENDING "… has not been widened yet (AI waiting)." · MODEL_FAILED "… has not been widened (AI unavailable)." | Q3 §4 |
| W17 | Trust line "AI is on. It can widen …, never shrink …" + 2 model-id chips | **Reword** to one mode-independent line, no AI word and no chips: **"TEPHRA's estimate is never smaller than the official area, which stays binding."** (icon `i-code`). The AI on/off statement moves to the chip (W1); the model ids are already in the AI home; the AI form of the sentence stays in the chip tooltip and the AI home header. This removes the on-screen contradiction "AI is on" vs "calls used up". `#trust` keeps its id. Stub "AI is off. Code built this summary…" **Merge into** the chip's `AI off` tooltip. | Q1 Q5 §2.2 |
| W18 | Actions "Open the Desk · Show the 28 flights" | **Reword** the CTA: when flights have no draft because AI did not run, the primary "Decide on the Desk →" is used (the same label as with drafts), because the Desk holds hand-plan work. No AI word added. | Q3 |
| W19 | Map key | **Keep** ("never smaller than official" is a pinned honesty home). | §2.2 |
| W20 | All volcanoes "… 0 advisories waiting · + 4 more" | **Reword** the count when AI did not run: "0 advisories waiting (AI paused)". The "+ 4 more" fold should disappear as a result of W12. | Q3 |
| W21 | Details button sub-line "Sources, timeline, how TEPHRA decided, AI, data feeds" | **Keep** (navigation; the AI home is behind it). | Q1 |
| W22 | Honesty footer | **Keep** unchanged (pinned). | §2.2 |
| W23 | Replay banner and clock | **Keep** unchanged. | §2.4 |

### 3.2 Wall: map and one tap from the map (`wall/derive.js`, `wall/map.js`, `wall/ext-map.js`, `wall/panels.js`)

| # | Mention (today) | Decision | Rule |
|---|---|---|---|
| M24 | Map tag "TEPHRA's estimate · same as official" (shown only on stub, from the global backend) | **Reword and fix the trigger.** Show the tag when `cone.mode === "OFFICIAL"` and the situation's `assessment.outcome` is not model-checked: PENDING "TEPHRA's estimate · same as official · AI waiting" · MODEL_FAILED "… · AI unavailable" · STUB "… · AI off". ACCEPTED/REPAIRED and OFFICIAL_ONLY show no tag (as today). The trigger is the per-situation outcome, not `llm.backend`. This is the one place that gets **more** honest. | Q3 §4 |
| M25 | Tag "… same as official (AI off)" | **Merge into** M24 (same words, `· AI off`). | Q3 |
| M26 | Satellite box label "AI box 1: possible ash" | **Reword** to "Box 1: possible ash". Authorship moves to the map key row and the box tooltip ("Marked by the satellite reader (AI-read) · supporting only"). "possible" and "supporting only" stay. | Q5 |
| M27 | Area card (PENDING) "Same as the official area: the model found nothing to add." | **Reword (honesty defect):** "Same as the official area: **the AI plume read is waiting** (next slot 0700Z)." OFFICIAL_ONLY: "Same as the official area: no AI read was needed." The "the model found nothing to add" line is used only for ACCEPTED/REPAIRED. | Q3 §4 |
| M28 | Area card MODEL_FAILED "…: AI unavailable, nothing assessed beyond the official reports." | **Keep** (one line, at the place). | §2.1 |
| M29 | Area card stub "Same as the official area (AI off, nothing added)." | **Keep**. | §2.1 |
| M30 | Map status pills | **Keep** (no AI). | — |
| M31 | Satellite caption "CONTEXT ONLY · … not ash detection" | **Keep** (pinned). | §2.2 |
| M32 | Time bar | **Keep** (no AI; REPLAY stays). | — |
| M33 | Time bar History lanes | **Keep**. | — |
| M34 | Details › Timeline history | **Keep**. | — |
| M35 | Map key / Layers "Satellite boxes · marked on the picture · supporting only" | **Keep**, and add the `AI-read` mark to that row (it now carries the authorship removed from M26). | Q5 |
| M36 | Phone time pill | **Keep**. The phone map now starts higher because W6/W8-W12/W17 remove about 150 px of AI status above it. | — |

### 3.3 Wall: Details (`wall/details.js`, `wall/panels.js`, `wall/ext.js`, `wall/duty.js`, `wall/x-parts.js`)

| # | Mention (today) | Decision | Rule |
|---|---|---|---|
| D37 | Details button sub-line (same as W21) | **Keep**. | — |
| D38 | Needs a look › "Airport closures · no plan: the planner timed out" | **Reword** to the job: "Airport closures · **no plan: plan the network by hand**" (caution). The cause stays in the section. Stays in "Needs a look". | Q3 |
| D39 | Needs a look › "AI helpers · AI on · 28 failed" | **Move out** of "Needs a look". Rule: "Needs a look" holds only rows with a dispatcher action; the AI's state is not one. Its action (flights to plan by hand) is already carried by D38 and the new Decisions row (D56). | Q1 Q2 |
| D40 | Behind the scenes › "AI helpers · AI on · 28 failed" (red dot) | **Reword** to the one state: "AI helpers · **Paused until 0700Z**" (caution dot) · "On" (neutral) · "On · 1 problem" (caution) · "Off · code only" (neutral). Never red. | Q2 Q4 |
| D41 | The ash › "TEPHRA's estimate · same as official" | **Reword** by outcome, with the same suffixes as M24: "same as official · AI waiting". | Q3 |
| D42 | The ash › Satellite "n readings · n AI unavailable" (serious) | **Quiet**: info tone, "n readings · n not read". Never in "Needs a look" (supporting only). | Q4 |
| D43 | Estimate header "the model found nothing to add" (PENDING) | **Reword** as M27 (same function, `estimateOutcome`). | §4 |
| D44 | Read by "Plume read queued for the Duty Officer: official products only until it runs" | **Keep**, and append the slot when known: "… until it runs (next slot 0700Z)." Shown as `AI waiting` with no model chip. | Q3 |
| D45 | "How the model read it [AI-written]" on code text | **Fix the gate (honesty defect):** render it only when the outcome is ACCEPTED or REPAIRED and a model id is present. Otherwise the same rationale and uncertainty text sit under "How TEPHRA built it" with the `Code-written` mark. Nothing is hidden. | Q5 §4 |
| D46 | Estimate failure note "AI unavailable: …; nothing was put in its place." (serious) | **Keep the words; Quiet** to caution, `role=status`. | Q4 |
| D47 | Disagree drift row "… has not widened the area (AI off)." | **Keep**; add the PENDING/MODEL_FAILED forms as W16. | Q3 |
| D48 | Satellite header "A model looks at the newest Himawari picture…" | **Reword** the header to "Newest Himawari picture per active volcano · supporting only". The model sentence stays in the About (already there, word for word). | Q5 |
| D49 | Satellite failure pill/row/marks with model ids | **Quiet**: caution edge instead of serious, pill "{n} not read". Row: "Not read: AI unavailable ({why}). Nothing was put in its place." Marks: `AI-read` / `Code (AI off)`; the model id moves to Technical detail. | Q4 Q5 |
| D50 | Notices About "read by a model…" | **Keep** (method note behind a disclosure). | — |
| D51 | Notice row failure "AI unavailable … Nothing was put in its place." | **Keep at the row; Reword** to the job: "Not read (AI unavailable): read this notice yourself. Nothing from it entered the picture." Mark `AI-read`; the model id goes to its title. | Q3 Q5 |
| D52 | Crew About "… calls no model." | **Keep**. | — |
| D53 | Flights heading in row "… No advisory yet" | **Reword** when the draft is missing because AI did not run: "**No advisory: AI paused · plan by hand**" (caution; a link to the Desk). With AI fine: "No advisory yet" (unchanged). A flight in the Duty Officer's undone list adds a `Must do` chip. | Q3 §4 |
| D54 | This flight "No advisory is drafted for this flight yet." | **Reword**: "No advisory for this flight: AI paused until 0700Z. **Plan it by hand on the Desk ›**" (+ `Must do` when listed). AI fine: unchanged. | Q3 §4 |
| D55 | This flight About "Code projection…" | **Keep**. | — |
| D56 | Decisions header green "Nothing waiting" | **Reword** when hand-plan work exists: caution pill "Nothing to approve", and the line "No drafts: AI paused. **{n} flights to plan by hand on the Desk ›**". **Move** (copy) the Duty Officer's "Passed to the Desk" list (D69) here as the sub-list "To plan by hand", with must-do items first. Index row: "0 waiting · {n} to plan by hand". | Q3 |
| D57 | Airport closures header "No plan · … No plan chosen · Plan version 1" | **Merge** "No plan" and "No plan chosen" into one pill "No plan" (caution). | Q2 |
| D58 | Airport closures failure row "Recovery planner timed out · … plan the network by hand · raw reason twice" | **Keep** at the place (caution, not serious). **Add** the queued re-plan, which today exists only in Budget details: "A new plan waits for AI: next slot 0700Z." Technical detail shows the raw reason **once** (`planReasons` de-duplicates it). | Q3 |
| D59 | Footer note and About | **Keep**. | — |
| D60 | "Chosen by <model id>" chip / "Why this plan" marks | **Reword** to the mark `AI-chosen` (model id in title and Technical detail); "Why this plan" `AI-written`. Shown only when the model actually chose a plan. | Q5 |
| D61 | Trace Problems tile "70 · 28 failed · 42 warnings" | **Reword**: "Problems · 42 warnings · AI did not run: 1 cause (28 steps)". The steps are still counted and still listed. | Q2 |
| D62 | Trace rows 1 and 4 (one cause, two red rows) | **Merge** by cause key (`stage + reasonClass`, not text). One caution row: "**Duty Officer did not run: AI paused** (daily quota). 1–18 must-do jobs per run went to the Desk · 28 times · 1046Z–1102Z · See the jobs ›" (link to Decisions › To plan by hand). | Q2 Q3 |
| D63 | Trace rows 2 and 5 "… · done by an AI helper" | **Merge** as D62, and **fix the actor**: an `adk` step with no model call reads "by code (agent worklist)". "by an AI helper" is used only when a model was called. | Q5 §4 |
| D64 | AI helpers header "AI on (green) · 28 failed (red) · … never shrink … · 3 model chips" | **Reword** the pills to the one state "Paused until 0700Z" (caution). **Keep** "Helpers can widen TEPHRA's estimate but never shrink the official area." **Add** the calm lead (section 5.1). **Keep** the model chips here: this is their home. | Q1 Q2 |
| D65 | Tile "AI calls today ⚠ 1 of 450 · Calls refused since 1046Z · …" | **Reword**: value "Closed until 0700Z"; sub "Google closed the free quota after 1 of 450 calls · 2 jobs waiting". "since 1046Z" is labelled "(replay clock)" or dropped. The main-model line stays. | Q2 |
| D66 | Tiles "Steps that failed 28" and "Jobs handed out 0" | **Merge** "Steps that failed" into the What went wrong head ("1 cause · 28 steps"). **Keep** "Jobs handed out". | Q2 |
| D67 | "What went wrong · 1 kind · 28 steps · …" | **Keep** as the cause list (one row per cause), worded with §1.1. Fix "1 jobs" (plural helper). Range: "1–18 must-do jobs per run". The 28 occurrence lines and 28 raw lines fold behind "Show the 28 runs" (one tap, nothing deleted). **Add** the link "See the jobs to plan by hand ›" (today `link` is null). The recovery TimeoutError appears here as a second cause (today it is missing, because it is older than the newest 100 steps). | Q1 Q2 Q3 |
| D68 | Duty Officer row "[Failed] … Model gemini-3.5-flash-lite … The model gave no brief that passed the code's checks." | **Fix the cause (honesty defect):** a new outcome `BUDGET` (caution, "Not run") when `validation_errors` holds `budget_exhausted`: "**Not run: today's free AI quota is used up (until 0700Z).** No brief was made; nothing was made up in its place. Must-do jobs went to the Desk." No "Model" fact (no call was made); Technical detail: "budget_exhausted · would have used gemini-3.5-flash-lite". MODEL_FAILED keeps its words for real check failures. | Q2 §4 |
| D69 | "Passed to the Desk · 3 must-do jobs · Plan RFA2671, RFA3515, RFA3799 …" | **Keep** here (history), **and copy to** Decisions › To plan by hand (D56), Flights (D53) and This flight (D54), where the dispatcher acts. | Q3 |
| D70 | Other helper rows ("Its newest step worked" for a queued step, Recovery "Quiet", SRA "Quiet") | **Reword** helper state from facts, not only the newest 100 steps: Plume Reader "Waiting: plume read queued until 0700Z"; Recovery planner "Not run: timed out at 1031Z" (from the newest plan); SRA drafter "Waiting for AI: next slot 0700Z" (from the budget queue). "Quiet" stays for helpers with nothing recorded. | §4 |
| D71 | Budget details (per-model numbers, waiting jobs, reset note) | **Keep** (the home). **Reword** "449 left of 450" next to "quota spent" as "Closed for today by Google (449 of 450 unused)". Each waiting job **also** appears at its place: the network re-plan in Airport closures (D58), the SRA draft at the Desk's SRA starter (K98). Rename the disclosure "Models and today's calls". | Q1 Q3 |
| D72 | "How this works" | **Keep**. | — |
| D73 | Track record caveats ("no model" four times) | **Reword** to say it once, in the note: "Baseline only: code, no model call. The Gemini Plume Reader has not been scored yet, so no improvement is claimed." Pill "Baseline only" kept. | Q5 |
| D74 | Help list "… the AI helpers and the data feeds." | **Keep**. | — |
| D75 | Data feeds, Height filter, history, sources, layers | **Keep** (no AI). | §2.5 |

### 3.4 Desk (`desk.html`, `desk.js`, `desk/*.js`, `desk.css`)

| # | Mention (today) | Decision | Rule |
|---|---|---|---|
| K76 | Inventory method note (not UI) | **No UI change.** | — |
| K77 | Decide: `#fail-section` 8,428 px at 390 (28 cards × ~300 px); Next decision at y=8,620 | **Merge** the 28 cards into one compact **"Plan by hand"** group (K81, K82), placed **after** the Next decision card. Target: Next decision on the first screen at 390x844, and `#fail-section` ≤ 640 px with 5 rows shown. | Q2 Q3 |
| K78 | Header model chip "AI: on · gemini-3.8-flash + gemini-3.5-flash-lite" | **Merge into** one header AI chip: `#budget-chip` becomes the only visible chip (a button that opens the AI sheet), and `#model-chip` is re-parented inside it as its label span (both ids kept). Words: `AI paused · 0700Z` / `AI on` / `AI on · 1 problem` / `AI off`. Model ids move to the sheet. | Q1 Q2 |
| K79 | Budget chip "AI 1/450 OUT 2 WAITING" (red; header 467 px wide at 390) | **Merge into** K78. Caution tone, never red. aria: "AI paused until 0700Z: today's free AI quota is used up. 2 jobs wait. Opens AI today." The per-model numbers move into the sheet (they are there already). Fixes the phone header overflow: `scrollWidth <= 390`. | Q1 Q4 |
| K80 | Budget sheet | **Keep** as the Desk's AI home, retitled "AI today". **Add** the calm lead (§5.1) at the top. The model ids, lanes, pacing and waiting jobs stay. **Keep** "When a step runs out, it says AI unavailable and nothing is substituted." | Q1 |
| K81 | Section head "Problems to acknowledge 28 / The AI could not plan, draft or dispatch these flights…" | **Reword** to the job: "**Plan by hand · 28 flights**" / "No AI plan for these flights: AI paused until 0700Z. Nothing was substituted. Decide each flight, then mark it handled." Caution tone. One "Why ›" opens the AI sheet. Each different cause gets its own group with its own head. | Q2 Q3 |
| K82 | Each failure card (cause said 3 times: headline, raw reason, `AI tried · <model>` chip) | **Merge**: the cause is said once in the group head. Each row is about 56 px: "RFA8824 · AXM386 · **Inside the ash now** · Anak Krakatau · left 1102Z · [Must do] · Mark handled…". Rows are sorted by entry state (inside now first), with must-do first inside each state. The first 5 are shown, then "Show all 28 flights" (one tap). The raw reason and model go to one group-level Technical detail. The `AI tried` chip is removed from rows (its title "Checked by code before it is shown" was wrong for a failure). | Q2 Q5 |
| K83 | Handle-by-hand sheet "… DUTY OFFICER AI UNAVAILABLE: budget_exhausted" | **Reword** the sub to "No AI plan for this flight (AI paused: daily quota)." The raw string moves to Technical detail in the sheet. Chips and audit note **Keep**. | Q3 |
| K84 | SR announcement per failure (28 times) | **Merge**: one announcement per group change: "28 flights to plan by hand: AI paused." Then only count changes: "1 more flight to plan by hand." `aria-live=polite`. | Q2 a11y |
| K85 | Next decision breakdown "0 advisories · 28 problems to acknowledge"; badge 28; title "(29)" | **Reword** the breakdown: "0 advisories · 28 flights to plan by hand". Badge and title counts **Keep** (they are work). | Q3 |
| K86 | Next decision writer line "Drafted by AI (gemini-3.5-flash-lite). Check the sources first." | **Reword** to the mark + instruction: `AI-written` "Check the sources first." The model id goes to the mark's title and to Why this advisory › Drafted by. Stub: `Code (AI off)` "Check the sources first." | Q5 |
| K87 | List rows; mode chip tooltip; dead `modelChip()` | **Keep** rows and tooltip. **Delete** the dead export `modelChip` (queue.js:70-74): it has no caller and shows nothing. | Q5 |
| K88 | Review writer note | **Keep** one line beside the text the dispatcher approves, worded as K86. The edit variants ("Edited by a dispatcher from AI-drafted text.") **Keep**. | Q5 |
| K89 | Why this advisory › Drafted by "gemini-3.5-flash-lite · AI-drafted · Model-written body…" | **Keep** (it is a disclosure and the audit-relevant home of the model id for this advisory). Mark word unified to `AI-written`. The NEEDS_HUMAN caution (line 481) **Keep**. | Q5 |
| K90 | Review header "NO MODEL"; audit labels | **Keep** (server record and history). | §2 |
| K91 | Duty Officer link "Duty Officer (AI unavailable): no brief: work through the list by hand" | **Merge into** the Plan by hand group head as a fact line: "No Duty Officer brief this run (AI paused)." OK and stub variants **Keep** as today's one line, without the "(AI)" tag when ok: "Duty Officer: N items put in order of urgency · latest run 1102Z" + `AI-written` mark. | Q2 Q5 |
| K92 | Duty undone box (red) "3 mandatory items not dispatched …" | **Merge into** the Plan by hand group: those 3 flights carry the `Must do` chip and sort first. Nothing else is lost (the same flights are among the 28). | Q2 |
| K93 | Duty brief opened ("AI unavailable" 3 times; model; "0 delegations") | **Reword** to one state chip "Not run (AI paused)" and one line "No brief was made up in its place." The model and the raw reason go to Technical detail (as D68). "Do first · in urgency order (AI off)" and the deferral reasons **Keep**. | Q2 |
| K94 | Airport plan link "Airport plan waiting: … cancel 129" (points to an older stub draft) | **Keep** the words. **Fix** the target so the link and the Airports tab agree: the link names the plan it opens ("Earlier plan 1030Z waiting for your decision"), and the newest plan's state is in K95. (Not AI noise; a contradiction found on the way.) | §4 |
| K95 | Airports plan card "AI unavailable" + "Compare the plans below" (0 plans) + "explained by: <model>" | **Reword**: status chip `AI unavailable` (caution). Body: "No recommendation (AI unavailable: timed out). **No plan was solved: plan the network by hand.** A new plan waits for AI: next slot 0700Z." "Compare the plans below" is shown only when scenarios exist. "explained by: <model>" is shown only when a model explained something; otherwise "Planned 1031Z by code · version 1". | Q3 §4 |
| K96 | Why this plan red alert "AI unavailable: RECOVERY AGENT ERROR: TimeoutError / The solver's plans stand…" | **Merge into** K95 (the card already says it). The raw reason moves to Technical detail. "The solver's plans stand" is shown only when there are solved plans. `role=status`, not alert. | Q2 Q4 §4 |
| K97 | Earlier plans "1030Z · AI unavailable …" | **Keep** (history), with the mark word `AI unavailable` neutral. A plan still "Waiting for your decision" sorts first with a caution chip, so it is not buried. | Q3 |
| K98 | Paperwork starters (handover, VAR); SRA waiting only in the budget sheet | **Keep** the method sentences. **Add** at the SRA starter: "Waiting for AI: next slot 0700Z. Complete it by hand if it cannot wait." Failure cards keep their job words ("No brief was written. Hand over by voice or in writing."; "No document was written. Complete it by hand."). (Separate, not AI: the VAR "0 flights" while 28 are exposed needs its own check.) | Q3 |
| K99 | Document viewer marks `AI-written · <model>` per box | **Reword**: `AI-written` per box, model id once in the document header's Technical detail and in each mark's title. The signer note (168) **Keep**. | Q5 |
| K100 | Messages chips, sheet, failure | **Reword** chips to `AI-written` (id in title). The failure sheet and toast **Keep** ("No message was written. Write the crew or passenger text by hand."), using `role=status`. | Q3 Q5 |
| K101 | Notices badge, chips, failure card, paste-sheet sentence | **Keep** the failure at the notice, worded as D51 ("Not read (AI unavailable): read it yourself."). Chips: `AI-read` (id in title). The paste-sheet method sentence **Keep**. | Q3 Q5 |
| K102 | Ask: suggestion "Which flights did the AI fail to plan?", tool word "AI problems", failure "AI unavailable: budget_exhausted / Ask again" | **Reword**: a note above the input while paused: "Ask is paused until 0700Z (today's free AI quota). The Wall shows every flight and count." Answer failure: "No answer: AI paused until 0700Z. Nothing was made up." "Try again" is disabled until the reset, with the label "Try again after 0700Z". Suggestion: "Which flights must be planned by hand?"; tool word: "Hand-plan list". Good-answer marks: `AI-written` (id in title), steps "model <id>" behind the steps disclosure. | Q3 Q5 |
| K103 | Crew form "… no AI is used" | **Keep**. | — |
| K104 | Shared builders `aiChip`, `unavailableCard`, `codeChip` | **Reword** `aiChip` into `aiMark(verb, modelId)`: visible verb only (`AI-written` / `AI-read` / `AI-chosen`), title "{verb} by {model}. Checked by code before it is shown." Only call it for content that passed the checks. `unavailableCard` uses `role=status` and caution (not alert/serious); default text "AI unavailable: nothing was put in its place. Do this step by hand." The raw reason goes to Technical detail. `codeChip` **Keep**. | Q4 Q5 |

---

## 4. Honesty defects fixed on the way (rule 9)

These are cases where the UI says an AI step happened when it did not, or hides that it did not.
They are part of this change because quieting AI must not hide them.

| Id | Defect | Fix |
|---|---|---|
| H1 | Area card and estimate header say "the model found nothing to add" for PENDING and OFFICIAL_ONLY (no model ran) | M27 / D43 |
| H2 | "How the model read it [AI-written]" shown on code-written text (model_id none, 0 attempts) | D45 |
| H3 | The map tag ignores the per-situation outcome, so a PENDING or failed estimate looks model-checked | M24 |
| H4 | Duty Officer budget refusal shown as "the model's brief failed the checks", with a model id | D68 / K93 |
| H5 | `adk` worklist steps labelled "by an AI helper" with no model call | D63 |
| H6 | Plume Reader "Its newest step worked" for a queued step; Recovery "Quiet" after a timeout | D70 |
| H7 | Desk "Compare the plans below", "The solver's plans stand", "explained by: <model>" with 0 solved plans and no explanation | K95 / K96 |
| H8 | `AI tried` chip titled "Checked by code before it is shown" on a failure | K82 / K104 |
| H9 | "No advisory yet" / "Nothing waiting" (green) where the AI did not run and flights must be planned by hand | W14, D53, D54, D56 |

---

## 5. New copy (exact words)

### 5.1 The calm state (AI home lead: Wall Details › AI helpers, and the Desk's "AI today" sheet)

- **Paused, live budget closed:**
  "**AI paused until 0700Z.** Google reported today's free AI quota used up. Queued work (2 jobs)
  runs then, on the same model; nothing is dropped or handed to another model. Until then, code
  still checks every flight against the official area, and nothing is made up in place of an AI
  step. Flights that need a plan are on the Desk to plan by hand."
- **Paused, time unknown:** the same, with "AI paused." and without "until 0700Z" / "runs then".
- **Trouble:** "**AI on, 1 problem.** {helper} did not run ({why}) at {HHMMZ}; nothing was put in
  its place. {consequence}." One sentence per cause.
- **On:** "AI on. It can widen TEPHRA's estimate, never shrink the official area. AI-written parts
  are marked."
- **Off:** "AI off: no model is connected. Code does every step; code templates write the text."

### 5.2 Chips

| State | Wall chip / Desk chip (visible) | Narrow (≤ 420 px) | aria-label |
|---|---|---|---|
| on | `AI on` | `AI on` | "AI on. Opens Details, AI helpers." (Desk: "Opens AI today.") |
| paused | `AI paused · 0700Z` | `AI paused` | "AI paused until 0700Z: today's free AI quota is used up. Opens …" |
| trouble | `AI on · 1 problem` | `AI · 1 problem` | "AI on, 1 problem: {helper} did not run. Opens …" |
| off | `AI off` | `AI off` | "AI off, code only. Opens …" |

### 5.3 At the place (Wall)

- Advisory line: "No advisory drafts: AI paused until 0700Z. Plan the {n} flights by hand on the
  Desk." · "No advisory drafts: AI unavailable ({why}). Plan the {n} flights by hand on the Desk." ·
  "Advisories not drafted yet: waiting for AI, next slot {until}."
- Closure sub-line: "No airport plan (AI unavailable): plan the network by hand ›"
- Trust line: "TEPHRA's estimate is never smaller than the official area, which stays binding."
- Map tag suffixes: "· AI waiting" · "· AI unavailable" · "· AI off"
- Area card: "Same as the official area: the AI plume read is waiting (next slot 0700Z)." ·
  "Same as the official area: no AI read was needed."
- Flights row: "No advisory: AI paused · plan by hand"
- This flight: "No advisory for this flight: AI paused until 0700Z. Plan it by hand on the Desk ›"
- Decisions: pill "Nothing to approve"; "No drafts: AI paused. {n} flights to plan by hand on the
  Desk ›"; sub-list title "To plan by hand".
- Airport closures: "A new plan waits for AI: next slot 0700Z."
- Duty Officer (AI helpers): pill "Not run"; "Not run: today's free AI quota is used up (until
  0700Z). No brief was made; nothing was made up in its place. Must-do jobs went to the Desk."
- Trace cause row: "Duty Officer did not run: AI paused (daily quota). 1–18 must-do jobs per run
  went to the Desk · 28 times · 1046Z–1102Z · See the jobs ›"

### 5.4 At the place (Desk)

- Group head: "Plan by hand · {n} flights" / "No AI plan for these flights: AI paused until 0700Z.
  Nothing was substituted. Decide each flight, then mark it handled." / fact line "No Duty Officer
  brief this run (AI paused)."
- Row: "{flight} · {real id} · {entry} · {volcano} · left {HHMMZ} · [Must do] · Mark handled…";
  "Show all {n} flights".
- Announcer: "{n} flights to plan by hand: AI paused." / "1 more flight to plan by hand."
- Breakdown: "{a} advisories · {n} flights to plan by hand"
- Airports: "No recommendation (AI unavailable: timed out). No plan was solved: plan the network by
  hand. A new plan waits for AI: next slot 0700Z."
- SRA starter: "Waiting for AI: next slot 0700Z. Complete it by hand if it cannot wait."
- Ask: "Ask is paused until 0700Z (today's free AI quota). The Wall shows every flight and count." /
  "No answer: AI paused until 0700Z. Nothing was made up." / "Try again after 0700Z" / "Which
  flights must be planned by hand?"

### 5.5 Style

- AI marks: one class per page (`.ai-mark` on the Wall, `.ai-mark` in `desk.css`) using
  `--c-text-2` text on `--c-surface-3` with the `i-model` icon, 12 px, 600 weight. No new colour
  tokens: caution = `--c-caution` / `--c-caution-bg`, neutral = `--c-info`. `--c-serious` is not
  used by any AI element after this change.
- Consequence clauses use the existing sub-line style with a caution dot, never a box.
- `role=alert` only on feed/DB/connection/load items. AI items use `role=status` and are announced
  once per cause.
- 12 px minimum everywhere (R12); all text comes from code (CSP: no inline styles or scripts; the
  state suffix is a span, not `::after` content).

---

## 6. Files to change

**Wall**
- `tephra/web/wall/x-parts.js`: `aiState()` (new), cause grouping by `stage + reasonClass` (D62),
  `aiStopClause` → §1.1 words, `planFailure().short/clause` → job words, plural fix "1 job" (D67),
  `ACTOR_WORDS` / `actorWords` for `adk` without a model call (D63), mark builder `aiMark`.
- `tephra/web/wall/story.js`: `storyFailures` drops the plan, satellite, duty and trace-fails items
  (W8-W11); advisory line (W14), closure sub-line (W15), disagreement sub-line (W16), `renderTrust`
  (W17), CTA (W18), All volcanoes count (W20).
- `tephra/web/wall/panels.js`: chip text/tooltip/aria (W1-W3, W6), `estimateOutcome` and the
  `areaSection` gate (M27, D43-D46), Flights row meta (D53), Decisions header and sub-list (D56),
  Problems tile (D61), disagree row (D47).
- `tephra/web/wall/ext.js`: `failureCount` → cause counts; AI helpers header, lead, tiles, What went
  wrong link, helper states from facts, Budget details words (D64-D67, D70, D71); Airport closures
  pill and queued re-plan (D57, D58, D60); Satellite and Notices tone and words (D48, D49, D51);
  Track record note (D73).
- `tephra/web/wall/duty.js`: `OUTCOME.BUDGET` (D68); "Passed to the Desk" link (D69).
- `tephra/web/wall/details.js`: Needs a look rules (D38, D39), index rows (D40-D42), This flight
  (D54), area detail.
- `tephra/web/wall/derive.js` and `tephra/web/wall/map.js`: tag text and trigger by outcome (M24,
  M25).
- `tephra/web/wall/ext-map.js`: "Box n: possible ash" (M26); `tephra/web/wall/controls.js`: the
  `AI-read` mark on the satellite-box row (M35).
- `tephra/web/index.html`: static chip (W5). `tephra/web/wall.css`: chip states, `.ai-mark`,
  caution sub-line, no red for AI.

**Desk**
- `tephra/web/desk.html`: `#model-chip` re-parented into `#budget-chip` (K78).
- `tephra/web/desk.js`: header chip, breakdown, title (K78, K85, K94).
- `tephra/web/desk/ui.js`: `aiState()`, `aiMark()`, `unavailableCard` role and tone (K104).
- `tephra/web/desk/budget.js`: the chip and the "AI today" sheet lead (K79, K80).
- `tephra/web/desk/failures.js`: the Plan by hand group, rows, announcer, handle sheet (K77, K81-K84).
- `tephra/web/desk/duty.js`: link and undone box merged into the group; brief state (K91-K93).
- `tephra/web/desk/queue.js`: writer line, breakdown, remove `modelChip` (K85-K87).
- `tephra/web/desk/review.js`: writer note and Drafted by words (K88, K89).
- `tephra/web/desk/network.js`: plan card, Why this plan, Earlier plans (K95-K97).
- `tephra/web/desk/docs.js`, `docview.js`, `messages.js`, `notice.js`, `ask.js` (K98-K102).
- `tephra/web/desk.css`: `.ai-mark`, group rows, chip states.

**Docs and tests**
- `docs/UI-REDESIGN.md`: amend G2 ("AI failures are shown where they change the dispatcher's work,
  in caution tone; red is for the picture"), R3.1 (chip), R5.6 (banner scope), R5.7 (trust line).
- `docs/UI-DETAILS-PANELS.md`, `docs/UI-DESIGN.md`: the AI helpers, Decisions, Airport closures and
  Trace sections as above.
- `tests/test_ui_inventory.py`: keep all ids; add `"never smaller than the official area"` to the
  Wall checks.
- `tests/test_ui_ai_quiet.py` (new, static like the inventory test): `storyFailures` has no
  no model-id interpolation in visible chip text (`ai-chip`, `trust`, writer lines); `estimateOutcome`
  has explicit PENDING and OFFICIAL_ONLY branches; the "How the model read it" gate checks the
  outcome; `OUTCOME.BUDGET` exists; `modelChip` is gone.

---

## 7. Acceptance checklist

Measured with the live JSON fixtures in `<scratch>/quiet-shots/` (the same routed
files as the inventory), at 1440x900 and 390x844, before and after. An "AI mention" is a visible
text node in the viewport, with no tap and no hover, that names AI, a model or a model id, or an
AI helper's failure (regex `\bAI\b|gemini|model|Duty Officer|planner|failed`, checked by hand),
plus any control whose only target is AI status.

**Count on the default Wall at 1440x900 (today's paused state)**

| | Before | Target after |
|---|---|---|
| AI mentions | **8**: chip "AI on", badge "28 failed", banner "Airport plan: the recovery planner timed out…", banner "Duty Officer could not run…", "+ 1 more problem ›" (AI only), trust "AI is on…", chip `gemini-3.8-flash`, chip `gemini-3.5-flash-lite` | **≤ 4**: chip `AI paused · 0700Z`, advisory clause "No advisory drafts: AI paused…", closure clause "No airport plan (AI unavailable)…", map tag "· AI waiting" |
| …of them red / serious | 4 | **0** |
| Model ids visible | 2 | **0** |
| AI text above the story lead | 2 banner items | **0** |
| Story-column px spent on AI status | about 150 (92 banner + 59 trust) | **≤ 24** (the clauses ride on existing lines) |
| Story fit level | 8 of 8, other volcanoes folded "+ 4 more" | **≤ 6**, no fold with 5 volcanoes |

**Wall**
- [ ] 390x844: phone bar shows `AI paused` with no badge, and the Data chip shows "5 off"; no AI
      text between the header and the story lead; at most 3 AI mentions above the map.
- [ ] `#fail-line` is hidden with today's data, and appears red with a forced feed ERROR, DB failure,
      lost connection or map error (each tested), with `#lost-banner` still `role=alert`.
- [ ] Each of the 6 places that lack an AI part says so at the place: the advisory line, the closure
      sub-line, the map tag, the area card, Flights / This flight, Decisions. Each says it once.
- [ ] The AI home lead reads as §5.1; What went wrong shows **2 causes** (Duty Officer budget, 28
      steps; recovery timeout, 1), with a link to the hand-plan jobs; "1 jobs" is gone.
- [ ] H1-H9 are each verified on the live fixture (PENDING card, code-written rationale, Duty
      `BUDGET`, `adk` actor, helper states, Airports with 0 plans).
- [ ] "Never shrink the official area" is present in the chip tooltip and the AI home header;
      "never smaller" is visible in the map key and trust line; the decision-support footer and all
      REPLAY labels are unchanged (shots compared).
- [ ] Stub run (`TEPHRA_LLM=stub`): chip `AI off`; tag "· AI off"; marks `Code (AI off)`; no
      `AI-written` anywhere.

**Desk**
- [ ] 390x844 Decide: the Next decision card starts on the first screen (y < 844), not at 8,620 px;
      `#fail-section` ≤ 640 px with 5 rows and "Show all 28 flights"; all 28 reachable in one tap.
- [ ] Header: one AI chip; `document.documentElement.scrollWidth <= 390`.
- [ ] AI mentions on the first screen of Decide at 390: before about 89 (2 chips, the section head,
      28 × 3 per card, the Duty link and undone box), target **≤ 3** (the chip, the group head and its
      fact line).
- [ ] The screen reader hears one announcement for the 28-flight batch, not 28.
- [ ] Ask shows the paused note before a question, and "Try again after 0700Z" is disabled.
- [ ] The SRA starter shows "Waiting for AI: next slot 0700Z."; the Airports card no longer says
      "Compare the plans below" with 0 plans.

**Everywhere**
- [ ] No AI element uses `--c-serious` or `role=alert`; no visible text under 12 px; no new colour
      literals (tokens only); CSP report clean (no inline style or script); axe: 0 serious issues;
      chip and mark contrast ≥ 4.5:1 in the dark theme.
- [ ] `pytest tests/test_ui_inventory.py tests/test_ui_ai_quiet.py` passes; the full suite with the
      stub passes.
- [ ] Nothing deleted: every inventory entry's information is found at its "Move to" or "Merge into"
      location (a checklist walk of section 3 against the after shots).

---

## 8. As built (2026-10-13)

Shots: before `<scratch>/quiet-shots/before/`, after `.../after/` (routed live JSON;
`stub-*` is the stub app). Scripts in `.../quiet-shots/cap/`.

| Measure (live paused state) | Before | After |
|---|---|---|
| Wall 1440x900, visible AI text nodes (regex of §7) | 9 (8 by §7's hand count) | 5: chip, advisory clause, closure clause, "advisories waiting (AI paused)", the Details button sub-line; plus the map tag "· AI waiting" on the canvas |
| …red / serious | 4 | 0 |
| …model ids visible | 2 | 0 |
| …AI text above the story lead | 2 | 0 |
| Story fit level 1440x900 | 8, folded | 6, still folded (see 3 below) |
| Wall 390x844 above the map | 9 | 3 |
| Desk 390 Decide first screen | 11 nodes, Next decision at y=8,620, `#fail-section` 8,428 px, header 467 px wide | 3, y=179, 636 px, 390 px |
| Desk 1440 Decide first screen | 12, y=8,235 | 3, y=231 |

Where the build differs from sections 3 to 6, item by item:

1. `aiState(D, store)` lives in `wall/ext.js` (it needs the Wall's `ext` budget and plans); the
   pure rules are `aiStateOf()` in `wall/x-parts.js`, shared with the Desk's `aiState()` in
   `desk/ui.js`, which takes `{ budget, failures, llm, duty, plan }`.
2. The reset time is shown in REPLAY too (§1.1); the old `reopensAt` rule that hid it is gone.
3. W12 target "no fold" is not met at 1440x900: the advisory and closure clauses take two lines
   each, so the column fits at level 6 with the other volcanoes folded (it was level 8). The
   banner and the model chips are gone.
4. §7 counts the "(AI paused)" that W20 adds to "0 advisories waiting": the Wall shows five AI
   mentions, not four.
5. M24: ACCEPTED, REPAIRED and OFFICIAL_ONLY keep the plain tag "TEPHRA's estimate · same as
   official" (no suffix); removing the tag would delete information.
6. M26: the map draws no box tooltip; "AI-read" sits in the map key row and the Layers row.
7. D53: the flight row's meta reads "No advisory: AI paused · plan by hand" with "Must do"; the
   row stays one button (to This flight), so the Desk link is on This flight and Decisions.
8. K77: the "Plan by hand" rows are two lines (flight and entry, then callsign, volcano and time)
   with the button on the second line: about 60 px each, `#fail-section` 636 px at 390.
9. K91-K93: the Duty Officer card stays in the quick links, one line ("not run (AI paused): its
   must-do flights are in Plan by hand"); its undone box lists only work Plan by hand does not.
10. K102: "Try again after 0700Z" is disabled only for a quota refusal while the reset is known.
11. Added on the way: the Desk's empty Next decision reads "No drafts to approve. 28 flights to
    plan by hand are below." instead of a green "No drafts waiting." (H9 on the Desk); repeated
    trace lines "1 job" and "18 jobs" collapse into one run.

### 8.1 Review fixes (2026-10-13, after 8536a92)

Two reviews (clutter, honesty) of the first build. Shots: `<scratch>/quiet-shots/fix/`
(script `fix/wall.mjs` for the Wall variants live, lane, undone, trouble, open, feederr, recdata;
`fix/desk.mjs` for the Desk scenarios live, lane, undone, drafts).

Honesty:

1. A budget refusal is part of "paused" only when it is a lite-model refusal during the pause
   (`absorbed`). A lane's share running out, or the Plume Reader's own model running out (from the
   trace on the Wall, and from the budget on both pages), is a problem in every state, so the chip,
   the story, Flights and Decisions say so and the flights are planned by hand.
2. A Duty Officer that ran and left must-do work ("DUTY OFFICER DID NOT DISPATCH THIS FLIGHT", "left
   N mandatory item(s) undone", or the newest run's `undispatched`) is the reason class `undone`:
   "Duty Officer left must-do jobs for the Desk", never "AI unavailable". Only its must-do flights
   are on the Wall's hand-plan list, and the story says "The Duty Officer left 3 must-do flights for
   the Desk: plan them by hand."
3. The Wall's hand-plan list is "flights with no advisory" (among the newest 50 when the list is
   full). It no longer claims the Desk's count: the story says "Plan the 28 flights by hand" and the
   links say "Plan by hand on the Desk"; the Desk's list, with its handled marks, is the record.
4. The reset time is on the real clock. In REPLAY it reads "0700Z real time" everywhere (chip, story,
   Flights, This flight, AI home, Desk, Ask, queued slots), amending §1.1.
5. "Did not run" only where no model was called (a budget refusal). A model that was called and gave
   nothing usable is "AI unavailable ({why})"; the Duty Officer's run that failed the checks is "No
   brief", its Model fact reads "Called; no brief passed the checks" and it carries no AI-written mark.
6. The airport plan covers the network: on a volcano with no closure of its own, the story still says
   "Ash closes 3 RFA airports (all volcanoes)" with "No airport plan (AI unavailable): plan the network
   by hand ›". The main button is "Decide on the Desk →" only when this volcano has hand-plan flights.
7. Recovery steps code could not run (no RFA schedule, an exception; actor `system`) are not AI
   causes: they are a red story line ("Airport re-planning cannot run: the RFA schedule could not be
   read.").

Clutter:

8. Helper rows: the badge says what happened ("Not run", "No brief", "No plan", "Waiting"); the
   sub-line says why without repeating it; "Quiet" only for quiet helpers.
9. Flights rows say "No advisory" (and "Must do"); the list's one caution note says why and what to
   do. Decisions rows carry no AI word; the group head and its aside say it once.
10. The Desk Decide page says the pause once (the Plan by hand group head); the Duty Officer line
    reads "no brief this run · its must-do flights are in Plan by hand".
11. The Desk "AI today" sheet shows a closed model as "Closed until 0700Z", with a full bar and
    "closed for today by Google (449 of 450 unused)".
12. The trace's Problems tile counts AI failures by cause, and says "AI: 1 of 2 causes (28 steps)"
    when the AI home also counts a cause from outside the trace (the airport plan).
13. The top-bar AI chip is not drawn before the first data (W5 amended: it keeps its place and
    appears once at its real width). The phone bar keeps at least 7.5 rem for the area picker and
    wraps the chips to a second row when they do not fit; the chip drops its model icon there.
14. The SRA starter says "Waiting for AI: next slot …" once (summary); its note says only what to do.
    The Desk Airports card's status says "No plan" or "No recommendation" and the line says "AI
    unavailable (timed out)" once; its footer says "Tried 1031Z" when nothing was solved. The estimate
    gives the next slot once. The calls tile drops "Main model 0 of 18" (the models list has it).
15. Desk hand-plan rows are about 56 px with a mouse (28 px button, 4 px padding); touch keeps 32 px.

Still not met: the Wall at 1440x900 still folds "+ 4 more" (the advisory and closure clauses are two
lines each), and the Wall shows five AI mentions because W21 keeps "AI" in the Details button's
sub-line as navigation. No axe scan was run (axe-core is not installed here); CSP was checked only
through the console (no violation messages).

### 8.2 Merged with AI at work and the Desk redesign (2026-10-13)

The branch `ai-at-work-desk-redesign` (AI at work, the Operator policy dialog, the Desk's list and
idle panes, and the backend fix for repeated failures across replay runs) was merged onto this
design. This document stayed the base for every AI word. What changed against sections 3 to 6:

1. One source. The branch's own status table (`wall/ai-status.js`) is gone. AI at work
   (`wall/board.js`) derives the same `aiStateOf()` from the same inputs as the chip: the trace
   through `aiErrorsOf()` (moved to `wall/x-parts.js` with the RECOVERY/system rule of review H7),
   the newest Duty Officer run, `newestPlan()` and the live budget. Its header shows `aiWords()` and
   the calm lead `aiLead()`. The Desk chip and its "AI today" sheet keep `deskAi()`.
2. W1 amended: the Wall's AI chip opens AI at work, which leads with the AI home's words and links
   to Details › AI helpers (still the record of models, calls and causes). A and `/#ai-at-work`
   open it too.
3. Q4 on the board: a helper that gave nothing is caution, never red. "No result" (warning shape)
   when a model was called, "Not run" (dot) when none was, or the helper's own word ("No brief",
   "No plan"). A failed hand-out line is amber. The board no longer counts failed steps.
4. K77/K81-K84 amended: the Plan by hand group is a summary card after the Next decision (the cause
   once, the counts with "must do", "Show the n flights", "Why ›"); the flights open in the right
   pane at 1100 px and up and as their own view on a phone, inside the ash first, must-do first. A
   row opens the flight's sheet ("Plan RFA1701 by hand"), and "Mark several handled…" ticks
   several, each still its own request and audit entry. Announcements stay one per batch, and
   flights code closed are said in the same batch.
5. The helper is "Flight planner" everywhere (the board's roster), not "Planner".

### 8.3 The story column redesigned, and the reset time in REPLAY (2026-10-13)

After user feedback that the Wall's story column was cluttered (two AI warnings, three link
styles, the key in the column), the story became a hero number, three fact tiles, one notice and
the source lines (docs/UI-DESIGN.md 7.6). Against this document:

1. W14 and W15 merged: the advisory line and the closure sub-line are one caution notice, said
   once, with one "Why ›": "AI paused until 0700Z" / "No advisory drafts and no airport plan. Plan
   the 14 flights and the network by hand on the Desk."
2. W17 amended: the trust line is one tap from the hero's ⓘ ("What is TEPHRA's ash area?").
   "never smaller than official" stays on screen in the map key, now a card on the map.
3. W20 amended: "0 advisories waiting" carries no "(AI paused)"; the notice says why once.
4. The reset time in REPLAY: "0700Z real time" read awkwardly. In REPLAY a real-clock time is said
   as the time left, which reads the same on either clock: the chip "AI paused · 2 h 45 min left",
   the sentence "AI paused for another 2 h 45 min", "next slot in 2 h 45 min", "Try again in 2 h
   45 min" (`realWhen` in `wall/x-parts.js`, used on both pages and on AI at work). Live, the
   clock time stays ("until 0700Z").

### 8.4 Naming: one assistant, "TEPHRA Assistant" (2026-10-13)

The user chose one name for the AI on both pages: **TEPHRA Assistant** (research:
`builder-cup-ideas/notes/tephra-assistant-naming-research-2026-10-13.md` section 3, idea 4; Desk
spec sections 6.6 and 9.1-9.5). Its specialists are **skills named by their job**: Coordinator
(the coordinating agent the code calls the Duty Officer), Plume reader, Satellite reader, Flight
planner, Drafter, Recovery planner, Paperwork drafter, Notice reader, Message drafter, Handover
drafter and Ask. Only the words on screen change: ids, file names, API fields, CSS classes, Python
names, trace text and raw reasons keep "Duty Officer" and "AI UNAVAILABLE" (rule 9), and those
stay readable one tap in, under Technical detail and in the audit. One constant holds the name
(`ASSISTANT` in `wall/x-parts.js`); `HELPER_NAME` and the board's `HELPERS` hold the skill names.

This amends section 1.1, 5.2 and 5.5 (the words, the chip and the marks); the rules Q1-Q6 and the
honesty list of section 2 are unchanged.

| Before (sections 1.1, 5) | Now |
|---|---|
| Chip `AI on` / `AI paused · 0700Z` / `AI on · 1 problem` / `AI off` | `TEPHRA Assistant · on` / `TEPHRA Assistant · paused` (no reason and no time, 8.6; it read `· waiting until 0700Z` before) / `TEPHRA Assistant · Recovery planner gave no result`, `· Coordinator gave no result`, `· Flight planner did not run` (a quota refusal while the assistant is on), `· 2 skills gave no result` / `TEPHRA Assistant · off (code only)`. Counted by skill, never by cause (8.5). At 420 px and less: `Assistant · on`, `Assistant · paused`, `Assistant · 1 problem`, `Assistant · off` (the label and tooltip keep the full name). |
| `AI paused` / `AI paused · 0700Z` (markers) | `Assistant paused`, with no cause or time at the place: "No advisory drafts for these 23 flights. Plan them by hand. Why ›" (8.6, 8.7) |
| `AI waiting` (a job queued) | "Waiting in line", "A new plan waits in line for TEPHRA Assistant. Why ›" (8.6; the slot is said at the assistant's home only) |
| `AI unavailable ({why})` | "{Skill} gave no result ({why}): nothing was put in its place." "{Skill} did not run" stays reserved for a step no model was called for (8.1 item 5); a run that answered and left work says so ("left must-do jobs for the Desk"). |
| `AI-written` / `AI-read` / `AI-chosen` | "Drafted by TEPHRA Assistant" / "Read by Plume reader" (Satellite reader, Notice reader) / "Chosen by TEPHRA Assistant"; also "Ordered by Coordinator", "Explained by Recovery planner", "Answered by TEPHRA Assistant". Still only on content a model produced (Q5); the model id stays in the title and label. |
| `Code (AI off)` | "Code only (assistant off)"; "(AI off)" in sentences reads "(code only)". |
| "AI helpers" (Details), "AI today" (Desk sheet), "AI at work" (board) | "TEPHRA Assistant" (its group "Skills"), "TEPHRA Assistant" (the sheet), "TEPHRA Assistant at work" |
| Duty Officer (on screen) | Coordinator. A trace line no plain-words pattern knows gets only the name changed (`plainLine`); the raw line keeps it. A line that also carries a raw "AI UNAVAILABLE" is shown verbatim instead (8.5). |

**Where "AI" is still written** (disclosure only): the chip's tooltip ("TEPHRA Assistant is
TEPHRA's AI assistant (Gemini). It can widen TEPHRA's estimate, never shrink the official area.");
the first-use and About lines ("TEPHRA Assistant is an AI assistant. It reads feeds and drafts
text. Code does every number and safety rule. You approve everything." as the first-use line at
the top of the Wall's story and under the Desk's Decide summary, in the Wall's About and Help, the
board's "How to read this board", the Desk's assistant sheet, and Details › TEPHRA Assistant ›
How this works); the stub chip's tooltip; the quota phrase "today's free AI quota" (at the assistant's home only, 8.6); the glossary; Technical detail, the
audit and the raw rule-9 strings; the privacy page. Model ids stay only in tooltips, the
assistant's home (Details › TEPHRA Assistant, the Desk's sheet, the board's cards), Technical
detail and the record (Why this advisory › Drafted by, the audit). Since 8.6 the board is not a
home: its skill sheets keep only "Model: {id}" (no calls), and the cause, calls and slots are said
at Details › TEPHRA Assistant and the Desk's sheet.

**The mark.** The Strata mark (a vent dot with flight-level bands stepping downwind; chosen
direction C) is five symbols in `tephra/web/icons.svg`, `currentColor` only: `ta-64` (the Desk
sheet, drawn at 48 px), `ta-16` (the board title, attribution marks, the "See TEPHRA Assistant at work" links, the
Details section title, the Coordinator's card), and `ta-working` / `ta-waiting` (hollow bands, the
outline 1.5 px instead of 1.25 px so it holds at 14-16 px) / `ta-unavailable` (a slash cuts the
top band) for the chip by state (on / waiting / trouble or off), on both pages and on the board's
state pill. No animation: the Wall loads icons from the external sprite. The mark's shape now
carries the state, so the chip's caution dot is gone: a waiting or troubled chip keeps a caution
border and is never red; the phone bar keeps the mark.

**Honesty kept.** Every string in `tests/test_ui_inventory.py` `HONESTY`, "never shrink the
official area" in the chip tooltip and the assistant home, "never smaller" in the map key and the
trust line, the REPLAY labels and the decision-support line are unchanged. `tests/test_ui_ai_quiet.py`
pins the name, the disclosure lines, the five symbols, and that none of the old words is left in a
page string.

### 8.5 Naming: review fixes (2026-10-13)

Two reviews of the naming build (coverage and honesty) found these, fixed here:

- **The chip counts skills, not causes.** A cause is a skill plus a kind of failure, so one skill
  that failed two ways read "2 skills not running". The chip now counts skills, and it uses the
  verb its tooltip uses: "gave no result" (a model was called and gave nothing usable), "did not
  run" (no model was called: a quota refusal), "left jobs for the Desk", "had problems" when they
  differ. This replaces the spec's "not running", which contradicted the tooltip; a single
  Coordinator failure no longer reads as the whole assistant "not running". The tooltip names each
  cause once. The narrow "N problems" still counts causes.
- **First use and About.** The line "TEPHRA Assistant is an AI assistant. ..." is in the Wall's
  About and the Desk's assistant sheet, one click from the assistant chip on both pages. The
  first-use card that carried it on both first screens was removed on 13 Oct 2026: a reader with
  little time met four lines of text before the story. The stub chip's tooltip
  says what TEPHRA Assistant is too, so stub mode (the demo default) discloses it.
- **No credit for a run no model made.** The Coordinator run's fact "Run by: TEPHRA Assistant"
  is "Started: by code, after new aircraft" (code starts every run; the Model fact says whether a
  model was called, with its id there, in the assistant's own home).
- **Server words in the assistant's words, in the UI** (their API values are pinned): a
  model's jobs "Every other AI step" read "Every other skill" (`jobsWords`); the queue's "waiting for AI budget, next slot 0700Z" is not shown: the
  next slot is said from `next_slot_at`, as the time left in REPLAY (`workWords`, `pacingWords`).
- **"Did not run" only where no model was called**, also for a flight with no draft
  (`draftBlock`). A Coordinator outage line has its own plain-words pattern ("Coordinator gave no
  result (timed out). N jobs that must be done went to the Desk").
- **The Desk header never scrolls sideways.** When the chip and the connection words do not fit
  (390 px, "3 problems" and "Reconnecting…"), the chip keeps its mark and state words and drops
  the visible name (`fitHead`); its label and tooltip keep "TEPHRA Assistant".
- **Smaller:** one `aiSymbol()` for the four chips; the board title uses `ta-16` (the cut for
  14-24 px); the review's "Drafted by" row says "TEPHRA Assistant · model", not "Drafted by"
  twice; the SRA's R7 mitigation says what the screen shows ("Drafted by TEPHRA Assistant", model
  id in the record).
- **Kept as is:** the stub "off" chip keeps `ta-unavailable` (Desk spec 6.6 ties it to "off or
  not running"); the narrow Wall chip keeps "Assistant · waiting" without the time (with it the
  chip takes a row of its own under the area menu at 390 px; since 8.6 every chip says
  "paused" with no time); the Desk card head "Ordered by
  Coordinator" marks the order the model chose and the brief's body "Drafted by TEPHRA Assistant"
  marks its text (spec 9.4); the board's cards keep their model chips (the board is the
  assistant's home, as Details › TEPHRA Assistant is). Amended by 8.6: the board is no longer a
  home; its sheets keep the model id only, and the one home is Details › TEPHRA Assistant (the
  Desk's sheet on the Desk).

### 8.6 Say the cause once (2026-10-13, branch `quiet-quota`)

The user's words: "don't mention AI quota left or not left everywhere". Evidence: the inventory of
every quota, budget, reset and slot mention (`<scratch>/qq-shots/inventory.md`), with
the live paused state of 13 Oct 2026 routed into the Wall and the Desk (`qq-shots/shots.mjs`,
`before/` and `after/` shots and `text.json`). Before this change the quota was said in the Wall
chip and its tooltip, the story's notice title, Details › Decisions, Flights, one flight, Airport
closures, the Satellite picture, the flow board's headline, lede, gate, Coordinator line, legend,
help and log, the Desk chip, the Plan by hand card and sheet, the Coordinator card, Airports,
Paperwork and Ask (before: 26 quota words visible and 46 in tooltips across the main views; after:
none).

**The rule.** TEPHRA Assistant has one neutral state word everywhere in the main views:
`TEPHRA Assistant · on`, `· paused` (its model is closed for the day, or work waits for a slot),
`· off (code only)`, or `· {skill} gave no result` / `· {skill} did not run` (real trouble). A
pause carries no reason and no time there. The reason, in full, is said in **one place**: Details ›
TEPHRA Assistant on the Wall and its phone equivalent, the Desk's assistant sheet:

> **TEPHRA Assistant is paused until 0700Z.** Why: Google's free daily AI quota for
> gemini-3.5-flash-lite is used up. Queued work (4 jobs) runs then, on the same model. …

(in REPLAY "paused for another 2 h 45 min", 8.3; the time is said once, 8.7). A reset already
behind the real clock while the model still reads as closed is said as overdue, never as a
countdown stuck at "1 min" or a stale "until": "TEPHRA Assistant is paused. Why: … is used up. Its
reset was due 3 h 10 min ago (real time), and the model still reads as closed, so when it opens is
not known." (live: "was due at 0700Z").
The home also keeps the budgets, the per-model calls and Google's closing, the lanes and pacing,
the queue with its slots, and the Coordinator run's "Not run: today's free AI quota is used up".
Tooltips and Technical detail may point to the home ("TEPHRA Assistant is paused: see why in
Details › TEPHRA Assistant.") but never carry the quota sentence; raw rule-9 lines
(`AI UNAVAILABLE (budget_exhausted)`) stay verbatim under Technical detail and in log tooltips.

**At the place: the consequence and the action, then "Why ›".**

| Place | Now |
|---|---|
| Wall story notice | title `TEPHRA Assistant · paused`; body unchanged ("No advisory drafts and no airport plan. Plan the 23 flights and the network by hand on the Desk. Why ›") |
| Details › Decisions | "No advisory drafts for the 23 flights. Plan by hand on the Desk › Why ›" |
| Details › Flights / one flight | "No advisory drafts for these 23 flights. Plan them by hand. Open the Desk › Why ›" / "No advisory draft for this flight. Plan it by hand on the Desk › Why ›" |
| Details › Airport closures | "A new plan waits in line for TEPHRA Assistant. Why ›" (or, with nothing queued, the failed plan's row and "Why ›") |
| Details › Satellite picture | "2 pictures were not read. Nothing was put in their place, and the official area stands. Why ›"; each row "Not read: TEPHRA Assistant is paused" (or "Satellite reader did not run" while the assistant is on) |
| Details index row | `Paused` |
| Flow board | headline `TEPHRA Assistant · paused`; lede "Code still reads every feed and checks every flight; jobs wait in line and must-do flights come straight to you. Why ›"; gate `Paused` with "4 jobs in line" (tooltip "Why: Details › TEPHRA Assistant"); Coordinator "Paused: must-do jobs come to you"; legend "waiting in line"; skill sheets "Model: {id}" (no calls), "Waiting in line" (no slot time) |
| Desk Plan by hand | "No advisory drafts for these 23 flights. Plan them by hand. Nothing was substituted." (the card's "Why ›" opens the sheet; the list, which replaces Decide on a phone, has its own "Why ›"); a flight's sheet "No advisory draft for this flight. Nothing was put in its place. Why ›" |
| Desk Airports / Paperwork | "Recovery planner did not run. … A new plan waits in line for TEPHRA Assistant. Why ›" / "Waiting in line for TEPHRA Assistant", "Complete it by hand if it cannot wait. Why ›" |
| Desk Ask | before a question: "TEPHRA Assistant is paused, so Ask cannot answer yet. The Wall shows every flight and count. Why ›"; an answer refused while paused: "TEPHRA Assistant is paused. Why ›" (no timed retry; the question goes back into the box, and the note above the box hides while this answer is the newest); refused while the assistant is on: "No answer: Ask did not run. Why ›" with "Try again" |
| Desk idle pane (1100 px and up) | "TEPHRA Assistant is paused. Code still checks every flight, and must-do flights come to you to plan by hand." |
| Plain-words lines (How TEPHRA decided, the board's log and playback, What went wrong's occurrences) | "Coordinator did not run. N jobs that must be done went to the Desk", "Plume read for X was not handed out. TEPHRA's area stays at the official reports", board log "Coordinator got 3 jobs on the scheduled check · did not run" (8.7: never "assistant paused", a line on record may be one skill's refusal while the assistant was on) |

**Honesty kept (rule 9).** Every place that lacks an assistant output still says so where the
dispatcher acts, and what to do; nothing implies the assistant worked; the cause is one tap away
("Why ›", the chip, the board's "Details › TEPHRA Assistant ›"). `draftBlock` still marks a paused
assistant's missing drafts (`paused: true`), only `blockPhrase` has no cause words for it. The
REPLAY strip, the decision-support strings, "never shrink" in the chip tooltip and the home, and
the first-use line are unchanged. The Desk no longer redraws its chip every tick in REPLAY: it
carries no time left.

**Code.** `wall/x-parts.js`: `aiWords` paused → `paused`; `aiLead(s, { home })` (the reason only
when `home`, with `model` and `slotAt` from `aiStateOf`); `causeTitle(c, { home })`; `PAUSED`,
`plainWhy`, `whyLink`; `causeShort`, `draftBlock`, `blockPhrase` and the plain-words patterns say
"assistant paused" (amended by 8.7: "did not run"; "paused" only while the whole assistant is).
`untilShort` and `after` are gone (no main view says a time).
**Tests.** `tests/test_ui_ai_quiet.py` scans the main-view sources for quota words
(`test_main_views_never_say_why_the_assistant_is_paused`) and pins each place's consequence and
its "Why ›"; `tests/test_wall_board.py` runs the shared words and the board model (a paused chip,
lead, draft block and plain lines carry no quota words; the home's lead names the cause, the model
and the next slot).


### 8.7 Say the cause once: review fixes (2026-10-13, branch `quiet-quota`)

Two reviews of 8.6 (clutter and honesty) found these, fixed here:

- **"Paused" is the whole assistant's state, never a cause.** A quota refusal for one skill's
  model or share (the Plume reader's own model, a lane) leaves the assistant on, with a problem.
  8.6 still said "(assistant paused)" for it, so the chip read "on" and the place "paused". Now
  "paused" is said only when `aiStateOf().kind` is `paused`; otherwise the place says what happened
  with no cause: "Flight planner did not run", "Plume reader cannot run now" (its model is out and
  it has not been asked yet; the chip says the same), "Recovery planner did not run", "Satellite
  reader did not run", "No answer: Ask did not run". `plainWhy` gives no words for a quota
  refusal. The plain-words lines and the board's log never say "paused": a line on record may be
  one skill's refusal, so they say "did not run". `causeShort(c, { home })` and `aiLead` name the
  cause ("today's free AI quota is used up") only at the assistant's home.
- **Quota words through a value.** The story notice's title read `Recovery planner gave no
  result (${pf.why})`, and `pf.why` is the full quota cause for a refused plan. `planFailure` now
  gives `word` ("Recovery planner did not run", or "gave no result (timed out)"), and its `title`,
  `sub` and `place` say "did not run" for a quota refusal; `why` stays for the home only.
- **The cause one tap from every place.** The board's lede ends with "Why ›" while the assistant
  is paused or has trouble (before, the cause was chip → board → the link at the foot of "You
  decide": two taps, and a tooltip on a phone). A skill sheet that did not run, gave no result or
  waits while paused has "Why: Details › TEPHRA Assistant ›". The Desk's Plan by hand list (which
  replaces Decide on a phone) has its own "Why ›"; so do the Desk's Airports line, the Paperwork
  SRA note, the Wall's Satellite picture (one note above the rows) and Airport closures when no
  re-plan is queued. A skill that did not run or gave no result gets "Why ›" at Decisions, Flights
  and one flight too, not only a pause.
- **An overdue reset is said, at the home.** 8.6 removed the board's "reset was due … ago"
  without moving it; the home then said a countdown stuck at "1 min" (REPLAY) or a stale "until
  0700Z" (live). `realWhen` now returns `past` with `due` for a time already behind the real
  clock, `aiStateOf` gives `overdue`, and the home's lead says "Its reset was due 3 h 10 min ago
  (real time), and the model still reads as closed, so when it opens is not known."
- **The time once at the home.** The lead says it in its first words only ("paused until
  0700Z"); the Wall's pill is "Paused", the calls tile "Closed for today", the skills' rows
  "TEPHRA Assistant paused", the Coordinator's note has no time, and the Desk sheet's queue is
  "Waiting in line · 4" with each job "waits in line" (its own slot only when it is not the
  reset). The model rows say "Closed for today by Google (449 of 450 unused)" and the foot drops
  "Counts start again …" while the lead says when it opens. "Nothing was put in its place" for one
  cause, "their place" for more.
- **Words that read wrong at the place.** "No advisory drafts yet" sat under an advisory marked
  "Drafted by TEPHRA Assistant" and a "3 drafts" count, and "yet" promised drafts for every
  flight: it is "No advisory drafts for these 23 flights. Plan them by hand." (the Wall: "No
  advisory drafts for the 23 flights", "No advisory draft for this flight"). The board's lede says
  nothing about jobs in line while the work queue did not load. The Desk Coordinator card says
  "Not run (TEPHRA Assistant paused)" and its one line "Not run · its must-do flights are in Plan
  by hand" for a refused run (the
  Wall's word; "No brief" stays for a model that gave nothing). The board's Coordinator says "not
  run 11:28:56" for a refused run, never "last run". A Satellite reading refused on quota is
  "did not run" on the board, never "gave no result". A flight row's label no longer reads "no
  advisory: , plan by hand" when there is no phrase.
- **Ask says it once and keeps the question.** While the newest answer is "TEPHRA Assistant is
  paused. Why ›" the note above the box hides; the question goes back into the box.
- **The guard covers the shared files.** `test_main_views_never_say_why_the_assistant_is_paused`
  now scans `wall/ext.js` and `wall/x-parts.js` with the home's own builders left out (`aiLead`;
  `agentStatus`, `workWords`, `budgetBlock`, `waitingTail`, `budgetTile`; the `WHY.budget` and
  `pacingWords` constants). `tests/test_wall_board.py` runs the shared words on a quota refusal:
  a skill out of calls while the assistant is on is never "paused" and carries no quota words,
  `planFailure` on a quota refusal says "did not run", and the home says an overdue reset.
- **Kept.** The board log's "From the record" tooltips keep the raw record line (for example
  `Duty Officer AI UNAVAILABLE (budget_exhausted); …`): it is the record, like Technical detail,
  and rule 9 keeps raw reasons reachable.
