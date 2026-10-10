"""The Plume Reader: Gemini reads one volcano's products side by side; code keeps it honest.

The model sees the raw SIGMET, VONA and VAA texts with their source ids and evidence
states, the code-found discrepancies, winds by flight level, the split-window summary and
the images. It returns a ``PlumeEstimate``. Code then checks the estimate against the
safety rules (``validate_estimate``), allows exactly one repair call, and otherwise falls
back to the official products alone. The cone builder unions every official polygon in any
case, so no answer can shrink the hazard; the validator stops answers that try.
"""

import math
import re
from collections.abc import Sequence
from datetime import datetime, timedelta
from functools import cache
from pathlib import Path
from typing import Final, Literal

from tephra.agents.llm import BUDGET_EXHAUSTED, LlmBackend, LlmCall, LlmPart, prompt_hash
from tephra.agents.validators import ZONE_TIME_PATTERN
from tephra.config import (
    MAX_HORIZON_H,
    MAX_PLUME_EXTENT_KM,
    MAX_SECTOR_WIDTH_DEG,
    NO_MODEL_LABEL,
    Settings,
)
from tephra.feeds.winds import profile_at, wind_at_fl
from tephra.geo.units import KM_PER_NM, ft_to_fl
from tephra.models import (
    BtdIndicator,
    EvidenceState,
    LlmBackendName,
    PlumeAssessment,
    PlumeEstimate,
    PlumeMode,
    Sigmet,
    Situation,
    TraceEvent,
    TraceSink,
    TraceStage,
    VaacAdvisory,
    Vona,
)
from tephra.reconcile import evidence_state
from tephra.util import timeutil
from tephra.util.hashing import stable_id

__all__ = [
    "PROMPT_PATH",
    "build_parts",
    "official_fallback",
    "read_plume",
    "stub_estimate",
    "validate_estimate",
]

PROMPT_PATH: Final[Path] = Path(__file__).resolve().parent / "prompts" / "plume_reader.md"

FALLBACK_NOTE: Final = "Model output rejected; official products only."
OFFICIAL_ONLY_NOTE: Final = "No model call was needed; official products only."

STUB_VONA_WINDOW_H: Final = 6.0
STUB_HALF_WIDTH_DEG: Final = 30.0
STUB_MAX_EXTENT_KM: Final = 300.0
STUB_MIN_EXTENT_KM: Final = 25.0
"""Calm winds still leave ash near the vent; a zero-length sector would draw nothing."""
STUB_HORIZON_H: Final = 3.0
STUB_CONFIDENCE: Final = 0.3
STUB_TOP_MARGIN_FL: Final = 20
WIND_OFFSETS_H: Final = (0, 3, 6, 12)
MAX_FL: Final = 600
MIN_HORIZON_H: Final = 1.0
"""Core keeps an assessment until ``created_at + horizon_h``; a horizon of minutes would ask
the model again on every tick and spend the day's budget."""
REPAIR_ECHO_CHARS: Final = 6000

_TIMESTAMPS: Final = (
    re.compile(r"\d{8}/\d{4}Z?"),
    re.compile(r"\d{4}-\d{2}-\d{2}"),
    # Lookbehinds keep advisory numbers such as "2026/1157" from reading as day/time.
    re.compile(r"(?<![\d/])\d{1,2}/\d{4}Z?(?!\d)"),
    re.compile(r"(?<!\d)\d{6}Z"),
    re.compile(r"(?<!\d)\d{4}Z"),
    re.compile(r"(?<!\d)\d{1,2}:\d{2}(?!\d)"),
    re.compile(ZONE_TIME_PATTERN, re.IGNORECASE),
)
_BLIND_BTD: Final = frozenset({BtdIndicator.SILENT, BtdIndicator.INCONCLUSIVE})
"""Split-window results that do not mean "no ash" (the science captions say so of both)."""
_NON_OBSERVATION_CUES: Final = (
    "silent",
    "inconclusive",
    "not observed",
    "not identifiable",
    "unobserved",
    "no ash",
    "night",
    "obscured",
    "could not see",
    "cannot see",
)
_HAZARD_PART: Final = r"(?:top|band|extent|sector|horizon|area|hazard|cone|polygon|width)"
_NARROWING: Final = re.compile(
    r"\b(?:(?:narrow|shrink|reduc|lower|cut|trim|smaller|narrower)\w*\s+"
    rf"(?:(?:the|our|its|this)\s+)?(?:\w+\s+)?{_HAZARD_PART}"
    r"|exclud\w*|rul(?:e|es|ed|ing) out|discount\w*|dismiss\w*)\b"
)
_NEGATIONS: Final = frozenset({"not", "never", "no", "cannot", "nor", "without", "neither"})
_SENTENCE_END: Final = re.compile(r"[.;!?\n]+")

Actor = Literal["code", "gemini", "stub"]
Outcome = Literal["ACCEPTED", "REPAIRED", "FALLBACK_OFFICIAL", "OFFICIAL_ONLY", "STUB"]


# --- the call ---------------------------------------------------------------------------


async def read_plume(
    situation: Situation,
    llm: LlmBackend,
    *,
    images: Sequence[LlmPart] = (),
    settings: Settings,
    trace: TraceSink | None = None,
    call_model: bool = True,
) -> PlumeAssessment:
    system = _system_prompt()
    parts = build_parts(situation, images)
    p_hash = prompt_hash(system, parts)
    report = _Reporter(trace, situation)
    known = situation.source_ids()
    dropped = [part for part in images if part.kind != "image" or part.label not in known]
    if dropped:
        report("code", f"Plume Reader: {len(dropped)} image(s) without a known source id not sent")

    if llm.name == "stub":
        return await _read_with_stub(situation, llm, system, parts, p_hash, settings, report)
    if not call_model:
        estimate = official_fallback(situation, settings).model_copy(
            update={"uncertainty_notes": OFFICIAL_ONLY_NOTE}
        )
        report("code", f"Plume: official products only ({_estimate_line(estimate)})")
        return _assessment(
            situation, estimate, llm, model_id="none", p_hash=p_hash, outcome="OFFICIAL_ONLY"
        )
    return await _read_with_model(situation, llm, system, parts, p_hash, settings, report)


async def _read_with_model(
    situation: Situation,
    llm: LlmBackend,
    system: str,
    parts: list[LlmPart],
    p_hash: str,
    settings: Settings,
    report: "_Reporter",
) -> PlumeAssessment:
    model_id = llm.model_id("main")
    images_used = [part.label for part in parts if part.kind == "image" and part.label]
    texts = len(situation.sigmets) + len(situation.vonas) + len(situation.vaas)
    report(
        "gemini",
        f"Plume Reader: asking {model_id} ({texts} texts, {len(images_used)} images, "
        f"{len(situation.discrepancies)} discrepancies)",
    )

    def stub() -> PlumeEstimate:
        return stub_estimate(situation, settings)

    estimate, call = await llm.structured(
        tier="main", system=system, parts=parts, schema=PlumeEstimate, stub=stub
    )
    calls = [call]
    problems = _problems(estimate, call, situation)
    if estimate is not None and not problems:
        report("gemini", f"Plume Reader accepted: {_estimate_line(estimate)}")
        return _assessment(
            situation, estimate, llm, model_id, p_hash, "ACCEPTED", calls, images_used=images_used
        )

    if call.raw_text:  # an empty answer has nothing to repair: fall back (MODULES.md 5.5)
        report(
            "code",
            "Plume Reader output rejected; one repair call",
            level="warn",
            detail={"validation_errors": problems},
        )
        repair_parts = [*parts, LlmPart.of_text(_repair_text(problems, call.raw_text))]
        estimate, call = await llm.structured(
            tier="main", system=system, parts=repair_parts, schema=PlumeEstimate, stub=stub
        )
        calls.append(call)
        problems = _problems(estimate, call, situation)
        if estimate is not None and not problems:
            report("gemini", f"Plume Reader repaired: {_estimate_line(estimate)}")
            return _assessment(
                situation, estimate, llm, model_id, p_hash, "REPAIRED", calls, images_used
            )

    fallback = _fallback(situation, settings)
    by_stub = fallback.mode is PlumeMode.HYPOTHESIS
    floor = f"the {NO_MODEL_LABEL} hypothesis" if by_stub else "official products only"
    report(
        "code",
        f"Plume Reader fell back to {floor} ({_estimate_line(fallback)})",
        level="warn",
        detail={"validation_errors": problems, "model_id": model_id},
    )
    return _assessment(
        situation,
        fallback,
        llm,
        model_id,
        p_hash,
        "FALLBACK_OFFICIAL",
        calls,
        images_used,
        validation_errors=problems,
        backend="stub" if by_stub else llm.name,
    )


async def _read_with_stub(
    situation: Situation,
    llm: LlmBackend,
    system: str,
    parts: list[LlmPart],
    p_hash: str,
    settings: Settings,
    report: "_Reporter",
) -> PlumeAssessment:
    def stub() -> PlumeEstimate:
        return stub_estimate(situation, settings)

    estimate, _ = await llm.structured(
        tier="main", system=system, parts=parts, schema=PlumeEstimate, stub=stub
    )
    errors: list[str] = []
    if estimate is None:
        errors = ["stub backend returned nothing"]
    elif not _is_empty_floor(estimate, situation):
        errors = validate_estimate(estimate, situation)
    if estimate is None or errors:
        estimate = official_fallback(situation, settings)
        report("stub", "NO MODEL: stub estimate rejected; official products only", level="warn")
    report("stub", f"{NO_MODEL_LABEL}: stub plume estimate {_estimate_line(estimate)}")
    return _assessment(
        situation,
        estimate,
        llm,
        llm.model_id("main"),
        p_hash,
        "STUB",
        validation_errors=errors,
    )


def _problems(estimate: PlumeEstimate | None, call: LlmCall, situation: Situation) -> list[str]:
    if estimate is None:
        return [f"no usable model output ({call.error or 'unknown error'})"]
    return validate_estimate(estimate, situation)


def _assessment(
    situation: Situation,
    estimate: PlumeEstimate,
    llm: LlmBackend,
    model_id: str,
    p_hash: str,
    outcome: Outcome,
    calls: Sequence[LlmCall] = (),
    images_used: Sequence[str] = (),
    *,
    validation_errors: Sequence[str] = (),
    backend: LlmBackendName | None = None,
) -> PlumeAssessment:
    """``backend`` is who produced the estimate when it is not ``llm`` (code's stub after a
    rejected answer), so the cone and advisories built on it read NO MODEL."""
    made = [call for call in calls if call.error != BUDGET_EXHAUSTED]
    volcano_id = situation.volcano.id
    input_hash = situation.input_hash
    return PlumeAssessment(
        id=stable_id("PA", volcano_id, input_hash, p_hash, model_id),
        volcano_id=volcano_id,
        created_at=timeutil.now(),
        input_hash=input_hash,
        estimate=estimate,
        llm_backend=backend or llm.name,
        model_id=model_id,
        prompt_hash=p_hash,
        outcome=outcome,
        attempts=len(made),
        validation_errors=list(validation_errors),
        images_used=list(images_used),
        latency_ms=sum(call.latency_ms for call in made) if made else None,
    )


def _repair_text(problems: Sequence[str], previous: str) -> str:
    listed = "\n".join(f"- {problem}" for problem in problems)
    return (
        "REPAIR\n"
        "Code rejected your previous answer for these reasons:\n"
        f"{listed}\n"
        "Your previous answer was:\n"
        f"{previous[:REPAIR_ECHO_CHARS]}\n"
        "Return a corrected JSON object that fixes every reason and keeps what was valid."
    )


@cache
def _system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


class _Reporter:
    def __init__(self, sink: TraceSink | None, situation: Situation) -> None:
        self._sink = sink
        self._volcano_id = situation.volcano.id

    def __call__(
        self,
        actor: Actor,
        message: str,
        *,
        level: Literal["info", "warn", "error"] = "info",
        detail: dict[str, object] | None = None,
    ) -> None:
        if self._sink is None:
            return
        event = TraceEvent.new(
            TraceStage.PLUME,
            actor,
            message,
            level=level,
            volcano_id=self._volcano_id,
            detail=detail,
        )
        self._sink(event)


def _estimate_line(estimate: PlumeEstimate) -> str:
    band = f"FL{estimate.base_fl:03d}-FL{estimate.top_fl:03d}"
    text = f"{estimate.mode.value} {band}, {round(estimate.confidence * 100)}%"
    if estimate.mode is PlumeMode.OFFICIAL or estimate.extent_km <= 0:
        return text
    return (
        f"{text}, sector {estimate.bearing_from_deg:.0f}-{estimate.bearing_to_deg:.0f} deg "
        f"to {estimate.extent_km:.0f} km over {estimate.horizon_h:g} h"
    )


# --- validation -------------------------------------------------------------------------


def validate_estimate(estimate: PlumeEstimate, situation: Situation) -> list[str]:
    """Every reason to reject the estimate; an empty list means accepted."""
    return [
        *_citation_problems(estimate, situation),
        *_timestamp_problems(estimate, situation),
        *_mode_problems(estimate, situation),
        *_geometry_problems(estimate, situation),
        *_hypothesis_problems(estimate, situation),
        *_narrowing_problems(estimate, situation),
    ]


def _citation_problems(estimate: PlumeEstimate, situation: Situation) -> list[str]:
    known = situation.source_ids()
    discrepancy_ids = {discrepancy.id for discrepancy in situation.discrepancies}
    problems = [
        f"sources_used cites {source!r}, which is not an input source id"
        for source in estimate.sources_used
        if source not in known
    ]
    for reading in estimate.disagreements_explained:
        if reading.discrepancy_id not in discrepancy_ids:
            problems.append(f"discrepancy_id {reading.discrepancy_id!r} is not in the input")
        if reading.which_source_we_lean_on not in known:
            problems.append(
                f"which_source_we_lean_on {reading.which_source_we_lean_on!r} is not an input "
                "source id"
            )
    return problems


def _timestamp_problems(estimate: PlumeEstimate, situation: Situation) -> list[str]:
    """Times are rendered by code from provenance; the model may cite ids, never write times."""
    ids = sorted(
        {*situation.source_ids(), *(d.id for d in situation.discrepancies)}, key=len, reverse=True
    )
    problems: list[str] = []
    for name, text in _text_fields(estimate):
        scrubbed = text
        for identifier in ids:
            scrubbed = scrubbed.replace(identifier, " ")
        found = sorted({match.group(0) for p in _TIMESTAMPS for match in p.finditer(scrubbed)})
        if found:
            problems.append(f"{name} contains time or date text {', '.join(found)}; write none")
    return problems


def _text_fields(estimate: PlumeEstimate) -> list[tuple[str, str]]:
    fields = [("rationale", estimate.rationale), ("uncertainty_notes", estimate.uncertainty_notes)]
    for index, reading in enumerate(estimate.disagreements_explained):
        fields.append((f"disagreements_explained[{index}].reading", reading.reading))
        fields.append((f"disagreements_explained[{index}].why", reading.why))
    return fields


def _mode_problems(estimate: PlumeEstimate, situation: Situation) -> list[str]:
    """With no official polygon the cone is the model's sector alone, and only HYPOTHESIS
    limits the advice to MONITOR or HOLD (``ALLOWED_ACTIONS``)."""
    if estimate.mode is PlumeMode.HYPOTHESIS and situation.official_valid_now():
        return ["HYPOTHESIS is not allowed while an official polygon is valid"]
    if estimate.mode is not PlumeMode.HYPOTHESIS and not situation.official_layers:
        return [
            f"{estimate.mode.value} needs an official polygon and there is none; use HYPOTHESIS"
        ]
    return []


def _geometry_problems(estimate: PlumeEstimate, situation: Situation) -> list[str]:
    problems: list[str] = []
    official_top = situation.official_top_ft()
    if official_top is not None and estimate.top_fl * 100 < official_top:
        problems.append(
            f"top_fl {estimate.top_fl} is below the official top FL{ft_to_fl(official_top):03d}; "
            "the hazard may be widened, never shrunk"
        )
    if estimate.sector_width_deg() > MAX_SECTOR_WIDTH_DEG:
        problems.append(
            f"sector is {estimate.sector_width_deg():.0f} degrees wide; the maximum is "
            f"{MAX_SECTOR_WIDTH_DEG:.0f}"
        )
    if estimate.extent_km > MAX_PLUME_EXTENT_KM:
        problems.append(
            f"extent_km {estimate.extent_km:g} exceeds the maximum {MAX_PLUME_EXTENT_KM:g}"
        )
    if estimate.horizon_h > MAX_HORIZON_H:
        problems.append(f"horizon_h {estimate.horizon_h:g} exceeds the maximum {MAX_HORIZON_H:g}")
    if estimate.horizon_h < MIN_HORIZON_H:
        problems.append(f"horizon_h {estimate.horizon_h:g} is below the minimum {MIN_HORIZON_H:g}")
    if estimate.base_fl >= estimate.top_fl:
        problems.append(f"base_fl {estimate.base_fl} must be below top_fl {estimate.top_fl}")
    return problems


def _hypothesis_problems(estimate: PlumeEstimate, situation: Situation) -> list[str]:
    """Without a valid official polygon the HYPOTHESIS sector is what the cone draws now, so
    while a recent VONA reports ash it must draw something and reach the reported top."""
    vona = _recent_ash_vona(situation)
    if estimate.mode is not PlumeMode.HYPOTHESIS or vona is None:
        return []
    problems: list[str] = []
    if estimate.extent_km <= 0 or estimate.sector_width_deg() <= 0:
        problems.append(
            f"HYPOTHESIS draws no sector while {_vona_name(vona)} reports ash; give extent_km "
            "above 0 and two different bearings"
        )
    floor_fl = _vona_floor_fl(vona)
    if floor_fl is not None and estimate.top_fl < floor_fl:
        problems.append(
            f"top_fl {estimate.top_fl} is below the {vona.cloud_top_ft:,} ft ash top that "
            f"{_vona_name(vona)} reports; top_fl must be >= {floor_fl}"
        )
    return problems


def _vona_floor_fl(vona: Vona) -> int | None:
    """The lowest top_fl reaching the VONA's reported top, capped at the FL600 an estimate
    can give: asking more of a Plinian column would reject every answer and the stub too."""
    if vona.cloud_top_ft is None:
        return None
    return min(MAX_FL, math.ceil(vona.cloud_top_ft / 100))


def _narrowing_problems(estimate: PlumeEstimate, situation: Situation) -> list[str]:
    """A non-observation or a blind split window may never be the reason to narrow.

    Two checks: leaning on such a source to settle a disagreement, and a sentence that
    names one next to a narrowing verb that is not negated ("does not narrow" is fine).
    """
    blind = _non_observation_ids(situation)
    problems = [
        f"disagreement {reading.discrepancy_id} leans on {reading.which_source_we_lean_on}, "
        "a non-observation; not seeing ash cannot settle a disagreement"
        for reading in estimate.disagreements_explained
        if reading.which_source_we_lean_on in blind
    ]
    for name, text in _text_fields(estimate):
        for sentence in _SENTENCE_END.split(text.lower()):
            if _narrows_on_non_observation(sentence):
                problems.append(
                    f"{name} narrows the hazard because ash was not seen: {sentence.strip()!r}"
                )
    return problems


def _non_observation_ids(situation: Situation) -> set[str]:
    blind_states = {
        EvidenceState.NOT_OBSERVED,
        EvidenceState.NIGHT_BLIND,
        EvidenceState.NOT_IDENTIFIABLE,
    }
    records: list[Sigmet | Vona | VaacAdvisory] = [*situation.vonas, *situation.vaas]
    ids = {
        record.provenance.source_id
        for record in records
        if evidence_state(record, situation.volcano, situation.as_of) in blind_states
    }
    if situation.btd is not None and situation.btd.indicator in _BLIND_BTD:
        ids.add(situation.btd.provenance.source_id)
    return ids


def _narrows_on_non_observation(sentence: str) -> bool:
    if not any(cue in sentence for cue in _NON_OBSERVATION_CUES):
        return False
    for match in _NARROWING.finditer(sentence):
        preceding = re.findall(r"[a-z']+", sentence[: match.start()])[-4:]
        negated = any(word in _NEGATIONS or word.endswith("n't") for word in preceding)
        if not negated:
            return True
    return False


# --- fallbacks --------------------------------------------------------------------------


def _fallback(situation: Situation, settings: Settings) -> PlumeEstimate:
    """After a rejected or missing answer: official products only, or with no official layer
    at all, code's NO MODEL hypothesis, so a recent ash report never leaves the cone empty.
    The hypothesis must pass the same rules as a model's answer."""
    if not situation.official_layers:
        estimate = stub_estimate(situation, settings)
        if estimate.mode is PlumeMode.HYPOTHESIS and not validate_estimate(estimate, situation):
            return estimate
    return official_fallback(situation, settings)


def official_fallback(situation: Situation, settings: Settings) -> PlumeEstimate:
    """Official products only: the band of the official layers (0/0 when there are none)."""
    base_fl, top_fl = _official_band_fl(situation)
    return PlumeEstimate(
        mode=PlumeMode.OFFICIAL,
        base_fl=base_fl,
        top_fl=top_fl,
        bearing_from_deg=0,
        bearing_to_deg=0,
        extent_km=0,
        horizon_h=settings.default_horizon_h,
        confidence=1.0,
        sources_used=sorted({layer.source_id for layer in situation.official_layers}),
        disagreements_explained=[],
        uncertainty_notes=FALLBACK_NOTE,
        rationale=_official_rationale(situation),
    )


def stub_estimate(situation: Situation, settings: Settings) -> PlumeEstimate:
    """Deterministic estimate for ``TEPHRA_LLM=stub`` (labelled NO MODEL everywhere)."""
    if situation.official_layers:
        return official_fallback(situation, settings).model_copy(
            update={
                "uncertainty_notes": "NO MODEL: no model read the products; official band only.",
                "rationale": f"NO MODEL: {_official_rationale(situation)}",
            }
        )
    vona = _recent_ash_vona(situation)
    if vona is not None:
        hypothesis = _stub_hypothesis(situation, vona)
        if hypothesis is not None:
            return hypothesis
        reason = f"{_vona_name(vona)} reports ash but gives no direction and no winds are known"
    else:
        reason = "no official product is in force and no recent VONA reports ash"
    return PlumeEstimate(
        mode=PlumeMode.OFFICIAL,
        base_fl=0,
        top_fl=0,
        bearing_from_deg=0,
        bearing_to_deg=0,
        extent_km=0,
        horizon_h=settings.default_horizon_h,
        confidence=1.0,
        sources_used=[],
        disagreements_explained=[],
        uncertainty_notes=f"NO MODEL: {reason}.",
        rationale=f"NO MODEL: nothing to draw; {reason}.",
    )


def _stub_hypothesis(situation: Situation, vona: Vona) -> PlumeEstimate | None:
    """A sector of +/- 30 degrees down the wind at the VONA's top (or its stated drift)."""
    top_ft = vona.cloud_top_ft or situation.volcano.summit_elev_ft
    top_fl = min(MAX_FL, math.ceil(top_ft / 1000) * 10 + STUB_TOP_MARGIN_FL)
    sources = [vona.provenance.source_id]
    profile = profile_at(situation.winds, situation.as_of)
    if profile is not None and profile.levels:
        wind = wind_at_fl(profile, ft_to_fl(top_ft))
        centre = wind.toward_deg
        extent = min(STUB_MAX_EXTENT_KM, wind.speed_kt * KM_PER_NM * STUB_HORIZON_H)
        sources.append(profile.provenance.source_id)
        basis = (
            f"the model wind at FL{wind.flight_level:03d} carries ash toward {centre:.0f} deg "
            f"at {wind.speed_kt:.0f} kt"
        )
    elif vona.movement_toward_deg is not None:
        centre = vona.movement_toward_deg
        extent = STUB_MAX_EXTENT_KM
        basis = f"no winds are known, so the sector follows the VONA drift toward {centre:.0f} deg"
    else:
        return None
    extent = max(extent, STUB_MIN_EXTENT_KM)
    return PlumeEstimate(
        mode=PlumeMode.HYPOTHESIS,
        base_fl=0,
        top_fl=top_fl,
        bearing_from_deg=(centre - STUB_HALF_WIDTH_DEG) % 360.0,
        bearing_to_deg=(centre + STUB_HALF_WIDTH_DEG) % 360.0,
        extent_km=round(extent, 1),
        horizon_h=STUB_HORIZON_H,
        confidence=STUB_CONFIDENCE,
        sources_used=sources,
        disagreements_explained=[],
        uncertainty_notes=(
            "NO MODEL: no official polygon is in force; this sector is a cautious placeholder "
            "from one observatory notice and model winds, not an observation of the cloud."
        ),
        rationale=(
            f"NO MODEL: {_vona_name(vona)} reports ash to {top_ft:,} ft and no official polygon "
            f"is in force. {basis[0].upper()}{basis[1:]}; the sector spans "
            f"{2 * STUB_HALF_WIDTH_DEG:.0f} deg to {extent:.0f} km, top FL{top_fl:03d}."
        ),
    )


def _recent_ash_vona(situation: Situation) -> Vona | None:
    recent = [
        vona
        for vona in situation.vonas
        if vona.ash_observed and vona.is_recent(situation.as_of, STUB_VONA_WINDOW_H)
    ]
    return max(recent, key=lambda vona: vona.issued_at, default=None)


def _is_empty_floor(estimate: PlumeEstimate, situation: Situation) -> bool:
    """The code-built "nothing to draw" estimate (OFFICIAL with no layers), exempt from the
    model rules that would otherwise reject its 0/0 band."""
    return estimate.mode is PlumeMode.OFFICIAL and not situation.official_layers


def _official_band_fl(situation: Situation) -> tuple[int, int]:
    base_ft = situation.official_base_ft()
    top_ft = situation.official_top_ft()
    if base_ft is None or top_ft is None:
        return 0, 0
    # Round outward so the band in flight levels never sits inside the official one.
    return max(0, math.floor(base_ft / 100)), min(MAX_FL, math.ceil(top_ft / 100))


def _official_rationale(situation: Situation) -> str:
    layers = situation.official_layers
    if not layers:
        return "No official polygon is in force or forecast."
    labels = sorted({layer.label for layer in layers})
    base_fl, top_fl = _official_band_fl(situation)
    band = f"{'SFC' if base_fl == 0 else f'FL{base_fl:03d}'}/FL{top_fl:03d}"
    return f"Official products only: {'; '.join(labels)}; band {band}."


def _vona_name(vona: Vona) -> str:
    return f"VONA {vona.notice_number}" if vona.notice_number else f"VONA {vona.volcano_name}"


# --- the request ------------------------------------------------------------------------


def build_parts(situation: Situation, images: Sequence[LlmPart]) -> list[LlmPart]:
    """Text blocks, then the images (each announced by its source id), then the task.

    Images whose label is not a source id of the situation are left out, so the model
    cannot be shown anything it is not allowed to cite.
    """
    known = situation.source_ids()
    usable = [part for part in images if part.kind == "image" and part.label in known]
    blocks = [
        _volcano_block(situation),
        _official_block(situation),
        _texts_block(situation),
        _discrepancy_block(situation),
        _winds_block(situation),
        _btd_block(situation),
        _images_block(situation, usable),
    ]
    return [
        *(LlmPart.of_text(block) for block in blocks),
        *usable,
        LlmPart.of_text(_task_block(situation)),
    ]


def _volcano_block(situation: Situation) -> str:
    volcano = situation.volcano
    return (
        "VOLCANO\n"
        f"{volcano.name} (GVP {volcano.id}), {volcano.country}. Vent {volcano.lat:.3f}, "
        f"{volcano.lon:.3f}. Summit {volcano.summit_elev_ft:,} ft ({volcano.summit_elev_m:,} m) "
        f"above sea level. VAAC area: {volcano.vaac.value}. Observatory: {volcano.observatory}."
    )


def _official_block(situation: Situation) -> str:
    lines = ["OFFICIAL FLOOR (code-built from SIGMET and VAA polygons; binding)"]
    if not situation.official_layers:
        lines.append("No official polygon is in force or forecast.")
        return "\n".join(lines)
    for layer in situation.official_layers:
        state = "in force now" if layer.is_valid(situation.as_of) else "forecast window"
        lines.append(
            f"- [{layer.source_id}] {layer.label}: {_band(layer.base_ft, layer.top_ft)}, {state}"
        )
    top_ft = situation.official_top_ft()
    if top_ft is not None:
        top_fl = math.ceil(top_ft / 100)
        lines.append(f"Highest official top: FL{top_fl:03d}; your top_fl must be >= {top_fl}.")
    valid_now = "yes" if situation.official_valid_now() else "no"
    lines.append(f"An official polygon is in force now: {valid_now}.")
    return "\n".join(lines)


def _texts_block(situation: Situation) -> str:
    records: list[Sigmet | Vona | VaacAdvisory] = [
        *situation.sigmets,
        *situation.vonas,
        *situation.vaas,
    ]
    lines = ["SOURCE TEXTS (verbatim; ages are minutes before now)"]
    if not records:
        lines.append("No SIGMET, VONA or VAA text is available.")
    for record in records:
        state = evidence_state(record, situation.volcano, situation.as_of)
        header = (
            f"[{record.provenance.source_id}] {_kind(record)}, evidence {state.value}, "
            f"{_age(_observed_at(record), situation.as_of)}"
        )
        if record.provenance.stale:
            header += ", served from the last good copy after a failed fetch"
        lines.extend(["", header, record.raw_text.strip()])
    return "\n".join(lines)


def _discrepancy_block(situation: Situation) -> str:
    lines = ["DISCREPANCIES (found by code; explain each one, do not reclassify)"]
    if not situation.discrepancies:
        lines.append("None found.")
    for discrepancy in situation.discrepancies:
        magnitude = (
            f", {discrepancy.magnitude:g} {discrepancy.unit}"
            if discrepancy.magnitude is not None and discrepancy.unit
            else ""
        )
        sources = ", ".join(f"[{source}]" for source in discrepancy.source_ids)
        lines.append(
            f"- {discrepancy.id} {discrepancy.kind.value} ({discrepancy.severity.value}), "
            f"aspect {discrepancy.aspect}{magnitude}; sources {sources}: {discrepancy.summary}"
        )
        if discrepancy.aspect in {"top", "base", "direction"}:
            values = "; ".join(f"[{key}] {value}" for key, value in discrepancy.values.items())
            lines.append(f"  values: {values}")
    return "\n".join(lines)


def _winds_block(situation: Situation) -> str:
    lines = [
        "WINDS AT THE VENT (Open-Meteo model forecast, not an observation; "
        "toward = where the wind carries ash)"
    ]
    chosen: dict[str, str] = {}
    for offset in WIND_OFFSETS_H:
        profile = profile_at(situation.winds, situation.as_of + timedelta(hours=offset))
        if profile is None or profile.provenance.source_id in chosen:
            continue
        hours = round((profile.valid_at - situation.as_of).total_seconds() / 3600)
        levels = "; ".join(
            f"FL{level.flight_level:03d} toward {level.toward_deg:03.0f} deg at "
            f"{level.speed_kt:.0f} kt"
            for level in sorted(profile.levels, key=lambda item: item.flight_level)
        )
        chosen[profile.provenance.source_id] = (
            f"- [{profile.provenance.source_id}] about {hours:+d} h: {levels}"
        )
    lines.extend(chosen.values() or ["No wind forecast is available."])
    return "\n".join(lines)


def _btd_block(situation: Situation) -> str:
    title = "SPLIT-WINDOW BTD (code-computed from raw Himawari-9; an indicator, not detection)"
    btd = situation.btd
    if btd is None:
        return f"{title}\nNo split-window result is available."
    lines = [
        title,
        f"[{btd.provenance.source_id}] indicator {btd.indicator.value}, bands {btd.band_pair}, "
        f"threshold {btd.threshold_k:g} K, {btd.pixel_count:,} pixels, "
        f"{btd.negative_fraction * 100:.2f} % below threshold.",
        f"BTD min {btd.min_btd_k:.2f} K, 5th percentile {btd.p05_btd_k:.2f} K, median "
        f"{btd.median_btd_k:.2f} K; coldest brightness temperature {btd.min_bt_k:.1f} K.",
    ]
    if btd.nearest_negative_km is not None:
        lines.append(f"Nearest negative pixel {btd.nearest_negative_km:.0f} km from the vent.")
    if btd.negative_centroid_bearing_deg is not None and btd.negative_centroid_distance_km:
        lines.append(
            f"Negative pixels centre on bearing {btd.negative_centroid_bearing_deg:.0f} deg, "
            f"{btd.negative_centroid_distance_km:.0f} km from the vent."
        )
    lines.extend(f"Caveat: {caveat}" for caveat in btd.caveats)
    if btd.indicator in _BLIND_BTD:
        lines.append(f"{btd.indicator.value} never means no ash.")
    return "\n".join(lines)


def _images_block(situation: Situation, images: Sequence[LlmPart]) -> str:
    lines = ["IMAGES (each follows as IMAGE <source id>; context, not proof)"]
    if not images:
        lines.append("No images are attached.")
        return "\n".join(lines)
    frames = {frame.provenance.source_id: frame for frame in situation.frames}
    btd = situation.btd
    for image in images:
        label = image.label or ""
        frame = frames.get(label)
        if frame is not None:
            where = (
                f"north up, west {frame.bbox.west:.2f} east {frame.bbox.east:.2f} "
                f"south {frame.bbox.south:.2f} north {frame.bbox.north:.2f}"
                if frame.bbox is not None
                else "not georeferenced: no coordinates can be read from it"
            )
            lines.append(f"- [{label}] {frame.product.value} crop around the vent; {where}")
        elif btd is not None and label == btd.provenance.source_id:
            box = btd.bbox
            lines.append(
                f"- [{label}] split-window BTD map, north up, west {box.west:.2f} east "
                f"{box.east:.2f} south {box.south:.2f} north {box.north:.2f}"
            )
        else:
            lines.append(f"- [{label}] image")
    return "\n".join(lines)


def _task_block(situation: Situation) -> str:
    if situation.official_valid_now():
        modes = "OFFICIAL or WIDENED (an official polygon is in force now)"
    elif situation.official_layers:
        modes = "OFFICIAL, WIDENED or HYPOTHESIS (official polygons exist only as forecasts)"
    else:
        modes = "HYPOTHESIS only (no official polygon exists)"
    top_ft = situation.official_top_ft()
    top_rule = f"top_fl >= {math.ceil(top_ft / 100)}, " if top_ft is not None else ""
    source_ids = ", ".join(sorted(situation.source_ids())) or "none"
    discrepancy_ids = ", ".join(d.id for d in situation.discrepancies) or "none"
    return (
        "TASK\n"
        f"Allowed modes now: {modes}.\n"
        f"Limits: {top_rule}base_fl < top_fl, sector <= {MAX_SECTOR_WIDTH_DEG:.0f} deg, "
        f"extent_km <= {MAX_PLUME_EXTENT_KM:.0f}, "
        f"{MIN_HORIZON_H:.0f} <= horizon_h <= {MAX_HORIZON_H:.0f}.\n"
        f"{_hypothesis_rule(situation)}"
        f"Source ids you may cite: {source_ids}.\n"
        f"Discrepancy ids to explain: {discrepancy_ids}.\n"
        "Weigh what is uncertain before you choose the mode, explain every discrepancy in "
        "disagreements_explained, write no times or dates, and return only the JSON object."
    )


def _hypothesis_rule(situation: Situation) -> str:
    """The task line for ``_hypothesis_problems``, while HYPOTHESIS is an allowed mode."""
    vona = _recent_ash_vona(situation)
    if vona is None or situation.official_valid_now():
        return ""
    floor_fl = _vona_floor_fl(vona)
    top = f"top_fl >= {floor_fl}, " if floor_fl is not None else ""
    return (
        f"{_vona_name(vona)} reports ash, so a HYPOTHESIS needs {top}extent_km > 0 and two "
        "different bearings.\n"
    )


def _kind(record: Sigmet | Vona | VaacAdvisory) -> str:
    if isinstance(record, Sigmet):
        return "SIGMET" if record.observed is not False else "SIGMET forecast polygon"
    if isinstance(record, Vona):
        return "VONA"
    return f"VAA from VAAC {record.vaac.value}"


def _observed_at(record: Sigmet | Vona | VaacAdvisory) -> datetime:
    if isinstance(record, Sigmet):
        return record.observed_at or record.provenance.issued_at or record.valid_from
    if isinstance(record, Vona):
        return record.issued_at
    return record.observation.valid_at if record.observation is not None else record.issued_at


def _age(then: datetime, now: datetime) -> str:
    minutes = round(timeutil.minutes_between(then, now))
    if minutes < 0:
        return f"starts in {-minutes} min"
    return f"observation age {minutes} min"


def _band(base_ft: int, top_ft: int) -> str:
    base = "SFC" if base_ft <= 0 else f"FL{ft_to_fl(base_ft):03d}"
    return f"{base}/FL{ft_to_fl(top_ft):03d}"
