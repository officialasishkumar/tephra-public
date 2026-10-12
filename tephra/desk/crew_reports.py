"""Crew (pilot) reports of ash, entered by a dispatcher on the Desk.

A report of ash seen, or of any encounter cue (a smell together with haze, St Elmo's fire,
engine signs), draws a "crew report caution area": a circle of the policy radius around the
reported position, stretched downwind when the wind at the reported level is strong, within
the reported level band plus the policy margin, for the policy validity from the observation
time. A sulphur smell or haze alone is a routine report and a "no ash seen" report is
recorded; neither draws or removes anything.

The area is a flag only. It never shrinks or replaces an official area, an official product
never shortens or removes it, and it never makes the code think an official area is in force:
it lives beside the situations and cones, never in them. Nothing here plans, drafts or calls
a model. Code writes every time, id, coordinate and line; a report is refused rather than
completed with a guess (no level, no position, a time in the future).
"""

from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timedelta
from typing import Final, NamedTuple
from uuid import uuid4

from pydantic import Field, model_validator

from tephra.desk import audit
from tephra.desk.approvals import SYSTEM_ACTOR
from tephra.geo.crew_area import (
    WIND_PROFILE_SLACK,
    area_polygon,
    pick_wind,
    relation_to_official,
    stretch_note,
)
from tephra.geo.exposure import Crossing, find_crossings
from tephra.geo.units import haversine_km
from tephra.models import (
    CREW_AREA_CUES,
    CREW_AREA_LABEL,
    CREW_FLAG_LINE,
    CREW_OUTSIDE_LINE,
    CREW_REPORTER_LINE,
    CREW_SMELL_AND_HAZE,
    NO_CATALOGUED_VOLCANO,
    Aircraft,
    AuditAction,
    CrewArea,
    CrewCue,
    CrewFeatureProps,
    CrewFlag,
    CrewPicture,
    CrewPositionBasis,
    CrewReport,
    CrewReportKind,
    CrewReportPolicy,
    CrewReportState,
    CrewReportView,
    GeoLineString,
    OfficialLayer,
    PolicySummary,
    TephraModel,
    UtcDatetime,
    Volcano,
    WindProfile,
    feature,
    feature_collection,
    is_airline_callsign,
    point,
)
from tephra.store.base import Collection, Store
from tephra.util import timeutil
from tephra.util.hashing import proxy_flight_number

__all__ = [
    "LIST_WINDOW",
    "LOAD_LIMIT",
    "AlreadyWithdrawn",
    "CheckedEntry",
    "CrewEntry",
    "CrewFix",
    "CrewReportNotFound",
    "CrewReportRefused",
    "FixHistory",
    "FixLookup",
    "WithdrawRequest",
    "build_picture",
    "build_report",
    "check_entry",
    "expire",
    "find_fix",
    "load_reports",
    "record_entry",
    "report_kind",
    "report_view",
    "resolve_flight",
    "withdraw",
]

LIST_WINDOW: Final = timedelta(hours=24)
"""The Wall and the Desk list reports observed this long ago or less; older ones stay in the
store and the audit trail."""
LOAD_LIMIT: Final = 500
MIN_WITHDRAW_REASON_CHARS: Final = 3
MAX_REMARKS_CHARS: Final = 300


class CrewReportRefused(Exception):
    """The entry cannot become a report as given; nothing was stored."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


class CrewReportNotFound(Exception): ...


class AlreadyWithdrawn(Exception): ...


class CrewEntry(TephraModel):
    """``POST /api/desk/crew-reports``. The flight is a tracked one (``hex``) or a typed
    airline callsign; the position is left out to use the flight's ADS-B fix."""

    hex: str | None = Field(default=None, pattern=r"^[0-9a-f]{6}$")
    callsign: str | None = Field(default=None, min_length=4, max_length=7)
    cues: list[CrewCue] = Field(min_length=1, max_length=len(CrewCue))
    level_from_fl: int | None = Field(default=None, ge=0, le=600)
    level_to_fl: int | None = Field(default=None, ge=0, le=600)
    observed_at: UtcDatetime
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    remarks: str | None = Field(default=None, max_length=MAX_REMARKS_CHARS)

    @model_validator(mode="after")
    def _one_flight(self) -> "CrewEntry":
        if (self.hex is None) == (self.callsign is None):
            raise ValueError("give exactly one of hex (a tracked flight) and callsign")
        return self


class WithdrawRequest(TephraModel):
    reason: str = Field(min_length=MIN_WITHDRAW_REASON_CHARS, max_length=500)


class CrewFix(NamedTuple):
    """One ADS-B position of an airline target, kept to place a late-entered report."""

    hex: str
    callsign: str | None
    lat: float
    lon: float
    alt_baro_ft: int | None
    observed_at: datetime
    source_id: str


class FixLookup(TephraModel):
    """``GET /api/desk/crew-reports/fix``: the fix the entry form would use, or why none."""

    found: bool
    hex: str | None = None
    proxy_flight: str | None = None
    callsign: str | None = None
    lat: float | None = None
    lon: float | None = None
    alt_baro_ft: int | None = None
    observed_at: UtcDatetime | None = None
    source_id: str | None = None
    note: str


class FixHistory:
    """Recent ADS-B positions of airline targets, per ICAO address. The live picture keeps
    only each target's newest position; a report entered minutes after the observation needs
    the position at the observation time."""

    def __init__(self, keep: timedelta) -> None:
        self.keep = keep
        self._fixes: dict[str, deque[CrewFix]] = {}

    def add(self, aircraft: Iterable[Aircraft], at: datetime) -> None:
        for target in aircraft:
            if not target.airline:
                continue
            fixes = self._fixes.setdefault(target.hex, deque())
            if fixes and fixes[-1].observed_at >= target.observed_at:
                continue
            fixes.append(
                CrewFix(
                    target.hex,
                    target.callsign,
                    target.lat,
                    target.lon,
                    target.alt_baro_ft,
                    target.observed_at,
                    target.source_id,
                )
            )
        cutoff = at - self.keep
        for hex_id in list(self._fixes):
            fixes = self._fixes[hex_id]
            while fixes and fixes[0].observed_at < cutoff:
                fixes.popleft()
            if not fixes:
                del self._fixes[hex_id]

    def clear(self) -> None:
        self._fixes.clear()

    def fixes(self, hex_id: str) -> Sequence[CrewFix]:
        return tuple(self._fixes.get(hex_id, ()))

    def hexes(self) -> list[str]:
        return sorted(self._fixes)

    def callsigns(self, hex_id: str) -> set[str]:
        return {fix.callsign for fix in self._fixes.get(hex_id, ()) if fix.callsign}


# --- entry -------------------------------------------------------------------------------


def report_kind(cues: Sequence[CrewCue]) -> CrewReportKind:
    given = set(cues)
    if CrewCue.ASH_SEEN in given and CrewCue.NO_ASH_SEEN in given:
        raise CrewReportRefused(["cues: 'ash seen' and 'no ash seen' cannot both be reported"])
    if given & CREW_AREA_CUES or given >= CREW_SMELL_AND_HAZE:
        return CrewReportKind.ASH
    if given & CREW_SMELL_AND_HAZE:
        return CrewReportKind.ROUTINE
    return CrewReportKind.NO_ASH


def resolve_flight(
    hex_id: str | None, typed: str | None, aircraft: Sequence[Aircraft], history: FixHistory
) -> tuple[str | None, str | None]:
    """``(hex, callsign)`` of the reporting flight. A tracked flight is named by its ICAO
    address; a typed callsign becomes that flight only when exactly one tracked target flies
    it, and stays an untracked callsign when none does. Exactly one of the two is given."""
    newest: dict[str, str | None] = {
        known: fixes[-1].callsign for known in history.hexes() if (fixes := history.fixes(known))
    }
    flown: dict[str, set[str]] = {known: history.callsigns(known) for known in history.hexes()}
    for target in aircraft:
        if target.airline:
            newest[target.hex] = target.callsign
            flown.setdefault(target.hex, set()).update([target.callsign] if target.callsign else [])
    if hex_id is not None:
        if hex_id not in newest:
            raise CrewReportRefused(["hex: not a tracked airline flight; type its callsign"])
        return hex_id, newest[hex_id]
    callsign = "".join((typed or "").split()).upper()
    if not is_airline_callsign(callsign):
        raise CrewReportRefused(["callsign: an airline callsign such as GIA417"])
    matches = sorted(known for known, names in flown.items() if callsign in names)
    if len(matches) > 1:
        raise CrewReportRefused(
            [f"callsign: {len(matches)} tracked flights fly {callsign}; pick the flight"]
        )
    return (matches[0] if matches else None), callsign


def find_fix(
    hex_id: str | None,
    observed_at: datetime,
    aircraft: Sequence[Aircraft],
    history: FixHistory,
    *,
    within: timedelta,
) -> CrewFix | None:
    """The flight's ADS-B position nearest the observation time, if one lies within
    ``within`` of it (the ADS-B stale age). Never an older or a projected one."""
    if hex_id is None:
        return None
    fixes = list(history.fixes(hex_id))
    for target in aircraft:
        if target.hex == hex_id:
            fixes.append(
                CrewFix(
                    target.hex,
                    target.callsign,
                    target.lat,
                    target.lon,
                    target.alt_baro_ft,
                    target.observed_at,
                    target.source_id,
                )
            )
    near = [fix for fix in fixes if abs(fix.observed_at - observed_at) <= within]
    if not near:
        return None
    return min(near, key=lambda fix: (abs(fix.observed_at - observed_at), fix.observed_at))


class CheckedEntry(NamedTuple):
    """An entry that passed every check: what it is, its levels and where it was."""

    kind: CrewReportKind
    levels: tuple[int, int]
    lat: float
    lon: float
    basis: CrewPositionBasis


def check_entry(
    entry: CrewEntry,
    *,
    at: datetime,
    flight: tuple[str | None, str | None],
    fix: CrewFix | None,
    fix_within: timedelta,
    policy: CrewReportPolicy,
) -> CheckedEntry:
    """Validate the entry; :class:`CrewReportRefused` lists every problem. The time is checked
    before the position: the ADS-B fix is looked up at the observation time, so a time that
    cannot be right says nothing about the position."""
    problems: list[str] = []
    kind: CrewReportKind | None = None
    try:
        kind = report_kind(entry.cues)
    except CrewReportRefused as exc:
        problems += exc.problems
    levels = _levels(entry, problems)
    time_problem = observed_problem(entry.observed_at, at, policy)
    position = None
    if time_problem is not None:
        problems.append(time_problem)
    else:
        hex_id, callsign = flight
        name = proxy_flight_number(hex_id) if hex_id else callsign
        position = _position(entry, fix, name or "the flight", fix_within, problems)
    if problems or kind is None or levels is None or position is None:
        raise CrewReportRefused(problems)
    return CheckedEntry(kind, levels, *position)


def observed_problem(observed_at: datetime, at: datetime, policy: CrewReportPolicy) -> str | None:
    """Why an observation time cannot be used, or None."""
    valid_min = policy.valid_min.value
    if observed_at > at:
        return (
            f"observed_at: {timeutil.hhmmz(observed_at)} is later than TEPHRA's clock"
            f" ({timeutil.hhmmz(at)}); a crew report cannot be in the future"
        )
    if observed_at < at - timedelta(minutes=valid_min):
        return (
            f"observed_at: {timeutil.hhmmz(observed_at)} is more than {valid_min} min before"
            f" TEPHRA's clock ({timeutil.hhmmz(at)}), longer than a crew report area lasts"
        )
    return None


def build_report(
    entry: CrewEntry,
    checked: CheckedEntry,
    *,
    actor: str,
    at: datetime,
    replay_case_id: str | None,
    flight: tuple[str | None, str | None],
    fix: CrewFix | None,
    volcano: Volcano | None,
    winds: Sequence[WindProfile],
    wind_place: str,
    no_wind_reason: str,
    policy: CrewReportPolicy,
    summary: PolicySummary,
) -> CrewReport:
    """The report of a checked entry, with its area drawn when it is a report of ash.
    ``winds`` are the profiles at ``wind_place`` (or none, for ``no_wind_reason``)."""
    kind, levels, lat, lon, basis = checked
    distance = haversine_km(lat, lon, volcano.lat, volcano.lon) if volcano else None
    area = None
    if kind is CrewReportKind.ASH:
        area = _area(
            lat,
            lon,
            levels,
            entry.observed_at,
            winds,
            wind_place,
            no_wind_reason,
            policy,
        )
    hex_id, callsign = flight
    adsb = basis is CrewPositionBasis.ADSB_FIX and fix is not None
    return CrewReport(
        id=f"CR-{uuid4().hex[:12]}",
        created_at=at,
        entered_wall_at=timeutil.SystemClock().now(),
        entered_by=actor,
        replay=replay_case_id is not None,
        replay_case_id=replay_case_id,
        hex=hex_id,
        callsign=callsign,
        proxy_flight=proxy_flight_number(hex_id) if hex_id else None,
        cues=list(dict.fromkeys(entry.cues)),
        kind=kind,
        observed_at=entry.observed_at,
        level_from_fl=levels[0],
        level_to_fl=levels[1],
        lat=lat,
        lon=lon,
        position_basis=basis,
        position_source_id=fix.source_id if adsb and fix else None,
        position_observed_at=fix.observed_at if adsb and fix else None,
        volcano_id=volcano.id if volcano is not None else None,
        volcano_name=volcano.name if volcano is not None else None,
        volcano_distance_km=round(distance, 1) if distance is not None else None,
        area=area,
        remarks=(" ".join(entry.remarks.split()) or None) if entry.remarks else None,
        policy_id=summary.policy_id,
        policy_version=summary.version,
        policy_hash=summary.policy_hash[:12],
    )


def _levels(entry: CrewEntry, problems: list[str]) -> tuple[int, int] | None:
    low, high = entry.level_from_fl, entry.level_to_fl
    if low is None:
        problems.append(
            "level: a crew report needs the reported flight level or band; TEPHRA never invents one"
        )
        return None
    high = low if high is None else high
    if high < low:
        problems.append("level: the lower flight level of the band comes first")
        return None
    return low, high


def _position(
    entry: CrewEntry,
    fix: CrewFix | None,
    name: str,
    within: timedelta,
    problems: list[str],
) -> tuple[float, float, CrewPositionBasis] | None:
    typed = entry.lat is not None or entry.lon is not None
    if typed and (entry.lat is None or entry.lon is None):
        problems.append("position: give both latitude and longitude")
        return None
    if fix is not None:
        if typed:
            problems.append(
                f"position: TEPHRA holds the ADS-B fix of {name} at"
                f" {timeutil.hhmmz(fix.observed_at)}; leave the position empty and the fix is"
                " used"
            )
            return None
        return fix.lat, fix.lon, CrewPositionBasis.ADSB_FIX
    if entry.lat is None or entry.lon is None:
        problems.append(
            f"position: no ADS-B fix of {name} within {round(within.total_seconds())} s of"
            f" {timeutil.hhmmz(entry.observed_at)}; type the position the crew reported"
        )
        return None
    return entry.lat, entry.lon, CrewPositionBasis.TYPED


def _area(
    lat: float,
    lon: float,
    levels: tuple[int, int],
    observed_at: datetime,
    profiles: Sequence[WindProfile],
    wind_place: str,
    no_wind_reason: str,
    policy: CrewReportPolicy,
) -> CrewArea:
    margin = policy.level_margin_ft.value
    base_ft = max(0, levels[0] * 100 - margin)
    top_ft = levels[1] * 100 + margin
    wind = pick_wind(profiles, observed_at, base_ft, top_ft)
    if wind is None and profiles:
        slack = round(WIND_PROFILE_SLACK.total_seconds() / 60)
        no_wind_reason = (
            f"no wind profile {wind_place} within {slack} min of {timeutil.hhmmz(observed_at)}"
        )
    threshold = policy.stretch_wind_kt.value
    stretch_nm = 0.0
    if wind is not None and wind.level.speed_kt > threshold:
        stretch_nm = wind.level.speed_kt * policy.downwind_stretch_min.value / 60.0
    radius = policy.radius_nm.value
    toward = wind.level.toward_deg if wind is not None else 0.0
    return CrewArea(
        polygon=area_polygon(lat, lon, radius, stretch_nm=stretch_nm, toward_deg=toward),
        radius_nm=radius,
        base_ft=base_ft,
        top_ft=top_ft,
        valid_from=observed_at,
        valid_to=observed_at + timedelta(minutes=policy.valid_min.value),
        stretched=stretch_nm > 0,
        stretch_nm=round(stretch_nm, 1) if stretch_nm > 0 else None,
        stretch_toward_deg=round(toward, 1) if stretch_nm > 0 else None,
        wind_kt=round(wind.level.speed_kt, 1) if wind is not None else None,
        wind_from_deg=round(wind.level.from_deg, 1) if wind is not None else None,
        wind_fl=wind.level.flight_level if wind is not None else None,
        wind_source_id=wind.source_id if wind is not None else None,
        stretch_note=stretch_note(
            wind,
            threshold_kt=threshold,
            stretch_nm=stretch_nm,
            wind_place=wind_place,
            no_wind_reason=no_wind_reason,
        ),
    )


# --- store and audit ---------------------------------------------------------------------


async def record_entry(store: Store, report: CrewReport) -> None:
    await store.put(Collection.CREW_REPORTS, report.id, report.model_dump(mode="json"))
    await audit.record(
        store,
        actor=report.entered_by,
        action=AuditAction.CREW_REPORT_ENTERED,
        after=_audit_view(report),
        note=_entry_note(report),
    )


async def withdraw(store: Store, report: CrewReport, *, reason: str, actor: str) -> CrewReport:
    """For entry errors (wrong flight, position or time). The report stays in the store and
    the audit trail; only its area stops counting."""
    cleaned = " ".join(reason.split())
    if len(cleaned) < MIN_WITHDRAW_REASON_CHARS:
        raise CrewReportRefused([f"reason: at least {MIN_WITHDRAW_REASON_CHARS} characters"])
    if report.withdrawn_at is not None:
        raise AlreadyWithdrawn(report.id)
    withdrawn = report.model_copy(
        update={"withdrawn_at": timeutil.now(), "withdrawn_by": actor, "withdraw_reason": cleaned}
    )
    await store.put(Collection.CREW_REPORTS, report.id, withdrawn.model_dump(mode="json"))
    await audit.record(
        store,
        actor=actor,
        action=AuditAction.CREW_REPORT_WITHDRAWN,
        before=_audit_view(report),
        after=_audit_view(withdrawn),
        note=cleaned,
    )
    return withdrawn


async def expire(
    store: Store, report: CrewReport, at: datetime, *, note: str | None = None
) -> CrewReport:
    """Write the expiry once: the area lapsed at its ``valid_to``, or ``note`` says what else
    ended it (the replay run it was entered in). An official product never ends one."""
    expired = report.model_copy(update={"expiry_recorded_at": at})
    await store.put(Collection.CREW_REPORTS, report.id, expired.model_dump(mode="json"))
    valid_to = report.area.valid_to if report.area is not None else None
    if note is None and valid_to is not None:
        note = f"crew report area lapsed at {timeutil.hhmmz(valid_to)}"
    await audit.record(
        store,
        actor=SYSTEM_ACTOR,
        action=AuditAction.CREW_REPORT_EXPIRED,
        before=_audit_view(report),
        after=_audit_view(expired),
        note=note,
    )
    return expired


async def load_reports(store: Store) -> list[CrewReport]:
    """Newest first; both modes (callers filter by mode and replay case)."""
    docs = await store.query(
        Collection.CREW_REPORTS, [], order_by="created_at", descending=True, limit=LOAD_LIMIT
    )
    return [CrewReport.model_validate(doc) for doc in docs]


def _audit_view(report: CrewReport) -> dict[str, object]:
    area = report.area
    return {
        "report_id": report.id,
        "kind": report.kind.value,
        "flight": report.flight,
        "hex": report.hex,
        "cues": [cue.value for cue in report.cues],
        "observed_at": timeutil.to_iso(report.observed_at),
        "level_fl": [report.level_from_fl, report.level_to_fl],
        "lat": report.lat,
        "lon": report.lon,
        "position_basis": report.position_basis.value,
        "position_source_id": report.position_source_id,
        "volcano_id": report.volcano_id,
        "band_ft": [area.base_ft, area.top_ft] if area else None,
        "valid_to": timeutil.to_iso(area.valid_to) if area else None,
        "wind_source_id": area.wind_source_id if area else None,
        "replay": report.replay,
        "replay_case_id": report.replay_case_id,
        "policy_id": report.policy_id,
        "policy_version": report.policy_version,
        "policy_hash": report.policy_hash,
        "withdrawn": report.withdrawn_at is not None,
    }


def _entry_note(report: CrewReport) -> str:
    if report.kind is CrewReportKind.ROUTINE:
        return "routine report (sulphur smell or haze alone): no area"
    if report.kind is CrewReportKind.NO_ASH:
        return "no ash seen: recorded; it removes nothing"
    return f"{CREW_AREA_LABEL} drawn"


# --- the picture -------------------------------------------------------------------------


def build_picture(
    reports: Iterable[CrewReport],
    *,
    at: datetime,
    replay_case_id: str | None,
    replay: bool,
    replay_run_since: datetime | None,
    aircraft: Sequence[Aircraft],
    layers: Sequence[OfficialLayer],
    lookahead_min: int,
) -> CrewPicture:
    """The reports of the current mode (and replay case, and replay run: entered on the wall
    clock at or after ``replay_run_since``) observed by ``at`` and within :data:`LIST_WINDOW`,
    with their states, the flights their active areas flag, and the map features. The official
    layers only set the display state; they never change an area.

    A flight is flagged when its projected level is inside the area's band, which already
    holds the policy level margin around the reported level: no second margin is added."""
    shown = sorted(
        (
            report
            for report in reports
            if report.replay == replay
            and (not replay or report.replay_case_id == replay_case_id)
            and (replay_run_since is None or report.entered_wall_at >= replay_run_since)
            and at - LIST_WINDOW <= report.observed_at <= at
        ),
        key=lambda report: (report.observed_at, report.id),
        reverse=True,
    )
    crossings: dict[str, list[Crossing]] = {}
    views: list[CrewReportView] = []
    for report in shown:
        state, covered_by, outside = _state(report, layers, at)
        hits: list[Crossing] = []
        area = report.area
        if area is not None and state in ("ACTIVE", "COVERED"):
            remaining = int((area.valid_to - at).total_seconds() // 60)
            hits = find_crossings(
                area.polygon,
                area.base_ft,
                area.top_ft,
                aircraft,
                at,
                lookahead_min=max(0, min(lookahead_min, remaining)),
                vertical_margin_ft=0,
            )
            crossings[report.id] = hits
        views.append(_view(report, state, covered_by, outside, hits, at))
    flags = _flags(crossings, {report.id: report for report in shown})
    return CrewPicture(reports=views, flags=flags, features=_features(views, flags))


def report_view(
    report: CrewReport, layers: Sequence[OfficialLayer], at: datetime
) -> CrewReportView:
    """One report's view outside the picture (another mode, or older than the window). It
    flags nothing: only the picture projects flights."""
    state, covered_by, outside = _state(report, layers, at)
    return _view(report, state, covered_by, outside, [], at)


_OUTSIDE_DETAIL: Final = {
    "OUTSIDE": "No valid official area meets it, sideways or in height.",
    "OVERLAPS": "Part of it lies outside every valid official area, sideways or in height.",
}


def _state(
    report: CrewReport, layers: Sequence[OfficialLayer], at: datetime
) -> tuple[CrewReportState, list[str], str | None]:
    """The state, the official layers covering the area, and why it is outside them (None
    when covered or not drawn). An expiry once recorded stands: a replay played again from
    an earlier time never brings the area back."""
    if report.withdrawn_at is not None:
        return "WITHDRAWN", [], None
    area = report.area
    if area is None:
        return "NO_AREA", [], None
    if report.expiry_recorded_at is not None or not area.is_valid(at):
        return "EXPIRED", [], None
    relation = relation_to_official(area.polygon, area.base_ft, area.top_ft, layers, at)
    if relation.relation == "COVERED":
        return "COVERED", relation.covered_by, None
    return "ACTIVE", [], _OUTSIDE_DETAIL[relation.relation]


_STATE_LABELS: Final[dict[CrewReportState, str]] = {
    "ACTIVE": "Active",
    "COVERED": "Covered by official area",
    "EXPIRED": "Expired",
    "WITHDRAWN": "Withdrawn",
}


def _state_label(report: CrewReport, state: CrewReportState) -> str:
    if state != "NO_AREA":
        return _STATE_LABELS[state]
    if report.kind is CrewReportKind.ROUTINE:
        alone = "haze only" if CrewCue.HAZE in report.cues else "sulphur smell only"
        return f"Routine report, no area ({alone})"
    return "No ash seen: no area, and it removes nothing"


def _view(
    report: CrewReport,
    state: CrewReportState,
    covered_by: list[str],
    outside: str | None,
    hits: Sequence[Crossing],
    at: datetime,
) -> CrewReportView:
    age_min = max(0, int((at - report.observed_at).total_seconds() // 60))
    return CrewReportView(
        report=report,
        state=state,
        state_label=_state_label(report, state),
        age_min=age_min,
        age_text="reported just now" if age_min < 1 else f"reported {_duration_text(age_min)} ago",
        place_text=_place_text(report),
        covered_by=covered_by,
        outside_official=outside is not None,
        discrepancy=CREW_OUTSIDE_LINE if outside is not None else None,
        outside_detail=outside,
        flagged=sorted({hit.target.hex for hit in hits}),
    )


def _duration_text(minutes: int) -> str:
    if minutes < 120:
        return f"{minutes} min"
    hours, rest = divmod(minutes, 60)
    return f"{hours} h {rest} min" if rest else f"{hours} h"


def _place_text(report: CrewReport) -> str:
    if report.volcano_name is None or report.volcano_distance_km is None:
        return NO_CATALOGUED_VOLCANO
    return f"near {report.volcano_name} ({report.volcano_distance_km:.0f} km)"


def _flags(
    crossings: Mapping[str, Sequence[Crossing]], reports: Mapping[str, CrewReport]
) -> list[CrewFlag]:
    """One flag per flight: the earliest entry over every area it crosses."""
    by_hex: dict[str, tuple[Crossing, list[str]]] = {}
    for report_id, hits in crossings.items():
        for hit in hits:
            held = by_hex.get(hit.target.hex)
            if held is None:
                by_hex[hit.target.hex] = (hit, [report_id])
                continue
            earliest = hit if hit.step < held[0].step else held[0]
            by_hex[hit.target.hex] = (earliest, [*held[1], report_id])
    flags = []
    for hex_id, (hit, report_ids) in by_hex.items():
        target = hit.target
        volcanoes = {reports[rid].volcano_id for rid in report_ids} - {None}
        reporter = any(reports[rid].hex == hex_id for rid in report_ids)
        flags.append(
            CrewFlag(
                hex=hex_id,
                callsign=target.callsign,
                proxy_flight=target.proxy_flight,
                alt_baro_ft=target.alt_baro_ft,
                report_ids=sorted(report_ids),
                volcano_ids=sorted(v for v in volcanoes if v is not None),
                inside_now=hit.step == 0,
                minutes_to_entry=hit.step,
                entry_lat=hit.entry[0],
                entry_lon=hit.entry[1],
                path=hit.path,
                reporter=reporter,
                line=CREW_REPORTER_LINE if reporter else CREW_FLAG_LINE,
            )
        )
    return sorted(flags, key=lambda flag: (flag.minutes_to_entry, flag.hex))


def _features(views: Sequence[CrewReportView], flags: Sequence[CrewFlag]) -> dict[str, object]:
    features = []
    drawn = {view.report.id: view for view in views if view.state in ("ACTIVE", "COVERED")}
    for view in drawn.values():
        report, area = view.report, view.report.area
        if area is None:
            continue
        for part in ("area", "pin"):
            props = CrewFeatureProps(
                report_id=report.id,
                feature=part,
                state=view.state,
                label=CREW_AREA_LABEL if part == "area" else f"{report.flight} {view.age_text}",
                flight=report.flight,
                volcano_id=report.volcano_id,
                age_text=view.age_text,
                base_ft=area.base_ft,
                top_ft=area.top_ft,
                valid_to=area.valid_to,
                replay=report.replay,
            )
            geometry = area.polygon if part == "area" else point(report.lat, report.lon)
            features.append(feature(geometry, props, feature_id=f"{report.id}#{part}"))
    for flag in flags:
        view = drawn[flag.report_ids[0]]
        props = CrewFeatureProps(
            report_id=view.report.id,
            feature="path",
            state=view.state,
            label=flag.line,
            flight=flag.proxy_flight,
            volcano_id=view.report.volcano_id,
            age_text=view.age_text,
            replay=view.report.replay,
        )
        geometry = GeoLineString(coordinates=flag.path)
        features.append(feature(geometry, props, feature_id=f"{flag.hex}#crew-path"))
    return feature_collection(features)
