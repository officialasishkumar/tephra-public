# Static map data for the Wall

Served from `/static/data/`. Every file is display context only: nothing in TEPHRA's hazard,
exposure or advice logic reads them. None is current enough for navigation, and the Wall says
"approximate" wherever it draws them.

| File | What | Source and licence |
|---|---|---|
| `firs.geojson` | 13 FIR outlines around TEPHRA's regions: WIIF Jakarta, WAAF Ujung Pandang, WSJC Singapore, WMFC Kuala Lumpur, WBFC Kota Kinabalu, AYPM Port Moresby, RPHI Manila, YBBB Brisbane, YMMM Melbourne, RJJJ Fukuoka, RKRR Incheon, RCAA Taipei, ZSHA Shanghai. Properties `icao`, `name`, `label`. Clipped to 75°E–180°E, 50°S–55°N and rounded to 0.01° (about 1 km). AWC's spellings "Yjung Pandang" and "Kuala Lampur" are corrected. | NOAA/NWS Aviation Weather Center, [`firpoly.topojson`](https://aviationweather.gov/gis/firpoly.topojson) (Last-Modified 2026-10-08, sha256 `e28daa0fa2918ee0…`), public domain ([weather.gov/disclaimer](https://www.weather.gov/disclaimer)). The geometry may predate the 2024 Jakarta/Singapore FIR realignment. |
| `vaac_aor.geojson` | Darwin and Tokyo VAAC areas of responsibility, clipped and rounded as above. Properties `vaac`, `label`. The two areas overlap between 10°N and 20°N west of 100°E as published; the issuing VAAC always comes from the VAA header, never from this geometry. | NOAA/NWS Aviation Weather Center, [`vaac.json`](https://aviationweather.gov/gis/vaac.json) (Last-Modified 2026-10-08, sha256 `a7a3d95a7646a7d0…`), public domain. |
| `land_apac.geojson` | Land polygons for 88°E–160°E, 20°S–42°N, simplified to 0.01° and rounded to 0.01°. Loaded when the OpenFreeMap basemap fails (offline fallback), and by TEPHRA Assistant at work, which draws its own map of the region from it (no tiles). Property `name`. | [Natural Earth](https://www.naturalearthdata.com/about/terms-of-use/) 1:50m admin 0 countries (sha256 `3e458fc036ad0a66…`), public domain. |
| `navaids.geojson` | VOR, DME, NDB and TACAN stations from 90°E to 142°E and 15°S to 22°N, plus Kyushu. | OurAirports `navaids.csv` (sha256 `57fb332b…a8976e24cb`, fetched 2026-10-10), released to the public domain. |

`guide-shots.json` is not map data: the Guide's screenshot sizes and numbered marks (percent of the
image), written with the WebP files in `../guide/shots/` by `scripts/capture_guide_shots.mjs`.

The earlier VATSIM-derived FIR file (CC BY-SA 4.0) was replaced by the AWC outlines on
2026-10-10, so nothing here carries a share-alike condition. The conversion scripts are not
part of the app; the steps are: decode the TopoJSON, keep the listed FIRs (or the Darwin and
Tokyo areas), intersect with the box above, drop non-polygon fragments, round to two decimals.
