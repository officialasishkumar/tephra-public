# TEPHRA: what is measured, and what is not

Every number here comes from a file in the tree or from a run of a command listed at the end.
Where a measurement is unfinished it says INCOMPLETE; where none was made it says "not measured".
The public demo serves the committed scorecards at `GET /api/evals`, and the Wall's Track record
group shows them with the same words.

## 1. Tests

The offline suite (`TEPHRA_LLM=stub uv run pytest`, no model, no network) runs on every push to
`main` through `.github/workflows/ci.yml`; the README badge is its result. The families, by file:

| Family | Files | What they pin |
|---|---|---|
| Parsers on real recorded responses | `test_feeds_text.py`, `test_feeds_geo.py`, `test_vona_archive.py`, `test_notices.py` | SIGMET, VAA, observatory notice, JMA report, TAF, METAR, ADS-B, winds and frame parsing, byte for byte |
| Disagreements | `test_discrepancies.py` | LAG, ENVELOPE, non-observation, DIRECTION_MISMATCH, HEIGHT_MISMATCH, SILENCE, CONFLICT on the real Semeru cases |
| Geometry and exposure | `test_geo.py`, `test_geo_props.py`, `test_reroute.py`, `test_reroute_agents.py` | the never-shrink union, the projection, the lateral reroute |
| Model steps and validators | `test_plume_reader.py`, `test_planner.py`, `test_plan_material.py`, `test_drafter.py`, `test_duty_officer.py`, `test_ask.py`, `test_recovery.py`, `test_comms.py`, `test_regdocs.py`, `test_satellite_reader.py` | structured output, one repair, `AI UNAVAILABLE`, nothing substituted |
| Kept answers and budgets | `test_ai_answers.py`, `test_seeded_answers.py`, `test_quota.py`, `test_ai_worker.py` | the material question, re-check before reuse, the per-day count |
| Desk, record and API | `test_approvals.py`, `test_failures.py`, `test_audit_chain.py`, `test_audit_verify_api.py`, `test_decision_guard.py`, `test_decision_guard_api.py`, `test_visitor_access.py`, `test_chain_api.py`, `test_evals_api.py`, `test_api.py` | the state machine, the hash chain, the server-side refusals, the visitor role |
| Pipeline, store and replay | `test_pipeline.py`, `test_runtime_state.py`, `test_store.py`, `test_replay.py`, `test_record_replay.py`, `test_backtest.py` | one tick from feeds to a draft; the replay minute; the rebuilt notice pages |
| Pages | `test_ui_inventory.py`, `test_ui_ai_quiet.py`, `test_glossary.py`, `test_readme.py`, `test_wall_*.py`, `test_desk_*.py` | the pinned honesty strings, the glossary words, no inline styles |
| Deploy and export | `test_scripts.py`, `test_ci_workflow.py`, `test_public_export.py` | the deploy paths filter, the pinned actions, the export lists |

The count of tests is not written here on purpose: it drifts with every push, and the badge says
whether they pass. The public tree skips exactly 26 tests whose fixtures are data that may not be
republished (BoM pages and FTP texts, MAGMA pages, NICT tiles); each skip reads "private fixture
(RED licence) not in this tree" (`docs/DATA-LICENCES.md`).

### Property tests

Hypothesis tests, with the example cap each decorator sets (`tests/test_geo_props.py`,
`tests/test_reroute.py`; 28 tests collected across the two files by
`uv run pytest --collect-only -q tests/test_geo_props.py tests/test_reroute.py`):

| Test | Examples | Property |
|---|---|---|
| `test_cone_contains_everything_the_official_rings_enclose` | 300 | the estimate contains every official polygon, a folded ring counting as all it encloses |
| `test_every_track_that_enters_the_cone_is_reported` | 300 | no track that crosses the estimate inside the lookahead is missed |
| `test_exposure_never_projects_a_non_finite_speed` | 100 | a non-finite ground speed is never projected |
| `test_divert_formula_reproduces_its_own_numbers` | 300 | the labelled divert formula round-trips |
| `test_t9_property_no_route_enters_the_cone_and_the_obstacle_covers_it` | 25 | no OK reroute enters the unbuffered estimate, and the obstacle is a superset of it |

## 2. Plume reader (Gemini 3.8 Flash)

Protocol: `evals/plume/README.md` (research/10 section 5). Scorecard:
`docs/evals/plume-scorecard.json`, generated 2026-10-14 22:04Z from
`evals/plume/results/scorecard-20261014T2204Z.md`; 3 runs per case; the majority of the runs is
the call.

| Arm | Input | Existence | Direction | Stability | Schema | Verdict |
|---|---|---|---|---|---|---|
| I (images, 10 Tokyo VAAC cases, advisory text withheld) | 3 Ash RGB frames, 1 IR frame, the vent pixel, the FL180 wind | 9 of 10 correct; 0 quiet cases called ash with high confidence | 4 of 4 detected cases within 45° | 9 of 10 cases agree across runs | 25 of 30 responses clean | INCOMPLETE: 5 of 30 responses not run yet |
| T (Semeru texts) | SIGMETs plus the observatory's text for the same hour | — | — | — | — | not run: the observatory's text is not in the repo (MAGMA disallows crawling) |

The one existence miss is the Taal case of 8 October (`20261008_27307000_0023`, class ash, called
"not ash" in both runs). Until every run of every case has a response, each verdict reads
INCOMPLETE rather than PASS or FAIL (`CLAUDE.md` rule 8: the free tier is never multiplied).

## 3. Backtest (`docs/backtest/scorecard.json`, 2026-10-11)

Each replay case is replayed on a fixed clock in 30-minute steps and TEPHRA's estimate is scored
against the official areas published later. `scripts/backtest.py` runs arm D offline.

| Arm | Reader | Moments scored | Official area missed | Later data used | Coverage of later official areas | Over-warning |
|---|---|---|---|---|---|---|
| D (code-only baseline) | the stub, no model | 1,190 (Krakatau 431, Semeru 757, Java 2) | 0 | 0 | 90.3% (the official area alone: 90.3%) | 0.29 |
| G (Plume reader) | kept Gemini reads, 0 new calls | not yet scored | — | — | — | — |

Arm D cannot beat the official area by construction: the stub proposes nothing, so the estimate is
the official union. The scorecard's own caveats stand: the later official product is partly derived
from the same inputs, an Indonesian SIGMET copies the Darwin VAA, and the estimate is a decision
margin, not a forecast of observed ash, so overlap scores against a later polygon are low by design.

## 4. Model calls per loop

Measured with `scripts/count_model_calls.py`, which plays the demo window with the stub's answers
under a model's name and counts every ask per skill (no model, no network). The demo window is
`anak-krakatau-20260905`, 2026-09-05 10:30Z to 19:30Z. "Lite" is every skill on the Flash-Lite
tier.

| 9-hour loop | Plume reader (main model, 18 a day) | Coordinator | Flight planner | Drafter | Lite asks |
|---|---|---|---|---|---|
| Loop 1, cold, before the material question (`docs/evals/call-counts.json`, `offset_0`) | 30 | 299 | 615 | 388 | 1,303 (one SRA draft included) |
| Loop 2, played again from kept answers (same run) | 2 | 48 | 50 | 149 | 247 |
| Loop 2 with the replay minute, 30 s offset (`offset_30_quantum_60`) | 2 | 48 | 50 | 149 | 247: the offset changes nothing |
| Loop 1, cold, material question, age limit on the replay clock (`material_question_cone_keyed_planning`) | 30 | 299 | 613 | 392 | 1,305 |
| Loops 2 and 3 of that run | 2 | 48 | 50 | 149 | 247 each: the same questions expired every loop |
| Loop 1, cold, shipped rule (`material_question_replay_age_free`) | 29 | 276 | 588 | 319 | 1,184 |
| Loop 2 of that run, from kept answers | 0 | 8 | 0 | 8 | 16 |

The replay minute (`TEPHRA_REPLAY_QUANTUM_S=60`) makes every loop and every deploy ask at the same
replay instants, so a kept answer matches again. The planner and drafter questions are keyed by the
flight's decision inputs (the hazard band, the allowed actions, the urgency band, the level, the
open alternates and the usable reroutes, the last by their content) rather than by the cone's id.
Two things were measured and not shipped: planning once per material question instead of per cone
(677 planner asks against 385 on a 12:00Z start, because the level and the nearest alternates move
with the aircraft), and the skill age limit on the replay clock (a question asked twice in a loop
more than the limit apart was asked of the model again in every loop: 247 lighter asks a loop that
never settled). In REPLAY a kept answer now serves its material question at any replay-clock age;
in LIVE the age limit stands. The cold loop needs about three days of the free lighter budget
(450 a day); after that the demo loop asks 16 lighter calls per 9 hours.

## 5. Speed and tokens

`docs/evals/replay-metrics.json` (`scripts/replay_metrics.py`, 2026-10-14): on the replay clock
with the stub's instant answers, 161 flights were exposed and 90 drafted in the first 60 minutes
from 10:30Z; median and p90 time from first exposure to a draft waiting on the Desk: 0.0 minutes.
That figure is honest and uninformative: the stub drains each minute's work inside the tick, so it
measures the pipeline, not a model. A live run adds the models' latency and the budget's pacing.

Tokens per advisory: **not measured.** The token fields exist on advisories and Coordinator runs;
the sum is reported once a live run has written them.

`scripts/measure_load.py` on the same replay: `/api/wall` is 283-308 KB raw and 25-29 KB gzipped
across the window; the Wall holds one event stream and polls five secondary endpoints once a minute;
the Desk holds one stream and polls nothing.

## 6. Free models: a negative result

`scripts/free_model_check.py`, 2026-10-12 (`evals/free_models/results/`, kept out of the public tree
until the owner tracks the folder): Gemma 4 31B on the free tier cannot hold the Notice reader
schema (0 of 5 parsed and passed the code's checks), held the Drafter and handover schemas 4 of 5
times, and failed both ADK tool runs (the Flight planner with a 503, the Coordinator with a 500 and
28 mandatory items not dispatched). TEPHRA stays on Gemini Flash-Lite for every lighter step.

## 7. Not measured

- Tokens and cost per advisory (section 5).
- Time to first draft with a live model.
- Arm G of the backtest, and Arm T of the plume test.
- Any dispatcher's time saved: no operator has run TEPHRA.
- The Indonesian and Japanese wording of the message templates (needs a native-speaker check).

## 8. Commands

```bash
TEPHRA_LLM=stub uv run pytest                                              # the suite
uv run pytest --collect-only -q tests/test_geo_props.py tests/test_reroute.py
uv run python scripts/backtest.py                                          # arm D, offline
uv run python scripts/plume_eval.py --score-only                           # re-score the cached responses
uv run python scripts/count_model_calls.py --start 2026-09-05T10:30:00Z --minutes 540 --loops 2 --quantum-s 60
uv run python scripts/replay_metrics.py                                    # docs/evals/replay-metrics.json
uv run python scripts/measure_load.py                                      # /api/wall sizes and requests per minute
GEMINI_API_KEY=... uv run python scripts/plume_eval.py --max-calls 18      # spends quota: owner only
GEMINI_API_KEY=... uv run python scripts/free_model_check.py               # spends quota: owner only
```
