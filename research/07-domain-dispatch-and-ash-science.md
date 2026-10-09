# 07 — Domain primer: airline volcanic-ash dispatch and ash science (lens: domain)

Written 2026-10-10 (IST) for Asish and Akash. Read time about 30 minutes. Lens: how ash avoidance works in airline operations, and whether TEPHRA's mechanic (reconcile contradicting sources into a provenance-stamped cone that never shrinks below the official polygon, project live aircraft, draft a per-flight advisory, human approves) is sound.

How to read the tags:
- [CONFIRMED: url, accessed 2026-10-10] means this agent opened the page, PDF or feed and it says that.
- [REPORTED: url] means a secondary source or a search-engine summary says it; the agent could not open the primary text (most ICAO meeting papers sit behind a Cloudflare challenge that returned HTTP 403 to curl and to the fetch tool).
- [UNVERIFIED] means not checked.
- Live snapshots (SIGMET JSON, VAA texts, VONAs, Himawari frames, ADS-B) were taken between 19:28 and 20:15 UTC on 2026-10-09, which is 00:58 to 01:45 IST on 2026-10-10. The access date in tags is the IST date.
- The web-search budget for this session ran out after 23 searches; later checks used direct fetches of known public pages only (see Search log).

---

## 0. Bottom line (judgement)

1. The problem is real and is written into regulation: EASA's guidance material for operators says the operator must show competence "to interpret data from different sources ... and correctly resolve any conflicts among data sources that may arise" and must "carefully consider and resolve differences or conflicts among the information sources" [CONFIRMED: https://www.easa.europa.eu/en/downloads/1979/en, accessed 2026-10-10]. That text is a direct transposition of ICAO Doc 9974 [CONFIRMED: https://ad.easa.europa.eu/blob/EASA_SIB_2023-13.pdf/SIB_2023-13_2, accessed 2026-10-10].
2. Disagreement between products is frequent, not rare. On the live snapshot, 6 of the 8 distinct volcanic-ash SIGMETs in force worldwide disagreed in some way with the matching VAA or VONA (Section 3.7). But almost all of these disagreements are about confidence and observation status (observed vs estimated vs "not observed at night"), not about geometry: the SIGMET polygons are usually copied from the VAA. So the reconciliation that matters is mostly "label each source's evidence type and take the conservative envelope", which code can do; Gemini's defensible job is reading the free-text remarks and VONA prose, classifying evidence, explaining, and drafting.
3. A cone that never shrinks below the official area is consistent with how operators already work (operator-specific no-fly zones, "suitable safety margins", official information treated as primary) [CONFIRMED: https://www.caa.co.uk/publication/download/14978, accessed 2026-10-10]. It becomes unacceptable if it grows without stated reasons or is presented as an airspace closure.
4. The satellite-reading step is the weakest part scientifically. The public JMA JPEGs offer a Dust RGB but no Ash RGB, at about 5.5 km per pixel, and at night the land of Java renders pink, the same family of colour JMA assigns to dust and ash (Section 5.3). Purpose-built neural networks on raw radiances detect only 48.5 to 84.1 % of volcanic-cloud pixels in independent tests [CONFIRMED: https://amt.copernicus.org/articles/19/4255/2026/, accessed 2026-10-10], and there is no published record of a vision-language model reading ash plumes (arXiv returns 0 papers; Section 5.7).
5. Verdict for the build: the mechanic is sound if (a) geometry comes only from official products plus explicit, bounded, labelled margins; (b) vertical logic is done properly (FL, pressure altitude, 2,000 ft buffers, drift-down); (c) the satellite frame is demoted to context; (d) "not observed" is never read as "no ash".

---

## 1. Prior-pack hypotheses checked

| Pack claim (2026-09-25 to 10-10) | Status | Evidence |
|---|---|---|
| "EASA SIB 2010-17R8" is the European reference (from the task text) | REFUTED | SIB 2023-13, issued 19 Dec 2023, "replaces EASA SIB 2010-17R7 dated 02 July 2015, which is withdrawn" [CONFIRMED: https://ad.easa.europa.eu/blob/EASA_SIB_2023-13.pdf/SIB_2023-13_2, accessed 2026-10-10]. No R8 was found. |
| Weathernews has sold AI ash detection on Himawari to airlines since 2021 | CONFIRMED | Press release dated 2021-04-26: "Full-Scale Operation of AI Volcanic Ash Detection System for Aviation Market Begins"; it detects ash "from gaps in clouds" using "shape and texture" [CONFIRMED: https://global.weathernews.com/news/16070/, accessed 2026-10-10]. |
| "JMA mirror of Darwin VAAC" (Ibu 2026/1081, Dukono 2026/788) | CORRECTED | The JMA page is titled "Volcanic Ash Advisories(Darwin VAAC Backup)" and lists only advisories Tokyo issued while backing up Darwin; its newest rows are 23 Sep 2026 and it said "Updated at 00:00 UTC, 01 October 2026" [CONFIRMED: https://ds.data.jma.go.jp/svd/vaac/data/vaac_darwin_list.html, accessed 2026-10-10]. It is not a live Darwin feed. |
| Ibu advisory count (1,081 by 23 Sep) | CONFIRMED and moving | Darwin VAA for Ibu numbered 2026/1146 at 20261009/0730Z [CONFIRMED: https://www.volcanodiscovery.com/ibu/news/374545/vaac-advisory-2026-1146.html, accessed 2026-10-10], i.e. 65 more in 16 days. |
| "EST VA CLD replaces OBS VA CLD when satellite cannot confirm the cloud" (ash-map README, quoted in pack) | CONFIRMED with a twist | Washington VAAs use EST when "VA EMS NOT OBS IN STLT IMG OR WEBCAM DUE TO HVY MET CLD CVR" [CONFIRMED: https://www.ospo.noaa.gov/VAAC/ARCH26/FUEG/2026J091854.html, accessed 2026-10-10]; but a Darwin-area VAA labelled "OBS VA CLD" said in RMK "VA NOT IDENTIFIABLE ON SATELLITE IMAGERY ... VA AREA IS AN ESTIMATED AREA" [CONFIRMED: https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20260923_26803000_1081_Text.html, accessed 2026-10-10]. The label alone cannot be trusted; RMK must be read. |
| "11 open VA SIGMETs" counts | CAUTION | The AWC JSON returned 11 VA records but only 8 distinct SIGMETs; 3 records with series IDs ending in "F" ("3F", "1F", "A5F") repeat the same raw text and carry the forecast polygon [CONFIRMED: https://aviationweather.gov/api/data/isigmet?format=json, accessed 2026-10-10]. Counts must de-duplicate by raw text. |
| JMA Dust-RGB is the right image | WEAK | Available every 10 min, but JMA's own guide gives dust and volcanic ash one colour class and lists "Poor display of low-level clouds (with dust cloud shading similar to that of low-level clouds)" as a limitation [CONFIRMED: https://www.jma.go.jp/jma/jma-eng/satellite/VLab/QG/RGB_QG_Dust_en.pdf, accessed 2026-10-10]. The purpose-built Ash RGB is not in the public JPEG product list (Section 5.3). |
| Anak Krakatau closed Soekarno-Hatta in Sep 2026 | REPORTED | AVweb (7 Sep 2026): "Seven Indonesian airports remained closed Monday", "2,961 canceled, delayed or diverted flights", BMKG "issued 18 SIGMETs after the eruption began late Friday" [REPORTED: https://avweb.com/aviation-news/volcanic-ash-shuts-seven-indonesia-airport/]. CNBC and Jakarta Post coverage appeared in search results [REPORTED: https://www.cnbc.com/2026/09/07/flights-canceled-jakarta-airport-anak-krakatau-eruption-disrupts-regional-travel-volcano.html]. |

---

## 2. The system: IAVW and the nine VAACs

- ICAO, with WMO, runs the International Airways Volcano Watch (IAVW); its governing documents are Annex 3 and the IAVW operational procedures, and its handbook is Doc 9766 [REPORTED: https://skybrary.aero/articles/volcanic-ash-advisory-centre-vaac].
- The chain of responsibility: the VAAC gives the meteorological watch office (MWO) and area control centre (ACC) the trajectory forecast and affected flight levels; "The MWO and ACC then issue the required SIGMET and notice to airmen (NOTAM) messages" [CONFIRMED: https://resources.eumetrain.org/data/1/144/media/paper/ManualonVolcanicAsh-ICAO.pdf, accessed 2026-10-10] (ICAO Doc 9691 draft with Amendment 1).
- Doc 9691 states "Eight States have accepted responsibility for providing nine VAACs as part of the IAVW on a 24-hour basis" [CONFIRMED: https://resources.eumetrain.org/data/1/144/media/paper/ManualonVolcanicAsh-ICAO.pdf, accessed 2026-10-10].

Areas of responsibility (wording from the Wikipedia table, which cites the IAVW handbook) [CONFIRMED: https://en.wikipedia.org/wiki/Volcanic_Ash_Advisory_Center, accessed 2026-10-10]:

| VAAC | Host | Area (abridged) | TEPHRA relevance |
|---|---|---|---|
| Tokyo | Japan Meteorological Agency | N6000 to N1000 from E09000 east to the Oakland/Anchorage FIR boundaries, except a box N2000–N1000, E09000–E10000 | Japan, Kamchatka/Kurils, northern Philippines (Taal, Mayon are Tokyo) |
| Darwin | Bureau of Meteorology | Southward from N1000 between E10000 and E16000 (plus a strip E08200–E10000 south of N2000) and the Colombo, Melbourne, Brisbane FIRs | Indonesia, PNG, southern Philippines |
| Wellington | MetService NZ | South of the Equator, E160 to W140 (except Melbourne/Brisbane FIRs), plus south of S10 from W140 to W090 | Vanuatu, Tonga, NZ |
| Anchorage | US NWS | Anchorage FIRs and part of Oakland Oceanic north of N43 | Aleutians |
| Washington | NOAA | US continental FIRs, New York and part of Oakland Oceanic, Central America, northern South America | Guatemala, Ecuador, Colombia |
| Montreal | Meteorological Service of Canada | Canadian, Gander, Søndrestrøm FIRs | — |
| London | Met Office | North Atlantic north of N71 east to E090 and the UK, Iceland, Nordic FIRs | — |
| Toulouse | Météo-France | Europe (other), Africa, Middle East, Asia west of E090 north of N20 | — |
| Buenos Aires | SMN Argentina | South of S10 between W010 and W090 | — |

- The Bureau of Meteorology's own guide says VAAC Darwin covers "the active volcanic regions of Indonesia, Papua New Guinea and the southern Philippines" and that it is operated "out of Melbourne" [CONFIRMED: https://www.bom.gov.au/aviation/data/education/volcanic-ash-advisories.pdf, accessed 2026-10-10].
- Tokyo backs up Darwin: on 23 Sep 2026 a pseudo-advisory said "VAAC TOKYO HAS ASSUMED RESPONSIBILITY FOR ISSUING VAA TO THE VAAC DARWIN AREA OF RESPONSIBILITY NORTH OF LATITUDE 20S" [CONFIRMED: https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20260923_99999902_0003_Text.html, accessed 2026-10-10]. That message is formatted as a VAA with "VOLCANO: NOTICE 999999", "PSN: N1000 E11300", "SOURCE ELEV: 9999M AMSL" (same source); a naive parser would plot a fake volcano in the Java Sea.
- Tokyo VAAC's information sources: JMA's four volcano warning centres, MWOs, "KVERT, PHIVOLCS, AVO", adjacent VAACs, pilot reports, satellites, and JMA NWP-based 6/12/18-hour transport forecasts [CONFIRMED: https://www.data.jma.go.jp/vaac/data/Inquiry/vaac_operation.html, accessed 2026-10-10].

---

## 3. The products

### 3.1 Volcanic Ash Advisory (VAA) text

Field meanings, from the Darwin VAAC guide (updated 13 Dec 2024) [CONFIRMED: https://www.bom.gov.au/aviation/data/education/volcanic-ash-advisories.pdf, accessed 2026-10-10]:
- DTG: time of origin, `YYYYMMDD/HHMMZ`.
- VOLCANO: name plus Smithsonian/IAVCEI number; PSN: volcano position in degrees and minutes.
- AREA: the State, or region.
- SUMMIT ELEV: summit height in metres and/or feet. (Live 2026 texts from Tokyo, Darwin and Washington now say SOURCE ELEV instead; see 3.1.2.)
- ADVISORY NR: count for that volcano in the calendar year, `YYYY/N`.
- AVIATION COLOUR CODE: present in the 2024 Darwin example; absent from every 2026 VAA read for this file.
- ERUPTION DETAILS: summary from the information source.
- OBS (or EST) VA DTG: day/time of the observation, `DD/HHMMZ`.
- OBS (or EST) VA CLD: "The horizontal and vertical extent of the observed or estimated ash cloud, if known, plus an indication of the movement of the cloud".
- FCST VA CLD (+6, 12, 18 HR): extent "at +6, +12, and +18 hours from the time of the observed cloud".
- RMK: further information.
- NXT ADVISORY: approximate time of next issue; "Will also indicate if the ash cloud is expected to move into an adjacent VAAC's area of responsibility".

Cadence:
- Darwin: "VAA are issued every 6 hours, or more often if significant new information becomes available"; when ash is not evident on satellite but an eruption is ongoing, "VAA may be issued every 24 hours" [CONFIRMED: https://www.bom.gov.au/aviation/data/education/volcanic-ash-advisories.pdf, accessed 2026-10-10].
- Tokyo: "VAAs are updated as a minimum at six-hour intervals (normally at 00, 06, 12 and 18 UTC)" and "as often as needed" if notable changes occur [CONFIRMED: https://www.data.jma.go.jp/vaac/data/Inquiry/vaac_operation.html, accessed 2026-10-10].
- Darwin reportedly changed policy in March 2024 to issue advisories when ground reports such as VONAs show an eruption [REPORTED: https://www.icao.int/sites/default/files/APAC/Meetings/2024/2024%20MET%20SG-28%20and%20MET%20Seminar/4-Information%20Papers/IP15_AI6_AUS-JPN-NZL_COMBINED-APAC-VAAC-MANAGEMENT-REPORT.pdf].

Forecast steps: the +6/+12/+18 polygons are tied to the observation time, not to DTG. Example: Taal 2026/22 has DTG 1130Z, OBS VA DTG 08/1050Z, +6 HR at 08/1650Z, +12 HR at 08/2250Z with top rising from FL150 to FL170, and "+18 HR: NO VA EXP" [CONFIRMED: https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20261008_27307000_0022_Text.html, accessed 2026-10-10].

#### 3.1.1 Exact meanings of the phrases the brief asks about

- "VA NOT IDENTIFIABLE FM SATELLITE DATA": the satellite analyst cannot see ash. Tokyo states the two possible reasons in its RMK: "VA IS NOT IDENTIFIABLE DUE TO MET CLOUD OR HAS DISSIPATED. WE WILL ISSUE FURTHER ADVISORY IF VA DETECTED IN SATELLITE IMAGERY." The same advisory carries a wind ("WIND FL180 060/9KT") in place of a polygon, and all forecasts are "NOT AVBL" [CONFIRMED: https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20261008_27307000_0024_Text.html, accessed 2026-10-10]. It is not an all-clear.
- The same phrase can follow a reported eruption: Mayon 2026/803 says "ERUPTION AT 20261007/1418Z FL100 EXTD WSW REPORTED" with info source "HIMAWARI-9 PHIVOLCS", then "OBS VA CLD: VA NOT IDENTIFIABLE FM SATELLITE DATA WIND FL100 050/7KT", forecasts "NOT AVBL", and "NXT ADVISORY: NO FURTHER ADVISORIES" [CONFIRMED: https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20261007_27303000_0803_Text.html, accessed 2026-10-10]. So an official text can say "ash to FL100 going WSW" and give no polygon. This is the clearest real case for a TEPHRA hypothesis cone.
- "NO VA EXP" vs "NOT AVBL": Sakurajima 2026/279 ("ERUPTION DETAILS: VA DISSIPATED ON SATELLITE IMAGERY") uses "NO VA EXP" for all forecasts, i.e. the forecaster expects no ash [CONFIRMED: https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20261008_28208001_0279_Text.html, accessed 2026-10-10]; "NOT AVBL" (Mayon, Taal 2026/24) means no forecast was produced. Code must keep these distinct.
- "EST VA CLD" vs "OBS VA CLD": EST is used when the cloud is not currently seen and its position is estimated. Washington's Fuego advisory: "EST VA DTG: 09/1830Z", "EST VA CLD: SFC/FL140 ...", RMK "VA EMS NOT OBS IN STLT IMG OR WEBCAM DUE TO HVY MET CLD CVR. OBSCD VA EMS PSBLY CONTNG BASED ON PREV ACTIVITY" [CONFIRMED: https://www.ospo.noaa.gov/VAAC/ARCH26/FUEG/2026J091854.html, accessed 2026-10-10]. Reventador: "OBS VA AREA ESTD FM NWP MDLS AND PREV VAA ... LOWER CONFIDENCE IN FCST DUE TO LGT FL WINDS" [CONFIRMED: https://www.ospo.noaa.gov/VAAC/ARCH26/REVE/2026J090455.html, accessed 2026-10-10].
- But the label is not reliable on its own: the Tokyo-as-Darwin-backup advisory for Ibu 2026/1081 is headed "OBS VA CLD: SFC/FL070 ..." while its RMK says "VA NOT IDENTIFIABLE ON SATELLITE IMAGERY. REGULAR GROUND REPORTS INDICATE INTERMITTENT DISCRETE ERUPTIONS ARE ONGOING ... VA AREA IS AN ESTIMATED AREA" [CONFIRMED: https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20260923_26803000_1081_Text.html, accessed 2026-10-10].
- RMK lines carry the evidence basis. Live examples: "SOME PART OF VA OBSCURED BY MET CLOUD" (Taal 2026/22, URL above); "VA HEIGHT AND MOVEMENT BASED ON GROUND REPORTS, HIMAWARI-9 SAT AND MODEL GUIDANCE" (Darwin Semeru 2026/1150) [CONFIRMED: https://volcanodiscovery.com/semeru/news/373618/vaac-advisory-2026-1150.html, accessed 2026-10-10]; "VA EMS OBS IN STLT IMG UP TO APPRX 45NM FM SUMMIT" (Washington Purace) [CONFIRMED: https://www.ospo.noaa.gov/VAAC/ARCH26/PURA/2026J091539.html, accessed 2026-10-10]. This free text is where an LLM is genuinely useful.

#### 3.1.2 Format variations a parser must survive (all CONFIRMED in live texts above)

- `SUMMIT ELEV: 1229M` (Darwin 2024 example) vs `SOURCE ELEV: 1325M AMSL` (Darwin 2026) vs `SOURCE ELEV: 12346 FT AMSL` (Washington 2026): field name and unit both vary.
- `FCST VA CLD +6 HR:` (Tokyo, Darwin) vs `FCST VA CLD +6HR:` (Washington).
- `NXT ADVISORY: NO LATER THAN 20240917/1100Z` (Darwin), `NXT ADVISORY: 20261008/1500Z` (Tokyo), `WILL BE ISSUED BY 20261010/0100Z` (Washington), `NO FURTHER ADVISORIES`.
- `AVIATION COLOUR CODE:` line present in 2024, absent in 2026. A 2023 ICAO workshop paper proposed removing the colour code from the VAA after VONA introduction [REPORTED: https://www.icao.int/sites/default/files/sp-files/SAM/Documents/2023-RLA06901-PANSMET/04_Taller%20PANS-MET-Prop%20Inic%203_SVO-VONA_En_08.10.2023_EN.pdf]. Which Annex 3 amendment made these changes was not checked [UNVERIFIED].
- Polygons are `N0127 E12736 - N0132 E12736 - ...` in degrees and minutes, not decimal degrees.
- Washington also publishes IWXXM XML alongside the text (links of the form `/products/atmosphere/vaac/volcanoes/xml_files/FVXX20_20261009_1854.xml`) [CONFIRMED: https://www.ospo.noaa.gov/products/atmosphere/vaac/messages.html, accessed 2026-10-10].

### 3.2 Volcanic Ash Graphic (VAG) and related Tokyo graphics

- Darwin: "Advisory messages for volcanic ash are also issued in graphical format whenever a text product is issued. The volcanic ash advisory graphic (VAG) ... displays the OBS VA CLD and FCST sections as polygons in 4 panels. Different line styles are used to distinguish ash at different heights (multi-level VAAs)" [CONFIRMED: https://www.bom.gov.au/aviation/data/education/volcanic-ash-advisories.pdf, accessed 2026-10-10].
- Tokyo: VAG gives presence, extent and 6/12/18-hour forecasts, updated "at intervals of six hours or less"; VAGI shows current extent only; VAGFN gives hourly 1–6 h forecasts with an upper layer FL180–FL550 and a lower layer SFC–FL180 [CONFIRMED: https://www.data.jma.go.jp/vaac/data/Inquiry/graphic_and_dispersion.htm, accessed 2026-10-10].
- Tokyo's list shows that VAG/VAGI are issued only for some advisories (Taal 2026/22 and 2026/23 have them; 2026/24 and Sakurajima 2026/279 do not) [CONFIRMED: https://ds.data.jma.go.jp/svd/vaac/data/vaac_list.html, accessed 2026-10-10].

### 3.3 Volcanic-ash SIGMET (WV SIGMET)

- Issuer: the MWO responsible for the FIR, not the VAAC. Darwin's guide: "Volcanic ash SIGMET messages are prepared by the relevant Meteorological Watch Offices (MWO) from the information contained in the VAA" [CONFIRMED: https://www.bom.gov.au/aviation/data/education/volcanic-ash-advisories.pdf, accessed 2026-10-10].
- Validity: ICAO Doc 9691 says the SIGMET "should be valid for six hours with a 12-hour 'outlook'" and should be "updated as necessary, but at least every six hours" [CONFIRMED: https://resources.eumetrain.org/data/1/144/media/paper/ManualonVolcanicAsh-ICAO.pdf, accessed 2026-10-10]. Current Annex 3 wording ("no more than 6 hours"; issue no more than 12 hours before validity starts) [REPORTED: https://www.icao.int/sites/default/files/APAC/Meetings/2021/2021%20MET-S%20WG11/3-Working%20Papers/WP07_A.I.6_AHG_SIGMET-GUIDANCE-FOR-VOLCANIC-ASH-FORECAST-TO-CROSS-FIR-BOUNDARIES.pdf]. Every live VA SIGMET had a validity of 6 hours or slightly less (e.g. `VALID 091610/092200`) [CONFIRMED: https://aviationweather.gov/api/data/isigmet?format=json, accessed 2026-10-10].
- An initial SIGMET may be issued "even without the 'outlook' while a trajectory forecast is awaited from the VAAC"; the SIGMET "is only issued when volcanic ash in the atmosphere is reported or expected to exist", whereas NOTAM/ASHTAM may be issued before an eruption [CONFIRMED: https://resources.eumetrain.org/data/1/144/media/paper/ManualonVolcanicAsh-ICAO.pdf, accessed 2026-10-10].
- Cancellation "in principle" when the VAAC confirms ash is no longer detectable, no further reports exist, and the volcano has reverted to pre-eruption status (same source).
- Scope: one SIGMET covers one FIR. When forecast ash will cross into a neighbouring FIR, the receiving MWO is expected to issue its own SIGMET; APAC working groups have treated this as a guidance gap [REPORTED: https://www.icao.int/sites/default/files/APAC/Meetings/2021/2021%20MET-S%20WG11/3-Working%20Papers/WP07_A.I.6_AHG_SIGMET-GUIDANCE-FOR-VOLCANIC-ASH-FORECAST-TO-CROSS-FIR-BOUNDARIES.pdf]. A 2021 APAC answer: a SIGMET is not required when the VAA says ash is not identifiable [REPORTED: same URL].

Format, from a live Indonesian SIGMET [CONFIRMED: https://aviationweather.gov/api/data/isigmet?format=json, accessed 2026-10-10]:

```
WVID21 WAAA 091820
WAAF SIGMET 12 VALID 091820/100020 WAAA-
WAAF UJUNG PANDANG  FIR VA
ERUPTION MT SEMERU PSN S0806 E11255 VA CLD OBS AT 1800Z WI S0803
E11253 - S0754 E11316 - S0807 E11324 - S0820 E11318 - S0811 E11253 -
S0803 E11253 SFC/FL150 MOV E 10KT NC=
```

- `WV` = volcanic ash SIGMET; `WAAA` = issuing MWO; `WAAF` = FIR; `WI` = within polygon; `SFC/FL150` = surface to FL150; `MOV E 10KT` = movement; `NC` = no change in intensity.
- Indonesian SIGMETs on the snapshot gave only `MOV`, no `FCST` polygon; Guatemalan and Ecuadorian ones gave `FCST AT 2200Z WI ...` or `FCST 2330Z VA CLD SFC/FL050 ...` (same source).
- A layer need not start at the surface: the EUR contingency-plan example reads `VA CLD OBS AT 0100Z ... FL200/350 MOV SE 35KT FCST 0705Z VA CLD APRX ...` [CONFIRMED: https://volcanoes.usgs.gov/vsc/file_mngr/file-138/EUR%20Doc%20019.pdf, accessed 2026-10-10].
- The AWC endpoint rejects `hazard=ash` with `{"status":"error","error":"Invalid value for hazard"}`; the unfiltered call returned 162 international SIGMETs of which 11 records had `"hazard":"VA"` [CONFIRMED: https://aviationweather.gov/api/data/isigmet?format=json, accessed 2026-10-10]. Fields include `firId`, `validTimeFrom`/`validTimeTo` (epoch seconds), `base`/`top` (feet), `dir`, `spd`, `coords` (decimal degrees) and `rawSigmet`.

### 3.4 VONA and the aviation colour code

Aviation colour code definitions (Darwin guide, which calls it "an alert level developed by the International Airways Volcano Watch") [CONFIRMED: https://www.bom.gov.au/aviation/data/education/volcanic-ash-advisories.pdf, accessed 2026-10-10]:
- GREEN: "Volcano is in normal non-eruptive state", or activity has ceased after a higher level.
- YELLOW: "signs of elevated unrest above known background levels", or decreased after a higher level but still closely monitored.
- ORANGE: "heightened unrest with increased likelihood of eruption", or "eruption is underway with no, or minor, ash emission".
- RED: "Eruption is forecast to be imminent with significant emission of ash into the atmosphere likely", or "Eruption is underway with significant emission of ash".

Who issues VONAs:
- Indonesia: the Center for Volcanology and Geological Hazard Mitigation (CVGHM, Indonesian acronym PVMBG) publishes VONAs on MAGMA; they are "disseminated via email to national and international stakeholders" and "All notifications are publicly available online" [CONFIRMED: https://magma.esdm.go.id/v1/vona, accessed 2026-10-10]. The archive counts on that page include Semeru (10189), Ibu (3064), Lewotobi Laki-laki (1568), Dukono (1198), Sinabung (1007), Anak Krakatau (601) (same source).
- Kamchatka: KVERT publishes "KVERT VONA" and "KVERT VAN & VONA" lists and aviation colour codes [CONFIRMED: http://kvert.febras.net/van/, accessed 2026-10-10].
- JMA and PHIVOLCS: whether they issue VONAs in the ICAO format was not verified [UNVERIFIED]. PHIVOLCS appears as an "INFO SOURCE" in Tokyo VAAs (Mayon 2026/803, URL above).

VONA format (live Semeru notice 2026SMR1920) [CONFIRMED: https://magma.esdm.go.id/v1/vona/22889?signature=5412ce61fc8ab19051a3a1682ceb3ec3cfcf9aca8457455414c1cadda2305bad, accessed 2026-10-10]:
1. Issued 20261009/1800Z; 2. Volcano: Semeru (263300); 3. Current Aviation Colour Code: ORANGE; 4. Previous: orange; 5. Source: Semeru Volcano Observatory; 6. Notice Number: 2026SMR1920; 7. Location; 8. Area; 9. Summit Elevation: 11763 FT (3676 M); 10. Volcanic Activity Summary: "Eruption at 1800 UTC (0100 local)."; 11. Volcanic Cloud Height: "Ash-cloud is not observed."; 12. Other Volcanic Cloud Information; 13. Remarks: "Eruption recorded on seismogram with maximum amplitude 14 mm and maximum duration 190 second."; 14. Contacts; 15. Next Notice: "A new VONA will be issued if conditions change significantly or the colour code is changes."

Two phrasings matter:
- When ash is seen, MAGMA writes heights both above sea level and above the summit, plus a hedge: "Best estimate of ash-cloud top is around 5520 FT (1725 M) above sea level or 1280 FT (400 M) above summit. May be higher than what can be obs[erved]" (Ibu, 20261009/0137Z) [CONFIRMED: https://magma.esdm.go.id/v1/vona?code=IBU, accessed 2026-10-10].
- When ash is not seen: "Ash-cloud is not observed", including at 0100 local (above). A ground observer at night, or under summit cloud, cannot see the column; the seismogram line shows an eruption did occur.

VONAs are event-driven ("if conditions change significantly"), so silence is not evidence of quiet: the newest Dukono VONA on the snapshot was dated 2026-09-29 15:30 UTC and said "Ash-cloud is not observed", while a Dukono VA SIGMET valid 091550/092150 said `VA CLD OBS AT 1530Z ... SFC/FL070 MOV NE 10KT` [CONFIRMED: https://magma.esdm.go.id/v1/vona?code=DUK and https://aviationweather.gov/api/data/isigmet?format=json, accessed 2026-10-10].

### 3.5 NOTAM and ASHTAM

- NOTAM/ASHTAM are issued by the ACC through the NOTAM office; they give volcano status, ash location/extent/movement and affected routes and levels, and "may be issued before an actual eruption" [CONFIRMED: https://resources.eumetrain.org/data/1/144/media/paper/ManualonVolcanicAsh-ICAO.pdf, accessed 2026-10-10]. The MWO must keep SIGMET and NOTAM/ASHTAM "mutually consistent" (same source).
- ASHTAM example (EUR Doc 019, 2014): `ASHTAM 015/10 A) ROMA FIR B) 01151650 C) ETNA 101-06 D) 3744N01500E E) RED ALERT F) AREA AFFECTED ... SFC/35000FT G) NE H) ROUTES AFFECTED WILL BE NOTIFIED BY ATC J) VULCANOLOGICAL AGENCY` [CONFIRMED: https://volcanoes.usgs.gov/vsc/file_mngr/file-138/EUR%20Doc%20019.pdf, accessed 2026-10-10]. Item E carries the colour code; item F gives the area with a height in feet, not FL.
- NOTAM example from the same plan: "AIRCRAFT ARE REQUIRED TO REMAIN AT LEAST XXXNM CLEAR OF VOLCANO", where "XXX is a distance established by the Provider State" (same source).
- A WACAF workshop reported NOTAMs for ash with no parallel SIGMET, or with mismatching content [REPORTED: https://www.icao.int/sites/default/files/WACAF/MeetingDocs/2025/Volcanic%20Ash/Session%207/Best-Practices-in-developing-SOP-for-Volcanic-Ash-Events.pdf].
- TEPHRA has no NOTAM feed in its plan. This is a gap (the brief lists only SIGMET, VONA, VAAC, satellite, winds, TAF, ADS-B).

### 3.6 Documented reasons VONA, VAA and SIGMET disagree

1. Different observers and instruments: a VONA is a ground observer plus seismometer; a VAA is mainly satellite plus model plus ground reports; a SIGMET is the MWO's restatement of the VAA for one FIR (sources in 3.1, 3.3, 3.4).
2. Night: ground observers report "Ash-cloud is not observed" at 0100 local while eruptions are on the seismogram (3.4). Five of the nine engine-failure (severity class 4) encounters in the USGS compilation happened at night [CONFIRMED: https://pubs.usgs.gov/ds/545/DS545.pdf, accessed 2026-10-10].
3. Meteorological cloud: Tokyo "VA IS NOT IDENTIFIABLE DUE TO MET CLOUD OR HAS DISSIPATED"; Washington "NOT OBS ... DUE TO HVY MET CLD CVR" (3.1.1).
4. Timing: VAAs every 6 h (or 24 h when precautionary), SIGMETs up to 6 h, VONAs on change only (3.1, 3.3, 3.4).
5. Height method: VONA heights are visual estimates above the summit with "May be higher than what can be observed"; one Darwin report says pilot reports put a plume up to 10,000 ft above the current advisory [REPORTED: https://www.icao.int/sites/default/files/APAC/Meetings/2021/2021%20MET%20SG%2025/4-Information%20Papers/IP08_AI.5_AUS_VAAC-Darwin-Management-Report.pdf]; another found a 23,000 ft estimate unsupported by a +6 °C plume-top temperature [REPORTED: https://www.icao.int/sites/default/files/APAC/Meetings/2021/2021%20MET-S%20WG11/4-Information%20Papers/IP07_AI.6_AUS_VAAC-Darwin-Management-Report-Rev-170321.pdf].
6. Delivery failure: a Semeru VONA (Aug 2021, ash to 25,000 ft) reached Darwin by email but not the MAGMA website; the advisory was later raised to 50,000 ft on satellite evidence [REPORTED: same 2021 Darwin URL].
7. Two VAACs on one cloud: a Northern Pacific case had two VAACs issuing uncoordinated products whose 12 and 18 h extents differed greatly [REPORTED: https://link.springer.com/chapter/10.1007/11157_2016_45].
8. Wording inheritance: SIGMETs restate VAA polygons but relabel them (3.7).

Not found: a quantitative study of how often VONA, VAA and SIGMET disagree in APAC (search budget ran out; queries in the Search log). Tupper and Wunderman (2009) on ground-vs-satellite height discrepancies is remembered but was not opened [UNVERIFIED].

### 3.7 Live disagreement table (snapshot 2026-10-09 19:28–20:15 UTC)

| Volcano (FIR) | SIGMET says | VAA says | VONA says | Kind of disagreement |
|---|---|---|---|---|
| Semeru (WAAF) | `VA CLD OBS AT 1800Z ... SFC/FL150 MOV E 10KT` | Last read: 2026/1150 at 08/0000Z, OBS SFC/FL150 MOV W 05KT | Six VONAs on 9 Oct (0706Z to 1800Z), each "Ash-cloud is not observed" | Observed vs not observed; movement E vs W a day earlier |
| Anak Krakatau (WIIF) | `VA CLD OBS AT 1550Z ... SFC/FL060 MOV W 05KT` | Search result titled "ash plume to 6,000 ft ... as of Oct 9, 09:50 UTC" [REPORTED: https://www.volcanodiscovery.com/krakatau/news/374625/vaac-advisory-2026-224.html] | 1144Z (1844 local): "Ash-cloud is not observed" | Observed vs not observed (after dusk) |
| Dukono (WAAF) | `VA CLD OBS AT 1530Z ... SFC/FL070 MOV NE 10KT` | not read | Newest VONA 29 Sep 1530Z "Ash-cloud is not observed" | VONA silent for 10 days |
| Ibu (WAAF) | `OBS AT 1310Z ... SFC/FL070 MOV E 10KT` | 2026/1146: OBS 09/0710Z SFC/FL070 MOV E 10KT | 0137Z: top 5,520 ft AMSL, "May be higher" | Consistent (VONA lower, hedged) |
| Fuego (MHTG) | `VA CLD OBS AT 1830Z SFC/FL140` | `EST VA CLD` 09/1830Z SFC/FL140, same polygon, "NOT OBS ... DUE TO HVY MET CLD CVR" | n/a | SIGMET calls an estimate "OBS" |
| Masaya (MHTG) | `VA CLD OBS AT 1740Z SFC/FL050` | `EST VA CLD` 09/1740Z SFC/FL050, same polygon, "NOT OBS IN STLT IMG DUE TO MET CLD" | n/a | SIGMET calls an estimate "OBS" |
| Purace (SKED) | `OBS AT 1600Z ... SFC/FL200` | OBS 09/1510Z SFC/FL190 | n/a | SIGMET 1,000 ft higher, 50 min later |
| Reventador (SEFG) | `OBS AT 1600Z ... SFC/FL140` | OBS 09/1600Z SFC/FL140 | n/a | Consistent |

Sources for the table: SIGMETs [CONFIRMED: https://aviationweather.gov/api/data/isigmet?format=json, accessed 2026-10-10]; Semeru VAA [CONFIRMED: https://volcanodiscovery.com/semeru/news/373618/vaac-advisory-2026-1150.html, accessed 2026-10-10]; Ibu VAA [CONFIRMED: https://www.volcanodiscovery.com/ibu/news/374545/vaac-advisory-2026-1146.html, accessed 2026-10-10]; VONAs [CONFIRMED: https://magma.esdm.go.id/v1/vona?code=SMR, https://magma.esdm.go.id/v1/vona?code=KRA, https://magma.esdm.go.id/v1/vona?code=DUK, https://magma.esdm.go.id/v1/vona?code=IBU, accessed 2026-10-10]; Washington VAAs [CONFIRMED: https://www.ospo.noaa.gov/VAAC/ARCH26/FUEG/2026J091854.html, https://www.ospo.noaa.gov/VAAC/ARCH26/MASA/2026J091807.html, https://www.ospo.noaa.gov/VAAC/ARCH26/PURA/2026J091539.html, https://www.ospo.noaa.gov/VAAC/ARCH26/REVE/2026J091640.html, accessed 2026-10-10].

Reading of the table (judgement): 6 of 8 SIGMETs disagree with something. In none of the 8 would taking the most conservative official statement produce a smaller area than the SIGMET. The disagreements are about evidence quality, which a dispatcher needs explained but not re-drawn.

---

## 4. The airline side

### 4.1 Who decides, and the safety risk assessment (SRA)

- "The operator is responsible for the safety of its operations, including within an area with known or forecast volcanic ash contamination" (EASA GM3 ORO.GEN.200(a)(3), ED Decision 2013/009/R, 16 Apr 2013) [CONFIRMED: https://www.easa.europa.eu/en/downloads/1979/en, accessed 2026-10-10].
- EASA SIB 2023-13 (19 Dec 2023; information only, "Recommendations are not mandatory") recommends operators develop a VA SRA (EU operators under GM2 ORO.GEN.200(a)(3); non-EU operators under ICAO Doc 9974, with no separate Europe SRA needed) and "Avoid operation in visible volcanic ash or, where visibility of the ash is impaired (IMC, night), avoid operation in discernible volcanic ash" [CONFIRMED: https://ad.easa.europa.eu/blob/EASA_SIB_2023-13.pdf/SIB_2023-13_2, accessed 2026-10-10].
- ICAO Doc 9974 ("Flight Safety and Volcanic Ash"), first edition 2012, is based on the 2010–2011 International Volcanic Ash Task Force [REPORTED: https://www.preventionweb.net/files/25588_9974unediteden1.pdf]. A file `9974_en.pdf` dated 2025-04 exists on icao.int [REPORTED: https://www.icao.int/sites/default/files/2025-04/9974_en.pdf]; its content was not opened (Cloudflare 403) [UNVERIFIED whether it is a new edition].
- UK CAA CAP 1236: commercial operators "must have an appropriate Operator Safety Risk Assessment (SRA) accepted by their National Aviation Authority" before penetrating forecast medium or high contamination, and "In areas where contamination levels are not provided, all affected airspace must be treated as forecast high" [CONFIRMED: https://www.caa.co.uk/publication/download/14978, accessed 2026-10-10].

### 4.2 What a dispatcher must do

- US Part 121: the dispatcher "shall provide the pilot in command with all available weather reports and forecasts of weather phenomena that may affect the safety of flight", and during flight "any additional available information of meteorological conditions" (14 CFR 121.601) [CONFIRMED: https://www.ecfr.gov/current/title-14/chapter-I/subchapter-G/part-121/subpart-U/section-121.601, accessed 2026-10-10].
- EASA expected initial actions at the start of an eruption: "(i) determine if any aircraft in flight could be affected, alert the crew and provide advice on re-routing and available aerodromes/operating sites as required; (ii) alert management; (iii) for flight departures, brief flight crew and revise flight and fuel planning ...; (iv) alert flight crew and operations staff to the need for increased monitoring of information (e.g. special air report (AIREP), volcanic activity report (VAR), significant weather information (SIGMET), NOTAMs and company messages)" [CONFIRMED: https://www.easa.europa.eu/en/downloads/1979/en, accessed 2026-10-10].
- EASA "enhanced flight watch": "(i) close and continuous monitoring of VAA, VAR/AIREP, SIGMET, NOTAM, ASHTAM and other relevant information ...; (ii) access to plots of the affected areas from SIGMETs, NOTAMs and relevant company information ...; (iii) communication of the latest information to crews ... in a timely fashion" (same source). This is close to a functional spec for TEPHRA.
- ICAO Doc 9691: options are "rerouting, unscheduled en-route technical stops, carriage of extra (contingency) fuel against possible en-route diversion or non-optimum flight altitudes, or cancellation"; "The aim is to avoid! Consequently, early knowledge of an event, however sketchy, will help airline operational staff"; "Dispatchers need to be in communication with their pilots en route so that a coordinated decision can be made between the pilot, the dispatcher and air traffic control"; and an aircraft projected to meet ash will not necessarily get "the most desirable air route" because of traffic and fuel [CONFIRMED: https://resources.eumetrain.org/data/1/144/media/paper/ManualonVolcanicAsh-ICAO.pdf, accessed 2026-10-10].
- OPSGROUP's January 2026 guidance tells operators to treat SIGMETs as "the operationally binding product", use ASHTAMs for airport-level impacts, and draw a route that is sensible "without being overly conservative" [CONFIRMED: https://ops.group/blog/volcanoes-ash-and-better-forecasts-meet-qva/, accessed 2026-10-10].

### 4.3 "Avoid" vs concentration zones

- ICAO Doc 9691: "there are no agreed values of ash concentration which constitute a hazard to jet aircraft engines ... the recommended procedure ... regardless of ash concentration — AVOID AVOID AVOID" [CONFIRMED: https://resources.eumetrain.org/data/1/144/media/paper/ManualonVolcanicAsh-ICAO.pdf, accessed 2026-10-10].
- European zones (EUR Doc 019, restated by EASA SIB 2023-13), "in 3 altitude bands": Low (cyan) > 0.2 × 10⁻³ g/m³ and ≤ 2 × 10⁻³ g/m³; Medium (grey) > 2 × 10⁻³ and < 4 × 10⁻³ g/m³; High (red) ≥ 4 × 10⁻³ g/m³ [CONFIRMED: https://ad.easa.europa.eu/blob/EASA_SIB_2023-13.pdf/SIB_2023-13_2, accessed 2026-10-10]. In mg/m³ these are 0.2 / 2 / 4. Iceland's 2026 AIC adds that High also covers "areas of contaminated airspace where no ash concentration guidance is available" [CONFIRMED: https://eaip.isavia.is/A_09-2026_2026_10_01/eAIC/B%2002-2026_2026_01_22/BI-AIC-en-GB.html, accessed 2026-10-10].
- Why the rest of the world uses "avoid": concentration charts exist only where London/Toulouse produce them; CAP 1236 notes "Some Volcanic Ash Advisory Centres (VAACs) in other parts of the world may not differentiate between different levels of contamination", and "in some areas of the world only a SIGMET or Notice to Airmen (NOTAM) may be published" [CONFIRMED: https://www.caa.co.uk/publication/download/14978, accessed 2026-10-10]. No APAC VAA read for this file carried a concentration.
- Quantitative Volcanic Ash (QVA) "became an official ICAO product on 27 November 2025", issued first by London and Toulouse, with others expected "over the following year"; the London API gives concentration and probability up to FL600 in 3-hourly steps to 24 h [CONFIRMED: https://ops.group/blog/volcanoes-ash-and-better-forecasts-meet-qva/, accessed 2026-10-10]. Whether Tokyo or Darwin issue QVA as of October 2026 was not established [UNVERIFIED]; the 2026 APAC VAAC management report that would say so was not readable.

### 4.4 Typical actions

From the sources in 4.2: pre-departure — delay, cancel, reroute, carry extra fuel, change alternates, plan a technical stop, plan a non-optimum level; airborne — continue (clear of ash), lateral reroute, level change, hold (ATC-dependent), divert. Recent APAC examples: on 13 Nov 2024 Jetstar paused Bali flights saying it was "currently not safe", Virgin Australia cancelled 10 services, and the airport reported 26 domestic and 64 international cancellations including airlines from Singapore, Hong Kong, Qatar, India and Malaysia [REPORTED: https://www.aljazeera.com/economy/2024/11/13/airlines-cancel-bali-flights-after-volcano-spews-ash-miles-into-the-sky]. Airline decisions in that event differed by carrier [REPORTED: same URL], which is consistent with operator-specific SRAs.

### 4.5 Distances and flight-level margins

- No global lateral number exists in the documents read. NOTAM templates leave it to the State: "REMAIN AT LEAST XXXNM CLEAR OF VOLCANO" [CONFIRMED: https://volcanoes.usgs.gov/vsc/file_mngr/file-138/EUR%20Doc%20019.pdf, accessed 2026-10-10].
- Iceland: "it is likely that an initial Danger Area will be established within a 120 NM radius around the volcano site or 60NM downwind from the site, if wind direction is known" [CONFIRMED: https://www.caa.co.uk/publication/download/14978, accessed 2026-10-10].
- Vertical (UK policy): treat significant contamination as "a 'solid object'", with "the assumed MSA ... at least 2,000 ft above the top of the ash cloud"; for underflight "the maximum usable level beneath a forecast Volcanic Ash Moderate or High Contamination Area will be 2,000 ft below the promulgated base" [CONFIRMED: https://www.caa.co.uk/publication/download/14978, accessed 2026-10-10].
- Operators should "use the most recent data from a recognised source for planning, with suitable safety margins" and "where possible, laterally avoid forecast areas of ash contamination" (same source).
- A general-audience article says crews meeting ash should deviate at least 20 nm on the upwind side [REPORTED: https://simpleflying.com/how-airline-pilots-handle-volcanic-ash/]. Treat as unsourced practice.
- A commercial provider triggers its own "enhanced" ash SIGMETs at "6,000 feet above the volcano's summit or 10,000 feet above ground, and extends over 50 nautical miles" [CONFIRMED: https://www.weathercompany.com/blog/volcanic-ash-and-aviation-safety-protecting-planes-passengers/, accessed 2026-10-10].

### 4.6 Fuel, alternates, ETOPS

- CAP 1236: "sufficient fuel is carried such that should a diversion be required, either en-route or at the destination, a diversion airfield available, and not affected by any forecast ash, may be reached with normal reserves" [CONFIRMED: https://www.caa.co.uk/publication/download/14978, accessed 2026-10-10].
- EASA: account for "fuel requirements for re-routeing and extended holding", "maximum allowed distance from a suitable aerodrome", "availability of aerodromes ... outside the forecast contaminated area", and "drift down and emergency descent considerations"; "take account of the risk of cabin depressurisation or engine failure resulting in the inability to maintain level flight above a volcanic cloud, especially when conducting ETOPS operations" [CONFIRMED: https://www.easa.europa.eu/en/downloads/1979/en, accessed 2026-10-10].
- US ETOPS threshold: no route point "Farther than a flying time from an Adequate Airport (at a one-engine-inoperative cruise speed under standard conditions in still air) of 60 minutes for a two-engine airplane or 180 minutes for a passenger-carrying airplane with more than two engines" without ETOPS approval (14 CFR 121.161) [CONFIRMED: https://www.ecfr.gov/current/title-14/chapter-I/subchapter-G/part-121/subpart-I/section-121.161, accessed 2026-10-10].
- US flag-operation fuel (turbine, non-turboprop): destination, then 10 % of trip time, then most distant alternate, then "30 minutes at holding speed at 1,500 feet above the alternate" (14 CFR 121.645(b)) [CONFIRMED: https://www.ecfr.gov/current/title-14/chapter-I/subchapter-G/part-121/subpart-U/section-121.645, accessed 2026-10-10].
- The maths TEPHRA can honestly do (judgement): (a) minutes to cone edge = along-track distance ÷ ground speed; (b) extra track miles for a lateral reroute around the cone + buffer; (c) whether the planned/nearest alternate lies inside the cone and whether an ash-free alternate exists within the ETOPS rule time at an assumed one-engine-inoperative speed; (d) whether an aircraft above the ash could descend (depressurisation to roughly FL100, not checked here [UNVERIFIED]) without entering the layer. Fuel in kilograms requires type, weight and wind data that ADS-B does not carry; show it only as a labelled estimate or leave it to the dispatcher.

### 4.7 Talking to the crew

- The channels named in the regulations read here are "company messages" and en-route communication between dispatcher and pilot (EASA GM3 and Doc 9691, URLs above). ACARS free-text uplinks are the usual medium for company messages [UNVERIFIED: no source opened]. No public example of airline company advisory text for ash was found [UNVERIFIED].
- A draft TEPHRA advisory should therefore mirror the elements regulators list: affected flight, source products with issue times, the affected layer (FL band) and time window, recommended action, alternates outside the area, and a request for crew reports (EASA asks for reports even of "any time that volcanic ash is not encountered in an area where it was forecast to be") [CONFIRMED: https://www.easa.europa.eu/en/downloads/1979/en, accessed 2026-10-10].

---

## 5. The science

### 5.1 Himawari status and bands

- JMA switched from Himawari-8 to Himawari-9 on 13 Dec 2022, and Himawari-10 manufacturing was contracted in March 2023 "with initial operation scheduled for FY 2029" [CONFIRMED: https://www.data.jma.go.jp/mscweb/en/himawari89/himawari_cast/Newsletter/HimawariCast_Newsletter_No.16.pdf, accessed 2026-10-10].
- WMO OSCAR now lists Himawari-10 "Launch ≥2030 EOL ≥2046", last updated 2026-06-08 [CONFIRMED: https://space.oscar.wmo.int/satellites/view/himawari_10, accessed 2026-10-10]. Himawari-10 is not operational in 2026; every 2026 VAA read cites "HIMAWARI-9".
- Bands used for ash: B11 8.6 µm, B13 10.4 µm, B14 11.2 µm, B15 12.4 µm (centre wavelengths as listed in JMA's RGB guides) [CONFIRMED: https://www.jma.go.jp/jma/jma-eng/satellite/VLab/QG/RGB_QG_Ash_en.pdf, accessed 2026-10-10].
- JMA's public real-time site offers a "Target Area" product labelled "Tropical cyclone or volcanic ash" alongside 10-minute regional frames [CONFIRMED: https://www.data.jma.go.jp/mscweb/data/himawari/, accessed 2026-10-10]. The 2.5-minute target-area cadence is from memory [UNVERIFIED].

### 5.2 Split-window brightness temperature difference (BTD)

- Physics: silicate ash has lower emissivity at ~11 µm than at ~12 µm, water/ice the reverse, so T(11) − T(12) separates ash (negative) from cloud; "The technique works best during the time period when the ash has dispersed from the cone and become semi-transparent, but not yet of such a low density that it has become undetectable" [CONFIRMED: https://resources.eumetrain.org/data/1/144/media/paper/ManualonVolcanicAsh-ICAO.pdf, accessed 2026-10-10].
- Failure conditions in the same manual: clouds "very difficult to distinguish from water/ice cloud" when "abnormally high contamination of the ash cloud by water", "not unusual in 'young' ash clouds within a few hours of the volcanic eruption and in deep moist tropical conditions"; also overshooting tops, viewing geometry, pixel alignment [CONFIRMED: same URL]. Young, wet, tropical plumes are exactly the Indonesian case.
- Tropical water vapour can mask the reverse-absorption signal [REPORTED: https://ramsdis.cira.colostate.edu/rammb/resources/docs/pavolonis_etal_jtech.pdf]. For Himawari, the Bureau of Meteorology reported ice-rich tropical eruption clouds giving "a very strong positive signature" in the 10.4–12.4 µm BTD, i.e. the opposite sign to the textbook ash test [REPORTED: https://ams.confex.com/ams/98Annual/webprogram/Paper334907.html].
- In Himawari bands the test is B13 − B15 (10.4 − 12.4 µm); a JMA slide set reports ash "essentially 'disappears'" with B14 − B15 [REPORTED: https://old.wmo.int/aemp/sites/default/files/Satellite_Comparison_Tokyo.pdf].

### 5.3 Dust RGB and Ash RGB

- JMA Dust RGB recipe: red = B15 − B13, range −4 to 2 K, gamma 1.0; green = B13 − B11, 0 to 15 K, gamma 2.5; blue = B13, 261 to 289 K, gamma 1.0; useful for "黄砂や火山灰等" (yellow sand, volcanic ash and similar) and day-night cloud analysis; JMA notes the Ash RGB uses the same bands with different ranges and gammas "for detecting volcanic ash and SO2" [CONFIRMED: https://www.data.jma.go.jp/mscweb/ja/prod/rgb_dst.html, accessed 2026-10-10].
- JMA Dust RGB Quick Guide: one colour class is "Dust (yellow sand)/ Volcanic ash"; limitations include "Difficulty of identifying thin or low-level dust clouds over sea areas", "Disturbance from high-level clouds over dust clouds", and "Poor display of low-level clouds (with dust cloud shading similar to that of low-level clouds)"; surface colours differ between day and night [CONFIRMED: https://www.jma.go.jp/jma/jma-eng/satellite/VLab/QG/RGB_QG_Dust_en.pdf, accessed 2026-10-10].
- JMA Ash RGB Quick Guide: ash appears as "red shading based on concentration", SO2 as "bright green", mixed as a combined colour; limitations: "Inability to estimate volcanic plume height and concentration from Ash RGB data alone", "Difficulty of identifying very thin or lower-level volcanic plumes", "Disturbance from high-level clouds over volcanic plumes", and colour contrast that depends on viewing angle [CONFIRMED: https://www.jma.go.jp/jma/jma-eng/satellite/VLab/QG/RGB_QG_Ash_en.pdf, accessed 2026-10-10].
- The public JPEG list for "Southeast Asia 3" offers 16 products per 10-minute slot (`b13, b03, b08, b07, arm, dnc, dms, tre, cve, ngt, dst, dsl, snd, vir, irv, trm`); `dst` is the Dust RGB; no Ash RGB code appears [CONFIRMED: https://www.data.jma.go.jp/mscweb/data/himawari/list_se3.html, accessed 2026-10-10]. The same 16 codes appear for "High-Resolution Asia 6" (Timor-Leste area) [CONFIRMED: https://www.data.jma.go.jp/mscweb/data/himawari/list_ha6.html, accessed 2026-10-10]. File names carry only HHMM, so frames are overwritten daily (same sources).
- Agent's own look (an observation, not a published finding): the `se3_dst_1800.jpg` frame is 1101 × 501 px for about 55° × 25°, i.e. about 0.05° (≈5.5 km) per pixel; its burned-in label reads "Himawari-9 DST 09.OCT.2026 18:10UTC" although the file name says 1800; at that time (01:00 local) all of Java, Bali and Nusa Tenggara render pinkish-violet, northern Australia is pink, and no plume is distinguishable at Semeru, where a SIGMET for SFC/FL150 was in force [CONFIRMED: https://www.data.jma.go.jp/mscweb/data/himawari/img/se3/se3_dst_1800.jpg, accessed 2026-10-10]. A model looking for "pink = ash" would flag all of Java.

### 5.4 SO2 as a proxy

- Doc 9691: "SO2 detection cannot be used to define the extent of the volcanic ash because each has a different dispersal mechanism, but its presence in high concentration does confirm that a cloud is of volcanic origin"; "The edge of the detected SO2 cloud does not necessarily coincide with the edge of the volcanic ash cloud" [CONFIRMED: https://resources.eumetrain.org/data/1/144/media/paper/ManualonVolcanicAsh-ICAO.pdf, accessed 2026-10-10].
- TROPOMI on Sentinel-5P: launched 13 Oct 2017; sun-synchronous with 13:30 local ascending node; "full daily surface coverage ... for latitudes > 7° and < -7°, and better than 95 % coverage for latitudes in the interval [-7°, 7°]" [CONFIRMED: https://sentiwiki.copernicus.eu/web/s5p-mission, accessed 2026-10-10]. One afternoon pass per day, UV-based, so no night SO2 from TROPOMI (judgement from the orbit and the UV method described for TOMS in Doc 9691).
- SACS (BIRA-IASB, an ESA project "supporting the Volcanic Ash Advisory Centers") provides near-real-time SO2 and ash notifications from OMI, GOME-2, OMPS, IASI, AIRS, and now TROPOMI SO2 and SO2 height [CONFIRMED: https://sacs.aeronomie.be/, accessed 2026-10-10]. OMI's current status was not checked [UNVERIFIED].

### 5.5 Detection limits to state plainly in the demo

- Thin ash: undetectable below some optical depth (Doc 9691, 5.2); VADUGS detects "60–70 % of all ash-loaded samples" with mass loading under 0.1 g/m² [REPORTED: https://nhess.copernicus.org/articles/22/1029/2022/].
- Ice-coated/wet ash and tropical moisture: 5.2 above.
- Meteorological cloud above ash: listed by JMA as a limitation of both RGBs (5.3); Tokyo's own RMKs cite it (3.1.1).
- Night: IR products work day and night (JMA lists "Daytime/nighttime applicability" for both RGBs [CONFIRMED: https://www.jma.go.jp/jma/jma-eng/satellite/VLab/QG/RGB_QG_Ash_en.pdf, accessed 2026-10-10]); ground observation, webcams, true-colour imagery and UV SO2 do not.
- Low plumes: most Indonesian SIGMETs on the snapshot topped at FL060–FL150 over summits of 1.3–3.7 km (Section 3.7), close to the "lower-level volcanic plumes" JMA says are hard to identify.

### 5.6 Published accuracy of ML ash detection

| System | Data | Result | Tag |
|---|---|---|---|
| VADUGS neural network | SEVIRI (Meteosat), trained on synthetic radiances | POD 0.84, false-alarm rate 0.05 against independent simulations | [CONFIRMED: https://nhess.copernicus.org/articles/22/1029/2022/, accessed 2026-10-10] |
| INGV MLP + plume tracking | 1,259 SEVIRI images, Etna | Balanced accuracy up to 92.0 %; detected 66.0 %, 48.5 %, 84.1 % of volcanic-cloud pixels in three unseen events; false alarms 7.7 %, 4.0 %, 21.9 % | [CONFIRMED: https://amt.copernicus.org/articles/19/4255/2026/, accessed 2026-10-10] |
| VGG16-U-Net hybrid | SEVIRI Ash RGB | Accuracy ~0.90; SVM baseline 74 % F1 | [REPORTED: https://www.sciencedirect.com/science/article/pii/S0377027324000386] |
| Pix2Pix GAN | multispectral imagery | "satisfactory" by loss/accuracy plots and visual inspection; no headline number in abstract | [CONFIRMED: https://arxiv.org/abs/2307.12970, accessed 2026-10-10] |
| SVM, Himawari-8 with Tokyo VAAC polygons as coarse labels | Himawari-8 | Student report; no accuracy found in snippet | [REPORTED: https://eodg.atm.ox.ac.uk/eodg/vacation_reports/2021Waugh.pdf] |
| JMA operational Himawari ash product | Himawari-8/9 | "Bayesian method and grouping technique"; based on NOAA GEOCAT/VOLCAT | [REPORTED: https://www-cdn.eumetsat.int/files/2020-04/pdf_conf_p_s11_12_tsuchiya_v.pdf] |
| Weathernews AI | Himawari IR | Operational since 2021-04-26; no accuracy published in the release | [CONFIRMED: https://global.weathernews.com/news/16070/, accessed 2026-10-10] |

No peer-reviewed deep-learning Himawari ash detector with POD/FAR was found in 3 searches (Search log).

### 5.7 Vision-language models on ash plumes

- arXiv API, 2026-10-10: `"volcanic ash" AND "language model"` → 0; `"volcanic ash" AND "vision language"` → 0; `volcanic AND "multimodal large language model"` → 0; `"volcanic ash" AND Himawari` → 0; `"volcanic ash"` alone → 35 [CONFIRMED: https://export.arxiv.org/api/query?search_query=all:%22volcanic%20ash%22, accessed 2026-10-10].
- A web search found general GPT-4V/Gemini comparisons and medical-imaging evaluations but no VLM evaluation on volcanic plumes (Search log #15).
- Conclusion: no published record exists. Gemini reading ash in Himawari JPEGs is an untested claim.

---

## 6. Judging the mechanic

### Q1. Is "sources contradict each other" real and frequent?

Yes. Evidence: the live table (6 of 8 SIGMETs in disagreement, Section 3.7); the OBS/EST label problem (3.1.1); VONA night blindness and event-driven silence (3.4); reported height errors of up to 10,000 ft and mis-delivered VONAs (3.6); and the fact that EASA writes conflict resolution into operator guidance (4.2). Caveat: the disagreements are mostly about whether ash was seen, by whom and when. The polygons are usually identical between VAA and SIGMET. A rule ("official union, labelled by evidence type") resolves most cases; the LLM is useful for reading RMK/VONA prose and explaining, not for inventing geometry.

### Q2. Is a cone that never shrinks below the official polygon operationally sensible?

Yes, with conditions. Supporting text: operators form an "operator specific no fly zone" treating "VAAC and NAA promulgated information ... as primary information" (CAP 1236 2.19) and use "suitable safety margins" (2.27) [CONFIRMED: https://www.caa.co.uk/publication/download/14978, accessed 2026-10-10]; EASA tells operators to treat the area "to be overflown as it would mountainous terrain, modified in accordance with its safety risk assessment" [CONFIRMED: https://www.easa.europa.eu/en/downloads/1979/en, accessed 2026-10-10]; a commercial provider already sells "enhanced" ash SIGMETs beyond VAAC bulletins (4.5). Limits: EASA and European States want to "avoid unnecessary airspace closures" [CONFIRMED: https://ad.easa.europa.eu/blob/EASA_SIB_2023-13.pdf/SIB_2023-13_2, accessed 2026-10-10] and OPSGROUP warns against routes that are "overly conservative" (4.2). So: the extension must be bounded, shown as a separate layer with its reason and source, never called a closure, and adjustable by the dispatcher. A dispatcher would reject an opaque AI area that is bigger "because the model said so".

### Q3. What would a real dispatcher want?

From regulator and practitioner text (no interviews, forum threads or IFALDA material could be read: PPRuNe returned 403 and the search budget ran out):
- One screen with VAA, SIGMET, NOTAM/ASHTAM, VAR/AIREP plotted (EASA enhanced flight watch).
- Which airborne flights could be affected and when, with alternates outside the area (EASA initial action (i)).
- Departures to re-plan: route, fuel for re-routing and extended holding, alternates (EASA (iii); CAP 1236 2.20).
- Vertical picture: which FL band, overflight/underflight with 2,000 ft margins, drift-down feasibility (CAP 1236; EASA routing policy).
- Early warning "however sketchy" with regular updates (Doc 9691).
- Not over-conservative routes; SIGMET treated as binding (OPSGROUP).
- "all relevant information in one place" for decision-makers (The Weather Company's HOTL reports) [CONFIRMED: https://www.weathercompany.com/blog/volcanic-ash-and-aviation-safety-protecting-planes-passengers/, accessed 2026-10-10].

### Q4. Failure modes that would embarrass the demo

1. Cloud or land read as ash: Dust RGB renders night land pink and gives dust and ash one colour (5.3).
2. Stale or expired products: SIGMET Ibu 10 was served at 19:28Z with validity ending 19:30Z (Section 3.3 source); the JMA "Darwin" page is a backup list last updated 1 Oct (Section 1); VONAs can be 10 days old (3.4).
3. Vertical error: flagging a flight at FL370 over a SFC/FL150 cloud as "inside" is wrong; ignoring that the same flight could not descend through the layer after a depressurisation is also wrong (4.6).
4. Altitude reference mix-up: on the snapshot near Jakarta, ADS-B `alt_geom` exceeded `alt_baro` by 2,050–2,325 ft at cruise (e.g. 37,325 vs 35,000) [CONFIRMED: https://api.adsb.lol/v2/point/-6.1/106.7/250, accessed 2026-10-10]. SIGMET FLs are pressure levels; comparing them with geometric altitude shifts every aircraft up by ~2,000 ft.
5. Climbing aircraft projected level: one A320 at `alt_baro` 12,950 ft had `nav_altitude_mcp` 28,992 and `baro_rate` 2,176 fpm (same source).
6. Thin night traffic: only 7 aircraft within the 250-unit radius of Jakarta at 19:43:58Z (02:44 local) (same source). (The radius unit is assumed to be nautical miles [UNVERIFIED].)
7. Fake volcano from a Tokyo backup "NOTICE 999999" message (Section 2).
8. Duplicate SIGMET records ("F" series) inflating counts (Section 1).
9. Reading "Ash-cloud is not observed" or "VA NOT IDENTIFIABLE" as "no ash" (3.1.1, 3.4).
10. Degree-minute coordinates parsed as decimals (`N0129` = 1°29′ = 1.483°, not 1.29°) (3.1.2).
11. Darwin feed unavailable: the BoM page answers automated requests with "Your access is blocked due to the detection of a potential automated access request. The Bureau of Meteorology website does not support web scraping" and points to an anonymous FTP channel [CONFIRMED: http://www.bom.gov.au/aviation/volcanic-ash/, accessed 2026-10-10].

---

## Conflicts with our idea

| # | Conflict | Grade | What would have to change |
|---|---|---|---|
| C1 | The satellite-reading step has no scientific footing in the planned form: public JMA JPEGs have Dust RGB but no Ash RGB, ~5.5 km pixels, night land renders pink like ash, and JMA lists low/thin plumes and overlying cloud as limits; purpose-built NNs on raw radiances reach 48.5–84.1 % pixel recall; no VLM has a published record (5.3, 5.6, 5.7). | SERIOUS | Remove the image from the geometry path. Show the frame as context only, labelled "not used to draw the cone", or compute a B13−B15 BTD from raw data in code (data access not verified here). Say in the video that VAACs, not Gemini, detect ash. |
| C2 | Most contradictions are evidence-label disagreements with identical polygons (3.7), so a judge who knows aviation may see the "reconciliation" as a lookup. | SERIOUS | Re-pitch Gemini's job as: read RMK and VONA prose, classify each source (observed / estimated / ground-only / night / cloud-obscured / stale), explain the disagreement in dispatcher language, and draft the advisory. Keep geometry in code. |
| C3 | Vertical logic is where an expert judge will test the tool (FL vs pressure altitude vs geometric altitude; 2,000 ft margins; drift-down). The plan mentions neither. | SERIOUS | Implement the vertical rules in "What this means for the build"; show one aircraft correctly classed "above layer, escape check" rather than "exposed". |
| C4 | Most ash decisions are pre-departure (route, fuel, alternates, delay, cancel), but ADS-B shows only airborne aircraft. | MINOR | Frame the airborne view as EASA's "enhanced flight watch" and initial action (i); add a short demo list of scheduled departures (fictional ops queue) for the pre-departure case. |
| C5 | HYPOTHESIS cones allow only "hold/monitor"; airborne holding is ATC-dependent and holding near an unconfirmed plume is not obviously safer. | MINOR | Allow "monitor", "request crew report (VAR)", "delay departure" for hypothesis cones; keep reroute/divert gated on an official product. |
| C6 | "EASA SIB 2010-17R8" and the 0.2/2/4 zones as a general rule: the SIB was replaced by SIB 2023-13 in Dec 2023, and the zones apply where concentration charts exist (Europe). | MINOR | Cite SIB 2023-13 and EASA GM3 ORO.GEN.200(a)(3); state that APAC uses "avoid" with no concentrations. |
| C7 | Darwin VAAC text has no keyless live feed known to work: BoM blocks scraping; the JMA Darwin page is backup-only; VolcanoDiscovery republishes but rate-limits (403 after a few requests). | SERIOUS for the Indonesia demo | Use SIGMET JSON as the Indonesian official floor; test BoM anonymous FTP for VAA text (unverified); cache and label any republished VAA as secondary. |
| C8 | No NOTAM/ASHTAM input although regulators list it alongside VAA and SIGMET. | MINOR | Add a manual-paste NOTAM field or state the omission on screen. |
| C9 | Competitors already sell parts of this: Weathernews AI detection (2021); The Weather Company enhanced ash SIGMETs, flight-plan guidance and HOTL consolidated reports (2024). | MINOR | Claim novelty only for per-flight drafted advisories with source-by-source evidence classification behind a human gate. |
| C10 | Fuel in kg cannot be derived from ADS-B. | MINOR | Show minutes and track miles; fuel only as a labelled assumption or left to the dispatcher. |
| C11 | Over-extension risk: an unbounded union of hedges would create alarm fatigue and contradict "avoid unnecessary closures". | MINOR | Cap and itemise each margin (e.g. vertical 2,000 ft per CAP 1236; lateral margin as a configurable, labelled operator setting). |
| C12 | The idea of a cone that never shrinks below official areas. | NONE | Supported by CAP 1236 and EASA GM3 (see support section). |

---

## What this supports

- The core job exists in regulation: EASA GM3 ORO.GEN.200(a)(3) asks operators to "correctly resolve any conflicts among data sources", run enhanced flight watch with "plots of the affected areas", and at eruption onset "determine if any aircraft in flight could be affected, alert the crew and provide advice on re-routing and available aerodromes" [CONFIRMED: https://www.easa.europa.eu/en/downloads/1979/en, accessed 2026-10-10].
- Contradictions are visible live on any given night (3.7), so the demo does not need staged data.
- The "never shrink" rule matches operator practice: official information is "primary information" and operators add "suitable safety margins" [CONFIRMED: https://www.caa.co.uk/publication/download/14978, accessed 2026-10-10].
- Official texts sometimes state an eruption height and direction with no polygon (Mayon 2026/803), the exact gap a labelled hypothesis cone can fill [CONFIRMED: https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20261007_27303000_0803_Text.html, accessed 2026-10-10].
- Remarks fields carry the evidence basis in compressed English ("VA AREA IS AN ESTIMATED AREA", "OBSCD VA EMS PSBLY CONTNG BASED ON PREV ACTIVITY"), which is a natural LLM extraction task (3.1.1).
- Night is the dangerous case (5 of 9 class-4 encounters at night [CONFIRMED: https://pubs.usgs.gov/ds/545/DS545.pdf, accessed 2026-10-10]) and the case where ground VONAs go blind; a tool that marks "night: ground observation blind" adds real value.
- Damaging encounters cluster early and near the source: "Most of the damaging encounters occurred within 24 hours of the onset of ash production or at distances less than 1,000 kilometers" [CONFIRMED: https://pubs.usgs.gov/ds/545/DS545.pdf, accessed 2026-10-10], which is when products disagree most and is the time window TEPHRA watches.
- Human approval is the norm: decisions rest "with the operator and aircraft commander" (CAP 1236 2.16) [CONFIRMED: https://www.caa.co.uk/publication/download/14978, accessed 2026-10-10].

---

## What this means for the build (rules the code must enforce)

Parsing and units
1. Parse VAA/SIGMET coordinates as degrees and minutes (`N0129` → 1 + 29/60). Never treat them as decimals.
2. FL = pressure altitude in hundreds of feet. `SFC/FL150` = 0–15,000 ft pressure altitude; `FL200/350` = 20,000–35,000 ft (base above surface); support `TOP FLxxx` and `ABV FLxxx` if seen (forms not observed today [UNVERIFIED]).
3. VONA heights are feet/metres AMSL and "above summit"; convert to an approximate FL with a visible "approx., AMSL→FL" label. `SOURCE ELEV`/`SUMMIT ELEV` may be in M or FT.
4. Compare aircraft altitude using ADS-B `alt_baro` (pressure altitude, may be the string "ground"), never `alt_geom` (≈2,000 ft higher at cruise in the tropics on the snapshot).
5. Speeds in knots (SIGMET `MOV ... KT`, ADS-B `gs`); headings in degrees true (`track`).
6. Accept `+6 HR` and `+6HR`; `NXT ADVISORY` in the three observed styles; optional `AVIATION COLOUR CODE`.

Source state and staleness
7. Drop SIGMETs with `validTimeTo` ≤ now; de-duplicate AWC records by `rawSigmet` and treat series IDs ending in "F" as the forecast polygon of the same SIGMET.
8. Mark a VAA overdue when now > its `NXT ADVISORY` time; never treat "NO FURTHER ADVISORIES" as all-clear.
9. Drop pseudo-advisories with `VOLCANO: NOTICE` (e.g. `999999`), but surface their RMK (backup handover) as a banner.
10. Store per source: issue time, observation time, validity, fetch time, URL, hash. Show age on every chip.
11. Classify every source into one evidence state: OBSERVED-SAT, OBSERVED-GROUND, ESTIMATED (EST label or RMK "ESTIMATED AREA"/"NOT IDENTIFIABLE"/"NOT OBS"), NOT-IDENTIFIABLE, NO-VA-EXPECTED, FORECAST-NOT-AVAILABLE, NIGHT-BLIND (VONA "not observed" when local solar time at the volcano is night), STALE. Use RMK text, not only the field label.
12. "Ash-cloud is not observed", "VA NOT IDENTIFIABLE" and absence of a SIGMET or VONA never reduce the area or downgrade an action.

Geometry
13. Official floor at time t = union of all valid SIGMET polygons (observed and forecast) and all VAA polygons for every layer at the bracketing time steps (union of the step before and after t, no shrinking interpolation), each with its FL band.
14. TEPHRA cone ⊇ official floor, layer by layer. Every extension is a separate, itemised margin with a reason string and source IDs (e.g. "vertical +2,000 ft: CAP 1236 policy"; "lateral +X nm: operator setting"; "drift by VONA-reported top and wind: hypothesis").
15. A cone with no official polygon under it is HYPOTHESIS and is drawn differently; it can trigger monitor / crew-report / delay-departure, not reroute or divert.
16. SIGMETs are per FIR: do not assume the SIGMET covers the whole cloud; use the VAA for cloud-wide extent and flag FIRs the VAA enters with no SIGMET.

Aircraft and exposure
17. Classify each aircraft in 3D: INSIDE (horizontal and vertical overlap with the layer ± 2,000 ft), ABOVE-LAYER (show an "escape check": can it descend outside the area?), BELOW-LAYER, NEAR (within lateral margin), CLEAR.
18. Project at most a short horizon (e.g. 30–60 min) along current `track` and `gs`, using `baro_rate` and `nav_altitude_mcp` for vertical; label the projection "if current track and climb held".
19. Report minutes and track miles to the cone; fuel only with a labelled per-type assumption, or "dispatcher to confirm".
20. For diversions, reject alternates inside the cone or under forecast ash, per CAP 1236 2.20.

Language and gating
21. Never write "airspace closed"; write "company advisory". Cite the binding product (SIGMET) first.
22. Every draft lists its sources with issue times and evidence state, the FL band and time window, the recommended action, alternates outside the area, and a request for a crew VAR, including "ash not encountered" reports.
23. The satellite frame, if shown, is labelled "context only; not used to draw the cone" unless a code-computed BTD layer exists.
24. Night flag: compute local time at the volcano (WIB/WITA/WIT offsets) and show "ground observation blind" when VONAs say "not observed" at night.

---

## Glossary

- AIREP / VAR: special air report / volcanic activity report from a crew.
- AMSL: above mean sea level.
- ASHTAM: NOTAM variant for volcanic activity, items A–K, item E colour code.
- BTD: brightness temperature difference between IR bands; for ash, B13 (10.4 µm) − B15 (12.4 µm) on Himawari.
- CVGHM / PVMBG: Indonesia's Center for Volcanology and Geological Hazard Mitigation; publishes VONAs on MAGMA.
- DTG: date-time group.
- Dust RGB / Ash RGB: false-colour composites of the same three IR differences with different scaling; JMA publishes Dust RGB JPEGs publicly.
- EST / OBS: estimated / observed ash cloud in a VAA.
- ETOPS: extended operations; for US twins, beyond 60 min one-engine-inoperative flying time from an adequate airport needs approval.
- FIR: flight information region; SIGMETs are issued per FIR.
- FL: flight level, pressure altitude in hundreds of feet.
- IAVW: International Airways Volcano Watch.
- MSA: minimum safe altitude (CAP 1236 uses it for overflight above ash).
- MWO: meteorological watch office; issues SIGMETs.
- NOTAM: notice to airmen.
- QVA: quantitative volcanic ash forecast (concentrations), ICAO product since 27 Nov 2025, London and Toulouse first.
- RMK: remarks line in a VAA.
- SIGMET (WV): significant meteorological information for volcanic ash, ≤ 6 h validity.
- SO2: sulphur dioxide; confirms volcanic origin, does not define ash extent.
- SRA: safety risk assessment (operator's VA SRA).
- TROPOMI: UV-visible spectrometer on Sentinel-5P; daily afternoon SO2.
- VAA / VAG / VAGI / VAGFN: volcanic ash advisory text / graphic / initial graphic / hourly forecast graphic.
- VAAC: volcanic ash advisory centre (nine).
- VONA: volcano observatory notice for aviation.

---

## Open questions

1. Is there a keyless, permitted source for Darwin VAA text (BoM anonymous FTP path, AWC, or another distributor)? Not verified.
2. Do JMA and PHIVOLCS issue ICAO-format VONAs? Not verified.
3. Will Tokyo or Darwin issue QVA in 2026–27? The MET SG-30 (July 2026) APAC VAAC report would say; it was not readable (Cloudflare 403).
4. Is the 2025-04 `9974_en.pdf` a new edition of Doc 9974 with changed guidance? Not opened.
5. What lateral buffers do APAC airlines use in their SRAs? Not public in anything read.
6. Can Gemini distinguish ash from cloud in JMA frames at all? Requires the planned test; given C1, test on daytime cases with official polygons as ground truth, and include night and quiet cases.
7. Which Annex 3 amendment changed `SUMMIT ELEV` to `SOURCE ELEV` and dropped the colour code from VAAs, and when?
8. Is the adsb.lol `/v2/point` radius in nautical miles?
9. Is Himawari raw (HSD) data available keyless for a code-computed BTD (e.g. a public cloud bucket)? Not checked.
10. Direct dispatcher views (PPRuNe, IFALDA, interviews) remain unread; one short call with a working dispatcher would settle Q2 and Q3 better than documents.

---

## Sources

All accessed 2026-10-10 (IST) unless marked REPORTED (seen only through search results).

Opened (CONFIRMED):
- https://aviationweather.gov/api/data/isigmet?format=json
- https://ds.data.jma.go.jp/svd/vaac/data/vaac_list.html
- https://ds.data.jma.go.jp/svd/vaac/data/vaac_darwin_list.html
- https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20261008_27307000_0021_Text.html
- https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20261008_27307000_0022_Text.html
- https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20261008_27307000_0023_Text.html
- https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20261008_27307000_0024_Text.html
- https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20261008_28208001_0277_Text.html
- https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20261008_28208001_0279_Text.html
- https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20261007_27303000_0803_Text.html
- https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20260923_26803000_1081_Text.html
- https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20260923_99999902_0003_Text.html
- https://www.data.jma.go.jp/vaac/data/Inquiry/vaac_operation.html
- https://www.data.jma.go.jp/vaac/data/Inquiry/graphic_and_dispersion.htm
- https://www.bom.gov.au/aviation/data/education/volcanic-ash-advisories.pdf
- http://www.bom.gov.au/aviation/volcanic-ash/ (block message)
- https://volcanodiscovery.com/semeru/news/373618/vaac-advisory-2026-1150.html
- https://www.volcanodiscovery.com/ibu/news/374545/vaac-advisory-2026-1146.html
- https://magma.esdm.go.id/v1/vona
- https://magma.esdm.go.id/v1/vona/22889?signature=5412ce61fc8ab19051a3a1682ceb3ec3cfcf9aca8457455414c1cadda2305bad
- https://magma.esdm.go.id/v1/vona?code=SMR
- https://magma.esdm.go.id/v1/vona?code=KRA
- https://magma.esdm.go.id/v1/vona?code=DUK
- https://magma.esdm.go.id/v1/vona?code=IBU
- http://kvert.febras.net/van/
- https://www.ospo.noaa.gov/products/atmosphere/vaac/messages.html
- https://www.ospo.noaa.gov/VAAC/ARCH26/FUEG/2026J091854.html
- https://www.ospo.noaa.gov/VAAC/ARCH26/MASA/2026J091807.html
- https://www.ospo.noaa.gov/VAAC/ARCH26/REVE/2026J091640.html
- https://www.ospo.noaa.gov/VAAC/ARCH26/REVE/2026J090455.html
- https://www.ospo.noaa.gov/VAAC/ARCH26/PURA/2026J091539.html
- https://www.ospo.noaa.gov/VAAC/ARCH26/SANTAMA/2026A011137.html
- https://en.wikipedia.org/wiki/Volcanic_Ash_Advisory_Center
- https://ad.easa.europa.eu/blob/EASA_SIB_2023-13.pdf/SIB_2023-13_2
- https://www.easa.europa.eu/en/newsroom-and-events/news/easa-issues-safety-information-bulletin-volcanic-ash-events
- https://www.easa.europa.eu/en/downloads/1979/en
- https://www.caa.co.uk/publication/download/14978
- https://eaip.isavia.is/A_09-2026_2026_10_01/eAIC/B%2002-2026_2026_01_22/BI-AIC-en-GB.html
- https://resources.eumetrain.org/data/1/144/media/paper/ManualonVolcanicAsh-ICAO.pdf
- https://volcanoes.usgs.gov/vsc/file_mngr/file-138/EUR%20Doc%20019.pdf
- https://www.ecfr.gov/current/title-14/chapter-I/subchapter-G/part-121/subpart-U/section-121.601
- https://www.ecfr.gov/current/title-14/chapter-I/subchapter-G/part-121/subpart-I/section-121.161
- https://www.ecfr.gov/current/title-14/chapter-I/subchapter-G/part-121/subpart-U/section-121.645
- https://pubs.usgs.gov/ds/545/DS545.pdf
- https://www.jma.go.jp/jma/jma-eng/satellite/VLab/QG/RGB_QG_Ash_en.pdf
- https://www.jma.go.jp/jma/jma-eng/satellite/VLab/QG/RGB_QG_Dust_en.pdf
- https://www.data.jma.go.jp/mscweb/ja/prod/rgb_dst.html
- https://www.data.jma.go.jp/mscweb/data/himawari/
- https://www.data.jma.go.jp/mscweb/data/himawari/list_se3.html
- https://www.data.jma.go.jp/mscweb/data/himawari/list_ha6.html
- https://www.data.jma.go.jp/mscweb/data/himawari/img/se3/se3_dst_1800.jpg
- https://www.data.jma.go.jp/mscweb/en/himawari89/himawari_cast/Newsletter/HimawariCast_Newsletter_No.16.pdf
- https://space.oscar.wmo.int/satellites/view/himawari_10
- https://sentiwiki.copernicus.eu/web/s5p-mission
- https://sacs.aeronomie.be/
- https://nhess.copernicus.org/articles/22/1029/2022/
- https://amt.copernicus.org/articles/19/4255/2026/
- https://export.arxiv.org/api/query?search_query=all:%22volcanic%20ash%22 (and the four zero-hit queries listed in the Search log)
- https://arxiv.org/abs/2307.12970
- https://arxiv.org/abs/2510.22889
- https://global.weathernews.com/news/16070/
- https://ops.group/blog/volcanoes-ash-and-better-forecasts-meet-qva/
- https://www.weathercompany.com/blog/volcanic-ash-and-aviation-safety-protecting-planes-passengers/
- https://avweb.com/aviation-news/volcanic-ash-shuts-seven-indonesia-airport/ (opened via fetch tool; tagged REPORTED in text because it is secondary news)
- https://api.adsb.lol/v2/point/-6.1/106.7/250

Seen only through search results (REPORTED):
- https://skybrary.aero/articles/volcanic-ash-advisory-centre-vaac
- https://www.icao.int/sites/default/files/APAC/Meetings/2026/2026%20MET%20SG-30/4.%20Information%20Papers/IP03_AI5_AUS-JPN-NZL-USA_COMBINED-APAC-VAAC-MANAGEMENT-REPORT.pdf (403 on direct fetch)
- https://www.icao.int/sites/default/files/APAC/Meetings/2024/2024%20MET%20SG-28%20and%20MET%20Seminar/4-Information%20Papers/IP15_AI6_AUS-JPN-NZL_COMBINED-APAC-VAAC-MANAGEMENT-REPORT.pdf
- https://www.icao.int/sites/default/files/APAC/Meetings/2021/2021%20MET%20SG%2025/4-Information%20Papers/IP08_AI.5_AUS_VAAC-Darwin-Management-Report.pdf
- https://www.icao.int/sites/default/files/APAC/Meetings/2021/2021%20MET-S%20WG11/4-Information%20Papers/IP07_AI.6_AUS_VAAC-Darwin-Management-Report-Rev-170321.pdf
- https://www.icao.int/sites/default/files/APAC/Meetings/2021/2021%20MET-S%20WG11/3-Working%20Papers/WP07_A.I.6_AHG_SIGMET-GUIDANCE-FOR-VOLCANIC-ASH-FORECAST-TO-CROSS-FIR-BOUNDARIES.pdf
- https://www.icao.int/sites/default/files/WACAF/MeetingDocs/2025/Volcanic%20Ash/Session%207/Best-Practices-in-developing-SOP-for-Volcanic-Ash-Events.pdf
- https://www.icao.int/sites/default/files/sp-files/SAM/Documents/2023-RLA06901-PANSMET/04_Taller%20PANS-MET-Prop%20Inic%203_SVO-VONA_En_08.10.2023_EN.pdf
- https://www.icao.int/sites/default/files/sp-files/APAC/Documents/edocs/WV-SIGMET.pdf (403 on direct fetch)
- https://www.icao.int/sites/default/files/2025-04/9974_en.pdf (403 on direct fetch)
- https://www.preventionweb.net/files/25588_9974unediteden1.pdf (download interstitial only)
- https://link.springer.com/chapter/10.1007/11157_2016_45
- https://ramsdis.cira.colostate.edu/rammb/resources/docs/pavolonis_etal_jtech.pdf
- https://ams.confex.com/ams/98Annual/webprogram/Paper334907.html
- https://old.wmo.int/aemp/sites/default/files/Satellite_Comparison_Tokyo.pdf
- https://www.sciencedirect.com/science/article/pii/S0377027324000386
- https://eodg.atm.ox.ac.uk/eodg/vacation_reports/2021Waugh.pdf
- https://www-cdn.eumetsat.int/files/2020-04/pdf_conf_p_s11_12_tsuchiya_v.pdf
- https://simpleflying.com/how-airline-pilots-handle-volcanic-ash/
- https://www.aljazeera.com/economy/2024/11/13/airlines-cancel-bali-flights-after-volcano-spews-ash-miles-into-the-sky
- https://www.cnbc.com/2026/09/07/flights-canceled-jakarta-airport-anak-krakatau-eruption-disrupts-regional-travel-volcano.html
- https://www.volcanodiscovery.com/krakatau/news/374625/vaac-advisory-2026-224.html
- https://www.pprune.org/rumours-news/669278-indonesian-volcanic-eruption.html (403 on direct fetch; content not read)

---

## Search log

WebSearch (23 completed, 1 refused when the session budget ran out):
1. International Airways Volcano Watch nine VAACs areas of responsibility ICAO (standard)
2. "VA NOT IDENTIFIABLE FM SATELLITE DATA" meaning volcanic ash advisory (extended)
3. "EST VA CLD" "OBS VA CLD" volcanic ash advisory difference estimated observed (extended)
4. ICAO Annex 3 Table A2-1 template advisory message volcanic ash "FCST VA CLD +6 HR" "NXT ADVISORY" (standard)
5. volcanic ash SIGMET WV format validity 6 hours "VA CLD OBS" ICAO Annex 3 issued by meteorological watch office forecast position (standard)
6. EASA SIB 2010-17 volcanic ash revision latest "safety risk assessment" operators ... (standard)
7. ICAO Doc 9974 Flight Safety and Volcanic Ash "avoid" visible ash safety risk assessment operator (standard)
8. volcanic ash concentration 0.2 2 4 mg/m3 low medium high contamination zones Europe 2010 CAP 1236 discernible ash (standard)
9. volcanic ash SIGMET inconsistent with VAAC advisory missing SIGMETs study Asia Pacific MWO compliance (extended)
10. Indonesia VONA aviation color code PVMBG CVGHM paper Darwin VAAC information flow ground observation satellite discrepancy (extended)
11. Himawari-10 launch schedule JMA operational 2029 Himawari-9 primary operational since December 2022 (standard)
12. JMA Dust RGB recipe Himawari B15-B13 B13-B11 B13 volcanic ash color appearance training (standard)
13. split window brightness temperature difference volcanic ash detection Prata 1989 limitations water vapour ice false negatives Himawari 10.4 12.4 (standard)
14. machine learning volcanic ash detection Himawari-8 deep learning accuracy paper Tokyo VAAC labels (extended)
15. vision language model GPT-4V Gemini satellite image volcanic plume ash cloud interpretation evaluation (extended)
16. Himawari-8 volcanic ash cloud detection neural network probability of detection false alarm rate Sakurajima Kirishima study (extended)
17. Weathernews volcanic ash AI detection Himawari airlines 2021 (standard)
18. volcanic ash avoidance buffer nautical miles lateral vertical margin airline policy "nm" upwind ash cloud SIGMET area dispatcher (extended)
19. Asia Pacific regional volcanic ash contingency plan ATM danger area buffer ICAO APAC VACP (standard)
20. Lewotobi November 2024 Bali flights cancelled Jetstar Virgin Australia Qantas assessment ash while airport open other airlines continued (standard)
21. Anak Krakatau September 2026 Soekarno-Hatta airport closed ash flights cancelled (extended)
22. pprune volcanic ash SIGMET dispatch Indonesia Darwin VAAC advisory confusing routing (extended)
23. ops.group volcanic ash Indonesia SIGMET VAAC conflicting information operators (standard)
24. (refused, budget exhausted) which volcano observatories issue VONA aviation colour code JMA PHIVOLCS KVERT PVMBG adoption list ICAO

arXiv API queries (6): `all:"volcanic ash"` (35); `"volcanic ash" AND "language model"` (0); `"volcanic ash" AND "vision language"` (0); `volcanic AND "multimodal large language model"` (0); `"volcanic ash" AND Himawari` (0); `volcanic AND "foundation model"` (3, none about ash); plus one `id_list` lookup for 2307.12970 and 2510.22889.

Not found after searches: a quantitative APAC study of VONA/VAA/SIGMET disagreement rates (searches 9, 10, 22, 23); an airline-published lateral ash buffer (18, 19); a VLM ash evaluation (15 plus 3 arXiv queries); a deep-learning Himawari ash detector with POD/FAR (14, 16); PPRuNe/IFALDA dispatcher discussion content (22; PPRuNe returned 403).

Direct fetches (not searches): all CONFIRMED URLs above, via curl with a browser user agent or the fetch tool. ICAO icao.int PDFs returned HTTP 403 (Cloudflare challenge) to both; the Playwright browser was busy and was not used. No gcloud, Vertex, Earth Engine or credentialed call was made.


## Verification log (2026-10-10)

Two independent verifiers checked this file's key claims: a source check (opened each cited URL) and a recency/counter-evidence check (searched for newer or contrary facts). Where a claim below is REFUTED or PARTLY, **the correction here overrides the text above**.

### Corrections

- **K1** (recency: PARTLY). Claim: EASA GM3 ORO.GEN.200(a)(3) (ED Decision 2013/009/R) requires operators to show competence to interpret data from different sources and 'correctly resolve any conflicts among data sources', to run enhanced flight watch with 'plots of the affected areas from SIGMETs, NOTAMs', and at eruption onset to 'determine if any aircraft in flight could be affected, alert the crew and provide advice on re-routing and available aerodromes'.
  - Evidence: The 2013 annex (https://www.easa.europa.eu/en/downloads/1979/en) does say "A new GM3 ORO.GEN.200(a)(3) is added" and contains "correctly resolve any conflicts among data sources that may arise", "access to plots of the affected areas from SIGMETs, NOTAMs and relevant company information" and "(i) determine if any aircraft in flight could be affected, alert the crew and provide advice on re-routing and available aerodromes/operating sites". The current consolidated text is Easy Access Rules for Air Operations, Revision 24, March 2026 (https://www.easa.europa.eu/en/downloads/20342/en, p.357). There the same text sits under "GM2 ORO.GEN.200(a)(3) Management system ... ED Decision 2017/007/R". SIB 2023-13 also calls it "GM2 ORO.GEN.200(a)(3) for aircraft operators".
  - Correction: The wording still applies, but cite it as GM2 ORO.GEN.200(a)(3) in the current EASA Air Ops Easy Access Rules (Rev 24, March 2026; last amended by ED Decision 2017/007/R; first introduced by ED Decision 2013/009/R). The '2013 GM3' label is out of date. It is guidance material (GM), not a binding requirement.
- **K2** (recency: PARTLY). Claim: EASA SIB 2023-13 (issued 19 Dec 2023) 'replaces EASA SIB 2010-17R7 dated 02 July 2015, which is withdrawn'; no R8 exists. It recommends avoiding visible ash, or discernible ash at night or in IMC, and sets the European 0.2/2/4 x10^-3 g/m3 zones.
  - Evidence: The SIB PDF says "Issued: 19 December 2023" and "This SIB replaces EASA SIB 2010-17R7 dated 02 July 2015, which is withdrawn". It recommends "Avoid operation in visible volcanic ash or, where visibility of the ash is impaired (IMC, night), avoid operation in discernible volcanic ash", and its zones are 0,2/2/4 x10-3 gr/m3. The EASA AD page (https://ad.easa.europa.eu/ad/2023-13) shows "Supersedure: None", so no R1 or R8 exists. Counter-evidence on the zones: the London VAAC now issues Quantitative Volcanic Ash (QVA) forecasts (https://www.metoffice.gov.uk/services/transport/aviation/regulated/international-aviation/vaac/qva) with thresholds of "0.2mg/m3, 2mg/m3, 5mg/m3, and 10mg/m3", probabilistic exceedance, and IWXXM feature objects. A webinar on them was held in Nov 2025.
  - Correction: SIB 2023-13 is still current and nothing supersedes it. However, the 0.2/2/4 zones are the SIB's recommendation for London/Toulouse concentration charts (EUR Doc 019). Operational practice in Europe is moving to ICAO QVA thresholds of 0.2/2/5/10 mg/m3 with probabilities, so do not present 0.2/2/4 as the current state of the art.
- **K3** (recency: PARTLY). Claim: Live contradiction: Semeru SIGMET 12 (WAAF, valid 091820/100020) says 'VA CLD OBS AT 1800Z ... SFC/FL150 MOV E 10KT', while the MAGMA VONA 2026SMR1920 at 1800Z (0100 local) says 'Ash-cloud is not observed' and records the eruption on the seismogram.
  - Evidence: AWC isigmet JSON (fetched 2026-10-09 20:28Z): "WAAF SIGMET 12 VALID 091820/100020 ... MT SEMERU ... VA CLD OBS AT 1800Z ... SFC/FL150 MOV E 10KT NC". MAGMA VONA 2026SMR1920 (https://magma.esdm.go.id/v1/vona?code=SMR, detail /v1/vona/22889) says "Eruption at 1800 UTC (0100 local). Ash-cloud is not observed." and "Eruption recorded on seismogram with maximum amplitude 14 mm and maximum duration 190 second." Counter-context: the live Darwin VAA 2026/1157 (BoM JSON, DTG 20261009/1820Z) has the identical polygon and FL150 and states "OBS VA CLD ... RMK: VA IDENTIFIABLE ON CURRENT SATELLITE IMAGERY MOVING EAST ... AREA IS PARTIALLY OBSCURED BY MET CLOUD". 13 of the last ~15 Semeru VONAs say 'not observed', mostly at night.
  - Correction: The two products do disagree, but neither is wrong. The SIGMET copies the Darwin VAA, which saw the ash by satellite. The VONA reflects a ground observer at 01:00 local who could not see it at night. Present this as a difference in how each source observes (satellite vs ground at night), not as an error, and treat 'Ash-cloud is not observed' at night as uninformative.
- **K4** (source-check: PARTLY). Claim: Washington VAAC gave Fuego as 'EST VA CLD' (09/1830Z, SFC/FL140) because ash was 'NOT OBS IN STLT IMG OR WEBCAM DUE TO HVY MET CLD CVR'. The Guatemalan SIGMET A5 restates the same polygon as 'VA CLD OBS AT 1830Z'. Masaya shows the same pattern. Geometry is copied and only the evidence label changes.
  - Evidence: Fuego VAA 2026/1180 (DTG 20261009/1854Z) has 'ERUPTION DETAILS: VA EMS PSBL', 'EST VA DTG: 09/1830Z', 'EST VA CLD: SFC/FL140 N1428 W09052 - N1423 W09047 - N1420 W09050 - N1427 W09053 - N1428 W09052 MOV SE 10KT' and 'RMK: VA EMS NOT OBS IN STLT IMG OR WEBCAM DUE TO HVY MET CLD CVR. OBSCD VA EMS PSBLY CONTNG BASED ON PREV ACTIVITY'. MHTG SIGMET A5 (VALID 091900/100100) has 'VA CLD OBS AT 1830Z SFC/FL140' with the same vertices and the same FCST polygon. Masaya VAA 2026/017 (MASA/2026J091807) has 'ERUPTION DETAILS: VA EMS OBS', 'EST VA CLD: SFC/FL050' and 'RMK: VA EMS NOT OBS IN STLT IMG DUE TO MET CLD CVR. VA EMS SEEN IN WEBCAM ... HGT BASED ON WEBCAM'. MHTG SIGMET 1 says 'VA CLD OBS AT 1740Z SFC/FL050' with the same polygon.
  - Correction: The Fuego finding holds, and the remark is about emissions ('VA EMS NOT OBS'), not the cloud. Masaya is not the same pattern. The geometry is copied and the label changes from EST to OBS, but the Masaya VAA says emissions were observed and 'SEEN IN WEBCAM'. The SIGMET's OBS there is defensible: observed by webcam, estimated extent. Only Fuego is a clear case of 'estimate relabelled as observed'.
- **K4** (recency: PARTLY). Claim: Washington VAAC gave Fuego as 'EST VA CLD' (09/1830Z, SFC/FL140) because ash was 'NOT OBS IN STLT IMG OR WEBCAM DUE TO HVY MET CLD CVR'. The Guatemalan SIGMET A5 restates the same polygon as 'VA CLD OBS AT 1830Z'. Masaya shows the same pattern. Geometry is copied and only the evidence label changes.
  - Evidence: Fuego VAA 2026/1180 (https://www.ospo.noaa.gov/VAAC/ARCH26/FUEG/2026J091854.html): "ERUPTION DETAILS: VA EMS PSBL ... EST VA CLD: SFC/FL140 N1428 W09052 - N1423 W09047 - N1420 W09050 - N1427 W09053 ... RMK: VA EMS NOT OBS IN STLT IMG OR WEBCAM DUE TO HVY MET CLD CVR". MHTG SIGMET A5: "VA FUEGO ... VA CLD OBS AT 1830Z SFC/FL140" with the identical polygon. Masaya VAA 2026/017 (https://www.ospo.noaa.gov/VAAC/ARCH26/MASA/2026J091807.html): "ERUPTION DETAILS: VA EMS OBS ... EST VA CLD: SFC/FL050 ... RMK: VA EMS NOT OBS IN STLT IMG DUE TO MET CLD CVR. VA EMS SEEN IN WEBCAM ... HGT BASED ON WEBCAM".
  - Correction: The Fuego part holds: emission was only possible and seen by nothing, yet the SIGMET says OBS over the copied polygon. Masaya does not show the same pattern, because a webcam observed the emission and the VAA itself says 'VA EMS OBS'; only the cloud extent was estimated. Say 'Fuego shows this pattern; Masaya is a weaker case (webcam-observed emission, satellite-estimated extent)'.
- **K5** (recency: PARTLY). Claim: Darwin-area VAA 2026/1081 (Ibu, issued by Tokyo as Darwin backup) is headed 'OBS VA CLD: SFC/FL070', but its RMK says 'VA NOT IDENTIFIABLE ON SATELLITE IMAGERY ... VA AREA IS AN ESTIMATED AREA'. The OBS/EST label cannot be trusted without reading the RMK.
  - Evidence: JMA text (https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20260923_26803000_1081_Text.html): "FVAU03 ADRM 231419 ... ADVISORY NR: 2026/1081 ... OBS VA CLD: SFC/FL070 ... RMK: VA NOT IDENTIFIABLE ON SATELLITE IMAGERY. REGULAR GROUND REPORTS INDICATE INTERMITTENT DISCRETE ERUPTIONS ARE ONGOING. HEIGHT AND MOVEMENT BASED ON SATELLITE IMAGERY. VA AREA IS AN ESTIMATED AREA." Counter-context: the live Darwin-issued VAAs of 9 Oct (BoM JSON) label OBS only when the RMK says "VA IDENTIFIABLE" (Semeru 1157, Ibu 1148, Krakatau 225). Manam 2026/51 correctly uses "EST VA CLD: VA NOT IDENTIFIABLE FM SATELLITE DATA".
  - Correction: The quoted text is correct, and the RMK even contradicts itself ('not identifiable on satellite' vs 'height and movement based on satellite imagery'). But it is one advisory issued by Tokyo while backing up Darwin. Darwin's own current VAAs use OBS and EST consistently. Keep the design rule (always parse the RMK), but cite it as one instance from a backup issuance, not a general Darwin habit.
- **K6** (source-check: PARTLY). Claim: Tokyo VAA meaning of 'VA NOT IDENTIFIABLE FM SATELLITE DATA': 'VA IS NOT IDENTIFIABLE DUE TO MET CLOUD OR HAS DISSIPATED'. A wind is given instead of a polygon and all forecasts are 'NOT AVBL'. Mayon 2026/803 reports an eruption to FL100 going WSW yet gives no polygon.
  - Evidence: The cited Mayon URL (20261007_27303000_0803) has 'ADVISORY NR: 2026/803 INFO SOURCE: HIMAWARI-9 PHIVOLCS ERUPTION DETAILS: ERUPTION AT 20261007/1418Z FL100 EXTD WSW REPORTED ... OBS VA CLD: VA NOT IDENTIFIABLE FM SATELLITE DATA WIND FL100 050/7KT FCST VA CLD +6 HR: NOT AVBL ... RMK: WE WILL ISSUE FURTHER ADVISORY IF VA IS DETECTED IN SATELLITE IMAGERY. NXT ADVISORY: NO FURTHER ADVISORIES'. The phrase 'VA IS NOT IDENTIFIABLE DUE TO MET CLOUD OR HAS DISSIPATED' is not in Mayon 803. It is in a different advisory, Taal 2026/24 (20261008_27307000_0024, 'WIND FL180 060/9KT').
  - Correction: The 'MET CLOUD OR HAS DISSIPATED' meaning comes from Tokyo VAA Taal 2026/24 (8 Oct 2026), not Mayon 2026/803. The Mayon facts (FL100, WSW, wind given instead of a polygon, all forecasts NOT AVBL) hold, and Mayon 803 also says 'NO FURTHER ADVISORIES'. Tokyo's RMK wording varies between advisories, so the parser cannot rely on a fixed phrase.
- **K6** (recency: PARTLY). Claim: Tokyo VAA meaning of 'VA NOT IDENTIFIABLE FM SATELLITE DATA': 'VA IS NOT IDENTIFIABLE DUE TO MET CLOUD OR HAS DISSIPATED'. A wind is given instead of a polygon and all forecasts are 'NOT AVBL'. Mayon 2026/803 reports an eruption to FL100 going WSW yet gives no polygon.
  - Evidence: Mayon 2026/803 (https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20261007_27303000_0803_Text.html): "ERUPTION AT 20261007/1418Z FL100 EXTD WSW REPORTED ... OBS VA CLD: VA NOT IDENTIFIABLE FM SATELLITE DATA WIND FL100 050/7KT FCST VA CLD +6 HR: NOT AVBL ... RMK: WE WILL ISSUE FURTHER ADVISORY IF VA IS DETECTED IN SATELLITE IMAGERY. NXT ADVISORY: NO FURTHER ADVISORIES". The phrase "VA IS NOT IDENTIFIABLE DUE TO MET CLOUD OR HAS DISSIPATED" is not in the Mayon text. It comes from Taal 2026/24 (https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20261008_27307000_0024_Text.html).
  - Correction: The facts hold, but the sourcing is mixed. The 'met cloud or has dissipated' wording is a RMK in Taal 2026/24, not a published Tokyo definition and not part of Mayon 2026/803. Mayon 2026/803 reports an eruption to FL100 going WSW, gives only a wind, sets all forecasts to NOT AVBL, and ends the series ('NO FURTHER ADVISORIES'). That makes it a stronger example that 'not identifiable' is not an all-clear.
- **K8** (recency: PARTLY). Claim: JMA's own Dust RGB guide gives 'Dust (yellow sand)/ Volcanic ash' one colour class and lists poor display of low-level clouds as a limitation. The public JMA real-time JPEG list includes Dust RGB ('dst') but no Ash RGB. The agent's own look at the 1800Z frame (about 5.5 km per pixel) showed all of Java pinkish at night and no visible plume at Semeru.
  - Evidence: The JMA Dust RGB guide (https://www.jma.go.jp/jma/jma-eng/satellite/VLab/QG/RGB_QG_Dust_en.pdf) lists "Dust (yellow sand)/ Volcanic ash" as one class and the limitation "Poor display of low-level clouds". https://www.data.jma.go.jp/mscweb/data/himawari/list_se3.html offers 16 codes (arm,b03,b07,b08,b13,cve,dms,dnc,dsl,dst,irv,ngt,snd,tre,trm,vir), and none is Ash RGB. Counter-evidence: NOAA's open bucket has full-disk Himawari-9 L1b keyless and current (s3://noaa-himawari9 AHI-L1b-FLDK/2026/10/09/1800/HS_H09_20261009_1800_B01_FLDK_R10_S0110.DAT.bz2 ...). An Ash RGB (B11/B13/B15) at about 2 km can therefore be computed from public data. Darwin VAA 2026/1157 said Semeru ash was "IDENTIFIABLE ON CURRENT SATELLITE IMAGERY" at 1800Z, the same time the agent saw nothing in the JPEG.
  - Correction: It is true that JMA's public JPEGs have no Ash RGB and are coarse. But satellite input is not limited to those JPEGs: keyless Himawari-9 radiances on AWS allow a real Ash RGB or BTD at full resolution. The Semeru case shows that the JPEG is inadequate, since Darwin saw the ash and the JPEG did not, rather than that satellite evidence is useless.
- **K9** (source-check: PARTLY). Claim: arXiv API returns 0 papers for 'volcanic ash' AND 'language model', 0 for 'volcanic ash' AND 'vision language', and 0 for 'volcanic ash' AND Himawari. No published record exists of a VLM reading ash plumes.
  - Evidence: export.arxiv.org API, re-run 2026-10-09 ~20:40Z. all:"volcanic ash" returned totalResults 35. "volcanic ash" AND "language model", "volcanic ash" AND "vision language", and "volcanic ash" AND Himawari each returned 0. volcanic AND GPT-4V returned 0, and "volcanic plume" AND "deep learning" returned 0. However, arXiv 2401.15071 ('From GPT-4 to Gemini and Beyond') Figure 135, 'Results on Remote Sensing', tests MLLMs on a satellite image of a volcanic eruption. It reports 'All MLLMs identify the volcanic eruption, with GPT-4 providing more detailed analysis and Gemini Pro offering some incorrect information' (Gemini put the eruption at Tonga).
  - Correction: The arXiv counts reproduce exactly. The conclusion is too strong. There is a published qualitative record of GPT-4 and Gemini Pro reading a satellite image of a volcanic eruption plume (arXiv 2401.15071, Fig. 135), and Gemini Pro hallucinated the location. Correct statement: there is no published quantitative evaluation of a VLM detecting or delineating volcanic ash in geostationary IR imagery. The only published anecdote shows Gemini getting facts wrong.
- **K11** (source-check: REFUTED). Claim: The Bureau of Meteorology blocks automated access to the Darwin VAAC page ('does not support web scraping'). The JMA 'Darwin' page is a backup-only list ('Darwin VAAC Backup'), last updated 1 Oct 2026, so there is no confirmed keyless live feed for Darwin VAA text.
  - Evidence: With curl's default user agent, http://www.bom.gov.au/aviation/volcanic-ash/ returns 'Your access is blocked ... does not support web scraping', and that block page points to 'An anonymous FTP channel'. That FTP channel is a keyless live Darwin VAA text feed. ftp://ftp.bom.gov.au/anon/gen/vaac/2026/ (directory modified 'Oct 09 19:28') holds IDY41xxx.YYYYMMDDHHMM.txt VAA text files plus IDY65xxx PNG graphics. Examples: IDY41295.202610091816.txt = 'FVAU02 ADRM 091820 ... VAAC: DARWIN VOLCANO: SEMERU ... ADVISORY NR: 2026/1157'; IDY41290.202610091928.txt = Ibu 2026/1148 at 1930Z. The JMA Darwin page is titled 'Darwin VAAC Backup', and its newest entries are from 23 Sep. That part of the claim is correct.
  - Correction: Darwin VAA text is available keyless and close to live (within minutes of issue) from the BoM anonymous FTP: ftp://ftp.bom.gov.au/anon/gen/vaac/<year>/IDY41*.txt. BoM itself recommends this channel instead of scraping. The IDY4127x–4131x codes are rotating slots, not per-volcano codes, so the parser must read VOLCANO/ADVISORY NR from each file. The BoM web page loads with a browser user agent but says scraping is not supported, so do not scrape it. The JMA backup list only matters when Tokyo is covering.
- **K11** (recency: REFUTED). Claim: The Bureau of Meteorology blocks automated access to the Darwin VAAC page ('does not support web scraping'). The JMA 'Darwin' page is a backup-only list ('Darwin VAAC Backup'), last updated 1 Oct 2026, so there is no confirmed keyless live feed for Darwin VAA text.
  - Evidence: Plain curl to https://www.bom.gov.au/aviation/volcanic-ash/ returns HTTP 403 with "if you are trying to access Bureau data through automated means, you should stop". With a browser User-Agent it returns 200. The page's va.js posts to /aviation/php/process.php {page: "volcanic-ash-darwin", javascript: 1}, which returned JSON with 5 live Darwin VAAs, including SEMERU 2026/1157 (20261009/1820Z), IBU 2026/1148 (1930Z), DUKONO 2026/855, KRAKATAU 2026/225 and MANAM 2026/51, each with full text and a graphic IDY652xx.png. The JMA backup page is confirmed as "Volcanic Ash Advisories(Darwin VAAC Backup) Updated at 00:00 UTC, 01 October 2026", with its newest rows on 23 Sep.
  - Correction: A live, keyless Darwin VAA feed does exist: BoM's process.php JSON returns full texts when called with a browser User-Agent. However, BoM explicitly tells automated clients to stop, so using it carries a policy and ToS risk for a public entry. The JMA page is indeed backup-only. Options: use the BoM feed only as a cached demo snapshot with attribution, or rely on the AWC SIGMET JSON (which copies the Darwin VAA polygons) plus the BoM VA SIGMET page.
- **K12** (source-check: PARTLY). Claim: Near Jakarta at 02:44 local, only 7 aircraft were in the adsb.lol 250-radius query. At cruise, alt_geom exceeded alt_baro by 2,050-2,325 ft. SIGMET FLs must be compared with alt_baro, otherwise the vertical exposure test is off by about 2,000 ft.
  - Evidence: Live re-queries of https://api.adsb.lol/v2/point/-6.1/106.7/250 at about 20:27Z and 20:37Z on 9 Oct (03:27–03:37 WIB) returned total 6 and 5 aircraft. alt_geom minus alt_baro at cruise was THA483 39000/41525 (+2,525), TGW58 37000/39400 (+2,400), VJC91 33000/35250 (+2,250) and BTK6180 33875/36075 (+2,200). Max dst was 231 nm, consistent with a radius in nm.
  - Correction: The original 02:44-local snapshot (7 aircraft; +2,050 to +2,325 ft) cannot be reproduced because the endpoint is live. Independent snapshots confirm the effect, with cruise differences of +2,200 to +2,525 ft. Say 'about 2,000–2,500 ft in the tropics'. Compare SIGMET FLs with alt_baro (pressure altitude, 1013.25 hPa reference). Traffic is very sparse at night: 5–7 aircraft in a 250 nm circle around Jakarta.
- **K13** (recency: PARTLY). Claim: Himawari-9 has been operational since 13 Dec 2022. Himawari-10 is not operational: JMA targeted FY2029 and WMO OSCAR now lists 'Launch >=2030' (updated 2026-06-08).
  - Evidence: WMO OSCAR Himawari-10: "Status Planned ... Launch >=2030 EOL >=2046 Last update: 2026-06-08". WMO OSCAR Himawari-9 (last update 2026-08-24): "Himawari-9 replaced Himawari-8 as primary on 13 Dec 2022. Himawari-8 became primary satellite from 12 Oct 2025 when anomalies seen in H-9 imagery. Himawari-9 replaced Himawari-8 as the primary satellite on 26 Nov 2025 after fixing imagery anomalies."
  - Correction: Himawari-10 is not operational (launch at or after 2030). Himawari-9 has been primary since 13 Dec 2022, except for 12 Oct to 26 Nov 2025, when Himawari-8 was primary because of H-9 imagery anomalies. Any data pipeline should handle a primary-satellite switch (for example H08 vs H09 file prefixes and bucket names).
- **K14** (source-check: PARTLY). Claim: Weathernews has run an 'AI volcanic ash detection system' on Himawari imagery for airlines since 2021-04-26.
  - Evidence: The page is dated 'Apr 26, 2021' and titled 'Full-Scale Operation of AI Volcanic Ash Detection System for Aviation Market Begins'. It says 'Weathernews Inc. has commenced operation of an "AI volcanic ash detection system"' using 'satellite images that overlook the entire earth', detecting ash 'from gaps in clouds' by 'shape and texture', and that it was introduced 'into the volcanic ash diffusion prediction methods employed by the Weathernews Terrestrial Center for airlines'. The example image is Himawari-8 IR of Dukono, 5 Apr 2021.
  - Correction: The page supports that operation began on 2021-04-26, at Weathernews' Terrestrial Center, feeding its ACOS ash service for airlines, with a Himawari-8 example. It does not show that the system is still running in 2026, and it gives no accuracy figures. Write 'launched in April 2021', not 'has run since'.

### New findings raised by the verifiers

- GO-relevant, data access. Darwin VAA text has a keyless, near-live feed at ftp://ftp.bom.gov.au/anon/gen/vaac/2026/IDY41*.txt, with graphics as IDY65*.png. Semeru 2026/1157 (1820Z) and Ibu 2026/1148 (1930Z) were both there within minutes of issue on 9 Oct. This removes the 'no Darwin feed' blocker (C/§6 item 11). Use FTP, not the BoM web page, which says it does not support scraping.
- Changes the headline Semeru contradiction (K3). Darwin VAA 2026/1157 at 1800Z says 'VA IDENTIFIABLE ON CURRENT SATELLITE IMAGERY MOVING EAST ... AREA IS PARTIALLY OBSCURED BY MET CLOUD'. Its SFC/FL150 polygon matches WAAF SIGMET 12 vertex for vertex. So the SIGMET is well-founded; only the night-time ground VONA says 'not observed'. Demo narrative: the reconciler must keep the polygon and explain why the ground observer could not see ash at 01:00 local. It must not flag the SIGMET as wrong.
- Strong evidence for SERIOUS C1. At 1800Z Darwin analysts identified Semeru ash on Himawari-9, while the public JMA Dust RGB JPEG for the same slot (se3_dst_1800.jpg, stamped 18:10UTC) shows no distinguishable plume at Semeru. A VLM reading that JPEG would have produced a false negative against the official observation. That is a live, citable case against putting image-reading in the geometry path.
- A public Ash RGB source exists that the sweep missed. CIRA RAMMB SLIDER serves Himawari-9 full-disk 'eumetsat_ash' imagery keyless every 10 min: https://slider.cira.colostate.edu/data/json/himawari/full_disk/eumetsat_ash/latest_times.json, newest 20261009200000. If any imagery is shown, it should be the Ash RGB rather than the JMA Dust RGB. CIRA's terms of use were not checked.
- More SIGMET-copies-VAA evidence. WAAF SIGMET 13 (Ibu, OBS AT 1910Z, SFC/FL070) has the same polygon as Darwin VAA 2026/1148, whose RMK says 'DISCRETE VA EMISSIONS IDENTIFIABLE ON SATELLITE IMAGERY'. Geometry duplication is the norm, which confirms that the reconciliation work is mostly about evidence labels.
- Published VLM-on-volcano record: arXiv 2401.15071 (Fig. 135) shows GPT-4 and Gemini Pro describing a satellite image of a volcanic eruption, with Gemini Pro giving a wrong location (Tonga). Judges may know this. Frame Gemini's role as text and evidence classification, not plume detection.
- Parser hazards. Tokyo-as-Darwin-backup advisories keep the 'FVAU0x ADRM' and 'VAAC: DARWIN' headers, so the issuer cannot be inferred from the header. BoM FTP IDY41270–41315 file codes are rotating slots: one code covers different volcanoes over time (e.g. IDY41305 = Krakatau, IDY41300 = Lewotolok). Tokyo RMK wording for 'not identifiable' varies between advisories (Mayon 803 vs Taal 24).
- Minor: the BoM Darwin VA advisory web page (darwin-va-advisory.shtml, created 20:33Z) showed 'Nil current Darwin Volcanic Ash Advisories' while the FTP held 2026/1157 and 2026/1148 from the last two hours. The HTML page appears to depend on JavaScript or is unreliable for automation. The FTP is the source of truth.
- A live Darwin VAA feed exists. BoM's https://www.bom.gov.au/aviation/php/process.php (POST page=volcanic-ash-darwin&javascript=1, browser UA) returned JSON with full current Darwin VAA texts (Semeru 2026/1157, Ibu 2026/1148, Dukono 2026/855, Krakatau 2026/225, Manam 2026/51) and graphic names. However, BoM tells automated clients 'you should stop', so treat it as ToS risk: use it for a cached demo snapshot, not a production poller.
- Most SIGMET-vs-VAA 'contradictions' are copies of each other. Semeru WAAF SIGMET 12 matches Darwin VAA 2026/1157 exactly (polygon, SFC/FL150, MOV E 10KT), and that VAA RMK says 'VA IDENTIFIABLE ON CURRENT SATELLITE IMAGERY'. The real disagreement is VAA/SIGMET (satellite) vs VONA (ground observer at night). 13 of the ~15 most recent Semeru VONAs say 'Ash-cloud is not observed', so a reconciler must down-weight night VONA non-observations, or it will flag a 'conflict' every hour.
- The research file's Section 3.7 row for Masaya ('SIGMET calls an estimate OBS') is wrong. The Washington VAA says 'ERUPTION DETAILS: VA EMS OBS' and 'VA EMS SEEN IN WEBCAM'. Only the extent was estimated. The '6 of 8 SIGMETs disagree' count should be re-checked with this in mind.
- Quantitative Volcanic Ash (QVA) is now live at the London VAAC: gridded 3-D concentration, exceedance probabilities at 0.2/2/5/10 mg/m3, and IWXXM feature objects at T+0 to T+24 (Met Office QVA page; webinar Nov 2025). Judges with aviation knowledge may ask why TEPHRA builds its own 'cone' rather than consuming QVA. The deck should position TEPHRA for regions without QVA (Darwin/Tokyo, which still issue only polygon VAAs) or plan to ingest QVA where it exists.
- Full-disk Himawari-9 L1b radiances are public and keyless on AWS (s3://noaa-himawari9/AHI-L1b-FLDK/2026/10/09/1800/...). A proper Ash RGB or split-window BTD can be computed at about 2 km instead of reading JMA's 5.5 km Dust-RGB JPEG. This removes the 'no Ash RGB' blocker, though it adds build effort.
- Mayon 2026/803 is the strongest demo example of 'not identifiable is not an all-clear'. An eruption to FL100 was reported, yet the advisory gives only a wind, all forecasts are NOT AVBL, and it ends with 'NO FURTHER ADVISORIES'.
- Himawari-8 was primary from 12 Oct to 26 Nov 2025 because of Himawari-9 imagery anomalies (WMO OSCAR). Ingest code should not hard-code H09.
- Possible prior work to check for novelty: 'Aircraft responses to volcanic ash advisories during volcanic eruptions' (Research Square preprint, DOI 10.21203/rs.3.rs-5423602/v1, Nov 2024), which appears to relate ADS-B tracks to VAAs.
- EASA's current consolidated rules number the volcanic-ash guidance GM2 ORO.GEN.200(a)(3) (EAR Air Ops Rev 24, March 2026, ED Decision 2017/007/R). Cite that, not the 2013 'GM3' label, in the deck.

### All verdicts

- **K1** source-check: HOLDS; recency: PARTLY. Claim: EASA GM3 ORO.GEN.200(a)(3) (ED Decision 2013/009/R) requires operators to show competence to interpret data from different sources and 'correctly resolve any conflicts among data sources', to run enhanced flight watch with 'plots of the affected areas from SIGMETs, NOTAMs', and at eruption onset to 'determine if any aircraft in flight could be affected, alert the crew and provide advice on re-routing and available aerodromes'.
- **K2** source-check: HOLDS; recency: PARTLY. Claim: EASA SIB 2023-13 (issued 19 Dec 2023) 'replaces EASA SIB 2010-17R7 dated 02 July 2015, which is withdrawn'; no R8 exists. It recommends avoiding visible ash, or discernible ash at night or in IMC, and sets the European 0.2/2/4 x10^-3 g/m3 zones.
- **K3** source-check: HOLDS; recency: PARTLY. Claim: Live contradiction: Semeru SIGMET 12 (WAAF, valid 091820/100020) says 'VA CLD OBS AT 1800Z ... SFC/FL150 MOV E 10KT', while the MAGMA VONA 2026SMR1920 at 1800Z (0100 local) says 'Ash-cloud is not observed' and records the eruption on the seismogram.
- **K4** source-check: PARTLY; recency: PARTLY. Claim: Washington VAAC gave Fuego as 'EST VA CLD' (09/1830Z, SFC/FL140) because ash was 'NOT OBS IN STLT IMG OR WEBCAM DUE TO HVY MET CLD CVR'. The Guatemalan SIGMET A5 restates the same polygon as 'VA CLD OBS AT 1830Z'. Masaya shows the same pattern. Geometry is copied and only the evidence label changes.
- **K5** source-check: HOLDS; recency: PARTLY. Claim: Darwin-area VAA 2026/1081 (Ibu, issued by Tokyo as Darwin backup) is headed 'OBS VA CLD: SFC/FL070', but its RMK says 'VA NOT IDENTIFIABLE ON SATELLITE IMAGERY ... VA AREA IS AN ESTIMATED AREA'. The OBS/EST label cannot be trusted without reading the RMK.
- **K6** source-check: PARTLY; recency: PARTLY. Claim: Tokyo VAA meaning of 'VA NOT IDENTIFIABLE FM SATELLITE DATA': 'VA IS NOT IDENTIFIABLE DUE TO MET CLOUD OR HAS DISSIPATED'. A wind is given instead of a polygon and all forecasts are 'NOT AVBL'. Mayon 2026/803 reports an eruption to FL100 going WSW yet gives no polygon.
- **K7** source-check: HOLDS; recency: HOLDS. Claim: UK CAA CAP 1236: treat significant ash as a 'solid object' with the assumed MSA at least 2,000 ft above the ash top; the maximum usable level for underflight is 2,000 ft below the base. Operators form an operator-specific no-fly zone that treats VAAC and NAA information as primary, and use suitable safety margins. Where contamination levels are not provided, all affected airspace is treated as forecast high.
- **K8** source-check: HOLDS; recency: PARTLY. Claim: JMA's own Dust RGB guide gives 'Dust (yellow sand)/ Volcanic ash' one colour class and lists poor display of low-level clouds as a limitation. The public JMA real-time JPEG list includes Dust RGB ('dst') but no Ash RGB. The agent's own look at the 1800Z frame (about 5.5 km per pixel) showed all of Java pinkish at night and no visible plume at Semeru.
- **K9** source-check: PARTLY; recency: HOLDS. Claim: arXiv API returns 0 papers for 'volcanic ash' AND 'language model', 0 for 'volcanic ash' AND 'vision language', and 0 for 'volcanic ash' AND Himawari. No published record exists of a VLM reading ash plumes.
- **K10** source-check: HOLDS; recency: HOLDS. Claim: A purpose-built neural network on SEVIRI radiances (INGV, AMT 2026) detected only 66.0%, 48.5% and 84.1% of volcanic-cloud pixels in three unseen events, with balanced accuracy up to 92.0%. VADUGS reports POD 0.84 and FAR 0.05.
- **K11** source-check: REFUTED; recency: REFUTED. Claim: The Bureau of Meteorology blocks automated access to the Darwin VAAC page ('does not support web scraping'). The JMA 'Darwin' page is a backup-only list ('Darwin VAAC Backup'), last updated 1 Oct 2026, so there is no confirmed keyless live feed for Darwin VAA text.
- **K12** source-check: PARTLY; recency: HOLDS. Claim: Near Jakarta at 02:44 local, only 7 aircraft were in the adsb.lol 250-radius query. At cruise, alt_geom exceeded alt_baro by 2,050-2,325 ft. SIGMET FLs must be compared with alt_baro, otherwise the vertical exposure test is off by about 2,000 ft.
- **K13** source-check: HOLDS; recency: PARTLY. Claim: Himawari-9 has been operational since 13 Dec 2022. Himawari-10 is not operational: JMA targeted FY2029 and WMO OSCAR now lists 'Launch >=2030' (updated 2026-06-08).
- **K14** source-check: PARTLY; recency: HOLDS. Claim: Weathernews has run an 'AI volcanic ash detection system' on Himawari imagery for airlines since 2021-04-26.
