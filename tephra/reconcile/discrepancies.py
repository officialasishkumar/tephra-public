"""Which volcanoes are active, which records belong to each, and where the products differ.

Everything here is deterministic code: Gemini explains discrepancies, it never decides what
counts as one. The rules follow research/13, which re-read the two "the sources disagreed"
days against the primary texts:

* A non-observation ("Ash-cloud is not observed", "VA NOT IDENTIFIABLE", a night-time
  observer, an absent product) is an evidence state, never a CONFLICT. CONFLICT needs an
  explicit negative assertion (a VAA saying no ash is expected, or a final VAA that is not
  merely "not identifiable") in force when another product observed ash.
* A SIGMET that repeats a VAA polygon vertex for vertex is the same source twice (the
  Indonesian MWOs copy Darwin's polygon). The two are compared as one unit and named
  together, so an echo never manufactures a disagreement.
* Times are compared on observation time (a SIGMET's ``OBS AT``, a VAA's observation step,
  a VONA's issue time), not on issue or validity times (research/13, data-quality 9).
"""

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Final, Literal

from shapely.geometry import Point, Polygon

from tephra.config import MAX_HORIZON_H, Settings
from tephra.geo.cone import geometry_to_shape, official_layers
from tephra.geo.units import (
    bearing_diff_deg,
    deg_to_compass,
    destination_point,
    ft_to_fl,
    solar_hour,
    unwrap_lon,
)
from tephra.models import (
    BtdResult,
    Discrepancy,
    DiscrepancyKind,
    EvidenceState,
    GeoPolygon,
    RunMode,
    SatelliteFrame,
    Severity,
    Sigmet,
    Situation,
    VaacAdvisory,
    VaacCentre,
    Volcano,
    Vona,
    WindProfile,
)
from tephra.util import timeutil
from tephra.util.hashing import stable_id

if TYPE_CHECKING:
    from tephra.feeds.volcanoes import VolcanoCatalogue

__all__ = [
    "build_situation",
    "evidence_state",
    "find_active",
    "find_discrepancies",
    "select_records",
]

VONA_FRESH_H: Final = 6.0
"""A VONA older than this describes an earlier puff: its evidence state is STALE."""
VAA_LOOKBACK_H: Final = 24.0
"""``select_records`` keeps, per VAAC, the newest VAA issued within this many hours."""
CLOCK_SLACK: Final = timedelta(minutes=5)
"""Products stamped slightly after "now" (feed clocks, replay steps) still count."""
OVERDUE_GRACE_MIN: Final = 10
"""VAAs are polled every 5 minutes; a next advisory this late has really not appeared."""
POLYGON_PROBE_KM: Final = 15.0
"""research/13: 15 km down the VONA direction separates near-vent coverage from drift."""
ECHO_TOLERANCE_DEG: Final = 0.005
"""Vertex tolerance for "same polygon": JSON SIGMET coordinates carry 3 decimals, VAA
coordinates are whole minutes (0.0167 degrees apart), so this cannot merge distinct shapes."""
NIGHT_START_H: Final = 18.0
NIGHT_END_H: Final = 6.0
_KM_PER_DEG_LAT: Final = 110.57
_KM_PER_DEG_LON_EQUATOR: Final = 111.32

_SEVERITY_RANK: Final = {Severity.WARNING: 0, Severity.CAUTION: 1, Severity.INFO: 2}
_KIND_RANK: Final = {kind: index for index, kind in enumerate(DiscrepancyKind)}

Aspect = Literal["presence", "time", "ash_observed", "top", "base", "direction", "polygon"]


# --- activity and record selection ------------------------------------------------------


def find_active(
    catalogue: "VolcanoCatalogue",
    *,
    sigmets: Sequence[Sigmet],
    vonas: Sequence[Vona],
    vaas: Sequence[VaacAdvisory],
    at: datetime,
    settings: Settings,
) -> dict[str, list[str]]:
    """``volcano_id -> reasons``. Reasons are stable texts (no ages) so situations only
    change when the products do."""
    reasons: dict[str, list[str]] = {}

    def add(volcano_id: str, reason: str) -> None:
        held = reasons.setdefault(volcano_id, [])
        if reason not in held:
            held.append(reason)

    seen_vona: set[str] = set()
    for vona in sorted(vonas, key=lambda item: item.issued_at, reverse=True):
        volcano = _vona_volcano(catalogue, vona)
        if volcano is None or volcano.id in seen_vona:
            continue
        if vona.is_recent(at, settings.vona_window_h):
            seen_vona.add(volcano.id)
            ash = "ash reported" if vona.ash_observed else "ash not observed"
            add(volcano.id, f"{_vona_label(vona)} ({vona.color_code.value}, {ash})")
    for vaa in sorted(vaas, key=lambda item: item.issued_at, reverse=True):
        volcano = _vaa_volcano(catalogue, vaa)
        if volcano is not None and vaa.is_current(at):
            add(volcano.id, f"Current {_vaa_label(vaa)}")
    for sigmet in sigmets:
        if not sigmet.is_valid(at):
            continue
        match = _sigmet_volcano(catalogue, sigmet, settings.active_radius_km)
        if match is not None:
            add(match[0].id, f"Valid {_sigmet_label(sigmet)}: {match[1]}")
    return {volcano_id: reasons[volcano_id] for volcano_id in sorted(reasons)}


def select_records(
    catalogue: "VolcanoCatalogue",
    volcano: Volcano,
    *,
    sigmets: Sequence[Sigmet],
    vonas: Sequence[Vona],
    vaas: Sequence[VaacAdvisory],
    at: datetime,
    settings: Settings,
) -> tuple[list[Sigmet], list[Vona], list[VaacAdvisory]]:
    horizon_end = at + timedelta(hours=MAX_HORIZON_H)
    chosen_sigmets = [
        sigmet
        for sigmet in sigmets
        if not sigmet.cancelled
        and (sigmet.is_valid(at) or at < sigmet.valid_from <= horizon_end)
        and _sigmet_belongs(catalogue, sigmet, volcano, settings.active_radius_km)
    ]
    chosen_sigmets.sort(key=lambda item: (item.valid_from, item.series_id), reverse=True)

    chosen_vonas = [
        vona
        for vona in vonas
        if vona.is_recent(at, settings.vona_window_h)
        and _same(_vona_volcano(catalogue, vona), volcano)
    ]
    chosen_vonas.sort(key=lambda item: item.issued_at, reverse=True)

    earliest = at - timedelta(hours=VAA_LOOKBACK_H)
    newest: dict[VaacCentre, VaacAdvisory] = {}
    for vaa in vaas:
        if not earliest <= vaa.issued_at <= at + CLOCK_SLACK:
            continue
        if not _same(_vaa_volcano(catalogue, vaa), volcano):
            continue
        held = newest.get(vaa.vaac)
        if held is None or vaa.issued_at > held.issued_at:
            newest[vaa.vaac] = vaa
    chosen_vaas = sorted(newest.values(), key=lambda item: item.issued_at, reverse=True)
    return chosen_sigmets, chosen_vonas, chosen_vaas


def build_situation(
    volcano: Volcano,
    *,
    active_reasons: list[str],
    sigmets: Sequence[Sigmet],
    vonas: Sequence[Vona],
    vaas: Sequence[VaacAdvisory],
    winds: Sequence[WindProfile],
    frames: Sequence[SatelliteFrame],
    btd: BtdResult | None,
    at: datetime,
    mode: RunMode,
    settings: Settings,
) -> Situation:
    return Situation(
        volcano=volcano,
        as_of=at,
        mode=mode,
        active_reasons=list(active_reasons),
        sigmets=list(sigmets),
        vonas=sorted(vonas, key=lambda item: item.issued_at, reverse=True),
        vaas=sorted(vaas, key=lambda item: item.issued_at, reverse=True),
        winds=_upcoming_winds(winds, at),
        frames=list(frames),
        btd=btd,
        official_layers=official_layers(volcano, sigmets, vaas, at),
        discrepancies=find_discrepancies(
            volcano, sigmets=sigmets, vonas=vonas, vaas=vaas, at=at, settings=settings
        ),
    )


def _upcoming_winds(winds: Sequence[WindProfile], at: datetime) -> list[WindProfile]:
    """Hourly profiles from the current hour to the horizon; if the forecast has run out,
    the newest older profile, so the reader still sees winds (with its own source id)."""
    start = timeutil.floor_minutes(at, 60)
    end = at + timedelta(hours=MAX_HORIZON_H)
    ordered = sorted(winds, key=lambda item: item.valid_at)
    upcoming = [profile for profile in ordered if start <= profile.valid_at <= end]
    if upcoming:
        return upcoming
    older = [profile for profile in ordered if profile.valid_at < start]
    return older[-1:]


# --- evidence states --------------------------------------------------------------------


def evidence_state(
    record: Sigmet | Vona | VaacAdvisory, volcano: Volcano, at: datetime
) -> EvidenceState:
    """What the product actually asserts now, read from its content rather than its label."""
    if isinstance(record, Sigmet):
        return _sigmet_evidence(record, at)
    if isinstance(record, Vona):
        return _vona_evidence(record, volcano, at)
    return _vaa_evidence(record, at)


def _sigmet_evidence(sigmet: Sigmet, at: datetime) -> EvidenceState:
    if sigmet.cancelled or at > sigmet.valid_to:
        return EvidenceState.STALE
    if sigmet.observed:
        return EvidenceState.OBSERVED_SAT
    if sigmet.observed is False:
        return EvidenceState.ESTIMATED
    return EvidenceState.UNKNOWN


def _vona_evidence(vona: Vona, volcano: Volcano, at: datetime) -> EvidenceState:
    if not vona.is_recent(at, VONA_FRESH_H):
        return EvidenceState.STALE
    if not vona.ash_observed:
        # MAGMA gives no reason for "not observed"; a ground observer after dark is the
        # usual one (research/13, 7 Oct). Solar time is a coarse, labelled proxy for dark.
        return EvidenceState.NIGHT_BLIND if _is_night(volcano, vona) else EvidenceState.NOT_OBSERVED
    if vona.source_text and "satellite" in vona.source_text.lower():
        return EvidenceState.OBSERVED_SAT
    return EvidenceState.OBSERVED_GROUND


def _vaa_evidence(vaa: VaacAdvisory, at: datetime) -> EvidenceState:
    if not vaa.is_current(at):
        return EvidenceState.STALE
    obs = vaa.observation
    if obs is not None and obs.layers:
        return EvidenceState.ESTIMATED if obs.estimated else EvidenceState.OBSERVED_SAT
    if obs is not None and obs.not_identifiable:
        return EvidenceState.NOT_IDENTIFIABLE
    if _vaa_negative(vaa):
        return EvidenceState.NO_VA_EXPECTED
    if vaa.forecasts and all(step.not_available for step in vaa.forecasts):
        return EvidenceState.FORECAST_NOT_AVAILABLE
    return EvidenceState.UNKNOWN


def _is_night(volcano: Volcano, vona: Vona) -> bool:
    hour = solar_hour(volcano.lon, vona.issued_at)
    return hour >= NIGHT_START_H or hour < NIGHT_END_H


def _vaa_negative(vaa: VaacAdvisory) -> bool:
    """An explicit "no ash": NO VA EXP, or a final VAA that is not just "not identifiable".

    "NO FURTHER ADVISORIES" after "VA NOT IDENTIFIABLE" means the VAAC could not see it,
    which is a non-observation, not an all-clear.
    """
    obs = vaa.observation
    if obs is not None and obs.layers:
        return False
    if obs is not None and obs.no_ash_expected:
        return True
    if vaa.final and not (obs is not None and obs.not_identifiable):
        return True
    return bool(vaa.forecasts) and all(step.no_ash_expected for step in vaa.forecasts)


# --- discrepancies ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Unit:
    """One product as compared: a SIGMET (with any VAA it echoes), a VAA, or a VONA."""

    kind: Literal["SIGMET", "VAA", "VONA"]
    label: str
    source_ids: tuple[str, ...]
    obs_time: datetime
    valid_from: datetime
    valid_to: datetime
    base_ft: int | None
    top_ft: int | None
    toward_deg: float | None
    stationary: bool
    polygon: GeoPolygon | None
    height_text: str
    movement_text: str
    positive: bool
    negative: bool

    def valid_at(self, at: datetime) -> bool:
        return self.valid_from <= at <= self.valid_to


def find_discrepancies(
    volcano: Volcano,
    *,
    sigmets: Sequence[Sigmet],
    vonas: Sequence[Vona],
    vaas: Sequence[VaacAdvisory],
    at: datetime,
    settings: Settings,
) -> list[Discrepancy]:
    sigmet_units, vaa_units = _official_units(sigmets, vaas, at)
    official_now = [unit for unit in sigmet_units if unit.valid_at(at)] + vaa_units
    finder = _Finder(volcano, settings)

    for index, first in enumerate(official_now):
        for second in official_now[index + 1 :]:
            finder.lag(first, second)
            finder.height(first, second)
            finder.direction(first, second)

    ordered_vonas = sorted(vonas, key=lambda item: item.issued_at, reverse=True)
    latest = ordered_vonas[0] if ordered_vonas else None
    with_top = _first(v for v in ordered_vonas if v.ash_observed and v.cloud_top_ft is not None)
    with_direction = _first(
        v for v in ordered_vonas if v.ash_observed and v.movement_toward_deg is not None
    )
    if latest is not None:
        for other in _comparators(latest, sigmet_units, vaa_units, at):
            finder.lag(_vona_unit(latest, volcano, at), other)
    if with_top is not None:
        for other in _comparators(with_top, sigmet_units, vaa_units, at):
            finder.height(_vona_unit(with_top, volcano, at), other)
    if with_direction is not None:
        unit = _vona_unit(with_direction, volcano, at)
        for other in _comparators(with_direction, sigmet_units, vaa_units, at):
            finder.direction(unit, other)
        for other in sigmet_units:
            if other.valid_at(with_direction.issued_at):
                finder.polygon(unit, other)

    vona_units = [_vona_unit(vona, volcano, at) for vona in ordered_vonas]
    finder.conflicts([*sigmet_units, *vaa_units, *vona_units], at)
    finder.silence_after_vona(ordered_vonas, vaas, at)
    finder.silence_without_vaa(sigmet_units, any(vaa.is_current(at) for vaa in vaas), at)
    finder.overdue_vaas(vaas, at)
    return finder.result()


def _first[T](items: Iterable[T]) -> T | None:
    return next(iter(items), None)


def _comparators(
    vona: Vona, sigmet_units: Sequence[_Unit], vaa_units: Sequence[_Unit], at: datetime
) -> list[_Unit]:
    """SIGMETs in force when the VONA was issued (else those in force now), plus the VAAs.

    Pairing a VONA with the SIGMET valid at its own time is what makes the comparison fair:
    research/13 shows the cited 25 Sep pair was 37 hours apart, a LAG, while the SIGMET in
    force at the VONA's time disagreed with it on direction.
    """
    at_vona_time = [unit for unit in sigmet_units if unit.valid_at(vona.issued_at)]
    sigmets_now = at_vona_time or [unit for unit in sigmet_units if unit.valid_at(at)]
    return [*sigmets_now, *vaa_units]


class _Finder:
    def __init__(self, volcano: Volcano, settings: Settings) -> None:
        self._volcano = volcano
        self._settings = settings
        self._found: dict[str, Discrepancy] = {}

    def result(self) -> list[Discrepancy]:
        return sorted(
            self._found.values(),
            key=lambda d: (_SEVERITY_RANK[d.severity], _KIND_RANK[d.kind], d.aspect, d.id),
        )

    def _add(
        self,
        kind: DiscrepancyKind,
        aspect: Aspect,
        values: dict[str, str],
        summary: str,
        magnitude: float | None = None,
        unit: Literal["ft", "deg", "min"] | None = None,
    ) -> None:
        source_ids = sorted(values)
        discrepancy = Discrepancy(
            id=stable_id("D", kind.value, aspect, *source_ids, length=8),
            volcano_id=self._volcano.id,
            kind=kind,
            aspect=aspect,
            source_ids=source_ids,
            values=dict(sorted(values.items())),
            magnitude=magnitude,
            unit=unit,
            summary=summary,
        )
        self._found.setdefault(discrepancy.id, discrepancy)

    # LAG ---------------------------------------------------------------------------------

    def lag(self, first: _Unit, second: _Unit) -> None:
        minutes = abs(timeutil.minutes_between(first.obs_time, second.obs_time))
        if minutes <= self._settings.lag_threshold_min:
            return
        older, newer = sorted((first, second), key=lambda unit: unit.obs_time)
        summary = f"{older.label} observation is {_duration(minutes)} older than {newer.label}"
        for unit in (older, newer):
            if unit.kind == "VONA" and not unit.positive:
                summary += f"; {unit.label} reports activity it could not observe (not a conflict)"
        values = {
            **_values(older, f"OBS {timeutil.hhmmz(older.obs_time)}"),
            **_values(newer, f"OBS {timeutil.hhmmz(newer.obs_time)}"),
        }
        self._add(DiscrepancyKind.LAG, "time", values, summary, round(minutes), "min")

    # heights -----------------------------------------------------------------------------

    def height(self, first: _Unit, second: _Unit) -> None:
        if first.kind == "VONA" or second.kind == "VONA":
            point, band = (first, second) if first.kind == "VONA" else (second, first)
            if point.top_ft is not None and band.top_ft is not None:
                self._point_in_band(point, point.top_ft, band, band.base_ft or 0, band.top_ft)
        elif first.top_ft is not None and second.top_ft is not None:
            if first.top_ft != second.top_ft:
                self._band_vs_band(first, first.top_ft, second, second.top_ft)

    def _point_in_band(
        self, point: _Unit, point_top: int, band: _Unit, band_base: int, band_top: int
    ) -> None:
        """A VONA gives a single top, so it is a point checked against an official band."""
        tolerance = self._settings.height_tolerance_ft
        values = {**_values(point, point.height_text), **_values(band, band.height_text)}
        if band_base <= point_top <= band_top:
            summary = f"{point.label} {point.height_text} inside {band.label} {band.height_text}"
            magnitude = point_top - band_top
            self._add(DiscrepancyKind.ENVELOPE, "top", values, summary, magnitude, "ft")
            return
        above = point_top > band_top
        distance = point_top - band_top if above else band_base - point_top
        aspect: Aspect = "top" if above else "base"
        where = "above" if above else "below"
        summary = (
            f"{point.label} {point.height_text} is {distance:,} ft {where} "
            f"{band.label} {band.height_text}"
        )
        signed = distance if above else -distance
        if distance <= tolerance:
            summary += f" (within the {tolerance:,} ft tolerance)"
            self._add(DiscrepancyKind.ENVELOPE, aspect, values, summary, signed, "ft")
        else:
            self._add(DiscrepancyKind.HEIGHT_MISMATCH, aspect, values, summary, signed, "ft")

    def _band_vs_band(self, first: _Unit, first_top: int, second: _Unit, second_top: int) -> None:
        if first_top < second_top:
            lower, lower_top, higher, higher_top = first, first_top, second, second_top
        else:
            lower, lower_top, higher, higher_top = second, second_top, first, first_top
        difference = higher_top - lower_top
        inside = (higher.base_ft or 0) <= lower_top
        values = {**_values(lower, lower.height_text), **_values(higher, higher.height_text)}
        summary = (
            f"{lower.label} {lower.height_text} tops out {difference:,} ft below "
            f"{higher.label} {higher.height_text}"
        )
        if inside or difference <= self._settings.height_tolerance_ft:
            self._add(DiscrepancyKind.ENVELOPE, "top", values, summary, -difference, "ft")
        else:
            self._add(DiscrepancyKind.HEIGHT_MISMATCH, "top", values, summary, -difference, "ft")

    # directions --------------------------------------------------------------------------

    def direction(self, first: _Unit, second: _Unit) -> None:
        if first.toward_deg is None or second.toward_deg is None:
            return
        if first.stationary or second.stationary:
            return
        difference = bearing_diff_deg(first.toward_deg, second.toward_deg)
        if difference <= self._settings.direction_tolerance_deg:
            return
        values = {**_values(first, first.movement_text), **_values(second, second.movement_text)}
        summary = (
            f"{first.label} {first.movement_text} vs {second.label} {second.movement_text}: "
            f"{difference:.0f} deg apart"
        )
        self._add(
            DiscrepancyKind.DIRECTION_MISMATCH,
            "direction",
            values,
            summary,
            round(difference, 1),
            "deg",
        )

    def polygon(self, vona: _Unit, sigmet: _Unit) -> None:
        if vona.toward_deg is None or sigmet.polygon is None:
            return
        volcano = self._volcano
        lat, lon = destination_point(volcano.lat, volcano.lon, vona.toward_deg, POLYGON_PROBE_KM)
        shape = geometry_to_shape(sigmet.polygon, ref_lon=volcano.lon)
        if shape.covers(Point(unwrap_lon(lon, volcano.lon), lat)):
            return
        compass = deg_to_compass(vona.toward_deg)
        values = {**_values(vona, vona.movement_text), **_values(sigmet, "polygon")}
        summary = (
            f"A point {POLYGON_PROBE_KM:.0f} km {compass} of the vent ({vona.label} drift) "
            f"lies outside the {sigmet.label} polygon"
        )
        self._add(DiscrepancyKind.DIRECTION_MISMATCH, "polygon", values, summary)

    # CONFLICT ----------------------------------------------------------------------------

    def conflicts(self, units: Sequence[_Unit], at: datetime) -> None:
        """A negative VAA in force at the time another product observed ash after it.

        A positive observation older than the negative VAA is not a conflict: the VAA is the
        newer word, and the gap shows up as LAG.
        """
        for negative in units:
            if not negative.negative or not negative.valid_at(at):
                continue
            for positive in units:
                if not positive.positive or set(positive.source_ids) & set(negative.source_ids):
                    continue
                if not negative.obs_time <= positive.obs_time <= negative.valid_to:
                    continue
                minutes = timeutil.minutes_between(negative.obs_time, positive.obs_time)
                values = {
                    **_values(negative, negative.height_text),
                    **_values(positive, positive.height_text),
                }
                summary = (
                    f"{negative.label} says no ash ({negative.height_text}) while "
                    f"{positive.label} observed ash {_duration(minutes)} after it"
                )
                self._add(
                    DiscrepancyKind.CONFLICT,
                    "ash_observed",
                    values,
                    summary,
                    round(minutes),
                    "min",
                )

    # SILENCE -----------------------------------------------------------------------------

    def silence_after_vona(
        self, vonas: Sequence[Vona], vaas: Sequence[VaacAdvisory], at: datetime
    ) -> None:
        """The oldest VONA with ash that no VAA has followed yet: silence since then."""
        unanswered = [
            vona
            for vona in vonas
            if vona.ash_observed and not any(vaa.issued_at >= vona.issued_at for vaa in vaas)
        ]
        if not unanswered:
            return
        oldest = min(unanswered, key=lambda vona: vona.issued_at)
        minutes = timeutil.minutes_between(oldest.issued_at, at)
        if minutes <= self._settings.silence_threshold_min:
            return
        label = _vona_label(oldest)
        values = {oldest.provenance.source_id: f"ash {_vona_height_text(oldest)}"}
        summary = f"No VAA issued since {label} reported ash ({_duration(minutes)})"
        self._add(DiscrepancyKind.SILENCE, "presence", values, summary, round(minutes), "min")

    def silence_without_vaa(
        self, sigmet_units: Sequence[_Unit], has_current_vaa: bool, at: datetime
    ) -> None:
        if has_current_vaa:
            return
        for unit in sigmet_units:
            if not unit.valid_at(at):
                continue
            minutes = timeutil.minutes_between(unit.valid_from, at)
            if minutes <= self._settings.silence_threshold_min:
                continue
            summary = f"{unit.label} in force with no current VAA ({_duration(minutes)})"
            values = _values(unit, unit.height_text)
            self._add(DiscrepancyKind.SILENCE, "presence", values, summary, round(minutes), "min")

    def overdue_vaas(self, vaas: Sequence[VaacAdvisory], at: datetime) -> None:
        for vaa in _latest_per_vaac(vaas):
            if vaa.final or vaa.next_advisory_at is None:
                continue
            minutes = timeutil.minutes_between(vaa.next_advisory_at, at)
            if minutes <= OVERDUE_GRACE_MIN:
                continue
            label = _vaa_label(vaa)
            values = {vaa.provenance.source_id: f"NXT {timeutil.hhmmz(vaa.next_advisory_at)}"}
            summary = f"{label} next advisory overdue by {_duration(minutes)}"
            self._add(DiscrepancyKind.SILENCE, "presence", values, summary, round(minutes), "min")


# --- building comparison units ----------------------------------------------------------


def _official_units(
    sigmets: Sequence[Sigmet], vaas: Sequence[VaacAdvisory], at: datetime
) -> tuple[list[_Unit], list[_Unit]]:
    """SIGMET units (each merged with any current VAA it echoes) and the remaining VAAs.

    Only a SIGMET in force now absorbs its VAA: a VAA outlives the SIGMET that copied it by
    up to an hour, and must then be compared in its own right.
    """
    current = [vaa for vaa in _latest_per_vaac(vaas) if vaa.is_current(at)]
    observed = sorted(
        (s for s in sigmets if not s.cancelled and s.observed is not False),
        key=lambda item: item.valid_from,
        reverse=True,
    )
    echoed: set[str] = set()
    sigmet_units: list[_Unit] = []
    for sigmet in observed:
        twins = [
            vaa
            for vaa in current
            if sigmet.is_valid(at)
            and vaa.provenance.source_id not in echoed
            and _echoes(sigmet, vaa)
        ]
        echoed.update(vaa.provenance.source_id for vaa in twins)
        sigmet_units.append(_sigmet_unit(sigmet, twins))
    vaa_units = [_vaa_unit(vaa) for vaa in current if vaa.provenance.source_id not in echoed]
    return sigmet_units, vaa_units


def _latest_per_vaac(vaas: Sequence[VaacAdvisory]) -> list[VaacAdvisory]:
    latest: dict[VaacCentre, VaacAdvisory] = {}
    for vaa in vaas:
        held = latest.get(vaa.vaac)
        if held is None or vaa.issued_at > held.issued_at:
            latest[vaa.vaac] = vaa
    return sorted(latest.values(), key=lambda item: item.vaac.value)


def _echoes(sigmet: Sigmet, vaa: VaacAdvisory) -> bool:
    if sigmet.polygon is None or vaa.observation is None:
        return False
    return any(
        layer.polygon is not None and _same_ring(sigmet.polygon, layer.polygon)
        for layer in vaa.observation.layers
    )


def _same_ring(first: GeoPolygon, second: GeoPolygon) -> bool:
    """Vertex-for-vertex equality of exterior rings, allowing a different start vertex or
    winding (a SIGMET may close the ring a VAA leaves open; both are closed by now)."""
    a = first.coordinates[0][:-1]
    b = second.coordinates[0][:-1]
    if len(a) != len(b) or not a:
        return False
    for candidate in (b, b[::-1]):
        for shift in range(len(candidate)):
            rotated = candidate[shift:] + candidate[:shift]
            if all(_close(p, q) for p, q in zip(a, rotated, strict=True)):
                return True
    return False


def _close(p: tuple[float, float], q: tuple[float, float]) -> bool:
    return abs(p[0] - q[0]) <= ECHO_TOLERANCE_DEG and abs(p[1] - q[1]) <= ECHO_TOLERANCE_DEG


def _sigmet_unit(sigmet: Sigmet, twins: Sequence[VaacAdvisory]) -> _Unit:
    label = " = ".join([_sigmet_label(sigmet), *(_vaa_label(vaa) for vaa in twins)])
    obs_time = sigmet.observed_at or sigmet.provenance.issued_at or sigmet.valid_from
    return _Unit(
        kind="SIGMET",
        label=label,
        source_ids=(sigmet.provenance.source_id, *(vaa.provenance.source_id for vaa in twins)),
        obs_time=obs_time,
        valid_from=sigmet.valid_from,
        valid_to=sigmet.valid_to,
        base_ft=sigmet.base_ft,
        top_ft=sigmet.top_ft,
        toward_deg=sigmet.movement_toward_deg,
        stationary=sigmet.stationary,
        polygon=sigmet.polygon,
        height_text=_band_text(sigmet.base_ft, sigmet.top_ft),
        movement_text=_movement_text(
            sigmet.movement_toward_deg, sigmet.movement_speed_kt, sigmet.stationary
        ),
        positive=bool(sigmet.observed),
        negative=False,
    )


def _vaa_unit(vaa: VaacAdvisory) -> _Unit:
    obs = vaa.observation
    layers = obs.layers if obs is not None else []
    base = min((layer.base_ft for layer in layers), default=None)
    top = max((layer.top_ft for layer in layers), default=None)
    moving = next((layer for layer in layers if layer.movement_toward_deg is not None), None)
    negative = _vaa_negative(vaa)
    if layers:
        height_text = _band_text(base or 0, top)
    elif negative:
        height_text = "NO VA EXP" if not vaa.final else "NO FURTHER ADVISORIES"
    elif obs is not None and obs.not_identifiable:
        height_text = "VA NOT IDENTIFIABLE"
    else:
        height_text = "no observed layer"
    return _Unit(
        kind="VAA",
        label=_vaa_label(vaa),
        source_ids=(vaa.provenance.source_id,),
        obs_time=obs.valid_at if obs is not None else vaa.issued_at,
        valid_from=vaa.issued_at,
        valid_to=vaa.valid_until(),
        base_ft=base,
        top_ft=top,
        toward_deg=moving.movement_toward_deg if moving is not None else None,
        stationary=False,
        polygon=None,
        height_text=height_text,
        movement_text=_movement_text(
            moving.movement_toward_deg if moving else None,
            moving.movement_speed_kt if moving else None,
            False,
        ),
        positive=bool(layers),
        negative=negative,
    )


def _vona_unit(vona: Vona, volcano: Volcano, at: datetime) -> _Unit:
    state = _vona_evidence(vona, volcano, at)
    direction = vona.movement_toward_deg
    return _Unit(
        kind="VONA",
        label=_vona_label(vona),
        source_ids=(vona.provenance.source_id,),
        obs_time=vona.issued_at,
        valid_from=vona.issued_at,
        valid_to=vona.issued_at + timedelta(hours=VONA_FRESH_H),
        base_ft=None,
        top_ft=vona.cloud_top_ft if vona.ash_observed else None,
        toward_deg=direction if vona.ash_observed else None,
        stationary=False,
        polygon=None,
        height_text=_vona_height_text(vona) if vona.ash_observed else _non_observation(state),
        movement_text=f"moving {deg_to_compass(direction)}" if direction is not None else "",
        positive=vona.ash_observed,
        negative=False,
    )


def _non_observation(state: EvidenceState) -> str:
    if state is EvidenceState.NIGHT_BLIND:
        return "ash not observed (night)"
    return "ash not observed"


# --- labels and display values ----------------------------------------------------------


def _values(unit: _Unit, value: str) -> dict[str, str]:
    return dict.fromkeys(unit.source_ids, value)


def _sigmet_label(sigmet: Sigmet) -> str:
    return f"SIGMET {sigmet.fir_id} {sigmet.series_id}"


def _vaa_label(vaa: VaacAdvisory) -> str:
    return f"VAA {vaa.vaac.value} {vaa.advisory_nr}"


def _vona_label(vona: Vona) -> str:
    if vona.notice_number:
        return f"VONA {vona.notice_number}"
    if vona.magma_id is not None:
        return f"VONA {vona.volcano_name.upper()} #{vona.magma_id}"
    return f"VONA {vona.volcano_name.upper()}"


def _vona_height_text(vona: Vona) -> str:
    if vona.cloud_top_ft is None:
        return "height not given"
    if vona.cloud_top_m is not None:
        return f"{vona.cloud_top_ft:,} ft ({vona.cloud_top_m:,} m)"
    return f"{vona.cloud_top_ft:,} ft"


def _band_text(base_ft: int, top_ft: int | None) -> str:
    base = "SFC" if base_ft <= 0 else f"FL{ft_to_fl(base_ft):03d}"
    top = "TOP NOT STATED" if top_ft is None else f"FL{ft_to_fl(top_ft):03d}"
    return f"{base}/{top}"


def _movement_text(toward_deg: float | None, speed_kt: float | None, stationary: bool) -> str:
    if stationary:
        return "STNR"
    if toward_deg is None:
        return "movement not stated"
    text = f"MOV {deg_to_compass(toward_deg)}"
    return f"{text} {speed_kt:02.0f}KT" if speed_kt is not None else text


def _duration(minutes: float) -> str:
    whole = round(abs(minutes))
    if whole < 120:
        return f"{whole} min"
    hours, rest = divmod(whole, 60)
    return f"{hours} h {rest} min"


# --- which volcano a record belongs to --------------------------------------------------


def _same(found: Volcano | None, volcano: Volcano) -> bool:
    return found is not None and found.id == volcano.id


def _vona_volcano(catalogue: "VolcanoCatalogue", vona: Vona) -> Volcano | None:
    if vona.volcano_code:
        by_code = catalogue.by_magma_code(vona.volcano_code)
        if by_code is not None:
            return by_code
    return catalogue.resolve(vona.volcano_name)


def _vaa_volcano(catalogue: "VolcanoCatalogue", vaa: VaacAdvisory) -> Volcano | None:
    if vaa.volcano_number:
        by_number = catalogue.get(vaa.volcano_number)
        if by_number is not None:
            return by_number
    return catalogue.resolve(vaa.volcano_name) or catalogue.find_in_text(vaa.raw_text)


def _sigmet_belongs(
    catalogue: "VolcanoCatalogue", sigmet: Sigmet, volcano: Volcano, radius_km: float
) -> bool:
    match = _sigmet_volcano(catalogue, sigmet, radius_km)
    return match is not None and match[0].id == volcano.id


def _sigmet_volcano(
    catalogue: "VolcanoCatalogue", sigmet: Sigmet, radius_km: float
) -> tuple[Volcano, str] | None:
    """The volcano a SIGMET is about, and why.

    A SIGMET that names a volcano belongs to that volcano only; proximity would otherwise
    activate every neighbour of an erupting vent (Bromo, Raung and Kelud all lie within
    300 km of Semeru). Proximity decides only for a SIGMET whose name the catalogue does not
    know, and then the nearest vent within ``radius_km`` takes it.
    """
    named = catalogue.find_in_text(sigmet.raw_text)
    if named is None and sigmet.volcano_name:
        named = catalogue.resolve(sigmet.volcano_name)
    if named is not None:
        return named, "names it"
    if sigmet.polygon is None:
        return None
    distances = [
        (_polygon_distance_km(sigmet.polygon, volcano.lat, volcano.lon), volcano)
        for volcano in catalogue.all()
    ]
    within = [(km, volcano) for km, volcano in distances if km <= radius_km]
    if not within:
        return None
    km, nearest = min(within, key=lambda item: (item[0], item[1].id))
    return nearest, f"polygon {km:.0f} km from the vent"


def _polygon_distance_km(polygon: GeoPolygon, lat: float, lon: float) -> float:
    """Distance from a point to a polygon (0 inside), on a local equirectangular plane.

    Over a few hundred kilometres near the tropics the plane's error is well under 1 %,
    far below the 300 km activity radius it is compared with.
    """
    kx = _KM_PER_DEG_LON_EQUATOR * math.cos(math.radians(lat))
    ring = [
        ((unwrap_lon(p_lon, lon) - lon) * kx, (p_lat - lat) * _KM_PER_DEG_LAT)
        for p_lon, p_lat in polygon.coordinates[0]
    ]
    shape = Polygon(ring)
    if not shape.is_valid:
        shape = shape.buffer(0)
    return float(shape.distance(Point(0.0, 0.0)))
