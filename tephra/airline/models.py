"""The onboarding answers, the stored airline documents, the views the API returns and the
request bodies (``tephra.api.routes_airline``).

No field anywhere holds a key, PIN, secret, token, password, Ollama address or file contents:
the airline's own Gemini key and its schedule files stay in its browser and its setup kit.
Validator messages never repeat the input (the app's 422 body copies them as written).
"""

import re
import unicodedata
from typing import Any, Final, Literal, Self

from pydantic import ConfigDict, Field, ValidationInfo, field_validator, model_validator

from tephra.models import PushProblem, TephraModel, UtcDatetime

__all__ = [
    "EMAIL",
    "ONBOARD_FORMAT",
    "STATUS_LABEL",
    "AccountCreate",
    "AccountCreated",
    "AirlineAnswers",
    "AirlineDeskRow",
    "AirlineDeskView",
    "AirlineIdentity",
    "AirlineList",
    "AirlineLogin",
    "AirlineRecord",
    "AirlineSessionView",
    "AirlineStatus",
    "AirlineView",
    "AnswersUpdate",
    "AshPolicy",
    "AssistantChoice",
    "AssistantUpdate",
    "DeclineAirline",
    "DeleteAccount",
    "DeleteAirline",
    "Dispatcher",
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
    "People",
    "PolicyChange",
    "Recover",
    "RecoveryCode",
    "ScheduleSummary",
    "SignIn",
    "StatusStep",
    "VerifyAirline",
]

ONBOARD_FORMAT: Final = "tephra.onboard/2"
EMAIL: Final = r"^[^@\s]{1,64}@[^@\s]{1,189}\.[^@\s]{2,63}$"
ICAO_AIRPORT: Final = r"^[A-Z]{4}$"
_AIRPORT = re.compile(ICAO_AIRPORT)
_PREFIX = re.compile(r"^[A-Z]{3}$")
_AI_STUDIO_MODEL = re.compile(r"^(gemini|gemma)-[a-z0-9.-]{1,60}$")
_OLLAMA_TAG = re.compile(r"^[a-z0-9._-]{1,60}:[a-z0-9._-]{1,40}$")
_BIDI_CONTROLS: Final = frozenset("‪‫‬‭‮⁦⁧⁨⁩")

AirlineStatus = Literal["pending", "verified", "declined"]
STATUS_LABEL: Final[dict[str, str]] = {
    "pending": "Pending verification",
    "verified": "Verified",
    "declined": "Declined",
}


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
    """Counts only: the schedule files stay in the airline's browser and its setup kit."""

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


# --- stored documents -------------------------------------------------------------------

HistoryAction = Literal["created", "answers_changed", "assistant_changed", "verified", "declined"]


class HistoryEntry(TephraModel):
    """The airline record's own hash-linked history, private to the airline and the Desk (never
    the public audit trail, which would list airlines publicly)."""

    seq: int = Field(ge=1)
    at: UtcDatetime = Field(description="Wall clock")
    actor: str = Field(description="'airline' or 'desk:<name>'")
    action: HistoryAction
    note: str | None = Field(default=None, max_length=500)
    prev_sha256: str = Field(description="'0' * 64 for the first entry")
    sha256: str = Field(description="sha256_json of the entry without sha256")


class AirlineRecord(TephraModel):
    """Collection ``airlines``, id = ``id``. Compare-and-set on ``version``."""

    id: str = Field(pattern=r"^AL-[0-9a-f]{12}$")
    version: int = Field(ge=1)
    status: AirlineStatus
    login_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    email: str
    answers: AirlineAnswers
    submitted_at: UtcDatetime
    updated_at: UtcDatetime
    decided_at: UtcDatetime | None = None
    decline_reason: str | None = Field(default=None, max_length=500)
    flags: list[str] = Field(default_factory=list, description="Reviewer hints, Desk only")
    history: list[HistoryEntry]


class AirlineLogin(TephraModel):
    """Collection ``airline_logins``, id = ``login_key``: credentials, never returned."""

    login_key: str
    airline_id: str
    email: str
    password: str = Field(description="scrypt$N$r$p$<salt>$<hash>, never the password")
    recovery_sha256: str
    session_version: int = Field(ge=1, description="Bumped on recovery: other browsers sign out")
    created_at: UtcDatetime
    password_changed_at: UtcDatetime


# --- views ------------------------------------------------------------------------------


class StatusStep(TephraModel):
    kind: Literal["submitted", "verified", "declined"]
    at: UtcDatetime
    reason: str | None = None


class AirlineView(TephraModel):
    """``GET /api/airline/me``: never the login key, the reviewer flags or the history."""

    id: str
    version: int
    status: AirlineStatus
    status_label: str
    email: str
    answers: AirlineAnswers
    submitted_at: UtcDatetime
    updated_at: UtcDatetime
    steps: list[StatusStep]
    editable: bool

    @classmethod
    def of(cls, record: AirlineRecord) -> Self:
        steps = [StatusStep(kind="submitted", at=record.submitted_at)]
        if record.status != "pending" and record.decided_at is not None:
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
    """``GET /api/airline/session``: from the cookie alone, no store read."""

    accounts: bool = Field(description="onboard is on and the session secret is set")
    signed_in: bool
    icao: str | None = None
    name: str | None = None


class AirlineDeskRow(TephraModel):
    id: str
    version: int
    status: AirlineStatus
    status_label: str
    name: str
    icao: str
    state_of_operator: str
    aoc_number: str | None
    ops_email: str
    email: str
    submitted_at: UtcDatetime
    aircraft: int
    airports: int
    flags: list[str]

    @classmethod
    def of(cls, record: AirlineRecord) -> Self:
        airline = record.answers.airline
        return cls(
            id=record.id,
            version=record.version,
            status=record.status,
            status_label=STATUS_LABEL[record.status],
            name=airline.name,
            icao=airline.icao,
            state_of_operator=airline.state_of_operator,
            aoc_number=airline.aoc_number,
            ops_email=airline.ops_email,
            email=record.email,
            submitted_at=record.submitted_at,
            aircraft=len(record.answers.fleet.aircraft),
            airports=len(record.answers.network.airports),
            flags=record.flags,
        )


class AirlineList(TephraModel):
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
    answers: AirlineAnswers
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


class AssistantUpdate(_Form):
    version: int = Field(ge=1)
    assistant: AssistantChoice


class VerifyAirline(_Form):
    version: int = Field(ge=1)
    note: str | None = Field(default=None, max_length=300)

    @field_validator("note", mode="before")
    @classmethod
    def _tidy_optional(cls, value: object) -> object:
        return _optional(value)


class DeclineAirline(_Form):
    version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=500)


class DeleteAirline(_Form):
    version: int = Field(ge=1)
