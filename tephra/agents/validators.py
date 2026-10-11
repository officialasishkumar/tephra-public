"""Code checks on the Exposure Planner's decision and the Dispatch Drafter's text.

Each check returns a list of upper-case, code-written problems (empty = accepted). The
agents send these back to the model for one repair; a plan or draft that still fails is
reported as AI UNAVAILABLE and nothing is substituted. Nothing here asks a model anything:
what counts as a safe action, a known place or an honest number is decided by these rules
alone.
"""

import re
from collections.abc import Iterable
from typing import Final

from tephra.config import ADVISORY_BODY_MAX_CHARS, AIRLINE_NAME
from tephra.geo.units import ft_to_fl
from tephra.models import (
    ALLOWED_ACTIONS,
    ActionKind,
    DraftText,
    ExposedFlight,
    PlannedAction,
    PlannerContext,
    PlannerDecision,
    PlumeMode,
    RerouteOption,
    RerouteStatus,
)

MAX_LEVEL_FL: Final = 600
"""Bound on any level a decision names; the highest level TEPHRA proposes is the operator
policy's ``planner.max_change_level_fl`` (``PlannerContext.max_change_level_fl``)."""
COST_NOTE_MAX_CHARS: Final = 120
REASONING_MAX_CHARS: Final = 800

ZONE_TIME_PATTERN: Final = (
    r"(?<!\d)\d{4}\s?(?:UTC|GMT|Z|LT|LCL|LOCAL|WIB|WITA|WIT|JST|PHT|HRS)(?![A-Z])"
)
"""A clock time with a zone word ("1830 UTC", "0930UTC", "0521 local", "1830 HRS"), matched
ignoring case. VONAs print "2221 UTC (0521 local)", so a model quoting one writes a time;
the Plume Reader uses the same pattern."""

CLOCK_PATTERNS: Final[tuple[re.Pattern[str], ...]] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\d{8}/\d{4}Z?",
        r"\d{6}Z",
        r"\d{4}Z",
        r"(?<![\d/])\d{1,2}/\d{4}Z?(?!\d)",
        r"\d{1,2}:\d{2}",
        r"\d{4}-\d{2}-\d{2}",
        ZONE_TIME_PATTERN,
    )
)
"""The Plume Reader's timestamp patterns plus times with a zone word: a model never writes
a time or a date."""

ACTION_WORDS: Final[dict[ActionKind, tuple[str, ...]]] = {
    ActionKind.CONTINUE: ("CONTINUE",),
    ActionKind.MONITOR: ("MONITOR",),
    ActionKind.CHANGE_LEVEL: ("CLIMB", "DESCEND", "CHANGE LEVEL", "LEVEL CHANGE"),
    ActionKind.HOLD: ("HOLD",),
    ActionKind.DIVERT: ("DIVERT",),
    ActionKind.REROUTE: ("REROUTE",),
}
"""Words that name each action in an advisory body."""

_HYPOTHESIS_FORBIDDEN: Final = re.compile(
    r"(?<![A-Z0-9])(?:DIVER(?:T|SION)|CLIMB|DESCEN[DT]|CHANGE LEVEL|LEVEL CHANGE)[A-Z]*"
)
"""Diverting, climbing or descending in any inflection (DIVERTING, DIVERSION, DESCENT)."""

_VOCABULARY_TEXT: Final = """
ABLE ABOUT ABOVE ACFT ADVS AFTER AGAIN AHEAD ALERT ALLOW ALONG ALSO ALTN ALTNS AMEND
AMBER APCH APPLY AREA AREAS ASHES AVBL AVOID AWARE AWAY BAND BANDS BASE BASED BEEN
BEING BELOW BURN BURNS CABIN CALL CHECK CLEAR CLIMB CLOUD COMMS CONE CONES COST COSTS
CREW CREWS DATA DELAY DEST DIST DOWN DRIFT DUST EACH EARLY EAST EITHER ENGS ENTER ENTRY
ERUPT EVEN EXIT EXTRA FCST FIRST FLOW FROM FUEL FULL GIVE GIVEN GLOW GREEN HAVE HAZE
HELD HERE HIGH HOLD HOLDS HOUR HOURS INFO INTO ISSUE KEEP KNOWN LAST LATER
LEAVE LEFT LESS LEVEL LIGHT LIKE LIMIT LONG LOWER MAGMA MAIN MAKE MANY METAR MINUS
MNTN MODE MODEL MORE MOST MOVE MOVES MUST NEAR NEED NEXT NONE NORTH NOTAM NOTE NOTED
ODOR ODOUR ONLY ORDER OTHER OVER PASS PAST PLAN PLUME PLUS POINT POSN PRIOR RAIN RANGE
RATE READY REPLY RIGHT ROUTE RPRT RQST SAFE SAFER SEEN SEND SHALL SHOW SIDE SINCE
SMELL SMOKE SOME SOON SOUTH SPEED STAY STILL SUCH TAKE TEMPO THAN THAT THEIR THEM THEN
THERE THESE THEY THIS THOSE TIME TOPS TOTAL TRACK TURN TYPE UNIT UNTIL UPON UPPER
USED USING VAAC VALID VERY VIEW VONA WATCH WEST WHEN WHERE WHICH WHILE WIND WINDS WITH
WITHIN YOUR ZONE
"""
VOCABULARY: Final[frozenset[str]] = frozenset(_VOCABULARY_TEXT.split())
"""Plain English and ACARS words of four or five capitals that are not places.

No word here may be an ICAO location id or a place name, or an invented place could hide
behind it: HEAT (Assiut) and SAME (Mendoza) are station ids, and TOKYO is a city."""

_TECHNIQUE: Final = re.compile(
    r"\b(IDLE|THRUST|POWER (?:TO|BACK)|AUTOTHRUST|AUTOTHROTTLE|ESCAPE MANOEUVRE|ESCAPE MANEUVER)\b"
    r"|\bDESCEND\w*\s+(?:\d+\s*(?:DEG\w*)?\s*)?TURN\b"
    r"|\b180\s*(?:DEG\w*|TURN|-TURN)\b"
    r"|\bU-?TURN\b"
)
"""Engine handling and ash-escape manoeuvres (thrust to idle, a descending 180-degree turn).
Matched on upper-case text. TURN, REVERSE TRACK, HEADING 180 and FL180 stay legal: the
route and level are dispatch's to advise, an encounter is the crew's QRH."""
TECHNIQUE_PROBLEM: Final = (
    "BODY GIVES ENGINE-HANDLING OR ESCAPE TECHNIQUE: CREW FOLLOWS ITS QRH AND OPERATOR"
    " PROCEDURES; DISPATCH ADVISES ROUTE ONLY"
)

_CAPS_WORD = re.compile(r"(?<![A-Za-z0-9])[A-Z]{4,5}(?![A-Za-z0-9])")
_ALPHA_WORD = re.compile(r"[A-Z]+")
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
_COORDINATE = re.compile(r"(?<![A-Z0-9])\d{4}[NS]\d{5}[EW](?![A-Z0-9])")
_VAR = re.compile(r"(?<![A-Z0-9])VAR(?![A-Z0-9])")
_CLOSED = re.compile(r"(?<![A-Z])CLOS(?:E|ED|ES|ING|URE)(?![A-Z])")


def allowed_actions(mode: PlumeMode) -> list[ActionKind]:
    allowed = ALLOWED_ACTIONS[mode]
    return [action for action in ActionKind if action in allowed]


def band_clears_hazard(fl_min: int, fl_max: int, *, ctx: PlannerContext) -> bool:
    """True when the whole FL band lies outside the hazard band widened by the margin."""
    below = fl_max * 100 < ctx.hazard_base_ft - ctx.vertical_margin_ft
    above = fl_min * 100 > ctx.hazard_top_ft + ctx.vertical_margin_ft
    return below or above


def reroute_of(decision: PlannerDecision, ctx: PlannerContext) -> RerouteOption | None:
    """The option a REROUTE decision names, if the context has it."""
    if decision.reroute_id is None:
        return None
    return next((option for option in ctx.reroutes if option.id == decision.reroute_id), None)


def technique_problems(upper: str) -> list[str]:
    """The ban on engine handling and escape technique, for drafts and dispatcher edits."""
    return [TECHNIQUE_PROBLEM] if _TECHNIQUE.search(upper) else []


def clock_problems(text: str, field: str) -> list[str]:
    return [
        f"{field} CONTAINS A CLOCK TIME OR DATE ({match.group(0)}); TIMES ARE WRITTEN BY CODE"
        for pattern in CLOCK_PATTERNS
        if (match := pattern.search(text)) is not None
    ]


# --- planner decision -------------------------------------------------------------------


def validate_decision(decision: PlannerDecision, ctx: PlannerContext) -> list[str]:
    problems: list[str] = []
    # The mode decides what is safe; the context's own list may only narrow it.
    allowed = [a for a in allowed_actions(ctx.plume_mode) if a in ctx.allowed_actions]
    if decision.action not in allowed:
        listed = ", ".join(action.value for action in allowed)
        problems.append(
            f"ACTION {decision.action.value} NOT ALLOWED IN {ctx.plume_mode.value} MODE"
            f" (ALLOWED: {listed})"
        )
    match decision.action:
        case ActionKind.CHANGE_LEVEL:
            problems.extend(_change_level_problems(decision, ctx))
        case ActionKind.HOLD:
            problems.extend(_hold_problems(decision, ctx))
        case ActionKind.DIVERT:
            problems.extend(_divert_problems(decision, ctx))
        case ActionKind.REROUTE:
            problems.extend(_reroute_problems(decision, ctx))
        case ActionKind.CONTINUE:
            problems.extend(_continue_problems(ctx))
        case ActionKind.MONITOR:
            pass
    if decision.action is not ActionKind.REROUTE and decision.reroute_id is not None:
        problems.append("reroute_id BELONGS ONLY TO A REROUTE")
    reasoning = decision.reasoning.strip()
    if not reasoning:
        problems.append("REASONING IS EMPTY")
    elif len(reasoning) > REASONING_MAX_CHARS:
        problems.append(f"REASONING LONGER THAN {REASONING_MAX_CHARS} CHARACTERS")
    problems.extend(clock_problems(reasoning, "REASONING"))
    return problems


def _change_level_problems(decision: PlannerDecision, ctx: PlannerContext) -> list[str]:
    fl_min, fl_max = decision.change_level_fl_min, decision.change_level_fl_max
    if fl_min is None or fl_max is None:
        return ["CHANGE_LEVEL NEEDS change_level_fl_min AND change_level_fl_max"]
    if not 0 <= fl_min <= fl_max <= ctx.max_change_level_fl:
        return [
            f"CHANGE_LEVEL BAND FL{fl_min}-FL{fl_max} MUST BE ORDERED AND AT OR BELOW"
            f" FL{ctx.max_change_level_fl}"
        ]
    if not band_clears_hazard(fl_min, fl_max, ctx=ctx):
        return [
            f"CHANGE_LEVEL BAND FL{fl_min}-FL{fl_max} DOES NOT CLEAR THE HAZARD"
            f" {_hazard_with_margin(ctx)} (BAND PLUS MARGIN)"
        ]
    return []


def _hold_problems(decision: PlannerDecision, ctx: PlannerContext) -> list[str]:
    hold_fl = decision.hold_fl
    if hold_fl is None:
        return ["HOLD NEEDS hold_fl"]
    if not 0 < hold_fl <= MAX_LEVEL_FL:
        return [f"HOLD LEVEL FL{hold_fl} OUT OF RANGE"]
    if ctx.flight.inside_now and not band_clears_hazard(hold_fl, hold_fl, ctx=ctx):
        return [
            f"HOLD AT PRESENT POSITION IS INSIDE THE HAZARD NOW: FL{hold_fl} IS WITHIN"
            f" {_hazard_with_margin(ctx)} (BAND PLUS MARGIN); CHOOSE ANOTHER ACTION"
        ]
    present = ctx.flight.alt_baro_ft
    if present is None or hold_fl == ft_to_fl(present):
        return []
    # Holding at another level means climbing or descending to it first.
    if ctx.plume_mode is PlumeMode.HYPOTHESIS:
        return [
            f"HOLD AT THE PRESENT LEVEL FL{ft_to_fl(present)} IN HYPOTHESIS MODE:"
            " NO LEVEL CHANGE WITHOUT A VALID OFFICIAL PRODUCT"
        ]
    if hold_fl > ctx.max_change_level_fl:
        return [
            "HOLD AT ANOTHER LEVEL IS A LEVEL CHANGE AND MUST BE AT OR BELOW"
            f" FL{ctx.max_change_level_fl}"
        ]
    return []


def _continue_problems(ctx: PlannerContext) -> list[str]:
    low_ft, high_ft = ctx.flight.aircraft_band_ft
    below = high_ft < ctx.hazard_base_ft - ctx.vertical_margin_ft
    above = low_ft > ctx.hazard_top_ft + ctx.vertical_margin_ft
    if below or above:
        return []
    return [
        "CONTINUE ONLY WHEN THE PRESENT AND SELECTED LEVELS CLEAR THE HAZARD"
        f" {_hazard_with_margin(ctx)} (BAND PLUS MARGIN)"
    ]


def _divert_problems(decision: PlannerDecision, ctx: PlannerContext) -> list[str]:
    icao = decision.alternate_icao
    if not icao:
        return ["DIVERT NEEDS alternate_icao"]
    candidate = next((alt for alt in ctx.alternates if alt.icao == icao), None)
    if candidate is None:
        listed = ", ".join(alt.icao for alt in ctx.alternates) or "NONE"
        return [f"ALTERNATE {icao} IS NOT ONE OF THE LISTED ALTERNATES ({listed})"]
    if not candidate.check.ok:
        reasons = "; ".join(candidate.check.reasons) or "NOT ACCEPTABLE"
        return [f"ALTERNATE {icao} FAILED THE TAF AND CONE SCREEN ({reasons})"]
    if candidate.check.taf_source_id is None:
        return [f"ALTERNATE {icao} HAS NO TAF"]
    return []


def _reroute_problems(decision: PlannerDecision, ctx: PlannerContext) -> list[str]:
    if decision.reroute_id is None:
        return ["REROUTE NEEDS reroute_id"]
    option = reroute_of(decision, ctx)
    if option is None:
        listed = ", ".join(o.id for o in ctx.reroutes if o.status is RerouteStatus.OK) or "NONE"
        return [f"REROUTE {decision.reroute_id} IS NOT ONE OF THE LISTED OPTIONS ({listed})"]
    problems: list[str] = []
    if option.status is not RerouteStatus.OK:
        problems.append(f"REROUTE {option.id} IS NOT AVAILABLE ({option.status.value})")
    if any(
        value is not None
        for value in (
            decision.change_level_fl_min,
            decision.change_level_fl_max,
            decision.hold_fl,
            decision.alternate_icao,
        )
    ):
        problems.append("REROUTE TAKES NO LEVEL, HOLD OR ALTERNATE FIELDS")
    return problems


def _hazard_with_margin(ctx: PlannerContext) -> str:
    low = ft_to_fl(max(0, ctx.hazard_base_ft - ctx.vertical_margin_ft))
    high = ft_to_fl(ctx.hazard_top_ft + ctx.vertical_margin_ft)
    return f"FL{low}-FL{high}"


# --- drafter text -----------------------------------------------------------------------


def validate_draft(draft: DraftText, *, ctx: PlannerContext, plan: PlannedAction) -> list[str]:
    decision = plan.decision
    problems: list[str] = []
    if decision.action not in allowed_actions(ctx.plume_mode):
        problems.append(
            f"ACTION {decision.action.value} NOT ALLOWED IN {ctx.plume_mode.value} MODE"
        )
    if decision.action is ActionKind.DIVERT:
        problems.extend(_divert_draft_problems(decision.alternate_icao, ctx))
    if decision.action is ActionKind.REROUTE and reroute_of(decision, ctx) is None:
        problems.append(f"REROUTE {decision.reroute_id} IS NOT A LISTED OPTION")
    problems.extend(_body_problems(draft.body, ctx=ctx, plan=plan))
    problems.extend(_cost_note_problems(draft.cost_note, ctx=ctx, plan=plan))
    return problems


def _divert_draft_problems(icao: str | None, ctx: PlannerContext) -> list[str]:
    candidate = next((alt for alt in ctx.alternates if alt.icao == icao), None)
    if candidate is None:
        return [f"ALTERNATE {icao} IS NOT A LISTED ALTERNATE"]
    if candidate.check.taf_source_id is None:
        return [f"ALTERNATE {icao} HAS NO TAF"]
    if not candidate.check.ok:
        return [f"ALTERNATE {icao} FAILED THE TAF AND CONE SCREEN"]
    return []


def _body_problems(body: str, *, ctx: PlannerContext, plan: PlannedAction) -> list[str]:
    text = body.strip()
    if not text:
        return ["BODY IS EMPTY"]
    problems: list[str] = []
    if len(text) > ADVISORY_BODY_MAX_CHARS:
        problems.append(f"BODY LONGER THAN {ADVISORY_BODY_MAX_CHARS} CHARACTERS ({len(text)})")
    if not _printable_ascii(text, allow_newline=True):
        problems.append("BODY MUST BE PRINTABLE ASCII")
    if text != text.upper():
        problems.append("BODY MUST BE UPPER CASE")
    upper = text.upper()
    problems.extend(_action_word_problems(upper, ctx=ctx, plan=plan))
    if _CLOSED.search(upper):
        problems.append("BODY MUST NOT SAY CLOSED: TEPHRA WRITES COMPANY ADVISORIES, NOT NOTAMS")
    problems.extend(technique_problems(upper))
    if not _VAR.search(upper):
        problems.append("BODY MUST ASK THE CREW FOR A VOLCANIC ACTIVITY REPORT (VAR)")
    problems.extend(_flight_name_problems(upper, ctx.flight))
    problems.extend(clock_problems(text, "BODY"))
    problems.extend(_place_problems(upper, "BODY", ctx=ctx, plan=plan))
    problems.extend(_number_problems(text, "BODY", ctx=ctx, plan=plan))
    return problems


def _flight_name_problems(upper: str, flight: ExposedFlight) -> list[str]:
    """The fictional airline's advisory names its RFA flight, never the real aircraft's
    callsign it stands in for."""
    problems: list[str] = []
    if not _has_phrase(upper, flight.proxy_flight):
        problems.append(f"BODY MUST NAME THE FLIGHT AS {flight.proxy_flight}")
    callsign = (flight.callsign or "").upper()
    if callsign and callsign != flight.proxy_flight and _has_phrase(upper, callsign):
        problems.append(f"BODY MUST NOT NAME THE ADS-B CALLSIGN {callsign}")
    return problems


def _cost_note_problems(note: str, *, ctx: PlannerContext, plan: PlannedAction) -> list[str]:
    text = note.strip()
    problems: list[str] = []
    if "\n" in text or "\r" in text:
        problems.append("COST NOTE MUST BE ONE LINE")
    if len(text) > COST_NOTE_MAX_CHARS:
        problems.append(f"COST NOTE LONGER THAN {COST_NOTE_MAX_CHARS} CHARACTERS")
    if not _printable_ascii(text, allow_newline=False):
        problems.append("COST NOTE MUST BE PRINTABLE ASCII")
    problems.extend(clock_problems(text, "COST NOTE"))
    # The note may be mixed case; a lower-case place name is still a place.
    problems.extend(_place_problems(text.upper(), "COST NOTE", ctx=ctx, plan=plan))
    problems.extend(_number_problems(text, "COST NOTE", ctx=ctx, plan=plan))
    return problems


def _action_word_problems(upper: str, *, ctx: PlannerContext, plan: PlannedAction) -> list[str]:
    decision = plan.decision
    problems: list[str] = []
    words = ACTION_WORDS[decision.action]
    if not any(_has_phrase(upper, word) for word in words):
        problems.append(f"BODY MUST STATE THE ACTION ({' OR '.join(words)})")
    if ctx.plume_mode is PlumeMode.HYPOTHESIS:
        problems.extend(
            f"BODY MUST NOT ADVISE {word} WITHOUT A VALID OFFICIAL PRODUCT (HYPOTHESIS MODE)"
            for word in dict.fromkeys(_HYPOTHESIS_FORBIDDEN.findall(upper))
        )
    match decision.action:
        case ActionKind.DIVERT if decision.alternate_icao and not _has_phrase(
            upper, decision.alternate_icao
        ):
            problems.append(f"BODY MUST NAME THE ALTERNATE {decision.alternate_icao}")
        case ActionKind.CHANGE_LEVEL if not any(
            _has_flight_level(upper, fl)
            for fl in (decision.change_level_fl_min, decision.change_level_fl_max)
        ):
            problems.append("BODY MUST STATE THE NEW FLIGHT LEVEL BAND")
        case ActionKind.HOLD if not _has_flight_level(upper, decision.hold_fl):
            problems.append("BODY MUST STATE THE HOLDING FLIGHT LEVEL")
        case ActionKind.REROUTE:
            problems.extend(_route_text_problems(upper, reroute_of(decision, ctx)))
        case _:
            pass
    return problems


def _route_text_problems(upper: str, option: RerouteOption | None) -> list[str]:
    """The body carries the route string verbatim and no coordinate that is not in it."""
    if option is None:
        return []
    problems: list[str] = []
    if option.route_string not in upper:
        problems.append(f"BODY MUST CONTAIN THE ROUTE STRING VERBATIM: {option.route_string}")
    written = set(_COORDINATE.findall(option.route_string))
    if stray := sorted(set(_COORDINATE.findall(upper)) - written):
        problems.append(f"BODY HAS COORDINATES NOT IN THE ROUTE STRING: {', '.join(stray)}")
    return problems


def _place_problems(
    text: str, field: str, *, ctx: PlannerContext, plan: PlannedAction
) -> list[str]:
    known = VOCABULARY | input_words(ctx, plan)
    unknown = sorted({word for word in _CAPS_WORD.findall(text) if word not in known})
    if not unknown:
        return []
    return [
        f"{field} USES {', '.join(unknown)}: ONLY LISTED ICAO CODES AND PLAIN WORDS;"
        " NO INVENTED PLACES OR WAYPOINTS"
    ]


def _number_problems(
    text: str, field: str, *, ctx: PlannerContext, plan: PlannedAction
) -> list[str]:
    allowed = input_numbers(ctx, plan)
    invented = sorted({token for token in _number_tokens(text) if token not in allowed}, key=float)
    if not invented:
        return []
    return [f"{field} HAS NUMBERS NOT IN THE INPUT: {', '.join(invented)}"]


# --- what the input contains ------------------------------------------------------------


def input_words(ctx: PlannerContext, plan: PlannedAction) -> set[str]:
    """Capitalised words the drafter was given: ICAO codes, names and code-written lines."""
    words = {alternate.icao for alternate in ctx.alternates}
    for text in _input_texts(ctx, plan):
        words.update(_ALPHA_WORD.findall(text.upper()))
    return words


def input_numbers(ctx: PlannerContext, plan: PlannedAction) -> set[str]:
    """Every number the drafter may print, in normalised form (FL and feet both count)."""
    flight = ctx.flight
    decision = plan.decision
    heights_ft = [
        ctx.hazard_base_ft,
        ctx.hazard_top_ft,
        ctx.vertical_margin_ft,
        max(0, ctx.hazard_base_ft - ctx.vertical_margin_ft),
        ctx.hazard_top_ft + ctx.vertical_margin_ft,
        flight.alt_baro_ft,
        flight.nav_altitude_mcp_ft,
        *flight.aircraft_band_ft,
    ]
    levels_fl = [decision.change_level_fl_min, decision.change_level_fl_max, decision.hold_fl]
    values: list[float | None] = [
        flight.minutes_to_entry,
        round(ctx.confidence * 100),
        round(flight.gs_kt) if flight.gs_kt is not None else None,
        round(flight.track_deg) if flight.track_deg is not None else None,
    ]
    values += [v for ft in heights_ft if ft is not None for v in (ft, ft_to_fl(ft))]
    values += [v for fl in levels_fl if fl is not None for v in (fl, fl * 100)]
    for alternate in ctx.alternates:
        values += [round(alternate.distance_nm), round(alternate.bearing_deg)]
    numbers = {_normalise(value) for value in values if value is not None}
    for text in _input_texts(ctx, plan):
        numbers.update(_number_tokens(text))
    return numbers


def _input_texts(ctx: PlannerContext, plan: PlannedAction) -> list[str]:
    flight = ctx.flight
    texts = [AIRLINE_NAME, ctx.volcano_name, flight.proxy_flight, ctx.hold.formula]
    texts += [text for text in (flight.callsign, flight.type_icao) if text]
    for alternate in ctx.alternates:
        texts += [alternate.name, alternate.divert.formula, *alternate.check.reasons]
    if plan.fuel is not None:
        texts.append(plan.fuel.formula)
    option = reroute_of(plan.decision, ctx)
    if option is not None:
        texts += [
            option.route_string,
            option.note,
            option.wind_note or "",
            f"BUFFER {option.buffer_nm} NM",
            option.end_icao or "",
        ]
    return texts


def _number_tokens(text: str) -> set[str]:
    tokens = set()
    for raw in _NUMBER.findall(text):
        cleaned = raw.rstrip(",").replace(",", "")
        if cleaned:
            tokens.add(_normalise(float(cleaned)))
    return tokens


def _normalise(value: float) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else f"{number:g}"


def _has_phrase(upper: str, phrase: str) -> bool:
    return re.search(rf"(?<![A-Z0-9]){re.escape(phrase)}(?![A-Z0-9])", upper) is not None


def _has_flight_level(upper: str, fl: int | None) -> bool:
    return fl is not None and re.search(rf"\bFL\s?0*{fl}(?!\d)", upper) is not None


def _printable_ascii(text: str, *, allow_newline: bool) -> bool:
    return all((allow_newline and ch == "\n") or " " <= ch <= "~" for ch in text)


def first_problems(problems: Iterable[str], limit: int = 8) -> list[str]:
    """The first few problems: enough for a repair prompt without flooding it."""
    return list(problems)[:limit]
