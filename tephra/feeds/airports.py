"""The static aerodrome catalogue (``data/airports.json``) used for alternates and TAFs."""

from collections.abc import Sequence
from pathlib import Path

from tephra.geo.units import distance_nm
from tephra.models import Airport, AirportFile, BBox

__all__ = ["AIRPORT_FILE", "AirportCatalogue", "load_airports"]

AIRPORT_FILE = "airports.json"


class AirportCatalogue:
    """``min_runway_m`` is the operator policy's jet-alternate runway length."""

    def __init__(self, airports: Sequence[Airport], *, min_runway_m: int) -> None:
        self._min_runway_m = min_runway_m
        self._airports = sorted(airports, key=lambda airport: airport.icao)
        self._by_icao: dict[str, Airport] = {}
        for airport in self._airports:
            if airport.icao in self._by_icao:
                raise ValueError(f"duplicate airport {airport.icao}")
            self._by_icao[airport.icao] = airport

    def all(self) -> list[Airport]:
        return list(self._airports)

    def get(self, icao: str) -> Airport | None:
        return self._by_icao.get(icao.strip().upper())

    def icaos(self) -> set[str]:
        return set(self._by_icao)

    def in_bbox(self, bbox: BBox) -> list[Airport]:
        return [airport for airport in self._airports if bbox.contains(airport.lat, airport.lon)]

    def nearest(
        self,
        lat: float,
        lon: float,
        *,
        limit: int = 5,
        max_nm: float,
        alternates_only: bool = True,
    ) -> list[tuple[Airport, float]]:
        """``(airport, distance_nm)`` within ``max_nm``, nearest first."""
        found: list[tuple[Airport, float]] = []
        for airport in self._airports:
            if alternates_only and not self.alternate_ok(airport):
                continue
            distance = distance_nm(lat, lon, airport.lat, airport.lon)
            if distance <= max_nm:
                found.append((airport, distance))
        found.sort(key=lambda pair: (pair[1], pair[0].icao))
        return found[: max(limit, 0)]

    def alternate_ok(self, airport: Airport) -> bool:
        """Usable as a jet alternate in TEPHRA's simplified model: runway length only."""
        return (airport.longest_runway_m or 0) >= self._min_runway_m


def load_airports(data_dir: Path, *, min_runway_m: int) -> AirportCatalogue:
    catalogue = AirportFile.model_validate_json((data_dir / AIRPORT_FILE).read_bytes())
    return AirportCatalogue(catalogue.airports, min_runway_m=min_runway_m)
