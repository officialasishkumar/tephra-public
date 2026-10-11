"""Build ``data/routes_apac.json`` from VRS standing data (CC0): callsign -> airport chain.

Downloads ``routes.csv.gz`` (about 4.5 MB) and ``airports.csv.gz`` (about 1 MB) once from
vrs-standing-data.adsb.lol, or reads copies you already have with ``--routes-input`` and
``--airports-input``. A chain is kept when every airport in it has a known position (in
``data/airports.json``, else in the VRS airports file) and lies in the catalogue or within
``REACH_NM`` of one of TEPHRA's three regions, which keeps the file small. The positions of
kept airports that the catalogue lacks are stored in the file. The file records both sources,
their SHA-256 and the licence.

Run it yourself; without the ``--*-input`` options it makes two network requests.

    uv run python scripts/build_routes.py
    uv run python scripts/build_routes.py --routes-input R.csv.gz --airports-input A.csv.gz
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import sys
import urllib.request
from collections.abc import Mapping
from pathlib import Path

from tephra.config import PROJECT_ROOT, REGIONS
from tephra.feeds.airports import AIRPORT_FILE
from tephra.feeds.routes import ROUTES_FILE
from tephra.geo.units import distance_nm
from tephra.models import AirportFile
from tephra.util import timeutil
from tephra.util.hashing import sha256_bytes

ROUTES_URL = "https://vrs-standing-data.adsb.lol/routes.csv.gz"
AIRPORTS_URL = "https://vrs-standing-data.adsb.lol/airports.csv.gz"
LICENSE = "CC0-1.0 (github.com/vradarserver/standing-data)"
ROUTES_NOTE = (
    "Callsign to airport chain, crowd-sourced and possibly stale. Kept when every airport of"
    " the chain has a known position and lies in data/airports.json or within 1500 NM of a"
    " TEPHRA region."
)
AIRPORTS_NOTE = (
    "Airport positions (VRS airports, schema 01) for chain airports that data/airports.json"
    " lacks; latitude and longitude only."
)
REACH_NM = 1500.0
TIMEOUT_S = 60

type Position = tuple[float, float]


def parse_airports(csv_text: str) -> dict[str, Position]:
    """ICAO -> (lat, lon) for every row of the VRS airports file with a 4-letter ICAO code."""
    positions: dict[str, Position] = {}
    for row in csv.DictReader(io.StringIO(csv_text)):
        icao = (row.get("ICAO") or "").strip().upper()
        try:
            lat, lon = float(row["Latitude"]), float(row["Longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if len(icao) == 4 and icao.isalpha() and -90 <= lat <= 90 and -180 <= lon <= 180:
            positions.setdefault(icao, (round(lat, 4), round(lon, 4)))
    return positions


def within_reach(position: Position) -> bool:
    """Whether the point lies within ``REACH_NM`` of any region's bounding box."""
    lat, lon = position
    for region in REGIONS.values():
        box = region.bbox
        nearest = (min(max(lat, box.south), box.north), min(max(lon, box.west), box.east))
        if distance_nm(lat, lon, *nearest) <= REACH_NM:
            return True
    return False


def parse_routes(
    csv_text: str, catalogue: Mapping[str, Position], vrs: Mapping[str, Position]
) -> tuple[dict[str, str], dict[str, Position]]:
    """Callsign -> ``WIII-WARR`` for every row whose chain has 2+ airports, each placed (the
    catalogue first, else VRS) and in the catalogue or within reach; plus the positions of the
    kept airports that the catalogue lacks."""
    routes: dict[str, str] = {}
    extra: dict[str, Position] = {}
    for row in csv.DictReader(io.StringIO(csv_text)):
        callsign = (row.get("Callsign") or "").strip().upper()
        chain = [code.strip().upper() for code in (row.get("AirportCodes") or "").split("-")]
        if not callsign or len(chain) < 2 or callsign in routes:
            continue
        placed: dict[str, Position] = {}
        for code in chain:
            position = catalogue.get(code) or vrs.get(code)
            if position is None or (code not in catalogue and not within_reach(position)):
                break
            placed[code] = position
        else:
            routes[callsign] = "-".join(chain)
            extra.update({code: pos for code, pos in placed.items() if code not in catalogue})
    return dict(sorted(routes.items())), dict(sorted(extra.items()))


def build(
    routes_gz: bytes,
    airports_gz: bytes,
    catalogue: Mapping[str, Position],
    *,
    fetched: str,
) -> dict[str, object]:
    vrs = parse_airports(gzip.decompress(airports_gz).decode("utf-8-sig"))
    routes, extra = parse_routes(gzip.decompress(routes_gz).decode("utf-8-sig"), catalogue, vrs)
    return {
        "source": {
            "url": ROUTES_URL,
            "fetched": fetched,
            "sha256": sha256_bytes(routes_gz),
            "license": LICENSE,
            "note": ROUTES_NOTE,
        },
        "airports_source": {
            "url": AIRPORTS_URL,
            "fetched": fetched,
            "sha256": sha256_bytes(airports_gz),
            "license": LICENSE,
            "note": AIRPORTS_NOTE,
        },
        "airports": extra,
        "routes": routes,
    }


def _download(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=TIMEOUT_S) as response:
        return response.read()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build data/routes_apac.json (VRS, CC0).")
    parser.add_argument("--routes-input", type=Path, help="a local routes.csv.gz")
    parser.add_argument("--airports-input", type=Path, help="a local airports.csv.gz")
    parser.add_argument(
        "--fetched", help="date the --*-input copies were downloaded (default: today)"
    )
    parser.add_argument("--data-dir", type=Path, default=PROJECT_ROOT / "data")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    file = AirportFile.model_validate_json((args.data_dir / AIRPORT_FILE).read_bytes())
    catalogue = {airport.icao: (airport.lat, airport.lon) for airport in file.airports}
    routes_gz = args.routes_input.read_bytes() if args.routes_input else _download(ROUTES_URL)
    airports_gz = (
        args.airports_input.read_bytes() if args.airports_input else _download(AIRPORTS_URL)
    )
    fetched = args.fetched or timeutil.now().date().isoformat()
    document = build(routes_gz, airports_gz, catalogue, fetched=fetched)
    out = args.data_dir / ROUTES_FILE
    out.write_text(json.dumps(document, indent=0, separators=(",", ":")) + "\n", encoding="utf-8")
    print(  # type: ignore[arg-type]
        f"wrote {out}: {len(document['routes'])} callsigns, {len(document['airports'])} airports"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
