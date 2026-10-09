# 12. Raw Himawari split-window: can TEPHRA compute the ash signal itself? (Akash's point B)

Researched 2026-10-10 (local; the machine clock read 2026-10-09 19:32 to 20:00 UTC). Tags: [CONFIRMED: url, accessed 2026-10-10] means I opened it and it says that; [MEASURED] means I listed or downloaded the public file myself and computed the number in a scratch script (no project code was run); [REPORTED: url] is secondary; [UNVERIFIED] is my own knowledge or inference.

Note on method: the session's shared web-search budget ran out after three searches in this pass. Everything below was then established by opening known URLs directly, by DOI metadata lookups, and by listing and downloading the public bucket with curl. Gaps that need a search are listed in the Open questions.

## Bottom line

1. **Access: yes, today, with no account.** `s3://noaa-himawari9` lists and downloads anonymously over HTTPS. Full-disk Level 1b data arrive every 10 minutes as 160 bzip2 files (16 bands x 10 segments). The Java strip was on S3 about 12 to 13 minutes after the nominal scan start [MEASURED].
2. **Licence: fine for a competition prototype, with conditions; commercial use is not settled.** The AWS registry says "NOAA has rights to distribute this data freely and openly to the public", asks for attribution, forbids implying NOAA or JMA endorsement, and says modified data must not be presented as original [CONFIRMED: https://registry.opendata.aws/noaa-himawari/]. JMA's own channels steer profit use to JMBSC and forbid redistribution, so TEPHRA should show derived images and numbers, not re-serve the raw files.
3. **Cost: trivial.** Java and Bali sit in one segment (S06). Two bands are about 5.6 MB per 10 minutes. Decompressing and calibrating one segment took 0.12 s and 0.03 s on this laptop with numpy only; peak memory for two bands was about 205 MB [MEASURED]. That fits Cloud Run's free tier by a wide margin.
4. **Science: the split-window signal works, but often stays silent in the tropics.** Indonesia is the worst case: water vapour and ice mask the negative difference, and small, low eruptions fall below resolution. Tupper et al. (2004, Darwin VAAC and Tokyo VAAC authors) name Semeru as an example of eruptions that "have often fallen below satellite resolution or have been completely obscured by cloud" [CONFIRMED: http://www.bom.gov.au/info/vaac/publications/Tupper_etal_Western_Pacific_2004.pdf].
5. **Our own test on Akash's two cases: silent.** At Semeru on 2026-09-25 11:05Z and 2026-10-07 10:05Z and 10:15Z, no pixel within about 200 km of the vent had a negative 11-12 um difference. The local median was about +3 K [MEASURED]. The raw signal therefore cannot settle either SIGMET-versus-VONA disagreement. It is consistent with both "no ash" and "ash the method cannot see". The same code also stayed silent for 10 hours after the reported 2024-04-16 Ruang eruption, where the moist background was +4 to +6 K. It lit up clearly for the 2019 Raikoke plume in dry mid-latitude air: min -5.2 K, 3,331 pixels below -1 K [MEASURED]. The method works where the physics allows and goes blind over Indonesia.
6. **Verdict on B:** "Code computes BTD, Gemini reads it next to the texts" is sound and can be built by 2026-10-18. It is only sound as a one-way corroborating layer. A negative BTD near the vent can widen the cone or raise the urgency. A silent BTD must never narrow anything or be called "no ash". Show it as a heat-map crop with the official polygon drawn over it.

---

## 1. Access and licence

### 1.1 AWS registry page (quoted in full where it matters)

- Name: "JMA Himawari-8/9" [CONFIRMED: https://registry.opendata.aws/noaa-himawari/, accessed 2026-10-10].
- **Managed by:** "See all datasets managed by NOAA." [CONFIRMED: same URL]
- **License** (verbatim): "Himawari data is produced and managed by JMA. NOAA has rights to distribute this data freely and openly to the public. NOAA makes data openly available to ensure maximum use of our data, and to spur and encourage exploration and innovation throughout the industry. NOAA and JMA request attribution for the use or dissemination of unaltered data. However, it is not permissible to state or imply endorsement by or affiliation with NOAA or JMA. If you modify these data, you may not state or imply that it is original, unaltered data." [CONFIRMED: same URL]
- Update frequency: "10 minutes for Full Disk, 2.5 minutes for Regions 1, 2, and 3, and .5 minutes for Regions 4 and 5." [CONFIRMED: same URL]. (Regions 4 and 5 are not in the bucket; see 1.3.)
- Access: "Access (No AWS account required)", `aws s3 ls --no-sign-request s3://noaa-himawari9/`, region us-east-1 [CONFIRMED: same URL].
- New-object notifications: SNS topic `arn:aws:sns:us-east-1:123901341784:NewHimawariNineObject`, "only Lambda and SQS protocols allowed" [CONFIRMED: same URL]. A Google Cloud service cannot subscribe directly, so TEPHRA should poll the listing (one anonymous ListObjectsV2 call per minute is enough) [UNVERIFIED design note].
- Archive: "Archive data back to July 2015 is available for Full Disk (AHI-L1b-FLDK) products in the bucket" [CONFIRMED: same URL]. Older years sit in `s3://noaa-himawari8`; the 2019 files I read there are unsegmented whole-disk files (`..._S0101.DAT.bz2`, about 24.6 MB per band, uploaded 2022-02-16) [MEASURED].
- Contact: nodd@noaa.gov [CONFIRMED: same URL].

### 1.2 JMA's own position on use

- **JMA website terms (Public Data License v1.0, CC BY 4.0 compatible)** cover "Information made available on the Japan Meteorological Agency website" and require source citation and an "edited" statement for edited content [CONFIRMED: https://www.jma.go.jp/jma/en/copyright.html, accessed 2026-10-10]. These terms are for website content. They do not say they govern Himawari Standard Data redistributed by NOAA [UNVERIFIED interpretation].
- **JMA dissemination page:** JMA "provides Himawari-8/9 data to the private sector and other communities" through the Japan Meteorological Business Support Center (JMBSC). Four Japanese institutions provide "archiving and redistribution services on a best-effort basis for research, development and education", and users "must ... observe the individual data usage policies" [CONFIRMED: https://www.jma.go.jp/jma/jma-eng/satellite/dissemination.html, accessed 2026-10-10 via WebFetch summary].
- **HimawariCloud** (JMA's own feed) is "For NMHSs only" [CONFIRMED: https://www.data.jma.go.jp/mscweb/en/himawari89/cloud_service/cloud_service.html, accessed 2026-10-10].
- **JAXA P-Tree** (one of the research redistributors) states: "Use of the data provided by this system is limited to non-profit purposes such as research and education." It also states: "Regarding the use of data via this system, data from February 1, 2026 (00:00 UTC) are available for commercial use." and "You cannot redistribute the data to the third parties." For profit use it says to contact JMBSC [CONFIRMED: https://www.eorc.jaxa.jp/ptree/registration_top.html, accessed 2026-10-10; text pulled with curl].
- I did not find a JMA statement about the NOAA copy specifically, and the search budget ran out. The NOAA registry text is the only licence attached to the bucket.

**What this means for TEPHRA [UNVERIFIED interpretation, not legal advice]:**
- A competition prototype that downloads from the NOAA bucket and shows derived products (a BTD heat map, pixel counts, a polygon) is covered by the NOAA terms, provided it (a) credits "Himawari-9 data: JMA, distributed by NOAA (NODD / AWS Open Data)", (b) labels the derived product "processed by TEPHRA; not original JMA data", and (c) never uses NOAA or JMA logos or implies endorsement.
- Do not mirror or re-serve the raw HSD files from TEPHRA. Show derived products only.
- A paid product later should get written confirmation from nodd@noaa.gov and JMBSC. The P-Tree wording ("commercial use" allowed only from 2026-02-01 through that channel) suggests JMA's position on commercial use changed in 2026, but that is one redistributor's page.

### 1.3 What each prefix holds (listed 2026-10-09 ~19:33 UTC)

Top-level listing: `index.html` (an S3 explorer page) plus six prefixes [MEASURED: https://noaa-himawari9.s3.amazonaws.com/?list-type=2&delimiter=/]. Every prefix has year folders 2022 to 2026 (Clouds and Winds from 2023) and day folders up to 2026/10/09.

| Prefix | What it is | File pattern (real example) | Size per file | Files per slot | Cadence | Measured latency |
|---|---|---|---|---|---|---|
| `AHI-L1b-FLDK/` | Full-disk Level 1b, Himawari Standard Data (HSD) v1.3, bzip2 per file | `HS_H09_20261009_1910_B13_FLDK_R20_S0610.DAT.bz2` | IR bands 1.1 to 3.0 MB per segment (B13 S06 2,877,933 B); B01 up to 5.7 MB; B03 (0.5 km) larger | 160 (16 bands x 10 segments), 548 MB total for 1910Z | 10 min | 1910Z slot: objects written 19:20:44 to 19:24:08Z. B13 S06 header says scanned 19:15:05 to 19:16:04Z, file created 19:18:18Z, on S3 19:22:11Z. 1920Z slot: 129 of 160 objects present at 19:33:19Z |
| `AHI-L1b-Japan/` | Japan Area (Regions 1+2), 1500 x 1200 px at 2 km | `HS_H09_20261009_1910_B13_JP01_R20_S0101.DAT.bz2` (JP01..JP04 = the four 2.5-min scans in each 10-min timeline) | about 1.0 MB per IR band per scan | 64 in the 1910Z folder (16 bands x 4 scans), 70.6 MB | 2.5 min | JP01 written 19:16:33Z for a 19:10:14 to 19:11:51Z scan, so about 5 min |
| `AHI-L1b-Target/` | Target Area (Region 3), 500 x 500 px at 2 km, pointed by JMA | `HS_H09_20261009_1910_B13_R301_R20_S0101.DAT.bz2` (R301..R304) | about 0.27 MB per IR band per scan | 64 (16 bands x 4 scans), 17.7 MB | 2.5 min | about 4 to 5 min |
| `AHI-L2-FLDK-Clouds/` | NOAA Enterprise cloud products: `AHI-CHGT` (cloud-top height, temperature and pressure), `AHI-CMSK` (cloud mask), `AHI-CPHS` (cloud phase), netCDF4/HDF5 | `AHI-CHGT_v1r1_h09_s202610091900211_e202610091909405_c202610091914073.nc` | CHGT 744 MB, CMSK 349 MB, CPHS 85 MB | 3 | 10 min | 1900Z slot written 19:17:46Z, about 18 min after scan start |
| `AHI-L2-FLDK-Winds/` | NOAA derived motion winds (`NDMW-AHI-C07CT`, `C08CT`, `C14CT`), netCDF | `NDMW-AHI-C14CT_v1r2_h09_s202610091850213_e202610091859407_c202610091913511.nc` | 7.6 to 14.0 MB | 3 | 10 min | about 24 min |
| `AHI-L2-FLDK-ISatSS/` | AWIPS "Sectorized_CMI" tiles (GOES-R style netCDF4, ICD `SE-08_7034704_GS_AWIPS_Ext_ICD_RevB.3`), full disk (`OR_HFD-...`) plus Region 3 (`OR_HR3-...`) | `OR_HFD-020-B12-M1C13-T060_GH9_s20262821910000_c20262821919530.nc` | about 0.2 to 0.5 MB per 2-km tile; all 88 B13 tiles 26.3 MB | 1,408 per full-disk slot (16 channels x 88 tiles); HR3 slots at :x2, :x4, :x7 | 10 min (HFD), 2.5 min (HR3) | 1920Z HFD tiles written 19:30:41 to 19:33:38Z |

All rows are [MEASURED] by anonymous curl of `https://noaa-himawari9.s3.amazonaws.com/?list-type=2&prefix=...` on 2026-10-09 between 19:32 and 19:50 UTC. The CHGT contents come from metadata strings in byte-range reads of the file. They include "Enterprise Cloud-top Temperature (CTT)/ Pressure (CTP)/ Height (CTH) Products", "Enterprise Cloud Height Algorithm", "NESDIS Common Cloud Framework", variables `CldTopHght`, `CldTopTemp`, `CldTopPres`, `CldTopEmss`, `CldOptDpthAWIPS`, a "Parallax corrected Latitude", and a 5500-pixel dimension.

The bucket is not requester-pays, so downloads cost the user nothing on the AWS side [MEASURED: anonymous downloads succeeded]. Ingress to Cloud Run is free; only outbound internet transfer is billed [CONFIRMED: https://cloud.google.com/run/pricing, accessed 2026-10-10, "Outbound internet data transfer ... is charged"].

---

## 2. Geometry: which segments cover the volcanoes

### 2.1 Layout (source: JMA HSD User's Guide v1.3)

- Full disk at 2 km (bands 5 to 16) is 5,500 x 5,500 pixels. The Japan Area is 1,500 x 1,200 and the Target Area 500 x 500 at 2 km [CONFIRMED: https://www.data.jma.go.jp/mscweb/en/himawari89/space_segment/hsd_sample/HS_D_users_guide_en_v13.pdf, Table 3, accessed 2026-10-10].
- The file name segment field `kkll` means "kk: segment number (01 - ll)", "ll: total number of segments" [CONFIRMED: same PDF, Table 4].
- The projection is "Normalized Geostationary Projection ... as defined in 'LRIT/HRIT Global Specification' Section 4.4"; block #3 holds sub_lon = 140.7, CFAC, LFAC, COFF and LOFF; block #7 holds "Total number of segments", "Segment sequence number" and "First line number of image segment" [CONFIRMED: same PDF, section 3 and Table 6].
- Full-disk files are "divided into 10 segments from north to south" [REPORTED: JMA HimawariCloud page, via search summary; consistent with the headers below].
- Real headers on 2026-10-09: B13 S0610 has 5,500 columns x 550 lines, first line 2751, CFAC = LFAC = 20,466,275, COFF = LOFF = 2750.5, format version "1.3", internal compression flag 0 (the bzip2 wraps the whole file) [MEASURED]. Segment k therefore covers lines 550(k-1)+1 to 550k: S05 ends at line 2750 (the equator) and S06 starts at line 2751.

### 2.2 Segment per target (computed with the CGMS forward projection from the real header values) [MEASURED]

| Target | lat, lon | Full-disk line, column | 2-km segment |
|---|---|---|---|
| Krakatau / west Java corner | 6.1 S 105.4 E / 6 S 105 E | 3075 / 3069 | S0610 |
| Semeru | 8.11 S 112.92 E | 3186, 1314 | S0610 |
| Agung, Bali | 8.34 S 115.51 E | 3200 | S0610 |
| Java/Bali SE corner | 9 S 116 E | 3236 | S0610 |
| Lewotobi (Flores) | 8.54 S 122.78 E | 3215 | S0610 |
| Dukono, Halmahera | 1.69 N 127.89 E | 2657 | S0510 |
| Ibu, Halmahera | 1.49 N 127.63 E | 2669 | S0510 |
| Ruang | 2.30 N 125.37 E | 2624 | S0510 |
| Kanlaon | 10.41 N 123.13 E | 2185 | S0410 (near S04/S05 boundary at 2200) |
| Sakurajima, Kyushu | 31.59 N 130.66 E | 1141 | S0310; also inside the Japan Area every 2.5 min |

So the whole Java-Bali box (6 to 9 S, 105 to 116 E, lines 3069 to 3236) is in **one** segment, S06. Halmahera is in S05. Sakurajima is in S03, and better covered by `AHI-L1b-Japan`: the JP01 file of 2026-10-09 19:10Z spans roughly 20.6 to 52.9 N and 103 to 154 E at its corners, with its centre near 33.7 N 133.4 E [MEASURED from header COFF/LOFF].

### 2.3 Is the 2.5-minute Target Area ever pointed at volcanoes?

- JMA's real-time page labels the Target Area product "Tropical cyclone or volcanic ash". Its history page gives observation modes "TY:Tropical cyclone, VL:Volcanic ash, ND:Nadir, XD:South Pacific, XX:Reserve, IN:International cooperation, RT:Routine" and publishes a monthly CSV [CONFIRMED: https://www.data.jma.go.jp/mscweb/data/himawari/index.html and https://www.data.jma.go.jp/mscweb/data/himawari/obs_info_tg_en.html, accessed 2026-10-10].
- I scanned every monthly CSV from 2015-07 to 2026-10 (`https://www.data.jma.go.jp/mscweb/data/himawari/csv/tg/TG_OBS_POS_YYYYMM.csv`). **VL mode appears in every month from 2015-07 to 2018-11 and in no month from 2018-12 to 2026-10** [MEASURED]. Most VL scenes were centred near 158.1 E 51.9 N (Kamchatka); a few in 2016-01 were near 124.8 E 1.1 N (north Sulawesi) [MEASURED].
- Recent months are TY, CL (centred near 142 E 27 N; CL is not defined in the page legend) and IN. April 2024, the month of the Ruang eruption, had only CL, IN and ND [MEASURED]. The 2026-10-09 19:10Z scene was centred near 30.0 N 146.8 E, in TY mode per the October CSV [MEASURED].
- **Conclusion:** TEPHRA cannot count on 2.5-minute Target Area data over Indonesian volcanoes. It should use the 10-minute full disk for Indonesia and the 2.5-minute Japan Area for Sakurajima.

---

## 3. Format and readers

### 3.1 Format
- HSD (Himawari Standard Format) v1.3: 11 header blocks plus a data block of 2-byte unsigned counts; error count 65,535 and outside-scan count 65,534 [CONFIRMED: HSD guide Table 6; MEASURED: "format_version: 1.3" in 2026-10-09 files].
- IR calibration: radiance = slope x count + intercept. Effective temperature comes from the inverse Planck function at the central wavelength, then Tb = c0 + c1·Te + c2·Te², with the coefficients in block #5 [CONFIRMED: HSD guide pp. 12-13].
- The files on S3 are whole-file bzip2 (`.DAT.bz2`); the internal compression flag is 0 [MEASURED].

### 3.2 satpy `ahi_hsd`
- Reader docs: https://satpy.readthedocs.io/en/stable/api/satpy.readers.ahi_hsd.html. Options include `mask_space` (default True), `calib_mode` ('update' default, 'nominal', 'custom'), nominal versus observation times, and `round_actual_position` [CONFIRMED, accessed 2026-10-10].
- The reader YAML accepts `...S{segment:2d}{total_segments:2d}.DAT.bz2` for 2-km bands and sets `supports_fsspec: false`. `unzip_file()` decompresses `.bz2` to a temp file "Initially with pbzip2 if installed or bz2" [CONFIRMED: https://raw.githubusercontent.com/pytroll/satpy/main/satpy/etc/readers/ahi_hsd.yaml and .../satpy/readers/core/utils.py, accessed 2026-10-10]. So TEPHRA downloads the file first, then reads it locally.
- Dependencies (pyproject, main branch): numpy>=2.0, dask[array], xarray, pyresample>=1.24.0, pyproj>=2.2, pykdtree, pyorbital, trollimage, zarr, pillow, pooch, donfig, trollsift, universal_pathlib, platformdirs, packaging, pyyaml. **pyspectral is optional**, needed only for the `rayleigh` extra. **pyresample is required** [CONFIRMED: https://raw.githubusercontent.com/pytroll/satpy/main/pyproject.toml]. The latest PyPI release is satpy 0.60.0, uploaded 2026-03-04 [CONFIRMED: https://pypi.org/pypi/satpy/json]. `requires-python >=3.12` [CONFIRMED: pyproject].
- satpy's memory and time on Cloud Run were not measured; I did not install packages.

### 3.3 Without satpy (recommended for the demo)
- The HSD v1.3 tables are enough to write a reader in about 100 lines of numpy and the standard library. I wrote one in a scratch directory, using no project code, and checked it on live files:
  - B13 S0610 (1910Z): 6,051,523 bytes decompressed. **bz2 decompress 0.12 s, header parse <1 ms, count to brightness temperature 0.03 s.** B15 took 0.11 s and 0.02 s [MEASURED on this macOS laptop].
  - Peak RSS for the whole process (Python, numpy, two segments, float64 intermediates): **205 MB** [MEASURED, `/usr/bin/time -l`].
  - Sanity: B13 median 291.1 K and B15 median 286.6 K over a night-time tropical segment, both plausible [MEASURED].
- PyPI has no maintained package named `himawari`, `ahi-hsd`, `pyhimawari` or `hsd2nc`. `ahi` is an unrelated HTTP client, and `himawaripy` and `himawari8` download picture images (a desktop-wallpaper script and an image downloader) [CONFIRMED: https://pypi.org/pypi/<name>/json for each]. I could not search GitHub for a standalone numpy HSD parser (budget exhausted) [UNVERIFIED whether a good one exists].

### 3.4 Bytes per 10-minute update (1910Z sizes)
- Java/Bali, two bands (B13 + B15, S06): 2,877,933 + 2,771,942 = **5.65 MB per 10 min**, about 0.81 GB per day and 24 GB per 30 days [MEASURED].
- Java/Bali, four bands (B11, B13, B14, B15, for a three-band test and a background check): **10.8 to 11.4 MB per slot** [MEASURED].
- Add Halmahera (S05, two bands): 3,006,272 + 2,952,696 = 5.96 MB. Add Sakurajima via the full disk (S03, two bands): about 5.07 MB, or via the Japan Area at 2.5 min (two bands x four scans): about 8 MB [MEASURED].
- Measured download time from India to us-east-1 was 3 to 60 s per 3 MB file and varied a lot. From a Google Cloud region near us-east-1 it should be seconds [UNVERIFIED].

### 3.5 Cloud Run budget
- Request-based free tier per billing account per month: "180,000 vCPU-seconds", "360,000 GiB-seconds", "2 million requests". Jobs: "240,000 vCPU-seconds", "450,000 GiB-seconds" [CONFIRMED: https://cloud.google.com/run/pricing, accessed 2026-10-10].
- Estimate: one run every 10 min is 4,320 runs per month. At about 20 s wall time (mostly download) with 1 vCPU and 0.5 GiB, that is about 86,400 vCPU-s and 43,200 GiB-s, inside the free tier [UNVERIFIED arithmetic from MEASURED per-step timings].

### 3.6 Can `AHI-L2-FLDK-Clouds` estimate plume top?
- `AHI-CHGT` contains cloud-top height, temperature, pressure and emissivity, with errors and quality flags, from NOAA's "Enterprise Cloud Height Algorithm" [MEASURED from file metadata].
- It is a meteorological-cloud retrieval. It is not an ash retrieval, and it is 744 MB per full disk. NetCDF4 chunks could be byte-range read with h5netcdf and fsspec, but I did not test that. The file arrives about 18 min after scan start, later than L1b [MEASURED].
- For an opaque fresh plume, the B13 brightness temperature compared with a wind/temperature profile (TEPHRA already pulls Open-Meteo pressure-level data) gives a similar rough "top at or above X" estimate more simply. Either way it is an **estimate of the coldest cloud top near the vent**, not of ash height [UNVERIFIED]. VOLCAT's ash height comes from a dedicated optimal-estimation retrieval (Pavolonis et al. 2013) [CONFIRMED: abstract via https://api.crossref.org/works/10.1002/jgrd.50173].

---

## 4. Science

### 4.1 The method
- **Origin:** Prata (1989, GRL): for "nascent volcanic eruption clouds a reverse absorption effect is noticeable in the infrared window between 10µm and 13µm, for which absorption of infrared radiation increases with increasing wavelength. This effect may be of use in detecting hazardous volcanic clouds from space." [CONFIRMED: https://api.crossref.org/works/10.1029/GL016i011p01293]. Also Prata (1989, IJRS), "Observations of volcanic ash clouds in the 10-12 μm window using AVHRR/2 data", 10:751-761 [CONFIRMED title/citation: https://api.crossref.org/works/10.1080/01431168908903916; abstract not available].
- **Retrieval:** Wen and Rose (1994) retrieve effective particle radius, optical depth and fine-ash mass from the two bands, and note that "the mass estimate is more sensitive to the assumed ash size distribution than it is to the ash composition" [CONFIRMED: https://api.crossref.org/works/10.1029/93JD03340].
- **Rule:** ash makes T(11 um) minus T(12 um) negative; ice, water and water vapour make it positive. The classic automated test flags "a negative 11–12-μm brightness temperature difference" [CONFIRMED wording in the Pavolonis et al. 2006 abstract: https://api.crossref.org/works/10.1175/JTECH1926.1].
- **Himawari bands:** B13 10.4 um (10.4074 um central on AHI-9), B14 11.2 um (11.2080), B15 12.4 um (12.3648), B11 8.6 um [CONFIRMED: https://www.data.jma.go.jp/mscweb/en/himawari89/space_segment/spsg_ahi.html; MEASURED in block #5: 10.4074 and 12.3648]. The classic 11-12 um pair is **B14 - B15**. **B13 - B15** spans a wider gap and matches the old IR1 - IR2 pairing [UNVERIFIED inference]; note that "The Himawari-8/9 band corresponding to the MTSAT-1R/2 IR1 band was changed from 11.2 µm to 10.4 µm" [CONFIRMED: spsg_ahi page]. Compute both.
- **Thresholds in practice:** 0 K is the physical sign test. Operational analysts use stricter thresholds and corrections. Darwin VAAC (as of 2004) used ΔT* = ΔT + c for T ≥ 230 K, and ΔT* = ΔT + c + (230 − T11)/f for T < 230 K, with "f =12.5 K ... and c=0", to suppress false alarms on cold thunderstorm tops [CONFIRMED: Tupper et al. 2004 preprint p. 4, http://www.bom.gov.au/info/vaac/publications/Tupper_etal_Western_Pacific_2004.pdf]. I did not find a primary source for the common "-0.5 K / -1 K" rule [UNVERIFIED]. Treat -0.5 K as "candidate" and -1 K as "strong", and always print the local background value.
- **How the VAACs used it (2004):** "Tokyo VAAC uses 12-11 µm images stretched for contrast ... Darwin VAAC uses 11-12 µm superimposed on an 11 µm image ... to allow 'pattern analysis' on the same image." Also: "In practice, pattern analysis and reverse absorption are used together to produce operational analyses." [CONFIRMED: Tupper 2004 p. 4]. Current Tokyo VAAC pages say only that satellite imagery is an important source and show "INFO SOURCE: HIMAWARI-8" in a sample VAA. They do not describe the detection algorithm [CONFIRMED: https://www.data.jma.go.jp/vaac/data/Inquiry/vaac_operation.html and .../graphic_and_dispersion.htm].

### 4.2 Corrections and better methods
- **Water-vapour correction, Yu, Rose and Prata (2002):** "Both the mapping and the retrieval scheme are less accurate in the humid tropical atmosphere." Their scheme uses "the brightness temperature differences (BTD) to estimate the amount of BTD shift caused by lower tropospheric water vapor" [CONFIRMED: https://api.crossref.org/works/10.1029/2001JD000706]. A cheap stand-in for the demo: subtract the median clear-sky BTD in a ring around the vent before thresholding, and report the shift [UNVERIFIED design].
- **Four-channel daytime method, Pavolonis et al. (2006):** uses 0.65, 3.75, 11 and 12 um. "The greatest impact on detection sensitivity is seen in the Tropics, where water vapor can often mask the reverse absorption signal. The four-channel algorithm was able to detect volcanic clouds even when the 11–12-μm brightness temperature difference was greater than +2 K." [CONFIRMED: https://api.crossref.org/works/10.1175/JTECH1926.1]. The classic three-channel (3.9 + 11 + 12 um) test is credited to Ellrod et al. (2003) in Tupper 2004 ("3-channel techniques (Ellrod et al, 2003)") [CONFIRMED: Tupper 2004 p. 19]; I did not open Ellrod 2003. On AHI the 3.9 um band is B07.
- **Beyond BTD, Pavolonis (2010):** "BTDs are fundamentally limited"; effective-absorption optical depth ratios (β) give "significant increases in sensitivity ... especially for optically thin clouds" [CONFIRMED: https://api.crossref.org/works/10.1175/2010JAMC2433.1].
- **SECO / VOLCAT, Pavolonis et al. (2015a, b):** existing automated algorithms "either exhibit poor overall skill or can only be applied to a limited number of sensors and/or geographic regions". SECO uses a Bayesian per-pixel probability plus cloud objects "with a very low false alarm rate", day and night [CONFIRMED: https://api.crossref.org/works/10.1002/2014JD022968 and .../10.1002/2014JD022969].
- **Eruption detection without spectral ash signal, Pavolonis et al. (2018):** "The large optical depth of emergent volcanic clouds greatly limits the effectiveness of multispectral infrared-based techniques"; the Cloud Growth Anomaly method looks for clouds near volcanoes "growing rapidly in the vertical" [CONFIRMED: https://api.crossref.org/works/10.1029/2018EA000410]. For a demo, a simple "B13 at the vent dropped by more than X K in 10 to 20 min" alarm is a cheap cousin of this and is buildable [UNVERIFIED design].

### 4.3 Failure modes (with the Indonesia angle)
From Tupper et al. (2004), written by Darwin VAAC, JMA Tokyo VAAC and BoM/CSIRO authors, using GMS-5 data over the western Pacific and Indonesia [all CONFIRMED: Tupper 2004 preprint, http://www.bom.gov.au/info/vaac/publications/Tupper_etal_Western_Pacific_2004.pdf]:
- **Ice:** "The presence of substantial amounts of ice in ash cloud can partially or completely obscure the ash signal."
- **Water vapour:** "Positive absorption from high amounts of water vapor ... can obscure the ash signal."
- **Dust:** mineral dust storms "over the Australian continent and very frequently over China" can be confused with ash in IR-only analysis.
- **False alarms:** "in the presence of temperature inversions near the surface ..., in stratospheric thunderstorm cloud tops ..., and in other circumstances".
- **Opaque versus thin:** "reverse absorption requires the clouds to be semi-transparent and therefore usually in the dissipating stage". Fresh opaque columns show little or no negative BTD.
- **Small eruptions, Semeru by name:** "Many volcanoes, such as Semeru (Java, Indonesia) or Suwanosejima (Japan), have been in a state of frequent low-level eruption, but the eruptions have often fallen below satellite resolution or have been completely obscured by cloud".
- **Moist tropics:** "In the moist tropics, we would expect that entrainment of water vapor and the higher tropopause will increase the height of maximum ascent of otherwise small to moderate sized eruptions, resulting in high eruption clouds with high water vapor but relatively less ash ... and therefore a proportionally lower chance of detection". Manam (1998) and Ulawun (2001) produced clouds near the tropopause with TOMS SO2, but "no ash found with the split-window algorithm".
- **Papua New Guinea:** "If it were not for the exceptional work of the Rabaul Volcano Observatory and the equally important pilot reports ... many, if not most, eruptions would have been completely undetected." Similar conditions "are prevalent in Indonesia, the Solomon Islands and the Philippines for most of the year."
- **Headline numbers:** "Two of the six aircraft encounters described occurred in conditions where the volcanic cloud could not be clearly identified by remote sensing." Also: "No single method of observation or satellite sensor is able to identify and track volcanic clouds in every case." On the other hand, "Currently, the best method for discriminating dispersing volcanic ash clouds from water/ice clouds is the reverse absorption, or split-window technique", and they tracked one cloud for 80 hours with it.
- **Day/night:** the split-window BTD is purely thermal, so it runs day and night [UNVERIFIED general physics; SECO is described as "globally applicable (day and night)", CONFIRMED in its abstract]. Pavolonis 2006 is explicitly "A Daytime Complement" because it adds 0.65 and 3.75 um [CONFIRMED: title and abstract]. Semeru's two SIGMET times (10:05 to 11:05Z, 17:05 to 18:05 WIB) are at or after dusk, so a TEPHRA demo built on them is IR-only.
- **Not checked:** Simpson et al. (2000), "Failures in detecting volcanic ash from a satellite-based technique", RSE 72:191-217 [CONFIRMED citation: https://api.crossref.org/works/10.1016/S0034-4257(99)00103-0]. I could not read its abstract. Tupper 2004 notes that Prata et al. (2001) "criticized the methodology employed by Simpson et al. (2000), who defined a reverse absorption failure rate based on cloud identified using pattern analysis".

**Published POD/FAR numbers for BTD over Indonesia specifically: not found.** The search budget ran out before I could look for Himawari-8/9-era Indonesian validation papers. The best tropical evidence I have read is qualitative but strong (Tupper 2004; Pavolonis 2006 "+2 K"). Treat any per-pixel accuracy claim as unsupported.

### 4.4 Baselines TEPHRA should name
- **NOAA/CIMSS VOLCAT** (Volcanic Cloud Monitoring portal, SSEC, Pavolonis): sensors "GOES-EAST, GOES-WEST, MSG SEVIRI, MODIS, VIIRS, and HIMAWARI", with Himawari "via direct broadcast feeds and NASA/SSEC near real-time feed". Disclaimer: data "should be used for informational purposes only. Any use of this data for decision making processes is done at the sole risk of the end user." The site has a Login link [CONFIRMED: https://volcano.ssec.wisc.edu/ and https://volcano.ssec.wisc.edu/refs/, accessed 2026-10-10]. Whether TEPHRA can pull VOLCAT alerts programmatically was not checked.
- **JMA / Tokyo VAAC:** VAAs are "updated as a minimum at six-hour intervals (normally at 00, 06, 12 and 18 UTC) for as long as ash clouds are identified in satellite imagery". "When volcanic ash is not detected by a meteorological satellite, information to that effect is issued." [CONFIRMED: Tokyo VAAC operation and product pages]. I found no public JMA BTD or ash-detection product feed. JMA does publish the Target Area "Tropical cyclone or volcanic ash" imagery (see 2.3) and real-time sector imagery.
- **Darwin VAAC** (2004 method above). I did not open a current BoM methods page.

---

## 5. Our own check: does the raw signal see anything in Akash's cases?

Scratch script (`numpy` only, live S3 files, no project code). It reads S06 or S05 for B11, B13, B14 and B15, and takes a 200 x 200 pixel window (about 400 x 400 km) centred on the vent [all MEASURED]:

### 5.1 Semeru, 2026-09-25 (SIGMET 12 "VA CLD OBS 1100Z ... SFC/FL150 MOV SE")
- Timeline 1100Z; S06 scanned 11:05:04 to 11:06:02Z; 10.8 MB for four bands.
- B13: min 272.6 K, median 295.7 K, vent pixel 285.4 K (the high summit is colder).
- B13 - B15: min **+0.13 K**, median +3.17 K, pixels below 0 K: **0**. B14 - B15: min +0.55 K, median +2.94 K, pixels below 0 K: **0**.

### 5.2 Semeru, 2026-10-07 (SIGMET 12 "VA CLD OBS AT 1010Z ... SFC/FL150 MOV NE 05KT"; VONA 1122Z "Ash-cloud is not observed")
The SIGMET and VONA texts in 5.1 and 5.2 are as quoted in Akash's point C and the prior notes; I did not re-open them here.
- 1000Z timeline (S06 scanned 10:05:04 to 10:06:03Z): B13 - B15 min **+0.31 K**, median +3.24 K; B14 - B15 min +0.51 K; **0** negative pixels.
- 1010Z timeline (S06 scanned 10:15:04 to 10:16:03Z): B13 - B15 min **+0.20 K**, median +3.21 K; B14 - B15 min +0.40 K; **0** negative pixels. B13 min 231.7 K (some cold cloud in the box).

### 5.3 What this shows
- In both "disagreement" cases the raw signal is **silent**: the whole box has a positive background of about +3 K. That is the tropical water-vapour shift Yu et al. and Pavolonis describe.
- This does not show there was no ash. A SIGMET at SFC/FL150 for Semeru describes a low plume. Low, small, moist plumes are exactly what Tupper 2004 says the method misses at Semeru.
- So the raw layer **cannot referee** SIGMET versus VONA on these days. It can add a fact for the dispatcher: "Himawari 10:15Z: no split-window ash signal within 200 km; background +3.2 K (moist); this method often misses low Semeru plumes".

### 5.4 Tropical eruption: Ruang, 2024-04-16/17 (eruption "began at 9:45pm (13:45 GMT) on 16 April")
Eruption time per [REPORTED: https://en.wikipedia.org/wiki/Ruang]. I did not open a VAAC advisory for this event, so I cannot say how much ash was airborne in each frame. Treat this as a tropical test, not a confirmed positive. [MEASURED, S05, 200 x 200 px window, then a wider window of 402 lines x 550 columns]
- 1400Z (S05 scanned 14:04:03 to 14:05:04Z, about 20 min after onset): B13 min **212.0 K** (a very cold cloud top in the box: the eruption column and/or convection). B13 - B15 min -0.39 K and B14 - B15 min -0.42 K; **no pixel below -0.5 K**; box median B13 - B15 **+5.70 K**. In the wider window, 5 pixels were below -0.5 K and none below -1 K.
- 1600Z: B14 - B15 min +0.12 K, median +4.35 K, **no negative pixel**.
- 1900Z: B14 - B15 min -0.24 K, median +4.51 K. In the wider window, 2 pixels were below -1 K, near 6.06 N, about 420 km north: noise-level.
- 2024-04-17 0000Z: B14 - B15 min -1.37 K (one pixel), median +4.47 K. In the wider window, 2 pixels were below -1 K.
- Reading: over the Molucca Sea the background split-window difference was **+4 to +6 K** (much moister than Java's +3 K). The cold cloud in the 1400Z frame has a near-zero, not negative, difference. In the first 10 hours after a reported eruption, the 2-band method produced **no usable ash mask** in this box. This is what Tupper (2004) and Pavolonis (2006) predict for the moist tropics. It may also mean the ash was elsewhere or ice-coated, which I cannot separate without the VAAC record.

### 5.5 Dry-atmosphere positive control: Raikoke (Kurils), 2019-06-22 06:00Z
Eruption reported "At approximately 4:03 am, 22 June 2019", with plume "reaching between 13,000 m (43,000 ft) and 17,000 m (56,000 ft)" [REPORTED: https://en.wikipedia.org/wiki/Raikoke; time zone not stated]. Data: `s3://noaa-himawari8/AHI-L1b-FLDK/2019/06/22/0600/`. Note that the pre-2022 archive is **unsegmented** (`..._S0101.DAT.bz2`, about 24.6 MB per band). It is multi-stream bzip2 in roughly 900 kB blocks, so the northern lines can be decoded from an HTTP byte range of the first 8 MB [MEASURED].
- Window 500 x 500 px around the vent: B14 - B15 min **-5.24 K**, 3,331 pixels below -1 K and 5,561 below -0.5 K. B13 - B15 min -15.35 K, 6,235 pixels below -1 K. Background median +1.50 K [MEASURED].
- The rendered crop shows a coherent negative-difference plume streaming east of the vent, matching a bright cold cloud in B13 (image: `research/data/12-himawari/raikoke_20190622_0600.png`). The same code applied to Semeru and Ruang gave nothing. **The pipeline works; the tropics are the problem.**

Images (derived; JMA data via NOAA, processed in scratch, not original data): `research/data/12-himawari/semeru_20261007_1010.png`, `semeru_20260925_1100.png`, `ruang_20240416_1400.png`, `raikoke_20190622_0600.png`. Left half: B14 - B15 on a -3 K (blue) to +5 K (orange) scale; right half: B13 grey; cross marks the vent. The scratch scripts are beside them.

One more observation from the Semeru crops: the difference is lower (whiter, nearer 0 K) along Java's volcanic spine and at the vent pixel than over the sea. That is probably because there is less water vapour above high terrain [UNVERIFIED inference]. Any summit "signal" must be compared with the same pixel's clear-sky history before it is called ash.

---

## 6. Verdict and build spec

### 6.1 Is "code computes BTD, Gemini interprets it with the texts" sound and buildable by 2026-10-18?
**Yes, as an evidence layer. No, as a detector.**
- Buildable: one anonymous HTTPS GET per band per 10 min, a 100-line numpy reader, about 0.3 s of compute, inside the Cloud Run free tier. The data are live and current. Archive replays are available in the Himawari-9 bucket from 2022, and in the Himawari-8 bucket for older events such as Raikoke 2019 [MEASURED].
- Sound only if the output is one-way, consistent with TEPHRA's "may widen, never shrink" rule. A strong negative BTD cluster attached to or downwind of the vent can (a) raise urgency, (b) widen the cone where the cluster lies outside the official polygon, and (c) be quoted as "satellite corroboration". A silent BTD changes nothing except a note saying the method is blind in moist tropical air.
- Gemini's job is wording and reconciliation, not detection. Pass Gemini numbers and a picture (the heat map). Do not ask it to "find ash" in raw counts.

### 6.2 What the code must do (in order)
1. **Poll** `https://noaa-himawari9.s3.amazonaws.com/?list-type=2&prefix=AHI-L1b-FLDK/YYYY/MM/DD/HHMM/` each minute until the needed files exist. For Java: `HS_H09_<YYYYMMDD>_<HHMM>_B{13,15}_FLDK_R20_S0610.DAT.bz2` (add B14 and B11 if affordable; S0510 for Halmahera; `AHI-L1b-Japan` JP01..04 for Sakurajima).
2. **Download** anonymously (no AWS SDK credentials; plain HTTPS). Keep the actual scan time from header block #1 (start/end MJD), not just the folder name.
3. **Decompress** bzip2 in memory.
4. **Parse** blocks 1 to 11 by their stated lengths (block 10 has a 4-byte length). Read block 2 (columns, lines), block 3 (CFAC/LFAC/COFF/LOFF/sub_lon), block 5 (calibration), block 7 (first line).
5. **Calibrate**: mask counts 65535 and 65534; radiance = slope·count + intercept; inverse Planck at the block-5 wavelength; Tb = c0 + c1·Te + c2·Te².
6. **Crop**: compute the vent's line and column with the CGMS forward formula, and take ±100 to 150 px.
7. **BTD**: B13 - B15 and B14 - B15. Apply the Darwin cold-top correction for T11 < 230 K. Compute the background as the median BTD over warm (B13 > 270 K), low-variance pixels in a 100 to 200 km ring.
8. **Threshold and mask**: candidate pixels are BTD < -0.5 K; strong pixels are BTD < -1 K. Drop single pixels with a 3x3 open, keep connected components with at least N pixels, and keep only components within about 150 km of the vent or touching the official polygon.
9. **Polygonise**: trace each kept component (e.g. a convex or concave hull of pixel centres), convert to lat/lon with the inverse CGMS formula, and simplify to no more than 20 vertices.
10. **Emit** JSON: scan start/end, bands, background BTD, min BTD, candidate and strong pixel counts, component polygons, distance and bearing from the vent, overlap with and extension beyond the official polygon, and a state of `signal_present`, `no_signal_moist_background`, `obscured_by_cold_cloud` or `no_data`.
11. **Render** a PNG crop (see 6.4) and attach both to the Gemini prompt with the SIGMET, VONA and VAA texts.

### 6.3 What it must never claim
- Never "no ash" or "clear" from a silent BTD. The wording is "no split-window signal; the method often misses low or moist tropical plumes (Tupper et al. 2004)".
- Never an ash concentration, mass or height. The BTD gives none of these. A B13 cloud-top temperature is a cloud-top estimate at most.
- Never that it detects eruptions, or that it is official, VAAC-equivalent, or endorsed by JMA or NOAA.
- Never shrink, delay or override an official SIGMET or VAA polygon on the strength of BTD.
- Never present the derived image as "Himawari data" without the "processed by TEPHRA" label (NOAA licence condition).
- Never mix scan time and display time: show the actual scan time (for example "S06 scanned 10:15:04Z") so a 10 to 15 minute lag is visible.

### 6.4 How to show it on screen
- A square crop (about 400 x 400 km) of B13 - B15 in a **diverging palette centred at 0 K**: blue for negative (ash-like), neutral near 0, warm for positive (moist or ice), with a fixed scale of -3 to +5 K so frames are comparable.
- Overlay: the official SIGMET or VAA polygon as a solid outline with its FL band and VALID time; TEPHRA's widened cone as a dashed outline; flagged BTD components as a thin contour; the vent marker; live aircraft dots from ADS-B.
- Caption strip: "Himawari-9 B13-B15, scan 10:15:04Z (data: JMA via NOAA NODD; processed by TEPHRA, not original data) | background +3.2 K | 0 px < -0.5 K | state: no signal, moist background".
- Optional thumbnail: B13 brightness temperature in grey, so a judge sees the cloud scene the BTD sits on.
- In the demo, show one frame where the signal fires (archive positive case; today the only verified one is Raikoke 2019) and one live Indonesian frame where it stays silent, with the caveat. That is the honest story.

---

## Verdict on Akash's point(s)

| Point | Verdict | Why |
|---|---|---|
| B: raw Himawari 11/12 um data are freely accessible | **CONFIRMED** | Anonymous HTTPS listing and download of `s3://noaa-himawari9` work, with current files (1920Z on 2026-10-09 arriving at 19:30 to 19:33Z). Registry: "NOAA has rights to distribute this data freely and openly to the public." |
| B: legal to use in the competition | **PARTLY** | Prototype use with attribution, no implied endorsement and "modified" labelling fits the NOAA terms. Commercial use and redistribution are not settled by any JMA statement I found. JMA channels point profit use to JMBSC and forbid redistribution. |
| B: ordinary code can compute the split-window signal within a Cloud Run budget | **CONFIRMED** | One 2.8 MB segment per band covers all of Java and Bali; decompress plus calibrate takes about 0.15 s and about 205 MB per two bands; that is inside the Cloud Run free tier. |
| B: this is "the split-window method VAACs use" | **PARTLY** | Tupper et al. 2004 confirm Tokyo and Darwin VAACs used 11-12 um reverse absorption, always alongside pattern analysis and with corrections. Current JMA pages do not describe their algorithm, and NOAA's own operational approach (VOLCAT/SECO) moved beyond plain BTD. |
| B: Gemini can interpret the result next to the texts and add value | **PARTLY** | It is sound as a one-way corroboration layer. On both of Akash's disagreement cases the raw signal was silent (min BTD +0.13 to +0.31 K), and it stayed silent after the 2024 Ruang eruption. It fired strongly for Raikoke 2019 (dry air). So it cannot referee the Indonesian disputes and must never be read as "no ash". |
| C (bearing only): the 2026-09-25 and 2026-10-07 disagreements are real | **UNRESOLVED by satellite** | The raw Himawari split-window shows no ash signal on either date at Semeru. That neither supports the VONA ("not observed") nor refutes the SIGMET ("OBS"), because the method is known to miss low, moist Semeru plumes. |
| A: TEPHRA is a decision layer after detection | **PARTLY** (only the part point B can test) | The raw-data test supports this framing. TEPHRA is not a better detector than the VAAC (it saw nothing where the MWO's SIGMET reported ash), and the raw layer is evidence for the decision, not a replacement for detection. The flight-impact and cost parts of A are outside this note. |

## Open questions
1. Does JMA, JMBSC or NOAA have a written position on **commercial** use of the NOAA-distributed Himawari copy? Ask nodd@noaa.gov and JMBSC before any paid pilot.
2. Was there detectable airborne ash near Ruang on 2024-04-16/17 in the frames tested (5.4)? Pull the Darwin VAAC advisories for those times before using Ruang as a demo case. Also find a **tropical** positive control where BTD does fire (candidates to check: Lewotobi Laki-laki Nov 2024 or July 2025; Kanlaon 2024-2025; Taal 2020). Without one, the demo's "signal present" frame has to be Raikoke (dry, Kurils).
3. Published POD/FAR of BTD (or VOLCAT) over Indonesia with Himawari-8/9: not searched (budget exhausted). Queries to run: "Himawari-8 volcanic ash detection Indonesia validation", "VOLCAT Himawari false alarm rate Indonesia", "Semeru ash Himawari split window".
4. Current Darwin VAAC and Tokyo VAAC detection practice (Ash RGB, VOLCAT, their own BTD tools): not opened. Queries: "Darwin VAAC Himawari ash RGB operations", "Tokyo VAAC volcanic ash detection Himawari-8 algorithm".
5. Does a maintained pure-numpy HSD reader exist on GitHub? Not searched. A home-grown 100-line reader is proven to work, so this is low priority.
6. Can VOLCAT alerts be pulled programmatically and legally (the site has a Login link)?
7. Can the 744 MB `AHI-CHGT` be byte-range read for a Java crop (HDF5 chunking), and is its height useful over fresh plumes? Untested.
8. Download time from a Cloud Run region to us-east-1 (expected seconds) was not measured; my laptop in India saw 3 to 60 s per file.

## Sources
- AWS Registry, JMA Himawari-8/9: https://registry.opendata.aws/noaa-himawari/ [CONFIRMED, accessed 2026-10-10]
- Bucket listings (anonymous): https://noaa-himawari9.s3.amazonaws.com/?list-type=2&delimiter=/ and prefix listings for each product, 2026-10-09 19:32-19:50Z [MEASURED]
- JMA HSD User's Guide v1.3 (3 July 2017): https://www.data.jma.go.jp/mscweb/en/himawari89/space_segment/hsd_sample/HS_D_users_guide_en_v13.pdf (downloaded from the identical copy at https://www.data.jma.go.jp/mscweb/en/himawari89/space_segment/fig/HS_D_users_guide_en_v13.pdf) [CONFIRMED]
- JMA AHI specification page: https://www.data.jma.go.jp/mscweb/en/himawari89/space_segment/spsg_ahi.html [CONFIRMED]
- JMA HimawariCloud page: https://www.data.jma.go.jp/mscweb/en/himawari89/cloud_service/cloud_service.html [CONFIRMED]
- JMA dissemination outline: https://www.jma.go.jp/jma/jma-eng/satellite/dissemination.html [CONFIRMED via WebFetch summary]
- JMA distribution plan (2014): https://www.jma.go.jp/jma/jma-eng/satellite/news/himawari89/himawari89_distribution_plan.html [CONFIRMED; no licence terms on the page]
- JMA website terms: https://www.jma.go.jp/jma/en/copyright.html [CONFIRMED]
- JAXA P-Tree registration page: https://www.eorc.jaxa.jp/ptree/registration_top.html [CONFIRMED]
- JMA real-time imagery and Target Area: https://www.data.jma.go.jp/mscweb/data/himawari/index.html, https://www.data.jma.go.jp/mscweb/data/himawari/obs_info_tg_en.html, CSVs at https://www.data.jma.go.jp/mscweb/data/himawari/csv/tg/TG_OBS_POS_YYYYMM.csv [CONFIRMED / MEASURED]
- Tokyo VAAC operation and product pages: https://www.data.jma.go.jp/vaac/data/Inquiry/vaac_operation.html, https://www.data.jma.go.jp/vaac/data/Inquiry/graphic_and_dispersion.htm [CONFIRMED]
- NOAA story on Himawari on AWS (2020): https://www.noaa.gov/information-technology/stories/himawari-8-enabling-access-to-key-weather-data [CONFIRMED; no licence detail]
- satpy ahi_hsd docs: https://satpy.readthedocs.io/en/stable/api/satpy.readers.ahi_hsd.html; pyproject: https://raw.githubusercontent.com/pytroll/satpy/main/pyproject.toml; reader YAML: https://raw.githubusercontent.com/pytroll/satpy/main/satpy/etc/readers/ahi_hsd.yaml; utils: https://raw.githubusercontent.com/pytroll/satpy/main/satpy/readers/core/utils.py; PyPI: https://pypi.org/pypi/satpy/json [CONFIRMED]
- Cloud Run pricing: https://cloud.google.com/run/pricing [CONFIRMED]
- Tupper, Carn, Davey, Kamada, Potts, Prata, Tokuno (2004), RSE 91:27-46, doi:10.1016/j.rse.2004.02.004; open preprint http://www.bom.gov.au/info/vaac/publications/Tupper_etal_Western_Pacific_2004.pdf [CONFIRMED, read in full for the sections quoted]
- Prata (1989) GRL 16:1293-1296: https://api.crossref.org/works/10.1029/GL016i011p01293 [CONFIRMED abstract]
- Prata (1989) IJRS 10:751-761: https://api.crossref.org/works/10.1080/01431168908903916 [CONFIRMED citation only]
- Wen and Rose (1994) JGR 99:5421-5431: https://api.crossref.org/works/10.1029/93JD03340 [CONFIRMED abstract]
- Yu, Rose, Prata (2002) JGR 107(D16): https://api.crossref.org/works/10.1029/2001JD000706 [CONFIRMED abstract]
- Pavolonis, Feltz, Heidinger, Gallina (2006) JTECH 23:1422-1444: https://api.crossref.org/works/10.1175/JTECH1926.1 [CONFIRMED abstract]
- Pavolonis (2010) JAMC 49:1992-2012: https://api.crossref.org/works/10.1175/2010JAMC2433.1 [CONFIRMED abstract]
- Pavolonis, Heidinger, Sieglaff (2013) JGR 118:1436-1458: https://api.crossref.org/works/10.1002/jgrd.50173 [CONFIRMED abstract]
- Pavolonis, Sieglaff, Cintineo (2015a, b) JGR: https://api.crossref.org/works/10.1002/2014JD022968, https://api.crossref.org/works/10.1002/2014JD022969 [CONFIRMED abstracts]
- Pavolonis, Sieglaff, Cintineo (2018) ESS 5:903-928: https://api.crossref.org/works/10.1029/2018EA000410 [CONFIRMED abstract]
- Simpson et al. (2000) RSE 72:191-217: https://api.crossref.org/works/10.1016/S0034-4257(99)00103-0 [CONFIRMED citation only]
- NOAA/CIMSS Volcanic Cloud Monitoring (VOLCAT): https://volcano.ssec.wisc.edu/ and https://volcano.ssec.wisc.edu/refs/ [CONFIRMED]
- Ruang eruption time: https://en.wikipedia.org/wiki/Ruang [REPORTED]
- Raikoke 2019 eruption: https://en.wikipedia.org/wiki/Raikoke [REPORTED]; Himawari-8 archive files https://noaa-himawari8.s3.amazonaws.com/AHI-L1b-FLDK/2019/06/22/0600/HS_H08_20190622_0600_B1{3,4,5}_FLDK_R20_S0101.DAT.bz2 [MEASURED, byte-range read]
- Himawari-9 case files used: https://noaa-himawari9.s3.amazonaws.com/AHI-L1b-FLDK/{2026/09/25/1100, 2026/10/07/1000, 2026/10/07/1010}/..._B{11,13,14,15}_FLDK_R20_S0610.DAT.bz2 and {2024/04/16/1400, 1600, 1900, 2024/04/17/0000}/..._S0510.DAT.bz2 [MEASURED]
- Semantic Scholar lookups (used only to find the open Tupper preprint): https://api.semanticscholar.org/graph/v1/paper/DOI:10.1016/j.rse.2004.02.004

## Search log
- WebSearch (extended): "JMA Himawari Standard Data terms of use third party distribution NOAA AWS commercial use". Found the JMA dissemination page, P-Tree, DIAS and the registry; the DIAS policy text came only via the search summary and was not opened (do not rely on it).
- WebSearch (standard): "NOAA JMA agreement Himawari data redistribute 'freely and openly' NODD Himawari-9 AWS announcement". No agreement text found.
- WebSearch (standard): "Himawari Standard Data User's Guide HS_D_users_guide_en pdf segment 10 divided full disk". Found the guide.
- WebSearch (extended): "github python Himawari Standard Data HSD reader numpy brightness temperature 'HS_H09' -satpy". **Not run: the session web-search budget (200 shared calls) was exhausted.** No further searches were possible; everything after this point came from direct URL fetches, DOI lookups and bucket listings.
- Direct fetches that failed: https://www.data.jma.go.jp/mscweb/en/VRL/VLab_RGB/RGBimage.html (404); https://volcano.si.edu/volcano.cfm?vn=267010 (403); https://www.data.jma.go.jp/mscweb/en/product/index.html and product_list.html (404); AMS PDF for Tupper et al. 2007 (returned HTML, not read).
- PyPI name checks: himawari, ahi, himawari-python, pyhimawari, himawaripy, hsd2nc, himawari8, ahi-hsd.
