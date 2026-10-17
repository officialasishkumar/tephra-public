"""A message to the weather office and the VAAC, started from a crew report of ash.

EUR Doc 019 3.2.9 e) asks that "reported differences between published information and
observations (pilot reports, airborne measurements, etc.) are forwarded as soon as possible to
the appropriate authorities". This drafts that message: who it is for, a subject, and a short
text a dispatcher reads out or pastes into the operator's own channel. Code writes every line
from the report and the official products; no model is involved, and TEPHRA sends nothing.
The message names the nearest catalogued volcano only as a distance, never as the source.
"""

from datetime import datetime
from typing import Final

from tephra.config import Airline
from tephra.desk.approvals import SYSTEM_ACTOR
from tephra.models import (
    CREW_AREA_LABEL,
    CREW_CUE_TEXT,
    CrewPositionBasis,
    CrewReport,
    CrewReportKind,
    CrewReportView,
    TraceStage,
    VaacCentre,
)
from tephra.regdocs.common import band_text, document_labels, stamped_header
from tephra.regdocs.models import (
    VAR_HEADER,
    CrewMessageDraft,
    DocField,
    SignatureLine,
    SignRole,
)
from tephra.regdocs.registry import record_new_doc
from tephra.regdocs.runtime import DocsRuntime
from tephra.regdocs.var import format_position
from tephra.util import timeutil
from tephra.util.hashing import sha256_json, stable_id

__all__ = ["NotAnAshReport", "draft_crew_message"]

MWO: Final = "The meteorological watch office (MWO) for the FIR"


class NotAnAshReport(Exception):
    """Only a crew report of ash (an area was drawn) that is not withdrawn starts a message."""


async def draft_crew_message(
    runtime: DocsRuntime,
    view: CrewReportView,
    *,
    vaac: VaacCentre | None,
    actor: str = SYSTEM_ACTOR,
) -> CrewMessageDraft:
    report = view.report
    if report.kind is not CrewReportKind.ASH or report.area is None or report.withdrawn_at:
        raise NotAnAshReport(report.id)
    state = await runtime.system_state()
    airline = runtime.settings.airline
    created = timeutil.now()
    facts_in: dict[str, object] = {
        "crew_report_id": report.id,
        "state": view.state,
        "covered_by": view.covered_by,
        "outside_detail": view.outside_detail,
    }
    input_hash = sha256_json(facts_in)
    centre = (
        f"{vaac.value.title()} VAAC" if vaac is not None else "The VAAC responsible for the area"
    )
    subject = _subject(view)
    against = _against(view, created)
    body = "\n".join(
        [
            f"{_who(report, airline)} reported {_cues(report)} at"
            f" {format_position(report.lat, report.lon)}, {_level(report)}, at"
            f" {timeutil.hhmmz(report.observed_at)}.",
            _basis(report),
            against,
            _near(report, runtime.settings.active_radius_km),
            *([f"Crew remarks as entered: {report.remarks}"] if report.remarks else []),
            "Please take this report into account in the next VA advisory and VA SIGMET.",
            _signed(airline),
        ]
    )
    area = report.area
    doc = CrewMessageDraft(
        id=stable_id("DOC", "CREW_MESSAGE", report.id, timeutil.to_iso(created), input_hash),
        header=stamped_header(VAR_HEADER, shadow=airline.shadow),
        shadow=airline.shadow,
        labels=[
            "CREW REPORT ENTERED BY A DISPATCHER - NOT FROM A FEED",
            *([label] if (label := _flight_label(report, airline)) else []),
            *document_labels(state, backend=None),
        ],
        created_at=created,
        updated_at=created,
        replay=report.replay,
        signatures=[SignatureLine(role=SignRole.DISPATCHER, label="Dispatcher")],
        input_hash=input_hash,
        crew_report_id=report.id,
        flight=report.flight,
        title=f"Message to the weather office and VAAC: crew report from {report.flight}",
        to=[
            DocField.code(
                "to_mwo",
                "To",
                MWO,
                note="Verify the address against the AIP before use.",
            ),
            DocField.code("to_vaac", "To", centre),
            DocField.code(
                "from",
                "From",
                f"{airline.name} dispatch" + (" (fictional)" if airline.fictional else ""),
            ),
        ],
        subject=DocField.code("subject", "Subject", subject),
        body=body,
        facts=[
            DocField.code(
                "report",
                "Crew report",
                f"Entered by {report.entered_by.removeprefix('desk:')} at"
                f" {timeutil.hhmmz(report.created_at)}; {view.state_label.lower()}.",
                source_ids=[report.id],
            ),
            DocField.code(
                "official",
                "Against the official areas",
                against,
                source_ids=view.covered_by,
            ),
            DocField.code(
                "crew_area",
                CREW_AREA_LABEL,
                f"{area.radius_nm} NM around the report; {band_text(area.base_ft, area.top_ft)};"
                f" valid {timeutil.hhmmz(area.valid_from)} to {timeutil.hhmmz(area.valid_to)}."
                " TEPHRA's own flag, not part of the message.",
                source_ids=[area.wind_source_id] if area.wind_source_id else [],
            ),
        ],
        followups=[
            "Check the report with the crew before anything leaves the operator.",
            "Send it through the operator's own channel; TEPHRA sends nothing.",
            "Sign below to record who checked it. Withdrawing the crew report withdraws this"
            " message.",
        ],
    )
    await record_new_doc(runtime.store, runtime.bus, doc, actor=actor)
    runtime.trace(
        TraceStage.DOCS,
        "code",
        f"MESSAGE TO THE WEATHER OFFICE AND VAAC FROM THE CREW REPORT OF {report.flight}"
        f" ({timeutil.hhmmz(report.observed_at)}): DRAFT, NOT TRANSMITTED",
        volcano_id=report.volcano_id,
        detail={"doc_id": doc.id, "report_id": report.id},
    )
    return doc


def _subject(view: CrewReportView) -> str:
    if view.state == "COVERED":
        return "CREW REPORT OF VOLCANIC ASH INSIDE THE PUBLISHED VA AREA"
    if view.outside_detail is not None and view.outside_detail.startswith("Part"):
        return "CREW REPORT OF VOLCANIC ASH PARTLY OUTSIDE THE PUBLISHED VA AREA"
    return "CREW REPORT OF VOLCANIC ASH OUTSIDE THE PUBLISHED VA AREA"


def _against(view: CrewReportView, at: datetime) -> str:
    when = timeutil.hhmmz(at)
    if view.state == "COVERED":
        return f"At {when}, it lies inside the valid VA SIGMET and VA advisory areas."
    if view.outside_detail is not None and view.outside_detail.startswith("Part"):
        return (
            f"At {when}, part of it lies outside every valid VA SIGMET and VA advisory area,"
            " sideways or in height."
        )
    return f"At {when}, no valid VA SIGMET or VA advisory area meets it, sideways or in height."


def _signed(airline: Airline) -> str:
    if airline.fictional:
        return f"{airline.name} dispatch (fictional airline; decision support only)."
    return f"{airline.name} dispatch (decision support only)."


def _who(report: CrewReport, airline: Airline) -> str:
    if report.proxy_flight is not None:
        seen = f" for ADS-B callsign {report.callsign}" if report.callsign else ""
        if not airline.fictional:
            return f"{report.proxy_flight} ({airline.name} flight{seen})"
        return f"{report.proxy_flight} (proxy flight of the fictional airline{seen})"
    return f"Callsign {report.callsign} (typed by the dispatcher; not tracked by TEPHRA)"


def _flight_label(report: CrewReport, airline: Airline) -> str | None:
    """The fictional airline's proxy flight is labelled not real; an airline's own flight
    needs no label."""
    if report.proxy_flight is not None:
        if not airline.fictional:
            return None
        return f"{report.proxy_flight}: PROXY FLIGHT OF A FICTIONAL AIRLINE - NOT A REAL FLIGHT"
    return f"CALLSIGN {report.callsign} TYPED BY A DISPATCHER - NOT TRACKED BY TEPHRA"


def _cues(report: CrewReport) -> str:
    return ", ".join(CREW_CUE_TEXT[cue] for cue in report.cues)


def _level(report: CrewReport) -> str:
    if report.level_from_fl == report.level_to_fl:
        return f"FL{report.level_from_fl:03d}"
    return f"FL{report.level_from_fl:03d} to FL{report.level_to_fl:03d}"


def _basis(report: CrewReport) -> str:
    if report.position_basis is CrewPositionBasis.ADSB_FIX and report.position_observed_at:
        return (
            "Position: the flight's ADS-B fix at"
            f" {timeutil.hhmmz(report.position_observed_at)}, not a position the crew gave."
        )
    return "Position: as the crew reported it, typed by the dispatcher."


def _near(report: CrewReport, radius_km: float) -> str:
    if report.volcano_name is None or report.volcano_distance_km is None:
        return f"No catalogued volcano lies within {radius_km:.0f} km of the report."
    return (
        f"Nearest catalogued volcano: {report.volcano_name},"
        f" {report.volcano_distance_km:.0f} km from the report. The source is not known."
    )
