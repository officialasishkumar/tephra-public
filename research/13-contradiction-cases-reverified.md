# 13 · Contradiction cases re-verified (Akash's point C)

Research date: 2026-10-10 (IST). Fetches ran between about 19:00 and 20:00 UTC on 2026-10-09. In the tags below, "accessed 2026-10-10" means that window.
Scope: Akash's point C (the two "the sources disagreed" days), plus the parts of point D that call some disagreements artefacts. Points A, B and E are out of scope; I did not open the Devpost or DeepSeek links.

Tag key: **[CONFIRMED: url, accessed 2026-10-10]** means I opened the primary source and it says this. **[CONFIRMED-X2: url]** means two independent verifiers (a source lens and a counter-evidence lens) re-fetched the source on 2026-10-10 and the claim held under both. **[REPORTED: url]** means secondary or model output. **[UNVERIFIED]** means not established. **[COMPUTED]** means I did arithmetic or geometry on CONFIRMED primary text; the method is given in the text. **[verified 2026-10-10: ...]** marks a correction made after that two-lens check.

Verification status: all 12 key claims (K1-K12) were re-checked on 2026-10-10. Ten held under both lenses; two (K6, K11) held only in part and are corrected in place. See "Verification log (2026-10-10)" at the end. Web search was unavailable to the verifiers as well (budget used up), so the counter-evidence checks are limited to direct re-fetches.

---

## Bottom line

1. **All four texts Akash quotes exist, word for word.** They are: WAAF SIGMET 12 (251120Z, Semeru, SFC/FL150 MOV SE 10KT); VONA 20260923/2221Z (13,363 FT, moving NE); WAAF SIGMET 12 (071030Z, OBS AT 1010Z, SFC/FL150 MOV NE 05KT); VONA 20261007/1122Z ("Ash-cloud is not observed").
2. **Most of his critique is right about the pairs he cites:**
   - 13,363 ft sits inside SFC/FL150. That is an **ENVELOPE** case, not a conflict. [CONFIRMED-X2: https://magma.esdm.go.id/v1/vona/22702?signature=5d228f6100b2a77151e4085496fbb47c8bcaf46236d782011608e3e6794e237d] [verified 2026-10-10: the VONA marks its height as a lower bound ("May be higher than what can be observed clearly"), so ENVELOPE holds for the reported value only.]
   - The 23 Sep VONA was 37 hours older than the 25 Sep SIGMET. That is **LAG**. [verified 2026-10-10: 36 h 59 min to the SIGMET issue time (1120Z), 36 h 39 min (36.6 h) to its 1100Z observation time.]
   - On 7 Oct, "Ash-cloud is not observed" came from a ground observer after dark, about an hour after the SIGMET's observation time. That is a **NON-OBSERVATION**, not a contradiction. [CONFIRMED-X2: https://magma.esdm.go.id/v1/vona/22867?signature=977a4a9f44f6cba391bfd92976b21d39615917aabe1334b5ea3308511b3e4bd5] [verified 2026-10-10: "after dark" is an inference; the VONA gives no reason. The same station also said "not observed" in daylight (7 Oct 0355Z) and for 46 h overall, so cloud cover may also play a part.]
   - On 7 Oct the SIGMET direction (N/NE) and the last VONA that gave a direction (N) agreed. The SIGMET polygon reached 42 to 60 km north of the vent. [CONFIRMED-X2: https://aviationweather.gov/api/data/isigmet?format=json&hazard=va&date=2026-10-07T11:00:00Z] [verified 2026-10-10: that VONA (6 Oct 2251Z) came about 11.5 h before SIGMET 12's 1010Z observation, so "agreed" means its drift fits the polygon; the two observations were not simultaneous. It fits SIGMET 16 (valid at its time) as well.]
3. **"The VAAC had issued nothing" rests on misread sources and is very likely false for 24 to 26 Sep. For part of 23 Sep evening it may be true.**
   - The JMA page used as "the Darwin list" is Tokyo's **Darwin VAAC Backup** list. It shows only advisories Tokyo issued on Darwin's behalf. [CONFIRMED-X2: https://ds.data.jma.go.jp/svd/vaac/data/vaac_darwin_list.html]
   - The BoM Darwin page carries a hidden default string, "Nil current Darwin Volcanic Ash Advisories.", in its static HTML. The real advisories load later by JavaScript. [CONFIRMED-X2: https://www.bom.gov.au/aviation/volcanic-ash/js/va.js?v2]
   - Darwin's live Semeru advisory today is numbered **2026/1157**, which implies about 1,150 Semeru advisories this year. Its polygon is identical to the matching WAAF SIGMET.
   - I could not find a public archive that shows the 23 to 25 Sep Darwin texts themselves, so the exact days remain [UNVERIFIED].
   - [verified 2026-10-10: the backup list cuts both ways. From 23 Sep 1216Z Tokyo was the Darwin-area VAAC north of 20S, which includes Semeru (8S). During that backup the list is the authoritative record of Darwin-area VAAs, and it holds IBU 2026/1081 (1419Z) and DUKONO 2026/788 (1450Z) but **no Semeru VAA**. So the VAAC really was silent on Semeru for part of 23 Sep, overlapping the SIGMET gap below. Darwin appears to have resumed before about 1600Z; the exact end is unknown. The "very likely false" verdict applies to 24 to 26 Sep (and to 25 Sep, the day Akash cites), not to 23 Sep evening.]
4. **There was a real disagreement on the Semeru days, and the cited pair does not show it.** From 23 Sep 1725Z to 27 Sep 0520Z:
   - Every Semeru SIGMET said **MOV SE**, and its polygon reached only **8 to 10 km north** of the vent.
   - The **20 VONAs** in that window that gave a direction all said **N or NE**.
   - In all 20 cases, a point 15 km down the VONA's direction lies **outside** the SIGMET polygon valid at that moment. [CONFIRMED-X2: https://aviationweather.gov/api/data/isigmet?format=json&hazard=va&date=2026-09-25T16:00:00Z and the MAGMA Semeru list] [verified 2026-10-10: the result is distance-sensitive. Points 5 km and 8 km along each VONA direction are **inside** the valid polygon in 20 of 20; 10 km is outside in 19 of 20; 15 km is outside in 20 of 20. The polygons do cover the near-vent N/NE sector. The conflict is about the MOV direction and the downwind extent, not about near-vent ash being left out.]
   - The VONAs fell inside the SIGMET validity periods, often less than 30 minutes from the SIGMET observation time. This is a **DIRECTION MISMATCH beyond tolerance** (90 to 135 degrees against a 45-degree tolerance), and it is simultaneous. [verified 2026-10-10: "often less than 30 minutes" overstates it. Only 3-4 of the 20 VONAs are within about 30 min of a SIGMET observation time (25/2323 vs 2300Z, 26/1721 vs 1700Z, 26/2322 vs 2300Z, and 23/2221 vs the next SIGMET's 2250Z OBS, 29 min). Most are 1-6 h after the valid SIGMET's OBS time; the six 25 Sep 1515-1629Z VONAs are 4-5.5 h after SIGMET 12's 1100Z OBS. "Simultaneous" here means "inside the SIGMET's validity window".]
   - Model winds show strong shear at exactly these levels (700 hPa wind blowing ash toward ENE; 600 hPa toward SE). So both products may each describe part of the cloud. [verified 2026-10-10: PARTLY wrong. The 700 hPa level (about 3,150-3,190 m) is about 500 m **below** the 3,676 m summit, so it cannot carry ash leaving the vent. At the plume layer (650-550 hPa, about 3.8-5.1 km, which brackets the VONA tops of 3,976-4,976 m) model winds send ash toward **E to SE** throughout 23-26 Sep. The model favours the SIGMET's SE/E direction, makes NE at best marginal near summit level, and does not support "north". Observer viewing geometry is the more likely reason the VONA direction differs. Himawari is still needed to settle it. REPORTED, model output.]
5. **Two smaller real items:**
   - A **SILENCE** gap: no Semeru SIGMET was valid from 1550Z to 1725Z on 23 Sep, while the 1612Z VONA reported ash to 4,376 m moving east. [CONFIRMED-X2: https://aviationweather.gov/api/data/isigmet?format=json&hazard=va&date=2026-09-23T16:15:00Z] [verified 2026-10-10: WAAF SIGMET numbers on 23 Sep are contiguous (06 Semeru, 07 Ibu, 08 Dukono, 09 Ibu, 10 Lewotolok, 11 Semeru), so no Semeru issuance is missing from AWC's record. AWC is a relay and does not list cancellations. The gap overlaps the Tokyo-for-Darwin backup, during which no Semeru VAA appears either, so the VAAC was silent too.]
   - Two **marginal HEIGHT** cases on 26 Sep (4,876 m and 4,976 m AMSL against the SIGMET's FL150 top). The next SIGMET kept FL150. [verified 2026-10-10: also note WAAF SIGMET 17 (242320/250520) had a top of **SFC/FL140**, not FL150. The 24 Sep 2356Z VONA (4,376 m = 14,357 ft true) falls under it: within tolerance, but close to the top.]
6. **Sakurajima, Tokyo VAA 2026/249 (25 Sep 1252Z):**
   - It agrees with SIGMET B01, issued 5 minutes later (both say eruption at 1236Z, FL080, moving east).
   - "VA NOT IDENTIFIABLE FM SATELLITE DATA" means the satellite could not see it, not that there was no ash.
   - No Sakurajima SIGMET was valid at 1252Z (A01 expired 1204Z; B01 started 1257Z), so "while a SIGMET was open" is wrong by 5 minutes.
   - This is not a conflict. [CONFIRMED-X2: https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20260925_28208001_0249_Text.html and https://aviationweather.gov/api/data/isigmet?format=json&hazard=va&date=2026-09-25T13:05:00Z]
7. **A data-quality trap TEPHRA must handle:** MAGMA converts metres to feet with a factor of **3.2**, not 3.28084. "13363 FT (4176 M)" is really 13,701 ft. Parse the metre value. [CONFIRMED-X2: https://magma.esdm.go.id/v1/vona/22702?signature=5d228f6100b2a77151e4085496fbb47c8bcaf46236d782011608e3e6794e237d]

---

## Sources and how each was retrieved

| Source | Retrieved? | What it holds |
|---|---|---|
| MAGMA VONA list, Semeru filter, pages 1-10 (`https://magma.esdm.go.id/v1/vona?code=SMR&page=N`) | Yes, HTTP 200 | Every Semeru VONA from 15 Sep to 9 Oct 2026. Full text of each summary. Page numbers shift as new VONAs arrive; 23-27 Sep were on pages 7-8 and 6-8 Oct on page 2 at fetch time. [verified 2026-10-10: at 9 Oct 20:00Z the 23-24 Sep VONAs were on page 8 and the 26 Sep 2322Z VONA on page 6. Page numbers go stale; cite per-VONA URLs or notice numbers instead.] |
| MAGMA per-VONA pages (`/v1/vona/{id}?signature=...`) | Yes, 14 pages opened | Full 16-field VONA. |
| aviationweather.gov `api/data/isigmet` | Yes | **Takes a `date` parameter in ISO form.** `date=2026-09-25T12:00:00Z` returned the SIGMETs valid at that moment. The compact form `20260925_120000Z` returned HTTP 400 `{"status":"error","error":"Invalid value for date"}`. I swept every hour from 23 to 26 Sep and 6 to 8 Oct (168 queries; 3 returned HTTP 504 and are covered by the neighbouring hours), plus spot checks. [CONFIRMED-X2: https://aviationweather.gov/api/data/isigmet?format=json&hazard=va&date=2026-09-25T12:00:00Z] [verified 2026-10-10: the lookback is limited to 30 days. `date=2026-08-20T12:00:00Z` returns HTTP 400 "Data is available for up to 30 days for date". Queries can also return the same SIGMET twice with different `validTimeTo` values (e.g. RJJJ Q02 at 2026-10-07T11:00Z).] |
| Iowa Environmental Mesonet SIGMET archive (`/cgi-bin/request/gis/sigmets.py`) | Works, but no use here | 25 Sep 2026 returned 272 SIGMETs: 255 from KKCI and 17 from PHFO. **No WAAF or RJJJ.** It is US-only. [CONFIRMED: https://mesonet.agron.iastate.edu/cgi-bin/request/gis/sigmets.py?sts=2026-09-25T00:00Z&ets=2026-09-26T00:00Z&format=csv, accessed 2026-10-10] |
| OGIMET | No | The homepage has no SIGMET link. `sigmets.phtml.en`, `ultimos_sigmets.phtml.en`, `display_sigmets.php` and `cgi-bin/getbulletins` all returned 404. |
| JMA Tokyo VAAC recent list and text pages | Yes | Sakurajima VAAs 2026/246 to 249, and others. |
| JMA "Volcanic Ash Advisories (Darwin VAAC Backup)" (`vaac_darwin_list.html`) | Yes | **Only advisories Tokyo issued while backing up Darwin.** It is not Darwin's archive. |
| BoM Darwin VA advisories page | Yes, last 24 h only | The static HTML always contains a hidden "Nil current" default. The real list comes from a JavaScript POST to `/aviation/php/process.php`. No public history. The POST (`page=volcanic-ash-darwin&javascript=1`) returns JSON `{total, advisories{n:{name,text,graphic}}}`, a cleaner live source than the HTML. |
| NWS `tgftp.nws.noaa.gov/data/raw/fv/` | Yes, latest only | One file per bulletin header (FVAU02 ADRM = Semeru). Only the most recent copy; no history. |
| IEM AFOS text archive | No | `pil=VAADAR`, `FVAU02` and `VAAAU2` returned "Could not Find". |
| Smithsonian GVP (weekly report, Semeru page) | No | HTTP 403 by curl and by WebFetch. |
| Open-Meteo historical-forecast API (pressure-level winds) | Yes | Model winds at Semeru. Model output, so tagged REPORTED. |
| Web search | No | The session-wide search budget was used up before my first query; see the search log. All findings come from direct fetches of known URLs. The 2026-10-10 verifiers also had no web search; GVP (weekly report and RSS) and VolcanoDiscovery returned 403, so no independent archive of the 23-26 Sep Darwin texts could be checked. |

---

## Case 1: Semeru, 23 to 27 September 2026

### Akash's claim
"SIGMET: ash SFC to 15,000 ft moving SE; Semeru VONA 20260923/2221Z: 13,363 ft moving NE; the VAAC had issued nothing."

### Primary texts (quoted)

- **VONA 20260923/2221Z**, notice 2026SMR1806, Semeru (263300), colour code ORANGE (previous orange), source Semeru Volcano Observatory. [CONFIRMED-X2: https://magma.esdm.go.id/v1/vona/22702?signature=5d228f6100b2a77151e4085496fbb47c8bcaf46236d782011608e3e6794e237d]
  - "Eruption with volcanic ash cloud at 2221 UTC (0521 local)."
  - "Best estimate of ash-cloud top is around 13363 FT (4176 M) above sea level or 1600 FT (500 M) above summit. May be higher than what can be observed clearly. Source of height data: ground observer."
  - "Ash cloud moving to northeast."
  - Remarks: "Eruption recorded on seismogram with maximum amplitude 22 mm and maximum duration 150 second."
  - Summit elevation: "11763 FT (3676 M)".
- **WAAF SIGMET 12**, issued 251120Z, received by AWC 11:23:24Z: "WAAF SIGMET 12 VALID 251120/251720 WAAA- WAAF UJUNG PANDANG FIR VA ERUPTION MT SEMERU PSN S0806 E11255 VA CLD OBS AT 1100Z WI S0806 E11250 - S0801 E11254 - S0812 E11322 - S0824 E11323 - S0828 E11309 - S0806 E11250 SFC/FL150 MOV SE 10KT NC=" [CONFIRMED-X2: https://aviationweather.gov/api/data/isigmet?format=json&hazard=va&date=2026-09-25T12:00:00Z]
- **VONA 20260925/1137Z**, notice 2026SMR1815, ORANGE: "Eruption at 1137 UTC (1837 local)." Cloud height: "Ash-cloud is not observed." Other cloud information: "Ash-cloud is not observed." Remarks: seismogram "maximum amplitude 22 mm and maximum duration 122 second." [CONFIRMED: https://magma.esdm.go.id/v1/vona/22712?signature=6941ee196a309e3a6f38c95ddca8ba8d81e17a3439eb5467a5f11d09d2fc65f6, accessed 2026-10-10]
- **VONA 20260925/1515Z**, 2026SMR1816: "around 14003 FT (4376 M) above sea level ... May be higher than what can be observed clearly. Source of height data: ground observer." "Ash cloud moving to north." [CONFIRMED: https://magma.esdm.go.id/v1/vona/22713?signature=10d2d062ab9e53ee065e782593746514d8ce1c594f841cd909b3eb46208fd959, accessed 2026-10-10]
- **VONA 20260925/1526Z**, 2026SMR1817: "13363 FT (4176 M)", "Ash cloud moving to north." [CONFIRMED: https://magma.esdm.go.id/v1/vona/22714?signature=e9835f2a70805e94a7f776316ddb0c00624fee5e7d24ab508e717de75a50144c, accessed 2026-10-10]
- **VONA 20260925/2323Z**, 2026SMR1825: "14003 FT (4376 M)", "Ash cloud moving to northeast." [CONFIRMED: https://magma.esdm.go.id/v1/vona/22722?signature=05e04203c6eeb22ff7406b717746c9745ee87765f6440bce4a4e7d20b3223adb, accessed 2026-10-10]
- **VONA 20260926/2255Z**, 2026SMR1830: "15923 FT (4976 M) above sea level or 4160 FT (1300 M) above summit. May be higher than what can be observed clearly." "Ash cloud moving to northeast." [CONFIRMED: https://magma.esdm.go.id/v1/vona/22729?signature=092f3a4418bf50a8e4dbf5968fd5e7c57a6abf17d95048e1f8b5da15f713ce48, accessed 2026-10-10]

### Timeline (UTC). S = SIGMET (Ujung Pandang FIR, WAAF), V = VONA (MAGMA), D = Darwin VAAC, T = Tokyo VAAC

All SIGMET rows: [CONFIRMED: https://aviationweather.gov/api/data/isigmet?format=json&hazard=va&date=<hour>, accessed 2026-10-10]. The raw texts are in the appendix.
All VONA rows: [CONFIRMED: https://magma.esdm.go.id/v1/vona?code=SMR&page=7 and &page=8, accessed 2026-10-10]. [verified 2026-10-10: at 9 Oct 20:00Z the 23-24 Sep rows were on page 8 (not 7) and 26 Sep 2322Z on page 6. Cite notice numbers instead; pages shift.]
"North reach" is how far the polygon extends north of the vent [COMPUTED from the SIGMET vertices].

| Time (UTC) | Local (WIB) | Product | Content |
|---|---|---|---|
| 23 Sep 0950 | 16:50 | S WAAF 06, valid 0950-1550 | OBS 0930Z, SFC/FL150, MOV SE 10KT. North reach about 38 km. |
| 23 Sep 1216 | 19:16 | D/T NOTICE 2026/3 (issued by Tokyo) | "VAAC TOKYO HAS ASSUMED RESPONSIBILITY FOR ISSUING VAA TO THE VAAC DARWIN AREA OF RESPONSIBILITY NORTH OF LATITUDE 20S." [CONFIRMED: https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20260923_99999902_0003_Text.html, accessed 2026-10-10] |
| 23 Sep 1419 / 1450 | | D (issued by Tokyo as backup) | IBU 2026/1081 and DUKONO 2026/788. No Semeru advisory appears in the backup list. [CONFIRMED: https://ds.data.jma.go.jp/svd/vaac/data/vaac_darwin_list.html, accessed 2026-10-10] |
| 23 Sep 1550-1725 | | — | **No Semeru SIGMET valid** (AWC queries at 1555Z, 1615Z, 1645Z and 1715Z found none). WAAF numbers 07-10 in this span went to Ibu, Dukono, Ibu and Lewotolok, so the numbering is contiguous. [verified 2026-10-10] |
| 23 Sep 1612 | 23:12 | V | 4,376 m (printed as 14,003 ft), moving **east**. |
| 23 Sep 1725 | | S WAAF 11, valid 1725-2325 | OBS 1700Z, SFC/FL150, MOV SE 10KT. North reach about 10 km. |
| **23 Sep 2221** | 05:21 | **V 2026SMR1806** | **4,176 m ("13363 FT"), moving NE.** |
| 23 Sep 2325 | | S WAAF 16, valid 2325-0525 | OBS **2250Z**, SFC/FL150, **MOV SE** 10KT. North reach about 8 km. |
| 24 Sep 0042 | | V | 4,176 m, NE |
| 24 Sep 0525 / 1120 / 1725 | | S WAAF 04 / 08 / 12 | SFC/FL150, MOV SE 15/10/15KT |
| 24 Sep 1142, 1450 | | V | "Ash-cloud is not observed" (night) |
| 24 Sep 2020, 2127 | | V | 4,176 m, NE |
| 24 Sep 2314, 2356 | | V | 4,376 m, NE |
| 24 Sep 2320 | | S WAAF 17, valid 2320-0520 | OBS 2300Z, **SFC/FL140**, MOV SE 15KT, WKN. The 2356Z VONA (4,376 m = 14,357 ft true) falls under this FL140 top. |
| 25 Sep 0520 | | S WAAF 03, valid 0520-1120 | OBS 0500Z, SFC/FL150, MOV SE 15KT |
| **25 Sep 1120** | 18:20 | **S WAAF 12, valid 1120-1720** | **OBS 1100Z, SFC/FL150, MOV SE 10KT.** North reach about 10 km. |
| 25 Sep 1137 | 18:37 | V 2026SMR1815 | Eruption; "Ash-cloud is not observed." This is 53 minutes after civil dusk (10:44Z) [COMPUTED: NOAA solar-position formula, latitude -8.108, longitude 112.92]. |
| 25 Sep 1515-1629 | 22:15-23:29 | V ×6 (SMR1816 to 1822) | 3,976 to 4,476 m, **all "moving to north"** |
| 25 Sep 1720 | | S WAAF 17, valid 1720-2320 | OBS 1700Z, SFC/FL150, MOV SE 05KT |
| 25 Sep 2217, 2227 | | V | 4,576 m and 3,976 m, **north** |
| 25 Sep 2320 | | S WAAF 22, valid 2320-0520 | OBS **2300Z**, SFC/FL150, **MOV SE** 10KT, INTSF |
| 25 Sep 2323 | 06:23 | V 2026SMR1825 | 4,376 m, **NE** |
| 26 Sep 0520 / 1120 / 1720 | | S WAAF 04 / 09 / 13 | SFC/FL150, MOV SE 10/05/10KT |
| 26 Sep 1715, 1721 | | V | 4,076 m and 4,576 m, north |
| **26 Sep 2224, 2255** | 05:24, 05:55 | **V 2026SMR1829, 1830** | **4,876 m and 4,976 m AMSL**, NE, "May be higher than what can be observed clearly" |
| 26 Sep 2320 | | S WAAF 20, valid 2320-0520 | OBS 2300Z, **SFC/FL150 kept**, MOV SE 15KT |
| 26 Sep 2322 | 06:22 | V | 4,176 m, **NE**. One of the 20 directional VONAs; missing from the first version of this table. [verified 2026-10-10] |
| 27 Sep 1120 | | S WAAF (next cycle) | Pattern ends: SIGMET changes to **MOV E**, north reach about 15.7 km. [verified 2026-10-10] |
| 23-27 Sep | | D Darwin Semeru VAAs | **No text retrieved; [UNVERIFIED].** See "Was the VAAC silent?" below. |

### Classification

Tolerances I used:
- **Direction:** ±45 degrees, one 8-point compass step. N vs NE agrees; NE vs SE is 90 degrees; N vs SE is 135 degrees.
- **Height:** ±1,000 ft. Ground-observer heights come in 100 m steps; MAGMA's feet are understated by 2.5%; and FL150 is a pressure level, not an AMSL height.
- **Simultaneous:** the VONA falls inside the SIGMET's validity period, or the two observation times are within 60 minutes.

| # | Difference | Class | Why |
|---|---|---|---|
| 1 | "13,363 ft" against SFC/FL150 | **ENVELOPE** | Arithmetic: 13,363 < 15,000. With the correct conversion, 4,176 m × 3.28084 = 13,701 ft, still about 1,300 ft below FL150. **Akash is right.** [COMPUTED] |
| 2 | VONA 23 Sep 2221Z against SIGMET 12 at 25 Sep 1120Z (the pair as cited) | **LAG** | 37 h 0 min apart [verified 2026-10-10: 36 h 59 min to the 1120Z issue; 36 h 39 min to the 1100Z observation]. Comparing these two is not a fair test. **Akash is right.** |
| 3 | Same VONA (NE) against the SIGMETs valid at its own time: WAAF 11 (MOV SE, valid until 2325Z) and WAAF 16 (OBS 2250Z, MOV SE) | **DIRECTION MISMATCH, simultaneous** | 90 degrees. The SIGMET observation was 29 minutes after the VONA eruption. So the NE vs SE difference **was** simultaneous once the products are paired correctly. |
| 4 | VONA 25 Sep 1137Z "Ash-cloud is not observed" against SIGMET 12 "VA CLD OBS AT 1100Z" | **NON-OBSERVATION** (treat as SILENCE, not conflict) | The VONA still reports an eruption (seismic). The observer could not see the cloud after dark. "Not observed" is not "absent". |
| 5 | Six VONAs 1515-1629Z ("north") against SIGMET 12 (valid 1120-1720Z, MOV SE) | **DIRECTION MISMATCH, inside validity** | 135 degrees, inside the SIGMET's validity. A point 10 km north of the vent is **outside** the polygon (geometry below). [verified 2026-10-10: these VONAs are 4-5.5 h after SIGMET 12's 1100Z observation, so the observations were not simultaneous; points 5-8 km north are inside the polygon.] |
| 6 | VONA 2323Z (NE) against WAAF 22 (OBS 2300Z, MOV SE) | **DIRECTION MISMATCH, simultaneous** | 90 degrees, 23 minutes apart. |
| 7 | VONAs 26 Sep 2224Z and 2255Z (4,876 m and 4,976 m) against WAAF 13 (SFC/FL150, valid until 2320Z) and the next SIGMET WAAF 20 (still FL150) | **HEIGHT: at or just above the envelope top; within the ±1,000 ft tolerance** | 4,876 m = 15,997 ft and 4,976 m = 16,325 ft AMSL, which is 1,000 to 1,325 ft above a nominal 15,000 ft. FL150 in warm tropical air is usually a few hundred feet above 15,000 ft AMSL [UNVERIFIED for these dates; no sounding checked]. So this is marginal, not a clear conflict. But the SIGMET issued 25 minutes later did not raise the top, and the VONA says "May be higher". |
| 8 | VONA 23 Sep 1612Z (ash to 4,376 m, moving E) with no Semeru SIGMET valid 1550-1725Z | **SILENCE** | A 95-minute gap. It falls inside the Tokyo-backs-up-Darwin period that began at 1216Z. That the backup caused the gap is [UNVERIFIED]. [verified 2026-10-10: contiguous WAAF numbering rules out a missed issuance in AWC's record. Tokyo issued no Semeru VAA in the backup window either, while WAAF's Ibu/Dukono SIGMETs 07/08 followed Tokyo's backup VAAs by 21-25 min. Both the gap and the shrink of the north reach from about 38 km to about 10 km at 1725Z line up with the handover, which points to a hand-off artefact (inference, unverified).] |
| 9 | "The VAAC had issued nothing" | **Not SILENCE: a MISREAD SOURCE** (for 24-26 Sep) | See the next section. [verified 2026-10-10: for part of 23 Sep evening the VAAC was genuinely silent on Semeru (SILENCE), per the authoritative backup list.] |

### Geometry: does the observatory's reported drift stay inside the official polygon?

Method [COMPUTED]:
- Vent: S08°06'29" E112°55'12", from the VONA page.
- For each VONA, I found the WAAF SIGMET valid at the VONA's issue time.
- I placed points 5, 10, 15, 20 and 30 km from the vent along the VONA's direction and ran a ray-casting point-in-polygon test against that SIGMET's polygon.
- Sources are the CONFIRMED texts above.

Result for 23 Sep 1725Z to 27 Sep 0520Z:
- 20 VONAs gave a direction, and all 20 said north or northeast. Every SIGMET in the window said MOV SE.
- 5 km point: inside in all 20.
- 10 km point: outside in 19 of 20.
- 15 km point: outside in 20 of 20.
- The polygons reached only 8 to 10 km north of the vent, against 27 to 79 km south and 29 to 97 km east.
- [CONFIRMED-X2 for the 5/10/15 km counts; both verifiers reproduced them independently. verified 2026-10-10: an 8 km point is also **inside** in 20 of 20. The only 10 km exception is 23 Sep 2221Z. So the polygons do cover near-vent ash in the N/NE sector; the mismatch is in MOV direction and downwind extent. Say this precisely in the pitch and deck.]
- [verified 2026-10-10: timing. Most VONAs are 1-6 h after the valid SIGMET's OBS time; only 3-4 of 20 are within about 30 min.]

At the SIGMET's own speed of 10 kt (18.5 km/h), a north- or northeast-moving puff leaves the official area in about 30 to 50 minutes.

Earlier in the window the polygons were different. The 22 Sep 2150Z, 23 Sep 0350Z and 23 Sep 0950Z polygons reached 36 to 44 km north. From 1725Z on 23 Sep they shrank to about 10 km north and stayed that way for more than three days. [verified 2026-10-10: the pattern ends at 27 Sep 1120Z, when the SIGMET changes to MOV E with a north reach of about 15.7 km.]

**For TEPHRA:** on these days a dispatcher using only the SIGMET polygon would not cover the drift the observatory was reporting. "Take the cautious product" does not settle it, because neither product contains the other. The SIGMET is cautious about height (from the surface up) but points SE. The VONA points N/NE. The cautious answer is the **union** of the two. That is TEPHRA's "may widen, never shrink" rule, and here it does real work.

### Winds as a tie-breaker (model output, not observation)

Open-Meteo historical-forecast winds at Semeru (latitude -8.108, longitude 112.92) [REPORTED: https://historical-forecast-api.open-meteo.com/v1/forecast?latitude=-8.108&longitude=112.92&start_date=2026-09-23&end_date=2026-09-26&hourly=wind_speed_700hPa,wind_direction_700hPa,wind_speed_600hPa,wind_direction_600hPa,wind_speed_500hPa,wind_direction_500hPa&wind_speed_unit=kn&timezone=GMT]:
- **700 hPa** (about 3 km, just below the 3,676 m summit): wind from 231 to 257 degrees at 9 to 15 kt, so ash moves toward **ENE/NE**. [verified 2026-10-10: the range is 231-295 degrees (median 249), and 241-278 at the 20 VONA hours; on 26 Sep 22-23Z it was 273-278, i.e. toward E/ESE. Geopotential height is 3,151-3,192 m, about 500 m **below** the summit, so this level cannot carry ash leaving the vent.]
- **600 hPa** (about 4.2 km, near the VONA cloud tops): wind from 298 to 323 degrees at 13 to 20 kt, so ash moves toward **SE**. [verified 2026-10-10: the range is 296-328 degrees (median 309); geopotential height 4,426-4,455 m on 25 Sep.]
- Examples: 25 Sep 1500Z had 700 hPa from 246 at 13 kt and 600 hPa from 313 at 18 kt. 23 Sep 2200Z had 700 hPa from 241 at 10 kt and 600 hPa from 313 at 17 kt. [CONFIRMED-X2 for these examples: re-fetch matched exactly.]
- [verified 2026-10-10, added levels inside the plume layer (summit 3.68 km to VONA tops 3.98-4.98 km): **650 hPa** (3,762-3,801 m) wind from 246-315 at 3-11 kt, so ash goes toward ENE-SE, mostly E/ESE. **550 hPa** (5,110-5,151 m) wind from 273-328, so ash goes toward ESE/SE. During the six "north" VONAs on 25 Sep (~16Z): 650 hPa from 262, 600 hPa from 313, i.e. toward E and SE. No level between the summit and the observed tops sends ash toward N. REPORTED: same Open-Meteo endpoint with the 650/550 hPa and geopotential_height variables.]

~~Strong directional shear between the summit and plume-top levels makes both directions physically plausible.~~ [verified 2026-10-10: corrected. The shear is real but the NE-ward flow is below the vent. At plume height the model **favours the SIGMET's SE/E direction**, makes NE at best marginal near summit level (terrain-channelled or below-summit flow), and does not support the VONAs' "north". Observer viewing geometry (a ground observer judging drift of a near-vent column, often at night or dawn) is the more likely reason the VONA direction differs.] The model cannot settle it on its own. **Himawari imagery for a daylight eruption could** (for example 25 Sep 2323Z, which is after the 22:16Z sunrise). That is an open question below, and a good test for Akash's raw-data option B. For the pitch: say "model favours SE; observatory reported N/NE; satellite needed", not "both are physically plausible".

### Was the VAAC silent? (the "Darwin issued nothing" claim)

1. **The JMA page is not Darwin's archive.**
   - Its title is "Tokyo VAAC | Volcanic Ash Advisories(Darwin VAAC Backup)" and its header reads "Updated at 00:00 UTC, 01 October 2026".
   - It lists 36 rows going back to 2015, nearly all "NOTICE" test or backup announcements. The only 2026 volcano rows are IBU 2026/1081 (23 Sep 1419Z) and DUKONO 2026/788 (23 Sep 1450Z), both issued by Tokyo during the backup that began at 1216Z.
   - A list of Tokyo-issued backups cannot show what Darwin itself issued.
   - [CONFIRMED-X2: https://ds.data.jma.go.jp/svd/vaac/data/vaac_darwin_list.html and https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20260923_99999902_0003_Text.html]
   - [verified 2026-10-10: but during the backup itself (from 23 Sep 1216Z until Darwin resumed, apparently before about 1600Z) this list **is** the authoritative record of Darwin-area VAAs north of 20S. It holds Dukono and Ibu but no Semeru, although Semeru (8S) was in scope. So it supports a narrow silence claim for part of 23 Sep, not for 25 Sep.]
2. **The BoM page's "Nil" is a hidden template default.**
   - The static HTML contains `<div id="info" style="display:none;">...Nil current Darwin Volcanic Ash Advisories.</div>`.
   - `va.js` POSTs to `/aviation/php/process.php` and shows that string only `if (data.total == 0)`.
   - I fetched the HTML and the POST at about the same time on 9 Oct. The HTML said "Nil current"; the POST returned `total: 5`, including Semeru.
   - Any fetch that does not run JavaScript will always "see" Nil.
   - [CONFIRMED-X2: https://www.bom.gov.au/aviation/volcanic-ash/darwin-va-advisory.shtml and https://www.bom.gov.au/aviation/volcanic-ash/js/va.js?v2 ; re-POST at about 19:58-20:00Z on 9 Oct returned total=5 (DUKONO 2026/855, IBU 2026/1148, SEMERU 2026/1157, KRAKATAU 2026/225, MANAM 2026/51)]
3. **Darwin does issue routine Semeru advisories, matching the SIGMETs exactly.**
   - Live text: "FVAU02 ADRM 091820 VA ADVISORY DTG: 20261009/1820Z VAAC: DARWIN VOLCANO: SEMERU 263300 ... ADVISORY NR: 2026/1157 INFO SOURCE: HIMAWARI-9, CVGHM ERUPTION DETAILS: VA TO FL150 OBS AT 09/1800Z, MOV E ... OBS VA CLD: SFC/FL150 S0803 E11253 - S0754 E11316 - S0807 E11324 - S0820 E11318 - S0811 E11253 MOV E 10KT ... RMK: VA IDENTIFIABLE ON CURRENT SATELLITE IMAGERY MOVING EAST. DISCRETE EMISSIONS ARE ONGOING. AREA IS PARTIALLY OBSCURED BY MET CLOUD."
   - It matches WAAF SIGMET 12 (091820Z, OBS AT 1800Z) vertex for vertex, with the same FL150, MOV E 10KT and issue time. [CONFIRMED-X2 for the match: https://tgftp.nws.noaa.gov/data/raw/fv/fvau02.adrm..txt and https://aviationweather.gov/api/data/isigmet?format=json&hazard=va&date=2026-10-09T19:00:00Z; the SIGMET only closes the ring. Numbering is per volcano.]
   - The same is true for the Ibu, Dukono and Krakatau pairs live at the same time: 4 of 4 identical.
   - [CONFIRMED: https://tgftp.nws.noaa.gov/data/raw/fv/fvau02.adrm..txt and the BoM POST endpoint, accessed 2026-10-10; SIGMET at https://aviationweather.gov/api/data/isigmet?format=json&hazard=va, accessed 2026-10-10]
4. **Inference [UNVERIFIED]:**
   - Advisory number 1157 on day 282 averages about 4 per day, the same as the 6-hourly WAAF SIGMET cadence.
   - Darwin's Ibu number went from 1081 to 1148, and Dukono from 788 to 855, between 23 Sep and 9 Oct. That is 67 each in about 16 days.
   - So Darwin very likely issued Semeru VAAs throughout 23 to 26 Sep, saying SE like the SIGMETs. That would make SIGMET and VAAC **one source, not two**. [verified 2026-10-10: PARTLY. The match and cadence hold (also: the SIGMET's 0020Z validity end equals the VAA's "NXT ADVISORY: NO LATER THAN 20261010/0020Z", and on 23 Sep WAAF's Ibu SIGMET 07 at 1440Z and Dukono SIGMET 08 at 1515Z followed Tokyo's backup VAAs at 1419Z and 1450Z, which supports "SIGMETs echo VAAs"). But "throughout" is wrong for 23 Sep: the backup list shows no Semeru VAA from 1216Z. Corrected: Darwin very likely issued SE advisories matching the SIGMETs from about 23 Sep 1700Z to 26 Sep, with a real Semeru VAA gap during the 23 Sep Tokyo backup. The 23-26 Sep texts remain UNVERIFIED.]
   - I found no public archive to prove the exact texts. BoM shows 24 hours only, tgftp keeps the latest bulletin only, IEM AFOS has no FVAU, and GVP returned 403. (VolcanoDiscovery also returned 403 to the verifiers.)

**Classification: MISREAD SOURCE** for the claim as Akash made it (25 Sep). It is not evidence of silence on that day. [verified 2026-10-10: for part of 23 Sep evening, VAAC silence on Semeru is real and should be classified SILENCE.] This also undoes the earlier board claim that "the cached Darwin VAAC list contains ZERO Semeru advisories" (`prior/akash-src-tephra.json`, round-14 duel text).

---

## Case 2: Semeru, 6 to 8 October 2026

### Akash's claim
"SIGMET 12 at 1010Z: VA CLD OBS SFC/FL150 MOV NE 05KT; MAGMA VONA 1122Z: 'Ash-cloud is not observed'."

### Primary texts (quoted)

- **WAAF SIGMET 12**, issued 071030Z, received by AWC 10:29:41Z: "WAAF SIGMET 12 VALID 071030/071630 WAAA- WAAF UJUNG PANDANG FIR VA ERUPTION MT SEMERU PSN S0806 E11255 VA CLD OBS AT 1010Z WI S0818 E11306 - S0813 E11240 - S0749 E11237 - S0739 E11301 - S0756 E11318 - S0818 E11306 SFC/FL150 MOV NE 05KT NC=" [CONFIRMED-X2: https://aviationweather.gov/api/data/isigmet?format=json&hazard=va&date=2026-10-07T11:00:00Z]
  - Note: 1010Z is the **observation** time. The SIGMET was issued at 1030Z.
- **VONA 20261007/1122Z**, 2026SMR1902, ORANGE, Semeru Volcano Observatory: "Eruption at 1122 UTC (1822 local)." Cloud height: "Ash-cloud is not observed." Other: "Ash-cloud is not observed." Remarks: "maximum amplitude 25 mm and maximum duration 100 second." [CONFIRMED-X2: https://magma.esdm.go.id/v1/vona/22867?signature=977a4a9f44f6cba391bfd92976b21d39615917aabe1334b5ea3308511b3e4bd5]
- **VONA 20261007/1107Z**, 2026SMR1901: the same wording, "Eruption at 1107 UTC (1807 local)." [CONFIRMED: https://magma.esdm.go.id/v1/vona/22866?signature=dce8e61839ab2fd00666722078404b6a790308af7bfe3133c17a975ea6d16132, accessed 2026-10-10]
- **VONA 20261007/0355Z**, 2026SMR1900: "Eruption at 0355 UTC (1055 local)." "Ash-cloud is not observed." This one was in daylight. [CONFIRMED: https://magma.esdm.go.id/v1/vona/22865?signature=37b683db6f0090a3162da4b5b96e4c8845da0b91f58813d715f3d0f15b00ed0e, accessed 2026-10-10]
- **VONA 20261006/2251Z**, 2026SMR1899: "13043 FT (4076 M) above sea level ... May be higher than what can be observed clearly. Source of height data: ground observer." "Ash cloud moving to north." [CONFIRMED: https://magma.esdm.go.id/v1/vona/22864?signature=82239a53b1b9a2a0ea95a771bf01ac49e271d30bb7cf444da35d9be8a1413de4, accessed 2026-10-10]

### Timeline (UTC)

SIGMETs: [CONFIRMED: aviationweather.gov isigmet with date=2026-10-06T..Z to 2026-10-08T..Z, accessed 2026-10-10]. VONAs: [CONFIRMED: https://magma.esdm.go.id/v1/vona?code=SMR&page=2, accessed 2026-10-10].

| Time (UTC) | Local | Product | Content |
|---|---|---|---|
| 6 Oct 1720 | | S WAAF 16, valid 1720-2320 | OBS 1700Z, SFC/FL150, MOV N 05KT. North reach about 51 km. |
| 6 Oct 2206, 2235 | 05:06, 05:35 | V | "Ash-cloud is not observed" (before sunrise at 22:09Z) |
| **6 Oct 2251** | 05:51 | **V 2026SMR1899** | **4,076 m, moving north** |
| 6 Oct 2320 | | S WAAF 21, valid 2320-0520 | OBS **2300Z**, SFC/FL150, **MOV N** 05KT. North reach about 42 km. |
| 7 Oct 0355 | 10:55 | V 2026SMR1900 | Eruption; "Ash-cloud is not observed" (daytime) |
| 7 Oct 0520 | | S WAAF 07, valid 0520-1120 | OBS 0500Z, SFC/FL150, MOV NE 05KT |
| **7 Oct 1010 / 1030** | 17:10 | **S WAAF 12, valid 1030-1630** | **OBS 1010Z** (12 minutes before sunset at 10:22Z [COMPUTED]), SFC/FL150, **MOV NE 05KT**. North reach about 51 km. |
| 7 Oct 1107 | 18:07 | V 2026SMR1901 | Eruption; "Ash-cloud is not observed" (23-24 minutes after civil dusk at 10:43-10:44Z) |
| **7 Oct 1122** | 18:22 | **V 2026SMR1902** | **Eruption; "Ash-cloud is not observed"** |
| 7 Oct 1630 | | S WAAF 19 | OBS 1610Z, MOV N 05KT. North reach about 60 km. |
| 7 Oct 1810, 1817, 2200, 2213, 2239 | night or dawn | V ×5 | All "Ash-cloud is not observed" |
| 7 Oct 2230 | | S WAAF 26 | OBS 2210Z, MOV NE 05KT |
| 8 Oct 0149, 1003, 1444, 1446, 1847 | | V ×5 | All "Ash-cloud is not observed" |
| 8 Oct 2103 | 04:03 | V | First positive VONA after 6 Oct 2251Z: 4,376 m, north |

### Classification

| # | Difference | Class | Why |
|---|---|---|---|
| 1 | SIGMET 12 "VA CLD OBS AT 1010Z" against VONA 1122Z "Ash-cloud is not observed" | **NON-OBSERVATION** (SILENCE-type); not a real conflict | The VONA is inside the SIGMET's validity (1030-1630Z), so the overlap Akash describes is real. But the VONA **reports an eruption** (seismic, 25 mm, 100 s) and says the ground observer **could not see** the cloud. It came 38-39 minutes after civil dusk (10:43-10:44Z; the two verifier runs of the NOAA algorithm differ by a minute) [verified 2026-10-10], and the moon was a waning crescent, about 25.6 days old [COMPUTED, approximate], so not yet up in the early evening. The SIGMET's own observation was made in daylight, 72 minutes earlier. The two statements are compatible. If anything the VONA argues for **keeping** the SIGMET, because new ash was emitted that no one could measure. [verified 2026-10-10: the VONA gives no reason for "not observed", so "night-time" is an inference. The station also said "not observed" in daylight (0355Z) and for 46 h in all, so cloud cover or obscuration may contribute, not darkness alone. The NON-OBSERVATION class is unaffected.] |
| 2 | Direction: SIGMET MOV N/NE against the last directional VONA, "north" (6 Oct 2251Z, 9 minutes before the WAAF 21 observation time) | **AGREEMENT** | 0 to 45 degrees, within tolerance. Points 5 to 30 km north of the vent are all **inside** the valid polygon [COMPUTED]. [CONFIRMED-X2: SIGMET 12 north reach 50.8 km; points 5-40 km north inside, 50 km outside. The VONA was valid under SIGMET 16 (MOV N, 50.8 km reach, points 5-40 km inside) and also fits SIGMET 21 (to 30 km). It is about 11.5 h before SIGMET 12's observation, so against SIGMET 12 "agreement" means the drift fits the polygon, not a simultaneous observation.] |
| 3 | Height: VONA 4,076 m (13,373 ft true) against SFC/FL150 | **ENVELOPE** | Inside. |
| 4 | 46 hours of VONAs saying "not observed" (6 Oct 2251Z to 8 Oct 2103Z), several in daylight, while every SIGMET kept saying "VA CLD OBS ... NC" | **Open question, not classified** | The SIGMET "OBS" may rest on satellite detection (Darwin's 9 Oct remark says "VA IDENTIFIABLE ON CURRENT SATELLITE IMAGERY") or on persistence. Without the 7 Oct Darwin VAA text or Himawari imagery I cannot tell. [UNVERIFIED] |

**Verdict on 7 Oct:** this is **not** a contradiction day. It is a good example of a **night-time observation gap** that TEPHRA should label correctly ("eruption detected seismically; height and direction unobserved; keep the official envelope; check satellite"), not present as a disagreement.

---

## Case 3: Sakurajima, 25 September 2026 (Tokyo VAA 2026/249)

### Primary texts

- **VAA 2026/249**: "FVFE01 RJTD 251252 VA ADVISORY DTG: 20260925/1252Z VAAC: TOKYO VOLCANO: SAKURAJIMA (AIRA CALDERA) 282080 ... INFO SOURCE: JMA HIMAWARI-9 ERUPTION DETAILS: ERUPTED AT 20260925/1236Z FL080 EXTD E OBS VA DTG: 25/1230Z OBS VA CLD: VA NOT IDENTIFIABLE FM SATELLITE DATA WIND FL080 240/11KT FCST VA CLD +6 HR: NOT AVBL ... RMK: WE WILL ISSUE FURTHER ADVISORY IF VA IS DETECTED IN SATELLITE IMAGERY. NXT ADVISORY: NO FURTHER ADVISORIES=" [CONFIRMED-X2: https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20260925_28208001_0249_Text.html]
- **VAA 2026/247** (0601Z): OBS 0530Z "SFC/FL090 N3137 E13039 - N3137 E13043 - N3134 E13044 - N3134 E13039 MOV E 10KT", NXT ADVISORY 20260925/1200Z. [CONFIRMED: https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20260925_28208001_0247_Text.html, accessed 2026-10-10]
- **VAA 2026/248** (1150Z): "VA DISSIPATED ON SATELLITE IMAGERY ... FCST VA CLD +6 HR: NO VA EXP ... NXT ADVISORY: NO FURTHER ADVISORIES". [CONFIRMED: https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20260925_28208001_0248_Text.html, accessed 2026-10-10]
- **RJJJ SIGMET A01**, valid 250604/251204: OBS AT 0530Z, same 4-point polygon as VAA 247, SFC/FL090. **RJJJ SIGMET B01**, valid 251257/251857: "VA CLD OBS AT 1236Z FL080 MOV E=". [CONFIRMED: A01 in https://aviationweather.gov/api/data/isigmet?format=json&hazard=va&date=2026-09-25T12:00:00Z ; B01 in https://aviationweather.gov/api/data/isigmet?format=json&hazard=va&date=2026-09-25T13:05:00Z, accessed 2026-10-10]
- AWC queries at 1210Z and **1252Z** returned **no** Sakurajima SIGMET. [CONFIRMED: https://aviationweather.gov/api/data/isigmet?format=json&hazard=va&date=2026-09-25T12:52:00Z, accessed 2026-10-10]

### Timeline and classification

| Time (UTC) | Product | Content |
|---|---|---|
| 0512 | VAA 246 | Eruption 0500Z FL090, not identifiable on satellite |
| 0601 | VAA 247 | OBS 0530Z SFC/FL090 polygon, MOV E 10KT |
| 0604 | SIGMET A01 (to 1204) | Same polygon as VAA 247. Agreement by construction. |
| 1150 | VAA 248 | Dissipated; no further advisories |
| 1204 | A01 expires | 14 minutes after VAA 248 (LAG, minor) |
| 1236 | — | New eruption |
| 1252 | **VAA 249** | Erupted 1236Z FL080, EXTD E; "VA NOT IDENTIFIABLE FM SATELLITE DATA" |
| 1257 | **SIGMET B01** (to 1857) | OBS 1236Z FL080, MOV E |

- **VAA 249 against SIGMET B01: AGREEMENT.** Same eruption time, FL080, eastward. "Not identifiable from satellite" refers to satellite detection at 21:52 JST; it does not deny the ash. The SIGMET came 5 minutes later.
- **"While a SIGMET was open": wrong by 5 minutes.** There was a SIGMET gap from 1204Z to 1257Z. This is a **LAG** of 5 minutes, not a conflict.
- The older pitch line ("ground observer 13,363 ft vs 'VA NOT IDENTIFIABLE FM SATELLITE'") put a **Semeru** VONA next to a **Sakurajima** VAA, two volcanoes about 4,000 km apart. The prior research already flagged this, and it stays withdrawn.

---

## Data-quality findings TEPHRA must build in

1. **MAGMA feet are wrong by 2.5%.**
   - "11763 FT (3676 M)" is 3,676 × 3.2. "13363 FT (4176 M)" is 4,176 × 3.2. "1600 FT (500 M)" is 500 × 3.2.
   - The true values are 12,060 ft, 13,701 ft and 1,640 ft.
   - Parse metres and convert with 3.28084. [COMPUTED from CONFIRMED VONA text] [CONFIRMED-X2: https://magma.esdm.go.id/v1/vona/22702?signature=5d228f6100b2a77151e4085496fbb47c8bcaf46236d782011608e3e6794e237d ; further ×3.2 cases: 15923 FT (4976 M), 4160 FT (1300 M), 14003 FT (4376 M), 12723 FT (3976 M). The metre heights are summit (3,676) plus whole 100 m steps, so metres are the primary value.]
2. **Small summit-height mismatch.** MAGMA gives Semeru's summit as 3,676 m; Darwin's VAA gives SOURCE ELEV 3657M AMSL (a 19 m difference). [CONFIRMED, both sources above]
3. **WAAF VA SIGMETs repeat Darwin VAA polygons vertex for vertex** (4 of 4 live pairs checked). Count them as one source when reasoning about "independent" disagreement.
4. **Do not scrape BoM's static HTML for "Nil current".** It is a hidden template string. Use the JSON the page loads, or `tgftp.nws.noaa.gov/data/raw/fv/fvau0N.adrm..txt` for the latest bulletin per header. [verified 2026-10-10: the JSON is a direct POST of `page=volcanic-ash-darwin&javascript=1` to `https://www.bom.gov.au/aviation/php/process.php`, returning `{total, advisories{n:{name,text,graphic}}}`. Live only; no history.]
5. **The JMA "Darwin VAAC Backup" list is not a Darwin feed.** Use it only to detect backup periods. [verified 2026-10-10: during a backup period it is the authoritative Darwin-area record, so TEPHRA can use it to confirm VAAC silence inside that window.]
6. **AWC `isigmet` takes `date=YYYY-MM-DDTHH:MM:SSZ`** and returns the SIGMETs valid at that instant. That makes historical replay of VA SIGMETs possible for TEPHRA's demo log. How far back it reaches is untested beyond 23 Sep 2026. It returned 504 on 3 of 168 queries. [verified 2026-10-10: the lookback is **30 days** (HTTP 400 "Data is available for up to 30 days for date" for 2026-08-20). The 23-27 Sep Semeru SIGMETs become unretrievable around 23-27 Oct 2026, and 7 Oct around 6 Nov. **Archive the raw JSON now** for the demo replay log.]
7. **"Ash-cloud is not observed" is common and mostly happens at night.** Of 11 VONAs from 6 Oct 2251Z to 8 Oct 2103Z, all said "not observed", including some in daylight. A rule engine that reads "not observed" as "no ash" would be dangerously wrong. This is a legitimate place for Gemini to explain the difference.
8. **Deduplicate AWC SIGMETs.** [verified 2026-10-10] A `date` query can return the same SIGMET twice with different `validTimeTo` values (e.g. RJJJ Q02 with 071604 and 071152 at 2026-10-07T11:00Z, presumably a cancellation or amendment). Ingest must deduplicate and honour the earlier end time.
9. **Key freshness to the SIGMET's OBS time, not issue or validity time.** [verified 2026-10-10] WAAF SIGMET 07 (Ibu) was issued at 231440Z but says "VA CLD OBS AT 0950Z", an observation 4.8 h older than the issue.
10. **Cite VONAs by notice number or per-VONA URL**, not MAGMA list page; pages shift as new VONAs arrive. [verified 2026-10-10]
11. **SIGMET tops are not always FL150.** WAAF SIGMET 17 (242320/250520) was SFC/FL140. Read the top from each SIGMET. [verified 2026-10-10]

---

## What this means for the pitch wording

- Akash's proposed line, "the official sources often differ, and dispatchers must act on the cautious one quickly", is **half supported**.
  - "Differ" is supported: on 23 to 27 Sep, the observatory and the SIGMET/VAAC pointed in directions 90 to 135 degrees apart, simultaneously, for more than three days. [verified 2026-10-10: "simultaneously" means each VONA fell inside a valid SIGMET's window; most were 1-6 h after the SIGMET's observation, only 3-4 within about 30 min. Say "while the SIGMET was in force".]
  - "Often" is not shown. I checked two windows: one disagreed, one agreed.
  - "The cautious one" is ill-defined when neither product contains the other. The SIGMET covered the height but not the direction the observatory reported.
- A wording these sources support: **"Official volcanic-ash products are issued by different agencies, at different times, from different vantage points. Sometimes they point different ways for days. The safe area is their union, and building that union per flight, fast, with the reason shown, is the job."** Pair it with the 25 Sep 1515 to 1629Z example (six VONAs "moving to north" while a SIGMET polygon that reached only 10 km north was in force) as the on-screen proof. [verified 2026-10-10: state it precisely. The polygon does cover the first 5-8 km north of the vent; the reported drift leaves it beyond about 10 km. And do not say "both directions are physically plausible": model winds at plume height favour the SIGMET's SE. Say "model favours SE; observatory reported N/NE; satellite needed".]
- Drop "the VAAC had issued nothing" for 25 Sep, and drop the 7 Oct case as a "contradiction". Keep 7 Oct as an "unobserved eruption" example (dusk, possibly cloud). [verified 2026-10-10: a narrow, true replacement exists: "on 23 Sep evening, during a VAAC handover, neither a Semeru SIGMET nor a Semeru VAA was in force for 95 minutes while the observatory reported ash to 4.4 km".]

---

## Verdict on Akash's point(s)

- **C, 2026-09-25: PARTLY CONFIRMED.**
  - The SIGMET and VONA texts are exactly as he says.
  - The pair he cites is a **LAG** (37 h apart) plus an **ENVELOPE** (13,363 ft is inside SFC/FL150; 13,701 ft is inside too).
  - But a **real DIRECTION MISMATCH** existed on those days: N/NE against SE, for 20 VONAs across 23 to 27 Sep, each inside a valid SIGMET's window, with the reported drift leaving the official polygon beyond about 10 km (inside at 5-8 km, outside at 15 km in 20 of 20). [verified 2026-10-10: it is a mismatch of MOV direction and downwind extent, not of near-vent coverage; and most pairs are 1-6 h apart in observation time, not near-simultaneous.]
  - Model winds at plume height favour the SIGMET's SE, not the VONAs' N/NE. Which product was right is open until Himawari is checked. [verified 2026-10-10: replaces "both physically plausible".]
  - "The VAAC had issued nothing" is **not supported for 25 Sep or 24-26 Sep**. It came from a backup-only list and a hidden HTML default. Darwin is very likely to have issued SE advisories identical to the SIGMETs from about 23 Sep 1700Z; the exact texts are [UNVERIFIED]. [verified 2026-10-10: **but for part of 23 Sep evening it is true.** During the Tokyo-for-Darwin backup (from 1216Z) no Semeru VAA was issued, and no Semeru SIGMET was valid from 1550Z to 1725Z.]
- **C, 2026-10-07: CONFIRMED that the texts exist; REFUTED as a contradiction.** It is a **NON-OBSERVATION** (after civil dusk; cloud cover may also contribute). Directions agreed, though the agreeing VONA was about 11.5 h before SIGMET 12's observation.
- **D, "some disagreements are artefacts": CONFIRMED** for the exact examples circulated: lag, envelope, night non-observation, misread VAAC source, and the Sakurajima/Semeru mix-up. **But D is incomplete.** The same days contain a genuine disagreement that survives his tests.
- **D, "13,363 ft sits inside SFC-15,000 ft": CONFIRMED** (arithmetic, also with the corrected conversion; the VONA marks its height as a lower bound).
- **D, "a silent VAAC may just not have issued yet": PARTLY.** The 25 Sep "silence" was a data-reading error, not timing. One genuine silence exists on 23 Sep: no Semeru SIGMET from 1550 to 1725Z, and no Semeru VAA from the backup VAAC in the same window. It lines up with the Darwin-to-Tokyo handover, so it may be a hand-off artefact (inference, unverified) rather than "not issued yet".
- **Net after the 2026-10-10 two-lens check:** the verdicts above are unchanged in direction. Point C 25 Sep stays PARTLY CONFIRMED; 7 Oct stays REFUTED as a contradiction. Two things change: the VAAC-silence claim is now "false for 24-26 Sep, true for part of 23 Sep", and the wind tie-breaker now favours the SIGMET instead of supporting both.

## Open questions

1. Which way did the Semeru plume really go on 23 to 26 Sep? Check Himawari-9 for a daylight eruption: VONA 25 Sep 2323Z, or 26 Sep 2224Z and 2255Z, which are after the 22:16Z sunrise. Use AHI L1b B13 and B15 (split window) and true colour from `s3://noaa-himawari9` (anonymous listing found by the main session). This settles whether the SIGMET (SE) or the VONA (N/NE) was right, or whether shear made both right. It is the strongest possible demo of Akash's point B.
2. The Darwin Semeru VAA texts for 23 to 26 Sep and 7 Oct. Is there any archive (BoM registered-user service, ICAO IAVW, an airline's ops log, or a researcher's mirror)? Searching was blocked this session.
3. Why did the WAAF polygon's north reach shrink from about 40 km to about 10 km at 1725Z on 23 Sep, during the Tokyo-backs-up-Darwin period, and stay that way for three days? Was it a polygon template carried forward? (The SIGMETs say "NC", no change, repeatedly.) [verified 2026-10-10: the pattern ends at 27 Sep 1120Z (MOV E, about 15.7 km north reach). The timing with the handover suggests a hand-off artefact; unverified.]
4. ~~Was there a Semeru SIGMET cancellation or a missed issue during 23 Sep 1550 to 1725Z?~~ [verified 2026-10-10: partly answered. WAAF numbering 06-11 is contiguous, so no issuance is missing from AWC. A cancellation would not show in AWC, but nothing was valid to cancel after 1550Z.] When exactly did Darwin resume from the Tokyo backup on 23 Sep? Still open.
5. ~~How far back does AWC's `isigmet?date=` work?~~ [verified 2026-10-10: 30 days. Archive the 23-27 Sep and 6-8 Oct raw JSON before about 23 Oct and 6 Nov 2026.]
6. Do dispatchers in fact take the union, or the SIGMET only? This is outside point C; see the point D research.

## Sources

Primary (opened):
- MAGMA VONA list, Semeru: https://magma.esdm.go.id/v1/vona?code=SMR&page=1 to page=10 (pages 2, 7, 8 hold the case days)
- MAGMA VONA pages:
  - 22702 (23 Sep 2221Z): https://magma.esdm.go.id/v1/vona/22702?signature=5d228f6100b2a77151e4085496fbb47c8bcaf46236d782011608e3e6794e237d
  - 22703 (24 Sep 0042Z), 22712 (25 Sep 1137Z): https://magma.esdm.go.id/v1/vona/22712?signature=6941ee196a309e3a6f38c95ddca8ba8d81e17a3439eb5467a5f11d09d2fc65f6
  - 22713 (1515Z): https://magma.esdm.go.id/v1/vona/22713?signature=10d2d062ab9e53ee065e782593746514d8ce1c594f841cd909b3eb46208fd959
  - 22714 (1526Z): https://magma.esdm.go.id/v1/vona/22714?signature=e9835f2a70805e94a7f776316ddb0c00624fee5e7d24ab508e717de75a50144c
  - 22720 (2217Z): https://magma.esdm.go.id/v1/vona/22720?signature=d34595e87178cb3c38c9f6e6a4501f13a57c417f0a385ef2b62e57dcceefec6e
  - 22722 (2323Z): https://magma.esdm.go.id/v1/vona/22722?signature=05e04203c6eeb22ff7406b717746c9745ee87765f6440bce4a4e7d20b3223adb
  - 22728 (26 Sep 2224Z): https://magma.esdm.go.id/v1/vona/22728?signature=e5a140e4d2cf22f2c7b89a89cccddfe745bbe461cfd53f8f92523cf7c89e07b6
  - 22729 (26 Sep 2255Z): https://magma.esdm.go.id/v1/vona/22729?signature=092f3a4418bf50a8e4dbf5968fd5e7c57a6abf17d95048e1f8b5da15f713ce48
  - 22864 (6 Oct 2251Z): https://magma.esdm.go.id/v1/vona/22864?signature=82239a53b1b9a2a0ea95a771bf01ac49e271d30bb7cf444da35d9be8a1413de4
  - 22865 (7 Oct 0355Z): https://magma.esdm.go.id/v1/vona/22865?signature=37b683db6f0090a3162da4b5b96e4c8845da0b91f58813d715f3d0f15b00ed0e
  - 22866 (1107Z): https://magma.esdm.go.id/v1/vona/22866?signature=dce8e61839ab2fd00666722078404b6a790308af7bfe3133c17a975ea6d16132
  - 22867 (1122Z): https://magma.esdm.go.id/v1/vona/22867?signature=977a4a9f44f6cba391bfd92976b21d39615917aabe1334b5ea3308511b3e4bd5
  - 22868 (1810Z)
- AWC international SIGMET API, historical by date: https://aviationweather.gov/api/data/isigmet?format=json&hazard=va&date=2026-09-25T12:00:00Z (and every hour 2026-09-23T00Z to 2026-09-26T23Z and 2026-10-06T00Z to 2026-10-08T23Z; spot checks at 2026-09-23T15:55Z, 16:15Z, 16:45Z, 17:15Z, 17:30Z; 2026-09-25T12:10Z, 12:52Z, 13:05Z; 2026-09-27T00:30Z, 06:00Z). Live: https://aviationweather.gov/api/data/isigmet?format=json&hazard=va
- JMA Tokyo VAAC Darwin-backup list: https://ds.data.jma.go.jp/svd/vaac/data/vaac_darwin_list.html
- JMA Darwin-backup texts: https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20260923_99999902_0003_Text.html ; .../20260923_26803000_1081_Text.html ; .../20260923_26801000_0788_Text.html ; .../20260701_99999902_0001_Text.html
- JMA Tokyo VAAC recent list: https://ds.data.jma.go.jp/svd/vaac/data/vaac_list.html
- Tokyo VAAs: https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20260925_28208001_0249_Text.html ; ..._0248_Text.html ; ..._0247_Text.html ; ..._0246_Text.html
- BoM Darwin VA advisories page: https://www.bom.gov.au/aviation/volcanic-ash/darwin-va-advisory.shtml ; its script https://www.bom.gov.au/aviation/volcanic-ash/js/va.js?v2 ; data endpoint POST https://www.bom.gov.au/aviation/php/process.php (page=volcanic-ash-darwin)
- BoM VA SIGMET page: https://www.bom.gov.au/aviation/volcanic-ash/au-va-sigmet.shtml
- NWS raw bulletins: https://tgftp.nws.noaa.gov/data/raw/fv/fvau02.adrm..txt (Semeru), fvau01 (Dukono), fvau03 (Ibu), fvau04 (Krakatau)
- IEM SIGMET archive (US-only result): https://mesonet.agron.iastate.edu/cgi-bin/request/gis/sigmets.py?sts=2026-09-25T00:00Z&ets=2026-09-26T00:00Z&format=csv ; help: https://mesonet.agron.iastate.edu/cgi-bin/request/gis/sigmets.py?help

Model output (REPORTED):
- Open-Meteo historical-forecast winds: https://historical-forecast-api.open-meteo.com/v1/forecast?latitude=-8.108&longitude=112.92&start_date=2026-09-23&end_date=2026-09-26&hourly=wind_speed_700hPa,wind_direction_700hPa,wind_speed_600hPa,wind_direction_600hPa,wind_speed_500hPa,wind_direction_500hPa&wind_speed_unit=kn&timezone=GMT (and the same for 2026-10-06 to 2026-10-08)

Prior files compared against: `prior/akash-src-tephra.json`, `prior/board-tephra-pack.json`.

## Search log

- WebSearch, extended: "Darwin VAAC Semeru volcanic ash advisory September 2026". **Not performed**: the session-wide search budget was already used up. No other web searches were possible, so all findings come from direct fetches of known or discovered URLs.
- Direct fetches that failed or returned nothing useful:
  - `https://www.ogimet.com/sigmets.phtml.en`, `/ultimos_sigmets.phtml.en`, `/sigmet.phtml.en`, `/gsigmet.phtml.en`, `/display_sigmets.php?...lugar=WAAF...`, `/usigmets.phtml`, `/cgi-bin/getbulletins?...`: all 404.
  - `https://mesonet.agron.iastate.edu/request/gis/sigmets.phtml`: 404. The correct page `awc_sigmets.phtml` works but is US-only.
  - IEM AFOS `retrieve.py?pil=VAADAR|FVAU02|VAAAU2`: "Could not Find".
  - `https://www.bom.gov.au/info/vaac/advisories.shtml`: 404. `https://www.bom.gov.au/info/vaac/`: 403. `.../aviation/volcanic-ash/darwin-vaac/`: 404. `.../darwin-graphical-va-advisory.shtml`: 404.
  - `https://volcano.si.edu/reports_weekly.cfm` (curl) and `https://volcano.si.edu/volcano.cfm?vn=263300` (WebFetch): 403.
- AWC `isigmet?date=20260925_120000Z`: HTTP 400 "Invalid value for date". The ISO form works.

---

## Appendix: raw Semeru SIGMETs used (from AWC, whitespace collapsed)

```
WVID21 WAAA 222150 WAAF SIGMET 20 VALID 222150/230350 WAAA- WAAF UJUNG PANDANG FIR VA ERUPTION MT SEMERU PSN S0806 E11255 VA CLD OBS AT 2130Z WI S0808 E11250 - S0801 E11248 - S0743 E11319 - S0801 E11331 - S0822 E11319 - S0808 E11250 SFC/FL150 MOV E 10KT NC=
WVID21 WAAA 230350 WAAF SIGMET 02 VALID 230350/230950 ... VA CLD OBS AT 0330Z WI S0809 E11248 - S0801 E11249 - S0747 E11319 - S0803 E11328 - S0821 E11319 - S0825 E11304 - S0809 E11248 SFC/FL150 MOV NE 05KT NC=
WVID21 WAAA 230950 WAAF SIGMET 06 VALID 230950/231550 ... VA CLD OBS AT 0930Z WI S0808 E11249 - S0759 E11250 - S0746 E11314 - S0800 E11329 - S0816 E11323 - S0828 E11305 - S0808 E11249 SFC/FL150 MOV SE 10KT NC=
WVID21 WAAA 231725 WAAF SIGMET 11 VALID 231725/232325 ... VA CLD OBS AT 1700Z WI S0804 E11251 - S0801 E11256 - S0813 E11322 - S0835 E11320 - S0838 E11300 - S0804 E11251 SFC/FL150 MOV SE 10KT NC=
WVID21 WAAA 232325 WAAF SIGMET 16 VALID 232325/240525 ... VA CLD OBS AT 2250Z WI S0807 E11252 - S0802 E11256 - S0810 E11323 - S0825 E11329 - S0834 E11305 - S0807 E11252 SFC/FL150 MOV SE 10KT NC=
WVID21 WAAA 240525 WAAF SIGMET 04 VALID 240525/241125 ... VA CLD OBS AT 0500Z WI S0805 E11251 - S0801 E11254 - S0807 E11322 - S0824 E11327 - S0833 E11305 - S0805 E11251 SFC/FL150 MOV SE 15KT NC=
WVID21 WAAA 241120 WAAF SIGMET 08 VALID 241120/241720 ... VA CLD OBS AT 1100Z WI S0806 E11252 - S0802 E11254 - S0809 E11323 - S0826 E11322 - S0832 E11305 - S0806 E11252 SFC/FL150 MOV SE 10KT NC=
WVID21 WAAA 241725 WAAF SIGMET 12 VALID 241725/242320 ... VA CLD OBS AT 1700Z WI S0802 E11255 - S0809 E11323 - S0826 E11322 - S0832 E11305 - S0807 E11250 - S0802 E11255 SFC/FL150 MOV SE 15KT NC=
WVID21 WAAA 242320 WAAF SIGMET 17 VALID 242320/250520 ... VA CLD OBS AT 2300Z WI S0802 E11255 - S0809 E11323 - S0825 E11323 - S0828 E11308 - S0807 E11251 - S0802 E11255 SFC/FL140 MOV SE 15KT WKN=
WVID21 WAAA 250520 WAAF SIGMET 03 VALID 250520/251120 ... VA CLD OBS AT 0500Z WI S0802 E11255 - S0814 E11322 - S0824 E11323 - S0825 E11314 - S0807 E11251 - S0802 E11255 SFC/FL150 MOV SE 15KT NC=
WVID21 WAAA 251120 WAAF SIGMET 12 VALID 251120/251720 ... VA CLD OBS AT 1100Z WI S0806 E11250 - S0801 E11254 - S0812 E11322 - S0824 E11323 - S0828 E11309 - S0806 E11250 SFC/FL150 MOV SE 10KT NC=
WVID21 WAAA 251720 WAAF SIGMET 17 VALID 251720/252320 ... VA CLD OBS AT 1700Z WI S0805 E11250 - S0801 E11254 - S0812 E11322 - S0826 E11322 - S0828 E11307 - S0805 E11250 SFC/FL150 MOV SE 05KT NC=
WVID21 WAAA 252320 WAAF SIGMET 22 VALID 252320/260520 ... VA CLD OBS AT 2300Z WI S0805 E11250 - S0801 E11254 - S0807 E11311 - S0818 E11310 - S0821 E11300 - S0805 E11250 SFC/FL150 MOV SE 10KT INTSF=
WVID21 WAAA 260520 WAAF SIGMET 04 VALID 260520/261120 ... SFC/FL150 MOV SE 10KT NC=
WVID21 WAAA 261120 WAAF SIGMET 09 VALID 261120/261720 ... SFC/FL150 MOV SE 05KT NC=
WVID21 WAAA 261720 WAAF SIGMET 13 VALID 261720/262320 ... VA CLD OBS AT 1700Z WI S0805 E11250 - S0801 E11254 - S0811 E11322 - S0826 E11323 - S0829 E11306 - S0805 E11250 SFC/FL150 MOV SE 10KT NC=
WVID21 WAAA 262320 WAAF SIGMET 20 VALID 262320/270520 ... VA CLD OBS AT 2300Z WI S0805 E11250 - S0801 E11254 - S0827 E11348 - S0845 E11348 - S0849 E11328 - S0805 E11250 SFC/FL150 MOV SE 15KT NC=
WVID21 WAAA 061720 WAAF SIGMET 16 VALID 061720/062320 ... VA CLD OBS AT 1700Z WI S0813 E11246 - S0749 E11240 - S0739 E11258 - S0754 E11316 - S0814 E11310 - S0813 E11246 SFC/FL150 MOV N 05KT NC=
WVID21 WAAA 062320 WAAF SIGMET 21 VALID 062320/070520 ... VA CLD OBS AT 2300Z WI S0815 E11241 - S0752 E11240 - S0744 E11301 - S0757 E11316 - S0819 E11309 - S0815 E11241 SFC/FL150 MOV N 05KT NC=
WVID21 WAAA 070520 WAAF SIGMET 07 VALID 070520/071120 ... VA CLD OBS AT 0500Z WI S0816 E11243 - S0751 E11241 - S0744 E11303 - S0759 E11318 - S0820 E11308 - S0816 E11243 SFC/FL150 MOV NE 05KT NC=
WVID21 WAAA 071030 WAAF SIGMET 12 VALID 071030/071630 ... VA CLD OBS AT 1010Z WI S0818 E11306 - S0813 E11240 - S0749 E11237 - S0739 E11301 - S0756 E11318 - S0818 E11306 SFC/FL150 MOV NE 05KT NC=
WVID21 WAAA 071630 WAAF SIGMET 19 VALID 071630/072230 ... VA CLD OBS AT 1610Z WI S0813 E11243 - S0734 E11242 - S0734 E11310 - S0750 E11323 - S0818 E11304 - S0813 E11243 SFC/FL150 MOV N 05KT NC=
WVID21 WAAA 072230 WAAF SIGMET 26 VALID 072230/080430 ... VA CLD OBS AT 2210Z WI S0806 E11249 - S0736 E11311 - S0741 E11331 - S0802 E11333 - S0816 E11301 - S0806 E11249 SFC/FL150 MOV NE 05KT NC=
```

---

## Verification log (2026-10-10)

Two independent lenses per claim: a source lens (re-fetch the cited URL) and a counter-evidence lens (look for anything that breaks the claim). Both ran with the environment clock at about 2026-10-09 20:00Z; neither had web search. Scratch data: `<scratch>/v13/`.

- **K1** WAAF SIGMET 12 (251120Z) text and AWC `date` = valid-at-instant: HOLDS / HOLDS. CONFIRMED-X2. Added: 30-day lookback; compact date form returns 400.
- **K2** VONA 23 Sep 2221Z (13,363 ft, NE), LAG 37 h, ENVELOPE: HOLDS / HOLDS. CONFIRMED-X2. Refined: 36 h 59 min to issue, 36 h 39 min to OBS; height is a lower bound ("May be higher").
- **K3** 20 directional VONAs N/NE vs every SIGMET MOV SE, 15 km point outside 20/20: HOLDS / HOLDS. CONFIRMED-X2. Refined: 5 km and 8 km inside 20/20, 10 km outside 19/20; "often < 30 min" overstated (3-4 of 20); page citations corrected (8 and 6); 26 Sep 2322Z row added; pattern ends 27 Sep 1120Z.
- **K4** JMA list is Darwin-backup only: HOLDS / HOLDS. CONFIRMED-X2. Added: during the backup it is authoritative and shows no Semeru VAA, so a narrow 23 Sep silence is real.
- **K5** BoM "Nil current" is a hidden default; POST returned 5 incl. Semeru: HOLDS / HOLDS. CONFIRMED-X2.
- **K6** Darwin 2026/1157 matches WAAF SIGMET 12 (091820) vertex for vertex; "very likely issued matching SE advisories 23-26 Sep": PARTLY / PARTLY. Match and cadence CONFIRMED-X2; inference corrected to "from about 23 Sep 1700Z to 26 Sep", with a Semeru VAA gap during the 23 Sep backup. Texts still UNVERIFIED.
- **K7** 7 Oct SIGMET 12 (MOV NE, ~51 km north) contains the last directional VONA's drift: HOLDS / HOLDS. CONFIRMED-X2. Noted: VONA was ~11.5 h before SIGMET 12's OBS; also fits SIGMET 16 and 21.
- **K8** 7 Oct 1122Z "not observed" = night non-observation: HOLDS / HOLDS. CONFIRMED-X2. Refined: 38-39 min after civil dusk (10:43-10:44Z); "night-time" is inference; daytime "not observed" also occurs.
- **K9** Tokyo VAA 249 agrees with SIGMET B01; no Sakurajima SIGMET valid at 1252Z: HOLDS / HOLDS. CONFIRMED-X2.
- **K10** MAGMA uses ×3.2 for feet: HOLDS / HOLDS. CONFIRMED-X2. More ×3.2 cases added; metres are primary.
- **K11** Wind shear makes both directions plausible: PARTLY / PARTLY. Corrected: ranges were 231-295 (700 hPa) and 296-328 (600 hPa); 700 hPa is ~500 m below the summit; at plume height (650-550 hPa) ash goes E-SE. Model favours the SIGMET; does not support "north".
- **K12** No Semeru SIGMET valid 23 Sep 1550-1725Z: HOLDS / HOLDS. CONFIRMED-X2. Added: contiguous WAAF numbering 06-11 rules out a missed issuance; no Semeru VAA in the same window; possible hand-off artefact (unverified).

New findings folded in: Darwin-backup list cuts both ways (Bottom line 3, Case 1 classification 9, VAAC section, Verdict); wind physics (winds section, Bottom line 4, pitch); distance sensitivity and timing (Geometry, Bottom line 4, pitch); WAAF 17 FL140 (Bottom line 5, timeline, data-quality 11); AWC duplicate SIGMETs (data-quality 8); BoM JSON endpoint (sources table, data-quality 4); AWC 30-day lookback (sources table, data-quality 6, open question 5); WAAF 07 OBS 4.8 h before issue (data-quality 9); MAGMA pagination (sources table, data-quality 10); 26 Sep 2322Z row (timeline); no web search, GVP/VolcanoDiscovery 403 (sources table).
