# TEPHRA regulatory-paperwork research: Indonesia SE-DJPU 15/2026, ICAO Doc 9974 SRA, VAR/encounter reporting, Japan and Philippines

Research date 2026-10-11. I did not edit the repo, run project code or use gcloud. I skimmed `research/15-dispatcher-reality.md`, `research/03-prior-art-products.md`, `research/06-rules-terms-and-limits.md` and `data/policy/policy_a.json`. The repo has no existing coverage of SE-DJPU 15/2026, JCAB, CAAP or the VAR form, so those sections are new.

## 0. Headline findings and caveats

- **SE-DJPU 15/2026 exists. I could not get the primary PDF.** The only full account I read is one news article (Penajam News, dated 8 Sep 2026). A search-tool result said the JDIH listing shows it as "Berlaku", dated 6 Sep 2026. I did not verify that listing myself. The hubud.kemenhub.go.id regulations page and its search did not show it, and `jdih.dephub.go.id` refused my connection. Another search pass found no matching circular at all. Treat the circular's text as [REPORTED, secondary source], and have the user pull the PDF before the video claims anything specific.
- **The user's "Doc 9974, 2nd ed." is not confirmed.** Every source I found says First Edition 2012, and a standards catalogue lists it as active. I found no second edition.
- **Clause numbers differ between copies of Doc 9974.** I read the ICAO "unedited advance version", First Edition 2012, as hosted by PreventionWeb. In it the operator duties sit in section 4.1 (a to h) and the volcanic-activity guidance in Appendix E.4. Earlier repo research quoted "§2.4(d)", "§2.5(b)" and "2.10" from the COPAC copy. `policy_a.json` cites `9974-2.10` and `9974-app5-5.4d2`. The wording matches but the numbering does not. Recommendation: cite by title and quote ("Appendix E, End of eruption, ongoing eruption (d)(2)") or re-check the numbers against whichever copy the citation registry uses.
- **Japan and the Philippines:** no operator-SRA circular found for either. Both rely on ICAO Annex 3 and Doc 9974, plus NOTAMs and CAA statements.

## 1. Indonesia: SE-DJPU 15 Tahun 2026

### Identity [REPORTED, secondary source]

- **Title.** "Surat Edaran Direktur Jenderal Perhubungan Udara Nomor SE-DJPU 15 Tahun 2026 tentang Penanganan Dampak Abu Vulkanik terhadap Operasi Penerbangan". Source: https://penajamnews.com/kemenhub-terbitkan-surat-edaran-penanganan-dampak-abu-vulkanik-terhadap-operasi-penerbangan-keselamatan-tetap-menjadi-prioritas-utama/
- **Dates.** The article is dated 8 Sep 2026 22:01. It says the provisions have been in effect since 6 Sep 2026, so they apply retroactively from the date of issue. The ministry will "monitor and evaluate" implementation.
- **Signatory.** The article does not name one. The Director General of Civil Aviation (Lukman F. Laisa, per the article) issues it by virtue of office. Per CLAUDE.md-style honesty: "who signs" for the operator's own SRA is not specified in anything I found.
- **Basis.** The only legal link in the article is the Collaborative Decision Making approach "sebagaimana diatur dalam KP. 153 Tahun 2019".
- **Predecessors.** KP 153/2019 is the DGCA decision on CDM handling of ash impact via I-WISH. SE 15/2019 covers flight operations in force majeure. Source for both: search results citing Kemenhub 2024 coverage (see the bisnis.com 2024 articles, e.g. https://ekonomi.bisnis.com/read/20240112/98/1731716/erupsi-semeru-bandara-abdulrachman-saleh-malang-ditutup-sementara).

### Reported operator requirements (Indonesian wording as relayed by the article, then English)

| Topic | Indonesian quote (from article) | English |
|---|---|---|
| SRA | "operator pesawat udara diwajibkan melakukan Safety Risk Assessment sebelum merencanakan penerbangan" | Operators must do a Safety Risk Assessment before planning flights in areas potentially affected by ash. The result is the basis for continuing, rerouting, or cancelling. |
| Aircraft exposed | "Pesawat yang diduga atau terbukti terpapar abu vulkanik tidak dapat dioperasikan kembali sebelum dilakukan pemeriksaan" | An aircraft suspected or proven exposed may not return to service before inspection and, if needed, thorough cleaning per OEM technical guidance. |
| Reporting | "setiap kejadian paparan abu vulkanik (volcanic ash encounter) ... dilaporkan dan didokumentasikan melalui sistem pelaporan keselamatan" | Every encounter must be reported and documented through the safety reporting system. The data feeds preparedness and procedures. |
| Parked aircraft | (paraphrased in the article) | Aircraft parked at affected airports must be protected and inspected per procedure. |
| Passengers | "Maskapai penerbangan berjadwal wajib melaksanakan penanganan keterlambatan dan gangguan penerbangan" | Scheduled airlines handle delays and disruption (compensation, rerouting, refund, reschedule). |
| Other parties | n/a | Airports monitor ash on runway, taxiway and facilities. AirNav (Perum LPPNPI) monitors airspace and disseminates safety information. BMKG gives ash forecasts. PVMBG gives eruption data. |

The article mentions no deadlines other than the 6 Sep effective date. It also names no SRA template, thresholds or methodology, no named reporting system or form, and no sanctions. Treat all of those as UNVERIFIED.

### Related Indonesian context

- **Reopening conditions.** The transport minister told airlines to inspect the whole fleet. Pilots and crews must know the restricted polygons. Airlines should keep coordinating with airport operators. Source: the second search pass quoting Kemenhub (https://dephub.go.id/post/read/menhub-dudy--sejumlah-bandara-terdampak-abu-vulkanik-gunung-anak-krakatau-kembali-dibuka).
- **I-WISH.** Launched Sep 2018. Participants are the DGCA, airport authority, MET authority, ANSP, airlines and the volcanology agency. It shows ash extent from SIGMET and ASHTAM, affected airports and routes, has an API, and "is capable of documenting activities". It is not described as an encounter-reporting channel. Source: https://unitingaviation.com/news/safety/indonesias-integrated-web-based-aeronautical-information-system-handling/
- **Operator discretion.** A Kemenhub statement on Sinabung ash said airlines have authority to evaluate and assess their operations against actual conditions. [REPORTED, press statement] https://hubud.kemenhub.go.id/berita/4878

### Indonesian incident-reporting route [PARTLY UNVERIFIED]

- CASR 830 history: PM 6/2014 (notification and reporting of accidents and serious incidents), then PM 14/2015, then PM 74/2017. The PM 74/2017 title only mentions investigation procedure, so whether the notification part moved elsewhere is UNVERIFIED. Source: https://peraturan.go.id/files2/permenhub-no-pm+74-tahun-2017_terjemah.pdf
- A DGCA safety bulletin says Mandatory Occurrence Reports for AOC 121 and AOC 135 are required by CASR 830 and CASR Part 19 (https://hubud.kemenhub.go.id/hubud/website/assets/file/bulletinresponse/RESPONSE%20Vol%20III.pdf).
- PM 6/2014 delegates details to a DGCA regulation and a KNKT chairman regulation. The "72 hour" figure appeared only in an EU glossary, so it is NOT confirmed for Indonesia. Do not use it.
- The ICAO post-flight VAR goes to the VAAC. For Darwin VAAC the contact is darwin.vaac@bom.gov.au (https://skybrary.aero/sites/default/files/bookshelf/450.pdf, Doc 9766).

## 2. ICAO Doc 9974 SRA requirements

**Source read.** ICAO "Flight Safety and Volcanic Ash", unedited advance version, First Edition 2012 (https://www.preventionweb.net/files/25588_9974unediteden1.pdf). ICAO's own PDF returned 403 to me.

**Licence.** The foreword says distribution is "encouraged" in a volcanic event but it "may not be offered for sale or used commercially without the written permission from ICAO". Quote briefly and cite. Do not copy appendix text or tables into the public repo.

### Operator duties (section 4.1, verbatim items)

- (b) Have "an identifiable safety risk assessment within its SMS".
- (c) Complete it "before initiating operations" into forecast or contaminated airspace or aerodromes. The CAA evaluates it in normal oversight.
- (d) Satisfy the CAA on information-source accuracy and its own ability "to reliably and correctly resolve any conflicts among data sources".
- (e) Revise it when material changes occur.
- (f) Use type certificate holder (TCH) data on susceptibility and pre-, in- and post-flight precautions.
- (g) Ensure personnel get the relevant pre-flight and in-flight information.
- (h) Report "immediately" to the nearest ATS unit by VAR/AIREP, with a more detailed VAR on landing plus an ASR and AML entry, for (1) any volcanic-cloud incident, (2) any observation of ash activity, and (3) "anytime that volcanic ash is not encountered in an area(s) where it was forecast to be".
- Section 4.2: documented procedures covering flight crew, planners, dispatchers, ops, engineering and maintenance. Sufficient qualified and competent staff. Volcanic-ash exercises.

### Appendix A: process (from Appendix A.2)

1. Identify the hazard.
2. Severity.
3. Probability. Factors are information uncertainty, exposure duration, historic event data, expert judgement and operating environment.
4. Tolerability, classed acceptable or unacceptable.
5. Mitigation to a level acceptable to the Accountable Executive. "Not all risks may be suitably mitigated; in such cases, the operation should not proceed."
6. Repeat after mitigation and at intervals. Records must state assumptions. Mitigations are "completed and verified and supported by evidence prior to the start of operations".

### Appendix B: procedures to consider (headings)

- TCH advice.
- Personnel procedures.
- Enhanced Flight Watch: closely and continuously monitor VAA, VAR/AIREP, SIGMET, NOTAM and ASHTAM.
- Flight planning.
- Departure, destination and alternates: degree of contamination, performance, maintenance, fuel for reroute and holding.
- Routeing policy: the shortest time in or over the area, drift-down and emergency descent.
- Diversion policy: maximum distance from an alternate, alternates outside the area, post-encounter policy.
- MEL relief (a list including packs, bleeds, pressurisation, air data computers, TAWS, autoland and oxygen).
- Crew SOPs.
- AML entry.
- Incident reporting (VAR in flight, VAR post-flight, non-encounters, mandatory occurrence report).
- Maintenance procedures.

### Other appendices

- **Appendix C:** hazard and risk table by process, for example "Hazard #1 Information on ash concentration not properly communicated". The columns are existing and additional defences, the unsafe event "Inadvertent volcanic ash encounter", intermediate consequences (probe blockage, windscreen abrasion, turbine damage) and recovery measures.
- **Appendix D:** worksheet with columns Hazard description, Consequence, Existing controls, Severity, Probability, Risk tolerability, Further actions, then post-mitigation Severity and Probability.
- **Appendix E:** eruption-phase guidance.
  - Start of eruption: crews initiate or accept reroutes. Actions are to find which aircraft are affected and alert the crew, alert management, brief crew and revise fuel, and gather data.
  - Ongoing: monitor VAAC, SIGMET and NOTAM as a minimum. Use other sources the operator considers accurate and "carefully consider and resolve differences or conflicts ... notably between published information and observations". If no graduation is given, treat the whole area as high contamination "unless the operator's safety risk assessment allows it to do otherwise safely". Treat the danger area like mountainous terrain for overflight.
  - Require crew reports from in or near areas.
- **Appendix F:** CAA evaluation criteria. The operator must demonstrate it understands the hazards, is clear where risk limits are exceeded, applies mitigations including suspension, has robust procedures, chooses and interprets sources and resolves conflicts, uses TCH data, and has competent staff.
- **Appendix G:** CAA matrix. The operation (operator, AOC number, aircraft types, engines, number of aircraft, zones of operation), authorisation YES/NO items and evaluated factors.

### Annex 19 and SMS

- Doc 9974 ties the SRA to the SMS (Doc 9859 SMM). Appendix A also lists minimum SMS functions: hazard identification, remedial action, monitoring, continuous improvement.
- Annex 19 SMS framework (safety policy, risk management, assurance, promotion): UNVERIFIED, recalled from general knowledge. I did not fetch Annex 19.

## 3. Other regulator templates

### EASA SIB 2023-13 (replaces SIB 2010-17R7)

I did not read the EASA text directly. Facts below come from national circulars quoting it; check https://ad.easa.europa.eu/ad/2023-13.
- Operators keep an identifiable VA SRA in the SMS, accepted by the State regulator (Finland cites (1)(a)(1)). Source: https://www.ais.fi/aica/A/A2023/EF_AIC_2023_A_010_en.pdf
- Third-country operators need not build a separate SRA for Europe.
- Estonia gives concentration bands: low at or below 2×10⁻³ g/m³, medium 2 to 4×10⁻³, high at or above 4×10⁻³ (https://aim.eans.ee/sites/default/files/forms/aim_published_aic/EE-eAIC-2025-06-A.pdf).
- Malta's notice dated 19 Dec 2023 says the recommendations are not mandatory (https://www.transport.gov.mt/OAN-11-23-Guidelines-on-Volcanic-Ash-Cloud-Operation.pdf-f9375).

### UK CAP 1236 v4 (Feb 2017; a newer version is UNVERIFIED)

Read directly from https://www.caa.co.uk/publication/download/14978.
- 2.18: SRA before operations; NAA acceptance. For acceptance the operator must have a functioning SMS, an adequate proven safety record, the management experience and capability, documented procedures and training, and "Understanding of the hazards and its safety risks limits". Lateral avoidance first, then overflight, underflight, and lastly penetration.
- 2.19: VAAC and NAA information is primary. The SRA accounts for "the availability of flight watch and the capability of the operations unit to monitor".
- 2.20: fuel so a diversion to an unaffected aerodrome is reachable with normal reserves. Review MEL relief.
- 2.24: treat significant ash as a solid object, with assumed MSA at least 2,000 ft above the ash top. The overflight SRA covers MEL and alternates. 2.29: underflight maximum is 2,000 ft below the promulgated base. 2.32: further criteria are fuel burn, engine failure, obstacle clearance, weather and ATS availability.
- 3.3 and 3.4: ash encounter procedures, 180-degree turn, precautionary landing. 3.22 and 4.x: occurrence report plus ASR. Appendix C is a model VAR form.
- UK bands (mg/m³): low above 0.2 up to 2.0, medium above 2.0 to under 4.0, high 4.0 or more. Source: https://www.caa.co.uk/safety-initiatives/safety-projects/volcanic-ash/managing-ash-in-uk-airspace/

### CASA Australia

- AC 91-33 v1.0 (June 2024), "Flight in airspace with volcanic ash contamination". It is a means of compliance, not the only one. Source: https://www.casa.gov.au/node/265219.
- Airworthiness Bulletin 02-038 Issue 8 (Mar 2024) says operators are expected to do an SRA, with a mitigation structure from Doc 9974 (four phases).
- I did not read the AC text (the CASA page timed out), so the SRA sections of AC 91-33 are UNVERIFIED.

### New Zealand

No CAA advisory circular on volcanic ash SRA found. NZ uses the Volcanic Ash Advisory System ("Living with volcanic ash") and CAA-designated volcanic hazard zones. Source: https://aviation.govt.nz/assets/licensing-and-certification/meteorology/living-with-volcanic-ash.pdf

## 4. Encounter reporting: ICAO VAR

**Legal basis [REPORTED].** Annex 3 paragraphs 5.5 and 5.9, and PANS-ATM (Doc 4444) 4.12.3 and 4.12.5. The form is in Doc 4444 Appendix 1, section 2 ("Model VAR"). Sources: EUR/NAT VACP https://skybrary.aero/sites/default/files/bookshelf/357.pdf and Doc 9766 https://skybrary.aero/sites/default/files/bookshelf/450.pdf.

**Form fields.** I read a scanned copy of the Model VAR page (Doc 4444 Appendix 1, page AI-6, amendment 3, dated 18/11/10) hosted by the Serbian CAA (http://cad.gov.rs/upload/opasnesituacije/vulkanskipepeo/ICAO%20VAR.pdf). Later Doc 4444 amendments may have changed it, so this is UNVERIFIED against the current edition.

- **Header:** OPERATOR; A/C IDENTIFICATION (as on flight plan); PILOT-IN-COMMAND; DEP FROM, date, time UTC; ARR AT, date, time UTC; ADDRESSEE; "AIREP SPECIAL".
- **Items 1 to 8 (report immediately to the ATS unit):**
  1. Aircraft identification
  2. Position
  3. Time
  4. Flight level or altitude
  5. Volcanic activity observed at (position or bearing, estimated ash cloud level, distance from aircraft)
  6. Air temperature
  7. Spot wind
  8. Supplementary information (SO₂ detected Y/N; ash encountered Y/N; brief description of vertical and lateral extent, horizontal movement, rate of growth)
- **Items 9 to 16 (after landing):**
  9. Density of ash cloud (wispy, moderate dense, very dense)
  10. Colour (white, light grey, dark grey, black, other)
  11. Eruption (continuous, intermittent, not visible)
  12. Position of activity (summit, side, single, multiple, not observed)
  13. Other features (lightning, glow, large rocks, ash fallout, mushroom cloud, all)
  14. Effect on aircraft (communication, navigation systems, engines, pitot static, windscreen, windows)
  15. Other effects (turbulence, St Elmo's fire, other fumes)
  16. Other information

**Routing.** In-flight items go to the ATS unit, which forwards them to the meteorological watch office (MWO), which passes them to the VAAC and the OPMET data bank. The post-flight form goes to the meteorological authority or operator arrangement. The Doc 9766 handbook says "submit it ... to VAAC Darwin" for the Darwin area, with the Darwin VAAC e-mail darwin.vaac@bom.gov.au. The EUR/NAT example shows the voice AIREP SPECIAL and the ATS and MWO translations (`ARS UAL322 5503N17020E 0105 F300 ASC F350 VA CLD=`).

**Operator-side companion reports (Doc 9974):** AML entry, ASR, State mandatory occurrence report, and a report for non-encounters in forecast areas.

## 5. Japan JCAB and the Philippines CAAP

**Japan.** No JCAB operator SRA guidance found. The MLIT bulletin (Jan 2024) describes JMA's Tokyo VAAC monitoring and the VAA, SIGMET and dispersion products (https://www.mlit.go.jp/koku/content/001720985.pdf). Tokyo VAAC inquiry page: https://ds.data.jma.go.jp/vaac/data/Inquiry/vaac_operationj.html. UNVERIFIED: whether JCAB publishes anything operator-facing.

**Philippines.**
- CAAP acts through NOTAMs. For Mayon 2024 the reported restriction was a prohibition within 10,000 ft of the surface and advice to avoid the summit. For Kanlaon it set a vertical limit up to 17,000 ft (https://newsinfo.inquirer.net/1948888/caap-warns-pilots-to-avoid-flying-close-to-rumbling-kanlaon-volcano).
- CAR-ANS Part 3, 2nd edition (Jan 2024), covers aeronautical meteorology, with a mention of volcanic-ash changes (https://caap.gov.ph/wp-content/uploads/2024/12/CAR-ANS-Part-3-2nd-Edition-Governing-Aeronautical-Meteorological-Service.pdf).
- UNVERIFIED: whether PCAR Part 8 has ash provisions. No CAAP advisory circular found.

## Recommendation for TEPHRA

**Principle.** The airline fills and owns the SRA. TEPHRA should only pre-fill DRAFT evidence sections and keep every unfilled field visibly blank. Every document carries the header `DRAFT - NOT AN APPROVED SRA - FOR HUMAN SIGN-OFF. Illustrative airline (Ring of Fire Air). Source: ICAO Doc 9974 structure.` The label in `policy_a.json` ("ILLUSTRATIVE, not an airline SRA") already follows this.

### A. SRA document structure (one per region x route-family)

Use the deterministic Python template. The Gemini drafter writes only the narrative text boxes marked (G), and every other field comes from data. Keep Gemini calls to roughly one per region per day, cached by input hash. Use flash-lite for the narrative text, which stays inside the free-tier budget.

| # | Section | Required fields | TEPHRA evidence that fills it |
|---|---|---|---|
| 0 | Status block | doc_id, version, status=DRAFT, generated_at, region, route_ids, policy_id, owner role, "Accountable Executive: ____ (blank)", approval signature lines for dispatcher/OCC manager and safety manager, regulator acceptance reference "____" | policy preset id (`RFA-POLICY-A`), timestamps, blank sign-off fields |
| 1 | Scope and operation (Doc 9974 App G "The Operation") | operator, AOC no. (blank), aircraft types, engines, fleet count, zones of operation, flight phase | route table, ADS-B proxy type notes (state they are proxies) |
| 2 | Information sources and conflict resolution (4.1(d), E.4(b)) | source list with latency and reliability; table of conflicts found; rule used (never narrow the official area) | feeds snapshot, source timestamps, SIGMET vs VAA vs VONA vs Himawari disagreements, Gemini cone as "widen only" |
| 3 | Hazard characterisation | volcano, eruption phase (pre / start / ongoing / end), plume height, area polygon, FL base/top, contamination grading present or "no graduation, treated as high" | merged official areas, VONA colour code and heights, Himawari retrieval |
| 4 | Hazard and risk worksheet (App D/C format) | row id, hazard, consequence, existing controls, severity, probability, tolerability, further actions, post-mitigation severity and probability | prefilled rows: flying into ash (loss of thrust), windscreen, undetected damage near ash, communication failure; (G) fills consequence/control wording only; severity/probability suggested by rules, flagged "suggested" |
| 5 | Exposure analysis per flight | flight id, route, ETD, cone intersection, vertical margin used (2,000 ft per `policy_a`), min distance, alternates, TAF screen, fuel note | per-flight plan engine output |
| 6 | Mitigations and decision (App B) | decision (CONTINUE/MONITOR/CHANGE_LEVEL/HOLD/DIVERT), routeing, diversion and alternates, MEL relief note (blank for dispatcher), fuel for reroute, ACARS draft id | plans and ACARS drafts, labelled DRAFT |
| 7 | Flight watch (App B "Enhanced Flight Watch") | monitoring cadence, feeds monitored (VAA, SIGMET, NOTAM, VAR/AIREP), last-refreshed times, ops-unit capability statement | feed health and timestamps |
| 8 | Reporting and post-event | encounter-reporting route, VAR draft link, aircraft-inspection hold list | section B below |
| 9 | Assumptions, limits and review | stated assumptions, review trigger ("material change in eruption or source"), TCH data status "not supplied" | static text plus run metadata |
| 10 | Sign-off | dispatcher/duty manager approval, timestamp, decision log | the human-approval record |

Add an Indonesia overlay: when the region is Java/Bali or Halmahera, add a "SE-DJPU 15/2026 checklist" box: SRA done before flight planning, crew informed of restricted polygons, post-exposure aircraft inspection hold, encounter reported and documented through the safety reporting system, and passenger-handling obligations. Mark the box "per press report of the circular, verify against the PDF".

### B. VAR and encounter report draft structure

DRAFT JSON, rendered as the VAR layout, with human-completed fields blank and clearly marked `PILOT/DISPATCHER TO COMPLETE`.

```
var_draft {
  status: "DRAFT - for human sign-off; not transmitted",
  header: {operator, ac_ident, pic: null, dep, dep_date_utc, dep_time_utc, arr, arr_date_utc, arr_time_utc,
           addressee_suggestion: "nearest ATS unit; VAAC (Darwin: darwin.vaac@bom.gov.au) [verify]; operator ASR/MOR"},
  in_flight_items_1_8: {aircraft_ident, position, time_utc, fl_or_altitude,
      volcanic_activity_observed_at: {bearing_or_position, est_ash_level, distance},
      air_temp, spot_wind, so2_detected: null, ash_encountered: null, supplementary: "..."},
  post_flight_items_9_16: {density, colour, eruption, position_of_activity, other_features,
      effect_on_aircraft, other_effects, other_info},
  non_encounter_flag: bool,   // Doc 9974 4.1(h)(3): report when ash NOT met in a forecast area
  tephra_context: {nearest_official_area_ids, official_top_ft, cone_flag, source_timestamps}
  followups: ["aircraft AML entry","ASR","State mandatory occurrence report (CASR 830/19) - verify route","aircraft inspection per OEM before return to service","document in safety reporting system (SE-DJPU 15/2026)"]
}
```

What TEPHRA fills: aircraft ident and position/time/FL from ADS-B (marked as a proxy, never the real flight), the nearest hazard polygon and its top, and the source timestamps. What only a human can fill: items 6 to 16, PIC, SO₂ and encounter yes/no. Do not let Gemini invent crew observations.

Also generate a spoken-format string for the AIREP SPECIAL (items 1 to 4 plus "VOLCANIC ASH CLOUD") and an ARS-style line for the ATS-to-MWO step, using the EUR/NAT examples as templates.

### C. Items to flag in the deck

- Say "per press reports of SE-DJPU 15/2026" until the PDF is obtained. Ask the user to retrieve it from JDIH or Hubud and update `research/`.
- Cite Doc 9974 by title, with the First Edition (2012). Do not call it second edition.
- Do not state a reporting deadline or "72 hours" for Indonesia. No Indonesian source supports it.
- Add to the policy file notes: UK 2,000 ft margins (CAP 1236 2.24 and 2.29) already used; contamination bands only apply where an authority gives graduated areas.

### Licensing for the public repo

- Original template text and field labels: write your own wording. The VAR layout is an ICAO form, so credit it and do not copy the scan.
- Doc 9974, Doc 4444 and CAP 1236 are copyright documents. Short quotes with citation only.
- UK CAA publications are covered by the Open Government Licence per typical CAA practice [UNVERIFIED].

### Open verification list

1. Primary PDF of SE-DJPU 15/2026 (SRA contents, who signs, deadlines).
2. Current Doc 4444 Appendix 1 VAR form.
3. EASA SIB 2023-13 original text.
4. CASA AC 91-33 SRA sections.
5. Indonesian reporting route under the current CASR 830 replacement.
6. Annex 19 SMS wording.

Sources (primary documents read): https://www.preventionweb.net/files/25588_9974unediteden1.pdf, https://www.caa.co.uk/publication/download/14978, https://skybrary.aero/sites/default/files/bookshelf/357.pdf, https://skybrary.aero/sites/default/files/bookshelf/450.pdf, http://cad.gov.rs/upload/opasnesituacije/vulkanskipepeo/ICAO%20VAR.pdf. SE-DJPU 15/2026 source (secondary): https://penajamnews.com/kemenhub-terbitkan-surat-edaran-penanganan-dampak-abu-vulkanik-terhadap-operasi-penerbangan-keselamatan-tetap-menjadi-prioritas-utama/.
