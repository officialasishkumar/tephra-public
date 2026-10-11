"""The backtest report: one lite-tier model call writes the prose, code writes everything else.

The model gets a digest of ``scorecard.json`` with every figure already formatted, and may only
repeat those figures. A validator rejects any number that is not in the digest, any time or date
and any unknown case. One repair is allowed; after that there is no report: the scorecard
stands alone and the error says ``AI UNAVAILABLE`` (no template stands in for the model).
"""

import re
from functools import cache
from pathlib import Path
from typing import Final

from pydantic import Field

from tephra.agents.llm import LlmBackend, LlmPart
from tephra.agents.validators import clock_problems, first_problems
from tephra.backtest.models import BacktestScorecard, CaseScore, LeadSummary, Summary
from tephra.config import DISCLAIMER, NO_MODEL_LABEL, PROJECT_ROOT
from tephra.models import TephraModel

__all__ = ["ReportUnavailable", "build_report", "render_digest", "validate_prose", "write_report"]

PROMPT_PATH: Final = PROJECT_ROOT / "tephra" / "agents" / "prompts" / "backtest.md"
AI_UNAVAILABLE: Final = "AI UNAVAILABLE"
HEADLINE_TAU: Final = 0.9
_NUMBER: Final = re.compile(r"\d+(?:\.\d+)?")
PROSE_MAX_CHARS: Final = 900


class ReportUnavailable(RuntimeError):
    """No report was written; the message starts with ``AI UNAVAILABLE``."""


class CaseNote(TephraModel):
    case_id: str
    arm: str
    text: str = Field(max_length=PROSE_MAX_CHARS)


class ReportProse(TephraModel):
    summary: str = Field(max_length=PROSE_MAX_CHARS)
    cases: list[CaseNote]
    limits: str = Field(max_length=PROSE_MAX_CHARS)


# --- the digest the model sees ------------------------------------------------------------


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _points(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f} points"


def _ratio(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}x"


def _minutes(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0f} min"


def _headline_lead(leads: list[LeadSummary]) -> LeadSummary | None:
    return next((lead for lead in leads if lead.tau == HEADLINE_TAU), None)


def _line(summary: Summary, lead: LeadSummary | None) -> str:
    parts = [
        f"ticks scored {summary.ticks_scored}",
        f"coverage {_pct(summary.coverage_mean)}",
        f"official-only coverage {_pct(summary.coverage_official_mean)}",
        f"gain {_points(summary.coverage_gain_mean)}",
        f"over-warning {_pct(summary.overwarn_mean)}",
        f"excess {_ratio(summary.excess_vs_official_mean)}",
        f"vertical hit {_pct(summary.vertical_hit_rate)}",
    ]
    if lead is not None:
        parts += [
            f"polygons {lead.n_footprints}",
            f"missed {lead.n_missed}",
            f"covered before the official area {lead.n_covered_before_official}",
            f"median incremental lead {_minutes(lead.median_min)}",
            f"p90 incremental lead {_minutes(lead.p90_min)}",
        ]
    return "; ".join(parts)


def _case_line(case: CaseScore) -> str:
    return (
        f"case {case.case_id} arm {case.arm} ({case.region}; volcanoes {len(case.volcano_ids)}; "
        f"floor violations {case.floor_violations}; input leaks {case.input_leaks}): "
        f"{_line(case.summary, _headline_lead(case.lead))}"
    )


def render_digest(scorecard: BacktestScorecard) -> str:
    """Every figure the prose may use, formatted as it must be written."""
    lines = [
        f"Step: {scorecard.step_min} minutes. Cases run: {len(scorecard.cases)}.",
        f"Floor violations in total {scorecard.floor_violations}; "
        f"input leaks in total {scorecard.input_leaks}.",
    ]
    for arm, summary in scorecard.overall.items():
        leads = _headline_lead(scorecard.overall_lead.get(arm, []))
        lines.append(f"Overall arm {arm}: {_line(summary, leads)}")
    lines += [_case_line(case) for case in scorecard.cases]
    return "\n".join(lines)


# --- checks -----------------------------------------------------------------------------


def _numbers(text: str) -> set[str]:
    return {f"{float(token):g}" for token in _NUMBER.findall(text)}


def validate_prose(prose: ReportProse, scorecard: BacktestScorecard) -> list[str]:
    """Code-written problems with the prose; empty means accepted."""
    allowed = _numbers(render_digest(scorecard)) | _numbers(
        " ".join(case.case_id for case in scorecard.cases)
    )
    texts = [("summary", prose.summary), ("limits", prose.limits)]
    texts += [(f"cases[{note.case_id}]", note.text) for note in prose.cases]
    problems: list[str] = []
    for name, text in texts:
        problems += clock_problems(text, name)
        extra = sorted(_numbers(text) - allowed)
        if extra:
            problems.append(f"{name.upper()} HAS NUMBERS NOT IN THE INPUT: {', '.join(extra)}")
    expected = [(case.case_id, case.arm) for case in scorecard.cases]
    if [(note.case_id, note.arm) for note in prose.cases] != expected:
        problems.append("CASES MUST HAVE ONE NOTE PER CASE RUN, IN THE INPUT ORDER, WITH ITS ARM")
    return problems


# --- the report -------------------------------------------------------------------------


@cache
def _system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _stub_prose(scorecard: BacktestScorecard) -> ReportProse:
    """Offline test answer built from the digest figures (labelled NO MODEL when rendered)."""
    cases = [
        CaseNote(
            case_id=case.case_id,
            arm=case.arm,
            text=f"Coverage {_pct(case.summary.coverage_mean)}, gain "
            f"{_points(case.summary.coverage_gain_mean)}.",
        )
        for case in scorecard.cases
    ]
    return ReportProse(
        summary=f"Cases run: {len(scorecard.cases)}.",
        cases=cases,
        limits="The later official area has its own lag and shares inputs with the zone.",
    )


async def build_report(scorecard: BacktestScorecard, llm: LlmBackend) -> str:
    """The REPORT.md text; raises :class:`ReportUnavailable` when the model gives no valid prose."""
    system = _system_prompt()
    parts = [LlmPart.of_text(render_digest(scorecard))]
    problems: list[str] = []
    for attempt in range(2):
        prose, call = await llm.structured(
            tier="lite",
            system=system,
            parts=parts,
            schema=ReportProse,
            stub=lambda: _stub_prose(scorecard),
        )
        if prose is None:
            reason = call.error or "no usable model output"
            raise ReportUnavailable(f"{AI_UNAVAILABLE}: {reason}")
        problems = validate_prose(prose, scorecard)
        if not problems:
            return _render(scorecard, prose, llm.model_id("lite"), llm.name == "stub")
        if attempt == 0:
            parts = [*parts, LlmPart.of_text(_repair_text(problems, call.raw_text or ""))]
    reason = "; ".join(first_problems(problems, 3))
    raise ReportUnavailable(f"{AI_UNAVAILABLE}: the report failed its checks ({reason})")


def _repair_text(problems: list[str], previous: str) -> str:
    listed = "\n".join(f"- {problem}" for problem in first_problems(problems))
    return (
        f"Code rejected your previous answer for these reasons:\n{listed}\n"
        f"Your previous answer was:\n{previous[:2000]}\n"
        "Return a corrected JSON object that fixes every reason."
    )


def _render(scorecard: BacktestScorecard, prose: ReportProse, model_id: str, stub: bool) -> str:
    label = f"{NO_MODEL_LABEL}: test text" if stub else f"prose written by {model_id}"
    lines = [
        "# TEPHRA backtest report",
        "",
        f"_{DISCLAIMER}. Figures are computed by code from `scorecard.json`; {label}._",
        "",
        "## Summary",
        "",
        prose.summary,
        "",
        "## Headline table",
        "",
        "| Case | Arm | Ticks scored | Coverage | Official-only | Gain | Over-warning | Excess "
        "| Median lead | Missed | Vertical hit |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
        *(_row(case) for case in scorecard.cases),
        "",
        "## Cases",
        "",
    ]
    for note in prose.cases:
        lines += [f"### {note.case_id} (arm {note.arm})", "", note.text, ""]
    lines += ["## Method and limits", "", prose.limits, ""]
    lines += [f"- {caveat}" for caveat in scorecard.caveats]
    return "\n".join(lines) + "\n"


def _row(case: CaseScore) -> str:
    lead = _headline_lead(case.lead)
    s = case.summary
    cells = [
        case.case_id,
        case.arm,
        str(s.ticks_scored),
        _pct(s.coverage_mean),
        _pct(s.coverage_official_mean),
        _points(s.coverage_gain_mean),
        _pct(s.overwarn_mean),
        _ratio(s.excess_vs_official_mean),
        _minutes(lead.median_min if lead else None),
        f"{lead.n_missed} of {lead.n_footprints}" if lead else "n/a",
        _pct(s.vertical_hit_rate),
    ]
    return "| " + " | ".join(cells) + " |"


def write_report(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
