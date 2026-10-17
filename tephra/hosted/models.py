"""Hosted documents (tenant records, members, invites, operators, policy versions), the views
the hosted, airline and operator routes return (SPEC §4.3), and their request bodies.

Root collections hold the site's documents (``hosted_tenants``, ``hosted_members``,
``hosted_invites``, ``hosted_slots``, ``hosted_meter``, ``operators``, ``operator_invites``); an
airline's own namespace holds its ``policy_versions`` beside every other collection. No audit
entry and no view carries a password, a token or a model key; emails are shown to an airline's
ops managers and to TEPHRA's operators only.
"""

import unicodedata
from contextlib import AbstractContextManager
from datetime import date
from typing import Any, Final, Literal, Protocol, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from tephra.agents.budget import BudgetView
from tephra.airline.models import EMAIL, PolicyChange, Stamp
from tephra.config import RegionKey
from tephra.models import AuditEntry, ConnectionView, TephraModel, UtcDatetime
from tephra.store.base import Store
from tephra.store.metered import MeterDay

__all__ = [
    "ROLE_RANK",
    "ROLE_WORDS",
    "RUNNING",
    "STATE_WORDS",
    "AcceptBody",
    "AdminAi",
    "AdminContact",
    "AdminFeeds",
    "AdminList",
    "AdminMeter",
    "AdminRow",
    "AssistantBody",
    "AssistantKeyView",
    "AssistantTab",
    "BlobPuts",
    "CanSetUp",
    "ChainLine",
    "ConfirmBody",
    "ConfirmIcaoBody",
    "DeclineBody",
    "EmailBody",
    "FeedCard",
    "FeedKeyView",
    "FeedReason",
    "FeedsView",
    "GoLive",
    "GoLiveItem",
    "HostedMe",
    "HostedRefused",
    "HostedRole",
    "InviteBody",
    "InviteLink",
    "InviteRow",
    "InviteView",
    "JoinBody",
    "KeyBody",
    "KeyNameBody",
    "LastPass",
    "LinkView",
    "LiveBody",
    "LiveLine",
    "Member",
    "MemberRow",
    "Membership",
    "MeterCounts",
    "MeterDay",
    "ModelChoice",
    "Operator",
    "OperatorAcceptBody",
    "OperatorInvite",
    "OperatorInviteBody",
    "OperatorInviteView",
    "OperatorSignIn",
    "OperatorView",
    "PausedLine",
    "PeopleLimits",
    "PeopleTab",
    "PolicyBody",
    "PolicyConfirmed",
    "PolicyCurrent",
    "PolicyLine",
    "PolicyTab",
    "PolicyValueRow",
    "PolicyVersion",
    "PolicyVersionRow",
    "ProcessLine",
    "ReasonBody",
    "RecordHead",
    "RecordTab",
    "RegionChoice",
    "RegionOption",
    "RoleBody",
    "RuntimeLine",
    "SealedKey",
    "SetUpBody",
    "SlotDoc",
    "Slots",
    "Space",
    "SraAcceptance",
    "SraBody",
    "Stamp",
    "StartBody",
    "SuspendedLine",
    "TenantAssistant",
    "TenantHeader",
    "TenantRecord",
    "TenantState",
    "TokenBody",
    "VerifyBody",
    "VersionBody",
    "You",
]

TenantState = Literal["setup", "shadow", "live", "suspended", "deleting", "deleted"]
HostedRole = Literal["ops_manager", "dispatcher", "viewer"]
ROLE_RANK: Final[dict[str, int]] = {"viewer": 0, "dispatcher": 1, "ops_manager": 2}
ROLE_WORDS: Final[dict[str, str]] = {
    "ops_manager": "Ops manager",
    "dispatcher": "Dispatcher",
    "viewer": "Viewer",
}
RUNNING: Final[frozenset[str]] = frozenset({"shadow", "live"})
"""States that hold one of the site's airline places and run a runtime."""
STATE_WORDS: Final[dict[str, str]] = {
    "setup": "Verified",
    "shadow": "Shadow",
    "live": "Live",
    "suspended": "Suspended",
    "deleting": "Data deleted",
    "deleted": "Data deleted",
}


class HostedRefused(Exception):
    """A hosted action refused for a reason the person can act on. The routes answer it as
    ``ErrorBody(status, code, detail)``; ``detail`` never repeats what was typed."""

    def __init__(self, status: int, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.status = status
        self.code = code
        self.detail = detail


class Space(Protocol):
    """What the domain functions need of an airline's space (``registry.TenantSpace``): its
    store, and a binding of the wall clock and the airline for the work done on it."""

    icao: str
    store: Store

    def bound(self) -> AbstractContextManager[None]: ...


# --- stored documents -------------------------------------------------------------------


class SealedKey(TephraModel):
    """An airline's model key, sealed with AES-256-GCM (``tephra.hosted.keys``)."""

    v: Literal[1] = 1
    kid: str = Field(pattern=r"^[0-9a-f]{16}$", description="Which secret sealed it (HKDF)")
    nonce: str = Field(description="b64url, 12 bytes")
    ct: str = Field(description="b64url ciphertext with its tag")
    last4: str = Field(pattern=r"^[A-Za-z0-9_-]{4}$")
    set_by: Stamp


class TenantAssistant(TephraModel):
    model: str = Field(description="A key of Settings.model_limits (the free-tier table)")
    model_lite: str
    reserve_share: float = Field(
        default=0.2, ge=0.1, le=0.5, description="Held for the Desk (ai_interactive_share)"
    )
    daily_limits: dict[str, int] = Field(
        default_factory=dict,
        description="Model -> calls a day, each 1..that model's free-tier rpd; a model not "
        "named keeps TEPHRA's own budget (its free limit less the margin)",
    )


class PolicyConfirmed(Stamp):
    version: int = Field(ge=1)


class SraAcceptance(TephraModel):
    """Recorded by the airline; TEPHRA does not check it."""

    version: int = Field(ge=1)
    accepted_by: str = Field(min_length=2, max_length=80)
    accepted_on: date
    sra_ref: str | None = Field(default=None, max_length=120)
    recorded: Stamp


class TenantRecord(TephraModel):
    """``hosted_tenants/<ICAO>``; every change is a compare-and-set that bumps ``version``."""

    icao: str = Field(pattern=r"^[A-Z]{3}$")
    airline_id: str
    name: str
    iata: str | None = None
    version: int = Field(ge=1)
    state: TenantState
    state_since: UtcDatetime
    region: RegionKey | None = None
    created: Stamp
    started: Stamp | None = Field(default=None, description="The last setup -> shadow")
    live: Stamp | None = Field(default=None, description="The flip in force; None outside LIVE")
    suspended: Stamp | None = None
    suspend_reason: str | None = Field(default=None, max_length=300)
    ops_managers: list[str] = Field(description="Member ids; the source of truth for the role")
    assistant: TenantAssistant | None = None
    model_key: SealedKey | None = None
    policy_version: int = Field(default=1, ge=1)
    policy_confirmed: PolicyConfirmed | None = None
    sra: SraAcceptance | None = None
    restarts: dict[str, int] = Field(
        default_factory=dict, description="Pacific day -> runtime restarts (at most 6)"
    )
    chain_checked: Stamp | None = Field(default=None, description="The last full walk")
    deleted: Stamp | None = None


class Member(TephraModel):
    """``hosted_members/<ICAO>~<login key>``. For ops managers ``TenantRecord.ops_managers``
    wins: a role that disagrees is rewritten on read (``members.effective``)."""

    id: str = Field(pattern=r"^MB-[0-9a-f]{10}$", description="The only id the API shows")
    icao: str = Field(pattern=r"^[A-Z]{3}$")
    login_key: str
    email: str
    display_name: str = Field(min_length=2, max_length=32)
    role: HostedRole
    joined_at: UtcDatetime
    invited_by: str | None = Field(default=None, description="Member id or operator:<k8>")


class Invite(TephraModel):
    """``hosted_invites/<sha256(token)>``: the token itself is never stored."""

    id: str = Field(pattern=r"^IV-[0-9a-f]{10}$")
    sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$", description="The token's SHA-256: the document id"
    )
    icao: str = Field(pattern=r"^[A-Z]{3}$")
    email: str = Field(description="Lower-cased; only a login with this email may accept")
    role: HostedRole
    created: Stamp
    created_by: str = Field(description="Member id, or 'operator:<k[:8]>'")
    expires_at: UtcDatetime
    used: Stamp | None = None
    revoked: Stamp | None = None


class Operator(TephraModel):
    """``operators/<login key>``: one of TEPHRA's own people (never an airline member)."""

    login_key: str
    email: str
    name: str = Field(min_length=2, max_length=32)
    password: str = Field(description="scrypt$..., never returned")
    session_version: int = Field(default=1, ge=1)
    disabled: Stamp | None = None
    created_at: UtcDatetime
    last_sign_in_at: UtcDatetime | None = None


class OperatorInvite(TephraModel):
    """``operator_invites/<sha256(token)>``; ``created_by`` None is the bootstrap invite."""

    email: str
    name: str
    created_by: str | None
    created_at: UtcDatetime
    expires_at: UtcDatetime
    used_at: UtcDatetime | None = None


class PolicyVersion(TephraModel):
    """``tenants/<ICAO>/policy_versions/%06d``: every change from the base policy (not a
    difference from the version before)."""

    version: int = Field(ge=1)
    base_policy_id: str
    base_version: str
    changes: list[PolicyChange] = Field(max_length=32)
    created: Stamp
    note: str | None = Field(default=None, max_length=300)


class SlotDoc(TephraModel):
    """``hosted_slots/site``: the airlines holding one of the site's places."""

    holders: list[str] = Field(default_factory=list)
    version: int = 0


# --- views (SPEC §4.3) ------------------------------------------------------------------


class You(TephraModel):
    name: str
    role: HostedRole
    member_id: str


class Membership(TephraModel):
    icao: str
    name: str
    role: HostedRole
    state: TenantState


class RuntimeLine(TephraModel):
    running: bool
    last_tick_wall_at: UtcDatetime | None
    failures: int
    problem: str | None
    updating: bool = Field(description="The last tick finished at most 150 s ago")


class PausedLine(TephraModel):
    scope: Literal["airline", "site"]
    reason: Literal["reads", "writes", "deletes"]
    resumes_at: UtcDatetime


class SuspendedLine(TephraModel):
    at: UtcDatetime
    reason: str
    delete_after: UtcDatetime


class LiveLine(TephraModel):
    by: str
    at: UtcDatetime


class ChainLine(TephraModel):
    intact: bool
    entries: int
    checked_at: UtcDatetime | None


class PolicyLine(TephraModel):
    version: int
    label: str


class TenantHeader(TephraModel):
    icao: str
    name: str
    iata: str | None
    state: TenantState
    state_since: UtcDatetime
    wall_now: UtcDatetime
    you: You
    memberships: list[Membership]
    runtime: RuntimeLine
    paused: PausedLine | None
    suspended: SuspendedLine | None
    live: LiveLine | None
    chain: ChainLine
    policy: PolicyLine
    started: LiveLine | None = Field(
        default=None, description="Who started the runs and when, while shadow or live"
    )


class GoLiveItem(TephraModel):
    key: Literal["feeds", "assistant", "policy", "people"]
    done: bool
    title: str
    detail: str
    href: str


class RegionChoice(TephraModel):
    key: RegionKey
    name: str
    derived: bool


class RegionOption(TephraModel):
    key: RegionKey
    name: str


class Slots(TephraModel):
    used: int
    max: int


class GoLive(TephraModel):
    state: TenantState
    items: list[GoLiveItem]
    region: RegionChoice | None
    regions: list[RegionOption]
    region_note: str | None
    slots: Slots
    can_start: bool
    blocked: Literal["checklist", "region", "airline_limit_reached", "site_memory"] | None


class FeedReason(TephraModel):
    reason: str
    count: int


class FeedCard(TephraModel):
    feed: Literal["positions", "flight_plans", "pilot_reports"]
    declared: bool
    last_received_at: UtcDatetime | None
    records_last_hour: int
    refused_last_hour: int
    reasons: list[FeedReason]
    optional: bool = False


class FeedKeyView(ConnectionView):
    sections_seen: list[str] = Field(
        default_factory=list, description="Sections pushed since FeedsView.counted_since"
    )


class FeedsView(TephraModel):
    taken_in: bool = Field(description="False in setup: pushes are checked, not taken in")
    push_url: str
    counted_since: UtcDatetime
    cards: list[FeedCard]
    keys: list[FeedKeyView]


class PolicyCurrent(TephraModel):
    version: int
    created: Stamp
    note: str | None
    changes: list[PolicyChange]


class PolicyVersionRow(TephraModel):
    version: int
    created: Stamp
    changed: list[str]


class PolicyValueRow(TephraModel):
    name: str
    value: int
    base: int
    unit: str
    editable: bool
    not_built: str | None = None


class PolicyTab(TephraModel):
    current: PolicyCurrent
    versions: list[PolicyVersionRow]
    values: list[PolicyValueRow]
    label: str
    confirmed: PolicyConfirmed | None
    sra: SraAcceptance | None


class ModelChoice(TephraModel):
    name: str
    free_rpd: int


class AssistantKeyView(TephraModel):
    set: bool
    last4: str | None = None
    set_by: Stamp | None = None
    readable: bool | None = Field(default=None, description="None while no key is set")


class AssistantTab(TephraModel):
    model: str | None
    model_lite: str | None
    models: list[ModelChoice]
    key: AssistantKeyView
    reserve_share: float
    daily_limits: dict[str, int]
    state: Literal["on", "paused", "unavailable"]
    reason: str | None
    budget: BudgetView | None = Field(description="This airline's ledger; None in setup")


class MemberRow(TephraModel):
    id: str
    name: str
    email: str | None = Field(description="Ops managers only")
    role: HostedRole
    joined_at: UtcDatetime
    last_sign_in_at: UtcDatetime | None
    you: bool


class InviteRow(TephraModel):
    id: str
    email: str | None = Field(description="Ops managers only")
    role: HostedRole
    created: Stamp
    expires_at: UtcDatetime


class PeopleLimits(TephraModel):
    members: int
    open_invites: int


class PeopleTab(TephraModel):
    members: list[MemberRow]
    invites: list[InviteRow]
    limits: PeopleLimits


class InviteLink(TephraModel):
    invite: InviteRow
    link: str = Field(description="https://<host>/join#<token>: the token only here")


class RecordHead(TephraModel):
    intact: bool
    entries: int
    head_seq: int
    head_sha256: str
    verified_through_seq: int | None
    checked_at: UtcDatetime | None
    problems: list[str]
    note: str


class RecordTab(TephraModel):
    entries: list[AuditEntry]
    head: RecordHead | None = Field(description="None while the airline's record is empty")
    next_before_seq: int | None
    can_check: bool
    can_export: bool


class CanSetUp(TephraModel):
    icao: str
    name: str


class HostedMe(TephraModel):
    memberships: list[Membership]
    can_set_up: CanSetUp | None
    waiting: Literal["hosting_not_approved"] | None
    max_airlines: int = Field(
        ge=0, le=3, description="Airlines this site runs at once (TEPHRA_HOSTED_MAX_TENANTS)"
    )


class InviteYou(TephraModel):
    """The browser's own sign-in, when the join page is opened signed in: who it is (masked),
    whether this invite is for its email, and the name it uses in another airline."""

    email_hint: str
    for_you: bool
    name: str | None = None


class InviteView(TephraModel):
    airline: str
    icao: str
    role: HostedRole
    email_hint: str
    expires_at: UtcDatetime
    invited_by: str
    you: InviteYou | None = Field(default=None, description="None when signed out")


class OperatorView(TephraModel):
    name: str
    email: str
    k: str = Field(description="The operator's short key: the id in operator routes")
    created_at: UtcDatetime
    last_sign_in_at: UtcDatetime | None
    you: bool
    disabled: Stamp | None


class LinkView(TephraModel):
    """A one-time link (an operator's invite, an ops-manager invite): shown once."""

    link: str = Field(description="https://<host>/admin/join#<token> or /join#<token>")
    expires_at: UtcDatetime


class OperatorInviteView(TephraModel):
    name: str
    email_hint: str
    expires_at: UtcDatetime


class AdminContact(TephraModel):
    ops_email: str
    contact_name: str | None
    mailto: str


class MeterCounts(TephraModel):
    reads: int
    writes: int
    deletes: int


class BlobPuts(TephraModel):
    month: str
    used: int
    cap: int


class AdminMeter(TephraModel):
    day: date
    reads: int = Field(description="The whole site's, the demo's included")
    writes: int
    deletes: int
    airlines: MeterCounts = Field(
        description="The hosted airlines' together: what the site caps pause them on"
    )
    caps: MeterCounts
    allowance: MeterCounts
    by_namespace: dict[str, MeterCounts]
    blob_puts: BlobPuts
    counted_since: UtcDatetime


class ProcessLine(TephraModel):
    rss_mb: int
    limit_mb: int


class LastPass(TephraModel):
    at: UtcDatetime
    seconds: float
    budget_s: int


class AdminFeeds(TephraModel):
    ok: int
    stale: int
    error: int
    note: str | None


class AdminAi(TephraModel):
    model: str
    used: int
    budget: int


class AdminRow(TephraModel):
    airline_id: str
    name: str
    icao: str
    status: str = Field(description="Airline status (pending, declined) or the tenant state")
    status_label: str
    state_since: UtcDatetime | None
    hosting: Literal["desk", "operator"] | None
    checklist: str | None = Field(description="'2/4' for an airline in setup")
    feeds: AdminFeeds | None
    ai: list[AdminAi]
    advisories_waiting: int
    runtime_problem: str | None
    paused: PausedLine | None
    chain_intact: bool
    delete_after: UtcDatetime | None
    ops_email: str
    version: int = Field(description="The airline record's version (verify, decline, approve)")


class AdminList(TephraModel):
    slots: Slots
    limit_reached: bool
    hosting: Literal["always-on", "on-demand"]
    to_verify: int = Field(description="Airlines waiting to be verified (pending)")
    to_approve: int = Field(
        description="Airlines the Desk verified, waiting for an operator to approve hosting"
    )
    advisories_waiting: int
    meter: AdminMeter
    process: ProcessLine
    last_pass: LastPass | None
    unreadable_keys: int
    onboarding: int = Field(description="Airlines still onboarding: a count, never rows")
    rows: list[AdminRow]


# --- request bodies ---------------------------------------------------------------------


class _Body(TephraModel):
    """Unknown keys are refused; strings are stripped."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class _CredentialBody(TephraModel):
    """As the airline accounts': emails compared lower-cased, passwords NFC and never
    stripped."""

    model_config = ConfigDict(extra="forbid")

    @field_validator("email", "password", mode="before", check_fields=False)
    @classmethod
    def _normalise(cls, value: object, info: Any) -> object:
        if not isinstance(value, str):
            return value
        if info.field_name == "email":
            return value.strip().lower()
        return unicodedata.normalize("NFC", value)


class SetUpBody(_Body):
    display_name: str = Field(min_length=2, max_length=32)


class StartBody(_Body):
    region: RegionKey


class LiveBody(_Body):
    confirm_icao: str = Field(max_length=8)
    attest: Literal[True]


class ReasonBody(_Body):
    reason: str = Field(min_length=3, max_length=300)


class ConfirmIcaoBody(_Body):
    confirm_icao: str = Field(max_length=8)


class KeyNameBody(_Body):
    name: str = Field(min_length=2, max_length=48)


class PolicyBody(_Body):
    base_version: int = Field(ge=1)
    changes: list[PolicyChange] = Field(max_length=32)
    note: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _each_value_once(self) -> Self:
        names = [change.name for change in self.changes]
        if len(set(names)) != len(names):
            raise ValueError("each policy value may be changed once")
        return self


class ConfirmBody(_Body):
    version: int = Field(ge=1)


class VersionBody(_Body):
    version: int = Field(ge=1)


class SraBody(_Body):
    version: int = Field(ge=1)
    accepted_by: str = Field(min_length=2, max_length=80)
    accepted_on: date
    sra_ref: str | None = Field(default=None, max_length=120)


class AssistantBody(_Body):
    model: str = Field(max_length=101)
    model_lite: str = Field(max_length=101)
    reserve_share: float = Field(ge=0.1, le=0.5)
    daily_limits: dict[str, int] = Field(default_factory=dict, max_length=8)


class KeyBody(TephraModel):
    """The model key; never stripped (a key is exact) and never echoed in an error."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(max_length=200)


class InviteBody(_Body):
    email: str = Field(max_length=254, pattern=EMAIL)
    role: HostedRole

    @field_validator("email", mode="before")
    @classmethod
    def _lower(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


class RoleBody(_Body):
    role: HostedRole


class TokenBody(_Body):
    token: str = Field(min_length=20, max_length=100)


class AcceptBody(_Body):
    token: str = Field(min_length=20, max_length=100)
    display_name: str = Field(min_length=2, max_length=32)


class JoinBody(_CredentialBody):
    token: str = Field(min_length=20, max_length=100)
    email: str = Field(max_length=254, pattern=EMAIL)
    password: str = Field(min_length=12, max_length=128)
    display_name: str = Field(min_length=2, max_length=32)
    acknowledge: Literal[True]


class EmailBody(_CredentialBody):
    email: str = Field(max_length=254, pattern=EMAIL)


class OperatorInviteBody(_CredentialBody):
    name: str = Field(min_length=2, max_length=32)
    email: str = Field(max_length=254, pattern=EMAIL)


class OperatorAcceptBody(_CredentialBody):
    token: str = Field(min_length=20, max_length=100)
    email: str = Field(max_length=254, pattern=EMAIL)
    password: str = Field(min_length=12, max_length=128)


class OperatorSignIn(_CredentialBody):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


class VerifyBody(_Body):
    version: int = Field(ge=1)
    note: str | None = Field(default=None, max_length=300)


class DeclineBody(_Body):
    version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=500)
