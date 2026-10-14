"""Shapes of the SRA, VAR and crew report message drafts, stored in the ``docs`` collection.

A document is a list of fields and tables. Each field says who wrote it: ``code`` (filled
from TEPHRA's evidence or fixed wording), ``ai`` (a Gemini narrative box that passed the
checks in ``regdocs.sra``) or ``human`` (left blank for a person; ``value`` stays None until
then). A blank is never filled with a guess.
"""

from enum import StrEnum
from typing import Annotated, Final, Literal, Self

from pydantic import Field, TypeAdapter, computed_field

from tephra.models import LlmBackendName, TephraModel, UtcDatetime

__all__ = [
    "SRA_HEADER",
    "TO_COMPLETE",
    "VAR_HEADER",
    "CrewMessageDraft",
    "DocField",
    "DocKind",
    "DocModel",
    "DocStatus",
    "DocSummary",
    "DocTable",
    "FieldOrigin",
    "NarrativeBox",
    "RegDoc",
    "RegDocAdapter",
    "SignRole",
    "SignatureLine",
    "SraDraft",
    "SraNarrative",
    "SraSection",
    "VarDraft",
    "VarItem",
]

SRA_HEADER: Final = "DRAFT - NOT AN APPROVED SRA - FOR HUMAN SIGN-OFF"
VAR_HEADER: Final = "DRAFT - FOR HUMAN SIGN-OFF - NOT TRANSMITTED"
TO_COMPLETE: Final = "PILOT/DISPATCHER TO COMPLETE"

FieldOrigin = Literal["code", "ai", "human"]


class DocKind(StrEnum):
    SRA = "SRA"
    VAR = "VAR"
    CREW_MESSAGE = "CREW_MESSAGE"
    """A message to the weather office and the VAAC started from a crew report of ash"""
    HANDOVER = "HANDOVER"
    """Only in :class:`DocSummary`: a shift handover brief (``tephra.comms``), not paperwork."""


class DocStatus(StrEnum):
    """DRAFT until every signature line is filled. SIGNED is not an approval: the regulator
    accepts an SRA, and a VAR goes out only by the crew's and the operator's own channels.
    A handover brief is DRAFT until the incoming dispatcher reads it back (ACKNOWLEDGED). A
    crew report message is WITHDRAWN when its crew report is withdrawn: never to be sent."""

    DRAFT = "DRAFT"
    SIGNED = "SIGNED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    WITHDRAWN = "WITHDRAWN"


class SignRole(StrEnum):
    DISPATCHER = "DISPATCHER"
    SAFETY_MANAGER = "SAFETY_MANAGER"
    ACCOUNTABLE_EXECUTIVE = "ACCOUNTABLE_EXECUTIVE"
    PILOT_IN_COMMAND = "PILOT_IN_COMMAND"


class DocField(TephraModel):
    key: str
    label: str
    value: str | None = None
    origin: FieldOrigin
    note: str | None = None
    source_ids: list[str] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def blank(self) -> bool:
        return not (self.value or "").strip()

    @classmethod
    def code(
        cls,
        key: str,
        label: str,
        value: str,
        *,
        note: str | None = None,
        source_ids: list[str] | None = None,
    ) -> Self:
        return cls(
            key=key,
            label=label,
            value=value,
            origin="code",
            note=note,
            source_ids=source_ids or [],
        )

    @classmethod
    def ai(cls, key: str, label: str, value: str, *, source_ids: list[str]) -> Self:
        return cls(key=key, label=label, value=value, origin="ai", source_ids=source_ids)

    @classmethod
    def to_complete(cls, key: str, label: str, *, note: str = TO_COMPLETE) -> Self:
        return cls(key=key, label=label, value=None, origin="human", note=note)


class DocTable(TephraModel):
    """Rows are written by code; a None cell is a blank for a person to complete."""

    key: str
    title: str
    columns: list[str]
    rows: list[list[str | None]]
    note: str | None = None


class SignatureLine(TephraModel):
    role: SignRole
    label: str
    signed_name: str | None = None
    signed_at: UtcDatetime | None = None
    recorded_by: str | None = Field(default=None, description="'desk:<name>' who recorded it")


class _DocBase(TephraModel):
    id: str = Field(description="stable_id('DOC', kind, subject, created_at, input_hash)")
    version: int = Field(default=1, ge=1, description="Incremented on every signature")
    status: DocStatus = DocStatus.DRAFT
    header: str
    labels: list[str] = Field(description="Fictional airline, REPLAY, NO MODEL and the like")
    created_at: UtcDatetime
    updated_at: UtcDatetime
    replay: bool
    signatures: list[SignatureLine]
    input_hash: str = Field(description="sha256 of the facts the draft was made from")

    def signed_roles(self) -> list[SignRole]:
        return [line.role for line in self.signatures if line.signed_at is not None]


class SraSection(TephraModel):
    number: int
    key: str
    title: str
    reference: str | None = Field(default=None, description="Where the section comes from")
    fields: list[DocField] = Field(default_factory=list)
    tables: list[DocTable] = Field(default_factory=list)


class SraDraft(_DocBase):
    kind: Literal["SRA"] = "SRA"
    region_key: str
    region_name: str
    volcano_ids: list[str]
    policy_id: str
    policy_version: str
    policy_hash: str
    llm_backend: LlmBackendName
    model_id: str
    prompt_hash: str
    narrative_at: UtcDatetime | None = Field(
        default=None,
        description="When the model wrote the narrative boxes; the same model's boxes for "
        "identical facts keep their time. None: created_at",
    )
    sections: list[SraSection]
    source_ids: list[str] = Field(description="Every source id the evidence sections cite")


class VarItem(DocField):
    number: int = Field(ge=1, le=16)
    group: Literal["in_flight", "post_flight"]
    hint: str | None = Field(default=None, description="The choices the form lists")


class VarDraft(_DocBase):
    """The ICAO Model VAR layout with items 1 to 5 from ADS-B and the hazard. The aircraft is
    an ADS-B proxy flight of the fictional airline, never a real operator's flight."""

    kind: Literal["VAR"] = "VAR"
    flight_id: str
    proxy_flight: str
    volcano_id: str
    volcano_name: str
    header_fields: list[DocField]
    items: list[VarItem]
    airep_special: DocField
    ars_line: DocField
    non_encounter: DocField
    context: list[DocField]
    followups: list[str]


class CrewMessageDraft(_DocBase):
    """A message to the meteorological watch office and the VAAC about a crew report of ash
    (EUR Doc 019 3.2.9 e): forward differences between published information and pilot
    reports). Code writes every line from the report and the official products; no model is
    involved. A dispatcher signs it and sends it through the operator's own channel."""

    kind: Literal["CREW_MESSAGE"] = "CREW_MESSAGE"
    crew_report_id: str
    flight: str = Field(description="How the report names the flight (proxy or typed callsign)")
    title: str
    to: list[DocField]
    subject: DocField
    body: str = Field(description="Code-written message text, ready to read out or paste")
    facts: list[DocField] = Field(description="What each line of the body rests on")
    followups: list[str]
    withdrawn_note: str | None = Field(
        default=None, description="Set when the crew report was withdrawn (status WITHDRAWN)"
    )


DocModel = SraDraft | VarDraft | CrewMessageDraft
RegDoc = Annotated[DocModel, Field(discriminator="kind")]
RegDocAdapter: Final[TypeAdapter[DocModel]] = TypeAdapter(RegDoc)


class DocSummary(TephraModel):
    """One line of ``GET /api/docs`` and the payload of every ``doc`` SSE event (SRA, VAR and
    handover briefs alike): enough to list and open the document, never the document itself."""

    id: str
    kind: DocKind
    status: DocStatus
    title: str
    created_at: UtcDatetime
    updated_at: UtcDatetime
    replay: bool
    signed_roles: list[SignRole]
    missing_roles: list[SignRole]
    llm_backend: LlmBackendName | None = None
    region: str | None = Field(default=None, description="SRA: the region key")
    flight: str | None = Field(
        default=None, description="VAR: the proxy flight; CREW_MESSAGE: the reporting flight"
    )

    @classmethod
    def of(cls, doc: DocModel) -> Self:
        if isinstance(doc, SraDraft):
            title, backend = f"SRA draft: {doc.region_name}", doc.llm_backend
            region, flight = doc.region_key, None
        elif isinstance(doc, CrewMessageDraft):
            title, backend = doc.title, None
            region, flight = None, doc.flight
        else:
            title, backend = f"VAR draft: {doc.proxy_flight} / {doc.volcano_name}", None
            region, flight = None, doc.proxy_flight
        return cls(
            id=doc.id,
            kind=DocKind(doc.kind),
            status=doc.status,
            title=title,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            replay=doc.replay,
            signed_roles=doc.signed_roles(),
            missing_roles=[]
            if doc.status is DocStatus.WITHDRAWN
            else [line.role for line in doc.signatures if line.signed_at is None],
            llm_backend=backend,
            region=region,
            flight=flight,
        )


class NarrativeBox(TephraModel):
    """One AI-written box: text plus the ids it rests on (the text itself carries none)."""

    text: str = Field(description="Plain English, no times, ids or hashes")
    source_ids: list[str] = Field(description="Ids from the input facts that support the text")


class SraNarrative(TephraModel):
    """The model's whole output for an SRA: four boxes."""

    information_sources: NarrativeBox
    hazard_summary: NarrativeBox
    exposure_summary: NarrativeBox
    mitigation_summary: NarrativeBox
