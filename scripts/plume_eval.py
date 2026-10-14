# ruff: noqa: E501  (the prompts are the protocol's exact text; keep them verbatim)
"""Run the Plume Reader test protocol (research/10, section 5) and write a scorecard.

Arm I (images): for each case from ``scripts/make_plume_cases.py`` the model sees three Ash
RGB frames and one IR frame, the vent pixel and the VAA's FL180 wind; the advisory text is
withheld because it is the label. Arm T (texts): the Semeru SIGMET and VONA texts only.

Each case runs ``--runs`` times (default 3) and is scored on the majority answer:

1. Schema: every response parses and passes the code checks.
2. Existence: >= 8/10 cases right (the majority of runs says "ash" = ash_seen or "not ash"
   = anything else) and no quiet case returns ash_seen with high confidence.
3. Direction: on ash cases scored ash_seen, the 8-point drift or the bearing from the vent
   to the box centre is within 45 degrees of the bearing from the VAA vent to the VAA
   polygon centroid in >= 3 detected cases.
4. Stability: in >= 8/10 cases at least 2 of 3 runs agree on image_finding.
5. Arm T: the output names the direction disagreement between a SIGMET and the VONA and
   sets top_fl to at least the official top (FL150) from a text source. (research/13 showed
   the 25 Sep height difference is an ENVELOPE case, so naming it is reported, not required.)

Until every run of every case has a response, each verdict reads INCOMPLETE: a case that
has not been run is neither right nor wrong.

Every response is cached under ``evals/plume/results/raw/``, so a re-run spends no quota;
``--max-calls`` caps new calls (the free tier is reported at ~20/day for 3.8 Flash). A
failed call is reported and left for the next run. Needs GEMINI_API_KEY from a personal
Google AI Studio key. Run it yourself.

    uv run python scripts/plume_eval.py --arm I --max-calls 18
    uv run python scripts/plume_eval.py --arm T
    uv run python scripts/plume_eval.py --score-only
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from shapely.geometry import shape

from tephra.config import PROJECT_ROOT
from tephra.geo.units import bearing_diff_deg, compass_to_deg, initial_bearing_deg

ROOT = PROJECT_ROOT / "evals" / "plume"
CASES_DIR = ROOT / "cases"
ARM_T_DIR = ROOT / "arm_t"
RAW_DIR = ROOT / "results" / "raw"


def scorecard_json_path() -> Path:
    """``docs/evals/plume-scorecard.json`` beside ``ROOT``'s repository (``evals/plume``), so a
    test that moves ``ROOT`` moves the JSON with it and never writes into the repository."""
    return ROOT.parent.parent / "docs" / "evals" / "plume-scorecard.json"


SYSTEM_ARM_I = """You are the Plume Reader for an airline dispatch desk. You look at Himawari-9 images of one volcano and say only what the images show.
Image conventions: north is up. The red triangle marks the volcano vent. White or green lines are coastlines. A thin white vertical line is a meridian. Text in the top-left corner is a timestamp; ignore it.
Image types: "Ash RGB" (R = 12.3-10.4 micron difference, G = 10.4-8.6 micron difference, B = 10.4 micron brightness temperature). Ash often looks pink, red or orange but its colour changes with latitude, time of day and what is underneath; low water cloud can look similar in a single frame. "IR" is the 10.4 micron infrared image: brighter is colder.
You receive frames at T-20 min, T-10 min and T, plus one IR frame at T, the vent position, and upper winds.
Rules:
1. Report a plume only if a feature starts at or near the vent, or is consistent with drift from the vent along the given winds, AND it is visible in at least two of the three Ash RGB frames.
2. If met cloud covers the area downwind of the vent, answer "obscured_by_met_cloud". If you cannot tell, answer "cannot_tell". Never guess a plume to be helpful.
3. Give the plume as a box in the LAST frame, [ymin, xmin, ymax, xmax] normalised 0-1000. Do not convert to degrees or kilometres; code will do that.
4. Do not estimate plume height from the image. Set top_fl to null unless a text source gives it; this test gives none.
5. List every input you used in sources, by its id.
Return only JSON that matches the schema."""

SYSTEM_ARM_T = """You are the Plume Reader for an airline dispatch desk. You receive official volcanic-ash texts for one volcano: VA SIGMETs (issued by the meteorological watch office, usually copying the VAAC advisory) and a VONA (issued by the volcano observatory). There are no images: set image_finding to "cannot_tell", frames_with_feature to [] and plume_box_2d to [].
Rules:
1. Compare the sources field by field (existence, height, direction, extent, timing) and list every disagreement with both source ids and a short note. A value inside another source's cautious range is not a contradiction; say "inside the envelope" in the note.
2. "Ash-cloud is not observed" means the observer could not see ash (night, cloud); it is not evidence that ash is absent.
3. top_fl must be the highest official top in the texts, never lower; set top_fl_basis to "text_source".
4. drift_direction is the direction the most recent observation says the ash is moving toward.
5. Cite sources only by the ids given. Do not write any times.
Return only JSON that matches the schema."""

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "image_finding": {
            "type": "string",
            "enum": ["ash_seen", "no_ash_seen", "obscured_by_met_cloud", "cannot_tell"],
        },
        "frames_with_feature": {
            "type": "array",
            "items": {"type": "integer", "minimum": 1, "maximum": 3},
            "maxItems": 3,
        },
        "plume_box_2d": {
            "type": "array",
            "items": {"type": "integer", "minimum": 0, "maximum": 1000},
            "minItems": 0,
            "maxItems": 4,
            "description": "[ymin,xmin,ymax,xmax] in IMG-3, normalised 0-1000; "
            "empty unless image_finding is ash_seen",
        },
        "drift_direction": {
            "type": "string",
            "enum": ["N", "NE", "E", "SE", "S", "SW", "W", "NW", "none", "unclear"],
        },
        "top_fl": {"type": ["integer", "null"], "minimum": 0, "maximum": 600},
        "top_fl_basis": {"type": "string", "enum": ["text_source", "none"]},
        "horizon_h": {"type": "integer", "enum": [0, 3, 6]},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "confidence_reason": {"type": "string"},
        "sources": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "used_for": {
                        "type": "string",
                        "enum": ["existence", "position", "direction", "height", "timing"],
                    },
                },
                "required": ["id", "used_for"],
            },
        },
        "disagreements": {
            "type": "array",
            "maxItems": 6,
            "items": {
                "type": "object",
                "properties": {
                    "field": {
                        "type": "string",
                        "enum": ["existence", "height", "direction", "extent", "timing"],
                    },
                    "source_a": {"type": "string"},
                    "source_b": {"type": "string"},
                    "note": {"type": "string"},
                },
                "required": ["field", "source_a", "source_b", "note"],
            },
        },
    },
    "required": [
        "image_finding",
        "frames_with_feature",
        "plume_box_2d",
        "drift_direction",
        "top_fl",
        "top_fl_basis",
        "horizon_h",
        "confidence",
        "confidence_reason",
        "sources",
        "disagreements",
    ],
}

IMAGE_IDS = ["IMG-1", "IMG-2", "IMG-3", "IMG-4"]
IMAGE_FILES = [
    ("as_T-20.png", "Ash RGB T-20"),
    ("as_T-10.png", "Ash RGB T-10"),
    ("as_T.png", "Ash RGB T"),
    ("ir_T.png", "IR T"),
]


# --- model call ---------------------------------------------------------------------------

CALL_TIMEOUT_MS = 120_000


class Caller:
    """google-genai with a personal API key only (never Vertex AI, never ADC).

    Every call is one request with the protocol's exact settings. An SDK that cannot
    express them stops the run before any quota is spent, and a failed request is reported
    and skipped rather than retried with other settings.
    """

    def __init__(self, model: str, max_calls: int, pause_s: float) -> None:
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise SystemExit("GEMINI_API_KEY is not set (use a personal Google AI Studio key)")
        # The SDK reads GOOGLE_GENAI_USE_ENTERPRISE before GOOGLE_GENAI_USE_VERTEXAI.
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "FALSE"
        os.environ["GOOGLE_GENAI_USE_ENTERPRISE"] = "FALSE"
        from google import genai  # imported here so --score-only needs no SDK
        from google.genai import errors

        self._types = genai.types
        self._failures = (errors.APIError, errors.UnknownApiResponseError, httpx.HTTPError)
        try:
            self._types.GenerateContentConfig.model_validate(self._config(SYSTEM_ARM_I))
        except ValueError as exc:
            raise SystemExit(f"google-genai cannot express the protocol settings: {exc}") from exc
        # A request that never answers hung a whole run for 17 h; fail it and retry next run.
        self._client = genai.Client(
            api_key=key,
            vertexai=False,
            http_options=genai.types.HttpOptions(timeout=CALL_TIMEOUT_MS),
        )
        self.model = model
        self.calls_left = max_calls
        self._pause_s = pause_s

    def _config(self, system: str) -> dict[str, Any]:
        return {
            "system_instruction": system,
            "response_mime_type": "application/json",
            "response_json_schema": SCHEMA,
            "media_resolution": "MEDIA_RESOLUTION_HIGH",
            "thinking_config": {"thinking_level": "high"},
        }

    def call(self, system: str, parts: list[Any]) -> str:
        if self.calls_left <= 0:
            raise RuntimeError("call budget exhausted (--max-calls)")
        self.calls_left -= 1
        try:
            response = self._client.models.generate_content(
                model=self.model, contents=parts, config=self._config(system)
            )
        except self._failures as exc:
            raise RuntimeError(f"Gemini call failed: {exc}") from exc
        finally:
            time.sleep(self._pause_s)
        return response.text or ""

    def text(self, value: str) -> Any:
        return self._types.Part.from_text(text=value)

    def image(self, data: bytes) -> Any:
        return self._types.Part.from_bytes(data=data, mime_type="image/png")


def cached(path: Path, produce) -> str | None:
    if path.exists():
        return path.read_text()
    try:
        text = produce()
    except RuntimeError as exc:
        print(f"  {path.name}: {exc}")
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return text


# --- Arm I --------------------------------------------------------------------------------


def arm_i_parts(caller: Caller, case_dir: Path, case: dict[str, Any]) -> list[Any]:
    parts: list[Any] = []
    for image_id, (filename, label) in zip(IMAGE_IDS, IMAGE_FILES, strict=True):
        parts.append(caller.text(f"[{image_id}] {label}"))
        parts.append(caller.image((case_dir / filename).read_bytes()))
    vent = case.get("vent_px")
    if vent:
        parts.append(caller.text(f"[VENT] pixel x={vent[0]}, y={vent[1]} in IMG-3"))
    if case.get("wind_text"):
        parts.append(caller.text(f"[WIND] {case['wind_text'].removeprefix('WIND ')}"))
    return parts


def run_arm_i(caller: Caller | None, runs: int) -> dict[str, list[dict[str, Any] | None]]:
    """Answers per case (None: the response did not parse); runs not made yet are absent."""
    results: dict[str, list[dict[str, Any] | None]] = {}
    for case_dir in sorted(p for p in CASES_DIR.iterdir() if (p / "case.json").exists()):
        case = json.loads((case_dir / "case.json").read_text())
        answers = []
        for run in range(1, runs + 1):
            raw_path = RAW_DIR / f"I_{case['id']}_run{run}.json"
            if raw_path.exists():
                text: str | None = raw_path.read_text()
            elif caller is not None:
                parts = arm_i_parts(caller, case_dir, case)
                text = cached(raw_path, lambda parts=parts: caller.call(SYSTEM_ARM_I, parts))
            else:
                text = None
            if text is not None:
                answers.append(_parse(text))
        results[case["id"]] = answers
    return results


# --- Arm T --------------------------------------------------------------------------------


def arm_t_inputs() -> tuple[list[str], set[str]]:
    """The Semeru SIGMETs and the VONA, each under its own id; both kinds are required,
    because the arm scores the disagreement between them."""
    lines: list[str] = []
    ids: set[str] = set()
    for n, raw in enumerate(_semeru_sigmets(ARM_T_DIR / "sigmets.json")):
        source_id = f"SIGMET-{n + 1}"
        ids.add(source_id)
        lines.append(f"[{source_id}] {' '.join(raw.split())}")
    vona = "\n".join(
        line
        for line in (ARM_T_DIR / "vona.txt").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    )
    if not lines or not vona:
        raise SystemExit(
            "Arm T needs a Semeru SIGMET (make_plume_cases.py --arm-t-date) and the VONA text "
            f"pasted into {ARM_T_DIR / 'vona.txt'}"
        )
    ids.add("VONA-1")
    lines.append(f"[VONA-1] {' '.join(vona.split())}")
    return lines, ids


def _semeru_sigmets(path: Path) -> list[str]:
    try:
        records = json.loads(path.read_text() or "[]")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path} is not the isigmet JSON array: {exc}") from exc
    if not isinstance(records, list):
        raise SystemExit(f"{path} is not the isigmet JSON array")
    raws = (str(record.get("rawSigmet", "")) for record in records if isinstance(record, dict))
    return [raw for raw in raws if "SEMERU" in raw]


def run_arm_t(caller: Caller | None, runs: int) -> tuple[list[dict[str, Any] | None], set[str]]:
    """Answers (None: the response did not parse); runs not made yet are absent."""
    lines, ids = arm_t_inputs()
    answers = []
    for run in range(1, runs + 1):
        raw_path = RAW_DIR / f"T_semeru_run{run}.json"
        if raw_path.exists():
            text: str | None = raw_path.read_text()
        elif caller is not None:
            text = cached(
                raw_path, lambda: caller.call(SYSTEM_ARM_T, [caller.text("\n".join(lines))])
            )
        else:
            text = None
        if text is not None:
            answers.append(_parse(text))
    return answers, ids


# --- scoring ------------------------------------------------------------------------------


def _parse(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    try:
        value = json.loads(text.strip().removeprefix("```json").removesuffix("```"))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def schema_problems(answer: dict[str, Any] | None, allowed_ids: set[str], arm: str) -> list[str]:
    if answer is None:
        return ["no parseable JSON"]
    problems = [f"missing {key}" for key in SCHEMA["required"] if key not in answer]
    box = answer.get("plume_box_2d") or []
    if box and (
        len(box) != 4
        or not all(0 <= v <= 1000 for v in box)
        or box[0] >= box[2]
        or box[1] >= box[3]
    ):
        problems.append(f"bad box {box}")
    for source in answer.get("sources") or []:
        if source.get("id") not in allowed_ids:
            problems.append(f"unknown source id {source.get('id')!r}")
    if arm == "I" and answer.get("top_fl") is not None:
        problems.append("top_fl set from an image")
    return problems


def _majority(values: list[Any]) -> tuple[Any, int]:
    counts = Counter(v for v in values if v is not None)
    return counts.most_common(1)[0] if counts else (None, 0)


def _polygon_centroid(polygon: dict[str, Any]) -> tuple[float, float]:
    """Area centroid ``(lat, lon)`` of a GeoJSON polygon, taken in lon/lat as research/10
    says (a vertex mean would count the closing vertex twice)."""
    centroid = shape(polygon).centroid
    return centroid.y, centroid.x


def _verdict(passed: bool, missing: int, expected: int) -> str:
    if missing:
        return f"INCOMPLETE ({missing} of {expected} responses not run yet)"
    return "PASS" if passed else "FAIL"


def _box_bearing(answer: dict[str, Any], case: dict[str, Any]) -> float | None:
    """Bearing from the vent pixel to the box centre, assuming a north-up crop with square
    degrees per pixel (equirectangular), so east offsets shrink by cos(latitude)."""
    box, vent, size = answer.get("plume_box_2d"), case.get("vent_px"), case.get("image_size")
    lat = (case.get("vaa") or {}).get("volcano_lat")
    if not box or len(box) != 4 or not vent or not size or lat is None:
        return None
    width, height = size
    cy, cx = (box[0] + box[2]) / 2 / 1000 * height, (box[1] + box[3]) / 2 / 1000 * width
    dx, dy = (cx - vent[0]) * math.cos(math.radians(lat)), vent[1] - cy
    if dx == 0 and dy == 0:
        return None
    return math.degrees(math.atan2(dx, dy)) % 360


def score_arm_i(
    results: dict[str, list[dict[str, Any] | None]], runs: int
) -> tuple[list[str], dict[str, str], dict[str, Any]]:
    """Markdown rows, the verdict lines, and the same facts as JSON-safe values."""
    rows = [
        "| Case | Class | Call | Findings | Agree | Conf | Direction check | Schema |",
        "|---|---|---|---|---|---|---|---|",
    ]
    cases: list[dict[str, Any]] = []
    correct = stable = detected_dir_ok = 0
    quiet_high = schema_ok = 0
    for case_id, answers in results.items():
        case = json.loads((CASES_DIR / case_id / "case.json").read_text())
        ids = set(IMAGE_IDS) | {"VENT", "WIND"}
        problems = [p for a in answers for p in schema_problems(a, ids, "I")]
        schema_ok += sum(1 for a in answers if not schema_problems(a, ids, "I"))
        agree = _majority([a.get("image_finding") if a else None for a in answers])[1]
        stable += agree >= 2
        # Scored on "ash" (ash_seen) against "not ash" (anything else, unparseable included).
        votes = [a for a in answers if a and a.get("image_finding") == "ash_seen"]
        called_ash = 2 * len(votes) > len(answers)
        is_ash = case["class"] == "ash"
        correct += bool(answers) and called_ash == is_ash
        confidences = [str(a.get("confidence")) for a in votes]
        if not is_ash and called_ash and "high" in confidences:
            quiet_high += 1
        direction = "n/a"
        vaa = case.get("vaa") or {}
        if is_ash and called_ash and vaa.get("polygon") and vaa.get("volcano_lat") is not None:
            lat, lon = _polygon_centroid(vaa["polygon"])
            truth = initial_bearing_deg(vaa["volcano_lat"], vaa["volcano_lon"], lat, lon)
            drift = _majority([a.get("drift_direction") for a in votes])[0]
            drift_deg = compass_to_deg(drift) if drift else None
            box_deg = next((b for a in votes if (b := _box_bearing(a, case)) is not None), None)
            ok = any(
                d is not None and bearing_diff_deg(d, truth) <= 45 for d in (drift_deg, box_deg)
            )
            detected_dir_ok += ok
            direction = f"truth {truth:.0f} deg; drift {drift}; box {box_deg and round(box_deg)}: {'OK' if ok else 'MISS'}"
        call = ("ash" if called_ash else "not ash") if answers else "not run"
        findings = [str(a.get("image_finding")) if a else "unparseable" for a in answers]
        rows.append(
            f"| {case_id} | {case['class']} | {call} | {', '.join(findings) or '-'} | "
            f"{agree}/{len(answers)} | {', '.join(confidences) or '-'} | {direction} | "
            f"{'ok' if not problems else '; '.join(sorted(set(problems)))} |"
        )
        cases.append(
            {
                "id": case_id,
                "class": case["class"],
                "call": call,
                "findings": findings,
                "agree": agree,
                "runs": len(answers),
                "confidences": confidences,
                "direction": direction,
                "schema_problems": sorted(set(problems)),
            }
        )
    n = len(results)
    expected = n * runs
    missing = expected - sum(len(answers) for answers in results.values())
    facts: dict[str, Any] = {
        "cases": cases,
        "schema": {"clean": schema_ok, "expected": expected},
        "existence": {"correct": correct, "cases": n, "quiet_high_confidence_ash": quiet_high},
        "direction": {"detected_within_45_deg": detected_dir_ok},
        "stability": {"agreeing": stable, "cases": n},
        "missing": missing,
        "expected": expected,
    }
    verdict = {
        "schema": f"{schema_ok}/{expected} responses clean -> "
        + _verdict(schema_ok == expected, missing, expected),
        "existence": f"{correct}/{n} correct, {quiet_high} quiet case(s) with high-confidence ash -> "
        + _verdict(correct >= 8 and quiet_high == 0, missing, expected),
        "direction": f"{detected_dir_ok} detected case(s) within 45 deg -> "
        + _verdict(detected_dir_ok >= 3, missing, expected),
        "stability": f"{stable}/{n} cases with >= 2 runs agreeing -> "
        + _verdict(stable >= 8, missing, expected),
    }
    facts["verdicts"] = {key: value.rsplit(" -> ", 1)[1] for key, value in verdict.items()}
    return rows, verdict, facts


def _names(disagreement: dict[str, Any], field: str) -> bool:
    """A ``field`` disagreement between a SIGMET and the VONA (research/10 criterion 5)."""
    pair = {str(disagreement.get("source_a")), str(disagreement.get("source_b"))}
    return (
        disagreement.get("field") == field
        and "VONA-1" in pair
        and any(source.startswith("SIGMET-") for source in pair)
    )


def score_arm_t(
    answers: list[dict[str, Any] | None], ids: set[str], runs: int
) -> tuple[dict[str, str], dict[str, Any]]:
    """The verdict lines and the same facts as JSON-safe values."""
    clean = [a for a in answers if a and not schema_problems(a, ids, "T")]
    names_direction = sum(
        any(_names(d, "direction") for d in a.get("disagreements") or []) for a in clean
    )
    names_height = sum(
        any(_names(d, "height") for d in a.get("disagreements") or []) for a in clean
    )
    top_ok = sum(
        (a.get("top_fl") or 0) >= 150 and a.get("top_fl_basis") == "text_source" for a in clean
    )
    need = runs // 2 + 1
    verdict = _verdict(names_direction >= need and top_ok >= need, runs - len(answers), runs)
    lines = {
        "schema": f"{len(clean)}/{runs} responses clean",
        "SIGMET-VONA direction disagreement named": f"{names_direction}/{runs}",
        "SIGMET-VONA height difference named (reported only)": f"{names_height}/{runs}",
        "top_fl >= FL150 from text": f"{top_ok}/{runs}",
        "verdict": verdict,
    }
    facts = {
        "runs": runs,
        "answered": len(answers),
        "schema_clean": len(clean),
        "direction_disagreement_named": names_direction,
        "height_difference_named": names_height,
        "top_fl_from_text": top_ok,
        "verdict": verdict,
        "missing": runs - len(answers),
    }
    return lines, facts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run and score the Plume Reader protocol.")
    parser.add_argument("--arm", choices=["I", "T", "both"], default="both")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--model", default=os.environ.get("TEPHRA_MODEL", "gemini-3.8-flash"))
    parser.add_argument("--max-calls", type=int, default=18, help="new (uncached) calls allowed")
    parser.add_argument("--pause", type=float, default=4.0, help="seconds between calls")
    parser.add_argument("--score-only", action="store_true", help="score cached responses only")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    arm_i = args.arm in ("I", "both") and any(CASES_DIR.glob("*/case.json"))
    arm_t = args.arm in ("T", "both") and all(
        (ARM_T_DIR / name).exists() for name in ("sigmets.json", "vona.txt")
    )
    if not (arm_i or arm_t):
        print(f"No inputs for arm {args.arm} under {ROOT}: run make_plume_cases.py first.")
        return 2
    caller = None if args.score_only else Caller(args.model, args.max_calls, args.pause)
    lines = [
        f"# Plume Reader scorecard ({datetime.now(UTC):%Y-%m-%d %H:%MZ})",
        "",
        f"Model: `{args.model}`; runs per case: {args.runs}; protocol: research/10 section 5.",
        "",
    ]
    scorecard: dict[str, Any] = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": args.model,
        "runs": args.runs,
        "arm_i": None,
        "arm_t": None,
        "incomplete": [],
    }
    if arm_i:
        rows, verdict, facts = score_arm_i(run_arm_i(caller, args.runs), args.runs)
        lines += ["## Arm I (images, advisory text withheld)", "", *rows, ""]
        lines += [f"- **{k}:** {v}" for k, v in verdict.items()] + [""]
        scorecard["arm_i"] = facts
        if facts["missing"]:
            scorecard["incomplete"].append(
                f"Arm I: {facts['missing']} of {facts['expected']} responses not run yet"
            )
    else:
        scorecard["incomplete"].append("Arm I: not run")
    if arm_t:
        answers, ids = run_arm_t(caller, args.runs)
        arm_t_lines, arm_t_facts = score_arm_t(answers, ids, args.runs)
        lines += ["## Arm T (Semeru texts)", ""]
        lines += [f"- **{k}:** {v}" for k, v in arm_t_lines.items()]
        lines += [""]
        scorecard["arm_t"] = arm_t_facts
        if arm_t_facts["missing"]:
            scorecard["incomplete"].append(
                f"Arm T: {arm_t_facts['missing']} of {arm_t_facts['runs']} responses not run yet"
            )
    else:
        scorecard["incomplete"].append("Arm T: not run")
    lines += [
        "If Arm I fails, the image leaves the decision path: the Plume Reader becomes "
        "text-and-winds reconciliation and the video says so (research/10)."
    ]
    out = ROOT / "results" / f"scorecard-{datetime.now(UTC):%Y%m%dT%H%MZ}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    json_out = scorecard_json_path()
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(scorecard, indent=1) + "\n")
    print("\n".join(lines))
    print(f"\nwrote {out} and {json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
