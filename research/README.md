# TEPHRA research

Research on TEPHRA collected on 2026-10-09/10. The files were produced by parallel research passes; the key claims in each were checked by two independent verifiers (a source check and a recency/counter-evidence check). The results are in each file's "Verification log". **Where a verification log lists a correction, it overrides the text above it.** Tags: `[CONFIRMED: url]` (opened by the writer), `[CONFIRMED-X2: url]` (held under both checks), `[REPORTED: url]` (secondary source), `[UNVERIFIED]`.

Start with **`CONFLICTS.md`** (everything that conflicts with the idea, graded), then **`../docs/DECISION-MEMO.md`** (what to do), then **`AKASH-ANSWERS.md`** (the point-by-point check of Akash's 10 Oct notes).

**Update, 10 Oct (data hunt).** Seven passes catalogued every usable data source; the results are in **`17-data-sources.md`**. They correct several claims below. Each correction is dated, and the superseded wording is struck through rather than deleted. The research files themselves are left as written. Before the repo is made public, read **`../docs/DATA-LICENCES.md`**: some raw files in `research/data/` may not be republished.

## Index

| File | What it covers | Top facts |
|---|---|---|
| `00-prior-work.md` | Every earlier TEPHRA decision, score, architecture and objection (25 Sep – 10 Oct), with contradictions between agents | Scores moved 83 → 75 → 83.5 with no new fact about TEPHRA; no Gemini call or code ever existed before 10 Oct; Akash's last written line was "DO NOT START" without a plume test |
| `01-news-2026.md` | 2026 ash disruption news (JAPAC first) and news that could undercut the idea | Krakatau closed CGK and 7 other airports on 6–8 Sep (~2,961 flights, ~341,000 people); the VONA said "Ash-cloud is not observed" while BMKG issued 39 SIGMETs; ~~QVA becomes due from all VAACs on 26 Nov 2026~~ QVA is *recommended* for all VAACs from 26 Nov 2026 (corrected 10 Oct, file 17) |
| `02-history-and-costs.md` | 1982–2025 history, costs and documented source disagreements | 2010 cost: IATA >US$1.7 bn; Kelut 2014: an airliner flew through ash satellites could not see (9 ± 3 mg/m³); many historical "contradictions" are datum or altitude-band artefacts |
| `03-prior-art-products.md` | Commercial products graded for overlap | Jeppesen Stratosphere/Airflow and TWC already do AI per-flight drafts with approval; ICAO Doc 9974 §2.4(d) requires operators to resolve conflicts among sources; no product does LLM reconciliation with a never-shrink floor |
| `04-prior-art-oss-and-research.md` | OSS, hackathon entries and papers | `rezzzq/abu-gunung-api` fuses Indonesian ash sources live (no LLM); MeteoWatch/AeroGuard and WrightWay re-checked; Globot and Aegis ran on mock/seeded data |
| `05-feeds-verified.md` | Every feed fetched by curl, with status, licence and break risk | AWC SIGMET JSON and NWS tgftp VAA text are keyless and public domain; MAGMA forbids crawling; OpenSky needs a licence; WAAF had a VA SIGMET in 59/59 samples. Corrected 10 Oct: GIBS does have a TROPOMI SO2 layer (file 17, M2) |
| `06-rules-terms-and-limits.md` | Google terms, Gemini limits, aviation law | High Risk Activities names ATC (no human-in-loop exception); 3.8 Flash ~20 RPD reported; roster closes 11 Oct; ADK uses `GOOGLE_GENAI_USE_ENTERPRISE` |
| `07-domain-dispatch-and-ash-science.md` | Primer: IAVW, VAA/SIGMET/VONA formats, airline practice, ash science, 24 build rules | EASA GM3 asks operators to resolve conflicts and check airborne aircraft; disagreements are mostly about evidence labels, not geometry; 3D exposure classes and 2,000 ft buffers |
| `08-competition-fit.md` | Judging, theme, judge questions, storyboard, deck | Recommended theme Sustainability & Social Impact; likely score ~66 as shipped vs ~80 with a backtest and evals; the gap is proof |
| `09-live-state-and-replay-cases.md` | What is erupting now, probability for 18 Oct / 4 Dec, replay cases | P(APAC VA product open) ≈ 97–99%; best replay Krakatau 5–7 Sep but ~~its SIGMETs are gone~~ its SIGMETs are in the IEM NOAAPort archive (corrected 10 Oct, file 17, R1); 59/83 Fukuoka SIGMETs have no polygon. Corrected 10 Oct: Badan Geologi lowered Anak Krakatau to Level II on 21 Sep (file 17, L6) |
| `10-gemini-capability-and-architecture-check.md` | Can Gemini do the two jobs; is the stack right; 10-case test protocol | Drafting is low risk; ash reading untested and high risk; one Cloud Run service + one Scheduler job; Tokyo VAAC labelled archive for the test |
| `12-himawari-raw-split-window.md` | Raw Himawari access, licence, segments, readers, BTD science | Free on AWS; Java = segment S0610; numpy read+calibrate 0.15 s; BTD silent at Semeru on both dates (moist tropics) |
| `13-contradiction-cases-reverified.md` | Akash's two days re-checked from archives | 25 Sep = LAG + ENVELOPE; 7 Oct = night/fog non-observation; real mismatch 23–27 Sep: VONAs N/NE vs SIGMETs SE, simultaneous. 10 Oct: an observed sounding backs the SIGMET's SE at plume height (file 17, E9) |
| `14-contradiction-census-30-days.md` | 30-day census of VONA vs VAA vs SIGMET (data + parser in `data/census/`) | 28/92 Semeru ash reports point outside the official area at 10 km; VAA lag median 228 min; SIGMETs copy the VAA (489/492) |
| `15-dispatcher-reality.md` | What dispatchers and OCCs must do; where the pain is | No rule says "follow the cautious product"; the airline must resolve conflicts; no first-hand "struggling" account found; Mulder 2017: staff "only ever increase their no-fly zones" |
| `16-globot-and-shared-links.md` | Globot/Aegis, the DeepSeek link, the "decision layer" framing vs prior art | Globot = "High-Fidelity Mock"; decision layer occupied by Lido/Jeppesen/TWC; only cited reconciliation is open |
| `17-data-sources.md` | Every data source the 10 Oct data hunt verified, grouped by use (live feeds, replay archives, map layers, evaluation sets, pitch evidence), with licences quoted, what the build uses, and rejected sources | Krakatau 5–7 Sep is rebuildable (IEM SIGMETs, BoM VAAs, METAR VA ×69 at CGK); open ADS-B is blind at Semeru but sees Jakarta; a sounding backs the Semeru SIGMET; DGCA circular SE-DJPU 15/2026; BoM FTP files may not be republished |
| `CONFLICTS.md` | All conflicts, graded, with fixes; what supports the idea; net position | No FATAL; narrowed claim |
| `AKASH-ANSWERS.md` | Point-by-point answers plus a paste-ready message | — |
| `prior/` | Verbatim copies of the earlier board and Akash material | Hypotheses, not facts |
| `data/` | Census raw data, parser and outputs; Himawari probe scripts and BTD images | Reproducible numbers. Some raw files (BoM FTP texts, BoM and MAGMA pages) may not be republished: see `../docs/DATA-LICENCES.md` |

## Claims register (what the deck and video may rely on)

Rows 1–25 date from the first research pass. Rows 26–45 were added on 10 Oct from the data hunt (`17-data-sources.md` gives each source and how it was checked). A struck-through claim must not be used. Its replacement follows it in the same row.

| # | Claim | Source | Status |
|---|---|---|---|
| 1 | Anak Krakatau ash closed Soekarno-Hatta and 7 other airports, 6–8 Sep 2026; first full closure in CGK's history | 01 | Confirmed (news + ministry figures) |
| 2 | ~2,961 flights and ~341,000 people affected | 01, 08 | Confirmed (ABC citing transport ministry) |
| 3 | During it, MAGMA's only VONA (2026KRA026, RED, 5 Sep 02:00Z) said "Ash-cloud is not observed"; next VONA 74.5 h later | 01, 09 | Confirmed |
| 4 | In 30 days to 9 Oct, 28 of Semeru's 92 observatory ash reports pointed where the official area did not reach 10 km from the vent | 14 | Measured (our parser; reproducible) |
| 5 | Median 228 min (p90 463) for a Darwin VAA to reflect a new Semeru VONA | 14 | Measured |
| 6 | 23–27 Sep: every Semeru SIGMET MOV SE vs 20 VONAs N/NE, simultaneous. *10 Oct:* an observed sounding later supported the SIGMET's SE at plume height (#37), so say "they disagreed", never "the VONA was right" | 13, 17 | Confirmed (two rounds) |
| 7 | Indonesian SIGMETs copy the Darwin VAA (top match 489/492) | 14 | Measured |
| 8 | 87 of 112 Sakurajima/Mayon/Kanlaon/Taal VA SIGMETs had no drawable area | 14 | Measured |
| 9 | ICAO Doc 9974 §2.4(d): operator must "reliably and correctly resolve any conflicts that may arise among data sources" | 03, 15 | Confirmed X2 |
| 10 | EASA guidance: find affected aircraft in flight, alert crews, resolve source conflicts | 07, 15 | Confirmed |
| 11 | Mulder et al. 2017: ops staff "only ever increase their no-fly zones" | 15 | Confirmed |
| 12 | 2010 Eyjafjallajökull: IATA >US$1.7 bn lost airline revenue | 02 | Confirmed |
| 13 | Kelut 2014: Perth–Jakarta airliner flew through ash satellites could not see (9 ± 3 mg/m³ modelled) | 02 | Confirmed X2 |
| 14 | ~~QVA due from all VAACs on 26 Nov 2026~~ *Corrected 10 Oct:* Annex 3 Amendment 82 *recommends* that all VAACs issue QVA from 26 Nov 2026. London and Toulouse have issued it since late 2025; the other seven VAACs "will not initially supply QVA forecasts". No public Darwin or Tokyo QVA was found | 01, 03, 17 (P10: UK AIC P 157/2025) | Confirmed (AIC P 157/2025) |
| 15 | Raw Himawari-9 is free on AWS every 10 min; Java is one 2.8 MB segment per band | 12 | Confirmed (fetched). *10 Oct:* the same keys are also on Google Cloud Storage (17, L17) |
| 16 | Split-window showed no ash signal at Semeru on 25 Sep or 7 Oct | 12 | Measured |
| 17 | P(≥1 VA SIGMET/VAA open in Tokyo/Darwin areas at a random moment) ≈ 97–99% | 09 | Estimate from 119 snapshots |
| 18 | gemini-3.8-flash is a stable model with structured output, function calling and image input | 05, 06, 10 | Confirmed (docs) |
| 19 | Free-tier RPD for 3.8 Flash ≈ 20 | 06 | Reported only; check in AI Studio |
| 20 | Google Cloud ToS §3.3(d)(i) names air traffic control as a High Risk Activity | 00, 06 | Confirmed |
| 21 | Jeppesen Airflow: "AI proposes a specific action. A human approves." (agents announced 6 Oct 2026) | 03 | Confirmed |
| 22 | Weathernews AI ash detection in use since 26 Apr 2021 (in-house, feeds ACOS) | 03 | Confirmed (corrected scope) |
| 23 | MAGMA robots.txt `Disallow: /` | 05, 06, 17 | Confirmed (re-checked 10 Oct) |
| 24 | AWC SIGMET history covers only 30 days | 05, 14 | Confirmed (HTTP 400). *10 Oct:* older SIGMETs are in the IEM NOAAPort archive (17, R1) |
| 26 | Indonesia's DGCA circular SE-DJPU 15/2026, in force since 6 Sep 2026: aircraft operators must carry out a safety risk assessment before planning flights into areas ash may affect, and report every ash encounter | 17 (P1: DGCA release of 8 Sep) | Confirmed (press release; the circular's own text was not read). Do not say it requires software |
| 27 | Sinabung ash closed Kualanamu (KNO) on 1 Sep 2026 under NOTAM A3250/26: 45 flights cancelled, 6 rescheduled | 17 (P1: DGCA release of 2 Sep) | Confirmed |
| 28 | Two Indonesian hubs were closed by ash within a week: Kualanamu on 1 Sep and Soekarno-Hatta on 6 Sep | 17, rows 1 and 27 | Confirmed (from rows 1 and 27) |
| 29 | Soekarno-Hatta, 6 Sep (DGCA): closed from 01:30 WIB under NOTAM A3341/26 after a positive paper test at 00:35–01:05 WIB; from 01:30 to 09:30 WIB, 209 movements and 22,798 passengers were affected and 170 aircraft were held on the apron | 17 (P1) | Confirmed (DGCA releases). Quote per-airport numbers: one release's headline total (373) does not match its own breakdown |
| 30 | USGS DS 545, 1953–2009: volcanoes in Indonesia, the Philippines and Japan caused 52 of 129 recorded encounters (40%), 35 of the 79 damaging ones, and 5 of the 9 in-flight engine failures (severity 4: "Temporary engine failure requiring in-flight restart of engine") | 17 (P3) | Measured (our count of Appendix 1B, done twice) |
| 31 | Lewotobi, Nov 2024: 28 of 42 international airlines and 9 of 12 domestic airlines kept flying into Bali; the others did not. Same ash, different airline decisions | 17 (P5: airport GM quoted by VIVA, 14 Nov 2024) | Reported (operator statement via media) |
| 32 | Darwin VAAC workload: 5,885 text bulletins in 2024 and 5,672 in 2025 in BoM's FTP archive, about 16 a day | 17 (R4; 7.2 #11) | Measured (file count; a few are test or pointer messages) |
| 33 | On 7 Sep (~05:53Z) TROPOMI recorded SO2 above 5 DU over about 133,000 km² around Java (peak 55 DU), while Krakatau's latest VONA still said "Ash-cloud is not observed" | 17 (L14, M2) | Measured. SO2 is not ash, and the source volcano is not attributed |
| 34 | NOAA/CIMSS VOLCAT flagged no ash pixels in any of 4 sampled frames (Java 25 Sep and 10 Oct; Philippines on the Taal eruption day, 8 Oct, twice) | 17 (E8) | Measured (4 frames; no positive case in the region found) |
| 35 | The adsb.lol archive shows the closure: 6 Sep 11:00–11:30Z, 0 airborne aircraft within 100 nm of CGK against 59 in the same half-hour on 25 Sep; Manila and Kagoshima were normal | 17 (7.2 #3) | Measured |
| 36 | Open ADS-B is blind at Semeru: on 25 Sep, 11:00–11:30Z, adsb.lol had 0 aircraft within 100 nm of Semeru (nearest 115 nm), against 59 near CGK and 51 near Anak Krakatau. airplanes.live does cover East Java (12–22 aircraft an hour near Semeru) but answers only after an emailed request | 17 (7.2 #4; L10) | Measured. An empty map means "not seen", not "no traffic" |
| 37 | Surabaya radiosonde, 25 Sep 11:30Z (82 km from Semeru): toward 110° at about 3.9 km and 145° at about 4.5 km (plume height); north-east flow only at 700 hPa (3,182 m), below the 3,676 m summit. It supports the SIGMET's SE | 17 (E9) | Measured (re-checked from the file) |
| 38 | Badan Geologi lowered Anak Krakatau from Level III to Level II on 21 Sep 2026 at 18:30 WIB (report 1604.Lap/GL.03/BGL/2026). This conflicts with 09's reading of MAGMA's page (Level III on 10 Oct) | 17 (L6) | Confirmed (Badan Geologi). Check MAGMA's page by hand before stating a level |
| 39 | Semeru's summit elevation: GVP and Darwin 3,657 m, MAGMA 3,676 m, an independent SRTM tile 3,668 m. The differences are within DEM error, so they are never a conflict | 17 (7.2 #10) | Measured |
| 40 | The 5–7 Sep Jakarta FIR VA SIGMETs are archived (IEM NOAAPort): WIIF SIGMETs 01–03 read for 6 Sep 00:00–04:01Z; day files for 5–8 Sep exist | 17 (R1) | Confirmed (sampled) |
| 41 | Soekarno-Hatta's METARs reported VA 69 times, from 5 Sep 18:30Z (01:30 WIB on 6 Sep) to 7 Sep 05:00Z (12:00 WIB) | 01, 17 (R2, R3) | Measured (IEM and NOAA GHCNh agree; upgrades 01's REPORTED) |
| 42 | Between VONA KRA026 (5 Sep 02:00Z) and KRA027 (8 Sep 04:34Z), Darwin issued 28 advisories; 24 put ash at FL500, and the low layer changed direction six times | 17 (7.2 #1) | Measured from BoM FTP files. Cite the counts; do not republish the files |
| 43 | BMKG issued 39 SIGMETs for Anak Krakatau from 4 Sep to the morning of 7 Sep, and AirNav's NOTAM closed eight airports | 01, 17 (P2: BMKG release of 7 Sep) | Confirmed (the count may include cancellations) |
| 44 | NASA GIBS serves a daily TROPOMI SO2 layer (`TROPOMI_L2_Sulfur_Dioxide_Total_Vertical_Column`, from 2018-05-06) | 17 (M2) | Confirmed; corrects 05 §3.12 |
| 45 | The public encounter record since 2009 is mostly European: 113 encounters in 2010–2014, none with engine failure, mostly from EUROCONTROL EVAIR | 17 (P8) | Confirmed (conference slides, not peer-reviewed) |

## Open questions, ranked by how much they matter

Re-ranked on 10 Oct after the data hunt. One earlier question is answered (struck through, at the end).

1. Can Gemini 3.8 Flash grade evidence from VAA remarks and VONA prose reliably, and what is the false-flag rate? (Needs a personal key; protocol in `10-…md`.)
2. What are the real free-tier RPD/RPM for `gemini-3.8-flash` and `gemini-3.5-flash-lite` on a personal AI Studio project?
3. *New 10 Oct.* How will the repo become public: a fresh repository, or this one with its history rewritten? Are the BoM, MAGMA and NICT files out first? `../docs/DATA-LICENCES.md` recommends a fresh repository.
4. *New 10 Oct.* Will airplanes.live grant API access? It is the only open source of East Java traffic found, and only the user can ask (17, L10). Without it, the per-flight moment stays on Jakarta and Krakatau.
5. Will PVMBG grant VONA API access, or does the MAGMA email subscription work fast enough? (10 Oct: WOVO's survey says most observatories send VONAs by email; 17, E5.)
6. Does a MAGMA, adsb.lol or AWC fetch succeed from Cloud Run egress IPs?
7. Can we get one JAPAC dispatcher or OCC quote before 17 Oct (file 15 lists public routes)?
8. Which theme is filed, and is judging per theme or one pool?
9. *New 10 Oct.* Is Anak Krakatau at Level II (Badan Geologi, 21 Sep) or Level III (MAGMA's page as read in 09)? Check by hand.
10. Will Darwin issue any QVA before 4 Dec 2026? (10 Oct: none public. UK AIC P 157/2025 says the other seven VAACs "will not initially supply QVA". The ICAO APAC VAAC report that may say more needs a real browser.)
11. Exact submission cut-off time zone on 18 Oct (submit by 17 Oct regardless).
13. *New 10 Oct.* Which volcano produced the 7 Sep SO2 cloud over Java? It needs trajectories before any causal line in the pitch.
14. *New 10 Oct.* Does Indonesia's I-WISH platform have an airline-facing API that a desk like TEPHRA could feed? Reported only.
15. *New 10 Oct.* Does the WIS2 Singapore SIGMET stream work from Cloud Run (17, L8)?

~~10. What did Darwin's VAAs say on 23–26 Sep (texts not retrieved), and where is a public archive of the 5–7 Sep Krakatau SIGMETs?~~ *Answered 10 Oct:* BoM's anonymous FTP holds every Darwin VAA since 2022 (private use only; 17, R4). The IEM NOAAPort archive holds the SIGMETs and the FV relay of the same VAAs (17, R1).

## How to refresh this research

- **Live state:** `curl 'https://aviationweather.gov/api/data/isigmet?format=json&hazard=va'` (de-duplicate "F" series), `https://tgftp.nws.noaa.gov/data/raw/fv/` (all VAAs), adsb.lol `/v2/point/{lat}/{lon}/{nm}`.
- **Census:** re-run `data/census/census.py` over fresh downloads (manifest format in `data/census/manifest.tsv`); AWC history only covers 30 days.
- **Archives (10 Oct):**
  - SIGMETs older than 30 days: IEM NOAAPort (`scripts/record_replay.py noaaport`).
  - Darwin VAAs: BoM's anonymous FTP, for private use only.
  - Past ADS-B: adsb.lol `globe_history`.
  - Soundings: NOAA IGRA2.
  - METAR VA: IEM or NOAA GHCNh.

  Details and licences are in `17-data-sources.md`.
- **Prior art:** re-search Devpost/GitHub for "volcanic ash" + gemini/LLM/dispatch, Jeppesen Airflow release notes, TWC Maverick, `rezzzq/abu-gunung-api` activity.
- **Licences:** before publishing anything new, check it against `../docs/DATA-LICENCES.md`.
- The Claude Code skill `.claude/skills/tephra-research-refresh` walks through this.
