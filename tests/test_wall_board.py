"""AI at work (docs/UI-DESIGN.md 7.21): the board's logic, ``tephra/web/wall/board.js``.

The board must show what really happened and nothing else: a card's state, its newest result,
its model and calls, the hand-out lines and the count at the Desk all come from the data the Wall
loads. These tests run the module under Node (it has no DOM) on inputs shaped like the live
site's ``/api/wall``, ``/api/budget``, ``/api/recovery`` and ``/api/docs`` answers, one with the
AI budget closed and one from the offline stub. Skipped when Node is not installed.
"""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

WALL = Path(__file__).resolve().parents[1] / "tephra" / "web" / "wall"
MODULES = ("board.js", "util.js", "x-parts.js", "dk.js")
NODE = shutil.which("node")

RUNNER = """
import { readFileSync } from "node:fs";
import { boardModel } from "./wall/board.js";
const input = JSON.parse(readFileSync(process.argv[2], "utf8"));
const arrived = input.arrivedMs || {};
const live = input.liveMs || {};
input.arrivedAgo = (id) => (id in arrived ? arrived[id] : Infinity);
input.liveAgo = (tool) => (tool in live ? live[tool] : Infinity);
process.stdout.write(JSON.stringify(boardModel(input)));
"""

pytestmark = pytest.mark.skipif(NODE is None, reason="Node is not installed")


def _board(tmp_path: Path, data: dict[str, Any]) -> dict[str, Any]:
    (tmp_path / "wall").mkdir()
    for name in MODULES:
        shutil.copy(WALL / name, tmp_path / "wall" / name)
    (tmp_path / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    (tmp_path / "run.mjs").write_text(RUNNER, encoding="utf-8")
    (tmp_path / "input.json").write_text(json.dumps(data), encoding="utf-8")
    result = subprocess.run(
        [str(NODE), "run.mjs", "input.json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return json.loads(result.stdout)


def _state(backend: str, drafts: int | None) -> dict[str, Any]:
    return {
        "mode": "REPLAY",
        "now": "2026-09-05T10:48:56.968Z",
        "replay": {"case_id": "anak-krakatau-20260905", "label": "Anak Krakatau", "banner": "R"},
        "llm": {"backend": backend, "model_id": backend, "label": backend},
        "draft_count": drafts,
        "disclaimer": "Decision support only - fictional airline - not for operational use",
    }


def _trace(n: int, stage: str, message: str, level: str = "info", at: str = "10:30") -> dict:
    return {
        "id": f"t{stage}{n}",
        "at": f"2026-09-05T{at}:00.000Z",
        "stage": stage,
        "actor": "code",
        "level": level,
        "message": message,
    }


def _work(item_id: str, kind: str, label: str, status: str = "WAITING") -> dict[str, Any]:
    return {
        "id": item_id,
        "kind": "duty_item",
        "label": label,
        "item": {"id": item_id, "kind": kind, "subject": "s", "label": label, "mandatory": False},
        "model_id": "gemini-3.5-flash-lite",
        "lane": "routine",
        "status": status,
        "next_slot_at": "2026-10-13T07:00:00.000Z" if status == "WAITING" else None,
        "reason": "waiting for AI budget, next slot 0700Z",
    }


def _budget(closed: bool, waiting: list[dict[str, Any]], backend: str = "gemini") -> dict:
    return {
        "backend": backend,
        "resets_at": "2026-10-13T07:00:00.000Z",
        "models": [
            {"model_id": "gemini-3.8-flash", "jobs": "Plume Reader", "closed": False},
            {"model_id": "gemini-3.5-flash-lite", "jobs": "Every other AI step", "closed": closed},
        ],
        "tiers": [
            {
                "tier": "main",
                "model_id": "gemini-3.8-flash",
                "used": 0,
                "limit": 18,
                "remaining": 18,
            },
            {
                "tier": "lite",
                "model_id": "gemini-3.5-flash-lite",
                "used": 1,
                "limit": 450,
                "remaining": 449,
            },
        ],
        "waiting": waiting,
    }


def _closed_day() -> dict[str, Any]:
    """The live site on 12 Oct 2026: Google closed the lite model's day, routine work waits."""
    duty = {
        "id": "DUTY-1",
        "started_at": "2026-09-05T10:48:48.672Z",
        "finished_at": "2026-09-05T10:48:48.731Z",
        "replay": True,
        "worklist": [
            {"id": "DI-a", "kind": "PLAN", "label": "Plan RFA4259: inside", "mandatory": True}
        ],
        "dispatches": [],
        "deferred": [],
        "brief": None,
        "outcome": "MODEL_FAILED",
        "llm_backend": "gemini",
        "model_id": "gemini-3.5-flash-lite",
        "turns": 1,
        "validation_errors": ["budget_exhausted"],
        "undispatched": ["DI-a"],
        "recorded_answer": None,
    }
    waiting = [
        _work("DI-p", "PLAN", "Plan RFA5275 (Anak Krakatau): enters the area in 19 min"),
        _work("DI-r", "RECOVER", "Network recovery: WARA, WIHH, WIII closed by the hazard"),
        _work("DI-s", "SRA", "Draft SRA: Java / Bali now carries 25 exposed flight(s)"),
    ]
    return {
        "state": _state("gemini", 0),
        "duty": duty,
        "budget": _budget(True, waiting),
        "trace": [
            _trace(1, "DUTY", "Duty Officer: 1 item(s) to dispatch (tick)", at="10:48"),
            _trace(
                2,
                "DUTY",
                "Plume read: Anak Krakatau (sources or aircraft changed): not dispatched; "
                "the area stays at the official products",
                level="error",
                at="10:35",
            ),
        ],
        "situations": [
            {
                "volcano_id": "262000",
                "volcano_name": "Anak Krakatau",
                "assessment": {"outcome": "PENDING", "created_at": "2026-09-05T10:45:49.021Z"},
            }
        ],
        "recovery": [
            {
                "id": "REC-1",
                "status": "AI_UNAVAILABLE",
                "created_at": "2026-09-05T10:31:00.936Z",
                "unavailable_reason": "AI UNAVAILABLE: RECOVERY AGENT ERROR: TimeoutError",
                "validation_errors": [],
                "scenarios": [],
                "closures": [],
            }
        ],
        "docs": [
            {
                "id": "DOC-1",
                "kind": "SRA",
                "status": "DRAFT",
                "title": "SRA draft: Java / Bali",
                "created_at": "2026-09-05T10:31:02.289Z",
                "replay": True,
            },
            {
                "id": "DOC-2",
                "kind": "SRA",
                "status": "DRAFT",
                "title": "SRA draft: live",
                "created_at": "2026-09-05T10:31:02.289Z",
                "replay": False,
            },
        ],
        "docsLoaded": True,
        "feeds": [{"feed": "sigmet", "status": "OK"}, {"feed": "vona", "status": "DISABLED"}],
        "feedNames": {"sigmet": "VA SIGMET (AWC)"},
        "failedSteps": 26,
        "realNow": 1791851400000,  # 2026-10-13T00:30:00Z, real time
    }


def _stub_run() -> dict[str, Any]:
    plans = [
        {
            "tool": "plan_flights",
            "item_ids": [f"DI-{n}"],
            "ok": True,
            "result": f"RFA{n}: DRAFT MONITOR",
            "ms": 12,
        }
        for n in (1225, 1530)
    ]
    duty = {
        "id": "DUTY-2",
        "started_at": "2026-09-05T10:30:00.353Z",
        "finished_at": "2026-09-05T10:30:00.737Z",
        "replay": True,
        "worklist": [
            {"id": "DI-1225", "kind": "PLAN", "label": "Plan RFA1225", "mandatory": True},
            {"id": "DI-1530", "kind": "PLAN", "label": "Plan RFA1530", "mandatory": False},
        ],
        "dispatches": plans,
        "deferred": [],
        "brief": {"summary": "NO MODEL: 2 delegation(s) made in urgency order.", "priorities": []},
        "outcome": "STUB",
        "llm_backend": "stub",
        "model_id": "stub",
        "turns": 0,
        "validation_errors": [],
        "undispatched": [],
        "recorded_answer": None,
    }
    trace = [_trace(n, "DRAFTER", "DRAFT MONITOR (NO MODEL)") for n in range(3)]
    trace.append(_trace(9, "PLANNER", "NO MODEL: MONITOR"))
    return {
        "state": _state("stub", 2),
        "duty": duty,
        "budget": _budget(False, [], backend="stub"),
        "trace": trace,
        "advisories": [],
        "situations": [],
        "recovery": [],
        "docs": [],
        "docsLoaded": True,
        "feeds": [],
    }


def _card(model: dict[str, Any], card_id: str) -> dict[str, Any]:
    return next(card for card in [model["duty"], *model["team"]] if card["id"] == card_id)


def test_board_waits_for_the_first_state(tmp_path: Path) -> None:
    assert _board(tmp_path, {"state": None}) == {"ready": False}


def test_a_closed_ai_day_reads_as_waiting_and_not_run(tmp_path: Path) -> None:
    model = _board(tmp_path, _closed_day())
    duty = _card(model, "duty")
    # a quota refusal called no model: "Not run", in caution, never a failure in red
    assert (duty["state"], duty["word"]) == ("notrun", "Not run")
    # the reset time is on the real clock, so in REPLAY it says so
    assert duty["last"]["text"] == (
        "Not run: today's free AI quota is used up (until 0700Z real time). No brief was made. "
        "Passed 1 must-do job to the Desk."
    )
    assert duty["last"]["tone"] == "caution"
    assert duty["run"] == {
        "given": 1,
        "mandatory": 1,
        "handed": 0,
        "undone": 1,
        "later": 0,
        "turns": 1,
        "at": duty["run"]["at"],
    }
    plume = _card(model, "plume")
    assert plume["state"] == "notrun"
    assert plume["model"]["id"] == "gemini-3.8-flash"
    assert plume["model"]["text"] == "0 of 18 calls today"
    for helper in ("planner", "drafter", "recovery", "sra"):
        card = _card(model, helper)
        assert card["state"] == "waiting", helper
        assert card["waiting"]["slot"] == "next slot 0700Z", helper
        # a closed day's limit is left out: no call can go, whatever is left of it
        assert card["model"]["text"] == "1 call today, shared", helper
        assert card["model"]["closed"] == {"until": "0700Z", "by": "Google"}, helper
        assert card["steps"][0]["source"] == "AI work queue", helper
    recovery = _card(model, "recovery")
    # a model was called and timed out: "failed" (No result), drawn in caution
    assert recovery["last"]["tone"] == "failed"
    assert recovery["last"]["text"].startswith("Recovery planner timed out.")
    assert _card(model, "sat")["state"] == "quiet"
    assert model["counts"] == {
        "working": 0,
        "waiting": 4,
        "queued": 0,
        "failed": 0,
        "notrun": 2,
        "done": 0,
        "quiet": 1,
    }


def test_the_gate_counts_only_this_modes_work_for_a_person(tmp_path: Path) -> None:
    model = _board(tmp_path, _closed_day())
    gate = model["gate"]
    assert gate["drafts"] == 0
    assert [line["text"] for line in gate["others"]] == [
        "No airport plan was made: a dispatcher plans the network by hand",
        "1 safety risk assessment draft waits for sign-off",
        "1 must-do flight passed to a dispatcher by the latest Duty Officer run, to plan by hand",
    ]
    into_gate = {e["from"]: e["state"] for e in model["edges"] if e["to"] == "gate"}
    assert into_gate == {"drafter": "idle", "recovery": "idle", "sra": "used"}


def test_no_hand_out_in_the_latest_run_leaves_every_line_idle(tmp_path: Path) -> None:
    model = _board(tmp_path, _closed_day())
    from_duty = {e["to"]: e["state"] for e in model["edges"] if e["from"] == "duty"}
    assert set(from_duty.values()) == {"idle"}


def test_the_offline_stub_says_ai_off_and_shows_its_hand_outs(tmp_path: Path) -> None:
    model = _board(tmp_path, _stub_run())
    assert model["stub"] is True
    duty = _card(model, "duty")
    assert duty["state"] == "done"
    assert duty["last"]["text"] == "Handed out 2 jobs in urgency order (AI off)."
    assert duty["model"] == {"id": None, "text": "No model (offline stub): no calls", "tone": "off"}
    planner = _card(model, "planner")
    assert planner["handoff"]["count"] == 2
    assert planner["handoff"]["unit"] == "flight"
    assert planner["last"]["text"] == "Planner (AI off) chose: keep watching"
    drafter = _card(model, "drafter")
    # three identical lines collapse into one step with a count
    repeated = [s for s in drafter["steps"] if s["source"] == "How TEPHRA decided"]
    assert [s["count"] for s in repeated] == [3]
    from_duty = {e["to"]: e["state"] for e in model["edges"] if e["from"] == "duty"}
    assert from_duty["planner"] == from_duty["drafter"] == "used"
    assert from_duty["recovery"] == from_duty["sra"] == "idle"
    assert model["gate"]["drafts"] == 2


def test_a_step_that_just_arrived_is_working_and_its_hand_out_lights_up(tmp_path: Path) -> None:
    data = _stub_run()
    data["arrivedMs"] = {"tDRAFTER2": 1500}
    data["liveMs"] = {"plan_flights": 1500}
    model = _board(tmp_path, data)
    assert _card(model, "drafter")["state"] == "working"
    from_duty = {e["to"]: e["state"] for e in model["edges"] if e["from"] == "duty"}
    assert from_duty["planner"] == from_duty["drafter"] == "live"


def test_a_failed_hand_out_marks_its_line_failed(tmp_path: Path) -> None:
    data = _stub_run()
    data["duty"]["dispatches"][1]["ok"] = False
    model = _board(tmp_path, data)
    planner = _card(model, "planner")
    assert planner["handoff"]["failed"] == 1
    from_duty = {e["to"]: e["state"] for e in model["edges"] if e["from"] == "duty"}
    assert from_duty["planner"] == "failed"


def test_no_run_yet_says_so(tmp_path: Path) -> None:
    data = _stub_run()
    data["duty"] = None
    data["trace"] = []
    model = _board(tmp_path, data)
    duty = _card(model, "duty")
    assert duty["state"] == "quiet"
    assert duty["last"]["text"].startswith("No run yet.")
    quiet = _card(model, "recovery")["last"]["text"]
    assert quiet.startswith("Nothing in the newest 0 steps.")


def test_the_ai_status_uses_the_chips_words(tmp_path: Path) -> None:
    """One derived state (wall/x-parts.js aiStateOf) for the AI chip, this board and the Desk: a
    closed day is "AI paused · 0700Z real time" in caution, never a red count of failed steps."""
    (tmp_path / "paused").mkdir()
    (tmp_path / "off").mkdir()
    paused = _board(tmp_path / "paused", _closed_day())["ai"]
    assert paused["kind"] == "paused"
    words = paused["words"]
    assert (words["label"], words["suffix"], words["tone"]) == (
        "AI paused",
        "0700Z real time",
        "caution",
    )
    assert paused["lead"][0]["strong"] == "AI paused until 0700Z real time."
    assert "Queued work (3 jobs) runs then" in paused["lead"][0]["text"]
    off = _board(tmp_path / "off", _stub_run())["ai"]
    assert (off["kind"], off["words"]["label"]) == ("off", "AI off")
