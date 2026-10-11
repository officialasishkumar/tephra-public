"""Every data shape shared between TEPHRA modules.

Conventions (binding for all modules):

* Units are in field names: ``*_ft`` feet, ``*_fl`` flight level (hundreds of feet),
  ``*_m`` metres, ``*_km`` kilometres, ``*_nm`` nautical miles, ``*_kt`` knots,
  ``*_deg`` degrees true, ``*_k`` kelvin, ``*_s``/``*_min``/``*_h`` durations.
* Heights: SIGMET/VAA flight levels and VONA heights above sea level are compared on one
  scale (FL x 100 = ft). The pressure-altitude/QNH difference is ignored and said so.
* Directions: ``*_toward_deg`` is where something moves TO (SIGMET "MOV NE" = 45).
  ``WindLevel.from_deg`` is meteorological (where the wind blows FROM). Plume sectors use
  ``bearing_from_deg``/``bearing_to_deg``: bearings FROM THE VENT, sweeping clockwise from
  the first to the second (330 -> 30 is a 60 degree sector through north).
* Coordinates: named fields are ``lat``/``lon``; GeoJSON positions are ``(lon, lat)``.
* Datetimes are timezone-aware UTC (naive values fail validation) and serialise as
  fixed-width ISO 8601 ``2026-10-07T10:32:00.000Z``.
* Every value that came from a feed carries a :class:`Provenance`. Gemini never writes a
  timestamp, id or hash; code renders those.
"""

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Annotated, Any, Final, Literal, Self
from uuid import uuid4

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    computed_field,
    field_validator,
    model_validator,
)

from tephra.util import timeutil
from tephra.util.hashing import (
    combine_hashes,
    proxy_flight_number,
    sha256_json,
    sha256_text,
    short_hash,
)

UtcDatetime = Annotated[
    datetime,
    AfterValidator(timeutil.ensure_utc),
    PlainSerializer(timeutil.to_iso, return_type=str, when_used="json"),
]
"""A timezone-aware UTC datetime that serialises as fixed-width ISO 8601 with ``Z``."""

Position = tuple[float, float]
"""A GeoJSON position: ``(lon, lat)``."""

_AIRLINE_CALLSIGN = re.compile(r"[A-Z]{3}[0-9][0-9A-Z]{0,3}")

LlmBackendName = Literal["gemini", "stub"]
ProductKind = Literal["SIGMET", "VONA", "VAA"]

PRESSURE_LEVEL_FL: dict[int, int] = {
    850: 50,
    700: 100,
    600: 140,
    500: 180,
    400: 240,
    300: 300,
    250: 340,
    200: 390,
    150: 450,
}
"""Open-Meteo pressure levels (hPa) and the ISA flight level each one stands for."""


class TephraModel(BaseModel):
    """Base for every shared model: tolerant of extra keys so stored documents age well."""

    model_config = ConfigDict(
        extra="ignore", protected_namespaces=(), populate_by_name=True, ser_json_inf_nan="null"
    )


# --- enums ------------------------------------------------------------------------------


class FeedId(StrEnum):
    SIGMET = "sigmet"
    VONA = "vona"
    JMA_VOLCANO = "jma_volcano"
    VAAC_TOKYO = "vaac_tokyo"
    VAAC_DARWIN = "vaac_darwin"
    TAF = "taf"
    METAR = "metar"
    ADSB = "adsb"
    WINDS = "winds"
    FRAMES = "frames"
    HSD = "hsd"


class RunMode(StrEnum):
    LIVE = "LIVE"
    REPLAY = "REPLAY"


class AviationColor(StrEnum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    ORANGE = "ORANGE"
    RED = "RED"
    UNKNOWN = "UNKNOWN"


class VaacCentre(StrEnum):
    TOKYO = "TOKYO"
    DARWIN = "DARWIN"


class FrameProduct(StrEnum):
    B13_IR = "B13_IR"
    DUST_RGB = "DUST_RGB"
    TRUE_COLOR = "TRUE_COLOR"


class BtdIndicator(StrEnum):
    """Split-window result. SILENT never means "no ash": it may only fail to widen."""

    NEGATIVE_BTD_PRESENT = "NEGATIVE_BTD_PRESENT"
    SILENT = "SILENT"
    INCONCLUSIVE = "INCONCLUSIVE"


class EvidenceState(StrEnum):
    """What a product actually asserts, read from its text and remarks, not its labels.

    NOT_OBSERVED, NOT_IDENTIFIABLE and NIGHT_BLIND are non-observations: they never shrink
    the hazard, never downgrade an action and are never a CONFLICT by themselves.
    """

    OBSERVED_SAT = "OBSERVED_SAT"
    OBSERVED_GROUND = "OBSERVED_GROUND"
    ESTIMATED = "ESTIMATED"
    NOT_IDENTIFIABLE = "NOT_IDENTIFIABLE"
    NOT_OBSERVED = "NOT_OBSERVED"
    NIGHT_BLIND = "NIGHT_BLIND"
    NO_VA_EXPECTED = "NO_VA_EXPECTED"
    FORECAST_NOT_AVAILABLE = "FORECAST_NOT_AVAILABLE"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class DiscrepancyKind(StrEnum):
    CONFLICT = "CONFLICT"
    LAG = "LAG"
    ENVELOPE = "ENVELOPE"
    SILENCE = "SILENCE"
    HEIGHT_MISMATCH = "HEIGHT_MISMATCH"
    DIRECTION_MISMATCH = "DIRECTION_MISMATCH"


class Severity(StrEnum):
    INFO = "INFO"
    CAUTION = "CAUTION"
    WARNING = "WARNING"


DISCREPANCY_SEVERITY: dict[DiscrepancyKind, Severity] = {
    DiscrepancyKind.CONFLICT: Severity.WARNING,
    DiscrepancyKind.SILENCE: Severity.WARNING,
    DiscrepancyKind.HEIGHT_MISMATCH: Severity.CAUTION,
    DiscrepancyKind.DIRECTION_MISMATCH: Severity.CAUTION,
    DiscrepancyKind.LAG: Severity.INFO,
    DiscrepancyKind.ENVELOPE: Severity.INFO,
}


class PlumeMode(StrEnum):
    """How the hazard cone relates to the official products.

    OFFICIAL: the cone is the union of valid official polygons; the sector is ignored.
    WIDENED: official polygons unioned with the model's sector (never smaller).
    HYPOTHESIS: no official polygon is valid now; the cone is the model's sector alone and
    only MONITOR or HOLD may be advised.
    """

    OFFICIAL = "OFFICIAL"
    WIDENED = "WIDENED"
    HYPOTHESIS = "HYPOTHESIS"


class ActionKind(StrEnum):
    CONTINUE = "CONTINUE"
    MONITOR = "MONITOR"
    CHANGE_LEVEL = "CHANGE_LEVEL"
    HOLD = "HOLD"
    DIVERT = "DIVERT"
    REROUTE = "REROUTE"


ALLOWED_ACTIONS: dict[PlumeMode, frozenset[ActionKind]] = {
    PlumeMode.OFFICIAL: frozenset(ActionKind),
    PlumeMode.WIDENED: frozenset(ActionKind),
    PlumeMode.HYPOTHESIS: frozenset({ActionKind.MONITOR, ActionKind.HOLD}),
}
"""Safety rule: with no official product (HYPOTHESIS) TEPHRA may only advise MONITOR/HOLD."""


class AircraftCategory(StrEnum):
    LIGHT = "LIGHT"
    TURBOPROP = "TURBOPROP"
    REGIONAL_JET = "REGIONAL_JET"
    NARROWBODY = "NARROWBODY"
    WIDEBODY = "WIDEBODY"
    UNKNOWN = "UNKNOWN"


class AdvisoryStatus(StrEnum):
    """DRAFT -> APPROVED | EDITED | REJECTED by a dispatcher; DRAFT -> SUPERSEDED by code."""

    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    EDITED = "EDITED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


TERMINAL_STATUSES: frozenset[AdvisoryStatus] = frozenset(
    {
        AdvisoryStatus.APPROVED,
        AdvisoryStatus.EDITED,
        AdvisoryStatus.REJECTED,
        AdvisoryStatus.SUPERSEDED,
    }
)


class AuditAction(StrEnum):
    DRAFT_CREATED = "DRAFT_CREATED"
    APPROVED = "APPROVED"
    EDITED = "EDITED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"
    OUTBOUND_QUEUED = "OUTBOUND_QUEUED"
    AI_FAILED = "AI_FAILED"
    AI_FAILURE_HANDLED = "AI_FAILURE_HANDLED"
    ASKED = "ASKED"
    NOTICE_READ = "NOTICE_READ"
    RECOVERY_PROPOSED = "RECOVERY_PROPOSED"
    RECOVERY_DECIDED = "RECOVERY_DECIDED"
    MESSAGE_DRAFTED = "MESSAGE_DRAFTED"
    MESSAGE_DECIDED = "MESSAGE_DECIDED"
    DOC_DRAFTED = "DOC_DRAFTED"
    DOC_SIGNED = "DOC_SIGNED"
    HANDOVER_ACKED = "HANDOVER_ACKED"
    LOGIN_OK = "LOGIN_OK"
    LOGIN_FAILED = "LOGIN_FAILED"
    MODE_SWITCH = "MODE_SWITCH"


class FeedStatus(StrEnum):
    OK = "OK"
    STALE = "STALE"
    ERROR = "ERROR"
    DISABLED = "DISABLED"
    NEVER = "NEVER"


class TraceStage(StrEnum):
    POLL = "POLL"
    DISCREPANCY = "DISCREPANCY"
    PLUME = "PLUME"
    CONE = "CONE"
    EXPOSURE = "EXPOSURE"
    PLANNER = "PLANNER"
    DRAFTER = "DRAFTER"
    DESK = "DESK"
    SATELLITE = "SATELLITE"
    NOTICE = "NOTICE"
    ASK = "ASK"
    RECOVERY = "RECOVERY"
    MESSAGES = "MESSAGES"
    DOCS = "DOCS"
    DUTY = "DUTY"
    SYSTEM = "SYSTEM"


TraceActor = Literal["code", "gemini", "adk", "stub", "human", "system"]


class SseEvent(StrEnum):
    """Server-Sent Event names. Payload shapes are listed in MODULES.md."""

    STATE = "state"
    FEEDS = "feeds"
    VOLCANOES = "volcanoes"
    SITUATION = "situation"
    OFFICIAL = "official"
    CONES = "cones"
    EXPOSURES = "exposures"
    AIRCRAFT = "aircraft"
    OVERLAYS = "overlays"
    REROUTES = "reroutes"
    TRACE = "trace"
    ADVISORY = "advisory"
    AI_FAILURE = "ai_failure"
    SATELLITE = "satellite"
    NOTICE = "notice"
    RECOVERY = "recovery"
    MESSAGE = "message"
    DOC = "doc"
    DUTY = "duty"
    BUDGET = "budget"
    HEARTBEAT = "heartbeat"


# --- GeoJSON ----------------------------------------------------------------------------


class GeoPoint(TephraModel):
    type: Literal["Point"] = "Point"
    coordinates: Position


class GeoLineString(TephraModel):
    type: Literal["LineString"] = "LineString"
    coordinates: list[Position]


class GeoPolygon(TephraModel):
    """GeoJSON Polygon: closed rings of ``(lon, lat)``; the first ring is the exterior."""

    type: Literal["Polygon"] = "Polygon"
    coordinates: list[list[Position]]

    @field_validator("coordinates")
    @classmethod
    def _rings_closed(cls, rings: list[list[Position]]) -> list[list[Position]]:
        if not rings:
            raise ValueError("polygon needs an exterior ring")
        for ring in rings:
            if len(ring) < 4 or ring[0] != ring[-1]:
                raise ValueError("polygon rings need >= 4 positions and must be closed")
        return rings


class GeoMultiPolygon(TephraModel):
    type: Literal["MultiPolygon"] = "MultiPolygon"
    coordinates: list[list[list[Position]]]


Geometry = Annotated[GeoPolygon | GeoMultiPolygon, Field(discriminator="type")]
"""An area geometry (what cones and official products are made of)."""

EMPTY_FEATURE_COLLECTION: dict[str, Any] = {"type": "FeatureCollection", "features": []}


def polygon_from_latlon(points: Iterable[tuple[float, float]]) -> GeoPolygon:
    """Build a closed GeoJSON polygon from ``(lat, lon)`` pairs as feeds publish them."""
    ring: list[Position] = [(float(lon), float(lat)) for lat, lon in points]
    if len(set(ring)) < 3:
        raise ValueError("a polygon needs at least three distinct points")
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return GeoPolygon(coordinates=[ring])


def point(lat: float, lon: float) -> GeoPoint:
    return GeoPoint(coordinates=(lon, lat))


def feature(
    geometry: BaseModel | Mapping[str, Any],
    properties: BaseModel | Mapping[str, Any],
    feature_id: str | None = None,
) -> dict[str, Any]:
    """A JSON-safe GeoJSON Feature (models are dumped in JSON mode)."""
    geom = geometry.model_dump(mode="json") if isinstance(geometry, BaseModel) else geometry
    props = properties.model_dump(mode="json") if isinstance(properties, BaseModel) else properties
    result: dict[str, Any] = {"type": "Feature", "geometry": dict(geom), "properties": dict(props)}
    if feature_id is not None:
        result["id"] = feature_id
    return result


def feature_collection(features: Iterable[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": list(features)}


class BBox(TephraModel):
    west: float = Field(ge=-180, le=180)
    south: float = Field(ge=-90, le=90)
    east: float = Field(ge=-180, le=180)
    north: float = Field(ge=-90, le=90)

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.west >= self.east or self.south >= self.north:
            raise ValueError("bbox needs west < east and south < north (no antimeridian)")
        return self

    def contains(self, lat: float, lon: float) -> bool:
        return self.south <= lat <= self.north and self.west <= lon <= self.east

    def corners_lonlat(self) -> list[Position]:
        """Top-left, top-right, bottom-right, bottom-left: MapLibre image-source order."""
        return [
            (self.west, self.north),
            (self.east, self.north),
            (self.east, self.south),
            (self.west, self.south),
        ]


def blob_url(key: str) -> str:
    """Browser URL of a stored blob (rendered frames and BTD PNGs)."""
    return f"/api/blobs/{key}"


# --- provenance -------------------------------------------------------------------------


def source_slug(text: str) -> str:
    """Id-safe upper-case token: ``"Sakurajima (Aira)"`` -> ``SAKURAJIMA_AIRA``."""
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in text.strip().upper())
    return "_".join(part for part in cleaned.split("_") if part)


def make_source_id(kind: str, *parts: object) -> str:
    """``KIND:part:part``; see MODULES.md for the exact recipe per record type."""
    return ":".join([kind, *(str(part).strip().replace(" ", "_") for part in parts)])


class Provenance(TephraModel):
    """Where a record came from. ``source_id`` is the citation id shown to Gemini."""

    model_config = ConfigDict(
        extra="ignore", protected_namespaces=(), populate_by_name=True, frozen=True
    )

    source_id: str
    feed: FeedId
    url: str
    fetched_at: UtcDatetime
    issued_at: UtcDatetime | None = None
    valid_from: UtcDatetime | None = None
    valid_to: UtcDatetime | None = None
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$", description="SHA-256 of the raw bytes")
    stale: bool = False
    stale_age_s: int | None = Field(
        default=None, description="Seconds since the last good fetch when served from cache"
    )
    replay: bool = False

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sha256_short(self) -> str:
        return short_hash(self.sha256)


class SourceRef(TephraModel):
    """A source as printed on an advisory and its audit entry."""

    source_id: str
    feed: FeedId
    url: str
    issued_at: UtcDatetime | None = None
    fetched_at: UtcDatetime
    sha256: str
    sha256_short: str
    stale: bool = False

    @classmethod
    def from_provenance(cls, provenance: Provenance) -> Self:
        return cls(
            source_id=provenance.source_id,
            feed=provenance.feed,
            url=provenance.url,
            issued_at=provenance.issued_at,
            fetched_at=provenance.fetched_at,
            sha256=provenance.sha256,
            sha256_short=provenance.sha256_short,
            stale=provenance.stale,
        )


# --- static catalogues and regions ------------------------------------------------------


class Volcano(TephraModel):
    id: str = Field(description="Smithsonian GVP volcano number, e.g. '263300' (Semeru)")
    name: str
    aliases: list[str] = Field(
        default_factory=list,
        description="Names as SIGMET/VAA/MAGMA write them, matched case-insensitively",
    )
    magma_code: str | None = Field(default=None, description="MAGMA Indonesia code, e.g. SMR")
    country: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    summit_elev_m: int
    observatory: str
    vaac: VaacCentre

    @computed_field  # type: ignore[prop-decorator]
    @property
    def summit_elev_ft(self) -> int:
        return round(self.summit_elev_m * 3.28084)


class VolcanoFile(TephraModel):
    """Shape of ``data/volcanoes.json``."""

    source_note: str
    volcanoes: list[Volcano]


class Airport(TephraModel):
    icao: str = Field(pattern=r"^[A-Z]{4}$")
    iata: str | None = None
    name: str
    country: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    elev_ft: int
    longest_runway_m: int | None = Field(
        default=None,
        description="A jet alternate needs the operator policy's alternates.min_runway_m",
    )


class AirportFile(TephraModel):
    """Shape of ``data/airports.json``."""

    source_note: str
    airports: list[Airport]


class AdsbQueryPoint(TephraModel):
    lat: float
    lon: float
    radius_nm: int = Field(gt=0, le=250, description="adsb.lol point API maximum is 250")


class Region(TephraModel):
    key: str
    name: str
    center_lat: float
    center_lon: float
    zoom: float
    bbox: BBox
    adsb_points: list[AdsbQueryPoint]


# --- feed records -----------------------------------------------------------------------


class Sigmet(TephraModel):
    """One volcanic-ash SIGMET from aviationweather.gov international SIGMET JSON."""

    provenance: Provenance
    fir_id: str
    fir_name: str | None = None
    issuing_office: str | None = None
    series_id: str
    volcano_name: str | None = Field(default=None, description="As written, e.g. 'SEMERU'")
    volcano_lat: float | None = None
    volcano_lon: float | None = None
    observed: bool | None = Field(
        default=None,
        description=(
            "True for 'VA CLD OBS', False for forecast-only, None unknown or 'VA NOT IDENTIFIABLE'"
        ),
    )
    observed_at: UtcDatetime | None = Field(default=None, description="'OBS AT 1010Z'")
    base_ft: int = Field(default=0, description="0 means SFC")
    top_ft: int | None = None
    polygon: GeoPolygon | None = None
    movement_toward_deg: float | None = None
    movement_speed_kt: float | None = None
    stationary: bool = False
    intensity_change: str | None = Field(default=None, description="NC, WKN or INTSF")
    valid_from: UtcDatetime
    valid_to: UtcDatetime
    cancelled: bool = False
    raw_text: str

    def is_valid(self, at: datetime) -> bool:
        return not self.cancelled and self.valid_from <= at <= self.valid_to


class Vona(TephraModel):
    """A MAGMA Indonesia Volcano Observatory Notice for Aviation."""

    provenance: Provenance
    magma_id: int | None = Field(default=None, description="Numeric id in the MAGMA page URL")
    notice_number: str | None = None
    volcano_name: str
    volcano_code: str | None = None
    issued_at: UtcDatetime = Field(description="From the '20260923/2221Z' group")
    color_code: AviationColor
    ash_observed: bool = Field(description="False when the notice says ash is not observed")
    cloud_top_ft: int | None = Field(
        default=None,
        description="Ash-cloud top AMSL = round(cloud_top_m * 3.28084); MAGMA's own ft uses 3.2",
    )
    cloud_top_m: int | None = None
    movement_toward_deg: float | None = None
    movement_text: str | None = Field(default=None, description="Direction text as published")
    eruption_at: UtcDatetime | None = None
    source_text: str | None = Field(default=None, description="e.g. 'Ground observer'")
    remarks: str | None = None
    raw_text: str

    def is_recent(self, at: datetime, window_h: float) -> bool:
        return at - timedelta(hours=window_h) <= self.issued_at <= at + timedelta(minutes=5)


class VaLayer(TephraModel):
    """One ash layer in a VAA step, e.g. ``SFC/FL150 S0806 E11255 - ...``."""

    base_ft: int
    top_ft: int
    polygon: GeoPolygon | None = None
    movement_toward_deg: float | None = None
    movement_speed_kt: float | None = None


class VaacStep(TephraModel):
    """``OBS VA CLD`` (offset 0) or one ``FCST VA CLD +6/+12/+18 HR`` step."""

    offset_h: int = Field(description="0 for the observation/estimate, else 6, 12 or 18")
    valid_at: UtcDatetime
    layers: list[VaLayer] = Field(default_factory=list)
    estimated: bool = Field(default=False, description="'EST VA CLD' instead of 'OBS VA CLD'")
    not_identifiable: bool = Field(default=False, description="'VA NOT IDENTIFIABLE FM SAT'")
    no_ash_expected: bool = Field(default=False, description="'NO VA EXP'")
    not_available: bool = Field(default=False, description="'NOT AVBL' / 'NOT PROVIDED'")
    text: str


class VaacAdvisory(TephraModel):
    """A Volcanic Ash Advisory (FVFE01 RJTD from Tokyo, FVAU from Darwin)."""

    provenance: Provenance
    vaac: VaacCentre
    advisory_nr: str = Field(description="'2026/249'; numbered per volcano per year")
    issued_at: UtcDatetime
    volcano_name: str
    volcano_number: str | None = Field(default=None, description="GVP number if printed")
    volcano_lat: float | None = None
    volcano_lon: float | None = None
    area: str | None = None
    summit_elev_ft: int | None = None
    info_source: str | None = None
    aviation_color: AviationColor | None = None
    eruption_details: str | None = None
    observation: VaacStep | None = None
    forecasts: list[VaacStep] = Field(default_factory=list)
    remarks: str | None = None
    next_advisory_text: str | None = None
    next_advisory_at: UtcDatetime | None = None
    final: bool = Field(default=False, description="'NO FURTHER ADVISORIES'")
    raw_text: str

    def valid_until(self) -> datetime:
        """Shared validity rule: next advisory time + 60 min, final +1 h, otherwise +6 h."""
        if self.final:
            return self.issued_at + timedelta(hours=1)
        if self.next_advisory_at is not None:
            return self.next_advisory_at + timedelta(minutes=60)
        return self.issued_at + timedelta(hours=6)

    def is_current(self, at: datetime) -> bool:
        return self.issued_at <= at <= self.valid_until()


class TafPeriod(TephraModel):
    valid_from: UtcDatetime
    valid_to: UtcDatetime
    change: str | None = Field(default=None, description="None for base, FM/BECMG/TEMPO/PROB30")
    visibility_m: int | None = None
    ceiling_ft: int | None = Field(default=None, description="Lowest BKN/OVC/VV base AGL")
    weather: list[str] = Field(default_factory=list, description="e.g. ['VA', 'TSRA']")
    wind_from_deg: float | None = None
    wind_speed_kt: float | None = None


class Taf(TephraModel):
    provenance: Provenance
    icao: str
    issued_at: UtcDatetime
    valid_from: UtcDatetime
    valid_to: UtcDatetime
    periods: list[TafPeriod]
    raw_text: str


class Metar(TephraModel):
    provenance: Provenance
    icao: str
    observed_at: UtcDatetime
    visibility_m: int | None = None
    ceiling_ft: int | None = None
    weather: list[str] = Field(default_factory=list)
    flight_category: str | None = None
    raw_text: str


class Aircraft(TephraModel):
    """One airborne ADS-B target. Ground targets and targets without position are dropped."""

    hex: str = Field(description="ICAO 24-bit address, lower case")
    callsign: str | None = Field(default=None, description="Trimmed; registrations not kept")
    type_icao: str | None = None
    lat: float
    lon: float
    alt_baro_ft: int | None = Field(default=None, description="Pressure altitude; use this")
    alt_geom_ft: int | None = Field(default=None, description="GNSS; never used for exposure")
    nav_altitude_mcp_ft: int | None = Field(default=None, description="Autopilot selected alt")
    gs_kt: float | None = None
    track_deg: float | None = None
    baro_rate_fpm: int | None = None
    seen_pos_s: float | None = None
    observed_at: UtcDatetime = Field(description="Response time minus seen_pos")
    source_id: str = Field(description="source_id of the AdsbSnapshot it came from")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def proxy_flight(self) -> str:
        return proxy_flight_number(self.hex)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def airline(self) -> bool:
        """Airline-style callsign: only these become proxy flights of the fictional airline."""
        return is_airline_callsign(self.callsign)


def is_airline_callsign(callsign: str | None) -> bool:
    """ICAO airline designator plus flight number, e.g. GIA417 or QFA43A (not PKABC)."""
    return bool(callsign) and _AIRLINE_CALLSIGN.fullmatch(callsign or "") is not None


class AdsbSnapshot(TephraModel):
    """One adsb.lol point-API response."""

    provenance: Provenance
    query: AdsbQueryPoint
    aircraft: list[Aircraft]


class WindLevel(TephraModel):
    pressure_hpa: int
    flight_level: int
    speed_kt: float
    from_deg: float = Field(description="Meteorological convention: direction wind blows FROM")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def toward_deg(self) -> float:
        return (self.from_deg + 180.0) % 360.0


class WindProfile(TephraModel):
    """Winds at every pressure level for one hour at one point."""

    provenance: Provenance
    lat: float
    lon: float
    valid_at: UtcDatetime
    levels: list[WindLevel]


class WindForecast(TephraModel):
    """Hourly profiles above one volcano (store document ``winds/<volcano_id>``)."""

    volcano_id: str
    profiles: list[WindProfile]


class SatelliteFrame(TephraModel):
    """A rendered satellite image crop (support only, never evidence of ash by itself)."""

    provenance: Provenance
    product: FrameProduct
    observed_at: UtcDatetime
    volcano_id: str | None = None
    image_key: str = Field(description="Blob key, e.g. 'frames/263300_B13_IR_20261007T1030Z.png'")
    width_px: int
    height_px: int
    bbox: BBox | None = Field(default=None, description="None when not georeferenced")
    caption: str


class BtdResult(TephraModel):
    """Split-window brightness-temperature difference over a crop around one volcano.

    An indicator only: negative BTD suggests silicate ash, but tropical water vapour masks
    it, ice-coated or thin ash is missed, and cold cloud tops confuse it.
    ``provenance.sha256`` is ``combine_hashes(segment_sha256)``.
    """

    provenance: Provenance
    volcano_id: str
    scan_start: UtcDatetime
    band_pair: Literal["B13-B15", "B14-B15"]
    bbox: BBox = Field(description="Crop on a regular lat/lon grid; PNG corners match it")
    threshold_k: float
    pixel_count: int
    negative_pixel_count: int
    negative_fraction: float
    min_btd_k: float
    p05_btd_k: float
    median_btd_k: float
    min_bt_k: float = Field(description="Coldest brightness temperature of the first band")
    nearest_negative_km: float | None = None
    negative_centroid_bearing_deg: float | None = None
    negative_centroid_distance_km: float | None = None
    indicator: BtdIndicator
    caveats: list[str]
    segment_sha256: list[str]
    image_key: str | None = None


# --- reconciliation ---------------------------------------------------------------------


class Discrepancy(TephraModel):
    """A code-detected difference between products for one volcano."""

    id: str = Field(description="stable_id('D', kind, aspect, *sorted(source_ids)), length 8")
    volcano_id: str
    kind: DiscrepancyKind
    aspect: Literal["presence", "time", "ash_observed", "top", "base", "direction", "polygon"]
    source_ids: list[str]
    values: dict[str, str] = Field(description="source_id -> value as displayed ('FL150')")
    magnitude: float | None = None
    unit: Literal["ft", "deg", "min"] | None = None
    summary: str = Field(description="Code-written one-liner shown on the badge")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def severity(self) -> Severity:
        return DISCREPANCY_SEVERITY[self.kind]


class OfficialLayer(TephraModel):
    """One official ash polygon with its vertical band and validity window."""

    model_config = ConfigDict(
        extra="ignore", protected_namespaces=(), populate_by_name=True, frozen=True
    )

    source_id: str
    kind: Literal["SIGMET", "VAA"]
    layer: str = Field(description="'SIGMET', 'OBS', 'FCST+6H', 'FCST+12H' or 'FCST+18H'")
    label: str = Field(description="e.g. 'SIGMET WAAF 12' or 'VAA TOKYO 2026/249 FCST+6H'")
    volcano_id: str | None = None
    polygon: GeoPolygon
    base_ft: int
    top_ft: int
    valid_from: UtcDatetime
    valid_to: UtcDatetime

    def is_valid(self, at: datetime) -> bool:
        return self.valid_from <= at <= self.valid_to

    def to_feature(self) -> dict[str, Any]:
        props = OfficialFeatureProps(
            source_id=self.source_id,
            kind=self.kind,
            layer=self.layer,
            label=self.label,
            volcano_id=self.volcano_id,
            base_ft=self.base_ft,
            top_ft=self.top_ft,
            valid_from=self.valid_from,
            valid_to=self.valid_to,
        )
        return feature(self.polygon, props, feature_id=f"{self.source_id}#{self.layer}")


class SupportingEvidence(TephraModel):
    """A text another model step produced (the Satellite Reader's), given to the Plume Reader
    under its own source id. It is context only and is not part of ``Situation.input_hash``:
    a new picture alone never triggers a Plume Reader call."""

    source_id: str
    text: str


class Situation(TephraModel):
    """Everything known about one active volcano at one instant: the Plume Reader's input."""

    volcano: Volcano
    as_of: UtcDatetime
    mode: RunMode
    active_reasons: list[str]
    sigmets: list[Sigmet] = Field(default_factory=list)
    vonas: list[Vona] = Field(default_factory=list, description="Newest first")
    vaas: list[VaacAdvisory] = Field(default_factory=list, description="Newest first")
    winds: list[WindProfile] = Field(default_factory=list, description="Hourly, from as_of")
    frames: list[SatelliteFrame] = Field(default_factory=list)
    btd: BtdResult | None = None
    official_layers: list[OfficialLayer] = Field(default_factory=list)
    discrepancies: list[Discrepancy] = Field(default_factory=list)
    supporting: list[SupportingEvidence] = Field(
        default_factory=list, description="Set by the pipeline just before the Plume Reader call"
    )

    def provenances(self) -> list[Provenance]:
        records: list[Any] = [
            *self.sigmets,
            *self.vonas,
            *self.vaas,
            *self.winds,
            *self.frames,
        ]
        if self.btd is not None:
            records.append(self.btd)
        return [record.provenance for record in records]

    def source_ids(self) -> set[str]:
        ids = {provenance.source_id for provenance in self.provenances()}
        return ids | {item.source_id for item in self.supporting}

    def official_valid_now(self) -> bool:
        return any(layer.is_valid(self.as_of) for layer in self.official_layers)

    def official_top_ft(self) -> int | None:
        return max((layer.top_ft for layer in self.official_layers), default=None)

    def official_base_ft(self) -> int | None:
        return min((layer.base_ft for layer in self.official_layers), default=None)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def input_hash(self) -> str:
        """Trigger for a new Plume Reader call: official texts changed or the BTD flipped.

        Winds and frames refresh hourly and every ten minutes; they ride along with the next
        call instead of triggering one, which would cost about 150 calls a day per volcano.
        """
        texts: list[Any] = [*self.sigmets, *self.vonas, *self.vaas]
        # Each record's own text, not provenance.sha256: that hashes the whole HTTP response,
        # which every VA SIGMET worldwide shares, so any change anywhere would re-ask Gemini.
        parts = [f"{r.provenance.source_id}:{sha256_text(r.raw_text)}" for r in texts]
        if self.btd is not None:
            parts.append(f"BTD:{self.btd.indicator.value}")
        return combine_hashes(parts)


# --- plume ------------------------------------------------------------------------------


class DisagreementReading(TephraModel):
    discrepancy_id: str
    reading: str
    which_source_we_lean_on: str = Field(description="A source_id from the input")
    why: str


class PlumeEstimate(TephraModel):
    """The Plume Reader's structured output (Gemini ``response_schema``).

    Code validates it; see ``tephra.agents.plume_reader.validate_estimate``.
    """

    mode: PlumeMode
    base_fl: int = Field(ge=0, le=600)
    top_fl: int = Field(ge=0, le=600)
    bearing_from_deg: float = Field(ge=0, le=360, description="Sector start, from the vent")
    bearing_to_deg: float = Field(ge=0, le=360, description="Sector end, clockwise from start")
    extent_km: float = Field(ge=0, description="Sector radius from the vent")
    horizon_h: float = Field(gt=0, description="Hours ahead the estimate covers")
    confidence: float = Field(ge=0, le=1)
    sources_used: list[str] = Field(description="source_ids from the input only")
    disagreements_explained: list[DisagreementReading]
    uncertainty_notes: str
    rationale: str

    def sector_width_deg(self) -> float:
        width = (self.bearing_to_deg - self.bearing_from_deg) % 360.0
        return 360.0 if width == 0 and self.bearing_to_deg != self.bearing_from_deg else width


class PlumeAssessment(TephraModel):
    """A validated estimate plus the code-written facts about how it was produced."""

    id: str = Field(description="stable_id('PA', volcano_id, input_hash, prompt_hash, model_id)")
    volcano_id: str
    created_at: UtcDatetime
    input_hash: str
    estimate: PlumeEstimate
    llm_backend: LlmBackendName
    model_id: str
    prompt_hash: str
    outcome: Literal["ACCEPTED", "REPAIRED", "MODEL_FAILED", "OFFICIAL_ONLY", "PENDING", "STUB"]
    attempts: int = Field(
        ge=0, description="Model calls made: 0 (stub or OFFICIAL_ONLY), 1, or 2 with repair"
    )
    validation_errors: list[str] = Field(
        default_factory=list, description="Errors of the last rejected attempt, if any"
    )
    images_used: list[str] = Field(default_factory=list, description="source_ids of images sent")
    latency_ms: int | None = None


# --- cone -------------------------------------------------------------------------------


class HazardCone(TephraModel):
    """The final hazard area for one volcano. Always contains every official layer."""

    id: str = Field(description="stable_id('CONE', volcano_id, assessment_id)")
    volcano_id: str
    assessment_id: str
    mode: PlumeMode
    confidence: float
    llm_backend: LlmBackendName
    created_at: UtcDatetime
    horizon_h: float
    valid_to: UtcDatetime
    geometry: Geometry | None = Field(description="None when there is nothing to draw")
    sector: GeoPolygon | None = None
    base_ft: int
    top_ft: int
    official_source_ids: list[str]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def label(self) -> str:
        text = f"{self.mode.value} {round(self.confidence * 100)}%"
        return f"{text} (NO MODEL)" if self.llm_backend == "stub" else text

    def to_features(self) -> list[dict[str, Any]]:
        features: list[dict[str, Any]] = []
        parts: list[tuple[Literal["cone", "sector"], BaseModel | None]] = [
            ("cone", self.geometry),
            ("sector", self.sector),
        ]
        for part, geometry in parts:
            if geometry is None:
                continue
            props = ConeFeatureProps(
                cone_id=self.id,
                volcano_id=self.volcano_id,
                part=part,
                mode=self.mode,
                confidence=self.confidence,
                base_ft=self.base_ft,
                top_ft=self.top_ft,
                label=self.label,
                valid_to=self.valid_to,
            )
            features.append(feature(geometry, props, feature_id=f"{self.id}#{part}"))
        return features


# --- exposure and fuel ------------------------------------------------------------------


class FuelLine(TephraModel):
    """Time and fuel cost from TEPHRA's labelled simple formula (not airline tables)."""

    action: ActionKind
    minutes: int
    fuel_kg: int
    burn_kg_per_min: float
    category: AircraftCategory
    alternate_icao: str | None = None
    distance_nm: float | None = None
    formula: str = Field(description="Code-written, e.g. 'HOLD 20 MIN x 42 KG/MIN = 840 KG'")


class ExposedFlight(TephraModel):
    """An aircraft whose extrapolated track enters a cone within its level band."""

    id: str = Field(description="'<hex>:<volcano_id>', stable across ticks")
    hex: str
    callsign: str | None = None
    proxy_flight: str
    type_icao: str | None = None
    category: AircraftCategory
    lat: float
    lon: float
    alt_baro_ft: int | None = None
    nav_altitude_mcp_ft: int | None = None
    gs_kt: float | None = None
    track_deg: float | None = None
    observed_at: UtcDatetime
    source_id: str = Field(description="ADS-B snapshot source_id")
    volcano_id: str
    cone_id: str
    inside_now: bool
    minutes_to_entry: int = Field(ge=0, description="0 when already inside")
    entry_lat: float
    entry_lon: float
    aircraft_band_ft: tuple[int, int] = Field(description="Levels considered (baro and MCP)")
    hazard_band_ft: tuple[int, int] = Field(description="Cone band before margins")
    path: list[Position] = Field(description="Extrapolated (lon, lat) points up to entry")
    hold: FuelLine


# --- operator policy --------------------------------------------------------------------


class PolicyModel(BaseModel):
    """Base for the operator policy file. Unlike ``TephraModel`` it refuses unknown keys: a
    misspelt value name must stop startup, not leave the code without that value."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class PolicyValue(PolicyModel):
    """One operator value, with its unit and the reason it has this value."""

    value: int = Field(ge=0)
    unit: Literal["ft", "FL", "NM", "m", "min", "kt", "deg", "s", "USD", "count", "pct"]
    source: str = Field(min_length=1)
    citation_ids: list[str] = Field(default_factory=list)


class ExposurePolicy(PolicyModel):
    vertical_margin_ft: PolicyValue


class AlternatePolicy(PolicyModel):
    search_radius_nm: PolicyValue
    min_runway_m: PolicyValue
    min_visibility_m: PolicyValue
    min_ceiling_ft: PolicyValue
    taf_eta_window_min: PolicyValue
    terminal_radius_nm: PolicyValue


class PlannerPolicy(PolicyModel):
    level_search_ft: PolicyValue
    level_band_fl: PolicyValue
    max_change_level_fl: PolicyValue
    divert_within_min: PolicyValue
    hold_within_min: PolicyValue


class ReroutePolicy(PolicyModel):
    buffer_nm: PolicyValue
    simplify_nm: PolicyValue
    max_waypoints_count: PolicyValue
    max_turn_deg: PolicyValue
    rejoin_step_nm: PolicyValue
    max_extra_min: PolicyValue
    min_extra_min: PolicyValue
    route_max_cross_track_nm: PolicyValue
    cruise_tas_kt: PolicyValue


class RecoveryPolicy(PolicyModel):
    min_turn_min: PolicyValue
    max_delay_min: PolicyValue
    freeze_window_min: PolicyValue
    horizon_after_closure_min: PolicyValue
    scenario_extend_1_min: PolicyValue
    scenario_extend_2_min: PolicyValue
    solve_work_s: PolicyValue
    solve_time_limit_s: PolicyValue
    delay_cost_per_min_usd: PolicyValue
    delay_cost_per_pax_hour_usd: PolicyValue
    cancel_cost_per_pax_usd: PolicyValue
    cancel_cost_fixed_usd: PolicyValue
    swap_cost_usd: PolicyValue
    ferry_cost_per_block_min_usd: PolicyValue
    max_fdp_min: PolicyValue
    airport_closure_radius_nm: PolicyValue
    pax_notice_min_delay_min: PolicyValue


class FuelPolicy(PolicyModel):
    hold_min: PolicyValue
    divert_extra_min: PolicyValue


class DutyPolicy(PolicyModel):
    rerun_min: PolicyValue


class DraftPolicy(PolicyModel):
    """How long an open draft waits after its flight leaves the cone before it is retired."""

    unexposed_retire_min: PolicyValue
    position_lost_retire_min: PolicyValue


class SourceRule(PolicyModel):
    """One step of the source-trust order; the first is the most trusted."""

    rule_id: str = Field(pattern=r"^[A-Z0-9_]+$")
    text: str = Field(min_length=1)
    enforced_by: str = Field(min_length=1, description="The code that applies this rule today")
    citation_ids: list[str] = Field(min_length=1)


class PolicyCitation(PolicyModel):
    id: str = Field(pattern=r"^[a-z0-9.-]+$")
    ref: str = Field(min_length=1, description="Document, paragraph and page")
    text: str = Field(min_length=1, description="Quoted word for word")
    url: str = Field(pattern=r"^https://")


POSITIVE_POLICY_VALUES: Final = frozenset(
    {
        "alternates.search_radius_nm",
        "alternates.min_runway_m",
        "alternates.min_visibility_m",
        "alternates.min_ceiling_ft",
        "alternates.taf_eta_window_min",
        "alternates.terminal_radius_nm",
        "planner.level_search_ft",
        "planner.level_band_fl",
        "planner.max_change_level_fl",
        "planner.divert_within_min",
        "planner.hold_within_min",
        "fuel.hold_min",
        "drafts.unexposed_retire_min",
        "drafts.position_lost_retire_min",
    }
)
"""Values that must be above zero; every other value only needs to be zero or more."""


class OperatorPolicy(PolicyModel):
    """``data/policy/policy_a.json``: every margin, buffer, minimum and threshold the code
    applies on the operator's behalf. The values are illustrative; no airline's safety risk
    assessment (SRA) stands behind them."""

    policy_id: str = Field(pattern=r"^[A-Z0-9-]+$")
    version: str = Field(pattern=r"^\d{4}\.\d{1,2}\.\d+$", description="Bumped on every change")
    preset: Literal["A"]
    title: str = Field(min_length=1)
    label: Literal["ILLUSTRATIVE, not an airline SRA"]
    sra_ref: str | None = Field(description="The operator SRA behind the policy; none for A")
    risk_owner: str = Field(min_length=1)
    summary_text: str = Field(min_length=1)
    summary_citation_ids: list[str] = Field(min_length=1)
    exposure: ExposurePolicy
    alternates: AlternatePolicy
    planner: PlannerPolicy
    reroute: ReroutePolicy
    recovery: RecoveryPolicy
    fuel: FuelPolicy
    drafts: DraftPolicy
    duty: DutyPolicy
    source_order: list[SourceRule] = Field(min_length=1)
    citations: list[PolicyCitation] = Field(min_length=1)

    @model_validator(mode="after")
    def _citations_resolve(self) -> Self:
        known = [citation.id for citation in self.citations]
        if len(set(known)) != len(known):
            raise ValueError("citation ids must be unique")
        cited = {*self.summary_citation_ids}
        for item in [*self.source_order, *self.named_values().values()]:
            cited.update(item.citation_ids)
        if missing := sorted(cited - set(known)):
            raise ValueError(f"unknown citation ids: {', '.join(missing)}")
        return self

    @model_validator(mode="after")
    def _values_in_range(self) -> Self:
        """A zero here would switch a screen or a search off without saying so, and an
        inverted pair would skip a rule; both fail at startup instead."""
        values = self.named_values()
        zero = sorted(name for name in POSITIVE_POLICY_VALUES if values[name].value <= 0)
        if zero:
            raise ValueError(f"policy values must be above zero: {', '.join(zero)}")
        rules = self.planner
        if rules.divert_within_min.value > rules.hold_within_min.value:
            raise ValueError("planner.divert_within_min is above planner.hold_within_min")
        if rules.level_band_fl.value > rules.max_change_level_fl.value:
            raise ValueError("planner.level_band_fl is above planner.max_change_level_fl")
        return self

    def named_values(self) -> dict[str, PolicyValue]:
        """Every value by its dotted name, e.g. ``"planner.level_search_ft"``."""
        blocks: dict[str, PolicyModel] = {
            "exposure": self.exposure,
            "alternates": self.alternates,
            "planner": self.planner,
            "reroute": self.reroute,
            "recovery": self.recovery,
            "fuel": self.fuel,
            "drafts": self.drafts,
            "duty": self.duty,
        }
        return {
            f"{key}.{name}": getattr(block, name)
            for key, block in blocks.items()
            for name in type(block).model_fields
        }

    def content_hash(self) -> str:
        """SHA-256 of the canonical JSON: it changes with any value, not with file layout."""
        return sha256_json(self.model_dump(mode="json"))


class PolicySummary(TephraModel):
    """The active operator policy, as the Wall and Desk show it."""

    policy_id: str
    version: str
    preset: str
    label: str
    policy_hash: str

    @classmethod
    def of(cls, policy: OperatorPolicy) -> Self:
        return cls(
            policy_id=policy.policy_id,
            version=policy.version,
            preset=policy.preset,
            label=policy.label,
            policy_hash=policy.content_hash(),
        )


# --- planning ---------------------------------------------------------------------------


class AlternateCheck(TephraModel):
    """TAF screen of one alternate at an ETA (simplified planning minima, labelled)."""

    icao: str
    ok: bool
    reasons: list[str] = Field(description="Code-written, e.g. 'VA IN TEMPO GROUP'")
    taf_source_id: str | None = None
    checked_for: UtcDatetime


class AlternateCandidate(TephraModel):
    icao: str
    name: str
    distance_nm: float
    bearing_deg: float
    check: AlternateCheck
    divert: FuelLine


class RerouteKind(StrEnum):
    REJOIN_TRACK = "REJOIN_TRACK"
    """Around the hazard and back onto the present track beyond it: needs no destination."""
    DIRECT_DEST = "DIRECT_DEST"
    """Around the hazard and direct to the destination of the flight's published route."""


class RerouteStatus(StrEnum):
    OK = "OK"
    NOT_EXPOSED = "NOT_EXPOSED"
    START_INSIDE = "START_INSIDE"
    DEST_INSIDE = "DEST_INSIDE"
    NO_ROUTE = "NO_ROUTE"
    NO_DEST = "NO_DEST"
    NO_BENEFIT = "NO_BENEFIT"
    TOO_LONG = "TOO_LONG"


class FlightRoute(TephraModel):
    """Origin and destination of an ADS-B callsign from VRS standing data (CC0), kept only
    when the aircraft lies near that leg's great circle."""

    callsign: str
    origin_icao: str = Field(pattern=r"^[A-Z0-9]{4}$")
    dest_icao: str = Field(pattern=r"^[A-Z0-9]{4}$")
    cross_track_nm: float = Field(ge=0, description="Aircraft's distance from the leg")
    source: Literal["vrs-standing-data"] = "vrs-standing-data"


class RerouteOption(TephraModel):
    """A lateral route around the hazard, computed by code (``tephra.geo.reroute``).

    Turn points are latitude/longitude only (no named waypoint is ever invented), rounded to
    one arc-minute and written in ICAO ``DDMM[NS]DDDMM[EW]`` form in ``route_string``.
    """

    id: str = Field(description="stable_id('RR', flight_id, cone_id, kind)")
    flight_id: str
    cone_id: str
    kind: RerouteKind
    status: RerouteStatus
    note: str = Field(description="Code-written reason for the status")
    side: Literal["LEFT", "RIGHT"] | None = None
    fl: int | None = Field(default=None, description="Level the route is flown at")
    waypoints: list[Position] = Field(default_factory=list, description="(lon, lat) turn points")
    end: Position | None = Field(default=None, description="Rejoin point or destination")
    end_icao: str | None = None
    path: list[Position] = Field(
        default_factory=list, description="(lon, lat) polyline from the present position"
    )
    dist_nm: float | None = None
    extra_nm: float | None = None
    time_min: float | None = None
    extra_min: float | None = None
    buffer_nm: int | None = None
    max_turn_deg: float | None = None
    fuel: FuelLine | None = Field(default=None, description="Cost of the extra minutes")
    route_string: str = Field(default="", description="'DCT 0540S10930E DCT 0701S11215E DCT WADD'")
    wind_note: str | None = None
    compute_ms: float | None = None


class PlannerContext(TephraModel):
    """Everything the Exposure Planner may use for one flight; held in ADK session state.

    Deliberately contains no clock times so the model has none to copy.
    """

    flight: ExposedFlight
    volcano_name: str
    plume_mode: PlumeMode
    confidence: float
    hazard_base_ft: int
    hazard_top_ft: int
    vertical_margin_ft: int
    allowed_actions: list[ActionKind]
    alternates: list[AlternateCandidate]
    hold: FuelLine
    # Operator policy values the rules and validators apply (OperatorPolicy.planner).
    level_search_ft: int = Field(description="A clear band must lie this close to the level")
    level_band_fl: int
    max_change_level_fl: int
    divert_within_min: int
    hold_within_min: int
    route: FlightRoute | None = Field(default=None, description="Published route, if known")
    reroutes: list[RerouteOption] = Field(
        default_factory=list, description="Code-computed lateral options (OK and not OK)"
    )


class PlannerDecision(TephraModel):
    """What the planner submits (its ``submit_plan`` tool arguments)."""

    action: ActionKind
    change_level_fl_min: int | None = None
    change_level_fl_max: int | None = None
    hold_fl: int | None = None
    alternate_icao: str | None = None
    reroute_id: str | None = Field(default=None, description="An OK RerouteOption id (REROUTE)")
    reasoning: str = Field(description="Operational language, no clock times")
    alternatives_considered: list[ActionKind] = Field(default_factory=list)


class ToolCallRecord(TephraModel):
    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    result_summary: str


class PlannedAction(TephraModel):
    id: str = Field(description="stable_id('PLAN', flight_id, cone_id)")
    flight_id: str
    cone_id: str
    decision: PlannerDecision | None = Field(
        description="None when the model gave no plan that passed the checks (MODEL_FAILED)"
    )
    fuel: FuelLine | None = Field(default=None, description="HOLD or DIVERT cost line")
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    llm_backend: LlmBackendName
    model_id: str
    prompt_hash: str
    outcome: Literal["ACCEPTED", "REPAIRED", "MODEL_FAILED", "STUB"]
    validation_errors: list[str] = Field(default_factory=list)


# --- drafting, desk, outbound -----------------------------------------------------------


class DraftText(TephraModel):
    """The Dispatch Drafter's structured output (Gemini ``response_schema``)."""

    body: str = Field(description="ACARS-style upper-case plain text, <= 400 chars")
    cost_note: str = Field(description="One line")


class Advisory(TephraModel):
    """A per-flight advisory. Only a dispatcher moves it out of DRAFT (except SUPERSEDED)."""

    id: str = Field(description="'adv_' + 12 hex chars")
    version: int = Field(ge=1, description="Incremented on every transition (compare-and-set)")
    status: AdvisoryStatus
    created_at: UtcDatetime
    updated_at: UtcDatetime
    replay: bool
    volcano_id: str
    volcano_name: str
    flight_id: str
    proxy_flight: str
    callsign: str | None = None
    hex: str
    type_icao: str | None = None
    action: ActionKind
    change_level_fl_min: int | None = None
    change_level_fl_max: int | None = None
    hold_fl: int | None = None
    alternate_icao: str | None = None
    reroute: RerouteOption | None = None
    minutes_to_entry: int
    inside_now: bool
    urgency_bucket: int | None = Field(
        default=None,
        ge=0,
        description="0 inside the cone, then one more per operator time limit the entry lies"
        " beyond, when drafted; None on drafts from before the field",
    )
    fuel: FuelLine | None = None
    fuel_line: str = Field(description="FuelLine.formula, or '' when no cost applies")
    plume_mode: PlumeMode
    confidence: float
    cone_id: str
    assessment_id: str
    plan_id: str
    policy_id: str | None = Field(
        default=None, description="Operator policy the draft was made under; None on older drafts"
    )
    policy_version: str | None = None
    policy_hash: str | None = Field(
        default=None,
        description="First 12 hex chars of OperatorPolicy.content_hash(); None on older drafts",
    )
    replay_case_id: str | None = Field(
        default=None, description="The replay case a REPLAY draft was made from; None when live"
    )
    header: str = Field(description="Code-rendered: flight, UTC times, sources and hashes")
    body: str = Field(description="Model-written (or stub) body, as drafted")
    cost_note: str
    edited_body: str | None = None
    reject_reason: str | None = None
    decided_by: str | None = None
    decided_at: UtcDatetime | None = None
    superseded_by: str | None = None
    sources: list[SourceRef]
    input_hash: str
    llm_backend: LlmBackendName
    model_id: str
    prompt_hashes: dict[str, str] = Field(description="Keys: plume_reader, planner, drafter")
    validation_notes: list[str] = Field(default_factory=list)
    dedupe_key: str = Field(description="stable_id('DD', hex, volcano_id, action, target)")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def final_body(self) -> str:
        return self.edited_body if self.edited_body is not None else self.body

    @computed_field  # type: ignore[prop-decorator]
    @property
    def final_text(self) -> str:
        return "\n".join(part for part in (self.header, self.final_body, self.cost_note) if part)


class DutyItemKind(StrEnum):
    ASSESS = "ASSESS"
    """Read the plume (Satellite Reader, then Plume Reader) and rebuild the cone."""
    PLAN = "PLAN"
    """Plan and draft advice for one exposed flight (Exposure Planner, Dispatch Drafter)."""
    RECOVER = "RECOVER"
    """Re-plan the RFA network for a changed set of closed airports (recovery agent)."""
    SRA = "SRA"
    """Draft the safety risk assessment for a region newly carrying exposed flights."""


class DutyItem(TephraModel):
    """One piece of AI work code found due this tick, offered to the Duty Officer."""

    id: str = Field(description="stable_id('DI', kind, subject, version): one per piece of work")
    kind: DutyItemKind
    subject: str = Field(description="volcano id, flight id, 'network' or region key")
    label: str = Field(description="Code-written, e.g. 'RFA4238 inside the area now'")
    mandatory: bool = Field(
        description="Code requires it this run: undispatched, it goes to the Desk"
    )
    urgency: int = Field(ge=0, description="0 is the most urgent")
    volcano_id: str | None = None


class DutyPriority(TephraModel):
    item_id: str
    why: str = Field(description="One line, operational language, no clock times")


class DutyBrief(TephraModel):
    """What the Duty Officer submits (its ``submit_brief`` tool arguments)."""

    summary: str = Field(description="The operational picture in at most three sentences")
    priorities: list[DutyPriority] = Field(description="Item ids in the order they matter")
    watch: list[str] = Field(default_factory=list, description="At most four things to watch")


class DutyDispatch(TephraModel):
    """One delegation to a specialist, recorded by code as it ran."""

    tool: str
    item_ids: list[str]
    ok: bool
    result: str = Field(description="Code-written summary of what the specialist returned")
    ms: int


class DutyDeferral(TephraModel):
    item_id: str
    reason: str


class DutyRun(TephraModel):
    """One Duty Officer run: the work list it was given, what it delegated, and its brief."""

    id: str = Field(description="'DUTY-' + 12 hex chars")
    started_at: UtcDatetime
    finished_at: UtcDatetime
    replay: bool
    trigger: Literal["tick", "adsb"]
    worklist: list[DutyItem]
    dispatches: list[DutyDispatch] = Field(default_factory=list)
    deferred: list[DutyDeferral] = Field(default_factory=list)
    brief: DutyBrief | None = None
    outcome: Literal["ACCEPTED", "REPAIRED", "MODEL_FAILED", "STUB"]
    llm_backend: LlmBackendName
    model_id: str
    prompt_hash: str
    turns: int = 0
    validation_errors: list[str] = Field(default_factory=list)
    undispatched: list[str] = Field(
        default_factory=list, description="Mandatory item ids left undone; each went to the Desk"
    )

    def dispatched_ids(self) -> set[str]:
        return {item_id for dispatch in self.dispatches for item_id in dispatch.item_ids}


class AiFailure(TephraModel):
    """An exposed flight the AI could not plan or draft for. There is no substitute plan or
    template: the Desk shows it so a dispatcher handles the flight by hand."""

    id: str = Field(description="stable_id('AIF', flight_id, cone_id, stage)")
    created_at: UtcDatetime
    replay: bool
    stage: Literal["duty_officer", "planner", "drafter"]
    reason: str = Field(description="Code-written: the error or the checks that failed")
    model_id: str
    volcano_id: str
    volcano_name: str
    flight_id: str
    proxy_flight: str
    callsign: str | None = None
    hex: str
    type_icao: str | None = None
    cone_id: str
    minutes_to_entry: int
    inside_now: bool
    plan_id: str | None = Field(default=None, description="Set when the drafter failed")
    handled_by: str | None = None
    handled_at: UtcDatetime | None = None
    handled_note: str | None = None


class OutboundMessage(TephraModel):
    """An approved advisory placed on TEPHRA's own queue. Never sent to an external system."""

    id: str
    advisory_id: str
    advisory_version: int
    queued_at: UtcDatetime
    proxy_flight: str
    status: AdvisoryStatus = Field(description="APPROVED or EDITED")
    approved_by: str
    text: str
    destination: Literal["tephra-outbound"] = "tephra-outbound"
    replay: bool = False
    replay_case_id: str | None = None
    queued_wall_at: UtcDatetime | None = Field(
        default=None,
        description="Wall-clock time of queueing (queued_at follows the REPLAY clock);"
        " None only on records written before the field",
    )
    policy_id: str | None = None
    policy_version: str | None = None
    policy_hash: str | None = None


class AuditEntry(TephraModel):
    id: str
    at: UtcDatetime
    actor: str = Field(description="'desk:<name>' for a dispatcher, 'system' for code")
    action: AuditAction
    advisory_id: str | None = None
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    input_hashes: list[str] = Field(default_factory=list)
    model_id: str | None = None
    prompt_hash: str | None = None
    note: str | None = None


# --- operations -------------------------------------------------------------------------


class FeedHealth(TephraModel):
    feed: FeedId
    status: FeedStatus
    cadence_s: int
    last_attempt_at: UtcDatetime | None = None
    last_success_at: UtcDatetime | None = None
    age_s: int | None = Field(default=None, description="Seconds since last_success_at")
    last_error: str | None = None
    record_count: int = 0
    replay: bool = False


class TraceEvent(TephraModel):
    """One line of the live reasoning trace on the Wall."""

    id: str
    at: UtcDatetime
    stage: TraceStage
    actor: TraceActor
    level: Literal["info", "warn", "error"] = "info"
    message: str
    volcano_id: str | None = None
    flight_id: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def new(
        cls,
        stage: TraceStage,
        actor: TraceActor,
        message: str,
        *,
        level: Literal["info", "warn", "error"] = "info",
        volcano_id: str | None = None,
        flight_id: str | None = None,
        detail: Mapping[str, Any] | None = None,
    ) -> Self:
        return cls(
            id=uuid4().hex,
            at=timeutil.now(),
            stage=stage,
            actor=actor,
            level=level,
            message=message,
            volcano_id=volcano_id,
            flight_id=flight_id,
            detail=dict(detail or {}),
        )


type TraceSink = Callable[[TraceEvent], None]
"""Callback the agents use to stream trace lines; core publishes them on the bus."""


class TickReport(TephraModel):
    started_at: UtcDatetime
    finished_at: UtcDatetime
    mode: RunMode
    reason: str = Field(description="'scheduler', 'local', 'startup' or 'manual'")
    skipped: bool = Field(default=False, description="True when another tick was running")
    feeds_polled: list[FeedId] = Field(default_factory=list)
    feed_errors: dict[str, str] = Field(default_factory=dict)
    active_volcano_ids: list[str] = Field(default_factory=list)
    assessments_run: int = 0
    satellite_reads: int = 0
    recovery_plans: int = 0
    duty_runs: int = 0
    exposed_flights: int = 0
    drafts_created: int = 0
    drafts_superseded: int = 0
    notes: list[str] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def duration_ms(self) -> int:
        return int((self.finished_at - self.started_at).total_seconds() * 1000)


class ReplayRecord(TephraModel):
    feed: FeedId
    url: str = Field(description="Exact URL fetched, including the query string")
    fetched_at: UtcDatetime
    sha256: str
    path: str = Field(description="Relative to the case directory, POSIX separators")
    status_code: int
    content_type: str | None = None


class ReplayCase(TephraModel):
    """``data/replay/<case_id>/manifest.json``."""

    case_id: str
    label: str = Field(description="Human label, e.g. 'Semeru SIGMET vs VONA, 7 Oct 2026'")
    recorded_from: UtcDatetime
    recorded_to: UtcDatetime
    region: str
    volcano_ids: list[str] = Field(default_factory=list)
    notes: str | None = None
    records: list[ReplayRecord]

    @model_validator(mode="after")
    def _window_in_order(self) -> Self:
        if self.recorded_to < self.recorded_from:
            raise ValueError("replay case recorded_to is before recorded_from")
        return self

    @property
    def reconstructed(self) -> bool:
        """Rebuilt from archives rather than recorded live: both such manifests open their
        notes with these words."""
        return (self.notes or "").startswith("Reconstructed from archives")


# --- the Wall: map features, cards, snapshot --------------------------------------------


class VolcanoFeatureProps(TephraModel):
    id: str
    name: str
    color_code: AviationColor
    active: bool
    vaac: VaacCentre
    summit_elev_ft: int
    label: str


class OfficialFeatureProps(TephraModel):
    source_id: str
    kind: Literal["SIGMET", "VAA"]
    layer: str
    label: str
    volcano_id: str | None = None
    base_ft: int
    top_ft: int
    valid_from: UtcDatetime
    valid_to: UtcDatetime


class ConeFeatureProps(TephraModel):
    cone_id: str
    volcano_id: str
    part: Literal["cone", "sector"]
    mode: PlumeMode
    confidence: float
    base_ft: int
    top_ft: int
    label: str
    valid_to: UtcDatetime


class AircraftFeatureProps(TephraModel):
    hex: str
    callsign: str | None = None
    proxy_flight: str
    type_icao: str | None = None
    alt_baro_ft: int | None = None
    nav_altitude_mcp_ft: int | None = None
    gs_kt: float | None = None
    track_deg: float | None = None
    observed_at: UtcDatetime
    exposed: bool
    minutes_to_entry: int | None = None
    volcano_id: str | None = None
    label: str = Field(description="e.g. 'RFA4821 FL350' or 'RFA4821 FL350 +14 MIN'")


class ExposureFeatureProps(TephraModel):
    flight_id: str
    proxy_flight: str
    volcano_id: str
    kind: Literal["path", "entry"]
    minutes_to_entry: int


class RerouteFeatureProps(TephraModel):
    """A reroute on the Wall: its path as a LineString, each turn point as a Point.

    ``route_string`` and ``waypoint_labels`` are written by code (``tephra.geo.reroute``).
    """

    flight_id: str
    proxy_flight: str
    volcano_id: str
    kind: RerouteKind
    status: RerouteStatus
    feature: Literal["path", "waypoint"]
    route_string: str
    extra_nm: float | None = None
    extra_min: float | None = None
    side: Literal["LEFT", "RIGHT"] | None = None
    label: str = Field(description="Path: 'RFA417 REROUTE +14 NM'; waypoint: '0812S11245E'")
    waypoint_labels: list[str] = Field(default_factory=list, description="Path only")


class BtdOverlay(TephraModel):
    source_id: str
    volcano_id: str
    image_url: str
    corners: list[Position] = Field(description="BBox.corners_lonlat() order")
    scan_start: UtcDatetime
    indicator: BtdIndicator
    negative_fraction: float
    caption: str


class FrameThumb(TephraModel):
    source_id: str
    volcano_id: str | None = None
    product: FrameProduct
    observed_at: UtcDatetime
    image_url: str
    corners: list[Position] | None = None
    caption: str


class Overlays(TephraModel):
    btd: list[BtdOverlay] = Field(default_factory=list)
    frames: list[FrameThumb] = Field(default_factory=list)


class SourceCard(TephraModel):
    """One of the three right-rail cards (SIGMET, VONA, VAA) for a volcano."""

    kind: ProductKind
    missing: bool
    missing_note: str | None = Field(default=None, description="Code-written, e.g. 'No VAA'")
    evidence: EvidenceState = EvidenceState.UNKNOWN
    source_id: str | None = None
    title: str
    issued_at: UtcDatetime | None = None
    valid_from: UtcDatetime | None = None
    valid_to: UtcDatetime | None = None
    fetched_at: UtcDatetime | None = None
    sha256_short: str | None = None
    url: str | None = None
    raw_text: str = ""
    stale: bool = False
    stale_age_s: int | None = None
    display_fields: dict[str, str] = Field(
        default_factory=dict, description="Ordered display fields, e.g. {'Top': 'FL150'}"
    )
    discrepancy_ids: list[str] = Field(default_factory=list)
    extra_source_ids: list[str] = Field(
        default_factory=list, description="Other valid products of the same kind"
    )


class SituationCard(TephraModel):
    volcano_id: str
    volcano_name: str
    color_code: AviationColor
    active_reasons: list[str]
    as_of: UtcDatetime
    cards: list[SourceCard] = Field(description="Exactly three: SIGMET, VONA, VAA in that order")
    discrepancies: list[Discrepancy]
    assessment: PlumeAssessment | None = None
    cone_id: str | None = None
    btd: BtdResult | None = None
    frames: list[FrameThumb] = Field(default_factory=list)
    exposed_count: int = 0


class WallSnapshot(TephraModel):
    """Everything the Wall draws; SSE events replace one section at a time."""

    generated_at: UtcDatetime
    volcanoes: dict[str, Any] = Field(description="FeatureCollection, VolcanoFeatureProps")
    official: dict[str, Any] = Field(description="FeatureCollection, OfficialFeatureProps")
    cones: dict[str, Any] = Field(description="FeatureCollection, ConeFeatureProps")
    exposures: dict[str, Any] = Field(description="FeatureCollection, ExposureFeatureProps")
    aircraft: dict[str, Any] = Field(description="FeatureCollection, AircraftFeatureProps")
    reroutes: dict[str, Any] = Field(
        default_factory=lambda: feature_collection([]),
        description="FeatureCollection, RerouteFeatureProps",
    )
    situations: list[SituationCard]
    overlays: Overlays
    duty: DutyRun | None = Field(default=None, description="The newest Duty Officer run")
    satellite: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Latest SatelliteReading per active volcano (agents.satellite_reader)",
    )


class LlmInfo(TephraModel):
    backend: LlmBackendName
    model_id: str
    label: str = Field(description="Model id, or 'NO MODEL' for the stub")


class ReplayInfo(TephraModel):
    case_id: str
    label: str
    recorded_from: UtcDatetime
    recorded_to: UtcDatetime
    banner: str = Field(description="'REPLAY: recorded real feeds from <date>'")
    auto: bool = Field(description="True when switched by TEPHRA_AUTO_REPLAY")


class AirlineInfo(TephraModel):
    code: str
    name: str
    fictional: Literal[True] = True


class SystemState(TephraModel):
    mode: RunMode
    now: UtcDatetime = Field(description="Active clock (recorded time in REPLAY)")
    server_time: UtcDatetime = Field(description="Wall-clock time of the server")
    replay: ReplayInfo | None = None
    llm: LlmInfo
    airline: AirlineInfo
    disclaimer: str
    region: Region
    regions: list[Region]
    feeds: list[FeedHealth]
    active_volcano_ids: list[str]
    exposed_count: int
    draft_count: int
    policy: PolicySummary
    last_tick: TickReport | None = None


# --- HTTP request and response bodies ---------------------------------------------------


class WallResponse(TephraModel):
    state: SystemState
    snapshot: WallSnapshot
    advisories: list[Advisory]
    trace: list[TraceEvent]


class PolicyResponse(TephraModel):
    """``GET /api/policy``: the active operator policy and its content hash."""

    policy: OperatorPolicy
    policy_hash: str


class LoginRequest(TephraModel):
    pin: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=2, max_length=32, description="Dispatcher name or initials")


class SessionInfo(TephraModel):
    name: str
    expires_at: UtcDatetime


class DecisionRequest(TephraModel):
    version: int = Field(ge=1, description="The version the dispatcher saw")


class EditRequest(DecisionRequest):
    body: str = Field(min_length=1)


class RejectRequest(DecisionRequest):
    reason: str = Field(min_length=3, max_length=500)


class AdvisoryList(TephraModel):
    advisories: list[Advisory]


class AiFailureList(TephraModel):
    failures: list[AiFailure]


class HandledRequest(TephraModel):
    note: str = Field(default="", max_length=500, description="What the dispatcher did")


class AuditList(TephraModel):
    entries: list[AuditEntry]


class OutboundList(TephraModel):
    messages: list[OutboundMessage]


class ErrorBody(TephraModel):
    """Every 4xx/5xx JSON body."""

    error: str = Field(description="Machine code, see MODULES.md")
    detail: str
    problems: list[str] = Field(default_factory=list)
    current: Advisory | None = Field(default=None, description="Set on version_conflict")


def dump_all(models: Sequence[BaseModel]) -> list[dict[str, Any]]:
    """JSON-mode dump of a list of models (store documents and event payloads)."""
    return [model.model_dump(mode="json") for model in models]
