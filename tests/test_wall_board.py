"""AI at work (docs/UI-DESIGN.md 7.21): the board's logic, ``tephra/web/wall/board.js``.

The board must show what really happened and nothing else: a card's state, its newest result,
its model and calls, the hand-out lines and the count at the Desk all come from the data the Wall
loads. These tests run the module under Node (it has no DOM) on inputs shaped like the live
site's ``/api/wall``, ``/api/budget``, ``/api/recovery`` and ``/api/docs`` answers, one with the
AI budget closed and one from the offline stub. Skipped when Node is not installed.
"""

import json
import re
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
    # a quota refusal called no model: "Not run", in caution, never a failure in red; the board
    # says the assistant is paused and what happened to the work, never why (UI-AI-QUIET 8.6)
    assert (duty["state"], duty["word"]) == ("notrun", "Not run")
    assert duty["last"]["text"] == (
        "Not run: TEPHRA Assistant is paused. No brief was made. Passed 1 must-do job to the Desk."
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
    # the card names its model; calls today and Google's closing are said at the assistant's home
    # (Details, TEPHRA Assistant) only (8.6)
    assert plume["model"] == {
        "id": "gemini-3.8-flash",
        "text": "Model: gemini-3.8-flash",
        "tone": None,
    }
    for helper in ("planner", "drafter", "recovery", "sra"):
        card = _card(model, helper)
        assert card["state"] == "waiting", helper
        assert card["word"] == "Waiting in line", helper
        # that it waits, not when: no slot time on the board
        assert card["waiting"] == {"n": 1}, helper
        assert card["model"]["text"] == "Model: gemini-3.5-flash-lite", helper
        assert "closed" not in card["model"], helper
        assert card["steps"][0]["source"] == "Assistant work queue", helper
        assert card["steps"][0]["text"].startswith("Waiting in line: "), helper
    recovery = _card(model, "recovery")
    # a model was called and timed out: "failed" (No result), drawn in caution
    assert recovery["last"]["tone"] == "failed"
    assert recovery["last"]["text"].startswith("Recovery planner timed out.")
    assert _card(model, "sat")["state"] == "quiet"
    # no state is red: a closed day is waiting, not run or quiet, never failed or working
    states = [card["state"] for card in [model["duty"], *model["team"]]]
    assert sorted(states) == [
        "notrun",
        "notrun",
        "quiet",
        "waiting",
        "waiting",
        "waiting",
        "waiting",
    ]


def test_you_decide_counts_only_this_modes_work_for_a_person(tmp_path: Path) -> None:
    desk = _flow(tmp_path, _closed_day())["m"]["desk"]
    assert desk["drafts"] == 0
    # the live copy of the SRA is not this replay's work
    assert desk["sra"] == {"n": 1, "names": ["Java / Bali"]}
    assert desk["plan"] == "by hand"
    assert desk["must"] == 1


def test_no_hand_out_in_the_latest_run_leaves_every_skill_without_one(tmp_path: Path) -> None:
    model = _board(tmp_path, _closed_day())
    assert [card["handoff"] for card in model["team"]] == [None] * 6


def test_the_offline_stub_says_ai_off_and_shows_its_hand_outs(tmp_path: Path) -> None:
    model = _board(tmp_path, _stub_run())
    assert model["stub"] is True
    duty = _card(model, "duty")
    assert duty["state"] == "done"
    assert duty["last"]["text"] == "Handed out 2 jobs in urgency order (code only)."
    assert duty["model"] == {"id": None, "text": "No model (offline stub): no calls", "tone": "off"}
    planner = _card(model, "planner")
    assert planner["handoff"]["count"] == 2
    assert planner["handoff"]["unit"] == "flight"
    assert planner["last"]["text"] == "Flight planner (code only) chose: keep watching"
    drafter = _card(model, "drafter")
    # three identical lines collapse into one step with a count
    repeated = [s for s in drafter["steps"] if s["source"] == "How TEPHRA decided"]
    assert [s["count"] for s in repeated] == [3]
    assert drafter["handoff"]["count"] == 2
    assert _card(model, "recovery")["handoff"] is None
    assert _card(model, "sra")["handoff"] is None
    (tmp_path / "flow").mkdir()
    assert _flow(tmp_path / "flow", _stub_run())["m"]["desk"]["drafts"] == 2


def test_a_step_that_just_arrived_is_working(tmp_path: Path) -> None:
    data = _stub_run()
    data["arrivedMs"] = {"tDRAFTER2": 1500}
    model = _board(tmp_path, data)
    assert _card(model, "drafter")["state"] == "working"
    assert _card(model, "recovery")["state"] != "working"


def test_a_failed_hand_out_is_said_on_its_skill(tmp_path: Path) -> None:
    data = _stub_run()
    data["duty"]["dispatches"][1]["ok"] = False
    model = _board(tmp_path, data)
    planner = _card(model, "planner")
    assert planner["handoff"]["failed"] == 1
    handed = next(s for s in planner["steps"] if s["source"] == "Coordinator run")
    assert handed["tone"] == "failed"
    assert handed["text"].endswith(", 1 of 2 failed")


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
    """One derived state (wall/x-parts.js aiStateOf) for the assistant chip, this board and the
    Desk: a closed day is "TEPHRA Assistant · paused" in caution, never a red count of failed
    steps, and never says why or until when (docs/UI-AI-QUIET.md 8.6)."""
    (tmp_path / "paused").mkdir()
    (tmp_path / "off").mkdir()
    paused = _flow(tmp_path / "paused", _closed_day())["m"]
    assert paused["ai"]["kind"] == "paused"
    assert (paused["ai"]["label"], paused["ai"]["suffix"], paused["ai"]["tone"]) == (
        "TEPHRA Assistant",
        "paused",
        "caution",
    )
    # the tooltip points to the cause; the cause itself is not in it
    assert "see why in Details \u203a TEPHRA Assistant" in paused["ai"]["title"]
    assert "never shrink the official area" in paused["ai"]["title"]
    assert "jobs wait in line" in paused["sub"]
    off = _flow(tmp_path / "off", _stub_run())["m"]["ai"]
    assert (off["kind"], off["label"], off["suffix"]) == (
        "off",
        "TEPHRA Assistant",
        "off (code only)",
    )


def test_you_decide_takes_the_walls_count_of_flights_to_plan_by_hand(tmp_path: Path) -> None:
    """With the Wall's count of flights the assistant made no plan for (the story's Plan by hand),
    You decide says that count, the must-do ones inside it."""
    data = _closed_day()
    data["handPlan"] = {"n": 14, "must": 1}
    assert _flow(tmp_path, data)["m"]["desk"]["handPlan"] == {"n": 14, "must": 1}


XPARTS_RUNNER = """
import {
  aiStateOf, aiWords, aiLead, draftBlock, blockPhrase, plainLine, recordedWords, jobsWords,
  pacingWords, aiSymbol, replayWords, stripLabel, planFailure, failureEach, causeTitle,
} from "./wall/x-parts.js";
const at = Date.parse("2026-10-13T06:00:00Z");
const e = (stage, reason) => ({ stage, reason, at, raw: reason });
const chip = (errors) => aiWords(aiStateOf({ errors, now: at }));
const plume2 = [
  e("PLUME", "Plume read timed out after 60 s"), e("PLUME", "Plume read FAILED CHECKS: band"),
];
const recovery = e("RECOVERY", "AI UNAVAILABLE: RECOVERY AGENT ERROR: TimeoutError");
const dutyRaw = "Duty Officer AI UNAVAILABLE (TimeoutError); 0 delegation(s) made, "
  + "3 mandatory item(s) to the Desk";
const lane = aiStateOf({ errors: [e("PLANNER", "429 RESOURCE_EXHAUSTED quota")], now: at });
const closedBudget = {
  resets_at: "2026-10-13T07:00:00.000Z",
  models: [{ model_id: "gemini-3.5-flash-lite", jobs: "Every other AI step", closed: true }],
  tiers: [{ tier: "lite", model_id: "gemini-3.5-flash-lite", used: 1, limit: 450, remaining: 449 }],
  waiting: [],
};
const paused = aiStateOf({ budget: closedBudget, now: at });
// the budget still reads closed 3 h 10 min after its 0700Z reset (live and in REPLAY)
const late = Date.parse("2026-10-13T10:10:00Z");
const overdueLive = aiStateOf({ budget: closedBudget, now: late });
const overdueReplay = aiStateOf({ budget: closedBudget, now: late, replay: true });
// the Plume reader's own model is closed, the lite model is open: trouble, not a pause
const main = { model_id: "gemini-3.5-flash", used: 20, limit: 20, remaining: 0 };
const lite = { model_id: "gemini-3.5-flash-lite", used: 1, limit: 450, remaining: 449 };
const plumeRead = "Plume read: Anak Krakatau (budget_exhausted): not dispatched; "
  + "the area stays at the official products";
const plumeOut = aiStateOf({
  budget: {
    resets_at: "2026-10-13T07:00:00.000Z",
    models: [
      { ...main, jobs: "Plume reader", closed: true },
      { ...lite, jobs: "Every other AI step", closed: false },
    ],
    tiers: [{ tier: "main", ...main }, { tier: "lite", ...lite }],
    waiting: [],
  },
  errors: [e("PLUME", plumeRead)],
  now: at,
});
const quotaPlan = {
  status: "AI_UNAVAILABLE", unavailable_reason: "AI UNAVAILABLE: budget_exhausted",
  validation_errors: [], scenarios: [], created_at: "2026-10-13T05:00:00Z",
};
const refused = "Duty Officer AI UNAVAILABLE (budget_exhausted); 0 delegation(s) made, "
  + "2 mandatory item(s) to the Desk";
process.stdout.write(JSON.stringify({
  oneSkillTwoWays: chip(plume2),
  twoSkills: chip([...plume2, recovery]),
  lane: aiWords(lane),
  laneBlock: blockPhrase(draftBlock(lane)),
  laneMain: aiLead(lane, { home: false }),
  laneHome: aiLead(lane),
  laneTitle: causeTitle(lane.causes[0]),
  laneHomeTitle: causeTitle(lane.causes[0], { home: true }),
  overdueLive: aiLead(overdueLive),
  overdueReplay: aiLead(overdueReplay),
  overdueKinds: [overdueLive.kind, overdueLive.until, overdueReplay.until],
  plumeOut: {
    kind: plumeOut.kind, chip: aiWords(plumeOut),
    main: aiLead(plumeOut, { home: false }), home: aiLead(plumeOut),
  },
  quotaPlan: planFailure(quotaPlan),
  refusedEach: failureEach({ stage: "DUTY", message: plumeRead }),
  paused: aiWords(paused),
  pausedNarrow: aiWords(paused, { narrow: true }),
  pausedBlock: draftBlock(paused),
  pausedPhrase: blockPhrase(draftBlock(paused)),
  homeLead: aiLead(paused),
  mainLead: aiLead(paused, { home: false }),
  refusedLine: plainLine(refused),
  plumeRefused: plainLine(
    "Plume read: Anak Krakatau (budget_exhausted): not dispatched; "
      + "the area stays at the official products",
  ),
  off: aiWords(aiStateOf({ stub: true })),
  coordinator: chip([e("DUTY", dutyRaw)]),
  dutyLine: plainLine(dutyRaw),
  oddLine: plainLine("Duty Officer AI UNAVAILABLE (SOMETHING NEW) · nothing"),
  recorded: recordedWords("AI answer recorded on this replay's first pass at 0912Z real time"),
  jobs: jobsWords("Every other AI step"),
  pacing: pacingWords("Routine work is paced: 3 used; waiting for AI budget, next slot 0700Z."),
  symbols: ["on", "paused", "trouble", "off"].map(aiSymbol),
  strip: replayWords({
    recorded_from: "2026-09-05T06:00:00.000Z",
    banner: "REPLAY: recorded real feeds from 05 Sep 2026",
    label: "Anak Krakatau (reconstructed)", auto: true,
  }),
  stripLabels: [stripLabel(true), stripLabel(false)],
}));
"""


def _xparts(tmp_path: Path) -> dict[str, Any]:
    (tmp_path / "wall").mkdir()
    for name in MODULES:
        shutil.copy(WALL / name, tmp_path / "wall" / name)
    (tmp_path / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    (tmp_path / "run.mjs").write_text(XPARTS_RUNNER, encoding="utf-8")
    result = subprocess.run(
        [str(NODE), "run.mjs"], cwd=tmp_path, capture_output=True, text=True, timeout=60, check=True
    )
    return json.loads(result.stdout)


def test_the_chip_counts_skills_and_uses_its_tooltips_verb(tmp_path: Path) -> None:
    """Naming review: one skill that failed two ways is one skill, not "2 skills not running";
    the chip says what its tooltip says ("gave no result", "did not run" only where no model was
    called), and the tooltip names each cause once."""
    out = _xparts(tmp_path)
    assert out["oneSkillTwoWays"]["suffix"] == "Plume reader gave no result"
    assert out["oneSkillTwoWays"]["title"].count("Plume reader gave no result (timed out)") == 1
    assert out["twoSkills"]["suffix"] == "2 skills gave no result"
    assert out["coordinator"]["suffix"] == "Coordinator gave no result"
    assert out["lane"]["suffix"] == "Flight planner did not run"
    # a lane's quota refusal is "did not run" in the flight's words too, as in causeShort; its
    # cause is said at the assistant's home only, and it is never "paused": the assistant is on
    # (8.6)
    assert out["laneBlock"] == "Flight planner did not run"
    assert out["symbols"] == ["ta-working", "ta-waiting", "ta-unavailable", "ta-unavailable"]


QUOTA_WORDS = re.compile(
    r"quota|used up|closed by google|free ai|next slot|budget|\breset|\bspent\b|calls today"
    r"|\blanes?\b|pacing|\d{4}Z|for another \d",
    re.I,
)


def test_a_pause_says_its_cause_once_at_the_assistants_home(tmp_path: Path) -> None:
    """Say the cause once (docs/UI-AI-QUIET.md 8.6): the chip, a flight's missing draft and the
    plain-words lines say "paused" with no quota, budget or time; the home's lead says why and
    until when, so the cause stays one tap away (rule 9: the missing output is still said at the
    place)."""
    out = _xparts(tmp_path)
    assert (out["paused"]["suffix"], out["paused"]["tone"]) == ("paused", "caution")
    assert out["pausedNarrow"]["suffix"] == "paused"
    assert out["paused"]["aria"] == "TEPHRA Assistant paused. Opens TEPHRA Assistant at work."
    assert "see why in" in out["paused"]["title"]
    for key in ("paused", "pausedNarrow"):
        for field in ("suffix", "aria", "title"):
            assert not QUOTA_WORDS.search(out[key][field]), (key, field, out[key][field])
    # the place still knows the draft is missing: the block is there, its phrase says no cause
    assert out["pausedBlock"] == {"word": "Assistant paused", "paused": True}
    assert out["pausedPhrase"] == ""
    # a line on record says what happened, never "paused" (the refusal may have been one
    # skill's share while the assistant was on) and never the quota
    assert out["refusedLine"] == (
        "Coordinator did not run. 2 jobs that must be done went to the Desk"
    )
    assert out["plumeRefused"] == (
        "Plume read for Anak Krakatau was not handed out. "
        "TEPHRA's area stays at the official reports"
    )
    assert out["refusedEach"]["each"] == "Anak Krakatau: not handed out"
    main = " ".join(f"{p['strong']} {p['text']}" for p in out["mainLead"])
    assert main.startswith("TEPHRA Assistant is paused.")
    assert not QUOTA_WORDS.search(main), main
    # the home names the cause, the model and the next slot on the real clock
    home = " ".join(f"{p['strong']} {p['text']}" for p in out["homeLead"])
    assert home.startswith("TEPHRA Assistant is paused until 0700Z.")
    assert "Why: Google's free daily AI quota for gemini-3.5-flash-lite is used up." in home
    # the time is said once (review clutter 7)
    assert home.count("0700Z") == 1, home
    assert "nothing is made up in place of an assistant step" in home


def _lead(paras: list[dict[str, str]]) -> str:
    return " ".join(f"{p['strong']} {p['text']}" for p in paras)


def test_a_reset_already_past_is_said_as_overdue_at_the_home(tmp_path: Path) -> None:
    """The budget still reads closed after its reset: the home never says a stale "until 0700Z"
    or a countdown stuck at "1 min"; it says the reset was due and that when it opens is not
    known (the fact the board said before 8.6, now at the one place that says the cause)."""
    out = _xparts(tmp_path)
    assert out["overdueKinds"] == ["paused", None, None]
    live = _lead(out["overdueLive"])
    assert live.startswith("TEPHRA Assistant is paused. Why: Google's free daily AI quota")
    assert "Its reset was due at 0700Z (real time)" in live
    assert "until" not in live.split("Until then")[0]
    replay = _lead(out["overdueReplay"])
    assert "Its reset was due 3 h 10 min ago (real time)" in replay
    assert "1 min" not in replay
    assert "when it opens is not known" in replay


def test_a_skill_out_of_calls_while_the_assistant_is_on_is_never_paused(tmp_path: Path) -> None:
    """Honesty review 1: "paused" is the whole assistant's state. A skill refused for its own
    model or share while the assistant is on is trouble: the main views say what happened ("did
    not run", "cannot run now") with no quota words and never "paused"; the home names the cause."""
    out = _xparts(tmp_path)
    p = out["plumeOut"]
    assert p["kind"] == "trouble"
    assert p["chip"]["suffix"] == "Plume reader did not run"
    main = _lead(p["main"])
    for text in (p["chip"]["suffix"], p["chip"]["title"], p["chip"]["aria"], main):
        assert "paused" not in text, text
        # a step's own time ("at 0600Z") is not a slot or reset time
        assert not QUOTA_WORDS.search(text.replace(" at 0600Z", "")), text
    assert main.startswith("TEPHRA Assistant is on, 1 problem. Plume reader did not run")
    assert "Nothing was put in its place." in main
    home = _lead(p["home"])
    assert "Plume reader did not run (today's free AI quota is used up)" in home
    lane_main = _lead(out["laneMain"])
    assert "Flight planner did not run" in lane_main
    assert "paused" not in lane_main
    assert not QUOTA_WORDS.search(lane_main.replace(" at 0600Z", "")), lane_main
    assert "today's free AI quota is used up" in _lead(out["laneHome"])
    assert out["laneTitle"] == "Flight planner did not run"
    assert out["laneHomeTitle"] == "Flight planner did not run: today's free AI quota is used up"


def test_a_plan_refused_on_quota_says_did_not_run_with_no_quota_words(tmp_path: Path) -> None:
    """Honesty review 2: the story's notice title and the board take `word`, `title` and `place`
    from planFailure. A quota refusal called no model: "did not run", no quota words; the cause
    in full (`why`) is for the assistant's home only."""
    pf = _xparts(tmp_path)["quotaPlan"]
    assert pf["ai"] is True
    assert pf["word"] == "Recovery planner did not run"
    assert pf["title"] == "No plan: Recovery planner did not run"
    assert pf["place"] == "No airport plan (Recovery planner did not run): plan the network by hand"
    for key in ("word", "title", "sub", "place", "short"):
        assert not QUOTA_WORDS.search(pf[key]), (key, pf[key])
        assert "gave no result" not in pf[key], (key, pf[key])
    assert pf["why"] == "today's free AI quota is used up"
    story = (WALL / "story.js").read_text(encoding="utf-8")
    assert "pf?.ai ? pf.word" in story
    assert "pf.why" not in story


def test_the_off_chip_still_discloses_ai(tmp_path: Path) -> None:
    """Naming review: in stub mode (the demo default) the chip's tooltip still says what TEPHRA
    Assistant is, and that it never shrinks the official area."""
    title = _xparts(tmp_path)["off"]["title"]
    assert "TEPHRA's AI assistant" in title
    assert "never shrink the official area" in title
    assert "NO MODEL" in title


def test_server_words_are_shown_in_assistant_words(tmp_path: Path) -> None:
    """Naming review: a Coordinator outage line gets a real pattern (never a half-renamed raw
    rule-9 line); a line no pattern knows that carries "AI UNAVAILABLE" is shown verbatim; the
    REPLAY label keeps "recorded ... first pass ... real time"."""
    out = _xparts(tmp_path)
    assert out["dutyLine"] == (
        "Coordinator gave no result (timed out). 3 jobs that must be done went to the Desk"
    )
    assert out["oddLine"].startswith("Duty Officer AI UNAVAILABLE")
    assert out["recorded"] == (
        "TEPHRA Assistant's answer recorded on this replay's first pass at 0912Z real time"
    )
    assert out["jobs"] == "Every other skill"
    assert out["pacing"] == "Routine work is paced: 3 used; the next slot is at 0700Z."


def test_the_frame_strip_says_replay_once_with_the_case_in_its_tooltip(tmp_path: Path) -> None:
    """Say it once, in the frame (UI-DESIGN 7.1): the Wall and the Desk word the REPLAY strip from
    the same function; the case title and an automatic switch are in its tooltip and, for screen
    readers, after the visible words."""
    strip = _xparts(tmp_path)["strip"]
    assert strip["text"] == "Replay · recorded feeds from 05 Sep 2026"
    assert strip["live"] == " · not live"
    assert strip["title"] == (
        "REPLAY: recorded real feeds from 05 Sep 2026 · not live · Anak Krakatau (reconstructed)"
        " · switched automatically: no live activity"
    )
    assert strip["more"] == (
        " · Anak Krakatau (reconstructed) · switched automatically: no live activity"
    )


def test_the_frame_strip_is_named_for_what_it_holds(tmp_path: Path) -> None:
    """The strip's accessible name says "Replay" only while a replay plays; live, the strip holds
    the disclaimer alone and is named so."""
    assert _xparts(tmp_path)["stripLabels"] == ["Replay notice and disclaimer", "Disclaimer"]


# ------------------------------------------------------------------ the flow board (UI-DESIGN 7.21)
# flowModel, flowAt and foldRows are pure: each moving thing on the board is one real record.

FLOW_RUNNER = """
import { readFileSync } from "node:fs";
import { flowModel, flowAt, foldRows, stepEvents } from "./wall/board.js";
const input = JSON.parse(readFileSync(process.argv[2], "utf8"));
const m = flowModel(input);
const at = input.at ? Date.parse(input.at) : m.t1;
const steps = (input.steps || []).map(stepEvents);
process.stdout.write(JSON.stringify({ m, s: m.ready ? flowAt(m.events, at) : null,
  rows: m.ready ? foldRows(m.events) : null, steps }));
"""


def _flow(tmp_path: Path, data: dict[str, Any]) -> dict[str, Any]:
    (tmp_path / "wall").mkdir()
    for name in MODULES:
        shutil.copy(WALL / name, tmp_path / "wall" / name)
    (tmp_path / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    (tmp_path / "run.mjs").write_text(FLOW_RUNNER, encoding="utf-8")
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


REFUSED = (
    "Duty Officer AI UNAVAILABLE (budget_exhausted); 0 delegation(s) made, "
    "{n} mandatory item(s) to the Desk"
)


def _step(
    i: int,
    stage: str,
    message: str,
    at: str,
    *,
    actor: str = "code",
    level: str = "info",
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": f"s{i}",
        "at": f"2026-09-05T{at}.000Z",
        "stage": stage,
        "actor": actor,
        "level": level,
        "message": message,
        "detail": detail or {},
    }


def _refused_day() -> dict[str, Any]:
    """Three Coordinator runs the quota refused, as on the live site on 13 Oct 2026."""
    trace = []
    for k, (at, n) in enumerate((("11:28:26", 1), ("11:29:26", 3), ("11:30:26", 2))):
        trace.append(
            _step(
                10 * k, "DUTY", f"Duty Officer: {n + 1} item(s) to dispatch (tick)", at, actor="adk"
            )
        )
        trace.append(_step(10 * k + 1, "DUTY", REFUSED.format(n=n), at, level="error"))
    data = _closed_day()
    data["state"]["now"] = "2026-09-05T11:31:00.000Z"
    data["trace"] = trace
    data["feeds"] = []
    return data


def test_flow_refused_runs_send_no_work_to_a_skill(tmp_path: Path) -> None:
    """Honesty: with refused runs only, nothing reaches a skill; the jobs go to a person."""
    out = _flow(tmp_path, _refused_day())
    types = {e["type"] for e in out["m"]["events"]}
    assert types == {"duty", "refused"}
    assert not any(e.get("skill") for e in out["m"]["events"])
    assert out["m"]["gate"]["open"] is False
    assert out["m"]["gate"]["name"] == "Paused"
    # the view's refused branch routes its tokens down the code lane only, never to a skill
    view = (WALL / "board-view.js").read_text(encoding="utf-8")
    refused = view[view.index('e.type === "refused" || e.type === "undone") {') :]
    refused = refused[: refused.index("} else if")]
    assert "sk-" not in refused


def test_flow_hero_is_the_newest_refused_run_at_the_playhead(tmp_path: Path) -> None:
    data = _refused_day()
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "c").mkdir()
    end = _flow(tmp_path / "a", data)["s"]
    assert (end["must"], end["runs"]) == (2, 3)
    data["at"] = "2026-09-05T11:29:30.000Z"
    mid = _flow(tmp_path / "b", data)["s"]
    assert (mid["must"], mid["runs"]) == (3, 2)
    data["at"] = "2026-09-05T11:28:00.000Z"
    before = _flow(tmp_path / "c", data)["s"]
    assert before["must"] is None


def test_flow_log_folds_a_run_with_its_outcome_and_counts_repeats(tmp_path: Path) -> None:
    rows = _flow(tmp_path, _refused_day())["rows"]
    assert [r["kind"] for r in rows] == ["duty", "duty", "duty"]
    last = rows[-1]
    assert last["text"] == "Coordinator got 3 jobs on the scheduled check · did not run"
    assert last["toYou"] == "2 must-do to you"
    # one time form on the board, the replay clock's
    assert last["repeat"] == "3\u00d7 since 11:28:26"
    assert last["tone"] == "must"


def test_flow_feed_particles_come_only_from_real_reads(tmp_path: Path) -> None:
    """A POLL step, or a feed's last_success_at that moved, and never both for one read; a feed
    whose newest read is outside the window draws nothing."""
    data = _refused_day()
    data["trace"].append(
        _step(
            90,
            "POLL",
            "METAR: 13 new or changed record(s)",
            "11:30:27",
            detail={"feed": "metar", "records": 14},
        )
    )
    data["feeds"] = [
        {
            "feed": "metar",
            "status": "OK",
            "last_success_at": "2026-09-05T11:30:27.900Z",
            "record_count": 14,
        },
        {
            "feed": "sigmet",
            "status": "OK",
            "last_success_at": "2026-09-05T11:29:00.000Z",
            "record_count": 9,
        },
        {
            "feed": "vona",
            "status": "OK",
            "last_success_at": "2026-09-05T09:00:00.000Z",
            "record_count": 12,
        },
        {"feed": "vaac_tokyo", "status": "DISABLED", "last_success_at": None, "record_count": 0},
    ]
    data["feedReads"] = [{"feed": "sigmet", "at": "2026-09-05T11:28:40.000Z", "n": 9}]
    feeds = [e for e in _flow(tmp_path, data)["m"]["events"] if e["type"] == "feed"]
    assert sorted((e["feed"], e["src"]) for e in feeds) == [
        ("metar", "poll"),
        ("sigmet", "feeds"),
        ("sigmet", "state"),
    ]
    sigmet = next(e for e in feeds if e["src"] == "feeds")
    assert sigmet["kind"] == "official"
    assert sigmet["text"] == "VA SIGMETs read: 9 current"


def test_flow_steps_map_to_the_skills_they_name(tmp_path: Path) -> None:
    data = _refused_day()
    data["steps"] = [
        _step(
            1,
            "DUTY",
            "Duty Officer -> plan_flights: RFA1540: DRAFT MONITOR for a dispatcher",
            "10:01:00",
            actor="adk",
        ),
        _step(2, "DRAFTER", "DRAFT MONITOR (NO MODEL)", "10:01:00", actor="stub"),
        _step(3, "DESK", "RFA1540: DRAFT MONITOR waiting for a dispatcher", "10:01:00"),
        _step(
            4,
            "PLUME",
            "NO MODEL: stub plume estimate OFFICIAL FL000-FL060, 100%",
            "10:01:00",
            actor="stub",
        ),
        _step(
            5,
            "RECOVERY",
            "AI UNAVAILABLE: RECOVERY AGENT ERROR: TimeoutError",
            "10:01:00",
            actor="adk",
            level="error",
        ),
        _step(
            6,
            "EXPOSURE",
            "RFA1456 (BTK6253) enters the Anak Krakatau cone in 7 min at FL226 "
            "if track and level are held",
            "10:01:00",
            level="warn",
        ),
        _step(
            7,
            "CONE",
            "Ibu: cone OFFICIAL 100% (NO MODEL), SFC/FL070, 5 official layer(s)",
            "10:01:00",
        ),
    ]
    steps = _flow(tmp_path, data)["steps"]
    kinds = [[(e["type"], e.get("skill")) for e in s] for s in steps]
    assert kinds == [
        [("handoff", "planner")],
        [("skill", "drafter")],
        [("desk", "drafter")],
        [("skill", "plume")],
        [("skill-failed", "recovery")],
        [("flight", None)],
        [("note", None)],
    ]
    # code's stub plume estimate is not a model's reading: no amber on the map for it
    assert steps[3][0]["plume"] is False
    assert steps[5][0]["mins"] == 7
    assert steps[5][0]["inside"] is False


def test_flow_words_follow_the_assistant_state(tmp_path: Path) -> None:
    (tmp_path / "paused").mkdir()
    (tmp_path / "off").mkdir()
    paused = _flow(tmp_path / "paused", _refused_day())["m"]
    assert paused["ai"]["kind"] == "paused"
    # the state and what waits; why and until when are at the assistant's home (8.6)
    assert paused["status"] == "paused"
    assert paused["sub"] == (
        "Code still reads every feed and checks every flight; jobs wait in line and must-do "
        "flights come straight to you."
    )
    assert paused["gate"]["meta"] == "3 jobs in line"
    assert paused["gate"]["title"] == "Why: Details \u203a TEPHRA Assistant"
    assert paused["coord"]["meta"] == "Paused: must-do jobs come to you"
    for words in (paused["status"], paused["sub"], paused["gate"]["name"], paused["gate"]["meta"]):
        assert not QUOTA_WORDS.search(words), words
    assert [s["inLine"] for s in paused["skills"]] == [0, 0, 1, 0, 1, 1]
    off = _flow(tmp_path / "off", _stub_run())["m"]
    kinds = (off["ai"]["kind"], off["status"], off["gate"]["kind"])
    assert kinds == ("off", "off (code only)", "nomodel")
    # no model to close: the skills are code templates, so the gate is drawn as a bypass
    assert off["gate"]["open"] is True


def test_flow_example_never_touches_the_wall_store() -> None:
    """Example mode is drawn and counted in the view only, and the board writes nothing: the view
    imports nothing that holds the Wall's data and calls no endpoint."""
    view = (WALL / "board-view.js").read_text(encoding="utf-8")
    imports = re.findall(r'^import .* from "([^"]+)";$', view, flags=re.M)
    assert imports == ["./util.js", "./board.js"]
    assert not re.search(r"\bstore\b", view)
    assert not re.search(r"\bfetch\(", view.replace('fetch("/static/data/land_apac.geojson")', ""))
    assert "POST" not in view
    assert "Example · illustrative, not recorded." in view
    assert "EXAMPLE ONLY (illustrative)" in view


def test_a_refused_coordinator_run_is_never_working(tmp_path: Path) -> None:
    """The bug of the card board: a refusal line that just arrived made the Coordinator "Working"
    for 6 s although no model was called."""
    data = _closed_day()
    data["trace"].append(_trace(3, "DUTY", REFUSED.format(n=1), level="error", at="10:48"))
    data["arrivedMs"] = {"tDUTY3": 500, "tDUTY1": 600}
    duty = _card(_board(tmp_path, data), "duty")
    assert duty["state"] == "notrun"
    assert duty["word"] == "Not run"


def test_a_refusal_that_arrives_after_an_answered_run_is_never_working(tmp_path: Path) -> None:
    """The race: the snapshot still holds the previous, answered run when the refusal line arrives
    on the stream. No model call is in progress, so the Coordinator is not "Working"."""
    data = _closed_day()
    data["duty"].update(
        outcome="ACCEPTED",
        validation_errors=[],
        brief={"summary": "Plan the exposed flights first.", "priorities": []},
        dispatches=[],
        undispatched=[],
    )
    data["trace"].append(_trace(3, "DUTY", REFUSED.format(n=1), level="error", at="10:49"))
    data["arrivedMs"] = {"tDUTY3": 400}
    duty = _card(_board(tmp_path, data), "duty")
    assert duty["state"] != "working"
    assert duty["word"] != "Working"


def test_flow_a_reset_already_past_is_not_said_as_one_minute(tmp_path: Path) -> None:
    """The budget still says closed after its reset time: the board still says "paused" with what
    waits, never a countdown that stays at "1 min" (and never a reset time, 8.6)."""
    data = _refused_day()
    data["realNow"] = 1791886200000  # 2026-10-13T10:10:00Z, 3 h 10 min after the 0700Z reset
    m = _flow(tmp_path, data)["m"]
    assert m["status"] == "paused"
    assert "1 min" not in m["sub"]
    assert "1 min" not in m["gate"]["meta"]
    assert m["gate"]["meta"] == "3 jobs in line"
    # the overdue reset is said at the assistant's home, one tap away (the gate's "Why:" and the
    # lede's "Why"): test_a_reset_already_past_is_said_as_overdue_at_the_home
    assert m["gate"]["title"] == "Why: Details \u203a TEPHRA Assistant"


def test_flow_a_budget_that_did_not_load_says_nothing_about_the_queue(tmp_path: Path) -> None:
    data = _refused_day()
    data["budgetError"] = "HTTP 502"
    m = _flow(tmp_path, data)["m"]
    assert m["queue"] == []
    assert m["gate"]["open"] is False
    assert m["gate"]["meta"] == "Jobs in line: unknown, the work queue did not load"
    assert "next slot" not in m["gate"]["meta"]
    # with no queue loaded the lede says nothing about jobs in line (honesty review 8)
    assert "jobs wait in line" not in m["sub"]
    assert m["sub"].startswith("Code still reads every feed and checks every flight")
    assert [s["inLine"] for s in m["skills"]] == [0] * 6


def test_flow_trouble_closes_the_gate(tmp_path: Path) -> None:
    """Spec 5: a model that gave no result is unavailable, and an unavailable model is a closed
    gate, never an open one with "Quota left today"."""
    data = _stub_run()
    data["state"]["llm"] = {"backend": "gemini", "model_id": "g", "label": "g"}
    data["budget"] = _budget(False, [])
    data["trace"].append(
        _step(
            5,
            "RECOVERY",
            "AI UNAVAILABLE: RECOVERY AGENT ERROR: TimeoutError",
            "10:40:00",
            actor="adk",
            level="error",
        )
    )
    m = _flow(tmp_path, data)["m"]
    assert m["ai"]["kind"] == "trouble"
    assert m["gate"]["open"] is False
    assert m["gate"]["meta"] == "Nothing waits in line"


def test_flow_a_hand_out_goes_before_the_work_it_started(tmp_path: Path) -> None:
    """The Coordinator writes "Duty Officer -> plan_flights" when the tool returns, after the
    planner, drafter and desk lines it produced. The board shows the hand-out first, and the log
    keeps the record's own time."""
    data = _refused_day()
    data["trace"] = [
        _step(1, "DUTY", "Duty Officer: 1 item(s) to dispatch (tick)", "10:01:10", actor="stub"),
        _step(2, "PLANNER", "NO MODEL: MONITOR", "10:01:11", actor="stub"),
        _step(3, "DRAFTER", "DRAFT MONITOR (NO MODEL)", "10:01:11", actor="stub"),
        _step(4, "DESK", "RFA1540: DRAFT MONITOR waiting for a dispatcher", "10:01:11"),
        _step(
            5,
            "DUTY",
            "Duty Officer -> plan_flights: RFA1540: DRAFT MONITOR for a dispatcher",
            "10:01:12",
            actor="stub",
        ),
    ]
    data["state"]["now"] = "2026-09-05T10:02:00.000Z"
    out = _flow(tmp_path, data)
    order = [e["type"] for e in out["m"]["events"]]
    assert order == ["duty", "handoff", "skill", "skill", "desk"]
    handoff = next(e for e in out["m"]["events"] if e["type"] == "handoff")
    assert handoff["rec"] == handoff["at"] + 1001
    row = next(r for r in out["rows"] if r["kind"].startswith("handoff:"))
    assert row["tm"] == handoff["rec"]


def test_the_frame_strip_says_replay_while_the_board_covers_the_wall() -> None:
    """The board covers the Wall, which is not redrawn while it is open; the frame strip above it
    is, so a board opened from #ai-at-work in REPLAY still says REPLAY once (UI-DESIGN 7.1)."""
    wall = (WALL.parent / "wall.js").read_text(encoding="utf-8")
    board_branch = wall[wall.index("  if (ui.board.open) {\n    renderFrame(D.state);") :]
    board_branch = board_branch[: board_branch.index("return;")]
    assert "renderFlow();" in board_branch
    panels = (WALL / "panels.js").read_text(encoding="utf-8")
    frame = panels[panels.index("export function renderFrame(s)") :]
    frame = frame[: frame.index("\n}\n")]
    assert "banner.hidden = !replay;" in frame
    assert "renderFrame(s);" in panels[panels.index("export function renderChrome") :]
