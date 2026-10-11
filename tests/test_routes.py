"""Published routes (VRS standing data): the lookup that picks the leg a flight is flying,
and the script and data file that feed it. Nothing here reaches the network."""

import gzip
import importlib.util
import json
from pathlib import Path
from types import ModuleType

from tephra.config import PROJECT_ROOT
from tephra.feeds.airports import load_airports
from tephra.feeds.routes import RouteTable, load_routes
from tephra.geo.units import destination_point, distance_nm, initial_bearing_deg, nm_to_km
from tephra.policy import load_policy

DATA = PROJECT_ROOT / "data"
POLICY = load_policy(DATA)
AIRPORTS = load_airports(DATA, min_runway_m=POLICY.alternates.min_runway_m.value)
LIMIT_NM = POLICY.reroute.route_max_cross_track_nm.value


class Plane:
    def __init__(
        self, callsign: str | None, lat: float, lon: float, track_deg: float | None
    ) -> None:
        self.callsign, self.lat, self.lon, self.track_deg = callsign, lat, lon, track_deg


def on_leg(origin: str, dest: str, fraction: float, *, off_nm: float = 0.0) -> tuple[float, float]:
    """A point ``fraction`` of the way along a leg, ``off_nm`` to its right."""
    a, b = AIRPORTS.get(origin), AIRPORTS.get(dest)
    assert a is not None
    assert b is not None
    bearing = initial_bearing_deg(a.lat, a.lon, b.lat, b.lon)
    along = destination_point(
        a.lat, a.lon, bearing, nm_to_km(distance_nm(a.lat, a.lon, b.lat, b.lon) * fraction)
    )
    if off_nm == 0.0:
        return along
    return destination_point(*along, bearing + 90.0, nm_to_km(off_nm))


TABLE = RouteTable({"GIA101": "WIII-WARR", "GIA202": "WIII-WARR-WADD", "GIA303": "WIII-ZZZZ"})


def test_lookup_picks_the_leg_the_aircraft_is_on() -> None:
    lat, lon = on_leg("WIII", "WARR", 0.4)
    route = TABLE.lookup(Plane("GIA101", lat, lon, track_deg=100.0), AIRPORTS, POLICY)
    assert route is not None
    assert (route.callsign, route.origin_icao, route.dest_icao) == ("GIA101", "WIII", "WARR")
    assert route.cross_track_nm < 1.0


def test_lookup_uses_the_second_leg_of_a_chain() -> None:
    lat, lon = on_leg("WARR", "WADD", 0.5)
    route = TABLE.lookup(Plane("GIA202", lat, lon, track_deg=100.0), AIRPORTS, POLICY)
    assert route is not None
    assert (route.origin_icao, route.dest_icao) == ("WARR", "WADD")


def test_lookup_refuses_an_aircraft_off_the_leg_or_flying_away() -> None:
    near = on_leg("WIII", "WARR", 0.4, off_nm=LIMIT_NM - 10)
    far = on_leg("WIII", "WARR", 0.4, off_nm=LIMIT_NM + 20)
    assert TABLE.lookup(Plane("GIA101", *near, track_deg=100.0), AIRPORTS, POLICY) is not None
    assert TABLE.lookup(Plane("GIA101", *far, track_deg=100.0), AIRPORTS, POLICY) is None
    lat, lon = on_leg("WIII", "WARR", 0.4)
    assert TABLE.lookup(Plane("GIA101", lat, lon, track_deg=280.0), AIRPORTS, POLICY) is None
    assert TABLE.lookup(Plane("GIA101", lat, lon, track_deg=None), AIRPORTS, POLICY) is None


def test_lookup_refuses_an_aircraft_beyond_either_end_of_the_leg() -> None:
    origin = AIRPORTS.get("WIII")
    assert origin is not None
    behind = destination_point(origin.lat, origin.lon, 280.0, nm_to_km(150.0))
    assert TABLE.lookup(Plane("GIA101", *behind, track_deg=100.0), AIRPORTS, POLICY) is None


def test_lookup_ignores_unknown_callsigns_and_chains_with_unknown_airports() -> None:
    lat, lon = on_leg("WIII", "WARR", 0.4)
    assert TABLE.lookup(Plane("XXX999", lat, lon, track_deg=100.0), AIRPORTS, POLICY) is None
    assert TABLE.lookup(Plane("GIA303", lat, lon, track_deg=100.0), AIRPORTS, POLICY) is None
    assert TABLE.lookup(Plane(None, lat, lon, track_deg=100.0), AIRPORTS, POLICY) is None


def test_callsign_matching_ignores_case_space_and_leading_zeros() -> None:
    assert TABLE.chain(" gia101 ") == ("WIII", "WARR")
    assert TABLE.chain("GIA0101") == ("WIII", "WARR")
    assert TABLE.chain("GIA1") is None


def _script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "tephra_script_build_routes", PROJECT_ROOT / "scripts" / "build_routes.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CSV = (
    "\ufeffCallsign,Code,Number,AirlineCode,AirportCodes\n"
    "GIA101,GA,101,GIA,WIII-WARR\n"
    "GIA202,GA,202,GIA,WIII-WARR-WADD\n"
    "BAW9,BA,9,BAW,EGLL-WIII\n"
    "QFA1,QF,1,QFA,WIII\n"
    "GIA101,GA,101,GIA,WADD-WIII\n"
    "VOZ1,VA,1,VOZ,WADD-WBKK\n"
    "VOZ2,VA,2,VOZ,WADD-YYYY\n"
    "ANZ1,NZ,1,ANZ,WADD-NZAA\n"
)
AIRPORTS_CSV = (
    "\ufeffCode,Name,ICAO,IATA,Location,CountryISO2,Latitude,Longitude,AltitudeFeet\n"
    "WBKK,Kota Kinabalu,WBKK,BKI,Kota Kinabalu,MY,5.9372,116.051,10\n"
    "NZAA,Auckland,NZAA,AKL,Auckland,NZ,-37.0082,174.7917,23\n"
    "EGLL,Heathrow,EGLL,LHR,London,GB,51.4706,-0.4619,83\n"
)
CATALOGUE = {code: (a.lat, a.lon) for code in AIRPORTS.icaos() if (a := AIRPORTS.get(code))}


def _build(script: ModuleType) -> dict:
    return script.build(
        gzip.compress(CSV.encode("utf-8")),
        gzip.compress(AIRPORTS_CSV.encode("utf-8")),
        CATALOGUE,
        fetched="d",
    )


def test_build_keeps_chains_with_known_positions_inside_reach() -> None:
    document = _build(_script())
    assert document["routes"] == {
        "GIA101": "WIII-WARR",
        "GIA202": "WIII-WARR-WADD",
        "VOZ1": "WADD-WBKK",
    }
    # EGLL and NZAA are known but far outside every region; YYYY is unknown; a catalogue
    # airport is never copied into the file.
    assert document["airports"] == {"WBKK": (5.9372, 116.051)}


def test_build_records_both_sources() -> None:
    document = _build(_script())
    for key, name in (("source", "routes"), ("airports_source", "airports")):
        source = document[key]
        assert source["url"].endswith(f"{name}.csv.gz")
        assert source["license"].startswith("CC0")
        assert len(source["sha256"]) == 64


def test_build_script_writes_a_loadable_file(tmp_path: Path) -> None:
    script = _script()
    (tmp_path / "airports.json").write_bytes((DATA / "airports.json").read_bytes())
    routes, airports = tmp_path / "routes.csv.gz", tmp_path / "airports.csv.gz"
    routes.write_bytes(gzip.compress(CSV.encode("utf-8")))
    airports.write_bytes(gzip.compress(AIRPORTS_CSV.encode("utf-8")))
    argv = [
        "--routes-input",
        str(routes),
        "--airports-input",
        str(airports),
        "--data-dir",
        str(tmp_path),
        "--fetched",
        "2026-10-11",
    ]
    assert script.main(argv) == 0
    table = load_routes(tmp_path)
    assert len(table) == 3
    assert table.position("WBKK", AIRPORTS) == (5.9372, 116.051)
    written = json.loads((tmp_path / "routes_apac.json").read_text(encoding="utf-8"))
    assert written["source"]["fetched"] == "2026-10-11"


def test_a_leg_to_an_airport_outside_the_catalogue_is_resolved_from_the_routes_file() -> None:
    table = RouteTable({"VOZ1": "WADD-WBKK"}, {"WBKK": (5.9372, 116.051)})
    start = AIRPORTS.get("WADD")
    assert start is not None
    bearing = initial_bearing_deg(start.lat, start.lon, 5.9372, 116.051)
    lat, lon = destination_point(start.lat, start.lon, bearing, nm_to_km(500.0))
    route = table.lookup(Plane("VOZ1", lat, lon, track_deg=bearing), AIRPORTS, POLICY)
    assert route is not None
    assert (route.origin_icao, route.dest_icao) == ("WADD", "WBKK")
    assert table.position("wbkk", AIRPORTS) == (5.9372, 116.051)
    assert table.position("WADD", AIRPORTS) is not None
    assert table.position("ZZZZ", AIRPORTS) is None


def test_the_shipped_routes_file_is_small_cited_and_fully_placed() -> None:
    path = DATA / "routes_apac.json"
    assert path.stat().st_size < 2_000_000
    document = json.loads(path.read_text(encoding="utf-8"))
    for key, name in (("source", "routes"), ("airports_source", "airports")):
        source = document[key]
        assert source["url"] == f"https://vrs-standing-data.adsb.lol/{name}.csv.gz"
        assert source["license"].startswith("CC0")
        assert len(source["sha256"]) == 64
        assert source["fetched"]
    placed = AIRPORTS.icaos() | set(document["airports"])
    assert not set(document["airports"]) & AIRPORTS.icaos()
    assert document["routes"]
    for chain in document["routes"].values():
        assert set(chain.split("-")) <= placed
    assert len(load_routes(DATA)) == len(document["routes"])


def test_the_shipped_table_resolves_a_flight_on_one_of_its_legs() -> None:
    table = load_routes(DATA)
    document = json.loads((DATA / "routes_apac.json").read_text(encoding="utf-8"))
    known = AIRPORTS.icaos()
    callsign, joined = next(
        (c, j)
        for c, j in document["routes"].items()
        if set(j.split("-")[:2]) <= known and j.split("-")[0] != j.split("-")[1]
    )
    origin, dest = joined.split("-")[:2]
    lat, lon = on_leg(origin, dest, 0.5)
    a, b = AIRPORTS.get(origin), AIRPORTS.get(dest)
    assert a is not None
    assert b is not None
    track = initial_bearing_deg(lat, lon, b.lat, b.lon)
    route = table.lookup(Plane(callsign, lat, lon, track_deg=track), AIRPORTS, POLICY)
    assert route is not None
    assert route.dest_icao == dest


def test_the_shipped_table_resolves_a_leg_to_an_airport_the_catalogue_lacks() -> None:
    table = load_routes(DATA)
    document = json.loads((DATA / "routes_apac.json").read_text(encoding="utf-8"))
    outside = set(document["airports"])
    callsign, joined = next(
        (c, j)
        for c, j in document["routes"].items()
        if j.split("-")[0] in AIRPORTS.icaos() and j.split("-")[1] in outside
    )
    origin, dest = joined.split("-")[:2]
    a, b = AIRPORTS.get(origin), table.position(dest, AIRPORTS)
    assert a is not None
    assert b is not None
    bearing = initial_bearing_deg(a.lat, a.lon, *b)
    lat, lon = destination_point(a.lat, a.lon, bearing, nm_to_km(100.0))
    route = table.lookup(Plane(callsign, lat, lon, track_deg=bearing), AIRPORTS, POLICY)
    assert route is not None
    assert route.dest_icao == dest
