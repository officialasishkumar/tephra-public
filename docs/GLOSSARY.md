# TEPHRA glossary: one set of words

The words on screen are canonical. Documents use the same words; a code name appears once,
in parentheses, where a reader will meet it in the tree. `tests/test_glossary.py` keeps the
retired words out of the README, this file, ARCHITECTURE, PITCH, EVALS, THIRD_PARTY and every
page string.

## The assistant and its skills

| On screen (canonical) | In the code | What it is |
|---|---|---|
| TEPHRA Assistant | — | The one AI assistant. Everything a model does is shown under this name, with the skill that did it. Built on Gemini through the Gemini API and the Agent Development Kit (ADK). |
| Coordinator | `tephra/agents/duty_officer.py` (`DutyRun`, `DutyBrief`) | The ADK agent that orders the day's assistant work and hands it to the other skills through tools. Code builds the work list and holds the safety line; the Coordinator decides the order and writes the brief. |
| Plume reader | `tephra/agents/plume_reader.py` (`PlumeEstimate`) | Reads the official texts, the remarks and the discrepancy list, grades each source's evidence and proposes TEPHRA's estimate. Gemini 3.8 Flash, structured output. |
| Satellite reader | `tephra/agents/satellite_reader.py` | Reads the newest satellite picture; supporting evidence only. Hidden in the demo. |
| Flight planner | `tephra/agents/exposure_planner.py` (`PlannedAction`) | The ADK agent that chooses one action per exposed flight from the code's options. |
| Drafter | `tephra/agents/dispatch_drafter.py` (`DraftText`) | Writes the advisory body; code writes the header. |
| Recovery planner | `tephra/recovery/agent.py` around the CP-SAT solver | Compares the solver's scenarios and recommends one. |
| Paperwork drafter | `tephra/regdocs/narrative.py` | Writes the four narrative boxes of the SRA draft. |
| Message drafter | `tephra/comms/messages.py` | Templates for crew and passenger messages; code fills every fact. |
| Handover drafter | `tephra/comms/handover.py` | The two narrative fields of the shift handover. |
| Notice reader | `tephra/agents/notice_reader.py` | Reads a pasted notice with verbatim evidence. Hidden in the demo. |
| Ask | `tephra/agents/ask.py` | Answers questions from the data with a cited tool result behind every claim. |
| skill | — | One of the above. In a document the first mention may say "skill (an ADK agent or a Gemini structured-output step)". |

## The ash

| On screen (canonical) | In the code | What it is |
|---|---|---|
| official ash area | `official_layers`, `OfficialLayer` | The area an official product (SIGMET, VAA) says the ash covers. Binding. Drawn pink. |
| TEPHRA's estimate | `HazardCone`, `build_cone` ("the cone") | The cautious area: the union of every valid official polygon and the Plume reader's proposal. Never smaller than the official area. Drawn as amber dashes; "Where TEPHRA widened the area" is hatched. |
| the observatory's notice | `Vona` | The volcano observatory's notice for aviation (VONA). Supporting; it can widen, never shrink. |
| disagreement | `Discrepancy` | A difference between sources that code labels: LAG, ENVELOPE, non-observation, DIRECTION_MISMATCH, HEIGHT_MISMATCH, SILENCE or CONFLICT. Gemini never decides what counts. |
| binding | — | What official products are. TEPHRA's estimate contains them whatever a model says. |
| official-only | `CoverageMode.OFFICIAL` | TEPHRA's estimate equals the official area (no widening, or the Plume reader gave no result). |
| widened | `CoverageMode.WIDENED` | TEPHRA's estimate is larger than the official area, with the reason and the source leaned on. |
| hypothesis | `CoverageMode.HYPOTHESIS` | No official polygon is in force; only MONITOR or HOLD may be advised. |

## The flights and the decisions

| On screen | In the code | What it is |
|---|---|---|
| RFA flight | `proxy_flight` | Ring of Fire Air is a fictional airline; each RFA number stands in for a real aircraft seen on ADS-B. |
| in or heading in | `ExposedFlight` | Inside TEPHRA's estimate now, or projected to enter it if track, speed and level are held. |
| suggested reroute | `RerouteOption` | A lateral route computed by code around a superset of the estimate; a status when none is found. |
| advisory | `Advisory` | A message drafted for one flight. A draft until a dispatcher approves, edits or rejects it on the Desk. |
| the Desk, the Wall, the Guide | — | The phone page where a person decides; the public map; the manual. |
| the record | `/api/audit`, `desk/audit.py` | The append-only, hash-chained audit trail. |
| visitor | `SessionRole`, `POST /api/desk/visitor` | Someone who enters the demo Desk without a PIN while a replay plays; their decisions are real, audited as `visitor:<name>` and capped. |
| Why this advice | `GET /api/advisories/{id}/chain` | The four-step chain behind a draft: Coordinator, Plume reader, Flight planner, Drafter. |

## Airline onboarding

| On screen (canonical) | In the code | What it is |
|---|---|---|
| Onboard your airline | `/onboard`, `tephra/airline/` | Nine short pages that end in an airline account. Behind `TEPHRA_FEATURES` `onboard`. |
| Pending verification | `AirlineRecord.status` `pending` | The airline's status until a TEPHRA dispatcher verifies or declines it on the Desk (Airlines to verify). Verified means a person checked who the operator is; it approves no policy and no use of TEPHRA. |
| Airline workspace | `/workspace` | The airline's private pages after sign-in: its answers, Data feeds, its assistant's model and the setup kit. Never listed publicly, never on the demo's map or the Desk's picture. |
| Setup kit | `workspace/kit.js`, `tephra/web/kit/push.py` | The zip the workspace makes in the browser to run the airline's own TEPHRA: `airline.env`, `policy.json` (ILLUSTRATIVE), fleet, schedule and network files, `push.py` and a checklist. |
| Own fleet | `TEPHRA_FLEET_PREFIXES`, `TEPHRA_FLEET_HEXES`, `FleetFilter` | In an airline's own TEPHRA, the aircraft checked against the ash: its callsign prefixes, its aircraft addresses and every aircraft it pushes. Empty (every aircraft) in the demo. |
| Dry run | `POST /api/airline/feeds/dry-run` | A push file checked record by record in the workspace, as a push would be; nothing is taken in. |

## Modes and honesty

| Word | Meaning |
|---|---|
| REPLAY | Recorded or reconstructed real feeds, labelled for the whole session. |
| Replay clock | The Wall's clock label in REPLAY; with the page title it is the REPLAY label. |
| reconstructed | Rebuilt after the event from archives (IEM NOAAPort, adsb.lol history). |
| NO MODEL | The offline test mode (`TEPHRA_LLM=stub`); code answers every step, labelled. |
| AI UNAVAILABLE | A model step that failed, ran out of budget or failed the code's checks. Nothing is substituted. |
| decision support only | TEPHRA's output is advice to a dispatcher; it is not a forecast, a warning, a dispatch release or air traffic control. |

## Retired words (do not use in documents or page strings)

`Duty Officer` (say Coordinator; the raw trace line keeps its text), `Exposure Planner`
(Flight planner), `Dispatch Drafter` (Drafter), `AI helpers` (skills), `hazard cone` /
`hazard area` / `cautious hazard area` (TEPHRA's estimate; "the cone" only in code comments
and ARCHITECTURE's engineering sections), agents as a plural noun for the on-screen roster
(skills), "Gemini sees ash" (never), "forecast" for TEPHRA's output (estimate), `SRA drafter`
(Paperwork drafter), the earlier pages' word for someone who tries the demo Desk without a PIN
(visitor), `Plume Reader` / `Satellite Reader` / `Notice Reader` with a capital R (Plume reader,
Satellite reader, Notice reader).
