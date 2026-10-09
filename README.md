# TEPHRA

**A volcanic-ash decision desk for airline dispatch.** When the official ash products for a volcano differ, TEPHRA works out how they differ and builds the cautious hazard area, which never shrinks below the official one. It then finds which flights are heading into it and drafts an advisory for each of them. A duty dispatcher approves, edits or rejects every draft on a phone.

> **Decision support only. Ring of Fire Air (RFA) is a fictional airline. Nothing is sent to any real system. Not for operational use.**


> **Status (2026-10-10):** the code is written and passes static checks (compile, `ruff`, `node --check`, cross-module import check). It has **not been run yet**, and no Gemini call has been made. The first run is the next step: see [Getting started](#getting-started).

## The problem

On 6 September 2026, ash from Anak Krakatau closed Jakarta's Soekarno-Hatta airport for the first time in its history, along with seven other airports. About 2,961 flights and 341,000 people were affected. During the eruption the observatory's only aviation notice said *"Ash-cloud is not observed"*, while the met office issued 39 SIGMETs with ash up to 50,000 ft ([research/01](research/01-news-2026.md)).

The two official voices often differ:
- the volcano observatory (VONA);
- the Volcanic Ash Advisory Centre (VAA). Indonesian SIGMETs copy the VAA almost exactly (489 of 492 tops match).

Most of their differences are harmless: a lag, a value inside the other's envelope, or a night-time "not observed". But some are real. **In the 30 days to 9 October 2026, 28 of Semeru's 92 observatory ash reports had ash heading where the official ash area did not reach 10 km from the vent** ([research/14](research/14-contradiction-census-30-days.md)). In those cases no single product is "the cautious one".

ICAO Doc 9974 says the operator, not the ash centre, must "reliably and correctly resolve any conflicts that may arise among data sources" ([research/03](research/03-prior-art-products.md), [research/15](research/15-dispatcher-reality.md)). TEPHRA drafts that first pass.

## What TEPHRA does

```mermaid
flowchart LR
  F[Public feeds<br/>VA SIGMET · VAA · VONA*<br/>winds · TAF · ADS-B<br/>Himawari (optional)] --> D[Discrepancy finder<br/>code]
  D --> P[Plume Reader<br/>Gemini 3.8 Flash<br/>structured output]
  P --> C[Cautious hazard area<br/>code: union, never shrinks]
  C --> E[3D exposure<br/>code: alt_baro, 2,000 ft margins]
  E --> PL[Exposure Planner<br/>ADK agent + tools]
  PL --> DR[Dispatch Drafter<br/>Gemini]
  DR --> H{Dispatcher<br/>approve · edit · reject}
  H --> Q[(Own outbound queue<br/>+ hash-chained audit)]
```

| Step | Who does it | What it does |
|---|---|---|
| Poll | code | Collects VA SIGMETs (aviationweather.gov), Tokyo and Darwin VAAs (NWS tgftp, public domain), TAFs, Open-Meteo winds and adsb.lol positions. Every record keeps its source, fetch time and sha256. |
| Discrepancies | code | Labels every difference: LAG, ENVELOPE, non-observation, DIRECTION_MISMATCH (including drift outside the polygon), HEIGHT_MISMATCH, SILENCE or CONFLICT. Gemini never decides what counts as a disagreement. |
| Plume Reader | Gemini | Reads the texts, the remarks and the discrepancy list. Grades each source's evidence, explains it, and proposes a widened area (OFFICIAL / WIDENED / HYPOTHESIS). Code validates the output: only input sources may be cited, no model-written times, never below the official top, size caps. It allows one repair, then falls back to the official products. |
| Hazard area | code | The union of every valid official polygon and the model's sector. A property test checks that it contains every official polygon. |
| Exposure | code | Projects each aircraft along its track. A flight is exposed only if its pressure altitude band meets the hazard band within 2,000 ft. Gives minutes to entry. |
| Planner | ADK agent | Uses geometry, alternate and TAF tools to pick CONTINUE, MONITOR, CHANGE_LEVEL, HOLD or DIVERT. There are no reroutes, because the free data has no airways and any waypoint would be invented. HYPOTHESIS mode allows only MONITOR or HOLD. |
| Drafter | Gemini | Writes the ACARS-style body. Code writes the header with the flight, UTC times, sources and hashes, and a validator rejects any invented code or time. |
| Desk | human | Approve, edit (both versions kept) or reject (a reason is required). Only approved advisories reach the outbound queue, which never leaves the store. |

\* MAGMA VONAs are off by default (`TEPHRA_VONA_LIVE`), because MAGMA's robots.txt disallows crawling. Replays carry recorded VONAs.

Optional: a **split-window layer** computed by code from raw Himawari-9 B13/B15 data (AWS Open Data). It may only widen the area or raise urgency. "No signal" is never read as "no ash", because the method is often blind in moist tropical air ([research/12](research/12-himawari-raw-split-window.md)).

## What is live, what is ours

- **Live and public:** every SIGMET, VAA, TAF, wind and aircraft position, and every timestamp on screen, which is copied from the feeds and never written by a model.
- **Ours, said out loud:**
  - the airline and its queue (fictional);
  - routes extrapolated from track and speed (filed flight plans are not free);
  - the hazard area, which is a hypothesis with a confidence;
  - minutes and fuel from a simple labelled formula;
  - replays, which are always labelled.

## Getting started

```bash
uv sync --extra dev                                   # add --extra science for raw Himawari, --extra gcp for Firestore
uv run pytest                                         # stub LLM, no network
TEPHRA_LLM=stub TEPHRA_LOCAL_SCHEDULER=1 TEPHRA_DESK_PIN=1234 uv run tephra
# Wall: http://localhost:8080/    Desk (phone): http://localhost:8080/desk
TEPHRA_MODE=REPLAY TEPHRA_REPLAY_CASE=<case_id> uv run tephra          # labelled replay
GEMINI_API_KEY=<personal AI Studio key> TEPHRA_LLM=gemini uv run tephra  # real Gemini (free tier ~20 calls/day)
```

All settings are in [`.env.example`](.env.example). Gemini is reached only with a personal `GEMINI_API_KEY`, never through Vertex AI or Application Default Credentials. Daily call budgets fall back to code before the free-tier quota runs out.

| Path | Purpose |
|---|---|
| `/` | The Wall: map, official polygons, the hazard area, aircraft, the three source cards, the live reasoning trace |
| `/desk` | The phone desk: PIN login, draft cards, approve / edit / reject |
| `/api/wall`, `/api/state`, `/api/events` (SSE) | Read endpoints the Wall uses |
| `/api/desk/...` | Desk endpoints (cookie session, CSRF header, optimistic versioning) |
| `POST /tasks/tick` | Scheduler tick (`X-Tephra-Task-Token`) |

Deployment to Cloud Run (one service and one Cloud Scheduler job, with Firestore, Secret Manager and Artifact Registry) is in [`deploy/README.md`](deploy/README.md). The scripts there are run by a person from a personal Google account and refuse any other login.

## Evaluation

- `tests/`: unit tests on real recorded feed responses (`tests/fixtures/`). They cover parsers, discrepancy rules on the real Semeru cases, never-shrink geometry, exposure, validators, the Plume Reader's repair and fallback paths, the desk state machine with its audit hash chain, the store and the API.
- `evals/plume/`: the 10-case Gemini test on Tokyo VAAC's labelled archive (images) plus the Semeru text-reconciliation case, with pass criteria fixed in advance ([evals/plume/README.md](evals/plume/README.md)).
- `scripts/count_traffic.py`: whether there is enough traffic near a volcano for a live per-flight moment.
- `scripts/record_replay.py`: records or reconstructs a labelled replay.

## Research

[`research/`](research/README.md) holds the full research behind TEPHRA:
- news;
- history and costs;
- prior art (commercial products, open source, hackathon entries);
- feed checks;
- rules and terms;
- dispatch practice and ash science;
- a 30-day contradiction census;
- point-by-point answers to the team's own objections.

Every key claim was checked by two independent verifiers. Start with [`research/CONFLICTS.md`](research/CONFLICTS.md) and [`docs/DECISION-MEMO.md`](docs/DECISION-MEMO.md).

**What TEPHRA does not claim:**
- It does not detect ash.
- Per-flight AI advisories with human approval are not new (Jeppesen and The Weather Company have them).
- Its output is not a forecast, a warning or a dispatch release.

What it adds is the evidence reconciliation in front of them.

## Repository map

| Path | Contents |
|---|---|
| `tephra/` | The application (see `MODULES.md` for the contract and `docs/ARCHITECTURE.md` for the design and safety rules) |
| `tephra/web/` | Wall and Desk (plain HTML/CSS/JS, MapLibre GL 4.7.1, OpenFreeMap) |
| `data/` | Volcano and airport catalogues; `replay/` cases |
| `tests/`, `evals/`, `scripts/` | Tests, the Plume Reader evaluation, recording and counting tools |
| `deploy/` | Cloud Run, Scheduler, secrets and Firestore rules |
| `research/`, `docs/` | Research, decision memo, pitch |
| `.claude/skills/` | Claude Code skills for this repo |

## Licence and data credits

MIT (see `LICENSE`). Data:
- aviationweather.gov and NWS tgftp (US public domain);
- JMA / Tokyo VAAC;
- Bureau of Meteorology / Darwin VAAC (via NWS);
- adsb.lol (ODbL);
- Open-Meteo (CC BY 4.0, non-commercial free tier);
- Himawari-9 data from JMA, distributed by NOAA on AWS Open Data (derived products are labelled);
- the volcano catalogue from the Smithsonian GVP.
