"""Backtest metrics: polygon overlap in a local equal-area projection, and lead time.

All pure code on shapely shapes (research/18f section 1.3 and 1.4). Areas are km^2 in a
Lambert azimuthal equal-area projection centred on the vent, so a ratio of areas is a ratio of
ground areas. Every ratio is ``None`` when its denominator is zero.
"""

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import fmean, median
from typing import Final

import numpy as np
import shapely
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry

from tephra.backtest.models import FootprintLead, LeadSummary, Summary, TickScore
from tephra.geo.cone import AreaGeometry, geometry_to_shape

EARTH_RADIUS_KM: Final = 6371.0088
LEAD_CAP: Final = timedelta(hours=24)
"""Longest lead reported (research/18f 1.4)."""
TAUS: Final = (0.9, 0.5)
"""Coverage thresholds for a footprint to count as covered; 0.9 is the headline."""
EMPTY: Final[BaseGeometry] = Polygon()


@dataclass(frozen=True)
class Footprint:
    """One later official polygon: an advisory step or a SIGMET, with its times and top."""

    footprint_id: str
    volcano_id: str
    issued_at: datetime
    valid_at: datetime
    shape: BaseGeometry
    top_ft: int | None


class Projection:
    """Lambert azimuthal equal-area (spherical) around a vent."""

    def __init__(self, lat: float, lon: float) -> None:
        self._lat0 = math.radians(lat)
        self._lon0 = lon

    def shape(self, geometry: AreaGeometry) -> BaseGeometry:
        """The GeoJSON area as a valid shape in km, x east and y north of the vent."""
        return shapely.transform(geometry_to_shape(geometry, ref_lon=self._lon0), self._xy)

    def point(self, lat: float, lon: float) -> tuple[float, float]:
        x, y = self._xy(np.array([[lon, lat]]))[0]
        return float(x), float(y)

    def _xy(self, coords: np.ndarray) -> np.ndarray:
        lon = np.radians(coords[:, 0] - self._lon0)
        lat = np.radians(coords[:, 1])
        sin0, cos0 = math.sin(self._lat0), math.cos(self._lat0)
        denominator = 1.0 + sin0 * np.sin(lat) + cos0 * np.cos(lat) * np.cos(lon)
        k = np.sqrt(2.0 / np.maximum(denominator, 1e-12))
        x = EARTH_RADIUS_KM * k * np.cos(lat) * np.sin(lon)
        y = EARTH_RADIUS_KM * k * (cos0 * np.sin(lat) - sin0 * np.cos(lat) * np.cos(lon))
        return np.column_stack([x, y])


def union(shapes: Iterable[BaseGeometry]) -> BaseGeometry:
    return shapely.union_all([shape for shape in shapes if not shape.is_empty])


def _ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator > 0 else None


def coverage(zone: BaseGeometry, truth: BaseGeometry) -> float | None:
    """The share of the truth area that the zone contains."""
    return _ratio(zone.intersection(truth).area, truth.area)


def score_tick(
    *,
    t: datetime,
    volcano_id: str,
    cone_mode: str,
    zone: BaseGeometry,
    official: BaseGeometry,
    truth: BaseGeometry,
    footprints: Sequence[Footprint],
    zone_top_ft: int,
    airports: dict[str, BaseGeometry],
    floor_ok: bool,
    input_leaks: int,
) -> TickScore:
    """Score one tick's zone and official-only area against the later footprints' union."""
    z_area, o_area, a_area = zone.area, official.area, truth.area
    cov_z = coverage(zone, truth)
    cov_o = coverage(official, truth)
    gain = None if cov_z is None or cov_o is None else cov_z - cov_o
    inter = zone.intersection(truth).area
    tops = [fp.top_ft for fp in footprints if fp.top_ft is not None]
    scored = a_area > 0 and z_area > 0
    return TickScore(
        t=t,
        volcano_id=volcano_id,
        cone_mode=cone_mode,
        zone_area_km2=z_area,
        official_area_km2=o_area,
        truth_area_km2=a_area,
        footprints=len(footprints),
        coverage=cov_z,
        coverage_official=cov_o,
        coverage_gain=gain,
        overwarn=_ratio(z_area - inter, z_area) if a_area > 0 else None,
        excess_vs_official=_ratio(z_area, o_area),
        bias=_ratio(z_area, a_area),
        csi=_jaccard(zone, truth),
        csi_official=_jaccard(official, truth),
        hausdorff_km=shapely.hausdorff_distance(truth, zone) if scored else None,
        centroid_km=zone.centroid.distance(truth.centroid) if scored else None,
        vertical_hit=(zone_top_ft >= max(tops)) if tops and scored else None,
        airports_in_truth=sorted(icao for icao, spot in airports.items() if truth.covers(spot)),
        airports_covered=sorted(
            icao for icao, spot in airports.items() if truth.covers(spot) and zone.covers(spot)
        ),
        floor_ok=floor_ok,
        input_leaks=input_leaks,
    )


def _jaccard(a: BaseGeometry, b: BaseGeometry) -> float | None:
    return _ratio(a.intersection(b).area, a.union(b).area)


# --- lead time --------------------------------------------------------------------------


def lead_minutes(
    issued_at: datetime, ticks: Sequence[tuple[datetime, bool]], *, cap: timedelta = LEAD_CAP
) -> int | None:
    """Minutes before ``issued_at`` from which every tick up to the last one was covered.

    ``ticks`` are the replay ticks before the issue time with whether each one's area covered
    the footprint (a tick with no zone, or whose zone does not reach the footprint's valid
    time, is ``False``). ``None`` when the last tick before issue was not covered: a miss has
    no lead.
    """
    earliest: datetime | None = None
    for at, covered in sorted(ticks, reverse=True):
        if not covered or issued_at - at > cap:
            break
        earliest = at
    return None if earliest is None else int((issued_at - earliest).total_seconds() // 60)


def footprint_lead(
    footprint: Footprint,
    zone_ticks: Sequence[tuple[datetime, bool]],
    official_ticks: Sequence[tuple[datetime, bool]],
) -> FootprintLead:
    lead_z = lead_minutes(footprint.issued_at, zone_ticks)
    lead_o = lead_minutes(footprint.issued_at, official_ticks)
    return FootprintLead(
        footprint_id=footprint.footprint_id,
        volcano_id=footprint.volcano_id,
        issued_at=footprint.issued_at,
        valid_at=footprint.valid_at,
        lead_zone_min=lead_z,
        lead_official_min=lead_o,
        incremental_min=None if lead_z is None else lead_z - (lead_o or 0),
    )


def summarise_leads(tau: float, leads: Sequence[FootprintLead]) -> LeadSummary:
    covered = [lead for lead in leads if lead.incremental_min is not None]
    increments = [lead.incremental_min for lead in covered if lead.incremental_min is not None]
    return LeadSummary(
        tau=tau,
        n_footprints=len(leads),
        n_missed=len(leads) - len(covered),
        n_covered_before_official=sum(
            lead.lead_official_min is None or (lead.incremental_min or 0) > 0 for lead in covered
        ),
        median_min=float(median(increments)) if increments else None,
        p90_min=float(np.percentile(increments, 90)) if increments else None,
        footprints=list(leads),
    )


# --- roll-ups ---------------------------------------------------------------------------


def summarise(ticks: Sequence[TickScore]) -> Summary:
    scored = [tick for tick in ticks if tick.coverage is not None]

    def mean(values: Iterable[float | None]) -> float | None:
        kept = [value for value in values if value is not None]
        return fmean(kept) if kept else None

    def med(values: Iterable[float | None]) -> float | None:
        kept = [value for value in values if value is not None]
        return float(median(kept)) if kept else None

    hits = [tick.vertical_hit for tick in scored if tick.vertical_hit is not None]
    return Summary(
        ticks_scored=len(scored),
        coverage_mean=mean(t.coverage for t in scored),
        coverage_official_mean=mean(t.coverage_official for t in scored),
        coverage_gain_mean=mean(t.coverage_gain for t in scored),
        overwarn_mean=mean(t.overwarn for t in scored),
        excess_vs_official_mean=mean(t.excess_vs_official for t in scored),
        csi_mean=mean(t.csi for t in scored),
        csi_official_mean=mean(t.csi_official for t in scored),
        hausdorff_km_median=med(t.hausdorff_km for t in scored),
        centroid_km_median=med(t.centroid_km for t in scored),
        vertical_hit_rate=sum(hits) / len(hits) if hits else None,
    )
