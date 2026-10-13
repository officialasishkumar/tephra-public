# Data licences: checklist before the repo goes public

Prepared 2026-10-10. The inventory was taken between 06:56Z and 07:20Z. Other agents were adding files at the time, so run the checks in section 6 again just before publishing. This is a checklist, not legal advice. **Nothing has been removed, moved or rewritten. Every action below is for the user to take or approve.**

Why it matters:
- TEPHRA's own code and text are MIT (`LICENSE`). Third-party data keep their own terms, and the MIT licence does not cover them.

Sources for every licence quoted here are in `research/17-data-sources.md` (data) and `tephra/web/THIRD_PARTY.md` (browser assets, fonts, icons). The video and deck rules are in `docs/PITCH.md`.

Legend:
- **RED**: do not publish (remove, replace, or keep private).
- **AMBER**: publish only with the stated notice or change.
- **GREEN**: publish as is (a credit is still good practice).

---

## 1. Summary

| | What | Where | Count |
|---|---|---|---|
| RED | BoM FTP Darwin VAA texts. BoM's terms: "you may not supply that material to any other person". Each file ends with a BoM copyright notice | census; Semeru replay | 588 + 2 (census and its re-check), 73 (replay) |
| RED | BoM website pages and BoM's JSON endpoint | census; `tests/fixtures/darwin_vaac/` | 4 + 2 listings; 3 |
| RED | MAGMA pages: "Copyright 2026 © All Rights Reserved. MAGMA Indonesia", no licence, robots.txt `Disallow: /`. The list pages name the observatory staff member behind each VONA | census; `tests/fixtures/magma/`; Semeru replay | 25 + 3; 7; 23 |
| RED | One observatory staff name quoted in a research file | `research/05-feeds-verified.md`, line 114 (§3.3) | 1 line |
| RED (recommended) | NICT Himawari tiles: "This web application and data included are not allowed for commercial uses" | `tests/fixtures/himawari/`; Java live replay | 5; 57 so far |
| AMBER | adsb.lol data: ODbL 1.0 (attribution and share-alike). The fixtures keep airline registrations | fixtures; Java live replay | 3; 241 so far |
| AMBER | Open-Meteo responses: CC BY 4.0 with a required link; the free API is non-commercial | fixtures; Java live replay | 2; 11 |
| AMBER | Darwin and Wellington VAAs as relayed by NWS tgftp (no BoM footer); credit the originator | fixtures; Java live replay | 2; 138 |
| AMBER | Derived census tables that carry short third-party text columns | `research/data/census/out/` (`vaas.csv`, `vonas.csv`) | 2 files |
| GREEN | AWC and NWS products, NOAA listings, JMA content (with credit), OurAirports, Natural Earth, AWC GIS, the GVP catalogue (cited), IBM Plex (OFL), icons (with notices), our own code and text | everywhere else | — |
| — | **Git history already holds RED files.** The private GitHub repo has 4 pushed commits. The BoM texts and pages, the MAGMA pages and the NICT tiles went in with `3916eb2`, `50653e4` and `99bf879` | `origin/main` = `99bf879` | — |

**Recommendation:** publish a **fresh public repository**, seeded with a filtered copy of the history that never contains the RED files, and keep the current repository private as the team archive. The reasons and steps are in section 4.

---

## 2. Inventory of third-party files in the repo

"Committed" means the file is already in a pushed commit. Untracked files will become a problem only if they are committed.

### 2.1 `research/data/**` (committed)

| Path | What | Files | Licence | Status | Action |
|---|---|---|---|---|---|
| `census/raw/darwin/ftp/IDY41*.txt` | Darwin VAAs from BoM's anonymous FTP | 588 | "you may download, use and copy that material for personal use, or use within your organisation but you may not supply that material to any other person or use it for any commercial purpose. Users intending to publish Bureau data should do so as Registered Users." (bom.gov.au/catalogue/anon-ftp.shtml) | RED | Remove; keep a private copy, because `census.py` needs these files to re-run |
| `census/raw/darwin/bom_darwin_va_advisory.html`, `bom_IDD41270.html`, `bom_vaac_index.html`, `bom_volc_ash_recent.html` | BoM website pages | 4 | BoM copyright: no supply to others; "we do not allow you to use automated or manual techniques to hack, scrape or otherwise extract material from our site" | RED | Remove |
| `census/raw/darwin/ftp_2026_listing.txt`, `census/raw/recheck/bom_ftp_2026_listing_recheck.txt` | BoM FTP directory listings (names, sizes, dates) | 2 | BoM FTP | RED (low risk, not needed) | Remove |
| `census/raw/recheck/IDY41295.*.txt` | BoM FTP texts | 2 | As above | RED | Remove |
| `census/raw/magma/vona_p001.html` … `vona_p022.html` | MAGMA VONA list pages; each entry names its sender | 22 | "Copyright 2026 © All Rights Reserved. MAGMA Indonesia"; robots.txt `Disallow: /` | RED | Remove |
| `census/raw/magma/detail/*.html` | MAGMA VONA detail pages (office contacts only) | 3 | As above | RED | Remove |
| `census/raw/recheck/magma_vona_p001_recheck.html`, `vona_22811.html`, `vona_22827.html` | MAGMA pages (the list page names staff) | 3 | As above | RED | Remove |
| `census/raw/sigmet/*.json`, `census/raw/recheck/awc_isigmet_*.json` | aviationweather.gov SIGMET JSON | 764 + 2 | NWS: "in the public domain, unless specifically noted otherwise" | GREEN | Keep; credit AWC |
| `census/raw/tokyo/vaac_list.html`, `census/raw/tokyo/text/*.html`, `census/raw/recheck/jma_vaac_list_recheck.html`, `census/raw/recheck/20260921_27303000_0794_Text.html` | Tokyo VAAC list and advisory texts (JMA) | 1 + 153 + 2 | JMA Public Data License 1.0, "compatible with the Creative Commons Attribution License 4.0"; "The user must cite the source" | GREEN | Keep; credit "Source: Japan Meteorological Agency (Tokyo VAAC) website" |
| `census/raw/darwin/vaac_darwin_list.html`, `census/raw/darwin/jma_backup/*.html` | JMA-hosted Darwin backup list and texts | 1 + 3 | JMA PDL 1.0 | GREEN | Keep; credit JMA |
| `census/raw/darwin/wayback_cdx_volc_ash_recent.json` | An empty Wayback answer (`[]`) | 1 | — | GREEN | Keep |
| `census/manifest.tsv` | Our fetch log, with URLs and hashes, including MAGMA and BoM paths | 1 | Ours | GREEN | Keep. Note that the BoM and MAGMA rows point to files kept privately |
| `census/census.py` | Our parser | 1 | MIT | GREEN | — |
| `census/out/sigmets.csv` | Derived table; the `raw` column is AWC text | 1 | Public domain source | GREEN | — |
| `census/out/vaas.csv` | Derived table; the `eruption_details` column quotes a line of each Darwin VAA (from BoM's FTP copies) | 1 | BoM-authored text, also relayed publicly by NWS | AMBER | Keep, crediting the Darwin VAAC. To be conservative, drop the free-text column |
| `census/out/vonas.csv` | Derived table; its `text` column holds MAGMA's VONA sentences (no names) | 1 | MAGMA, all rights reserved | AMBER | Keep, crediting PVMBG, or drop the `text` column. The counts in research/14 do not depend on it |
| `census/out/vona_vs_official.csv` | Derived table; only `vona_dir_text` (direction words such as "north") comes from MAGMA | 1 | Facts | GREEN | Credit PVMBG in the census notes |
| `census/out/summary.json`, `per_volcano_table.md`, `run_stdout.txt` | Our derived numbers and run log | 3 | Ours | GREEN | — |
| `12-himawari/*.png` | BTD images TEPHRA computed from Himawari-8/9 HSD | 4 | NOAA/JMA: "NOAA and JMA request attribution … it is not permissible to state or imply endorsement" | GREEN | Caption: "Himawari data: JMA via NOAA; processed by TEPHRA, not original JMA data" |
| `12-himawari/*.py` | Our probe scripts | 4 | MIT | GREEN | — |

### 2.2 `research/*.md` and `research/prior/` (committed)

| Path | Issue | Status | Action |
|---|---|---|---|
| `research/05-feeds-verified.md`, line 114 (§3.3) | Quotes a MAGMA list entry with the observatory staff member's name | RED (that line) | Replace the name with "(observer name omitted)". `research/` is read-only for agents, so the user makes or approves this edit |
| `research/*.md` (all) | Short quotations from BoM, MAGMA, JMA, ICAO, news and terms pages, each with its source | AMBER (low) | Keep: short quotations for commentary, with sources |
| `research/prior/*` (6 files) | Team material copied from the two idea-board repositories (Akash's pages and specs, the board pack) | GREEN if both authors agree | Confirm with Akash before publishing |

### 2.3 `tests/fixtures/**`

| Folder | Files | Source and licence | Status | Action and owner |
|---|---|---|---|---|
| `adsb/` | 3 (committed) | adsb.lol point API, ODbL 1.0. The files keep `r` (registrations); all are airline aircraft | AMBER | Keep, with an ODbL notice (section 5, step 5). The app itself never keeps `r` |
| `aws_himawari/` | 1 (committed) | NOAA S3 listing XML | GREEN | — |
| `darwin_vaac/20260923_*_Text.html`, `vaac_darwin_list.html` | 3 (committed) | JMA PDL 1.0 | GREEN | Credit JMA |
| `darwin_vaac/bom_darwin_va_advisory.html`, `bom_volc_ash_recent.html` | 2 (committed) | BoM website. The second holds seven days of advisories from all nine VAACs | RED | Remove. feeds-text: change `tests/test_feeds_text.py` to use tgftp relay text, or skip when the file is absent. TEPHRA never reads BoM's site |
| `darwin_vaac/bom_process_volcanic-ash-darwin.json` | 1 (committed) | BoM's XHR endpoint, fetched by POST | RED | Remove (same owner) |
| `feeds_text/` | 7 SIGMET and 1 TAF JSON, 2 tgftp texts, README (untracked) | AWC: public domain. tgftp: NWS relay of Darwin VAAC (BoM) and Wellington VAAC text | GREEN / AMBER (low) | Credit the originating VAAC for the two tgftp texts |
| `himawari/jma_*` | 4 (committed) | JMA MSC images and the slot page, JMA PDL 1.0 | GREEN | Credit "Source: JMA Meteorological Satellite Center" |
| `himawari/nict_*` | 5 (committed) | NICT: "This web application and data included are not allowed for commercial uses." A public repo invites reuse that these terms forbid | RED (recommended) | Remove. feeds-geo: synthetic PNGs of the same size and shape for `tests/test_feeds_geo.py` and `tests/test_pipeline.py` |
| `jma/` | 6 XML files saved byte for byte (an Atom feed and five JMAXML reports) | JMA Public Data License 1.0; credit "Source: Japan Meteorological Agency website" | GREEN | Credit JMA; the README says TEPHRA parses, not edits, them |
| `notices/` | 4 synthetic notices (Indonesian, Filipino, Japanese) | Ours, written for the tests; no real MAGMA or PHIVOLCS text | GREEN | — |
| `isigmet/` | 2 (committed) | AWC, public domain | GREEN | — |
| `magma/vona_22880_semeru_ash.html`, `vona_22881_ibu_ash.html`, `vona_22889_semeru_no_ash.html` | 3 (committed) | MAGMA detail pages, all rights reserved | RED | Remove |
| `magma/vona_list.html`, `vona_list_p010_20261009.html` … `p012` | 1 committed, 3 untracked | MAGMA list pages that name staff | RED | Remove. feeds-text: synthetic pages in MAGMA's structure, with invented content and observer names such as "Observer A", for `tests/test_feeds_text.py`, `tests/test_vona_archive.py` and `tests/test_pipeline.py` |
| `openmeteo/`, `ops_evals/` | 1 committed, 1 untracked | Open-Meteo forecast and historical JSON. CC BY 4.0: "You must include a link next to any location Open-Meteo data are displayed"; the free API is non-commercial | AMBER | Keep, with "Weather data by Open-Meteo.com" in the fixture READMEs |
| `tokyo_vaac/` | 4 (committed) | JMA PDL 1.0 | GREEN | Credit JMA |
| `wx/` | 2 (committed) | AWC TAF and METAR JSON, public domain | GREEN | — |
| `README.md`, `FORMATS.md` | 2 (committed) | Ours; they describe third-party formats with short samples | GREEN | Update them after the removals |

### 2.4 `data/*.json` (committed)

| File | Source | Licence | Status |
|---|---|---|---|
| `airports.json` | OurAirports (positions, elevations, runways), checked against aviationweather.gov | "All data is released to the Public Domain" (ourairports.com/data) | GREEN |
| `volcanoes.json` | Smithsonian GVP Volcanoes of the World (WFS). MAGMA volcano codes are taken from VONA notice numbers (facts only) | The GVP database compilation is a work of US government employees; Smithsonian's site terms say "personal, educational, and other non-commercial purposes" | GREEN for the entry. Cite "Global Volcanism Program, 2025. Volcanoes of the World (v. 5.3.x), https://doi.org/10.5479/si.GVP.VOTW5-2025.5.3". Recheck the terms for a commercial product |
| `routes_apac.json` | VRS standing data `routes.csv.gz` and `airports.csv.gz` (vradarserver/standing-data, via vrs-standing-data.adsb.lol), fetched 2026-10-11; the file header holds both URLs, SHA-256 values and the licence. Crowd-sourced callsign-to-airport chains and chain-airport positions | CC0-1.0 | GREEN |
| `rfa/*.json` | Our own synthetic fleet, crews and schedule (fixed seed, built by `scripts/build_rfa_schedule.py`) on real airport pairs from `routes_apac.json` | MIT, fictional | GREEN |
| `policy/policy_a.json` | Our own illustrative operator policy; quotes Doc 9974 and PM 89/2015 text with references | MIT; short quotations | GREEN |

### 2.5 `data/replay/**` (untracked; also shipped in the Docker image)

`.dockerignore` keeps `data/replay/<case>/raw` in the image, so the public Cloud Run demo serves these files in REPLAY mode. The same rules therefore apply to the image.

| Case and folder | Files at 07:17Z | Source | Status | Action |
|---|---|---|---|---|
| `semeru-20260923/raw/sigmet/` | 91 | AWC `date=` snapshots (from the census) | GREEN | — |
| `semeru-20260923/raw/vaac_darwin/` | 102 | **Rebuilt on 10 Oct from IEM's NOAAPort archive** (the FVAU relay, public domain; no BoM files or footers). The recorder refuses BoM material (`tests/test_record_replay.py::test_bom_ftp_material_is_never_stored`) | GREEN | Credit the Darwin VAAC as originator |
| `semeru-20260923/raw/vona/` | 23 | MAGMA list pages (from the census); they name staff | RED | Choose one. (a) Pages rebuilt from VONA facts only (time, volcano, colour code, height in metres, direction, ash observed, notice number), with no names and the manifest labelled "reconstructed from PVMBG VONAs". (b) Ask PVMBG for permission. (c) Drop VONAs from the public case and show the disagreement from the census tables. Option (a) needs the core or ops owner, because `fetch_vonas` parses MAGMA HTML |
| `semeru-20260923/manifest.json` | 1 | Ours | GREEN | Regenerate after the swaps |
| `java-live-20261010/raw/adsb/` | 241 (still recording) | adsb.lol, ODbL 1.0. The files keep `r` (registrations) and `dbFlags`, and include business jets, military, police and light aircraft | AMBER | ODbL notice. Derived replay files stay ODbL. `scripts/scrub_adsb.py` drops every target that is not an airline callsign by the app's rule or is flagged military, and strips `r` and `dbFlags` from the rest (it keeps `t`). A person runs it (dry run first, then `--write`) and commits the result. The originals stay in git history, so the published history needs the FEED-05 filter as well (a user step) |
| `java-live-20261010/raw/frames/` | 8 html and 16 jpg | JMA MSC slot page and images, PDL 1.0 | GREEN | Credit JMA |
| `java-live-20261010/raw/frames/` | 9 json and 48 png | **NICT** `latest.json` and true-colour tiles | RED (recommended) | Exclude them from the published case, and note the exclusion in its manifest |
| `java-live-20261010/raw/metar/`, `taf/`, `sigmet/` | 6, 6, 47 | AWC, public domain | GREEN | — |
| `java-live-20261010/raw/vaac_darwin/` | 138 txt and 14 html | NWS tgftp relay (no BoM footer) and the JMA backup list | AMBER (low) / GREEN | Credit the Darwin VAAC and JMA |
| `java-live-20261010/raw/vaac_tokyo/` | 15 | JMA PDL 1.0 | GREEN | Credit JMA |
| `java-live-20261010/raw/winds/` | 11 | Open-Meteo, CC BY 4.0 | AMBER | Credit "Weather data by Open-Meteo.com" |
| `java-live-20261010/manifest.json` | none yet | Ours | — | Check it once recording ends |

### 2.6 `tephra/web/**` (untracked)

| Path | Source | Licence | Status |
|---|---|---|---|
| `data/firs.geojson`, `data/vaac_aor.geojson` | NOAA/NWS AWC `firpoly.topojson` and `vaac.json`. These replaced a VATSIM-derived CC BY-SA file on 10 Oct | Public domain | GREEN |
| `data/land_apac.geojson` | Natural Earth 1:50m | Public domain | GREEN |
| `data/navaids.geojson` | OurAirports | Public domain | GREEN |
| `fonts/*.woff2` and `fonts/OFL.txt` | IBM Plex Sans and Plex Mono | SIL Open Font License 1.1 (the text is shipped) | GREEN |
| `icons.svg` | Lucide 1.54.0 (ISC; Feather-derived icons MIT), Material Symbols "flight" (Apache-2.0), Maki "airport" (CC0), and symbols drawn for TEPHRA | As listed | GREEN, with the notices in `tephra/web/THIRD_PARTY.md` (present) |
| `THIRD_PARTY.md` | The UI builders' list of browser assets and services | Ours | GREEN. Keep it and this file consistent |

### 2.7 `evals/**`

| Path | Status | Action |
|---|---|---|
| `evals/plume/README.md` (committed) | GREEN | — |
| Case frames written by `scripts/make_plume_cases.py` (Tokyo VAAC Ash RGB and IR frames, Open-Meteo winds); none present at 07:17Z | AMBER | Credit JMA, and say "cropped by TEPHRA" if cropped (PDL 1.0 asks for an edit notice). Credit Open-Meteo |
| `evals/plume/arm_t/vona.txt` (MAGMA VONA text pasted by hand, per the README); not present yet | RED | Add it to `.gitignore` (ops-evals), or commit only the facts in our own words |
| `evals/plume/results/raw/` (model responses); not present yet | GREEN | Our outputs |

### 2.8 Other files

| Path | What | Action |
|---|---|---|
| `emis3.json` (repo root, untracked) | A stray GVP WFS error response from a probe; not ignored by `.gitignore` | Delete it |
| `.state/` | Runtime cache of fetched feeds (it can hold NICT, JMA, adsb.lol and, if polled, MAGMA responses) | Ignored by `.gitignore`. Make sure it is never force-added |
| `.hypothesis/` | Test cache | Ignored (it has its own `.gitignore`) |

---

## 3. Runtime services and their attribution text

These are the services TEPHRA calls at runtime or uses to build replays, and the credit each needs. `tephra/web/THIRD_PARTY.md` says where the browser shows each credit; keep the two lists in step.

| Service | Used for | Terms in short | Attribution text |
|---|---|---|---|
| aviationweather.gov (NOAA/NWS AWC) | VA SIGMETs, TAFs, METARs; FIR and VAAC outlines | Public domain; at most 100 requests a minute; custom User-Agent | "SIGMET · AWC" on cards; "FIR and VAAC lines: NOAA/NWS AWC (approximate)" on the map |
| NWS tgftp | Darwin VAAs (FVAU slots) | NWS public-domain notice; the content is BoM's | "Darwin VAAC (Bureau of Meteorology), via NOAA/NWS" on the VAA card |
| JMA Tokyo VAAC (`ds.data.jma.go.jp`) | Tokyo VAAs; the Darwin backup list | JMA PDL 1.0: cite the source; say when edited | "Source: Japan Meteorological Agency (Tokyo VAAC) website" |
| JMA MSC real-time images | Context frames | JMA PDL 1.0 | "Source: JMA Meteorological Satellite Center (<area> image); cropped by TEPHRA". The captions already carry this, per the feeds-geo review |
| NICT Himawari real-time | True-colour frames, which are also sent to Gemini | "not allowed for commercial uses" | "Himawari-9 true colour: NICT (non-commercial use only)". Better: replace with JMA, GIBS or AWS-derived images |
| NOAA Himawari-9 (NODD), read from Google Cloud Storage (the same bucket is also on AWS) | HSD segments for the split-window BTD | Attribution; "not permissible to state or imply endorsement"; label derived data | "Himawari-9 data: JMA, distributed by NOAA (NODD); read from Google Cloud Storage; processed by TEPHRA, not original JMA data" |
| adsb.lol point API | Aircraft positions | ODbL 1.0; the API asks production users to get in touch | "Aircraft: adsb.lol (ODbL 1.0)" in the map attribution |
| Open-Meteo (forecast; historical for replays and evals) | Winds by flight level | CC BY 4.0, with a link required; the free API is non-commercial | "Weather data by Open-Meteo.com", as a link next to any wind value or layer |
| MAGMA Indonesia (off unless `TEPHRA_VONA_LIVE=true`) | VONAs | "All Rights Reserved"; robots.txt `Disallow: /` | "VONA: PVMBG / MAGMA Indonesia" on the card. Live use only with PVMBG's permission |
| OpenFreeMap | Basemap, glyphs, Natural Earth II relief | Attribution required; no SLA; OpenStreetMap data under ODbL | "OpenFreeMap © OpenMapTiles Data from OpenStreetMap", always visible (not collapsed) |
| NASA GIBS | Himawari-9 tiles; TROPOMI SO2 | NASA asks for the acknowledgement; Himawari is JMA/NOAA; TROPOMI is Copernicus | On the layers: "Imagery: NASA GIBS · Himawari-9 data: JMA via NOAA". On SO2: "Imagery: NASA GIBS · Contains modified Copernicus Sentinel data 2026". In the About dialog and deck: "We acknowledge the use of imagery provided by services from NASA's Global Imagery Browse Services (GIBS), part of NASA's Earth Science Data and Information System (ESDIS)." |
| Mapterhorn | Terrain tiles (hillshade) | Open sources; Copernicus GLO-30 for Indonesia and the Philippines; GSI for Japan; no SLA | "© Mapterhorn", linking to mapterhorn.com/attribution |
| unpkg.com | MapLibre GL JS 4.7.1 (BSD-3-Clause); maplibre-gl-compare 0.5.0 (ISC) | Licence notices | "MapLibre" in the map attribution (MapLibre adds it) |
| Gemini API (Google AI Studio key) | Plume Reader, Planner, Drafter | Gemini API terms; free-tier prompts may be reviewed (research/06) | Not a data credit. Send only public feed content |
| IEM NOAAPort and ASOS archives (replay building only) | Past SIGMETs, FV relays, METARs | "in the public domain and may be used freely by anyone for any lawful purpose"; attribution "would be appreciated" | In replay manifests and the About text: "Archive: Iowa Environmental Mesonet, Iowa State University; bulletins from BMKG, BoM and other offices" |
| adsb.lol `globe_history` (replay building only) | Past ADS-B | ODbL 1.0 | "Aircraft: adsb.lol (ODbL 1.0)" on the replayed map |
| BoM anonymous FTP | Private evaluation only | No supply to others; no commercial use | Never in the public repo, demo, video or deck, unless BoM agrees (Registered User) |
| Wikidata and Wikimedia Commons (browser, at runtime) | A photo on a volcano's or an airport's map card | Wikidata CC0; each Commons file under its own licence. TEPHRA shows a photo only when Commons reports public domain, CC0, CC BY or CC BY-SA, and never stores it | "Photo: <author> · <licence>" under the photo, linked to its Commons page |
| Static files: OurAirports, Natural Earth, the GVP catalogue | Airports, navaids, land, volcanoes | Public domain; GVP citation | "Navaids: OurAirports"; "Made with Natural Earth" (offline fallback); the GVP citation in the README and About text |

For the video and deck, `docs/PITCH.md` lists the credits to show: the NASA Earth Observatory image credit line, GIBS, Copernicus, Open-Meteo, adsb.lol and OpenFreeMap. It also bans BoM graphics and MAGMA screenshots.

---

## 4. Git history: the choice the user must make

**The facts** (read-only `git log`, 10 Oct):
- `main` has four commits, all pushed to the private GitHub repository `officialasishkumar/tephra` (`origin/main` = `99bf879`):
  - `3916eb2` added the census, including the 588 BoM texts, the BoM pages and the MAGMA pages, and the research/05 line with a staff name;
  - `50653e4` added the census re-check;
  - `99bf879` added the fixtures, including the BoM pages, the MAGMA pages and the NICT tiles.
- Deleting a file in a new commit does not remove it from history. Anyone who can read the repository can read every old commit.
- GitHub's own guide says that after a history rewrite and force-push, "the commits with sensitive data may still be accessible elsewhere: In any clones or forks of your repository; Directly via their SHA-1 hashes in cached views on GitHub; Through any pull requests that reference them". It also says GitHub Support "won't remove non-sensitive data" [CONFIRMED: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository, accessed 2026-10-10]. Licensed data are not leaked credentials, so a purge request may be refused.

**Option A: a fresh public repository (recommended).** Create a new public repository and push a cleaned copy to it. The current repository stays private as the team archive.
- Nothing restricted has ever been in the public repository, so there is nothing to scrub from GitHub's caches, forks or pull requests.
- The dated history can be kept: filter it in a fresh local clone and push the filtered history. Each commit keeps its date and message, minus the removed paths.
- BoM's terms allow use "within your organisation", so the private archive can keep the census as it is.
- No force-push to a shared repository. Existing clones only need their remote URL updated (step 3).
- Costs: a new URL, unless the private repository is renamed first, and no carried-over issues or stars (there are none today).

**Option B: rewrite this repository's history, then make it public.**
- It keeps one URL. But it needs a force-push, both collaborators must re-clone, and any missed path is exposed the moment the repository turns public.
- The old commits stay reachable by hash in GitHub's cached views, and GitHub may decline to purge them (quoted above).

**Steps for option A** (the user runs them, from the personal-account context; no agent runs them):
1. Make the removals and replacements in section 5 in the working tree. Run the test suite with the stub LLM.
2. On GitHub, rename the private repository (for example to `tephra-private`).
3. Before step 4, re-point every existing clone at the renamed repository: `git remote set-url origin <renamed URL>`. That includes Akash's clone. GitHub warns: "If you create a new repository under your account in the future, do not reuse the original name of the renamed repository. If you do, redirects to the renamed repository will no longer work." [CONFIRMED: https://docs.github.com/en/repositories/creating-and-managing-repositories/renaming-a-repository, accessed 2026-10-10]. Once the new `tephra` exists, an old clone that still points at `officialasishkumar/tephra` would push the restricted history into the public repository.
4. Make a fresh local clone of the renamed private repository and filter it there only. `git filter-repo` is a separate tool that must be installed.
   - Drop the RED paths in section 5 from every commit: `git filter-repo --invert-paths --paths-from-file <list>`.
   - Replace the staff name in `research/05-feeds-verified.md` in every commit: `git filter-repo --replace-text <file>`. The name has been in that file since `3916eb2`, and a path filter does not touch it.

   If keeping the dated history does not matter, a single new commit of the cleaned tree also works.
5. Check the filtered clone (section 6). The check must print nothing for every RED path.
6. Create the new public repository `officialasishkumar/tephra`, add it as the remote of the filtered clone, and push. `pyproject.toml` and the feed User-Agent in `tephra/feeds/base.py` already cite this URL, so nothing in the code changes.
7. Keep `tephra-private` private.
8. From then on, work only in fresh clones of the public repository. A clone made before the filter still carries the old history, and pushing from it would publish that history.

**Steps for option B** (only if chosen): freeze pushes; back up a mirror clone; filter it with `git filter-repo` as in A.4; force-push all branches and tags; have Akash delete his clone and re-clone; check that the repository has no forks or pull requests; only then switch it to public.

---

## 5. Action list before publishing

Do these in order. The owners are the module keys in `MODULES.md`. "User" means the user decides or does it.

1. **User: choose option A or B** (section 4). Until the cleanup is done, do not run `git add -A`. Several RED files are untracked today: both replay cases and three new MAGMA fixtures.
2. **Remove or replace the BoM files.** Under option A, "remove" means "leave out of the public copy". The files stay in the private archive, where BoM's terms allow use within the team.
   - `research/data/census/raw/darwin/ftp/` (588 files), `research/data/census/raw/darwin/bom_*.html` (4), `research/data/census/raw/darwin/ftp_2026_listing.txt`, `research/data/census/raw/recheck/IDY41295.*.txt` (2), `research/data/census/raw/recheck/bom_ftp_2026_listing_recheck.txt`.
   - `tests/fixtures/darwin_vaac/bom_darwin_va_advisory.html`, `bom_volc_ash_recent.html`, `bom_process_volcanic-ash-darwin.json`. Owner feeds-text updates the tests that use them.
   - `data/replay/semeru-20260923/raw/vaac_darwin/` (73 files). Rebuild the bulletins from the IEM NOAAPort FVAU relay and regenerate the manifest (ops-evals / main session).
3. **Remove or replace the MAGMA pages:**
   - `research/data/census/raw/magma/` (25 files), and in `research/data/census/raw/recheck/`: `magma_vona_p001_recheck.html`, `vona_22811.html`, `vona_22827.html`. Leave them out of the public copy; they stay in the private archive.
   - `tests/fixtures/magma/` (7 files). Owner feeds-text replaces them with synthetic MAGMA-format pages that carry invented content and no real names. Name the new files `synthetic_*.html`, so the history check in section 6 can tell them apart from the removed pages.
   - `data/replay/semeru-20260923/raw/vona/` (23 files). Choose (a), (b) or (c) in section 2.5 (core / ops-evals).
   - `research/05-feeds-verified.md`, line 114: redact the name (user).
4. **Remove the NICT images:**
   - `tests/fixtures/himawari/nict_*` (5 files). Owner feeds-geo uses synthetic PNGs.
   - The NICT `json` and `png` files in `data/replay/java-live-20261010/raw/frames/`, once recording ends. Exclude them in the manifest (ops-evals / main session).
   - Team decision (feeds-geo review): stop sending NICT crops to Gemini, or replace NICT as a source.
5. **Add the notices:**
   - In `README.md` "Licence and data credits" (main session), add:
     - "Third-party data keep their own licences; MIT covers TEPHRA's code and text only";
     - the ODbL notice for adsb.lol data: "Contains information from adsb.lol, which is made available under the Open Database License (ODbL) 1.0", covering `tests/fixtures/adsb/` and `data/replay/*/raw/adsb/`;
     - "Weather data by Open-Meteo.com" (CC BY 4.0);
     - JMA (Public Data License 1.0);
     - the GVP citation;
     - OurAirports, Natural Earth and the AWC GIS layers;
     - NASA GIBS with Copernicus;
     - Mapterhorn;
     - IEM;
     - NICT, if any NICT image remains.
   - On screen (web-wall), see section 3 and `tephra/web/THIRD_PARTY.md`. Check especially the Open-Meteo link beside wind values, and the GIBS, Copernicus and Mapterhorn credits once those layers are drawn. At 07:05Z `wall.js` credited only adsb.lol and JMA/NOAA.
6. **Delete `emis3.json`** at the repo root (user).
7. **Evals:** add `evals/plume/arm_t/vona.txt` to `.gitignore` (ops-evals).
8. **Ask Akash** to agree to publishing `research/prior/` (user).
9. **Rebuild the Docker image after the removals** (user, from the dedicated personal-account gcloud configuration; never an agent). Then list `data/replay` inside it, because the demo serves those files.
10. **Run the checks in section 6** on the tree and on the history that will be published.
11. **Optional permissions** (user):
    - BoM: become a Registered User to publish Bureau data, or ask.
    - PVMBG: permission to use VONAs (the email subscription is the lawful live route).
    - airplanes.live: API access for East Java (research/17, L10).

---

## 6. Final checks (read-only commands)

Run these in the tree to be published, and in the filtered clone before pushing. Each should print nothing.

The patterns are limited to data files on purpose. Our own docs, `scripts/record_replay.py` and its test quote these strings in order to describe or refuse them.

```bash
# BoM's copyright notice inside data files
grep -rl --include='*.txt' --include='*.html' --include='*.json' "Commonwealth of Australia" --exclude-dir=.git .
# MAGMA pages
grep -rl --include='*.html' "All Rights Reserved. MAGMA" --exclude-dir=.git .
# NICT sources in replay manifests
grep -l "himawari8.nict.go.jp" data/replay/*/manifest.json
# NICT fixture files
find . -path ./.git -prune -o -name 'nict_*' -print
# BoM website pages kept as fixtures or census files
find . -path ./.git -prune -o -name 'bom_*' -print
# RED paths anywhere in the history about to be published
git log --all --format=%h --name-only | grep -E 'raw/darwin/ftp/|raw/magma/|recheck/(IDY|magma|vona_)|/bom_|nict_|fixtures/magma/vona_' | sort -u
```

The replay cases were not in any commit at 07:20Z, so the history check cannot see them. The content checks above cover them in the tree.

Then:
- run the test suite with the stub LLM (`uv run pytest`) to confirm that the fixture swaps work;
- open `research/05-feeds-verified.md` §3.3 to confirm the name is gone;
- look through the published replay manifests once by eye.
