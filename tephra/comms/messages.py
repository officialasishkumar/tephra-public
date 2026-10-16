"""Crew and passenger messages: model-written templates, code-filled facts, dispatcher decisions.

Gemini (structured output, Flash-Lite) writes one template per language with ``{PLACEHOLDERS}``
for every fact. It never sees a value: code fills the flight, route, times, delay, reason
and sources, so any digit left in the model's text is an invention and is rejected. A
template depends only on the kind of message, the status and the jurisdiction, so one call
serves every flight of a recovery plan that shares them.

A model that fails, or whose templates still fail the checks after one repair, gives
``AiUnavailable``: nothing is stored and no stand-in text is written. Approval, edit and
reject are compare-and-set on ``version``; an approved message goes only to the ``outbound``
collection.
"""

# Japanese text uses fullwidth punctuation on purpose.
# ruff: noqa: RUF001

import asyncio
import json
import re
import weakref
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from enum import StrEnum
from pathlib import Path
from typing import Any, Final, Literal, Protocol
from uuid import uuid4

from tephra.agents.answers import AiAnswers, Question, Reuse, prompt_version
from tephra.agents.llm import LlmBackend, LlmCall, LlmPart
from tephra.agents.validators import first_problems
from tephra.comms.models import (
    CrewPaxMessage,
    Language,
    MessageKind,
    MessageStatus,
    MessageText,
    RecoveryChange,
    RecoveryClosure,
    RecoveryInput,
)
from tephra.config import Airline
from tephra.desk import audit
from tephra.desk.approvals import SYSTEM_ACTOR
from tephra.feeds.airports import AirportCatalogue
from tephra.models import (
    ActionKind,
    Advisory,
    AdvisoryStatus,
    Airport,
    AuditAction,
    OperatorPolicy,
    OutboundMessage,
    RunMode,
    SseEvent,
    TephraModel,
    TraceActor,
    TraceEvent,
    TraceStage,
)
from tephra.recovery.models import RecoveryActionKind, RecoveryPlan
from tephra.store.base import Collection, Store, Where
from tephra.util import timeutil
from tephra.util.events import EventBus
from tephra.util.hashing import stable_id

__all__ = [
    "AI_UNAVAILABLE",
    "AiUnavailable",
    "CommsError",
    "CommsRuntime",
    "EditRejected",
    "InvalidTransition",
    "MessageNotFound",
    "SourceNotApproved",
    "SourceNotFound",
    "SourceUnusable",
    "VersionConflict",
    "advisory_action",
    "approve",
    "decision_lock",
    "draft_messages",
    "edit_and_approve",
    "get_message",
    "languages_for",
    "list_messages",
    "recovery_input",
    "reject",
    "template_problems",
    "templates_question",
    "text_part",
]

PROMPT_PATH: Final[Path] = (
    Path(__file__).resolve().parent.parent / "agents" / "prompts" / "messages.md"
)
AI_UNAVAILABLE: Final = "AI UNAVAILABLE"
MAX_TEMPLATE_CHARS: Final = 1500
MAX_BODY_CHARS: Final = 3000
MIN_REJECT_REASON_CHARS: Final = 3
REPAIR_ECHO_CHARS: Final = 2000
"""How much of an unreadable answer the repair prompt quotes back."""
PM89_CARD_REFUND_DAYS: Final = 30
"""PM 89/2015 Pasal 10: card purchases are refunded within 30 calendar days (research/18d 4.1)."""
_QUEUED: Final = frozenset({MessageStatus.APPROVED, MessageStatus.EDITED})
_URL_OR_ADDRESS: Final = re.compile(r"https?:|www\.|@", re.IGNORECASE)
_PLACEHOLDER: Final = re.compile(r"\{([A-Z][A-Z_]*)\}")
_BRACE: Final = re.compile(r"[{}]")
_CODE_WORD: Final = re.compile(r"(?<![A-Za-z0-9])[A-Z]{3,4}(?![A-Za-z0-9])")
_KANA: Final = re.compile("[\\u3040-\\u30ff]")
_CJK: Final = re.compile("[\\u3040-\\u30ff\\u3400-\\u4dbf\\u4e00-\\u9fff\\uff00-\\uffef]")


# --- errors -----------------------------------------------------------------------------


class CommsError(Exception):
    """Base of every error this module raises on purpose."""


class AiUnavailable(CommsError):
    """The model did not give usable text. Nothing was stored and nothing was substituted."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"{AI_UNAVAILABLE}: {reason}")
        self.reason = reason


class SourceNotFound(CommsError): ...


class SourceNotApproved(CommsError): ...


class SourceUnusable(CommsError):
    """The approved advisory or plan lacks a fact a message must state."""


class MessageNotFound(CommsError): ...


class InvalidTransition(CommsError): ...


class VersionConflict(CommsError):
    def __init__(self, current: CrewPaxMessage) -> None:
        super().__init__(f"message {current.id} is at version {current.version}")
        self.current = current


class EditRejected(CommsError):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


class CommsRuntime(Protocol):
    """The parts of ``tephra.pipeline.Runtime`` the messages use."""

    @property
    def store(self) -> Store: ...

    @property
    def bus(self) -> EventBus: ...

    @property
    def llm(self) -> LlmBackend: ...

    @property
    def answers(self) -> AiAnswers | None: ...

    @property
    def airports(self) -> AirportCatalogue: ...

    @property
    def policy(self) -> OperatorPolicy: ...

    @property
    def mode(self) -> RunMode: ...

    @property
    def airline(self) -> Airline:
        """Who the drafts speak for: the demo's fictional airline or the airline's own."""
        ...

    def trace(
        self,
        stage: TraceStage,
        actor: TraceActor,
        message: str,
        *,
        level: Literal["info", "warn", "error"] = "info",
        volcano_id: str | None = None,
        flight_id: str | None = None,
        detail: Mapping[str, Any] | None = None,
    ) -> TraceEvent: ...


# --- route facts: jurisdiction, languages, local time -----------------------------------


class Jurisdiction(StrEnum):
    ID = "ID"
    JP = "JP"
    OTHER = "OTHER"


def jurisdiction_of(origin: Airport, dest: Airport) -> Jurisdiction:
    countries = {origin.country, dest.country}
    if "Indonesia" in countries:
        return Jurisdiction.ID
    return Jurisdiction.JP if "Japan" in countries else Jurisdiction.OTHER


def languages_for(origin: Airport, dest: Airport) -> list[Language]:
    """Indonesia -> Bahasa Indonesia, Japan -> Japanese, and always English."""
    countries = {origin.country, dest.country}
    languages: list[Language] = []
    if "Indonesia" in countries:
        languages.append("id")
    if "Japan" in countries:
        languages.append("ja")
    return [*languages, "en"]


_LANGUAGE_ORDER: Final[tuple[Language, ...]] = ("id", "ja", "en")


def _merge_languages(groups: Sequence[Sequence[Language]]) -> tuple[Language, ...]:
    present = {language for group in groups for language in group}
    return tuple(language for language in _LANGUAGE_ORDER if language in present)


def local_zone(airport: Airport) -> tzinfo:
    """Fixed-offset local zone (none of these observes daylight time), named as people say it.

    Indonesia has three zones split by longitude: WIB west of 114.6E, WITA to 126E, WIT east.
    A country TEPHRA has no zone for is shown in UTC, plainly labelled.
    """
    match airport.country:
        case "Indonesia" if airport.lon < 114.6:
            return timezone(timedelta(hours=7), "WIB")
        case "Indonesia" if airport.lon < 126:
            return timezone(timedelta(hours=8), "WITA")
        case "Indonesia":
            return timezone(timedelta(hours=9), "WIT")
        case "Japan":
            return timezone(timedelta(hours=9), "JST")
        case "Philippines":
            return timezone(timedelta(hours=8), "PHT")
        case "Singapore":
            return timezone(timedelta(hours=8), "SGT")
        case _:
            return UTC


def local_text(at: datetime, airport: Airport) -> str:
    zone = local_zone(airport)
    return f"{at.astimezone(zone):%Y-%m-%d %H:%M} {zone.tzname(None)}"


# --- language packs (code-written words) ------------------------------------------------


@dataclass(frozen=True)
class Pack:
    cancelled: str
    delayed: str
    contact: str
    closure: str
    """``{airport} {sources} {start} {end}`` fields."""
    closure_open: str
    """The same with no published end: ``{airport} {sources} {start}`` fields."""
    next_open: str
    """In place of a time when the next update waits for the closure's end to be published."""
    change_cancel: str
    change_delay: str
    change_swap: str
    basis_pm89: str
    basis_carriage: str


PACKS: Final[dict[Language, Pack]] = {
    "en": Pack(
        cancelled="cancelled",
        delayed="delayed",
        contact="the Ring of Fire Air contact centre (fictional, no real number)",
        closure="volcanic ash closure of {airport} ({sources}) from {start} to {end}",
        closure_open=(
            "volcanic ash closure of {airport} ({sources}) from {start}, end not yet published"
        ),
        next_open="the time the end of the closure is published",
        change_cancel="{flight} {route}: CANCELLED",
        change_delay="{flight} {route}: DELAYED {delay_min} MIN, NEW DEPARTURE {new}",
        change_swap="{flight} {route}: MOVES TO AIRCRAFT {tail}",
        basis_pm89="PM 89/2015 Article 6(2)",
        basis_carriage="the Ring of Fire Air conditions of carriage (fictional)",
    ),
    "id": Pack(
        cancelled="dibatalkan",
        delayed="tertunda",
        contact="pusat kontak Ring of Fire Air (fiktif, tanpa nomor sebenarnya)",
        closure="penutupan {airport} akibat abu vulkanik ({sources}) dari {start} sampai {end}",
        closure_open=(
            "penutupan {airport} akibat abu vulkanik ({sources}) sejak {start},"
            " waktu berakhir belum diumumkan"
        ),
        next_open="saat waktu berakhirnya penutupan diumumkan",
        change_cancel="{flight} {route}: dibatalkan",
        change_delay="{flight} {route}: tertunda {delay_min} menit, keberangkatan baru {new}",
        change_swap="{flight} {route}: dipindahkan ke pesawat {tail}",
        basis_pm89="PM 89 Tahun 2015 Pasal 6 ayat (2)",
        basis_carriage="ketentuan pengangkutan Ring of Fire Air (fiktif)",
    ),
    "ja": Pack(
        cancelled="欠航",
        delayed="遅延",
        contact="Ring of Fire Airのお客様窓口（架空、実在の番号なし）",
        closure="火山灰による{airport}の閉鎖（{sources}）：{start}から{end}まで",
        closure_open="火山灰による{airport}の閉鎖（{sources}）：{start}から、終了時刻は未発表",
        next_open="閉鎖の終了時刻の発表時",
        change_cancel="{flight} {route}：欠航",
        change_delay="{flight} {route}：{delay_min}分遅延、新しい出発予定 {new}",
        change_swap="{flight} {route}：機材を{tail}に変更",
        basis_pm89="インドネシア運輸大臣規則PM 89/2015第6条2項",
        basis_carriage="Ring of Fire Airの運送約款（架空）",
    ),
}

ENCOUNTER_NOTE: Final = (
    "ENCOUNTER INDICATORS LISTED IN ICAO DOC 9974 GUIDANCE: ACRID OR SULPHUR SMELL, HAZE IN THE"
    " CABIN, ENGINE SURGING OR FLAMEOUT, WHITE GLOW AT THE ENGINE INLET, AIRSPEED FLUCTUATION,"
    " PRESSURISATION CHANGES, ST ELMO'S FIRE. WEATHER RADAR CANNOT DETECT ASH. ANY ONE INDICATOR"
    " IS ENOUGH TO ACT. VERIFY EVERY PROCEDURE AGAINST THE OPERATOR QRH."
)
REPORT_NOTE: Final = (
    "REPORT ANY ENCOUNTER: VAR, AML ENTRY AND A MANDATORY OCCURRENCE REPORT WHERE REQUIRED."
)


# --- placeholders and template checks ---------------------------------------------------

MEANINGS: Final[dict[str, str]] = {
    "FLIGHT": "the flight number",
    "ROUTE": "origin and destination airports",
    "STATUS": "the status word (cancelled or delayed)",
    "REASON_SOURCE": "why, in plain words, with the official products it rests on and their times",
    "ORIG_DEP_LOCAL": "the scheduled departure date and local time",
    "NEW_DEP_LOCAL": "the new departure date and local time",
    "DELAY_MIN": "minutes of delay (a number)",
    "NEXT_UPDATE_LOCAL": "the date and local time of the next update",
    "CONTACT": "the contact channel",
    "NOT_OWED_BASIS": "the rule or contract term under which no cash compensation is owed",
    "CARD_REFUND_DAYS": "days within which card purchases are refunded (a number)",
    "TAIL": "the aircraft registration",
    "CHANGES": "the list of changes, one per line",
    "VOLCANO": "the volcano",
    "ACTION": "the action TEPHRA proposes, as dispatch wrote it",
    "ENTRY": "when the flight enters the hazard area, or that it is inside",
    "FUEL": "the fuel and time cost line",
    "ENCOUNTER_NOTE": "the encounter indicators and the QRH reminder",
    "REPORT_NOTE": "the reporting reminders",
}


@dataclass(frozen=True)
class TemplateSpec:
    kind: MessageKind
    languages: tuple[Language, ...]
    required: tuple[str, ...]
    optional: tuple[str, ...] = ()
    status: str | None = None
    jurisdiction: Jurisdiction | None = None

    @property
    def allowed(self) -> frozenset[str]:
        return frozenset((*self.required, *self.optional))


def passenger_spec(
    status: Literal["CANCELLED", "DELAYED"],
    jurisdiction: Jurisdiction,
    languages: tuple[Language, ...],
) -> TemplateSpec:
    """The content list of research/18d 7.5: status, reason with sources, new time or next
    update, options (the model writes them), assistance, and what is not owed."""
    required = ["FLIGHT", "ROUTE", "STATUS", "REASON_SOURCE", "ORIG_DEP_LOCAL"]
    required += ["NEW_DEP_LOCAL", "DELAY_MIN"] if status == "DELAYED" else ["NEXT_UPDATE_LOCAL"]
    required += ["CONTACT", "NOT_OWED_BASIS"]
    if jurisdiction is Jurisdiction.ID:
        required.append("CARD_REFUND_DAYS")
    return TemplateSpec(
        MessageKind.PASSENGER_NOTICE,
        languages,
        tuple(required),
        status=status,
        jurisdiction=jurisdiction,
    )


def crew_notice_spec(languages: tuple[Language, ...]) -> TemplateSpec:
    return TemplateSpec(
        MessageKind.CREW_NOTICE,
        languages,
        ("TAIL", "CHANGES", "REASON_SOURCE"),
        optional=("CONTACT",),
    )


def crew_briefing_spec() -> TemplateSpec:
    return TemplateSpec(
        MessageKind.CREW_BRIEFING,
        ("en",),
        ("FLIGHT", "VOLCANO", "ACTION", "ENTRY", "REASON_SOURCE", "ENCOUNTER_NOTE", "REPORT_NOTE"),
        optional=("FUEL",),
    )


class TemplateText(TephraModel):
    language: Language
    text: str


class TemplateSet(TephraModel):
    """The model's answer: one template per requested language."""

    texts: list[TemplateText]


def template_problems(
    templates: TemplateSet, spec: TemplateSpec, *, known_codes: frozenset[str]
) -> list[str]:
    """Upper-case, code-written problems; empty means the templates are accepted."""
    returned = [text.language for text in templates.texts]
    if sorted(returned) != sorted(spec.languages):
        wanted = ", ".join(spec.languages)
        return [f"ANSWER MUST HAVE EXACTLY ONE TEXT PER LANGUAGE: {wanted}"]
    problems: list[str] = []
    for text in templates.texts:
        for problem in _text_problems(text.text, text.language, spec, known_codes):
            problems.append(f"{text.language.upper()}: {problem}")
    return problems


def _text_problems(
    text: str, language: Language, spec: TemplateSpec, known_codes: frozenset[str]
) -> list[str]:
    if not text.strip():
        return ["TEXT IS EMPTY"]
    problems: list[str] = []
    if len(text) > MAX_TEMPLATE_CHARS:
        problems.append(f"TEXT LONGER THAN {MAX_TEMPLATE_CHARS} CHARACTERS")
    used = _PLACEHOLDER.findall(text)
    stripped = _PLACEHOLDER.sub("", text)
    if _BRACE.search(stripped):
        problems.append("MALFORMED PLACEHOLDER: USE {UPPER_CASE_NAME} ONLY")
    unknown = sorted(set(used) - spec.allowed)
    if unknown:
        problems.append(f"UNKNOWN PLACEHOLDERS: {', '.join(unknown)}")
    missing = [name for name in spec.required if name not in used]
    if missing:
        problems.append(f"MISSING REQUIRED PLACEHOLDERS: {', '.join(missing)}")
    digits = sorted({char for char in stripped if char.isdigit()})
    if digits:
        problems.append(
            f"DIGITS OUTSIDE PLACEHOLDERS ({', '.join(digits)}): EVERY NUMBER AND TIME COMES"
            " FROM A PLACEHOLDER"
        )
    if _URL_OR_ADDRESS.search(stripped):
        problems.append("NO WEB ADDRESSES OR E-MAIL ADDRESSES: CONTACT IS A PLACEHOLDER")
    codes = sorted({word for word in _CODE_WORD.findall(stripped) if word in known_codes})
    if codes:
        problems.append(f"AIRPORT CODES ({', '.join(codes)}) COME FROM PLACEHOLDERS")
    if language == "ja" and not _KANA.search(stripped):
        problems.append("TEXT IS NOT JAPANESE")
    if language != "ja" and _CJK.search(stripped):
        problems.append("TEXT MUST NOT CONTAIN JAPANESE OR CHINESE CHARACTERS")
    return problems


def fill(template: str, values: Mapping[str, str]) -> str:
    return _PLACEHOLDER.sub(lambda match: values[match.group(1)], template)


# --- stub templates (TEPHRA_LLM=stub and tests only; labelled NO MODEL downstream) -------

_STUB: Final[dict[Language, dict[str, str]]] = {
    "en": {
        "intro": "Flight {FLIGHT} ({ROUTE}) is {STATUS}. Reason: {REASON_SOURCE}.",
        "orig_new": (
            "Original departure {ORIG_DEP_LOCAL}; new departure {NEW_DEP_LOCAL}"
            " ({DELAY_MIN} minutes later)."
        ),
        "orig": "Original departure {ORIG_DEP_LOCAL}.",
        "next": "Next update by {NEXT_UPDATE_LOCAL}.",
        "refund_days": (
            "You may rebook at no extra charge or take a full refund to the original payment"
            " method; cash refunds are immediate and card refunds are made within"
            " {CARD_REFUND_DAYS} calendar days."
        ),
        "refund": (
            "You may rebook at no extra charge or take a full refund to the original payment"
            " method."
        ),
        "help": "Our staff at the airport will assist you.",
        "no_travel": "Please do not travel to the airport for this flight.",
        "not_owed": "No cash compensation is owed under {NOT_OWED_BASIS}.",
        "contact": "Contact: {CONTACT}.",
        "crew_notice": (
            "Crew notice for aircraft {TAIL}. Changes:{CHANGES}\nReason: {REASON_SOURCE}."
        ),
        "briefing": (
            "Crew briefing for {FLIGHT}: volcanic ash from {VOLCANO}. {ENTRY}. Company advice:"
            " {ACTION}. Source: {REASON_SOURCE}. {ENCOUNTER_NOTE} {REPORT_NOTE}"
        ),
    },
    "id": {
        "intro": "Penerbangan {FLIGHT} ({ROUTE}) {STATUS}. Alasan: {REASON_SOURCE}.",
        "orig_new": (
            "Jadwal keberangkatan semula {ORIG_DEP_LOCAL}; jadwal baru {NEW_DEP_LOCAL}"
            " (tertunda {DELAY_MIN} menit)."
        ),
        "orig": "Jadwal keberangkatan semula {ORIG_DEP_LOCAL}.",
        "next": "Informasi terbaru kami sampaikan paling lambat {NEXT_UPDATE_LOCAL}.",
        "refund_days": (
            "Anda dapat mengubah jadwal tanpa biaya tambahan atau meminta pengembalian dana"
            " penuh ke metode pembayaran semula; pengembalian tunai dilakukan langsung dan"
            " pengembalian ke kartu dalam {CARD_REFUND_DAYS} hari kalender."
        ),
        "refund": (
            "Anda dapat mengubah jadwal tanpa biaya tambahan atau meminta pengembalian dana"
            " penuh ke metode pembayaran semula."
        ),
        "help": "Petugas kami di bandara siap membantu Anda.",
        "no_travel": "Mohon tidak datang ke bandara untuk penerbangan ini.",
        "not_owed": "Kompensasi tunai tidak berlaku berdasarkan {NOT_OWED_BASIS}.",
        "contact": "Hubungi {CONTACT}.",
        "crew_notice": (
            "Pemberitahuan kru untuk pesawat {TAIL}. Perubahan:{CHANGES}\nAlasan: {REASON_SOURCE}."
        ),
    },
    "ja": {
        "intro": "{FLIGHT}便（{ROUTE}）は{STATUS}となりました。理由：{REASON_SOURCE}。",
        "orig_new": (
            "当初の出発予定は{ORIG_DEP_LOCAL}、新しい出発予定は{NEW_DEP_LOCAL}"
            "（{DELAY_MIN}分遅れ）です。"
        ),
        "orig": "当初の出発予定は{ORIG_DEP_LOCAL}でした。",
        "next": "次回のご案内は{NEXT_UPDATE_LOCAL}までに行います。",
        "refund_days": (
            "手数料なしでの振替、または元のお支払い方法への全額払い戻しをお選びいただけます"
            "（カードへの払い戻しはカレンダー日で{CARD_REFUND_DAYS}日以内）。"
        ),
        "refund": (
            "手数料なしでの振替、または元のお支払い方法への全額払い戻しをお選びいただけます。"
        ),
        "help": "空港では係員がご案内します。",
        "no_travel": "この便のために空港へお越しにならないようお願いいたします。",
        "not_owed": "{NOT_OWED_BASIS}に基づき、現金補償の対象とはなりません。",
        "contact": "お問い合わせ：{CONTACT}。",
        "crew_notice": "機材{TAIL}の乗務員への通知。変更内容：{CHANGES}\n理由：{REASON_SOURCE}。",
    },
}


def stub_templates(spec: TemplateSpec) -> TemplateSet:
    return TemplateSet(
        texts=[TemplateText(language=lang, text=_stub_text(spec, lang)) for lang in spec.languages]
    )


def _stub_text(spec: TemplateSpec, language: Language) -> str:
    words = _STUB[language]
    match spec.kind:
        case MessageKind.CREW_BRIEFING:
            fuel = " Cost: {FUEL}." if "FUEL" in spec.allowed else ""
            return words["briefing"] + fuel
        case MessageKind.CREW_NOTICE:
            return words["crew_notice"]
        case MessageKind.PASSENGER_NOTICE:
            refund = (
                words["refund_days"] if "CARD_REFUND_DAYS" in spec.required else words["refund"]
            )
            if spec.status == "DELAYED":
                parts = [words["intro"], words["orig_new"], refund, words["help"]]
            else:
                parts = [words["intro"], words["orig"], words["next"], refund, words["no_travel"]]
            return " ".join([*parts, words["not_owed"], words["contact"]])


# --- asking the model -------------------------------------------------------------------


@dataclass(frozen=True)
class Templates:
    """What one template call produced, and who produced it."""

    by_language: dict[Language, str]
    backend: Literal["gemini", "stub"]
    model_id: str
    prompt_hash: str


def _facts(spec: TemplateSpec, airline: Airline) -> dict[str, Any]:
    return {
        # "Ring of Fire Air (fictional)" in the demo; an airline's own TEPHRA: its own name
        "airline": airline.label,
        "message": spec.kind.value,
        "status": spec.status,
        "jurisdiction": spec.jurisdiction.value if spec.jurisdiction is not None else None,
        "languages": list(spec.languages),
        "required_placeholders": {name: MEANINGS[name] for name in spec.required},
        "optional_placeholders": {name: MEANINGS[name] for name in spec.optional},
    }


def text_part(text: str, label: str) -> LlmPart:
    return LlmPart(kind="text", text=text, data=None, mime_type=None, label=label)


def _repair_text(
    answer: TemplateSet | None, call: LlmCall, problems: Sequence[str], spec: TemplateSpec
) -> str:
    listed = "\n".join(f"- {problem}" for problem in first_problems(problems))
    previous = (
        json.dumps(answer.model_dump(mode="json"), ensure_ascii=False, indent=1)
        if answer is not None
        else (call.raw_text or "")[:REPAIR_ECHO_CHARS]
    )
    return (
        f"Code checks rejected your answer:\n{listed}\nYour answer was:\n{previous}\n"
        f"Write the templates again for {', '.join(spec.languages)}, fixing every problem."
    )


def templates_question(spec: TemplateSpec, airline: Airline) -> Question:
    """What is material to a set of templates: everything the model is given, which is the
    template spec (kind, status, jurisdiction, languages and placeholders), never a flight's
    or an advisory's own values (code fills those in)."""
    system = PROMPT_PATH.read_text(encoding="utf-8")
    return Question("messages", {"prompt": prompt_version(system), "spec": _facts(spec, airline)})


async def request_templates(runtime: CommsRuntime, spec: TemplateSpec) -> Templates:
    """One lite call (and at most one repair). Raises ``AiUnavailable``; never substitutes.
    The same model's templates for the same spec are used when they pass the checks now; new
    ones that pass are kept."""
    system = PROMPT_PATH.read_text(encoding="utf-8")
    parts = [
        text_part(json.dumps(_facts(spec, runtime.airline), ensure_ascii=False, indent=1), "facts")
    ]
    known = _known_codes(runtime.airports)
    answers = runtime.answers
    reuse = None if answers is None else answers.reuse(templates_question(spec, runtime.airline))
    if reuse is not None and (held := await _known_templates(reuse, runtime, spec, known)):
        return held

    async def ask(extra: Sequence[LlmPart]) -> tuple[TemplateSet | None, LlmCall]:
        return await runtime.llm.structured(
            tier="lite",
            system=system,
            parts=[*parts, *extra],
            schema=TemplateSet,
            stub=lambda: stub_templates(spec),
        )

    answer, call = await ask([])
    first_hash = call.prompt_hash
    problems = _answer_problems(answer, call, spec, known)
    if problems and (answer is not None or call.raw_text) and runtime.llm.name != "stub":
        repair = text_part(_repair_text(answer, call, problems, spec), "repair")
        answer, call = await ask([repair])
        problems = _answer_problems(answer, call, spec, known)
    if answer is None or problems:
        raise AiUnavailable(_failure_reason(answer, call, problems))
    if reuse is not None:
        await reuse.keep(
            call.model_id,
            answer.model_dump(mode="json"),
            prompt_hash=first_hash,
            answered_at=timeutil.now(),
        )
    return Templates(
        by_language={text.language: text.text.strip() for text in answer.texts},
        backend=runtime.llm.name,
        model_id=call.model_id,
        prompt_hash=first_hash,
    )


async def _known_templates(
    reuse: Reuse, runtime: CommsRuntime, spec: TemplateSpec, known: frozenset[str]
) -> Templates | None:
    found = await reuse.recall_as(runtime.llm.model_id("lite"), TemplateSet)
    if found is None:
        return None
    answer, held = found
    problems = template_problems(held, spec, known_codes=known)
    if problems:
        reuse.rejected(problems)
        return None
    return Templates(
        by_language={text.language: text.text.strip() for text in held.texts},
        backend=runtime.llm.name,
        model_id=answer.model_id,
        prompt_hash=answer.prompt_hash,
    )


def _answer_problems(
    answer: TemplateSet | None, call: LlmCall, spec: TemplateSpec, known: frozenset[str]
) -> list[str]:
    if answer is None:
        return [f"NO ANSWER RETURNED ({call.error or 'unknown error'})"]
    return template_problems(answer, spec, known_codes=known)


def _failure_reason(answer: TemplateSet | None, call: LlmCall, problems: Sequence[str]) -> str:
    if answer is None:
        return f"NO ANSWER RETURNED ({call.error or 'unknown error'})"
    return f"TEXT FAILED CHECKS AFTER REPAIR: {'; '.join(first_problems(problems, 3))}"


def _known_codes(airports: AirportCatalogue) -> frozenset[str]:
    codes = {airport.icao for airport in airports.all()}
    codes.update(airport.iata for airport in airports.all() if airport.iata)
    return frozenset(codes)


# --- what a message is about ------------------------------------------------------------


@dataclass
class Target:
    """One message to make: who it is for, its template spec and the filled values."""

    kind: MessageKind
    key: str
    spec: TemplateSpec
    values: dict[Language, dict[str, str]]
    flight_no: str | None = None
    tail: str | None = None
    route: str | None = None


def _airport(airports: AirportCatalogue, icao: str) -> Airport:
    airport = airports.get(icao)
    if airport is None:
        raise SourceUnusable(f"airport {icao} is not in the catalogue")
    return airport


def _airport_label(airport: Airport) -> str:
    return f"{airport.name} ({airport.iata or airport.icao})"


def _route_text(origin: Airport, dest: Airport) -> str:
    return f"{_airport_label(origin)} → {_airport_label(dest)}"


def _closure_text(closure: RecoveryClosure, airports: AirportCatalogue, pack: Pack) -> str:
    airport = _airport(airports, closure.icao)
    return (pack.closure_open if closure.open_ended else pack.closure).format(
        airport=_airport_label(airport),
        sources=", ".join(closure.source_ids) or "-",
        start=local_text(closure.start, airport),
        end=local_text(closure.end, airport),
    )


def _relevant_closures(
    closures: Sequence[RecoveryClosure], icaos: set[str]
) -> list[RecoveryClosure]:
    """Closures at the flight's own airports; with none, every closure that drove the plan."""
    own = [closure for closure in closures if closure.icao in icaos]
    return own or list(closures)


def _reason_text(
    closures: Sequence[RecoveryClosure], airports: AirportCatalogue, language: Language
) -> str:
    return "; ".join(_closure_text(closure, airports, PACKS[language]) for closure in closures)


def _pax_values(
    change: RecoveryChange,
    *,
    origin: Airport,
    dest: Airport,
    closures: Sequence[RecoveryClosure],
    airports: AirportCatalogue,
    jurisdiction: Jurisdiction,
    language: Language,
) -> dict[str, str]:
    pack = PACKS[language]
    delayed = change.kind == "DELAY"
    new_std = change.std + timedelta(minutes=change.delay_min)
    next_update = (
        pack.next_open
        if any(closure.open_ended for closure in closures)
        else local_text(max(closure.end for closure in closures), origin)
    )
    basis = pack.basis_pm89 if jurisdiction is Jurisdiction.ID else pack.basis_carriage
    return {
        "FLIGHT": change.flight_no,
        "ROUTE": _route_text(origin, dest),
        "STATUS": pack.delayed if delayed else pack.cancelled,
        "REASON_SOURCE": _reason_text(closures, airports, language),
        "ORIG_DEP_LOCAL": local_text(change.std, origin),
        "NEW_DEP_LOCAL": local_text(new_std, origin),
        "DELAY_MIN": str(change.delay_min),
        "NEXT_UPDATE_LOCAL": next_update,
        "CONTACT": pack.contact,
        "NOT_OWED_BASIS": basis,
        "CARD_REFUND_DAYS": str(PM89_CARD_REFUND_DAYS),
    }


def _change_line(
    change: RecoveryChange, *, origin: Airport, dest: Airport, language: Language
) -> str:
    pack = PACKS[language]
    route = _route_text(origin, dest)
    match change.kind:
        case "CANCEL":
            return pack.change_cancel.format(flight=change.flight_key, route=route)
        case "DELAY":
            new_std = change.std + timedelta(minutes=change.delay_min)
            return pack.change_delay.format(
                flight=change.flight_key,
                route=route,
                delay_min=change.delay_min,
                new=local_text(new_std, origin),
            )
        case "SWAP":
            return pack.change_swap.format(
                flight=change.flight_key, route=route, tail=change.new_tail or "-"
            )


def passenger_targets(
    plan: RecoveryInput, airports: AirportCatalogue, policy: OperatorPolicy
) -> list[Target]:
    """A cancellation always gets a passenger notice; a delay only from the policy's minimum
    (PM 89/2015 category 1 starts at 30 minutes); a swap changes nothing a passenger sees."""
    min_delay = policy.recovery.pax_notice_min_delay_min.value
    targets: list[Target] = []
    for change in sorted(plan.changes, key=lambda c: (c.std, c.flight_key)):
        if change.kind == "SWAP" or (change.kind == "DELAY" and change.delay_min < min_delay):
            continue
        origin = _airport(airports, change.origin_icao)
        dest = _airport(airports, change.dest_icao)
        closures = _relevant_closures(plan.closures, {origin.icao, dest.icao})
        if not closures:
            raise SourceUnusable(f"recovery plan {plan.id} lists no closure to give as the reason")
        languages = tuple(languages_for(origin, dest))
        jurisdiction = jurisdiction_of(origin, dest)
        status: Literal["CANCELLED", "DELAYED"] = (
            "DELAYED" if change.kind == "DELAY" else "CANCELLED"
        )
        targets.append(
            Target(
                kind=MessageKind.PASSENGER_NOTICE,
                key=stable_id("MSG", plan.id, MessageKind.PASSENGER_NOTICE, change.flight_key),
                spec=passenger_spec(status, jurisdiction, languages),
                values={
                    language: _pax_values(
                        change,
                        origin=origin,
                        dest=dest,
                        closures=closures,
                        airports=airports,
                        jurisdiction=jurisdiction,
                        language=language,
                    )
                    for language in languages
                },
                flight_no=change.flight_key,
                route=_route_text(origin, dest),
            )
        )
    return targets


def crew_notice_targets(plan: RecoveryInput, airports: AirportCatalogue) -> list[Target]:
    """One notice per aircraft the plan touches: the tail a flight leaves and the one it joins."""
    by_tail: dict[str, list[RecoveryChange]] = {}
    for change in sorted(plan.changes, key=lambda c: (c.std, c.flight_key)):
        for tail in dict.fromkeys([change.tail, change.new_tail or change.tail]):
            by_tail.setdefault(tail, []).append(change)
    targets: list[Target] = []
    for tail, changes in sorted(by_tail.items()):
        legs = [
            (change, _airport(airports, change.origin_icao), _airport(airports, change.dest_icao))
            for change in changes
        ]
        icaos = {airport.icao for _, origin, dest in legs for airport in (origin, dest)}
        closures = _relevant_closures(plan.closures, icaos)
        if not closures:
            raise SourceUnusable(f"recovery plan {plan.id} lists no closure to give as the reason")
        languages = _merge_languages([languages_for(origin, dest) for _, origin, dest in legs])
        values: dict[Language, dict[str, str]] = {}
        for language in languages:
            lines = [
                f"- {_change_line(change, origin=origin, dest=dest, language=language)}"
                for change, origin, dest in legs
            ]
            values[language] = {
                "TAIL": tail,
                "CHANGES": "\n" + "\n".join(lines),
                "REASON_SOURCE": _reason_text(closures, airports, language),
                "CONTACT": PACKS[language].contact,
            }
        targets.append(
            Target(
                kind=MessageKind.CREW_NOTICE,
                key=stable_id("MSG", plan.id, MessageKind.CREW_NOTICE, tail),
                spec=crew_notice_spec(languages),
                values=values,
                tail=tail,
            )
        )
    return targets


def advisory_action(advisory: Advisory) -> str:
    match advisory.action:
        case ActionKind.CHANGE_LEVEL:
            return (
                f"CHANGE LEVEL FL{advisory.change_level_fl_min or 0:03d}"
                f"-FL{advisory.change_level_fl_max or 0:03d}"
            )
        case ActionKind.HOLD:
            return f"HOLD FL{advisory.hold_fl or 0:03d}"
        case ActionKind.DIVERT:
            return f"DIVERT {advisory.alternate_icao}"
        case ActionKind.REROUTE if advisory.reroute is not None and advisory.reroute.route_string:
            return f"REROUTE {advisory.reroute.route_string}"
        case _:
            return advisory.action.value


def _advisory_sources(advisory: Advisory) -> str:
    if not advisory.sources:
        return "TEPHRA ESTIMATE, NO OFFICIAL PRODUCT LISTED"
    return "; ".join(
        f"{source.source_id} ISSUED "
        f"{timeutil.ddhhmmz(source.issued_at) if source.issued_at is not None else 'N/A'}"
        for source in advisory.sources
    )


def briefing_target(advisory: Advisory) -> Target:
    entry = (
        "INSIDE THE HAZARD AREA NOW"
        if advisory.inside_now
        else f"ENTRY IN {advisory.minutes_to_entry} MIN IF TRACK AND LEVEL ARE HELD"
    )
    values = {
        "FLIGHT": advisory.callsign or advisory.proxy_flight,
        "VOLCANO": advisory.volcano_name.upper(),
        "ACTION": advisory_action(advisory),
        "ENTRY": entry,
        "REASON_SOURCE": _advisory_sources(advisory),
        "ENCOUNTER_NOTE": ENCOUNTER_NOTE,
        "REPORT_NOTE": REPORT_NOTE,
        "FUEL": advisory.cost_note,
    }
    return Target(
        kind=MessageKind.CREW_BRIEFING,
        key=stable_id("MSG", advisory.id, advisory.version, MessageKind.CREW_BRIEFING),
        spec=crew_briefing_spec(),
        values={"en": values},
        flight_no=advisory.proxy_flight,
    )


# --- recovery plans ------------------------------------------------------------


def recovery_input(doc: Mapping[str, Any]) -> RecoveryInput:
    """Read a stored recovery plan (``Collection.RECOVERY``) into what messages need.

    The flights are the chosen scenario's changes. The reason is the closures as forecast
    from the official products, not the scenario's extended ones: the extension is a planning
    assumption, and a passenger is told what the products say.
    """
    plan = RecoveryPlan.model_validate(doc)
    chosen = plan.chosen
    if chosen is None:
        raise SourceUnusable(f"recovery plan {plan.id} has no chosen scenario")
    return RecoveryInput(
        id=plan.id,
        approved=plan.status == "APPROVED",
        replay=plan.replay,
        changes=[
            RecoveryChange(
                flight_no=action.flight_no,
                flight_key=action.flight_key,
                origin_icao=action.origin,
                dest_icao=action.dest,
                std=action.std,
                kind=action.kind.value,  # type: ignore[arg-type]
                delay_min=action.delay_min,
                tail=action.tail,
                new_tail=action.new_tail,
            )
            for action in chosen.actions
            if action.kind is not RecoveryActionKind.KEEP
        ],
        closures=[
            RecoveryClosure(
                icao=closure.icao,
                start=closure.start,
                end=closure.end,
                source_ids=closure.source_ids,
                open_ended=closure.open_ended,
            )
            for closure in plan.closures
        ],
    )


# --- drafting ---------------------------------------------------------------------------


async def draft_messages(
    runtime: CommsRuntime,
    *,
    advisory_id: str | None = None,
    recovery_id: str | None = None,
    actor: str,
) -> list[CrewPaxMessage]:
    """DRAFT messages for an approved advisory (crew briefing) or an approved recovery plan
    (a passenger notice per cancelled or delayed flight, a crew notice per aircraft).

    A target that already has an open or approved message is returned as it is, with no model
    call. All templates are obtained before anything is stored, so a model failure stores
    nothing and raises ``AiUnavailable``.
    """
    if (advisory_id is None) == (recovery_id is None):
        raise ValueError("give exactly one of advisory_id and recovery_id")
    if advisory_id is not None:
        source = await _load_advisory(runtime.store, advisory_id)
        source_kind: Literal["advisory", "recovery"] = "advisory"
        source_id, source_version = source.id, source.version
        replay = source.replay
        targets = [briefing_target(source)]
        input_hashes = [source.input_hash, *(ref.sha256 for ref in source.sources)]
    else:
        assert recovery_id is not None
        plan = await _load_recovery(runtime.store, recovery_id)
        source_kind, source_id, source_version = "recovery", plan.id, None
        replay = plan.replay
        targets = [
            *passenger_targets(plan, runtime.airports, runtime.policy),
            *crew_notice_targets(plan, runtime.airports),
        ]
        input_hashes = []
    existing = await _existing_by_key(runtime.store, source_id)
    needed = [target for target in targets if target.key not in existing]
    templates = await _templates_for(runtime, needed, actor=actor)
    created = [
        _new_message(
            target,
            templates[_spec_key(target.spec)],
            source_kind=source_kind,
            source_id=source_id,
            source_version=source_version,
            replay=replay,
            input_hashes=input_hashes,
        )
        for target in needed
    ]
    for message in created:
        await _store_draft(runtime, message, actor=actor)
    by_key = {**existing, **{message.dedupe_key: message for message in created}}
    return [by_key[target.key] for target in targets]


async def _load_advisory(store: Store, advisory_id: str) -> Advisory:
    doc = await store.get(Collection.ADVISORIES, advisory_id)
    if doc is None:
        raise SourceNotFound(f"advisory {advisory_id}")
    advisory = Advisory.model_validate(doc)
    if advisory.status not in (AdvisoryStatus.APPROVED, AdvisoryStatus.EDITED):
        raise SourceNotApproved(f"advisory {advisory_id} is {advisory.status.value}")
    return advisory


async def _load_recovery(store: Store, recovery_id: str) -> RecoveryInput:
    doc = await store.get(Collection.RECOVERY, recovery_id)
    if doc is None:
        raise SourceNotFound(f"recovery plan {recovery_id}")
    plan = recovery_input(doc)
    if not plan.approved:
        raise SourceNotApproved(f"recovery plan {recovery_id} is not approved")
    return plan


async def _existing_by_key(store: Store, source_id: str) -> dict[str, CrewPaxMessage]:
    """Open and approved messages of the source by dedupe key; a rejected one may be redrafted."""
    docs = await store.query(
        Collection.MESSAGES,
        [Where("source_id", "==", source_id)],
        order_by="created_at",
        descending=False,
        limit=500,
    )
    messages = (CrewPaxMessage.model_validate(doc) for doc in docs)
    return {m.dedupe_key: m for m in messages if m.status is not MessageStatus.REJECTED}


def _spec_key(spec: TemplateSpec) -> tuple[Any, ...]:
    return (spec.kind, spec.status, spec.jurisdiction, spec.languages)


async def _templates_for(
    runtime: CommsRuntime, targets: Sequence[Target], *, actor: str
) -> dict[tuple[Any, ...], Templates]:
    """One model call per distinct (kind, status, jurisdiction, languages)."""
    found: dict[tuple[Any, ...], Templates] = {}
    for target in targets:
        key = _spec_key(target.spec)
        if key in found:
            continue
        try:
            found[key] = await request_templates(runtime, target.spec)
        except AiUnavailable as exc:
            await _record_ai_failure(runtime, target.spec, exc.reason, actor=actor)
            raise
        runtime.trace(
            TraceStage.MESSAGES,
            "stub" if found[key].backend == "stub" else "gemini",
            _templates_line(target.spec, found[key]),
        )
    return found


def _templates_line(spec: TemplateSpec, templates: Templates) -> str:
    label = "NO MODEL" if templates.backend == "stub" else "AI-WRITTEN"
    what = " ".join(part for part in (spec.kind.value, spec.status) if part)
    return f"TEMPLATES {what} ({'+'.join(spec.languages)}) {label}"


async def _record_ai_failure(
    runtime: CommsRuntime, spec: TemplateSpec, reason: str, *, actor: str
) -> None:
    what = " ".join(part for part in (spec.kind.value, spec.status) if part)
    runtime.trace(
        TraceStage.MESSAGES,
        "code",
        f"MESSAGES {AI_UNAVAILABLE} ({reason}): NOTHING WRITTEN FOR {what}",
        level="error",
    )
    await audit.record(
        runtime.store,
        actor=SYSTEM_ACTOR,
        action=AuditAction.AI_FAILED,
        after={"stage": "messages", "kind": spec.kind.value, "requested_by": actor},
        model_id=runtime.llm.model_id("lite"),
        note=f"{AI_UNAVAILABLE}: {reason}",
    )


def _new_message(
    target: Target,
    templates: Templates,
    *,
    source_kind: Literal["advisory", "recovery"],
    source_id: str,
    source_version: int | None,
    replay: bool,
    input_hashes: Sequence[str],
) -> CrewPaxMessage:
    at = timeutil.now()
    texts = [
        MessageText(
            language=language,
            template=templates.by_language[language],
            body=fill(templates.by_language[language], target.values[language]),
        )
        for language in target.spec.languages
    ]
    return CrewPaxMessage(
        id="msg_" + uuid4().hex[:12],
        version=1,
        status=MessageStatus.DRAFT,
        created_at=at,
        updated_at=at,
        replay=replay,
        kind=target.kind,
        source_kind=source_kind,
        source_id=source_id,
        source_version=source_version,
        flight_no=target.flight_no,
        tail=target.tail,
        route=target.route,
        texts=texts,
        llm_backend=templates.backend,
        model_id=templates.model_id,
        prompt_hashes={"templates": templates.prompt_hash},
        input_hashes=list(input_hashes),
        dedupe_key=target.key,
    )


async def _store_draft(runtime: CommsRuntime, message: CrewPaxMessage, *, actor: str) -> None:
    await runtime.store.put(Collection.MESSAGES, message.id, message.model_dump(mode="json"))
    await audit.record(
        runtime.store,
        actor=actor,
        action=AuditAction.MESSAGE_DRAFTED,
        advisory_id=_advisory_ref(message),
        after=_audit_view(message),
        input_hashes=message.input_hashes,
        model_id=message.model_id,
        prompt_hash=message.prompt_hashes.get("templates"),
    )
    runtime.bus.publish(SseEvent.MESSAGE, message)


# --- dispatcher decisions ---------------------------------------------------------------

_locks: "weakref.WeakKeyDictionary[Store, asyncio.Lock]" = weakref.WeakKeyDictionary()


def decision_lock(store: Store) -> asyncio.Lock:
    """The store's compare-and-set covers advisories only, so decisions on messages and
    handover read-backs are serialised here (Cloud Run runs one instance)."""
    lock = _locks.get(store)
    if lock is None:
        lock = _locks[store] = asyncio.Lock()
    return lock


async def get_message(store: Store, message_id: str) -> CrewPaxMessage | None:
    doc = await store.get(Collection.MESSAGES, message_id)
    return None if doc is None else CrewPaxMessage.model_validate(doc)


async def list_messages(
    store: Store,
    *,
    status: MessageStatus | None = None,
    replay: bool | None = None,
    limit: int = 50,
) -> list[CrewPaxMessage]:
    """Newest first."""
    where = [] if status is None else [Where("status", "==", status.value)]
    if replay is not None:
        where.append(Where("replay", "==", replay))
    docs = await store.query(
        Collection.MESSAGES, where, order_by="created_at", descending=True, limit=limit
    )
    return [CrewPaxMessage.model_validate(doc) for doc in docs]


async def approve(
    store: Store,
    bus: EventBus,
    message_id: str,
    *,
    expected_version: int,
    actor: str,
    airline: Airline,
) -> CrewPaxMessage:
    """``airline``: who the outbound copy speaks for (``Runtime.airline``)."""
    return await _decide(
        store,
        bus,
        message_id,
        expected_version=expected_version,
        actor=actor,
        status=MessageStatus.APPROVED,
        changes={},
        airline=airline,
    )


async def edit_and_approve(
    store: Store,
    bus: EventBus,
    message_id: str,
    *,
    expected_version: int,
    bodies: Mapping[Language, str],
    actor: str,
    airline: Airline,
) -> CrewPaxMessage:
    current = await get_message(store, message_id)
    if current is None:
        raise MessageNotFound(message_id)
    problems = _edit_problems(current, bodies)
    if problems:
        raise EditRejected(problems)
    edited = {language: body.strip() for language, body in bodies.items()}
    return await _decide(
        store,
        bus,
        message_id,
        expected_version=expected_version,
        actor=actor,
        status=MessageStatus.EDITED,
        changes={"edited_bodies": edited},
        airline=airline,
    )


def _edit_problems(message: CrewPaxMessage, bodies: Mapping[Language, str]) -> list[str]:
    languages = {text.language for text in message.texts}
    problems = [
        f"{language}: this message has no such language"
        for language in bodies
        if language not in languages
    ]
    for language, body in bodies.items():
        if not body.strip():
            problems.append(f"{language}: edited body is empty")
        elif len(body.strip()) > MAX_BODY_CHARS:
            problems.append(f"{language}: edited body is longer than {MAX_BODY_CHARS} characters")
    return problems


async def reject(
    store: Store,
    bus: EventBus,
    message_id: str,
    *,
    expected_version: int,
    reason: str,
    actor: str,
) -> CrewPaxMessage:
    cleaned = reason.strip()
    if len(cleaned) < MIN_REJECT_REASON_CHARS:
        raise EditRejected([f"a reject reason needs at least {MIN_REJECT_REASON_CHARS} characters"])
    return await _decide(
        store,
        bus,
        message_id,
        expected_version=expected_version,
        actor=actor,
        status=MessageStatus.REJECTED,
        changes={"reject_reason": cleaned},
        airline=None,
    )


async def _decide(
    store: Store,
    bus: EventBus,
    message_id: str,
    *,
    expected_version: int,
    actor: str,
    status: MessageStatus,
    changes: Mapping[str, Any],
    airline: Airline | None,
) -> CrewPaxMessage:
    """``airline``: who an approved message's outbound copy speaks for; None only for a
    rejection, which queues nothing."""
    async with decision_lock(store):
        current = await get_message(store, message_id)
        if current is None:
            raise MessageNotFound(message_id)
        if current.version != expected_version:
            raise VersionConflict(current)
        if current.status is not MessageStatus.DRAFT:
            raise InvalidTransition(f"message {message_id} is {current.status.value}, not DRAFT")
        at = timeutil.now()
        data = current.model_dump()
        data.update(changes)
        data.update(
            status=status,
            version=current.version + 1,
            updated_at=at,
            decided_by=actor,
            decided_at=at,
        )
        decided = CrewPaxMessage.model_validate(data)
        await store.put(Collection.MESSAGES, message_id, decided.model_dump(mode="json"))
    await audit.record(
        store,
        actor=actor,
        action=AuditAction.MESSAGE_DECIDED,
        advisory_id=_advisory_ref(decided),
        before=_audit_view(current),
        after=_audit_view(decided),
        input_hashes=decided.input_hashes,
        model_id=decided.model_id,
        prompt_hash=decided.prompt_hashes.get("templates"),
        note=decided.reject_reason,
    )
    if decided.status in _QUEUED:
        if airline is None:
            raise ValueError("an approved message needs the airline it speaks for")
        await _queue_outbound(store, decided, actor=actor, airline=airline)
    bus.publish(SseEvent.MESSAGE, decided)
    return decided


async def _queue_outbound(
    store: Store, message: CrewPaxMessage, *, actor: str, airline: Airline
) -> None:
    queued = OutboundMessage(
        id=uuid4().hex,
        advisory_id=message.id,
        advisory_version=message.version,
        queued_at=timeutil.now(),
        proxy_flight=message.flight_no or message.tail or "",
        status=AdvisoryStatus(message.status.value),
        approved_by=actor,
        text=outbound_text(message, actor=actor, airline=airline),
    )
    await store.put(Collection.OUTBOUND, queued.id, queued.model_dump(mode="json"))
    await audit.record(
        store,
        actor=actor,
        action=AuditAction.OUTBOUND_QUEUED,
        advisory_id=_advisory_ref(message),
        after={
            "outbound_id": queued.id,
            "message_id": message.id,
            "message_version": message.version,
            "destination": queued.destination,
        },
        input_hashes=message.input_hashes,
        model_id=message.model_id,
        prompt_hash=message.prompt_hashes.get("templates"),
    )


def outbound_text(message: CrewPaxMessage, *, actor: str, airline: Airline) -> str:
    """The demo's 'RING OF FIRE AIR (FICTIONAL) CREW BRIEFING - NOT FOR OPERATIONAL USE'; an
    airline's own TEPHRA names the airline and never calls it fictional."""
    kind = message.kind.value.replace("_", " ")
    blocks = [
        f"{airline.label.upper()} {kind} - NOT FOR OPERATIONAL USE",
        *(f"[{language.upper()}]\n{body}" for language, body in message.final_bodies.items()),
        f"MESSAGE {message.id} VERSION {message.version} APPROVED BY {actor}"
        f" {timeutil.to_iso(message.decided_at or message.updated_at)}",
    ]
    return "\n\n".join(blocks)


def _advisory_ref(message: CrewPaxMessage) -> str | None:
    return message.source_id if message.source_kind == "advisory" else None


def _audit_view(message: CrewPaxMessage) -> dict[str, Any]:
    return {
        "message_id": message.id,
        "kind": message.kind.value,
        "source_kind": message.source_kind,
        "source_id": message.source_id,
        "status": message.status.value,
        "version": message.version,
        "flight_no": message.flight_no,
        "tail": message.tail,
        "languages": [text.language for text in message.texts],
        "edited_bodies": message.edited_bodies,
        "reject_reason": message.reject_reason,
    }
