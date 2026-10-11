"""The Notice Reader: a pasted volcano notice in any language, checked field by field.

Gemini (lite tier, one call and at most one repair) copies fields out of the notice, each with
an ``evidence`` string. Code then decides what stands. Evidence must be a verbatim run of
the NFKC-normalised notice, every number must appear in its evidence, enums must match words
in it, and times and heights are converted by code (zones to UTC, metres to feet), never by
the model. A notice with any claim that fails, or with no volcano or no readable time, is
stored as not verified: the dispatcher sees the raw text, and nothing reaches the pipeline.
A verified notice that says whether ash was seen becomes a ``Vona`` for the live picture.

A model failure is reported as ``AI UNAVAILABLE`` and nothing is substituted.
"""

import math
import re
import unicodedata
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from functools import cache
from pathlib import Path
from typing import Final, Literal

from pydantic import Field, computed_field

from tephra.agents.llm import LlmBackend, LlmPart, prompt_hash
from tephra.agents.plume_reader import AI_UNAVAILABLE
from tephra.config import FEED_CLOCK_SLACK, NO_MODEL_LABEL
from tephra.feeds.jma_volcano import VOLCANO_NAMES
from tephra.feeds.volcanoes import VolcanoCatalogue
from tephra.geo.units import FT_PER_M
from tephra.models import (
    AviationColor,
    FeedId,
    LlmBackendName,
    Provenance,
    TephraModel,
    UtcDatetime,
    Volcano,
    Vona,
)
from tephra.util import timeutil
from tephra.util.hashing import sha256_text, short_hash

__all__ = [
    "JMA_SOURCE_PREFIX",
    "MAX_NOTICE_CHARS",
    "PROMPT_PATH",
    "Check",
    "NoticeExtraction",
    "NoticeField",
    "NoticeReading",
    "check_extraction",
    "jma_reading",
    "normalise_notice",
    "notice_id",
    "parse_notice_time",
    "read_notice",
    "stub_extraction",
]

PROMPT_PATH: Final[Path] = Path(__file__).resolve().parent / "prompts" / "notice_reader.md"
MAX_NOTICE_CHARS: Final = 6000
MAX_PLUME_M: Final = 50_000
"""Taller than any recorded eruption column; a larger figure is a typo or a unit mix-up."""
REPAIR_ECHO_CHARS: Final = 6000
NOTICE_URL: Final = "tephra://desk/notice/{short_id}"

ZONE_HOURS: Final[dict[str, int]] = {
    "utc": 0, "gmt": 0, "z": 0, "wib": 7, "wita": 8, "wit": 9, "jst": 9, "pht": 8,
}  # fmt: skip
"""UTC offsets of the zone words a notice may print."""
_ZONE: Final = re.compile(r"(?<![a-z])(wita|wib|wit|jst|pht|utc|gmt|z)(?![a-z])")
_JAPAN_TIME: Final = "日本時間"
_MONTHS: Final[dict[str, int]] = {
    name: number
    for number, names in enumerate(
        (
            ("january", "jan", "januari", "enero"),
            ("february", "feb", "februari", "pebrero"),
            ("march", "mar", "maret", "marso"),
            ("april", "apr", "abril"),
            ("may", "mei", "mayo"),
            ("june", "jun", "juni", "hunyo"),
            ("july", "jul", "juli", "hulyo"),
            ("august", "aug", "agu", "agustus", "agosto"),
            ("september", "sep", "sept", "setyembre"),
            ("october", "oct", "okt", "oktober", "oktubre"),
            ("november", "nov", "nobyembre"),
            ("december", "dec", "des", "desember", "disyembre"),
        ),
        start=1,
    )
    for name in names
}
_DATE_PATTERNS: Final = (
    ("ymd", re.compile(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日")),
    ("ymd", re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")),
    ("dmy", re.compile(r"(\d{1,2})\s+([a-z]+)\.?,?\s+(\d{4})")),
    ("mdy", re.compile(r"([a-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})")),
)
_TIME_PATTERNS: Final = (
    re.compile(r"(\d{1,2})時\s*(\d{1,2})分()"),
    re.compile(r"(?<!\d)(\d{2})(\d{2})()\s*(?=utc|gmt|z(?![a-z]))"),
    re.compile(r"(?<![\d:.])(\d{1,2})[:.](\d{2})\s*(am|pm|a\.m\.|p\.m\.)?(?![\d])"),
)
_NUMBER: Final = re.compile(r"\d[\d.,]*")
_UNIT: Final[dict[str, re.Pattern[str]]] = {
    "m": re.compile(r"^\s*(?:m|meters?|metres?|metr\w*|メートル)(?![a-z])", re.IGNORECASE),
    "ft": re.compile(r"^\s*(?:ft|feet|foot|kaki|talampakan|フィート)(?![a-z])", re.IGNORECASE),
}
_DATUM_AFTER: Final[dict[str, re.Pattern[str]]] = {
    "above_summit": re.compile(
        r"(?:above|over)\s+(?:the\s+)?(?:summit|crater|vent|peak)"
        r"|di\s+atas\s+(?:puncak|kawah)|dari\s+(?:puncak|kawah)"
        r"|sa\s+itaas\s+ng\s+(?:tuktok|bunganga)",
        re.IGNORECASE,
    ),
    "above_sea_level": re.compile(
        r"above\s+(?:mean\s+)?sea\s+level|(?<![a-z])(?:asl|amsl|msl|dpl)(?![a-z])"
        r"|di\s+atas\s+permukaan\s+laut|sa\s+itaas\s+ng\s+(?:antas\s+ng\s+)?dagat",
        re.IGNORECASE,
    ),
}
_DATUM_BEFORE: Final[dict[str, re.Pattern[str]]] = {
    "above_summit": re.compile(r"(?:火口上|火口縁上|山頂上)\s*$"),
    "above_sea_level": re.compile(r"(?:海抜|標高)\s*$"),
}
"""Japanese writes the datum before the number ("火口上1000m"); the other languages after."""
_COLOUR_WORDS: Final[dict[str, re.Pattern[str]]] = {
    "RED": re.compile(r"(?<![a-z])(?:red|merah|pula)(?![a-z])|赤|レッド", re.IGNORECASE),
    "ORANGE": re.compile(
        r"(?<![a-z])(?:orange|oranye|jingga|kahel)(?![a-z])|オレンジ|橙", re.IGNORECASE
    ),
    "YELLOW": re.compile(
        r"(?<![a-z])(?:yellow|kuning|dilaw)(?![a-z])|黄色|イエロー", re.IGNORECASE
    ),
    "GREEN": re.compile(r"(?<![a-z])(?:green|hijau|berde)(?![a-z])|緑|グリーン", re.IGNORECASE),
}
_NOT_OBSERVED: Final = re.compile(
    r"tidak\s+(?:teramati|terlihat|tampak)|not\s+(?:be\s+)?(?:observed|visible|seen)"
    r"|hindi\s+(?:nakita|namataan|nasilayan)|確認でき(?:ず|ない)|観測されず|不明",
    re.IGNORECASE,
)
_ASH_CUE: Final = re.compile(
    r"(?<![a-z])(?:ash|abu|abo|plume|column|kolom)(?![a-z])|噴煙|火山灰", re.IGNORECASE
)
_OBSERVER_SOURCE: Final = {
    "ground_observer": "Ground observer",
    "satellite": "Satellite",
    "seismic": "Seismic record",
    "radar": "Radar",
    "aircraft": "Aircraft report",
    "other": "Other",
}

# --- what the model returns -------------------------------------------------------------

ObserverType = Literal["ground_observer", "satellite", "seismic", "radar", "aircraft", "other"]
Datum = Literal["above_summit", "above_sea_level", "unclear"]


class TextRead(TephraModel):
    value: str | None = None
    evidence: str | None = None


class ColourRead(TephraModel):
    value: Literal["GREEN", "YELLOW", "ORANGE", "RED"] | None = None
    evidence: str | None = None


class FlagRead(TephraModel):
    value: bool | None = None
    evidence: str | None = None


class HeightRead(TephraModel):
    value: float | None = None
    unit: Literal["m", "ft"] | None = None
    datum: Datum | None = None
    evidence: str | None = None


class ObserverRead(TephraModel):
    value: ObserverType | None = None
    evidence: str | None = None


class NoticeExtraction(TephraModel):
    """The Gemini answer: claims with evidence, none of them trusted until checked."""

    language: Literal["en", "id", "ja", "fil", "other"]
    volcano: TextRead
    date_text: TextRead
    time_text: TextRead
    colour_code: ColourRead
    alert_level: TextRead
    ash_observed: FlagRead
    plume_height: HeightRead
    direction: TextRead
    observer_type: ObserverRead


# --- what TEPHRA stores -----------------------------------------------------------------


class NoticeField(TephraModel):
    """One field that passed its checks, with the words it rests on."""

    name: str
    value: str
    evidence: str
    derived: str | None = Field(
        default=None, description="What code computed from it: UTC time, feet, catalogue id"
    )


class NoticeReading(TephraModel):
    id: str = Field(description="NOTICE-<short sha of the normalised text>")
    sha256: str
    created_at: UtcDatetime
    replay: bool = False
    language: str | None = None
    text: str = Field(description="The notice as read: NFKC-normalised")
    source_kind: Literal["pasted", "jma_xml"] = Field(
        default="pasted",
        description="jma_xml: parsed by code from JMA's XML; no model, verified by construction",
    )
    status: Literal["verified", "unverified", "ai_unavailable"]
    reason: str | None = Field(
        default=None, description="Why it is not verified, or the AI UNAVAILABLE reason"
    )
    fields: list[NoticeField] = Field(default_factory=list)
    problems: list[str] = Field(default_factory=list)
    vona: Vona | None = None
    llm_backend: LlmBackendName | None = None
    model_id: str | None = None
    prompt_hash: str | None = None
    label: str | None = Field(default=None, description="NO MODEL for the stub backend")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def verified(self) -> bool:
        return self.status == "verified"


JMA_SOURCE_PREFIX: Final = "JMA-"


def jma_reading(vona: Vona, *, replay: bool) -> NoticeReading:
    """A JMA volcano report from the live picture, listed beside the pasted notices. Code parsed
    it from JMA's XML, so it is verified by construction; no model read it."""
    fields = [NoticeField(name="volcano", value=vona.volcano_name, evidence="")]
    if vona.cloud_top_ft is not None:
        fields.append(NoticeField(name="cloud_top_ft", value=str(vona.cloud_top_ft), evidence=""))
    if vona.movement_text:
        fields.append(NoticeField(name="movement", value=vona.movement_text, evidence=""))
    return NoticeReading(
        id=vona.provenance.source_id,
        sha256=sha256_text(vona.raw_text),
        created_at=vona.issued_at,
        replay=replay,
        language="ja",
        text=vona.raw_text,
        source_kind="jma_xml",
        status="verified",
        fields=fields,
        vona=vona,
    )


# --- the call ---------------------------------------------------------------------------


async def read_notice(
    text: str, llm: LlmBackend, catalogue: VolcanoCatalogue, *, replay: bool = False
) -> NoticeReading:
    source = normalise_notice(text)
    system = _system_prompt()
    parts = [LlmPart.of_text(_notice_part(source))]
    p_hash = prompt_hash(system, parts)
    at = timeutil.now()

    def stub() -> NoticeExtraction:
        return stub_extraction(source, catalogue)

    extraction, call = await llm.structured(
        tier="lite", system=system, parts=parts, schema=NoticeExtraction, stub=stub
    )
    base = _ReadBase(source, at, replay, llm, p_hash)
    if extraction is None:
        reason = f"{AI_UNAVAILABLE}: {call.error or 'no usable model output'}"
        return base.reading("ai_unavailable", reason=reason)

    check = check_extraction(extraction, source, catalogue, at)
    if check.problems and call.raw_text:
        repair = [*parts, LlmPart.of_text(_repair_text(check.problems, call.raw_text))]
        second, _ = await llm.structured(
            tier="lite", system=system, parts=repair, schema=NoticeExtraction, stub=stub
        )
        if second is not None:
            extraction, check = second, check_extraction(second, source, catalogue, at)
    return base.finish(extraction, check)


def stub_extraction(text: str, catalogue: VolcanoCatalogue) -> NoticeExtraction:
    """Offline test answer (``TEPHRA_LLM=stub``): the volcano's name and nothing else, so a
    stub-read notice is never verified."""
    volcano = catalogue.find_in_text(text)
    named = TextRead()
    if volcano is not None:
        for alias in (volcano.name, *volcano.aliases):
            found = re.search(rf"(?<![A-Za-z]){re.escape(alias)}(?![A-Za-z])", text, re.IGNORECASE)
            if found is not None:
                named = TextRead(value=volcano.name, evidence=found.group(0))
                break
    return NoticeExtraction(
        language="other",
        volcano=named,
        date_text=TextRead(),
        time_text=TextRead(),
        colour_code=ColourRead(),
        alert_level=TextRead(),
        ash_observed=FlagRead(),
        plume_height=HeightRead(),
        direction=TextRead(),
        observer_type=ObserverRead(),
    )


def normalise_notice(text: str) -> str:
    return unicodedata.normalize("NFKC", text.replace("\r\n", "\n").replace("\r", "\n")).strip()


def notice_id(text: str) -> str:
    """The id a notice is stored under; the same text, however spaced, gives the same id."""
    return f"NOTICE-{short_hash(_sha(normalise_notice(text)))}"


@dataclass(frozen=True)
class _ReadBase:
    source: str
    at: datetime
    replay: bool
    llm: LlmBackend
    p_hash: str

    @property
    def sha(self) -> str:
        return _sha(self.source)

    def reading(
        self,
        status: Literal["verified", "unverified", "ai_unavailable"],
        *,
        reason: str | None = None,
        extraction: NoticeExtraction | None = None,
        check: "Check | None" = None,
        vona: Vona | None = None,
    ) -> NoticeReading:
        return NoticeReading(
            id=f"NOTICE-{short_hash(self.sha)}",
            sha256=self.sha,
            created_at=self.at,
            replay=self.replay,
            language=extraction.language if extraction else None,
            text=self.source,
            status=status,
            reason=reason,
            fields=check.fields if check else [],
            problems=check.problems if check else [],
            vona=vona,
            llm_backend=self.llm.name,
            model_id=self.llm.model_id("lite"),
            prompt_hash=self.p_hash,
            label=NO_MODEL_LABEL if self.llm.name == "stub" else None,
        )

    def finish(self, extraction: NoticeExtraction, check: "Check") -> NoticeReading:
        reasons = [*check.problems, *check.missing]
        if reasons:
            return self.reading(
                "unverified",
                reason="NOT VERIFIED: " + "; ".join(reasons),
                extraction=extraction,
                check=check,
            )
        vona = self._vona(check)
        reason = None if vona else "No statement on ash, so nothing was added to the live picture."
        return self.reading(
            "verified", reason=reason, extraction=extraction, check=check, vona=vona
        )

    def _vona(self, check: "Check") -> Vona | None:
        if check.ash is None or check.volcano is None or check.issued_at is None:
            return None
        reading_id = f"NOTICE-{short_hash(self.sha)}"
        provenance = Provenance(
            source_id=reading_id,
            feed=FeedId.VONA,
            url=NOTICE_URL.format(short_id=short_hash(self.sha)),
            fetched_at=self.at,
            issued_at=check.issued_at,
            sha256=self.sha,
            replay=self.replay,
        )
        return Vona(
            provenance=provenance,
            volcano_name=check.volcano.name,
            issued_at=check.issued_at,
            color_code=check.colour,
            ash_observed=check.ash,
            cloud_top_ft=check.top_ft if check.ash else None,
            cloud_top_m=check.top_m if check.ash else None,
            movement_text=check.direction,
            source_text=_OBSERVER_SOURCE.get(check.observer) if check.observer else None,
            raw_text=self.source,
        )


# --- verification -----------------------------------------------------------------------


@dataclass
class Check:
    """What survived verification, and why anything did not."""

    fields: list[NoticeField] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    """Claims the notice does not support: the model is asked to repair them once."""
    missing: list[str] = field(default_factory=list)
    """What the notice must state for it to be verified and is not (or code cannot read)."""
    volcano: Volcano | None = None
    issued_at: datetime | None = None
    colour: AviationColor = AviationColor.UNKNOWN
    ash: bool | None = None
    top_ft: int | None = None
    top_m: int | None = None
    direction: str | None = None
    observer: ObserverType | None = None


def check_extraction(
    extraction: NoticeExtraction, source: str, catalogue: VolcanoCatalogue, at: datetime
) -> Check:
    """Every claim of the model against the notice text. ``at`` is now, for the future check."""
    check = Check()
    _volcano(check, extraction.volcano, source, catalogue)
    _time(check, extraction.date_text, extraction.time_text, source, at)
    _colour(check, extraction.colour_code, source)
    _alert_level(check, extraction.alert_level, source)
    _ash(check, extraction.ash_observed, source)
    _height(check, extraction.plume_height, source)
    _direction(check, extraction.direction, source)
    _observer(check, extraction.observer_type, source)
    if check.volcano is None and not any(p.startswith("volcano") for p in check.problems):
        check.missing.append("the notice names no catalogue volcano")
    return check


def _claim(
    check: Check, name: str, value: object | None, evidence: str | None, source: str
) -> str | None:
    """The evidence when ``value`` is a claim whose evidence is in the notice. Silence is
    not a problem; a claim without evidence in the text is."""
    if value is None and not evidence:
        return None
    if value is None or not evidence or _squash(evidence) not in _squash(source):
        check.problems.append(f"{name}: evidence {evidence!r} is not in the notice")
        return None
    return evidence


def _volcano(check: Check, read: TextRead, source: str, catalogue: VolcanoCatalogue) -> None:
    evidence = _claim(check, "volcano", read.value, read.evidence, source)
    if evidence is None:
        return
    found = catalogue.find_in_text(evidence) or _japanese_volcano(evidence, catalogue)
    named = catalogue.resolve(read.value or "")
    if found is None or (named is not None and named.id != found.id):
        check.problems.append(f"volcano: {read.value!r} is not named in its evidence")
        return
    check.volcano = found
    check.fields.append(
        NoticeField(
            name="volcano",
            value=read.value or found.name,
            evidence=evidence,
            derived=f"{found.name} ({found.id})",
        )
    )


def _japanese_volcano(evidence: str, catalogue: VolcanoCatalogue) -> Volcano | None:
    for name, alias in VOLCANO_NAMES.items():
        if name in evidence:
            return catalogue.resolve(alias)
    return None


def _time(check: Check, date: TextRead, clock: TextRead, source: str, at: datetime) -> None:
    before = len(check.problems)
    date_evidence = _claim(check, "date_text", date.value, date.evidence, source)
    clock_evidence = _claim(check, "time_text", clock.value, clock.evidence, source)
    for name, read, evidence in (
        ("date_text", date, date_evidence),
        ("time_text", clock, clock_evidence),
    ):
        if evidence and _squash(read.value or "") not in _squash(evidence):
            check.problems.append(f"{name}: value is not copied from its evidence")
    if len(check.problems) > before:
        return
    if not (date_evidence and clock_evidence):
        check.missing.append("the notice gives no date and clock time with a zone word")
        return
    issued_at = parse_notice_time(date.value or "", clock.value or "")
    if issued_at is None:
        check.missing.append(
            "the date (with year), clock time and zone word could not be read"
            f" ({date.value!r}, {clock.value!r})"
        )
        return
    if issued_at > at + FEED_CLOCK_SLACK:
        check.problems.append(f"the notice time {timeutil.to_iso(issued_at)} is in the future")
        return
    check.issued_at = issued_at
    check.fields.append(
        NoticeField(
            name="notice_time",
            value=f"{date.value} {clock.value}",
            evidence=f"{date_evidence} | {clock_evidence}",
            derived=f"{timeutil.to_iso(issued_at)} UTC",
        )
    )


def parse_notice_time(date_text: str, time_text: str) -> datetime | None:
    """UTC time from a verbatim date and a verbatim clock time with a zone word; None when
    either is missing or not in a known layout. Zones are never assumed."""
    date_parts = _parse_date(unicodedata.normalize("NFKC", date_text).lower())
    time_normal = unicodedata.normalize("NFKC", time_text).lower()
    clock = _parse_clock(time_normal)
    zone = _ZONE.search(time_normal)
    offset = ZONE_HOURS[zone.group(1)] if zone else 9 if _JAPAN_TIME in time_normal else None
    if date_parts is None or clock is None or offset is None:
        return None
    try:
        local = datetime(*date_parts, *clock, tzinfo=timezone(timedelta(hours=offset)))
    except ValueError:
        return None
    return local.astimezone(UTC)


def _parse_date(text: str) -> tuple[int, int, int] | None:
    for order, pattern in _DATE_PATTERNS:
        match = pattern.search(text)
        if match is None:
            continue
        a, b, c = match.groups()
        if order == "ymd":
            return int(a), int(b), int(c)
        month = _MONTHS.get(b if order == "dmy" else a)
        if month is not None:
            return (int(c), month, int(a)) if order == "dmy" else (int(c), month, int(b))
    return None


def _parse_clock(text: str) -> tuple[int, int] | None:
    for pattern in _TIME_PATTERNS:
        match = pattern.search(text)
        if match is None:
            continue
        hour, minute, meridiem = int(match.group(1)), int(match.group(2)), match.group(3)
        if meridiem:
            if not 1 <= hour <= 12:
                return None
            hour = hour % 12 + (12 if meridiem.startswith("p") else 0)
        return hour, minute
    return None


def _colour(check: Check, read: ColourRead, source: str) -> None:
    evidence = _claim(check, "colour_code", read.value, read.evidence, source)
    if evidence is None or read.value is None:
        return
    if _COLOUR_WORDS[read.value].search(evidence) is None:
        check.problems.append(f"colour_code: {read.value} is not named in its evidence")
        return
    check.colour = AviationColor(read.value)
    check.fields.append(NoticeField(name="colour_code", value=read.value, evidence=evidence))


def _alert_level(check: Check, read: TextRead, source: str) -> None:
    evidence = _claim(check, "alert_level", read.value, read.evidence, source)
    if evidence is None or read.value is None:
        return
    if not _numbers(read.value) <= _numbers(evidence):
        check.problems.append("alert_level: a number in the value is not in its evidence")
        return
    check.fields.append(NoticeField(name="alert_level", value=read.value, evidence=evidence))


def _ash(check: Check, read: FlagRead, source: str) -> None:
    evidence = _claim(check, "ash_observed", read.value, read.evidence, source)
    if evidence is None or read.value is None:
        return
    not_observed = _NOT_OBSERVED.search(evidence) is not None
    seen = _ASH_CUE.search(evidence) is not None and not not_observed
    if not (seen if read.value else not_observed):
        word = "seen" if read.value else "not observed"
        check.problems.append(f"ash_observed: {word} is not what its evidence says")
        return
    check.ash = read.value
    check.fields.append(
        NoticeField(name="ash_observed", value="yes" if read.value else "no", evidence=evidence)
    )


def _height(check: Check, read: HeightRead, source: str) -> None:
    evidence = _claim(check, "plume_height", read.value, read.evidence, source)
    if evidence is None or read.value is None:
        return
    if read.unit is None or read.datum is None or not 0 < read.value <= MAX_PLUME_M * FT_PER_M:
        check.problems.append("plume_height: needs a positive value, a unit and a datum")
        return
    if not _height_supported(evidence, read.value, read.unit, read.datum):
        check.problems.append(
            f"plume_height: {read.value:g} {read.unit} {read.datum} is not what its evidence says"
        )
        return
    shown = f"{read.value:g} {read.unit} ({read.datum.replace('_', ' ')})"
    if read.datum == "unclear":
        check.fields.append(
            NoticeField(
                name="plume_height",
                value=shown,
                evidence=evidence,
                derived="not used: the notice does not say what the height is measured from",
            )
        )
        return
    metres = read.value if read.unit == "m" else read.value / FT_PER_M
    if read.datum == "above_summit":
        if check.volcano is None:
            return
        metres += check.volcano.summit_elev_m
    if metres > MAX_PLUME_M:
        check.problems.append(f"plume_height: {metres:.0f} m is beyond any recorded column")
        return
    check.top_m, check.top_ft = round(metres), round(metres * FT_PER_M)
    check.fields.append(
        NoticeField(
            name="plume_height",
            value=shown,
            evidence=evidence,
            derived=f"{check.top_ft} ft above sea level ({check.top_m} m)",
        )
    )


def _height_supported(evidence: str, value: float, unit: Literal["m", "ft"], datum: Datum) -> bool:
    """Some number equal to ``value`` in the evidence is followed by ``unit`` and, unless the
    datum is "unclear", by the datum's words before the next number (or preceded by them)."""
    matches = list(_NUMBER.finditer(evidence))
    for index, match in enumerate(matches):
        if not any(math.isclose(value, reading) for reading in _readings(match.group(0))):
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(evidence)
        after = evidence[match.end() : end]
        if _UNIT[unit].search(after) is None:
            continue
        if datum == "unclear":
            return True
        before = evidence[: match.start()]
        if _DATUM_AFTER[datum].search(after) or _DATUM_BEFORE[datum].search(before):
            return True
    return False


def _direction(check: Check, read: TextRead, source: str) -> None:
    evidence = _claim(check, "direction", read.value, read.evidence, source)
    if evidence is None or read.value is None:
        return
    if _squash(read.value) not in _squash(evidence):
        check.problems.append("direction: value is not copied from its evidence")
        return
    check.direction = read.value
    check.fields.append(NoticeField(name="direction", value=read.value, evidence=evidence))


def _observer(check: Check, read: ObserverRead, source: str) -> None:
    evidence = _claim(check, "observer_type", read.value, read.evidence, source)
    if evidence is None or read.value is None:
        return
    check.observer = read.value
    check.fields.append(NoticeField(name="observer_type", value=read.value, evidence=evidence))


# --- numbers and text -------------------------------------------------------------------


def _readings(token: str) -> set[float]:
    """The values a printed number can mean: with its separators as thousands grouping
    ("5.584", "4,000") or as a decimal point ("6.5")."""
    token = token.rstrip(".,")
    values: set[float] = set()
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", token):
        values.add(float(re.sub(r"[.,]", "", token)))
    with suppress(ValueError):  # "1.234.567" has no decimal reading
        values.add(float(token.replace(",", ".")))
    return values


def _numbers(text: str) -> set[float]:
    return {value for token in _NUMBER.findall(text) for value in _readings(token)}


def _squash(text: str) -> str:
    return " ".join(text.split())


def _sha(source: str) -> str:
    return sha256_text(_squash(source))


def _notice_part(source: str) -> str:
    return f"<notice>\n{source}\n</notice>"


def _repair_text(problems: list[str], previous: str) -> str:
    listed = "\n".join(f"- {problem}" for problem in problems)
    return (
        "REPAIR\n"
        "Code rejected these claims of your previous answer:\n"
        f"{listed}\n"
        "Your previous answer was:\n"
        f"{previous[:REPAIR_ECHO_CHARS]}\n"
        "Return a corrected JSON object. For each rejected claim copy the evidence exactly from "
        "the notice, or set the field to null."
    )


@cache
def _system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")
