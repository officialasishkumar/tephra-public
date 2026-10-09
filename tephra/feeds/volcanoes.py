"""The static JAPAC volcano catalogue (``data/volcanoes.json``) and name lookups.

Feeds name volcanoes in several ways: SIGMETs write ``ERUPTION MT SEMERU``, VAAs
``SEMERU 263300`` or ``SAKURAJIMA (AIRA CALDERA)`` (BoM prints square brackets), MAGMA
``Semeru (263300)``. Every lookup goes through :func:`source_slug`, which upper-cases and
reduces punctuation and brackets to single separators, so all of these compare equal to
the catalogue aliases.
"""

import re
from collections.abc import Sequence
from pathlib import Path

from tephra.geo.units import haversine_km
from tephra.models import BBox, Volcano, VolcanoFile, source_slug

__all__ = ["VOLCANO_FILE", "VolcanoCatalogue", "load_volcanoes"]

VOLCANO_FILE = "volcanoes.json"

_GVP_NUMBER = re.compile(r"(?<!\d)(\d{6})(?!\d)")
_NAME_PREFIXES = ("MT_", "MOUNT_", "GUNUNG_", "VOLCAN_")


class VolcanoCatalogue:
    def __init__(self, volcanoes: Sequence[Volcano]) -> None:
        self._volcanoes = sorted(volcanoes, key=lambda volcano: volcano.id)
        self._by_id: dict[str, Volcano] = {}
        self._by_slug: dict[str, Volcano] = {}
        self._by_code: dict[str, Volcano] = {}
        for volcano in self._volcanoes:
            if volcano.id in self._by_id:
                raise ValueError(f"duplicate volcano id {volcano.id}")
            self._by_id[volcano.id] = volcano
            for name in (volcano.name, *volcano.aliases):
                self._add_slug(source_slug(name), volcano)
            if volcano.magma_code:
                self._by_code[volcano.magma_code.upper()] = volcano
        # Longest first, so "ANAK_KRAKATAU" wins over "KRAKATAU" at the same position.
        self._text_slugs = sorted(self._by_slug, key=len, reverse=True)

    def all(self) -> list[Volcano]:
        return list(self._volcanoes)

    def get(self, volcano_id: str) -> Volcano | None:
        return self._by_id.get(volcano_id.strip())

    def resolve(self, name: str) -> Volcano | None:
        """A catalogue volcano for a name as a feed prints it, a GVP number, or None."""
        number = _GVP_NUMBER.search(name)
        if number is not None and number.group(1) in self._by_id:
            return self._by_id[number.group(1)]
        slug = source_slug(_GVP_NUMBER.sub(" ", name))
        for candidate in (slug, *_without_prefix(slug)):
            volcano = self._by_slug.get(candidate)
            if volcano is not None:
                return volcano
        return None

    def find_in_text(self, text: str) -> Volcano | None:
        """The volcano whose alias appears earliest in raw text as whole words."""
        haystack = f"_{source_slug(text)}_"
        best: tuple[int, Volcano] | None = None
        for slug in self._text_slugs:
            position = haystack.find(f"_{slug}_")
            if position >= 0 and (best is None or position < best[0]):
                best = (position, self._by_slug[slug])
        return best[1] if best is not None else None

    def by_magma_code(self, code: str) -> Volcano | None:
        return self._by_code.get(code.strip().upper())

    def nearest(self, lat: float, lon: float, max_km: float) -> Volcano | None:
        best: tuple[float, Volcano] | None = None
        for volcano in self._volcanoes:
            distance = haversine_km(lat, lon, volcano.lat, volcano.lon)
            if distance <= max_km and (best is None or distance < best[0]):
                best = (distance, volcano)
        return best[1] if best is not None else None

    def in_bbox(self, bbox: BBox) -> list[Volcano]:
        return [volcano for volcano in self._volcanoes if bbox.contains(volcano.lat, volcano.lon)]

    def _add_slug(self, slug: str, volcano: Volcano) -> None:
        if not slug:
            raise ValueError(f"volcano {volcano.id} has an empty name or alias")
        existing = self._by_slug.get(slug)
        if existing is not None and existing.id != volcano.id:
            raise ValueError(f"alias {slug} names both {existing.id} and {volcano.id}")
        self._by_slug[slug] = volcano


def load_volcanoes(data_dir: Path) -> VolcanoCatalogue:
    catalogue = VolcanoFile.model_validate_json((data_dir / VOLCANO_FILE).read_bytes())
    return VolcanoCatalogue(catalogue.volcanoes)


def _without_prefix(slug: str) -> list[str]:
    return [slug.removeprefix(prefix) for prefix in _NAME_PREFIXES if slug.startswith(prefix)]
