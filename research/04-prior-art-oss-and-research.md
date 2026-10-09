# 04 · Prior art: open source, hackathon entries and research (lens: prior-art-oss)


## Method and limits

- GitHub repository metadata (stars, created, last push, archived flag, file trees) came from the public GitHub REST API without authentication; READMEs and source files came from `raw.githubusercontent.com`. No `gh`, no gcloud, no credentials were used.
- GitHub **code** search was not run: it requires an authenticated token and I did not use any account. Only repository search (name, description, README topics) was run, 20 queries.
- Devpost project pages return a Cloudflare challenge (HTTP 403) to `curl` and to WebFetch. I read the Devpost project pages and the Devpost project search through the public reader `r.jina.ai` **before** the session's web-search budget ran out; after the budget notice I stopped using the reader and ran no further searches of any kind. `gemini3.devpost.com` answered `curl` directly (HTTP 200).
- Tags: [CONFIRMED: url, accessed 2026-10-10] means I opened that page, file or API response myself and it says this. [REPORTED: url] means a secondary source or a search-result summary says it. [UNVERIFIED] means I could not check it.

## Short verdict

The pack's 2026-10-09 "PARTLY built" verdict holds and is, if anything, slightly too generous to us on the data layer. Two new open-source projects the pack missed already fuse the same Indonesian ash feeds TEPHRA plans to use: **Sebaran Abu Gunung Api** (`rezzzq/abu-gunung-api`, pushed 2026-10-09) puts Darwin VAAC polygons, MAGMA VONAs and alert levels, Himawari-9 true colour, Ash RGB and an experimental split-window ash signal, airport METARs and winds on one live map refreshed every 15 minutes; **Pantau Abu** (`kusumaindraputra/monitoring-abu`) adds BMKG VA SIGMETs as a secondary confirmation. Neither uses an LLM, neither touches aircraft, neither reconciles disagreement into one product, and neither drafts a decision. The hackathon side is as the pack said (MeteoWatch 2024, AeroGuard 2026, WrightWay 2026), with two corrections: AeroGuard does not use Gemini (it is the MeteoWatch README with the name changed, Azure OpenAI), and the Gemini 3 Hackathon winners Globot and Aegis both ran on mock or simulated data. No project, paper or product page I opened reconciles conflicting VONA / VAAC / SIGMET / satellite evidence into one confidence-stated hazard area and turns it into a per-flight, dispatcher-approved decision on live aircraft. That step is still open, but it is narrow, and a judge can ask why a deterministic union of polygons is not enough.

## Overlap grades used in the table

- **HIGH**: does one of TEPHRA's core steps (live aircraft x ash/SIGMET geometry, LLM-written per-flight warning, dispatcher-gated recommendation, or live fusion of the same ash feeds) so a judge could call that step "already built".
- **MEDIUM**: same domain and same feeds, but stops at display or ingest.
- **LOW**: the same pattern in another hazard or domain, or a single component (parser, detector, paper).
- **NONE**: no meaningful overlap.

## Prior-art table

| Name | Kind | URL | Date (created / last activity) | LLM | Overlap | Note |
|---|---|---|---|---|---|---|
| Sebaran Abu Gunung Api (`rezzzq/abu-gunung-api`) | Open source, live public site | https://github.com/rezzzq/abu-gunung-api | 2026-09-06 / 2026-10-09 | No | HIGH (data layer) | **New.** Darwin VAAC (BOM + NOAA mirror, "using the newer"), MAGMA VONA + PVMBG levels, Himawari-9 true colour / Ash RGB / experimental ash signal, METARs, Open-Meteo winds, every 15 min. Public audience, no aircraft, no decision. |
| AshMap (`mzmznasipadang/ash-map`) | Open source, live site | https://github.com/mzmznasipadang/ash-map | 2026-09-06 / 2026-09-08 | No | MEDIUM | Darwin VAAC polygons via BOM FTP, PVMBG alert levels, winds, airports under ash, NOTAMs. Tells users the three sources "can disagree"; does not reconcile. 0 stars. |
| Pantau Abu Vulkanik Indonesia (`kusumaindraputra/monitoring-abu`) | Open source | https://github.com/kusumaindraputra/monitoring-abu | 2026-09-07 / 2026-09-07 | No | MEDIUM | Darwin VAAC vs 38 provinces, 508 regencies, 244 airports to +18 h; BMKG Ina-SIAM VA SIGMET shown only as "konfirmasi sekunder"; MAGMA status. Reports MAGMA WAF 403 for many datacenter IPs. 0 stars. |
| WrightWay | Hackathon (BigRed//Hacks 2026) | https://devpost.com/software/wrightway | 2026-10-03 / 2026-10-04 | Yes (Grok) | HIGH (decision + human gate) | North Atlantic dispatcher console; deterministic engine ranks diversions; Grok only phrases; dispatcher approves. Ash = live VA SIGMET or simulated scenario, "always forbidden, 50 nm buffer". Simulated flight. No reconciliation. |
| MeteoWatch | Hackathon (Microsoft Fabric and AI Learning Hackathon, category winner) | https://devpost.com/software/dajoma | 2024-11-10 | Yes (Azure OpenAI) | HIGH (aircraft x SIGMET + LLM warning) | OpenSky + ADSDB + AviationWeather SIGMETs; trajectory x SIGMET intersection; Azure OpenAI writes a per-aircraft warning. No ash-specific logic. Won "Best use of Real-Time Intelligence in Microsoft Fabric". |
| AeroGuard AI / "MeteoWatch - The AeroGuard AI" | Hackathon (Build with Gemini XPRIZE, RevenueCat Shipaton 2026, ML Empowerment 3.0) | https://devpost.com/software/meteowatch-the-aeroguard-ai | 2026-08-17 / 2026-08-21 | Yes (Azure OpenAI, not Gemini) | HIGH (same as MeteoWatch) | README is the MeteoWatch 2024 README with the project name changed; different authors. Same pipeline, no Gemini. |
| GeoSentinel | Hackathon | https://devpost.com/software/geosentinel-k9pn53 | not shown | Yes (Gemini 2.0 Flash, Live voice) | LOW | Voice OSINT globe on Cloud Run: OpenSky aviation arcs, USGS quakes, AIS, FIRMS. No ash or dispatch logic found. |
| Globot | Hackathon (Gemini 3 Hackathon, Grand Prize) | https://devpost.com/software/globot-341w9q | Devpost 2026-02-09 / repo push 2026-08-05 | Yes (Gemini 3 Flash, Gemini Vision) | LOW (pattern) | Shipping-disruption multi-agent; Gemini Vision on satellite images; human approval. README: "Default demos use mock and synthetic data." |
| Aegis | Hackathon (Gemini 3 Hackathon, Second Place) | https://devpost.com/software/aegis-autonomous-multi-agent-crisis-command | repo 2026-01-21 / 2026-02-08 | Yes (Gemini 3 Pro / Flash) | LOW (pattern) | 911 mass-casualty triage swarm; "Protocol Zero" human approval; README: "Simulation-First", all signals from `simulation_data.json`. |
| FlightFixer | Hackathon (event not identified) | https://devpost.com/software/world-s-first-ai-driven-geospatial-data-modeling-recommender-i2c3z9 | not shown | Yes (Gemini, ADK) | LOW | **New.** Airline disruption agents (rebooking, crew, maintenance) with Gemini + ADK on Cloud Run; simulation-driven; no weather-hazard geometry. Shows "Gemini + ADK airline ops" is not new by itself. |
| AeroTwin AI | Hackathon | https://devpost.com/software/hackon-team | not shown | Yes (OpenAI) | LOW | **New.** OCC "operations copilot" over a flight graph with a rule-based risk engine incl. weather thresholds. No ash. |
| IceSight | Hackathon | https://devpost.com/software/icesight | not shown | No (unsupervised ML) | LOW | **New.** GOES-R icing-risk heatmap pitched as finer than icing SIGMETs. Same "official polygon is too coarse" argument, different hazard. |
| Vector-Dispatch ("Dispatch") | Hackathon (TAMUhack 2026, MLH MongoDB winner) | https://devpost.com/software/dispatch-z5wdxg | ~2026-01 | Yes (RAG) | NONE | **New.** Gate vs maintenance "stop-loss" with MEL RAG on simulated flight states. Airline ops, no weather. |
| `shuvam-sinha/flight-dispatch-agent` | Open source | https://github.com/shuvam-sinha/flight-dispatch-agent | 2026-08-04 / 2026-08-18 | Yes (local models) | LOW | **New.** LLM agent calls deterministic routing, winds-aloft and airspace tools; "every number it reports comes from real tool output". Flight planning, no ash. Same grounding pattern TEPHRA's ADK planner needs. |
| APAC SIGMET Monitor (`songhan89/sigmet-wiw2-gemini`) | Open source, live demo | https://github.com/songhan89/sigmet-wiw2-gemini | 2026-09-05 / 2026-09-05 | No dependency found | LOW | **New.** IWXXM SIGMET parser for Singapore (WSJC) and Jakarta (WIIF) FIRs incl. VA, cancellation pairing, MapLibre replay of a May 2026 archive. "gemini" is only in the repo name. |
| Volcano-vis / "Reading Indonesia's volcanic skies" (`tuttinator/volcano-vis`) | Open source + article | https://github.com/tuttinator/volcano-vis | 2026-09-17 / 2026-09-21 | No | LOW | Retrospective replay: 104 Darwin VAAC editions, 579 Himawari Band-13 and Ash RGB frames, Anak Krakatau 4-8 Sep 2026, provenance kept. "Not an operational warning service." |
| Awas Abu (`hikgum-ops/awas-abu`) | Open source | https://github.com/hikgum-ops/awas-abu | 2026-09-06 / 2026-09-14 | No | LOW | **New.** Human operator relays official ash bulletins to web and WhatsApp; "Missing data is always reported as BELUM ADA DATA, never AMAN." Ground public, not aviation. |
| GOES Volcanic Monitoring Chile (`MendozaVolcanic/goes-volcanic-monitoring`) | Open source, HF Space | https://github.com/MendozaVolcanic/goes-volcanic-monitoring | 2026-04-05 / 2026-10-09 | Not found | LOW | **New.** GOES-19 Ash RGB, split-window ash detection and SO2 for Chilean volcanoes (SERNAGEOMIN). Same satellite step, other region and satellite. |
| `vance1028/ashfallcorridor-base` | Open source | https://github.com/vance1028/ashfallcorridor-base | 2026-08-20 / 2026-08-20 | No | LOW | Chinese-language Go/Postgres backend: ash-notice approval workflow, verification flights, runway clearance, audit chain. No live feeds, no AI. 0 stars, one push. |
| `andyprata/volcanic-ash-ml` | Open source (research code) | https://github.com/andyprata/volcanic-ash-ml | 2021-07-06 / 2023-03-15 | No | LOW | Linear SVC on 16 Himawari AHI bands, labels from Tokyo VAAC polygons x BTD, 2020 Nishinoshima. 3 stars, inactive. |
| arXiv 2307.12970 | Paper | https://arxiv.org/abs/2307.12970 | 2023-07-24 | No (Pix2Pix GAN) | LOW | "Volcanic ash delimitation using Artificial Intelligence based on Pix2Pix"; ash masks from multispectral images. |
| `martanto/magma-vona` | Open source (stub) | https://github.com/martanto/magma-vona | 2025-08-15 / 2025-08-15 | No | LOW | v0.0.1; depends on `magma-database` and `magma-auth`, so it targets MAGMA's own authenticated store, not public scraping. 0 stars. |
| `metno/fetch-vaa` | Open source (archived) | https://github.com/metno/fetch-vaa | 2015-02-06 / 2023-03-22 | No | LOW | "This repository is no longer maintained", moved to MET Norway's internal GitLab. 3 stars. |
| `ryo-a/node-vaa` | Open source | https://github.com/ryo-a/node-vaa | 2019-08-25 / 2021-05-10 | No | LOW | Hobby VAA parser; "How to use: WIP". 0 stars. |
| `apifyforge/aviation-safety-risk-mcp` | Open source / paid actor | https://github.com/apifyforge/aviation-safety-risk-mcp | 2026-03-21 | Serves LLM agents | LOW | **New.** MCP server returning a composite aviation safety score from 8 government sources; README mentions volcanic ash. Insurer/lessor audience. |
| `Shlok266/drone-replanner` | Hackathon code | https://github.com/Shlok266/drone-replanner | 2026-09-25 / 2026-09-29 | No | NONE | Pygame drone A* replanning around synthetic hazard volumes incl. "volcanic ash". |
| Weathernews AI volcanic ash detection | Product | https://global.weathernews.com/news/16070/ | 2021-04-26 | Proprietary image AI | MEDIUM (satellite step) | "first in the world ... real-time image recognition of volcanic ash clouds from gaps in clouds using AI", fed into ash forecasts for airlines. |
| The Weather Company Enroute Hazards / HOTL ash reports | Product | https://www.weathercompany.com/blog/volcanic-ash-and-aviation-safety-protecting-planes-passengers/ | 2024-11-11 | Not stated | MEDIUM (consolidation) | Human-Over-the-Loop PDFs combining "SIGMETs, wind barbs, and satellite imagery"; Volcanic Ash Flight Plan Guidance; enhanced SIGMETs. Meteorologist-made, not per flight. |
| FlySafe.zone Volcanic Ash Map + Fleet Monitor | Product | https://www.flysafe.zone/tools/volcanic-ash-map/ | snapshot "CHECKED 09 Oct 2026 18:25 UTC" | No AI text found | MEDIUM | Observatory colour codes incl. PVMBG (MAGMA), VAAC advisories, MODIS/VIIRS thermal anomalies, ADS-B traffic near vents; "Airline OCC / dispatch Fleet Monitor", Console $99/mo, API + webhooks. |
| NOAA VOLCAT | Government product | https://www.nesdis.noaa.gov/news/airlines-observatories-and-others-keep-tabs-volcanic-activity-volcat | undated page | No | LOW | Satellite volcanic-cloud alerts for observatories and VAACs. |

## Re-verification of the pack's items

### AeroGuard AI / MeteoWatch (Devpost, 2026)
- The page exists, titled "MeteoWatch -The AeroGuard AI" [CONFIRMED: https://devpost.com/software/meteowatch-the-aeroguard-ai, accessed 2026-10-10].
- It combines "OpenSky Network, ADSDB, and AviationWeather", "checks whether aircraft trajectories intersect with SIGMET hazard areas" and "uses **Azure OpenAI** to convert technical weather information into a clear, natural-language warning that can be tailored to the affected flight" [CONFIRMED: same URL, accessed 2026-10-10].
- It was submitted to "Build with Gemini XPRIZE", "RevenueCat Shipaton 2026" and "ML Empowerment Build Challenge 3.0"; its Built With list includes `openai` and no Gemini; page timestamps are 2026-08-17 and 2026-08-21; no winner badge [CONFIRMED: same URL, accessed 2026-10-10].
- Its linked repository `bharad07-cyber/AeroGruard-AI--MeteoWatch` was created and last pushed on 2026-08-17 with 0 stars [CONFIRMED: https://github.com/bharad07-cyber/AeroGruard-AI--MeteoWatch, accessed 2026-10-10]. Its README reuses the MeteoWatch 2024 README section by section ("Generated Alarms by OpenAI", "Azure OpenAI API is used to generate warning messages", the same seven build steps) with "MeteoWatch" partly renamed [CONFIRMED: https://github.com/bharad07-cyber/AeroGruard-AI--MeteoWatch and https://github.com/MeteoWatch/MeteoWatch, accessed 2026-10-10].
- Judgement: AeroGuard is a re-submission of the 2024 MeteoWatch design under new authors, not an independent Gemini build. The pack's description "Build with Gemini XPRIZE entry ... uses generative AI" is true but misleading; it does not use Gemini. LLM: yes. Reconciles sources: no. Drafts advisories: a warning sentence per flight, yes. Human gate: no.

### MeteoWatch (Devpost, 2024)
- The page exists and says MeteoWatch "calculates whether a flight will be affected by a SIGMET and creates a natural language warning message, which could be tailored and sent to a specific aircraft" [CONFIRMED: https://devpost.com/software/dajoma, accessed 2026-10-10].
- It was submitted to the Microsoft Fabric and AI Learning Hackathon and shows "Winner Best use of Real-Time Intelligence in Microsoft Fabric"; the team wrote "We all work at Deutsche Bahn" [CONFIRMED: same URL, accessed 2026-10-10]. The pack did not record the win.
- Repo `MeteoWatch/MeteoWatch`: created 2024-11-10, last push 2024-11-10, 2 stars [CONFIRMED: https://github.com/MeteoWatch/MeteoWatch, accessed 2026-10-10].
- LLM: yes (Azure OpenAI). Reconciles: no. Ash-specific: no. Human gate: no.

### WrightWay (Devpost, BigRed//Hacks 2026)
- The page exists; Wright Way is "a real-time decision-support console for airline dispatchers on North Atlantic routes"; for "fuel leak, airport closure, volcanic ash, icing, or a solar storm" it "Filters out unusable airports", "Ranks the remaining ones into three clear strategies" and "Uses grounded Grok voice to explain the recommendation" [CONFIRMED: https://devpost.com/software/wrightway, accessed 2026-10-10].
- The engine "is 100% deterministic Python"; "The voice layer only uses Grok for phrasing and TTS — every answer is verified against the engine's actual decision record"; "If the model tried to use a number or airport code that wasn't in the current decision record, we rejected it" [CONFIRMED: same URL, accessed 2026-10-10].
- Submitted to BigRed//Hacks 2026; timestamp 2026-10-04; Built With css, grok, python, react, typescript; no winner badge shown [CONFIRMED: same URL, accessed 2026-10-10].
- Repo `trisharaichura/WrightWay` created 2026-10-03, last push 2026-10-04, 0 stars [CONFIRMED: https://github.com/trisharaichura/WrightWay, accessed 2026-10-10].
- In the code, `volcanic_ash` is "always forbidden, wider buffer" and returns "no ash-free path exists to the airport" when no route avoids it [CONFIRMED: https://github.com/trisharaichura/WrightWay/blob/HEAD/engine/hazards.py, accessed 2026-10-10]. The sim README says "This is a simulation and decision-support prototype, **not flight software**", ash is "always forbidden, 50 nm buffer", live mode maps aviationweather.gov SIGMET "VA → volcanic_ash", and the ash scenario `ash_iceland` is a labelled "Simulated scenario" [CONFIRMED: https://github.com/trisharaichura/WrightWay/blob/HEAD/sim/README.md, accessed 2026-10-10].
- LLM: yes (Grok, phrasing only). Reconciles sources: no; it takes one SIGMET polygon as truth. Drafts a recommendation: yes (three ranked strategies). Human gate: yes. Region: North Atlantic. Aircraft: one simulated flight anchored on a real flight's last position.

### AshMap (`mzmznasipadang/ash-map`)
- Exists; description "Live volcanic ash advisory map: real ICAO VAA polygons from Darwin VAAC, live wind, GSAP-animated forecast drift, GIS export. No API keys."; TypeScript; 0 stars; created 2026-09-06; last push 2026-09-08 [CONFIRMED: https://github.com/mzmznasipadang/ash-map, accessed 2026-10-10]. The live site answered HTTP 200 with the title "AshMap — Monitor volcanic ash in Indonesia" [CONFIRMED: https://ash-map-blush.vercel.app/en, accessed 2026-10-10].
- It adds, beyond the pack's note: PVMBG alert levels scraped "because the JSON API needs credentials while the public page does not"; airports-under-ash with an inclusive boundary test; NOTAM lookup via a paid key; a first-run dialog explaining "that three independent official sources are on screen, each answering a different question, and that they can disagree"; a "source health" panel that marks a feed **suspect** when it "succeeded and returned nothing plausible" [CONFIRMED: https://github.com/mzmznasipadang/ash-map, accessed 2026-10-10].
- It flags "`EST VA CLD` (estimated) replaces `OBS VA CLD` when satellite cannot confirm the cloud. Four of five live Indonesian volcanoes use it" [CONFIRMED: same URL, accessed 2026-10-10].
- `package.json` has no LLM SDK [CONFIRMED: https://github.com/mzmznasipadang/ash-map/blob/HEAD/package.json, accessed 2026-10-10]. It says "It is not a forecast of its own — it is geometry over published polygons" [CONFIRMED: README, accessed 2026-10-10].
- LLM: no. Reconciles: no (shows sources side by side). Advisories: no. Human gate: n/a. Aircraft: no.

### Pantau Abu Vulkanik Indonesia (`kusumaindraputra/monitoring-abu`)
- Exists; Python/FastAPI; 0 stars; created and last pushed 2026-09-07 [CONFIRMED: https://github.com/kusumaindraputra/monitoring-abu, accessed 2026-10-10].
- Sources: Darwin VAAC via BOM's own `process.php` endpoint; "Konfirmasi SIGMET abu vulkanik FIR Indonesia" from BMKG Ina-SIAM via `inasiam.rack.my.id/api/v1/opmet/sigmet/geojson`; MAGMA activity levels [CONFIRMED: README, accessed 2026-10-10].
- SIGMET is used only as confirmation: "Tidak satu pun poligon, jarak, ketinggian, atau status di halaman ini berasal dari SIGMET" (no polygon, distance, height or status on the page comes from the SIGMET) [CONFIRMED: README, accessed 2026-10-10]. The author notes the SIGMET host is on a personal `.my.id` domain with a `rack.my.id` certificate, not a BMKG domain, and that its "kelima VA SIGMET-nya cocok persis dengan kelima gunung" (all five VA SIGMETs matched the five volcanoes under VAAC advisory) at the time of writing [CONFIRMED: README, accessed 2026-10-10].
- It reports that ESDM's WAF returns "HTTP 403 'Request Rejected'" to many IPs "termasuk banyak IP datacenter" across `magma.esdm.go.id`, `vsi.esdm.go.id` and `geologi.esdm.go.id` [CONFIRMED: README, accessed 2026-10-10].
- It deliberately drops crater-level Open-Meteo wind as misleading, because the VAAC forecast polygon already contains the wind [CONFIRMED: README, accessed 2026-10-10].
- LLM: no. Reconciles: no (SIGMET confirms, does not change). Advisories: no. Aircraft: no.

### Volcano-vis (`tuttinator/volcano-vis`)
- Exists; 0 stars; created 2026-09-17; last push 2026-09-21; topics include `himawari`, `maplibre`, `volcanic-ash` [CONFIRMED: https://github.com/tuttinator/volcano-vis, accessed 2026-10-10].
- Contents: "104 editions, 470 geometries, six volcanoes" of Darwin VAAC advisories; "579 frames each" of Himawari Band 13 and Ash RGB, 4-8 September 2026; "This is a retrospective explanation, not an operational warning service"; "Ash RGB does not measure ash concentration" [CONFIRMED: README, accessed 2026-10-10].
- The companion article "Reading Indonesia's volcanic skies" was published Sep 18, 2026 [CONFIRMED: https://caleb-tutty.com/posts/indonesia-volcanic-ash, accessed 2026-10-10].
- No LLM-related file names in its 1,343-file tree [CONFIRMED: GitHub tree API for the repo, accessed 2026-10-10]. LLM: no. Reconciles: shows sources on one clock, no merged product. Advisories: no.

### `vance1028/ashfallcorridor-base`
- Exists; Go; 0 stars; created and pushed 2026-08-20 within seconds; description "Volcanic ash aviation monitoring and corridor coordination backend" [CONFIRMED: https://github.com/vance1028/ashfallcorridor-base, accessed 2026-10-10].
- The README (Chinese) describes coordinator logins, ash-cloud notice approval ("灰云通告审批"), verification flights, runway clearance, an audit chain, and a dev account `admin / admin123` [CONFIRMED: README, accessed 2026-10-10]. No LLM-related paths in its 223-file tree [CONFIRMED: tree API, accessed 2026-10-10].
- Judgement: a generated CRUD backend with a human approval workflow on ash notices, no live feed ingestion and no AI. Overlap LOW.

### `andyprata/volcanic-ash-ml`
- Exists; 3 stars; created 2021-07-06; last push 2023-03-15; the description now reads "Python notebook for plotting VAAC polygons" [CONFIRMED: https://github.com/andyprata/volcanic-ash-ml, accessed 2026-10-10].
- It trains "Linear Kernel Support Vector Classifier (SVC) models" pixel by pixel on "all 16 bands of the raw AHI data", labelling as ash the pixels with negative corrected BTD inside the Tokyo VAAC polygon, for the 2020 Nishinoshima eruption [CONFIRMED: README, accessed 2026-10-10]. LLM: no.

### arXiv 2307.12970
- Exists: "Volcanic ash delimitation using Artificial Intelligence based on Pix2Pix", Christian Carrillo, Gissela Torres, Christian Mejia-Escobar, published 2023-07-24; a Pix2Pix GAN produces "black and white ash cloud images from multispectral satellite images" [CONFIRMED: https://arxiv.org/abs/2307.12970, accessed 2026-10-10]. LLM: no.

### `martanto/magma-vona`
- Exists; 0 stars; created and pushed 2025-08-15; version 0.0.1; README is two lines [CONFIRMED: https://github.com/martanto/magma-vona, accessed 2026-10-10].
- `pyproject.toml` depends on `magma-database>=1.6.0` and `magma-auth>=1`; authors include Martanto, Devy Kamil Syahbana and Syarif Abdul Manaf [CONFIRMED: https://github.com/martanto/magma-vona/blob/HEAD/pyproject.toml, accessed 2026-10-10]. Judgement: it reads MAGMA's authenticated store, so it does not help a public poller.

### `metno/fetch-vaa`
- Archived; "This repository is no longer maintained. The code is moved to MET Norways internal gitlab"; 3 stars, 2 forks; last push 2023-03-22 [CONFIRMED: https://github.com/metno/fetch-vaa, accessed 2026-10-10].

### `ryo-a/node-vaa`
- Exists; 0 stars; last push 2021-05-10; "This library is NOT made by aviation authorities ... but just a hobby library"; usage section "WIP" [CONFIRMED: https://github.com/ryo-a/node-vaa, accessed 2026-10-10].

### GeoSentinel (Devpost)
- Exists; built on "Gemini 2.0 Flash"; "a live, interactive 3D digital twin of Earth" with "Aviation arcs, Maritime paths, NASA FIRMS wildfire clusters"; data from USGS earthquakes, OpenSky and AIS; deployed "to Google Cloud Run" [CONFIRMED: https://devpost.com/software/geosentinel-k9pn53, accessed 2026-10-10].
- No volcanic-ash or dispatch logic appears on the page [CONFIRMED: same URL, accessed 2026-10-10]. The pack's statement that it was a Gemini Live Agent Challenge entry is [REPORTED: board-tephra-pack.json]; the page text I extracted did not include the "Submitted to" block.

## New finds the pack missed

### Sebaran Abu Gunung Api (`rezzzq/abu-gunung-api`) — the closest data-layer overlap
- Repo: created 2026-09-06, last push 2026-10-09, 0 stars [CONFIRMED: https://api.github.com/search/repositories?q=volcanic%20ash, accessed 2026-10-10]. Live at https://abu-gunung-api.netlify.app (HTTP 200) and branded niriksagara.id [CONFIRMED: https://github.com/rezzzq/abu-gunung-api, accessed 2026-10-10].
- It shows "Every volcano with an active Darwin Volcanic Ash Advisory Centre (VAAC) advisory, plus PVMBG Level III and IV volcanoes"; "PVMBG alert level and the latest VONA ... from MAGMA Indonesia"; "Four satellite views of Himawari-9": true colour, "the JMA 'Ash RGB' composite", "an experimental ash signal", and NASA GIBS infrared; airport METARs; "Wind at four heights above the selected crater" [CONFIRMED: README, accessed 2026-10-10].
- Pipeline: GitHub Actions every 15 minutes pulls the newest bulletin from BOM's archive and the NOAA mirror, "the newest per volcano wins and a lag between the two is noted", parses the MAGMA level table and all-volcano VONA page as HTML, and downloads raw Himawari-9 bands from the NOAA open-data bucket [CONFIRMED: README, accessed 2026-10-10].
- Its live JSON at 2026-10-09T15:30:13Z had `sourceErrors: []`, a `magmaFetchedAt` timestamp, six volcanoes, and the note "vaac: KAR sources differ: noaa newest 2026-10-06T21:27:00Z, bom newest 2026-10-07T03:07:00Z; using the newer" [CONFIRMED: https://abu-gunung-api.netlify.app/data/latest.json, accessed 2026-10-10]. Judgement: this is rule-based mirror reconciliation (same product, newest wins), not cross-source reconciliation.
- The experimental ash signal is a split-window method with a two-day clear-sky reference and ice/water-cloud rejections; it keeps a blob only if it touches an active VAAC zone or lies within 150 km of an active volcano; "None of the statistics prove correctness; they only measure agreement with the VAAC" [CONFIRMED: https://github.com/rezzzq/abu-gunung-api/blob/HEAD/docs/superpowers/specs/2026-09-06-ash-signal-design.md, accessed 2026-10-10].
- Its public evaluation log has 209 scans from 2026-09-06T10:50Z to 2026-10-09T15:10Z; across them the median share of candidate ash pixels inside an active VAAC zone is 0.14% (mean 0.36%, max 3.45%), and the median scan keeps 15 blobs and rejects 1,082 [CONFIRMED: computed by me from https://github.com/rezzzq/abu-gunung-api/blob/HEAD/data/signal-log.jsonl, accessed 2026-10-10]. Judgement: automated infrared ash detection over humid Indonesia produces mostly unconfirmed candidates; this is evidence for keeping the satellite picture as support only.
- No LLM dependency in `package.json` or `scripts/requirements.txt` (satpy, pyresample, numpy, pillow, pytest, ruff) [CONFIRMED: https://github.com/rezzzq/abu-gunung-api, accessed 2026-10-10]. No aircraft layer, no per-flight output, no human gate; audience is the public ("so people across Indonesia can check the latest picture") [CONFIRMED: README, accessed 2026-10-10].
- License: MIT [CONFIRMED: README, accessed 2026-10-10].

### Live contradiction visible in that feed on 2026-10-09 (useful for the demo)
- Darwin VAAC advisory 2026/1156 for Semeru, issued 2026-10-09T12:20Z: estimated (`EST`) ash SFC to FL150 moving E at 10 kt, with remarks "VA NOT IDENTIFIABLE ON CURRENT SATELLITE IMAGERY DUE TO MET CLOUD. HOWEVER, INTERMITTENT DISCRETE EMISSIONS ARE EXPECTED TO BE ONGOING" [REPORTED: https://abu-gunung-api.netlify.app/data/latest.json, a parse of the Darwin bulletin; the BOM bulletin itself was not opened by me].
- MAGMA VONA 2026SMR1918 for Semeru, issued 20261009/1334Z, colour code ORANGE: "Eruption at 1334 UTC (2034 local)", "Volcanic Cloud Height : Ash-cloud is not observed.", remarks "Eruption recorded on seismogram with maximum amplitude 22 mm and maximum duration 118 second" [CONFIRMED: https://magma.esdm.go.id/v1/vona/22887?signature=93c59312d91d519eed68595447535f902adcdbd3925b7756c08033f8a25273cc, accessed 2026-10-10].
- Same pattern for Anak Krakatau: VAAC 2026/224 at 10:15Z "VA IDENTIFIABLE ON LATEST SATELLITE IMAGERY MOVING W", OBS ash SFC/FL060; VONA at 11:44Z "Eruption at 1144 UTC (1844 local). Ash-cloud is not observed." [REPORTED: https://abu-gunung-api.netlify.app/data/latest.json].
- Judgement: these are not errors by either agency; the VONA is a seismic-detected night eruption with no visual, the VAAC is a model-and-satellite estimate. A tool that only draws the union of polygons hides why the sources differ; reading the remarks and the VONA fields to state confidence is the work Gemini can do here.

### Awas Abu (`hikgum-ops/awas-abu`)
- A web site and pull-only WhatsApp bot that relay official ash status; "This service does **not** issue warnings, predict ash movement, or broadcast. Missing data is always reported as `BELUM ADA DATA`, never `AMAN`." An operator page accepts source URLs only from BMKG, MAGMA Indonesia, Badan Geologi or BNPB domains; status goes stale after `valid_minutes` [CONFIRMED: https://github.com/hikgum-ops/awas-abu, accessed 2026-10-10]. Judgement: same "never report safe on missing data" safety rule as TEPHRA's "never shrink the official polygon", for the public, without AI.

### APAC SIGMET Operations & Timeline Monitor (`songhan89/sigmet-wiw2-gemini`)
- Parses IWXXM and TAC SIGMET bulletins for the "Singapore (WSJC) and Jakarta (WIIF)" FIRs, including volcanic ash, pairs cancellations with the cancelled SIGMET, and replays a "30-Min Timeline Engine (1,488 steps across May 2026)" on MapLibre; live demo on GitHub Pages (HTTP 200) [CONFIRMED: https://github.com/songhan89/sigmet-wiw2-gemini and https://songhan89.github.io/sigmet-wiw2-gemini/, accessed 2026-10-10].
- No Gemini or other LLM package in `sigmet-poc/package.json`; the README does not mention Gemini except in URLs [CONFIRMED: same repo, accessed 2026-10-10]. Judgement: "gemini" in the name likely refers to how it was coded, not to a runtime model [UNVERIFIED].

### Flight-dispatch LLM agents and airline-ops hackathons
- `shuvam-sinha/flight-dispatch-agent`: "an agent orchestrates real routing, weather, and airspace tools to produce a flight plan"; "All routing, weather and airspace logic lives in deterministic Python functions"; "every number it reports comes from real tool output"; 598 unit tests; runs on "two local model backends" [CONFIRMED: https://github.com/shuvam-sinha/flight-dispatch-agent, accessed 2026-10-10]. No ash.
- FlightFixer: "a comprehensive, real-time disruption management platform for airlines" with specialised agents; "It leverages Google Gemini AI for root cause analysis, impact assessment, and communication generation"; "both custom and ADK-based agents"; a Cloud Run URL `flightfixer-118666262682.us-west4.run.app`; the page mentions simulation repeatedly [CONFIRMED: https://devpost.com/software/world-s-first-ai-driven-geospatial-data-modeling-recommender-i2c3z9, accessed 2026-10-10]. Hackathon not identified [UNVERIFIED].
- AeroTwin AI: "an AI Operating System for Airline OCCs" with an "Operational Risk Engine" using "weather thresholds" and an "Operations Copilot"; AI layer "OpenAI API" [CONFIRMED: https://devpost.com/software/hackon-team, accessed 2026-10-10].
- Vector-Dispatch: TAMUhack 2026, "Winner [MLH] Best Use of MongoDB Atlas"; "A Node.js WebSocket server pushes a heartbeat every 2 seconds to simulate live flight states"; an "AI Oracle (RAG pipeline over 1,000-page MEL/CDL manuals)" [CONFIRMED: https://devpost.com/software/dispatch-z5wdxg, accessed 2026-10-10].
- IceSight: ingests "near real-time multispectral imagery from NOAA's GOES-R" and argues icing SIGMETs are "Updated only once every 6 hours", span "at least 3,000 square miles" and give "only binary risk indication" [CONFIRMED: https://devpost.com/software/icesight, accessed 2026-10-10].
- GitHub repository search also returned, without my opening them: `vrai/ga_weather_briefing_agentic` ("agent skills that produce a General Aviation (GA) weather briefing for UK flights"), `kevinrodriguezfernandez/aviation-ops-briefing-agent` ("multi-agent system built with LangGraph that ingests daily flight schedules, real-time weather, and NOTAMs"), `jayrav13/skywatch` ("Agentic aviation weather briefer"), `Perufitlife/aviation-mcp`, `mounalokesh2001-ai/Aviation-MCP-Agent` ("AI agent using ADK + MCP to analyze aviation safety data") [CONFIRMED as repository descriptions: https://api.github.com/search/repositories?q=aviation%20weather%20agent and ?q=adk%20aviation, accessed 2026-10-10]. None mentions volcanic ash in its description.
- Judgement: "LLM agent + aviation weather + dispatcher" is now a crowded hobby and hackathon pattern; only the ash reconciliation and the APAC live feeds separate TEPHRA from it.

### Satellite ash detection repos
- `MendozaVolcanic/goes-volcanic-monitoring`: "Dashboard de monitoreo volcánico en tiempo casi-real usando imágenes del satélite geoestacionario GOES-19" producing "Ash RGB, detección de ceniza (BTD split-window) y SO2", deployed on a Hugging Face Space for SERNAGEOMIN [CONFIRMED: https://github.com/MendozaVolcanic/goes-volcanic-monitoring, accessed 2026-10-10].
- `ulil-hidayat/volcanic-ash-detection` (Himawari AHI visualisation, 2024) and `szczynk/deteksi_awan_debu_vulkanik_RST_ASH` (RST-ASH on Himawari-8, 2022) appear in repository search [CONFIRMED as descriptions: https://api.github.com/search/repositories?q=himawari%20ash, accessed 2026-10-10].

## Gemini 3 Hackathon winners: what they did and why they placed

- The Gemini 3 Hackathon ran Dec 17, 2025 – Feb 9, 2026 with 35,517 participants and $100,000 in prizes; Grand Prize $50,000, Second Place $20,000 [CONFIRMED: https://gemini3.devpost.com/, accessed 2026-10-10].
- Its Stage Two criteria were "Technical Execution - 40%", "Potential Impact - 20%", "Innovation/Wow Factor - 30%", "Presentation/Demo - 10%", each scored 1-5 and averaged; judging ran "February 10, 2026 through February 27, 2026" [CONFIRMED: https://gemini3.devpost.com/rules, accessed 2026-10-10]. Judges' reasons for individual winners are not published on these pages [CONFIRMED: same URLs, accessed 2026-10-10]; any "why it won" below is my reading of the entries against those criteria.
- **Globot (Grand Prize)**: "a 5-Agent AI Reasoning Engine powered by Gemini 3" (Market Sentinel, Risk Hedger, Logistics Orchestrator, Compliance Manager, Adversarial Debate); "Key Innovation: We use Gemini Vision to analyze satellite imagery, detecting port congestion and canal blockages 6 hours before official announcements"; "Human-in-the-Loop: All critical decisions require human approval"; built with CrewAI, deck.gl, Gemini 3 Flash, Gemini Vision, Gemini Embeddings; gallery captions include "Human On The Loop" and "Satellite cloud image analysis (cross-verification of information)" [CONFIRMED: https://devpost.com/software/globot-341w9q, accessed 2026-10-10]. Its "What's next" lists "MarineTraffic API for real-time AIS ship tracking" and "Sentinel-2 Satellite API" [CONFIRMED: same URL], and its current README says "Default demos use mock and synthetic data" [CONFIRMED: https://github.com/Vector897/Globot, accessed 2026-10-10; the README was last pushed 2026-08-05, after judging, so it may differ from the submitted version].
- **Aegis (Second Place)**: "a Multi-Agent Swarm powered by Google Gemini 3" (Coordinator, Triage, Surveillance, Logistics, Reporter); "Protocol Zero: For high-stakes decisions ... the AI flags uncertainty and requests 'Voice of God' approval from the human commander"; Google Search used to "verify locations, weathers and incidents against real-world data before dropping a pin" [CONFIRMED: https://devpost.com/software/aegis-autonomous-multi-agent-crisis-command, accessed 2026-10-10]. Its README: "a 'Simulation-First' resilient layer that doesn't rely on live, flaky APIs. Instead, it uses a deterministic 'Doomsday Dataset'"; "All distress signals come from `simulation_data.json`" [CONFIRMED: https://github.com/iamdanishm/aegis, accessed 2026-10-10].
- Judgement on why they placed: both show several named Gemini agents with visible reasoning, a multimodal step, an explicit human approval gate, and a polished demo video; both scored on Technical Execution and Innovation/Wow without live data. A Devpost commenter on Globot wrote that another project "was just a prototype feeding fake data" [CONFIRMED: Globot page comments, accessed 2026-10-10], so live-vs-fake data is something the community notices, but the two top prizes went to simulated or mock-data demos.
- Correction to the pack: it said Globot did "Live operational replanning on satellite imagery". The submission claims satellite analysis, but its README says default demos use mock and synthetic data and its roadmap lists live AIS and Sentinel-2 as future work. Do not say "Globot was live" in our deck.

## Research literature

- arXiv 2307.12970 (Pix2Pix GAN ash masks) is confirmed above.
- Search-result summaries mention: a 2024 study using a U-Net with a VGG16 backbone to segment ash in SEVIRI Ash RGB images over Sicily [REPORTED: https://www.sciencedirect.com/science/article/pii/S0377027324000386]; a GEOKOMPSAT-2A ash detection method using the 3.8 µm band with day/night thresholds [REPORTED: https://doi.org/10.3390/s21041359]; KNN and SVM classifiers on MODIS for Puyehue-Cordón Caulle 2011 [REPORTED: https://ui.adsabs.harvard.edu/abs/2021AGUFM.A14I..04N/abstract]. None of these uses a language model.
- One search for "volcanic ash large language model aviation advisory SIGMET VAAC" returned only ICAO/NOAA guidance documents and no LLM work [REPORTED: search results incl. https://www.icao.int/sites/default/files/APAC/Documents/edocs/APAC-Regional-SIGMET-Guide-11th-edition_MET_SG28_vSubmitted.pdf]. One search for "Gemini volcanic ash satellite image detection" returned no result about Google's Gemini [REPORTED: search results, 2026-10-10].
- The pack's claims "arXiv has 0 papers for '\"volcanic ash\" AND \"language model\"'" and the EGU26-560 SAM2 result on TROPOMI SO2 were not re-checked [UNVERIFIED].
- Hugging Face, Kaggle, Zenodo and Google Scholar were not searched [UNVERIFIED].

## Commercial reference points (re-verified)

- Weathernews: press release dated Apr 26, 2021, "Full-Scale Operation of AI Volcanic Ash Detection System for Aviation Market Begins"; "This system is the first in the world to be capable of real-time image recognition of volcanic ash clouds from gaps in clouds using AI"; it is introduced "into the volcanic ash diffusion prediction methods employed by the Weathernews Terrestrial Center for airlines"; example is Himawari-8 infrared of Dukono on April 5, 2021 [CONFIRMED: https://global.weathernews.com/news/16070/, accessed 2026-10-10].
- The Weather Company, November 11, 2024: "Human-Over-the-Loop (HOTL) Reports ... compile relevant volcanic ash data into easy-to-read PDFs, featuring essential information such as SIGMETs, wind barbs, and satellite imagery"; "Volcanic Ash forecast Flight Plan Guidance (FPGs)"; "the Enroute Hazards package and enhanced SIGMETs" [CONFIRMED: https://www.weathercompany.com/blog/volcanic-ash-and-aviation-safety-protecting-planes-passengers/, accessed 2026-10-10].
- FlySafe.zone: colour codes "read directly from the issuing observatories — USGS ..., INGV ..., the Icelandic Met Office, PVMBG (MAGMA) in Indonesia, and KVERT"; "Satellite thermal anomalies are detected from MODIS/VIIRS radiative power"; ADS-B "Traffic near vent"; product lines "Airline OCC / dispatch Fleet Monitor · early-warning FIR risk + webhooks" and "Console for people · $99/mo"; the strings "AI", "LLM" and "Gemini" do not appear on the page [CONFIRMED: https://www.flysafe.zone/tools/volcanic-ash-map/, accessed 2026-10-10].
- NOAA VOLCAT provides "volcano observatories and Volcanic Ash Advisory Centers (VAACs) around the globe with activity alerts, and useful satellite imagery" [CONFIRMED: https://www.nesdis.noaa.gov/news/airlines-observatories-and-others-keep-tabs-volcanic-activity-volcat, accessed 2026-10-10].

## Conflicts with our idea

1. **The Indonesian ash data-fusion layer is already built, live and open source (Sebaran Abu Gunung Api, AshMap, Pantau Abu).** — **SERIOUS.** The demo moment "the SIGMET, VONA and VAAC texts disagreeing on the right rail" plus Himawari Ash RGB and winds already exists on a public site refreshed every 15 minutes, built in September 2026 by a volunteer (`rezzzq/abu-gunung-api`). A judge who knows these will not credit side-by-side display. What must change: the claim must be the reconciliation output (one hazard area with stated confidence, cited sources and named disagreements) and the per-flight decision, never the feed fusion. Name these projects on the "existing solutions" slide and say what TEPHRA adds.
2. **Live aircraft x SIGMET intersection with an LLM-written per-flight warning is a hackathon commodity (MeteoWatch 2024 category winner; AeroGuard 2026 re-submission).** — **SERIOUS** for the Innovation criterion, not fatal. What must change: do not present aircraft projection or "AI-written warning" as novel; present the ash-specific reconciliation and the continue/hold/reroute/divert decision with minutes and fuel.
3. **WrightWay (4 Oct 2026) already shows a dispatcher console that handles volcanic ash, ranks options deterministically, has an LLM explain, and requires dispatcher approval.** — **SERIOUS** for the "human-gated dispatcher advisory" claim. Differences that hold: North Atlantic not APAC, one simulated flight, ash taken as a fixed 50 nm buffer around one SIGMET, no reconciliation, Grok not Gemini. What must change: lead with APAC live feeds and the reconciliation; adopt WrightWay's grounding rule (reject any number or airport code not present in tool output) so a judge cannot say ours is less safe.
4. **A deterministic union of polygons already satisfies "never shrink below the official polygon" without an LLM.** — **SERIOUS** for Technical Merit's "Does the use of Gen AI contribute directly". Sebaran Abu Gunung Api already resolves its two VAAC mirrors with "newest wins" code. What must change: show at least one live case where the union is not enough and Gemini's reading changes the output, e.g. a VONA eruption with "Ash-cloud is not observed" against a VAAC `EST` cloud with "VA NOT IDENTIFIABLE ... DUE TO MET CLOUD" (2026-10-09, Semeru), or a VONA-only eruption with no VAAC yet (the HYPOTHESIS cone). Keep the union as the floor in code and let Gemini only widen, time-extend and annotate.
5. **Commercial products already sell AI ash detection (Weathernews since 2021-04-26), meteorologist-compiled multi-source ash briefs (TWC HOTL PDFs: SIGMETs, wind barbs, satellite imagery) and dispatch-facing ash route scoring (FlySafe Fleet Monitor).** — **MINOR** for a hackathon, **SERIOUS** if the deck claims "first". What must change: never say "first AI to see ash" or "first to combine sources"; say "per-flight, provenance-stamped draft produced in minutes from public feeds, for a dispatcher who does not have a meteorologist on shift".
6. **Automated infrared ash detection over Indonesia is noisy.** Sebaran Abu Gunung Api's public log shows a median 0.14% of split-window ash candidates inside VAAC zones over 209 scans. — **MINOR** (it is a different detector from Gemini and does not test Gemini). It supports the pack's existing rule that the satellite picture is support only. What must change: nothing new; keep Gemini's satellite reading as evidence with a stated confidence, never as the source of a cone on its own.
7. **The pack's description of the Gemini 3 winners is partly wrong.** Globot's README says default demos use mock and synthetic data; Aegis runs on a scripted dataset. — **NONE** for the idea; **MINOR** for the deck. What must change: drop "the pattern that won Gemini 3 ... on real feeds" phrasing about Globot; the honest line is "both top Gemini 3 entries ran on simulated data; ours runs on public live feeds".
8. **AeroGuard does not use Gemini.** — **NONE** for the idea; the pack's "Build with Gemini XPRIZE entry" wording should not be read as "someone already built this on Gemini".
9. **MAGMA may block datacenter IPs.** Pantau Abu reports ESDM's WAF returning 403 to many datacenter IPs across all ESDM domains; Sebaran Abu Gunung Api fetched MAGMA successfully from GitHub Actions at 2026-10-09T15:30Z; I fetched a VONA page directly with HTTP 200 from this machine. — **MINOR to SERIOUS** for the build, depending on Cloud Run egress. What must change: test a MAGMA fetch from Cloud Run on day one; keep the 48-hour last-good cache the pack already plans; if blocked, read VONA fields from a second path (for example the public VONA page cached by a scheduled job outside Cloud Run) and say so.

## What this supports

- No GitHub repository found by name/description search pairs an LLM with volcanic ash: the queries "volcanic ash gemini", "volcanic ash llm", "volcanic ash sigmet" and "vaac parser" each returned 0 repositories, and the 25 most recently updated of the 73 results for "volcanic ash" (the ones I read) contain no LLM project [CONFIRMED: https://api.github.com/search/repositories?q=volcanic%20ash%20gemini (and the other queries in the search log), accessed 2026-10-10]. GitHub code search was not run.
- The Devpost project search for "volcanic ash" returned only WrightWay as an aviation project; "VAAC" returned no ash project; "SIGMET" returned MeteoWatch, AeroGuard and IceSight [CONFIRMED: https://devpost.com/software/search?query=volcanic+ash, ?query=VAAC, ?query=SIGMET, read 2026-10-10 before the search budget ran out; first results page only].
- Every Indonesian ash project found stops at display. AshMap leaves the reader to compare sources that "can disagree"; Pantau Abu uses the SIGMET only as confirmation; Sebaran Abu Gunung Api reconciles only two mirrors of the same VAAC product by "newest wins" [CONFIRMED: the three READMEs and latest.json, accessed 2026-10-10]. The reconciliation step is open.
- Live, official, public contradictions occur on ordinary days: on 2026-10-09 the Semeru VONA at 1334Z reported an eruption with "Ash-cloud is not observed" while Darwin VAAC 2026/1156 carried an estimated cloud to FL150 [CONFIRMED for the VONA: MAGMA URL above; REPORTED for the VAAC: latest.json]. That is the demo case the pack wanted, with a fresh date.
- Airlines already pay for ash detection and ash briefs (Weathernews, TWC, FlySafe pricing), which supports the Impact criterion: the user and the job exist [CONFIRMED: the three product pages, accessed 2026-10-10].
- The WrightWay and `flight-dispatch-agent` pattern (deterministic numbers, LLM phrasing, reject unsupported numbers) is a ready-made safety design to cite and adopt [CONFIRMED: https://devpost.com/software/wrightway and https://github.com/shuvam-sinha/flight-dispatch-agent, accessed 2026-10-10].
- The two top Gemini 3 Hackathon entries ran on mock or simulated data, so running on public live feeds is a real differentiator in front of Google judges [CONFIRMED: Globot and Aegis READMEs, accessed 2026-10-10].

## The remaining open gap (deck paragraph)

Public projects already cover each half of TEPHRA separately. Volunteer maps in Indonesia (AshMap, Sebaran Abu Gunung Api, Pantau Abu) put the Darwin VAAC ash polygons, MAGMA volcano notices, Himawari ash imagery and winds side by side and leave the reader to compare them; hackathon tools (MeteoWatch, 2024; WrightWay, October 2026) intersect an official SIGMET box with aircraft and have a language model phrase a warning or explain a diversion that a human approves; Weathernews, The Weather Company and FlySafe sell ash detection, meteorologist-compiled briefs and route scores. In a search of GitHub, Devpost and the web on 10 October 2026 we found no project, paper or product that takes the official sources at the moment they disagree, such as a volcano notice reporting an eruption with "ash-cloud not observed" while the ash centre estimates ash to 15,000 ft, and turns them into one hazard area that states its confidence, cites each source and never shrinks below the official polygon, and then drafts a continue, hold, reroute or divert decision for each live aircraft for a dispatcher to approve. That reconciliation-to-decision step, on live Asia-Pacific feeds, is the gap TEPHRA fills.

## Open questions

2. Does a MAGMA VONA fetch succeed from Cloud Run egress IPs (Pantau Abu reports WAF 403s for many datacenter IPs)?
5. arXiv, Google Scholar, Hugging Face, Kaggle and Zenodo were not searched for LLM / vision-language work on volcanic ash or SIGMETs; the pack's "0 papers" and EGU26-560 claims remain unverified.
6. GitHub code search (authenticated) for strings such as `VA CLD` + `genai`, `VONA` + `gemini`, `OBS VA CLD` + `openai` was not run; a repo with a generic name could still contain such code.
7. Which hackathon FlightFixer (Gemini + ADK airline disruption on Cloud Run) was submitted to, and did it place? If it was a Google event, judges may have seen "Gemini + ADK airline ops" already.
8. Was Globot's submitted version (Feb 2026) running on mock data as its August 2026 README says, or did it use live feeds at judging time?
9. Can Gemini, in one call, state the reason behind a VONA/VAAC disagreement correctly (e.g. night seismic detection vs model estimate) on 5 real and 5 quiet cases? This is the test the pack scheduled for 8-9 October; no result is recorded in the pack.

## Sources

All accessed 2026-10-10 unless marked otherwise.

- https://github.com/mzmznasipadang/ash-map (README, package.json, tree via api.github.com)
- https://ash-map-blush.vercel.app/en
- https://github.com/kusumaindraputra/monitoring-abu (README)
- https://github.com/tuttinator/volcano-vis (README, tree)
- https://caleb-tutty.com/posts/indonesia-volcanic-ash
- https://github.com/vance1028/ashfallcorridor-base (README, tree)
- https://github.com/andyprata/volcanic-ash-ml (README, tree)
- https://arxiv.org/abs/2307.12970 and https://export.arxiv.org/api/query?id_list=2307.12970
- https://github.com/martanto/magma-vona (README, pyproject.toml, tree)
- https://github.com/metno/fetch-vaa
- https://github.com/ryo-a/node-vaa
- https://devpost.com/software/meteowatch-the-aeroguard-ai (read via r.jina.ai)
- https://github.com/bharad07-cyber/AeroGruard-AI--MeteoWatch
- https://devpost.com/software/dajoma (read via r.jina.ai)
- https://github.com/MeteoWatch/MeteoWatch
- https://devpost.com/software/wrightway (read via r.jina.ai)
- https://github.com/trisharaichura/WrightWay (engine/hazards.py, sim/README.md, tree)
- https://devpost.com/software/geosentinel-k9pn53 (read via r.jina.ai)
- https://devpost.com/software/globot-341w9q (read via r.jina.ai)
- https://github.com/Vector897/Globot
- https://devpost.com/software/aegis-autonomous-multi-agent-crisis-command (read via r.jina.ai)
- https://github.com/iamdanishm/aegis
- https://gemini3.devpost.com/
- https://gemini3.devpost.com/rules
- https://github.com/rezzzq/abu-gunung-api (README, package.json, scripts/requirements.txt, docs/superpowers/specs/2026-09-06-ash-signal-design.md, data/signal-log.jsonl)
- https://abu-gunung-api.netlify.app and https://abu-gunung-api.netlify.app/data/latest.json
- https://magma.esdm.go.id/v1/vona/22887?signature=93c59312d91d519eed68595447535f902adcdbd3925b7756c08033f8a25273cc
- https://github.com/hikgum-ops/awas-abu
- https://github.com/songhan89/sigmet-wiw2-gemini and https://songhan89.github.io/sigmet-wiw2-gemini/
- https://github.com/MendozaVolcanic/goes-volcanic-monitoring
- https://github.com/shuvam-sinha/flight-dispatch-agent
- https://github.com/apifyforge/aviation-safety-risk-mcp
- https://github.com/Shlok266/drone-replanner
- https://github.com/RozainMalik/Airline-fuel-optimizing-Agent
- https://github.com/emeritusdax82/Volcanic-Ash-Observation
- https://devpost.com/software/world-s-first-ai-driven-geospatial-data-modeling-recommender-i2c3z9 (FlightFixer, read via r.jina.ai)
- https://devpost.com/software/hackon-team (AeroTwin AI, read via r.jina.ai)
- https://devpost.com/software/icesight (read via r.jina.ai)
- https://devpost.com/software/dispatch-z5wdxg (read via r.jina.ai)
- https://devpost.com/software/search?query=volcanic+ash, ?query=VAAC, ?query=volcano+aviation, ?query=airline+dispatch, ?query=flight+dispatcher, ?query=SIGMET (read via r.jina.ai)
- https://api.github.com/search/repositories (20 queries, listed in the search log)
- https://global.weathernews.com/news/16070/
- https://www.weathercompany.com/blog/volcanic-ash-and-aviation-safety-protecting-planes-passengers/
- https://www.flysafe.zone/tools/volcanic-ash-map/
- https://www.nesdis.noaa.gov/news/airlines-observatories-and-others-keep-tabs-volcanic-activity-volcat
- Search-result-only (not opened): https://www.opportunitiescircle.com/google-cloud-ai-builder-cup/, https://opportunitiesradar.com/google-ai-builder-cup-2026/, https://www.eventbrite.com/e/ai-builder-cup-tickets-2001509747534, https://www.sciencedirect.com/science/article/pii/S0377027324000386, https://doi.org/10.3390/s21041359, https://ui.adsabs.harvard.edu/abs/2021AGUFM.A14I..04N/abstract, https://www.icao.int/sites/default/files/APAC/Documents/edocs/APAC-Regional-SIGMET-Guide-11th-edition_MET_SG28_vSubmitted.pdf
- research/prior/board-tephra-pack.json (prior-work pack, read as hypotheses)

## Search log

**WebSearch (extended), 3 run, 3 refused (budget exhausted):**
2. `volcanic ash large language model aviation advisory SIGMET VAAC` — ICAO/NOAA guidance; no LLM work.
3. `Gemini volcanic ash satellite image detection` — ML/CNN detection papers; nothing on Google Gemini.

**GitHub repository search API (unauthenticated, sorted by last update), 20 run:** `volcanic ash sigmet` (0), `vaac parser` (0), `volcanic ash advisory` (5), `vona volcano` (0), `himawari ash` (3), `volcanic ash gemini` (0), `volcanic ash llm` (0), `ash dispersion api` (0), `flight dispatch llm` (3), `dispatcher copilot aviation` (0), `ads-b sigmet` (0), `aviation weather llm` (10), `aviation weather agent` (17), `adk aviation` (1), `sigmet gemini` (1), `volcanic ash aviation` (1), `volcanic ash` (73), `VAAC` (139, almost all unrelated "VAACT"/name collisions), `flight operations gemini` (4), `airline dispatch` (28).

**Devpost project search (via r.jina.ai, before the budget notice), 6 run, first page only:** `volcanic ash`, `VAAC`, `volcano aviation`, `airline dispatch`, `flight dispatcher`, `SIGMET`.

**Not run (budget or authentication):** GitHub code search; Devpost searches for `"Gemini" aviation weather`, `Google Cloud hackathon aviation`, `flight operations`; arXiv / Google Scholar topic searches; Kaggle; Hugging Face; Zenodo; LinkedIn / X.

Total searches run: 29 (3 web + 20 GitHub + 6 Devpost). Direct page, file and API fetches of known URLs are listed under Sources and are not counted as searches.
