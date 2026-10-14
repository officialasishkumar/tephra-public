"""Models for crew and passenger messages, the shift handover brief and their requests."""

from enum import StrEnum
from typing import Literal

from pydantic import Field, computed_field, model_validator

from tephra.models import LlmBackendName, TephraModel, UtcDatetime

__all__ = [
    "ContingencyLine",
    "CrewPaxMessage",
    "DecisionMade",
    "DraftMessagesRequest",
    "EditMessageRequest",
    "EquipmentData",
    "HandoverBrief",
    "HandoverRequest",
    "HandoverSeverity",
    "Language",
    "MessageConflict",
    "MessageKind",
    "MessageList",
    "MessageStatus",
    "MessageText",
    "OfficialArea",
    "OpenAction",
    "ReceiverAck",
    "RecoveryChange",
    "RecoveryClosure",
    "RecoveryInput",
    "SourcedText",
    "TrafficRow",
    "WeatherAsh",
]

Language = Literal["id", "ja", "en"]
"""Bahasa Indonesia, Japanese, English."""


class MessageKind(StrEnum):
    CREW_BRIEFING = "CREW_BRIEFING"
    PASSENGER_NOTICE = "PASSENGER_NOTICE"
    CREW_NOTICE = "CREW_NOTICE"


class MessageStatus(StrEnum):
    """DRAFT -> APPROVED | EDITED | REJECTED, by a dispatcher only."""

    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    EDITED = "EDITED"
    REJECTED = "REJECTED"


class MessageText(TephraModel):
    """One language of one message."""

    language: Language
    template: str = Field(description="Model-written; facts are {PLACEHOLDERS}")
    body: str = Field(description="The template with every placeholder filled by code")


class CrewPaxMessage(TephraModel):
    """A crew briefing, crew notice or passenger notice. Only a dispatcher moves it."""

    id: str = Field(description="'msg_' + 12 hex chars")
    version: int = Field(ge=1, description="Incremented on every transition")
    status: MessageStatus
    created_at: UtcDatetime
    updated_at: UtcDatetime
    replay: bool
    kind: MessageKind
    source_kind: Literal["advisory", "recovery"]
    source_id: str = Field(description="Advisory id or recovery plan id")
    source_version: int | None = Field(
        default=None, description="Advisory version it was made from"
    )
    flight_no: str | None = None
    tail: str | None = None
    route: str | None = None
    texts: list[MessageText] = Field(min_length=1)
    edited_bodies: dict[Language, str] = Field(default_factory=dict)
    reject_reason: str | None = None
    decided_by: str | None = None
    decided_at: UtcDatetime | None = None
    llm_backend: LlmBackendName
    model_id: str
    prompt_hashes: dict[str, str] = Field(
        description="Template call hash per language set, key 'templates'"
    )
    input_hashes: list[str] = Field(default_factory=list)
    dedupe_key: str

    @computed_field  # type: ignore[prop-decorator]
    @property
    def final_bodies(self) -> dict[Language, str]:
        return {
            text.language: self.edited_bodies.get(text.language, text.body) for text in self.texts
        }


class MessageList(TephraModel):
    messages: list[CrewPaxMessage]


class MessageConflict(TephraModel):
    """409 body when a dispatcher decided on a version that is no longer current."""

    error: Literal["version_conflict"] = "version_conflict"
    detail: str
    current: CrewPaxMessage


class DraftMessagesRequest(TephraModel):
    advisory_id: str | None = None
    recovery_id: str | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> "DraftMessagesRequest":
        if (self.advisory_id is None) == (self.recovery_id is None):
            raise ValueError("give exactly one of advisory_id and recovery_id")
        return self


class EditMessageRequest(TephraModel):
    version: int = Field(ge=1, description="The version the dispatcher saw")
    bodies: dict[Language, str] = Field(min_length=1, description="Replacement body per language")


# --- handover -----------------------------------------------------------------------------

HandoverSeverity = Literal["calm", "watch", "active", "critical"]


class SourcedText(TephraModel):
    text: str
    source_ids: list[str] = Field(default_factory=list)


class ContingencyLine(TephraModel):
    """An 'if ... then ...' written by the model, with the evidence it rests on."""

    condition: str
    then: str
    source_ids: list[str] = Field(default_factory=list)


class OfficialArea(TephraModel):
    source_id: str
    label: str
    base_ft: int
    top_ft: int
    valid_from: UtcDatetime
    valid_to: UtcDatetime


class WeatherAsh(TephraModel):
    official_areas: list[OfficialArea] = Field(default_factory=list)
    latest_vaa_utc: UtcDatetime | None = None
    disagreements: list[SourcedText] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class EquipmentData(TephraModel):
    feeds_stale: list[str] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)


class TrafficRow(TephraModel):
    flight: str
    plan: str
    status: str
    reason: str
    source_ids: list[str] = Field(default_factory=list)


class OpenAction(TephraModel):
    owner: str
    action: str
    due_utc: UtcDatetime | None = None
    source_ids: list[str] = Field(default_factory=list)


class DecisionMade(TephraModel):
    by: str
    utc: UtcDatetime
    what: str
    source_ids: list[str] = Field(default_factory=list)


class ReceiverAck(TephraModel):
    """I-PASS 'synthesis by receiver': filled when the incoming dispatcher reads back."""

    read_back_by: str | None = None
    utc: UtcDatetime | None = None
    open_drafts: list[str] = Field(
        default_factory=list,
        description="Ids of the drafts still open at the read-back: handed over open, not decided",
    )


class HandoverBrief(TephraModel):
    """WEST (weather, equipment, situation, traffic) plus I-PASS (severity, actions,
    contingencies, receiver read-back). Code gathers every fact; the model writes only
    ``situation`` and ``contingencies``, each with source ids."""

    doc_type: Literal["handover"] = "handover"
    id: str = Field(description="'ho_' + 12 hex chars")
    created_at: UtcDatetime
    replay: bool
    shift_from: UtcDatetime
    shift_to: UtcDatetime
    outgoing: str
    incoming: str
    severity: HandoverSeverity = Field(description="Set by code from the gathered facts")
    weather_ash: WeatherAsh
    equipment_data: EquipmentData
    situation: SourcedText = Field(description="Written by the model")
    traffic: list[TrafficRow] = Field(default_factory=list)
    actions_open: list[OpenAction] = Field(default_factory=list)
    handed_over_open: list[str] = Field(
        default_factory=list,
        description="Ids of the advisory, message and recovery drafts open when the brief was made",
    )
    contingencies: list[ContingencyLine] = Field(
        default_factory=list, description="Written by the model"
    )
    decisions_made: list[DecisionMade] = Field(default_factory=list)
    receiver_ack: ReceiverAck = Field(default_factory=ReceiverAck)
    evidence_ids: list[str] = Field(description="Every id the model was allowed to cite")
    llm_backend: LlmBackendName
    model_id: str
    prompt_hash: str
    narrative_at: UtcDatetime | None = Field(
        default=None,
        description="When the model wrote situation and contingencies; the same model's text "
        "for identical facts keeps its time. None: created_at",
    )


class HandoverRequest(TephraModel):
    since: UtcDatetime
    incoming: str = Field(min_length=2, max_length=64)
    outgoing: str | None = Field(
        default=None, min_length=2, max_length=64, description="Defaults to the signed-in name"
    )


# --- what a recovery plan must give the messages ------------------------------------------


class RecoveryChange(TephraModel):
    """One flight the recovery plan moves, as the messages need it."""

    flight_no: str
    flight_key: str = Field(description="flight_no and service date, e.g. RFA239/06SEP")
    origin_icao: str
    dest_icao: str
    std: UtcDatetime = Field(description="Scheduled departure before the plan")
    kind: Literal["CANCEL", "DELAY", "SWAP"]
    delay_min: int = Field(default=0, ge=0, description="DELAY only")
    tail: str = Field(description="The aircraft the flight was planned on")
    new_tail: str | None = Field(default=None, description="SWAP only")


class RecoveryClosure(TephraModel):
    icao: str
    start: UtcDatetime
    end: UtcDatetime
    source_ids: list[str] = Field(default_factory=list)
    open_ended: bool = Field(
        default=False, description="No end is published: ``end`` is only the planning horizon"
    )


class RecoveryInput(TephraModel):
    """The fields of a recovery plan (``tephra.recovery.models.RecoveryPlan``) that crew and
    passenger messages are made from."""

    id: str
    approved: bool
    replay: bool
    changes: list[RecoveryChange]
    closures: list[RecoveryClosure]
