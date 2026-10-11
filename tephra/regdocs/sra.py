"""The SRA draft: sections after the layout of ICAO Doc 9974, filled by code from TEPHRA's
evidence, plus four narrative boxes written by one lite-model call.

Fields TEPHRA cannot know stay blank for a person (AOC number, severity, probability,
tolerability, MEL relief, the accountable executive). The wording is TEPHRA's own; ICAO text is
quoted only in short pieces and cited by title, because clause numbers differ between copies of
Doc 9974. The document is a DRAFT: it is not an SRA until the operator's accountable executive
accepts it and the regulator evaluates it.
"""

from collections.abc import Sequence
from typing import Any, Final

from tephra.agents.llm import LlmCall
from tephra.config import AIRLINE_NAME
from tephra.desk import audit
from tephra.desk.approvals import SYSTEM_ACTOR
from tephra.geo.units import ft_to_fl
from tephra.models import (
    ActionKind,
    Advisory,
    AdvisoryStatus,
    AuditAction,
    ExposedFlight,
    OperatorPolicy,
    PolicySummary,
    Provenance,
    Situation,
    TraceStage,
)
from tephra.regdocs.common import band_text, document_labels
from tephra.regdocs.evidence import Evidence, FlightView, VolcanoView, gather_evidence
from tephra.regdocs.models import (
    SRA_HEADER,
    DocField,
    DocTable,
    SignatureLine,
    SignRole,
    SraDraft,
    SraNarrative,
    SraSection,
)
from tephra.regdocs.narrative import AiUnavailable, write_narrative
from tephra.regdocs.registry import record_new_doc
from tephra.regdocs.runtime import DocsRuntime
from tephra.util import timeutil
from tephra.util.hashing import sha256_json, short_hash, stable_id

__all__ = ["DOC_9974", "build_sra", "draft_sra", "narrative_facts"]

DOC_9974: Final = "ICAO Doc 9974, Flight Safety and Volcanic Ash, First Edition 2012"
QUOTE_SRA: Final = "an identifiable safety risk assessment within its SMS"
QUOTE_CONFLICTS: Final = "to reliably and correctly resolve any conflicts among data sources"
QUOTE_NOT_MITIGATED: Final = (
    "Not all risks may be suitably mitigated; in such cases, the operation should not proceed."
)
SE_DJPU_NOTE: Final = "per press reports of the circular; verify against the PDF"
MAX_FACT_FLIGHTS: Final = 20
MAX_LOG_ROWS: Final = 50
_DECIDED: Final = frozenset({AdvisoryStatus.APPROVED, AdvisoryStatus.EDITED})
BLANK_FOR_RISK_OWNER: Final = "RISK OWNER TO COMPLETE"
_NOT_FILLED: Final = "Left blank on purpose: TEPHRA does not know this."


async def draft_sra(runtime: DocsRuntime, region: str, *, actor: str = SYSTEM_ACTOR) -> SraDraft:
    """Build, store and announce an SRA draft for a region.

    Raises ``UnknownRegion`` or ``NoActiveVolcano`` (nothing to assess) and, when the model
    gives no usable narrative, ``AiUnavailable`` after an audit entry and a trace line; no
    document is stored then.
    """
    evidence = await gather_evidence(runtime, region)
    facts = narrative_facts(evidence, runtime.policy)
    try:
        narrative, call = await write_narrative(runtime.llm, facts)
    except AiUnavailable as exc:
        await audit.record(
            runtime.store,
            actor=SYSTEM_ACTOR,
            action=AuditAction.AI_FAILED,
            after={"doc_kind": "SRA", "region": region},
            input_hashes=[sha256_json(facts)],
            model_id=exc.model_id,
            note=str(exc),
        )
        runtime.trace(
            TraceStage.DOCS,
            "code",
            f"SRA DRAFT FOR {evidence.region.name.upper()}: {exc}",
            level="error",
        )
        raise
    doc = build_sra(evidence, runtime.policy, runtime.policy_summary, narrative, call, facts=facts)
    await record_new_doc(
        runtime.store,
        runtime.bus,
        doc,
        actor=actor,
        model_id=call.model_id,
        prompt_hash=call.prompt_hash,
    )
    runtime.trace(
        TraceStage.DOCS,
        "gemini" if call.backend == "gemini" else "stub",
        f"SRA DRAFT FOR {evidence.region.name.upper()}: EVIDENCE BY CODE, 4 NARRATIVE BOXES"
        f" ({'AI-WRITTEN' if call.backend == 'gemini' else 'NO MODEL'}); NOT AN APPROVED SRA",
        detail={"doc_id": doc.id},
    )
    return doc


# --- facts for the model ----------------------------------------------------------------


def narrative_facts(evidence: Evidence, policy: OperatorPolicy) -> dict[str, Any]:
    """Everything the model may say. No clock times: it must not copy one."""
    inside = sum(view.flight.inside_now for view in evidence.flights)
    conflicts = [
        {
            "id": item.id,
            "volcano": view.situation.volcano.name,
            "kind": item.kind.value,
            "aspect": item.aspect,
            "severity": item.severity.value,
            "source_ids": item.source_ids,
        }
        for view in evidence.volcanoes
        for item in view.situation.discrepancies
    ]
    return {
        "airline": f"{AIRLINE_NAME} (fictional)",
        "region": evidence.region.name,
        "run_mode": "REPLAY" if evidence.replay else "LIVE",
        "counts": {
            "volcanoes": len(evidence.volcanoes),
            "conflicts": len(conflicts),
            "exposed": len(evidence.flights),
            "inside_now": inside,
            "advisories": len(evidence.advisories),
        },
        "policy": {
            "vertical_margin_ft": policy.exposure.vertical_margin_ft.value,
            "source_order": [rule.text for rule in policy.source_order],
        },
        "volcanoes": [_volcano_facts(view) for view in evidence.volcanoes],
        "conflicts": conflicts,
        "feeds": [
            {"feed": feed.feed.value, "status": feed.status.value, "age_min": _age_min(feed.age_s)}
            for feed in evidence.state.feeds
        ],
        "flights": [_flight_facts(view) for view in evidence.flights[:MAX_FACT_FLIGHTS]],
        "allowed_ids": _allowed_ids(evidence),
    }


def _volcano_facts(view: VolcanoView) -> dict[str, Any]:
    situation, cone = view.situation, view.cone
    return {
        "name": situation.volcano.name,
        "plume_mode": cone.mode.value if cone is not None else None,
        "cone_confidence_pct": round(cone.confidence * 100) if cone is not None else None,
        "cone_band": band_text(cone.base_ft, cone.top_ft) if cone is not None else None,
        "official_band": _official_band(situation),
        "official_layers_valid": len(_valid_layers(situation)),
        "colour_code": view.color.value,
    }


def _flight_facts(view: FlightView) -> dict[str, Any]:
    advisory = view.advisory
    return {
        "flight": view.flight.proxy_flight,
        "status": _status_text(view.flight),
        "action": advisory.action.value if advisory is not None else None,
        "advisory_status": advisory.status.value if advisory is not None else None,
        "ai_failure_open": view.failure is not None,
    }


def _allowed_ids(evidence: Evidence) -> list[str]:
    ids: set[str] = set()
    for view in evidence.volcanoes:
        ids |= view.situation.source_ids()
        ids |= {item.id for item in view.situation.discrepancies}
        if view.cone is not None:
            ids.add(view.cone.id)
    ids |= {advisory.id for advisory in evidence.advisories}
    return sorted(ids)


# --- the document -----------------------------------------------------------------------


def build_sra(
    evidence: Evidence,
    policy: OperatorPolicy,
    summary: PolicySummary,
    narrative: SraNarrative,
    call: LlmCall,
    *,
    facts: dict[str, Any],
) -> SraDraft:
    sections = [
        _status_section(evidence, policy, summary),
        _scope_section(evidence),
        _sources_section(evidence, narrative),
        _hazard_section(evidence, policy, narrative),
        _worksheet_section(policy),
        _exposure_section(evidence, policy, narrative),
        _mitigation_section(evidence, narrative),
        _watch_section(evidence),
        _reporting_section(evidence),
        _assumptions_section(),
        _signoff_section(evidence),
    ]
    if any(view.situation.volcano.country == "Indonesia" for view in evidence.volcanoes):
        sections.append(_indonesia_section(evidence))
    input_hash = sha256_json(facts)
    created = evidence.created
    return SraDraft(
        id=stable_id("DOC", "SRA", evidence.region.key, timeutil.to_iso(created), input_hash),
        header=SRA_HEADER,
        labels=document_labels(evidence.state, backend=call.backend),
        created_at=created,
        updated_at=created,
        replay=evidence.replay,
        signatures=[
            SignatureLine(role=SignRole.DISPATCHER, label="Dispatcher or OCC manager"),
            SignatureLine(role=SignRole.SAFETY_MANAGER, label="Safety manager"),
            SignatureLine(role=SignRole.ACCOUNTABLE_EXECUTIVE, label="Accountable executive"),
        ],
        input_hash=input_hash,
        region_key=evidence.region.key,
        region_name=evidence.region.name,
        volcano_ids=[view.situation.volcano.id for view in evidence.volcanoes],
        policy_id=policy.policy_id,
        policy_version=policy.version,
        policy_hash=summary.policy_hash,
        llm_backend=call.backend,
        model_id=call.model_id,
        prompt_hash=call.prompt_hash,
        sections=sections,
        source_ids=facts["allowed_ids"],
    )


def _status_section(
    evidence: Evidence, policy: OperatorPolicy, summary: PolicySummary
) -> SraSection:
    region = evidence.region
    return SraSection(
        number=0,
        key="status",
        title="Status block",
        reference=f'{DOC_9974}: the operator keeps "{QUOTE_SRA}".',
        fields=[
            DocField.code("document", "Document", f"Draft SRA evidence pack for {region.name}"),
            DocField.code("generated", "Generated (UTC)", timeutil.to_iso(evidence.created)),
            DocField.code(
                "mode",
                "Picture",
                evidence.state.replay.banner if evidence.state.replay else "LIVE feeds",
            ),
            DocField.code(
                "policy",
                "Operator policy",
                f"{policy.policy_id} version {policy.version}"
                f" (hash {short_hash(summary.policy_hash)})",
                note=policy.label,
            ),
            DocField.code("risk_owner", "Risk owner named by the policy", policy.risk_owner),
            DocField.to_complete("accountable", "Accountable executive", note=BLANK_FOR_RISK_OWNER),
            DocField.to_complete("acceptance", "Regulator acceptance reference", note=_NOT_FILLED),
        ],
    )


def _scope_section(evidence: Evidence) -> SraSection:
    region = evidence.region
    box = region.bbox
    types = ", ".join(f"{name} x{count}" for name, count in evidence.aircraft_types)
    fields = [
        DocField.code("operator", "Operator", f"{AIRLINE_NAME} (fictional airline)"),
        DocField.to_complete("aoc", "Air operator certificate number", note=_NOT_FILLED),
        DocField.code(
            "types",
            "Aircraft types seen",
            types or "none seen in the region on ADS-B",
            note="ADS-B proxies of the fictional airline in the region now;"
            " its fleet is not modelled.",
        ),
        DocField.to_complete("engines", "Engine types", note=_NOT_FILLED),
        DocField.to_complete("fleet", "Number of aircraft", note=_NOT_FILLED),
        DocField.code(
            "zones",
            "Zone of operation",
            f"{region.name}: latitude {box.south} to {box.north},"
            f" longitude {box.west} to {box.east}",
        ),
        DocField.code(
            "phase",
            "Flight phase",
            "En route, as seen on ADS-B proxies; departures and arrivals are not modelled.",
        ),
    ]
    if not any(view.situation.volcano.country == "Indonesia" for view in evidence.volcanoes):
        fields.append(
            DocField.to_complete(
                "state_rules",
                "State requirements",
                note="No State circular is loaded in TEPHRA for this region."
                " Add the State's own rules.",
            )
        )
    return SraSection(
        number=1,
        key="scope",
        title="Scope and operation",
        reference=f"{DOC_9974}, Appendix G (the operation)",
        fields=fields,
    )


def _sources_section(evidence: Evidence, narrative: SraNarrative) -> SraSection:
    records = [
        [
            view.situation.volcano.name,
            provenance.source_id,
            provenance.feed.value,
            _time_text(provenance.issued_at),
            _time_text(provenance.fetched_at),
            "stale" if provenance.stale else "fresh",
        ]
        for view in evidence.volcanoes
        for provenance in _key_provenances(view.situation)
    ]
    conflicts = [
        [
            view.situation.volcano.name,
            item.kind.value,
            item.aspect,
            item.severity.value,
            item.summary,
            ", ".join(item.source_ids),
        ]
        for view in evidence.volcanoes
        for item in view.situation.discrepancies
    ]
    return SraSection(
        number=2,
        key="sources",
        title="Information sources and conflict resolution",
        reference=(
            f"{DOC_9974}: the operator must satisfy the authority on its ability"
            f' "{QUOTE_CONFLICTS}".'
        ),
        fields=[
            DocField.code(
                "rule",
                "Rule applied",
                "The official area is binding. TEPHRA's hazard cone may only widen it, and a"
                " source that does not see ash never narrows it.",
            ),
            _ai_field(
                narrative.information_sources, "information_sources", "How the sources compare"
            ),
        ],
        tables=[
            DocTable(
                key="records",
                title="Products in the picture",
                columns=["Volcano", "Source id", "Feed", "Issued", "Fetched", "State"],
                rows=records,
            ),
            DocTable(
                key="conflicts",
                title="Conflicts found by code",
                columns=["Volcano", "Kind", "Aspect", "Severity", "Summary", "Sources"],
                rows=conflicts,
                note=None if conflicts else "No conflict between products was found.",
            ),
        ],
    )


def _key_provenances(situation: Situation) -> list[Provenance]:
    """Valid SIGMETs, the newest VONA and VAA, and the split-window result."""
    newest = [
        max(records, key=lambda item: item.provenance.issued_at or item.provenance.fetched_at)
        for records in (situation.vonas, situation.vaas)
        if records
    ]
    records: list[Any] = [
        *(sigmet for sigmet in situation.sigmets if sigmet.is_valid(situation.as_of)),
        *newest,
    ]
    if situation.btd is not None:
        records.append(situation.btd)
    return [record.provenance for record in records]


def _hazard_section(
    evidence: Evidence, policy: OperatorPolicy, narrative: SraNarrative
) -> SraSection:
    rows = [
        [
            view.situation.volcano.name,
            view.cone.mode.value if view.cone is not None else "no cone",
            f"{round(view.cone.confidence * 100)}%" if view.cone is not None else None,
            band_text(view.cone.base_ft, view.cone.top_ft) if view.cone is not None else None,
            _official_band(view.situation) or "none",
            str(len(_valid_layers(view.situation))),
            view.color.value,
            f"FL{ft_to_fl(view.vona.cloud_top_ft):03d}"
            if view.vona is not None and view.vona.cloud_top_ft is not None
            else None,
        ]
        for view in evidence.volcanoes
    ]
    return SraSection(
        number=3,
        key="hazard",
        title="Hazard characterisation",
        reference=f"{DOC_9974}, Appendix E (eruption phases)",
        fields=[
            DocField.to_complete(
                "phase",
                "Eruption phase (before, start, ongoing, end)",
                note="RISK OWNER TO COMPLETE. TEPHRA does not classify the phase.",
            ),
            DocField.code(
                "grading",
                "Contamination grading",
                policy.summary_text,
                note="From the operator policy file; the official products carry no graduation.",
            ),
            _ai_field(narrative.hazard_summary, "hazard_summary", "Hazard in short"),
        ],
        tables=[
            DocTable(
                key="hazard",
                title="Hazard per volcano",
                columns=[
                    "Volcano",
                    "Mode",
                    "Confidence",
                    "TEPHRA cone band",
                    "Official band",
                    "Official layers valid",
                    "Colour code",
                    "Latest VONA ash top",
                ],
                rows=rows,
                note="A blank cell means the source gave no value.",
            )
        ],
    )


_RISK_ROWS: Final[tuple[tuple[str, str, str, str], ...]] = (
    (
        "R1",
        "Flight into volcanic ash",
        "Loss of engine thrust or engine damage; loss of reliable air data.",
        "Official areas are binding and the cone may only widen them. Each exposed flight gets a"
        " drafted avoidance action; a dispatcher approves every advisory."
        " Vertical margin: {margin} ft.",
    ),
    (
        "R2",
        "Ash the crew cannot see (night, cloud, instruments)",
        "An encounter that is noticed late, or damage that is not noticed in flight.",
        "The hazard is drawn from products, not from what the crew sees. A silent or"
        " inconclusive indicator never shrinks it.",
    ),
    (
        "R3",
        "Abrasion and contamination of windscreen, airframe, probes and air systems",
        "Degraded visibility and air data; damage found after landing.",
        "A VAR draft per flight and a hold list for inspection (section 8).",
    ),
    (
        "R4",
        "Conflicting, late or missing information from the sources",
        "A decision made on a product that is out of date or contradicted by another.",
        "Conflicts are detected by code and listed in section 2. Stale products are marked."
        " A source order is set in the operator policy.",
    ),
    (
        "R5",
        "Loss of flight watch (feed outage, desk unattended)",
        "Changes in the eruption are not seen in time.",
        "Feed health and age are shown (section 7). Flights the AI could not plan are listed for"
        " handling by hand.",
    ),
    (
        "R6",
        "The crew is not told about the area",
        "A crew flies on without knowing the hazard.",
        "Advisory text is drafted per exposed flight. Delivery to the crew is outside TEPHRA.",
    ),
)


def _worksheet_section(policy: OperatorPolicy) -> SraSection:
    margin = str(policy.exposure.vertical_margin_ft.value)
    rows: list[list[str | None]] = [
        [row_id, hazard, consequence, controls.format(margin=margin), *[None] * 6]
        for row_id, hazard, consequence, controls in _RISK_ROWS
    ]
    return SraSection(
        number=4,
        key="worksheet",
        title="Hazard and risk worksheet",
        reference=f"{DOC_9974}, Appendices C and D (worksheet layout)",
        fields=[
            DocField.code(
                "caution",
                "Rule from the guidance",
                QUOTE_NOT_MITIGATED,
                note=f"{DOC_9974}, Appendix A. Severity, probability and tolerability are the"
                " risk owner's judgement: TEPHRA leaves them blank.",
            )
        ],
        tables=[
            DocTable(
                key="worksheet",
                title="Worksheet",
                columns=[
                    "Row",
                    "Hazard",
                    "Consequence",
                    "Existing controls",
                    "Severity",
                    "Probability",
                    "Risk tolerability",
                    "Further actions",
                    "Severity after mitigation",
                    "Probability after mitigation",
                ],
                rows=rows,
                note=BLANK_FOR_RISK_OWNER,
            )
        ],
    )


def _exposure_section(
    evidence: Evidence, policy: OperatorPolicy, narrative: SraNarrative
) -> SraSection:
    margin = policy.exposure.vertical_margin_ft.value
    names = {view.situation.volcano.id: view.situation.volcano.name for view in evidence.volcanoes}
    rows: list[list[str | None]] = [
        [
            view.flight.proxy_flight,
            f"{view.flight.callsign or 'no callsign'} / {view.flight.type_icao or 'type unknown'}",
            names[view.flight.volcano_id],
            _status_text(view.flight),
            _fl_range(view.flight.aircraft_band_ft),
            band_text(*view.flight.hazard_band_ft),
            str(margin),
            view.flight.cone_id,
        ]
        for view in evidence.flights
    ]
    return SraSection(
        number=5,
        key="exposure",
        title="Exposure analysis per flight",
        reference="TEPHRA exposure engine: extrapolated ADS-B track against the cone and its"
        " level band",
        fields=[_ai_field(narrative.exposure_summary, "exposure_summary", "Exposure in short")],
        tables=[
            DocTable(
                key="exposure",
                title="Exposed flights (ADS-B proxies)",
                columns=[
                    "Flight",
                    "ADS-B callsign / type",
                    "Volcano",
                    "Status",
                    "Aircraft levels",
                    "Hazard band",
                    "Vertical margin (ft)",
                    "Cone",
                ],
                rows=rows,
                note=None if rows else "No flight is exposed in this region.",
            )
        ],
    )


def _mitigation_section(evidence: Evidence, narrative: SraNarrative) -> SraSection:
    rows = [_decision_row(view) for view in evidence.flights]
    return SraSection(
        number=6,
        key="mitigation",
        title="Mitigations and decision",
        reference=f"{DOC_9974}, Appendix B (procedures to consider)",
        fields=[
            _ai_field(narrative.mitigation_summary, "mitigation_summary", "Mitigation in short")
        ],
        tables=[
            DocTable(
                key="decisions",
                title="Drafted decisions",
                columns=[
                    "Flight",
                    "Action",
                    "Detail",
                    "MEL relief",
                    "Fuel",
                    "Advisory",
                    "Advisory status",
                ],
                rows=rows,
                note="MEL relief is for the dispatcher to complete. Advisories are DRAFTS until a"
                " dispatcher decides them.",
            )
        ],
    )


def _decision_row(view: FlightView) -> list[str | None]:
    advisory = view.advisory
    flight = view.flight.proxy_flight
    if advisory is None:
        action = (
            "AI UNAVAILABLE: handle by hand" if view.failure is not None else "no advisory drafted"
        )
        return [flight, action, None, None, None, None, None]
    return [
        flight,
        advisory.action.value,
        _action_detail(advisory) or None,
        None,
        advisory.fuel_line or None,
        advisory.id,
        advisory.status.value,
    ]


def _action_detail(advisory: Advisory) -> str:
    match advisory.action:
        case ActionKind.CHANGE_LEVEL:
            return f"FL{advisory.change_level_fl_min:03d}-FL{advisory.change_level_fl_max:03d}"
        case ActionKind.HOLD:
            return f"FL{advisory.hold_fl:03d}"
        case ActionKind.DIVERT:
            return advisory.alternate_icao or ""
        case ActionKind.REROUTE:
            return advisory.reroute.route_string if advisory.reroute is not None else ""
        case _:
            return ""


def _watch_section(evidence: Evidence) -> SraSection:
    rows = [
        [
            feed.feed.value,
            feed.status.value,
            _time_text(feed.last_success_at) or "never",
            str(_age_min(feed.age_s)) if feed.age_s is not None else None,
            str(feed.cadence_s),
        ]
        for feed in evidence.state.feeds
    ]
    return SraSection(
        number=7,
        key="watch",
        title="Flight watch",
        reference=f"{DOC_9974}, Appendix B (enhanced flight watch)",
        fields=[
            DocField.to_complete(
                "capability",
                "Capability of the operations unit to monitor",
                note="RISK OWNER TO COMPLETE. State staffing and hours.",
            )
        ],
        tables=[
            DocTable(
                key="feeds",
                title="Feeds monitored by TEPHRA",
                columns=["Feed", "Status", "Last success", "Age (min)", "Cadence (s)"],
                rows=rows,
            )
        ],
    )


def _reporting_section(evidence: Evidence) -> SraSection:
    inside = [view for view in evidence.flights if view.flight.inside_now]
    names = {view.situation.volcano.id: view.situation.volcano.name for view in evidence.volcanoes}
    return SraSection(
        number=8,
        key="reporting",
        title="Reporting and post-event",
        reference=f"{DOC_9974}, Appendix B (incident reporting)",
        fields=[
            DocField.code(
                "route",
                "Encounter reporting route",
                "In flight: a special air-report to the ATS unit. After landing: the volcanic ash"
                " report (VAR) to the meteorological authority or the VAAC, a maintenance log"
                " entry, an air safety report and the State occurrence report (verify the route).",
            ),
            DocField.code(
                "non_encounter",
                "Non-encounters",
                "Ash that is NOT met in an area where it was forecast is also reported.",
            ),
            DocField.code(
                "var_drafts",
                "VAR drafts for this region",
                f"{len(evidence.var_drafts)} drafted, "
                f"{sum(draft.status.value == 'SIGNED' for draft in evidence.var_drafts)} signed",
                source_ids=[draft.id for draft in evidence.var_drafts],
            ),
        ],
        tables=[
            DocTable(
                key="inspection",
                title="Suspected exposed, hold for inspection (proxies inside the hazard now)",
                columns=["Flight", "Volcano"],
                rows=[[view.flight.proxy_flight, names[view.flight.volcano_id]] for view in inside],
                note=None if inside else "No flight is inside a hazard area now.",
            )
        ],
    )


def _assumptions_section() -> SraSection:
    return SraSection(
        number=9,
        key="assumptions",
        title="Assumptions, limits and review",
        fields=[
            DocField.code(
                "heights",
                "Heights",
                "Flight levels and heights above sea level are compared on one scale (FL x 100"
                " = ft); the pressure-altitude and QNH difference is ignored.",
            ),
            DocField.code(
                "traffic",
                "Traffic",
                "Flights are ADS-B proxies of a fictional airline, and their tracks are"
                " extrapolated in a straight line. Routes and schedules are not known.",
            ),
            DocField.code(
                "hazard",
                "Hazard",
                "The hazard is the official area, which TEPHRA's model may widen and never shrink."
                " With no valid official product it is a hypothesis and only MONITOR or HOLD"
                " may be advised.",
            ),
            DocField.code(
                "tch",
                "Type certificate holder data",
                "Not supplied to TEPHRA. The operator adds the holder's data on susceptibility"
                " and precautions.",
            ),
            DocField.code(
                "review",
                "Review trigger",
                "Review when the eruption or a source changes in a material way.",
            ),
        ],
    )


def _signoff_section(evidence: Evidence) -> SraSection:
    rows: list[list[str | None]] = [
        [
            advisory.id,
            advisory.proxy_flight,
            advisory.action.value,
            advisory.status.value,
            advisory.decided_by,
            _time_text(advisory.decided_at),
        ]
        for advisory in evidence.advisories[:MAX_LOG_ROWS]
    ]
    return SraSection(
        number=10,
        key="signoff",
        title="Sign-off and decision log",
        fields=[
            DocField.code(
                "signatures",
                "Signatures",
                "Signature lines are on the document. A signed draft is still not an approved"
                " SRA until the regulator accepts it.",
            )
        ],
        tables=[
            DocTable(
                key="decisions",
                title="Advisory decisions in this region",
                columns=["Advisory", "Flight", "Action", "Status", "Decided by", "Decided"],
                rows=rows,
                note=None if rows else "No advisory has been drafted in this region.",
            )
        ],
    )


def _indonesia_section(evidence: Evidence) -> SraSection:
    decided = sum(advisory.status in _DECIDED for advisory in evidence.advisories)
    inside = sum(view.flight.inside_now for view in evidence.flights)
    signed = sum(draft.status.value == "SIGNED" for draft in evidence.var_drafts)
    rows: list[list[str | None]] = [
        [
            "A safety risk assessment is done before flights are planned in areas the ash"
            " may affect",
            "This is a draft and not an approved SRA; the acceptance reference is blank.",
            None,
        ],
        [
            "Crews know the restricted areas",
            f"{len(evidence.advisories)} advisories drafted in this region,"
            f" {decided} approved or edited.",
            None,
        ],
        [
            "An aircraft suspected or proven exposed stays out of service until inspected",
            f"{inside} proxy flights inside a hazard area now (section 8).",
            None,
        ],
        [
            "Every ash encounter is reported and documented through the safety reporting system",
            f"{len(evidence.var_drafts)} VAR drafts, {signed} signed.",
            None,
        ],
        [
            "Delay and disruption handling for passengers",
            "Not covered by this document.",
            None,
        ],
    ]
    return SraSection(
        number=11,
        key="indonesia",
        title="Indonesia overlay: SE-DJPU 15/2026 checklist",
        reference=f"SE-DJPU 15/2026, {SE_DJPU_NOTE}.",
        fields=[
            DocField.code(
                "caveat",
                "Source of this checklist",
                "This checklist rests on press reports of the circular, not on its text."
                " Check it against the PDF before relying on it.",
            )
        ],
        tables=[
            DocTable(
                key="checklist",
                title="Checklist",
                columns=["Requirement as reported", "TEPHRA evidence", "Done (risk owner)"],
                rows=rows,
            )
        ],
    )


# --- helpers ----------------------------------------------------------------------------


def _ai_field(box: Any, key: str, label: str) -> DocField:
    return DocField.ai(key, label, box.text.strip(), source_ids=list(box.source_ids))


def _valid_layers(situation: Situation) -> list[Any]:
    return [layer for layer in situation.official_layers if layer.is_valid(situation.as_of)]


def _official_band(situation: Situation) -> str | None:
    layers = _valid_layers(situation)
    if not layers:
        return None
    return band_text(min(layer.base_ft for layer in layers), max(layer.top_ft for layer in layers))


def _status_text(flight: ExposedFlight) -> str:
    if flight.inside_now:
        return "inside now"
    return f"entry in {flight.minutes_to_entry} min"


def _fl_range(band_ft: Sequence[int]) -> str:
    low, high = band_ft
    return f"FL{ft_to_fl(low):03d}-FL{ft_to_fl(high):03d}"


def _age_min(age_s: int | None) -> int | None:
    return None if age_s is None else round(age_s / 60)


def _time_text(value: Any) -> str | None:
    return None if value is None else timeutil.ddhhmmz(value)
