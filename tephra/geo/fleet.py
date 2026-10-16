"""The own-fleet filter: which aircraft an airline's own TEPHRA checks against the ash.

Empty by default, so every aircraft is checked as the demo does. Set, it narrows only which
aircraft enter exposure: the map, pushes and crew-report lookups still see every aircraft, and
no validator changes.
"""

from dataclasses import dataclass
from typing import Final, Self

from tephra.config import Settings
from tephra.models import PUSH_SOURCE_PREFIX, Aircraft, OwnFleet

__all__ = ["ALL_AIRCRAFT", "FleetFilter"]


@dataclass(frozen=True, slots=True)
class FleetFilter:
    prefixes: frozenset[str] = frozenset()
    hexes: frozenset[str] = frozenset()

    @property
    def everyone(self) -> bool:
        return not (self.prefixes or self.hexes)

    def admits(self, aircraft: Aircraft) -> bool:
        """Pushed positions are the airline's own by construction; an ADS-B target counts when
        its address is listed or its airline-style callsign starts with a listed prefix."""
        if self.everyone or aircraft.source_id.startswith(PUSH_SOURCE_PREFIX):
            return True
        if aircraft.hex in self.hexes:
            return True
        return aircraft.airline and (aircraft.callsign or "")[:3] in self.prefixes

    def own_fleet(self) -> OwnFleet | None:
        if self.everyone:
            return None
        return OwnFleet(prefixes=sorted(self.prefixes), hex_count=len(self.hexes))

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        return cls(prefixes=settings.fleet_prefixes, hexes=settings.fleet_hexes)


ALL_AIRCRAFT: Final = FleetFilter()
