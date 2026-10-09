# 14. Contradiction census: 30 days of VONA, VAA and SIGMET (points C and D)

Prepared 2026-10-10 (local; archives downloaded 2026-10-09 19:33Z to 20:30Z UTC). Window: **2026-09-09 19:00Z to 2026-10-09 19:00Z**, exactly 30 days.

Raw downloads (1,567 fetches, each with URL, UTC time, HTTP status and sha256): `research/data/census/manifest.tsv`. Parser: `research/data/census/census.py` (standard library only; run as `python3 -I census.py <census dir>`). Outputs: `research/data/census/out/` (`vonas.csv`, `vaas.csv`, `sigmets.csv`, `vona_vs_official.csv`, `summary.json`, `per_volcano_table.md`, `run_stdout.txt`).

**Provenance note.** An earlier, unfinished run of this task had already downloaded the raw archive and written a first `census.py`. I re-read all of it and checked it against the raw files. Then I corrected it and re-ran it. The changes:
- VONA heights now come from the metre value. The printed feet use MAGMA's ×3.2 factor, and that undercounted "VONA above VAA top" from 23 to 4 for Semeru.
- There is now a separate count of Darwin's "not identifiable" wording.
- A polygon test now checks whether the official area covers the VONA's direction of drift.
- I added a Tokyo-area lag from the observatory report to the VAA.
- A SIGMET volcano-name regex that missed 5 SIGMETs is fixed.

I re-fetched the key items on 2026-10-10 into `raw/recheck/`. The two Darwin texts I re-fetched are byte-identical to the archived copies.

---

## 1. Bottom line

1. **The official sources differ often. Most of the differences do not change what a dispatcher should do.** Over 30 days at Semeru:
   - 93 of 185 VONAs said "Ash-cloud is not observed". Every one of the 93 came while a Darwin VAA was in force.
   - 69 of the 92 VONAs that reported ash gave a top inside the VAA's FL150 envelope.
   - Both kinds are "envelope" or "non-observation" differences. Following the more cautious product is correct for them, as Akash says.
2. **For Indonesia, the SIGMET is not an independent source.** WAAF and WIIF SIGMETs repeat the Darwin VAA:
   - The top matches in 489 of 492 Indonesian SIGMET/VAA pairs (528 of 532 across all FIRs).
   - No pair differs in direction by more than 45°.
   - In practice there are two voices: the observatory (VONA) and the VAAC (VAA, copied by the SIGMET).
3. **The material difference is direction, not height.** In 44 of 92 Semeru ash VONAs, the observatory's drift direction differs from the VAA's MOV by more than 45° (41 by 90° or more).
   - In **28 of 92** (Ibu 3 of 21, Lewotolok 0 of 6), a point 10 km from the vent along the observatory's direction lies **outside every ash polygon of the official VAA**.
   - In those cases no single official product is "the cautious one". The cautious area is the union of the two.
4. **Height conflicts are rare.** By more than 1,000 ft: 2 of 92 Semeru ash VONAs.
   - On 26 Sep Darwin raised the top to FL160 within 25 min.
   - On 1 Oct the observatory's 4,976 m (about 16,300 ft) was **never** adopted. VAAs 2026/1125 to 1129 kept FL150 for the next 25 h.
5. **Lag is real and structural.** Darwin re-issues Semeru on a fixed cycle: the median gap between VAAs is 360 min, and the largest is 455 min.
   - After an ash VONA, the first VAA built on information at least as new as that VONA came a **median 228 min later (90th percentile 463 min)**. Pooled over all volcanoes: median 205 min, p90 449, n=116.
   - In Japan and the Philippines the report-to-VAA lag is short: median 16 min at Sakurajima, 22.5 min at Mayon. But the first VAA says ash is not identifiable on satellite in 61 of 65 Sakurajima reports and 14 of 14 Mayon reports.
6. **Silence is rare but real.**
   - Sinabung, 1 Oct 02:49Z: an ash VONA to 2,960 m was followed by no VAA and no SIGMET for at least 24 h.
   - Karangetang, 30 Sep 10:07Z: an ash VONA to 2,784 m was followed by its first VAA 13 h later, and that VAA was triggered by a later satellite sighting.
   - Manam: Darwin issued 24 VAAs in the window, 18 of them with an ash area. 16 of those 18 had no AYPM SIGMET within ±1 h in the AWC record, and all 16 date from 3 to 9 Oct.
7. **SIGMETs in Japan and the Philippines often cannot be drawn.**
   - 60 of 83 RJJJ Sakurajima SIGMETs and all 29 RPHI SIGMETs (Mayon, Kanlaon, Taal) carry no polygon.
   - 10 Mayon SIGMETs carry no top either.
   - Indonesia: 0 of 494 WAAF/WIIF SIGMETs lack a polygon.
8. **Historical SIGMETs can be measured only for 30 days.**
   - AWC returns HTTP 400 "Data is available for up to 30 days for date" for older dates.
   - IEM is US-only, and OGIMET has no SIGMET archive.
   - TEPHRA must record its own SIGMET history.

---

## 2. Sources and coverage

| Source | What was collected | Coverage check |
|---|---|---|
| MAGMA VONA list, `https://magma.esdm.go.id/v1/vona?page=1..22` | 268 VONAs in the window, with time, volcano, colour, activity line, height (m and printed ft), direction, and whether ash was observed | Page 22 reaches 2026-09-01, before the window start. A re-fetch of page 1 on 2026-10-10 shows the newest VONA still at 2026-10-09 18:00Z, so nothing is missing at the end. [CONFIRMED: https://magma.esdm.go.id/v1/vona?page=1, accessed 2026-10-10] |
| Darwin VAAC text archive, `ftp://ftp.bom.gov.au/anon/gen/vaac/2026/` (IDY41xxx.YYYYMMDDhhmm.txt) | 588 listed text files from 8 Sep to 9 Oct, all downloaded; 548 Darwin VAAs in the window after removing pointer messages | Advisory numbers are contiguous except Semeru 2026/1090, Ibu 2026/1080 and Lewotolok 2026/269. All three gaps fall on 23 Sep, when Tokyo was backing up Darwin. [CONFIRMED: ftp://ftp.bom.gov.au/anon/gen/vaac/2026/, accessed 2026-10-10] |
| JMA "Darwin VAAC Backup" list and texts | 3 texts (the D/T notice, Ibu 1081, Dukono 788) | [CONFIRMED: https://ds.data.jma.go.jp/svd/vaac/data/vaac_darwin_list.html, accessed 2026-10-10] |
| Tokyo VAAC list, `https://ds.data.jma.go.jp/svd/vaac/data/vaac_list.html`, and `TextData/2026/*_Text.html` | 158 list entries from 2026-09-01 to 2026-10-08; 151 Tokyo VAAs in the window | [CONFIRMED: https://ds.data.jma.go.jp/svd/vaac/data/vaac_list.html, accessed 2026-10-10] |
| AWC international SIGMET API, `https://aviationweather.gov/api/data/isigmet?format=json&hazard=va&date=<hour>` | 744 hourly snapshots from 2026-09-08 20:00Z to 2026-10-09 19:00Z. 14 hours returned HTTP 504 and one timed out. 20 hours before 08 Sep 20Z returned HTTP 400. 621 VA SIGMETs in JAPAC FIRs. | Both `date=20261001_1200` and `date=2026-10-01T12:00:00Z` return HTTP 200 today. `date=2026-09-08T00:00:00Z` and `2026-08-20T12:00:00Z` return HTTP 400 `{"status":"error","error":"Data is available for up to 30 days for date"}`, while `2026-09-09T00:00:00Z` works. [CONFIRMED: https://aviationweather.gov/api/data/isigmet?format=json&hazard=va&date=2026-09-08T00:00:00Z, accessed 2026-10-10] |
| BoM web pages (`/products/Volc_ash_recent.shtml`, `/aviation/volcanic-ash/darwin-va-advisory.shtml`, `/products/IDD41270.shtml`) | Recent advisories only, no archive | The Wayback CDX query for Volc_ash_recent from 2026-08-01 returned `[]` (no captures). |

**SIGMET caveats.**
- The AWC record never contained a `CNL SIGMET` message (0 in 621). Cancellations show only as a shorter `validTimeTo` on a later snapshot, which the parser keeps (the minimum across snapshots). For example, RJJJ Q02 on 7 Oct appears once as valid to 1604Z and once as valid to 1152Z. A SIGMET issued and cancelled within one hour between snapshots would be missed.
- Every SIGMET count is "as relayed by AWC". A missing SIGMET may be an AWC relay gap rather than a non-issue [UNVERIFIED which].

**Volcanoes in scope.** Volcanoes with activity in the window:
- Semeru, Ibu, Dukono, Ili Lewotolok, Anak Krakatau, Marapi and Karangetang (Indonesia, Darwin VAAC);
- Sakurajima (Japan, Tokyo VAAC);
- Mayon, Kanlaon and Taal (Philippines, Tokyo VAAC);
- Manam and Ulawun (PNG, Darwin VAAC).

Lewotobi Laki-laki had **no VONA, VAA or SIGMET** in the window. Its name appears on the MAGMA pages only in the filter menu.

Sheveluch, Chikurachki and Alaid (Russian FIRs, whose SIGMETs I did not collect) and Ambrym (Wellington VAAC, not collected) appear in the raw tables. They are excluded from the conclusions.

---

## 3. Per-volcano counts (window 2026-09-09 19Z to 2026-10-09 19Z)

| Volcano | VONAs | ash VONAs | 'not observed' VONAs | VAAs | VAAs with ash area | EST (estimated, not seen) VAAs | exact "VA NOT IDENTIFIABLE FM SATELLITE DATA" | any "NOT IDENTIFIABLE" | VA SIGMETs |
|---|---|---|---|---|---|---|---|---|---|
| Semeru | 185 | 92 | 93 | 123 | 123 | 91 | 0 | 83 | 121 |
| Ibu | 21 | 21 | 0 | 123 | 123 | 81 | 0 | 71 | 122 |
| Dukono | 1 | 0 | 1 | 126 | 125 | 58 | 1 | 46 | 124 |
| Ili Lewotolok | 6 | 6 | 0 | 108 | 100 | 78 | 8 | 67 | 101 |
| Sakurajima | 0 (JMA, no VONA) | – | – | 92 | 21 | 0 | 71 | 71 | 83 |
| Mayon | 0 (PHIVOLCS, no VONA) | – | – | 19 | 0 | 0 | 19 | 19 | 21 |
| Anak Krakatau | 2 | 0 | 2 | 20 | 17 | 10 | 3 | 12 | 17 |
| Manam | 0 | – | – | 24 | 18 | 9 | 6 | 12 | 4 |
| Karangetang | 1 | 1 | 0 | 9 | 6 | 6 | 3 | 5 | 6 |
| Marapi | 6 | 0 | 6 | 7 | 3 | 7 | 4 | 4 | 3 |
| Ulawun | 0 | – | – | 5 | 4 | 4 | 1 | 4 | 4 |
| Kanlaon | 0 | – | – | 4 | 0 | 0 | 4 | 4 | 4 |
| Taal | 0 | – | – | 4 | 2 | 0 | 2 | 2 | 4 |
| Sinabung | 2 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |

Every Semeru, Ibu, Dukono and Lewotolok VONA in the window was ORANGE. The other 44 VONAs are mostly single GREEN "Ash-cloud is not observed" (30) or YELLOW "Increasing in volcanic activity" (19) notices at quiet volcanoes. [CONFIRMED: MAGMA list pages 1-22, accessed 2026-10-10; counts COMPUTED by census.py]

**"Not identifiable" counts, by centre.**
- Tokyo: the exact phrase "VA NOT IDENTIFIABLE FM SATELLITE DATA" appears in 105 of 151 Tokyo VAAs (70%).
- Darwin: the exact phrase appears in only 27 of 548. Darwin writes free-text remarks instead, with more than 25 variants. Examples: "VA NOT IDENTIFIABLE ON SATELLITE IMAGERY DUE TO MET CLOUD" (74), "...ON CURRENT SATELLITE IMAGERY..." (26).
- Darwin VAAs with any "NOT IDENTIFIABLE": 305 of 548 (56%). Of the 303 files checked for a stated reason, 192 give met cloud (or darkness) as the reason.
- Darwin VAAs drawn as "EST VA CLD" (estimated, not observed) rather than "OBS VA CLD": 345 of 548 (63%).

**Total across all VAAs: 132 contain the exact phrase, and 410 of 699 (59%) contain "NOT IDENTIFIABLE" in some form.**

---

## 4. Measured differences, with exact definitions

All counts are COMPUTED by `census.py` from the CONFIRMED raw files listed in §2.

**Comparison VAA.** The VAA in force at the VONA time. If none is in force, the first VAA issued within 3 h after it. A VAA is in force from its DTG until the earliest of:
- the next VAA for the same volcano from the same centre;
- its "NXT ADVISORY: NO LATER THAN" time;
- DTG + 6 h.

A "NO FURTHER ADVISORIES" VAA ends coverage at its own DTG. The comparison SIGMET uses the same rule.

### 4.1 Lag from an ash VONA to the VAA

Three definitions, because Semeru and Ibu have a continuous VAA chain, so a "first VAA for the eruption" almost never exists:

- **Onset lag.** For an ash VONA with **no** VAA in force for that volcano, the time to the next VAA. Four cases in 30 days:

| Volcano, VONA | VONA content | First VAA after it | Lag |
|---|---|---|---|
| Ili Lewotolok, 07 Oct 21:01Z | ash to about 6,300 ft, W to NW | 21:30Z | **29 min** |
| Semeru, 23 Sep 16:12Z | 4,376 m, E | Darwin 2026/1091 at 17:25Z | **73 min** (possibly an artefact: 2026/1090 is missing from the FTP archive on the Darwin-outage day) |
| Karangetang, 30 Sep 10:07Z (YELLOW, "white to brown", 2,784 m, N) | | Darwin 2026/2 at 23:09Z, "VA TO FL090 OBS AT 30/2250Z", i.e. triggered by a later satellite sighting, not by the VONA; WAAF SIGMET 15 at 23:10Z | **782 min** |
| Sinabung, 01 Oct 02:49Z (YELLOW, "white", 2,960 m, SE to SW) | | none within 24 h; no SIGMET either | **never** |

  Sources: [CONFIRMED: https://magma.esdm.go.id/v1/vona/22811?signature=7bdeca823123aa5666de9e491d05be074afbcb89428c4526f868aa96993fc140, accessed 2026-10-10] and [CONFIRMED: https://magma.esdm.go.id/v1/vona/22819?signature=eccf77ed2c4919864b1ba70130889bd04ff62d235d84c2f9a54df62b20be1229, accessed 2026-10-10].

- **Update lag.** For any ash VONA, the time to the next VAA for the volcano:
  - Semeru: median 128 min, p90 337 (n=92).
  - Ibu: median 124, p90 272 (n=21).
  - Lewotolok: median 50.5, p90 311 (n=6).
  - The next WAAF SIGMET follows almost exactly: Semeru median 133, p90 341.

- **Reflect lag** (the one that matters). The time to the first VAA whose ERUPTION DETAILS cite a report or observation time at or after the VONA's time (5 min tolerance). In other words, the first VAA built on information at least as new as the VONA:
  - Semeru: median **228 min**, p90 **463 min**. n=89; 3 had no such VAA within 24 h.
  - Ibu: median 139, p90 310 (n=20).
  - Lewotolok: median 343.5, p90 396 (n=6).
  - Pooled: median **205 min**, p90 **449 min** (n=116).
  - 23 of 89 Semeru reflect lags exceed 360 min, which means the next scheduled VAA did not yet carry the VONA.

- **Age of what the dispatcher is looking at.** When a Semeru ash VONA arrived, the VAA in force had been issued a median 233 min earlier (max 358). The newest report it cited was a median 371 min old (p90 945).

**Japan and the Philippines (report to VAA).** Tokyo VAAs that cite "ERUPTED AT <t>" (JMA) or "ERUPTION AT <t> ... REPORTED" (PHIVOLCS), grouped by (volcano, t):

| Volcano | n | First VAA after the report | First SIGMET (start of validity) after the report |
|---|---|---|---|
| Sakurajima | 65 | median 16 min, p90 26 | median 21 min, p90 38; none within 3 h once |
| Mayon | 14 | median 22.5, p90 33 | median 20, p90 28; none once |
| Kanlaon | 4 | median 23 | median 20 |
| Taal | 1 | 23 | 10 |

Tokyo is fast, but its first VAA carried a not-identifiable statement for 61 of 65 Sakurajima, 14 of 14 Mayon, 4 of 4 Kanlaon and 1 of 1 Taal reports. That VAA is a relay of the ground report with no drawn area.

### 4.2 "Ash not observed" while a VAA or SIGMET was valid

**Definition.** A VONA whose height and other-cloud fields say "Ash-cloud is not observed" (and give no height), issued while a VAA (or SIGMET) for that volcano was in force.

| Volcano | 'not observed' VONAs | with a VAA in force | with a SIGMET in force | with either |
|---|---|---|---|---|
| Semeru | 93 (all "Eruption at ..." with a seismic record) | 93 (100%) | 92 | 93 |
| Dukono | 1 | 1 | 1 | 1 |
| Anak Krakatau | 2 | 1 | 1 | 1 |
| Marapi | 6 | 0 | 0 | 0 |
| All 147 'not observed' VONAs | 147 | 95 | 94 | 95 |

The remaining 52 are routine GREEN/YELLOW notices at volcanoes with no VAA.

- Darwin later **cited the time of 24 of the 93 Semeru 'not observed' VONAs** in a VAA's ERUPTION DETAILS. For example, VAA 2026/1148 (7 Oct 1630Z): "VA TO FL150 REP FM GND 07/1122Z". The 1122Z VONA said "Ash-cloud is not observed". [CONFIRMED: ftp://ftp.bom.gov.au/anon/gen/vaac/2026/IDY41295.202610071634.txt, accessed 2026-10-10; https://magma.esdm.go.id/v1/vona/22867?signature=977a4a9f44f6cba391bfd92976b21d39615917aabe1334b5ea3308511b3e4bd5]
  - Darwin reads an eruption report as "ash still being produced to the usual height", not as "no ash". What Darwin actually received from CVGHM at 1122Z is [UNVERIFIED].
- Darkness is not the main reason. With night defined as 18:00 to 05:59 WIB, 58 of 93 'not observed' and 62 of 92 ash-observed Semeru VONAs fall at night, nearly the same share.

### 4.3 VONA height vs VAA top (true conflict vs envelope)

**Definition.** VONA top in ft = metres × 3.28084, compared with the comparison VAA's highest FL × 100. "Envelope" means the VONA is at or below the VAA top. FL is pressure altitude and the VONA is above mean sea level, so differences of a few hundred feet are within that ambiguity.

| Volcano | compared | inside (envelope) | above by >0 ft | above by >500 ft | above by >1,000 ft |
|---|---|---|---|---|---|
| Semeru | 92 | 69 (75%) | 23 | 3 | 2 |
| Ibu | 21 | 21 | 0 | 0 | 0 |
| Ili Lewotolok | 6 | 3 | 3 (all ≤ 309 ft) | 0 | 0 |
| **Pooled** | **119** | **93 (78%)** | **26** | **3** | **2** |

- Using MAGMA's printed feet (×3.2) instead, Semeru "above" falls from 23 to 4. TEPHRA must parse metres.
- 20 of the 23 Semeru "above" cases are 4,576 m (15,013 ft) or 4,676 m (15,341 ft) against FL150. That is within the FL/AMSL ambiguity: not a conflict.
- The two cases above 1,000 ft:
  - **26 Sep 22:55Z.** The VONA gave 4,976 m (16,325 ft) moving NE. Darwin VAA 2026/1105 at 23:20Z raised the area to SFC/FL160 with the remark "INTERMITTENT ERUPTIONS ARE ONGOING TO FL160". Adopted in 25 min. [CONFIRMED: https://magma.esdm.go.id/v1/vona/22729?signature=092f3a4418bf50a8e4dbf5968fd5e7c57a6abf17d95048e1f8b5da15f713ce48 and ftp://ftp.bom.gov.au/anon/gen/vaac/2026/IDY41295.202609262322.txt, accessed 2026-10-10]
  - **1 Oct 22:24Z.** VONA 2026SMR1871: "15923 FT (4976 M) above sea level or 4160 FT (1300 M) above summit ... Ash cloud moving to north". The next VAA, 2026/1125 at 23:20Z, used Himawari at 22:50Z and kept "SFC/FL150 ... MOV N 05KT". So did VAAs 1126 to 1129, through 2 Oct 23:20Z. **Not adopted.** [CONFIRMED: https://magma.esdm.go.id/v1/vona/22827?signature=fe2ef8eae707cbee5f5a5dd65c1fbcd81ae4a77aed65e522e4edf9ffab73c8b1 and ftp://ftp.bom.gov.au/anon/gen/vaac/2026/IDY41295.202610012318.txt, accessed 2026-10-10]
- **SIGMET vs VAA, Indonesia.** For each SIGMET, the nearest VAA within ±60 min that depicts ash: the top is identical in 489 of 492 Indonesian pairs, and no pair differs in direction by more than 45°. The 3 that differ are Dukono, each by more than 1,000 ft. Across all FIRs: 528 of 532, the fourth being Sakurajima.
- **Philippines.** RPHI SIGMETs for Mayon on 21 and 23 Sep say "SFC/FL180". The matching Tokyo VAA 2026/794 says "ERUPTION AT 20260921/1147Z VA CLD UNKNOWN REPORTED ... VA NOT IDENTIFIABLE FM SATELLITE DATA WIND FL180 330/4KT". The SIGMET's FL180 equals the VAA's **wind level**, which suggests the MWO turned a wind level into a cloud top [UNVERIFIED interpretation]. [CONFIRMED: https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20260921_27303000_0794_Text.html, accessed 2026-10-10]

### 4.4 Direction differences

**Definition.** The VONA's "Ash cloud moving to X" becomes a bearing; "moving from X to Y" becomes the middle of that sector. The VAA direction is the first "MOV" in its OBS/EST VA CLD field. A difference is counted when it exceeds 45°. "Overlapping time" means the comparison VAA (the one in force, or the next within 3 h).

| Volcano | pairs | >45° | ≥90° | ≥135° | still >45° vs the first VAA that reflects the VONA |
|---|---|---|---|---|---|
| Semeru | 92 | **44 (48%)** | 41 | 14 | 39 of 89 |
| Ibu | 21 | 5 | 5 | 2 | 2 of 20 |
| Ili Lewotolok | 6 | 2 | 0 | 0 | 0 of 5 |
| **Pooled** | **119** | **51 (43%)** | 46 | 16 | 41 of 114 |

- Typical Semeru pairs (VONA vs VAA MOV): "to north" vs SE (14), "to northeast" vs SE (13), "to northeast" vs E (9), "to north" vs NE (8), "to southwest" vs SE (7).
- The observatory sees drift about 1 km above the summit. The VAA polygon is one SFC/FL150 layer that moves with model and satellite winds. Wind shear can make both correct.
- **Polygon cover.** This test turns the direction difference into an action question. Take points 5, 10 and 20 km from the vent (the VAA's PSN) along the VONA direction, and test whether each lies inside any ash polygon of the comparison VAA (flat-earth offset, ray-casting test):

| Volcano | tested | 5 km outside | **10 km outside** | 20 km outside |
|---|---|---|---|---|
| Semeru | 92 | 0 | **28 (30%)** | 58 |
| Ibu | 21 | 1 | 3 | 8 |
| Ili Lewotolok | 6 | 0 | 0 | 1 |

- In Semeru's 10-km-outside cases, 25 of 28 also have a direction difference above 45°. Where the direction differs by 45° or less, only 3 of 48 are outside at 10 km.
- So the polygon covers the vent area every time, but in about a third of reports it does not extend down the direction the observatory reports. This matches file 13's 20 hand-checked cases: inside at 5 and 8 km, outside at 10 to 15 km.

### 4.5 Other cross-product differences

- **SIGMET says "OBS", the VAA says "EST".** 317 of 492 Indonesian SIGMET/VAA pairs (320 of 532 across all FIRs) (Semeru 90 of 121, Ibu 80 of 122, Lewotolok 76 of 101, Dukono 56 of 123). The SIGMET says "VA CLD OBS AT ..." while the VAA it copies said "EST VA CLD" and usually "NOT IDENTIFIABLE ON SATELLITE IMAGERY".
  - Example: WAAF SIGMET 12, 7 Oct, "VA CLD OBS AT 1010Z". Darwin 2026/1147: "EST VA DTG: 07/1010Z ... RMK: VA NOT IDENTIFIABLE ON SATELLITE IMAGERY DUE TO MET CLOUD ... BASED ON GROUND REPORTS AND MODEL GUIDANCE". [CONFIRMED: ftp://ftp.bom.gov.au/anon/gen/vaac/2026/IDY41295.202610071025.txt and https://aviationweather.gov/api/data/isigmet?format=json&hazard=va&date=2026-10-07T11:00:00Z]
- **VAA closed while the SIGMET is still open.** **Definition:** a VAA that says "NO FURTHER ADVISORIES" while a VA SIGMET for the same volcano is valid at the VAA DTG, or starts within 15 min after it, and stays valid at least 60 min after the VAA DTG. Counts: Sakurajima 67 of 71, Mayon 17 of 19, Kanlaon 4 of 4, Taal 2 of 2, Manam 2 of 6, Marapi 1 of 3, Ulawun 1 of 1, Semeru/Ibu/Lewotolok 0.
  - Example: Tokyo VAA 2026/249 at 1252Z, "VA NOT IDENTIFIABLE FM SATELLITE DATA ... NO FURTHER ADVISORIES". Five minutes later, RJJJ SIGMET B01 1257Z to 1857Z: "VA CLD OBS AT 1236Z FL080 MOV E=". (See file 13.)
- **SIGMETs with no polygon.** In the window: RJJJ Sakurajima 60 of 83, RPHI Mayon 21 of 21 (10 also have no top), RPHI Kanlaon 4 of 4, RPHI Taal 2 of 4, AYPM 3 of 8, WAAF/WIIF 0 of 494.
  - Example text: "VA CLD OBS AT 0810Z FL120 STNR=" or "VA CLD OBS AT 1147Z=". No area can be drawn from these.
- **VAA with an ash area but no SIGMET within ±1 h.** Manam 16 of 18 (Darwin 2026/32 to 2026/50, 3 to 9 Oct; most are "OBS" by Himawari, FL060 to FL070). AWC holds AYPM SIGMETs for Manam on 12 to 13 Sep (V1 to V5) and none after that. Indonesian volcanoes: 0. Japan/Philippines: 0.
- **SIGMET with no VAA.** 0 in JAPAC once Ambrym is excluded (Wellington VAAC, not collected).

---

## 5. Which differences would change a dispatcher's action

| Difference | 30-day count | Changes action? | Why |
|---|---|---|---|
| VONA "not observed" while a VAA or SIGMET is valid | Semeru 93 of 93; all volcanoes 95 | **No** | The VAA/SIGMET stays binding. "Not observed" is a non-observation (cloud cover; Darwin's own remarks cite met cloud). TEPHRA rule: it never shrinks the hazard. |
| VONA top inside the VAA top (envelope), or ≤ 500 ft above it | 93 inside + 23 within 500 ft, of 119 | **No** | The cautious product already covers it. This is Akash's 13,363-ft point, confirmed at scale. |
| SIGMET "OBS" vs VAA "EST / not identifiable" | 317 of 492 Indonesian pairs | **No** for routing (same polygon) | It changes how confident the dispatcher should be, not where to fly. Useful context for the advisory text. |
| VAA "NO FURTHER ADVISORIES" while the SIGMET is valid | 94 (mostly Sakurajima and Mayon) | **No** | Follow the SIGMET (the cautious one). Exactly Akash's "act on the cautious one". |
| Lag (VAA reflects the VONA a median 3.4 to 3.8 h later) | pooled median 205 min, p90 449 | **Sometimes.** Only when the new VONA falls outside the existing area. | Lag alone is harmless when the VONA sits inside the envelope (78%). It matters in combination with the next two rows. |
| VONA direction outside the VAA polygon at 10 km | Semeru 28 of 92, Ibu 3 of 21, Lewotolok 0 of 6 (**31 of 119**) | **Yes, for low-level traffic near the vent** (climb, descent, approaches below FL150 within about 10 to 30 km). Not for cruise above the VAA top. | No single official product is "the cautious one" here; the cautious area is the union. |
| VONA top above the VAA top by >1,000 ft and not adopted | 1 (Semeru, 1 Oct, ~16,300 ft vs FL150 for 25 h) | **Yes, for flights planned at FL150 to FL170 near Semeru** | A change-level decision differs. |
| Ash VONA with no VAA or SIGMET | Sinabung (never), Karangetang (13 h) | **Yes**, if a flight passes nearby below about FL100 | Both reports were YELLOW and partly "white" cloud, so a VAAC judging them as non-ash is plausible [UNVERIFIED]. |
| VAA ash area with no SIGMET (Manam, 16) | 16 | **Depends on the operator**: yes if its planning tool draws only SIGMETs | ICAO's expectation that an MWO issues a VA SIGMET from the VAA was not checked here [UNVERIFIED]. |
| SIGMET with no polygon (RJJJ 60, RPHI 27) | 87 | **Yes, in the sense of ambiguity**: the dispatcher must invent an area, from the vent, the level and the VAA wind | This is where a computed cone (vent + wind + level) adds value even with no disagreement at all. |

---

## 6. Honest deck claims (measured; pick one)

- **Primary:** "In the 30 days to 9 October 2026, 28 of Semeru's 92 observatory ash reports had ash heading where the official ash area did not reach 10 km from the vent."
- **Lag variant:** "In 30 days, the official ash advisory took a median 3.8 hours (90th percentile 7.7 hours) to catch up with each new Semeru ash report from the observatory."
- **Japan/Philippines variant:** "In 30 days, 87 of the 112 ash SIGMETs for Sakurajima, Mayon, Kanlaon and Taal carried no area a dispatcher could draw."

Do **not** claim "the VAAC was silent" as a pattern. The case count is 1 to 2 in 30 days, at YELLOW volcanoes.

---

## Verdict on Akash's point(s)

- **C (sources disagreed on 25 Sep and 7 Oct): PARTLY.**
  - The texts are as he quotes (confirmed again in file 13 and here).
  - The 7 Oct case is a non-observation, not a conflict. The VONA "not observed" came during VAA 2026/1147, which was itself EST and "NOT IDENTIFIABLE ... DUE TO MET CLOUD". Darwin then cited that VONA's time as a ground report to FL150.
  - The 25 Sep height (13,363 ft printed; really 13,701 ft) sits inside FL150, so it is an envelope.
  - The **direction** part of 25 Sep (VONA N vs SIGMET SE) is the kind of difference that survives scrutiny. It happens in 44 of 92 Semeru reports.
- **D (dispatchers may just follow the most cautious product; many disagreements are artefacts): MOSTLY CONFIRMED, with one important exception.**
  - Artefacts: 93 of 93 'not observed' cases, 93 of 119 envelope cases, and the SIGMET/VAA wording differences do not change action. Neither do the 94 "VAA closed, SIGMET open" cases.
  - Exception: in **31 of 119** ash reports the observatory's drift direction is outside the official polygon at 10 km. In 1 case the reported top stayed above the official top for 25 h. In those cases "follow the cautious one" has no answer, because neither product contains the other.
  - Akash's proposed wording is accurate and safe. A slightly stronger, still-measured version: "The official sources often differ. Usually the cautious one is obvious, but about a quarter of the time no single product covers both, and the dispatcher has to build the union quickly."
- **"Dispatchers are struggling": UNRESOLVED** by this census. It measures products, not people (see file 15).
- **Lag as artefact: CONFIRMED that it exists and is structural** (Darwin's 6-hour Semeru cycle). It is harmless when the VONA sits inside the envelope.
- **"A silent VAAC may just not have issued yet": CONFIRMED** for the cases found:
  - Karangetang: the VAA came 13 h later, triggered by a later satellite sighting.
  - Semeru 23 Sep: the 73-min onset lag falls on the Darwin outage day, with advisory 1090 missing from the archive.
  - Sinabung: no VAA came at all.

## Open questions

1. Did CVGHM send Darwin anything with a height at 7 Oct 1122Z, when the public VONA said "not observed"? (Darwin cites that time as "VA TO FL150 REP FM GND".)
2. Was the missing Manam SIGMET cover from 3 to 9 Oct a PNG non-issue or an AWC relay gap? Check against a second SIGMET relay (e.g. a WMO GTS mirror) if one can be found.
3. How do Lido and Jeppesen draw a polygon-less SIGMET ("VA CLD OBS AT 1147Z=")? A radius around the vent, nothing, or the VAA? (See file 15.)
4. Does Darwin deliberately draw Semeru's polygon from the FL150 wind rather than the near-summit drift? If so, should TEPHRA's widening come from the near-vent sector of the VONA direction, out to about 20 km?
5. The census covers one 30-day window. Semeru's ORANGE phase dominates it. A second window (TEPHRA's own recorder, from October onward) is needed before claiming rates beyond "in these 30 days".
6. FL vs AMSL: the actual QNH offset at Semeru on the 1 Oct case was not computed.

## Sources

- MAGMA VONA list, pages 1 to 22: https://magma.esdm.go.id/v1/vona?page=1 (to page=22) [CONFIRMED, accessed 2026-10-10]
- VONA 22811 (Sinabung 1 Oct 0249Z): https://magma.esdm.go.id/v1/vona/22811?signature=7bdeca823123aa5666de9e491d05be074afbcb89428c4526f868aa96993fc140 [CONFIRMED]
- VONA 22819 (Karangetang 30 Sep 1007Z): https://magma.esdm.go.id/v1/vona/22819?signature=eccf77ed2c4919864b1ba70130889bd04ff62d235d84c2f9a54df62b20be1229 [CONFIRMED]
- VONA 22827 (Semeru 1 Oct 2224Z): https://magma.esdm.go.id/v1/vona/22827?signature=fe2ef8eae707cbee5f5a5dd65c1fbcd81ae4a77aed65e522e4edf9ffab73c8b1 [CONFIRMED]
- VONA 22729 (Semeru 26 Sep 2255Z): https://magma.esdm.go.id/v1/vona/22729?signature=092f3a4418bf50a8e4dbf5968fd5e7c57a6abf17d95048e1f8b5da15f713ce48 [CONFIRMED]
- VONA 22701 (Semeru 23 Sep 1612Z): https://magma.esdm.go.id/v1/vona/22701?signature=da7a78ffd27d8e281849737eafbf34da58aefaea73745670380cfdc5d331fc89 [CONFIRMED via list page]
- VONA 22867 (Semeru 7 Oct 1122Z): https://magma.esdm.go.id/v1/vona/22867?signature=977a4a9f44f6cba391bfd92976b21d39615917aabe1334b5ea3308511b3e4bd5 [CONFIRMED]
- Darwin VAAC FTP archive: ftp://ftp.bom.gov.au/anon/gen/vaac/2026/ [CONFIRMED]. Key texts: IDY41295.202610012318.txt (2026/1125), IDY41295.202610071025.txt (2026/1147), IDY41295.202610071634.txt (2026/1148), IDY41295.202609262322.txt (2026/1105), IDY41295.202610020514.txt (2026/1126)
- JMA Darwin-backup list: https://ds.data.jma.go.jp/svd/vaac/data/vaac_darwin_list.html [CONFIRMED]
- Tokyo VAAC list: https://ds.data.jma.go.jp/svd/vaac/data/vaac_list.html [CONFIRMED]; Mayon VAA 2026/794: https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20260921_27303000_0794_Text.html [CONFIRMED]
- AWC SIGMET API (hourly, 2026-09-08T20Z to 2026-10-09T19Z): https://aviationweather.gov/api/data/isigmet?format=json&hazard=va&date=2026-10-07T11:00:00Z (example) [CONFIRMED]; 30-day limit: https://aviationweather.gov/api/data/isigmet?format=json&hazard=va&date=2026-09-08T00:00:00Z [CONFIRMED HTTP 400]
- BoM recent pages: https://www.bom.gov.au/products/Volc_ash_recent.shtml , https://www.bom.gov.au/aviation/volcanic-ash/darwin-va-advisory.shtml [CONFIRMED, recent only]
- Wayback CDX: https://web.archive.org/cdx/search/cdx?url=bom.gov.au/products/Volc_ash_recent.shtml&from=20260801&output=json (returned `[]`)
- Earlier TEPHRA research: `13-contradiction-cases-reverified.md` (IEM is US-only; OGIMET SIGMET pages 404; 25 Sep Sakurajima B01 case)

## Search log

- No web search was needed. Every number comes from primary archives fetched with curl (see `manifest.tsv`, 1,567 fetch rows).
- Fetches:
  - MAGMA `v1/vona?page=1..22`;
  - BoM FTP directory listing plus 588 IDY41xxx text files;
  - JMA `vaac_list.html`, `vaac_darwin_list.html` and 154 + 3 TextData files;
  - AWC `isigmet` for every hour from 2026-09-08 00Z to 2026-10-09 19Z (20 × HTTP 400 beyond 30 days, 14 × HTTP 504, 1 timeout, 744 OK);
  - BoM web pages; the Wayback CDX query (HTTP 504 the first time, then `[]`).
- Re-checks on 2026-10-10 (`raw/recheck/`):
  - MAGMA page 1;
  - the FTP listing;
  - the JMA list;
  - AWC on 2026-09-08T00Z (400), 2026-09-09T00Z (200), 2026-09-09T12Z (200), 2026-09-11T12Z (200) and 2026-08-20T12Z (400);
  - Darwin IDY41295.202610012318 and .202610071634 (byte-identical to the archived copies);
  - VONAs 22811 and 22827;
  - Tokyo 2026/794.
- Not found or not usable:
  - a historical Darwin web archive (BoM pages show recent only; Wayback has no captures since August);
  - a non-US SIGMET archive (IEM is US-only and OGIMET has none, per file 13);
  - cancellation messages in AWC (0 `CNL SIGMET` records).
