# Feed fixtures

Real responses from the public feeds TEPHRA reads, saved byte for byte so parsers
can be written and tested against the formats the feeds actually serve. Field
names, value formats and quirks are in [FORMATS.md](FORMATS.md).

All files were fetched on 2026-10-09 between 19:36Z and 19:44Z (02:36-02:44 WIB,
04:36-04:44 JST) with `curl -L --compressed`, a descriptive User-Agent
(`tephra-fixture-sampler/0.1`), no cookies and no credentials, with 1-2 s between
requests. Night in Indonesia and Japan matters for three of them: ADS-B counts are
low, NICT true-colour tiles over Java are black, and the JMA images are infrared.

Do not "refresh" these files in place. Tests can pin the sha256 values below; if a
feed changes format, add a new dated fixture next to the old one.

The pages are third-party content and are kept unedited. They carry the sites' own
anonymous session values (MAGMA `csrf-token` meta tags, BoM analytics beacons) and
public office contact addresses; none of these are TEPHRA credentials.

## Layout

| Folder | Feed |
|---|---|
| `isigmet/` | aviationweather.gov international SIGMET JSON |
| `magma/` | MAGMA Indonesia VONA list and detail pages (HTML) |
| `tokyo_vaac/` | Tokyo VAAC advisory list and advisory text pages (HTML) |
| `darwin_vaac/` | Darwin VAAC: JMA-hosted list and texts, BoM pages and BoM's JSON endpoint |
| `wx/` | aviationweather.gov TAF and METAR JSON |
| `adsb/` | adsb.lol `/v2/point` JSON |
| `openmeteo/` | Open-Meteo pressure-level winds JSON |
| `himawari/` | NICT `latest.json` and tiles, JMA MSC Band-13 and Dust RGB images |
| `aws_himawari/` | NOAA Himawari-9 S3 bucket listing (XML only) |

## Files

### `isigmet/`

**`isigmet/isigmet_va.json`**  
International SIGMETs filtered to volcanic ash. 11 records; 4 in Indonesia (WAAF Dukono 11, Semeru 12, Ibu 13; WIIF Krakatau 07). No Sakurajima (RJJJ) VA SIGMET was open.

- URL: `https://aviationweather.gov/api/data/isigmet?format=json&hazard=va`
- Fetched: 2026-10-09T19:36:48Z · HTTP 200 · `application/json; charset=utf-8` · 8,343 bytes
- sha256: `e3ade89102a491afa8aee98e37d8145c8c2db1bf31e0f93094dc603005e096fa`

**`isigmet/isigmet_all.json`**  
All international SIGMETs (152: TS 83, TURB 36, TC 11, VA 11, ICE 11). Contains one `geom: AREAS` record (coords is a list of rings); `base` is null in 95 records and `top` in 4.

- URL: `https://aviationweather.gov/api/data/isigmet?format=json`
- Fetched: 2026-10-09T19:36:50Z · HTTP 200 · `application/json; charset=utf-8` · 128,538 bytes
- sha256: `09b1da34acb3ec82737005121d1827284f2508d0df8f73de87b0e2e010138297`


### `magma/`

**`magma/vona_list.html`**  
MAGMA VONA list, page 1 (15 entries, 2026-10-08 01:49Z to 2026-10-09 18:00Z; Semeru x13, Anak Krakatau x1, Ibu x1). Pagination shows 1243 pages.

- URL: `https://magma.esdm.go.id/v1/vona`
- Fetched: 2026-10-09T19:37:17Z · HTTP 200 · `text/html; charset=UTF-8` · 44,115 bytes
- sha256: `b3f36b0eb33e49070751970fd4516a24623925a00489a2d7f67e3ea319b72cd3`

**`magma/vona_22880_semeru_ash.html`**  
VONA detail, Semeru 20261008/2103Z, ash observed: top 14003 FT (4376 M) ASL, moving north, ORANGE.

- URL: `https://magma.esdm.go.id/v1/vona/22880?signature=9678e5287b728bc1210c62090abbbab47c3fa7e66f72a155954ab56c74cc2d03`
- Fetched: 2026-10-09T19:37:35Z · HTTP 200 · `text/html; charset=UTF-8` · 15,330 bytes
- sha256: `1dc4c5adac0f8de0f018a3358a88e88610dc033f82e05b00f20cf3de3d182b24`

**`magma/vona_22881_ibu_ash.html`**  
VONA detail, Ibu 20261009/0137Z, ash observed: top 5520 FT (1725 M) ASL, moving east, ORANGE.

- URL: `https://magma.esdm.go.id/v1/vona/22881?signature=9b1dd1019782c6c6dc83817dc6f9538e08b294a61f3ec41481dbcb4a462b58df`
- Fetched: 2026-10-09T19:37:38Z · HTTP 200 · `text/html; charset=UTF-8` · 15,299 bytes
- sha256: `1523cbec2f668df029b8eba532c9a57460e6c0c0a6c8cde559b64bc2e0e09d7d`

**`magma/vona_22889_semeru_no_ash.html`**  
VONA detail, Semeru 20261009/1800Z, eruption on seismogram, 'Ash-cloud is not observed.' (Darwin advisory 2026/1157 for the same 1800Z says VA to FL150 observed on satellite.)

- URL: `https://magma.esdm.go.id/v1/vona/22889?signature=5412ce61fc8ab19051a3a1682ceb3ec3cfcf9aca8457455414c1cadda2305bad`
- Fetched: 2026-10-09T19:37:39Z · HTTP 200 · `text/html; charset=UTF-8` · 15,035 bytes
- sha256: `c51fb92d8d044a3126c2e39b7de14b49dc4620f56686650e90e7048b9392ddd4`


### `tokyo_vaac/`

**`tokyo_vaac/vaac_list.html`**  
Tokyo VAAC advisory list (158 rows, 2026-09-01 03:17Z to 2026-10-08 17:50Z; Sakurajima 96, Sheveluch 22, Mayon 19, Chikurachki 7, Kanlaon 7, Taal 4, Alaid 2, Krasheninnikov 1).

- URL: `https://ds.data.jma.go.jp/svd/vaac/data/vaac_list.html`
- Fetched: 2026-10-09T19:38:17Z · HTTP 200 · `text/html` · 117,112 bytes
- sha256: `6498b9361c125bdadfddcdd1185e8471777adf26bcbd0dfcf2580498e496c890`

**`tokyo_vaac/20261008_28208001_0278_Text.html`**  
Tokyo VAA, Sakurajima 2026/278: observed polygon SFC/FL080 MOV N 10KT, +6 h and +12 h polygons, +18 h NO VA EXP.

- URL: `https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20261008_28208001_0278_Text.html`
- Fetched: 2026-10-09T19:38:38Z · HTTP 200 · `text/html` · 1,133 bytes
- sha256: `3f7b52c85a6f1645fed5c4af176d1450d39781af29b8a7c3d64e667d479ebf1b`

**`tokyo_vaac/20261008_28208001_0279_Text.html`**  
Tokyo VAA, Sakurajima 2026/279: 'VA NOT IDENTIFIABLE FM SATELLITE DATA WIND FL180 040/1KT', all forecasts NO VA EXP, NO FURTHER ADVISORIES.

- URL: `https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20261008_28208001_0279_Text.html`
- Fetched: 2026-10-09T19:38:40Z · HTTP 200 · `text/html` · 979 bytes
- sha256: `79ac08dc189855a1d4415450df257126c107d360b8ad313c7eaa87c77140b09a`

**`tokyo_vaac/20261008_27307000_0023_Text.html`**  
Tokyo VAA, Taal 2026/23: observed polygon SFC/FL150 MOV SW 15KT, +6 h (FL160) and +12 h (FL180) polygons, +18 h NO VA EXP, RMK about met cloud.

- URL: `https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20261008_27307000_0023_Text.html`
- Fetched: 2026-10-09T19:38:42Z · HTTP 200 · `text/html` · 1,165 bytes
- sha256: `ff8f0ee47846f609dc565101853669bf132f305d7586811dcf468a120de9f433`


### `darwin_vaac/`

**`darwin_vaac/vaac_darwin_list.html`**  
JMA-hosted Darwin list. Sparse: 34 rows back to 2015-11-25, 19 of them NOTICE messages; newest 2026-09-23 (Dukono 2026/788, Ibu 2026/1081). It is not a live mirror of Darwin output.

- URL: `https://ds.data.jma.go.jp/svd/vaac/data/vaac_darwin_list.html`
- Fetched: 2026-10-09T19:38:53Z · HTTP 200 · `text/html` · 21,797 bytes
- sha256: `fbb4dccfc32b8caa65f5562870e8638f62cb24f52b8e5ca4ef879e0a74b4942f`

**`darwin_vaac/20260923_26801000_0788_Text.html`**  
Darwin VAA via JMA, Dukono 2026/788: polygon plus RMK 'VA NOT IDENTIFIABLE ON CURRENT SATELLITE IMAGERY ... VA AREA IS AN ESTIMATED AREA'.

- URL: `https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20260923_26801000_0788_Text.html`
- Fetched: 2026-10-09T19:39:02Z · HTTP 200 · `text/html` · 1,437 bytes
- sha256: `838e95e1818aeb5aee4e00ce6fa480abdfa39ab73aae0ebb37c6eaab95254c75`

**`darwin_vaac/20260923_26803000_1081_Text.html`**  
Darwin VAA via JMA, Ibu 2026/1081: polygon built from ground reports while satellite cannot see the ash.

- URL: `https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20260923_26803000_1081_Text.html`
- Fetched: 2026-10-09T19:39:04Z · HTTP 200 · `text/html` · 1,471 bytes
- sha256: `7cf09e307713a9f07fabf7a136d83b03fd2b367b43dd77b5c1e04d84e959eb9e`

**`darwin_vaac/bom_darwin_va_advisory.html`**  
BoM Darwin VA advisory page. Static HTML only: the advisories are loaded by JavaScript (see the next file). The 'Nil current Darwin Volcanic Ash Advisories.' text in it is a hidden fallback (display:none).

- URL: `https://www.bom.gov.au/aviation/volcanic-ash/darwin-va-advisory.shtml`
- Fetched: 2026-10-09T19:39:13Z · HTTP 200 · `text/html; charset=UTF-8` · 39,169 bytes
- sha256: `eb521a21a485b622f92f8a925d0b4aafc4349e32b58da3ba0a380315a2f882ff`

**`darwin_vaac/bom_volc_ash_recent.html`**  
BoM 'Volcanic Ash Advisories Received in Last 7 Days' for all nine VAACs, plain text in <pre> blocks. Darwin block holds 32 advisories (2026-10-06 to 2026-10-09).

- URL: `https://www.bom.gov.au/products/Volc_ash_recent.shtml`
- Fetched: 2026-10-09T19:39:15Z · HTTP 200 · `text/html; charset=UTF-8` · 90,840 bytes
- sha256: `ed649293f93417029475182894a091279ab0b374735baf16ade9d2085e0984bb`

**`darwin_vaac/bom_process_volcanic-ash-darwin.json`**  
The XHR the BoM page makes (from /aviation/volcanic-ash/js/va.js): 5 current Darwin advisories (Dukono 855, Ibu 1148, Semeru 1157, Krakatau 225, Manam 51). Body is JSON although Content-Type says text/html.

- URL: `https://www.bom.gov.au/aviation/php/process.php` (HTTP POST, form body `page=volcanic-ash-darwin&javascript=1`, headers `X-Requested-With: XMLHttpRequest` and a Referer of the advisory page)
- Fetched: 2026-10-09T19:39:49Z · HTTP 200 · `text/html; charset=UTF-8` · 5,531 bytes
- sha256: `bff477b976943a1b49d9b140bb347a71f4045be1c4aa4672bc62513176ff7ad2`


### `wx/`

**`wx/taf.json`**  
TAF JSON for the 8 corridor airports (one most-recent TAF each).

- URL: `https://aviationweather.gov/api/data/taf?ids=WARR,WADD,WIII,WAAA,RJFK,RJFF,RPLL,WSSS&format=json`
- Fetched: 2026-10-09T19:40:20Z · HTTP 200 · `application/json; charset=utf-8` · 9,841 bytes
- sha256: `1fbb88542ff05f508a82f6cfef55ad1b5b6cdcea54d4392eba4eb4efdd06ec0b`

**`wx/metar.json`**  
METAR JSON for the 8 corridor airports. RJFK is 7.5 h old (091200Z).

- URL: `https://aviationweather.gov/api/data/metar?ids=WARR,WADD,WIII,WAAA,RJFK,RJFF,RPLL,WSSS&format=json`
- Fetched: 2026-10-09T19:40:23Z · HTTP 200 · `application/json; charset=utf-8` · 3,590 bytes
- sha256: `62f3f7b09a0423fbfd07a1ef1c775982c5d6153871bb21d2614a57bd61dc8beb`


### `adsb/`

**`adsb/point_java_-7.9_112.9_250.json`**  
adsb.lol point query, East Java, 250 nm: 7 aircraft at 02:40 WIB.

- URL: `https://api.adsb.lol/v2/point/-7.9/112.9/250`
- Fetched: 2026-10-09T19:40:46Z · HTTP 200 · `application/json` · 4,292 bytes
- sha256: `a5b05cda7dc15d4ac45d5f156f7ac835896a4a371137637565ab37414e45676d`

**`adsb/point_jakarta_-6.1_106.7_150.json`**  
adsb.lol point query, Jakarta, 150 nm: 6 aircraft at 02:40 WIB.

- URL: `https://api.adsb.lol/v2/point/-6.1/106.7/150`
- Fetched: 2026-10-09T19:40:49Z · HTTP 200 · `application/json` · 3,764 bytes
- sha256: `28bb45d30a57fbb2a4d1eea4747f0d9da8c3c47e2115f39c0f8943fb4c997d92`

**`adsb/point_kyushu_31.6_130.6_200.json`**  
adsb.lol point query, Kyushu, 200 nm: 19 aircraft at 04:40 JST, including 2 with no gs/track (calc_track only) and stale positions.

- URL: `https://api.adsb.lol/v2/point/31.6/130.6/200`
- Fetched: 2026-10-09T19:40:51Z · HTTP 200 · `application/json` · 12,350 bytes
- sha256: `de33970de85ab9c4bd138a4b93b8cbbdd7271797b9231820e7c614d611d356e2`


### `openmeteo/`

**`openmeteo/semeru_pressure_level_winds.json`**  
Open-Meteo hourly wind speed (kn) and direction at 850-200 hPa at Semeru, 2026-10-09T00:00 to T23:00 GMT.

- URL: `https://api.open-meteo.com/v1/forecast?latitude=-8.108&longitude=112.922&hourly=wind_speed_850hPa,wind_direction_850hPa,wind_speed_700hPa,wind_direction_700hPa,wind_speed_600hPa,wind_direction_600hPa,wind_speed_500hPa,wind_direction_500hPa,wind_speed_400hPa,wind_direction_400hPa,wind_speed_300hPa,wind_direction_300hPa,wind_speed_250hPa,wind_direction_250hPa,wind_speed_200hPa,wind_direction_200hPa&wind_speed_unit=kn&forecast_days=1`
- Fetched: 2026-10-09T19:41:09Z · HTTP 200 · `application/json; charset=utf-8` · 3,076 bytes
- sha256: `8ddfa9d9ac3c48920db3f76475a271d625df89a953b7ad09a06eed1af598dbf2`


### `himawari/`

**`himawari/nict_latest.json`**  
NICT latest frame pointer: 2026-10-09 19:20:00.

- URL: `https://himawari8.nict.go.jp/img/D531106/latest.json`
- Fetched: 2026-10-09T19:41:23Z · HTTP 200 · `application/json` · 83 bytes
- sha256: `3c73b5788f2eaea204fbfb8981a06811dea9e5374cc1cfee645b99c66faf031c`

**`himawari/nict_D531106_1d_550_20261009_192000_0_0.png`**  
NICT true colour, level 1d (full disk in one 550 px tile), 19:20Z. Night side is black.

- URL: `https://himawari8.nict.go.jp/img/D531106/1d/550/2026/10/09/192000_0_0.png`
- Fetched: 2026-10-09T19:41:41Z · HTTP 200 · `image/png` · 164,188 bytes
- sha256: `746c853b21da55468c414b2231bd7b8791fb0ad771eddd4ad91aae619d104ce4`

**`himawari/nict_D531106_4d_550_20261009_192000_1_2.png`**  
NICT true colour, level 4d tile x=1 y=2 (Lesser Sundas, Timor, NW Australia), 19:20Z. Night: a 444-byte 1-bit all-black PNG.

- URL: `https://himawari8.nict.go.jp/img/D531106/4d/550/2026/10/09/192000_1_2.png`
- Fetched: 2026-10-09T19:41:45Z · HTTP 200 · `image/png` · 444 bytes
- sha256: `e450fca6019cb4884dd22c8d4a84f31f1476500ef719394212260b498ddf97f1`

**`himawari/nict_D531106_4d_550_20261009_050000_1_2_daytime.png`**  
Same 4d tile x=1 y=2 at 05:00Z (midday WITA) for comparison: Flores/Lewotobi/Lewotolok chain at left, Timor, NW Australia.

- URL: `https://himawari8.nict.go.jp/img/D531106/4d/550/2026/10/09/050000_1_2.png`
- Fetched: 2026-10-09T19:41:57Z · HTTP 200 · `image/png` · 519,196 bytes
- sha256: `d55517319bf8ba64e08318f2b9636fc7f28f919c4bebdbd404d066ecb8f45684`

**`himawari/nict_D531106_4d_550_20261009_050000_0_2_daytime.png`**  
4d tile x=0 y=2 at 05:00Z: Indian Ocean with Java/Bali at the top-right corner. Semeru sits near the 0_2 / 1_2 seam, so a Java view needs both tiles stitched.

- URL: `https://himawari8.nict.go.jp/img/D531106/4d/550/2026/10/09/050000_0_2.png`
- Fetched: 2026-10-09T19:42:14Z · HTTP 200 · `image/png` · 517,590 bytes
- sha256: `a37891ecfecd8ace82cffa73d868040d1e8ae2c08e6bd90d197f0754e606be51`

**`himawari/jma_mscweb_sat_img_se3.html`**  
JMA MSC real-time image page for area se3; its slt_time <option> list is the index of the last ~24 h of image slots (137 slots).

- URL: `https://www.data.jma.go.jp/mscweb/data/himawari/sat_img.php?area=se3`
- Fetched: 2026-10-09T19:43:00Z · HTTP 200 · `text/html; charset=UTF-8` · 16,537 bytes
- sha256: `20ba01a3e4c65c761761007f4ba6b3257eacf15e77f04b8299b21eb2696ce0f7`

**`himawari/jma_se3_b13_1920.jpg`**  
JMA Himawari-9 Band 13 (10.4 um IR), Southeast Asia 3, slot 1920 (caption on image: 19:30UTC), 1101x501.

- URL: `https://www.data.jma.go.jp/mscweb/data/himawari/img/se3/se3_b13_1920.jpg`
- Fetched: 2026-10-09T19:43:07Z · HTTP 200 · `image/jpeg` · 202,158 bytes
- sha256: `b1047e495fdf292d51b0cb37eb8b21c6fdfb0c86e60dfacc0334f13d180c3c25`

**`himawari/jma_se3_dst_1920.jpg`**  
JMA Himawari-9 Dust RGB, Southeast Asia 3, slot 1920, 1101x501.

- URL: `https://www.data.jma.go.jp/mscweb/data/himawari/img/se3/se3_dst_1920.jpg`
- Fetched: 2026-10-09T19:43:09Z · HTTP 200 · `image/jpeg` · 229,539 bytes
- sha256: `eea1dcca12639588e3d1f446584c9d9f2ce098227587ec8c17de2a9d8257233a`

**`himawari/jma_jpn_b13_1920.jpg`**  
JMA Himawari-9 Band 13, Japan area, slot 1920, 801x641.

- URL: `https://www.data.jma.go.jp/mscweb/data/himawari/img/jpn/jpn_b13_1920.jpg`
- Fetched: 2026-10-09T19:43:11Z · HTTP 200 · `image/jpeg` · 152,316 bytes
- sha256: `12c7c3d862bd27d0c534f0e0c05f85b4c6f2956f5658312d74eae621699feab8`


### `aws_himawari/`

**`aws_himawari/list_AHI-L1b-FLDK_2026-10-09_1800.xml`**  
S3 ListObjectsV2 XML for the 18:00Z full-disk slot: 160 keys (16 bands x 10 segments), not truncated. DAT files not downloaded; sizes below.

- URL: `https://noaa-himawari9.s3.amazonaws.com/?list-type=2&prefix=AHI-L1b-FLDK/2026/10/09/1800/`
- Fetched: 2026-10-09T19:43:37Z · HTTP 200 · `application/xml` · 57,694 bytes
- sha256: `465026c98e67fd478ea927e6898d1f650c5115dd9980b7936b4c5ea3f6d68af8`

## Himawari-9 L1b DAT sizes (not downloaded)

From `aws_himawari/list_AHI-L1b-FLDK_2026-10-09_1800.xml`. Each 10-minute full-disk slot is
160 bzip2-compressed HSD segment files, 500.4 MB in total. `R05`/`R10`/`R20` are 0.5/1/2 km
resolution. Objects landed between 18:10:35Z and 18:13:56Z, 10-14 minutes after the 18:00Z scan start.

| Band | Res | Segments | Total MB | Smallest segment (bytes) | Largest segment (bytes) |
|---|---|---|---|---|---|
| B01 | R10 | 10 | 36.06 | 1,821,436 | 4,649,324 |
| B02 | R10 | 10 | 35.45 | 1,751,138 | 4,560,966 |
| B03 | R05 | 10 | 176.30 | 9,564,267 | 21,920,972 |
| B04 | R10 | 10 | 49.56 | 2,699,341 | 6,117,534 |
| B05 | R20 | 10 | 7.93 | 355,964 | 1,024,614 |
| B06 | R20 | 10 | 8.99 | 446,157 | 1,165,178 |
| B07 | R20 | 10 | 21.00 | 997,027 | 2,730,479 |
| B08 | R20 | 10 | 8.89 | 424,153 | 1,305,628 |
| B09 | R20 | 10 | 11.33 | 568,102 | 1,653,775 |
| B10 | R20 | 10 | 16.32 | 877,358 | 2,323,425 |
| B11 | R20 | 10 | 23.08 | 1,117,416 | 2,976,060 |
| B12 | R20 | 10 | 19.62 | 874,199 | 2,674,135 |
| B13 | R20 | 10 | 23.20 | 1,163,310 | 3,014,537 |
| B14 | R20 | 10 | 22.96 | 1,147,973 | 3,007,471 |
| B15 | R20 | 10 | 22.51 | 1,186,015 | 2,963,442 |
| B16 | R20 | 10 | 17.23 | 966,717 | 2,365,791 |
| all | | 160 | 500.4 | | |

Band 13 (10.4 um, the ash/IR band) per segment; S01 is the northern edge of the disk, S10 the southern:

| Key | Bytes | LastModified |
|---|---|---|
| `AHI-L1b-FLDK/2026/10/09/1800/HS_H09_20261009_1800_B13_FLDK_R20_S0110.DAT.bz2` | 1,273,700 | 2026-10-09T18:11:59.000Z |
| `AHI-L1b-FLDK/2026/10/09/1800/HS_H09_20261009_1800_B13_FLDK_R20_S0210.DAT.bz2` | 2,141,125 | 2026-10-09T18:12:02.000Z |
| `AHI-L1b-FLDK/2026/10/09/1800/HS_H09_20261009_1800_B13_FLDK_R20_S0310.DAT.bz2` | 2,608,004 | 2026-10-09T18:11:42.000Z |
| `AHI-L1b-FLDK/2026/10/09/1800/HS_H09_20261009_1800_B13_FLDK_R20_S0410.DAT.bz2` | 2,890,869 | 2026-10-09T18:11:46.000Z |
| `AHI-L1b-FLDK/2026/10/09/1800/HS_H09_20261009_1800_B13_FLDK_R20_S0510.DAT.bz2` | 3,014,537 | 2026-10-09T18:12:03.000Z |
| `AHI-L1b-FLDK/2026/10/09/1800/HS_H09_20261009_1800_B13_FLDK_R20_S0610.DAT.bz2` | 2,872,271 | 2026-10-09T18:12:02.000Z |
| `AHI-L1b-FLDK/2026/10/09/1800/HS_H09_20261009_1800_B13_FLDK_R20_S0710.DAT.bz2` | 2,698,737 | 2026-10-09T18:11:57.000Z |
| `AHI-L1b-FLDK/2026/10/09/1800/HS_H09_20261009_1800_B13_FLDK_R20_S0810.DAT.bz2` | 2,453,059 | 2026-10-09T18:11:59.000Z |
| `AHI-L1b-FLDK/2026/10/09/1800/HS_H09_20261009_1800_B13_FLDK_R20_S0910.DAT.bz2` | 2,087,416 | 2026-10-09T18:12:50.000Z |
| `AHI-L1b-FLDK/2026/10/09/1800/HS_H09_20261009_1800_B13_FLDK_R20_S1010.DAT.bz2` | 1,163,310 | 2026-10-09T18:13:39.000Z |

## Requests made but not saved here

These were made in the same 19:36-19:44Z session to understand the feeds (exact
times were not recorded); their results are described in FORMATS.md.

| Request | Result |
|---|---|
| `GET https://magma.esdm.go.id/v1/vona/22880` (no `signature` query) | HTTP 403, 10,320 bytes HTML. Detail pages need the signed URL from the list. |
| `GET https://magma.esdm.go.id/v1/vona?page=2` | HTTP 200, 44,849 bytes. Pagination works with `?page=N`. |
| `GET https://www.bom.gov.au/aviation/volcanic-ash/js/va.js?v2` | HTTP 200, 1,574 bytes. Shows the page loads advisories with `POST /aviation/php/process.php {page: "volcanic-ash-darwin", javascript: 1}`. |
| `GET https://www.data.jma.go.jp/mscweb/data/himawari/sat_img.js` | HTTP 200, 557 bytes. Shows the image URL is built as `img/{area}/{area}_{element}_{time}.jpg`. |
