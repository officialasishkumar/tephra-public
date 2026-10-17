"""The storage contract implemented by SQLite (local) and Firestore + Cloud Storage (Cloud Run).

Documents are JSON-safe dicts, normally ``model.model_dump(mode="json")``. Timestamps are
fixed-width ISO strings, so ordering by a timestamp field is ordering in time.
"""

from collections.abc import Callable, Mapping, Sequence
from enum import StrEnum
from typing import Any, Literal, NamedTuple, Protocol, runtime_checkable

from tephra.models import AuditEntry, FeedHealth, FeedId

__all__ = [
    "BLOB_KEY_PATTERN",
    "Collection",
    "Store",
    "Where",
    "WhereOp",
    "escape_doc_id",
    "unescape_doc_id",
]

BLOB_KEY_PATTERN = r"^(frames|btd)/[A-Za-z0-9._-]{1,200}\.png$"
"""The only blob keys TEPHRA writes and the API serves."""


class Collection(StrEnum):
    """Collection names and their document ids (see MODULES.md for the model per collection)."""

    SIGMETS = "sigmets"  # source_id -> Sigmet
    VONAS = "vonas"  # source_id -> Vona
    VAAS = "vaas"  # source_id -> VaacAdvisory
    TAFS = "tafs"  # ICAO -> latest Taf
    METARS = "metars"  # ICAO -> latest Metar
    WINDS = "winds"  # volcano_id -> WindForecast
    FRAMES = "frames"  # source_id -> SatelliteFrame
    BTD = "btd"  # source_id -> BtdResult
    SITUATIONS = "situations"  # volcano_id -> latest Situation
    ASSESSMENTS = "assessments"  # assessment id -> PlumeAssessment
    CONES = "cones"  # volcano_id -> latest HazardCone
    PLANS = "plans"  # plan id -> PlannedAction
    ADVISORIES = "advisories"  # advisory id -> Advisory (compare-and-set on version)
    AI_FAILURES = "ai_failures"  # failure id -> AiFailure (no plan or draft; handled by hand)
    REROUTES = "reroutes"  # RerouteOption id -> RerouteOption
    SAT_READINGS = "sat_readings"  # reading id -> SatelliteReading
    NOTICES = "notices"  # notice id -> NoticeReading (Gemini read of a free-text notice)
    ASK_LOG = "ask_log"  # answer id -> AskAnswer
    RECOVERY = "recovery"  # recovery plan id -> RecoveryPlan
    MESSAGES = "messages"  # message id -> CrewPaxMessage (DRAFT -> APPROVED/EDITED/REJECTED)
    DOCS = "docs"  # doc id -> SraDraft | VarDraft | HandoverBrief
    BACKTEST = "backtest"  # "latest" -> BacktestScorecard
    DUTY = "duty"  # run id -> DutyRun
    CREW_REPORTS = "crew_reports"  # report id -> CrewReport (entered on the Desk)
    CONNECTIONS = "connections"  # connection id -> Connection (airline data pushed in)
    AIRLINES = "airlines"  # airline id -> AirlineRecord (private: the airline and dispatchers)
    AIRLINE_LOGINS = "airline_logins"  # login key -> AirlineLogin (credentials; never returned)
    OUTBOUND = "outbound"  # message id -> OutboundMessage
    AUDIT = "audit"  # entry id -> AuditEntry (append-only)
    FEED_STATE = "feed_state"  # FeedId value -> FeedHealth
    RUNTIME = "runtime"  # "state" -> core's bookkeeping: mode, replay choice, LIVE marks
    AI_BUDGET = "ai_budget"  # "<quota day>/<model id>" -> that model's calls on that day
    AI_WORK = "ai_work"  # work id -> AI work waiting for, or running in, the AI worker
    AI_ANSWERS = "ai_answers"  # answer key -> AiAnswer: a model's answer to a material question
    # Hosted airlines. Root namespace unless noted; an airline's own documents use every
    # collection above inside its namespace (see tephra.store.open_store).
    HOSTED_TENANTS = "hosted_tenants"  # ICAO -> TenantRecord (compare-and-set on version)
    HOSTED_MEMBERS = "hosted_members"  # "<ICAO>~<login key>" -> Member
    HOSTED_INVITES = "hosted_invites"  # sha256(token) -> Invite
    HOSTED_SLOTS = "hosted_slots"  # "site" -> SlotDoc (the airlines holding a place)
    HOSTED_METER = "hosted_meter"  # Pacific quota day -> MeterDay (store operations)
    OPERATORS = "operators"  # login key -> Operator (TEPHRA's own people)
    OPERATOR_INVITES = "operator_invites"  # sha256(token) -> OperatorInvite
    POLICY_VERSIONS = "policy_versions"  # "%06d" -> PolicyVersion (an airline's namespace)


WhereOp = Literal["==", "!=", "<", "<=", ">", ">=", "in"]


class Where(NamedTuple):
    """A filter on a top-level document field."""

    field: str
    op: WhereOp
    value: Any


@runtime_checkable
class Store(Protocol):
    """Async document store. ``collection`` is a :class:`Collection` value.

    ``doc_id`` may be any non-empty string up to 500 characters (source ids contain ``/``
    and ``:``); implementations escape it as their backend needs, e.g. with
    :func:`escape_doc_id`, and must return documents unchanged.
    """

    async def put(self, collection: str, doc_id: str, doc: Mapping[str, Any]) -> None:
        """Create or replace a document."""
        ...

    async def get(self, collection: str, doc_id: str) -> dict[str, Any] | None: ...

    async def delete(self, collection: str, doc_id: str) -> None:
        """Delete if present; deleting a missing document is not an error."""
        ...

    async def list_docs(
        self,
        collection: str,
        *,
        limit: int = 100,
        order_by: str | None = None,
        descending: bool = True,
    ) -> list[dict[str, Any]]: ...

    async def query(
        self,
        collection: str,
        where: Sequence[Where] = (),
        *,
        order_by: str | None = None,
        descending: bool = True,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """All filters are ANDed. Implementations may filter or sort in memory."""
        ...

    async def page(
        self,
        collection: str,
        *,
        field: str,
        before: Any | None,
        limit: int,
        descending: bool = True,
    ) -> list[dict[str, Any]]:
        """Up to ``limit`` documents ordered by ``field``, starting strictly past the cursor
        ``before`` in that order (below it when descending, above it when ascending; None
        starts at the end). Documents without ``field`` are never returned. Served by one
        single-field index, so it costs one read per document returned."""
        ...

    async def count(self, collection: str, where: Sequence[Where] = ()) -> int:
        """How many documents match (filters ANDed), counted without reading them where the
        backend can: a capacity check must not cost a read per document."""
        ...

    async def delete_some(self, collection: str, *, limit: int) -> int:
        """Delete up to ``limit`` documents of ``collection`` (any of them) and return how
        many went. Only the purge of a deleted airline's namespace uses it; it costs one read
        and one delete per document."""
        ...

    async def update(
        self,
        collection: str,
        doc_id: str,
        change: Callable[[dict[str, Any] | None], dict[str, Any]],
    ) -> dict[str, Any]:
        """Atomically replace a document with ``change(stored)`` and return what was written.

        ``stored`` is None when the document does not exist. ``change`` may run more than once
        (a Firestore transaction retries on contention), so it must not have side effects; an
        exception it raises aborts the update, writes nothing and propagates.
        """
        ...

    async def compare_and_set_advisory(
        self, advisory_id: str, expected_version: int, doc: Mapping[str, Any]
    ) -> bool:
        """Atomically write ``doc`` if the stored version equals ``expected_version``.

        ``expected_version == 0`` means "create; the advisory must not exist yet".
        ``doc["version"]`` must equal ``expected_version + 1``. Returns False on conflict.
        """
        ...

    async def append_audit(self, entry: AuditEntry) -> None:
        """Insert an audit entry; an existing id is never overwritten."""
        ...

    async def get_feed_state(self, feed: FeedId) -> FeedHealth | None: ...

    async def put_feed_state(self, state: FeedHealth) -> None: ...

    async def list_feed_states(self) -> list[FeedHealth]: ...

    async def put_blob(self, key: str, data: bytes, content_type: str) -> None:
        """Store a binary object; ``key`` must match :data:`BLOB_KEY_PATTERN`."""
        ...

    async def get_blob(self, key: str) -> tuple[bytes, str] | None:
        """Return ``(data, content_type)`` or None."""
        ...

    async def aclose(self) -> None: ...


def escape_doc_id(doc_id: str) -> str:
    """Make an id safe for Firestore (no ``/``, never ``.`` or ``..``), reversibly."""
    if not doc_id:
        raise ValueError("empty document id")
    return doc_id.replace("%", "%25").replace("/", "%2F").replace(".", "%2E")


def unescape_doc_id(escaped: str) -> str:
    return escaped.replace("%2E", ".").replace("%2F", "/").replace("%25", "%")
