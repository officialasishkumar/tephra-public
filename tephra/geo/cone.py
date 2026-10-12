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
from itertools import pairwise
from typing import Final

import shapely
from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.geometry.polygon import orient

from tephra.config import FEED_CLOCK_SLACK, MAX_HORIZON_H
from tephra.geo.units import (
    destination_point,
    ft_to_fl,
    normalize_lon,
    sector_width_deg,
    unwrap_lon,
)
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

VAA_CLOCK_SLACK: Final = FEED_CLOCK_SLACK
"""A VAA stamped up to this long after ``at`` already counts as issued. A tick takes about a
minute, and record selection allows the same slack and passes on the newest VAA of each VAAC
(plus any older one it keeps), so ignoring it would leave that VAAC with no polygon at all."""

AreaGeometry = GeoPolygon | GeoMultiPolygon


# --- official floor ---------------------------------------------------------------------


def official_layers(
    volcano: Volcano, sigmets: Sequence[Sigmet], vaas: Sequence[VaacAdvisory], at: datetime
) -> list[OfficialLayer]:
    layers = [layer for sigmet in sigmets if (layer := _sigmet_layer(sigmet, volcano)) is not None]
    for vaa, suffix in _floor_vaas(vaas, at):
        layers.extend(_vaa_layers(vaa, volcano, suffix))
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


def _floor_vaas(vaas: Sequence[VaacAdvisory], at: datetime) -> list[tuple[VaacAdvisory, str]]:
    """The VAAs whose layers form each VAAC's floor at ``at``, with a label suffix.

    Per VAAC, the newest advisory issued by ``at`` (give or take the clock slack) replaces
    the older ones only when it draws an area, is final or says no ash is expected
    (``replaces_vaa_floor``); it counts only while it is current, so a superseded advisory
    never comes back as the official floor. A newer advisory that gives no area (VA NOT
    IDENTIFIABLE, forecasts NOT AVBL, a blank cloud field) is a non-observation and never
    shrinks the hazard: the newest earlier advisory with an area keeps its layers, each under
    its own window, labelled as kept.
    """
    issued: dict[VaacCentre, list[VaacAdvisory]] = {}
    for vaa in vaas:
        if vaa.issued_at <= at + VAA_CLOCK_SLACK:
            issued.setdefault(vaa.vaac, []).append(vaa)
    chosen: list[tuple[VaacAdvisory, str]] = []
    for advisories in issued.values():
        newest, *older = sorted(advisories, key=vaa_order, reverse=True)
        if replaces_vaa_floor(newest):
            if at <= newest.valid_until():
                chosen.append((newest, ""))
        elif (kept := kept_vaa(newest, older)) is not None:
            chosen.append((kept, f" (kept: VAA {newest.advisory_nr} gives no area)"))
    return chosen


def kept_vaa(newest: VaacAdvisory, older: Sequence[VaacAdvisory]) -> VaacAdvisory | None:
    """The earlier VAA whose layers stay on the floor under ``newest`` (one VAAC, ``older``
    newest first): the first that replaces the floor, if it draws an area. A final or
    negative VAA in between ends the chain, so nothing is kept past it."""
    if replaces_vaa_floor(newest):
        return None
    kept = next((vaa for vaa in older if replaces_vaa_floor(vaa)), None)
    return kept if kept is not None and draws_vaa_area(kept) else None


def vaa_order(vaa: VaacAdvisory) -> tuple[datetime, int, int]:
    """Oldest to newest by DTG, then by advisory number: Darwin can issue two advisories with
    one DTG (Marapi 2026/82 and 2026/83, the second ending what the first said)."""
    year, _, number = vaa.advisory_nr.partition("/")
    return vaa.issued_at, _number(year), _number(number)


def _number(text: str) -> int:
    digits = text.strip()
    return int(digits) if digits.isdigit() else 0


def draws_vaa_area(vaa: VaacAdvisory) -> bool:
    """True when the VAA draws an ash polygon in its observation or any forecast step."""
    steps = [vaa.observation, *vaa.forecasts] if vaa.observation is not None else vaa.forecasts
    return any(layer.polygon is not None for step in steps for layer in step.layers)


def is_negative_vaa(vaa: VaacAdvisory) -> bool:
    """An explicit "no ash": NO VA EXP, or a final VAA, from a VAA that had something to say.

    A VAA that draws ash, could not see it ("VA NOT IDENTIFIABLE"), had no observation to
    give ("NOT AVBL", "NOT PROVIDED") or left the cloud field blank (a hand-over notice) is
    not an all-clear, whatever follows it. Darwin's closing template adds NO VA EXP forecasts
    even when met cloud hid the vent (Marapi 2026/80), and every closing VAA in the 30-day
    census reads "VA NOT IDENTIFIABLE".
    """
    obs = vaa.observation
    if obs is not None:
        if obs.layers or obs.not_identifiable or obs.not_available or not obs.text.strip():
            return False
        if obs.no_ash_expected:
            return True
    if vaa.final:
        return True
    return bool(vaa.forecasts) and all(step.no_ash_expected for step in vaa.forecasts)


def replaces_vaa_floor(vaa: VaacAdvisory) -> bool:
    """A VAA replaces its VAAC's earlier layers when it draws an area, is final or is an
    explicit negative; any other VAA is a non-observation that leaves them standing."""
    return draws_vaa_area(vaa) or vaa.final or is_negative_vaa(vaa)


def _vaa_layers(vaa: VaacAdvisory, volcano: Volcano, suffix: str) -> list[OfficialLayer]:
    layers: list[OfficialLayer] = []
    obs = vaa.observation
    if obs is not None:
        end = max(obs.valid_at, vaa.valid_until())
        name = "EST" if obs.estimated else "OBS"
        bounds = (obs.valid_at, end)
        layers.extend(
            _step_layers(vaa, obs, volcano, layer="OBS", name=name, window=bounds, suffix=suffix)
        )
    window = timedelta(hours=FORECAST_WINDOW_H)
    for step in vaa.forecasts:
        layer = f"FCST+{step.offset_h}H"
        bounds = (step.valid_at - window, step.valid_at + window)
        layers.extend(
            _step_layers(vaa, step, volcano, layer=layer, name=layer, window=bounds, suffix=suffix)
        )
    return layers


def _step_layers(
    vaa: VaacAdvisory,
    step: VaacStep,
    volcano: Volcano,
    *,
    layer: str,
    name: str,
    window: tuple[datetime, datetime],
    suffix: str,
) -> list[OfficialLayer]:
    drawn = [(va, va.polygon) for va in step.layers if va.polygon is not None]
    result: list[OfficialLayer] = []
    for va, polygon in drawn:
        label = f"VAA {vaa.vaac.value} {vaa.advisory_nr} {name}"
        if len(drawn) > 1:
            label += f" {_band_text(va.base_ft, va.top_ft)}"
        label += suffix
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
    """True when the cone contains every layer, laterally and in its vertical band.

    A layer whose ring encloses no area (all its points on one line) has nothing to contain
    laterally, so it is covered even by a cone without geometry.
    """
    if not layers:
        return True
    if cone.geometry is None:
        ref_lon = _reference_lon(layers[0].polygon)
        shape: BaseGeometry = Polygon()
    else:
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


def geometry_entries(
    geometry: AreaGeometry, tracks: Sequence[Sequence[tuple[float, float]]]
) -> list[tuple[int, tuple[float, float]] | None]:
    """Where each track of ``(lat, lon)`` points, one step apart, first reaches the area (a
    cone, or a crew report area).

    Each result is ``(step, (lat, lon))``, or None if the track never reaches it. Step 0 is
    the first point, when it is inside. Any later step is judged on the segment that ends at
    it, so a track crossing a corner or a narrow part of the area between two points is still
    caught; the position is that step's point if it is inside, else where the segment comes in.
    """
    ref_lon = _reference_lon(geometry)
    shape = geometry_to_shape(geometry, ref_lon=ref_lon)
    shapely.prepare(shape)
    return [_track_entry(shape, track, ref_lon) for track in tracks]


def _track_entry(
    shape: BaseGeometry, track: Sequence[tuple[float, float]], ref_lon: float
) -> tuple[int, tuple[float, float]] | None:
    if not track:
        return None
    positions = [(unwrap_lon(lon, ref_lon), lat) for lat, lon in track]
    if shape.covers(Point(positions[0])):
        return 0, track[0]
    if len(positions) == 1 or not shape.intersects(LineString(positions)):
        return None
    segments = shapely.linestrings([[start, end] for start, end in pairwise(positions)])
    first = next((i for i, hit in enumerate(shapely.intersects(shape, segments)) if hit), None)
    if first is None:
        return None
    step = first + 1
    if shape.covers(Point(positions[step])):
        return step, track[step]
    return step, _first_point_inside(shape, segments[first])


def _first_point_inside(shape: BaseGeometry, segment: LineString) -> tuple[float, float]:
    """``(lat, lon)`` where a segment that starts outside the shape first meets it."""
    meeting = shapely.get_coordinates(segment.intersection(shape))
    if len(meeting) == 0:  # the predicate saw a touch that the overlay rounded away
        meeting = shapely.get_coordinates(shapely.shortest_line(segment, shape))[:1]
    along = shapely.line_locate_point(segment, shapely.points(meeting))
    lon, lat = meeting[min(range(len(meeting)), key=lambda i: along[i])]
    return float(lat), normalize_lon(float(lon))


# --- GeoJSON <-> shapely ----------------------------------------------------------------


def geometry_to_shape(geometry: AreaGeometry, *, ref_lon: float) -> BaseGeometry:
    """A valid polygonal shapely geometry; longitudes unwrapped to within 180 of ``ref_lon``.

    An invalid feed polygon (a ring that crosses, folds back over or touches itself) becomes
    everything its rings enclose. ``make_valid`` keeps area by even-odd parity, which cuts a
    hole wherever a folded ring encloses an area twice; ICAO polygons have no holes, so all of
    it is ash area. Coverage checks repair it the same way, so "the cone covers the official
    polygon" is judged against the same area that went into the union.
    """
    polygons = [geometry.coordinates] if isinstance(geometry, GeoPolygon) else geometry.coordinates
    shapes = [
        Polygon(_unwrap_ring(rings[0], ref_lon), [_unwrap_ring(r, ref_lon) for r in rings[1:]])
        for rings in polygons
    ]
    shape: BaseGeometry = shapes[0] if len(shapes) == 1 else MultiPolygon(shapes)
    if shape.is_valid:
        return shape
    return _enclosed_area(shape)


def _enclosed_area(shape: BaseGeometry) -> BaseGeometry:
    """The union of every face the noded rings of ``shape`` bound (empty if they bound none)."""
    linework = shapely.union_all(shapely.get_rings(shapely.get_parts(shape)))
    faces = shapely.get_parts(shapely.polygonize(shapely.get_parts(linework)))
    return shapely.union_all(faces) if len(faces) else Polygon()


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
