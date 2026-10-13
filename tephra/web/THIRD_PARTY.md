# Third-party assets and services used by the Wall and the Desk

Everything the two pages load or show that TEPHRA did not make, with its licence and the credit
the page must carry. Verified on 2026-10-10. The UI spec (`docs/UI-DESIGN.md`) says where each
credit appears. Feed terms in full: `research/05-feeds-verified.md` and
`research/17-data-sources.md`; publication rules for the video and deck: `docs/DATA-LICENCES.md`.

## Code loaded by the browser

| What | Version, where from | Licence | Credit or notice |
|---|---|---|---|
| MapLibre GL JS | `maplibre-gl@4.7.1` (`dist/maplibre-gl.js`, `dist/maplibre-gl.css`) from unpkg.com, pinned; the UMD build that exposes `window.maplibregl` | BSD-3-Clause | "MapLibre" in the map attribution control (MapLibre adds it). |
| Map card photos (`wall/photo.js`) | Read at runtime, never stored: Wikidata's image (P18) of a volcano (Smithsonian volcano number, P1886) or an airport (ICAO code, P239), served by Wikimedia Commons (`upload.wikimedia.org`, `thumb.wikimedia.org`) | Shown only when Commons' `LicenseShortName` is public domain, CC0, CC BY or CC BY-SA | Under the photo: "Photo: <author> · <licence>", linking to the file's Commons page, as each licence asks. |
| maplibre-gl-compare | `@maplibre/maplibre-gl-compare@0.5.0` (`dist/maplibre-gl-compare.js`, `.css`) from unpkg.com, pinned; loaded only by the Wall, used for swipe compare | ISC | None required on screen; keep the licence notice with any copy. |

The CSP (`CONTENT_SECURITY_POLICY` in `tephra/api/server.py`) allows scripts only from these two
package paths on unpkg.com.

## Files shipped in `tephra/web/`

| File | Origin | Licence | Notice |
|---|---|---|---|
| `fonts/ibm-plex-sans-var-*.woff2` | IBM Plex Sans (variable, weight 400-700), latin and latin-ext subsets as served by Google Fonts (css2 API, v23) | SIL Open Font License 1.1 | `fonts/OFL.txt`: "Copyright © 2017 IBM Corp. with Reserved Font Name "Plex"". |
| `fonts/ibm-plex-mono-{400,500}-*.woff2` | IBM Plex Mono 400 and 500, latin and latin-ext subsets, Google Fonts (v20) | SIL Open Font License 1.1 | Same `fonts/OFL.txt` (identical text for both families). |
| `icons.svg`, symbols `i-*` except the two below | Lucide icons, `lucide-static@1.54.0` | ISC; the icons Lucide derived from Feather (for example `check`, `x`, `chevron-*`, `clock`, `compass`, `info`, `lock`, `log-out`, `minus`, `plus`, `external-link`, `navigation-2`) are MIT | "ISC License, Copyright (c) 2026 Lucide Icons and Contributors" and "The MIT License (MIT), Copyright (c) 2013-present Cole Bemis" (full texts below). |
| `icons.svg`, symbol `i-aircraft` (and the same path drawn on the map in `wall.js`) | Material Symbols "flight", rounded, filled (`@material-symbols/svg-400@0.48.0`, google/material-design-icons) | Apache License 2.0 | "Material Symbols by Google, Apache License 2.0". |
| `icons.svg`, symbol `i-airport` | Maki 8.2.0 "airport" (Mapbox) | CC0 1.0 | None required. |
| `icons.svg`, symbols `st-*`, `lg-*`, `i-eruption` | Drawn for TEPHRA. The eruption symbol follows the ICAO/WMO volcanic-eruption symbol as the Darwin, Tokyo and Washington VAACs draw it. | Part of TEPHRA | None. |
| `data/firs.geojson`, `data/vaac_aor.geojson` | NOAA/NWS Aviation Weather Center, `aviationweather.gov/gis/firpoly.topojson` and `/gis/vaac.json`, trimmed (see `data/README.md`) | Public domain (weather.gov disclaimer) | Shown on the map as "FIR and VAAC lines: NOAA/NWS AWC (approximate)". |
| `data/land_apac.geojson` | Natural Earth 1:50m admin 0 countries, trimmed | Public domain | "Made with Natural Earth" when the offline fallback is on screen. |
| `data/navaids.geojson` | OurAirports `navaids.csv` | Public domain | "Navaids: OurAirports" in the attribution when the layer is on. |

## Services the browser fetches from

| Service | What TEPHRA uses | Terms | Credit that must be on screen |
|---|---|---|---|
| OpenFreeMap, `tiles.openfreemap.org` | The `dark` style, its OpenMapTiles vector tiles (planet build 20261004), Noto Sans glyphs for map labels, and the style's `ne2_shaded` Natural Earth II relief raster | No keys, no limits, commercial use allowed, attribution required, no warranty or SLA ([openfreemap.org/tos](https://openfreemap.org/tos/)). Map data © OpenStreetMap contributors, ODbL 1.0. Noto Sans: SIL OFL 1.1. Natural Earth: public domain. | The style's own attribution: "OpenFreeMap © OpenMapTiles Data from OpenStreetMap", always visible (not collapsed) in the map attribution control. |
| NASA GIBS, `gibs.earthdata.nasa.gov` (WMTS, EPSG:3857) | Himawari-9 AHI `Himawari_AHI_Band13_Clean_Infrared` and `Himawari_AHI_Air_Mass` (GoogleMapsCompatible_Level6), `Himawari_AHI_Band3_Red_Visible_1km` (Level7), `TROPOMI_L2_Sulfur_Dioxide_Total_Vertical_Column` (daily, Level6). Context layers only, never ash detection. | NASA asks for this acknowledgement: "We acknowledge the use of imagery provided by services from NASA's Global Imagery Browse Services (GIBS), part of NASA's Earth Science Data and Information System (ESDIS)." Himawari-9 is JMA data distributed by NOAA: attribute, and do not state or imply endorsement. TROPOMI is Copernicus Sentinel-5P data: free, full and open, with credit. | On every satellite layer, in the layer's context label: "Imagery: NASA GIBS · Himawari-9 data: JMA via NOAA". On the SO2 layer: "Imagery: NASA GIBS · Contains modified Copernicus Sentinel data 2026". The full GIBS acknowledgement goes in the Wall's About dialog and the deck. |
| Mapterhorn, `tiles.mapterhorn.com` | Terrarium-encoded terrain tiles (512 px WebP, to z12) for the hillshade | Code BSD-3-Clause; data from open sources listed at [mapterhorn.com/attribution](https://mapterhorn.com/attribution). Indonesia and the Philippines: Copernicus GLO-30 DEM ("COPERNICUS full, free and open license"; © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018, provided under COPERNICUS by the European Union and ESA). Japan: GSI elevation data (国土地理院). No SLA. | "© Mapterhorn" linking to mapterhorn.com/attribution, set as the DEM source's `attribution` so MapLibre shows it. |

## Feed content the pages display (fetched by TEPHRA's server, not the browser)

Shown verbatim with source, time and hash.

| Feed | Credit shown in the UI |
|---|---|
| ADS-B positions, adsb.lol | "Aircraft: adsb.lol (ODbL 1.0)" in the map attribution |
| Himawari-9 frames and the split-window BTD computed by TEPHRA | "Himawari-9 data: JMA via NOAA; processed by TEPHRA" next to the overlay |
| VA SIGMETs, TAFs, METARs (aviationweather.gov) | Source line on each card ("SIGMET · AWC") |
| VAAs: Tokyo (JMA), Darwin (BoM, via NOAA tgftp) | Source line on each card |
| VONAs (MAGMA Indonesia, PVMBG) | Source line on each card; live polling is off by policy |
| Winds (Open-Meteo, CC BY 4.0) | "Weather data by Open-Meteo.com" as a link next to any wind value or layer |

## Design references (nothing copied)

Astro UX Design System status system (shape plus colour plus word), GOV.UK "Check answers"
pattern, Nielsen Norman Group on confirmation dialogs, WCAG 2.2 Understanding documents, Paul
Tol, Okabe-Ito and IBM colour-blind-safe palettes, the Darwin, Tokyo and Washington VAAC
graphics, NASA Worldview's swipe compare, Flightradar24 Playback's timeline, Windy's altitude
slider. These shaped the design; no code, text or images from them are in the repo.

## Licence texts

### Lucide (ISC)

```
ISC License

Copyright (c) 2026 Lucide Icons and Contributors

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
```

### Feather (MIT), for the Lucide icons derived from it

```
The MIT License (MIT)

Copyright (c) 2013-present Cole Bemis

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### Material Symbols (Apache License 2.0)

The `flight` glyph is used under the Apache License, Version 2.0
(https://www.apache.org/licenses/LICENSE-2.0). Copyright Google LLC. Distributed on an "AS IS"
basis, without warranties or conditions of any kind.

### IBM Plex (SIL Open Font License 1.1)

See `fonts/OFL.txt`.
