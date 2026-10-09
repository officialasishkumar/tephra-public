# 05 — TEPHRA live feeds, verified by fetching them

Lens: **feeds**. Every feed TEPHRA plans to poll was fetched with `curl` from this machine between **2026-10-09 19:27 UTC and 19:57 UTC (2026-10-10 00:57–01:27 IST)**. All access dates below are written as 2026-10-10 (IST) per the brief. No gcloud, Vertex, Earth Engine, ADC or Gemini key was used. Google-side facts come from public docs pages only (opened with WebFetch, because `ai.google.dev` loops on redirects under plain curl).

Tags: [CONFIRMED: url, accessed 2026-10-10] = I fetched it and it says that. [REPORTED: url] = a secondary source says it. [UNVERIFIED] = not checked. Numbers I derived from fetched data are marked "(derived)".

---

## 1. Bottom line

1. **The text spine is real, keyless and live today.** aviationweather.gov returned 9 distinct VA SIGMETs worldwide at 19:27 UTC, 4 of them in Indonesian FIRs (Ibu, Dukono, Semeru in WAAF; Krakatau in WIIF) [CONFIRMED: https://aviationweather.gov/api/data/isigmet?format=json&hazard=va, accessed 2026-10-10]. In 59 of 59 successful 12-hourly samples over the last 30 days, at least one VA SIGMET was open in the Ujung Pandang FIR (WAAF) (derived from https://aviationweather.gov/api/data/sigmet?format=json&hazard=va&date=…, accessed 2026-10-10).
2. **A live three-way contradiction exists right now, for Semeru.** SIGMET WAAF 12 (1820Z) and Darwin VAA 2026/1157 (1820Z) both put ash at SFC/FL150 moving east, while the MAGMA VONA 20261009/1800Z says "Ash-cloud is not observed." Open-Meteo puts 700 hPa wind from 301° and 500 hPa wind from 67° over the summit, so the plume direction depends on which level you trust. This is exactly the reconciliation case TEPHRA is built for (section 4).
3. **Three planned sources must change** because their terms forbid our use or because they are not what the pack thought:
   - **MAGMA**: the JSON API needs a JWT (401 "Token not provided"), detail pages need a signed URL, and `robots.txt` is `Disallow: /` for every user agent. Polling the HTML is against the site's stated crawler policy. **SERIOUS.**
   - **Darwin VAAC via BoM**: BoM's copyright page says "we do not allow you to use automated or manual techniques to hack, scrape or otherwise extract material from our site" and `robots.txt` disallows `/fwo/`. **The JMA "Darwin mirror" is only a backup page** (34 rows since 2015; last real entries 23 Sep 2026). The clean replacement is the NWS `tgftp` raw bulletin directory, which carries every live Darwin advisory as plain text in the public domain. **MINOR once switched.**
   - **OpenSky REST**: its terms now require a written licence for "Operational use of the REST API in any live product, service, or automated system ... regardless of the entity's non-profit status." TEPHRA's poller is exactly that. **SERIOUS if kept; NONE if dropped** (adsb.lol covers it).
4. **The satellite-image step is weaker than the pack assumes.** JMA's public Band-13/Dust-RGB JPEGs are about 20 px per degree (roughly 5 km per pixel), so today's Semeru SIGMET polygon covers roughly 10 × 9 pixels in the `se3` frame (derived). NICT tiles are sharper but "not allowed for commercial uses". The open, full-resolution route is the NOAA/AWS `noaa-himawari9` bucket (2 km IR bands B11/B13/B14/B15, 10-minute cadence, attribution licence), which needs HSD decoding. This supports "image as support only".
5. **Gemini side:** `gemini-3.8-flash` is a real, stable model ID on the public models page (page last updated 2026-10-06), structured JSON output via `response_format` works with Gemini 3 models together with tools, and the free tier is "Free of charge". Exact free-tier RPM/RPD numbers are not published on the docs page; they show only in AI Studio.

---

## 2. Master table

| # | Feed | Exact URL tested | Status today | Key | Cadence | Licence / terms (short) | Break risk | Alternate |
|---|---|---|---|---|---|---|---|---|
| 1 | AWC SIGMET JSON (VA) | `https://aviationweather.gov/api/data/isigmet?format=json&hazard=va` and `/api/data/sigmet?format=json&hazard=va` | 200, `application/json`, 9,895 B / 9,231 B | No | Cache file updates once a minute; API `cache-control: max-age=180` | NWS public domain; AWC: "rate limited to 100 requests per minute" | Low. `isigmet` is marked `deprecated: true`; no CORS; one HTTP 504 in 60 historical calls | `/data/cache/sigmets.cache.json.gz` (once a minute, `max-age=30`) |
| 2 | AWC TAF / METAR JSON | `/api/data/taf?ids=WIII,WARR,WADD,WAAA,RJFK,RJFF,RPLL&format=json` and `/api/data/metar?...` | 200; 7 TAFs (9,100 B), 7 METARs (3,082 B) | No | METAR hourly, TAF 6-hourly; cache files 1 min / 10 min | Same as above | Low | `/data/cache/tafs.cache.xml.gz`, `metars.cache.csv.gz` |
| 3 | MAGMA VONA list (HTML) | `https://magma.esdm.go.id/v1/vona` | 200 HTML, 44,115 B, 15 VONAs per page | No (HTML); JWT for `/api/v1/vona` (401) | Event-driven; 11 VONAs in the 24 h to 18:00Z on 9 Oct | "Copyright 2026 © All Rights Reserved"; `robots.txt`: `User-agent: * / Disallow: /` | **High**: HTML scrape, signed detail URLs (unsigned → 403), F5 WAF cookie, `/v1/vona/rss` → 403 | VONA email subscription (offered on the page); CVGHM content quoted inside Darwin VAAs; ask PVMBG for a token |
| 4 | Tokyo VAAC list + text | `https://ds.data.jma.go.jp/svd/vaac/data/vaac_list.html`, `.../TextData/2026/<date>_<vnum>_<nr>_Text.html` | 200 (117,112 B list; 1,056 B text). `TextData/2026/` directory listing → 403 | No | 158 VAAs from 1 Sep to 8 Oct (34 of 38 days) | JMA Public Data License 1.0, "compatible with ... CC BY 4.0"; must cite and say if edited | Low–medium: HTML list scrape; directory index forbidden | NWS tgftp `fvfe01.rjtd..txt` (latest only) |
| 5 | "Darwin mirror" at JMA | `https://ds.data.jma.go.jp/svd/vaac/data/vaac_darwin_list.html` | 200, 21,797 B, **backup only** (34 rows since 2015) | No | Only when Tokyo backs up Darwin | JMA PDL 1.0 | **Not a live feed** | NWS tgftp `fvau0[1-10].adrm..txt` |
| 6 | Darwin VAAC at BoM | `https://www.bom.gov.au/aviation/volcanic-ash/darwin-va-advisory.shtml` (+ JS POST `/aviation/php/process.php`) | Page 200 (data via JS); `IDD41300/IDD41301` .html/.txt → 404; FTP → 550 | No | Each VAA (≤6 h per active volcano) | BoM forbids scraping; `Disallow: /fwo/` | **High (terms)** | NWS tgftp (public domain) |
| 7 | **NWS tgftp raw VAAs (all VAACs)** | `https://tgftp.nws.noaa.gov/data/raw/fv/` (e.g. `fvau02.adrm..txt`) | 200 `text/plain`, ~0.6–1 KB each; Darwin files modified 19:28Z | No | One file per WMO header, overwritten on each issue | NWS: "public domain ... may be used without charge for any lawful purpose" | Low. Keeps only the latest bulletin per header, so poll ≤5 min | AWC has no VAA endpoint (none listed) |
| 8 | NICT Himawari real-time | `https://himawari8.nict.go.jp/img/D531106/latest.json`; tiles `img/D531106/{n}d/550/YYYY/MM/DD/HHMMSS_x_y.png`; IR `img/FULL_24h/B13/{n}d/550/...` | 200; latest `2026-10-09 19:10:00`, file `PI_H09_...` | No | 10 min | "This web application and data included are **not allowed for commercial uses**" | Medium: undocumented paths; archive patchy (2026-04-01 06Z 404, 2026-05-01 200) | AWS `noaa-himawari9` |
| 9 | JMA MSC real-time JPEGs | `https://www.data.jma.go.jp/mscweb/data/himawari/img/se3/se3_{b13,dst}_HHMM.jpg` | 200 `image/jpeg`, 1101×501, 206–238 KB | No | 10 min, ~13–14 min latency; 23 h ring | JMA PDL 1.0 / CC BY 4.0-compatible | **Date-less file names**: at 19:32Z the "1920" slot still held the 8 Oct frame | JMA bosai dated tiles (below) |
| 10 | JMA bosai Himawari tiles | `https://www.jma.go.jp/bosai/himawari/data/satimg/{T}/fd/{T}/{B13/TBB, DST/ETC, SND/ETC...}/{z}/{x}/{y}.jpg`, index `targetTimes_fd.json` | 200 at z≤5; z6–z9 → 404; 211 timestamps (~35 h) | No | 10 min; tiles kept ~3–4 days | JMA PDL 1.0 | Undocumented; max z5 (~5 km/px) | AWS HSD |
| 11 | **AWS `noaa-himawari9`** | `https://noaa-himawari9.s3.amazonaws.com/?list-type=2&prefix=AHI-L1b-FLDK/2026/10/09/1800/` | 200, 160 objects per 10-min slot (16 bands × 10 segments) | No (anonymous) | 10 min FLDK; files land ~11–14 min after nominal | "NOAA and JMA request attribution ... not permissible to state or imply endorsement" | Low; needs HSD (bz2) decoding | `noaa-himawari8` backup bucket |
| 12 | NASA Worldview snapshot (SO2) | see §3.12 | 200 `image/png`, 14–22 KB; `access-control-allow-origin: *` | No | Daily (polar orbit) | "NASA promotes full and open sharing of data"; GIBS acknowledgement requested | Low; daily only, swath gaps, no TROPOMI layer in GIBS | GIBS WMS (200) |
| 13 | NASA FIRMS | API `/api/area/csv/[MAP_KEY]/...`; public `.../J1_VIIRS_C2_SouthEast_Asia_24h.csv` | API without key → 400 "Invalid MAP_KEY."; public CSV 200, 1.85 MB, 22,275 rows | API: free MAP_KEY; CSV: none | Per overpass | NASA open data | Low | Public 24 h CSV needs no key |
| 14 | adsb.lol point | `https://api.adsb.lol/v2/point/-8.1/112.9/250` | 200, 4,241 B, 7 aircraft, ~0.5–0.9 s | No ("In the future, you will require an API key") | Live | ODbL 1.0; "contact me" for production | Medium: rate limits "dynamic"; key requirement announced | adsb.fi `/v3/lat/.../dist/...` |
| 15 | adsb.fi | `https://opendata.adsb.fi/api/v2/lat/-8.1/lon/112.9/dist/250` | 200, 4,435 B, 7 aircraft | No | Live | "**personal, non-commercial use only** ... You must cite adsb.fi"; 1 req/s | Medium | adsb.lol |
| 16 | airplanes.live | `https://api.airplanes.live/v2/point/-8.1/112.9/250` | **403** JSON: "Please contact us at contact@airplanes.live..." | Effectively yes | — | Non-commercial [REPORTED] | **Dead for us today** | adsb.lol |
| 17 | OpenSky REST | `https://opensky-network.org/api/states/all?lamin=-12&lomin=105&lamax=-4&lomax=120` | 200, 8 states, `x-rate-limit-remaining: 395` | No (anon 400 credits/day) | 10 s resolution anon | "Operational use of the REST API in any live product, service, or automated system also requires a written license" | **High (terms)** | adsb.lol |
| 18 | adsb.lol history | `github.com/adsblol/globe_history_2026` releases | Daily releases exist for 2026-09-06, 09-07, 09-25, 10-08 (3.5–4.2 GB/day) | No | Daily | ODbL 1.0 | Low; large downloads | ADSBx samples (JS index; not inspected) |
| 19 | Open-Meteo pressure-level winds | `https://api.open-meteo.com/v1/forecast?latitude=-8.108&longitude=112.922&hourly=wind_speed_700hPa,...` | 200, 1,204 B | No | Hourly | "only use the free API services for non-commercial purposes"; CC BY 4.0; <10,000/day, 5,000/h, 600/min | Low | NOAA GFS via NOMADS filter (200, GRIB2) or AWS `noaa-gfs-bdp-pds` |
| 20 | Smithsonian GVP weekly | `https://volcano.si.edu/news/WeeklyVolcanoRSS.xml`, `/reports_weekly.cfm` | **403**, Cloudflare page "This Smithsonian site is temporarily unavailable" | — | Weekly | [UNVERIFIED] | Down at check time | Not needed for live loop |
| 21 | JMA volcanic warnings | `https://www.jma.go.jp/bosai/volcano/data/warning.json` | 200, 12,028 B, 14 entries (Japanese labels) | No | Event-driven | JMA PDL 1.0 | Undocumented JSON | JMA VAAC text |
| 22 | GeoNet VAL | `https://api.geonet.org.nz/volcano/val` | 200 GeoJSON, 3,074 B | No | Event-driven | [UNVERIFIED] | Low | — |
| 23 | KVERT | `http://kvert.febras.net/` (old `kscnet.ru` URLs redirect or time out) | 200 HTML | No | Event-driven | [UNVERIFIED] | HTML only | Tokyo VAAC covers Kamchatka |
| 24 | PHIVOLCS bulletins | `https://www.phivolcs.dost.gov.ph/` (200); guessed bulletin paths → 404 | Bulletin URL not found | — | Daily | [UNVERIFIED] | Unknown | Tokyo VAAC Taal/Mayon/Kanlaon VAAs |
| 25 | BMKG aviation VA map JSON | `https://web-aviation.bmkg.go.id/va-map.php?data=1` | **403 Cloudflare managed challenge** (`cf-mitigated: challenge`) | — | — | — | **Unusable server-side** | AWC SIGMET |

---

## 3. Feed-by-feed detail

### 3.1 aviationweather.gov SIGMETs (the spine)

- **URL and status.** `https://aviationweather.gov/api/data/isigmet?format=json&hazard=va` → HTTP 200, `application/json; charset=utf-8`, 9,895 bytes, `cache-control: max-age=180`, served via Azure Front Door (`x-azure-ref`) [CONFIRMED: https://aviationweather.gov/api/data/isigmet?format=json&hazard=va, accessed 2026-10-10]. The general `https://aviationweather.gov/api/data/isigmet?format=json` → 200, 139,904 bytes, 164 records: TS 94, TURB 37, ICE 13, VA 11, TC 9 [CONFIRMED: https://aviationweather.gov/api/data/isigmet?format=json, accessed 2026-10-10].
- **Deprecation.** The OpenAPI spec (v4.0) marks `/api/data/isigmet` as `deprecated: true` and offers `/api/data/sigmet`, described as "Decoded SIGMETs. This includes SIGMETs issued by the United States in domestic format ... and international SIGMETs", with the same `hazard=va` filter and a `date` parameter [CONFIRMED: https://aviationweather.gov/data/schema/openapi.yaml, accessed 2026-10-10]. `/api/data/sigmet?format=json&hazard=va` → 200, 9,231 bytes, `cache-control: max-age=180` [CONFIRMED: https://aviationweather.gov/api/data/sigmet?format=json&hazard=va, accessed 2026-10-10]. GeoJSON (`format=geojson`) also returned 200 [CONFIRMED: https://aviationweather.gov/api/data/sigmet?format=geojson&hazard=va, accessed 2026-10-10].
- **VA SIGMETs open at 19:27 UTC on 9 Oct (00:57 IST 10 Oct).** 13 records = **9 distinct SIGMETs**. Records with an `F` suffix (A4F, A5F, 1F, 3F) carry the same `rawSigmet` as their parent and hold the forecast polygon, so counting records over-counts [CONFIRMED: https://aviationweather.gov/api/data/isigmet?format=json&hazard=va, accessed 2026-10-10].

  | FIR | Series | Volcano | Valid (UTC) | Layer | Movement |
  |---|---|---|---|---|---|
  | WAAF Ujung Pandang | 10 | Ibu | 09 1330–1930 | SFC/FL070 | E 10 kt, NC |
  | WAAF Ujung Pandang | 11 | Dukono | 09 1550–2150 | SFC/FL070 | NE 10 kt, NC |
  | WAAF Ujung Pandang | 12 | Semeru | 09 1820–10 0020 | SFC/FL150 | E 10 kt, NC |
  | WIIF Jakarta | 07 | Krakatau | 09 1615–2215 | SFC/FL060 | W 05 kt, NC |
  | MHTG Central American | A4 (expiring 1926), A5 | Fuego | to 10 0100 | SFC/FL140 | S/SE |
  | MHTG Central American | 1 | Masaya | to 10 0032 | to 5,000 ft | SW |
  | SKED Bogota | A3 | Puracé | to 2200 | SFC/20,000 ft | NW |
  | SEFG Guayaquil | 3 | Reventador | to 2254 | to 14,000 ft | NW |

  **Asia-Pacific: 4 open, all Indonesian (WAAF ×3, WIIF ×1). No Fukuoka (RJJJ) or Manila (RPHI) VA SIGMET was open at this moment.** Tokyo VAAC's home page agreed: "There is no currently announced volcanic ash Advisories" (updated 19:00 UTC) [CONFIRMED: https://ds.data.jma.go.jp/svd/vaac/data/, accessed 2026-10-10].
- **Sample (trimmed), Semeru:**
  ```
  WVID21 WAAA 091820
  WAAF SIGMET 12 VALID 091820/100020 WAAA-
  WAAF UJUNG PANDANG  FIR VA
  ERUPTION MT SEMERU PSN S0806 E11255 VA CLD OBS AT 1800Z WI S0803
  E11253 - S0754 E11316 - S0807 E11324 - S0820 E11318 - S0811 E11253 -
  S0803 E11253 SFC/FL150 MOV E 10KT NC=
  ```
  JSON fields per record include `icaoId, firId, firName, receiptTime, validTimeFrom, validTimeTo, seriesId, hazard, qualifier, base, top, geom, coords[{lat,lon}], dir, spd, chng, rawSigmet`; the cache file adds `issueTime` and `sigmetType` (`OBS`/`FCST`) [CONFIRMED: https://aviationweather.gov/data/cache/sigmets.cache.json.gz, accessed 2026-10-10].
- **History for replay.** The `date` parameter works for the last 30 days: `date=20260925_1200` → 200 with 13 records; `date=20260907_0600` → 400 `{"status":"error","error":"Data is available for up to 30 days for date"}` [CONFIRMED: https://aviationweather.gov/api/data/sigmet?format=json&hazard=va&date=20260907_0600, accessed 2026-10-10]. So **the 7 Sep Anak Krakatau closure day is already outside the window**, and 25 Sep will drop out around 25 Oct (derived).
- **25 Sep check of the brief's example.** The 25 Sep 11:20Z Semeru SIGMET reads "SFC/FL150 MOV SE 10KT NC", matching the brief's "surface to 15,000 ft moving south-east"; RJJJ SIGMET A01 for Sakurajima (0604Z) was also open [CONFIRMED: https://aviationweather.gov/api/data/sigmet?format=json&hazard=va&date=20260925_1200, accessed 2026-10-10]. Distinct VA SIGMETs at 25 Sep 12:00Z: 10 worldwide, 5 in Asia-Pacific (RJJJ A01; WAAF 07 Dukono, 10 Ibu, 11 Lewotolok, 12 Semeru) (derived).
- **30-day availability sample (derived).** 60 calls to `/api/data/sigmet?format=json&hazard=va&date=…` every 12 h from 2026-09-10 06Z to 2026-10-09 18Z: 59 returned 200, one returned **HTTP 504 Gateway Time-out** (2026-10-08 18Z). In all 59, at least one WAAF VA SIGMET was open; distinct Asia-Pacific VA SIGMETs per sample ranged 3–11. FIRs seen: WAAF 59/59, RJJJ 25, RPHI 13, WIIF 12, UHMM 4, AYPM 3, PAZA 3, NFFF 2 [CONFIRMED: https://aviationweather.gov/api/data/sigmet?format=json&hazard=va&date=20261008_1800 (504) and the other 59 dated calls, accessed 2026-10-10]. The tier review's "11 open VA SIGMETs on 8 October" is plausible only as a **record** count; my 8 Oct 06Z sample had 7 distinct (5 Asia-Pacific: RJJJ and WAAF) (derived).
- **Rate limits and rules (quoted).** "All requests are rate limited to 100 requests per minute." "Most endpoints return a maximum of 400 entries." "**Cross-origin resource sharing is not permitted at this time.**" "Set a custom user agent to prevent automated filtering inadvertently blocking valid traffic." "Undocumented query parameter requests are restricted and will result in an error." "The weather database currently allows access to up to the previous 30 days of data." [CONFIRMED: https://aviationweather.gov/data/api/, accessed 2026-10-10]. The docs page's `termsOfService` points back to `/data/api/` [CONFIRMED: https://aviationweather.gov/data/schema/openapi.yaml, accessed 2026-10-10].
- **Cadence.** Cache file "/data/cache/sigmets.cache.json.gz — All current SIGMETs (JSON) — Once a minute" [CONFIRMED: https://aviationweather.gov/data/api/, accessed 2026-10-10]; its `last-modified` was 19:55:41 for a 19:55:44 request and `cache-control: max-age=30` [CONFIRMED: https://aviationweather.gov/data/cache/sigmets.cache.json.gz, accessed 2026-10-10]. The API endpoint is cached 180 s, so polling it every 60 s, as the board card says, mostly returns cached data; **poll the cache file for 60-s freshness** (judgement).
- **Licence.** NWS: "The information on National Weather Service (NWS) Web pages are in the public domain, unless specifically noted otherwise, and may be used without charge for any lawful purpose so long as you do not: 1) claim it is your own ... 2) use it in a manner that implies an endorsement ... or 3) modify its content and then present it as official government material." [CONFIRMED: https://www.weather.gov/disclaimer, accessed 2026-10-10]. The AWC page carries a US-government system-use banner [CONFIRMED: https://aviationweather.gov/data/api/, accessed 2026-10-10].
- **How it breaks.** 429 above 100/min; 504 (seen once); 400 for undocumented params; no CORS, so the browser cannot call it directly; `isigmet` may be removed. Fix: server-side poller on the cache file, User-Agent set, last-good cache.

### 3.2 aviationweather.gov TAF and METAR

- `https://aviationweather.gov/api/data/taf?ids=WIII,WARR,WADD,WAAA,RJFK,RJFF,RPLL&format=json` → 200, 9,100 bytes, 7 TAFs [CONFIRMED: https://aviationweather.gov/api/data/taf?ids=WIII,WARR,WADD,WAAA,RJFK,RJFF,RPLL&format=json, accessed 2026-10-10]. `.../metar?ids=...&format=json` → 200, 3,082 bytes, 7 METARs [CONFIRMED: https://aviationweather.gov/api/data/metar?ids=WIII,WARR,WADD,WAAA,RJFK,RJFF,RPLL&format=json, accessed 2026-10-10].
- Sample:
  ```
  TAF WARR 091700Z 0918/1018 26005KT 4000 HZ FEW020 BECMG 1000/1002 10010KT 9999 NSW
  TAF WIII 091700Z 0918/1100 19005KT 6000 SCT020 BECMG 0921/0923 4000 HZ BECMG 1001/1003 35010KT 8000 NSW ...
  METAR WARR 091900Z 24002KT 5000 HZ FEW020 27/23 Q1010 NOSIG
  METAR WAAA 091900Z VRB01KT 5000 HZ FEW020 22/20 Q1010 NOSIG
  METAR RJFK 091200Z 10011KT 060V130 9999 FEW030 SCT130 23/18 Q1020
  ```
  JSON TAF fields: `icaoId, dbPopTime, bulletinTime, issueTime, validTimeFrom, validTimeTo, rawTAF, mostRecent, remarks, lat, lon, elev, prior, name` (e.g. "Surabaya/Juanda Intl").
- Note: RJFK's latest METAR in the API was 1200Z while others were 1900Z (RJFK is not a 24-h station or the feed lagged) [CONFIRMED: same URL]. No TAF/METAR mentions VA today (derived). Cache files: TAFs "Every 10 minutes", METARs "Once a minute" [CONFIRMED: https://aviationweather.gov/data/api/, accessed 2026-10-10].

### 3.3 MAGMA Indonesia VONA

- **List page.** `https://magma.esdm.go.id/v1/vona` → 200 `text/html; charset=UTF-8`, 44,115 bytes, 15 VONAs per page, paged with `?page=2` (200, 44,849 bytes) and filterable with `?code=SMR` (200) [CONFIRMED: https://magma.esdm.go.id/v1/vona, accessed 2026-10-10]. The pager showed 1,243 pages and per-volcano archive counts, e.g. "Semeru (10189)", "Ibu (3064)", "Lewotobi Laki-laki (1568)", "Dukono (1198)", "Anak Krakatau (601)" [CONFIRMED: same URL].
- **Sample (list page text, trimmed):**
  ```
  2026-10-09 18:00:00 UTC
  Orange
  Semeru - 20261009/1800Z
  Agastya Rajendra, Semeru Volcano Observatory - 1 hour ago
  Eruption at 1800 UTC (0100 local). Ash-cloud is not observed. Ash-cloud is not observed..
  2026-10-09 11:44:00 UTC
  Orange
  Anak Krakatau - 20261009/1144Z
  Eruption at 1144 UTC (1844 local). Ash-cloud is not observed. ...
  2026-10-09 01:37:00 UTC
  Orange
  Ibu - 20261009/0137Z
  Eruption with volcanic ash cloud at 0137 UTC (1037 local). Best estimate of ash-cloud top is around
  5520 FT (1725 M) above sea level or 1280 FT (400 M) above summit. ... Source of height data:
  ground observer. Ash cloud moving to east. ...
  2026-10-08 21:03:00 UTC
  Orange
  Semeru - 20261008/2103Z
  ... ash-cloud top is around 14003 FT (4376 M) above sea level ... Ash cloud moving to north. ...
  ```
  In the 24 h to 18:00Z on 9 Oct the list held 11 VONAs (9 Semeru, 1 Anak Krakatau, 1 Ibu) (derived).
- **Detail page.** `https://magma.esdm.go.id/v1/vona/22889?signature=5412ce61...` → 200, 15,035 bytes, structured fields: Issued 20261009/1800Z; Volcano "Semeru (263300)"; Current Aviation Colour Code ORANGE; Notice Number "2026SMR1920"; Summit Elevation "11763 FT (3676 M)"; Volcanic Cloud Height "Ash-cloud is not observed." The same URL without `?signature=` → **403** [CONFIRMED: https://magma.esdm.go.id/v1/vona, accessed 2026-10-10 (links taken from it)]. Detail links are Laravel-style signed URLs, so a poller must scrape the list page to get them (judgement).
- **JSON API.** `https://magma.esdm.go.id/api/v1/vona` and `/api/v1/vona/latest` → **401**, body `{"message": "Token not provided"}`, header `WWW-Authenticate: jwt-auth`, `X-RateLimit-Limit: 90` [CONFIRMED: https://magma.esdm.go.id/api/v1/vona, accessed 2026-10-10]. `/api/v1/home/vona`, `/api/v1/python/magma-var/latest`, `/rss`, `/feed` → 404; `/v1/vona/rss` → 403 "Forbidden" [CONFIRMED: https://magma.esdm.go.id/v1/vona/rss, accessed 2026-10-10]. **The pack's "JSON API returns 401" is confirmed.**
- **Terms.** `robots.txt` (26 bytes): `User-agent: *` / `Disallow: /` [CONFIRMED: https://magma.esdm.go.id/robots.txt, accessed 2026-10-10]. Footer: "Copyright 2026 © All Rights Reserved. MAGMA Indonesia" [CONFIRMED: https://magma.esdm.go.id/v1/vona, accessed 2026-10-10]. The page also says: "The reports are disseminated via email to national and international stakeholders in the aviation sector. Other interested parties can avail of them through email subscription. All notifications are publicly available online." [CONFIRMED: same URL]. A third-party project says MAGMA CCTV images are CC BY-NC-ND 4.0 [REPORTED: https://github.com/abah/PantauErupsi].
- **Related pages.** `/v1/gunung-api/tingkat-aktivitas` (200, 48,765 B) and `/v1/gunung-api/informasi-letusan` (200, 49,503 B) are HTML [CONFIRMED: https://magma.esdm.go.id/v1/gunung-api/tingkat-aktivitas, accessed 2026-10-10]. `https://vsi.esdm.go.id/` → 200 HTML [CONFIRMED: https://vsi.esdm.go.id/, accessed 2026-10-10]. An unofficial Python scraper of `tingkat-aktivitas` exists [REPORTED: https://github.com/Gabrielbjb/Magma-Indonesia-API].
- **How it breaks.** HTML layout change; F5 WAF cookie (`TSab544faa027`) may challenge data-centre IPs such as Cloud Run [UNVERIFIED: not tested from Cloud Run]; signed detail links; robots.txt disallows crawling.
- **Alternates.** (a) Subscribe to VONA email and ingest mail (the page offers it). (b) Darwin VAAs already cite "INFO SOURCE: HIMAWARI-9, CVGHM" and quote CVGHM ("CVGHM INDICATE DISCRETE ERUPTIONS ARE ONGOING") [CONFIRMED: https://tgftp.nws.noaa.gov/data/raw/fv/fvau03.adrm..txt, accessed 2026-10-10]. (c) Ask PVMBG for an API token. (d) BMKG's aviation VA JSON is behind a Cloudflare managed challenge (403, `cf-mitigated: challenge`) [CONFIRMED: https://web-aviation.bmkg.go.id/va-map.php?data=1, accessed 2026-10-10], so it is not an alternate.

### 3.4 Tokyo VAAC (JMA)

- Index `https://ds.data.jma.go.jp/svd/vaac/data/` → 200, 4,913 bytes; "Updated at 19:00 UTC, 09 October 2026 ... There is no currently announced volcanic ash Advisories." Also notes "VAGNFR (Discontinued on Nov. 28, 2024)" [CONFIRMED: https://ds.data.jma.go.jp/svd/vaac/data/, accessed 2026-10-10].
- List `https://ds.data.jma.go.jp/svd/vaac/data/vaac_list.html` → 200, 117,112 bytes, 158 rows from 2026-09-01 03:17 to 2026-10-08 17:50 UTC: Sakurajima 96, Sheveluch 22, Mayon 19, Chikurachki 7, Kanlaon 7, Taal 4, Alaid 2, Krasheninnikov 1 (derived from the page). Advisories were issued on 34 of the 38 days; max 15 in a day (derived). Newest: Taal 2026/24 at 17:50Z 8 Oct; Sakurajima 2026/279 at 11:50Z 8 Oct [CONFIRMED: https://ds.data.jma.go.jp/svd/vaac/data/vaac_list.html, accessed 2026-10-10].
- Text pattern `TextData/2026/YYYYMMDD_<GVP number+suffix>_<advisory nr>_Text.html`; the 25 Sep Sakurajima advisory exists and reads (trimmed):
  ```
  FVFE01 RJTD 251252
  VA ADVISORY
  DTG: 20260925/1252Z
  VAAC: TOKYO
  VOLCANO: SAKURAJIMA (AIRA CALDERA) 282080
  ADVISORY NR: 2026/249
  INFO SOURCE: JMA HIMAWARI-9
  ERUPTION DETAILS: ERUPTED AT 20260925/1236Z FL080 EXTD E
  OBS VA CLD: VA NOT IDENTIFIABLE FM SATELLITE DATA WIND FL080 240/11KT
  FCST VA CLD +6 HR: NOT AVBL
  RMK: WE WILL ISSUE FURTHER ADVISORY IF VA IS DETECTED IN SATELLITE IMAGERY.
  NXT ADVISORY: NO FURTHER ADVISORIES=
  ```
  [CONFIRMED: https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20260925_28208001_0249_Text.html, accessed 2026-10-10]. **The brief's event "VA NOT IDENTIFIABLE FM SATELLITE DATA" is confirmed word for word.**
- `https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/` (directory listing) → **403** [CONFIRMED: that URL, accessed 2026-10-10]; individual files must be found from the list page. `ds.data.jma.go.jp/robots.txt` → 404 (no crawler policy) [CONFIRMED: https://ds.data.jma.go.jp/robots.txt, accessed 2026-10-10].
- Graphic/forecast pages follow `VAGFN/2026/html/YYYYMMDD_<vnum>_<nr>_QH21.html` [CONFIRMED: https://ds.data.jma.go.jp/svd/vaac/data/vaac_list.html, accessed 2026-10-10].
- **Licence (quoted).** "Information made available on the Japan Meteorological Agency website ... may be used in accordance with the terms and conditions of use stipulated in Public Data License (Version 1.0)"; "The user must cite the source"; edited content needs a statement that it was edited and must not be presented "in a format that may be misconstrued as having been created by the Government of Japan"; "The Terms of Use are compatible with the Creative Commons Attribution License 4.0"; and "The use of Content may be restricted by the Meteorological Service Act", citing the Article 17 licence for forecasting services "for intended provision of meteorological services in Japan" [CONFIRMED: https://www.jma.go.jp/jma/en/copyright.html, accessed 2026-10-10].

### 3.5 The "JMA mirror of Darwin VAAC" is a backup page, not a mirror

- `https://ds.data.jma.go.jp/svd/vaac/data/vaac_darwin_list.html` → 200, 21,797 bytes, titled "Volcanic Ash Advisories (Darwin VAAC Backup)", "Updated at 00:00 UTC, 01 October 2026". It lists **34 rows from 2015-11-25 to 2026-09-23**, most of them exercises (volcano number `99999902`); the only real 2026 entries are Dukono 2026/788 (14:50Z 23 Sep) and Ibu 2026/1081 (14:19Z 23 Sep) [CONFIRMED: https://ds.data.jma.go.jp/svd/vaac/data/vaac_darwin_list.html, accessed 2026-10-10].
- So the brief's "Darwin VAAC Ibu advisory numbered 2026/1081" is real, but it was issued by Tokyo while backing up Darwin on 23 Sep. The NWS directory shows `fvau09.adrm` and `fvau10.adrm` last modified 23-Sep-2026 14:37 and 15:32 [CONFIRMED: https://tgftp.nws.noaa.gov/data/raw/fv/, accessed 2026-10-10], consistent with a Darwin backup episode that day [UNVERIFIED: interpretation].
- **The page cannot be used as the live Darwin feed.** Use §3.7.

### 3.6 Darwin VAAC at the Bureau of Meteorology

- `http://www.bom.gov.au/aviation/volcanic-ash/` → redirects to https, 200, 45,756 bytes, a JS-driven page [CONFIRMED: https://www.bom.gov.au/aviation/volcanic-ash/, accessed 2026-10-10]. It states: "By entering this site, you acknowledge that this information is produced solely for use by the aviation industry, and you are aware that any information for the purposes of flight planning should be obtained from Airservices Australia." [CONFIRMED: same URL].
- `darwin-va-advisory.shtml` → 200; its static HTML holds a **hidden** default div "Nil current Darwin Volcanic Ash Advisories." (`style="display:none;"`); real content is loaded by `va.js`, which POSTs `{page: "volcanic-ash-darwin", javascript: 1}` to `/aviation/php/process.php` [CONFIRMED: https://www.bom.gov.au/aviation/volcanic-ash/darwin-va-advisory.shtml, accessed 2026-10-10]. That POST returned `{"total":5,...}` with Dukono, Ibu, Semeru, Krakatau and **Manam (PNG)**, each with a graphic such as `IDY65295.png` (Semeru), and `https://www.bom.gov.au/fwo/IDY65295.png` returned 200 `image/png`, 118,394 bytes [CONFIRMED: https://www.bom.gov.au/aviation/php/process.php, accessed 2026-10-10]. This endpoint is undocumented (judgement).
- The pack's text products **IDD41300 / IDD41301 do not resolve**: `/fwo/IDD41300.html`, `/fwo/IDD41301.html`, `/fwo/IDD41300.txt` → 404; `ftp://ftp.bom.gov.au/anon/gen/fwo/IDD41300.txt` → FTP 550 [CONFIRMED: https://www.bom.gov.au/fwo/IDD41300.txt, accessed 2026-10-10]. A web search found no page that mentions these IDs (not found after 1 search; query in log). `darwin-graphical-va-advisory.shtml` → 404 [CONFIRMED: https://www.bom.gov.au/aviation/volcanic-ash/darwin-graphical-va-advisory.shtml, accessed 2026-10-10].
- **Terms (quoted).** "Unless we state otherwise, you can download, copy and use our content for personal use, or use within your organisation. You must not supply it to any other person or use it for any commercial purpose." and "we do not allow you to use automated or manual techniques to hack, scrape or otherwise extract material from our site." [CONFIRMED: https://www.bom.gov.au/copyright, accessed 2026-10-10]. `robots.txt` contains `Disallow: /fwo/` (twice) [CONFIRMED: https://www.bom.gov.au/robots.txt, accessed 2026-10-10].
- **Verdict:** do not poll BoM. Use NWS tgftp (§3.7); link to the BoM page for humans.

### 3.7 NWS tgftp raw volcanic ash advisories (the clean VAAC source)

- `https://tgftp.nws.noaa.gov/data/raw/fv/` → 200, 9,292-byte Apache index listing one file per WMO heading: Darwin `fvau01..10.adrm..txt`, Tokyo `fvfe01.rjtd..txt`, Washington `fvxx20..27.knes..txt`, Anchorage `fvak2x.pawu...`, Wellington `fvps0x.nzkl..txt`, London `fvxx0x.egrr`, Toulouse `fvxx0x.lfpw`, Buenos Aires `fvag0x.sabm`, Montreal `fvcn0x.cwao` [CONFIRMED: https://tgftp.nws.noaa.gov/data/raw/fv/, accessed 2026-10-10]. Latest modifications: Darwin `fvau03.adrm` 09-Oct-2026 19:28; Tokyo `fvfe01.rjtd` 08-Oct-2026 17:50; Washington `fvxx20.knes` 09-Oct-2026 18:56; Anchorage `fvak21.pawu.vaa.ak1` 01-Oct-2026 16:58; Wellington `fvps01.nzkl` 19-Sep-2026 22:41 [CONFIRMED: same URL].
- `fvau02.adrm..txt` → 200 `text/plain; charset=utf-8`, 1,035 bytes, `Last-Modified: Fri, 09 Oct 2026 18:17:03 GMT`, `Cache-Control: no-cache, private`. Sample:
  ```
  FVAU02 ADRM 091820
  VA ADVISORY
  DTG: 20261009/1820Z
  VAAC: DARWIN
  VOLCANO: SEMERU 263300
  ADVISORY NR: 2026/1157
  INFO SOURCE: HIMAWARI-9, CVGHM
  ERUPTION DETAILS: VA TO FL150 OBS AT 09/1800Z, MOV E
  OBS VA CLD: SFC/FL150 S0803 E11253 - S0754 E11316 - S0807
          E11324 - S0820 E11318 - S0811 E11253 MOV E 10KT
  FCST VA CLD +6 HR: 10/0000Z SFC/FL150 S0803 E11253 - S0753
          E11317 - S0807 E11324 - S0821 E11318 - S0811 E11253
  RMK: VA IDENTIFIABLE ON CURRENT SATELLITE IMAGERY MOVING
          EAST. DISCRETE EMISSIONS ARE ONGOING. AREA IS PARTIALLY
          OBSCURED BY MET CLOUD. HEIGHT AND MOVEMENT BASED ON
          SATELLITE IMAGERY, GROUND REPORTS AND MODEL GUIDANCE.
  NXT ADVISORY: NO LATER THAN 20261010/0020Z=
  ```
  [CONFIRMED: https://tgftp.nws.noaa.gov/data/raw/fv/fvau02.adrm..txt, accessed 2026-10-10].
- Other live Darwin advisories: Dukono 2026/855 (1550Z, SFC/FL070 MOV NE) [CONFIRMED: https://tgftp.nws.noaa.gov/data/raw/fv/fvau01.adrm..txt, accessed 2026-10-10]; Ibu 2026/1148 (1930Z, SFC/FL070 MOV E) [CONFIRMED: https://tgftp.nws.noaa.gov/data/raw/fv/fvau03.adrm..txt, accessed 2026-10-10]; Krakatau 2026/225 (1615Z, SFC/FL060 MOV W, "+12 HR: NO VA EXP") [CONFIRMED: https://tgftp.nws.noaa.gov/data/raw/fv/fvau04.adrm..txt, accessed 2026-10-10]. Darwin's 2026 numbering for these four volcanoes alone sums to 3,385 advisories so far (derived). **Ibu has moved from 2026/1081 (23 Sep, per the pack) to 2026/1148.**
- Tokyo's latest: Taal 2026/24, "VA NOT IDENTIFIABLE FM SATELLITE DATA WIND FL180 060/9KT" [CONFIRMED: https://tgftp.nws.noaa.gov/data/raw/fv/fvfe01.rjtd..txt, accessed 2026-10-10]. Washington's latest: Fuego 2026/1180, "EST VA CLD: SFC/FL140" [CONFIRMED: https://tgftp.nws.noaa.gov/data/raw/fv/fvxx20.knes..txt, accessed 2026-10-10]. Wellington's latest: Ambrym 2026/8, 19 Sep [CONFIRMED: https://tgftp.nws.noaa.gov/data/raw/fv/fvps01.nzkl..txt, accessed 2026-10-10]. Anchorage: Gareloi 2026/001, 1 Oct [CONFIRMED: https://tgftp.nws.noaa.gov/data/raw/fv/fvak21.pawu.vaa.ak1.txt, accessed 2026-10-10].
- **Terms.** NWS public domain (quoted in §3.1) [CONFIRMED: https://www.weather.gov/disclaimer, accessed 2026-10-10]. NWS guidance: "If you are querying a service for short fused warnings it may make sense to query our service once or twice a minute" [CONFIRMED: same URL].
- **How it breaks.** Each file is overwritten by the next advisory under the same heading, so an advisory can be missed if two are issued under one heading between polls; the Tokyo list page (§3.4) is the history backstop for Tokyo; for Darwin there is no public history (judgement). The server sets a 600-s session cookie on every response [CONFIRMED: response headers, same URLs].

### 3.8 Himawari imagery: NICT

- `https://himawari8.nict.go.jp/img/D531106/latest.json` → 200 `application/json`, 83 bytes: `{"date":"2026-10-09 19:10:00","file":"PI_H09_20261009_1910_TRC_FLDK_R10_PGPFD.png"}` (H09 = Himawari-9) [CONFIRMED: https://himawari8.nict.go.jp/img/D531106/latest.json, accessed 2026-10-10]. `img/FULL_24h/latest.json` → `{"date":"2026-10-09 19:10:00"}` [CONFIRMED: https://himawari8.nict.go.jp/img/FULL_24h/latest.json, accessed 2026-10-10]. The `himawari8-dl.nict.go.jp/himawari8/...` host also answers [CONFIRMED: https://himawari8-dl.nict.go.jp/himawari8/img/D531106/latest.json, accessed 2026-10-10].
- **Tile pattern** (from `js/env.js` and `js/himawari8-image.js`): `img/D531106/{n}d/550/{YYYY/MM/DD/HHMMSS}_{x}_{y}.png` for true colour; `img/FULL_24h/{band}/{n}d/550/...` for bands B01–B16, default `B13`; scales `n` = 1, 2, 4, 8, 16, 20 [CONFIRMED: https://himawari8.nict.go.jp/js/env.js, accessed 2026-10-10]. Tested: `D531106/1d/.../191000_0_0.png` → 200 (154,220 B); `FULL_24h/B13/8d/550/2026/10/09/180000_1_4.png` → 200 (51,602 B, mode LA = grey + alpha, i.e. a cloud overlay on Blue Marble, not a raw brightness-temperature image); `FULL_24h/B13/20d/...` → 404 [CONFIRMED: https://himawari8.nict.go.jp/img/FULL_24h/B13/8d/550/2026/10/09/180000_1_4.png, accessed 2026-10-10]. The 8d true-colour tile 1_4 shows the Sunda Strait and west Java (inspected).
- **Archive.** `oldestDate: new Date("2015-07-07T01:50:00Z")` in env.js, but tests at 06:00Z were patchy: 2026-09-07, 09-25, 10-01, 06-01, 05-01, 03-01 → 200; 2026-04-01, 02-01, 01-01, 2025-10-09, 2025-07-01, 2016-01-01 → 404 [CONFIRMED: https://himawari8.nict.go.jp/img/D531106/1d/550/2026/09/07/060000_0_0.png and siblings, accessed 2026-10-10]. **The 7 Sep 2026 Anak Krakatau day is available** (true colour and B13 8d).
- **Terms (quoted).** "This web application and data included are not allowed for commercial uses. Both graphic and numerical data (24 hours after observation) are accessible through the WSDBank (World Science Data Bank) on the NICT Science Cloud." [CONFIRMED: https://himawari8.nict.go.jp/himawari8-help.htm, accessed 2026-10-10]. The "about" page says only "in preparation" [CONFIRMED: https://himawari8.nict.go.jp/himawari8-about.htm, accessed 2026-10-10].
- **How it breaks.** Undocumented paths (a 2021 app, `appVersion: "6.4.1n"`); tiles 404 if requested before they are rendered; non-commercial clause.

### 3.9 Himawari imagery: JMA

- **MSC real-time JPEGs (the pack's "se3").** Page `https://www.data.jma.go.jp/mscweb/data/himawari/sat_img.php?area=se3` → 200; area codes include `se1, se2, se3, se4, ha1–ha6, hp1–hp3, jpn, fd_`; band codes include `b13` "B13 (Infrared)", `dst` "Dust RGB", `ngt` "Night Microphysics RGB", `snd` "Sandwich", `tre` "True Color RGB (Enhanced)"; animation choices top out at "Last 23 Hours" (135 frames) [CONFIRMED: https://www.data.jma.go.jp/mscweb/data/himawari/sat_img.php?area=se3, accessed 2026-10-10]. URL rule from `sat_img.js`: `"img/" + area + "/" + area + "_" + element + "_" + time + ".jpg"` [CONFIRMED: https://www.data.jma.go.jp/mscweb/data/himawari/sat_img.js, accessed 2026-10-10]. `img/se3/se3_b13_1920.jpg` → 200 `image/jpeg`, 206,851 B, 1101×501; `se3_dst_1920.jpg` → 200, 237,796 B [CONFIRMED: https://www.data.jma.go.jp/mscweb/data/himawari/img/se3/se3_dst_1920.jpg, accessed 2026-10-10].
- **Stale-frame trap (confirmed).** File names carry only HHMM. At 19:32Z: `se3_dst_1910.jpg` Last-Modified 09 Oct 19:23:43; `se3_dst_1920.jpg` Last-Modified **08 Oct 19:33:42** (and CloudFront `Hit`, `max-age=600`), although the page already listed "19:20 UTC 09 October 2026" [CONFIRMED: https://www.data.jma.go.jp/mscweb/data/himawari/img/se3/se3_dst_1920.jpg, accessed 2026-10-10]. The burned-in label of that frame read "08.OCT.2026 19:30UTC"; labels run 10 min after the file slot (the 1910 file is labelled 19:20UTC) (inspected). **A poller that trusts the slot name can serve a 24-hour-old frame. Check `Last-Modified` or use dated tiles.**
- **Resolution.** The se3 frame has a 10° graticule about 200 px apart, so about 20 px per degree, roughly 5.5 km per pixel (derived by inspection). The Semeru SIGMET polygon (112.88–113.40°E, 7.90–8.33°S) covers roughly 10 × 9 pixels (derived). The hi-res areas `ha1–ha6` did not cover Java or Halmahera on inspection (`ha6` shows Flores/Timor) (inspected). No ash plume was visible to me at whole-frame scale over Semeru or Ibu at 19:10Z (night) (inspected; judgement).
- **bosai tiles (dated, better for polling).** `https://www.jma.go.jp/bosai/himawari/data/satimg/targetTimes_fd.json` → 200, 211 timestamps from 2026-10-08 07:30 to 2026-10-09 19:20 UTC [CONFIRMED: that URL, accessed 2026-10-10]. Tiles `.../satimg/20261009190000/fd/20261009190000/{B13/TBB, DST/ETC, SND/ETC, B03/ALBD, B08/TBB, REP/ETC}/5/26/16.jpg` → all 200, 256-px JPEGs; z6–z9 → 404; a 2026-10-06 tile → 200; 2026-10-01 → 404 [CONFIRMED: https://www.jma.go.jp/bosai/himawari/data/satimg/20261009190000/fd/20261009190000/DST/ETC/5/26/16.jpg, accessed 2026-10-10]. z5 = 256 px per 11.25°, about 23 px per degree (derived). `https://www.jma.go.jp/bosai/himawari/` itself → 404 [CONFIRMED: that URL, accessed 2026-10-10].
- **Satellite status.** Himawari-9 is the operational imager: NICT and AWS file names use `H09`, and every VAA today cites "HIMAWARI-9" [CONFIRMED: https://tgftp.nws.noaa.gov/data/raw/fv/fvau02.adrm..txt, accessed 2026-10-10]. JMA's operations bulletin lists routine cancellations, e.g. "East-west station keeping maneuver for Himawari-9 on 9 October, 2026 ... the following observation will be cancelled: 11:10 UTC(P067)" [CONFIRMED: https://ds.data.jma.go.jp/mscweb/en/oper/opr_bulletin_H9.html, accessed 2026-10-10]. Himawari-10 launch is reported delayed to FY2030 [REPORTED: https://en.wikipedia.org/wiki/Himawari_(satellites)]; it plays no part before Dec 2026.

### 3.10 Himawari imagery: NOAA on AWS (open, full resolution)

- `https://noaa-himawari9.s3.amazonaws.com/?list-type=2&delimiter=/` → 200; prefixes `AHI-L1b-FLDK/`, `AHI-L1b-Japan/`, `AHI-L1b-Target/`, `AHI-L2-FLDK-Clouds/`, `AHI-L2-FLDK-ISatSS/`, `AHI-L2-FLDK-Winds/` [CONFIRMED: https://noaa-himawari9.s3.amazonaws.com/?list-type=2&delimiter=/&max-keys=50, accessed 2026-10-10].
- One 10-min slot (`AHI-L1b-FLDK/2026/10/09/1800/`) holds 160 objects; example keys and sizes:
  ```
  HS_H09_20261009_1800_B11_FLDK_R20_S0110.DAT.bz2 1231376 2026-10-09T18:11:46Z
  HS_H09_20261009_1800_B13_FLDK_R20_S0510.DAT.bz2 3014537 2026-10-09T18:12:03Z
  HS_H09_20261009_1800_B14_FLDK_R20_S0710.DAT.bz2 2657611 2026-10-09T18:12:59Z
  HS_H09_20261009_1800_B15_FLDK_R20_S0810.DAT.bz2 2342727 2026-10-09T18:13:01Z
  ```
  Naming: `HS_H09_{YYYYMMDD}_{HHMM}_B{band}_FLDK_R{res}_S{segment}10.DAT.bz2`; IR bands at R20 (2 km); 10 segments per band; objects land 11–14 min after nominal time [CONFIRMED: https://noaa-himawari9.s3.amazonaws.com/?list-type=2&prefix=AHI-L1b-FLDK/2026/10/09/1800/&max-keys=200, accessed 2026-10-10]. B11, B13, B14 and B15 are all present, which is what a split-window (B13–B15) ash test needs (judgement).
- **Licence (quoted).** "Himawari data is produced and managed by JMA. NOAA has rights to distribute this data freely and openly to the public. ... NOAA and JMA request attribution for the use or dissemination of unaltered data. However, it is not permissible to state or imply endorsement by or affiliation with NOAA or JMA. If you modify these data, you may not state or imply that it is original, unaltered data." Update frequency: "10 minutes for Full Disk"; "Archive data back to July 2015 is available for Full Disk"; access "No AWS account required" [CONFIRMED: https://registry.opendata.aws/noaa-himawari/, accessed 2026-10-10].
- **How it breaks.** Needs HSD decoding (e.g. satpy) and segment selection (Java sits in a southern segment); about 2–3 MB per band-segment (derived). Low licence risk.

### 3.11 NOAA GFS (alternate winds)

- NOMADS index needed HTTP/1.1 (curl over HTTP/2 failed on a malformed `content-length` header) and then returned 200 with `gfs.20261007/`–`gfs.20261009/` [CONFIRMED: https://nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod/, accessed 2026-10-10]. The grib filter for UGRD/VGRD at 500 and 300 mb over 110–116°E, 5–11°S → 200 `application/octet-stream`, 3,452 bytes, starting `GRIB` [CONFIRMED: https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl?dir=%2Fgfs.20261009%2F12%2Fatmos&file=gfs.t12z.pgrb2.0p25.f003&var_UGRD=on&var_VGRD=on&lev_500_mb=on&lev_300_mb=on&subregion=&leftlon=110&rightlon=116&toplat=-5&bottomlat=-11, accessed 2026-10-10]. AWS mirror `noaa-gfs-bdp-pds` lists `gfs.20261009/12/atmos/gfs.t12z.pgrb2.0p25.f003` and `.idx` [CONFIRMED: https://noaa-gfs-bdp-pds.s3.amazonaws.com/?list-type=2&prefix=gfs.20261009/12/atmos/gfs.t12z.pgrb2.0p25.f003&max-keys=5, accessed 2026-10-10]. Public domain under the NWS policy (§3.1). Needs a GRIB2 decoder.

### 3.12 SO2: NASA Worldview snapshot / GIBS

- GIBS capabilities list SO2 layers `OMI_SO2_{Planetary_Boundary_Layer, Lower_Troposphere, Middle_Troposphere, Upper_Troposphere_and_Stratosphere}`, `OMPS_SO2_*`, `OMPS_NOAA20_SO2_*`, `AIRS_Prata_SO2_Index_Day/Night`, `MLS_SO2_147hPa_*`; **no TROPOMI SO2 layer** [CONFIRMED: https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/1.0.0/WMTSCapabilities.xml, accessed 2026-10-10]. Time domains end 2026-10-09, daily (`P1D`), e.g. `OMPS_NOAA20_SO2_Middle_Troposphere` 2024-10-31/2026-10-09/P1D; OMI has gaps (e.g. 2024-02-11, 2025-06-18 missing) [CONFIRMED: same URL].
- **Working example (keyless):**
  `https://wvs.earthdata.nasa.gov/api/v1/snapshot?REQUEST=GetSnapshot&TIME=2026-10-08&BBOX=-12,108,-4,118&CRS=EPSG:4326&LAYERS=OMPS_NOAA20_SO2_Middle_Troposphere,Coastlines_15m&FORMAT=image/png&WIDTH=500&HEIGHT=400` → 200 `image/png`, 14,103 B, headers `access-control-allow-origin: *`, `access-control-expose-headers: Content-Length, Data-Present, Acquisition-Time` [CONFIRMED: that URL, accessed 2026-10-10]. The 7 Sep request over Sunda Strait (`BBOX=-10,100,-2,112`, OMPS NOAA-20 + OMI) → 200, 22,027 B; it shows coarse swath pixels with gaps (inspected). GIBS WMS equivalent → 200 [CONFIRMED: https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=OMPS_NOAA20_SO2_Middle_Troposphere&CRS=EPSG:4326&BBOX=-10,100,-2,112&WIDTH=600&HEIGHT=400&FORMAT=image/png&TIME=2026-09-07, accessed 2026-10-10].
- Terms: "NASA promotes full and open sharing of data"; acknowledgement requested: "We acknowledge the use of imagery provided by services from NASA's Global Imagery Browse Services (GIBS), part of NASA's Earth Science Data and Information System (ESDIS)." [CONFIRMED: https://nasa-gibs.github.io/gibs-api-docs/, accessed 2026-10-10].
- Judgement: once-a-day, tens-of-km pixels; useful as a "SO2 present yes/no" context layer, not for a 10-min cone.

### 3.13 NASA FIRMS thermal anomalies

- API without a valid key: `https://firms.modaps.eosdis.nasa.gov/api/area/csv/DEMO_KEY/VIIRS_SNPP_NRT/112,-9,114,-7/1` → 400 `text/plain`, body "Invalid MAP_KEY." [CONFIRMED: that URL, accessed 2026-10-10]. Docs: "MAP_KEY is needed in order to process your request. MAP_KEY limit is 5000 transactions / 10-minute interval"; the key is labelled "free"; `DAY_RANGE: 1 .. 5` [CONFIRMED: https://firms.modaps.eosdis.nasa.gov/api/area/, accessed 2026-10-10].
- **Keyless alternative:** `https://firms.modaps.eosdis.nasa.gov/data/active_fire/noaa-20-viirs-c2/csv/J1_VIIRS_C2_SouthEast_Asia_24h.csv` → 200 `text/csv`, 1,850,739 B, 22,275 rows (8–9 Oct) [CONFIRMED: that URL, accessed 2026-10-10]. Sample:
  ```
  latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,confidence,version,bright_ti5,frp,daynight
  -10.41227,150.37822,330.23,0.58,0.52,2026-10-08,0306,N20,nominal,2.0NRT,297.98,5.96,D
  ```
  Hotspots within 0.1° of active vents: Semeru 5 (max FRP 51.73 MW), Krakatau 12, Ibu 6, Dukono 1, Lewotolok 3, Lewotobi 1 (derived). Useful as independent "the vent is hot" evidence.

### 3.14 Aircraft positions

- **adsb.lol** `https://api.adsb.lol/v2/point/-8.1/112.9/250` → 200 `application/json`, 4,241 B, 0.5–0.9 s; 7 aircraft within 250 nm of Semeru at 02:37 local; five sequential calls all 200; no CORS header [CONFIRMED: that URL, accessed 2026-10-10]. Sample:
  ```
  BTK6540  PK-BKY A320 alt_baro 34325 gs 456.4 track 98.82  lat -6.803 lon 109.248 dst 231.0 nm
  SIA237   9V-SKY A388 alt_baro 39000 gs 497.8 track 146.05 lat -8.999 lon 109.367 dst 216.6 nm
  MAS128   9M-MNJ A339 alt_baro 40000 gs 465.8 track 310.91 lat -6.181 lon 112.466 dst 118.2 nm
  BTK6274  PK-BGZ B738 alt_baro 35000 gs 447.2 track 53.18  lat -5.294 lon 112.483 dst 170.5 nm
  THA462   HS-THX A359 alt_baro 40000 gs 483.0 track 329.93 lat -5.036 lon 113.026 dst 184.1 nm
  ```
  Each record also has `hex, r, t, alt_geom, ias, tas, mach, wd, ws, oat, true_heading, baro_rate, squawk, category, nav_altitude_mcp, nic, seen_pos, rssi, dir`. Around Ibu (1.49°N 127.63°E): 1 aircraft; around Krakatau: 7 [CONFIRMED: https://api.adsb.lol/v2/point/1.49/127.63/250, accessed 2026-10-10].
  Terms (quoted from the API's own OpenAPI `info`): "You can use the API for free. In the future, you will require an API key which you can get by feeding to adsb.lol. If you want to use the API for production purposes, please contact me so I do not break your application by accident." Licence: "Open Data Commons Open Database License (ODbL) v1.0" [CONFIRMED: https://api.adsb.lol/api/openapi.json, accessed 2026-10-10]. "Rate limits are dynamic based on the environment load. If you get 4xx errors, you are doing something wrong." [CONFIRMED: https://github.com/adsblol/api, accessed 2026-10-10]. Docs page: "The API is available to everyone." "License: ODbL 1.0" [CONFIRMED: https://www.adsb.lol/docs/open-data/api/, accessed 2026-10-10]. Point endpoints: `/v2/point/{lat}/{lon}/{radius}`, `/v2/closest/...`, `/v2/lat/{lat}/lon/{lon}/dist/{radius}` [CONFIRMED: https://api.adsb.lol/api/openapi.json, accessed 2026-10-10].
- **adsb.fi** `https://opendata.adsb.fi/api/v2/lat/-8.1/lon/112.9/dist/250` → 200, 4,435 B, `resultCount: 7` (same aircraft as adsb.lol) [CONFIRMED: that URL, accessed 2026-10-10]. README: the v2 lat/lon/dist endpoint "is considered deprecated" (use `/v3/lat/.../lon/.../dist/...`, "up to 250 NM"); "The public endpoints are rate limited to 1 request per second"; "adsb.fi open data is for personal, non-commercial use only. You may not license, sell, rent, or lease any part of the data or the service. ... You must cite adsb.fi and include a link to our home page." [CONFIRMED: https://raw.githubusercontent.com/adsbfi/opendata/main/README.md, accessed 2026-10-10].
- **airplanes.live** `https://api.airplanes.live/v2/point/-8.1/112.9/250` → **403** `{"error": "Please contact us at contact@airplanes.live. Your email MUST include any links, a description of the project, and any information you deem appropriate."}`; its API guide page also 403 [CONFIRMED: https://api.airplanes.live/v2/point/-8.1/112.9/250, accessed 2026-10-10]. Whether this is IP-based or a policy change is [UNVERIFIED]. Its guide is described as non-commercial with no SLA [REPORTED: https://airplanes.live/api-guide].
- **OpenSky REST** `https://opensky-network.org/api/states/all?lamin=-12&lomin=105&lamax=-4&lomax=120` → 200, 1,090 B, 8 state vectors, `x-rate-limit-remaining: 395` [CONFIRMED: that URL, accessed 2026-10-10]. Limits: anonymous 400 credits daily per endpoint bucket; standard user 4,000; active feeder 8,000; bounding boxes ≤25 sq° cost 1 credit, 25–100 sq° 2, 100–400 sq° 3; anonymous: "Only the most recent state vectors are available"; "Time resolution is 10 seconds" [CONFIRMED: https://openskynetwork.github.io/opensky-api/rest.html, accessed 2026-10-10]. **Terms (quoted):** "Any use by a for-profit or commercial entity requires written permission and a license ... Operational use of the REST API in any live product, service, or automated system also requires a written license, regardless of the entity's non-profit status." and "(vi) The REST API is provided for non-profit research and educational use only." [CONFIRMED: https://opensky-network.org/about/terms-of-use, accessed 2026-10-10]. The old `index.php/about/terms-of-use` URL → 410 [CONFIRMED: https://opensky-network.org/index.php/about/terms-of-use, accessed 2026-10-10]. Historical Trino access exists (a "Trino Client" section is on the REST page) [CONFIRMED: https://openskynetwork.github.io/opensky-api/rest.html, accessed 2026-10-10] and falls under the same research-only licence (judgement).
- **Replay archives.** adsb.lol: "Historical data is dumped daily ... The data is made available by GitHub releases"; "a JSON GZIP file containing the data for that aircraft for the day"; "License: ODbL 1.0" [CONFIRMED: https://www.adsb.lol/docs/open-data/historical/, accessed 2026-10-10]. Releases exist for `v2026.09.06-planes-readsb-prod-0` (3,511,347,200 B), `v2026.09.07-planes-readsb-prod-0` (3,858,968,576 B), `v2026.09.25-planes-readsb-prod-0` (3,793,626,624 B) and `v2026.10.08-...` (split into `.tar.aa/.ab/.ac`) [CONFIRMED: https://api.github.com/repos/adsblol/globe_history_2026/releases/tags/v2026.09.07-planes-readsb-prod-0, accessed 2026-10-10]. **A real 7 Sep 2026 replay is possible** (about 3.9 GB to download for the day). ADS-B Exchange samples redirect to a JS index at `https://samples.adsbexchange.com/index.html` that I did not parse [CONFIRMED: https://samples.adsbexchange.com/index.html, accessed 2026-10-10]; its terms are [UNVERIFIED].

### 3.15 Winds: Open-Meteo

- `https://api.open-meteo.com/v1/forecast?latitude=-8.108&longitude=112.922&hourly=wind_speed_850hPa,wind_direction_850hPa,wind_speed_700hPa,wind_direction_700hPa,wind_speed_500hPa,wind_direction_500hPa,wind_speed_300hPa,wind_direction_300hPa,wind_speed_250hPa,wind_direction_250hPa,geopotential_height_500hPa&wind_speed_unit=kn&forecast_hours=6&timezone=GMT` → 200, 1,204 B [CONFIRMED: that URL, accessed 2026-10-10]. Sample (19Z):
  ```
  2026-10-09T19:00  850hPa 1.2 kt/270°  700hPa 12.9 kt/301°  500hPa 4.9 kt/67°  300hPa 14.6 kt/21°  250hPa 10.4 kt/263°  z500 5870 m
  2026-10-09T23:00  850hPa 0.9 kt/214°  700hPa 12.9 kt/301°  500hPa 7.1 kt/90°  300hPa 14.3 kt/18°   250hPa 9.9 kt/259°
  ```
  Directions are "from" (meteorological convention), so the 700 hPa flow carries ash toward about 121° (ESE) and the 500 hPa flow toward about 247° (WSW) (derived). The `/v1/gfs` endpoint also works (200) [CONFIRMED: https://api.open-meteo.com/v1/gfs?latitude=-8.108&longitude=112.922&hourly=wind_speed_200hPa,wind_direction_200hPa,wind_speed_150hPa&forecast_hours=3, accessed 2026-10-10].
- Levels on the docs page: 1000, 975, 950, 925, 900, 850, 800, 700, 600, 500, 400, 300, 250, 200, 150, 100, 70, 50, 30 hPa [CONFIRMED: https://open-meteo.com/en/docs, accessed 2026-10-10].
- **Terms (quoted):** "Less than 10'000 API calls per day, 5'000 per hour and 600 per minute. You may only use the free API services for non-commercial purposes. You accept to the CC-BY 4.0 licence"; commercial use includes "Integrating our service into commercial products or promotional activities." [CONFIRMED: https://open-meteo.com/en/terms, accessed 2026-10-10].

### 3.16 Volcano status sources

- **Smithsonian GVP:** `WeeklyVolcanoRSS.xml`, `WeeklyVolcanoCAP.xml`, `reports_weekly.cfm` and the home page all → 403 with a Cloudflare page: "This Smithsonian site is temporarily unavailable" [CONFIRMED: https://volcano.si.edu/news/WeeklyVolcanoRSS.xml, accessed 2026-10-10]; WebFetch also got 403 [CONFIRMED: https://volcano.si.edu/reports_weekly.cfm, accessed 2026-10-10]. Weekly cadence makes it irrelevant to the live loop (judgement).
- **JMA warnings:** `https://www.jma.go.jp/bosai/volcano/data/warning.json` → 200, 14 current entries, Japanese labels, e.g. `2022-07-27T20:00:00+09:00 506 レベル３（入山規制） ['桜島']` (Sakurajima Level 3) and `2026-10-08T11:00:00+09:00 323 ... ['ベヨネース列岩']` [CONFIRMED: that URL, accessed 2026-10-10]. `volcano_list.json` → 200 [CONFIRMED: https://www.jma.go.jp/bosai/volcano/const/volcano_list.json, accessed 2026-10-10]. Undocumented JSON (judgement).
- **GeoNet:** `https://api.geonet.org.nz/volcano/val` → 200 `application/vnd.geo+json;version=2`, e.g. Taupo `acc: Green`, `level: 0` [CONFIRMED: that URL, accessed 2026-10-10]. Licence [UNVERIFIED].
- **KVERT:** old `kscnet.ru` paths redirect to `http://kvert.febras.net/` (200 HTML, Russian/English) or time out; `updates.xml` → 404 [CONFIRMED: http://kvert.febras.net/, accessed 2026-10-10].
- **PHIVOLCS:** home page 200; guessed bulletin paths → 404; bulletin URL not found after 1 web search (query in log) [CONFIRMED: https://www.phivolcs.dost.gov.ph/, accessed 2026-10-10]. Tokyo VAAC covers Taal/Mayon/Kanlaon advisories (§3.4).

---

## 4. A live contradiction you can show today (Semeru, 9 Oct 18:00–19:30 UTC)

| Source | Time | What it says |
|---|---|---|
| MAGMA VONA 20261009/1800Z, notice 2026SMR1920 | 18:00Z (01:00 local) | "Eruption at 1800 UTC (0100 local). Ash-cloud is not observed." Colour code ORANGE |
| SIGMET WAAF 12 | issued 18:20Z | "VA CLD OBS AT 1800Z ... SFC/FL150 MOV E 10KT NC" |
| Darwin VAA 2026/1157 | 18:20Z | "VA IDENTIFIABLE ON CURRENT SATELLITE IMAGERY MOVING EAST ... AREA IS PARTIALLY OBSCURED BY MET CLOUD"; forecast polygon stationary to +18 h |
| Open-Meteo winds over summit | 19:00Z | 700 hPa from 301° at 12.9 kt; 500 hPa from 67° at 4.9 kt |
| FIRMS VIIRS | 8 Oct 06:29Z, 17:34Z | 5 hotspots within 0.1° of the vent, max FRP 51.73 MW |
| adsb.lol | 19:37Z | 7 aircraft within 250 nm, nearest MAS128 at FL400, 118 nm |

Sources: [CONFIRMED: https://magma.esdm.go.id/v1/vona, https://aviationweather.gov/api/data/isigmet?format=json&hazard=va, https://tgftp.nws.noaa.gov/data/raw/fv/fvau02.adrm..txt, https://api.open-meteo.com/v1/forecast?latitude=-8.108&longitude=112.922&..., https://firms.modaps.eosdis.nasa.gov/data/active_fire/noaa-20-viirs-c2/csv/J1_VIIRS_C2_SouthEast_Asia_24h.csv, https://api.adsb.lol/v2/point/-8.1/112.9/250, all accessed 2026-10-10].

Judgement: the VONA's "not observed" at 01:00 local most likely reflects a ground observer who cannot see at night, not a real absence of ash; daytime VONAs at 11:49 and 14:06 local said the same, which points to cloud cover. A reconciler has to weigh observer limits, satellite confidence ("partially obscured") and wind shear between 700 and 500 hPa. That is a reasoning task, not a lookup, and the official polygon (SFC/FL150) is the floor the cone may not shrink below.

---

## 5. Google side (public docs only, no key)

- **Model IDs.** The models page (footer "Last updated 2026-10-06 UTC") lists as stable: `gemini-3.8-flash` (New), `gemini-3.8-live` (New), `gemini-3.8-live-extended-thinking`, `gemini-3.8-flash-tts`, `gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`, image models; preview: `gemini-3.1-pro-preview`, `gemini-3-flash-preview`, `gemini-3.1-flash-live-preview` (marked legacy, "update to Gemini 3.8 Live"); shut down: `gemini-2.0-flash`, `gemini-3-pro-preview`, `gemini-3.1-flash-lite-preview` [CONFIRMED: https://ai.google.dev/gemini-api/docs/models, accessed 2026-10-10]. **"gemini-3.8-flash" is a real ID today.**
- **Pricing / free tier.** Free tier input and output are "Free of charge" for 3.8 Flash, 3.7 Flash, 3.5 Flash, 3.5 Flash-Lite and 3.8 Live. Paid 3.8 Flash: input "$0.75 through December 31, 2026" then "$1.50 starting January 1, 2027"; output "$3.75" then "$7.50". The Free plan card says content is used to improve products. Gemma 4: free tier only [CONFIRMED: https://ai.google.dev/gemini-api/docs/pricing, accessed 2026-10-10].
- **Rate limits.** "Rate limits are applied per project, not per API key"; RPD resets at midnight Pacific; tiers Free, Tier 1 ("Set up and link an active billing account"), Tier 2, Tier 3. **Per-model free-tier RPM/RPD numbers are not printed on the page**; it says "View your active rate limits in AI Studio" [CONFIRMED: https://ai.google.dev/gemini-api/docs/rate-limits, accessed 2026-10-10].
- **Image input.** "a maximum of 3,600 image files per request"; inline data limits total request size "to 20MB"; MIME types PNG, JPEG, WEBP, HEIC, HEIF; "258 tokens if both dimensions <= 384 pixels"; larger images "tiled into 768x768 pixel tiles, each costing 258 tokens"; bounding boxes "normalized to [0, 1000]"; segmentation returns contour masks [CONFIRMED: https://ai.google.dev/gemini-api/docs/image-understanding, accessed 2026-10-10]. A 1101×501 se3 frame works out to about 8 tiles, roughly 2,000 tokens, by the page's formula (derived).
- **Structured output.** Configured via `response_format` with `mime_type: application/json` and a `schema`; supports a JSON-Schema subset (`enum`, `minimum`, `maximum`, `items`, `prefixItems`, `minItems`, `maxItems`, `required`, `additionalProperties`, ...); "Very large or deeply nested schemas may be rejected"; "Gemini 3 lets you combine Structured Outputs with built-in tools, including Grounding with Google Search" and Function Calling [CONFIRMED: https://ai.google.dev/gemini-api/docs/structured-output, accessed 2026-10-10]. The page does not use the older `response_mime_type`/`response_schema` names (WebFetch summary; judgement that SDK names may differ by version).
- **Live API.** Inputs: "Audio (raw 16-bit PCM audio, 16kHz, little-endian), images (JPEG <= 1FPS), text"; recommends "ephemeral tokens instead of standard API keys" for client-to-server production use; the page itself does not list models or session limits [CONFIRMED: https://ai.google.dev/gemini-api/docs/live, accessed 2026-10-10]. `gemini-3.8-live` is stable per the models page (above).

---

## 6. Conflicts with our idea

| # | Conflict | Grade | Evidence | What has to change |
|---|---|---|---|---|
| C1 | **MAGMA forbids crawling and has no public machine API.** `robots.txt` is `Disallow: /` for all agents; JSON API needs a JWT (401); detail pages need signed URLs (unsigned 403); RSS 403; "All Rights Reserved". | **SERIOUS** | https://magma.esdm.go.id/robots.txt; https://magma.esdm.go.id/api/v1/vona; https://magma.esdm.go.id/v1/vona | Do not run a 5-minute scraper as the core VONA source. Subscribe to VONA email (offered on the page) and ingest mail; show the MAGMA page as a human link; use CVGHM content quoted in Darwin VAAs; write to PVMBG for a token. If the demo scrapes at all, keep it to a low-rate list fetch, say so on screen, and cache. Do not claim "every input is keyless and public" for MAGMA. |
| C2 | **OpenSky licence bars our use.** Live automated use of the REST API needs a written licence even for non-profits. | **SERIOUS** (if used) → NONE if dropped | https://opensky-network.org/about/terms-of-use | Remove OpenSky from pollers and from any "live" claim. Use adsb.lol (ODbL). The brief's "783 flights in one daytime hour" figure came from OpenSky; recompute it from adsb.lol or cite it as a one-off research count. |
| C3 | **BoM forbids scraping; IDD41300/41301 do not exist publicly; the JMA "Darwin mirror" is a backup page.** | MINOR (after switch) | https://www.bom.gov.au/copyright; https://www.bom.gov.au/robots.txt; https://ds.data.jma.go.jp/svd/vaac/data/vaac_darwin_list.html | Read Darwin (and all VAACs) from `https://tgftp.nws.noaa.gov/data/raw/fv/` (public domain, plain text, updated within minutes). Poll ≤5 min because each header keeps only the latest bulletin. |
| C4 | **Satellite JPEGs are coarse and partly non-commercial.** JMA public frames ~5 km/px (Semeru polygon ≈ 10 × 9 px); JMA hi-res areas miss Java and Halmahera; NICT tiles are "not allowed for commercial uses"; NICT B13 tiles are alpha cloud overlays, not brightness temperatures. | **SERIOUS** for the "Gemini reads the plume" step; NONE for the text spine | https://www.data.jma.go.jp/mscweb/data/himawari/img/se3/se3_dst_1920.jpg; https://himawari8.nict.go.jp/himawari8-help.htm | Keep the image as support only, as the answer to Akash already says. If an image is used, crop from AWS `noaa-himawari9` B13/B15 at 2 km (open licence, attribution) or JMA bosai dated tiles; never claim Gemini detects ash from the picture alone. |
| C5 | **JMA real-time JPEG slots are date-less and keep 23 h**; the 19:20 slot served the previous day's frame at 19:32Z. | MINOR | https://www.data.jma.go.jp/mscweb/data/himawari/img/se3/se3_dst_1920.jpg | Check `Last-Modified` or the burned-in label, or switch to bosai tiles with full timestamps (`targetTimes_fd.json`). Store every frame you use; the ring overwrites daily. |
| C6 | **adsb.fi and Open-Meteo free tiers are non-commercial; adsb.lol announces a future key and asks production users to get in touch; airplanes.live returns 403.** | MINOR for a hackathon; SERIOUS for any commercial pitch | https://raw.githubusercontent.com/adsbfi/opendata/main/README.md; https://open-meteo.com/en/terms; https://api.adsb.lol/api/openapi.json; https://api.airplanes.live/v2/point/-8.1/112.9/250 | Hackathon use is inside the terms. In the deck, say the production path is a paid Open-Meteo plan or NOAA GFS (public domain), and ADS-B from a licensed provider or the airline's own feed. Attribute adsb.lol (ODbL), Open-Meteo (CC BY 4.0), adsb.fi if used. |
| C7 | **AWC `isigmet` is deprecated; API responses are cached 180 s; no CORS; 30-day history only.** | MINOR | https://aviationweather.gov/data/schema/openapi.yaml; https://aviationweather.gov/data/api/ | Use `/api/data/sigmet` or the once-a-minute cache file from the Cloud Run poller. **Archive the replay cases now**: 7 Sep is already out of the window and 25 Sep leaves around 25 Oct. |
| C8 | **The 7 Sep Anak Krakatau hook cannot be replayed from AWC or tgftp** (out of 30-day window; tgftp keeps only the latest). NICT imagery and adsb.lol history for 7 Sep do exist. | MINOR | https://aviationweather.gov/api/data/sigmet?format=json&hazard=va&date=20260907_0600 | Use 7 Sep as the news hook only, or find an archived SIGMET/VAA text source for that day (open question). Use a fresher in-window case for any replay. |
| C9 | **No Fukuoka or Manila VA SIGMET was open at check time;** Asia-Pacific coverage today is Indonesian only. | MINOR | https://aviationweather.gov/api/data/isigmet?format=json&hazard=va | Plan the live demo around Indonesian FIRs (present in 59/59 samples); treat Japan/Philippines as "sometimes". |
| C10 | **Smithsonian GVP returned 403 and BMKG aviation sits behind a Cloudflare challenge.** | MINOR | https://volcano.si.edu/news/WeeklyVolcanoRSS.xml; https://web-aviation.bmkg.go.id/va-map.php?data=1 | Do not depend on either. |
| C11 | **Gemini free tier uses content to improve Google products**; per-model free limits are only visible in AI Studio. | MINOR | https://ai.google.dev/gemini-api/docs/pricing; https://ai.google.dev/gemini-api/docs/rate-limits | All TEPHRA inputs are public, so the data-use clause is acceptable for the demo; check the real RPD in AI Studio once a personal key exists; budget calls (one reconcile per new product, not per poll). |
| C12 | **JMA terms mention the Meteorological Service Act Article 17 forecasting licence** for providing forecasting services in Japan. | MINOR | https://www.jma.go.jp/jma/en/copyright.html | Not relevant to a hackathon demo; relevant if the cone were sold as a forecast service in Japan. Label output as decision support built on official products. |

No conflict found is FATAL: every core input (SIGMET, VAA text, winds, aircraft) has a keyless source whose terms allow a non-commercial hackathon build.

---

## 7. What this supports

- **"Every input is real and keyless" is mostly true**: AWC SIGMET/TAF/METAR (200), NWS tgftp VAAs (200), Tokyo VAAC list/text (200), JMA/NICT/AWS Himawari (200), Worldview SO2 (200), FIRMS public CSV (200), adsb.lol (200), adsb.fi (200), Open-Meteo (200), NOMADS GFS (200) all answered without keys today (sources in §2). The exceptions are MAGMA's API (JWT), FIRMS API (free key) and airplanes.live (403).
- **Fresh ash on demo days is very likely in Indonesia**: WAAF had a VA SIGMET in 59 of 59 samples over 30 days; Darwin numbering shows Semeru 2026/1157 and Ibu 2026/1148 by 9 Oct (§3.1, §3.7).
- **Sources really do disagree**, and on a schedule: VONAs at night report "Ash-cloud is not observed" while SIGMETs and VAAs report FL150; Tokyo VAAs often say "VA NOT IDENTIFIABLE FM SATELLITE DATA" (25 Sep Sakurajima, 8 Oct Taal) while a SIGMET or eruption report exists (§3.3, §3.4, §4). This backs the claim that reconciliation, not lookup, is the core job.
- **The official polygon is machine-readable** (`coords` in SIGMET JSON; lat/lon strings in VAAs with +6/+12/+18 h forecasts), so "never shrink below the official polygon" is implementable as a geometric union/containment rule (§3.1, §3.7).
- **Wind shear is visible in public data** (700 vs 500 hPa directions differ by ~126° over Semeru today), giving Gemini a real reason to hedge a cone (§3.15).
- **Replay material exists**: adsb.lol daily history for 7 Sep and 25 Sep (≈3.5–3.9 GB each), NICT imagery for 7 Sep, AWC SIGMETs back to 10 Sep (§3.1, §3.8, §3.14).
- **Gemini 3.8 Flash exists, is free on the free tier, accepts multiple images per call and returns schema-constrained JSON alongside tools** (§5).
- **Independent corroboration feeds exist** (FIRMS hotspots at every active Indonesian vent; daily SO2), useful as "evidence for" chips in the provenance panel (§3.12, §3.13).

---

## 8. Recommended feed stack for the build (judgement)

1. SIGMET: `https://aviationweather.gov/data/cache/sigmets.cache.json.gz` every 60 s (fallback `/api/data/sigmet?format=json&hazard=va`), custom User-Agent.
2. VAAs: `https://tgftp.nws.noaa.gov/data/raw/fv/` every 2–5 min, diff by `Last-Modified`; Tokyo history from `vaac_list.html` hourly.
3. VONA: email subscription ingest; MAGMA list page as low-rate, cached, clearly labelled fallback only if the team accepts the robots.txt issue.
4. Winds: Open-Meteo pressure levels (non-commercial) with NOMADS GFS as the licence-clean fallback.
5. Aircraft: adsb.lol `/v2/point` (≤250 nm) per active volcano every 30–60 s; adsb.fi `/v3/...` fallback at ≤1 req/s with citation; no OpenSky.
6. Imagery (support only): JMA bosai dated tiles (Dust RGB, B13) at z5 for the map; AWS `noaa-himawari9` B13/B15 crops if a sharper image is wanted for Gemini.
7. Context chips: FIRMS public 24 h CSV; Worldview SO2 snapshot daily.
8. Archive everything you show (raw text + hash + fetch time), because tgftp, JMA JPEGs and AWC history all age out.

---

## Open questions

1. Will PVMBG/CVGHM grant an API token for `magma.esdm.go.id/api/v1/vona`, or approve low-rate polling of the list page? (Email needed.)
2. Does the VONA email subscription still work, how fast does it arrive after issue, and can Cloud Run receive it (e.g. via a mail-to-webhook service)?
3. Is there an archived, public source of 7 Sep 2026 SIGMET and Darwin VAA texts (Ogimet guess returned 404; data.gov.au BoM dataset pages redirect)?
4. Are adsb.lol, MAGMA (F5 WAF) and AWC reachable from Cloud Run egress IPs without challenges? Not testable without deploying.
5. What are the exact free-tier RPM/RPD for `gemini-3.8-flash` and `gemini-3.8-live` on a personal (non-work) AI Studio project?
6. Why did airplanes.live return 403 (IP-based block vs. policy change)?
7. GeoNet and KVERT licence terms (not checked; low priority).
8. Can Gemini, given a 2-km B13/B15 crop plus the VAA polygon, say anything useful that the VAA text does not already say? Needs a key and a 10-case test.
9. Where are PHIVOLCS daily bulletins served now (guessed paths 404)?

---

## Sources

All accessed 2026-10-10 (IST; 2026-10-09 19:27–19:57 UTC) unless marked REPORTED.

- https://aviationweather.gov/api/data/isigmet?format=json&hazard=va
- https://aviationweather.gov/api/data/isigmet?format=json
- https://aviationweather.gov/api/data/sigmet?format=json&hazard=va
- https://aviationweather.gov/api/data/sigmet?format=geojson&hazard=va
- https://aviationweather.gov/api/data/sigmet?format=json&hazard=va&date=20260925_1200 (and 60 dated calls 20260910_0600 … 20261009_1800)
- https://aviationweather.gov/api/data/sigmet?format=json&hazard=va&date=20260907_0600
- https://aviationweather.gov/api/data/isigmet?format=json&hazard=va&date=20260925_1200
- https://aviationweather.gov/data/api/
- https://aviationweather.gov/data/schema/openapi.yaml
- https://aviationweather.gov/data/cache/sigmets.cache.json.gz
- https://aviationweather.gov/api/data/taf?ids=WIII,WARR,WADD,WAAA,RJFK,RJFF,RPLL&format=json
- https://aviationweather.gov/api/data/metar?ids=WIII,WARR,WADD,WAAA,RJFK,RJFF,RPLL&format=json
- https://www.weather.gov/disclaimer
- https://magma.esdm.go.id/v1/vona (also ?page=2, ?code=SMR, and signed detail /v1/vona/22889?signature=…)
- https://magma.esdm.go.id/api/v1/vona ; https://magma.esdm.go.id/api/v1/vona/latest ; https://magma.esdm.go.id/api/v1/home/vona ; https://magma.esdm.go.id/api/v1/python/magma-var/latest ; https://magma.esdm.go.id/v1/vona/rss ; https://magma.esdm.go.id/rss ; https://magma.esdm.go.id/feed
- https://magma.esdm.go.id/robots.txt
- https://magma.esdm.go.id/v1/gunung-api/tingkat-aktivitas ; https://magma.esdm.go.id/v1/gunung-api/informasi-letusan
- https://vsi.esdm.go.id/
- https://web-aviation.bmkg.go.id/va-map.php?data=1 ; https://web-aviation.bmkg.go.id/robots.txt
- https://github.com/abah/PantauErupsi (REPORTED for CCTV licence)
- https://github.com/Gabrielbjb/Magma-Indonesia-API (REPORTED)
- https://ds.data.jma.go.jp/svd/vaac/data/
- https://ds.data.jma.go.jp/svd/vaac/data/vaac_list.html
- https://ds.data.jma.go.jp/svd/vaac/data/vaac_darwin_list.html
- https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/ (403)
- https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20260925_28208001_0249_Text.html
- https://ds.data.jma.go.jp/robots.txt (404)
- https://www.jma.go.jp/jma/en/copyright.html
- https://www.bom.gov.au/aviation/volcanic-ash/
- https://www.bom.gov.au/aviation/volcanic-ash/darwin-va-advisory.shtml
- https://www.bom.gov.au/aviation/volcanic-ash/js/va.js?v2
- https://www.bom.gov.au/aviation/php/process.php (POST)
- https://www.bom.gov.au/fwo/IDY65295.png
- https://www.bom.gov.au/fwo/IDD41300.html ; https://www.bom.gov.au/fwo/IDD41301.html ; https://www.bom.gov.au/fwo/IDD41300.txt ; ftp://ftp.bom.gov.au/anon/gen/fwo/IDD41300.txt
- https://www.bom.gov.au/aviation/volcanic-ash/darwin-graphical-va-advisory.shtml (404)
- https://www.bom.gov.au/copyright
- https://www.bom.gov.au/robots.txt
- https://tgftp.nws.noaa.gov/data/raw/fv/
- https://tgftp.nws.noaa.gov/data/raw/fv/fvau01.adrm..txt ; fvau02.adrm..txt ; fvau03.adrm..txt ; fvau04.adrm..txt ; fvfe01.rjtd..txt ; fvxx20.knes..txt ; fvps01.nzkl..txt ; fvak21.pawu.vaa.ak1.txt
- https://himawari8.nict.go.jp/ ; https://himawari8.nict.go.jp/js/env.js ; https://himawari8.nict.go.jp/js/himawari8-image.js
- https://himawari8.nict.go.jp/img/D531106/latest.json ; https://himawari8.nict.go.jp/img/FULL_24h/latest.json ; https://himawari8-dl.nict.go.jp/himawari8/img/D531106/latest.json
- https://himawari8.nict.go.jp/img/D531106/1d/550/2026/10/09/191000_0_0.png (and dated archive probes 2016-01-01 … 2026-10-09)
- https://himawari8.nict.go.jp/img/FULL_24h/B13/8d/550/2026/10/09/180000_1_4.png ; https://himawari8.nict.go.jp/img/D531106/8d/550/2026/10/09/040000_1_4.png
- https://himawari8.nict.go.jp/himawari8-help.htm ; https://himawari8.nict.go.jp/himawari8-about.htm ; https://sc-web.nict.go.jp/himawari/
- https://www.data.jma.go.jp/mscweb/data/himawari/sat_img.php?area=se3 ; https://www.data.jma.go.jp/mscweb/data/himawari/sat_img.js ; https://www.data.jma.go.jp/mscweb/data/himawari/index.html
- https://www.data.jma.go.jp/mscweb/data/himawari/img/se3/se3_b13_1920.jpg ; se3_dst_1830/1900/1910/1920/1930/2000/2010.jpg ; img/ha1…ha6, hp1…hp3 _dst_1910.jpg
- https://www.jma.go.jp/bosai/himawari/ (404) ; https://www.jma.go.jp/bosai/himawari/data/satimg/targetTimes_fd.json ; https://www.jma.go.jp/bosai/himawari/data/satimg/targetTimes_jp.json
- https://www.jma.go.jp/bosai/himawari/data/satimg/20261009190000/fd/20261009190000/DST/ETC/5/26/16.jpg (and B13/TBB, SND/ETC, B03/ALBD, B08/TBB, REP/ETC; z6–z9 probes; 20261006/20261001 probes)
- https://ds.data.jma.go.jp/mscweb/en/oper/opr_bulletin_H9.html
- https://noaa-himawari9.s3.amazonaws.com/?list-type=2&delimiter=/&max-keys=50
- https://noaa-himawari9.s3.amazonaws.com/?list-type=2&prefix=AHI-L1b-FLDK/2026/10/09/1800/&max-keys=200
- https://registry.opendata.aws/noaa-himawari/
- https://en.wikipedia.org/wiki/Himawari_(satellites) (REPORTED)
- https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/1.0.0/WMTSCapabilities.xml
- https://wvs.earthdata.nasa.gov/api/v1/snapshot?REQUEST=GetSnapshot&TIME=2026-10-08&BBOX=-12,108,-4,118&CRS=EPSG:4326&LAYERS=OMPS_NOAA20_SO2_Middle_Troposphere,Coastlines_15m&FORMAT=image/png&WIDTH=500&HEIGHT=400
- https://wvs.earthdata.nasa.gov/api/v1/snapshot?REQUEST=GetSnapshot&TIME=2026-09-07&BBOX=-10,100,-2,112&CRS=EPSG:4326&LAYERS=OMPS_NOAA20_SO2_Middle_Troposphere,OMI_SO2_Middle_Troposphere,Coastlines_15m&FORMAT=image/png&WIDTH=600&HEIGHT=400
- https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=OMPS_NOAA20_SO2_Middle_Troposphere&CRS=EPSG:4326&BBOX=-10,100,-2,112&WIDTH=600&HEIGHT=400&FORMAT=image/png&TIME=2026-09-07
- https://nasa-gibs.github.io/gibs-api-docs/
- https://firms.modaps.eosdis.nasa.gov/api/area/csv/DEMO_KEY/VIIRS_SNPP_NRT/112,-9,114,-7/1 ; https://firms.modaps.eosdis.nasa.gov/api/ ; https://firms.modaps.eosdis.nasa.gov/api/area/
- https://firms.modaps.eosdis.nasa.gov/data/active_fire/noaa-20-viirs-c2/csv/J1_VIIRS_C2_SouthEast_Asia_24h.csv
- https://api.adsb.lol/v2/point/-8.1/112.9/250 ; https://api.adsb.lol/v2/point/1.49/127.63/250 ; https://api.adsb.lol/v2/point/-6.1/105.4/250
- https://api.adsb.lol/docs ; https://api.adsb.lol/api/openapi.json ; https://www.adsb.lol/docs/open-data/api/ ; https://www.adsb.lol/docs/open-data/historical/ ; https://github.com/adsblol/api
- https://api.github.com/repos/adsblol/globe_history_2026/releases?per_page=5 ; …/releases/tags/v2026.09.07-planes-readsb-prod-0 ; …/v2026.09.06-planes-readsb-prod-0 ; …/v2026.09.25-planes-readsb-prod-0
- https://opendata.adsb.fi/api/v2/lat/-8.1/lon/112.9/dist/250 ; https://raw.githubusercontent.com/adsbfi/opendata/main/README.md
- https://api.airplanes.live/v2/point/-8.1/112.9/250 ; https://airplanes.live/api-guide/ (403; REPORTED content via search)
- https://opensky-network.org/api/states/all?lamin=-12&lomin=105&lamax=-4&lomax=120 ; https://opensky-network.org/about/terms-of-use ; https://opensky-network.org/index.php/about/terms-of-use (410) ; https://openskynetwork.github.io/opensky-api/rest.html
- https://www.adsbexchange.com/products/historical-data/ ; https://samples.adsbexchange.com/index.html
- https://api.open-meteo.com/v1/forecast?latitude=-8.108&longitude=112.922&hourly=wind_speed_850hPa,wind_direction_850hPa,wind_speed_700hPa,wind_direction_700hPa,wind_speed_500hPa,wind_direction_500hPa,wind_speed_300hPa,wind_direction_300hPa,wind_speed_250hPa,wind_direction_250hPa,geopotential_height_500hPa&wind_speed_unit=kn&forecast_hours=6&timezone=GMT
- https://api.open-meteo.com/v1/gfs?latitude=-8.108&longitude=112.922&hourly=wind_speed_200hPa,wind_direction_200hPa,wind_speed_150hPa&forecast_hours=3
- https://open-meteo.com/en/terms ; https://open-meteo.com/en/docs
- https://nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod/ ; https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl?dir=%2Fgfs.20261009%2F12%2Fatmos&file=gfs.t12z.pgrb2.0p25.f003&var_UGRD=on&var_VGRD=on&lev_500_mb=on&lev_300_mb=on&subregion=&leftlon=110&rightlon=116&toplat=-5&bottomlat=-11
- https://noaa-gfs-bdp-pds.s3.amazonaws.com/?list-type=2&prefix=gfs.20261009/12/atmos/gfs.t12z.pgrb2.0p25.f003&max-keys=5
- https://volcano.si.edu/news/WeeklyVolcanoRSS.xml ; https://volcano.si.edu/news/WeeklyVolcanoCAP.xml ; https://volcano.si.edu/reports_weekly.cfm ; https://volcano.si.edu/ (all 403)
- https://www.jma.go.jp/bosai/volcano/data/warning.json ; https://www.jma.go.jp/bosai/volcano/const/volcano_list.json ; https://www.jma.go.jp/bosai/volcano/data/volcano.json (404)
- https://api.geonet.org.nz/volcano/val
- http://kvert.febras.net/ ; http://www.kscnet.ru/ivs/kvert/van/index?type=1 ; http://www.kscnet.ru/ivs/kvert/updates.xml (404)
- https://www.phivolcs.dost.gov.ph/ ; https://www.phivolcs.dost.gov.ph/index.php/volcano-hazard/volcano-bulletin2 (404)
- https://www.ospo.noaa.gov/products/atmosphere/vaac/ (200) ; https://www.weather.gov/vaac (200) ; https://www.metservice.com/aviation/volcanic-ash-advisory-centre (200) ; https://www.ssd.noaa.gov/VAAC/messages.html (no response) ; https://vaac.metservice.com/ (no response)
- https://data.gov.au/data/dataset/volcanic-ash-advisory-past-archived-advisories (302, not resolved)
- https://www.ogimet.com/display_sigmets.php?... (404; guessed URL)
- https://ai.google.dev/gemini-api/docs/models ; https://ai.google.dev/gemini-api/docs/rate-limits ; https://ai.google.dev/gemini-api/docs/pricing ; https://ai.google.dev/gemini-api/docs/image-understanding ; https://ai.google.dev/gemini-api/docs/structured-output ; https://ai.google.dev/gemini-api/docs/live (via WebFetch; curl loops on 302)

## Search log

Web searches (WebSearch tool): 5.
1. "Himawari-10 launch date status 2026 JMA" (standard) — found the Wikipedia citation of an NHK report of delay to FY2030; no JMA primary page fetched.
2. "magma.esdm.go.id api vona token json github" (extended) — no official MAGMA API docs; found PantauErupsi and an unofficial scraper.
3. "PHIVOLCS volcano bulletin Taal Mayon Kanlaon October 2026" (standard) — nothing current; bulletin URL not found.
4. "\"IDD41300\" OR \"IDD41301\" Bureau of Meteorology volcanic ash" (standard) — not found after 1 search.
5. "airplanes.live API \"contact@airplanes.live\" 403 api key required" (standard) — no page documenting the 403; guide described as non-commercial.

Direct fetches: about 190 curl requests (status, headers and bodies saved under the session scratchpad `feeds/` directory), plus WebFetch on 9 pages (adsb.lol API docs, six ai.google.dev pages, GIBS docs, GVP weekly page).
