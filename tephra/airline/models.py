"""The onboarding answers, the stored airline documents, the views the API returns and the
request bodies (``tephra.api.routes_airline``).

No airline document holds a password or a recovery code; a hosted airline's model key is held
only sealed, in its tenant record (D5). No field holds a PIN, secret, token, Ollama address or
file contents: the schedule files stay in the airline's browser.
Validator messages never repeat the input (the app's 422 body copies them as written).
"""

import re
import unicodedata
from typing import Annotated, Any, Final, Literal, Self

from pydantic import (
    BeforeValidator,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from tephra.models import PushProblem, TephraModel, UtcDatetime


def _is_none(value: object) -> bool:
    return value is None


__all__ = [
    "DESK_STATUSES",
    "EMAIL",
    "ONBOARD_FORMAT",
    "STAFF_STATUS_LABEL",
    "STATUS_LABEL",
    "AccountCreate",
    "AccountCreated",
    "AirlineAnswers",
    "AirlineDeskRow",
    "AirlineDeskView",
    "AirlineIdentity",
    "AirlineLogin",
    "AirlineRecord",
    "AirlineSessionView",
    "AirlineStatus",
    "AirlineView",
    "AnswersUpdate",
    "AshPolicy",
    "AssistantChoice",
    "AssistantUpdate",
    "DeleteAccount",
    "DeskStatus",
    "Dispatcher",
    "DraftUpdate",
    "DraftValues",
    "DryRunRecord",
    "DryRunResult",
    "DryRunSection",
    "Feeds",
    "Fleet",
    "FleetAircraft",
    "HistoryAction",
    "HistoryEntry",
    "Network",
    "NetworkAirport",
    "OnboardDraft",
    "People",
    "PolicyChange",
    "Recover",
    "RecoveryCode",
    "ScheduleSummary",
    "SignIn",
    "StaffList",
    "Stamp",
    "StatusStep",
    "Submit",
]

ONBOARD_FORMAT: Final = "tephra.onboard/2"
EMAIL: Final = r"^[^@\s]{1,64}@[^@\s]{1,189}\.[^@\s]{2,63}$"
ICAO_AIRPORT: Final = r"^[A-Z]{4}$"
_AIRPORT = re.compile(ICAO_AIRPORT)
_PREFIX = re.compile(r"^[A-Z]{3}$")
_AI_STUDIO_MODEL = re.compile(r"^(gemini|gemma)-[a-z0-9.-]{1,60}$")
_OLLAMA_TAG = re.compile(r"^[a-z0-9._-]{1,60}:[a-z0-9._-]{1,40}$")
_BIDI_CONTROLS: Final = frozenset("‪‫‬‭‮⁦⁧⁨⁩")

AirlineStatus = Literal["draft", "pending", "verified", "declined"]
DeskStatus = Literal["pending", "verified", "declined"]
"""What TEPHRA staff see: a draft is the airline's own until it submits."""
DESK_STATUSES: Final[tuple[DeskStatus, ...]] = ("pending", "verified", "declined")
PageKey = Literal[
    "airline", "policy", "fleet", "network", "schedule", "feeds", "people", "assistant", "review"
]
STATUS_LABEL: Final[dict[str, str]] = {
    "draft": "Not submitted",
    "pending": "Pending verification",
    "verified": "Verified",
    "declined": "Declined",
}
# The staff console's words (hosting on or off): "Pending" beside its To verify filter.
STAFF_STATUS_LABEL: Final[dict[str, str]] = {**STATUS_LABEL, "pending": "Pending"}


def _has_control(text: str) -> bool:
    return any(unicodedata.category(ch) == "Cc" or ch in _BIDI_CONTROLS for ch in text)


def _upper(value: object) -> object:
    return value.strip().upper() if isinstance(value, str) else value


def _optional(value: object) -> object:
    """An optional text answer left blank is no answer."""
    if isinstance(value, str):
        return value.strip() or None
    return value


def _codes(value: object) -> object:
    if not isinstance(value, list):
        return value
    return [_upper(code) for code in value]


def _check_codes(codes: list[str], pattern: re.Pattern[str], what: str) -> list[str]:
    if any(pattern.fullmatch(code) is None for code in codes):
        raise ValueError(f"each {what} must match {pattern.pattern}")
    if len(set(codes)) != len(codes):
        raise ValueError(f"each {what} may be given once")
    return codes


class _Form(TephraModel):
    """Unknown keys are refused, strings are stripped, and no free text carries a control
    character (one shared check, so a stored answer never breaks a page or a log line)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("*", mode="after")
    @classmethod
    def _no_control_characters(cls, value: Any) -> Any:
        texts = value if isinstance(value, list) else [value]
        if any(isinstance(text, str) and _has_control(text) for text in texts):
            raise ValueError("must not contain control characters")
        return value


# --- the answers ------------------------------------------------------------------------


class AirlineIdentity(_Form):
    name: str = Field(min_length=2, max_length=120)
    icao: str = Field(pattern=r"^[A-Z]{3}$")
    iata: str | None = Field(default=None, pattern=r"^[A-Z0-9]{2}$")
    callsign_prefix: str = Field(pattern=r"^[A-Z]{3}$")
    state_of_operator: str = Field(
        min_length=2, max_length=60, description="The State that issued the AOC"
    )
    aoc_number: str | None = Field(default=None, max_length=40, description="As on the AOC")
    main_base: str = Field(pattern=ICAO_AIRPORT)
    ops_email: str = Field(max_length=254, pattern=EMAIL)
    contact_name: str | None = Field(default=None, max_length=80)

    @field_validator("icao", "iata", "callsign_prefix", "main_base", mode="before")
    @classmethod
    def _tidy_codes(cls, value: object, info: ValidationInfo) -> object:
        value = _upper(value)
        return _optional(value) if info.field_name == "iata" else value

    @field_validator("aoc_number", "contact_name", mode="before")
    @classmethod
    def _tidy_optional(cls, value: object) -> object:
        return _optional(value)

    @field_validator("ops_email", mode="before")
    @classmethod
    def _tidy_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("name")
    @classmethod
    def _no_variable(cls, value: str) -> str:
        """The name may end up as ``TEPHRA_AIRLINE_NAME`` in a ``.env`` file, whose loader
        (python-dotenv) expands ``${VAR}`` in any quoting: a name holding one would print another
        setting, such as the session secret, in every advisory header."""
        if "${" in value:
            raise ValueError("must not contain ${")
        return value


class PolicyChange(_Form):
    name: str = Field(max_length=60, description="A key of the policy's named_values()")
    value: int = Field(ge=0, le=100_000)
    reason: str = Field(min_length=3, max_length=300)


class AshPolicy(_Form):
    preset: Literal["A"]
    changes: list[PolicyChange] = Field(default_factory=list, max_length=32)
    risk_owner: str = Field(min_length=2, max_length=80)
    sra_ref: str | None = Field(default=None, max_length=120)

    @field_validator("sra_ref", mode="before")
    @classmethod
    def _tidy_optional(cls, value: object) -> object:
        return _optional(value)

    @model_validator(mode="after")
    def _changes_named_once_and_referenced(self) -> Self:
        names = [change.name for change in self.changes]
        if len(set(names)) != len(names):
            raise ValueError("each policy value may be changed once")
        if self.changes and self.sra_ref is None:
            raise ValueError("a changed value needs your SRA reference (sra_ref)")
        return self


class FleetAircraft(_Form):
    registration: str = Field(pattern=r"^[A-Z0-9-]{2,10}$")
    type_icao: str = Field(pattern=r"^[A-Z0-9]{2,4}$")
    seats: int = Field(ge=0, le=1000, description="0 for a freighter")
    home_base: str | None = Field(default=None, pattern=ICAO_AIRPORT)
    hex: str | None = Field(default=None, pattern=r"^[0-9a-f]{6}$")

    @field_validator("registration", "type_icao", "home_base", mode="before")
    @classmethod
    def _tidy_codes(cls, value: object, info: ValidationInfo) -> object:
        value = _upper(value)
        return _optional(value) if info.field_name == "home_base" else value

    @field_validator("hex", mode="before")
    @classmethod
    def _tidy_hex(cls, value: object) -> object:
        if isinstance(value, str):
            return "".join(value.split()).lower() or None
        return value


class Fleet(_Form):
    aircraft: list[FleetAircraft] = Field(min_length=1, max_length=1000)
    extra_prefixes: list[str] = Field(default_factory=list, max_length=4)

    @field_validator("extra_prefixes", mode="before")
    @classmethod
    def _tidy_prefixes(cls, value: object) -> object:
        return _codes(value)

    @field_validator("extra_prefixes", mode="after")
    @classmethod
    def _check_prefixes(cls, value: list[str]) -> list[str]:
        return _check_codes(value, _PREFIX, "callsign prefix")

    @model_validator(mode="after")
    def _each_aircraft_once(self) -> Self:
        for key in ("registration", "hex"):
            seen: dict[str, int] = {}
            for row, aircraft in enumerate(self.aircraft, start=1):
                value = getattr(aircraft, key)
                if value is None:
                    continue
                if value in seen:
                    raise ValueError(f"aircraft {row} has the same {key} as aircraft {seen[value]}")
                seen[value] = row
        return self


class NetworkAirport(_Form):
    icao: str = Field(pattern=ICAO_AIRPORT)
    alternates: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("icao", mode="before")
    @classmethod
    def _tidy_icao(cls, value: object) -> object:
        return _upper(value)

    @field_validator("alternates", mode="before")
    @classmethod
    def _tidy_alternates(cls, value: object) -> object:
        return _codes(value)

    @model_validator(mode="after")
    def _alternates_elsewhere(self) -> Self:
        _check_codes(self.alternates, _AIRPORT, "alternate")
        if self.icao in self.alternates:
            raise ValueError("an airport is not its own alternate")
        return self


class Network(_Form):
    airports: list[NetworkAirport] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def _each_airport_once(self) -> Self:
        codes = [airport.icao for airport in self.airports]
        if len(set(codes)) != len(codes):
            raise ValueError("each airport may be listed once")
        return self


class ScheduleSummary(_Form):
    """Counts only: the schedule files stay in the airline's browser."""

    provided: bool = False
    flights: int = Field(default=0, ge=0, le=20_000)
    tails: int = Field(default=0, ge=0, le=5_000)
    crews: int = Field(default=0, ge=0, le=5_000)
    crew_bases: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("crew_bases", mode="before")
    @classmethod
    def _tidy_bases(cls, value: object) -> object:
        return _codes(value)

    @field_validator("crew_bases", mode="after")
    @classmethod
    def _check_bases(cls, value: list[str]) -> list[str]:
        return _check_codes(value, _AIRPORT, "crew base")


class Feeds(_Form):
    positions: bool = False
    flight_plans: bool = False
    pilot_reports: bool = False
    source_system: str | None = Field(default=None, max_length=80)

    @field_validator("source_system", mode="before")
    @classmethod
    def _tidy_optional(cls, value: object) -> object:
        return _optional(value)


class Dispatcher(_Form):
    name: str = Field(
        min_length=2, max_length=32, description="A name or initials, as the Desk sign-in takes"
    )
    role: Literal["approves", "views"]


class People(_Form):
    dispatchers: list[Dispatcher] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def _someone_approves(self) -> Self:
        if not any(person.role == "approves" for person in self.dispatchers):
            raise ValueError("at least one person must approve advisories")
        return self


AssistantProvider = Literal["gemini", "ollama", "none"]


class AssistantChoice(_Form):
    """Where the airline's own TEPHRA runs its model: names only, never a key or an address.
    One AI Studio key serves both Gemini and Gemma names."""

    provider: AssistantProvider
    model: str | None = Field(default=None, max_length=101)
    model_lite: str | None = Field(default=None, max_length=101)

    @field_validator("model", "model_lite", mode="before")
    @classmethod
    def _tidy_optional(cls, value: object) -> object:
        return _optional(value)

    @model_validator(mode="after")
    def _names_fit_the_provider(self) -> Self:
        names = (self.model, self.model_lite)
        if self.provider == "none":
            if any(name is not None for name in names):
                raise ValueError("no model: leave both model names empty")
            return self
        pattern, words = (
            (_AI_STUDIO_MODEL, "a Gemini or Gemma model name, e.g. gemini-3.8-flash")
            if self.provider == "gemini"
            else (_OLLAMA_TAG, "an Ollama tag, name:tag, e.g. gemma4:e4b")
        )
        if any(name is None or pattern.fullmatch(name) is None for name in names):
            raise ValueError(f"model and model_lite must each be {words}")
        return self


class AirlineAnswers(_Form):
    format: Literal["tephra.onboard/2"]
    airline: AirlineIdentity
    policy: AshPolicy
    fleet: Fleet
    network: Network
    schedule: ScheduleSummary
    feeds: Feeds
    people: People
    assistant: AssistantChoice

    @model_validator(mode="after")
    def _extra_prefixes_are_extra(self) -> Self:
        if self.airline.callsign_prefix in self.fleet.extra_prefixes:
            raise ValueError("an extra callsign prefix repeats the airline's callsign prefix")
        return self


# --- the draft: the pages as typed, before the airline submits -------------------------------


def _clean_text(value: object) -> object:
    """A draft keeps what was typed, each control character as a space (the page refuses one
    as typed, and submit refuses it, so a save never fails over it). Numbers typed into a text box
    arrive as numbers from a file reader and are kept as text."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        value = str(value)
    if isinstance(value, str):
        return "".join(" " if _has_control(ch) else ch for ch in value)
    return value


_Text = Annotated[str, BeforeValidator(_clean_text), Field(max_length=320)] | None
_Code = Annotated[str, BeforeValidator(_clean_text), Field(max_length=16)]


class _DraftPart(TephraModel):
    """Every key the onboarding pages write, nothing else, each value bounded; nothing is
    required (a page not reached yet is empty)."""

    model_config = ConfigDict(extra="forbid")


class DraftAirline(_DraftPart):
    name: _Text = None
    icao: _Text = None
    iata: _Text = None
    callsign_prefix: _Text = None
    callsign_touched: bool = False
    state_of_operator: _Text = None
    aoc_number: _Text = None
    main_base: _Text = None
    ops_email: _Text = None
    contact_name: _Text = None


class DraftChange(_DraftPart):
    value: _Text = None
    reason: _Text = None
    base: float | None = None
    unit: _Text = None


class DraftPolicy(_DraftPart):
    preset: Literal["A"] = "A"
    changes: dict[Annotated[str, Field(max_length=60)], DraftChange] = Field(
        default_factory=dict, max_length=64
    )
    risk_owner: _Text = None
    sra_ref: _Text = None


class DraftAircraft(_DraftPart):
    registration: _Text = None
    type_icao: _Text = None
    seats: _Text = None
    home_base: _Text = None
    hex: _Text = None


class DraftFleet(_DraftPart):
    aircraft: list[DraftAircraft] = Field(default_factory=list, max_length=1000)
    extra_prefixes: list[_Code] = Field(default_factory=list, max_length=8)


class DraftNetwork(_DraftPart):
    airports: list[_Code] = Field(default_factory=list, max_length=200)
    alternates: dict[_Code, list[_Code]] = Field(default_factory=dict, max_length=201)

    @field_validator("alternates", mode="after")
    @classmethod
    def _few_alternates(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        if any(len(codes) > 8 for codes in value.values()):
            raise ValueError("at most 8 alternates an airport")
        return value


class DraftSummary(_DraftPart):
    flights: int = Field(default=0, ge=0, le=20_000)
    tails: int = Field(default=0, ge=0, le=5_000)
    crews: int = Field(default=0, ge=0, le=5_000)
    crew_bases: list[_Code] = Field(default_factory=list, max_length=50)


class DraftSchedule(_DraftPart):
    skipped: bool = False
    summary: DraftSummary | None = None


class DraftFeeds(_DraftPart):
    positions: bool = False
    flight_plans: bool = False
    pilot_reports: bool = False
    source_system: _Text = None


class DraftDispatcher(_DraftPart):
    name: _Text = None
    role: Literal["approves", "views"] | None = None


class DraftPeople(_DraftPart):
    dispatchers: list[DraftDispatcher] = Field(default_factory=list, max_length=60)


class DraftAssistant(_DraftPart):
    provider: AssistantProvider | None = None
    model: _Text = None
    model_lite: _Text = None


class DraftValues(_DraftPart):
    """The onboarding pages' values as typed (``onboard/pages.js`` ``emptyValues``), checked
    for shape and size only: the rules are checked on each page and again on submit."""

    airline: DraftAirline = Field(default_factory=DraftAirline)
    policy: DraftPolicy = Field(default_factory=DraftPolicy)
    fleet: DraftFleet = Field(default_factory=DraftFleet)
    network: DraftNetwork = Field(default_factory=DraftNetwork)
    schedule: DraftSchedule = Field(default_factory=DraftSchedule)
    feeds: DraftFeeds = Field(default_factory=DraftFeeds)
    people: DraftPeople = Field(default_factory=DraftPeople)
    assistant: DraftAssistant = Field(default_factory=DraftAssistant)


class OnboardDraft(_DraftPart):
    """Where the airline is in onboarding: the page it is on, the pages it has opened and the
    values. Private to the account, like the answers."""

    at: PageKey | None = None
    seen: list[PageKey] = Field(default_factory=list, max_length=9)
    values: DraftValues = Field(default_factory=DraftValues)

    @field_validator("seen", mode="after")
    @classmethod
    def _each_page_once(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


# --- stored documents -------------------------------------------------------------------

HistoryAction = Literal[
    "created",
    "answers_changed",
    "assistant_changed",
    "submitted",
    "verified",
    "declined",
    "hosting_approved",
]


class Stamp(TephraModel):
    """Who did something and when (wall clock). ``by`` is ``"<display name>#<member id>"`` for
    an airline member or ``"operator:<name>#<k[:8]>"`` for TEPHRA staff; pages
    show the part before ``#``."""

    by: str = Field(min_length=1, max_length=160)
    at: UtcDatetime


class HistoryEntry(TephraModel):
    """The airline record's own hash-linked history, private to the airline and TEPHRA staff
    (never the public audit trail, which would list airlines publicly)."""

    seq: int = Field(ge=1)
    at: UtcDatetime = Field(description="Wall clock")
    actor: str = Field(
        description="'airline', 'operator:<name>#<k8>' (TEPHRA staff), or 'desk:<name>' on "
        "records the Desk decided before staff verified airlines"
    )
    action: HistoryAction
    note: str | None = Field(default=None, max_length=500)
    prev_sha256: str = Field(description="'0' * 64 for the first entry")
    sha256: str = Field(description="sha256_json of the entry without sha256")


class AirlineRecord(TephraModel):
    """Collection ``airlines``, id = ``id``. Compare-and-set on ``version``. A ``draft`` has
    its pages as typed and no answers; submitting checks them into ``answers`` and the draft
    goes. A record stored before drafts existed has answers, a status and no draft."""

    id: str = Field(pattern=r"^AL-[0-9a-f]{12}$")
    version: int = Field(ge=1)
    status: AirlineStatus
    login_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    email: str
    answers: AirlineAnswers | None = None
    draft: OnboardDraft | None = None
    created_at: UtcDatetime | None = Field(default=None, description="None before drafts")
    submitted_at: UtcDatetime | None = None
    updated_at: UtcDatetime

    @model_validator(mode="after")
    def _answers_once_submitted(self) -> Self:
        if self.status != "draft" and self.answers is None:
            raise ValueError("a submitted airline has its answers")
        if self.status != "draft" and self.submitted_at is None:
            raise ValueError("a submitted airline has its submitted_at")
        return self

    def submitted(self) -> AirlineAnswers:
        """The answers of a submitted airline (never a draft's)."""
        if self.answers is None:
            raise ValueError(f"airline {self.id} has not submitted")
        return self.answers

    decided_at: UtcDatetime | None = None
    decline_reason: str | None = Field(default=None, max_length=500)
    flags: list[str] = Field(default_factory=list, description="Reviewer hints, TEPHRA staff only")
    history: list[HistoryEntry]
    hosting: Stamp | None = Field(
        default=None,
        exclude_if=_is_none,
        description="An operator's approval to host this airline on the site (hosted feature)",
    )


class AirlineLogin(TephraModel):
    """Collection ``airline_logins``, id = ``login_key``: credentials, never returned."""

    login_key: str
    airline_id: str | None = Field(
        description="None: a member-only login (joined a hosted airline; no onboarding record)"
    )
    email: str
    password: str = Field(description="scrypt$N$r$p$<salt>$<hash>, never the password")
    recovery_sha256: str
    session_version: int = Field(ge=1, description="Bumped on recovery: other browsers sign out")
    created_at: UtcDatetime
    password_changed_at: UtcDatetime
    last_sign_in_at: UtcDatetime | None = Field(default=None, exclude_if=_is_none)


# --- views ------------------------------------------------------------------------------


class StatusStep(TephraModel):
    kind: Literal["submitted", "verified", "declined"]
    at: UtcDatetime
    reason: str | None = None


class AirlineView(TephraModel):
    """``GET /api/airline/me``: never the login key, the reviewer flags or the history. A
    draft has ``draft`` and no answers; a submitted airline has answers and no draft."""

    id: str
    version: int
    status: AirlineStatus
    status_label: str
    email: str
    answers: AirlineAnswers | None
    draft: OnboardDraft | None
    submitted_at: UtcDatetime | None
    updated_at: UtcDatetime
    steps: list[StatusStep]
    editable: bool = Field(description="The answers can be changed (pending only)")

    @classmethod
    def of(cls, record: AirlineRecord) -> Self:
        steps: list[StatusStep] = []
        if record.submitted_at is not None and record.status != "draft":
            steps.append(StatusStep(kind="submitted", at=record.submitted_at))
        if record.status in ("verified", "declined") and record.decided_at is not None:
            steps.append(
                StatusStep(kind=record.status, at=record.decided_at, reason=record.decline_reason)
            )
        return cls(
            id=record.id,
            version=record.version,
            status=record.status,
            status_label=STATUS_LABEL[record.status],
            email=record.email,
            answers=record.answers,
            draft=record.draft if record.status == "draft" else None,
            submitted_at=record.submitted_at,
            updated_at=record.updated_at,
            steps=steps,
            editable=record.status == "pending",
        )


class AccountCreated(TephraModel):
    airline: AirlineView
    recovery_code: str = Field(description="XXXX-XXXX-XXXX-XXXX, in this answer only")


class RecoveryCode(TephraModel):
    recovery_code: str = Field(description="A new code; the old one no longer works")


class AirlineSessionView(TephraModel):
    """``GET /api/airline/session``: from the cookie alone, no store read (a draft's ICAO and
    name are None). Sign-in answers with the same shape and the record's ``status``."""

    accounts: bool = Field(description="onboard is on and the session secret is set")
    signed_in: bool
    icao: str | None = None
    name: str | None = None
    status: AirlineStatus | None = Field(default=None, description="Sign-in's answer only")
    staff: bool = Field(
        default=False,
        description="A signed, unexpired TEPHRA staff cookie came along (no store read): the nav "
        "then asks GET /api/admin/me",
    )


class AirlineDeskRow(TephraModel):
    """A submitted airline, as TEPHRA staff read it: never a draft."""

    id: str
    version: int
    status: DeskStatus
    status_label: str
    name: str
    icao: str
    state_of_operator: str
    aoc_number: str | None
    ops_email: str
    email: str
    submitted_at: UtcDatetime | None
    decided_at: UtcDatetime | None = Field(default=None, description="Verified or declined at")
    aircraft: int
    airports: int
    flags: list[str]

    @classmethod
    def of(cls, record: AirlineRecord) -> Self:
        answers = record.submitted()
        airline = answers.airline
        return cls(
            id=record.id,
            version=record.version,
            status=record.status,
            status_label=STAFF_STATUS_LABEL[record.status],
            name=airline.name,
            icao=airline.icao,
            state_of_operator=airline.state_of_operator,
            aoc_number=airline.aoc_number,
            ops_email=airline.ops_email,
            email=record.email,
            submitted_at=record.submitted_at,
            decided_at=record.decided_at,
            aircraft=len(answers.fleet.aircraft),
            airports=len(answers.network.airports),
            flags=record.flags,
        )


class StaffList(TephraModel):
    """The staff console's airlines on a site that hosts none (``hosted`` off)."""

    to_verify: int = Field(description="Airlines waiting to be verified (pending)")
    onboarding: int = Field(description="Airlines still onboarding: a count, never rows")
    airlines: list[AirlineDeskRow]


class AirlineDeskView(AirlineDeskRow):
    answers: AirlineAnswers
    history: list[HistoryEntry]
    history_ok: bool = Field(description="Every link of the private history checks out")
    history_broken_at: int | None = Field(
        default=None, description="The first entry whose link does not check out"
    )


class DryRunSection(TephraModel):
    total: int
    accepted: int


class DryRunRecord(TephraModel):
    section: Literal["positions", "flight_plans", "pilot_reports"]
    index: int
    text: str = Field(description="One line, e.g. '8a0412 · RFA1654 · -6.21, 106.40 · FL350'")
    note: str | None = None


class DryRunResult(TephraModel):
    """A push file checked as the push would check it, with nothing taken in."""

    format: str
    checked_at: UtcDatetime = Field(description="Wall clock: freshness is checked against it")
    positions: DryRunSection
    flight_plans: DryRunSection
    pilot_reports: DryRunSection
    rejected: list[PushProblem]
    accepted: list[DryRunRecord]


# --- request bodies ---------------------------------------------------------------------


class _Credentials(TephraModel):
    """Passwords are never stripped, only NFC-normalised: the same password typed on two
    keyboards (composed or not) is the same password. Emails are compared lower-cased."""

    model_config = ConfigDict(extra="forbid")

    @field_validator("email", "password", "new_password", mode="before", check_fields=False)
    @classmethod
    def _normalise(cls, value: object, info: ValidationInfo) -> object:
        if not isinstance(value, str):
            return value
        if info.field_name == "email":
            return value.strip().lower()
        return unicodedata.normalize("NFC", value)


class AccountCreate(_Credentials):
    """The account comes first: its onboarding pages are a draft until the airline submits."""

    email: str = Field(max_length=254, pattern=EMAIL)
    password: str = Field(min_length=12, max_length=128)
    acknowledge: Literal[True] = Field(description="Decision support only; a person decides")
    website: str = Field(default="", max_length=0, description="Left empty by people")

    @model_validator(mode="after")
    def _password_is_not_the_email(self) -> Self:
        if self.password.strip().lower() == self.email:
            raise ValueError("the password must not be the email")
        return self


class SignIn(_Credentials):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


class Recover(_Credentials):
    email: str = Field(max_length=254)
    recovery_code: str = Field(max_length=32)
    new_password: str = Field(min_length=12, max_length=128)


class DeleteAccount(_Credentials):
    password: str = Field(max_length=128)


class AnswersUpdate(_Form):
    version: int = Field(ge=1)
    answers: AirlineAnswers


class DraftUpdate(TephraModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    draft: OnboardDraft


class Submit(_Form):
    """Review's Submit for verification: the pages' answers, checked as a whole."""

    version: int = Field(ge=1)
    answers: AirlineAnswers


class AssistantUpdate(_Form):
    version: int = Field(ge=1)
    assistant: AssistantChoice
