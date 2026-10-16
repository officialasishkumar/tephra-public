"""The onboarding pages' rules, ``tephra/web/onboard/pages.js``, run under Node (it has no DOM).

The browser must refuse what the server refuses, in the page's own words (SPEC-v2 §6.3); the
browser draft must become answers that ``tephra.airline.models.AirlineAnswers`` takes; the fleet
and schedule files are read in the browser with every refused row named; and a ``?next=`` never
sends a signed-in airline off the site. Skipped when Node is not installed.
"""

import copy
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "tephra" / "web"
DRAFT = json.loads((ROOT / "tests" / "fixtures" / "airline" / "draft.json").read_text("utf-8"))
NODE = shutil.which("node")

# Each call is [function name, ...arguments]; {"$answers": true} stands for toAnswers(draft).
RUNNER = """
import { readFileSync } from "node:fs";
import * as P from "./onboard/pages.js";
const { draft, calls } = JSON.parse(readFileSync("calls.json", "utf8"));
const answers = P.toAnswers(draft);
const arg = (a) => (a && a.$answers ? answers : a);
const out = calls.map(([fn, ...args]) => P[fn](...args.map(arg)));
process.stdout.write(JSON.stringify(out));
"""
ANSWERS = {"$answers": True}

pytestmark = pytest.mark.skipif(NODE is None, reason="Node is not installed")


def _run(tmp_path: Path, calls: list[list[Any]]) -> list[Any]:
    (tmp_path / "onboard").mkdir(exist_ok=True)
    shutil.copy(WEB / "onboard" / "pages.js", tmp_path / "onboard" / "pages.js")
    (tmp_path / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    (tmp_path / "run.mjs").write_text(RUNNER, encoding="utf-8")
    (tmp_path / "calls.json").write_text(json.dumps({"draft": DRAFT, "calls": calls}), "utf-8")
    result = subprocess.run(
        [str(NODE), "run.mjs"], cwd=tmp_path, capture_output=True, text=True, timeout=60, check=True
    )
    return json.loads(result.stdout)


def _one(tmp_path: Path, *call: Any) -> Any:
    return _run(tmp_path, [list(call)])[0]


def _values(**pages: Any) -> dict[str, Any]:
    v: dict[str, Any] = {
        "airline": {},
        "policy": {"preset": "A", "changes": {}},
        "fleet": {"aircraft": [], "extra_prefixes": []},
        "network": {"airports": [], "alternates": {}},
        "schedule": {"skipped": False, "summary": None},
        "feeds": {},
        "people": {"dispatchers": []},
        "assistant": {"provider": None},
    }
    v.update(pages)
    return v


def _messages(problems: list[dict[str, str]]) -> dict[str, str]:
    return {p["field"]: p["message"] for p in problems}


def _row(reg: str, typ: str, seats: str, base: str = "", hexa: str = "") -> dict[str, str]:
    return {"registration": reg, "type_icao": typ, "seats": seats, "home_base": base, "hex": hexa}


def test_airline_page_words(tmp_path: Path) -> None:
    airline = {
        "name": "R",
        "icao": "R1A",
        "iata": "R!",
        "callsign_prefix": "",
        "state_of_operator": "Indonesia",
        "main_base": "WII",
        "ops_email": "ops.rfa.example",
        "aoc_number": "x" * 41,
    }
    m = _messages(_one(tmp_path, "checkPage", "airline", _values(airline=airline)))
    assert m["airline.name"] == "At least 2 characters."
    assert m["airline.icao"] == "Three letters, A to Z."
    assert m["airline.iata"] == "Two letters or digits."
    assert m["airline.callsign_prefix"] == "Callsign prefix is needed."
    assert m["airline.main_base"] == "Four letters, A to Z."
    assert m["airline.ops_email"] == "Enter an email address, like ops@rfa.example."
    assert m["airline.aoc_number"] == "At most 40 characters."
    assert "airline.state_of_operator" not in m


def test_policy_page_words(tmp_path: Path) -> None:
    named = {
        "planner.divert_within_min": {"value": 15, "unit": "min"},
        "planner.hold_within_min": {"value": 30, "unit": "min"},
        "fuel.hold_min": {"value": 30, "unit": "min"},
        "exposure.vertical_margin_ft": {"value": 2000, "unit": "ft"},
    }
    changes = {
        "planner.divert_within_min": {"value": "40", "base": 15, "reason": "SRA 3"},
        "fuel.hold_min": {"value": "0", "base": 30, "reason": "no"},
        "exposure.vertical_margin_ft": {"value": "2.5", "base": 2000, "reason": ""},
    }
    policy = {"preset": "A", "changes": changes}
    out = _one(tmp_path, "checkPage", "policy", _values(policy=policy), {"named": named})
    fields = [(p["field"], p["message"]) for p in out]
    divert = ("policy.v.planner.divert_within_min", "Divert time must not be later than hold time.")
    assert divert in fields
    zero = ("policy.v.fuel.hold_min", "Must be above zero: a zero would switch this check off.")
    assert zero in fields
    assert ("policy.r.fuel.hold_min", "A reason of 3 to 300 characters is needed.") in fields
    margin = ("policy.v.exposure.vertical_margin_ft", "A whole number from 0 to 100,000.")
    assert margin in fields
    assert ("policy.risk_owner", "Risk owner is needed.") in fields
    assert ("policy.sra_ref", "Your SRA reference is needed once a value changes.") in fields


def test_fleet_page_words(tmp_path: Path) -> None:
    fleet = {
        "aircraft": [
            _row("PK-RFA", "A320", "0", "", "8a0412"),
            _row("pk-rfa", "A3200", "1001", "WII", "8a04g2"),
            _row("PK-RFC", "B738", "189", "WARR", "8A0412"),
        ],
        "extra_prefixes": ["RFA", "RX"],
    }
    values = _values(airline={"callsign_prefix": "RFA"}, fleet=fleet)
    m = _messages(_one(tmp_path, "checkPage", "fleet", values))
    assert "fleet.aircraft.0.seats" not in m  # 0 seats: a freighter
    assert m["fleet.aircraft.1.registration"] == "This is already on row 1."
    assert m["fleet.aircraft.1.type_icao"] == "An ICAO type designator, e.g. A320."
    assert m["fleet.aircraft.1.seats"] == "A whole number from 0 to 1,000."
    assert m["fleet.aircraft.1.home_base"] == "Four letters, A to Z."
    assert m["fleet.aircraft.1.hex"] == "Hex is 6 characters, 0-9 and a-f."
    assert m["fleet.aircraft.2.hex"] == "This is already on row 1."
    assert m["fleet.extra_prefixes.0"] == "This is already your callsign prefix."
    assert m["fleet.extra_prefixes.1"] == "Three letters, A to Z."


def test_people_and_assistant_words(tmp_path: Path) -> None:
    people = _values(people={"dispatchers": [{"name": "A", "role": "views"}]})
    gemini = {"provider": "gemini", "model": "gemma-4-31b-it", "model_lite": "gemma4:e4b"}
    ollama = {"provider": "ollama", "model": "gemma4:e4b", "model_lite": "gemini-3.8-flash"}
    out = _run(
        tmp_path,
        [
            ["checkPage", "people", people],
            ["checkPage", "assistant", _values(assistant=gemini)],
            ["checkPage", "assistant", _values(assistant=ollama), {"ollamaUrl": "ftp://x"}],
            ["checkPage", "assistant", _values()],
        ],
    )
    pairs = [(p["field"], p["message"]) for p in out[0]]
    assert ("people.dispatchers.0.name", "2 to 32 characters.") in pairs
    assert ("people.dispatchers", "At least one person must approve advisories.") in pairs
    g = _messages(out[1])
    assert "assistant.model" not in g  # Gemma on the same AI Studio key
    assert g["assistant.model_lite"] == "A Gemini or Gemma model name, e.g. gemini-3.8-flash."
    o = _messages(out[2])
    assert o["assistant.model_lite"] == "An Ollama tag, name:tag, e.g. gemma4:e4b."
    assert o["assistant.ollama_url"] == "An address like http://127.0.0.1:11434."
    assert _messages(out[3]) == {"assistant.provider": "Choose where the model runs."}


def test_the_draft_becomes_answers_the_server_takes(tmp_path: Path) -> None:
    from tephra.airline.models import AirlineAnswers

    answers = _one(tmp_path, "toAnswers", {"values": DRAFT["values"]})
    parsed = AirlineAnswers.model_validate(answers)
    assert parsed.airline.icao == "RFA"
    assert parsed.airline.main_base == "WIII"
    assert parsed.airline.ops_email == "ops@rfa.example"
    assert parsed.airline.iata is None
    # an unchanged value is not a change
    assert [c.name for c in parsed.policy.changes] == ["exposure.vertical_margin_ft"]
    assert parsed.fleet.aircraft[0].registration == "PK-RFA"
    assert parsed.fleet.aircraft[0].hex == "8a0412"
    assert parsed.fleet.aircraft[3].seats == 0
    # the main base is the first network airport, once
    assert [a.icao for a in parsed.network.airports] == ["WIII", "WARR", "WADD"]
    assert parsed.network.airports[0].alternates == ["WIHH"]
    assert parsed.schedule.provided is True
    text = json.dumps(answers).lower()
    for word in ("password", "secret", "token", "http://", "https://", "api_key", "gemini_key"):
        assert word not in text, word


def test_summaries(tmp_path: Path) -> None:
    named = {"reroute.buffer_nm": {"value": 20, "unit": "NM"}}
    pages = ["airline", "policy", "fleet", "network", "schedule", "feeds", "people", "assistant"]
    got = _run(tmp_path, [["summaryOf", p, ANSWERS, named] for p in pages])
    out = dict(zip(pages, got, strict=True))
    assert out["airline"] == "Ring of Fire Air · RFA · main base WIII"
    assert out["policy"] == "Policy A · margin 3,000 ft · buffer 20 NM · 1 value changed"
    assert out["fleet"] == "4 aircraft · A320, B738"
    assert out["network"] == "3 airports"
    assert out["schedule"] == "2 flights · 1 crew"
    assert out["feeds"] == "Positions and pilot reports"
    assert out["people"] == "2 dispatchers"
    assert out["assistant"] == "Gemma on your computer (Ollama) · gemma4:e4b"


def test_server_problems_say_the_page_s_own_words(tmp_path: Path) -> None:
    problems = [
        "answers.fleet.aircraft.6.hex: String should match pattern '^[0-9a-f]{6}$'",
        "answers.airline.icao: String should match pattern",
        "answers.policy.changes.0.value: Input should be less than or equal to 100000",
        "answers.network: something new",
        "website: should be empty",
    ]
    hexa, icao, change, other, unknown = _run(
        tmp_path, [["mapServerProblem", p, ANSWERS] for p in problems]
    )
    assert hexa == {
        "page": "fleet",
        "field": "fleet.aircraft.6.hex",
        "text": "Fleet: row 7 hex is 6 characters, 0-9 and a-f.",
    }
    assert icao["text"] == "Airline: ICAO designator: Three letters, A to Z."
    assert change["field"] == "policy.v.exposure.vertical_margin_ft"
    assert other["page"] == "network"
    assert unknown == {"page": "review", "field": None, "text": "Review: should be empty"}


def test_fleet_files_are_read_and_every_refusal_is_named(tmp_path: Path) -> None:
    csv = "\n".join(
        [
            "registration,type,seats,home_base,hex",
            "PK-RFA,A320,180,WIII,8a0412",
            "PK-RFB\tA320\t180\t\t8a0413",
            "PK-RFC,B738,189,WARR,8a04g2",
            "PK-RFA,A320,180,,",
        ]
    )
    tails = [
        {"tail": "PK-RFD", "type": "AT76", "seats": 72, "home_base": "WIII", "hex": "8a0415"},
        {"tail": "PK-RFE", "type": "AT76"},
    ]
    existing = [{"registration": "PK-RFX", "hex": "8a0415"}]
    from_csv, from_json, bad = _run(
        tmp_path,
        [
            ["parseFleetFile", csv, "fleet.csv"],
            ["parseFleetFile", json.dumps({"tails": tails}), "fleet.json", existing],
            ["parseFleetFile", "{nope", "fleet.json"],
        ],
    )
    assert [r["registration"] for r in from_csv["rows"]] == ["PK-RFA", "PK-RFB"]
    assert {r["message"] for r in from_csv["refused"]} == {
        "Row 4: hex is 6 characters, 0-9 and a-f.",
        "Row 5: PK-RFA is already in your fleet.",
    }
    assert from_json["rows"] == []
    assert {r["message"] for r in from_json["refused"]} == {
        "Row 1: hex 8a0415 is already in your fleet.",
        "Row 2: seats is needed.",
    }
    assert bad["error"].startswith("This is not JSON: ")


def _flight(no: str, origin: str, dest: str, std: int, **more: Any) -> dict[str, Any]:
    return {
        "flight_no": no,
        "origin": origin,
        "dest": dest,
        "std_min": std,
        "block_min": 80,
        **more,
    }


def test_schedule_files_are_checked_against_the_fleet(tmp_path: Path) -> None:
    header = {"label": "RFA", "anchor_utc_offset_h": 7}
    good = {
        "header": header,
        "flights": [
            _flight("RFA101", "WARR", "WIII", 300, tail="PK-RFA", days="135"),
            _flight("RFA102", "WIII", "WARR", 420),
        ],
    }
    bad = {"header": header, "flights": [_flight("RFA101", "WIII", "WIII", 300, tail="PK-ZZZ")]}
    crews = {
        "crews": [
            {"crew_id": "C1", "base": "WIII", "report_min": 285},
            {"crew_id": "C2", "base": "WARR", "report_min": 300},
        ]
    }
    fleet = ["PK-RFA"]
    ok, no = _run(
        tmp_path,
        [
            ["checkSchedule", {"flights": json.dumps(good), "crews": json.dumps(crews)}, fleet],
            ["checkSchedule", {"flights": json.dumps(bad), "crews": json.dumps(crews)}, fleet],
        ],
    )
    assert ok["ok"] is True
    assert ok["summary"] == {"flights": 2, "tails": 1, "crews": 2, "crew_bases": ["WARR", "WIII"]}
    assert _one(tmp_path, "fileLine", ok["flights"]) == "flights.json · 2 flights · 0 problems"
    assert no["ok"] is False
    assert no["summary"] is None
    assert "Flight 1: origin and dest are the same airport." in no["flights"]["problems"]
    assert "Flight 1: tail PK-ZZZ is not in your fleet." in no["flights"]["problems"]


def test_the_free_tier_list_and_the_positive_values_match_the_server() -> None:
    from tephra.config import DEFAULT_MODEL_LIMITS
    from tephra.models import POSITIVE_POLICY_VALUES

    pages = (WEB / "onboard" / "pages.js").read_text(encoding="utf-8")
    free = re.search(r"export const FREE_TIER_MODELS = \[([^\]]+)\]", pages)
    assert free is not None
    assert re.findall(r'"([^"]+)"', free.group(1)) == list(DEFAULT_MODEL_LIMITS)
    positive = re.search(r"export const POSITIVE_POLICY_VALUES = \[([^\]]+)\]", pages)
    assert positive is not None
    assert sorted(re.findall(r'"([^"]+)"', positive.group(1))) == sorted(POSITIVE_POLICY_VALUES)


def test_editable_policy_values_match_the_server(tmp_path: Path) -> None:
    from tephra.airline.policy_check import EDITABLE
    from tephra.policy import load_policy

    names = sorted(load_policy(ROOT / "data").named_values())
    keep = _run(tmp_path, [["isEditablePolicyValue", n] for n in names])
    assert sorted(n for n, k in zip(names, keep, strict=True) if k) == sorted(EDITABLE)


def test_next_is_followed_only_to_the_workspace_and_edit_pages(tmp_path: Path) -> None:
    cases = {
        "//evil.example/workspace": "/workspace",
        "https://x/workspace": "/workspace",
        "/workspace/x": "/workspace",
        "javascript:alert(1)": "/workspace",
        "/onboard/review?edit=1": "/workspace",
        "/workspace/feeds": "/workspace/feeds",
        "/onboard/fleet?edit=1": "/onboard/fleet?edit=1",
        "/workspace": "/workspace",
    }
    out = _run(tmp_path, [["safeNext", n] for n in cases])
    assert out == list(cases.values())


def test_the_nine_provide_lines_are_the_spec_s() -> None:
    pages = (WEB / "onboard" / "pages.js").read_text(encoding="utf-8")
    names = re.findall(r'\{ key: "\w+", icon: "[\w-]+", name: "([^"]+)", text:', pages)
    assert names == [
        "Airline",
        "Ash policy",
        "Fleet",
        "Network",
        "Schedule and crews",
        "Data feeds",
        "People",
        "Assistant (AI model)",
        "Review",
    ]
    assert "start from Policy A, which is ILLUSTRATIVE, and set your own margins" in pages


def test_an_added_airport_prefers_tephras_list_over_a_free_code(tmp_path: Path) -> None:
    airports = {
        "RJFO": {"name": "Oita", "iata": "OIT"},
        "RJBE": {"name": "Kobe", "iata": "UKB"},
        "WADD": {"name": "I Gusti Ngurah Rai (Bali)", "iata": "DPS"},
        "WIII": {"name": "Soekarno-Hatta", "iata": "CGK"},
        "WARR": {"name": "Juanda (Surabaya)", "iata": "SUB"},
    }
    calls = [
        ["airportCode", text, airports]
        for text in [
            "Oita",
            "kobe",
            "Bali",
            "WIII",
            "dps",
            "WIII · Soekarno-Hatta",
            "ZZZZ",
            "zz",
            "a",
        ]
    ]
    assert _run(tmp_path, calls) == [
        "RJFO", "RJBE", "WADD", "WIII", "WADD", "WIII", "ZZZZ", None, None,
    ]  # fmt: skip
    two = {
        **airports,
        "WAHI": {"name": "Yogyakarta International", "iata": "YIA"},
        "WAHH": {"name": "Adisutjipto (Yogyakarta)", "iata": "JOG"},
    }
    assert _one(tmp_path, "airportCode", "adisutjipto", two) == "WAHH"
    assert _one(tmp_path, "airportCode", "Yogyakarta", two) is None  # two match: pick one


def test_the_kit_preview_takes_only_values_the_kit_would(tmp_path: Path) -> None:
    values = copy.deepcopy(DRAFT["values"])
    values["fleet"]["aircraft"][1]["hex"] = "8a01zz"
    values["airline"]["callsign_prefix"] = "R1"
    checked = _one(tmp_path, "checkedValues", values)

    assert checked["fleet"]["aircraft"][1]["hex"] == ""
    assert checked["fleet"]["aircraft"][0]["hex"] == values["fleet"]["aircraft"][0]["hex"]
    assert checked["airline"]["callsign_prefix"] == ""
    assert checked["airline"]["name"] == values["airline"]["name"]
    assert values["fleet"]["aircraft"][1]["hex"] == "8a01zz"  # the draft itself is unchanged
