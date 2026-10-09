# Where the world conflicts with TEPHRA

Synthesis of research files 00–16 (2026-10-10). Every row points to the file that holds the evidence and URLs. Severity: **FATAL** (kills the idea), **SERIOUS** (must change the build or the pitch), **MINOR** (wording or a small design rule). "Known before" = whether the earlier board/Akash passes (2026-09-25 to 10-09) already had it.

**Bottom line: no FATAL conflict.** TEPHRA survives as a narrower idea than the one on the board. The novelty is not the map, not per-flight alerting, not "Gemini sees ash", and not "an AI drafts a diversion a human approves". All of those exist. What is still open is **evidence reconciliation**: classifying what each official ash source actually observed, building the cautious union when no single product covers the others, and turning that into per-flight drafts a dispatcher signs.

---

## (a) Already built or occupied

| # | Conflict | Severity | Known before | Evidence | What changes |
|---|---|---|---|---|---|
| A1 | Jeppesen Stratosphere/Elrey (GenAI, beta Oct 2025) and Jeppesen ForeFlight Airflow (agents announced 6 Oct 2026: "AI proposes a specific action. A human approves.") already do "AI drafts a SIGMET-triggered diversion with fuel and alternates; OCC dispatcher approves; why-trail kept". | SERIOUS | No | 03 | Never claim novelty for "LLM per-flight advisory behind a human gate". Claim only the ash-specific evidence layer. |
| A2 | The Weather Company sells meteorologist-made company ash SIGMETs, VA flight-plan guidance and HOTL reports, and WXAlert auto-alerts dispatchers when a flight is "projected to intersect" a hazard. | SERIOUS | Partly | 03, 16 | A human-made reconciled ash area wired to flight alerts exists. TEPHRA's claim: automated, cited, evidence-graded, never-shrink, for carriers without a TWC contract. |
| A3 | Weathernews has used AI ash detection on satellite imagery since 26 Apr 2021 to feed ACOS dispersion forecasts sold to Japan and SE Asia airlines; it also runs an affected-aircraft service co-developed with JAL (turbulence). | SERIOUS for any image claim; MINOR for the idea | Yes (overstated as "sold on its own") | 03 | No "Gemini sees ash" claim anywhere. |
| A4 | EUROCONTROL EVITA already works out which flights ash affects and supports rerouting (Europe only). Tomorrow.io Altitude/Gale at Lufthansa has weather-agent diversion and alternate tools. | SERIOUS | No | 01, 03 | Cite both as prior art; TEPHRA's ground is APAC, the observatory-vs-VAAC reconciliation and the dispatcher draft. |
| A5 | Live Indonesian ash fusion layers are open source: `rezzzq/abu-gunung-api` (Darwin VAA + MAGMA VONA + Himawari Ash RGB + experimental split-window + METAR + winds, every 15 min, pushed 2026-10-09), AshMap, Pantau Abu. None uses an LLM, shows aircraft or decides anything. | SERIOUS | Partly (AshMap only) | 04 | Showing sources side by side is not novel. Lead with the reconciled area and the decision. |
| A6 | SIGMET × live aircraft × LLM warning is a hackathon pattern: MeteoWatch (Fabric 2024 category winner, Azure OpenAI), AeroGuard (2026 re-submission of the same README; not Gemini, no volcano logic). | SERIOUS (pattern) / MINOR (specifics) | Yes, but overstated | 00, 04 | Do not lead with the exposure count. |
| A7 | WrightWay (BigRed//Hacks, 4 Oct 2026, Grok): North Atlantic dispatcher console; ash = fixed 50 nm buffer around one SIGMET; deterministic ranking; LLM phrases; dispatcher approves; simulated flight (live mode ingests polygon SIGMETs). | SERIOUS | Yes | 00, 04, 16 | Differentiate on reconciliation of disagreeing sources, real APAC feeds, evidence grades. |
| A8 | FlySafe.zone fuses MAGMA colour codes, VAAC advisories, thermal anomalies and ADS-B, and sells per-FIR route scoring and webhooks; it says it is not a recommendation engine. | MINOR | Yes | 03, 16 | Name it. |
| A9 | NOAA/CIMSS VOLCAT already automates Himawari ash detection (BETA; sectors over historically active volcanoes). | MINOR | Yes | 12, 16 | The split-window layer is an independent witness, never "earlier detection". |
| A10 | A deterministic union of polygons already gives "never shrink below official" without an LLM. | SERIOUS | No | 04 | The demo must show a live case where Gemini's reading of VONA/VAA remarks changes the output (evidence grade, direction union, urgency), not just the union. |

## (b) Feeds and licences

| # | Conflict | Severity | Evidence | What changes |
|---|---|---|---|---|
| B2 | The JMA `vaac_darwin_list.html` "Darwin mirror" lists only advisories Tokyo issues as Darwin's **backup** (last entries 23 Sep 2026). BoM forbids scraping, hides a static "Nil current" default, and its IDD41300/41301 products return 404. | SERIOUS (easy fix) | 01, 05, 07, 13 | Read all live VAAs (Darwin and Tokyo) from NWS `https://tgftp.nws.noaa.gov/data/raw/fv/` (US public domain); keep the JMA list only to detect handovers. |
| B3 | OpenSky REST terms need a written licence for any live automated use. | SERIOUS (if used) | 05, 06 | Drop OpenSky. Use adsb.lol (ODbL); adsb.lol has announced a future API-key requirement. |
| B4 | AWC `isigmet` is deprecated, responses are cached 180 s, CORS is off, history covers only 30 days (HTTP 400 beyond), and records duplicate with "F" series IDs (11 rows = 8 distinct SIGMETs on 9 Oct). | MINOR | 05, 07, 09, 14 | De-duplicate by series; record our own SIGMET history from day one (7 Sep Krakatau is already gone; 25 Sep expires ~25 Oct). |
| B5 | JMA public Himawari JPEGs are ~5.5 km/px (the Semeru polygon is ~10×9 px), date-less slots served a 24-h-old frame, there is no Ash RGB JPEG, and night land renders pink in Dust RGB. NICT is non-commercial and its B13 tiles are alpha overlays, not brightness temperatures. | SERIOUS for the image step | 05, 07, 10 | Images are context only. If a satellite layer is shown, compute it from AWS `noaa-himawari9` B13/B15 at 2 km. |
| B6 | Open-Meteo free tier, adsb.fi and NICT are non-commercial; airplanes.live 403; Smithsonian GVP 403; BMKG behind a Cloudflare challenge. | MINOR (hackathon) / SERIOUS (commercial pitch) | 05 | Fine for the entry; list licences in the deck's business slide. |
| B7 | Raw Himawari on AWS: NOAA distributes "freely and openly" with attribution, no implied endorsement, modified data labelled; JMA's own channels send profit use to JMBSC and forbid redistribution. | MINOR | 12 | Attribute NOAA/JMA; label derived products; commercial use needs written confirmation. |
| B8 | Japan and Philippine VA SIGMETs often have no polygon (60 of 83 RJJJ Sakurajima, all 29 RPHI; 10 Mayon with no top). | SERIOUS for "never shrink" | 09, 14 | A rule for point-only SIGMETs: use the VAA polygon if one exists, else a labelled radius around the vent, flagged NO_POLYGON. |

## (c) Rules, terms and law

| # | Conflict | Severity | Evidence | What changes |
|---|---|---|---|---|
| C1 | Google Cloud ToS §3.3(d)(i) "High Risk Activities" and the Google APIs Terms both name **air traffic control**; neither has a human-in-the-loop exception. | MINOR for a sandboxed prototype; SERIOUS if the deck claims live airline operation | 00, 06 | Decision support only, fictional airline, own outbound queue only, nothing auto-sent; AI may only add caution; "CONTINUE" comes from deterministic code. Production would need a negotiated agreement and the operator's own safety risk assessment. |
| C2 | Gemini 3.8 Flash free tier is reported at ~20 requests/day (Flash-Lite ~500); per-model limits appear only in AI Studio. | SERIOUS | 06, 10 | Event-driven, cached calls only (input-hash change); Flash-Lite for routine steps; replay mode; or a capped paid tier (~$0.015/call). Do not create extra projects to evade quota (barred). |
| C4 | Free-tier prompts may be read by human reviewers and used to improve Google products. | MINOR | 06, 10 | Send only public feed data; strip aircraft registrations and approver names from prompts. |
| C5 | Cloud Run needs a billing account; only 3 Cloud Scheduler jobs are free; Firestore 20K writes/day; Cloud Storage free tier is US-only; Cloud Run jobs bill ≥1 min per run (~10.8× the free tier for 60-s pollers). | MINOR with design | 06, 10 | One request-billed service + one Scheduler job hitting `/tasks/tick`; SQLite-or-Firestore; no per-feed jobs. |
| C6 | 14 CFR 121.101 (approved sources), FAA 121.533/663 and Japan Civil Aeronautics Act Art. 77 put the decision with a licensed dispatcher/captain. | MINOR | 06 | Present TEPHRA output as additional information and a draft; never a dispatch release. |
| C7 | Japan Meteorological Service Act Art. 17 (forecast licence) and Art. 23 (JMA warning monopoly). | MINOR now; SERIOUS for a Japan go-to-market | 06 | Never call TEPHRA output a "forecast" or a "warning". Use "hazard area", "advisory draft". |
| C8 | EASA SIB 2010-17 is withdrawn (last revision R7; "R8" never existed); SIB 2023-13 replaced it 19 Dec 2023. UK AIC P 157/2025 retires the medium/high concentration charts on 27 Nov 2026. | MINOR | 06, 07, 15 | Cite SIB 2023-13 and Doc 9974; mention QVA as a dated hook. |
| C9 | ADK 2.11: `GOOGLE_GENAI_USE_VERTEXAI` is now `GOOGLE_GENAI_USE_ENTERPRISE`; `safety_v1` and `multi_turn_*` eval criteria need Agent Platform (Vertex). | MINOR | 06, 10 | Set both flags false; use only key-path eval criteria. |
| C10 | Search grounding is not on the free tier and its storage terms conflict with the audit log. | MINOR | 06, 10 | Do not use grounding. |
| C11 | gcloud on this Mac is the user's work account. | MINOR process | 06, 10 | Deploy scripts pin a separate gcloud configuration and refuse any other account; the user runs them. |

## (d) Science and operations

| # | Conflict | Severity | Evidence | What changes |
|---|---|---|---|---|
| D1 | Most "contradictions" are artefacts. At Semeru over 30 days: 93/185 VONAs said "Ash-cloud is not observed" (all while a VAA was in force: night/fog non-observations, not absence); 93/119 ash heights sat inside the VAA envelope and 23 more within 500 ft. Akash's two cited cases are LAG+ENVELOPE (25 Sep) and a non-observation (7 Oct). | SERIOUS (for the pitch as written) | 13, 14 | Code classifies LAG / ENVELOPE / NON_OBSERVATION first. Never pitch those as conflicts. |
| D2 | Indonesian SIGMETs copy the Darwin VAA (top matches 489/492; polygons vertex for vertex). "SIGMET vs VAAC vs VONA" is two voices, not three. | MINOR | 01, 07, 13, 14 | Model evidence lineage; say "observatory vs ash centre". |
| D3 | Satellite IR ash detection fails in the moist tropics: split-window was silent on both Semeru cases and on Ruang before the paroxysm (background +3 to +6 K); weak cluster at Ruang 17 Apr; strong only for Raikoke 2019 in dry air. Purpose-built NNs reach 48.5–84.1% pixel recall; no VLM has a published ash record. | SERIOUS for any image or BTD claim | 02, 07, 10, 12 | BTD/images may only widen or raise urgency; "no signal" is never "no ash"; heights come only from official texts. |
| D4 | No rule says "follow the most cautious product". Doc 9974 and EASA put the airline in charge and require it to "carefully consider and resolve differences or conflicts among the information sources". | Supports TEPHRA; MINOR for wording | 03, 07, 15 | Pitch: the operator must resolve conflicts between sources; TEPHRA drafts that first pass. |
| D5 | Vertical logic: FL is pressure altitude; ADS-B `alt_geom` is ~2,000 ft above `alt_baro` at cruise; CAP 1236 uses 2,000 ft buffers; EASA wants drift-down and depressurisation checks. | SERIOUS (build) | 07 | Exposure classes INSIDE / ABOVE_LAYER (with escape check) / BELOW / NEAR / CLEAR on `alt_baro`, 2,000 ft margins. |
| D6 | Most ash decisions are made before departure; ADS-B shows only airborne aircraft. Airborne holding depends on ATC. | MINOR | 07 | Frame the airborne view as EASA "enhanced flight watch"; HYPOTHESIS allows MONITOR, HOLD (request), or a crew/ATC request, never a reroute. |
| D7 | Fuel in kg cannot be derived from ADS-B. | MINOR | 07 | Show minutes and track miles; any fuel figure is a labelled rule-of-thumb. |
| D8 | An unbounded union of hedges causes alarm fatigue and contradicts "not overly conservative". | MINOR | 07 | Cap and itemise every margin. |
| D9 | No NOTAM/ASHTAM input, yet the decisive Jakarta actions were NOTAM closures. | MINOR | 01, 07 | Add "destination/alternate closed" as a manual or replay input; say NOTAMs are out of scope otherwise. |
| D10 | MAGMA prints feet with a ×3.2 factor (13,363 ft printed = 13,701 ft from 4,176 m). | MINOR (build) | 13, 14 | Parse metres, convert in code. |

## (e) News that weakens or changes the hook

| # | Conflict | Severity | Evidence | What changes |
|---|---|---|---|---|
| E1 | ICAO quantitative volcanic ash (QVA) becomes due from all VAACs on 26 Nov 2026, eight days before the finale; London/Toulouse since late 2025; Tokyo reportedly only after an early-2028 system update. | MINOR | 01, 03, 15 | Treat any QVA as one more official floor; it is a dated hook, not a threat. |
| E2 | Tokyo VAAC took over Darwin's area north of 20°S on 23 Sep 2026 (reason unpublished). | MINOR | 01, 13 | Handle VAAC handovers; the JMA backup list detects them. |
| E3 | The 2010 cost line: "EUR 1.3 bn" is IATA's US$1.7 bn converted (confirmed after a first-pass reversal); Oxford Economics gives US$2.2 bn net worldwide. | MINOR | 02 | Quote IATA US$1.7 bn with source. |
| E4 | Globot's "real feeds" contrast is wrong: Globot ran on a "High-Fidelity Mock" with a static Maps tile, Aegis on seeded incidents. Judges rewarded them anyway. | MINOR | 04, 08, 16 | Live feeds are a differentiator, but do not sell them against the winners. |

## (f) Gemini capability

| # | Conflict | Severity | Evidence | What changes |
|---|---|---|---|---|
| F1 | No Gemini call has ever been made on TEPHRA inputs; no personal key exists. Gen AI is 40 points. | SERIOUS | 00, 10 | Get a personal AI Studio key; run the 10-case protocol in `10-…md` from the Tokyo VAAC labelled archive (68 advisories with frames since 10 Sep). |
| F2 | Benchmarks: weak localisation (EarthSpatialBench), colour confusion (ClimateIQA), weak cross-image matching (BLINK). | SERIOUS for the image step | 10 | Categorical image outputs only; geometry in code. |
| F3 | `thinking_level: minimal` errors on 3.8 Flash; temperature 1.0 recommended, so outputs vary run to run. | MINOR | 10 | Validators and repeated runs in evals. |

## (g) Time and team

| # | Conflict | Severity | Evidence | What changes |
|---|---|---|---|---|
| G1 | Akash's last written position (7 Oct) was "DO NOT START TEPHRA" unless a two-hour plume test is unambiguous; there is no record of a joint decision on 10 Oct. | SERIOUS | 00 | Agree the narrowed version together (this file + `docs/DECISION-MEMO.md`). |
| G2 | Eight days left; the full spec was 22–26 developer-days. The code is now written but has never run. | SERIOUS | 00, this repo | First run + fix loop is the critical path; feature freeze 15 Oct. |
| G3 | The "100k users" bar from the explainer does not fit a dispatcher tool; the explainer transcript itself is unverified. | SERIOUS (pitch) | 08 | Reframe as passengers protected per event (341,000 in the Sept 2026 Krakatau event) plus the measured disagreement rate. |

---

## What still supports the idea

- **The job is written into guidance.** ICAO Doc 9974 §2.4(d): the operator must be able "to reliably and correctly resolve any conflicts that may arise among data sources" (verified by two checks, file 03). EASA GM3 ORO.GEN.200(a)(3) asks operators to find aircraft in flight that could be affected, alert crews, re-plan and resolve conflicts (07, 15). Mulder et al. 2017 found operations staff under time pressure "only ever increase their no-fly zones" (15), which is practitioner support for never-shrink.
- **A measured, real disagreement exists.** In the 30 days to 9 Oct, **28 of Semeru's 92 observatory ash reports had ash heading where the official ash area did not reach 10 km from the vent** (31/119 pooled); in those cases no single product is "the cautious one" and the cautious area is the union (14). It survived Akash's tests: 23–27 Sep, 20 VONAs said N/NE while every SIGMET said MOV SE, simultaneously (13).
- **The lag is structural and measurable.** A Darwin VAA reflecting a new Semeru VONA came a median 228 min later (p90 463) (14).
- **Fresh, big hook.** Anak Krakatau closed Soekarno-Hatta and seven other airports on 6–8 Sep 2026: ~2,961 flights and ~341,000 passengers affected, the airport's first full closure; the observatory's only VONA during it said "Ash-cloud is not observed" while BMKG issued 39 SIGMETs with ash to 50,000 ft (01).
- **Live state is near-certain on both judging days.** Every one of 119 six-hourly snapshots over 30 days had ≥3 VA SIGMETs open in APAC FIRs; P(≥1 open in Tokyo/Darwin areas at a random moment) ≈ 97–99% (09).
- **The text spine is keyless and public domain.** AWC SIGMET JSON and NWS tgftp VAA text (05).
- **No product found does the specific step:** an LLM reconciling contradictory official ash sources with a never-shrink floor and evidence-graded actions (03, 04, 16).

## Net position

TEPHRA is still worth building, **in its narrowed form**: an evidence-reconciliation and drafting desk, not a detector, not a map and not an "AI dispatcher".

- **Keep:** the SIGMET + VAA (tgftp) spine; deterministic discrepancy classes (LAG / ENVELOPE / NON_OBSERVATION / DIRECTION_OUTSIDE / HEIGHT_ABOVE / SILENCE / NO_POLYGON); the cautious union that never shrinks; Gemini reading remarks and VONA prose to grade evidence and write the explanation; 3D exposure on real ADS-B; per-flight drafts behind the dispatcher gate; the audit trail; a labelled replay of 23–27 Sep Semeru; the measured "28 of 92" claim.
- **Demote to optional context:** raw split-window BTD (an independent witness that may only widen), rendered satellite frames.
- **Drop:** reroutes with waypoints, OpenSky, BoM scraping, the JMA "Darwin mirror", MAGMA polling by default, Search grounding, fuel in kg as a fact.
- **Never claim:** that Gemini (or TEPHRA) detects or sees ash; that TEPHRA is first to do per-flight AI ash advisories with human approval; that its output is a forecast, a warning or a dispatch release; that dispatchers are "struggling" (unverified); that "the VAAC was silent" is a pattern (1–2 cases in 30 days).
