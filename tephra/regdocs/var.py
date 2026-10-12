"""The ICAO Model VAR (volcanic ash report) layout, pre-filled from ADS-B and the hazard.

No model is involved: a VAR records what a crew saw, and a model must not invent that. Items 1
to 5 come from the ADS-B position of a proxy flight and from the official products; items 6 to
16 stay blank for the pilot or dispatcher. A VAR started from a crew report a dispatcher entered
(``draft_crew_var``) carries that report in items 1 to 5, 8, 14 and 15 instead. The form's
layout is ICAO's (PANS-ATM, Doc 4444, Appendix 1, Model VAR); the labels here are TEPHRA's own
wording.
"""

from typing import Final, Literal

from tephra.config import AIRLINE_NAME
from tephra.desk.approvals import SYSTEM_ACTOR
from tephra.geo.units import distance_nm, ft_to_fl, initial_bearing_deg
from tephra.models import (
    CREW_AREA_LABEL,
    CREW_CUE_TEXT,
    CREW_OUTSIDE_LINE,
    NO_CATALOGUED_VOLCANO,
    CrewArea,
    CrewCue,
    CrewPositionBasis,
    CrewReport,
    CrewReportKind,
    CrewReportView,
    ExposedFlight,
    HazardCone,
    OfficialLayer,
    PlumeMode,
    RunMode,
    Situation,
    TraceStage,
    VaacCentre,
)
from tephra.regdocs.common import band_text, document_labels
from tephra.regdocs.models import (
    VAR_HEADER,
    DocField,
    SignatureLine,
    SignRole,
    VarDraft,
    VarItem,
)
from tephra.regdocs.registry import record_new_doc
from tephra.regdocs.runtime import DocsRuntime
from tephra.util import timeutil
from tephra.util.hashing import sha256_json, stable_id

__all__ = ["FlightNotExposed", "NotAnAshReport", "draft_crew_var", "draft_var", "format_position"]

FORM_REFERENCE: Final = "ICAO Model VAR (PANS-ATM, Doc 4444, Appendix 1)"
NOT_AN_OBSERVATION: Final = (
    "TEPHRA reference from the official products. NOT a crew observation: the crew confirms or"
    " corrects it."
)
_POST_FLIGHT: Final[tuple[tuple[int, str, str], ...]] = (
    (9, "Density of the ash cloud", "wispy / moderately dense / very dense"),
    (10, "Colour of the cloud", "white / light grey / dark grey / black / other"),
    (11, "Eruption", "continuous / intermittent / not visible"),
    (12, "Position of the activity", "summit / side / single / multiple / not observed"),
    (13, "Other features", "lightning / glow / large rocks / ash fallout / mushroom cloud"),
    (
        14,
        "Effect on the aircraft",
        "communications / navigation / engines / pitot-static / windscreen",
    ),
    (15, "Other effects", "turbulence / St Elmo's fire / fumes or smell"),
    (16, "Other information", "free text"),
)


class FlightNotExposed(Exception):
    """The flight is not in the current exposure set, so there is nothing to pre-fill from."""


def format_position(lat: float, lon: float) -> str:
    """``0809S11342E``: degrees and minutes, the way an AIREP and a route string write them."""
    return f"{_dm(lat, 2, 'NS')}{_dm(lon, 3, 'EW')}"


def _dm(value: float, width: int, hemispheres: str) -> str:
    degrees, minutes = divmod(round(abs(value) * 60), 60)
    return f"{degrees:0{width}d}{minutes:02d}{hemispheres[0] if value >= 0 else hemispheres[1]}"


async def draft_var(runtime: DocsRuntime, flight_id: str, *, actor: str = SYSTEM_ACTOR) -> VarDraft:
    flight = runtime.exposed.get(flight_id)
    situation = runtime.situations.get(flight.volcano_id) if flight is not None else None
    if flight is None or situation is None:
        raise FlightNotExposed(flight_id)
    cone = runtime.cones.get(flight.volcano_id)
    state = await runtime.system_state()
    created = timeutil.now()
    layers = [layer for layer in situation.official_layers if layer.is_valid(situation.as_of)]
    facts = _facts(flight, cone, layers)
    input_hash = sha256_json(facts)
    items = _items(flight, situation, cone, layers)
    doc = VarDraft(
        id=stable_id("DOC", "VAR", flight_id, timeutil.to_iso(created), input_hash),
        header=VAR_HEADER,
        labels=[
            "ADS-B PROXY FLIGHT OF A FICTIONAL AIRLINE - NOT A REAL FLIGHT",
            *document_labels(state, backend=None),
        ],
        created_at=created,
        updated_at=created,
        replay=runtime.mode is RunMode.REPLAY,
        signatures=[
            SignatureLine(role=SignRole.PILOT_IN_COMMAND, label="Pilot-in-command"),
            SignatureLine(role=SignRole.DISPATCHER, label="Dispatcher"),
        ],
        input_hash=input_hash,
        flight_id=flight_id,
        proxy_flight=flight.proxy_flight,
        volcano_id=situation.volcano.id,
        volcano_name=situation.volcano.name,
        header_fields=_header_fields(flight, situation.volcano.vaac),
        items=items,
        airep_special=_airep_special(flight),
        ars_line=_ars_line(flight),
        non_encounter=DocField.to_complete(
            "non_encounter",
            "Ash NOT met in an area where it was forecast",
            note=(
                "PILOT/DISPATCHER TO COMPLETE. Doc 9974 asks the operator to report this too:"
                " mark ash encountered, or ash not encountered in a forecast area."
            ),
        ),
        context=_context(flight, situation, cone, layers),
        followups=_followups(situation.volcano.country),
    )
    await record_new_doc(runtime.store, runtime.bus, doc, actor=actor)
    runtime.trace(
        TraceStage.DOCS,
        "code",
        f"VAR DRAFT FOR {flight.proxy_flight} / {situation.volcano.name}: ITEMS 1-5 FROM ADS-B,"
        " 6-16 BLANK FOR THE CREW",
        volcano_id=situation.volcano.id,
        flight_id=flight_id,
        detail={"doc_id": doc.id},
    )
    return doc


def _facts(
    flight: ExposedFlight, cone: HazardCone | None, layers: list[OfficialLayer]
) -> dict[str, object]:
    return {
        "flight_id": flight.id,
        "observed_at": timeutil.to_iso(flight.observed_at),
        "lat": flight.lat,
        "lon": flight.lon,
        "alt_baro_ft": flight.alt_baro_ft,
        "cone_id": cone.id if cone is not None else None,
        "official": sorted(layer.source_id for layer in layers),
    }


def _header_fields(flight: ExposedFlight, vaac: VaacCentre) -> list[DocField]:
    ident = f"ADS-B callsign {flight.callsign or 'none'}, ICAO address {flight.hex}"
    return [
        DocField.code("operator", "Operator", f"{AIRLINE_NAME} (fictional)"),
        DocField.code(
            "ac_ident",
            "Aircraft identification",
            flight.proxy_flight,
            note=f"Proxy flight number derived from the aircraft ({ident}).",
        ),
        DocField.to_complete("pic", "Pilot-in-command"),
        DocField.to_complete("dep", "Departed from (airport, date, time UTC)"),
        DocField.to_complete("arr", "Arrived at (airport, date, time UTC)"),
        DocField.code(
            "addressee",
            "Addressee (suggestion)",
            f"Nearest ATS unit while airborne; after landing the VAAC for the area ({vaac.value})"
            " and the operator's own safety reporting.",
            note="Verify against the current Doc 4444 and the AIP before use.",
        ),
    ]


def _items(
    flight: ExposedFlight,
    situation: Situation,
    cone: HazardCone | None,
    layers: list[OfficialLayer],
) -> list[VarItem]:
    in_flight = [
        _item(
            1, "in_flight", DocField.code("item_1", "Aircraft identification", flight.proxy_flight)
        ),
        _item(
            2,
            "in_flight",
            DocField.code(
                "item_2",
                "Position",
                format_position(flight.lat, flight.lon),
                note="ADS-B position of the proxy flight.",
            ),
        ),
        _item(
            3,
            "in_flight",
            DocField.code(
                "item_3",
                "Time (UTC)",
                timeutil.hhmmz(flight.observed_at),
                note="Time of the ADS-B position.",
            ),
        ),
        _item(4, "in_flight", _level_field(flight)),
        _item(5, "in_flight", _activity_field(flight, situation, cone, layers)),
        _item(6, "in_flight", DocField.to_complete("item_6", "Air temperature"), hint="degrees C"),
        _item(
            7, "in_flight", DocField.to_complete("item_7", "Spot wind"), hint="direction / speed"
        ),
        _item(
            8,
            "in_flight",
            DocField.to_complete("item_8", "Supplementary information"),
            hint="SO2 detected Y/N; ash encountered Y/N; extent, movement, rate of growth",
        ),
    ]
    post_flight = [
        _item(number, "post_flight", DocField.to_complete(f"item_{number}", label), hint=hint)
        for number, label, hint in _POST_FLIGHT
    ]
    return [*in_flight, *post_flight]


def _item(
    number: int,
    group: Literal["in_flight", "post_flight"],
    field: DocField,
    *,
    hint: str | None = None,
) -> VarItem:
    return VarItem.model_validate(
        {**field.model_dump(), "number": number, "group": group, "hint": hint}
    )


def _level_field(flight: ExposedFlight) -> DocField:
    if flight.alt_baro_ft is None:
        return DocField.to_complete(
            "item_4", "Flight level or altitude", note="ADS-B gave no barometric altitude."
        )
    return DocField.code(
        "item_4",
        "Flight level or altitude",
        f"FL{ft_to_fl(flight.alt_baro_ft):03d}",
        note="ADS-B pressure altitude.",
    )


def _activity_field(
    flight: ExposedFlight,
    situation: Situation,
    cone: HazardCone | None,
    layers: list[OfficialLayer],
) -> DocField:
    volcano = situation.volcano
    bearing = initial_bearing_deg(flight.lat, flight.lon, volcano.lat, volcano.lon)
    distance = distance_nm(flight.lat, flight.lon, volcano.lat, volcano.lon)
    value = (
        f"{volcano.name}, vent at {format_position(volcano.lat, volcano.lon)}:"
        f" bearing {round(bearing):03d} deg true, {round(distance)} NM from the aircraft."
    )
    if layers:
        value += f" Official ash top FL{ft_to_fl(max(layer.top_ft for layer in layers)):03d}."
    elif cone is not None and cone.mode is PlumeMode.HYPOTHESIS:
        value += (
            f" No valid official product: TEPHRA estimate {band_text(cone.base_ft, cone.top_ft)}."
        )
    return DocField.code(
        "item_5",
        "Volcanic activity observed at (position or bearing, estimated ash level, distance)",
        value,
        note=NOT_AN_OBSERVATION,
        source_ids=sorted(layer.source_id for layer in layers),
    )


def _airep_special(flight: ExposedFlight) -> DocField:
    label = "Voice report (AIREP SPECIAL)"
    if flight.alt_baro_ft is None:
        return DocField.to_complete("airep_special", label, note="No ADS-B level for the report.")
    value = (
        f"AIREP SPECIAL {flight.proxy_flight} {format_position(flight.lat, flight.lon)}"
        f" {_hhmm(flight)} FL{ft_to_fl(flight.alt_baro_ft):03d} VOLCANIC ASH CLOUD"
    )
    return DocField.code(
        "airep_special",
        label,
        value,
        note="Template for the crew. TEPHRA does not know whether the crew saw ash: use it only"
        " if they report ash, through their own channel.",
    )


def _ars_line(flight: ExposedFlight) -> DocField:
    label = "ATS to MWO line (ARS), for reference"
    if flight.alt_baro_ft is None:
        return DocField.to_complete("ars_line", label, note="No ADS-B level for the report.")
    value = (
        f"ARS {flight.proxy_flight} {format_position(flight.lat, flight.lon)} {_hhmm(flight)}"
        f" F{ft_to_fl(flight.alt_baro_ft):03d} VA CLD="
    )
    return DocField.code(
        "ars_line",
        label,
        value,
        note="The ATS unit writes this line, not the crew. Shown so the dispatcher can read the"
        " same report back.",
    )


def _hhmm(flight: ExposedFlight) -> str:
    return timeutil.hhmmz(flight.observed_at).removesuffix("Z")


def _context(
    flight: ExposedFlight,
    situation: Situation,
    cone: HazardCone | None,
    layers: list[OfficialLayer],
) -> list[DocField]:
    fields: list[DocField] = []
    entry = (
        "inside the hazard area now"
        if flight.inside_now
        else (
            f"enters the hazard area in {flight.minutes_to_entry} min if track and level are held"
        )
    )
    fields.append(DocField.code("exposure", "Exposure when drafted", entry))
    if cone is not None:
        label = f"{cone.label} {band_text(cone.base_ft, cone.top_ft)}"
        fields.append(DocField.code("cone", "TEPHRA hazard cone", label, source_ids=[cone.id]))
    official = ", ".join(
        f"{layer.label} {band_text(layer.base_ft, layer.top_ft)}" for layer in layers
    )
    fields.append(
        DocField.code(
            "official",
            "Official areas valid at the time",
            official or "none valid",
            source_ids=sorted(layer.source_id for layer in layers),
        )
    )
    stamps = _source_stamps(situation)
    fields.append(
        DocField.code(
            "sources",
            "Product issue times",
            "; ".join(f"{source_id} issued {issued}" for source_id, issued in stamps) or "none",
            source_ids=[source_id for source_id, _ in stamps],
        )
    )
    return fields


def _source_stamps(situation: Situation) -> list[tuple[str, str]]:
    stamps: list[tuple[str, str]] = []
    for record in [*situation.sigmets, *situation.vonas, *situation.vaas]:
        issued = record.provenance.issued_at
        if issued is not None:
            stamps.append((record.provenance.source_id, timeutil.ddhhmmz(issued)))
    return stamps


def _followups(country: str) -> list[str]:
    steps = [
        "Make the aircraft maintenance log (AML) entry.",
        "File the air safety report (ASR) in the operator's safety reporting system.",
        "Report to the State authority under its mandatory occurrence rules (verify the route).",
        "Keep the aircraft out of service until it has been inspected per the manufacturer's"
        " guidance.",
    ]
    if country == "Indonesia":
        steps.append(
            "Document the encounter through the safety reporting system, as SE-DJPU 15/2026 is"
            " reported to require (per press reports of the circular; verify against the PDF)."
        )
    return steps


# --- a VAR pre-filled from a crew report ---------------------------------------------------


class NotAnAshReport(Exception):
    """Only a crew report of ash (an area that was drawn, not withdrawn) becomes a VAR."""


async def draft_crew_var(
    runtime: DocsRuntime,
    view: CrewReportView,
    *,
    vaac: VaacCentre | None,
    actor: str = SYSTEM_ACTOR,
) -> VarDraft:
    """The message to the weather office and the VAAC, started from a crew report: the VAR
    layout with the crew's own report in items 1 to 5, 8, 14 and 15 and the discrepancy with
    the official products in the context. A human signs it; TEPHRA sends nothing."""
    report = view.report
    area = report.area
    if report.kind is not CrewReportKind.ASH or area is None or report.withdrawn_at is not None:
        raise NotAnAshReport(report.id)
    state = await runtime.system_state()
    created = timeutil.now()
    facts: dict[str, object] = {
        "crew_report_id": report.id,
        "state": view.state,
        "covered_by": view.covered_by,
        "outside_official": view.outside_official,
    }
    input_hash = sha256_json(facts)
    entered = (
        f"From the crew report entered by {report.entered_by.removeprefix('desk:')} at"
        f" {timeutil.hhmmz(report.created_at)}; the crew confirms or corrects it."
    )
    doc = VarDraft(
        id=stable_id("DOC", "VAR", report.id, timeutil.to_iso(created), input_hash),
        header=VAR_HEADER,
        labels=[
            "CREW REPORT ENTERED BY A DISPATCHER - NOT FROM A FEED",
            f"FLIGHT OF A FICTIONAL AIRLINE ({report.flight}) - NOT A REAL FLIGHT",
            *document_labels(state, backend=None),
        ],
        created_at=created,
        updated_at=created,
        replay=report.replay,
        signatures=[
            SignatureLine(role=SignRole.PILOT_IN_COMMAND, label="Pilot-in-command"),
            SignatureLine(role=SignRole.DISPATCHER, label="Dispatcher"),
        ],
        input_hash=input_hash,
        flight_id=report.hex or report.callsign or report.id,
        proxy_flight=report.flight,
        volcano_id=report.volcano_id,
        volcano_name=report.volcano_name or NO_CATALOGUED_VOLCANO,
        crew_report_id=report.id,
        header_fields=_crew_header_fields(report, vaac),
        items=_crew_items(report, entered),
        airep_special=_crew_airep(report),
        ars_line=_crew_ars(report),
        non_encounter=DocField.code(
            "non_encounter",
            "Ash NOT met in an area where it was forecast",
            "Not this report: the crew reported ash or an encounter cue.",
        ),
        context=_crew_context(view, area),
        followups=_crew_followups(view, vaac),
    )
    await record_new_doc(runtime.store, runtime.bus, doc, actor=actor)
    runtime.trace(
        TraceStage.DOCS,
        "code",
        f"VAR DRAFT FROM THE CREW REPORT OF {report.flight} ({timeutil.hhmmz(report.observed_at)})"
        ": FOR THE WEATHER OFFICE AND THE VAAC, NOT TRANSMITTED",
        volcano_id=report.volcano_id,
        detail={"doc_id": doc.id, "report_id": report.id},
    )
    return doc


def _crew_level(report: CrewReport) -> str:
    if report.level_from_fl == report.level_to_fl:
        return f"FL{report.level_from_fl:03d}"
    return f"FL{report.level_from_fl:03d} TO FL{report.level_to_fl:03d}"


def _crew_header_fields(report: CrewReport, vaac: VaacCentre | None) -> list[DocField]:
    centre = f"the VAAC ({vaac.value})" if vaac is not None else "the VAAC responsible for the area"
    return [
        DocField.code("operator", "Operator", f"{AIRLINE_NAME} (fictional)"),
        DocField.code("ac_ident", "Aircraft identification", report.flight),
        DocField.to_complete("pic", "Pilot-in-command"),
        DocField.to_complete("dep", "Departed from (airport, date, time UTC)"),
        DocField.to_complete("arr", "Arrived at (airport, date, time UTC)"),
        DocField.code(
            "addressee",
            "Addressee (suggestion)",
            f"The meteorological watch office (MWO) for the FIR, and {centre}.",
            note="Verify against the current Doc 4444 and the AIP before use.",
        ),
    ]


def _crew_items(report: CrewReport, entered: str) -> list[VarItem]:
    given = set(report.cues)
    basis = (
        f"ADS-B fix of the reporting flight at {timeutil.hhmmz(report.position_observed_at)}."
        if report.position_basis is CrewPositionBasis.ADSB_FIX and report.position_observed_at
        else "Typed by the dispatcher."
    )
    cues = ", ".join(CREW_CUE_TEXT[cue] for cue in report.cues)
    encounter = sorted(
        CREW_CUE_TEXT[cue] for cue in given & {CrewCue.HAZE, CrewCue.ST_ELMOS_FIRE, CrewCue.ENGINE}
    )
    supplementary = (
        f"Sulphur smell: {'yes' if CrewCue.SULPHUR_SMELL in given else 'not reported'};"
        f" ash seen: {'yes' if CrewCue.ASH_SEEN in given else 'not reported'};"
        f" encounter cues: {', '.join(encounter) or 'none reported'}."
    )
    other = [
        text
        for cue, text in (
            (CrewCue.ST_ELMOS_FIRE, "St Elmo's fire"),
            (CrewCue.SULPHUR_SMELL, "fumes or smell"),
            (CrewCue.HAZE, "haze or dust in the cabin"),
        )
        if cue in given
    ]
    in_flight = [
        _item(1, "in_flight", DocField.code("item_1", "Aircraft identification", report.flight)),
        _item(
            2,
            "in_flight",
            DocField.code(
                "item_2", "Position", format_position(report.lat, report.lon), note=basis
            ),
        ),
        _item(
            3,
            "in_flight",
            DocField.code("item_3", "Time (UTC)", timeutil.hhmmz(report.observed_at), note=entered),
        ),
        _item(
            4,
            "in_flight",
            DocField.code("item_4", "Flight level or altitude", _crew_level(report), note=entered),
        ),
        _item(
            5,
            "in_flight",
            DocField.code(
                "item_5",
                "Volcanic activity observed at (position or bearing, estimated ash level,"
                " distance)",
                f"{cues} at {format_position(report.lat, report.lon)}, {_crew_level(report)}"
                f" ({report.volcano_name or NO_CATALOGUED_VOLCANO}).",
                note=entered,
            ),
        ),
        _item(6, "in_flight", DocField.to_complete("item_6", "Air temperature"), hint="degrees C"),
        _item(
            7, "in_flight", DocField.to_complete("item_7", "Spot wind"), hint="direction / speed"
        ),
        _item(
            8,
            "in_flight",
            DocField.code("item_8", "Supplementary information", supplementary, note=entered),
            hint="SO2 detected Y/N; ash encountered Y/N; extent, movement, rate of growth",
        ),
    ]
    post_flight: list[VarItem] = []
    for number, label, hint in _POST_FLIGHT:
        field = DocField.to_complete(f"item_{number}", label)
        if number == 14 and CrewCue.ENGINE in given:
            field = DocField.code(f"item_{number}", label, "engines", note=entered)
        elif number == 15 and other:
            field = DocField.code(f"item_{number}", label, " / ".join(other), note=entered)
        elif number == 16 and report.remarks:
            field = DocField.code(
                f"item_{number}", label, report.remarks, note="The dispatcher's remarks."
            )
        post_flight.append(_item(number, "post_flight", field, hint=hint))
    return [*in_flight, *post_flight]


def _crew_airep(report: CrewReport) -> DocField:
    value = (
        f"AIREP SPECIAL {report.flight} {format_position(report.lat, report.lon)}"
        f" {timeutil.hhmmz(report.observed_at).removesuffix('Z')} {_crew_level(report)}"
        " VOLCANIC ASH CLOUD"
    )
    return DocField.code(
        "airep_special",
        "Voice report (AIREP SPECIAL)",
        value,
        note="As the crew would have voiced it, rebuilt from the report; for reference.",
    )


def _crew_ars(report: CrewReport) -> DocField:
    label = "ATS to MWO line (ARS), for reference"
    if report.level_from_fl != report.level_to_fl:
        return DocField.to_complete(
            "ars_line", label, note="The crew reported a band; the ATS unit writes the level."
        )
    value = (
        f"ARS {report.flight} {format_position(report.lat, report.lon)}"
        f" {timeutil.hhmmz(report.observed_at).removesuffix('Z')} F{report.level_from_fl:03d}"
        " VA CLD="
    )
    return DocField.code(
        "ars_line",
        label,
        value,
        note="The ATS unit writes this line, not the crew. Shown so the dispatcher can read the"
        " same report back.",
    )


def _crew_context(view: CrewReportView, area: CrewArea) -> list[DocField]:
    report = view.report
    fields = [
        DocField.code(
            "crew_area",
            CREW_AREA_LABEL,
            f"{area.radius_nm} NM around the report; {band_text(area.base_ft, area.top_ft)};"
            f" {area.stretch_note[:1].lower()}{area.stretch_note[1:]};"
            f" valid {timeutil.hhmmz(area.valid_from)} to"
            f" {timeutil.hhmmz(area.valid_to)}.",
            source_ids=[report.id] + ([area.wind_source_id] if area.wind_source_id else []),
        ),
        DocField.code("state", "State when drafted", view.state_label),
    ]
    if view.covered_by:
        relation = f"Covered by official area: {', '.join(view.covered_by)}"
    elif view.outside_official:
        relation = f"{CREW_OUTSIDE_LINE}: no valid official area meets it, laterally and vertically"
    else:
        relation = "Partly inside an official area"
    fields.append(
        DocField.code(
            "official", "Against the official areas", relation, source_ids=view.covered_by
        )
    )
    return fields


def _crew_followups(view: CrewReportView, vaac: VaacCentre | None) -> list[str]:
    centre = f"the VAAC ({vaac.value})" if vaac is not None else "the VAAC responsible for the area"
    steps = ["Check the report with the crew before anything leaves the operator."]
    if view.outside_official:
        steps.append(
            "Pass the difference between the official products and this crew report to the MWO"
            f" for the FIR and to {centre} through the operator's own channel; TEPHRA sends"
            " nothing. EUR Doc 019 3.2.9 e) asks that reported differences between published"
            " information and pilot reports are forwarded as soon as possible."
        )
    else:
        steps.append(
            f"Pass the report to the MWO for the FIR and to {centre} through the operator's own"
            " channel if the crew has not; TEPHRA sends nothing."
        )
    if CrewCue.ENGINE in view.report.cues or CrewCue.ST_ELMOS_FIRE in view.report.cues:
        steps += [
            "Make the aircraft maintenance log (AML) entry.",
            "Keep the aircraft out of service until it has been inspected per the manufacturer's"
            " guidance.",
        ]
    return steps
