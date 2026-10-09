# TEPHRA research

Research on TEPHRA collected on 2026-10-09/10. The files were produced by parallel research passes; the key claims in each were checked by two independent verifiers (a source check and a recency/counter-evidence check). The results are in each file's "Verification log". **Where a verification log lists a correction, it overrides the text above it.** Tags: `[CONFIRMED: url]` (opened by the writer), `[CONFIRMED-X2: url]` (held under both checks), `[REPORTED: url]` (secondary source), `[UNVERIFIED]`.

Start with **`CONFLICTS.md`** (everything that conflicts with the idea, graded), then **`../docs/DECISION-MEMO.md`** (what to do), then **`AKASH-ANSWERS.md`** (the point-by-point check of Akash's 10 Oct notes).

## Index

| File | What it covers | Top facts |
|---|---|---|
| `00-prior-work.md` | Every earlier TEPHRA decision, score, architecture and objection (25 Sep – 10 Oct), with contradictions between agents | Scores moved 83 → 75 → 83.5 with no new fact about TEPHRA; no Gemini call or code ever existed before 10 Oct; Akash's last written line was "DO NOT START" without a plume test |
| `01-news-2026.md` | 2026 ash disruption news (JAPAC first) and news that could undercut the idea | Krakatau closed CGK and 7 other airports on 6–8 Sep (~2,961 flights, ~341,000 people); the VONA said "Ash-cloud is not observed" while BMKG issued 39 SIGMETs; QVA becomes due from all VAACs on 26 Nov 2026 |
| `02-history-and-costs.md` | 1982–2025 history, costs and documented source disagreements | 2010 cost: IATA >US$1.7 bn; Kelut 2014: an airliner flew through ash satellites could not see (9 ± 3 mg/m³); many historical "contradictions" are datum or altitude-band artefacts |
| `03-prior-art-products.md` | Commercial products graded for overlap | Jeppesen Stratosphere/Airflow and TWC already do AI per-flight drafts with approval; ICAO Doc 9974 §2.4(d) requires operators to resolve conflicts among sources; no product does LLM reconciliation with a never-shrink floor |
| `04-prior-art-oss-and-research.md` | OSS, hackathon entries and papers | `rezzzq/abu-gunung-api` fuses Indonesian ash sources live (no LLM); MeteoWatch/AeroGuard and WrightWay re-checked; Globot and Aegis ran on mock/seeded data |
| `05-feeds-verified.md` | Every feed fetched by curl, with status, licence and break risk | AWC SIGMET JSON and NWS tgftp VAA text are keyless and public domain; MAGMA forbids crawling; OpenSky needs a licence; WAAF had a VA SIGMET in 59/59 samples |
| `06-rules-terms-and-limits.md` | Google terms, Gemini limits, aviation law | High Risk Activities names ATC (no human-in-loop exception); 3.8 Flash ~20 RPD reported; roster closes 11 Oct; ADK uses `GOOGLE_GENAI_USE_ENTERPRISE` |
| `07-domain-dispatch-and-ash-science.md` | Primer: IAVW, VAA/SIGMET/VONA formats, airline practice, ash science, 24 build rules | EASA GM3 asks operators to resolve conflicts and check airborne aircraft; disagreements are mostly about evidence labels, not geometry; 3D exposure classes and 2,000 ft buffers |
| `08-competition-fit.md` | Judging, theme, judge questions, storyboard, deck | Recommended theme Sustainability & Social Impact; likely score ~66 as shipped vs ~80 with a backtest and evals; the gap is proof |
| `09-live-state-and-replay-cases.md` | What is erupting now, probability for 18 Oct / 4 Dec, replay cases | P(APAC VA product open) ≈ 97–99%; best replay Krakatau 5–7 Sep but its SIGMETs are gone; 59/83 Fukuoka SIGMETs have no polygon |
| `10-gemini-capability-and-architecture-check.md` | Can Gemini do the two jobs; is the stack right; 10-case test protocol | Drafting is low risk; ash reading untested and high risk; one Cloud Run service + one Scheduler job; Tokyo VAAC labelled archive for the test |
| `12-himawari-raw-split-window.md` | Raw Himawari access, licence, segments, readers, BTD science | Free on AWS; Java = segment S0610; numpy read+calibrate 0.15 s; BTD silent at Semeru on both dates (moist tropics) |
| `13-contradiction-cases-reverified.md` | Akash's two days re-checked from archives | 25 Sep = LAG + ENVELOPE; 7 Oct = night/fog non-observation; real mismatch 23–27 Sep: VONAs N/NE vs SIGMETs SE, simultaneous |
| `14-contradiction-census-30-days.md` | 30-day census of VONA vs VAA vs SIGMET (data + parser in `data/census/`) | 28/92 Semeru ash reports point outside the official area at 10 km; VAA lag median 228 min; SIGMETs copy the VAA (489/492) |
| `15-dispatcher-reality.md` | What dispatchers and OCCs must do; where the pain is | No rule says "follow the cautious product"; the airline must resolve conflicts; no first-hand "struggling" account found; Mulder 2017: staff "only ever increase their no-fly zones" |
| `16-globot-and-shared-links.md` | Globot/Aegis, the DeepSeek link, the "decision layer" framing vs prior art | Globot = "High-Fidelity Mock"; decision layer occupied by Lido/Jeppesen/TWC; only cited reconciliation is open |
| `CONFLICTS.md` | All conflicts, graded, with fixes; what supports the idea; net position | No FATAL; narrowed claim |
| `AKASH-ANSWERS.md` | Point-by-point answers plus a paste-ready message | — |
| `prior/` | Verbatim copies of the earlier board and Akash material | Hypotheses, not facts |
| `data/` | Census raw data, parser and outputs; Himawari probe scripts and BTD images | Reproducible numbers |

## Claims register (what the deck and video may rely on)

| # | Claim | Source | Status |
|---|---|---|---|
| 1 | Anak Krakatau ash closed Soekarno-Hatta and 7 other airports, 6–8 Sep 2026; first full closure in CGK's history | 01 | Confirmed (news + ministry figures) |
| 2 | ~2,961 flights and ~341,000 people affected | 01, 08 | Confirmed (ABC citing transport ministry) |
| 3 | During it, MAGMA's only VONA (2026KRA026, RED, 5 Sep 02:00Z) said "Ash-cloud is not observed"; next VONA 74.5 h later | 01, 09 | Confirmed |
| 4 | In 30 days to 9 Oct, 28 of Semeru's 92 observatory ash reports pointed where the official area did not reach 10 km from the vent | 14 | Measured (our parser; reproducible) |
| 5 | Median 228 min (p90 463) for a Darwin VAA to reflect a new Semeru VONA | 14 | Measured |
| 6 | 23–27 Sep: every Semeru SIGMET MOV SE vs 20 VONAs N/NE, simultaneous | 13 | Confirmed (two rounds) |
| 7 | Indonesian SIGMETs copy the Darwin VAA (top match 489/492) | 14 | Measured |
| 8 | 87 of 112 Sakurajima/Mayon/Kanlaon/Taal VA SIGMETs had no drawable area | 14 | Measured |
| 9 | ICAO Doc 9974 §2.4(d): operator must "reliably and correctly resolve any conflicts that may arise among data sources" | 03, 15 | Confirmed X2 |
| 10 | EASA guidance: find affected aircraft in flight, alert crews, resolve source conflicts | 07, 15 | Confirmed |
| 11 | Mulder et al. 2017: ops staff "only ever increase their no-fly zones" | 15 | Confirmed |
| 12 | 2010 Eyjafjallajökull: IATA >US$1.7 bn lost airline revenue | 02 | Confirmed |
| 13 | Kelut 2014: Perth–Jakarta airliner flew through ash satellites could not see (9 ± 3 mg/m³ modelled) | 02 | Confirmed X2 |
| 14 | QVA due from all VAACs on 26 Nov 2026 | 01, 03 | Reported/confirmed (ICAO pages partly blocked) |
| 15 | Raw Himawari-9 is free on AWS every 10 min; Java is one 2.8 MB segment per band | 12 | Confirmed (fetched) |
| 16 | Split-window showed no ash signal at Semeru on 25 Sep or 7 Oct | 12 | Measured |
| 17 | P(≥1 VA SIGMET/VAA open in Tokyo/Darwin areas at a random moment) ≈ 97–99% | 09 | Estimate from 119 snapshots |
| 18 | gemini-3.8-flash is a stable model with structured output, function calling and image input | 05, 06, 10 | Confirmed (docs) |
| 19 | Free-tier RPD for 3.8 Flash ≈ 20 | 06 | Reported only; check in AI Studio |
| 20 | Google Cloud ToS §3.3(d)(i) names air traffic control as a High Risk Activity | 00, 06 | Confirmed |
| 21 | Jeppesen Airflow: "AI proposes a specific action. A human approves." (agents announced 6 Oct 2026) | 03 | Confirmed |
| 22 | Weathernews AI ash detection in use since 26 Apr 2021 (in-house, feeds ACOS) | 03 | Confirmed (corrected scope) |
| 23 | MAGMA robots.txt `Disallow: /` | 05, 06 | Confirmed |
| 24 | AWC SIGMET history covers only 30 days | 05, 14 | Confirmed (HTTP 400) |

## Open questions, ranked by how much they matter

1. Can Gemini 3.8 Flash grade evidence from VAA remarks and VONA prose reliably, and what is the false-flag rate? (Needs a personal key; protocol in `10-…md`.)
2. What are the real free-tier RPD/RPM for `gemini-3.8-flash` and `gemini-3.5-flash-lite` on a personal AI Studio project?
3. Will PVMBG grant VONA API access, or does the MAGMA email subscription work fast enough?
4. Does a MAGMA, adsb.lol or AWC fetch succeed from Cloud Run egress IPs?
5. Can we get one JAPAC dispatcher or OCC quote before 17 Oct (file 15 lists public routes)?
6. Which theme is filed, and is judging per theme or one pool?
7. Will Darwin issue any QVA before 4 Dec 2026?
8. Exact submission cut-off time zone on 18 Oct (submit by 17 Oct regardless).
10. What did Darwin's VAAs say on 23–26 Sep (texts not retrieved), and where is a public archive of the 5–7 Sep Krakatau SIGMETs?

## How to refresh this research

- **Live state:** `curl 'https://aviationweather.gov/api/data/isigmet?format=json&hazard=va'` (de-duplicate "F" series), `https://tgftp.nws.noaa.gov/data/raw/fv/` (all VAAs), adsb.lol `/v2/point/{lat}/{lon}/{nm}`.
- **Census:** re-run `data/census/census.py` over fresh downloads (manifest format in `data/census/manifest.tsv`); AWC history only covers 30 days.
- **Prior art:** re-search Devpost/GitHub for "volcanic ash" + gemini/LLM/dispatch, Jeppesen Airflow release notes, TWC Maverick, `rezzzq/abu-gunung-api` activity.
- The Claude Code skill `.claude/skills/tephra-research-refresh` walks through this.
