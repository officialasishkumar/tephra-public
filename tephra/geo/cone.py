"""The official floor and the hazard cone built on top of it.

The cone is a planar union in lon/lat degrees. That is adequate at the regional scale of a
plume (a few hundred kilometres) and keeps every official vertex exactly where the feed put
it: the union is never simplified, buffered inward or clipped, so the cone always covers
every official polygon. Longitudes are unwrapped around a reference meridian so a shape
crossing the antimeridian stays continuous (outside TEPHRA's JAPAC scope, but guarded); in
that case GeoJSON longitudes may exceed 180, which MapLibre draws correctly.
"""

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Final

import shapely
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.geometry.polygon import orient

from tephra.config import MAX_HORIZON_H
from tephra.geo.units import destination_point, ft_to_fl, sector_width_deg, unwrap_lon
from tephra.models import (
    GeoMultiPolygon,
    GeoPolygon,
    HazardCone,
    OfficialLayer,
    PlumeAssessment,
    PlumeMode,
    Position,
    Sigmet,
    Situation,
    VaacAdvisory,
    VaacCentre,
    VaacStep,
    Volcano,
)
from tephra.util.hashing import stable_id

FORECAST_WINDOW_H: Final = 3.0
"""A VAA forecast polygon stands for +/- this many hours around its step time."""

UNKNOWN_TOP_FT: Final = 60_000
"""A SIGMET polygon with no stated top is binding all the way up (FL600), never dropped."""

AREA_TOLERANCE_DEG2: Final = 1e-12
"""About 0.01 square metres: noding slack in coverage checks, and the least area a sector has."""

AreaGeometry = GeoPolygon | GeoMultiPolygon


# --- official floor ---------------------------------------------------------------------


def official_layers(
    volcano: Volcano, sigmets: Sequence[Sigmet], vaas: Sequence[VaacAdvisory], at: datetime
) -> list[OfficialLayer]:
    layers = [layer for sigmet in sigmets if (layer := _sigmet_layer(sigmet, volcano)) is not None]
    for vaa in _latest_current_per_vaac(vaas, at):
        layers.extend(_vaa_layers(vaa, volcano))
    horizon_end = at + timedelta(hours=MAX_HORIZON_H)
    kept = [layer for layer in layers if layer.valid_to >= at and layer.valid_from <= horizon_end]
    return sorted(kept, key=_layer_order)


def _layer_order(layer: OfficialLayer) -> tuple[bool, datetime, str, str]:
    return layer.kind != "SIGMET", layer.valid_from, layer.source_id, layer.label


def _sigmet_layer(sigmet: Sigmet, volcano: Volcano) -> OfficialLayer | None:
    if sigmet.cancelled or sigmet.polygon is None:
        return None
    label = f"SIGMET {sigmet.fir_id} {sigmet.series_id}"
    if sigmet.top_ft is None:
        label += " TOP NOT STATED"
    return OfficialLayer(
        source_id=sigmet.provenance.source_id,
        kind="SIGMET",
        layer="SIGMET",
        label=label,
        volcano_id=volcano.id,
        polygon=sigmet.polygon,
        base_ft=sigmet.base_ft,
        top_ft=sigmet.top_ft if sigmet.top_ft is not None else UNKNOWN_TOP_FT,
        valid_from=sigmet.valid_from,
        valid_to=sigmet.valid_to,
    )


def _latest_current_per_vaac(vaas: Sequence[VaacAdvisory], at: datetime) -> list[VaacAdvisory]:
    """The newest advisory each VAAC had issued by ``at``, if it is still current.

    A newer advisory replaces the older one even after it lapses (a final VAA, for
    instance), so a superseded advisory never comes back as the official floor.
    """
    latest: dict[VaacCentre, VaacAdvisory] = {}
    for vaa in vaas:
        if vaa.issued_at > at:
            continue
        held = latest.get(vaa.vaac)
        if held is None or vaa.issued_at > held.issued_at:
            latest[vaa.vaac] = vaa
    return [vaa for vaa in latest.values() if vaa.is_current(at)]


def _vaa_layers(vaa: VaacAdvisory, volcano: Volcano) -> list[OfficialLayer]:
    layers: list[OfficialLayer] = []
    obs = vaa.observation
    if obs is not None:
        end = max(obs.valid_at, vaa.valid_until())
        name = "EST" if obs.estimated else "OBS"
        bounds = (obs.valid_at, end)
        layers.extend(_step_layers(vaa, obs, volcano, layer="OBS", name=name, window=bounds))
    window = timedelta(hours=FORECAST_WINDOW_H)
    for step in vaa.forecasts:
        layer = f"FCST+{step.offset_h}H"
        bounds = (step.valid_at - window, step.valid_at + window)
        layers.extend(_step_layers(vaa, step, volcano, layer=layer, name=layer, window=bounds))
    return layers


def _step_layers(
    vaa: VaacAdvisory,
    step: VaacStep,
    volcano: Volcano,
    *,
    layer: str,
    name: str,
    window: tuple[datetime, datetime],
) -> list[OfficialLayer]:
    drawn = [(va, va.polygon) for va in step.layers if va.polygon is not None]
    result: list[OfficialLayer] = []
    for va, polygon in drawn:
        label = f"VAA {vaa.vaac.value} {vaa.advisory_nr} {name}"
        if len(drawn) > 1:
            label += f" {_band_text(va.base_ft, va.top_ft)}"
        result.append(
            OfficialLayer(
                source_id=vaa.provenance.source_id,
                kind="VAA",
                layer=layer,
                label=label,
                volcano_id=volcano.id,
                polygon=polygon,
                base_ft=va.base_ft,
                top_ft=va.top_ft,
                valid_from=window[0],
                valid_to=window[1],
            )
        )
    return result


def _band_text(base_ft: int, top_ft: int) -> str:
    base = "SFC" if base_ft <= 0 else f"FL{ft_to_fl(base_ft):03d}"
    return f"{base}/FL{ft_to_fl(top_ft):03d}"


# --- sector and cone --------------------------------------------------------------------


def sector_polygon(
    lat: float,
    lon: float,
    bearing_from_deg: float,
    bearing_to_deg: float,
    extent_km: float,
    *,
    steps: int = 32,
) -> GeoPolygon | None:
    """Wedge from the vent sweeping clockwise; a 360 degree sweep is a disc.

    A sweep or radius too small to enclose any area gives None, like a zero one, so a
    sector is never a degenerate sliver that the union would silently drop.
    """
    width = sector_width_deg(bearing_from_deg, bearing_to_deg)
    if extent_km <= 0 or width <= 0:
        return None
    segments = max(steps, 3)
    if width >= 360.0:
        ring = [_arc_vertex(lat, lon, 360.0 * i / segments, extent_km) for i in range(segments)]
    else:
        arc = [
            _arc_vertex(lat, lon, bearing_from_deg + width * i / segments, extent_km)
            for i in range(segments + 1)
        ]
        ring = [(lon, lat), *arc]
    ring.append(ring[0])
    if Polygon(ring).area <= AREA_TOLERANCE_DEG2:
        return None
    return GeoPolygon(coordinates=[ring])


def _arc_vertex(lat: float, lon: float, bearing_deg: float, extent_km: float) -> Position:
    vertex_lat, vertex_lon = destination_point(lat, lon, bearing_deg % 360.0, extent_km)
    return unwrap_lon(vertex_lon, lon), vertex_lat


def build_cone(situation: Situation, assessment: PlumeAssessment) -> HazardCone:
    estimate = assessment.estimate
    volcano = situation.volcano
    layers = situation.official_layers
    sector = None
    if estimate.mode is not PlumeMode.OFFICIAL:
        sector = sector_polygon(
            volcano.lat,
            volcano.lon,
            estimate.bearing_from_deg,
            estimate.bearing_to_deg,
            estimate.extent_km,
        )
    parts: list[AreaGeometry] = [layer.polygon for layer in layers]
    if sector is not None:
        parts.append(sector)
    geometry = None
    if parts:
        shapes = [geometry_to_shape(part, ref_lon=volcano.lon) for part in parts]
        geometry = shape_to_geometry(shapely.unary_union(shapes))
    return HazardCone(
        id=stable_id("CONE", volcano.id, assessment.id),
        volcano_id=volcano.id,
        assessment_id=assessment.id,
        mode=estimate.mode,
        confidence=estimate.confidence,
        llm_backend=assessment.llm_backend,
        created_at=situation.as_of,
        horizon_h=estimate.horizon_h,
        valid_to=assessment.created_at + timedelta(hours=estimate.horizon_h),
        geometry=geometry,
        sector=sector,
        base_ft=min([estimate.base_fl * 100, *(layer.base_ft for layer in layers)]),
        top_ft=max([estimate.top_fl * 100, *(layer.top_ft for layer in layers)]),
        official_source_ids=sorted({layer.source_id for layer in layers}),
    )


# --- checks and measures ----------------------------------------------------------------


def covers_official(cone: HazardCone, layers: Sequence[OfficialLayer]) -> bool:
    """True when the cone contains every layer, laterally and in its vertical band."""
    if not layers:
        return True
    if cone.geometry is None:
        return False
    ref_lon = _reference_lon(cone.geometry)
    shape = geometry_to_shape(cone.geometry, ref_lon=ref_lon)
    shapely.prepare(shape)
    return all(
        cone.base_ft <= layer.base_ft
        and cone.top_ft >= layer.top_ft
        and _covers(shape, geometry_to_shape(layer.polygon, ref_lon=ref_lon))
        for layer in layers
    )


def _covers(shape: BaseGeometry, part: BaseGeometry) -> bool:
    return bool(shape.covers(part)) or part.difference(shape).area <= AREA_TOLERANCE_DEG2


def polygon_iou(a: AreaGeometry, b: AreaGeometry) -> float:
    """Intersection over union, computed on degree areas.

    IoU is a ratio, so the cos(latitude) scale of a degree of longitude cancels; only its
    variation across the two shapes remains, which is negligible at plume scale.
    """
    ref_lon = _reference_lon(a)
    shape_a = geometry_to_shape(a, ref_lon=ref_lon)
    shape_b = geometry_to_shape(b, ref_lon=ref_lon)
    union_area = shape_a.union(shape_b).area
    if union_area == 0:
        return 0.0
    return float(shape_a.intersection(shape_b).area / union_area)


def contains_point(cone: HazardCone, lat: float, lon: float) -> bool:
    return points_in_cone(cone, [(lat, lon)])[0]


def points_in_cone(cone: HazardCone, points: Sequence[tuple[float, float]]) -> list[bool]:
    """For each ``(lat, lon)``: inside the cone or on its edge. One shape build per call."""
    if cone.geometry is None or not points:
        return [False] * len(points)
    ref_lon = _reference_lon(cone.geometry)
    shape = geometry_to_shape(cone.geometry, ref_lon=ref_lon)
    shapely.prepare(shape)
    candidates = shapely.points([(unwrap_lon(lon, ref_lon), lat) for lat, lon in points])
    return [bool(hit) for hit in shapely.covers(shape, candidates)]


# --- GeoJSON <-> shapely ----------------------------------------------------------------


def geometry_to_shape(geometry: AreaGeometry, *, ref_lon: float) -> BaseGeometry:
    """A valid polygonal shapely geometry; longitudes unwrapped to within 180 of ``ref_lon``.

    An invalid feed polygon (a self-crossing ring) is repaired with ``make_valid``. Coverage
    checks repair it the same way, so "the cone covers the official polygon" is judged
    against the same area that went into the union.
    """
    polygons = [geometry.coordinates] if isinstance(geometry, GeoPolygon) else geometry.coordinates
    shapes = [
        Polygon(_unwrap_ring(rings[0], ref_lon), [_unwrap_ring(r, ref_lon) for r in rings[1:]])
        for rings in polygons
    ]
    shape: BaseGeometry = shapes[0] if len(shapes) == 1 else MultiPolygon(shapes)
    if shape.is_valid:
        return shape
    parts = [
        part
        for part in shapely.get_parts(shapely.make_valid(shape))
        if isinstance(part, Polygon | MultiPolygon)
    ]
    return shapely.unary_union(parts) if parts else Polygon()


def shape_to_geometry(shape: BaseGeometry) -> AreaGeometry | None:
    """GeoJSON for a polygonal shape (exterior rings counter-clockwise, RFC 7946)."""
    polygons = [part for part in shapely.get_parts(shape) if isinstance(part, Polygon)]
    rings = [_rings(orient(polygon, sign=1.0)) for polygon in polygons if not polygon.is_empty]
    if not rings:
        return None
    if len(rings) == 1:
        return GeoPolygon(coordinates=rings[0])
    return GeoMultiPolygon(coordinates=rings)


def _rings(polygon: Polygon) -> list[list[Position]]:
    exterior = [(float(x), float(y)) for x, y in polygon.exterior.coords]
    holes = [[(float(x), float(y)) for x, y in ring.coords] for ring in polygon.interiors]
    return [exterior, *holes]


def _unwrap_ring(ring: Sequence[Position], ref_lon: float) -> list[Position]:
    return [(unwrap_lon(lon, ref_lon), lat) for lon, lat in ring]


def _reference_lon(geometry: AreaGeometry) -> float:
    if isinstance(geometry, GeoPolygon):
        return geometry.coordinates[0][0][0]
    return geometry.coordinates[0][0][0][0]
