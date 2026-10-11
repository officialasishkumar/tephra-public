# TEPHRA research report: BACKTEST agent (replay past eruptions, score the zone against later official products)

Written 2026-10-11. I read research/README.md, 09, 13, 14, 17, data/replay/README.md, the header of scripts/record_replay.py and the evals/plume file list. I did not repeat their content. Checks marked "curl" were my own header or byte-range requests; no project code was run and gcloud was not used.

## 0. Findings that change the plan

1. **NOAAPort day files hold everything needed, back to 2016.** I streamed the first ~150 MB of `20241209.tgz` and found these WMO headers: `FVFE01 RJTD 090724` (Tokyo VAA), `FVAU01/02/03 ADRM` (Darwin VAA), `WVID21 WAAA` (Ujung Pandang SIGMET) and `WVPH31 RPLL` (Philippines SIGMET). The Tokyo bulletin at 07:24Z matches Tokyo VAA 2024/62 (issued 0724Z, eruption 0703Z, FL180).
   - Source: https://mesonet-longterm.agron.iastate.edu/archive/raw/noaaport/2024/20241209.tgz
2. **The IEM AFOS query API does not hold these international bulletins.** `retrieve.py` returned "Could not Find" for the six-character AFOS PILs `WVID20`, `FVAU04`, `FVFE01`, `WVAU01` and `SIGAUS`, and for the three-character prefix `VAA`. The `retrieve.py` help page lists `pil`, `sdate`, `edate`, `limit` (max 9999), `fmt`, `matches`, `center` and `ttaaii`, but only for US text products. For these cases, stream the day tarballs; the recorder already does (`record_replay.py noaaport`).
   - https://mesonet.agron.iastate.edu/cgi-bin/afos/retrieve.py?help
   - https://mesonet.agron.iastate.edu/info/datasets/afos.html describes the dataset as "Generally US NWS Offices".
3. **NASA GIBS cannot serve past Himawari imagery.** My GetCapabilities fetch on 11 Oct showed rolling windows: `Himawari_AHI_Band13_Clean_Infrared` starts 2026-08-29, `Himawari_AHI_Air_Mass` starts 2026-09-19, and `Himawari_AHI_Band3_Red_Visible_1km` starts 2026-08-30, all at PT10M.
   - https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/wmts.cgi?SERVICE=WMTS&REQUEST=GetCapabilities
   - For older cases use the AWS buckets `noaa-himawari8` and `noaa-himawari9`, which hold full-disk archive data back to July 2015: https://registry.opendata.aws/noaa-himawari/
4. **The Tokyo VAAC list page is only a recent window.** The list at https://www.data.jma.go.jp/vaac/data/vaac_list.html starts at 1 Sep 2026 (advisory 2026/184), has no year or month archive links, and offers no bulk download. Older advisories are reachable only by constructing the URL (section 2.3).
5. **FMS is the Jaccard index, and it punishes TEPHRA's design.** The never-shrink widening makes the zone bigger than the official area, so Jaccard against a later official polygon will be low by construction. Lead the scorecard with coverage (POD) and cost (extra area), and show FMS only as a secondary number (section 1.3).

## 1. Verification metrics

### 1.1 What the literature uses

- **FMS.**
  - Definition: FMS = |A_mod ∩ A_obs| / |A_mod ∪ A_obs|, from 0 (no overlap) to 1 (perfect).
  - Prata et al. 2021 (FALL3D-8.0) pair it with SAL. "SAL below 1.5 and FMS above 0.40" are taken as acceptable agreement with satellite retrievals.
  - Objects are pixels above a detection threshold: 0.2 g m⁻² for SEVIRI ash. All comparisons are on a 0.1° grid.
  - SAL = |S|+|A|+|L|, range 0 to 6, where L = L1 + L2 (centre-of-mass distance terms).
  - Source: https://gmd.copernicus.org/articles/14/409/2021/gmd-14-409-2021.html
  - The same paper notes that it is "not yet clear" what absolute values count as acceptable.
- **Fractions Skill Score (FSS).**
  - Harvey and Dacre first used it to score NAME (the London VAAC model) against SEVIRI for Eyjafjallajökull.
  - It separates a "near miss" from a badly placed forecast, and showed useful skill at neighbourhood scales of 200 to 700 km (the source says "km²", which looks like a typo).
  - https://acp.copernicus.org/articles/16/861/2016/acp-16-861-2016.pdf
- **No standard exists for probabilistic ash forecasts.**
  - Crawford et al. 2022 (HYSPLIT ensembles, Bezymianny) use rank histograms, reliability diagrams, FSS and precision-recall curves.
  - https://acp.copernicus.org/articles/22/13967/2022/ and https://egusphere.copernicus.org/preprints/2022/egusphere-2022-290/egusphere-2022-290.pdf
- **How VAACs verify.**
  - Informally: forecasters compare the forecast cloud with satellite imagery by eye, so no objective score comes out (Harvey and Dacre).
  - The London QVA service says validation is done "at least once every 12 months": https://eur-registry.swim.aero/services/met-office-vaac-london-quantitative-volcanic-ash-10/selfvalidation-186526
  - I found no published hit-rate study of Darwin or Tokyo advisory polygons. Treat that as a literature gap, UNVERIFIED as a claim of absence.
- **Caveats that apply to any backtest against advisory polygons.**
  - The Darwin management report says the polygon's observation time comes from imagery that is slightly old because of receipt delay: https://www.icao.int/sites/default/files/APAC/Meetings/2025/2025%20MET%20SG29/4-Information%20Papers/IP08-AI.5-AUS-VAAC-MANAGEMENT-REPORT.pdf
  - Satellite ash retrievals are insensitive to particles larger than about 10 µm: https://nora.nerc.ac.uk/id/eprint/538536/1/JGR%20Atmospheres%20-%202024%20-%20Saint%20-%20Using%20Simulated%20Radiances%20to%20Understand%20the%20Limitations%20of%20Satellite%E2%80%90Retrieved%20Volcanic.pdf
  - Repo findings (research/14): SIGMETs copy the VAA (top matches 489 of 492), so "official later" is effectively one voice (the Darwin VAA) in Indonesia.
- **Hausdorff distance.** I found no VAAC paper that uses it. It is a standard polygon-distance measure, available as `shapely.hausdorff_distance` (general knowledge, UNVERIFIED against a VAAC source). Use it only as a "worst miss distance" diagnostic.

### 1.2 Truth definition for the backtest

"Official later" means the ash footprint in advisories issued after the replay time T0, never anything TEPHRA could see at T0.
- **Footprint A_k:** the OBS VA polygon and the +6/+12/+18 h forecast polygons of every VAA issued after T0, plus later VA SIGMET polygons. Each has an issue time t_k, a valid time v_k and a top FL.
- **Independent check:** METAR `VA` or `VCVA` at airports. IEM has these with no 30-day limit (research/17 R2). Example: WIII had 69 VA reports from 5 Sep 18:30Z to 7 Sep 05:00Z.
- **Leakage rule:** only feed data with timestamps ≤ T0. The existing `ReplaySource` already serves "the latest response at or before the replay clock".

### 1.3 Metric set (all deterministic, shapely, equal-area local projection, 0.1° grid for the cell-based ones)

Polygons: Z = TEPHRA zone at T0, O0 = official area at T0 (including its forecast polygon valid at v_k), A_k = later official footprint.

| Metric | Formula | Role |
|---|---|---|
| **Coverage (POD, area form)** | \|Z ∩ A_k\| / \|A_k\| | **Headline.** Ash the later official products included that TEPHRA already covered. |
| Baseline coverage | \|O0 ∩ A_k\| / \|A_k\| | What the official product at T0 already covered. |
| **Coverage gain** | Coverage − baseline | **Headline.** Always ≥ 0 by the never-shrink floor, which is a test in itself. |
| **Over-warning cost** | \|Z \ A_k\| / \|A_k\| (equivalently 1 − precision, i.e. FAR) | Headline. Shown next to the gain. |
| Excess vs official | \|Z\| / \|O0\| | Area ratio. Needed because TEPHRA widens. |
| Bias | \|Z\| / \|A_k\| | Area ratio against later truth. |
| CSI and FMS | \|Z ∩ A_k\| / \|Z ∪ A_k\| | Secondary. Same formula as Jaccard, so FMS ≡ CSI when only the two areas are counted. Compute both Z and O0 so the reader sees the intentional trade. |
| Hausdorff (km) | `shapely.hausdorff_distance(A_k, Z)` | Diagnostic: worst miss distance. |
| Centroid offset (km) | distance between centroids | Like SAL's L1 (SAL's L1 is normalised by the maximum domain distance). |
| Vertical hit | top_FL(Z) ≥ top_FL(A_k) | Boolean. Catches the Semeru 1 Oct case (observatory 4,976 m never adopted, research/14). |
| Airports reached | airports inside A_k, covered by Z or not | Dispatcher view. Compare with METAR VA reports. |

Reference lines: Prata's "FMS > 0.40" is the only published threshold I found, and it is for model versus satellite. Quote it as context, not as a pass mark for TEPHRA.

### 1.4 Lead-time metric (the one to feature)

For each later official footprint A_k, with issue time t_k and a coverage threshold τ = 0.9 (also report 0.5):
- t*_Z = the earliest replay tick t ≤ t_k such that the TEPHRA zone Z at t (and every later tick up to t_k) has coverage(A_k) ≥ τ and passes the vertical test.
- Lead_Z(k) = t_k − t*_Z, in minutes, capped at 24 h.
- Lead_O(k) is the same computation with the official-only zone.
- **Incremental lead = Lead_Z − Lead_O.** Report its median and p90, plus the count of footprints that TEPHRA covered before the official product did.
- Context for how large the gap can be: the repo census measured the lag from a new Semeru VONA to a VAA built on it at a median of 228 min (p90 463) (research/14).
- Two honest guards: report "no lead" cases (a miss or a tie), and show lead only where coverage also held at the issue time.

## 2. Archive sources for the backtest

### 2.1 IEM NOAAPort day files (primary)
- URL pattern: `https://mesonet-longterm.agron.iastate.edu/archive/raw/noaaport/YYYY/YYYYMMDD.tgz`
- Verified by curl HEAD, all 200: 20191230 (345 MB), 20200113 (353 MB), 20211204 (264 MB), 20231203 (274 MB), 20240417 (293 MB), 20241104 (302 MB), 20241209 (300 MB), 20250707 (307 MB), and 20160101, 20180101 and 20190101. 20120101 returned 404, and the directory index lists year folders from 2016.
- Licence: public domain and free for any lawful purpose, attribution appreciated (https://mesonet.agron.iastate.edu/disclaimer.php, quoted in research/17 R1). The bulletins come from BMKG, BoM, JMA and others; credit the originators too. Redistribution in a public repo is allowed for these relayed texts. The repo already refuses BoM-footer content.
- Rate limits: the main-host robots.txt says `Crawl-delay: 120`. The longterm host showed no stated limit. A day file is about 300 MB of plain gzip and must be read from byte 0.
- Cost of a case: a 4-day window streams about 1.2 GB. Cache the VA-only JSON lines once.
- Headers to keep:
  - `FVFE01 RJTD` (Tokyo VAA)
  - `FVAU01–04 ADRM` (Darwin VAA)
  - `WVID20 WIII` and `WVID21 WAAA` (Indonesian SIGMETs)
  - `WVPH31 RPLL` (Philippines)
  - `WVJP?? RJ??` (Japan) is UNVERIFIED; check the real header on a Sakurajima day
  - `WVAU01 YMMC` (Melbourne)
  - METAR collectives for the Indonesian and Philippine stations
- Other query routes:
  - IEM ASOS and METAR CSV: https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py with `report_type=3&report_type=4`; one request per second per IP (research/17).
  - The AFOS API is useless for these headers, see 0.2.
  - AWC `isigmet` has 30 days of history only (research/09).

### 2.2 Himawari imagery for a case
- AWS buckets `noaa-himawari8` and `noaa-himawari9` hold full-disk archive data back to July 2015 (https://registry.opendata.aws/noaa-himawari/). The licence text says "NOAA and JMA request attribution for the use or dissemination of unaltered data" and does not allow implying endorsement. Redistribution of derived stills in a public repo is fine with attribution. Raw segments are large, so keep stills only.
- The `evals/plume/cases` folders already use Tokyo VAAC's labelled Ash RGB and IR frames. Reuse that source for backtest stills, not GIBS.

### 2.3 Tokyo VAAC archive
- Advisory text pages follow `https://www.data.jma.go.jp/vaac/data/TextData/YYYY/YYYYMMDD_<GVP number + 2-digit suffix>_<advisory seq>_Text.html`. Verified examples:
  - Kanlaon (GVP 272020): https://www.data.jma.go.jp/vaac/data/TextData/2024/20241209_27202000_0062_Text.html, with 0063 and 0064 the same day.
  - Sakurajima (GVP 282080): https://www.data.jma.go.jp/vaac/data/TextData/2022/20220722_28208001_0036_Text.html
- Pages with a `_DA_` suffix, such as https://www.data.jma.go.jp/vaac/data/TextData/2024/20240418_26701000_0025_DA_Text.html (Ruang), are JMA copies of Darwin advisories. Why JMA issued them (probably Darwin backup) is an inference, UNVERIFIED.
- Licence: JMA Public Data License 1.0, compatible with CC BY 4.0. Cite "Source: Japan Meteorological Agency website (URL)"; state any edits. The terms exclude third-party content and the JMA logo, and are subject to the Meteorological Service Act. https://www.jma.go.jp/jma/en/copyright.html
- Use: ground-truth reading and citation links. Prefer NOAAPort for bulk, since the list page only reaches back to 1 Sep 2026.

### 2.4 Smithsonian GVP
- Fetching volcano.si.edu returned 403 (WebFetch, and in research/05). I could not read its pages.
- Licence: the site says its content is governed by the Smithsonian Terms of Use (personal, educational and other non-commercial use), with minimum citation "Global Volcanism Program, Smithsonian Institution". The weekly report is a joint product with USGS, and the cite page says it is a product of US employees (UNVERIFIED which Terms category and what it allows). Sources: https://volcano.si.edu/gvp_termsofuse.cfm and https://volcano.si.edu/gvp_cite.cfm (via search summaries).
- Redistribution in a public repo: treat as NOT confirmed. Quote only eruption facts (date, VEI) with the citation. Do not copy report text or the database.
- Eruption times for ground truth are better taken from the observatory VONA texts, the VAA remarks, and agency statements. Use the GVP number only as the volcano ID.

## 3. Candidate eruption cases

A dispatcher-grade case needs: an eruption time, official products across several issues, and a public archive. "Verified" means I saw it in a source in this session; where the VAAC top is not verified I say so. Sakurajima's 2022 Level 5 event and Taal 2020 are confirmed events but have no verified Tokyo FL in my sources.

| # | Event (UTC) | Region, VAAC | Verified facts | Archive day file(s) | Status |
|---|---|---|---|---|---|
| 1 | Anak Krakatau, 5–7 Sep 2026 | Java, Darwin | Ash to FL500; CGK and 7 airports closed (repo research/01, 17) | already a replay case | In repo |
| 2 | Semeru, 23–27 Sep 2026 | Java, Darwin | SIGMETs MOV SE vs VONAs N/NE (research/13) | already a replay case | In repo |
| 3 | Taal, 8 Oct 2026 | Luzon, Tokyo | Last Tokyo advisory 2026/24 at 08/1750Z (research/09) | 20261008 (posted ~10:05Z next day) | To record |
| 4 | **Kanlaon, 9 Dec 2024** | Negros, Tokyo | Eruption 0703Z; 2024/62 FL180; 2024/63 FL220 on a ground report; 2024/64 SFC/FL220 W 30 kt, +6 h FL250, +12 h FL300; PHIVOLCS Level 3; cancellations 9–10 Dec | 20241209, 20241210 (200 verified for 1209) | Strong |
| 5 | **Ruang, 17–18 Apr 2024** | N Sulawesi, Darwin | Level IV 17 Apr; Darwin 2024/25 18 Apr 1500Z FL500, code RED; Manado closed 18 Apr 0000Z to 22 Apr 0400Z | 20240417, 20240418 | Strong |
| 6 | Ruang, 30 Apr to 1 May 2024 | same | Darwin: FL450/630 layers plus a low layer to FL080 | 20240430, 20240501 | Strong |
| 7 | **Lewotobi, 3–4 Nov 2024** | Flores, Darwin | Directed blast 23:57 local on 3 Nov (sources date it 3 or 4 Nov), 9 dead, Level IV; ash about 2,000 m per NASA EO; Bali cancellations from 4 Nov | 20241103, 20241104 (1104 verified 200) | Date disputed; FL UNVERIFIED |
| 8 | Lewotobi, 13 Nov 2024 | Flores, Darwin | Ash to 9–10 km; 90 Bali flights cancelled; flights resumed 14 Nov | 20241113 | Strong |
| 9 | Lewotobi, 17 Jun 2025 | Flores, Darwin | Darwin advisory to FL530 (search snippet, UNVERIFIED primary); ~32 Bali flights cancelled | 20250617 | Needs check |
| 10 | Lewotobi, 7 Jul 2025 | Flores, Darwin | Ash column ~18 km above summit; 24 Bali flights cancelled; Komodo and Maumere closed. Darwin FL not found | 20250707 (verified 200) | FL UNVERIFIED |
| 11 | Semeru, 19 Nov 2025 | Java, Darwin | PDCs from 1413 local; Level IV; ASHTAM VAWR6038: low-level ash up to FL150, high-level up to FL450; no airport closures | 20251119 | Strong (VAA text not read) |
| 12 | Semeru, 4 Dec 2021 | Java, Darwin | Dome-collapse PDCs; NASA says a cloud reaching about 15 km; Darwin said ash drifting SW; Darwin FL not found | 20211204 (verified 200) | FL UNVERIFIED |
| 13 | Marapi, 3 Dec 2023 | Sumatra, Darwin | Eruption 07:54Z; Darwin's final advisory estimated FL500 (CIMSS); ground reports ~3 km | 20231203 (verified 200) | Outside your regions but good coverage |
| 14 | Ibu, 13–27 May 2024 | Halmahera, Darwin | Level III on 8 May, Level IV on 16 May with a red VONA; ash 5–6 km; Darwin FL not found | 20240513, 20240516, 20240527 | FL UNVERIFIED |
| 15 | Sakurajima, 24 Jul 2022 | Kyushu, Tokyo | Eruption ~20:05 JST (about 11:05Z), alert Level 5; Tokyo advisories 2022/36 (22 Jul, FL050), 38 (23 Jul) | 20220724 | Event confirmed; ash FL UNVERIFIED |
| 16 | Taal, 12–13 Jan 2020 | Luzon, Tokyo | NAIA suspension 12 Jan (departures from 6:22 pm, arrivals from 7:00 pm local); AFP 15 km; magmatic phase 02:49 local 13 Jan | 20200112, 20200113 (verified 200) | Tokyo FL UNVERIFIED |

Sources for the table:
- Kanlaon: https://www.data.jma.go.jp/vaac/data/TextData/2024/20241209_27202000_0063_Text.html and https://www.data.jma.go.jp/vaac/data/TextData/2024/20241209_27202000_0064_Text.html, plus https://abs-cbn.com/news/business/2024/12/10/list-cancelled-flights-due-to-kanlaon-eruption-december-10-1105
- Ruang: https://www.icao.int/sites/default/files/APAC/Meetings/2024/2024%20ATMSG-12/4-Information%20Papers/IP08-Contingency-Plan-for-Volcanic-Ash-at-Mount-Ruang-Indonesia.pdf, https://www.data.jma.go.jp/vaac/data/TextData/2024/20240501_26701000_0065_DA_Text.html
- Lewotobi 2024: https://ijog.geologi.esdm.go.id/index.php/IJOG/article/view/1318, https://www.aljazeera.com/economy/2024/11/13/airlines-cancel-bali-flights-after-volcano-spews-ash-miles-into-the-sky, https://en.antaranews.com/amp/news/334221/bali-airport-cancels-90-flights-due-to-mt-lewotobi-eruption
- Lewotobi 2025: https://mataram.antaranews.com/berita/468229/lewotobi-eruption-24-flights-cancelled-at-bali-airport, https://earthobservatory.nasa.gov/images/154520/towering-plume-from-mount-lewotobi-laki-laki, https://www.aljazeera.com/news/2025/6/18/dozens-of-bali-flights-cancelled-after-indonesia-volcano-erupts
- Semeru 2025: https://sentinel-asia.org/EO/2025/article20251119ID.html, https://earthobservatory.sg/news/blog/how-the-recent-eruptions-in-indonesia-were-reported-to-aviation-authorities
- Semeru 2021: https://science.nasa.gov/earth/earth-observatory/a-deadly-day-on-mount-semeru-149198/
- Marapi: https://cimss.ssec.wisc.edu/satellite-blog/archives/date/2023/12/03, https://en.wikipedia.org/wiki/2023_eruption_of_Mount_Marapi
- Ibu: https://www.thejakartapost.com/indonesia/2024/05/16/authorities-raises-halmahera-volcano-alert-level-to-highest-
- Sakurajima: https://www.data.jma.go.jp/vaac/data/TextData/2022/20220722_28208001_0036_Text.html
- Taal 2020: https://newsinfo.inquirer.net/1211954/miaa-puts-all-naia-flights-on-hold-after-taal-eruption/
- Kanlaon is active now (Tokyo advisories 2026/260 and 261 on the 11 Oct list page), so live and backtest can share a volcano.

Recommended order: cases 4, 5, 8, 11 (verified, with different VAACs and regimes), then 1 and 2 (already built), then 3 and 15 for Tokyo and Kyushu coverage. If a day file lacks a case's SIGMET or VAA (spot-check each before building), drop that case rather than reconstruct.

## 4. Fitting the free Gemini quota

- **Budget:** about 20 RPD for gemini-3.8-flash and about 500 RPD for gemini-3.5-flash-lite (task statement; research/06 lists 3.8 Flash at about 20 as "reported only", so check in AI Studio). Token-per-minute limits are UNVERIFIED.
- **Scoring is pure code:** polygons, grid, shapely, no model calls. A rerun costs nothing.
- **Zone-generation arms:**
  - **Arm D (deterministic).** The union of the official polygons plus a wedge from the vent along the observatory direction, with its length set by wind speed times VONA-to-VAA lag. Zero calls. It shows what the never-shrink floor and the wedge give without an LLM.
  - **Arm G (Gemini).** The Gemini cone, clipped by union-with-official so it can only widen. Run on gemini-3.5-flash-lite and cache every response keyed by the sha256 of the inputs (the same approach as `evals/plume/results/raw`).
  - Budget: 13 cases × about 6 ticks ≈ 78 calls, so one day on flash-lite. Do not plan it on the 20-RPD flash model. State in the report that the backtest used flash-lite whenever the live demo uses a different model.
- **Write-up:** one flash-lite call per run. Inject the scorecard JSON and ask for per-case prose and a summary. Then post-check that every number in the prose appears in the JSON, regenerate or drop the sentence if not, and never let the model compute anything.
- Resumable runs: reuse the existing pattern (`--max-calls`, cache, `--score-only`).

## 5. Output formats

**Markdown report** (`evals/backtest/REPORT.md`):
1. Headline table: one row per case, columns Coverage gain, Over-warning cost, Excess ratio, Median incremental lead, Vertical hit.
2. Per-case section: timeline, the three polygons, flagged misses.
3. Method and limits, including these four caveats:
   - The official later product is partly derived from the same VONA and satellite inputs.
   - The Indonesian SIGMET copies the Darwin VAA.
   - Satellite retrievals miss coarse ash.
   - TEPHRA's zone is a decision margin, not a forecast of observed ash.

**JSON scorecard** (`evals/backtest/scorecard.json`), one object per case:
```json
{
 "case_id": "kanlaon-20241209", "vaac": "Tokyo", "t0": "2024-12-09T08:30Z",
 "arm": "gemini-flash-lite|deterministic",
 "inputs": {"sources_used": ["VONA","VAA","SIGMET"], "latest_input_ts": "..."},
 "ticks": [{"t": "...", "zone_area_km2": 0, "official_area_km2": 0,
   "coverage": 0.0, "coverage_official": 0.0, "coverage_gain": 0.0,
   "overwarn": 0.0, "excess_vs_official": 0.0, "bias": 0.0,
   "csi": 0.0, "csi_official": 0.0, "hausdorff_km": 0.0,
   "centroid_km": 0.0, "vertical_hit": true,
   "airports_reached": ["RPVB"], "metar_va_airports": ["RPVB"]}],
 "lead": {"tau": 0.9, "median_min": 0, "p90_min": 0, "n_footprints": 0,
   "n_covered_before_official": 0, "n_missed": 0},
 "floor_violations": 0,
 "models": {"gemini": "model-id", "calls": 0}
}
```
`floor_violations` is a self-test: it must be 0, because the zone may never shrink below the official polygon.

## 6. UI and video presentation

- **UI.** Add a "Backtest" tab to the replay banner:
  - A case picker and a time scrubber over the existing REPLAY mode, with three layers: TEPHRA zone at T0, official at T0, and official later, with a tick marking each later issue time.
  - Beneath the map, three chips (coverage gain, over-warning cost, median lead) and a lead-time bar per footprint.
  - A list of misses, because showing failures is credible.
  - A link to the scorecard JSON.
- **Video (about 25 s of the 3-minute cut).** Pick one clean case (Kanlaon 9 Dec 2024 or Ruang 18 Apr 2024). Freeze at T0 and show the official area and TEPHRA's wider zone. Scrub forward to the later official polygon landing inside TEPHRA's zone, and caption the median lead in minutes. Close on the scorecard row. Say plainly that official products at T0 already covered X% and TEPHRA added Y points at Z% extra area.
- **Deck.** One slide: a table of 6 to 8 cases, with the caveat line. Do not use FMS as the pass mark; explain in a footnote why a widened zone lowers Jaccard.

## 7. Recommendation for TEPHRA

1. **Metric set.** Headline: coverage (POD), coverage gain over the official baseline, over-warning cost (1 − precision), and incremental lead time at τ = 0.9. Diagnostics: area ratios, Hausdorff km, centroid km, vertical hit, airports reached against METAR VA. Secondary: CSI/FMS shown for Z and for O0, quoting Prata's 0.40 only as context.
2. **Spatial setup.** Project to a local azimuthal equal-area system around the vent. Use a 0.1° grid for cell metrics, matching Prata's grid. Compare only footprints whose FL band overlaps the zone, and report vertical hit separately.
3. **Lead-time algorithm.** Ticks every 30 min of replay clock; a footprint is "covered" when coverage ≥ τ continuously from t* to t_k; cap at 24 h; report median, p90 and counts, with the official-only baseline computed identically.
4. **Case list.** Start with Kanlaon 9 Dec 2024, Ruang 18 Apr 2024 and 1 May 2024, Lewotobi 13 Nov 2024, Semeru 19 Nov 2025 (all with verified official coverage), plus the two built cases (Krakatau, Semeru Sep 2026). Add Taal 8 Oct 2026 and Sakurajima 24 Jul 2022 for Tokyo and Kyushu. Before building each, confirm the day files contain the case's `WVxx` and `FVxx` bulletins.
5. **Data files.** Per case, store the VA-only JSON lines from the NOAAPort stream (SIGMET, Darwin and Tokyo VAA, METAR) as the existing `backfill` produces them, and keep only derived stills for imagery. Cite IEM, JMA (Public Data License 1.0, "Source: Japan Meteorological Agency website (URL)") and the issuing agencies. Do not store BoM FTP files, MAGMA pages or GVP text.
6. **Zone arms and quota.** Run Arm D (deterministic) on every case at no cost. Run Arm G on flash-lite with sha256 caching, at most about 78 calls in one day. Do one flash-lite call to write the report, with a number-match check against the scorecard JSON.
7. **Self-tests that must pass before showing results.** `floor_violations == 0` on every tick, and no input timestamp after T0.
8. **Messaging.** "TEPHRA covered N% of the ash the officials later drew, M points more than the official area at the time, at K% extra area, a median of X minutes earlier." Show the misses and the cost side. Do not claim ash truth, because the later official polygon is itself a product with its own lag.
9. **Open items.**
   - Darwin and Tokyo FLs for cases 7, 9, 10, 12, 14, 15 and 16.
   - The header of the Japanese VA SIGMET (`WVJP??`).
   - The GVP terms category for the weekly report.
   - The free-tier token-per-minute limits.
   - Why JMA hosts `_DA_` pages.
