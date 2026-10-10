# feeds-text fixtures

Real responses saved byte for byte, in the same spirit as `../README.md`: do not refresh
them in place. Live copies were fetched on 2026-10-10 with a `TEPHRA/0.1` User-Agent, one
GET each. The `isigmet_va_2026MMDD_HHMM.json` files are copies of the research census
snapshots (`research/data/census/raw/sigmet/`, fetched 2026-10-09 with AWC's `date=`
parameter; URLs and fetch times in `research/data/census/manifest.tsv`).

| File | Source | Fetched (UTC) | sha256 | Shows |
|---|---|---|---|---|
| `tgftp_fvau05_lewotolok_2026-322.txt` | `https://tgftp.nws.noaa.gov/data/raw/fv/fvau05.adrm..txt` | 2026-10-10 04:57:41 (Last-Modified 09 Oct 23:10:54) | `f38ac1683fdf2c9b9b093c03cb056649176d4cba41879623e3d8be36c5e522c2` | Lewotolok 2026/322, current until 06:10Z; the slot the poller missed |
| `tgftp_fvau08_status_test.txt` | `https://tgftp.nws.noaa.gov/data/raw/fv/fvau08.adrm..txt` | 2026-10-10 04:57:44 (Last-Modified 06 Oct 01:06:10) | `a9ee0a5fe44bae31c20d0012fdce73fc65c885505418c194944746ce10e69ebd` | `STATUS: TEST`, `VOLCANO: TEST 999999`, issued by Wellington for Darwin |
| `isigmet_va_20261010T0500Z.json` | `https://aviationweather.gov/api/data/isigmet?format=json&hazard=va` | 2026-10-10 05:00:50 | `83dac22fa66dc95afebe82107d3509c687c4a689ac8b7ac2f0bde1fafdd151c5` | WAAF 15 Lewotolok; vertices on the PSN (Sangay, Reventador, Masaya); RPHI 1 Kanlaon with no area, where AWC's `coords` are its own 50 NM circle |
| `taf_20261010T0504Z.json` | `https://aviationweather.gov/api/data/taf?ids=CYYT,EGLL,EHAM,KSFO,RJFK,RPLL,WAAA,WADD,WARR,WIII,WSSS,WILL,RJFF&format=json` | 2026-10-10 05:04:40 | `32316ed925c7f6f81bf2954c1c511dadb9c80ddd3a53a25ee4ec7cf6a6f7a616` | BECMG groups with `timeBec` (RJFF, EHAM, WAAA, WIII, WARR) |
| `isigmet_va_20260916_2000.json` | census, `date=20260916_2000` | 2026-10-09 19:47:56 | `9463455aacf5f0fbf494d017f1289833c445332fda8c2b6ea493faf38ac040cc` | RJJJ M01 Sakurajima `ABV FL080`, no JSON levels |
| `isigmet_va_20260921_0000.json` | census, `date=20260921_0000` | 2026-10-09 19:52:31 | `f2e7ec16534ed1e37153beb9310c74f06e12605ccf4832aafcc06a235c831efd` | SPIM 2 `VA NOT IDENTIFIABLE FM STLT DATA` |
| `isigmet_va_20260924_1300.json` | census, `date=20260924_1300` | 2026-10-09 19:56:33 | `d415761f62b70c43ec14dc2e6cd34c5d084e757f582488d2ed55e9fb2e57c95f` | RJJJ V03 `FIR MT SAKURAJIMA (AIRA CALDERA) PSN`, no `VA` token, no qualifier |
| `isigmet_va_20260925_0300.json` | census, `date=20260925_0300` | 2026-10-09 19:57:11 | `219b922f6fc4c4f7e95e053274c5c19f2b4e147fab37bfa27dabb18a43c66edc` | RJJJ Y02 Sakurajima: two clouds, each observed and forecast; AWC keeps the first |
| `isigmet_va_20260926_0800.json` | census, `date=20260926_0800` | 2026-10-09 19:58:27 | `ff4b15c9058bdd4dcf6150b5b6661a80ac2ffa5022e9a4e1803bddbb7a5b0bad` | WAAF 05 Dukono: SFC/FL070 MOV NE `AND` SFC/FL150 MOV W; AWC keeps the first |
| `isigmet_va_20260929_1300.json` | census, `date=20260929_1300` | 2026-10-09 20:02:42 | `d06f386518521379a6785c60cfd1e90880edab4f2e09fe4b94a6c1224fb90f07` | WIIF 06 `FIR MT MARAPI PSN`, no `VA` token, no qualifier |
