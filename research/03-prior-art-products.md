# TEPHRA prior art: commercial and operational products

Lens: `prior-art-products`. Written 2026-10-10 by a research agent. Scope: commercial, operational and agency products that already do part of TEPHRA, plus 2025-2026 LLM/GenAI products in airline dispatch and operations control.

Method: I opened vendor and agency pages myself with WebFetch and curl wherever they loaded. Several sites (icao.int, flightradar24.com, support.tomorrow.io, collinsaerospace.com) returned Cloudflare/403 pages; claims from those sites are tagged REPORTED from search-result text. The session's shared web-search budget ran out after 35 of my searches (3 further queries were refused), so a few named targets (Garuda, Air New Zealand, Indra, Vaisala, EUMETSAT's own ash-RGB guide, current Mitiga aviation offering) got one search or none; they are marked as such. Hackathon and GitHub prior art belongs to another lens and is only referenced from the prior-work pack, untested here.

Tag key: [CONFIRMED: url, accessed 2026-10-10] = I opened the page and it says that. [CONFIRMED-X2: url] = I opened it, and two adversarial verifiers (source-check and recency) both reopened it on 2026-10-10 and found the claim holds. [X2-FOUND: url] = new evidence a verifier opened on 2026-10-10; I did not reopen it. [REPORTED: url] = a secondary source or a search-result summary says it; I could not open the primary. [UNVERIFIED] = not checked. "[verified 2026-10-10: ...]" notes record a correction made after the second check. The full verdict list is in "Verification log (2026-10-10)" at the end.

---

## 1. Bottom line

- No product I found uses an LLM to reconcile contradictory official volcanic-ash sources (VONA vs VAA vs SIGMET vs satellite) into one hazard area that shows its disagreements, stamps provenance per source, and can never shrink below the official polygon. That step is open. [Based on the product pages listed in section 3; absence claim, so tag: not found after 35 searches and ~45 page fetches. The 2026-10-10 second check found no counter-example, but its search budget also ran out.]
- Every other TEPHRA step has a commercial or official occupant:
  - Feed ingestion and polygon display are commodity.
  - Projecting flights into a hazard and alerting the dispatcher is sold by The Weather Company, Lido, DTN and Weathernews. For ash specifically, EUROCONTROL's EVITA already calculates which flights are hit by QVA ash concentration or danger areas and assists re-routing, in Europe (missed by this file before the second check; section 4.8, conflict 12).
  - A company-own ash hazard area made by meteorologists is sold by The Weather Company and Weathernews. The Weather Company also issues customer-specific ash SIGMETs when ash is "detected near customer destinations".
  - AI ash detection on satellite imagery is sold by Weathernews and run by NOAA (VOLCAT).
  - "Generative AI recommends a diversion, the OCC dispatcher approves it" is a Jeppesen product pattern: Stratosphere/Elrey in beta since Oct 2025, and the first Airflow agents launched 6 Oct 2026. Tomorrow.io sells an agentic OCC platform (Gale/Altitude) whose support docs list a volcanic-ash alert premium layer.
- The prior-work pack missed the Jeppesen pattern. It is the most important new finding. It is not FATAL, because Jeppesen's published examples are turbulence/wind SIGMETs and crew disruption, with no ash and no source reconciliation. It does mean TEPHRA cannot claim novelty for "AI drafts a per-flight advisory behind a human approval gate". The novelty claim has to sit on the ash-specific evidence layer.
- Regulators support the open step. ICAO Doc 9974 says the operator must be able "to reliably and correctly resolve any conflicts that may arise among data sources" [CONFIRMED-X2: https://www.copac.es/wp-content/uploads/2021/09/ICAO-Guidance-on-Flight-Operations-and-Volcanic-Ash.pdf (Doc 9974, 1st ed. 2012)]. That makes TEPHRA's core step a named regulatory task, not an invented one. Check whether ICAO has issued a later edition before quoting section numbers in the deck.
- Verdict: GO, with a reframed claim (section 8). Nothing found is FATAL. After the 2026-10-10 second check, five findings are SERIOUS: Jeppesen Stratosphere/Airflow, The Weather Company ash SIGMETs + FPGs + WXAlert, Weathernews ACOS + AI detection (for the image claim), EUROCONTROL EVITA (new), and Tomorrow.io Gale/Altitude with an ash layer (raised from MINOR). All five are about what TEPHRA may claim as new, not about whether it can be built or shown. The novelty must rest on multi-source contradiction handling, per-source provenance, the never-shrink floor and evidence-graded actions, not on per-flight ash alerting.

---

## 2. TEPHRA steps used for grading

| # | TEPHRA step | Short name |
|---|---|---|
| S1 | Poll live public feeds (VA SIGMET, MAGMA VONA, Tokyo/Darwin VAA, Himawari Band-13/Dust-RGB, winds, TAF, ADS-B) | Ingest |
| S2 | Gemini reconciles contradictory sources into one cone with confidence, provenance and listed disagreements; code forbids shrinking below the official polygon | Reconcile |
| S3 | Code projects live aircraft into the cone and finds who enters and when | Intersect |
| S4 | Gemini explains each exposed flight and drafts continue/hold/reroute/divert with minutes and fuel | Draft advisory |
| S5 | Duty dispatcher approves/edits/rejects on a phone; HYPOTHESIS cones allow only hold/monitor | Human gate |
| S6 | Log with feed timestamps and source hashes | Audit log |
| S7 | (Support only) Gemini reads ash in satellite imagery | Image read |

Overlap grades: **core step** = the product does one of S2-S5 for real users. **adjacent** = it does S1, S6 or S7, or a core step for a different hazard. **none** = no material overlap found.

---

## 3. Comparison table

"Reconciles?" means it merges contradictory sources into one hazard area. "Per-flight advisory?" means it drafts a per-flight action. "Human gate?" means an explicit approval step before action. "LLM?" means a generative or language model is stated.

| Product | Vendor | URL | What it does (short) | Reconciles? | Per-flight advisory? | Human gate? | LLM? | Overlap | Evidence |
|---|---|---|---|---|---|---|---|---|---|
| Stratosphere / Elrey (Fleet Insight) | Jeppesen (now Jeppesen ForeFlight) | news.jeppesen.com/aviator-articles/putting-flight-disruption-back-in-its-place-introducing-stratosphere/ | Agents register a SIGMET (severe turbulence at HKG), predict a hold, recommend a diversion with alternate flight plans and fuel; dispatcher approves; then it files the flight-plan change and schedules refuelling itself | No (single SIGMET in example) | Yes (diversion recommendation) | Yes ("reviews and approves") | Yes ("Powered by generative AI") | **core step** (S4, S5) | CONFIRMED-X2 |
| Airflow platform and agents (Augmented Ops Control etc.) | Jeppesen ForeFlight | ai.jeppesenforeflight.com | Aviation AI engine; L1-L4 autonomy, L2 = "AI proposes a specific action. A human approves.", L3/L4 on/off the loop; visible why-trail; limited beta 2026; first agents (crew and aircraft disruption, no weather) 6 Oct 2026, broader rollout 2027 | No | Recommends and ranks options; disruption focus | Yes (L2) | Model-agnostic; LLM not named | **core step** (S5, S6 pattern) | CONFIRMED-X2 |
| Enroute Hazards package, enhanced VA SIGMETs, VA Flight Plan Guidance, HOTL reports (listed as separate services) | The Weather Company | weathercompany.com/blog/volcanic-ash-and-aviation-safety-protecting-planes-passengers/ | Meteorologist-issued ash alerts, incl. customer-specific ash SIGMETs when ash is near customer destinations; GFS-based ash dispersion; ash track displays; daily airport ash impact reports; PDF reports | Yes, by human meteorologists | Per customer destination, not per flight | Human-made product | No AI/LLM step stated for ash | **core step** (S2, human version) | CONFIRMED (PARTLY on second check; corrected) |
| Maverick WXAlert | The Weather Company | weathercompany.com/aviation/maverick-wxalert/ | Auto-alerts dispatcher and pilots when a flight is projected to intersect an en-route hazard; proprietary Enroute Hazard SIGMETs and FPGs; diversion guidance via ACARS. Turbulence-centric page; ash not named, but its FPG feed includes ash FPGs, so per-flight ash alerts are plausible | Proprietary SIGMETs "redefined, and verified" by meteorologists | Diversion guidance, not drafted per flight | No approval step described | Not stated | **core step** (S3) | CONFIRMED-X2 |
| Maverick Dispatch (Smart NOTAMs) | The Weather Company | weathercompany.com/aviation/maverick-dispatch/ | Dispatch platform; "AI-driven summaries group and rank NOTAMs" | No | No | n/a | AI summaries (model not named) | adjacent | CONFIRMED |
| Fusion | The Weather Company | weathercompany.com/aviation/ | Manage-by-exception flight tracking and alerting for dispatchers | No | No | n/a | Not stated | adjacent (S3) | CONFIRMED |
| ACOS ash dispersion + AI volcanic ash detection | Weathernews Inc. | global.weathernews.com/news/16070/ | AI detects ash through cloud gaps on satellite imagery (Himawari-8 IR in example) and feeds proprietary dispersion forecasts to airlines, mainly Japan and SE Asia, since 26 Apr 2021 | Partly (own forecast from satellite, VAAC, cameras) | No | n/a | No (image AI) | **core step** (S2 own-product) and adjacent (S7) | CONFIRMED-X2 |
| Automated Enroute Risk Notification / route overlay | Weathernews Inc. | wxtech.weathernews.com/en/industries/airline/ | Risk Notification lists aircraft passing near a severe-turbulence PIREP (co-developed with JAL), uplinks via ACARS (turbulence only). A separate Enroute Optimization Support Service overlays proprietary forecasts and SIGMETs on routes, sells ash dispersion forecasts and simulates route changes | No | Notification, not advisory | Not stated | No | **core step** (S3, turbulence) | CONFIRMED-X2 |
| Flight Plan Editor | Weathernews Inc. | wxtech.weathernews.com/en/products/sky/flightplan-editor/ | Visualise turbulence and ash dispersion along routes; edit routes; export ATC plans | No | No | n/a | No | adjacent | CONFIRMED |
| Volcanic Ash Advisory data (GeoJSON) | Weathernews Inc. | wxtech.weathernews.com/en/products/data/services/volcanic-eruption/ | VAAC advisories as GeoJSON with original bulletin text | No | No | n/a | No | adjacent (S1) | CONFIRMED |
| Lido Flight 4D (NHM, IFS, WINDS) | Lufthansa Systems | lhsystems.com/product-brands/lido/lido-flight-4d | Flight planning that accounts for volcanic ash; IFS monitors flights, resolves some issues autonomously and raises exception alerts to dispatchers for the rest; WINDS is a legacy module that IFS replaces | No | No (exceptions, not drafts) | Dispatcher handles exceptions only | Not stated | **core step** (S3) | CONFIRMED (PARTLY on second check; corrected) |
| Lido Weather / mPilot / pilot apps | Lufthansa Systems | lhsystems.com/solutions/pilot-applications | VAA and SIGMET polygons on the enroute map; ash alerts for pilots | No | No | n/a | No | adjacent (S1) | CONFIRMED |
| Lido NOTAM-AI Extractor | Lufthansa Systems | lhsystems.com/blog-entry/how-ai-transforming-aviation-data-lido-notam-ai-extractor-accelerates-flight-planning | AI NOTAM relevance/extraction, "Human-Verified Accuracy" | No | No | Human verification | "AI" (type not stated) | adjacent | CONFIRMED (title level) |
| NetLine/Ops ++ aiOCC | Lufthansa Systems | lhsystems.com/solutions/ai-other-services/netlineops-aiocc | Reinforcement-learning delay-risk recommendations for ops control | No | Ops recommendations, not weather | Not stated | No (RL) | adjacent | CONFIRMED |
| Command+ (successor to N-Flight Planning, N-Ops&Crew, N-Tracking) | Airbus Skywise (ex-NAVBLUE) | skywise.com/en/digital-solutions/planning-operations-control/command-for-ops-control-centres | OCC workspace consolidating alerts; manage-by-exception | No | No | n/a | Not stated | adjacent (S3) | CONFIRMED |
| N-Tracking volcano info and ash forecast | NAVBLUE (Airbus) | n-tracking.support.navblue.aero/... (now redirects) | Support article titled "View Volcano Information and the Related Ash Forecast" | Unknown | Unknown | Unknown | Unknown | adjacent | REPORTED |
| Flight Route Alerting | DTN | dtn.com/weather/aviation/airlines/flight-route-alerting/ | Patented 4D alerting on flight plans and up to 25 airports; layers include volcanic ash and SIGMETs | No | No | n/a | Not stated | **core step** (S3) | CONFIRMED-X2 |
| FLIGHTKEYS 5D | Flightkeys | flightkeys.com | Flight management system; weather-hazard consideration | Not found | Not found | Not found | Not found | adjacent | REPORTED |
| eWAS | SITA | apps.apple.com/us/app/-/id1068135642 | EFB weather app; layers include Volcanic Ash and SIGMET; airline can choose weather providers | No | No | n/a | No | adjacent (S1) | CONFIRMED |
| GoDirect Weather / Weather Information Service | Honeywell | aerospace.honeywell.com/.../weather-information-service | Pilot/dispatcher weather; 2018 release says helps detect volcanic ash | No | No | n/a | No | adjacent (S1) | REPORTED |
| Altitude + Gale | Tomorrow.io | tomorrow.io/blog/tomorrow-io-launches-altitude-the-aviation-weather-intelligence-platform/ | "Agentic aviation resilience platform"; deployed across Lufthansa's network; route exposure; Alternate Routing Assistant; Diversion Assessment Tool; decision logging; MCP server; support docs list "SIGMETs and Volcanic Ash Alerts" and "Volcanic Ash" premium layers | No (own models) | Alternates and diversion tools | Not stated | Agentic AI (LLM vendor REPORTED as Azure OpenAI) | **core step** (S4 pattern for weather; ash alerts on the same platform) — raised from adjacent | CONFIRMED-X2 (posts, PARTLY: 800 figure corrected); REPORTED (ash layer, LLM vendor) |
| Volcanic Ash Map + Console/API/Fleet Monitor | FlySafe.zone | flysafe.zone/tools/volcanic-ash-map/ | Colour codes incl. PVMBG/MAGMA, VAAC advisories, thermal anomalies, ADS-B counts; "Airline OCC / dispatch" Fleet Monitor with per-FIR risk and webhooks from $99/mo; "Not operational guidance" | No (lists sources side by side) | No (FIR level) | No | Not mentioned | adjacent (live, cheap, ash-focused dispatch competitor) | CONFIRMED |
| VOLCAT / Volcanic Cloud Monitoring | NOAA / CIMSS | volcano.ssec.wisc.edu | Automated satellite detection and alerts (incl. Himawari); email/text alerts | No | No | n/a | No ("algorithms") | adjacent (S7) | CONFIRMED |
| Quantitative Volcanic Ash (QVA) | UK Met Office (VAAC London) + Météo-France | metoffice.gov.uk/.../clearing-the-air-... | Gridded ash concentration and exceedance-probability forecasts: Met Office from 27 Nov 2025 (free), Toulouse from 15 Dec 2025; Annex 3 recommends all VAACs from 26 Nov 2026; Tokyo not before early 2028 | Official product, not reconciliation | No | n/a | No | adjacent (input that becomes the floor) | CONFIRMED (PARTLY on second check; corrected) |
| EVITA (European crisis visualisation tool) | EUROCONTROL | Joint QVA Task Force timeline PDF (assets.ctfassets.net/.../Joint_QVA_Task_Force_-_QVA_Implementation_Timeline.pdf) | Ingests QVA from VAAC London and Toulouse; calculates which flights are "impacted by either ash concentration data or danger areas, or areas locally defined by aircraft operators"; takes AIREPs; assists re-routings around ash | No (displays official and operator-defined areas) | Flight impact and re-routing, ATFCM level, not a dispatch advisory | n/a | No | **core step** (S3 for ash, Europe) | X2-FOUND |
| Mitiga Solutions (ICE4ATM, SORT-ATM) | Mitiga Solutions | mitigasolutions.com | Homepage now sells climate-risk intelligence (EarthScan); no aviation or volcano mention on homepage | n/a | Historic SORT-ATM notified affected flights (2018, REPORTED) | n/a | n/a | adjacent (historic) | CONFIRMED (homepage); REPORTED (ash products) |
| Himawari Ash RGB | JMA MSC | jma.go.jp/jma/jma-eng/satellite/VLab/QG/RGB_QG_Ash_en.pdf | RGB recipe for ash/SO2 detection | No | No | n/a | No | adjacent (S7 input) | CONFIRMED |
| Premium Weather Layers | FlightAware (data by DTN) | blog.flightaware.com/flightaware-global-premium-weather | Map layer incl. volcanic ash for Global customers | No | No | n/a | No | adjacent (S1) | CONFIRMED |
| Weather layers (volcanic ash) | Flightradar24 | flightradar24.com/blog/... | VAAC advisory text behind volcano icons, refreshed hourly | No | No | n/a | No | adjacent (S1) | REPORTED |
| International SIGMETs | ForeFlight | blog.foreflight.com/2015/11/11/international-sigmets/ | International SIGMET polygons incl. ash since v7.4 | No | No | n/a | No | adjacent (S1) | REPORTED |
| Garmin Pilot | Garmin | apps.apple.com/app/garmin-pilot/id340917615 | Store listing has no volcanic-ash mention | No | No | n/a | No | none found | CONFIRMED (absence on page) |
| Navearth | AirNav Indonesia | airnavindonesia.co.id (links app-pia.airnavindonesia.co.id/navearth/) | Real-time digital flight map integrating NOTAM, ASHTAM and aviation met | No | No | n/a | No | adjacent (S1) | CONFIRMED |
| Tokyo VAAC site | JMA | data.jma.go.jp/vaac/data/index.html | VAA texts, map, Darwin backup | Official issuer | No | n/a | No | adjacent (S1 source) | CONFIRMED |
| Darwin VAAC site | Bureau of Meteorology | bom.gov.au/aviation/volcanic-ash/ | VAA, VA SIGMET, graphics, registered-user products | Official issuer | No | n/a | No | adjacent (S1 source) | CONFIRMED |
| AVIOBOOK | Thales | aviobook.aero | EFB suite; homepage has no ash mention | No | No | n/a | No | none found | CONFIRMED (absence on homepage) |
| Frequentis | Frequentis | frequentis.com | Homepage has no ash mention | No | No | n/a | No | none found | CONFIRMED (absence on homepage) |
| Collins Aerospace / ARINC | Collins | collinsaerospace.com | Page blocked (403); no ash product found | n/a | n/a | n/a | n/a | none found | UNVERIFIED |
| Indra; Vaisala | Indra; Vaisala | n/a | No ash product found after 1 search each | n/a | n/a | n/a | n/a | none found | UNVERIFIED |

---

## 4. Product notes

### 4.1 Jeppesen / Jeppesen ForeFlight: the LLM dispatch-agent incumbent (missed by the pack)

- Stratosphere is "Powered by generative AI" and "enhances airline operations with real-time insights and recommendations". The front end, Elrey, is in beta "embedded within Jeppesen Fleet Insight". The article is dated 21 Oct 2025. It also says Stratosphere "will soon be available across all Jeppesen products". [CONFIRMED-X2: https://news.jeppesen.com/aviator-articles/putting-flight-disruption-back-in-its-place-introducing-stratosphere/]
- Its worked example matches TEPHRA's flow for a different hazard:
  - "Stratosphere's weather agent automatically detects a wind-pattern shift and registers the SIGMET". The SIGMET is for severe turbulence at HKG.
  - An agent then recommends diverting to Macau and "prepares alternate flight plans, estimates fuel and ground handling needs".
  - "A human-in-the-loop (OCC dispatcher or operations manager) reviews and approves the recommended diversion."
  - Once approved, Stratosphere itself "files the flight-plan change" and schedules refuelling. The incumbent pattern is "dispatcher approves, system acts", which goes further than TEPHRA's drafted advisory.
  - No volcanic ash anywhere on the page.
  - [CONFIRMED-X2: same URL]
- Elrey was announced 29 Jul 2025 as a chatbot for "dispatchers, flight followers and operations teams". The article does not use the words "LLM" or "generative". [CONFIRMED: https://news.jeppesen.com/aviator-articles/your-new-ai-assistant-for-smarter-flight-operations/, accessed 2026-10-10]
- Airflow is "the aviation AI engine powering agents, products, and decisions across your operation". [CONFIRMED-X2: https://ai.jeppesenforeflight.com/]
  - Autonomy tiers: "L2 Approve Human in the Loop AI proposes a specific action. A human approves." Elsewhere: "L2 · Human in the loop: AI proposes, human approves, AI acts." It also offers L3 (human on the loop) and L4 (autonomous) under a "patent-pending AI-Safety Management System".
  - Provenance: "Every decision carries a visible why-trail: the inputs that triggered it, the alternatives it considered, the outcomes it expects". [verified 2026-10-10: the two verifiers quote this line differently, "Every decision" (source-check) and "Every recommendation" (recency); the page may use both. Quote it in the deck as "a visible why-trail" only.]
  - Status: "Limited beta is open".
  - Its agent plane lists "Flight following, disruption management, cockpit situational awareness".
  - The page does not mention volcanic ash or SIGMETs; weather appears only as an input ("ORD weather: TS active +2hr").
- Airflow's pitch against generic LLMs: "Generic AI is confident, fluid, and often wrong." It says the AI is grounded in "deterministic engines". [CONFIRMED: https://ai.jeppesenforeflight.com/, accessed 2026-10-10]
- AvWeb, 6 Oct 2026 (headline "Jeppesen ForeFlight Expands AI Into Airline Operations"): Jeppesen ForeFlight "unveiled the first artificial intelligence agents" for Airflow.
  - Agents: "Trip Trading, Target Mastery, and Augmented Ops Control".
  - Design: they "are designed to provide recommendations and reasoning to human operators, not make independent decisions".
  - Rollout: "a broader rollout expected early next year", after a co-development phase. The GlobeNewswire release and AIN (both 6 Oct 2026, seen as search summaries by a verifier) agree on 2027. Airflow itself was introduced as Jeppesen's agentic AI strategy in July 2026.
  - Scope: Augmented Ops Control "evaluates possible responses when aircraft or crew disruptions occur" (fatigue, reserve coverage, cost, crew connections). None of the three agents covers weather hazards, SIGMETs or ash.
  - ForeFlight's ClearNOTAMs (July) generates "plain-language summaries of coded NOTAMs".
  - [CONFIRMED-X2: https://avweb.com/aviation-news/foreflight-brings-ai-to-airline-operations/]
- Timeline read: no Jeppesen ash agent or ash advisory product was found by either verifier. The incumbent's agent roadmap does not yet cover hazard reconciliation, but it could by 2027.
- Jeppesen ForeFlight is independent of Boeing after a US$10.55 billion sale to Thoma Bravo. [REPORTED: https://avitrader.com/2025/11/06/jeppesen-foreflight-takes-off-as-independent-digital-aviation-firm/]
- FliteDeck Pro: I found no source confirming an ash layer (not found after 1 search: "Jeppesen FliteDeck Pro volcanic ash weather overlay").
- Grade: **core step** for S4 and S5 as a pattern, and beyond S5 (the system acts after approval; L3/L4 tiers exist). No ash, no multi-source reconciliation.

### 4.2 The Weather Company: the human-meteorologist version of S2 + S3

- The Nov 2024 ash blog (dated 11 Nov 2024) by "Eric Bott, Meteorologist in Charge | Aviation Forecasting" describes four services [CONFIRMED: https://www.weathercompany.com/blog/volcanic-ash-and-aviation-safety-protecting-planes-passengers/, accessed 2026-10-10; PARTLY on second check, corrected below]:
  - "the Enroute Hazards package";
  - "enhanced volcanic ash SIGMET (Significant Meteorological Information) notifications";
  - "Volcanic Ash forecast Flight Plan Guidance (FPGs) display where volcanic ash is expected to track over a period of time";
  - "Human-Over-the-Loop (HOTL) Reports" (PDFs).
  - [verified 2026-10-10: the blog does not say the FPGs and HOTL Reports belong to the Enroute Hazards package. It lists them as separate Weather Company services next to that package and next to the enhanced ash SIGMETs.]
- The same post says forecasters use "third-party webcams to visually monitor volcanic activity in real time", run GFS-based ash dispersion modelling, and send daily airport ash impact reports. The ash SIGMETs are tailored per customer: "SIGMETs are also issued for added safety if ash is detected near customer destinations, even if it doesn't meet these thresholds". That is close to per-customer ash alerting, though not per flight. [CONFIRMED-X2: https://www.weathercompany.com/blog/volcanic-ash-and-aviation-safety-protecting-planes-passengers/]
- [verified 2026-10-10: the blog itself names no AI and no per-flight advisory, but that is true of this one post only. As a vendor, TWC sells en-route volcanic-ash alerts (aviation page), an "AI-Powered" dispatch platform (Maverick Dispatch) and flight-projected hazard alerts (WXAlert) fed by the same proprietary SIGMET/FPG layer. Say "TWC does not state an AI or LLM step in its ash products"; do not say TWC lacks AI or per-flight alerting.]
- Maverick WXAlert [CONFIRMED-X2: https://www.weathercompany.com/aviation/maverick-wxalert/]:
  - It will "Automatically alert the dispatcher and pilots simultaneously when the flight is projected to intersect an en-route weather hazard".
  - Its hazards include "Enroute Hazard SIGMETS (proprietary) and Flight Plan Guidance (FPGs) ... monitored, redefined, and verified continuously by expert aviation meteorologists 24/7 x 365".
  - It guides "pilots to optimal diversion alternatives". Alerts go "via ACARS".
  - The page names turbulence, crosswind and SIGMET hazards. It does not name volcanic ash.
  - The product sheet (c)2025 is titled "Strengthen tactical decision-making for all enroute hazards" and says "Alert messages are generated when a flight is projected to intersect an enroute hazard" from "forecaster issued SIGMETs/FPGs". [X2-FOUND: https://www.weathercompany.com/wp-content/uploads/2025/12/Maverick-WXAlert-FINAL.pdf]
  - [verified 2026-10-10: because TWC issues volcanic-ash FPGs, per-flight ash alerting through WXAlert is plausible even though neither page says "ash".] United renewed its WXAlert contract [X2-FOUND: airlinegeeks, 12 Mar 2026].
- The aviation landing page promises "precise en route alerts and guidance for turbulence, convective activity, icing, volcanic ash, and dust storms from our team of EWINS-certified, expert meteorologists". It describes Fusion as letting dispatchers "Manage fleet operations by exception". [CONFIRMED: https://www.weathercompany.com/aviation/, accessed 2026-10-10]
- Maverick Dispatch: "AI-driven summaries group and rank NOTAMs by operational impact". No ash or SIGMET text on that page. [CONFIRMED: https://www.weathercompany.com/aviation/maverick-dispatch/, accessed 2026-10-10]
- ITA Airways case study (Aircraft IT Operations, V15 Q2 2026): "AI-driven Smart NOTAM (NOTice to AirMen) summaries ... help dispatchers to filter critical information rapidly". [CONFIRMED: https://www.weathercompany.com/wp-content/uploads/2026/06/Aircraft-IT-Operations-ITA-The-Weather-Co-case-study.pdf, accessed 2026-10-10]
- Ownership: the lens brief calls this "IBM aviation". The current site footer reads "© Copyright The Weather Company LLC 2014, 2026" [CONFIRMED: https://www.weathercompany.com/aviation/, accessed 2026-10-10]. I did not verify the current owner [UNVERIFIED].
- Grade: **core step**. Human meteorologists already make a company-own ash hazard area (S2), customer-specific ash SIGMETs exist, and software already alerts dispatchers when a flight will intersect a hazard (S3), plausibly including ash. The difference from TEPHRA:
  - The human version shows no explicit per-source disagreement list.
  - It has no never-shrink rule visible to the user.
  - It drafts no per-flight continue/hold/reroute/divert text.

### 4.3 Weathernews Inc.: APAC ash specialist with AI imagery

- The press release is dated "Apr 26, 2021" and titled "Full-Scale Operation of AI Volcanic Ash Detection System for Aviation Market Begins". [CONFIRMED-X2: https://global.weathernews.com/news/16070/]
- Exact claims in that release [CONFIRMED-X2: same URL]:
  - It is "the first in the world to be capable of real-time image recognition of volcanic ash clouds from gaps in clouds using AI, using satellite images that overlook the entire earth".
  - It "uses modeling to distinguish subtle differences between clouds and volcanic ash clouds, such as shape and texture".
  - The system runs at the Weathernews Terrestrial Center and feeds "volcanic ash diffusion prediction methods employed by the Weathernews Terrestrial Center for airlines".
  - The figure caption shows "Himawari-8 infrared imagery" of Dukono on 5 Apr 2021, where the plume "cannot be observed in the infrared satellite image (left)" but the AI "captures volcanic ash cloud (right)".
  - ACOS "is offered mainly to airlines operating in Japan and Southeast Asia".
  - "Airlines make their flight decisions based on information released by public agencies, but this service can also be used as reference information".
  - A second world-first claim: "the first in the world that uses satellite imagery to detect eruptions and track volcanic ash cloud movements in real-time using AI". Live volcano cameras were to be added later.
  - No newer Weathernews ash-AI announcement was found by the second check (two searches).
- Correction to the pack: the pack says Weathernews "has sold AI ash detection on Himawari infrared to airlines since 2021". The release supports a narrower reading. The AI is used inside Weathernews' own forecasting centre to feed the ACOS ash-dispersion service sold to airlines. Himawari-8 IR is named only in the figure caption. [CONFIRMED: same URL, accessed 2026-10-10]
- Current airline page [CONFIRMED-X2: https://wxtech.weathernews.com/en/industries/airline/]:
  - Under a separate "Enroute Optimization Support Service", it offers "rapid and proprietary volcanic ash dispersion forecasts" covering "eruption source, ash plume trajectory, spatial extent, and estimated time of arrival".
  - The same service overlays "Weathernews' proprietary forecasts, SIGMETs and information from international agencies with the planned flight route" and can "simulate the operational impact of potential route changes".
  - The "Automated Enroute Risk Notification Service" ("We support flight dispatchers in early detection of risks") generates "a list of aircraft currently passing through or scheduled to pass near the reported area" after a severe-turbulence PIREP. It was "Co-developed with Japan Airlines Co., Ltd." and sends turbulence information "automatically ... via ACARS".
  - [verified 2026-10-10: the ash forecasts and SIGMET overlay belong to the Enroute Optimization Support Service; the automated risk notification covers turbulence only.] No AI/LLM text on the page.
- Flight Plan Editor lets users "visualize weather risks, turbulence forecasts, and volcanic ash dispersion along flight routes" and edit routes, "Supporting dispatchers and pilots". No AI is mentioned. [CONFIRMED: https://wxtech.weathernews.com/en/products/sky/flightplan-editor/, accessed 2026-10-10]
- The VAA data service delivers "The latest volcanic ash forecast data issued by the Volcanic Ash Advisory Centers (VAACs) worldwide" in GeoJSON with the original bulletin. [CONFIRMED: https://wxtech.weathernews.com/en/products/data/services/volcanic-eruption/, accessed 2026-10-10]
- I found no 2025-2026 Weathernews announcement of new ash features or LLM use (not found after 1 search: "Weathernews airline volcanic ash dispersion forecast service ACOS 2025 2026 airlines Asia").
- Grade: **core step** for S2 as its own-forecast product in TEPHRA's region. **Adjacent** for S7. S3 is covered for turbulence and not shown for ash.

### 4.4 Lufthansa Systems (Lido, NetLine)

- Lido Flight 4D's Natural Hazard Mitigation feature "ensures that potential environmental hazards, such as volcanic ash, turbulence, storms, and extreme low temperatures are accounted for". [CONFIRMED-X2: https://www.lhsystems.com/product-brands/lido/lido-flight-4d] The product text is undated and names no AI; the product sheet is "2026 v1".
- Lido Flight 4D IFS "continuously monitor[s] aeronautical factors that may impact flights". When "the system cannot resolve autonomously, users—such as dispatchers or mission support officers—are alerted through exception notifications". [CONFIRMED-X2: same URL] [verified 2026-10-10: IFS resolves some issues autonomously and alerts dispatchers only for exceptions it cannot resolve. The incumbent already runs monitoring with no person in the loop, a higher autonomy level than "alerts dispatchers" suggests.]
- WINDS is a legacy module: the page says IFS "replaces our legacy modules Lido Flight AOS, WINDS and IFM". WINDS "can generate alerts when disruptions or diversions impact designated flights or airports", but cite IFS, not WINDS, as the current product. [CONFIRMED: same URL, accessed 2026-10-10; PARTLY on second check, corrected]
- Lido Weather 2026 sheet: "Weather phenomena such as Convection (NowCast), Cloud Top Height, SIGMETs, Volcanic Ash Advisory, Tropical Cyclone Advisory, Turbulence, and Icing Forecasts are displayed on the enroute map as polygons". [CONFIRMED: https://cdn.lhsystems.com/2026-01/Lido%20Weather%20Product%20Sheet%202026%20.pdf, accessed 2026-10-10]
- The pilot-applications page: Lido Weather provides "critical alerts such as SIGMETs and volcanic ash advisories". [CONFIRMED: https://www.lhsystems.com/solutions/pilot-applications, accessed 2026-10-10]
- Lido NOTAM-AI Extractor (blog, 11 Dec 2025) promises "Human-Verified Accuracy". The page body did not load, so the AI type is unknown. [CONFIRMED (title/alt text only): https://www.lhsystems.com/blog-entry/how-ai-transforming-aviation-data-lido-notam-ai-extractor-accelerates-flight-planning, accessed 2026-10-10]
- NetLine/Ops ++ aiOCC "translates information from multiple sources into actionable recommendations". "Using Reinforcement Learning, it is the first in the industry to provide meaningful recommendations". No weather or ash. [CONFIRMED: https://www.lhsystems.com/solutions/ai-other-services/netlineops-aiocc, accessed 2026-10-10]
- Lufthansa Systems began offering Google Cloud through its Global Aviation Cloud in Aug 2024 [REPORTED: https://www.onboardhospitality.com/lufthansa-systems-partners-with-google-cloud/]. The 2023 GAC article I opened does not mention Google [CONFIRMED: https://www.lhsystems.com/article/global-aviation-cloud-gac-lufthansa-systems, accessed 2026-10-10].
- The Lufthansa Group's Google Cloud work I could open is a 2022 Vertex AI wind-forecast experiment for the "Operations Decision Support Suite". The production plan was stated as future. Not an LLM. [CONFIRMED: https://cloud.google.com/blog/products/ai-machine-learning/how-lufthansa-reduce-flight-delays-with-google-cloud-ml, accessed 2026-10-10]
- Not checked: Lufthansa Systems' "zeroG – AI in Aviation" offering, linked from the Lido navigation. Check it for any LLM dispatch or hazard product before the deck is final [UNVERIFIED].
- Grade: **core step** for S3 (IFS exception alerts on monitored flights, ash in planning). **Adjacent** otherwise.

### 4.5 Airbus Skywise (ex-NAVBLUE)

- navblue.aero now returns HTTP 301 to skywise.com. [CONFIRMED: curl of https://www.navblue.aero/, accessed 2026-10-10]
- Command+ "represents the next-generation evolution of our existing solutions such as N-Flight Planning, N-Ops&Crew and N-Tracking". It consolidates "alerts from flight operations, crew scheduling, maintenance and airspace systems". It offers a "Manage-by-Exception dashboard" for "the flights requiring review or intervention". No ash or AI on the page. [CONFIRMED: https://www.skywise.com/en/digital-solutions/planning-operations-control/command-for-ops-control-centres, accessed 2026-10-10]
- A NAVBLUE N-Tracking support article is titled "View Volcano Information and the Related Ash Forecast". The URL now redirects to skywise.com, so I could not read it. [REPORTED: https://n-tracking.support.navblue.aero/support/solutions/articles/35000193366-view-volcano-information-and-the-related-ash-forecast]
- Grade: adjacent.

### 4.6 DTN, Flightkeys, SITA, Honeywell

- DTN Flight Route Alerting "is a comprehensive, 4D alerting engine" covering "flight planning, pre-flight briefing, flight following, and in-flight updates". "The flight plan — and up to 25 airports and destination alternates — are continually monitored". Its data list includes "SIGMETs ... volcanic ash, and more". It is "patented" and offers "simultaneous, real-time evaluation of multiple flight plans". No AI/LLM mention. [CONFIRMED-X2: https://www.dtn.com/weather/aviation/airlines/flight-route-alerting/] Grade: **core step** (S3).
- Flightkeys homepage text has no ash mention [CONFIRMED: https://flightkeys.com/index.html, accessed 2026-10-10]. Its features include "consideration of weather hazards" [REPORTED: https://flightkeys.com/index.html (search summary)]. Flightkeys was the flight-planning partner in Google's 2025 contrail trial with American Airlines, where dispatchers chose avoidance routes voluntarily [REPORTED: https://www.barchart.com/story/news/846965/american-airlines-and-google-say-ai-helped-airplanes-reduce-contrails-that-trap-heat]. Grade: adjacent.
- SITA eWAS (App Store, "SITA eWAS for iPhone"): "eWAS offers the following weather data: ... Volcanic Ash · Lightning · SIGMET". It "allows to define an airline policy with various options including the selections of various weather providers". [CONFIRMED: https://apps.apple.com/us/app/-/id1068135642, accessed 2026-10-10] Grade: adjacent.
- Honeywell: a 2018 release says GoDirect Weather helps customers "detect and navigate lightning, turbulence, cloud tops, and volcanic ash" [REPORTED: https://www.honeywell.com/us/en/press/2018/05/honeywell-expands-godirect-flight-with-new-connected-service-offerings-for-pilots-dispatchers]. The WIS product page I curled has no ash text in its static HTML [CONFIRMED: https://aerospace.honeywell.com/us/en/products-and-services/product/services/flight-services/weather-information-service, accessed 2026-10-10]. Grade: adjacent.

### 4.7 Tomorrow.io: agentic weather AI in airline OCCs

- A 26 Mar 2026 post (headline "Lufthansa Deploys Tomorrow.io's Altitude") describes Altitude as an "agentic aviation resilience platform enabled by Gale, Tomorrow.io's artificial intelligence engine", deployed across Lufthansa's network. It offers rule-based alerts and route exposure. The post does not mention ash or SIGMETs. [CONFIRMED-X2: https://www.tomorrow.io/blog/tomorrow-io-launches-altitude-the-aviation-weather-intelligence-platform/] [verified 2026-10-10: "nearly 800 flights a day" is the size of Lufthansa's operation ("Lufthansa operates nearly 800 flights a day across one of the most complex route networks"), not a count of flights Altitude monitors. The post is a deployment story, not a launch announcement.]
- Feb 2026 update: "Alternate Routing Assistant: Evaluate weather impacts on alternate routes directly from Gale or the map". "Diversion Assessment Tool: Identify alternate airports within a defined radius and fuel range". "Built for: Airlines, OCCs, and drone operators". The post also mentions SIGMET polygons via a "Weather Events API", but not ash. [CONFIRMED-X2: https://www.tomorrow.io/blog/february-product-update/]
- Gale can "log operational decisions with point-in-time weather context" and "stand up monitors from guided prompts". A "3D route view exposes altitude-specific risk so dispatch and pilots coordinate on safer profiles". [CONFIRMED: https://www.tomorrow.io/blog/operate-safer-and-faster-with-agentic-weather-ai-route-intelligence-and-unified-dashboards/, accessed 2026-10-10]
- Spring 2026 update (28 Apr 2026): a native MCP server, and Altitude "monitoring every active flight — with route, altitude, and crew context attached". [CONFIRMED: https://www.tomorrow.io/blog/tomorrow-io-spring-2026-product-update/, accessed 2026-10-10]
- Two further reports, not opened:
  - A "SIGMETs and Volcanic Ash Alerts (Aviation, Premium Layer)" exists for aviation customers. It covers Washington, London and Toulouse VAACs per its documentation, which would leave out Tokyo and Darwin. [REPORTED: https://support.tomorrow.io/hc/en-us/articles/36154937966356-SIGMETs-and-Volcanic-Ash-Alerts-Aviation-Customers (403 to me)] A verifier also saw a separate support article titled "Volcanic Ash (Aviation, Premium Layer)" in search results; both returned 403 to fetch. The VAAC-coverage limit stays unverified by second check.
  - Gale "integrates Microsoft AI Foundry & Azure OpenAI". [REPORTED: search summary of a Tomorrow.io press release; primary not opened]
- Grade: **core step** for S4 as a weather pattern (raised from adjacent on 2026-10-10). An agentic LLM platform in a major airline's OCC that already carries ash alerts, alternate routing and diversion tools is the closest commercial path to TEPHRA's S4. It does not show ash reconciliation, per-source disagreement or a floor. "Tomorrow.io has no ash capability" would be false.

### 4.8 Ash-specific public tools: FlySafe.zone, VOLCAT, QVA, Mitiga, satellite RGBs

- FlySafe.zone Volcanic Ash Map (snapshot built 09 Oct 2026 18:25 UTC) [CONFIRMED: https://www.flysafe.zone/tools/volcanic-ash-map/, accessed 2026-10-10]:
  - It plots observatory colour codes including "PVMBG (MAGMA)", VAAC advisories, MODIS/VIIRS thermal anomalies, and ADS-B traffic counts.
  - "Stand-down notices are dropped".
  - It calls itself "Reference visualisation of published volcanic ash advisories. Not operational guidance."
- FlySafe homepage [CONFIRMED: https://www.flysafe.zone/, accessed 2026-10-10]:
  - It sells "Airline OCC / dispatch" a "Fleet Monitor · early-warning FIR risk + webhooks".
  - It offers "Per-FIR risk + webhook into your dispatch dashboard".
  - The Console is "$99/mo". The site is run by Digital Power FZE LLC.
  - The homepage text has no AI mention.
  - Grade: adjacent (FIR level, not per flight, no reconciliation, no LLM). Cite it in the deck as live, cheap, ash-focused dispatch competition.
- NOAA/CIMSS Volcanic Cloud Monitoring portal: "near real-time processing of many geostationary and low-earth orbit satellites" including "HIMAWARI". It is a "BETA website" for "informational purposes only". [CONFIRMED: https://volcano.ssec.wisc.edu/, accessed 2026-10-10]
- VOLCAT alerts are "often the first indication that an eruption has begun". Users include VAACs, observatories and "aviation interests". Article dated 2017; "still in an experimental phase". [CONFIRMED: https://www.nesdis.noaa.gov/news/airlines-observatories-and-others-keep-tabs-volcanic-activity-volcat, accessed 2026-10-10] Grade: adjacent (S7).
- Met Office QVA [CONFIRMED: https://www.metoffice.gov.uk/about-us/news-and-media/media-centre/corporate-news/2025/clearing-the-air-new-met-office-service-to-cut-aviation-disruption-from-volcanic-ash, accessed 2026-10-10; PARTLY on second check, corrected]:
  - The Met Office release, written before launch, says the service "launches on 27 November 2025" "in tandem with Meteo France (VAAC Toulouse)".
  - [verified 2026-10-10: Météo-France's Toulouse QVA service is documented as running "since 15/12/2025" [X2-FOUND: https://assets.ctfassets.net/krj50g99u3hm/56ZjQ3Omw7OpcUMpfpFll8/6057af9b554a9de8c5698dc06e55c34b/Joint_QVA_Task_Force_-_QVA_Implementation_Timeline.pdf], and VAAC Toulouse issued QVA "under operational conditions" for the Hayli Gubbi eruption on 23 Nov 2025 (ICAO APAC IP03). "Free" is stated only for the Met Office service, not for Météo-France.]
  - "The seven other VAACs will follow one year later", i.e. about 27 Nov 2026.
  - It is "available free to all airlines and the aviation industry worldwide" (Met Office service).
  - It gives "gridded forecasts ... for 12 horizontal slices of the atmosphere" plus "probability forecasts which indicate the likelihood that certain ash concentrations will be exceeded".
  - "At lower concentrations flights may operate through ash (if certified by their engine manufacturer, and if authorised by their CAA)".
- QVA regulatory status [X2-FOUND: https://assets.ctfassets.net/krj50g99u3hm/56ZjQ3Omw7OpcUMpfpFll8/6057af9b554a9de8c5698dc06e55c34b/Joint_QVA_Task_Force_-_QVA_Implementation_Timeline.pdf (Joint QVA Task Force, "QVA Implementation Timeline", April 2026)]:
  - Annex 3 (Amendment 82) makes all-VAAC QVA a Recommended Practice, not a Standard: "as of 26 November 2026 all VAACs should issue forecasts of QVA". That is 8 days before the 4 Dec 2026 finale.
  - Operational use in Europe waits for an updated EUR/NAT VACP ("Nov 26 : More realistic VACP approval date"; "earliest beginning of 2027"). EUROCONTROL keeps the legacy VA concentration charts meanwhile. Operators in Europe are therefore reconciling legacy and new official products right now.
  - QVA supplements, and does not replace, the deterministic VAA/VAG, so deterministic advisories continue everywhere.
  - ops.group (12 Jan 2026) says only that more VAACs are "expected to join over the following year". [X2-FOUND]
- QVA status in APAC [CONFIRMED by the source-check verifier, who opened https://www.icao.int/sites/default/files/APAC/Meetings/2026/2026%20MET%20SG-30/4.%20Information%20Papers/IP03_AI5_AUS-JPN-NZL-USA_COMBINED-APAC-VAAC-MANAGEMENT-REPORT.pdf in a browser and extracted the text with pdf.js; the recency verifier got a Cloudflare 403, so one-verifier only]:
  - ICAO APAC MET SG/30 IP/03 (Bangkok, 20-24 July 2026), 2.6: "VAAC Tokyo has initiated a major update of its information dissemination system, with completion scheduled for early 2028. QVA service provision will commence following the update."
  - 2.4: "VAAC Darwin is moving the Dispersion Ensemble Prediction System (DEPS) interface into the forecasting software Visual Weather. This will improve the workflow for QVA ... the VAAC will be able to test the feature soon before it becomes operational."
  - [verified 2026-10-10: the paper gives no QVA start date for Darwin, Wellington, Washington or Anchorage, and never calls APAC advisories "contradictory". Only Tokyo is documented as late (not before early 2028). Darwin's QVA workflow was in pre-operational testing as of July 2026. Darwin or Wellington may issue QVA by the finale; treat any QVA that appears as an authoritative floor input.]
  - The same paper reports a heavy 2026 APAC ash workload: Philippines VAAs average "around five ... per day" based on VONA reports; VAAC Wellington issued 84% of its 2025 VAA total in the first five months of 2026, mostly for Ambae; Sheveluch reached FL480 on 3 Apr 2026.
- EUROCONTROL EVITA (missed by this file until the second check) [X2-FOUND: https://assets.ctfassets.net/krj50g99u3hm/56ZjQ3Omw7OpcUMpfpFll8/6057af9b554a9de8c5698dc06e55c34b/Joint_QVA_Task_Force_-_QVA_Implementation_Timeline.pdf]:
  - EVITA, EUROCONTROL's crisis visualisation tool, already ingests QVA from VAAC London and Toulouse.
  - It lets users "calculate if they are impacted by either ash concentration data or danger areas, or areas locally defined by aircraft operators".
  - It can "Facilitate input of AIREPs" and "Assist with re-routings, avoiding areas that are affected by ash."
  - This is an official, ash-specific flight-impact and intersection tool that also accepts operator-defined hazard areas. It is European ATFCM, with no LLM, no VONA/VAA/SIGMET reconciliation, no APAC coverage and no per-flight dispatch advisory.
  - Grade: **core step** (S3 for ash, Europe); adjacent for S2 (it displays, but does not reconcile, official and operator areas).
- QVA grade: adjacent. QVA is an official input that, where issued, becomes part of TEPHRA's floor. It is not a competitor, but a judge may compare TEPHRA's hedged cone with official probabilistic ash products that are already live in Europe.
- Mitiga Solutions:
  - Its homepage now sells "Science-Based Climate Risk Intelligence" via EarthScan. The homepage has no "volcan", "aviation" or "airline" strings. [CONFIRMED: https://www.mitigasolutions.com/, accessed 2026-10-10]
  - Its 2018 SORT-ATM software was described as notifying airlines "24-48 hours in advance about the section of the flight route that will be affected ... and which scheduled flights may proceed without risk". [REPORTED: https://bsc.es/node/51283]
  - ICE4ATM was an EU project. [REPORTED: https://cordis.europa.eu/project/id/874346]
  - The current ash offering is unknown [UNVERIFIED].
  - Grade: adjacent (historic per-flight notification concept).
- JMA Himawari Ash RGB Quick Guide limitations: "Inability to estimate volcanic plume height and concentration from Ash RGB data alone", "Difficulty of identifying very thin or lower-level volcanic plumes", "Disturbance from high-level clouds over volcanic plumes". [CONFIRMED: https://www.jma.go.jp/jma/jma-eng/satellite/VLab/QG/RGB_QG_Ash_en.pdf, accessed 2026-10-10]
- I did not find EUMETSAT's own ash-RGB guide (not found after 1 search: "EUMETSAT volcanic ash RGB product Himawari ash RGB JMA user guide"). JMA's guide covers the same channel physics.

### 4.9 Consumer and EFB maps

- FlightAware Global "Premium Weather Layers Provided by DTN" include volcanic ash; "All Global account tiers give you access". Post dated 1 Nov 2020. [CONFIRMED: https://blog.flightaware.com/flightaware-global-premium-weather, accessed 2026-10-10]
- Flightradar24: users "active the Volcanic ash layer under Settings >> Weather, then click on a volcano icon". Advisories are refreshed hourly. [REPORTED: https://www.flightradar24.com/blog/inside-flightradar24/welcoming-weather-to-flightradar24/ (403 to me)]
- ForeFlight Mobile 7.4 displays international SIGMETs including ash. If a SIGMET lacks bounds, "the entire FIR may be outlined in red". [REPORTED: https://blog.foreflight.com/2015/11/11/international-sigmets/ (URL now redirects to a resource centre)]
- Garmin Pilot store listing: no volcanic-ash mention. [CONFIRMED: https://apps.apple.com/app/garmin-pilot/id340917615, accessed 2026-10-10]
- Grade: adjacent at most. These make S1 display commodity.

### 4.10 ATM vendors

- Thales AVIOBOOK homepage and Frequentis homepage: no ash mention. [CONFIRMED: https://www.aviobook.aero/ and https://www.frequentis.com/, accessed 2026-10-10]
- Collins Aerospace returned 403. No Collins/ARINC ash product found after 1 search ("Collins Aerospace ARINC volcanic ash flight operations weather service airlines").
- Indra: none found after 1 search ("Thales OR Frequentis OR Indra volcanic ash air traffic management tool ANSP").
- Grade: none found.

### 4.11 APAC official agencies: the existing reconciliation of record

- VAAC Darwin's letter of 26 Feb 2018 (Dr Adele Crozier, VAAC Darwin Manager) on MAGMA says "Ground reports (Volcano Observatory Notices to Aviation) hosted on the site are now received in real time (a first for VAAC Darwin) leading to faster forecasting of volcanic ash cloud movement". It calls MAGMA "greatly needed situational awareness" for "the VAAC and airline operators in the region". Signed by the VAAC Darwin Manager. [CONFIRMED-X2: https://publicadministration.un.org/unpsa/Portals/0/UNPSA_Submitted_Docs/2018/4E384934-AAB8-4FE4-888A-7CE9231FCDF7/VAAC_Darwin_MAGMA_Letter.pdf?ver=2018-02-26-044107-637]
- Fresher evidence that VAACs turn VONAs into advisories: in the Philippines "around five Volcanic Ash Advisories (VAAs) are issued per day based on ... VONA reports" (ICAO APAC MET SG/30 IP/03, July 2026; one-verifier, via browser). The MAGMA VONA page (https://magma.esdm.go.id/v1/vona) returned HTTP 200 on 2026-10-10 with a live VONA list, "disseminated via email to national and international stakeholders in the aviation sector". [X2-FOUND]
- BoM Darwin VAAC page [CONFIRMED: https://www.bom.gov.au/aviation/volcanic-ash/, accessed 2026-10-10]:
  - It lists "Australian VA SIGMET", "Darwin VA Advisories", "Darwin Graphical VA Advisories" and "VA Registered Users".
  - "By entering this site, you acknowledge that this information is produced solely for use by the aviation industry, and you are aware that any information for the purposes of flight planning should be obtained from Airservices Australia."
- Tokyo VAAC home, "Updated at 19:00 UTC, 09 October 2026": "There is no currently announced volcanic ash Advisories." It hosts a "Darwin VAAC Backup". [CONFIRMED: https://www.data.jma.go.jp/vaac/data/index.html, accessed 2026-10-10]
- AirNav Indonesia's homepage advertises Navearth: "Aplikasi peta penerbangan digital secara real time ... yang terintegrasi dengan NOTAM (Notice to Airmen), ASHTAM (Volcanic Ash), dan meteorologi penerbangan". In English: a real-time digital flight map integrated with NOTAM, ASHTAM and aviation meteorology. [CONFIRMED: https://airnavindonesia.co.id/, accessed 2026-10-10]
- AirNav issues ASHTAMs "through the International NOTAM Office AirNav Indonesia". It uses "Himawari-8 satellite images", "monitoring cameras (webcams)" and PVMBG data. Article dated 20 Nov 2025. [CONFIRMED: https://en.tempo.co/read/2067292/no-airport-disruption-following-mount-semerus-eruption-says-airnav-indonesia, accessed 2026-10-10]
- Grade: adjacent. These agencies already merge VONA, satellite and webcam into official products. TEPHRA consumes their products and must not look like it replaces them. (That conclusion is ours; the 2018 letter only describes real-time VONA receipt.)

### 4.12 LLM / GenAI in airline operations, 2025-2026 (non-ash)

- Air France-KLM, July 2025: building a "generative AI factory" with Accenture and Google Cloud. It reports results in ground ops, engineering/maintenance and customer service. [REPORTED: https://newsroom.accenture.com/news/2025/accenture-and-google-cloud-support-air-france-klm-in-building-a-generative-ai-factory-to-revolutionize-operations]
- Ryanair, 12 Aug 2026: "Gemini Enterprise will be used to help automate decision-making, optimise flight crew logistics". It plans to use "Google DeepMind models, including AlphaEvolve and WeatherNext". No operations-control or ash use stated. [CONFIRMED: https://www.googlecloudpresscorner.com/2026-08-12-Ryanair-and-Google-Cloud-Announce-Five-Year-Data-and-AI-Partnership, accessed 2026-10-10]
- ANA, 16 Oct 2025: "neoAI Chat" generative AI platform for "airport, maintenance, cabin and flight operations". It "cuts manual and regulation search time by approximately 90%". No dispatch decision support. [CONFIRMED: https://www.anahd.co.jp/group/en/pr/202510/20251016-2.html, accessed 2026-10-10]
- Singapore Airlines, 18 Aug 2026 article: more than 160 AI applications. For crew scheduling, "AI models would be integrated with existing scheduling tools to support decisions". No ops-control weather use. [CONFIRMED: https://techwireasia.com/2026/08/singapore-airlines-ai-applications/, accessed 2026-10-10]
- Cathay Pacific, 9 Sep 2026: trialled Google's contrail forecasts. Dispatchers and pilots make "informed altitude adjustments", and forecasts reach pilots through Cathay's Electronic Flight Folder. "More than 100 flights" were targeted. [CONFIRMED: https://www.greenairnews.com/?p=9505, accessed 2026-10-10]
- Cathay's BCG/KLM tools (Pathfinder, Sentry) are ML optimisers. No GenAI or weather is stated. [CONFIRMED: https://www.bcg.com/x/mark-your-moment/transforming-airline-operations-with-ai, accessed 2026-10-10]
- Qantas, Jan 2026: plans to "embrace AI in 2026". No dispatch GenAI found. [REPORTED: https://australianaviation.com.au/2026/01/qantas-to-embrace-ai-in-2026-says-hudson/]
- JAL: Phi-4 small language model for cabin-crew reports. [REPORTED: https://news.microsoft.com/source/asia/features/japan-airlines-new-ai-app-will-make-it-easier-for-cabin-attendants-to-report-inflight-events-with-microsofts-phi-4-small-language-model/]
- Research: the "Pre-Flight" benchmark (arXiv 2607.01829, 2 Jul 2026) found the best 2026 model at "82.7%" on 300 aviation-operations questions, against an informal expert reference of about 95%. [CONFIRMED: https://arxiv.org/abs/2607.01829, accessed 2026-10-10]
- CHATATC (2024) is an LLM conversational agent for strategic traffic flow management, as research. [REPORTED: https://arxiv.org/pdf/2402.14850]
- Not searched (budget exhausted): Garuda, Air New Zealand, NASA ATM-X by name, Eurocontrol AI programmes. One combined search ("NASA ATM-X OR EUROCONTROL large language model air traffic flow management assistant 2026") found no deployed LLM assistant.

### 4.13 Airline ash practice (public)

- Qantas, 7 Jul 2025: "Our meteorologists and operations teams are closely monitoring the movement of volcanic ash". Virgin Australia: "our team of expert meteorologists are closely monitoring the situation and ash cloud activity". [CONFIRMED: https://www.abc.net.au/news/2025-07-07/indonesia-mount-lewotobi-laki-laki-erupts-again-cancels-flights/105503740, accessed 2026-10-10]
- Lufthansa and Singapore Airlines: no public ash-dispatch procedure found after 1 search each ("Lufthansa volcanic ash policy risk assessment operations control ash concentration"; "Singapore Airlines Scoot volcanic ash Anak Krakatau September 2026 cancellations statement").
- Regulator text that frames the dispatcher's job:
  - ICAO Doc 9974 §2.4(d): the operator "should have satisfied its CAA regarding the likely accuracy and quality of the information sources it uses in its SMS and its own competence and capability to interpret such data correctly in order to reliably and correctly resolve any conflicts that may arise among data sources". [CONFIRMED-X2: https://www.copac.es/wp-content/uploads/2021/09/ICAO-Guidance-on-Flight-Operations-and-Volcanic-Ash.pdf (9-page extract of Doc 9974, 1st ed. 2012, mirrored by COPAC)] [verified 2026-10-10: cite as Doc 9974 1st Edition (2012). The extract starts on page 2-2 at item (c); one verifier could not see the "2.4" heading, the other's pdftotext places item d) under 2.4. Whether ICAO has issued a later edition is unconfirmed, so check before quoting section numbers in the deck.]
  - Doc 9974 §2.5(b): procedures should cover "flight crew, flight planners, dispatchers, operations, engineering and maintenance personnel such that they are equipped to evaluate correctly the risk of flights encountering airspace contaminated by volcanic clouds". [CONFIRMED-X2: same URL]
  - EASA SIB 2010-17R7 (24 Jun 2015): states "recognise that operators will make their own decisions to operate or not into areas of forecast ash contamination, based on their VA SRA". [CONFIRMED: https://ad.easa.europa.eu/blob/EASA_SIB_2010_17_R7_CORR.pdf/SIB_2010-17R7_1, accessed 2026-10-10]

---

## 5. Step-by-step occupancy

| TEPHRA step | Status | Who occupies it | Evidence |
|---|---|---|---|
| S1 Ingest feeds | **Commodity** | Lido Weather, SITA eWAS, DTN, FlightAware, Flightradar24, ForeFlight, FlySafe, Weathernews GeoJSON, AirNav Navearth | Sections 4.4, 4.6, 4.8, 4.9, 4.11 |
| S2 Reconcile into one hazard area | **Occupied by humans/models; LLM version with disagreement list and never-shrink floor is open** | TWC proprietary Enroute Hazard SIGMETs, customer-specific ash SIGMETs, ash FPGs and HOTL (meteorologists); Weathernews ACOS (own dispersion with AI detection); VAACs and AirNav themselves (official reconciliation); EVITA displays operator-defined areas next to QVA (no reconciliation) | 4.2, 4.3, 4.8, 4.11 |
| S3 Intersect flights with hazard | **Occupied (core step)** | TWC WXAlert ("projected to intersect", ash plausible via ash FPGs), Lido IFS (partly autonomous; WINDS is legacy), DTN Flight Route Alerting (ash in data list), Weathernews affected-aircraft list (turbulence), Skywise Command+, **EUROCONTROL EVITA (ash-specific, QVA, Europe)**; hackathons per pack (AeroGuard/MeteoWatch) [UNVERIFIED here] | 4.2, 4.4, 4.6, 4.3, 4.5, 4.8 |
| S4 Draft per-flight advisory | **Occupied as a pattern (beta), open for ash** | Jeppesen Stratosphere (GenAI diversion recommendation with fuel and alternate plans); Airflow Augmented Ops Control (crew/aircraft disruption, rollout 2027); Tomorrow.io Gale/Altitude Alternate Routing Assistant / Diversion Assessment Tool on a platform with a reported ash alert layer | 4.1, 4.7 |
| S5 Human approval gate | **Occupied as a pattern** | Jeppesen Stratosphere ("reviews and approves", then the system files the change itself), Airflow L2 ("AI proposes ... A human approves") plus L3/L4; Lido IFS escalates only the exceptions it cannot resolve. Evidence-graded action limits (HYPOTHESIS → hold/monitor only) not seen anywhere | 4.1, 4.4 |
| S6 Audit log with provenance | **Occupied as a concept** | Airflow "why-trail"; Gale "log operational decisions with point-in-time weather context"; FlySafe "dated, referenced records". Feed hashes not seen | 4.1, 4.7, 4.8 |
| S7 Read ash in imagery | **Occupied** | Weathernews AI detection (since 2021), NOAA VOLCAT | 4.3, 4.8 |

---

## 6. Conflicts with our idea

Severities re-graded after the 2026-10-10 second check. Changes: conflict 8 raised MINOR → SERIOUS; conflict 12 is new (SERIOUS); conflict 13 is new (MINOR); conflicts 1, 2 and 5 widened in scope with the grade unchanged.

1. **Jeppesen Stratosphere / Airflow occupy "GenAI drafts a per-flight action, dispatcher approves" — SERIOUS (unchanged; scope wider).**
   - Jeppesen published a SIGMET → diversion recommendation with fuel and alternate plans → "A human-in-the-loop (OCC dispatcher or operations manager) reviews and approves". It did so on 21 Oct 2025 (beta), and the first Airflow agents launched 6 Oct 2026. [CONFIRMED-X2: https://news.jeppesen.com/aviator-articles/putting-flight-disruption-back-in-its-place-introducing-stratosphere/ and https://avweb.com/aviation-news/foreflight-brings-ai-to-airline-operations/]
   - The incumbent goes further than TEPHRA: after approval Stratosphere "files the flight-plan change" and schedules refuelling, it "will soon be available across all Jeppesen products", and Airflow offers L3 (human on the loop) and L4 (autonomous) tiers.
   - A judge who follows aviation tech will see TEPHRA's S4-S6 as Jeppesen's pattern.
   - What must change:
     - Drop any claim to be the first AI dispatch co-pilot or the first human-gated advisory.
     - Name Jeppesen in the deck as the general pattern.
     - Claim only the ash-specific layer Jeppesen does not show: contradictory official sources, a hedged cone with a code-enforced floor, and evidence-grade-limited actions.
     - Present TEPHRA's draft-only, never-sends design as a deliberate choice for an evidence-poor hazard, not as a gap.
   - Not FATAL. Stratosphere is beta and enterprise-only. Its published example is a turbulence SIGMET at HKG; the 6 Oct 2026 agents cover crew and aircraft disruption, not weather or ash; broader rollout is 2027. No Jeppesen ash agent was found by either verifier. The window is real but could close in 2027.

2. **The Weather Company already sells meteorologist-made ash hazard areas, customer-specific ash alerts and automatic flight-intersection alerts — SERIOUS (unchanged; scope wider).**
   - Services (listed separately, not all inside the "Enroute Hazards package"): "enhanced volcanic ash SIGMET ... notifications", issued even below thresholds "if ash is detected near customer destinations"; "Volcanic Ash forecast Flight Plan Guidance"; GFS-based ash dispersion; daily airport ash impact reports; "HOTL" reports. [CONFIRMED-X2 with correction: https://www.weathercompany.com/blog/volcanic-ash-and-aviation-safety-protecting-planes-passengers/]
   - WXAlert will "Automatically alert the dispatcher and pilots simultaneously when the flight is projected to intersect an en-route weather hazard", from forecaster-issued SIGMETs/FPGs that include ash FPGs. Per-flight ash alerting is therefore plausible even though the page never says "ash". [CONFIRMED-X2: https://www.weathercompany.com/aviation/maverick-wxalert/]
   - The aviation page sells "en route alerts and guidance for ... volcanic ash", and Maverick Dispatch is marketed as AI-powered. [CONFIRMED: https://www.weathercompany.com/aviation/, accessed 2026-10-10]
   - So "a company-own ash area that is not just the VAAC polygon, wired to per-customer and probably per-flight alerts" is a paid product, minus any stated LLM.
   - What must change: position TEPHRA's S2 as an auditable, source-by-source version for operators without a 24/7 meteorologist contract. The provenance and disagreement display are the visible difference. Do not claim nobody gives dispatchers a reconciled ash area or per-flight ash alerts. Do not say TWC lacks AI; say it states no AI or LLM step in its ash products.

3. **Weathernews already sells AI-assisted ash detection and proprietary ash forecasts to Japanese and SE Asian airlines — SERIOUS for the image claim, MINOR for the idea (unchanged).**
   - Confirmed from the 26 Apr 2021 release and the current airline page. [CONFIRMED-X2: https://global.weathernews.com/news/16070/ and https://wxtech.weathernews.com/en/industries/airline/]
   - Its affected-aircraft notification, co-developed with JAL, is the S3 pattern for turbulence only in Japan; the ash forecasts and SIGMET route overlay sit in a separate Enroute Optimization Support Service.
   - What must change: the pack's existing fix stands (image is support only). Also avoid the phrases "first to detect ash with AI" and "first to track ash in real time with AI"; Weathernews claims both world firsts.

4. **Flight-hazard intersection alerting is a commodity product feature — MINOR (unchanged).**
   - Sold by TWC WXAlert, Lido IFS, DTN Flight Route Alerting and Weathernews; done for ash in Europe by EUROCONTROL EVITA (conflict 12). Lido IFS already resolves some issues with no person involved and escalates only exceptions; WINDS is a legacy module. [CONFIRMED-X2: section 4 URLs]
   - What must change: spend under 10 seconds of the video on intersection. Treat it as plumbing.

5. **QVA rollout can make the "official product is a hard polygon" premise look dated at the finale — MINOR (unchanged grade; wider scope, premise narrowed to Tokyo).**
   - Met Office QVA launched 27 Nov 2025; Toulouse's service dates from 15 Dec 2025 and issued QVA operationally for Hayli Gubbi on 23 Nov 2025. Annex 3 recommends that all VAACs issue QVA from 26 Nov 2026, 8 days before the 4 Dec 2026 finale. [CONFIRMED: Met Office URL; X2-FOUND: https://assets.ctfassets.net/krj50g99u3hm/56ZjQ3Omw7OpcUMpfpFll8/6057af9b554a9de8c5698dc06e55c34b/Joint_QVA_Task_Force_-_QVA_Implementation_Timeline.pdf]
   - Only Tokyo is documented as late: QVA "will commence following" a system update due early 2028 [one-verifier, via browser: ICAO APAC MET SG/30 IP03]. Darwin's QVA workflow was in pre-operational testing in July 2026; Darwin and Wellington may issue QVA before the finale.
   - A judge may compare TEPHRA's hedged cone with official probabilistic ash products already live in Europe.
   - What must change:
     - Do not claim that APAC as a whole stays deterministic through the finale. Claim it only for the Tokyo VAAC area.
     - List QVA as an optional input that, when present, becomes the authoritative floor.
     - Use the transition as a pitch point: QVA supplements the deterministic VAA/VAG, and Europe cannot use QVA operationally until the VACP update (earliest beginning of 2027), so operators are reconciling legacy and new products right now.

6. **The official system already reconciles VONA, satellite and webcam — MINOR (unchanged).**
   - VAAC Darwin receives MAGMA VONAs "in real time" [CONFIRMED-X2: UN PSA letter URL, 2018]. In the Philippines "around five" VAAs a day are issued from VONA reports (ICAO APAC IP03, July 2026) [one-verifier]. AirNav builds ASHTAMs from Himawari, webcams and PVMBG [CONFIRMED: https://en.tempo.co/read/2067292/..., accessed 2026-10-10].
   - TEPHRA's cone could read as second-guessing the VAAC.
   - What must change (our conclusion, not a source's):
     - Frame S2 as gap-filling between official updates (a VONA newer than the last VAA, a SIGMET with no VAA).
     - Say the cone can only add caution.
     - Cite ICAO Doc 9974 (1st ed. 2012) §2.4(d), which puts conflict resolution on the operator.

7. **The satellite-read science limits what Gemini may claim from an image — MINOR (unchanged).**
   - JMA: Ash RGB cannot estimate "plume height and concentration ... alone" and struggles with thin, low or cloud-covered plumes. [CONFIRMED: https://www.jma.go.jp/jma/jma-eng/satellite/VLab/QG/RGB_QG_Ash_en.pdf, accessed 2026-10-10]
   - What must change: never let the image set the top height. Heights come from VONA/VAA/SIGMET; the image only supports presence and drift direction.

8. **Agentic weather AI with an ash alert layer already runs in a major airline's OCC — SERIOUS (raised from MINOR on 2026-10-10).**
   - Tomorrow.io Altitude/Gale is deployed across Lufthansa's network, with alternate routing, diversion assessment, decision logging and an MCP server. [CONFIRMED-X2: Tomorrow.io URLs in 4.7]
   - Its support docs list "SIGMETs and Volcanic Ash Alerts (Aviation, Premium Layer)" and "Volcanic Ash (Aviation, Premium Layer)". [REPORTED: support.tomorrow.io titles seen in search results; 403 to fetch] The reported limit to Washington, London and Toulouse VAACs is unverified by second check.
   - This is the closest commercial path to TEPHRA's S4: an LLM agent that already sees ash alerts and can evaluate diversions. No ash reconciliation, per-source disagreement or floor is shown.
   - What must change: name Tomorrow.io next to Jeppesen in the deck. Never say Tomorrow.io has no ash capability. Differentiate on reconciliation of contradictory official sources, the floor and evidence-graded actions, and on APAC VAAC coverage only if the coverage limit is confirmed.

9. **FlySafe.zone already fuses MAGMA colour codes, VAAC advisories, thermal anomalies and ADS-B, and sells webhooks to dispatch — MINOR (unchanged).** [CONFIRMED: https://www.flysafe.zone/tools/volcanic-ash-map/ and https://www.flysafe.zone/, accessed 2026-10-10] Run by Digital Power FZE LLC; "Airline OCC / dispatch" Fleet Monitor with "early-warning FIR risk + webhooks", Console from $99/mo, labelled "Not operational guidance". It works at FIR level, does no per-flight cone and states no AI. What must change: do not present "we put MAGMA, VAAC and ADS-B on one map" as new; cite FlySafe as live, cheap, ash-focused competition.

10. **The BoM Darwin VAAC page carries a use condition — MINOR, for the data-licensing lens (unchanged).** "This information is produced solely for use by the aviation industry" and flight-planning information "should be obtained from Airservices Australia". [CONFIRMED: https://www.bom.gov.au/aviation/volcanic-ash/, accessed 2026-10-10] What must change: the licensing lens should check whether a public demo that re-displays Darwin VAA graphics is acceptable. Using the JMA-hosted Darwin text mirror may avoid the question [UNVERIFIED].

11. **Tokyo VAAC can be quiet — NONE for this lens, flagged for the live-data lens (unchanged).** At 19:00 UTC on 9 Oct 2026 the Tokyo VAAC home page showed no current advisories. [CONFIRMED: https://www.data.jma.go.jp/vaac/data/index.html, accessed 2026-10-10] The demo should lean on the Darwin region and SIGMETs. APAC workload is otherwise high in 2026 (Philippines ~5 VAAs/day, Wellington, Sheveluch to FL480), so a live case is likely somewhere in the region.

12. **EUROCONTROL EVITA already does ash-specific flight-impact calculation and re-routing support from QVA — SERIOUS (new on 2026-10-10; missed by this file and the pack).**
   - EVITA ingests QVA from VAAC London and Toulouse and lets users "calculate if they are impacted by either ash concentration data or danger areas, or areas locally defined by aircraft operators"; it can "Facilitate input of AIREPs" and "Assist with re-routings, avoiding areas that are affected by ash." [X2-FOUND: https://assets.ctfassets.net/krj50g99u3hm/56ZjQ3Omw7OpcUMpfpFll8/6057af9b554a9de8c5698dc06e55c34b/Joint_QVA_Task_Force_-_QVA_Implementation_Timeline.pdf]
   - That is an official, ash-specific S3 tool that also accepts operator-defined hazard areas. A European judge may know it.
   - What must change: name EVITA in the deck and differentiate. EVITA is European ATFCM, with no LLM, no VONA/VAA/SIGMET reconciliation, no APAC coverage and no per-flight dispatch advisory. Do not claim ash-specific flight-impact calculation as new.

13. **Lido IFS already monitors flights with no person in the loop and escalates only exceptions — MINOR (new on 2026-10-10).**
   - "If an issue arises that the system cannot resolve autonomously, users ... are alerted through exception notifications." [CONFIRMED-X2: https://www.lhsystems.com/product-brands/lido/lido-flight-4d]
   - What must change: do not present unattended monitoring plus dispatcher escalation as new. Lufthansa Systems' "zeroG – AI in Aviation" was not checked [UNVERIFIED]; check it before the deck is final.

No FATAL conflict found. No product found does LLM reconciliation of contradictory official ash texts with a never-shrink floor and evidence-graded action limits. Five conflicts are SERIOUS (1, 2, 3 for the image claim, 8, 12), all on what TEPHRA may claim as new.

---

## 7. What this supports

1. **The core step is a regulatory duty.** ICAO Doc 9974 requires the operator's "competence and capability to interpret such data correctly in order to reliably and correctly resolve any conflicts that may arise among data sources". It names "dispatchers" among the staff whose procedures must let them "evaluate correctly the risk". [CONFIRMED-X2: https://www.copac.es/wp-content/uploads/2021/09/ICAO-Guidance-on-Flight-Operations-and-Volcanic-Ash.pdf] This is the strongest citation found for the impact slide. Cite it as Doc 9974 1st Edition (2012) and check for a later edition first.
2. **The decision belongs to the operator.** EASA SIB 2010-17R7: "operators will make their own decisions to operate or not into areas of forecast ash contamination, based on their VA SRA". [CONFIRMED: https://ad.easa.europa.eu/blob/EASA_SIB_2010_17_R7_CORR.pdf/SIB_2010-17R7_1, accessed 2026-10-10] The BoM page also routes flight-disruption questions to "the relevant airline/s". [CONFIRMED: https://www.bom.gov.au/aviation/volcanic-ash/, accessed 2026-10-10]
3. **The open step is real.** Across about 30 products and programmes checked (table in section 3), none states that it uses an LLM to reconcile contradictory VONA/VAA/SIGMET/satellite inputs, shows the disagreements, or enforces a never-shrink floor. Absence claim: not found after 35 searches; queries in the search log. The second check added EVITA and Tomorrow.io's ash layer, and neither does this step.
4. **The market leader validates the human-gated pattern.** Jeppesen ForeFlight's L2 tier ("AI proposes a specific action. A human approves.") and its warning that generic LLMs are "confident, fluid, and often wrong" match TEPHRA's design choices: code-enforced floor, structured output, human gate. [CONFIRMED-X2: https://ai.jeppesenforeflight.com/] Its first agents (6 Oct 2026) cover crew and aircraft disruption, not weather hazards, with broader rollout in 2027; the incumbents' agent roadmaps do not yet cover hazard reconciliation. For a hackathon this is support. It shows the problem framing is what the industry is moving toward. TEPHRA's ash evidence layer is the part the incumbent does not show.
5. **Commercial ash products also present themselves as supplements to official data**, the same stance TEPHRA takes. Weathernews says airlines decide on public-agency information and its service "can also be used as reference information". [CONFIRMED-X2: https://global.weathernews.com/news/16070/] FlySafe says "Not operational guidance". [CONFIRMED: https://www.flysafe.zone/tools/volcanic-ash-map/, accessed 2026-10-10]
6. **Google AI already reaches dispatchers in APAC.** Cathay's dispatchers and pilots use Google contrail forecasts (Sep 2026). [CONFIRMED: https://www.greenairnews.com/?p=9505, accessed 2026-10-10] Ryanair adopted Gemini Enterprise to "help automate decision-making" (Aug 2026). [CONFIRMED: https://www.googlecloudpresscorner.com/2026-08-12-Ryanair-and-Google-Cloud-Announce-Five-Year-Data-and-AI-Partnership, accessed 2026-10-10] A Google Cloud judge will recognise Gemini-in-dispatch as plausible.
7. **The Tokyo VAAC area stays deterministic through the finale, and everyone is reconciling legacy and new products.** Tokyo's QVA will start only after an information-system update due early 2028 [one-verifier, via browser: ICAO APAC MET SG/30 IP03, 2.6]. [verified 2026-10-10: the earlier claim that all of APAC stays in a "deterministic, contradictory regime" was withdrawn. The paper gives no date for Darwin, Wellington, Washington or Anchorage and never says "contradictory"; Annex 3 recommends all VAACs issue QVA from 26 Nov 2026, so Darwin or Wellington may do so before 4 Dec 2026.] QVA supplements, and does not replace, the deterministic VAA/VAG everywhere, and Europe cannot use QVA operationally until the VACP update (earliest beginning of 2027) while EUROCONTROL keeps legacy charts. [X2-FOUND: https://assets.ctfassets.net/krj50g99u3hm/56ZjQ3Omw7OpcUMpfpFll8/6057af9b554a9de8c5698dc06e55c34b/Joint_QVA_Task_Force_-_QVA_Implementation_Timeline.pdf] That supports TEPHRA's pitch that operators are stuck reconciling several official products of different kinds.
8. **The VONA is a legitimate operational input.** VAAC Darwin calls real-time VONA receipt via MAGMA "a first for VAAC Darwin" and says it is "greatly needed situational awareness" for "airline operators in the region". [CONFIRMED-X2: UN PSA letter URL, 2018] In 2026 the Philippines issues "around five" VAAs a day from VONA reports (ICAO APAC IP03) [one-verifier].
9. **The intended user exists.** Qantas and Virgin Australia say in-house meteorologists and operations teams monitor ash. [CONFIRMED: https://www.abc.net.au/news/2025-07-07/indonesia-mount-lewotobi-laki-laki-erupts-again-cancels-flights/105503740, accessed 2026-10-10] That smaller APAC carriers lack such teams is [UNVERIFIED].
10. **Tokyo and Darwin coverage is not universal in Western ash-alert products.** Tomorrow.io's ash layer is reported to cover only Washington, London and Toulouse VAACs [REPORTED: support.tomorrow.io article] (unverified by second check). EVITA covers Europe only. This leaves room for an APAC-specific reconciliation story, but do not put the Tomorrow.io coverage limit in the deck until it is confirmed.
11. **Dispatch faces real ash advisory volume in APAC in 2026.** ICAO APAC MET SG/30 IP03 (July 2026): Philippines VAAs average "around five ... per day"; VAAC Wellington issued 84% of its 2025 VAA total in the first five months of 2026, mostly for Ambae; Sheveluch reached FL480 on 3 Apr 2026. [one-verifier, via browser: ICAO IP03 URL in Sources] Use this on the problem slide.

---

## 8. Verdict

**Commodity (do not claim, build fast or borrow):**
- S1 feed ingestion and polygon display (Lido, eWAS, DTN, FlightAware, FR24, ForeFlight, FlySafe, Weathernews, AirNav Navearth).
- S3 flight-hazard intersection alerting (TWC WXAlert, Lido IFS, DTN FRA, Weathernews; for ash in Europe, EUROCONTROL EVITA).
- NOTAM summarisation by AI (TWC Smart NOTAMs, ForeFlight ClearNOTAMs, Lido NOTAM-AI).

**Occupied by a product (acknowledge, do not claim as new):**
- A company-own ash hazard area produced by meteorologists and models (TWC enhanced ash SIGMETs, ash FPGs and HOTL; Weathernews ACOS), including customer-specific ash alerts (TWC).
- AI ash detection in satellite imagery (Weathernews since 2021; NOAA VOLCAT).
- "GenAI recommends a diversion with fuel and alternates; OCC dispatcher approves; why-trail kept" (Jeppesen Stratosphere beta 2025; Airflow agents 2026; Tomorrow.io Gale/Altitude diversion tools on a platform with an ash alert layer).
- Ash-specific flight-impact calculation and re-routing support from official QVA (EUROCONTROL EVITA, Europe).

**Open (TEPHRA's defensible claim):**
1. LLM reconciliation of contradictory official ash texts and images. Every disagreement is listed with its source and timestamp, and "VA NOT IDENTIFIABLE" and "EST VA CLD" cases are handled explicitly.
2. A code-enforced rule that the reconciled area can never be smaller than the newest official polygon.
3. Evidence-graded action limits: a HYPOTHESIS cone allows only hold/monitor; a full reroute/divert needs an official product.
4. An ash-specific per-flight advisory draft for APAC FIRs that cites which official source drove each action, from public feeds a judge can open. (Per-flight ash alerting alone is not open: TWC WXAlert plausibly does it.)

**Recommended wording for the deck:** "Jeppesen and Tomorrow.io already put AI recommendations in front of dispatchers, The Weather Company sells meteorologist-made ash alerts, and EUROCONTROL's EVITA shows European flows which flights hit ash. None of them shows the dispatcher why three official ash sources disagree. TEPHRA does that, never draws a smaller box than the official one, and limits what it may recommend by how good the evidence is."

**Overall overlap grade: PARTLY.** This agrees with the 2026-10-09 sweep, but the occupied share is larger than the sweep said: S4-S5 are occupied by Jeppesen (and Tomorrow.io as a weather pattern), and S3 by at least four vendors plus EVITA for ash in Europe. The remaining gap is narrower than the pack's "reconcile + per-flight advisory + phone approval". It is "reconcile contradictory sources with provenance + floor + evidence-graded actions, for ash, in APAC". The second check left this grade unchanged.

---

## 9. Corrections to the prior-work pack

- **Missed:** Jeppesen Stratosphere/Elrey (Oct 2025 beta) and Airflow agents (6 Oct 2026). These are the most relevant commercial overlap for S4-S6.
- **Missed:** TWC Maverick WXAlert ("projected to intersect" alerts) and TWC's proprietary meteorologist-verified Enroute Hazard SIGMETs. The pack listed TWC only as "adjacent".
- **Missed:** Weathernews Automated Enroute Risk Notification (affected-aircraft list, co-developed with JAL, ACARS uplink); Tomorrow.io Altitude/Gale at Lufthansa; DTN Flight Route Alerting with ash; AirNav Navearth.
- **Missed (by the pack and by this file's first pass; found in the 2026-10-10 second check):** EUROCONTROL EVITA, which computes flight impact from QVA ash and assists re-routing in Europe; TWC customer-specific ash SIGMETs; Tomorrow.io's volcanic-ash premium layers.
- **Corrected (second check):** QVA does not start for "the seven other VAACs" as a mandate; it is an Annex 3 Recommended Practice from 26 Nov 2026, Toulouse's service dates from 15 Dec 2025, and only Tokyo is documented as late. "APAC stays deterministic through the finale" holds only for the Tokyo VAAC area.
- **Corrected (second check):** Lido WINDS is a legacy module replaced by IFS; Tomorrow.io's "800 flights" is Lufthansa's daily operation, not Altitude's coverage.
- **Narrowed:** Weathernews' AI ash detection is used internally to feed the ACOS service; the AI is not itself sold. Himawari-8 IR is named only in a figure caption (section 4.3).
- **Updated:** NAVBLUE now redirects to Airbus Skywise; Command+ succeeds N-Flight Planning, N-Ops&Crew and N-Tracking.
- **Updated:** Mitiga Solutions' homepage now sells climate-risk intelligence (EarthScan) with no aviation/volcano text. Its ash-for-airlines status is unknown.
- **Confirmed:** Lido Flight 4D accounts for volcanic ash in planning (NHM); the pack's "Lido intersects official polygons" is supported via NHM and IFS alerts (WINDS is legacy). A Jeppesen FliteDeck ash overlay was not confirmed.
- **Added support:** ICAO Doc 9974 §2.4(d) conflict-resolution duty, which the pack did not cite.

---

## Open questions

1. Does Jeppesen Stratosphere/Airflow handle volcanic ash, or ingest VAAs or VONAs at all? No public page says so, and the second check found no Jeppesen ash product. A judge from Google Cloud may know Jeppesen's roadmap.
2. Does TWC's WXAlert "projected to intersect" logic include volcanic-ash SIGMETs and VA Flight Plan Guidance polygons? The page and product sheet name SIGMETs and FPGs generally ("all enroute hazards"), not ash. The second check rates it plausible; treat it as yes in the deck.
3. Does Weathernews' affected-aircraft notification cover ash dispersion areas as well as turbulence PIREPs? Which APAC airlines buy ACOS today?
4. Will VAAC Darwin or Wellington issue any QVA product between 26 Nov and 4 Dec 2026? Partly answered: a verifier opened the ICAO APAC paper in a browser. It confirms Tokyo is not before early 2028 and Darwin was in pre-operational testing in July 2026, but gives no Darwin or Wellington date. Annex 3 recommends all VAACs from 26 Nov 2026. Recheck the Darwin VAAC page in late November.
5. What does the NAVBLUE N-Tracking "View Volcano Information and the Related Ash Forecast" article describe? The URL now redirects.
6. Is Tomorrow.io's "SIGMETs and Volcanic Ash Alerts" layer (and the separate "Volcanic Ash" layer) still limited to Washington, London and Toulouse VAACs? Is Gale's LLM Azure OpenAI? Both support pages return 403 to fetch; open them in a browser.
7. Mitiga Solutions: is any aviation ash product still sold?
8. Garuda, Air New Zealand, Collins/ARINC, Indra, Vaisala and EUMETSAT were not checked properly because the search budget ran out. A rerun with budget should cover them.
9. Do smaller APAC carriers (Lion Group, Citilink, Cebu Pacific, Air Niugini) have in-house meteorologists? This decides whether "operators without a meteorologist contract" is a real segment.
10. Are the BoM Darwin VAA graphics usable in a public demo under the page's use statement? This belongs to the data-licensing lens.
11. Does Lufthansa Systems' "zeroG – AI in Aviation" offer an LLM dispatch or hazard product? Not checked by either pass.
12. Is EVITA available to airline operators outside Europe, and does it accept VAAC Tokyo or Darwin products? Only the Joint QVA Task Force timeline was read.
13. Has ICAO issued a later edition of Doc 9974 that renumbers §2.4(d) and §2.5(b)?

---

## Sources

All accessed 2026-10-10 unless marked as a search result only.

Opened directly (WebFetch or curl):
- https://global.weathernews.com/news/16070/
- https://wxtech.weathernews.com/en/industries/airline/
- https://wxtech.weathernews.com/en/products/sky/flightplan-editor/
- https://wxtech.weathernews.com/en/products/data/services/volcanic-eruption/
- https://www.weathercompany.com/blog/volcanic-ash-and-aviation-safety-protecting-planes-passengers/
- https://www.weathercompany.com/aviation/
- https://www.weathercompany.com/aviation/maverick-wxalert/
- https://www.weathercompany.com/aviation/maverick-dispatch/
- https://www.weathercompany.com/wp-content/uploads/2026/06/Aircraft-IT-Operations-ITA-The-Weather-Co-case-study.pdf
- https://www.flysafe.zone/tools/volcanic-ash-map/
- https://www.flysafe.zone/
- https://www.flysafe.zone/pricing/ (downloaded, not quoted)
- https://www.flysafe.zone/api/ (downloaded, not quoted)
- https://www.lhsystems.com/product-brands/lido/lido-flight-4d
- https://www.lhsystems.com/solutions/pilot-applications
- https://cdn.lhsystems.com/2026-01/Lido%20Weather%20Product%20Sheet%202026%20.pdf
- https://www.lhsystems.com/blog-entry/how-ai-transforming-aviation-data-lido-notam-ai-extractor-accelerates-flight-planning
- https://www.lhsystems.com/solutions/ai-other-services/netlineops-aiocc
- https://www.lhsystems.com/article/global-aviation-cloud-gac-lufthansa-systems
- https://cloud.google.com/blog/products/ai-machine-learning/how-lufthansa-reduce-flight-delays-with-google-cloud-ml
- https://news.jeppesen.com/aviator-articles/putting-flight-disruption-back-in-its-place-introducing-stratosphere/
- https://news.jeppesen.com/aviator-articles/your-new-ai-assistant-for-smarter-flight-operations/
- https://ai.jeppesenforeflight.com/
- https://avweb.com/aviation-news/foreflight-brings-ai-to-airline-operations/
- https://www.navblue.aero/ (301 to skywise.com)
- https://www.navblue.aero/?p=1489
- https://www.skywise.com/en/digital-solutions/planning-operations-control/command-for-ops-control-centres
- https://www.skywise.com/en/digital-solutions/flight-operations/mission
- https://flightkeys.com/index.html
- https://www.dtn.com/weather/aviation/airlines/flight-route-alerting/
- https://apps.apple.com/us/app/-/id1068135642
- https://aerospace.honeywell.com/us/en/products-and-services/product/services/flight-services/weather-information-service
- https://www.tomorrow.io/blog/february-product-update/
- https://www.tomorrow.io/blog/tomorrow-io-launches-altitude-the-aviation-weather-intelligence-platform/
- https://www.tomorrow.io/blog/tomorrow-io-spring-2026-product-update/
- https://www.tomorrow.io/blog/operate-safer-and-faster-with-agentic-weather-ai-route-intelligence-and-unified-dashboards/
- https://www.tomorrow.io/blog/tomorrow-io-debuts-next-gen-ai-operator-for-weather/
- https://www.nesdis.noaa.gov/news/airlines-observatories-and-others-keep-tabs-volcanic-activity-volcat
- https://volcano.ssec.wisc.edu/
- https://www.metoffice.gov.uk/about-us/news-and-media/media-centre/corporate-news/2025/clearing-the-air-new-met-office-service-to-cut-aviation-disruption-from-volcanic-ash
- https://www.ainonline.com/aviation-news/aerospace/2026-01-15/icao-introduces-new-and-improved-volcanic-ash-forecast
- https://www.mitigasolutions.com/
- https://www.jma.go.jp/jma/jma-eng/satellite/VLab/QG/RGB_QG_Ash_en.pdf
- https://blog.flightaware.com/flightaware-global-premium-weather
- https://apps.apple.com/app/garmin-pilot/id340917615
- https://blog.foreflight.com/?p=6175 (redirected to resource centre; no SIGMET text)
- https://www.aviobook.aero/
- https://www.frequentis.com/
- https://airnavindonesia.co.id/
- https://www.data.jma.go.jp/vaac/data/index.html
- https://www.bom.gov.au/aviation/volcanic-ash/
- https://publicadministration.un.org/unpsa/Portals/0/UNPSA_Submitted_Docs/2018/4E384934-AAB8-4FE4-888A-7CE9231FCDF7/VAAC_Darwin_MAGMA_Letter.pdf?ver=2018-02-26-044107-637
- https://en.tempo.co/read/2067292/no-airport-disruption-following-mount-semerus-eruption-says-airnav-indonesia
- https://www.copac.es/wp-content/uploads/2021/09/ICAO-Guidance-on-Flight-Operations-and-Volcanic-Ash.pdf
- https://ad.easa.europa.eu/blob/EASA_SIB_2010_17_R7_CORR.pdf/SIB_2010-17R7_1
- https://www.googlecloudpresscorner.com/2026-08-12-Ryanair-and-Google-Cloud-Announce-Five-Year-Data-and-AI-Partnership
- https://www.anahd.co.jp/group/en/pr/202510/20251016-2.html
- https://techwireasia.com/2026/08/singapore-airlines-ai-applications/
- https://www.greenairnews.com/?p=9505
- https://www.bcg.com/x/mark-your-moment/transforming-airline-operations-with-ai
- https://www.abc.net.au/news/2025-07-07/indonesia-mount-lewotobi-laki-laki-erupts-again-cancels-flights/105503740
- https://arxiv.org/abs/2607.01829

Opened by the 2026-10-10 verifiers only (X2-FOUND; not reopened by me):
- https://assets.ctfassets.net/krj50g99u3hm/56ZjQ3Omw7OpcUMpfpFll8/6057af9b554a9de8c5698dc06e55c34b/Joint_QVA_Task_Force_-_QVA_Implementation_Timeline.pdf (EVITA, QVA timeline, VACP)
- https://www.icao.int/sites/default/files/APAC/Meetings/2026/2026%20MET%20SG-30/4.%20Information%20Papers/IP03_AI5_AUS-JPN-NZL-USA_COMBINED-APAC-VAAC-MANAGEMENT-REPORT.pdf (one verifier, in the user's Chrome via pdf.js; the other got 403)
- https://www.weathercompany.com/wp-content/uploads/2025/12/Maverick-WXAlert-FINAL.pdf
- https://www.weathercompany.com/aviation/weather-forecast-services/
- https://magma.esdm.go.id/v1/vona
- AirlineGeeks, 12 Mar 2026 (United renews WXAlert); GlobeNewswire and AIN, 6 Oct 2026 (Airflow agents); ops.group, 12 Jan 2026 (QVA) — search summaries only

Tried but blocked (403 / Cloudflare); used only via search-result text (REPORTED):
- https://www.icao.int/sites/default/files/APAC/Meetings/2026/2026%20MET%20SG-30/4.%20Information%20Papers/IP03_AI5_AUS-JPN-NZL-USA_COMBINED-APAC-VAAC-MANAGEMENT-REPORT.pdf
- https://www.icao.int/sites/default/files/2025-04/9974_en.pdf (the copac.es extract used instead)
- https://support.tomorrow.io/hc/en-us/articles/36154937966356-SIGMETs-and-Volcanic-Ash-Alerts-Aviation-Customers
- https://support.tomorrow.io/hc/en-us/articles/16557265262868-Using-Gale-Tomorrow-io-s-AI-Weather-Agent
- https://www.flightradar24.com/blog/inside-flightradar24/welcoming-weather-to-flightradar24/
- https://www.flightradar24.com/blog/inside-flightradar24/volcanoes-history-and-statistics-new-and-updated-flightradar24-features/
- https://www.collinsaerospace.com/what-we-do/industries/business-aviation/flight-operations/arincdirect
- https://n-tracking.support.navblue.aero/support/solutions/articles/35000193366-view-volcano-information-and-the-related-ash-forecast (redirects to skywise.com)

Search-result only (REPORTED, not opened):
- https://avitrader.com/2025/11/06/jeppesen-foreflight-takes-off-as-independent-digital-aviation-firm/
- https://www.onboardhospitality.com/lufthansa-systems-partners-with-google-cloud/
- https://www.honeywell.com/us/en/press/2018/05/honeywell-expands-godirect-flight-with-new-connected-service-offerings-for-pilots-dispatchers
- https://www.barchart.com/story/news/846965/american-airlines-and-google-say-ai-helped-airplanes-reduce-contrails-that-trap-heat
- https://bsc.es/node/51283
- https://cordis.europa.eu/project/id/874346
- https://assets.ctfassets.net/krj50g99u3hm/56ZjQ3Omw7OpcUMpfpFll8/6057af9b554a9de8c5698dc06e55c34b/Joint_QVA_Task_Force_-_QVA_Implementation_Timeline.pdf
- https://newsroom.accenture.com/news/2025/accenture-and-google-cloud-support-air-france-klm-in-building-a-generative-ai-factory-to-revolutionize-operations
- https://australianaviation.com.au/2026/01/qantas-to-embrace-ai-in-2026-says-hudson/
- https://news.microsoft.com/source/asia/features/japan-airlines-new-ai-app-will-make-it-easier-for-cabin-attendants-to-report-inflight-events-with-microsofts-phi-4-small-language-model/
- https://arxiv.org/pdf/2402.14850
- https://blog.foreflight.com/2015/11/11/international-sigmets/

---

## Search log

WebSearch queries run: 35 (mode in brackets). Three more were refused because the session's shared search budget was exhausted.

1. Lufthansa Systems Lido Flight 4D volcanic ash [standard]
2. Lufthansa Systems Google Cloud generative AI Lido 2025 [extended]
3. Flightkeys 5D volcanic ash dispatch [standard]
4. SITA eWAS volcanic ash pilot app [standard]
5. Lido mPilot weather overlay volcanic ash SIGMET [standard]
6. Jeppesen FliteDeck Pro volcanic ash weather overlay [standard]
7. NAVBLUE Flight Plan volcanic ash N-Flight Planning weather hazards [standard]
8. Jeppesen generative AI flight operations 2025 dispatch assistant [extended]
9. Honeywell Weather Information Service volcanic ash GoDirect weather [standard]
10. DTN aviation volcanic ash dispatch flight planning weather [standard]
11. Mitiga Solutions volcanic ash forecast airlines VAAC product [standard]
12. Met Office quantitative volcanic ash QVA VAAC 2025 2026 rollout ICAO [extended]
13. Flightradar24 volcanic ash SIGMET layer map [standard]
14. ForeFlight volcanic ash advisory layer map international SIGMET [standard]
15. Tomorrow.io Gale AI weather assistant aviation airline operations LLM [standard]
16. tomorrow.io volcanic ash monitoring aviation release notes Gale alternate routing assistant [extended]
17. airline operations control center generative AI agent disruption recommendations 2026 Google Cloud Gemini airline [extended]
18. Air France-KLM Google Cloud generative AI operations 2025 [standard]
19. Qantas generative AI operations centre flight dispatch 2026 [extended]
20. Cathay Pacific OR "Singapore Airlines" OR "Japan Airlines" OR ANA generative AI operations control flight dispatch 2026 [extended]
21. Weathernews airline volcanic ash dispersion forecast service ACOS 2025 2026 airlines Asia [extended]
22. Collins Aerospace ARINC volcanic ash flight operations weather service airlines [standard]
23. Thales OR Frequentis OR Indra volcanic ash air traffic management tool ANSP [standard]
24. AirNav Indonesia volcanic ash tool ASHTAM Lewotobi Anak Krakatau 2026 rerouting [extended]
25. Bureau of Meteorology Darwin VAAC airline aviation volcanic ash products Visual Weather ensemble 2026 [extended]
26. Tokyo VAAC quantitative volcanic ash QVA JMA 2026 implementation [extended]
27. "VAAC Darwin" QVA "late 2026" OR "November 2026" quantitative volcanic ash Darwin implementation [extended]
28. EUMETSAT volcanic ash RGB product Himawari ash RGB JMA user guide [standard]
29. Vaisala volcanic ash aviation product OR Garmin Pilot volcanic ash SIGMET [standard]
30. Cathay Pacific Google contrail avoidance dispatchers Google Cloud trial 2025 2026 [standard]
31. NASA ATM-X OR EUROCONTROL large language model air traffic flow management assistant 2026 [extended]
32. Qantas volcanic ash "meteorologists" decision cancel flights Bali Lewotobi review conditions [extended]
33. Lufthansa volcanic ash policy risk assessment operations control ash concentration [standard]
34. Singapore Airlines Scoot volcanic ash Anak Krakatau September 2026 cancellations statement [standard]
35. EASA volcanic ash safety risk assessment operator "conflicting information" OR "resolve conflicts" information sources SIB 2010-17 [extended]

Refused (budget exhausted, not run):
- Mitiga Solutions volcanic ash airlines 2025 2026 product launch
- VOLCAT volcanic cloud analysis toolkit website alerts public volcano.ssec.wisc.edu 2026
- The Weather Company aviation 2026 AI agent airline operations volcanic ash Enroute Hazards

Direct page fetches: about 45 WebFetch calls and about 40 curl downloads of the URLs listed under Sources. No search engine was queried through curl. No gcloud, Vertex AI, Earth Engine or other credentialed tool was used.

---

## Verification log (2026-10-10)

Two adversarial verifiers rechecked each key claim: source-check (does the cited page say it?) and recency (is it still true, and is there newer counter-evidence?). Both shared one exhausted search budget, so K8-K14 rest on direct page fetches rather than two counter-searches each.

| Claim | Subject | Source-check | Recency | Action taken |
|---|---|---|---|---|
| K1 | Jeppesen Stratosphere: GenAI, SIGMET → diversion, dispatcher approves, Elrey beta, no ash | HOLDS | HOLDS | Tag → CONFIRMED-X2; added HKG turbulence SIGMET, system files the change itself, "soon across all Jeppesen products" |
| K2 | Airflow L2 "AI proposes ... human approves", why-trail, limited beta, no ash | HOLDS | HOLDS (wording nit) | Tag → CONFIRMED-X2; added L3/L4 tiers; noted "decision" vs "recommendation" wording split |
| K3 | AvWeb 6 Oct 2026: first Airflow agents, recommendations not decisions, rollout early next year | HOLDS | HOLDS | Tag → CONFIRMED-X2; added headline, Augmented Ops Control scope (crew/aircraft, no weather), 2027 rollout |
| K4 | TWC WXAlert: flight-projected hazard alerts, proprietary SIGMETs, diversion guidance | HOLDS | HOLDS (caveat) | Tag → CONFIRMED-X2; added product sheet, ACARS, ash alerts plausible via ash FPGs |
| K5 | TWC Nov 2024 ash blog: Enroute Hazards package with ash SIGMETs, FPGs, HOTL; no AI | PARTLY | PARTLY | Corrected: FPGs/HOTL listed separately from the package; ash SIGMETs are customer-specific; TWC sells AI dispatch and ash en-route alerts elsewhere |
| K6 | Weathernews AI ash detection (2021), ACOS for Japan/SE Asia, "reference information" | HOLDS | HOLDS | Tag → CONFIRMED-X2; added second world-first claim |
| K7 | Weathernews risk notification (turbulence, JAL, ACARS); ash forecasts and SIGMET overlay | HOLDS | HOLDS (precision) | Tag → CONFIRMED-X2; ash and SIGMET overlay moved to Enroute Optimization Support Service |
| K8 | Lido NHM accounts for ash; IFS exception notifications; WINDS alerts | PARTLY | HOLDS | Corrected: WINDS is legacy, replaced by IFS; IFS resolves some issues autonomously; zeroG unchecked |
| K9 | DTN Flight Route Alerting: 4D engine, 25 airports, ash in data list | HOLDS | HOLDS | Tag → CONFIRMED-X2; added "patented", multiple flight plans |
| K10 | ICAO Doc 9974 §2.4(d) conflict resolution; §2.5(b) dispatchers | HOLDS | HOLDS (edition caveat) | Tag → CONFIRMED-X2; cite 1st ed. 2012; check for a later edition |
| K11 | Met Office + Météo-France free QVA from 27 Nov 2025; seven others a year later | PARTLY | PARTLY | Corrected: Toulouse from 15 Dec 2025; "free" is Met Office only; all-VAAC QVA is a Recommended Practice from 26 Nov 2026; Europe awaits VACP update |
| K12 | Tokyo QVA after early-2028 update; Darwin moving DEPS into Visual Weather; APAC deterministic through finale | PARTLY (facts confirmed via browser) | PARTLY (primary 403) | Facts kept (one-verifier); conclusion narrowed to Tokyo VAAC area; section 7.7 and conflict 5 rewritten |
| K13 | VAAC Darwin 2018 letter: VONAs received in real time; so frame cone as gap-filling | HOLDS | HOLDS | Tag → CONFIRMED-X2; marked gap-filling as our conclusion; added 2026 Philippines VONA → VAA evidence |
| K14 | Tomorrow.io Altitude agentic platform at Lufthansa (~800 flights/day); Feb 2026 diversion tools; no ash | HOLDS | PARTLY | Corrected: 800 is Lufthansa's operation, not Altitude coverage; ash premium layers exist; overlap raised to core step, conflict 8 → SERIOUS |

New findings folded in: EVITA (section 4.8, conflict 12, SERIOUS); QVA regulatory status and Toulouse dates (4.8, conflict 5, section 7.7); APAC 2026 ash workload (4.8, 4.11, section 7.11); Lido IFS autonomy (4.4, conflict 13, MINOR); TWC customer-specific ash SIGMETs and AI dispatch (4.2, conflict 2); Jeppesen executes after approval and 2027 timeline (4.1, conflict 1); Tomorrow.io ash layers (4.7, conflict 8); FlySafe as live dispatch competition (4.8, conflict 9). Open items: zeroG, Tomorrow.io ash-layer VAAC coverage, Darwin/Wellington QVA dates, Doc 9974 edition.

Final conflict grades: 1 SERIOUS, 2 SERIOUS, 3 SERIOUS (image claim) / MINOR (idea), 4 MINOR, 5 MINOR, 6 MINOR, 7 MINOR, 8 SERIOUS (raised), 9 MINOR, 10 MINOR, 11 NONE, 12 SERIOUS (new), 13 MINOR (new). No FATAL.
