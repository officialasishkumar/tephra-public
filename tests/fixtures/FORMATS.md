# Feed formats as observed

What the fixtures in this folder actually contain, fetched 2026-10-09 19:36-19:44Z.
Every example value below is copied from a fixture. Where something is a rule
documented elsewhere but not seen in these files, it says so.

## Differences from the product spec

Read this first. The spec and the earlier research notes assumed some things the
feeds do not do.

1. **BoM "Nil current Darwin Volcanic Ash Advisories" is not data.** That sentence is
   a hidden fallback (`<div id="info" style="display:none;">`) in the static HTML of
   `darwin-va-advisory.shtml`. The page fills `#box-content` from JavaScript
   (`/aviation/volcanic-ash/js/va.js`), which POSTs to `/aviation/php/process.php`.
   At the same moment that endpoint returned 5 current Darwin advisories, including
   Semeru 2026/1157. Earlier claims that Darwin "had nil advisories" came from
   reading the static HTML and should be treated as wrong.
2. **The JMA "Darwin mirror" is not a mirror.** `vaac_darwin_list.html` has 34 rows
   going back to 2015, 19 of them NOTICE messages, and its newest row is
   2026-09-23. Darwin had issued Ibu 2026/1148 and Semeru 2026/1157 by 2026-10-09.
   The claim that "Darwin VAAC issued nothing for Semeru all week" was most likely
   read from this list. Use BoM (`process.php` or `Volc_ash_recent.shtml`) for Darwin.
3. **For Semeru, the VAAC polygon existed.** At fetch time the Indonesian FIR VA
   SIGMETs (WAAF 11, 12, 13 and WIIF 07) carried exactly the observed polygon of the
   matching Darwin advisory (Dukono 855, Semeru 1157, Ibu 1148, Krakatau 225), vertex
   for vertex, with the first vertex repeated to close the ring. The spec's opening
   hook ("the VAAC polygon ... does not exist yet") does not hold tonight. The real
   disagreement in tonight's fixtures is between MAGMA and Darwin: VONA
   20261009/1800Z for Semeru says "Ash-cloud is not observed." while Darwin 2026/1157
   says "VA TO FL150 OBS AT 09/1800Z, MOV E".
4. **MAGMA feet values are metres x 3.2, not x 3.28084.** Every FT figure in the
   VONA pages is the metre figure times exactly 3.2: 4376 M -> 14003 FT, 3676 M ->
   11763 FT, 700 M -> 2240 FT, 1725 M -> 5520 FT. The true value of 4376 m is
   14,357 ft, so MAGMA feet understate by about 2.5%. Parse the metres and convert
   yourself. The spec's "13,363 ft" for Semeru is 4176 m x 3.2.
5. **isigmet `top` and `base` are feet, not flight levels.** `top: 15000` is FL150 and
   `base: 0` is SFC. There is no volcano field; the name is inside `qualifier`
   (`"ERUPTION MT SEMERU"`, but `"FUEGO"` and `"MASAYA"` from the MHTG FIR have no prefix).
6. **isigmet sometimes splits one SIGMET into two records.** When a SIGMET has a
   `FCST AT` polygon (SEFG and MHTG tonight), AWC returns two records with the same
   raw text, `seriesId` `"3"` and `"3F"`. The plain one carries the observed polygon,
   the `F` one the forecast polygon. Indonesian SIGMETs tonight have no forecast part.
7. **Open-Meteo `forecast_days=1` covers the current UTC day only.** It returns
   `2026-10-09T00:00`..`T23:00`; fetched at 19:41Z that is 4 hours of future. Use
   `forecast_days=2` (or `forecast_hours`) for a +6/+12 h plume.
8. **Open-Meteo snaps to a grid cell at the summit.** Requested (-8.108, 112.922);
   served (-8.119508, 112.94268), `elevation: 3665.0`. 850 hPa (about 1.5 km) is
   below that cell's ground, but values are still returned.
9. **MAGMA detail URLs need the signature.** `/v1/vona/22880` without
   `?signature=...` returned HTTP 403. Take the full signed URL from the list page.
10. **NICT tiles over Java are black at night** (a 444-byte, 1-bit PNG). Java also
    sits on the seam between 4d tiles `0_2` and `1_2`, so a Java view needs two tiles.
11. **JMA mscweb file names carry the slot start, but the burned-in caption shows
    slot start + 10 min.** `se3_b13_1920.jpg` is captioned `19:30UTC`. File names
    have no date, so each name is overwritten every 24 h.
12. **adsb.lol `nav_altitude_mcp` is quantised.** Values such as 31008, 36992, 29008
    and 38016 mean FL310, FL370, FL290 and FL380. Round to the nearest 100 ft.

---

## aviationweather.gov international SIGMET (`isigmet/`)

`GET https://aviationweather.gov/api/data/isigmet?format=json&hazard=va` returns a
JSON **array** of flat objects (11 tonight). Without `hazard` it returns all hazards
(152). Content-Type `application/json; charset=utf-8`.

| Key | Type | Example | Notes |
|---|---|---|---|
| `icaoId` | str | `"WAAA"` | Issuing MWO, not the FIR |
| `firId` | str | `"WAAF"` | FIR. WIIF for Krakatau, WAAF for Semeru/Ibu/Dukono |
| `firName` | str | `"WAAF UJUNG PANDANG"` | |
| `receiptTime` | str | `"2026-10-09T18:30:42.738Z"` | ISO 8601 with ms and `Z` |
| `validTimeFrom` | int | `1791570000` | Unix seconds (= 2026-10-09 18:20Z) |
| `validTimeTo` | int | `1791591600` | Unix seconds (= 2026-10-10 00:20Z); VA validity is 6 h |
| `seriesId` | str | `"12"`, `"A3"`, `"3F"` | Not an int. `F` suffix = forecast-polygon record (see above) |
| `hazard` | str | `"VA"` | Also `TS`, `TURB`, `TC`, `ICE` in the full feed |
| `qualifier` | str or null | `"ERUPTION MT SEMERU"`, `"ERUPTION MT VOLCAN PURACE"`, `"FUEGO"` | Volcano name is in here |
| `base` | int or null | `0` | Feet; 0 = SFC. Null in 95 of 152 records in the full feed |
| `top` | int or null | `15000` | Feet (FL150). Null in 4 of 152 |
| `geom` | str | `"AREA"` | `"AREAS"` once in the full feed |
| `coords` | list | `[{"lon": 112.883, "lat": -8.05}, ...]` | Decimal degrees, 3 dp, ring closed (last == first). For `AREAS`, a list of rings |
| `dir` | str or null | `"E"`, `"NE"`, `"ENE"`, `"-"` | 16-point compass; `"-"` with `spd: "0"` is STNR; null when the text gives no movement |
| `spd` | str or null | `"10"`, `"0"` | Knots, as a **string** |
| `chng` | str or null | `"NC"`, `"INTSF"`, `"WKN"` | |
| `rawSigmet` | str | see below | `\n` line breaks |

Raw text example (Semeru):

```
WVID21 WAAA 091820
WAAF SIGMET 12 VALID 091820/100020 WAAA-
WAAF UJUNG PANDANG  FIR VA
ERUPTION MT SEMERU PSN S0806 E11255 VA CLD OBS AT 1800Z WI S0803
E11253 - S0754 E11316 - S0807 E11324 - S0820 E11318 - S0811 E11253 -
S0803 E11253 SFC/FL150 MOV E 10KT NC=
```

Quirks: double spaces (`UJUNG PANDANG  FIR`), trailing spaces, a lat/lon pair can
be split across lines, `=` terminates. Other FIRs put the level before the vertices
(`VA CLD OBS AT 1740Z SFC/FL050 N1200 W08610 - ...`) or write `FCST 2330Z VA CLD`
instead of `FCST AT 2200Z WI`. A non-VA record in the full feed has a stray `?`
(`ORBB SIGMET S3 VALID 091850/092250 ORBI?`). The JSON `coords` already resolve all
of this, so parse geometry from `coords` and keep `rawSigmet` for display and audit.

Tonight's VA set: WAAF 11 Dukono SFC/FL070 MOV NE 10KT; WIIF 07 Krakatau SFC/FL060
MOV W 05KT; WAAF 12 Semeru SFC/FL150 MOV E 10KT; WAAF 13 Ibu SFC/FL070 MOV E 10KT
INTSF; plus Purace (SKED), Reventador x2, Masaya x2, Fuego x2. No RJJJ (Sakurajima).

## MAGMA Indonesia VONA (`magma/`)

Server-rendered Laravel HTML, `text/html; charset=UTF-8`. No public JSON.

### List page `https://magma.esdm.go.id/v1/vona` (`?page=N`, 15 per page, 1243 pages)

Each entry is one `div.timeline-item`:

```html
<div class="timeline-time"><small>2026-10-09 18:00:00 UTC</small>
  <a href="#" class="btn btn-sm btn-warning">Orange</a></div>
<div class="timeline-body">
  <p class="timeline-title"><a href="#">Semeru - 20261009/1800Z</a></p>
  <p class="timeline-author"><a href="#">{observer name}</a>, Semeru Volcano Observatory - 1 hour ago </p>
  <p class="timeline-text">Eruption at 1800 UTC (0100 local). Ash-cloud is not observed. Ash-cloud is not observed..</p>
  <a class="card-link m-b-10" href="https://magma.esdm.go.id/v1/vona/22889?signature=5412ce61...2305bad">View</a>
```

- Issue time: `<small>YYYY-MM-DD HH:MM:SS UTC</small>`, and again as `YYYYMMDD/HHMMZ` in the title.
- Colour: button text `Orange` / `Green` / `Red` with classes `btn-warning` / `btn-success` /
  `btn-danger` (all three appear in the 22-page census under `research/data/census`;
  Yellow was not seen).
- Title is `{Volcano name} - {YYYYMMDD/HHMMZ}`. Names seen: `Semeru`, `Ibu`,
  `Anak Krakatau`, `Ili Lewotolok`, `Dukono`, ... There is no volcano ID in the list.
  No `Lewotobi` VONA appears in the 22 census pages.
- `timeline-text` is the detail page's rows 11 + 12 + 13 joined, ending in `..`.
- Detail link: numeric id plus a 64-hex `signature`. The id increases by one per VONA.
- `timeline-date` separators (`9th of October 2026, 1 day ago`) and "N hours ago"
  are relative to fetch time; ignore them.

### Detail page `https://magma.esdm.go.id/v1/vona/{id}?signature={hex}`

`<title>ORANGE | SEMERU | 20261008/2103Z` (newline before `</title>`). The body is one
table of 16 rows, each `<td>(n)</td><td><b>Label</b></td><td><b>:</b></td><td>value</td>`:

| # | Label | Ash observed (22880) | Ash not observed (22889) |
|---|---|---|---|
| 2 | Issued | `20261008/2103Z` | `20261009/1800Z` |
| 3 | Volcano | `Semeru (263300)` (GVP number) | `Semeru (263300)` |
| 4 | Current Aviation Colour Code | `<b>ORANGE</b>` | `ORANGE` |
| 5 | Previous Aviation Colour Code | `orange` (lower case) | `orange` |
| 6 | Source | `Semeru Volcano Observatory` | |
| 7 | Notice Number | `2026SMR1913` | `2026SMR1920` |
| 8 | Volcano Location | `S 08 deg 06 min 29 sec E 112 deg 55 min 12 sec` | |
| 9 | Area | `East java, Indonesia` | |
| 10 | Summit Elevation | `11763 FT (3676 M)` | |
| 11 | Volcanic Activity Summary | `Eruption with volcanic ash cloud at 2103 UTC (0403 local).` | `Eruption at 1800 UTC (0100 local).` |
| 12 | Volcanic Cloud Height | `Best estimate of ash-cloud top is around 14003 FT (4376 M) above sea level or 2240 FT (700 M) above summit. May be higher than what can be observed clearly. Source of height data: ground observer.` | `Ash-cloud is not observed.` |
| 13 | Other Volcanic Cloud Information | `Ash cloud moving to north. Volcanic ash is observed to be white to gray. The intensity of volcanic ash is observed to be thick.` | `Ash-cloud is not observed.` |
| 14 | Remarks | `Eruption recorded on seismogram with maximum amplitude 19 mm and maximum duration 139 second.` | |
| 15-16 | Contacts, Next Notice | boilerplate | |

Ibu (22881): `Ibu (268030)`, `N 01 deg 29 min 17 sec E 127 deg 37 min 48 sec`,
`North Maluku, Indonesia`, `4240 FT (1325 M)`, top `5520 FT (1725 M)` ASL /
`1280 FT (400 M)` above summit, `Ash cloud moving to east.`, gray, medium,
`(1037 local)` for 0137 UTC.

Parsing notes:

- Ash top ASL = summit + above-summit, in metres (3676 + 700 = 4376). Use metres; see the 3.2 factor above.
- "local" is the observatory's zone: +7 for Semeru (WIB), +9 for Ibu (WIT).
- Direction is English words after `Ash cloud moving to`. Census vocabulary: `north`,
  `northeast`, `east`, `southeast`, `south`, `southwest`, `west`, `northwest`, and
  ranges `from northeast to east`, `from west to northwest`, `from north to northeast`,
  `from southeast to southwest`, `from southeast to south`, `from southwest to west`.
- Colour: `white`, `gray`, `white to gray`, `gray to dark`, `white to brown`.
  Intensity: `thin`, `medium`, `thick`, `from medium to thick`, `from thin to thick`.
- Row 11 also appears as `Increasing in volcanic activity.`
- Summit elevation differs from the VAAC's: MAGMA Semeru 3676 M, Darwin `SOURCE ELEV: 3657M AMSL`.

## VAA text (Tokyo, Darwin, and the other VAACs on BoM)

All VAACs follow the ICAO Annex 3 VAA layout. Observed field lines, in order:

```
FVFE01 RJTD 081500                 WMO header TTAAii CCCC DDHHMM
VA ADVISORY
DTG: 20261008/1500Z
VAAC: TOKYO
VOLCANO: TAAL 273070               name + 6-digit GVP number
PSN: N1400 E12100
AREA: PHILIPPINES
SOURCE ELEV: 311M AMSL             Anchorage: 5159 FT AMSL
ADVISORY NR: 2026/23               not zero-padded (Washington pads: 2026/017)
INFO SOURCE: HIMAWARI-9            also "JMA HIMAWARI-9", "HIMAWARI-9, CVGHM", "HIMAWARI-9 CVGHM"
ERUPTION DETAILS: VA CONTINUOUSLY OBS IN SATELLITE IMAGERY
OBS VA DTG: 08/1420Z               DD/HHMMZ only; take month/year from DTG
OBS VA CLD: SFC/FL150 N1340 E12014 - N1326 E12008 - N1316 E12015 - N1330 E12023 MOV SW 15KT
FCST VA CLD +6 HR: 08/2020Z SFC/FL160 N1321 E11910 - N1230 E11932 - N1231 E11904 - N1320 E11801
FCST VA CLD +12 HR: 09/0220Z SFC/FL180 N1259 E11812 - ...
FCST VA CLD +18 HR: NO VA EXP
RMK: SOME PART OF VA OBSCURED BY MET CLOUD.
NXT ADVISORY: 20261008/1800Z=
```

Variants seen:

| Field | Values |
|---|---|
| OBS/EST | `OBS VA DTG:` / `OBS VA CLD:`, or `EST VA DTG:` / `EST VA CLD:` (Darwin Manam 2026/51) |
| No ash | Tokyo `VA NOT IDENTIFIABLE FM SATELLITE DATA WIND FL180 040/1KT`; Darwin `VA NOT IDENTIFIABLE FM SATELLITE DATA WIND SFC/FL070 160/05KT`; Anchorage `VA NOT IDENTIFIABLE FROM SATELLITE` |
| Forecast none | Tokyo `FCST VA CLD +18 HR: NO VA EXP`; Darwin `FCST VA CLD +12 HR: 10/0350Z NO VA EXP` (time included); Anchorage `FCST VA CLD +6HR: NO VA EXP` (no space before `HR`) |
| Next | `20261008/1800Z`, `NO LATER THAN 20261009/2150Z`, `NO FURTHER ADVISORIES` |
| Terminator | `=` at the end of `NXT ADVISORY`; the Anchorage copy on BoM has none |

Geometry rules:

- Vertices are `[NS]DDMM [EW]DDDMM` separated by ` - `. VAA polygons are **not closed**
  (4-5 vertices, last != first); close them yourself. The SIGMET copies are closed.
- Level band precedes the vertices: `SFC/FL150`. `MOV {dir} {nn}KT` follows them.
- Only one polygon per time step appears in these fixtures; ICAO allows several
  (`... AND FL100/FL200 ...`), so do not assume one.
- One malformed coordinate exists on BoM: Anchorage `PSN: N5147 W178047`. Fail soft.
- Line wrapping differs by source and can split a lat/lon pair: Tokyo breaks after
  `- `; BoM `process.php` breaks between lat and lon (`N0222<br />E12839`); BoM 7-day
  text indents continuations by 8 spaces. Join continuation lines first (a new field
  starts with a known `KEY:` at line start), then tokenise.
- The WMO header number is not per volcano (Darwin used FVAU04 for both Krakatau and
  Manam, FVAU05 for both Manam and Taal). Key advisories on volcano + `ADVISORY NR`.
- RMK carries the useful prose: `VA NOT IDENTIFIABLE ON CURRENT SATELLITE IMAGERY. VA
  EMISSION IS EXPECTED TO BE ONGOING ... VA AREA IS AN ESTIMATED AREA.` (Darwin draws
  an estimated polygon even when satellite cannot see the ash.)

### Tokyo list `https://ds.data.jma.go.jp/svd/vaac/data/vaac_list.html`

Content-Type `text/html` with no charset parameter; the page declares `<meta charset="UTF-8">`. Rows are
`<tr class="mtx" id=trN ...>` inside `<tbody id="tbd1">`, newest first, 158 rows back to
2026-09-01:

| Cell | Example |
|---|---|
| 0 (hidden, sort key) | `<td style="DISPLAY: none">2026/10/08 15:00:00</td>` |
| 1 | `15:00 UTC, 08 Oct. 2026` |
| 2 volcano | `TAAL`, `SAKURAJIMA (AIRA CALDERA)` |
| 3 area | `PHILIPPINES`, `JAPAN`, `RUSSIA` |
| 4 number | `<font size=2 color="black">2026/23</font>` |
| 5 text | `<a href="TextData/2026/20261008_27307000_0023_Text.html">Text</a>` |
| 6-9 | VAG / VAGI / VAGFN / SAT links in `onClick="opennewwide('VAG/2026/html/..._PF15.html')"`, or `-` |

Text URL = `https://ds.data.jma.go.jp/svd/vaac/data/` + href. File id is
`{YYYYMMDD}_{GVP number + 2 digits}_{NNNN}`: Sakurajima 282080 -> `28208001`, Taal
273070 -> `27307000`, Dukono 268010 -> `26801000`, NOTICE -> `99999902`. A `VAG` link
present usually means the text has polygons (0278, 0023); a `-` usually means VA not
identifiable (0279). Treat that as a hint, not a rule.

### Tokyo text page `.../TextData/YYYY/{id}_Text.html`

The advisory sits between `<!-- VAA Text Start -->` and `<!-- VAA Text End -->` inside
`<div class="mtx">`, lines separated by upper-case `<BR>`, last line `...=<BR>`. Page
`<title>` is `Tokyo VAAC | Volcanic Ash Advisory Text` for Darwin texts too.

### Darwin via JMA `.../vaac_darwin_list.html`

Same table layout as the Tokyo list. Stale and sparse (see the top section). Its two
newest texts (Dukono 2026/788, Ibu 2026/1081, both 2026-09-23) are saved for format
coverage only.

### Darwin via BoM

**`POST https://www.bom.gov.au/aviation/php/process.php`**, form body
`page=volcanic-ash-darwin&javascript=1` (the page's own XHR). Responds
`text/html; charset=UTF-8` but the body is JSON:

```json
{"total": 5,
 "advisories": {
   "2": {"text": "<p class=\"product\">FVAU01 ADRM 091550<br \/>VA ADVISORY<br \/>...NXT ADVISORY: NO LATER THAN 20261009\/2150Z=<\/p><br \/>",
         "graphic": "IDY65280.png", "isBackup": false, "name": "DUKONO 268010"},
   "4": {...}, "5": {...}, "7": {...}, "8": {...}}}
```

- `advisories` is an **object keyed by non-contiguous string indices**, not a list.
- `text` is HTML: `<p class="product">`, `<br />` line breaks, JSON-escaped `\/`.
- `graphic` resolves to `https://www.bom.gov.au/fwo/{graphic}` (from `va.js`).
- `name` is `{VOLCANO} {GVP number}`.
- `va.js` shows the "nil" message when `total == 0`; the empty shape was not observed.
- Tonight: Dukono 2026/855, Ibu 2026/1148, Semeru 2026/1157, Krakatau 2026/225, Manam
  2026/51 (Manam is a terminated `NO FURTHER ADVISORIES` still listed).

**`GET https://www.bom.gov.au/products/Volc_ash_recent.shtml`**: static HTML, all
nine VAACs, last 7 days, newest first. Each VAAC is
`<h3>Darwin VAAC</h3><pre>IDD60156 ... </pre>`; inside, each advisory starts with

```
Received FVAU03 at 19:28 UTC, 09/10/26 from ADRM
```

(`HH:MM UTC, DD/MM/YY`, day first, two-digit year) followed by the VAA text with
8-space continuation indents. Darwin block: 32 advisories 2026-10-06..10-09 (Ibu,
Semeru, Krakatau, Dukono, Manam, Taal, Karangetang). Tokyo's Sakurajima appears as
`SAKURAJIMA [AIRA CALDERA] 282080` (square brackets) where JMA writes parentheses.
Anchorage inserts an extra `VAAAK1` line after the `Received` line. This is the
simplest source for a Darwin parser and gives history for free.

## TAF and METAR (`wx/`)

`GET https://aviationweather.gov/api/data/taf?ids=WARR,WADD,WIII,WAAA,RJFK,RJFF,RPLL,WSSS&format=json`
and the same for `/metar`. JSON arrays, one object per airport, sorted by ICAO id
(RJFF, RJFK, RPLL, WAAA, WADD, WARR, WIII, WSSS), not request order.

METAR keys: `icaoId`, `receiptTime` (ISO), `obsTime` (Unix s), `reportTime`
(`"2026-10-09T19:30:00.000Z"`), `temp`/`dewp` (deg C), `wdir`, `wspd` (kt), `visib`,
`altim` (hPa, `1018`), `qcField`, `metarType` (`"METAR"`), `rawOb`, `lat`, `lon`, `elev`
(m), `name` (`"Fukuoka Arpt, 40, JP"`), `cover`, `clouds` (`[{"cover":"FEW","base":2000}]`,
base in ft), `fltCat` (`VFR`/`MVFR`/`IFR`), and `wxString` (`"HZ"`) **only when present**.

TAF keys: `icaoId`, `dbPopTime`, `bulletinTime`, `issueTime` (ISO), `validTimeFrom`,
`validTimeTo` (Unix s), `rawTAF`, `mostRecent` (1), `remarks`, `lat`, `lon`, `elev`,
`prior`, `name`, `fcsts`. Each `fcsts[]` item: `timeFrom`, `timeTo`, `timeBec` (Unix s;
`timeBec` set on BECMG), `fcstChange` (`null` for the base period, `"TEMPO"`,
`"BECMG"`), `probability`, `wdir`, `wspd`, `wgst`, `wshearHgt`, `wshearDir`,
`wshearSpd`, `visib`, `altim`, `vertVis`, `wxString` (`"HZ"`, `"NSW"`, `"SHRA BR"`),
`notDecoded`, `clouds` (`[{"cover":"FEW","base":2300,"type":"CB"}]`), `icgTurb`, `temp`.

Type traps:

- `visib` is `"6+"` (string), a float in **statute miles** (`2.49` = 4000 m, `3.11` =
  5000 m, `4.97` = 8000 m, `1.86` = 3000 m), or `""` in TEMPO groups that omit it.
- `wdir` is an int or `"VRB"`; null in TEMPO groups without wind.
- RJFK's METAR was `091200Z` at a 19:40Z fetch (7.5 h old); check `obsTime` age.
- Tonight's raw examples: `METAR WARR 091930Z 24004KT 5000 HZ FEW020 26/23 Q1010 NOSIG`;
  `TAF WARR 091700Z 0918/1018 26005KT 4000 HZ FEW020 BECMG 1000/1002 10010KT 9999 NSW`.

## adsb.lol (`adsb/`)

`GET https://api.adsb.lol/v2/point/{lat}/{lon}/{radius_nm}` returns
`{"ac": [...], "msg": "No error", "now": 1791574846501, "total": 7, "ctime": 1791574846501, "ptime": 0}`.
`now`/`ctime` are Unix **milliseconds**. `ac` is not sorted by distance.

Aircraft keys (readsb format; every key is optional, counts vary per aircraft):

| Key | Example | Notes |
|---|---|---|
| `hex` | `"8a091f"` | ICAO 24-bit, lower case |
| `type` | `"adsb_icao"` | Message source |
| `flight` | `"BTK6264 "` | Callsign padded to 8 with spaces; **missing** on some (HS-THX, JA216P) |
| `r`, `t` | `"PK-BKJ"`, `"A320"` | Registration and ICAO type from adsb.lol's database |
| `alt_baro` | `31025` | Feet. readsb documents the string `"ground"`; not seen here |
| `alt_geom` | `33150` | Feet |
| `gs` | `458.7` | Knots |
| `track` | `93.25` | Degrees true |
| `calc_track` | `247` | Present instead of `track`/`gs` on 2 Kyushu aircraft with stale positions |
| `nav_altitude_mcp` | `31008` | Selected altitude, quantised; round to 100 ft |
| `nav_altitude_fms` | `35392`, `18240` | FMS altitude; can be far from cruise (MAS128 at FL400 shows 18240) |
| `nav_heading`, `nav_qnh`, `nav_modes` | `..., 1012.8, ["autopilot","vnav","lnav","tcas"]` | |
| `lat`, `lon` | `-6.387945`, `109.168159` | |
| `seen_pos` | `0.383` | Seconds since last position, relative to `now`. Up to `48.863` here |
| `seen` | `0.0` | Seconds since any message |
| `dst` | `240.137` | Distance from the query point, nm |
| `dir` | `292.0` | Bearing from the query point, degrees |
| `category` | `"A3"`, `"A5"`, `"A0"` | |
| `squawk`, `emergency` | `"2361"`, `"none"` | |
| `mlat`, `tisb` | `[]` | Lists of field names derived by MLAT/TIS-B |

Also present: `ias`, `tas`, `mach`, `wd`, `ws`, `oat`, `tat`, `track_rate`, `roll`,
`mag_heading`, `true_heading`, `baro_rate`, `geom_rate`, `nic`, `rc`, `version`,
`nic_baro`, `nac_p`, `nac_v`, `sil`, `sil_type`, `gva`, `sda`, `alert`, `spi`, `messages`, `rssi`.

Counts at 02:40 WIB / 04:40 JST: East Java 250 nm 7, Jakarta 150 nm 6, Kyushu 200 nm 19.
The same aircraft (8a091f BTK6264) appears in both Java and Jakarta circles; de-duplicate on `hex`.

## Open-Meteo (`openmeteo/`)

```
https://api.open-meteo.com/v1/forecast?latitude=-8.108&longitude=112.922
  &hourly=wind_speed_850hPa,wind_direction_850hPa,...,wind_speed_200hPa,wind_direction_200hPa
  &wind_speed_unit=kn&forecast_days=1
```

```json
{"latitude": -8.119508, "longitude": 112.94268, "generationtime_ms": 55.5,
 "utc_offset_seconds": 0, "timezone": "GMT", "timezone_abbreviation": "GMT", "elevation": 3665.0,
 "hourly_units": {"time": "iso8601", "wind_speed_850hPa": "kn", "wind_direction_850hPa": "°", ...},
 "hourly": {"time": ["2026-10-09T00:00", ...], "wind_speed_850hPa": [2.3, ...], "wind_direction_850hPa": [311, ...], ...}}
```

- Column-oriented: parallel arrays under `hourly`, 24 entries, no nulls tonight.
- `time` strings have no seconds and no `Z`; they are UTC because `timezone` is GMT.
- Speeds are floats in knots; directions are int degrees the wind blows **from**.
  Ash drifts toward `direction + 180`.
- At 19:00Z over Semeru: 600 hPa 6.6 kt from 290 (ash would drift ESE), 500 hPa 4.9 kt
  from 67, 400 hPa 20.1 kt from 159. The SIGMET says MOV E 10KT at SFC/FL150 (~570 hPa).
- Approximate pressure-to-FL (standard atmosphere): 850 = FL050, 700 = FL100,
  600 = FL140, 500 = FL180, 400 = FL240, 300 = FL300, 250 = FL340, 200 = FL390.

## Himawari imagery (`himawari/`)

### NICT

`GET https://himawari8.nict.go.jp/img/D531106/latest.json` returns
`{"date":"2026-10-09 19:20:00","file":"PI_H09_20261009_1920_TRC_FLDK_R10_PGPFD.png"}`.
`date` is the scan start in UTC with no zone marker. There is a `file` key the spec
did not mention; the tile URLs do not use it. Fetched at 19:41:23Z, so about 21 min
after scan start.

Tile URL:
`https://himawari8.nict.go.jp/img/D531106/{L}d/550/{YYYY}/{MM}/{DD}/{HHMMSS}_{x}_{y}.png`
with `L` in 1, 2, 4, 8, 16, 20 tiles per side, `x` = column from west, `y` = row from
north, both from 0. Every tile is 550x550 PNG. Level 1d is the full disk in one tile.

- Night tiles are a 444-byte, 1-bit grayscale all-black PNG; daytime tiles are about
  520 KB RGB. Size under 1 KB is a reliable "dark" test.
- At 4d, `1_2` covers Flores (Lewotobi, Lewotolok), Timor and NW Australia; `0_2`
  covers the Indian Ocean with Java and Bali in its top-right corner. Semeru is near the
  seam of the two.

### JMA Meteorological Satellite Center

Pattern (from `sat_img.js`):
`https://www.data.jma.go.jp/mscweb/data/himawari/img/{area}/{area}_{element}_{HHMM}.jpg`

- `area` codes: `fd_`, `aus`, `ca1`, `nzl`, `pi1`..`pi9`, `pia`, `se1`, `se2`, `se3`, `se4`,
  `ha1`..`ha6`, `hp1`..`hp3`, `jpn`.
- `element` codes: `b13` (IR), `b03` (visible), `b08` (water vapour), `b07` (SWIR),
  `dms`, `ngt` (night microphysics), `dst` (Dust RGB), `arm` (airmass), `dsl`, `dnc`,
  `tre`, `trm`, `cve`, `snd`, `vir`, `irv`, `hrp`.
- `HHMM` is the 10-minute slot start. The list of slots that exist right now is the
  `<select name="slt_time">` in `https://www.data.jma.go.jp/mscweb/data/himawari/sat_img.php?area=se3`:
  `<option value=1920>19:30 UTC 09 October 2026</option>`, 137 options back to
  `2000` on 08 October. The option label and the burned-in caption are slot + 10 min.
  The file name has no date and is overwritten after 24 h, so store frames under the
  date and time from the option label.
- `se3`: 1101x501 JPEG, about 200-230 KB. Coastlines (green) and a dotted 10-degree
  graticule are burned in. Graticule lines sit at x = 200, 400, 600, 800, 1000 and
  y = 200, 400, which with coastline checks gives an equirectangular grid of 0.05
  deg/px from 90E, 10N (top-left) to 145E, 15S. Semeru is near pixel (458, 362).
  This georeference is inferred, not published; check it before drawing on top.
- `jpn`: 801x641 JPEG. Graticule columns at x = 100, 300, 500, 700 (20 px/deg,
  115E..155E) and rows near y = 200 and 445, consistent with a Mercator grid from about
  47N to 21N. Also inferred.
- Images contain no metadata beyond JFIF.

## NOAA Himawari-9 on AWS (`aws_himawari/`)

`GET https://noaa-himawari9.s3.amazonaws.com/?list-type=2&prefix=AHI-L1b-FLDK/2026/10/09/1800/`
returns S3 `ListBucketResult` XML in namespace `http://s3.amazonaws.com/doc/2006-03-01/`:
`KeyCount` 160, `MaxKeys` 1000, `IsTruncated` false, then `Contents` with `Key`,
`LastModified`, `ETag`, `ChecksumAlgorithm` (`CRC32`), `ChecksumType`, `Size`,
`StorageClass`.

- Directories are per 10-minute slot (`.../HHMM/`), not per hour. An hour prefix
  (`.../2026/10/09/18`) would hold 960 keys, still under 1000.
- Key: `AHI-L1b-FLDK/2026/10/09/1800/HS_H09_20261009_1800_B13_FLDK_R20_S0510.DAT.bz2`
  = band `B01`..`B16`, resolution `R05`/`R10`/`R20` (0.5/1/2 km), segment `S{nn}10`
  (nn of 10, north to south).
- One slot is 500.4 MB; Band 13 alone is 23.2 MB over 10 segments (README has the table).
- Objects appeared 10.6-13.9 min after scan start.
- At 2 km, Java (8.1S) falls in segment 06 and Kyushu (31.6N) in segment 03, computed
  from the HSD fixed-grid geometry (LOFF 2750.5, 312.3 lines per degree of scan angle).
  Not checked against data.
