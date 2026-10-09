# 09 · Live state of the ash feeds, demo-day odds, and replay cases

Lens: live-state. Written 2026-10-10 (IST). All live checks were made between 19:45Z and 20:10Z on 2026-10-09 (01:15 to 01:40 IST on 2026-10-10). "Accessed 2026-10-10" below means that window. No gcloud, Vertex, Earth Engine or Google credentials were used; everything was fetched with curl or WebFetch from public pages.

Tags: [CONFIRMED: url] = I opened the page or feed and it says this. [REPORTED: url] = a secondary source or a search-result summary says it and I could not open the primary. [UNVERIFIED] = not checked.

Important limitation: the shared web-search budget for this session ran out after 4 completed searches (see Search log). Everything else here comes from direct fetches of known URLs and public feeds. Several facts I would normally confirm by search (Kanlaon and Taal flight cancellations, OpenSky Trino terms, GVP weekly text) are therefore marked UNVERIFIED.

---

## 1. Bottom line

1. At the moment of checking there were 8 distinct VA SIGMETs open worldwide (the feed returned 11 rows; 3 are duplicates), 4 of them in Asia-Pacific (Dukono, Semeru, Ibu in Ujung Pandang FIR; Krakatau in Jakarta FIR) [CONFIRMED: https://aviationweather.gov/api/data/isigmet?format=json&hazard=va, accessed 2026-10-10]. Darwin VAAC had 4 open advisories (same four volcanoes); Tokyo VAAC had none open (its last advisory, Taal 2026/24 at 08/1750Z, said "NO FURTHER ADVISORIES") [CONFIRMED: https://tgftp.nws.noaa.gov/data/raw/fv/, accessed 2026-10-10].
2. In 119 six-hourly snapshots of the same SIGMET API from 2026-09-10 00Z to 2026-10-09 18Z, every snapshot had at least 3 open VA SIGMETs in Asia-Pacific FIRs; 119/119 had one in the Darwin VAAC area, 67/119 (56%) had one in the Tokyo VAAC area [CONFIRMED: https://aviationweather.gov/api/data/isigmet?format=json&hazard=va&date=..., accessed 2026-10-10; my own count, method in section 3].
3. My estimate: P(at least one VA SIGMET or VAA open in the Tokyo or Darwin area at a random moment on 2026-10-18 or 2026-12-04) is about 97-99%. P(one open in the Tokyo area specifically) is about 55%. P(a headline event, FL300+ ash or an airport closure, open on that day) is about 3%. Arithmetic in section 3.
4. The sources contradict each other today, live, without any replay: at 1800Z on 2026-10-09 the Semeru SIGMET and Darwin VAA both say "VA CLD OBS ... SFC/FL150 MOV E", while the Semeru VONA issued for the same minute says "Ash-cloud is not observed" [CONFIRMED: https://magma.esdm.go.id/v1/vona and https://tgftp.nws.noaa.gov/data/raw/fv/fvau02.adrm..txt, accessed 2026-10-10].
5. Best replay: Anak Krakatau, 2026-09-05 to 2026-09-07. MAGMA issued a RED VONA at 0200Z on 5 Sep that says "Ash-cloud is not observed" and then no VONA for three days. During that time Darwin VAAC put ash at FL500, Soekarno-Hatta and seven other airports closed, and "nearly 3,000 flights" were cancelled, delayed or diverted. The catch is that the SIGMETs from 5-7 Sep have already dropped out of the free SIGMET API, which only goes back 30 days, and the VAA texts sit behind a Cloudflare challenge. The fallback, which is fully scriptable today, is Taal on 2026-10-08 (section 5).
6. One finding changes the build. 59 of the 83 Fukuoka-FIR (Japan) VA SIGMETs in the sample have no polygon at all, only a point and a flight level. "The cone can never shrink below the official polygon" needs a rule for when there is no polygon (section 6).

---

## 2. Today table (checked 2026-10-09 19:45-20:10Z)

### 2a. Open VA SIGMETs, worldwide, by FIR

Source: https://aviationweather.gov/api/data/isigmet?format=json&hazard=va [CONFIRMED, accessed 2026-10-10]. The API returned 11 rows, but SEFG, MHTG/Masaya and MHTG/Fuego each appear twice with identical raw text. The poller must deduplicate on raw text.

| FIR | Volcano | SIGMET | Valid (UTC) | Layer, movement | Responsible VAAC |
|---|---|---|---|---|---|
| WAAF Ujung Pandang | Dukono | WAAF SIGMET 11 | 091550-092150 | SFC/FL070 MOV NE 10KT, polygon | Darwin |
| WIIF Jakarta | Krakatau | WIIF SIGMET 07 | 091615-092215 | SFC/FL060 MOV W 05KT, polygon | Darwin |
| WAAF Ujung Pandang | Semeru | WAAF SIGMET 12 | 091820-100020 | SFC/FL150 MOV E 10KT, polygon | Darwin |
| WAAF Ujung Pandang | Ibu | WAAF SIGMET 13 | 091930-100130 | SFC/FL070 MOV E 10KT, polygon, INTSF | Darwin |
| SKED Bogota | Purace | SKED SIGMET A3 | 091610-092200 | SFC/FL200 MOV NW | Washington |
| SEFG Guayaquil | Reventador | SEFG SIGMET 3 | 091654-092254 | SFC/FL140 MOV NW | Washington |
| MHCC Central American | Masaya | MHTG SIGMET 1 | 091832-100032 | SFC/FL050 MOV SW | Washington |
| MHCC Central American | Fuego | MHTG SIGMET A5 | 091900-100100 | SFC/FL140 MOV SE | Washington |

Count: 8 unique worldwide. In Asia-Pacific all 4 are in the Darwin area, none in the Tokyo area.

### 2b. Open VAAs by VAAC

Source: NOAA's raw WMO bulletin directory, which keeps the latest bulletin per WMO header [CONFIRMED: https://tgftp.nws.noaa.gov/data/raw/fv/, accessed 2026-10-10].

| VAAC | Volcano | Advisory | DTG | Content (short quote) | Next |
|---|---|---|---|---|---|
| Darwin | Dukono | 2026/855 | 20261009/1550Z | "VA TO FL070 OBS AT 09/1530Z, MOV NE" | NO LATER THAN 20261009/2150Z |
| Darwin | Semeru | 2026/1157 | 20261009/1820Z | "VA TO FL150 OBS AT 09/1800Z, MOV E ... AREA IS PARTIALLY OBSCURED BY MET CLOUD" | NO LATER THAN 20261010/0020Z |
| Darwin | Ibu | 2026/1148 | 20261009/1930Z | "VA TO FL070 OBS AT 09/1910Z MOV E ... CVGHM INDICATE DISCRETE ERUPTIONS ARE ONGOING" | NO LATER THAN 20261010/0130Z |
| Darwin | Krakatau | 2026/225 | 20261009/1615Z | "VA TO FL060 OBS AT 09/1550Z MOV W ... VA EXPECTED TO DISSIPATE WITHIN 6-12 HOURS" | NO LATER THAN 20261009/2215Z |
| Darwin | Taal (pointer) | 2026/29 | 20261008/1810Z | "PLEASE SEE FVFE01 RJTD 081750 ISSUED BY VAAC TOKYO" | NO FURTHER ADVISORIES |
| Tokyo | Taal | 2026/24 | 20261008/1750Z | "VA NOT IDENTIFIABLE FM SATELLITE DATA" | NO FURTHER ADVISORIES |

Count: Darwin 4 open, Tokyo 0 open. The Tokyo VAAC list page had last been updated "17:54 UTC, 08 October 2026" (header last-modified Thu, 08 Oct 2026 17:55 GMT). That is consistent with no new Tokyo advisory for 26 hours; the page is not stale [CONFIRMED: https://ds.data.jma.go.jp/svd/vaac/data/vaac_list.html, accessed 2026-10-10].

### 2c. Observatory levels

| Country / observatory | Status at check time | Source |
|---|---|---|
| Indonesia, MAGMA (PVMBG/CVGHM) | Level IV: 0. Level III (Siaga): Anak Krakatau, Merapi, Semeru, Sinabung. Level II: 23, including Dukono, Ibu, Ili Lewotolok, Karangetang, Lewotobi Laki-laki, Marapi. Ruang at Level I. | [CONFIRMED: https://magma.esdm.go.id/v1/gunung-api/tingkat-aktivitas, accessed 2026-10-10] |
| Indonesia, VONAs in the last ~36 h | 9 Oct: Semeru at 0449, 0706, 1114, 1323, 1334, 1654, 1800Z (all ORANGE, all "Ash-cloud is not observed"); Anak Krakatau 1144Z (ORANGE, "Ash-cloud is not observed"); Ibu 0137Z (ORANGE, ash top "5520 FT ... ground observer", moving east). 8 Oct: Semeru 6 VONAs, one with ash "14003 FT ... moving to north", the rest "not observed". | [CONFIRMED: https://magma.esdm.go.id/v1/vona, accessed 2026-10-10] |
| Japan, JMA | Sakurajima Level 3 (since 2022-07-27); Suwanosejima Level 2; Kirishima-Shinmoedake Level 2 (lowered 2025-10-17); Aso Level 2 (lowered from 3 on 2026-09-01); Kuchinoerabujima Level 1 (lowered 2026-09-28); Tokachidake Level 3 (raised 2026-09-12); Hokkaido-Komagatake Level 2 (raised 2026-10-02); Meakandake Level 2; Nishinoshima near-crater warning. | [CONFIRMED: https://www.jma.go.jp/bosai/volcano/data/warning.json, accessed 2026-10-10] |
| Philippines, PHIVOLCS | Alert Levels: Taal 1, Kanlaon 2, Bulusan 1, Pinatubo 0, Mayon 2. Taal 24-h bulletin dated 09 Oct: "1 Minor Phreatomagmatic eruption (5 minutes long)", plume "4000 meters tall; Voluminous emission; southwest drift", SO2 3071 t/d. Mayon: plume 400 m, 11 VEs. Kanlaon: plume 900 m, SO2 3219 t/d. | [CONFIRMED: https://wovodat.phivolcs.dost.gov.ph/bulletin/list-of-bulletin and https://wovodat.phivolcs.dost.gov.ph/bulletin/activity-tvo?bid=16869&lang=en, accessed 2026-10-10] |
| Russia, KVERT | Weekly release 41-2026 (08 Oct 21:18Z): Sheveluch ORANGE ("Ash explosions up to 12 km (39,400 ft) a.s.l. could occur at any time"); Bezymianny, Klyuchevskoy, Krasheninnikov YELLOW; all Kuriles GREEN. Last VONAs: Chikurachki 05 Oct 22:20Z (GREEN, "NO ASH CLOUD PRODUCED"), Sheveluch 05 Oct. | [CONFIRMED: http://kvert.febras.net/ and http://www.kscnet.ru/ivs/kvert/van/index?type=1, accessed 2026-10-10] |
| PNG, Vanuatu, Tonga | Not fetched directly (the VMGD page I tried did not show levels). From the SIGMET sample: Manam and Ulawun SIGMETs (AYPM) on 13-14 Sep; Ambrym SIGMETs (NFFF) on 19 Sep; no Tonga VA SIGMET in the sample. | [CONFIRMED for the SIGMET sample; observatory levels UNVERIFIED] |
| Smithsonian GVP weekly report | Not readable: volcano.si.edu returned HTTP 403 to curl and WebFetch, and the RSS returned a "Smithsonian request verification" page. Latest-week contents not found. | [CONFIRMED that it is blocked: https://volcano.si.edu/reports_weekly.cfm, https://volcano.si.edu/news/WeeklyVolcanoRSS.xml, accessed 2026-10-10] |

### 2d. Live contradictions on screen right now

| Volcano | SIGMET / VAA says | VONA / observatory says | Kind of disagreement |
|---|---|---|---|
| Semeru | SIGMET 12 and VAA 2026/1157: VA OBS at 1800Z, SFC/FL150, MOV E | VONA 20261009/1800Z: "Eruption at 1800 UTC (0100 local). Ash-cloud is not observed." | Satellite sees ash, ground observer cannot (night) |
| Krakatau | SIGMET 07 and VAA 2026/225: VA OBS at 1550Z, SFC/FL060, MOV W | Last VONA 20261009/1144Z: "Ash-cloud is not observed." | Same, and the VONA is 4 h older than the SIGMET |
| Ibu | VAA 2026/1148: SFC/FL070 MOV E at 1910Z | VONA 0137Z: ash top 5,520 ft, moving east, "May be higher than what can be observed clearly" | Height differs by about 1,500 ft and the VONA is 17 h old |
| Taal (8 Oct) | Tokyo VAA 2026/21 at 1029Z: "ERUPTION AT 20261008/1006Z FL150 EXTD SW REPORTED ... VA NOT IDENTIFIABLE FM SATELLITE DATA"; RPHI SIGMET 1 SFC/FL090, then SIGMET 2 SFC/FL150 18 min later | PHIVOLCS: one 5-minute "minor" eruption, plume 4,000 m, Alert Level stays 1 | Three heights in 30 minutes; detail in section 5 |

[CONFIRMED: the sources in 2a-2c, accessed 2026-10-10]

### 2e. Live traffic near the volcanoes (adsb.lol, night-time sample)

| Point, radius | Local time | Aircraft | At FL200 or above |
|---|---|---|---|
| Krakatau (-6.1, 105.4), 250 nm | 02:53 WIB | 2 | 2 |
| Semeru (-8.1, 112.9), 250 nm | 02:53 WIB | 6 | 6 |
| Ibu (1.5, 127.6), 250 nm | 03:53 WIT | 1 | 1 |
| Taal (14.0, 121.0), 150 nm | 04:06 PHT | 16 | 9 |
| Sakurajima (31.6, 130.65), 150 nm | 05:06 JST | 17 | 17 |

[CONFIRMED: https://api.adsb.lol/v2/point/{lat}/{lon}/{nm}, accessed 2026-10-10]. The fourth and fifth calls first returned HTTP 429 "Too Many Requests" after three calls within about 10 seconds; they succeeded after a pause of a few minutes, with 6 s between calls. The poller must pace its requests.

---

## 3. Probability that ash is open on the two days that matter

### 3a. Inputs

**Advisory numbers year-to-date (numbers are per volcano per year, so the number is the count issued so far):**

| VAAC | Volcano | Latest number seen | Date | Day of year | Rate per day | Source |
|---|---|---|---|---|---|---|
| Darwin | Semeru | 2026/1157 | 2026-10-09 | 282 | 4.10 | [CONFIRMED: tgftp fvau02.adrm] |
| Darwin | Ibu | 2026/1148 | 2026-10-09 | 282 | 4.07 | [CONFIRMED: tgftp fvau03.adrm] |
| Darwin | Dukono | 2026/855 | 2026-10-09 | 282 | 3.03 | [CONFIRMED: tgftp fvau01.adrm] |
| Darwin | Krakatau | 2026/225 | 2026-10-09 | 282 | 0.80 | [CONFIRMED: tgftp fvau04.adrm] |
| Darwin | Karangetang | 2026/9 | 2026-10-06 | 279 | 0.03 | [CONFIRMED: tgftp fvau06.adrm] |
| Tokyo | Mayon | 2026/803 | 2026-10-07 | 280 | 2.87 | [CONFIRMED: Tokyo vaac_list.html] |
| Tokyo | Sheveluch | 2026/353 | 2026-10-05 | 278 | 1.27 | [CONFIRMED: Tokyo vaac_list.html] |
| Tokyo | Sakurajima | 2026/279 | 2026-10-08 | 281 | 0.99 | [CONFIRMED: Tokyo vaac_list.html] |
| Tokyo | Kanlaon | 2026/254 | 2026-09-19 | 262 | 0.97 | [CONFIRMED: Tokyo vaac_list.html] |
| Tokyo | Taal | 2026/24 | 2026-10-08 | 281 | 0.09 | [CONFIRMED: Tokyo vaac_list.html] |
| Darwin | Ibu (2025) | 2025/1371 | 2025-12-08 | 342 | 4.01 | [REPORTED: https://www.volcanodiscovery.com/ibu/news/288951/vaac-advisory-2025-1371.html] |
| Darwin | Semeru (2025) | 2025/1480 | 2025-12-27 | 361 | 4.10 | [REPORTED: https://www.volcanodiscovery.com/semeru/news/290436/vaac-advisory-2025-1480.html] |
| Darwin | Lewotobi (2025) | 2025/344 | 2025-03-20 | 79 | n/a | [REPORTED: https://www.volcanodiscovery.com/lewotobi/news/271897/vaac-advisory-2025-344.html] |

Cross-check against the brief: Ibu was 2026/1081 on 23 Sep (Tokyo's Darwin-backup page) and 2026/1148 on 9 Oct, so 67 advisories in 16.2 days, or 4.1 a day [CONFIRMED: https://ds.data.jma.go.jp/svd/vaac/data/vaac_darwin_list.html]. One correction to the brief: the Darwin-backup page lists only advisories that Tokyo issued while backing up Darwin (on 23 Sep), not Darwin's normal output.

Why about 4 a day means "almost always open": a Darwin VAA for ongoing ash ends with "NXT ADVISORY: NO LATER THAN" the DTG plus 6 hours (all four open VAAs above show this). Six-hourly reissue gives 4 a day, so a rate of 4.07 to 4.10 a day over a full year means Ibu and Semeru advisories were open almost continuously in 2025 and 2026. This is my inference from the numbering, not a published statistic.

**Tokyo VAAC issuance by day:** the list page covers 2026-09-01 to 2026-10-08, 38 days, with 158 advisories. At least one Tokyo VAA was issued on 34 of the 38 days; none were issued on 3, 4, 5 and 7 Sep. By volcano: Sakurajima 96, Sheveluch 22, Mayon 19, Chikurachki 7, Kanlaon 7, Taal 4, Alaid 2, Krasheninnikov 1 [CONFIRMED: https://ds.data.jma.go.jp/svd/vaac/data/vaac_list.html, accessed 2026-10-10; my parse].

**SIGMET snapshot sample:** I queried `https://aviationweather.gov/api/data/isigmet?format=json&hazard=va&date=<ISO time>` every 6 hours from 2026-09-10T00Z to 2026-10-09T18Z, 120 requests; one request (2026-10-04T18Z) failed, leaving 119 snapshots. I counted a SIGMET as Asia-Pacific when its FIR is one of WAAF, WIIF, RPHI, RJJJ, UHMM, AYPM, NFFF, PAZA, and so on.

- 119 of 119 snapshots had at least 3 Asia-Pacific VA SIGMETs; the maximum was 8.
- Presence by volcano: Ibu 118, Semeru 116, Dukono 115, Lewotolok 97, Sakurajima 50, Mayon 16, Krakatau 16, Sheveluch (UHMM or PAZA) 14, Karangetang 6, Kanlaon 4, Manam 4, Ulawun 4, Ambrym 4, Marapi 3, Taal 2, Chikurachki 4, Alaid 1, Krasheninnikov 1.
- Darwin-area FIRs (WAAF, WIIF, AYPM and others) in 119 of 119; Tokyo-area FIRs (RJJJ, RPHI, UHMM) in 67 of 119.
- 1,166 unique VA SIGMET texts worldwide in the sample.

[CONFIRMED: aviationweather.gov API, accessed 2026-10-10; my count. Caveat: I assume the `date` parameter returns SIGMETs valid at that time; the API documentation was not checked.]

### 3b. Arithmetic

1. **Any VA SIGMET or VAA open in the Darwin or Tokyo area at a random moment.**
   - Empirical: 119/119 snapshots. By the rule of three, the 95% upper bound on the miss rate is 3/119 = 2.5%. Snapshots 6 h apart are autocorrelated, so a more honest count is 30 independent days, giving 3/30 = 10% as a loose upper bound.
   - Mechanism: Ibu, Semeru and Dukono are each open on about 97%, 97% and 97% of snapshots (115-118/119). Even treated as fully dependent, P(none) is at most 3%. If they are independent, P(none) is about 0.03^3, essentially 0.
   - Persistence to 4 Dec (56 days ahead): Ibu's and Semeru's 2025 and 2026 rates are almost identical (4.0-4.1 a day), so both have run at least 21 months. I assume, as a judgement and not a measurement, a 10-15% chance that each falls quiet for a whole day by 4 Dec. With independence, P(all three quiet) ≈ 0.15^3 ≈ 0.3%. Adding Sakurajima, Mayon, Lewotolok and Krakatau lowers it further.
   - **Estimate: 97-99% for each of 2026-10-18 and 2026-12-04.** The 1-3% residual covers correlated quieting, a feed outage and the API's 1-in-120 failure rate seen in the sample.
2. **Tokyo area specifically (Japan, Philippines, Kamchatka/Kurils).** 67/119 snapshots = 56%. P(at least one Tokyo VAA issued during the calendar day) = 34/38 = 89%. **Estimate: about 55% at a random moment, about 85-90% at some point in the day.** Sakurajima drives this; its Level 3 has held since 2022.
3. **A headline event (ash at FL300 or above, or an airport closure in APAC) open on a given day.** From the cases in section 4, 2024-2026 had roughly 6 such episodes (Ruang Apr 2024, Lewotobi Nov 2024, Kanlaon Dec 2024, Lewotobi Mar 2025, Lewotobi Jun 2025 [REPORTED: https://www.aljazeera.com/news/2025/6/18/dozens-of-bali-flights-cancelled-after-indonesia-volcano-erupts], Anak Krakatau Sep 2026), each lasting about 2-10 days, so about 25-30 event-days in about 900 days. **Estimate: about 3% per day.** The episode list is not exhaustive because the search budget ran out, so treat this as a rough lower-end figure.
4. **Meaning for the demo:** the live feed will almost certainly show 3-5 low-level plumes (FL060-FL150) in Indonesia, contradicting VONAs and probably a Sakurajima point-SIGMET. It will almost certainly not show an airport closure. The drama therefore has to come from a labelled replay.

---

## 4. Replay candidates (2024-2026)

Each case is checked against four legs: (a) a SIGMET or VAA with polygon and FL band, (b) a VONA or observatory notice that disagreed, (c) archived aircraft positions, (d) satellite frames.

### Archive facts that apply to every case

- **SIGMETs, aviationweather.gov:** history goes back only 30 days. A request for 2026-09-06 returned `{"status":"error","error":"Data is available for up to 30 days for date"}` [CONFIRMED: https://aviationweather.gov/api/data/isigmet?format=json&hazard=va&date=2026-09-06T12:00:00Z, accessed 2026-10-10]. Any event older than about 2026-09-09 has lost its SIGMET leg from this source. I found no free long-term international SIGMET archive (IEM's guessed endpoint returned 404). For older cases the VAA becomes the official polygon, since it carries polygon, FL band and movement too.
- **Tokyo VAAC text archive:** URL pattern `https://ds.data.jma.go.jp/svd/vaac/data/TextData/YYYY/YYYYMMDD_<volcano code>_<NNNN>_Text.html`. 2024 files are still served (Kanlaon 2024/62-66 returned 200). The directory listing returns 403, so the date and number must be known or probed [CONFIRMED, accessed 2026-10-10]. Volcano codes seen: Sakurajima 28208001, Mayon 27303000, Kanlaon 27202000, Taal 27307000, Sheveluch 30027000.
- **Darwin VAAC:** the BoM pages load advisory content with JavaScript, and my fetch of https://www.bom.gov.au/aviation/volcanic-ash/darwin-va-advisory.shtml returned page chrome but no advisory text. An earlier fetch in this session (by another agent, file cached in the scratchpad) got a BoM block page reading "The Bureau of Meteorology website does not support web scraping" and pointing to anonymous FTP. The anonymous FTP `ftp://ftp.bom.gov.au/anon/gen/fwo/` lists IDD65xxx volcanic-ash product files (current only) [CONFIRMED listing, accessed 2026-10-10]. NOAA's https://tgftp.nws.noaa.gov/data/raw/fv/ keeps only the latest bulletin per header. For past Darwin VAAs the usable mirror is VolcanoDiscovery: per-volcano list pages fetch fine, but individual advisory pages returned a Cloudflare "Just a moment..." challenge to curl [CONFIRMED, accessed 2026-10-10]. So historical Darwin VAA polygons need a real browser, or must be archived by our own poller from now on.
- **MAGMA VONA archive:** `https://magma.esdm.go.id/v1/vona?code=<CODE>&page=<n>`, 15 VONAs per page, back to 2019; detail pages are signed links. Codes: KRA Anak Krakatau, SMR Semeru, IBU, DUK, LWK Lewotobi Laki-laki, RUA Ruang. All-time VONA counts shown on the page: Semeru 10,189, Ibu 3,064, Lewotobi Laki-laki 1,568, Dukono 1,198, Sinabung 1,007, Anak Krakatau 601, Ili Lewotolok 313, Marapi 307, Ruang 20 [CONFIRMED: https://magma.esdm.go.id/v1/vona, accessed 2026-10-10].
- **Himawari-9 (AWS):** public bucket `noaa-himawari9`, prefixes `AHI-L1b-FLDK/`, `AHI-L1b-Japan/`, `AHI-L1b-Target/`, `AHI-L2-FLDK-Clouds/`, `AHI-L2-FLDK-ISatSS/`, `AHI-L2-FLDK-Winds/`. Full disk every 10 min as HSD `.DAT.bz2` in 10 segments per band, for example `AHI-L1b-FLDK/2024/04/30/0030/HS_H09_20240430_0030_B13_FLDK_R20_S0510.DAT.bz2`. Each FLDK folder holds 160 files (16 bands × 10 segments). Verified present for 2024-04-17 1500, 2024-04-30 0030, 2024-11-07 1500, 2025-03-20 1500, 2026-09-06 1200, 2026-09-25 1400 and 2026-10-09 1800 [CONFIRMED: https://noaa-himawari9.s3.amazonaws.com/?list-type=2&prefix=AHI-L1b-FLDK/..., accessed 2026-10-10]. Segment for the equatorial belt: about S05 (0-16 N) or S06 (0-16 S) [UNVERIFIED segment mapping; check against the HSD header].
- **Himawari quick-look (NICT):** true-colour tiles `https://himawari8-dl.nict.go.jp/himawari8/img/D531106/1d/550/YYYY/MM/DD/HHMMSS_0_0.png` returned 200 for 2026-09-06 0300 and 2026-04-30 0300, and 404 for 2026-01-01, 2025-10-09, 2025-03-20 and 2024-04-30. `INFRARED_FULL` returned 404 for the paths I tried [CONFIRMED, accessed 2026-10-10]. Retention appears to cover 2026 dates only; 2024-2025 cases need the AWS HSD files.
- **ADS-B, adsb.lol:** daily releases on GitHub, `https://github.com/adsblol/globe_history_YYYY/releases/tag/vYYYY.MM.DD-planes-readsb-prod-0`, as a split tar (`.tar.aa`, `.tar.ab`). The README says: "This database is made available under the Open Database License" and "Each release is 1 day of flight data" [CONFIRMED: https://raw.githubusercontent.com/adsblol/globe_history_2026/main/README.md]. Sizes seen: 2024-04-17 1.84 GB, 2024-04-30 1.84 GB, 2024-11-12 2.11 GB, 2024-11-13 2.12 GB, 2024-12-09 1.99 GB, 2025-03-20 2.53 GB, 2026-09-05 3.42 GB, 2026-09-06 3.27 GB, 2026-09-07 3.59 GB, 2026-09-25 3.53 GB, 2026-10-08 3.72 GB [CONFIRMED, accessed 2026-10-10]. Coverage over Indonesia and the Philippines is not measured [UNVERIFIED]; the night-time counts in section 2e show it is not zero.
- **ADS-B Exchange samples:** `https://samples.adsbexchange.com/readsb-hist/YYYY/MM/01/000000Z.json.gz` returned 200 for 2024-04-01, 2024-11-01, 2025-03-01, 2026-09-01 and 2026-10-01 [CONFIRMED]. Samples exist only for the 1st of the month, and none of the events fall on a 1st, so they are useless here. Licence terms not read [UNVERIFIED].
- **OpenSky Trino:** the page https://opensky-network.org/data/trino is JavaScript-rendered and WebFetch got 403. Whether a free account gets Trino access is [UNVERIFIED]. My prior understanding, unchecked, is that it needs an approved research or non-commercial application, so do not plan on it.
- **Flightradar24 playback:** not checked; the FR24 blog page returned 403 [UNVERIFIED].

### Replay-case table

| # | Event | (a) Official polygon + FL | (b) Disagreeing notice | (c) Aircraft archive | (d) Satellite | News / impact | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | **Anak Krakatau, 2026-09-05 to 09-07** | Darwin VAAs 2026/189 (06 Sep 14:10Z), 192 (06 Sep 23:10Z), 195 (07 Sep 08:10Z) at FL500; 197 at FL150 (07 Sep 14:10Z); 199 at FL070 (07 Sep 23:10Z) [CONFIRMED titles on the mirror list page https://www.volcanodiscovery.com/krakatau/news.html; polygon text behind Cloudflare]. WIIF SIGMETs: **lost** from aviationweather (more than 30 days old) [CONFIRMED]. | VONA 2026KRA026, 20260905/0200Z, colour **RED**: "Volcanic Cloud Height: Ash-cloud is not observed", remarks "Eruption and ash emission is continuing ... booming sounds and air shockwaves". Next VONA 2026KRA027 only on 20260908/0434Z, ORANGE, "Ash-cloud is not observed" [CONFIRMED: https://magma.esdm.go.id/v1/vona/22575?signature=4bce6aa9ba49588f081932c1c7f70bf9e2ec6e6159818c722d6bd692cfc19289 and .../22593?signature=db900e48d358430906f21bca19dc4d6743f4aa81d32146855f4e5d77dfcdb72c]. | adsb.lol v2026.09.05, .06, .07 prod (3.4, 3.3, 3.6 GB) [CONFIRMED]. Jakarta (CGK) is the region's busiest hub. | AWS `AHI-L1b-FLDK/2026/09/06/...` [CONFIRMED]; NICT true colour 2026-09-06 [CONFIRMED]. | ABC: Soekarno-Hatta "and seven others" closed; "Nearly 3,000 flights have been cancelled, delayed or diverted"; "about 341,000 passengers"; ash "up to 20,000 feet on the Java side" and "as high as 50,000 feet over Sumatra"; Qantas QF39-42 and Singapore Airlines cancelled [CONFIRMED: https://www.abc.net.au/news/2026-09-07/australians-stranded-as-volcanic-ash-closes-jakarta-airport/107125502]. CNBC "373 flights" in the brief: [UNVERIFIED, 403]. | **Best story; legs a, b, c, d all exist, but (a) needs manual copying of about 10 VAA texts from a browser** |
| 2 | **Taal, 2026-10-08 10:06Z to 21:11Z** | RPHI SIGMET 1 (1016Z) SFC/FL090 MOV SW, point only; SIGMET 2 (1034Z) SFC/FL150; SIGMET 3 (1141Z) polygon SFC/FL150 with 1650Z forecast polygon; SIGMET 4 (1511Z) polygon SFC/FL150, forecast SFC/FL160, valid to 2111Z [CONFIRMED: aviationweather isigmet with date=2026-10-08T12:00:00Z and T18:00:00Z]. Tokyo VAAs 2026/21-24 [CONFIRMED: TextData/2026/20261008_27307000_002{1..4}_Text.html]. | VAA 21 (1029Z): "ERUPTION AT 20261008/1006Z FL150 EXTD SW REPORTED ... VA NOT IDENTIFIABLE FM SATELLITE DATA ... NO FURTHER ADVISORIES". VAA 22 (1130Z) then gives a polygon SFC/FL150 MOV W 20KT. VAA 24 (1750Z): "VA IS NOT IDENTIFIABLE DUE TO MET CLOUD OR HAS DISSIPATED ... NO FURTHER ADVISORIES", while SIGMET 4 stays valid to 2111Z. PHIVOLCS: one "Minor" 5-minute eruption, plume 4,000 m SW, Alert Level 1 unchanged. | adsb.lol v2026.10.08 prod (3.72 GB) [CONFIRMED]. Manila (RPLL) is about 60 km north; 16 aircraft within 150 nm even at 04 PHT [CONFIRMED]. | AWS FLDK every 10 min [CONFIRMED pattern]; NICT 2026 retention likely [UNVERIFIED for this date]. | Cancellations [UNVERIFIED, no search budget]. | **Most complete and fully scriptable today; weak news hook. SIGMETs drop out of the API around 2026-11-07, so save them now** |
| 3 | **Ruang, 2024-04-16/17 and 2024-04-30** | Darwin VAA titled "HIGH LEVEL VA ERUPTION TO FL300 MOV W OBS VA DTG: 16/1830Z" [REPORTED: https://www.volcanodiscovery.com/ruang/news/239340/Ruang-Volcano-Volcanic-Ash-Advisory-HIGH-LEVEL-VA-ERUPTION-TO-FL300-MOV-W-OBS-VA-DTG-161830Z-to-3000.html]. For 30 Apr, GVP citing Darwin VAAC: plumes to 15.2 km by 0300 and 19.2 km (63,000 ft) by 0320 local, possibly 23 km [REPORTED: https://volcano.si.edu/showreport.cfm?wvar=GVP.WVAR20240424-267010 via search summary]. An ICAO APAC VAAC paper reportedly says about 80,000 ft with a base near 45,000 ft [REPORTED: ICAO MET SG/28 IP/15, via search summary]. SIGMETs lost. | VONA 2024RUA003, 20240417/1215Z, ORANGE: "11920 FT (3725 M) above sea level ... Source of height data: ground observer". VONA 20240430/0035Z, still **ORANGE**: ash top "18320 FT (5725 M)", ground observer; the previous VONA (20240429/1835Z) said "Ash-cloud is not observed" [CONFIRMED: https://magma.esdm.go.id/v1/vona?code=RUA&page=1 and page=2, and the detail page for vona/8160]. MAGMA defines Orange as column "below 6000 meter above sea level", while the VAAC reported 15-19 km. | adsb.lol v2024.04.17 and v2024.04.30 prod (1.84 GB each; the 2024 network was smaller) [CONFIRMED]. | AWS 2024-04-17 and 2024-04-30 [CONFIRMED]; NICT tile 404 for 2024-04-30. | Sam Ratulangi (Manado) closed from 17 Apr 19:26 WITA, extended several times; AirNav: 33 flights and 3,182 passengers on the first closure [REPORTED: https://en.tempo.co/read/1857929/..., https://english.news.cn/20240418/9bc2cb176f0a430eb5c7a24b6c3b094b/c.html]; FR24: "seven airports have been closed" [REPORTED: https://www.flightradar24.com/blog/aviation-news/aviation-safety/ruang-volcano-flight-disruption/]. | Largest height disagreement (VONA 18,320 ft vs VAAC 63,000 ft), but VAA text and ADS-B coverage near Manado are weak |
| 4 | **Lewotobi Laki-laki, 2024-11-07 to 11-13** | Darwin VAAC: 16.7 km (55,000 ft) on 7 Nov, 15.2 km on 8 Nov, 15.8 km on 9 Nov; 2.4-4.6 km on 13-16 Nov; ash moving W at about 20 kt on 13 Nov 0700Z [REPORTED: https://volcano.si.edu/showreport.cfm?wvar=GVP.WVAR20241113-264180 and https://watchers.news/2024/11/13/bali-flights-canceled-as-lewotobi-volcano-eruption-sends-ash-9-km-29-500-feet-high-indonesia/, via search summary]. Polygons need the mirror. SIGMETs lost. | VONAs (LWK pages 50-54): 20241107/0319Z RED, 30,669 ft; 20241108/2126Z RED, 37,069 ft; 20241112/0559Z RED, 33,869 ft; 20241112/1118Z RED, "Ash-cloud is not observed"; 20241110/0100Z RED, "Ash-cloud is not observed" [CONFIRMED: https://magma.esdm.go.id/v1/vona?code=LWK&page=52 and neighbouring pages]. VONA 30,669 ft against VAAC 55,000 ft on 7 Nov. | adsb.lol v2024.11.12 and v2024.11.13 (2.1 GB each) [CONFIRMED]. Bali to Australia traffic. | AWS 2024-11-07 [CONFIRMED]. | Bali: at least 90 flights cancelled [REPORTED: https://en.antaranews.com/amp/news/334221/bali-airport-cancels-90-flights-due-to-mt-lewotobi-eruption]; Virgin Australia: "all Virgin Australia flights in and out of Denpasar have been canceled for today, 13 November 2024" [REPORTED: https://simpleflying.com/virgin-australia-airlines-cancel-flights-bali-volcanic-ash-mount-lewotobi-laki-laki-eruption/]. | Good story with Australian airlines, but VAA texts would have to be retrieved by hand |
| 5 | **Lewotobi Laki-laki, 2025-03-20** | Darwin VAA 2025/344 "VA TO FL100 NO LONGER OBSERVED OBS VA DTG: 20/2320Z" [REPORTED: mirror title]. Peak heights [UNVERIFIED]. | VONA 20250320/1456Z RED, 30,669 ft; 20250322/1116Z ORANGE, "Ash-cloud is not observed" [CONFIRMED: LWK pages 37-38]. | adsb.lol v2025.03.20 (2.53 GB) [CONFIRMED]. | AWS 2025-03-20 [CONFIRMED]; NICT 404. | "ash cloud 8km high, some flights cancelled" [REPORTED: https://www.aljazeera.com/amp/news/2025/3/21/indonesian-volcano-sends-ash-cloud-8km-high-some-flights-cancelled]. | Weaker than #4 |
| 6 | **Kanlaon, 2024-12-09** | Tokyo VAA 2024/62 (0724Z): "ERUPTION AT 20241209/0703Z FL180 EXTD W-SW REPORTED ... VA NOT IDENTIFIABLE FM SATELLITE DATA ... NO FURTHER ADVISORIES". VAA 2024/63 (0825Z): polygon SFC/FL220 MOV W 25KT, "VA HEIGHT UPDATED TO FL220 BASED ON GROUND REPORT", +6 h SFC/FL230, +12 h SFC/FL240. VAA 2024/66 (2350Z): "NOT IDENTIFIABLE ... NO FURTHER ADVISORIES" [CONFIRMED: https://ds.data.jma.go.jp/svd/vaac/data/TextData/2024/20241209_27202000_0062_Text.html, ..._0063_..., ..._0066_...]. SIGMETs lost. | The VAAC contradicts itself within one hour (not identifiable at FL180, then a polygon to FL220). PHIVOLCS figures for the day [UNVERIFIED]. | adsb.lol v2024.12.09 (1.99 GB) [CONFIRMED]. | AWS FLDK 10-min [UNVERIFIED for this date; the pattern held for every date tried]. | Cancellations [UNVERIFIED]. | Fully scriptable from Tokyo; good "VAAC revised itself" case |
| 7 | Semeru, 2026-09-23 to 09-25 | WAAF SIGMET 12 at 25 Sep 1120Z, polygon SFC/FL150 [CONFIRMED: isigmet date=2026-09-25T14:00:00Z]. Retrievable until about 2026-10-24. | Brief: VONA 20260923/2221Z at 13,363 ft moving NE, against SIGMET SFC/FL150 moving SE [UNVERIFIED by me]. | adsb.lol v2026.09.25 (3.53 GB) [CONFIRMED]. | AWS 2026-09-25 1400 [CONFIRMED]. | None. | Routine; same pattern as live data |
| 8 | Sakurajima, 2026-09-25 | RJJJ SIGMET B01 (1257Z): "VA CLD OBS AT 1236Z FL080 MOV E", no polygon; earlier SIGMETs Y01-Y03 and A01 have polygons SFC/FL070-FL100 [CONFIRMED]. | Tokyo VAA 2026/249 (1252Z): "ERUPTED AT 20260925/1236Z FL080 EXTD E ... VA NOT IDENTIFIABLE FM SATELLITE DATA" [CONFIRMED: https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20260925_28208001_0249_Text.html]. | adsb.lol v2026.09.25 [CONFIRMED]; Japanese coverage dense (17 aircraft within 150 nm at 05 JST). | AWS + JMA. | None. | Good for the point-only SIGMET case; low drama |
| - | Etna | Out of region (Toulouse VAAC, Rome FIR); a LIRR SIGMET for Etna was open on 2026-09-25 [CONFIRMED in sample]. Not researched further. | | | | | Not JAPAC; skip |

### Best single replay: Anak Krakatau, 2026-09-06 14:10Z to 2026-09-07 14:10Z

Reasons:
1. It is the strongest disagreement of all the cases. The official observatory notice was RED, said "Ash-cloud is not observed", and then went silent for 3 days, while Darwin VAAC carried ash at FL500 and eight airports closed. A dispatcher holding only the VONA would have seen no ash height; a dispatcher holding only the VAA would have seen nothing of the observatory's "continuing" eruption remarks.
2. It has the biggest and freshest impact figures: nearly 3,000 flights and 341,000 passengers (ABC), with Qantas and Singapore Airlines named. It is the brief's own lead hook.
3. All four legs exist. Aircraft: adsb.lol 5, 6 and 7 Sep. Satellite: AWS HSD and NICT true colour. Notices: MAGMA. Official polygons: Darwin VAAs, from the mirror.
4. The real diversions in the 6-7 Sep ADS-B are ground truth against which TEPHRA's drafted advisories can be compared. No other case offers that.

What must be done, and by when:
- Copy the Darwin VAA texts 2026/185 to 2026/199 by hand from a browser. The VolcanoDiscovery advisory pages need JavaScript; the list page gives the URLs, for example `https://www.volcanodiscovery.com/krakatau/news/343133/vaac-advisory-2026-189.html`. If they cannot be obtained by about 2026-10-12, switch to Taal.
- Accept that the WIIF SIGMET leg is missing and say so on screen: "official polygon = Darwin VAA".

**Fallback, and the build test case: Taal 2026-10-08.** Every leg can be fetched by script today. The SIGMET history API serves 8 Oct until about 7 Nov. It has dense traffic next to Manila and a clean three-source timeline:
- 1006Z: eruption.
- 1016Z: SIGMET FL090.
- 1029Z: VAAC "not identifiable", reported FL150, "no further advisories".
- 1034Z: SIGMET FL150.
- 1130Z: VAAC polygon FL150.
- 1750Z: VAAC "not identifiable", "no further advisories".
- SIGMET valid until 2111Z.
- PHIVOLCS: 4,000 m, Alert Level 1.

Save its SIGMETs, VAAs, PHIVOLCS bulletin and the adsb.lol 2026-10-08 release this week.

---

## 5. Conflicts with our idea

| # | Conflict | Grade | What has to change |
|---|---|---|---|
| C1 | The free SIGMET history API keeps only 30 days. The Anak Krakatau SIGMETs (5-7 Sep) are already gone, Semeru and Sakurajima on 25 Sep go around 25 Oct, and Taal on 8 Oct goes around 7 Nov [CONFIRMED error text above]. | SERIOUS for the Krakatau replay, MINOR overall | Start archiving the SIGMET JSON, MAGMA VONAs, tgftp FV bulletins and Tokyo TextData to Cloud Storage now, before the build. For pre-September cases use the VAA as the official polygon and label it. |
| C2 | 59 of 83 Fukuoka-FIR VA SIGMETs in the sample have no polygon, only "PSN ... FL080 MOV E" or "STNR". All 473 Indonesian ones do have polygons [CONFIRMED, my count]. The rule "the cone can never shrink below the official polygon" is undefined for these. | SERIOUS (design rule) | Define a fallback official shape: a circle around PSN of stated radius, or the matching VAA polygon if one exists, labelled as derived. Gemini must not invent the official shape. |
| C3 | Darwin VAAC's own pages do not serve advisory text to scripts. BoM's block page says scraping is not supported. Historical Darwin VAA detail pages on the mirror are behind a Cloudflare challenge [CONFIRMED]. | MINOR live, SERIOUS for history | Live: poll `https://tgftp.nws.noaa.gov/data/raw/fv/fvau0[1-9].adrm..txt` (NOAA, public, latest per header), which gave all four open Darwin VAAs. History: copy by hand, or rely on our own archive from now on. |
| C4 | The VONA "contradiction" is mostly night-time visibility. Most Semeru VONAs say "Ash-cloud is not observed" because the observer cannot see; they do not mean there is no ash [CONFIRMED pattern on https://magma.esdm.go.id/v1/vona]. A judge may see the disagreement as trivial. | MINOR | The prompt and the UI must treat "not observed" as "no information", never as "no ash". Lead the pitch with real height disagreements (Ruang: VONA 18,320 ft vs VAAC 63,000 ft; Lewotobi: VONA 30,669 ft vs VAAC 55,000 ft; Krakatau: RED VONA with no height vs VAAC FL500) and the SIGMET outlasting the VAAC (Taal). |
| C5 | Headline events are rare: about 3% of days. The live demo on 18 Oct and 4 Dec will show routine low plumes (FL060-FL150), not a closure. | MINOR | Live mode for proof-of-liveness, labelled replay for the per-flight drama. That is already the plan; make the label explicit. |
| C6 | adsb.lol returned HTTP 429 after three point queries within about 10 s [CONFIRMED]. | MINOR | One poll per 60 s for a single bounding box, or the bulk `/v2/` endpoints with a back-off. |
| C7 | Night traffic near the Indonesian volcanoes is thin (1-6 aircraft within 250 nm at 03-04 local) [CONFIRMED]. | MINOR | Demo between 00Z and 10Z (08-18 SGT/WITA/PHT). The Singapore finale on 4 Dec is in UTC+8 daytime, which suits this. |
| C8 | The brief's impact number "at least 373 flights affected" (CNBC) could not be opened (403). ABC gives "nearly 3,000 flights" and 341,000 passengers. | NONE (supports a bigger hook) | Use the ABC numbers with the ABC link; drop the 373 figure unless CNBC is re-checked. |
| C9 | The brief calls the Tokyo Darwin-backup page "Darwin's list". It only shows advisories that Tokyo issued as backup. | MINOR | Cite the Darwin numbers from tgftp or the VAA itself. |
| C10 | The Smithsonian GVP weekly report and RSS are behind a bot-verification page [CONFIRMED 403]. | MINOR | Do not use GVP as a live feed; it is not needed. |
| C11 | NICT true-colour tiles were not served for any 2024-2025 date tested. | MINOR | For 2024-2025 replays render Band 13 or Dust RGB from the AWS HSD files (more work), or prefer the 2026 cases. |

Nothing found is FATAL. Every feed the idea needs was reachable today without keys. The ash really is there on any day, and the sources really do disagree in public text.

---

## 6. What this supports

- **Ash is present on demo days:** 119/119 six-hourly snapshots over 30 days had at least 3 open Asia-Pacific VA SIGMETs. Ibu and Semeru have run at about 4 Darwin advisories a day through all of 2025 and 2026 to date.
- **The feeds are reachable without keys:** aviationweather SIGMET JSON, NOAA tgftp FV bulletins (Darwin and Tokyo VAAs), MAGMA VONA HTML, JMA warning JSON, the PHIVOLCS WOVOdat bulletins, the KVERT pages, adsb.lol live and history, Himawari on AWS and NICT. All returned 200 today, apart from the rate-limit and Cloudflare notes above.
- **Contradictions are public and timestamped,** which is the core of the Gemini step:
  - Semeru, today: SIGMET/VAA "VA CLD OBS ... SFC/FL150" against VONA "Ash-cloud is not observed", same minute.
  - Taal, 8 Oct: SIGMET FL090 then FL150 within 18 min; VAAC "not identifiable" then a polygon, then terminated while the SIGMET runs 3 more hours; PHIVOLCS calls it "minor" and keeps Alert Level 1.
  - Kanlaon, 2024: the VAAC raised FL180 to FL220 within an hour on a ground report.
  - Ruang, 2024: the VONA stayed ORANGE (column below 6,000 m by definition) while the VAAC reported 19 km.
  - Anak Krakatau, 2026: a RED VONA with "Ash-cloud is not observed" and 3 days of silence during an eight-airport closure.
- **Ground-truth replay exists:** adsb.lol daily dumps (ODbL) for every candidate date, so the advisories TEPHRA drafts can be compared with what aircraft actually did.
- **A "SIGMET history" feature is possible for free:** the API's `date` parameter serves the last 30 days, which lets the app show the evolution of a case as it happened.

---

## Open questions

1. Can the Darwin VAA texts 2026/185-199 for Krakatau (5-7 Sep) be copied from VolcanoDiscovery in a normal browser? Do they carry multi-polygons at FL500?
2. Does the isigmet `date` parameter return SIGMETs valid at that instant, or issued near it? The API docs were not read.
3. What is adsb.lol coverage over the Java Sea, Sunda Strait and Mindoro on the replay days? It needs one tar download and a count of traces within 250 nm.
4. Were any flights cancelled or diverted for Taal on 8 Oct 2026 or Kanlaon on 9 Dec 2024? Not searched (budget).
5. What heights did PHIVOLCS publish for Kanlaon on 9 Dec 2024?
6. Does OpenSky give Trino access to a free account? Unchecked; assume no.
7. Is there a free long-term archive of international SIGMETs (Ogimet or similar) for events older than 30 days? Not found.
8. What did the latest Smithsonian GVP weekly report say (blocked)? And what are the current PNG (RVO), Vanuatu (VMGD) and Tonga alert levels?
9. Which HSD segment numbers cover Krakatau (6.1 S), Taal (14 N) and Ruang (2.3 N)?
10. Will Sinabung and Merapi (both Level III) or Tokachidake (Level 3 since 12 Sep) produce a fresh headline event before 18 Oct? This cannot be forecast; check again on 17 Oct.

## Sources

All accessed 2026-10-10 (UTC 2026-10-09 19:45-20:10) unless marked.

- https://aviationweather.gov/api/data/isigmet?format=json&hazard=va
- https://aviationweather.gov/api/data/isigmet?format=json&hazard=va&date=2026-09-06T12:00:00Z (30-day error)
- https://aviationweather.gov/api/data/isigmet?format=json&hazard=va&date=2026-09-25T14:00:00Z
- https://aviationweather.gov/api/data/isigmet?format=json&hazard=va&date=2026-10-08T10:30:00Z
- https://aviationweather.gov/api/data/isigmet?format=json&hazard=va&date=<every 6 h, 2026-09-10T00:00:00Z to 2026-10-09T18:00:00Z> (120 requests)
- https://tgftp.nws.noaa.gov/data/raw/fv/ and fvau01.adrm..txt through fvau08.adrm..txt, fvfe01.rjtd..txt
- https://ds.data.jma.go.jp/svd/vaac/data/vaac_list.html
- https://ds.data.jma.go.jp/svd/vaac/data/vaac_darwin_list.html
- https://ds.data.jma.go.jp/svd/vaac/data/index.html
- https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20261008_27307000_0021_Text.html (also _0022, _0023, _0024)
- https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20261008_28208001_0279_Text.html
- https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20261007_27303000_0803_Text.html
- https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20261005_30027000_0353_Text.html
- https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20260925_28208001_0249_Text.html
- https://ds.data.jma.go.jp/svd/vaac/data/TextData/2024/20241209_27202000_0062_Text.html (also _0063, _0066)
- https://www.jma.go.jp/bosai/volcano/data/warning.json
- https://www.data.jma.go.jp/vois/data/tokyo/STOCK/kaisetsu/English/level.html
- https://magma.esdm.go.id/v1/gunung-api/tingkat-aktivitas
- https://magma.esdm.go.id/v1/vona
- https://magma.esdm.go.id/v1/vona?code=RUA (pages 1-2)
- https://magma.esdm.go.id/v1/vona?code=KRA (pages 1-12)
- https://magma.esdm.go.id/v1/vona?code=LWK (pages 20, 36-40, 50-54, 56, 60, 80)
- https://magma.esdm.go.id/v1/vona/8160?signature=8e186b6b1d6e1e371bffb72a478bada883aadb26c151d500c138debfc39e8917
- https://magma.esdm.go.id/v1/vona/8212?signature=6d3c3cbe2d4dea2e0048b48aeb3d372ac3b5416a89cc6eadc0d8261e2073ab0a
- https://magma.esdm.go.id/v1/vona/22575?signature=4bce6aa9ba49588f081932c1c7f70bf9e2ec6e6159818c722d6bd692cfc19289
- https://magma.esdm.go.id/v1/vona/22593?signature=db900e48d358430906f21bca19dc4d6743f4aa81d32146855f4e5d77dfcdb72c
- https://wovodat.phivolcs.dost.gov.ph/bulletin/list-of-bulletin
- https://wovodat.phivolcs.dost.gov.ph/bulletin/activity-tvo?bid=16869&lang=en
- https://wovodat.phivolcs.dost.gov.ph/bulletin/activity-mvo?bid=16872&lang=en
- https://wovodat.phivolcs.dost.gov.ph/bulletin/activity-kvo?bid=16870&lang=en
- http://www.kscnet.ru/ivs/kvert/van/index?type=1
- http://kvert.febras.net/ and http://kvert.febras.net/color
- https://www.bom.gov.au/aviation/volcanic-ash/ and https://www.bom.gov.au/aviation/volcanic-ash/darwin-va-advisory.shtml
- ftp://ftp.bom.gov.au/anon/gen/fwo/ (listing)
- https://www.volcanodiscovery.com/krakatau/news.html
- https://www.volcanodiscovery.com/ibu/news/374545/vaac-advisory-2026-1146.html
- https://www.volcanodiscovery.com/krakatau/news/343133/vaac-advisory-2026-189.html (Cloudflare challenge)
- https://www.abc.net.au/news/2026-09-07/australians-stranded-as-volcanic-ash-closes-jakarta-airport/107125502
- https://www.cnbc.com/2026/09/07/flights-canceled-jakarta-airport-anak-krakatau-eruption-disrupts-regional-travel-volcano.html (403)
- https://noaa-himawari9.s3.amazonaws.com/?list-type=2&delimiter=/&prefix= and the AHI-L1b-FLDK date prefixes listed in section 4
- https://himawari8-dl.nict.go.jp/himawari8/img/D531106/1d/550/2026/09/06/030000_0_0.png (and the other dates tested)
- https://github.com/adsblol/globe_history_2024, _2025, _2026 releases and expanded_assets for the tags listed
- https://raw.githubusercontent.com/adsblol/globe_history_2026/main/README.md
- https://api.adsb.lol/v2/point/-6.1/105.4/250 (and the other points in section 2e)
- https://samples.adsbexchange.com/readsb-hist/2026/09/01/000000Z.json.gz (and other 1st-of-month dates)
- https://www.adsbexchange.com/products/historical-data/
- https://opensky-network.org/data/trino (JS only; WebFetch 403)
- https://volcano.si.edu/reports_weekly.cfm and https://volcano.si.edu/news/WeeklyVolcanoRSS.xml (403 or verification page)
- https://www.vmgd.gov.vu/vmgd/index.php/geohazards/volcano/volcano-info/volcanic-alert-level
- https://mesonet.agron.iastate.edu/cgi-bin/afos/retrieve.py (no VAA products found)
- From search results (not opened): https://www.volcanodiscovery.com/ibu/news/288951/vaac-advisory-2025-1371.html ; https://www.volcanodiscovery.com/semeru/news/290436/vaac-advisory-2025-1480.html ; https://www.volcanodiscovery.com/lewotobi/news/271897/vaac-advisory-2025-344.html ; https://www.volcanodiscovery.com/ruang/news/239340/Ruang-Volcano-Volcanic-Ash-Advisory-HIGH-LEVEL-VA-ERUPTION-TO-FL300-MOV-W-OBS-VA-DTG-161830Z-to-3000.html ; https://volcano.si.edu/showreport.cfm?wvar=GVP.WVAR20240424-267010 ; https://volcano.si.edu/showreport.cfm?wvar=GVP.WVAR20241113-264180 ; https://www.icao.int/sites/default/files/APAC/Meetings/2024/2024%20MET%20SG-28%20and%20MET%20Seminar/4-Information%20Papers/IP15_AI6_AUS-JPN-NZL_COMBINED-APAC-VAAC-MANAGEMENT-REPORT.pdf (403 on fetch) ; https://en.tempo.co/read/1857929/indonesias-ruang-volcano-eruption-forces-sam-ratulangi-airport-closure ; https://english.news.cn/20240418/9bc2cb176f0a430eb5c7a24b6c3b094b/c.html ; https://en.antaranews.com/news/311316/manado-airport-extends-closure-until-monday-due-to-mt-ruang-eruption ; https://www.flightradar24.com/blog/aviation-news/aviation-safety/ruang-volcano-flight-disruption/ (403 on fetch) ; https://en.antaranews.com/amp/news/334221/bali-airport-cancels-90-flights-due-to-mt-lewotobi-eruption ; https://simpleflying.com/virgin-australia-airlines-cancel-flights-bali-volcanic-ash-mount-lewotobi-laki-laki-eruption/ ; https://watchers.news/2024/11/13/bali-flights-canceled-as-lewotobi-volcano-eruption-sends-ash-9-km-29-500-feet-high-indonesia/ ; https://www.aljazeera.com/amp/news/2025/3/21/indonesian-volcano-sends-ash-cloud-8km-high-some-flights-cancelled ; https://www.aljazeera.com/news/2025/6/18/dozens-of-bali-flights-cancelled-after-indonesia-volcano-erupts

## Search log

WebSearch (extended mode): 4 completed and 1 refused (session budget exhausted).
1. `Darwin VAAC Ibu "ADVISORY NR: 2025/" December 2025`: found Ibu 2025/1371 (8 Dec 2025).
2. `volcanodiscovery Semeru "vaac-advisory-2025" December 2025 Darwin`: found Semeru 2025/1480 (27 Dec 2025).
3. `Ruang eruption 30 April 2024 Darwin VAAC FL ash height Sam Ratulangi airport closed flights`: GVP 63,000 ft, ICAO 80,000 ft, Manado closures.
4. `Lewotobi Laki-laki November 2024 eruption Bali flights cancelled Darwin VAAC FL ash column height Jetstar Virgin`: Bali cancellations, VAAC heights.
5. `Anak Krakatau eruption September 2026 Soekarno-Hatta airport closed flights cancelled ash`: **not performed** (budget). Replaced by a direct fetch of the ABC article from the prior pack and the MAGMA/VolcanoDiscovery archives.

WebFetch: 9 calls (volcanodiscovery Ibu 403, GVP weekly 403, ICAO PDF 403, CNBC 403, ABC OK, FR24 403, OpenSky 403, plus the two above).

Direct curl fetches: about 230. These include 120 SIGMET-history snapshots, 260 parallel probes of Tokyo TextData for Kanlaon (5 hits), about 25 MAGMA pages, 10 tgftp bulletins, 8 Himawari S3 listings, 6 NICT tiles, about 14 GitHub release pages, 5 adsb.lol live queries (2 rate-limited, retried), and the JMA, PHIVOLCS, KVERT, BoM, ADS-B Exchange, OpenSky, GVP, VMGD and IEM pages listed in Sources.
