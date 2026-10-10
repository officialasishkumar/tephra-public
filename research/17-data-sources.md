# 17. Data sources: what the 10 Oct data hunt verified

Prepared 2026-10-10. The sources were fetched between about 04:50Z and 06:30Z the same day. Seven parallel passes looked for: ash products and their archives, observatory data, satellite layers, aircraft data, weather, winds and airspace, evaluation and pitch evidence, and UI references. This file catalogues what they verified, what each source is for, and what it costs. Publication rules for the data are in `../docs/DATA-LICENCES.md`.

**How the hunt worked.** GET requests only, about 50 MB at most per source, robots.txt and crawl delays respected, no sign-ups, no keys, no gcloud, and nothing fetched from magma.esdm.go.id. One accident is on record: a shell bug turned four ECMWF byte-range requests into a full download, which was stopped after at least 86 MB of a 136 MB file and deleted (weather pass). One RealEarth `/api/` search went out in the same command as the robots.txt check, before its `Disallow: /api/` was read; no further `/api/` calls were made. The hunt's own scripts, samples and downloaded files stayed in the session scratchpad, outside this repo (section 12).

**How to read an entry.**
- **Gives**, **URL**, **Licence** (quoted, with the page it came from), **Access**, **Verified**, **Use** (Now = in the build; Could = a proposal), **Effort** (S under a day, M one to two days, L more).
- A **Verified** line is the hunt's own fetch on 10 Oct. Read it as `[CONFIRMED: first URL listed, accessed 2026-10-10]` unless it says UNVERIFIED or REPORTED. "Re-checked" means the figure was recounted for this file from the hunt's saved copy.
- Status tags: **IN BUILD**, **CANDIDATE**, **PRIVATE USE ONLY** (the licence bars publishing), **NEEDS PERMISSION**, **EVAL ONLY**, **PITCH ONLY**.
- Every new map host must be added to both `img-src` and `connect-src` of the CSP in `tephra/api/server.py` (api owner) and to `MODULES.md` 8.1. At 07:05Z the CSP allowed `tiles.openfreemap.org`, `gibs.earthdata.nasa.gov` and `tiles.mapterhorn.com`.

---

## 1. Bottom line

1. **The Anak Krakatau replay can be rebuilt; research/09 called it lost.** The Iowa Environmental Mesonet (IEM) NOAAPort archive holds the Jakarta FIR VA SIGMETs, and the Melbourne FIR ones for the detached high cloud (R1). The hunt read 6 Sep 00:00–04:01Z and found WIIF SIGMETs 01–03; the day files for 5–8 Sep exist. BoM's anonymous FTP holds every Darwin VAA of the event, 2026/161–207 (R4). Jakarta's METARs reported VA 69 times (R2). The adsb.lol archive shows the empty sky (section 7.2, item 3). The one catch is the licence: BoM's FTP copies may not be passed on, so a public replay must use the NWS or IEM relay of the same bulletins.
2. **Open ADS-B sees Jakarta and Krakatau but not Semeru.** On 25 Sep, 11:00–11:30Z, adsb.lol had 0 aircraft within 100 nm of Semeru and 59 within 100 nm of Soekarno-Hatta. There were none within 250 nm of Lewotobi, Lewotolok, Dukono or Ibu. The live per-flight moment has to use Jakarta and Krakatau traffic. airplanes.live does cover East Java, but its API answers only after the user emails them (L10).
3. **An observed sounding backs the SIGMET at Semeru on 25 Sep.** The Surabaya radiosonde of 11:30Z measured winds toward 110° and 145° at plume height, which is the SIGMET's south-east. The north-east flow sat below the summit (E9). The pitch must not imply that the observatory's "north" was right. TEPHRA's value is that it plans around both while the sources disagree.
4. **Four earlier statements are corrected** (README claims register; section 10):
   - QVA is *recommended* for all VAACs from 26 Nov 2026, not due. No public Darwin or Tokyo QVA was found (P10).
   - NASA GIBS does have a TROPOMI SO2 layer (M2).
   - Badan Geologi lowered Anak Krakatau to Level II on 21 Sep (L6).
   - The sources' summit elevations for Semeru agree within DEM error (section 7.2, item 10).
5. **New pitch evidence with primary sources** (section 7):
   - Indonesia's DGCA circular SE-DJPU 15/2026, in force since 6 Sep, requires operators to do a safety risk assessment before flying into ash-threatened airspace, and to report every ash encounter.
   - Sinabung closed Kualanamu on 1 Sep, five days before Jakarta closed.
   - DGCA's own numbers for Soekarno-Hatta on 6 Sep.
   - USGS DS 545: Indonesia, the Philippines and Japan account for 40% of recorded encounters and 5 of the 9 in-flight engine failures (1953–2009).
   - Bali, Nov 2024: 28 of 42 international airlines kept flying while the others did not.
   - Darwin's workload is about 5,700–5,900 advisory bulletins a year.
6. **Licence traps.**
   - BoM FTP files may not be supplied to anyone else.
   - MAGMA pages are "All Rights Reserved" and name observatory staff.
   - NICT imagery and Open-Meteo's free API are non-commercial.
   - adsb.lol data is ODbL (attribution, share-alike).
   - MIROVA forbids altering its data, and PHIVOLCS forbids redistribution.
   - In Japan, editing JMA forecast values counts as forecasting under the Meteorological Service Act.
   `../docs/DATA-LICENCES.md` turns this into a checklist.
7. **There is a licence-clean alternative for each non-commercial input:**
   - for winds, ECMWF open data (CC BY 4.0) and GFS (public domain);
   - for imagery, NOAA's Himawari HSD and NASA GIBS tiles;
   - for FIR outlines, AWC's public-domain polygons, which the Wall now uses.
8. **A Google Cloud angle that needs no login.** Himawari-8/9 HSD, GFS, ECMWF open data and ARCO-ERA5 all sit in public Google Cloud Storage buckets, readable over plain HTTPS (L17, L18, L19, R9).
9. **More prior art.**
   - `mzmznasipadang/ash-map` is the AshMap project already in research/04, now with more detail.
   - Indonesia's DGCA runs ash collaborative decision-making through I-WISH.
   - AirNav Indonesia has a GenAI NOTAM tool.
   - SITA eWAS Dispatch shows dispatchers every aircraft with hazards.
   They are added to `CONFLICTS.md` (A11–A14).

---

## 2. What the build already uses

"Seen in the tree" records what was in the working tree between 07:05Z and 07:25Z on 10 Oct. Other agents were editing at the same time.

| Source | Entry | Where | Seen in the tree |
|---|---|---|---|
| NASA GIBS (Himawari-9 tiles; TROPOMI SO2) | M1, M2 | Wall map layers | The CSP allows `gibs.earthdata.nasa.gov`, and `tephra/web/THIRD_PARTY.md` lists the layers; the layer code was not yet in `wall.js` |
| Mapterhorn terrain tiles | M10 | Wall hillshade | The CSP allows `tiles.mapterhorn.com`; the layer code was not yet in `wall.js` |
| IEM NOAAPort raw-text archive | R1 | Replay back-fill | `scripts/record_replay.py noaaport` |
| Open-Meteo Historical Forecast API | R7 | Plume evaluation winds; replay winds | `scripts/make_plume_cases.py`; `scripts/record_replay.py` (`historical_wind_url`); `tests/fixtures/ops_evals/` |
| adsb.lol archive (`globe_history` heatmaps) | R5 | Replay ADS-B back-fill | `scripts/record_replay.py` (heatmap decoder that rebuilds point-API answers) |
| AWC FIR polygons and VAAC areas | M14 | Wall context layers | `tephra/web/data/firs.geojson`, `vaac_aor.geojson` (replaced the VATSIM file the same day) |
| OurAirports navaids and airports | M16 | Wall layer; airport catalogue | `tephra/web/data/navaids.geojson`, `data/airports.json` |
| Natural Earth 1:50m countries | M20 | Offline basemap fallback | `tephra/web/data/land_apac.geojson` |
| Smithsonian GVP WFS | M23 | Volcano catalogue | `data/volcanoes.json` |
| BoM anonymous FTP | R4 | Census; Semeru replay | `research/data/census/raw/darwin/ftp/`, `data/replay/semeru-20260923/raw/vaac_darwin/` (private use only) |
| Tokyo VAAC frames | E2 | Plume Reader evaluation | `scripts/make_plume_cases.py` |
| IBM Plex fonts; Lucide, Material Symbols, Maki icons | section 8 | Wall and Desk | `tephra/web/fonts/` (with `OFL.txt`), `tephra/web/icons.svg` |

The older live feeds are documented in research/05 and are not repeated here. They are: AWC SIGMET, TAF and METAR JSON; NWS tgftp FV (Darwin VAAs); the JMA Tokyo VAAC list; JMA MSC images; NICT; AWS Himawari HSD; the adsb.lol point API; Open-Meteo forecasts; and MAGMA VONAs, which are off by default.

---

## 3. Live feeds

### L1. AWC SIGMET API in IWXXM (`format=iwxxm`) — CANDIDATE
- **Gives:** the VA SIGMETs TEPHRA already reads as JSON, as ICAO IWXXM 2025-2 `VolcanicAshSIGMET` XML. Each has GML polygons (lat lon order), sequence number, validity and motion, plus the original TAC and WMO header in a comment. The 30-day history works through `date=`.
- **URL:** https://aviationweather.gov/api/data/isigmet?format=iwxxm&hazard=va ; https://aviationweather.gov/api/data/sigmet?format=iwxxm&hazard=va&date=2026-10-08T12:00:00Z
- **Licence:** "The information on National Weather Service (NWS) Web pages are in the public domain, unless specifically noted otherwise" (https://www.weather.gov/disclaimer).
- **Access:** keyless; 100 requests a minute; no CORS. AWC marks these translations `permissibleUsage="NON-OPERATIONAL"`; `isigmet` is deprecated in favour of `/sigmet`.
- **Verified:** 05:50Z, HTTP 200, 50,279 B, 12 records (WAAF, WIIF, RPHI, SEFG, MHTG, SKED). History for 8 Oct 12:00Z: 200, 17 VA SIGMETs including RJJJ S03 and RPHI 1–3 (Taal). The Kanlaon RPHI SIGMET 1 of 10 Oct carries no geometry.
- **Use:** Could add an optional IWXXM path to `tephra/feeds/sigmet.py` (feeds-text) that links each SIGMET to its raw bulletin and collapses duplicates; the JSON path stays the default. Pitch line: "TEPHRA reads ICAO's digital format".
- **Effort:** M.

### L2. NWS tgftp WV directory (raw VA SIGMET bulletins, cancellations included) — CANDIDATE
- **Gives:** the latest raw VA SIGMET bulletin per WMO header, among them Jakarta (`wvid20.wiii`), Ujung Pandang, Melbourne (Indian Ocean, `wvau01.ymmc`), Manila, Fukuoka, Kuala Lumpur and Wellington. Unlike the AWC JSON, it carries CNL SIGMETs.
- **URL:** https://tgftp.nws.noaa.gov/data/raw/wv/
- **Licence:** the NWS notice as in L1. NWS adds: "Third-party information and imagery are used under license by the individual third-party provider." The bulletins come from BMKG, BoM and other offices.
- **Access:** keyless directory of 375 entries, the latest bulletin per header only.
- **Verified:** 05:34Z. `wvid20.wiii` (modified 04:14Z): 'WIIF SIGMET 04 VALID 100412/101012 … MT KRAKATAU … SFC/FL060 MOV SW 05KT WKN='. Two Krakatau-event cancellations were never overwritten: WIIF on 5 Sep 00:51Z and YMMM on 7 Sep 11:32Z.
- **Use:** Could poll every 60 s next to AWC, apply CNL lines at once, and add YMMC so ash over the Indian Ocean is covered. The Krakatau high cloud crossed into the Melbourne FIR on 6–7 Sep. Take the FIR and series from the text, not the file name.
- **Effort:** S.

### L3. JMA disaster-prevention XML (eruption observation reports, plume-direction reports, ash-fall forecasts, warnings) — CANDIDATE (Japan)
- **Gives:** a machine-readable Japanese observatory notice that plays the VONA's part.
  - Eruption observation report (VFVO52): eruption time, crater position, plume height above the crater (m) and above sea level (FT), and direction, about 8 minutes after an eruption.
  - Plume-direction report (VFVO60): a 46-level wind profile over the crater, SFC to FL450.
  - Ash-fall forecast (VFVO53): 3-hourly ash-fall polygons and the municipalities affected. Sakurajima's forecast of 10 Oct 05:00Z listed Kirishima City, where Kagoshima airport (RJFK) is.
- **URL:** https://www.data.jma.go.jp/developer/xml/feed/eqvol.xml (updated every minute, keeps at least 10 minutes); https://www.data.jma.go.jp/developer/xml/feed/eqvol_l.xml (hourly, keeps several days)
- **Licence:** content "may be used in accordance with the terms and conditions of use stipulated in Public Data License (Version 1.0)", and "The Terms of Use are compatible with the Creative Commons Attribution License 4.0" (https://www.jma.go.jp/jma/en/copyright.html).
  - The XML notes (2020-09-01) say secondary use is "原則として制限はありません" (in principle unrestricted), as long as it does not go against the Meteorological Service Act. Editing forecast values, or showing values that differ from the XML, counts as forecasting business and needs a licence under Art. 17 (https://xml.kishou.go.jp/considerationforxml.pdf).
  - More than 10 GB a day from one IP gets the IP blocked (https://xml.kishou.go.jp/xmlpull.html).
- **Access:** keyless Atom feeds; conditional GET returns 304.
- **Verified:** 05:19Z. `eqvol.xml` 200 (33 entries). `eqvol_l.xml` 200 (499 entries, 3–10 Oct: 392 ash-fall forecasts, 16 eruption reports, 16 plume-direction reports, 16 warnings). Sample eruption report: Sakurajima on 8 Oct at 04:53Z, 1,000 m above the crater, 6,800 FT AMSL, straight up. The message came 8 minutes after the eruption.
- **Use:** Could add a poller (for example `tephra/feeds/jma_volcano.py`) and use it in three ways:
  - eruption reports become the observatory card for Japanese volcanoes;
  - the plume-direction profile becomes JMA's own vent wind;
  - the ash-fall forecast is drawn as a separate, unaltered "JMA ash-fall forecast" layer.
  TEPHRA must never widen or edit a JMA warning or ash-fall polygon (Meteorological Service Act Art. 17 and 23). JMA volcano codes map to GVP numbers through L4 (506 → 282080).
- **Effort:** M.

### L4. JMA bosai volcano JSON — CANDIDATE
- **Gives:** the table of 120 JMA volcano codes with positions and names, plus the latest commentary and warning per volcano. On 9 Oct Sakurajima had 16 eruptions over 5–9 Oct, at Level 3.
- **URL:** https://www.jma.go.jp/bosai/volcano/const/volcano_list.json ; https://www.jma.go.jp/bosai/volcano/data/info/506.json ; https://www.jma.go.jp/bosai/volcano/data/warning/506.json
- **Licence:** JMA Public Data License 1.0, as L3.
- **Access:** keyless and undocumented.
- **Verified:** 05:22Z, all 200 (`volcano_list.json` 19,697 B, 120 entries; some lack English names).
- **Use:** Could build the JMA-code to GVP table once, and show JMA's alert level on Japanese volcano cards.
- **Effort:** S.

### L5. PHIVOLCS-LAVA daily bulletins (Taal, Kanlaon, Mayon, Bulusan) — CANDIDATE, display only
- **Gives:** daily 24-hour summaries in English and Filipino: alert level, earthquakes, SO2 flux, plume height and drift, and recommendations ("Flying any aircraft close to the volcano" is listed as prohibited).
- **URL:** https://wovodat.phivolcs.dost.gov.ph/bulletin/list-of-bulletin
- **Licence:** the PHIVOLCS data policy (https://wovodat.phivolcs.dost.gov.ph/user/policy) says:
  - "Data source should be cited as DOST-PHIVOLCS."
  - "DOST-PHIVOLCS data should not be used by anyone other than DOST-PHIVOLCS officials for publicly forecasting ongoing unrest in a monitored active volcano in the Philippines."
  - "Redistribution or charging for access to DOST-PHIVOLCS data is prohibited."

  RA 8293 s.176.1 says government works carry no copyright, but "prior approval … shall be necessary for exploitation of such work for profit".
- **Access:** keyless HTML; robots.txt allows everything; there is no API.
- **Verified:** 05:27Z. The list page is 200. Taal (`bid=16873`) is 200: 'ALERT LEVEL 1 … Sulfur Dioxide Flux 2,406 tonnes / day … Plume 900 meters tall; Moderate emission; southwest drift'. The URL path does not fix the volcano: `bid=12000` showed a Kanlaon bulletin under a 'TAAL VOLCANO' header.
- **Use:** Could show a daily observatory chip for Philippine volcanoes, with "Source: DOST-PHIVOLCS" and a link. Never republish whole bulletins, and never present forecasts of unrest.
- **Effort:** S.

### L6. Badan Geologi news archive (PVMBG alert-level changes) — CANDIDATE
- **Gives:** official reports on Indonesian level changes. Report No. 1604.Lap/GL.03/BGL/2026 covers Anak Krakatau:
  - raised to Level III on 2 Jul 2026;
  - a continuous eruption from 4 Sep 16:07Z to 5 Sep 17:04Z;
  - lowered to Level II on 21 Sep 2026 at 18:30 WIB.
- **URL:** https://geologi.esdm.go.id/profil/arsip-berita ; https://geologi.esdm.go.id/media-center/laporan-khusus-penurunan-tingkat-aktivitas-gunungapi-anak-krakatau-provinsi-lampung-dari-level-iii-siaga-menjadi-level-ii-waspada-tanggal-21-september-2026-pukul-18-30-wib
- **Licence:** none found. The footer reads 'Hak Cipta © 2026 Badan Geologi, Kementerian Energi dan Sumber Daya Mineral'. Link to it and quote facts only.
- **Access:** keyless. Unlike MAGMA, robots.txt disallows only `/geomap/` and `/geolindo/`.
- **Verified:** 05:40Z. robots.txt 200. The Krakatau report is 200 (6.1 MB with inline images). Archive pages 1–3 (11 Sep to 9 Oct) show no later change for Anak Krakatau.
- **Use:** Could poll page 1 hourly and show "Indonesian alert-level change (Badan Geologi)" with a link. Could also annotate the 4–6 Sep replay with the report's timeline. It is the only crawlable official Indonesian volcano channel the hunt found.
- **Effort:** S.

### L7. NWS tgftp WM directory (ICAO VONAs) — WATCH
- **Gives:** the latest VONA per WMO header. Today the relay carries only US (AVO, HVO, CNMI) and New Zealand VONAs, none from Indonesia, the Philippines or Japan.
- **URL:** https://tgftp.nws.noaa.gov/data/raw/wm/
- **Licence:** US VONAs are US government works: "Copyright protection under this title is not available for any work of the United States Government" (17 U.S.C. §105). NZ VONAs come from GeoNet: "licensed under a Creative Commons Attribution 3.0 New Zealand License".
- **Access:** keyless. The IWXXM twin, `/data/raw/lm/`, returned 403.
- **Verified:** 05:33Z, a listing of 8 files. The US relays are cut off after the colour-code lines, and the NZ files include `STATUS: TEST` messages. NWS SCN 25-71 confirms VONAs have been sent on the Aeronautical Fixed Service since November 2025.
- **Use:** Could add `wm` to the tgftp poller and raise an alert if an Indonesian or Philippine header ever appears. That would be the first lawful keyless VONA relay for the region. Drop TEST and EXER messages.
- **Effort:** S.

### L8. WMO WIS2: Singapore FIR SIGMETs over MQTT — data flow UNVERIFIED
- **Gives:** a keyless push channel for Singapore FIR (WSJC) SIGMETs, VA included, next to the Jakarta FIR.
- **URL:** discovery at https://wis2-gdc.weather.gc.ca/collections/wis2-discovery-metadata/items?q=volcanic&f=json ; topic `origin/a/wis2/sg-mss/data/recommended/weather/experimental/aviation/sigmet` on the WIS2 global brokers.
- **Licence:** Singapore Open Data Licence: "The Agency grants you a worldwide, perpetual, royalty-free, non-exclusive licence to Use the datasets." Products must include "a conspicuous notice acknowledging the source of the datasets." (https://data.gov.sg/open-data-licence)
- **Access:** MQTT with public credentials. The data class is 'recommended', which global caches do not hold.
- **Verified:** catalogue query 200, with 6 'volcanic' matches including `urn:wmo:md:sg-mss:recommended.weather.aviation.sigmet`. The stream itself was not subscribed. BMKG and JMA list no aviation datasets on WIS2 yet.
- **Use:** optional. Use the "ready for WIS2" pitch line only after the stream has been tested.
- **Effort:** M.

### L9. adsb.fi open data API (v3 point endpoint) — CANDIDATE fallback, non-commercial
- **Gives:** the same readsb JSON as adsb.lol (`ac`, and `now` in ms), within up to 250 nm of a point.
- **URL:** https://opendata.adsb.fi/api/v3/lat/{lat}/lon/{lon}/dist/{nm}
- **Licence:** 'adsb.fi open data is for personal, non-commercial use only. You may not license, sell, rent, or lease any part of the data or the service. … You must cite adsb.fi and include a link to our home page.' (https://github.com/adsbfi/opendata/blob/main/README.md)
- **Access:** keyless; one request a second; errors count toward a temporary IP block.
- **Verified:**
  - 05:21Z, within 100 nm of Surabaya: the same 2 aircraft adsb.lol had.
  - Within 100 nm of Bali: 0 aircraft.
  - 05:48Z, within 120 nm of Soekarno-Hatta: 18 aircraft against adsb.lol's 20, with 16 in common.
- **Use:** Could act as the fallback when adsb.lol answers 429 or 5xx, or be merged in for the Jakarta point (about 10% more targets). The parser works unchanged. It does not fix the eastern gap.
- **Effort:** S.

### L10. airplanes.live REST API — NEEDS PERMISSION (the user must email them)
- **Gives:** live aircraft in readsb format from the only open network the hunt saw covering East Java, including the Surabaya approaches.
- **URL:** https://api.airplanes.live/v2/point/{lat}/{lon}/{nm}
- **Licence:** not read; the API guide sits behind a Cloudflare challenge. The adsb.exposed README quotes the conditions airplanes.live set for that project: "no reselling the data; - no commercial use (except for within this application) without an agreement; - attribution is required" [REPORTED].
- **Access:** every path returns 403 with `{"error": "Please contact us at contact@airplanes.live. Your email MUST include any links, a description of the project, and any information you deem appropriate."}`.
- **Verified:** the API itself is UNVERIFIED (403 at 05:21Z). The coverage evidence comes from adsb.exposed rows tagged `airplanes.live` for 25 Sep:
  - 234 aircraft in an East Java box (6–10°S, 111–116°E), the nearest 14 nm from Semeru;
  - 19,394 positions below 10,000 ft within 30 nm of Surabaya;
  - 12–22 aircraft an hour within 100 nm of Semeru between 00Z and 14Z.

  For one flight, GIA420, adsb.lol's own trace has a single point while the airplanes.live rows have 890.
- **Use:** only the user can ask (an agent must not). The email should give:
  - the repo and live URL;
  - a one-paragraph description: a non-commercial hackathon decision-support demo;
  - the query plan: 2–3 points, at most one request a minute each;
  - the attribution line.

  If they agree, add it for the Semeru/East Java point only, with credit on the Wall. There are 8 days left, so a slow answer is likely.
- **Effort:** S once access is granted.

### L11. adsb.lol aircraft-derived winds (`wd`, `ws`, `oat`) — CANDIDATE
- **Gives:** wind direction, speed and outside air temperature that readsb derives for each aircraft from heading, airspeed, track and ground speed. These are observed winds at flight level.
- **URL:** the point API TEPHRA already calls, https://api.adsb.lol/v2/point/{lat}/{lon}/{nm}
- **Licence:** ODbL 1.0 (https://api.adsb.lol/api/openapi.json, research/05).
- **Access:** keyless; the same dynamic rate limits as the point calls TEPHRA already makes (bursts get 429).
- **Verified:** 05:50Z near Semeru: 14 aircraft, 8 of them with wind at FL270–FL380 (for example MAS250 at FL380, wind from 065° at 12 kt).
- **Use:** Could keep these fields with `alt_baro` and show an "aircraft-observed wind at FLxxx" chip beside the model wind. TEPHRA receives them today and drops them.
- **Effort:** S.

### L12. Open-Meteo Ensemble API — CANDIDATE, non-commercial
- **Gives:** wind from all 51 ECMWF ensemble members at pressure levels, which gives a measured spread of drift direction.
- **URL:** https://ensemble-api.open-meteo.com/v1/ensemble?latitude=-8.108&longitude=112.922&hourly=wind_speed_600hPa,wind_direction_600hPa&models=ecmwf_ifs025&forecast_hours=3&wind_speed_unit=kn&timezone=GMT
- **Licence:** as Open-Meteo (R7): the data are CC BY 4.0 and the free API is non-commercial only.
- **Access:** keyless, within the free-tier limits. Live only: a request for 25 Sep returned all members as null.
- **Verified:** 05:50Z, 200, 51 members at 600 hPa, toward 087–106° at 6.2–11.9 kt.
- **Use:** Could widen the forecast sector to the member spread at the plume-top level (widen only), with at most one call per volcano per model cycle.
- **Effort:** S.

### L13. NWS tgftp METAR and TAF station files — CANDIDATE fallback
- **Gives:** the latest METAR and TAF per station as plain text, plus hourly worldwide METAR cycle files covering 24 hours.
- **URL:** https://tgftp.nws.noaa.gov/data/observations/metar/stations/WARR.TXT ; https://tgftp.nws.noaa.gov/data/forecasts/taf/stations/WARR.TXT
- **Licence:** the NWS public-domain notice.
- **Access:** keyless plain text; only the latest report per station.
- **Verified:** 05:36Z. WARR METAR and TAF 200; WARA 301 (missing).
- **Use:** Could be the fallback when AWC answers 429 or 5xx. Archiving the cycle files hourly would build our own METAR history.
- **Effort:** S.

### L14. TROPOMI L2 SO2 on AWS Open Data (`meeo-s5p`, near-real-time granules as cloud-optimised GeoTIFFs) — CANDIDATE daily job
- **Gives:** Sentinel-5P SO2 per 5-minute granule as GeoTIFF (EPSG:4326, 0.035°, mol/m², 1 DU = 4.4615e-4 mol/m²) with a quality COG.
- **URL:** https://meeo-s5p.s3.amazonaws.com/?list-type=2&prefix=COGT/NRTI/L2__SO2___/2026/10/08/&max-keys=100
- **Licence:** the Copernicus legal notice: "users shall have a free, full and open access to Copernicus Sentinel Data"; credit "Contains modified Copernicus Sentinel data [Year]" (https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice). The registry says "No AWS account required" (https://registry.opendata.aws/sentinel5p/).
- **Access:** anonymous S3 over HTTPS. The Copernicus Data Space download needs a token (401), so AWS is the keyless route.
- **Verified:** 05:25–05:35Z, 25 granules listed for 10 Oct, with 2–4 MB COGs downloaded.
  - 8 Oct: at most 3.9 DU within 0.3° of Semeru.
  - 7 Sep, granule 05:51–05:56Z, quality above 0.5, 104–114°E and 11–4°S: SO2 above 5 DU over about 133,000 km² and above 10 DU over about 17,500 km², with a peak of 55.0 DU at 111.65°E 6.11°S.
  - On 7 Sep the Krakatau pixel, at the swath edge, read about 4.4 DU.
- **Use:** Could run once a day after the overpass. It would compute the highest DU within 50 km of each vent and emit an evidence chip ("TROPOMI SO2 14 DU, 06:10Z"), with the object key and ETag as provenance. SO2 is not ash, and it never shrinks anything. Map rendering can stay on GIBS (M2).
- **Effort:** M.

### L15. MIROVA near-real-time volcanic radiative power — CANDIDATE chip; non-commercial, no alteration
- **Gives:** the latest MODIS and VIIRS hot-spot detections with radiative power (MW) for 176 volcanoes, all TEPHRA targets included, over a rolling ~12.6 h window. It also has per-volcano charts.
- **URL:** https://www.mirovaweb.it/NRT/latest.php
- **Licence:** "Free to copy, share, and quote for non-commercial purposes with appropriate attribution to MIROVA. Not permitted to alter, transform, or use for commercial purposes without explicit permission." (https://www.mirovaweb.it/NRT/credits.php)
- **Access:** keyless HTML; robots.txt 404.
- **Verified:** 05:36Z, 528 rows from 9 Oct 14:54Z to 10 Oct 03:30Z. Examples: Semeru 8.06 MW at 18:36Z on 9 Oct (VIIRS 375 m); Lewotobi 23.48 MW at 00:25Z on 10 Oct; Ibu 37.63 MW at 17:12Z on 9 Oct.
- **Use:** Could show a quoted chip ("MIROVA VRP 8 MW, VIIRS 375 m, 18:36Z"). Never re-plot the data, and never feed it to geometry or scoring. Thermal activity is not ash.
- **Effort:** S.

### L16. MOUNTS per-volcano SO2 mass — CANDIDATE chip; non-commercial
- **Gives:** daily TROPOMI SO2 mass in tonnes per volcano since 2020, for 93 targets (all TEPHRA volcanoes except Suwanosejima). Semeru has 2,216 points from 2020-10-07: 376.4 t on 8 Oct and 166.2 t on 9 Oct.
- **URL:** http://www.mounts-project.com/timeseries/263300
- **Licence:** "permission to freely copy, share and quote for non-commercial purposes, with attribution to MOUNTS and ESA as the original source" (http://www.mounts-project.com/about)
- **Access:** HTTP only, so it must be fetched server side.
- **Verified:** 06:00Z, Semeru page 200.
- **Use:** Could give a cheap daily SO2 figure for any replay date since 2020. L14 stays the licence-clean primary.
- **Effort:** S.

### L17. Himawari HSD on Google Cloud Storage (`gs://noaa-himawari9`, `gs://noaa-himawari8`) — CANDIDATE
- **Gives:** the same HSD files and keys as the AWS bucket TEPHRA's science module reads. Himawari-9 runs from December 2022. Himawari-8 runs 2015–2022 as whole-disk files of about 25 MB per band per slot.
- **URL:** https://storage.googleapis.com/noaa-himawari9/AHI-L1b-FLDK/2026/10/10/0520/HS_H09_20261010_0520_B13_FLDK_R20_S0610.DAT.bz2
- **Licence:** no GCS-specific page was found, so the NOAA registry text applies: "NOAA and JMA request attribution for the use or dissemination of unaltered data. However, it is not permissible to state or imply endorsement by or affiliation with NOAA or JMA." (https://registry.opendata.aws/noaa-himawari/)
- **Access:** keyless HTTPS; no gcloud needed.
- **Verified:** 05:33Z. The listing is 200. The 05:20Z slot was created at 05:32Z (B13 segment S0610: 2,903,609 B).
- **Use:** Could change the HSD base URL in `tephra/science` (science owner), so that Cloud Run reads inside Google Cloud. Pitch line: "raw Himawari-9 read from Google Cloud Storage".
- **Effort:** S.

### L18. NOAA GFS 0.25° (AWS `noaa-gfs-bdp-pds`, GCS `global-forecast-system`, NOMADS) — CANDIDATE licence-clean winds
- **Gives:** analyses and forecasts of u/v, temperature and heights at every pressure level, plus tropopause height. Single fields can be read by byte range through `.idx` files.
- **URL:** https://noaa-gfs-bdp-pds.s3.amazonaws.com/gfs.20260925/06/atmos/gfs.t06z.pgrb2.0p25.f000.idx ; https://storage.googleapis.com/global-forecast-system/
- **Licence:**
  - The registry says: "NOAA data disseminated through NODD are open to the public and can be used as desired. … NOAA requests attribution for the use or dissemination of unaltered NOAA data. However, it is not permissible to state or imply endorsement by or affiliation with NOAA." (https://registry.opendata.aws/noaa-gfs-bdp-pds/)
  - Earth Engine's GFS page says the data "are not subject to copyright and carry no restrictions on their subsequent use by the public".
- **Access:** keyless, with range requests. NOMADS keeps only 10 days.
- **Verified:** the 25 Sep 06Z f000 fields at (-8.00, 113.00) were decoded with a small numpy reader. At 700 mb the wind was toward 084° at 7.1 kt; at 600 mb, toward 126° at 13.4 kt. Both equal Open-Meteo's `gfs_global`. The GCS mirror holds the same object.
- **Use:** Could replace Open-Meteo where the non-commercial clause matters, for example in a product pitch. It could also feed an animated wind layer. It needs a GRIB2 decoder (cfgrib or eccodes).
- **Effort:** M.

### L19. ECMWF open data (AWS `ecmwf-forecasts`, GCS `ecmwf-open-data`) — CANDIDATE licence-clean winds
- **Gives:** IFS and AIFS 0.25° forecasts with u, v, t and gh at 14 levels (1000–10 hPa). JSON-lines `.index` files allow byte-range reads.
- **URL:** https://ecmwf-forecasts.s3.eu-central-1.amazonaws.com/?list-type=2&prefix=20260925/06z/ifs/0p25/oper/ ; https://storage.googleapis.com/ecmwf-open-data/
- **Licence:** "governed by the Creative Commons CC-BY-4.0 licence"; the data "may be redistributed and used commercially, subject to appropriate attribution" (https://www.ecmwf.int/en/forecasts/datasets/open-data).
- **Access:** keyless on both mirrors. The files are 136 MB, so use index-based range reads.
- **Verified:** listings are 200, and the index lists u/v at 600 and 700 hPa. Values were not decoded because of the over-download incident; the hunt cross-checked them through Open-Meteo's `models=ecmwf_ifs025` instead.
- **Use:** It answers a judge who asks about Open-Meteo's non-commercial terms. It is also a second model for the "which wind level" question.
- **Effort:** M.

### L20. NASA FIRMS 7-day South-East Asia CSV — CANDIDATE
- **Gives:** VIIRS NOAA-20 active-fire and thermal-anomaly points for the last 24 h, 48 h or 7 days.
- **URL:** https://firms.modaps.eosdis.nasa.gov/data/active_fire/noaa-20-viirs-c2/csv/J1_VIIRS_C2_SouthEast_Asia_7d.csv
- **Licence:** "NASA promotes full and open sharing of data"; cite as "NASA FIRMS" (https://www.earthdata.nasa.gov/data/tools/firms/faq).
- **Access:** the CSV needs no key; the API and WMS GetMap need a MAP_KEY. With a bad key the WMS returns HTTP 200 with an error picture, so a poller that trusts the status code fails silently.
- **Verified:** 05:38Z, HEAD 200, 8,087,100 B.
- **Use:** Could back-fill 7 days of hot spots when a replay is recorded. Older dates come from M3.
- **Effort:** S.

---

## 4. Replay archives

### R1. IEM NOAAPort raw-text archive — IN BUILD (`scripts/record_replay.py noaaport`)
- **Gives:** the full NOAAPort text stream as one tar per day, with one member per hour. It includes:
  - Jakarta FIR VA SIGMETs (WVID20 WIII), Ujung Pandang ones (WVID21 WAAA) and Melbourne FIR ones (WVAU01 YMMC);
  - Darwin, Washington, Wellington and Toulouse VAAs (FV*);
  - Indonesian METAR bulletins;
  - CNL SIGMETs.
- **URL:** https://mesonet-longterm.agron.iastate.edu/archive/raw/noaaport/2026/ (for example `20260906.tgz`)
- **Licence:** "The materials found on this website are in the public domain and may be used freely by anyone for any lawful purpose." and "Attributing the Iowa Environmental Mesonet of Iowa State University would be appreciated." (https://mesonet.agron.iastate.edu/disclaimer.php). The bulletins come from BMKG, BoM and other agencies, so credit those originators too.
- **Access:** keyless.
  - Each day file is 283–310 MB of plain gzip, so it must be read from byte 0.
  - A day's file appears around 10:05Z the next day.
  - The main IEM host's robots.txt sets `Crawl-delay: 120`.
- **Verified:** 05:39–05:47Z. The listing (281 daily files to 8 Oct) is 200. 49.7 MB of `20260906.tgz` decompressed to 6 Sep 00:00–04:01Z and held 52 VA bulletins, among them:
  - 'WVID20 WIII 060034 / WIIF SIGMET 01 VALID 060035/060335 … MT KRAKATAU … SFC/FL200 MOV E 10KT NC AND … SFC/FL500 MOV W 30KT NC=';
  - WIIF SIGMET 02, and WIIF SIGMET 03 ('CNL SIGMET 27 052035/062235');
  - YMMM SIGMETs H07 and K01;
  - FVAU04 ADRM 060030 (Darwin 2026/183).

  HEAD requests are 200 for older event days back to 2016. Tokyo, RJJJ and RPHI bulletins are likely present but UNVERIFIED.
- **Use:** Now: the recorder streams a day and keeps the VA bulletins. Next:
  - Rebuild the 4–8 Sep Krakatau SIGMET leg (about 1.2 GB streamed) and store each bulletin under the live poller's URL with a "reconstructed" note. The same recipe works for Ruang 2024, Lewotobi 2024, Kanlaon 2024 and any SIGMET older than AWC's 30 days.
  - De-duplicate on whitespace-normalised text, because each bulletin arrives twice.
  - Parse CNL lines, and flag any validity over 6 hours: WIIF SIGMET 03 cancels a SIGMET 27 that ran for 26 hours.
  - BMKG's count of 39 SIGMETs from 4 Sep to the morning of 7 Sep (P2) is a completeness test.
  - Its FVAU copies of the Darwin VAAs are the publishable replacement for BoM's FTP files (R4).
- **Effort:** M.

### R2. IEM ASOS/METAR archive for international stations — CANDIDATE (replay, evaluation)
- **Gives:** raw METAR and SPECI history with no 30-day limit. The present-weather code VA or VCVA is an observer's report of ash at or near the airport.
- **URL:** https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?station=WIII&station=WIHH&station=WILL&station=WICC&station=WIIX&data=metar&year1=2026&month1=9&day1=4&hour1=12&year2=2026&month2=9&day2=9&hour2=0&tz=Etc%2FUTC&format=onlycomma&latlon=no&missing=M&trace=T&direct=no&report_type=3&report_type=4
- **Licence:** the IEM public-domain notice, as R1.
- **Access:** keyless CSV, with one request a second per IP (since 2026-04-21) and at most 1,000 station-years per request. Under load it answers 429 or 503.
- **Verified:** 05:48Z, 4–9 Sep, 588 METARs, 193 of them with VA.
  - Soekarno-Hatta (WIII): 69 VA reports from 5 Sep 18:30Z ('WIII 051830Z COR 03003KT 5000 HZ VA SCT018 27/23 Q1012 NOSIG') to 7 Sep 05:00Z; lowest visibility 4,500 m.
  - Radin Inten II (WILL): 74 reports from 5 Sep 18:00Z to 7 Sep 15:30Z; lowest visibility 2,900 m.
  - Halim (WIHH): 50 reports.
  - Kagoshima (RJFK): VA or VCVA on 15 Sep, 22–23 Sep and 8 Oct.
  - No VA at WARR, WADD, WAAA or WAMM in September.
  - A query for Manado (Ruang, 30 Apr 2024) also works.
- **Use:**
  - Replay: a "VA reported at CGK" chip and timeline.
  - Evaluation: did each official or TEPHRA area cover the airports that reported VA, and how early?
  - Live: the METARs TEPHRA already polls from AWC carry the same group. A VA chip may only widen the hazard to include the airport.

  A METAR without VA is not evidence of no ash.
- **Effort:** S.

### R3. NOAA NCEI GHCNh (hourly station data with the raw METAR) — EVAL
- **Gives:** hourly and half-hourly observations with the original METAR string in each row. For these stations it replaces ISD, which ends on 2025-08-24.
- **URL:** https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/access/by-year/2026/psv/GHCNh_IDU096749-1_2026.psv (Jakarta)
- **Licence:** "These data were produced by NOAA and are not subject to copyright protection in the United States. NOAA waives any potential copyright and related rights in these data worldwide through the Creative Commons Zero 1.0 Universal Public Domain Dedication (CC0-1.0)." (https://www.ncei.noaa.gov/metadata/geoportal/rest/metadata/item/gov.noaa.ncdc:C01688/xml)
- **Access:** keyless, with range requests; about a two-day lag.
- **Verified:** a 200 KB range of the Jakarta 2026 file held the same 69 VA METARs as IEM.
- **Use:** the citable CC0 source for the METAR-VA evaluation set, with IEM as the query tool.
- **Effort:** S.

### R4. BoM anonymous FTP: Darwin VAAC archive (texts `IDY41xxx`, graphics `IDY65xxx`) — PRIVATE USE ONLY
- **Gives:** every Darwin VAA since January 2022 as a dated text file, each paired with its four-panel volcanic ash graphic (PNG).
  - The 2026 tree is effectively live: `IDY41305.202610100407.txt` landed at 04:07Z, the same minute as the live `/fwo` slot.
  - The Krakatau set is complete: 2026/161–207, from 4 Sep 05:10Z to 9 Sep 23:00Z.
- **URL:** ftp://ftp.bom.gov.au/anon/gen/vaac/2026/ ; ftp://ftp.bom.gov.au/anon/gen/README
- **Licence:** "All products available via the anonymous FTP service are subject to the default terms of the Bureau's copyright notice: you may download, use and copy that material for personal use, or use within your organisation but you may not supply that material to any other person or use it for any commercial purpose. Users intending to publish Bureau data should do so as Registered Users." (https://www.bom.gov.au/catalogue/anon-ftp.shtml; re-checked against the hunt's saved copy). Each text ends with 'Copyright Commonwealth of Australia 2011, Bureau of Meteorology (ABN 92 637 533 532). Users of these web pages are deemed to have read and accepted the conditions described in the Copyright, Disclaimer, and Privacy statements'.
- **Access:** keyless anonymous FTP. Passive mode was flaky: 12 of 47 PNGs needed a retry. BoM's web pages forbid scraping and point automated users here.
- **Verified:** 05:17–06:25Z.
  - The 2026 listing has 9,373 entries: 4,687 texts and 4,686 PNGs.
  - The hunt downloaded 47 Krakatau texts and 47 PNGs with no sha256 mismatch.
  - Text files per year: 2,020 in 2022, 3,066 in 2023, 5,885 in 2024 and 5,672 in 2025.
  - Sample 2026/189: 'VA TO FL500 MOV SW, VA TO FL150 MOV SE … HIGH LEVEL VA TO FL500 IS DETACHED FROM THE VOLCANO AND MOVING SW'.
  - Ruang 2024 (2024/1–62, FL630) and Lewotobi November 2024 (2024/896–917, FL550) are present.
- **Use:**
  - Now: the research census holds 588 of these files, and the `semeru-20260923` replay holds 73, stored under tgftp URLs.
  - Could: privately evaluate Darwin's cadence and lag over 2022–2026.
  - Not allowed, without BoM's permission or Registered User status: the public repo, the public demo and video stills. Public replays should use the same bulletins as relayed by NWS tgftp or IEM NOAAPort (R1); those copies carry no BoM footer.
- **Effort:** S.

### R5. adsb.lol `globe_history` over HTTP (half-hour heatmaps, per-aircraft traces) — IN BUILD (heatmaps, in `scripts/record_replay.py`)
- **Gives:** every aircraft adsb.lol saw worldwide, at 10-second sampling.
  - `heatmap/NN.bin.ttf`: one gzip file per UTC half-hour (9–29 MB), made of 16-byte records (hex, lat, lon, barometric altitude in 25-ft steps, ground speed) plus callsign records.
  - `traces/…/trace_full_<hex>.json`: one full-day track per aircraft with every readsb field.
- **URL:** https://adsb.lol/globe_history/2026/09/25/heatmap/22.bin.ttf ; https://github.com/adsblol/globe_history_2026
- **Licence:** "This database is made available under the Open Database License: http://opendatacommons.org/licenses/odbl/1.0/." (release body)
- **Access:** keyless; no robots.txt; limits "dynamic". Fetch a few files per case and cache them; never fetch from the per-tick poller. Most January–August 2026 dates return 404 on the website, but GitHub has every day (R6).
- **Verified:** 04:50–05:10Z.
  - Heatmap 22 for 25 Sep (17,913,727 B) decoded to 1,265,496 records and 13,886 aircraft. 30 were within 250 nm of Semeru; the nearest was 115 nm away.
  - Heatmap 22 for 6 Sep is 200.
  - HEAD returns 200 for every replay-case date checked back to 2024-04-17.
- **Use:**
  - Now: `scripts/record_replay.py` decodes the heatmaps and rebuilds point-API answers for a case window. Heatmaps carry no aircraft type, registration or selected altitude.
  - Next: take aircraft types from the trace files, and drop `r`.
  - Evaluation: compare per-flight exposure with what aircraft actually flew (Krakatau 5–7 Sep, Taal 8 Oct).
  - Derived replay files stay ODbL, with the credit "adsb.lol (ODbL 1.0)".
- **Effort:** M.

### R6. adsb.lol `globe_history` GitHub releases read by byte range — CANDIDATE fallback
- **Gives:** the same daily archive as a split ustar tar of 3.5–4.2 GB. The traces come first (about 77% of the bytes, with no index); the 48 heatmaps sit in the last ~886 MB.
- **URL:** https://github.com/adsblol/globe_history_2026/releases/tag/v2026.09.25-planes-readsb-prod-0
- **Licence:** ODbL 1.0 (release body).
- **Access:** release URLs redirect to signed URLs valid for about an hour, which answer Range requests with 206.
- **Verified:** an index built from about 5.6 MB of range probes located heatmap 22 at `.tar.ab` bytes 1,295,288,832–1,313,202,558; it is byte-identical to the website copy. The latest release, `v2026.10.09`, was published on 10 Oct at 03:25Z.
- **Use:** fall back here when the website returns 404. Per-aircraft traces cannot be found cheaply this way.
- **Effort:** S.

### R7. Open-Meteo Historical Forecast API — IN BUILD (evaluation and replay recording)
- **Gives:** archived hourly model winds, plus temperature, humidity and geopotential, at 1000–30 hPa for any point and past date. The response has the same shape as the live call, and several models can be asked side by side.
- **URL:** https://historical-forecast-api.open-meteo.com/v1/forecast?latitude=-8.108&longitude=112.922&start_date=2026-09-25&end_date=2026-09-25&hourly=wind_speed_200hPa,wind_direction_200hPa,wind_speed_300hPa,wind_direction_300hPa,wind_speed_500hPa,wind_direction_500hPa,wind_speed_700hPa,wind_direction_700hPa&wind_speed_unit=kn&timezone=GMT
- **Licence:**
  - "API data are offered under Attribution 4.0 International (CC BY 4.0)"; "You must include a link next to any location Open-Meteo data are displayed, for example: Weather data by Open-Meteo.com" (https://open-meteo.com/en/licence).
  - "You may only use the free API services for non-commercial purposes" (https://open-meteo.com/en/terms, research/05).
  - For commercial use, the historical APIs "require the Professional API Plan or higher" (https://open-meteo.com/en/pricing).
- **Access:** keyless, with 600 calls a minute, 5,000 an hour, 10,000 a day and 300,000 a month. A request with more than 10 variables counts as extra calls; TEPHRA's live call has 18, about 1.8 calls.
- **Verified:** 05:17Z.
  - Semeru, 25 Sep 11:00Z: 700 hPa from 242° at 13.6 kt; 500 hPa from 217° at 6.5 kt.
  - For 23–27 Sep, ECMWF IFS, GFS, ICON, JMA GSM and ECMWF AIFS all give 600 hPa toward SE/ESE and 700 hPa toward ENE/E.
  - History starts on 2016-01-01; a request for Kelut 2014 returns 400.
- **Use:**
  - Now: winds for the ash cases of the Plume Reader evaluation (`scripts/make_plume_cases.py`; fixture `tests/fixtures/ops_evals/open_meteo_historical_taal_20261008T14.json`), and replay winds (`scripts/record_replay.py`, `historical_wind_url`).
  - Could: pin `models=` so recorded cases are reproducible, and add geopotential height so VONA heights in metres match real levels. The cone may take the union of 3–4 models' directions (widen only).
  - Wherever the data are shown, put "Weather data by Open-Meteo.com" beside them.
- **Effort:** S.

### R8. AWC METAR and TAF history (30 days) — record now
- **Gives:** past METARs and TAFs for the last 30 days. It is the only keyless, crawl-permitted source found for Indonesian TAF history.
- **URL:** https://aviationweather.gov/api/data/taf?ids=WARR&format=raw&date=20260925_1200
- **Licence:** the NWS public-domain notice.
- **Access:** keyless; 100 requests a minute; history limited to 30 days.
- **Verified:** TAF WARR for 25 Sep 12Z is 200. TAF WIII for 6 Sep is 400: "Data is available for up to 30 days for date".
- **Use:** record the Semeru 23–27 Sep TAFs before about 23–27 Oct, and the Taal 8 Oct TAFs before about 7 Nov, with `scripts/record_replay.py`. The Krakatau 5–7 Sep TAFs are already gone; use the METAR archive (R2) for that case.
- **Effort:** S.

### R9. ARCO-ERA5 on Google Cloud (`gcp-public-data-arco-era5`) — EVAL
- **Gives:** ERA5/ERA5T reanalysis, hourly, 0.25°, 37 levels, from 1940 to about a week ago. ERA5T reached 2026-10-02 at the time of checking.
- **URL:** https://storage.googleapis.com/gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3/.zattrs
- **Licence:** "Yes, you can use our ERA5 data according to the terms of the Copernicus license" and "Commercial users, please be sure to provide acknowledgement to the Copernicus Climate Change Service" (https://github.com/google-research/arco-era5).
- **Access:** keyless HTTPS. Point reads are heavy: 84 MB per hour per variable in Zarr, or about 45 MB per day per level in NetCDF.
- **Verified:** `.zattrs` 200. A 64 KB range of the 25 Sep 700 hPa NetCDF returned 206 with the HDF5 signature. No values were decoded, because of the size cap.
- **Use:** run offline (Colab, or a Cloud Run job). It can score which level and model best matched each VAA and SIGMET movement, including cases before 2016 such as Kelut 2014. It is the only keyless pressure-level source before 2016. Pitch: "reanalysis from Google Cloud's public ERA5".
- **Effort:** L.

---

## 5. Map layers and static reference files

### M1. NASA GIBS: Himawari-9 tiles (Band 13 IR, Band 3 visible, Air Mass RGB) — IN BUILD (CSP host added)
- **Gives:** Web Mercator 256-px PNG tiles every 10 minutes.
  - `Himawari_AHI_Band13_Clean_Infrared` (z0–6, about 2 km).
  - `Himawari_AHI_Band3_Red_Visible_1km` (z0–7).
  - `Himawari_AHI_Air_Mass` (z0–6).

  GIBS has no Himawari ash or dust RGB.
- **URL:** https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/Himawari_AHI_Band13_Clean_Infrared/default/{TIME}/GoogleMapsCompatible_Level6/{z}/{y}/{x}.png
- **Licence:**
  - GIBS: "NASA promotes full and open sharing of data". It requests: "We acknowledge the use of imagery provided by services from NASA's Global Imagery Browse Services (GIBS), part of NASA's Earth Science Data and Information System (ESDIS)." (https://nasa-gibs.github.io/gibs-api-docs/)
  - Earthdata: "Non-NASA data available through the ESDIS project is subject to the license arrangements of the sponsoring organization."
  - Himawari is JMA data, so the NOAA/JMA attribution and no-endorsement terms apply.
  - Credit: "Imagery: NASA GIBS; Himawari-9 data: JMA via NOAA".
- **Access:** keyless, CORS `*`. The tiles send `no-store`, so every viewer fetches from GIBS. Missing and future times return 404.
- **Verified:** 05:17–05:20Z.
  - Capabilities 200.
  - Band 13 tiles over Java for 25 Sep 15:00Z, for 10 Oct 04:40Z and for 7 Sep 06:00Z (the Krakatau day) are all 200. So are Band 3 and Air Mass.
  - `default` lagged about 40–50 minutes behind.
  - The Band 13 colour map has 237 one-degree bins with no repeated colour, and about 97% of pixels decode to a temperature.
  - The archive is solid from March 2022, with gaps: none for July–September 2024, and 2026-09-15 09:50–18:10Z is missing.
- **Use:** one raster source per band at about 0.6 opacity, below the official fill. Floor the active clock to 10 minutes, so REPLAY lines up, and fall back one slot on 404. Show the frame time and the label "context only; not ash detection". The Band 13 pixels could also be decoded into an approximate cloud-top temperature chip (this is not a BTD).
- **Effort:** S.

### M2. NASA GIBS: SO2 layers (TROPOMI, OMPS, OMI, AIRS, MLS) and aerosol index — CANDIDATE; corrects research/05
- **Gives:**
  - TROPOMI: `TROPOMI_L2_Sulfur_Dioxide_Total_Vertical_Column` (DU, daily, 2018-05-06 to 2026-10-09).
  - OMPS: `OMPS_NOAA20_SO2_*` from 2024-10-31 and `OMPS_SO2_*` from 2012.
  - Others: `OMI_SO2_*`, `AIRS_Prata_SO2_Index_*`, `MLS_SO2_147hPa_*`, and the OMPS and OMI aerosol index.
- **URL:** https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/TROPOMI_L2_Sulfur_Dioxide_Total_Vertical_Column/default/{YYYY-MM-DD}/GoogleMapsCompatible_Level6/{z}/{y}/{x}.png
- **Licence:** the GIBS acknowledgement, as M1. TROPOMI is Copernicus data. The legal notice allows "(a) reproduction; (b) distribution; (c) communication to the public; (d) adaptation, modification and combination". It requires "'Copernicus Sentinel data [Year]'" or, if modified, "'Contains modified Copernicus Sentinel data [Year]'".
- **Access:** as M1.
- **Verified:**
  - Tiles over Java for 6 and 7 Sep and for 8 and 9 Oct are 200.
  - The 7 Sep tile shows SO2 south of western Java, which matches L14.
  - Worldview snapshots for Krakatau (6 Sep 2026), Ruang (30 Apr 2024) and Lewotobi (7 Nov 2024) show clear SO2 plumes.
  - research/05 §3.12 said GIBS had "no TROPOMI SO2 layer". The layer exists; its identifier says "Sulfur_Dioxide", not "SO2".
- **Use:** a toggle "SO2 (TROPOMI, daily)" with its DU legend. Its time is the replay date, or yesterday for live. Pair it with M1 in the 7 Sep replay. SO2 is not ash. The layer is about a day behind, has swath gaps, and saturates at 32 DU.
- **Effort:** S.

### M3. NASA GIBS thermal anomalies as vector tiles (EPSG:4326) — CANDIDATE, server side
- **Gives:** daily FIRMS hot-spot points with full attributes (FRP, brightness, time, confidence) for any day back to 2012 (S-NPP), 2020 (NOAA-20) or 2000 (MODIS), without a MAP_KEY.
- **URL:** https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/VIIRS_NOAA20_Thermal_Anomalies_375m_All/default/{YYYY-MM-DD}/500m/{z}/{row}/{col}.mvt
- **Licence:** the GIBS acknowledgement; FIRMS asks for the credit "NASA FIRMS".
- **Access:** keyless. The EPSG:3857 versions return 404 at every zoom, so the tiles must be decoded server side.
- **Verified:** tiles for 8 Oct, z2–z6, are 200. The decoder found 20 points, two of them at Semeru (FRP 0.49 and 4.88 MW).
- **Use:** hot-spot evidence chips and map circles for any replay date. Hot spots are not ash.
- **Effort:** M.

### M4. NASA GIBS polar-orbiter layers (VIIRS and MODIS true colour, Day/Night Band, Black Marble) — CANDIDATE
- **URL:** https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_NOAA20_CorrectedReflectance_TrueColor/default/{YYYY-MM-DD}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg
- **Licence:** NASA-mission data are CC0; credit GIBS.
- **Access:** keyless; CORS `*`. Polar orbiters pass once or twice a day, with swath gaps.
- **Verified:** VIIRS NOAA-20 true colour over Java for 8 Oct is 200.
- **Use:** a daily true-colour toggle for the replay date. The 7 Sep VIIRS scene of the Sunda Strait could be used in the video.
- **Effort:** S.

### M5. JMA bosai Himawari tiles (dated XYZ Web Mercator) — CANDIDATE
- **Gives:** JMA's own renderings as XYZ JPEG tiles: Band 13, Dust RGB, true colour, B03, B08 and Sandwich. The full disk comes every 10 minutes (z0–5, about 5 km per pixel over Indonesia) and Japan every 2.5 minutes (z0–6). JMA publishes no Ash RGB.
- **URL:** https://www.jma.go.jp/bosai/himawari/data/satimg/targetTimes_fd.json ; https://www.jma.go.jp/bosai/himawari/data/satimg/{basetime}/fd/{validtime}/DST/ETC/{z}/{x}/{y}.jpg
- **Licence:** JMA Public Data License 1.0. Credit "Source: Japan Meteorological Agency website (URL)", and say so when the content is edited (https://www.jma.go.jp/jma/en/copyright.html).
- **Access:** keyless and undocumented; CORS `*`; about 36 hours of slots.
- **Verified:** 05:36Z. The time list (211 slots) is 200, and three products for the 05:30Z slot were online by 05:35Z. Volcano positions projected with Web Mercator land on the islands.
- **Use:** a georeferenced live layer that could replace the side-strip JMA frames (`bbox=None` today). Replays must save the tiles when they are recorded. Label it "Dust RGB (JMA)", not ash.
- **Effort:** S.

### M6. SSEC RealEarth "RGB Volcanic Ash" tiles — CANDIDATE through a backend proxy
- **Gives:** the only verified Web Mercator Ash RGB tile layer (`HIMAWARI-ash`), plus Band 13, dust, true colour and air mass.
- **URL:** https://realearth.ssec.wisc.edu/tiles/HIMAWARI-ash/{z}/{x}/{y}.png
- **Licence:** "Public use of the data visualizations of RealEarth through its websites, devices, and API is freely available"; credit "Source: SSEC RealEarth, UW-Madison" (https://www.ssec.wisc.edu/realearth/terms-of-use). The watermark policy says "The volume threshold for anonymous users is 500 megapixels per 24 hour rolling window" and "Requests from unregistered websites are blocked" (https://realearth.ssec.wisc.edu/doc/watermarks.php).
- **Access:** keyless within the threshold; CORS `*`. robots.txt disallows `/api/` but allows `/tiles/`. Tiles are kept 1–3 days.
- **Verified:** about 05:50Z: the latest and 10 Oct 05:00Z tiles are 200; tiles from 7 Oct and earlier are 404.
- **Use:** a live Ash RGB toggle served by a small TEPHRA proxy that caches one fetch per tile per slot (about 113 megapixels a day, under the threshold). The alternative is for the user to register. Not for replays.
- **Effort:** S.

### M7. CIRA RAMMB SLIDER (Ash RGB, JMA SO2 RGB, split-window difference) — CANDIDATE evidence frames; licence unclear
- **Gives:** Himawari-9 full disk every 10 minutes as 688-px tiles in geostationary projection, with Ash RGB, JMA's Volcanic Emissions (SO2) RGB and the 10.3–12.3 µm split-window difference. Continuous from 2026-08-10.
- **URL:** https://slider.cira.colostate.edu/data/json/himawari/full_disk/eumetsat_ash/latest_times.json
- **Licence:** no reuse licence was found. The only terms are the CIRA Experimental Products Disclaimer: "All CSU CIRA products are considered experimental products. … provided strictly 'as-is'" and "Any users of this product shall hold harmless and indemnify Colorado State University…" (https://rammb2.cira.colostate.edu/resources/experimental_products_disclaimer/). The footer credits "SLIDER by RAMMB / CIRA @ CSU".
- **Access:** keyless; no CORS; robots.txt 404.
- **Verified:** 05:25Z. The tile from Krakatau to Semeru is 200 for 25 Sep 15:00Z, 10 Oct 05:00Z and 7 Sep 06:00Z; Java was clear in the Ash RGB. The split-window and SO2 RGB tiles for 25 Sep 15:00Z are 200.
- **Use:** a server-side evidence frame, both for the side strip and as a Gemini image input, instead of NICT tiles. The evaluation could also compare TEPHRA's BTD with SLIDER's split-window frame. Credit CIRA, and do not redistribute in bulk.
- **Effort:** M.

### M8. EUMETView Geo Ring Ash RGB (WMS, 3-hourly since 2021) — CANDIDATE for older replays; licence unconfirmed
- **URL:** https://view.eumetsat.int/geoserver/ows?service=WMS&version=1.3.0&request=GetMap&layers=mumi:wideareacoverage_rgb_ash&styles=&crs=EPSG:3857&bbox={bbox-epsg-3857}&width=256&height=256&format=image/png&time={ISO}
- **Licence:** UNVERIFIED from a primary page, because the licensing page is a JavaScript app (403). Secondary sources say imagery older than about 3 hours is free with "(c) EUMETSAT (year)".
- **Access:** keyless; CORS `*`; 3-hourly, with about 3 hours' latency.
- **Verified:** capabilities 200 (from 2021-06-03T18:00Z, 3-hourly). GetMap over Java is 200 for 25 Sep 15:00Z, 10 Oct 03:00Z and 2024-04-17 15:00Z.
- **Use:** Ash RGB context for older replays that GIBS misses, such as Ruang 2024. Not live.
- **Effort:** S.

### M9. EOX Sentinel-2 cloudless basemap — OPTIONAL, non-commercial share-alike
- **URL:** https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2025_3857/default/g/{z}/{y}/{x}.jpg
- **Licence:** "EOxCloudless https://cloudless.eox.at by EOX IT Services GmbH (Contains modified Copernicus Sentinel data 2019) released under Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License."
- **Access:** keyless; CORS `*`.
- **Verified:** capabilities 200; the Semeru tile is 200 with CORS `*`.
- **Use:** an optional satellite basemap for close-ups and the video, with the CC BY-NC-SA credit. Not for a commercial pitch.
- **Effort:** S.

### M10. Mapterhorn terrain tiles (Copernicus GLO-30 in Terrarium WebP) — IN BUILD (CSP host added)
- **Gives:** a 512-px Terrarium-encoded WebP elevation model. It uses Copernicus GLO-30 for Indonesia and the Philippines and GSI elevation models for Japan, and goes to z12 over Semeru.
- **URL:** https://tiles.mapterhorn.com/{z}/{x}/{y}.webp ; https://tiles.mapterhorn.com/tilejson.json
- **Licence:**
  - TileJSON attribution: "<a href='https://mapterhorn.com/attribution'>© Mapterhorn</a>".
  - GLO-30 entry: "COPERNICUS full, free and open license", with producer "DLR e.V. 2010-2014, Airbus Defence and Space GmbH 2014-2018, provided under COPERNICUS by the European Union and ESA. All rights reserved." (https://download.mapterhorn.com/attribution.json)
  - The Japanese GSI data carry their own approval text.
  - The code is BSD-3.
- **Access:** keyless; CORS `*`; no stated limits and no SLA.
- **Verified:** TileJSON 200; the z12 Semeru tile is 200 (143,344 B) and z13 is 404; `attribution.json` 200 (151 sources). A decoded z8 tile reads 3,618 m near Semeru.
- **Use:** a subtle hillshade, and optional 3D close-ups. Do not combine 3D terrain with flight-level extrusions, because that shifts the levels.
- **Effort:** S.

### M11. AWS Terrain Tiles (Tilezen Terrarium) — fallback elevation
- **URL:** https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png
- **Licence:** "Attribution is required for many terrain tile data providers." The required lines include "United States 3DEP (formerly NED) and global GMTED2010 and SRTM terrain data courtesy of the U.S. Geological Survey." and "Global ETOPO1 terrain data U.S. National Oceanic and Atmospheric Administration" (https://github.com/tilezen/joerd/blob/master/docs/attribution.md).
- **Access:** keyless; static since 2017; CORS `*` when an Origin header is sent.
- **Verified:** the z12 Semeru tile is 200, with its highest pixel 3,668 m at (-8.1077, 112.9225) and about 38 m pixels. The z10 tile reads 3,651 m and the z8 tile 3,593 m.
- **Use:** fallback for M10, and an independent summit elevation (section 7.2, item 10).
- **Effort:** S.

### M12. NASA GIBS ASTER GDEM shaded relief — OPTIONAL
- **URL:** https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/ASTER_GDEM_Greyscale_Shaded_Relief/default/GoogleMapsCompatible_Level12/{z}/{y}/{x}.jpg
- **Licence:** the GIBS acknowledgement.
- **Access:** keyless; CORS `*`; maximum zoom 12.
- **Verified:** the Semeru tile is 200, with CORS `*`.
- **Use:** the simplest hillshade, with no elevation decoding; maximum z12.
- **Effort:** S.

### M13. OpenFreeMap styles and their built-in Natural Earth II relief — IN BUILD (basemap)
- **Gives:** style JSON (dark, fiord, positron, liberty, bright) and Noto Sans glyphs. Every style also defines an unused raster source, `ne2_shaded`: Natural Earth II shaded relief, z0–6.
- **URL:** https://tiles.openfreemap.org/styles/dark ; https://tiles.openfreemap.org/natural_earth/ne2sr/{z}/{x}/{y}.png
- **Licence:** openfreemap.org says "there are no limits on the number of map views or requests"; "Is commercial usage allowed?" "Yes"; "Attribution is required." The terms (9 Sep 2026) give no warranties and forbid any attempt to "collect data from the service in automated ways without permission". The map data are OpenStreetMap (ODbL).
- **Access:** keyless; no limits stated; CORS `*`; already allowed by the CSP.
- **Verified:** five style files are 200; glyphs are 200; the relief tile is 200 and shows Java's chain of volcanoes. The dark style's land and sea differ by only ΔE 4.2.
- **Use:**
  - Now: the Wall basemap.
  - Could: lift the water colour, and put the `ne2_shaded` relief under the `water` layer; neither needs a CSP change.
  - OpenFreeMap has no SLA, so keep the Natural Earth fallback (M20).
- **Effort:** S.

### M14. AWC GIS layers: VAAC areas and FIR polygons — IN BUILD (`tephra/web/data/firs.geojson`, `vaac_aor.geojson`)
- **Gives:** TopoJSON of the VAAC areas of responsibility (12 polygons) and 262 FIRs with ICAO codes, among them WIIF, WAAF, RPHI, RJJJ, YBBB, AYPM and WSJC.
- **URL:** https://aviationweather.gov/gis/vaac.json ; https://aviationweather.gov/gis/firpoly.topojson
- **Licence:** "The information on National Weather Service (NWS) Web pages are in the public domain, unless specifically noted otherwise" and "may be used without charge for any lawful purpose" (https://www.weather.gov/disclaimer).
- **Access:** keyless; no CORS header was seen, so the converted files are served from TEPHRA's own origin.
- **Verified:** HEAD 200 for both, last modified 8 Oct 2026 18:41Z. The WIIF, WAAF, WSJC and RPHI extents match VATSIM's.
- **Use:** Now: the Wall's FIR outlines and the seam between the Darwin and Tokyo areas. These replaced a VATSIM-derived file on 10 Oct, so no share-alike condition remains. Label them "approximate": they may predate the 2024 Jakarta/Singapore realignment. The Darwin and Tokyo polygons overlap at 10–20°N, so the issuing VAAC is always taken from the VAA header.
- **Effort:** done.

### M15. VATSIM vatspy-data-project FIR boundaries — REPLACED by M14
- **URL:** https://raw.githubusercontent.com/vatsimnetwork/vatspy-data-project/master/Boundaries.geojson
- **Licence:** LICENSE "Attribution-ShareAlike 4.0 International".
- **Access:** keyless (GitHub raw).
- **Verified:** 200 (1,219 features). A point-in-polygon test put each test volcano in the FIR that issues its SIGMETs: Semeru, Merapi, Lewotobi, Lewotolok, Ibu, Dukono and Ruang in WAAF; Krakatau in WIIF; Taal, Mayon and Kanlaon in RPHI.
- **Use:** none now; it is simulator data with a share-alike licence.
- **Effort:** none (not used).

### M16. OurAirports navaids and airports — IN BUILD (`tephra/web/data/navaids.geojson`, `data/airports.json`)
- **Gives:** 11,008 navaids worldwide: 216 in Indonesia (163 NDB, 52 VOR-DME, 1 TACAN), 57 in the Philippines and 219 in Japan. Also airports with a scheduled-service flag, and runways.
- **URL:** https://davidmegginson.github.io/ourairports-data/navaids.csv
- **Licence:** "All data is released to the Public Domain, and comes with no guarantee of accuracy or fitness for use." (https://ourairports.com/data/)
- **Access:** keyless (GitHub Pages, rebuilt nightly).
- **Verified:** HEAD 200 for the airports, runways and navaids files (rebuilt 10 Oct 01:53Z). The nearest navaids to Semeru are the Malang NDB (ML, 16 nm), the Lawang NDB (LW, 22 nm) and the Surabaya VOR-DME (SBR, 45 nm).
- **Use:**
  - Now: the airport catalogue and the navaid layer.
  - Could: let code, never the model, describe positions the way dispatchers do, for example "ASH AREA 40 NM SE SBR".
  - This is not AIRAC data, so label it "approximate".
- **Effort:** S.

### M17. SimAware TRACON boundaries — OPTIONAL
- **URL:** https://raw.githubusercontent.com/vatsimnetwork/simaware-tracon-project/main/Boundaries/WARR/WARR.json
- **Licence:** CC BY-SA 4.0 (GitHub licence field).
- **Access:** keyless (GitHub raw).
- **Verified:** WARR "Surabaya Radar" is 200.
- **Use:** an optional terminal-area layer. It is simulator data under share-alike.
- **Effort:** S.

### M18. FlightGear / Robin Peel airway file (`awy.dat`) — background only
- **URL:** https://gitlab.com/flightgear/fgdata/-/raw/next/Navaids/awy.dat.gz
- **Licence:** "This data is free software; you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation; either version 2 of the License, or (at your option) any later version."
- **Access:** keyless (GitLab raw).
- **Verified:** 200, data cycle 2013.10, with 1,662 segments in the Indonesia box.
- **Use:** at most a faint layer labelled "airways (2013 data, not current)". The planner rule stays: no reroute waypoints. Shipping a derived file carries GPL obligations.
- **Effort:** S.

### M19. BNPB InaRISK volcanic hazard index — OPTIONAL
- **URL:** https://gis.bnpb.go.id/server/rest/services/inarisk/INDEKS_BAHAYA_GUNUNGAPI/ImageServer?f=json
- **Licence:** "Peta dan informasi yang termuat di dalam website ini dapat disebarluaskan dalam format lain baik dalam bentuk berkas digital maupun cetakan." (may be disseminated digitally or in print) (https://inarisk.bnpb.go.id/disclaimer)
- **Access:** keyless ArcGIS REST; robots.txt does not forbid it.
- **Verified:** metadata and an image export around Semeru and Bromo are 200.
- **Use:** a faint, labelled ground-hazard overlay. It must never enter the airborne-ash logic. The data are from 2015.
- **Effort:** S.

### M20. Natural Earth 1:50m countries — IN BUILD (`tephra/web/data/land_apac.geojson`, offline fallback)
- **URL:** https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson
- **Licence:** "All versions of Natural Earth raster + vector map data found on this website are in the public domain." (https://www.naturalearthdata.com/about/terms-of-use/)
- **Access:** keyless; bundled as a static file.
- **Verified:** the GeoJSON is 200 (3,083,490 B); a 231 KB subset of 26 Asia-Pacific countries was made from it.
- **Use:** if the OpenFreeMap style fails to load, TEPHRA's layers still have land under them.
- **Effort:** done.

### M21. VersaTiles dark styles — OPTIONAL alternative basemap
- **URL:** https://tiles.versatiles.org/assets/styles/colorful-dark/style.json
- **Licence:** style code MIT; "Iconsets and Rendered Spritemaps: CC0 1.0 Universal". The public server publishes no terms.
- **Access:** keyless; CORS `*`; no published terms or SLA.
- **Verified:** styles and tiles are 200 with CORS `*`. The colorful-dark land and sea differ by ΔE 11.6.
- **Use:** a fallback or A/B basemap. Its font names differ from OpenFreeMap's.
- **Effort:** S.

### M22. OSMF Shortbread vector tiles — not for the demo
- **URL:** https://vector.openstreetmap.org/shortbread_v1/tilejson.json
- **Licence (usage policy):** "Clearly display license attribution"; "They have strictly limited capacity"; access "may be withdrawn at any point" (https://operations.osmfoundation.org/policies/vector/).
- **Access:** keyless, but requests need a valid User-Agent and Referer; capacity is limited.
- **Verified:** TileJSON 200 (tiles to z14).
- **Use:** none planned.
- **Effort:** —

### M23. Smithsonian GVP Volcanoes of the World (GeoServer WFS) — IN BUILD (`data/volcanoes.json`)
- **Gives:** 1,214 Holocene volcanoes, 11,089 Holocene eruptions and 2,248 eruptions since 1960, as JSON or CSV with filters.
- **URL:** https://webservices.volcano.si.edu/geoserver/GVP-VOTW/ows?service=WFS&version=2.0.0&request=GetCapabilities
- **Licence:**
  - GVP citation page (Wayback copy, 2026-07-25): "The Smithsonian invites visitors to use its online content for personal, educational, and other non-commercial purposes. The database compilation, Bulletin of the Global Volcanism Network, and Smithsonian / USGS Weekly Volcanic Activity Report are products of employees of the United States".
  - Terms page (Wayback copy, 2026-07-09): "(2) the Content was never eligible for copyright protection because it was created by an employee of the United States as part of his or her official duties".
  - The WFS declares `Fees NONE` and `AccessConstraints NONE`.
  - Cite: Global Volcanism Program, 2025. Volcanoes of the World (v. 5.3.x). https://doi.org/10.5479/si.GVP.VOTW5-2025.5.3
- **Access:** keyless WFS. The main volcano.si.edu site served a Cloudflare "temporarily unavailable" page for at least two days.
- **Verified:** capabilities 200. The service returned 111 eruptions since 1960 for 11 TEPHRA volcanoes. Elevations: Semeru 3,657 m, Taal 311 m, Ibu 1,357 m, Dukono 1,273 m, Lewotolok 1,431 m, Krakatau 285 m. There is no Anak Krakatau eruption record after 2024-02-20, because the data run to about 25 Mar 2026. The emissions layer is broken.
- **Use:**
  - Now: the volcano catalogue.
  - Could: add "erupting since" and the highest VEI to the map tooltips.
  - Do not cite GVP for the 2026 Krakatau eruption.
- **Effort:** S.

### M24. VRS standing data (callsign routes, airlines, ICAO aircraft types, ICAO address blocks) — CANDIDATE
- **Gives:**
  - callsign routes, for example GIA402 → WIII–WADD;
  - airline names;
  - 2,857 ICAO type designators with engine count, engine type and wake class;
  - ICAO 24-bit address blocks by country.

  adsb.lol mirrors the routes as one JSON file per callsign.
- **URL:** https://github.com/vradarserver/standing-data ; https://vrs-standing-data.adsb.lol/routes/GI/GIA402.json
- **Licence:** CC0 1.0 ("Creative Commons Zero v1.0 Universal").
- **Access:** keyless (GitHub raw). The adsb.lol mirror sits behind Cloudflare with CORS `*`.
- **Verified:**
  - Route files for 10 Indonesian carriers are 200, and 3,680 routes resolve against OurAirports.
  - The data covered 22 of 23 Indonesian-carrier callsigns seen near Semeru, and 5 of 5 spot checks matched the observed climbs and descents.
  - The adsb.lol mirror is about three weeks behind.
- **Use:** copy the carrier route files, airlines, aircraft types and address blocks into `data/` with a CC0 note (feeds-geo owner). This would let TEPHRA:
  - show "Garuda Indonesia GA402 CGK→DPS" on desk cards;
  - give the planner each flight's destination;
  - generate the fuel categories from the type table. That also fixes `PA28` and `E175` in `tephra/geo/fuel.py`, which are not ICAO designators (the real ones are P28A, P28B, P28R, E75L and E75S).

  Label routes "route per VRS standing data (CC0), not a filed flight plan".
- **Effort:** S.

### M25. JMA multilingual dictionary — CANDIDATE (UI)
- **URL:** https://www.data.jma.go.jp/developer/jma_multilingual.xlsx
- **Licence:** follow the JMA website terms (Public Data License 1.0).
- **Access:** keyless spreadsheet (2 MB).
- **Verified:** 200 (updated 2026-03-26), about 7,300 rows with English, Indonesian and Tagalog columns.
- **Use:** translate JMA terms (directions, alert-level names) from the dictionary rather than asking Gemini.
- **Effort:** S.

### M26. Copernicus DEM GLO-30 (cloud-optimised GeoTIFFs on AWS) — EVAL
- **URL:** https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_S09_00_E112_00_DEM/Copernicus_DSM_COG_10_S09_00_E112_00_DEM.tif
- **Licence:** "GLO-30 Public and GLO-90 are available on a free basis for the general public under the terms and conditions of the Licence" (https://registry.opendata.aws/copernicus-dem/)
- **Access:** anonymous S3; the files need a GeoTIFF reader.
- **Verified:** HEAD 200 (17.5 MB); not downloaded.
- **Use:** a one-off script that stores an independent summit elevation for each volcano.
- **Effort:** M.

---

## 6. Evaluation sets

### E1. Tokyo VAAC yearly archive lists, 2006–2026 — EVAL
- **Gives:** an index of every Tokyo VAA per year, with links to the text and to the VAG, VAGI and VAGFN graphics. 2024 has 1,153 advisories, 2025 has 1,733 and 2026 so far has 1,758; 2014 has 1,347 (text only).
- **URL:** https://ds.data.jma.go.jp/svd/vaac/data/Archives/2024_vaac_list.html
- **Licence:** JMA Public Data License 1.0: "The user must cite the source when using the Content."
- **Access:** keyless HTML (0.7–1.1 MB per year); no robots.txt.
- **Verified:** 06:08–06:12Z, the 2014, 2024, 2025 and 2026 lists are 200; `archive.js` lists 2006–2026.
- **Use:** a Japan and Philippines evaluation set. Examples: Sakurajima "not identifiable" advisories against JMA ground reports (E3), Kanlaon 2024 and Taal. Pair them with IEM SIGMETs (R1), and fetch at about one request a second.
- **Effort:** S.

### E2. Tokyo VAAC graphics and per-advisory Himawari loops — IN BUILD (evaluation); CANDIDATE (UI)
- **Gives:**
  - Graphics per advisory: the VAG (observed, +6, +12 and +18 h), the VAGI (initial) and the VAGFN. The VAGFN is hourly for 1–6 h in two layers, FL180–FL550 and SFC–FL180, with ATS routes drawn on.
  - A volcano-centred loop of 37 frames per channel (IR, true colour and Ash RGB; 668×501 px). Loops are kept about 30 days (10 Sep to 8 Oct when checked).
- **URL:** https://ds.data.jma.go.jp/svd/vaac/data/vaac_list.html ; https://ds.data.jma.go.jp/svd/vaac/data/VAGFN/2026/Images/20261008_27307000_0023_QH21_01.png ; https://ds.data.jma.go.jp/svd/vaac/data/Sat/2026/Script/20261008_27307000_0023_as.js
- **Licence:** JMA Public Data License 1.0. "If you have edited the Content for use, you must include a statement expressing that the Content has been edited".
- **Access:** keyless. The image paths are built from the list page's scripts and are undocumented; no robots.txt.
- **Verified:** 05:43–05:45Z. The VAG, the VAGI, the VAGFN (Taal, base time 14:20Z on 8 Oct, plume FL150) and an Ash RGB frame are all 200. Tokyo's page says it also issues VAAs in IWXXM, but no public copy was found.
- **Use:**
  - Now: the Plume Reader evaluation's image arm uses these labelled frames (`scripts/make_plume_cases.py`, `evals/plume`).
  - Could: show the official VAGFN panel beside TEPHRA's cone for Tokyo-area volcanoes, with "Source: JMA Tokyo VAAC".
  - Could: give Gemini 2–3 Ash RGB frames from the advisory's own loop instead of the coarse `se3` crops.

  Archive every frame used, because the loops expire.
- **Effort:** S.

### E3. JMA archive of past volcano information (eruption observation reports since 2014) — EVAL
- **Gives:** every eruption observation report per volcano as a small HTML page: time, plume height above the crater (m) with the height above sea level (FT), and direction. Sakurajima has 7,806 reports since January 2014.
- **URL:** https://www.data.jma.go.jp/vois/data/report/volinfo/volinfo.php?info=VG&id=506
- **Licence:** JMA Public Data License 1.0. Cite "Source: Japan Meteorological Agency website (URL)" and say when the content is edited.
- **Access:** keyless HTML pages of about 400 B; robots.txt is a 404.
- **Verified:** the index is 200 (1.2 MB, 7,806 links). One pair was checked:
  - JMA ground report, 7 Oct 00:21Z: '火口上1000m（海抜6800FT）流向：南' (1,000 m above the crater, 6,800 FT, moving south).
  - Tokyo VAA 2026/267: 'ERUPTED AT 20261007/0021Z FL070 EXTD S … VA NOT IDENTIFIABLE FM SATELLITE DATA'.
  - The next advisory, 2026/268, gave a polygon SFC/FL070 MOV S.
- **Use:** a labelled set of "the ground sees it, the satellite cannot" cases, the mirror image of Semeru's night "not observed". It tests that "not identifiable" is never a CONFLICT, and it could give the pitch a measured rate. Back-fill slowly, about one request a second.
- **Effort:** M.

### E4. USGS HANS public API (VONAs in the 2026 ICAO format) — EVAL
- **Gives:** real VONAs as TAC text and as structured JSON (cloud-height option, height source, movement, colour code), plus a dump of every notice since 2006: 765 VONAs since 2008.
- **URL:** https://volcanoes.usgs.gov/hans-public/api/notice/getVonasWithinLastYear ; https://volcanoes.usgs.gov/hans-public/api/research/dataDump
- **Licence:** US federal works: "Copyright protection under this title is not available for any work of the United States Government" (17 U.S.C. §105). The USGS copyright page itself returned a WAF challenge and was not read.
- **Access:** keyless; CORS `*`; no published rate limit.
- **Verified:** 05:16Z: 99 VONAs from 2025-10-18 to 2026-10-06, and a 1.66 MB dump of 3,799 notices. Three traps:
  - The text prints 'VA CLD HGT: 0FT AMSL' when the structured field says 'NO VA CLD PRODUCED'.
  - AVO issues GREEN VONAs that still report resuspended ash to 6,000 ft.
  - The contact field holds staff names, emails and phone numbers. Strip it.
- **Use:** a regression corpus for a parser built on the ICAO VONA template. It includes negative phrases that must never shrink the hazard. US volcanoes only.
- **Effort:** S.

### E5. ICAO VONA template (PANS-MET Appendix 7, Table A7-1) and the WOVO 2025 observatory survey — specification and pitch
- **URL:** https://wovo.iavceivolcano.org/content/uploads/sites/20/2026/02/vona_format_pans-met_july2025.pdf ; https://wovo.iavceivolcano.org/content/uploads/sites/20/2026/02/survey_results_10nov2025.pdf
- **Licence:** reference only. The text is ICAO PANS-MET; the WOVO site says "Copyright © 2026 The World Organization of Volcano Observatories".
- **Access:** keyless PDFs; robots.txt disallows only the WordPress admin.
- **Verified:** both PDFs 200. The survey reports "Via email: 25, Via website: 8, Via telegram: 1, Via Fax: 1, Via other systems: 2" and concludes "The majority of VONA are issued via email".
- **Use:** the specification for a VONA parser and validator. Pitch support: the VONA email subscription, not a web scraper, is the realistic lawful route to PVMBG's VONAs.
- **Effort:** S.

### E6. Washington VAAC KML and IWXXM advisories — EVAL (parser fixtures)
- **URL:** https://www.ospo.noaa.gov/products/atmosphere/vaac/messages.html ; https://tgftp.nws.noaa.gov/data/raw/lu/luxx21.knes..txt
- **Licence:** the NWS public-domain notice (OSPO's own disclaimer was not opened).
- **Access:** keyless.
- **Verified:** the messages page (335 KML and 335 XML links), a Sangay KML and an IWXXM 3.0 `VolcanicAshAdvisory` are all 200. The tgftp `lu` folder carries IWXXM only from Washington and Anchorage, none from Darwin or Tokyo.
- **Use:** fixtures for an IWXXM advisory parser, and a template for exporting TEPHRA's cone as KML.
- **Effort:** S.

### E7. BoM VOLCAT case studies (Zenodo 3579613) — EVAL
- **Gives:** ten netCDF cases of VOLCAT retrievals (ash probability, height, mass loading, BTD) for Indonesia, PNG and the Solomons, 2014–2019. They include Kelut 2014, Rinjani 2015 and 2016, Soputan 2016, Merapi 2018, Agung 2019, Manam 2015 and 2018, Tinakula 2017 and Sangeang Api 2014.
- **URL:** https://zenodo.org/records/3579613
- **Licence:** CC BY 4.0 (Zenodo record).
- **Access:** keyless; files range from 14.5 MB to 1.13 GB.
- **Verified:** the API is 200. `Rinjani2.nc` (14.5 MB) was downloaded and its md5 matches. Ash appears at 05:00Z (120 pixels, top 10.15 km) and shrinks to 11 pixels by 11:00Z. Some files reach 1.13 GB.
- **Use:**
  - An Indonesian arm for `evals/plume` whose labels come from an algorithm, not a forecaster's "not identifiable". The matching Himawari-8 HSD comes from L17.
  - A pixel-by-pixel check of the BTD module.

  Never use these cases as few-shot examples.
- **Effort:** M.

### E8. NOAA/CIMSS VOLCAT public imagery — EVAL and pitch
- **Gives:** 10-minute Himawari-9 VOLCAT images (ash height, loading, probability, BTD and RGB). Public sectors include Java, Semeru, Krakatau, Dukono, Ruang, the Philippines, Taal, Mayon, Japan, Aira and Suwanosejima. The archive rolls over about 30 days.
- **URL:** https://volcano.ssec.wisc.edu/imagery/get_list/json/sector:Java_1_km::instr:AHI::sat:HIMAWARI-9::image_type:Ash_Height
- **Licence:** none stated. The disclaimer reads: "any user implicitly agrees to use the services and data available through this website as is with no warranty issued or implied and should be used for informational purposes only. Any use of this data for decision making processes is done at the sole risk of the end user." Alerts need a login.
- **Access:** keyless for images (no CORS header); alerts need a login.
- **Verified:** 05:40–05:55Z; the image lists and images are 200. A count of coloured pixels found no flagged ash in any of the four frames sampled:
  - Java, 25 Sep 15:00Z;
  - Java, 10 Oct 05:00Z;
  - Philippines, 8 Oct 10:30Z and 11:30Z. That was the Taal eruption day, when Tokyo VAA 21 said "VA NOT IDENTIFIABLE FM SATELLITE DATA".

  No positive case in the region was found, so VOLCAT's hit rate here is unknown.
- **Use:** an evidence column in the evaluation ("VOLCAT flagged ash: none / to N km") beside TEPHRA's BTD. For the pitch: the operational detector is often silent here, which is why silence never shrinks the hazard. Credit "NOAA/CIMSS VOLCAT" and keep the use informational.
- **Effort:** M.

### E9. NOAA IGRA2 radiosondes — EVAL and pitch
- **Gives:** observed soundings (wind, temperature, height), usually at 00Z and 12Z. 2026 files exist for:
  - 8 Indonesian stations, including 96935 Surabaya-Juanda, 82 km from Semeru;
  - 8 Philippine stations, including 98444 Legazpi near Mayon and 98433 Tanay near Taal;
  - 16 Japanese stations, including 47827 Kagoshima.
- **URL:** https://www.ncei.noaa.gov/data/integrated-global-radiosonde-archive/access/data-y2d/IDM00096935-data-beg2026.txt.zip
- **Licence:** cite as "Durre, Imke; Yin, Xungang; Vose, Russell S.; Applequist, Scott; Arnfield, Jeff; Korzeniewski, Bryant; Hundermark, Bruce. (2016) Integrated Global Radiosonde Archive (IGRA), Version 2. … DOI:10.7289/V5X63K0Q". The access constraints are only a liability disclaimer.
- **Access:** keyless, with a 1–3 day lag, so not for live use.
- **Verified:** 200. The sounding released on 25 Sep at 11:30Z, 10 minutes after the 11:20Z Semeru SIGMET, measured:

  | Level | Height | Wind toward | Speed |
  |---|---|---|---|
  | 700 hPa | 3,182 m (below the 3,676 m summit) | 060° | 9.9 kt |
  | 642 hPa | about 3,883 m | 110° | 14 kt |
  | 596 hPa | about 4,486 m | 145° | 15.9 kt |

  The levels and winds were re-checked from the saved file. The heights at 642 and 596 hPa are the hunt's log-pressure interpolation; the file gives none. On 24 Sep at 11:30Z, about 3.9 km went toward 070° and 4.2–4.8 km toward 120–130°.
- **Use:** in each replay, score which wind level matches the SIGMET and VONA drift, and show an "observed sounding, Surabaya 11:30Z" card next to the model winds. For the pitch, see section 7.2, item 6.
- **Effort:** S.

### E10. Himawari-9 derived motion winds (AWS `noaa-himawari9`, `AHI-L2-FLDK-Winds`) — EVAL
- **URL:** https://noaa-himawari9.s3.amazonaws.com/?list-type=2&prefix=AHI-L2-FLDK-Winds/2026/09/25/1100/
- **Licence:** NOAA and JMA attribution, with no implied endorsement.
- **Access:** anonymous S3.
- **Verified:** the listing is 200, with 6 products per slot (5.7–14.5 MB each); they were not decoded.
- **Use:** an observed check on the model and sounding winds near a vent.
- **Effort:** M.

### E11. GEO-KOMPSAT-2A L1B on AWS (`noaa-gk2a-pds`) — EVAL
- **URL:** https://noaa-gk2a-pds.s3.amazonaws.com/?list-type=2&prefix=AMI/L1B/FD/202610/10/04/
- **Licence:** "NOAA data disseminated through NODD are open to the public and can be used as desired", with attribution requested and no implied endorsement (https://registry.opendata.aws/noaa-gk2a-pds/).
- **Access:** anonymous S3; about 35 MB per band per time step.
- **Verified:** listings are 200. The 2 km IR NetCDF files are about 35 MB per band, and the archive runs from February 2023.
- **Use:** a second-satellite check of a weak BTD signal (ir105 minus ir123).
- **Effort:** L.

### E12. CEReS gridded Himawari (Chiba University) — EVAL ONLY, restricted
- **URL:** ftp://hmwr829gr.cr.chiba-u.ac.jp/gridded/FD/V20190123/
- **Licence:** "CEReS H8/9 gridded data is limited for non-commercial use." "We also prohibit the distribution of our gridded data to third parties, except among the research communities." Data from the last 24 hours are IP-restricted, and two papers must be cited.
- **Access:** anonymous FTP for data older than 24 hours; the same-day folder is IP-restricted.
- **Verified:** the listing is 226 (OK), and a 256 KB range of a Band 13 file is valid bzip2. The same-day folder was refused.
- **Use:** an offline BTD cross-check only. Never ship or redistribute it. The AWS HSD path covers the same need openly.
- **Effort:** M.

### E13. MrAirspace aircraft flight schedules (Parquet derived from adsb.lol) — EVAL and pitch
- **Gives:** one row per detected flight per quarter from 2024 Q2: hex, registration, type, airline, callsign, the start and end of the track, and a VRS-validated route. 2026 Q2 has 14,040,611 flights.
- **URL:** https://github.com/MrAirspace/aircraft-flight-schedules
- **Licence:** ODbL 1.0 (GitHub licence field). The README says: "Please use in line with the license defined in this repository. No guarantee, no liability, no warranty."
- **Access:** GitHub release assets; Range requests let single columns be read remotely.
- **Verified:** the footer was read with one 64 KB range, and two columns (about 39 MB) were read remotely. Q2 holds 89,002 flights by 10 Indonesian carriers, 94% of them with a route.
- **Use:** offline only. Write a small `data/rfa_schedule.json` so the fictional airline flies real-looking patterns, with ODbL attribution. Drop registrations. Coverage follows adsb.lol, so East Java is under-counted.
- **Effort:** M.

### E14. adsb.exposed public ClickHouse table — MEASUREMENT ONLY
- **Gives:** SQL over about 50 billion ADS-B rows from adsb.lol, ADS-B Exchange samples and airplanes.live.
- **URL:** https://adsb.exposed/ ; https://github.com/ClickHouse/adsb.exposed
- **Licence:** the repo licence is "Other". The README says the adsb.lol rows are ODbL, and that airplanes.live gave its data with these conditions: "no reselling the data; - no commercial use (except for within this application) without an agreement; - attribution is required".
- **Access:** a read-only user, with at most 1,000 selects a minute per IP. It runs on a staging service with deliberate fault injection.
- **Verified:** seven aggregate queries (4.5–6 s each).
  - In the East Java box, the only rows came from airplanes.live.
  - A Flores box had 0 positions all day on 25 Sep.
  - A Halmahera box had 3 aircraft; the nearest was 96 nm from Dukono.
- **Use:** coverage numbers for the deck only. Never poll it from Cloud Run. Cite "adsb.exposed (ClickHouse), data: airplanes.live / adsb.lol".
- **Effort:** S.

### E15. OpenAP aircraft performance model — EVAL (fuel-rate check)
- **URL:** https://github.com/TUDelft-CNS-ATM/openap
- **Licence:** the code is LGPL-3.0; the data directory carries "GNU GENERAL PUBLIC LICENSE Version 3".
- **Access:** keyless (GitHub and PyPI).
- **Verified:** the repo and PyPI are 200. The hunt re-implemented OpenAP 2.6's en-route formula rather than running OpenAP:

  | Type | Cruise (kg/min) | Holding (kg/min) |
  |---|---|---|
  | A320 | 44.3 | 40.6 |
  | B738 | 43.8 | 39.1 |
  | E190 | 33.2 | 30.5 |
  | A333 | 91.1 | 83.8 |

  OpenAP has no turboprop: it maps the ATR to the E145 jet.
- **Use:** cite it as a check on TEPHRA's flat rates. NARROWBODY at 42 kg/min fits, WIDEBODY at 110 is high, and REGIONAL_JET at 25 is low. Do not copy its GPL data into the MIT repo. Check the figures before quoting them.
- **Effort:** S.

### E16. NOMADS HYSPLIT meteorology — out of scope for 18 Oct
- **URL:** https://nomads.ncep.noaa.gov/pub/data/nccf/com/hysplit/prod/
- **Licence:** NOAA/NWS; the public-domain notice was assumed, not checked for this directory.
- **Access:** keyless; NOMADS needs HTTP/1.1.
- **Verified:** the listing is 200; the GDAS1 weekly files are 585 MB, kept about two months.
- **Use:** a physics trajectory baseline, only if someone wants one.
- **Effort:** L.

### E17–E20. Low-priority sets

All four are keyless. The effort is S each, except the SEVIRI set, which is M because the file is 333 MB.
- **SEVIRI balanced ash/ice/SO2 dataset** (https://zenodo.org/records/20313629, CC BY 4.0). The 333 MB file was not downloaded. It covers Etna only, in dry mid-latitude air, so it does not represent Indonesia.
- **Raikoke 2019 Himawari ash retrievals** (https://researchdata.reading.ac.uk/335/). The satellite data are "(C) Crown Copyright 2021 … licensed by the rights-holder under the Non-commercial Government Licence 2.0", and the simulations are CC BY 4.0. It is a dry-air positive control (research/12 already used Raikoke).
- **NCAR EOL VAA archives, 2011–2012** (https://data.ucar.edu/dataset/volcanic-ash-advisory-center-darwin-ash-advisory). The metadata say "Legal Constraints none" and "Access Constraints none". The download route was not tested. They are old-format samples for the parser.
- **GeoNet NZ volcanic alert levels** (https://api.geonet.org.nz/volcano/val). "GeoNet content is copyright Earth Sciences New Zealand and is licensed under a Creative Commons Attribution 3.0 New Zealand License". A clean second source for status-chip unit tests; New Zealand only.

---

## 7. Pitch evidence

### 7.1 Documents and records

All of these are public pages, read without a key. Using one costs S (cite it with a link) unless the entry says otherwise. They are evidence for the deck and video, not inputs to TEPHRA.

**P1. Indonesia DGCA press releases (Ditjen Hubud, Kemenhub)** [CONFIRMED: pages opened and saved on 10 Oct].
- **Circular SE-DJPU 15/2026** (release of 8 Sep; https://hubud.kemenhub.go.id/hubud/website/berita/4888):
  - "operator pesawat udara diwajibkan melakukan Safety Risk Assessment sebelum merencanakan penerbangan pada wilayah yang berpotensi terdampak abu vulkanik": aircraft operators must carry out a safety risk assessment before planning flights in areas that ash may affect.
  - The result is a basis for deciding whether to continue, reroute or cancel.
  - "setiap kejadian paparan abu vulkanik (volcanic ash encounter) perlu dilaporkan dan didokumentasikan melalui sistem pelaporan keselamatan": every ash encounter must be reported and documented through the safety reporting system.
  - The circular uses Collaborative Decision Making under KP 153/2019, drawing on PVMBG, BMKG, flight information, pilot reports and airport conditions.
  - "Ketentuan ini mulai berlaku sejak 6 September 2026": it has applied since 6 Sep 2026.
- **Soekarno-Hatta, 6 Sep** (releases 4885–4887):
  - NOTAM A3341/26 closed CGK from 01:30 WIB, after a positive paper test at 00:35–01:05 WIB.
  - A second positive test at 06:05–06:35 WIB extended the closure to 09:30 WIB (A3344/26), and a later NOTAM to 13:30 WIB (A3346/26).
  - From 01:30 to 09:30 WIB, 209 movements and 22,798 passengers were affected, and 170 aircraft were held on the apron (T1 66, T2 51, T3 49, cargo 4).
  - By 10:35 WIB: CGK 202 flights affected (167 cancelled), Halim 29 (all cancelled), Radin Inten II 8 (all cancelled), and 277 at other airports.
  - Release 4887's headline says 373 flights, but its own breakdown adds up to 516. Quote the per-airport figures, not the total.
- **Kualanamu, 1 Sep** (release 4878, 2 Sep):
  - Thin Sinabung ash on the apron closed Kualanamu under NOTAM A3250/26; it reopened under A3254/26.
  - 45 flights were cancelled and 6 rescheduled.
  - The Darwin-sourced SIGMET gave ash to 14,000 ft, moving SW at about 5 kt.
  - The release says airlines "memiliki kewenangan untuk melakukan evaluasi dan assessment terhadap operasional penerbangannya": airlines have the authority to evaluate and assess their own operations.
- **Ruang, April 2024** (releases 4624 and 4625):
  - ASHTAM VAWR7240 closed Sam Ratulangi (Manado) from 17 Apr 19:26 WITA.
  - NOTAM A1010/24 extended the closure to 19 Apr 18:00 WITA by agreement of the airport authority, AirNav, BMKG and four airlines.
  - The procedures are those of KP 153/2019 on "Collaborative Decision Making (CDM) … melalui Integrated Web Based Aeronautical Information System Handling (I-WISH)".
- **Lewotobi, November 2024** (releases 4689 and 4698):
  - Ash reached FL400 on 5 Nov 2024, and ASHTAMs covered eight Flores-area airports.
  - Komodo airport closed under NOTAM A3479/24.
  - Frans Seda (Maumere) was closed from 17 Jul to 1 Dec 2024.
- **Licence:** no statement; the footer reads '© 2026 Direktorat Jenderal Perhubungan Udara', and robots.txt allows everything. Cite with links; do not republish.
- **Caveats:**
  - Each release is a same-day snapshot, and the scopes differ: movements, flights or passengers.
  - The circular's own text was not fetched, so attribute its content to "DGCA says".
  - Do not claim the circular requires software.

**P2. BMKG press release, 7 Sep 2026** [CONFIRMED by WebFetch]. https://www.bmkg.go.id/siaran-pers/imbas-sebaran-abu-vulknaik-anak-krakatau-8-bandara-ditutup-sementara-bmkg-minta-waspada-dan-tenang
- BMKG had issued "sebanyak 39 dokumen Significant Meteorological Information (SIGMET)" (39 SIGMETs) since the first eruption on 4 Sep.
- AirNav's NOTAM closed eight airports "hingga pukul 18.00 WIB" (until 18:00 WIB).
- The latest SIGMET put ash to 15,000 ft moving west, with a layer to 50,000 ft over the Indian Ocean.
- Licence not checked: quote only. The count may include cancellations.

**P3. USGS Data Series 545** (Guffanti, Casadevall and Budding 2010), https://pubs.usgs.gov/ds/545/ [MEASURED: our count of Appendix 1B, re-computed for this file].
- 129 recorded encounters, 1953–2009.
- Volcanoes in Indonesia, the Philippines and Japan account for:
  - 52 of the 129 (40%);
  - 35 of the 79 damaging encounters (severity 2–4);
  - 5 of the 9 severity-4 encounters, defined as "Temporary engine failure requiring in-flight restart of engine" (Table 1).
- Indonesia alone had 7 encounters, including the two 1982 Galunggung 747 engine failures.
- Licence: "Although this report is in the public domain, permission must be secured from the individual copyright owners to reproduce any copyrighted materials contained within this report."
- Caveats: the data end in 2009 and are a minimum count; one Japanese severity-4 case is listed as "Unzen?".

**P4. USGS Open-File Report 2007-1256 and Guffanti et al. 2009** (airports disrupted 1944–2006), https://pubs.usgs.gov/of/2007/1256/ ; https://zenodo.org/records/1232830 [CONFIRMED].
- 171 incidents at 101 airports in 28 countries.
- Indonesia had 13 incidents at 8 airports from 7 volcanoes, the most source volcanoes of any country.
- Manado was hit in 1984, 1991 and 2001, so Ruang 2024 was at least its fourth.
- "Since 1980, five airports per year on average have been affected by volcanic activity."
- Licence: the report is public domain (with the same caveat as P3); the article's Zenodo copy is CC0. The data end in 2006.

**P5. Airport-operator statements in Indonesian media** [REPORTED: operator statements quoted by media].
- **Bali, Lewotobi, November 2024.**
  - The airport's general manager said that on 13 Nov 135 flights were cancelled, 115 of them because of Lewotobi.
  - 205 of 340 movements (60%) still operated, and the airport stayed open.
  - VIVA on 14 Nov 2024: "9 maskapai rute domestik yang tetap beroperasi dari total 12" (9 of 12 domestic airlines kept operating). And: "untuk penerbangan internasional terdapat 28 maskapai yang tetap terbang dari total 42 maskapai" (28 of 42 international airlines kept flying). The other 14 did not.
  - Sources: https://www.viva.co.id/berita/nasional/1771668-41-penerbangan-di-bandara-ngurah-rai-kembali-dibatalkan-hari-ini-dampak-erupsi-gunung-lewatobi ; https://news.detik.com/berita/d-7637858/115-penerbangan-di-bandara-ngurah-rai-bali-batal-imbas-erupsi-lewotobi
- **Manado, Ruang, 30 Apr 2024.** The spokesperson gave 38 flights and about 3,832 passengers; the general manager gave 18 flights and about 1,745 passengers by 12:00 WITA. The difference is the cut-off time.
- Licence: the publishers' copyright; cite the facts with links. Antara's footer forbids crawling or indexing for AI without written permission.

**P6. Engwell et al. 2021**, Bull. Volcanol. 83:9 (CC BY 4.0), https://nora.nerc.ac.uk/id/eprint/529824/1/Engwell2021_Article_Near-real-timeVolcanicCloudMon.pdf [CONFIRMED].
- The paper analyses all VAAs from the nine VAACs, 2009–2018. Darwin issued 18,153, about 1,800 a year.
- It summarises Tupper and Wunderman (2009): ground and satellite eruption heights over Indonesia and PNG differ so much that "the datasets are independent and cannot, without further investigation, be used to substitute for each other". Satellite heights are better for large events, and ground reports for small, low plumes. This summary is second-hand.

**P7. Delbrel et al. 2025**, J. Applied Volcanology (CC BY 4.0), https://doi.org/10.1186/s13617-025-00150-7 [CONFIRMED: abstract].
- "aircraft adopt a range of strategies to avoid ash, largely avoiding the indicated air space affected by ash".
- "the greater the volume of air affected by volcanic ash the greater the deviation".
- Reroutes mean "longer air travel time and delays, suggesting greater fuel consumption and carbon emissions".
- Caveats: the samples are small (5 Marapi flights), and the Flightradar24 data cannot be shared. A "52% delayed" figure was flagged as inconsistent with n = 5: do not use it.

**P8. Christmann, Nunes, Schmitt and Guffanti 2015** (IWVA slides), https://old.wmo.int/aemp/sites/default/files/P-35_CHRISTMANN.pdf [CONFIRMED].
- 113 encounters in 2010–2014, none of them severity 4, taken mostly from EUROCONTROL's EVAIR.
- "not all encounters are reported and therefore remain unknown".
- Use: the public record since 2009 is mostly European; pair this with the reporting duty in SE-DJPU 15/2026. These are slides, not a peer-reviewed paper.

**P9. VAAC Model Setup Tables 2023** (Beckett et al., Zenodo 10671098, CC BY 4.0). Darwin runs HYSPLIT driven by ACCESS (ensemble and deterministic) and GFS. Tokyo runs JMA-ATM driven by JMA-GSM, with data insertion. So neighbouring VAACs may draw one cloud differently at a boundary. Check the cells before quoting them.

**P10. UK AIC P 157/2025 (NATS)** [CONFIRMED]; corrects claims-register #14. https://nats-uk.ead-it.com/cms-nats/opencms/en/Publications/aip-supplements/EG_Circ_2025_P_157_en.pdf
- "VAAC London and VAAC Toulouse will provide QVA forecasts from 27 November 2025. The other seven ICAO designated worldwide VAACs will not initially supply QVA forecasts. However, Amendment 82 recommends that all VAACs should issue QVA forecasts from 26 November 2026."
- London's QVA API needs a licence acceptance and an emailed request.
- Licence: Crown copyright; cite only.
- Use: say "recommended", not "due". No public Darwin or Tokyo QVA was found on 10 Oct. When a QVA product exists, TEPHRA can take it as one more official floor.

**P11. NASA Earth Observatory Image of the Day, 9 Sep 2026: "Anak Krakatau Rumbles Again"** (Landsat 8 OLI, 5 Sep), https://science.nasa.gov/earth/earth-observatory/anak-krakatau-rumbles-again/
- It gives ash to 6,000 m to the east and about 15,000 m to the west, matching the two-layer SIGMETs.
- Licence: NASA imagery "generally are not subject to copyright in the United States". It "must not explicitly or implicitly convey NASA's endorsement of commercial goods or services", and "NASA should be acknowledged as the source of the material". Credit line: "NASA Earth Observatory/Michala Garrison" (https://www.nasa.gov/nasa-brand-center/images-and-media/).
- Use: the opening shot, with the credit line and no NASA logo. The image file was not downloaded.

**P12. Smithsonian/USGS Weekly Volcanic Activity Report** [UNVERIFIED live: the site was down]. The Wayback copy of 1 Oct 2026 restates PVMBG, PHIVOLCS and JMA reports in English. Context only, once the site returns.

**P13. Sentinel-2 L2A via Earth Search** (https://earth-search.aws.element84.com/v1/search). There are 18 Semeru scenes since 1 Aug with less than 40% cloud. The full COGs exceed 300 MB, so use windowed reads for stills only. Credit: "Contains modified Copernicus Sentinel data 2026".

**P14. Google Earth Engine catalogue** (Sentinel-5P SO2 and aerosol index, CAMS SO2, ERA5, WeatherNext): roadmap only.
- The data need a Cloud project registered for Earth Engine. That is a sign-up, and it would have to be on the personal account, never the work gcloud. WeatherNext also needs a request form.
- There is no Himawari collection in Earth Engine.
- CAMS: "There is no restriction on use or reproduction and redistribution, with or without adaptation, for commercial or non-commercial purposes."

**Prior art found by the hunt** (graded in `CONFLICTS.md` A11–A14):
- **P15. `mzmznasipadang/ash-map`** (the AshMap of research/04).
  - Created on 6 Sep 2026, during the Krakatau event.
  - A keyless map of Darwin VAA polygons read from BoM FTP `/fwo`, with a TypeScript VAA parser for all VAACs, Open-Meteo winds, a drift animation, GIS export and NOTAMs through a paid API.
  - It has no LLM and does no reconciliation.
  - Its licence is "Other" (NOASSERTION): do not copy its code.
  - Its README says BoM's dated tree "lags real time by days"; that is false today, since the same advisory sat in both trees at 04:07Z on 10 Oct.
- **P16. Indonesia DGCA's I-WISH** (Integrated Web Based Aeronautical Information System Handling).
  - KP 153/2019 runs the collaborative ash procedure through it [CONFIRMED: P1, releases 4624 and 4625].
  - The hunt also reported, from search summaries only, that it has run since September 2018, is restricted, combines SIGMET and ASHTAM ash spread with affected airports and routes, and has an API [REPORTED; the ICAO APAC paper returned 403].
- **P17. AirNav Indonesia "NOTAM AI Generation".** AirNav's home page (fetched 10 Oct; the item is undated) says it was recognised for a generative-AI tool "yang mengonversi teks bebas menjadi NOTAM terstruktur" (that turns free text into structured NOTAMs), built with Telkom University.
- **P18. SITA eWAS Dispatch.** It gives "dispatchers a real-time view of the location of every aircraft and live and upcoming weather hazards", with "an early warning system that provides alerts on potential weather issues" (Runway Girl Network, October 2022, about Azul; https://runwaygirlnetwork.com/2022/10/sita-ewas-dispatch-azul/). Its volcanic-ash and SIGMET layers come from search results only.

### 7.2 Measurements the hunt made

| # | Measurement | How | Caveat |
|---|---|---|---|
| 1 | **Krakatau, 5–8 Sep.** Between VONA 2026KRA026 (5 Sep 02:00Z, "Ash-cloud is not observed") and KRA027 (8 Sep 04:34Z, about 74.5 h later), Darwin issued 28 advisories (2026/172–199). 24 of them carried a SFC/FL500 layer, and the low layer changed direction six times (SE, E, W, E, SE, W, SW). Advisory 2026/196 (7 Sep 11:30Z) says "VA TO FL500 NO LONGER DISCERNIBLE". | Parsed from BoM FTP texts (R4) | BoM's files may not be republished; cite the counts |
| 2 | **METAR VA at Jakarta.** Soekarno-Hatta reported VA 69 times from 5 Sep 18:30Z to 7 Sep 05:00Z; Radin Inten II 74 times; Halim 50. | IEM (R2); identical rows in GHCNh (R3, CC0) | VA in a METAR is an observer's call; its absence is not "no ash" |
| 3 | **The closure seen by ADS-B.** On 6 Sep, 11:00–11:30Z, adsb.lol saw 0 airborne aircraft within 100 nm of Soekarno-Hatta, against 59 in the same half-hour on 25 Sep. Within 250 nm of Anak Krakatau: 0 against 63. Manila (39 against 38) and Kagoshima (63 against 72) were normal, so this was not a feeder outage. | Decoded heatmaps (R5) | One half-hour each; 6 Sep was a Sunday and 25 Sep a Friday |
| 4 | **Open ADS-B coverage, 25 Sep, 11:00–11:30Z.** 0 aircraft within 100 nm of Semeru (nearest 115 nm). 0 within 250 nm of Lewotobi, Lewotolok, Dukono and Ibu. 51 within 100 nm of Anak Krakatau (48 below FL200), 59 within 100 nm of Soekarno-Hatta, 40 at Taal, 52 at Sakurajima. A live check at 05:21Z on 10 Oct found the same 2 aircraft on adsb.lol and adsb.fi within 100 nm of Surabaya, and 0 within 100 nm of Bali. | Decoded heatmap; live point calls (L9) | An empty map means "not seen", not "not there". airplanes.live saw 12–22 aircraft an hour near Semeru (L10) |
| 5 | **Traffic past Semeru.** About 101 flights a day by 10 Indonesian carriers fly a great-circle leg within 25 nm of Semeru (CGK–DPS about 61), about 133 within 50 nm, and about 92 more start or end at Surabaya or Malang. The CGK–DPS great circle passes 1.9 nm from the vent. | Q2 2026 schedules (E13, ODbL) and VRS routes (M24) | Lower bounds: foreign carriers are excluded, East Java is under-detected, and a great circle is not the airway flown |
| 6 | **The Semeru sounding.** On 25 Sep at 11:30Z, at plume height, the wind blew toward 110° (about 3.9 km) and 145° (about 4.5 km). North-east flow appeared only at 700 hPa (3,182 m), below the summit. | IGRA2 (E9), re-checked | One station, 82 km away, twice a day. It backs the SIGMET's SE at plume height; the VONAs' north is not supported at any level that day |
| 7 | **Five models agree for 23–27 Sep.** ECMWF IFS, GFS, ICON, JMA GSM and ECMWF AIFS give 600 hPa toward SE/ESE and 700 hPa toward ENE/E. A raw GFS decode reproduced Open-Meteo's `gfs_global` exactly. | R7, L18 | Model output |
| 8 | **SO2 on 7 Sep.** At about 05:53Z TROPOMI saw SO2 above 5 DU over about 133,000 km² around Java, with a peak of 55 DU at 111.65°E 6.11°S. Krakatau's latest VONA (5 Sep) still said "Ash-cloud is not observed". | AWS COG, quality above 0.5 (L14); visible on GIBS (M2) | SO2 is not ash. The source volcano is not attributed; trajectories are needed before any causal claim |
| 9 | **VOLCAT was silent.** No flagged ash pixels in any of four sampled frames: Java 25 Sep 15:00Z, Java 10 Oct 05:00Z, Philippines 8 Oct 10:30Z and 11:30Z. | Pixel count of public images (E8) | Four frames; no positive case in the region; hit rate unknown |
| 10 | **Semeru's summit elevation.** GVP and the Darwin VAA give 3,657 m and MAGMA 3,676 m, a 19 m spread. An independent DEM at full resolution (AWS Terrain Tiles z12, SRTM) gives 3,668 m, between the two, and SRTM's vertical error is about 16 m. Coarser tiles read lower (z10 3,651 m, z8 3,593 m, Mapterhorn z8 3,618 m), because each pixel averages a wider area. Darwin's SOURCE ELEV matches GVP for 8 of 12 volcanoes; Ibu, Dukono, Lewotolok and Krakatau differ. | M11, M10, M23 | Datum and DEM choices. Never a CONFLICT |
| 11 | **Darwin's workload.** BoM's FTP archive holds 2,020 text bulletins for 2022, 3,066 for 2023, 5,885 for 2024, 5,672 for 2025, and 4,687 for 2026 up to 10 Oct, about 16 a day. In 2009–2018 Darwin issued 18,153 VAAs (P6). | FTP listing count (R4) | A file count, not unique advisories; a few are test or pointer messages |
| 12 | **The DS 545 share.** Indonesia, the Philippines and Japan: 52 of 129 encounters (40%), 35 of 79 damaging ones, and 5 of 9 in-flight engine failures, 1953–2009. | P3, re-computed | A minimum count; ends 2009 |
| 13 | **Anak Krakatau's level.** Badan Geologi lowered it from Level III to Level II on 21 Sep 2026 at 18:30 WIB. research/09 recorded MAGMA's level page at Level III on 10 Oct. | L6 | Either MAGMA's page lags or two official statuses disagree. Check MAGMA by hand, not by crawling |

---

## 8. Assets and libraries (not data)

| Item | Licence | Status |
|---|---|---|
| MapLibre GL JS 4.7.1 (unpkg) | BSD-3-Clause | IN BUILD |
| @maplibre/maplibre-gl-compare 0.5.0 (unpkg) | ISC | IN BUILD (CSP allows it) |
| MapLibre GL JS 5.24.0 | BSD-3-Clause | Optional, for a globe intro. Version 6 drops the UMD build, so do not move to it this week |
| IBM Plex Sans and IBM Plex Mono | SIL Open Font License | IN BUILD (`tephra/web/fonts/`, with `OFL.txt`) |
| Lucide 1.54.0 icons | "ISC License … provided that the above copyright notice and this permission notice appear in all copies" (Feather-derived icons are MIT) | IN BUILD (`tephra/web/icons.svg`) |
| Material Symbols "flight" (@material-symbols/svg-400 0.48.0) | Apache-2.0 | IN BUILD (`icons.svg`) |
| Maki 8.2.0 ("airport") | CC0-1.0 | IN BUILD (`icons.svg`) |
| B612, Atkinson Hyperlegible, Inter, JetBrains Mono | OFL (B612 also EPL-2.0 and EDL-1.0) | Checked, not used |
| Noto Sans glyphs (OpenFreeMap) | OFL | IN BUILD through the basemap |

The design references the hunt checked are in `docs/UI-DESIGN.md` (UI builders' file): WCAG 2.2, NN/g on confirmation dialogs, GOV.UK "check answers", web.dev offline UX, Google AIP-154, the Astro UX Design status system, the AVO colour-code icons, AWC's SIGMET colours, Flightradar24 Playback, Windy, tar1090, the VAAC graphic conventions and the colour-vision palettes. They are references only. Two things must not be copied: tar1090 code (GPL) and AVO's icon images. Astro UXDS is US-government public domain with a licence grant, so keep its notice if any of it is used.

---

## 9. Rejected or not recommended

| Reason | Sources |
|---|---|
| **robots.txt or terms forbid automated use** | MAGMA (magma.esdm.go.id, magma.vsi.esdm.go.id), vsi.esdm.go.id and geoportal.esdm.go.id: `Disallow: /` (re-checked 10 Oct); MAGMA's API needs a JWT; "All Rights Reserved". The lawful routes are the VONA email subscription or a PVMBG token. · Ogimet: `Disallow: /`. · SACS: `/nrt/` disallowed; alerts by email sign-up. · ULB IASI SO2 alerts: `Disallow: /`. · MODVOLC: its tools sit under a disallowed `/cgi-bin/`. · RealEarth `/api/`: disallowed (tiles used instead, M6). · KVERT: terms forbid use without permission and any commercial use. · BoM website pages, including the Australian VA SIGMET page: "we do not allow you to use automated or manual techniques to hack, scrape or otherwise extract material from our site". · OpenSky REST: "Use of the REST API in any operational capacity … requires a previous written agreement, even for non-profit or governmental entities"; OAuth2 only; no coverage east of 110.94°E. · OpenSky aircraft database and Doc 8643 CSV: "solely for the purpose of non-profit research and non-profit education"; no distribution outside your institute. · adsbdb routes: "may not be copied, published, or incorporated into other databases without the explicit permission of David J Taylor, Edinburgh". · hexdb.io: "Please do not scrape the database"; routes date from 2011; not needed. · Antara: no crawling or AI indexing without written permission (cite by hand only). |
| **Needs an account, key or sign-up** | FIRMS API and keyed WMS (MAP_KEY). · Copernicus Data Space downloads (token; use L14). · ERA5 through the CDS API (use R9). · Earth Engine data and WeatherNext (P14). · BigQuery public datasets (Google auth; gcloud must not run here). · London and Toulouse QVA APIs (Europe only). · VOLCAT alerts (collaborator login). · USGS VNS email. · SADIS and WIFS. · ADSBHub (you must feed data). · OpenAIP (needs a user; requester-pays bucket; reported CC BY-NC). · MapTiler terrain, CARTO basemaps and the Protomaps API (keys). · FAA NOTAM Search (403; the API needs registration and keeps no history). · NASA MEaSUREs SO2 (Earthdata login). · Philippine eAIP (login and subscription). · AIS Japan (did not resolve; registration reported). · ICAO FIR datasets (sold for USD 1,995–4,495). · ICAO Doc 8643 online (403/401). · planespotters API (needs a contact User-Agent). · Weathernews WxTech, CheckWX and AVWX (commercial keys). |
| **Blocked, down or unreachable** | BMKG aviation sites and data.bnpb.go.id (Cloudflare challenge). · satudata.esdm.go.id and katalog.satudata.go.id (do not resolve). · Indonesian eAIP hosts (do not resolve). · Wellington VAAC site (connection reset). · University of Wyoming soundings (timeout; use E9). · NASA GSFC SO2 site (TLS failure). · Smithsonian GVP website, weekly report and RSS (Cloudflare "temporarily unavailable"; the WFS works, M23). · ICAO APAC MET SG/30 IP/03, ATMSG/14 WP30 and other ICAO papers (403). · NATO STO encounter paper (403). · USGS copyright and alert-level pages (WAF or 403). · EUROCONTROL EVITA pages (403; UNVERIFIED). · NOAA nowCOAST help (403). · Flightradar24 site (403). · IVESPA (self-signed certificate; not bypassed). · Swiss FOCA turboprop emissions PDF (502). · BPS passenger statistics (403 through the news site). · WAFS GRIB2 on NOMADS (403). · tgftp `/data/raw/lm/` (403). · airplanes.live history and ADSB One (403). |
| **Exists, but not useful here** | IEM SIGMET GIS service, AFOS text archive and TAF archive (US only); IEM SIGMET page (404). · NCEI ISD (ends 2025-08-24; use R3). · Wayback captures of SIGMET and BMKG pages (0 captures). · AWC PIREP/AIREP (no reports over Indonesia, none with ash) and AWC navaid/fix API (US only). · GK-2A as an ash product (L1B only). · data.go.id (regional hazard tables only). · WOVOdat (historical research database). · PHIVOLCS WordPress API and RSS (401; news only). · Tokyo VAAC site as a VONA source (none). · Open-Meteo Previous Runs at pressure levels (400), ERA5 archive at pressure levels (nulls) and GraphCast (nulls). · GVP emissions WFS layer (broken). · GIBS thermal tiles in EPSG:3857 (404; use M3). · JMA "Himawari Ash RGB" (does not exist publicly) and Himawari in Earth Engine (not in the catalogue). · MapLibre demo terrain (an Austrian test area). · adsb.lol route endpoints (empty or 500). · avioadsb.org (6 receivers worldwide). · ADS-B Exchange samples (1st of each month only; no licence stated). · Wingbits sample (one day; evaluation only). · OpenSky COVID flight lists (stopped in January 2022). · `Jonty/airline-route-data` (no licence; scraped with browser impersonation). · tar1090-db and Mictronics (no licence). · Acropole (AGPL-3.0). · tar1090 code and markers (GPL). · Airframes.io (undocumented; carries feeder identities). · OpenFlights (frozen in June 2014). · PANGAEA and Figshare (nothing relevant). · Hugging Face volcanic datasets (drone photos; synthetic data). · the Engwell 2021 VAA dataset (never deposited). · Flightradar24 trajectories behind Delbrel 2025 (subscription). · VolcanoDiscovery's VAA mirror (Cloudflare; R4 has the texts). · aggregator pages and social posts (secondary). · Darwin and Tokyo QVA (nothing public). · IWXXM VAAs from Darwin or Tokyo, and IWXXM SIGMETs from BMKG (no public copy; AWC's IWXXM is its own translation). · restricted and danger-area polygons (no keyless, licence-clean source). · IVAO sector files (no licence). |
| **UI choices rejected** | OpenFreeMap "fiord" (overlay contrast falls to 2.4:1 and 1.8:1). · MapLibre 6.x this week (drops the UMD build). · `map.loadImage` with `data:` or SVG URLs (blocked by the CSP; SVG unsupported). · Lucide "plane" as the aircraft marker. · `mapbox-gl-sync-move` (unnecessary). · Re-hosting Darwin VA graphic PNGs ("This information is produced solely for use by the aviation industry", research/03). · VATSIM FIR outlines (share-alike; replaced by M14). |

---

## 10. Corrections to earlier research files

The research files themselves are left as written. Each correction is recorded, dated, in the claims register of `README.md` and, where it changes a conflict, in `CONFLICTS.md`.

| File | Earlier statement | Correction (10 Oct, this file) |
|---|---|---|
| README (index row 01; claim #14), CONFLICTS E1 | QVA becomes "due" from all VAACs on 26 Nov 2026 | Annex 3 Amendment 82 *recommends* QVA from all VAACs from 26 Nov 2026; the other seven VAACs "will not initially supply QVA"; no public Darwin or Tokyo QVA found (P10) |
| 05 §3.12 | GIBS has "no TROPOMI SO2 layer" | It does: `TROPOMI_L2_Sulfur_Dioxide_Total_Vertical_Column`, daily since 2018-05-06 (M2) |
| 09 §1.5 and C1; `data/replay/README.md`; README index row 09; CONFLICTS B4; DECISION-MEMO step 11 | The 5–7 Sep Krakatau SIGMETs are gone, and the VAA texts sit behind Cloudflare | The SIGMETs are in the IEM NOAAPort archive (R1). Every Darwin VAA is on BoM FTP (R4, private use only) and in NOAAPort's FV relay |
| 09 §2 (state table) | Anak Krakatau at Level III (MAGMA page, 10 Oct) | Badan Geologi lowered it to Level II on 21 Sep 2026 at 18:30 WIB (L6). Check MAGMA by hand |
| 13 (wind levels) | "At plume height the model favours the SIGMET's SE/E direction" | Now backed by an observation: the Surabaya sounding of 25 Sep 11:30Z (E9). Do not pitch "wind shear proves the VONA right" |
| 01 | Jakarta's METAR "carried VA" [REPORTED] | Measured: 69 VA reports at WIII, 5 Sep 18:30Z to 7 Sep 05:00Z (R2, R3) |
| 05, 09, PITCH | Night traffic near Semeru is thin, so record by day | Open ADS-B sees no aircraft near Semeru even by day; it sees Jakarta and Krakatau (section 7.2, items 3–4) |
| 07, census | Summit elevations differ between products | The sources' Semeru elevations agree within DEM error (section 7.2, item 10). Treat elevation differences as datum choices |

---

## 11. Open items that need a person

1. **Email airplanes.live** (L10). Only the user can. It is the one open route to East Java traffic.
2. **Decide on the BoM files** (R4): keep them out of the public repo and demo, or ask BoM (Registered User). See `../docs/DATA-LICENCES.md`.
3. **Check MAGMA's level page for Anak Krakatau by hand** (section 7.2, item 13). Do not crawl it.
4. **Open in a real browser** the pages that refused scripts: ICAO APAC MET SG/30 IP/03 (Darwin and Tokyo QVA plans), ATMSG/14 WP30 (Indonesia's ash CDM and I-WISH), and the EUROCONTROL EVITA pages, before citing any of them in the deck.
5. **Approve the full IEM download** for 4–8 Sep (about 1.2 GB streamed) if the Krakatau replay is wanted.
6. **Attribute the 7 Sep SO2 cloud** with trajectories before any causal line in the pitch (section 7.2, item 8).
7. **Optionally subscribe to WIS2 once** (L8) to confirm the Singapore SIGMET stream works.

---

## 12. Where the hunt's raw material is

The hunt's scripts, samples and downloads stayed in the session scratchpad, outside the repo. They are not part of this repository. Some carry licences that bar republishing: the BoM FTP Krakatau texts and graphics in particular.

These scripts are worth porting into `scripts/`, with tests, if needed:
- `stream_noaaport_va.py` and `fetch_iem_krakatau_full_days.sh` (IEM NOAAPort filter; `record_replay.py` already has its own `noaaport` command);
- `heatmap_decode.py` and `tarscan.py` (adsb.lol heatmaps and the release tar index);
- `igra_layer.py` (soundings);
- `grib2_mini.py` (GFS fields, template 5.3 only);
- `terrarium_peak.py` (DEM tiles);
- `vaa_table.py` and `ds545_region.py` (the counts in section 7).

The structured reports themselves are `datahunt_reports.json` and `review_reports.json` in the same scratchpad.
