"""The demo's Assistant tab (SPEC v2 5.2.5): ``tephra/web/wall/assist.js`` under Node.

Each folded board row gets the step it belongs to, who took it and how it went; the rows at a
playhead hold only steps at or before it; the player always says "Replay" in REPLAY and never a
bare "paused"; LIVE has no player; with the offline stub the state line says NO MODEL. The module
has no DOM, so these run on plain data. Skipped when Node is not installed.
"""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

WALL = Path(__file__).resolve().parents[1] / "tephra" / "web" / "wall"
MODULES = ("assist.js", "board.js", "util.js", "x-parts.js", "dk.js")
NODE = shutil.which("node")

RUNNER = """
import { readFileSync } from "node:fs";
import { rowView, visibleRows, minuteGroups, playerWords, stateLine, stageOf }
  from "./wall/assist.js";
import { flowEvents } from "./wall/board.js";
const input = JSON.parse(readFileSync(process.argv[2], "utf8"));
const at = (hms) => Date.parse(`2026-09-05T${hms}Z`);
const views = input.rows.map((r) => rowView({ key: r.kind, at: at("10:30:00"), ...r }));
const M = { replay: true, events: flowEvents({ trace: input.trace, now: at("10:40:00") }).events };
const rows = visibleRows(M, at("10:31:30"));
const all = visibleRows(M, at("10:40:00"));
const P = (mode, t) => ({ mode, t: at(t), from: at(t), rm: false });
process.stdout.write(JSON.stringify({
  views,
  rows: rows.map((r) => ({ tm: new Date(r.tm).toISOString(), stage: r.stage, actor: r.actor })),
  groups: minuteGroups(all).map((g) => [g.minute, g.rows.length]),
  player: {
    follow: playerWords(M, P("follow", "10:32:00")),
    paused: playerWords(M, P("paused", "10:31:00")),
    playing: playerWords(M, P("playing", "10:30:00")),
    calm: playerWords(M, { ...P("playing", "10:30:00"), rm: true }),
    live: playerWords({ replay: false, events: M.events }, P("follow", "10:32:00")),
  },
  stub: stateLine({ suffix: "off (code only)" }, { stub: true, kind: "off" }),
  paused: stateLine({ suffix: "paused" }, { kind: "paused" }),
  trouble: stateLine({ suffix: "Flight planner gave no result" }, { kind: "trouble" }),
  on: stateLine({ suffix: "on" }, { kind: "on" }),
  noKind: stageOf({}),
}));
"""

pytestmark = pytest.mark.skipif(NODE is None, reason="Node is not installed")


def _step(n: int, stage: str, message: str, at: str, actor: str = "code", **extra: Any) -> dict:
    return {
        "id": f"s{n}",
        "at": f"2026-09-05T{at}.000Z",
        "stage": stage,
        "actor": actor,
        "level": "info",
        "message": message,
        **extra,
    }


ROWS = [
    {"kind": "flight", "items": [{}], "text": "Code: RFA1654 is inside the Anak Krakatau ash area"},
    {"kind": "duty", "items": [{}], "out": None, "text": "Coordinator got 3 jobs"},
    {
        "kind": "duty",
        "items": [{}],
        "out": {"k": 1},
        "text": "Coordinator got 3 jobs · gave no result",
    },
    {
        "kind": "handoff:planner",
        "items": [{"skill": "planner"}],
        "text": "Coordinator handed a job",
    },
    {
        "kind": "skill:planner",
        "items": [{"skill": "planner"}],
        "text": "Used the price_divert tool",
    },
    {"kind": "skill:drafter", "items": [{"skill": "drafter"}], "text": "Drafted an advisory"},
    {"kind": "skill:plume", "items": [{"skill": "plume"}], "text": "Plume reader gave no result"},
    {"kind": "skill-failed", "items": [{"skill": "planner"}], "text": "Flight planner failed"},
    {"kind": "desk:drafter", "items": [{"skill": "drafter"}], "text": "Draft reached the Desk"},
    {"kind": "feed", "items": [{"feed": "sigmet"}], "text": "VA SIGMETs read: 3 current"},
    {"kind": "adsb", "items": [{}], "text": "Aircraft positions read (adsb.lol)"},
    {"kind": "adsb", "items": [{"feed": "airline"}], "text": "Airline positions pushed"},
    {"kind": "decided", "items": [{}], "text": "A dispatcher approved RFA1654"},
    {"kind": "note", "items": [{"actor": "gemini"}], "text": "A note from the model"},
    {"kind": "note", "items": [{"actor": "code"}], "text": "A note from code"},
]

TRACE = [
    _step(
        1,
        "POLL",
        "VA SIGMET (AWC): 3 new or changed record(s)",
        "10:30:10",
        detail={"feed": "sigmet"},
    ),
    _step(2, "EXPOSURE", "RFA1654 (GIA123) is inside the Anak Krakatau cone at FL350", "10:31:05"),
    _step(3, "DUTY", "Duty Officer: 2 item(s) to dispatch (scheduled)", "10:32:20", actor="adk"),
]


@pytest.fixture(scope="module")
def out(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    tmp = tmp_path_factory.mktemp("assist")
    (tmp / "wall").mkdir()
    for name in MODULES:
        shutil.copy(WALL / name, tmp / "wall" / name)
    (tmp / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    (tmp / "run.mjs").write_text(RUNNER, encoding="utf-8")
    (tmp / "input.json").write_text(json.dumps({"rows": ROWS, "trace": TRACE}), encoding="utf-8")
    result = subprocess.run(
        [str(NODE), "run.mjs", "input.json"],
        cwd=tmp,
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return json.loads(result.stdout)


def test_each_row_kind_names_its_step_actor_and_kind(out: dict[str, Any]) -> None:
    got = [(v["stage"], v["actor"], v["kind"]) for v in out["views"]]
    assert got == [
        ("code", "Code checks", "no AI"),
        ("ai", "Coordinator", "TEPHRA Assistant"),
        ("ai", "Coordinator", "TEPHRA Assistant"),
        ("ai", "Coordinator", "TEPHRA Assistant"),
        ("ai", "Flight planner", "TEPHRA Assistant"),
        ("ai", "Drafter", "TEPHRA Assistant"),
        ("ai", "Plume reader", "TEPHRA Assistant"),
        ("ai", "Flight planner", "TEPHRA Assistant"),
        ("ai", "Drafter", "TEPHRA Assistant"),  # a draft reaching the Desk: no person acted
        ("feeds", "SIGMET", "public feed"),
        ("feeds", "Aircraft positions", "public feed"),
        ("feeds", "Airline positions", "airline feed"),
        ("desk", "A person", "the Desk"),
        ("ai", "TEPHRA Assistant", None),
        ("code", "Code", "no AI"),
    ]
    assert out["noKind"] == "ai"


def test_result_words_follow_what_the_step_says(out: dict[str, Any]) -> None:
    results = [v["result"] for v in out["views"]]
    assert results == [
        None,
        None,
        "noresult",
        None,
        "tool",
        "done",
        "noresult",
        "noresult",
        "done",
        None,
        None,
        None,
        None,
        None,
        None,
    ]
    # the row's own words reach the panel unchanged (textContent)
    assert out["views"][0]["text"] == ROWS[0]["text"]


def test_the_rows_at_a_playhead_hold_only_steps_at_or_before_it(out: dict[str, Any]) -> None:
    rows = out["rows"]
    assert [r["tm"] for r in rows] == ["2026-09-05T10:31:05.000Z", "2026-09-05T10:30:10.000Z"]
    assert [r["stage"] for r in rows] == ["code", "feeds"]


def test_minute_groups_keep_the_newest_first_order(out: dict[str, Any]) -> None:
    assert out["groups"] == [["10:32 UTC", 1], ["10:31 UTC", 1], ["10:30 UTC", 1]]


def test_the_player_always_says_replay_and_never_a_bare_paused(out: dict[str, Any]) -> None:
    p = out["player"]
    for state in ("follow", "paused", "playing", "calm"):
        assert p[state]["lead"] == "Replay", state
        assert p[state]["live"] is False, state
    assert p["follow"]["text"] == "TEPHRA's steps on the replayed feeds, at the replay clock"
    assert p["follow"]["time"] == "10:32:20"
    assert p["follow"]["valuetext"] == "step at replay clock 10:32:20, the newest step"
    assert p["follow"]["button"] == "Pause the steps"
    # The player moves only the panel's steps: it never claims the replay itself is paused.
    assert p["paused"]["text"] == "steps paused at 10:31:00 (the replay clock runs on)"
    assert p["paused"]["button"] == "Play the steps from 10:31:00"
    assert p["playing"]["button"] == "Pause the steps"
    assert "Pause the replay" not in json.dumps(p)
    assert p["playing"]["text"] == "playing back from 10:30:00 at 8x"
    assert p["calm"]["text"] == "playing back from 10:30:00 one step at a time"
    assert "recorded" not in json.dumps(p)


def test_live_has_no_player_only_one_line(out: dict[str, Any]) -> None:
    live = out["player"]["live"]
    assert live == {"live": True, "lead": "Live", "text": "new steps appear as they come"}


def test_the_state_line_says_no_model_with_the_stub(out: dict[str, Any]) -> None:
    assert out["stub"]["strong"] == "NO MODEL"
    assert out["stub"]["text"] == "offline stub: code checks still run"
    assert out["stub"]["why"] is False
    assert (out["paused"]["text"], out["paused"]["why"]) == ("paused", True)
    assert out["trouble"]["text"] == "Flight planner gave no result"
    assert out["trouble"]["tone"] == "caution"
    assert (out["on"]["text"], out["on"]["tone"]) == ("on", "ok")
