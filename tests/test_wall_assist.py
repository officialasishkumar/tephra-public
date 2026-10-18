"""The demo's Assistant tab (SPEC v2 5.2.5): ``tephra/web/wall/assist.js`` under Node.

Each folded board row gets the step it belongs to, who took it and how it went; the rows at a
playhead hold only steps at or before it; the player always says "Replay" in REPLAY and never a
bare "paused"; LIVE has no player; with the offline stub the tab bar's one status says AI off.
On arrival the tab catches up on TEPHRA's last full chain of kept steps (lastChain): every beat
is recorded events, a chain with a part missing says so, and a run that did not run ends with the
must-do work passed to a person, never a skill. The module has no DOM, so these run on plain data.
Skipped when Node is not installed.
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
import { rowView, visibleRows, minuteGroups, playerWords, stageOf, lastChain, beatMs,
  chainNote, eventsShown, catchupSkills, sayBeat, rowsOf, CATCHUP_MS, RM_STEP_MS }
  from "./wall/assist.js";
import { flowEvents } from "./wall/board.js";
import { plainLine, stateLine } from "./wall/x-parts.js";
import { collapseRuns } from "./wall/dk.js";
const input = JSON.parse(readFileSync(process.argv[2], "utf8"));
const at = (hms) => Date.parse(`2026-09-05T${hms}Z`);
const views = input.rows.map((r) => rowView({ key: r.kind, at: at("10:30:00"), ...r }));
const M = { replay: true, events: flowEvents({ trace: input.trace, now: at("10:40:00") }).events };
const rows = visibleRows(M, at("10:31:30"));
const all = visibleRows(M, at("10:40:00"));
const P = (mode, t) => ({ mode, t: at(t), from: at(t), rm: false });
const chainOf = (trace, feeds = []) => {
  const C = lastChain({ events: flowEvents({ trace, feeds, now: at("10:50:00") }).events });
  return { full: C.full, missing: C.missing, note: chainNote(C),
    beats: C.beats.map((b) => ({ kind: b.kind, node: b.node, n: b.n, text: b.text, said: sayBeat(b),
      at: new Date(b.at).toISOString(), feeds: b.feeds || null })) };
};
const FM = { events: flowEvents({ trace: input.full, now: at("10:50:00") }).events };
const FC = lastChain(FM);
const firstBeat = new Set(FC.beats[0].ids);
// an airline's own TEPHRA: its flights by callsign, flight number or registration, one minute
const OM = { events: flowEvents({ trace: input.own, now: at("10:50:00") }).events };
const OC = lastChain(OM);
const upTo = (i) => new Set(OC.beats.slice(0, i + 1).flatMap((b) => b.ids));
const runs = collapseRuns(input.ownRuns.map((text, i) => ({ text, t: i })),
  { textOf: (x) => x.text, timeOf: (x) => x.t });
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
    catchup: playerWords(M, P("catchup", "10:31:05")),
    waiting: playerWords(M, P("waiting", "10:31:05")),
  },
  chains: {
    full: chainOf(input.full),
    refused: chainOf(input.refused),
    partial: chainOf(input.partial),
    empty: chainOf([]),
    stateRead: chainOf(input.partial.slice(1), [{ feed: "vaac_darwin", status: "OK",
      last_success_at: "2026-09-05T10:45:00.500Z", record_count: 4 }]),
  },
  shownAtStart: eventsShown(FM, FC, firstBeat).map((e) => e.type),
  own: {
    events: OM.events.map((e) => ({ type: e.type, flight: e.flight ?? null })),
    chain: { full: OC.full, missing: OC.missing,
      beats: OC.beats.map((b) => ({ kind: b.kind, n: b.n, text: b.text })) },
    plain: input.own.map((t) => plainLine(t.message)),
    runs: runs.map((r) => r.label),
    // the catch-up at each beat: the log's rows and each skill's row
    shown: OC.beats.map((b, i) => rowsOf(eventsShown(OM, OC, upTo(i))).map((r) => r.text)),
    skills: OC.beats.map((b, i) => catchupSkills(OM, OC, i)),
    say: OC.beats.map(sayBeat),
  },
  pace: { six: beatMs(6), two: beatMs(2), twenty: beatMs(20), rm: beatMs(6, true),
    total: CATCHUP_MS, rmStep: RM_STEP_MS },
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
    {"kind": "flight", "items": [{}], "text": "RFA1654 is inside the Anak Krakatau ash area"},
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


POLL = {"feed": "sigmet"}
FULL = [
    _step(10, "POLL", "VA SIGMET (AWC): 3 new or changed record(s)", "10:30:10", detail=POLL),
    _step(11, "EXPOSURE", "RFA1654 (GIA123) is inside the Anak Krakatau cone at FL350", "10:31:05"),
    _step(12, "DUTY", "Duty Officer: 1 item(s) to dispatch (scheduled)", "10:31:06", actor="adk"),
    _step(13, "PLANNER", "NO MODEL: MONITOR", "10:31:07", actor="stub"),
    _step(14, "DRAFTER", "DRAFT MONITOR (NO MODEL)", "10:31:07", actor="stub"),
    _step(15, "DESK", "RFA1654: DRAFT MONITOR waiting for a dispatcher", "10:31:07"),
    _step(
        16,
        "DUTY",
        "Duty Officer -> plan_flights: RFA1654: DRAFT MONITOR for a dispatcher",
        "10:31:08",
        actor="adk",
    ),
    # a newer run that put nothing in front of a person: not a full chain, so the one above plays
    _step(20, "EXPOSURE", "RFA7012 (AWQ240) is inside the Anak Krakatau cone at FL051", "10:35:00"),
    _step(21, "PLANNER", "NO MODEL: MONITOR", "10:35:01", actor="stub"),
    _step(
        22,
        "DUTY",
        "Duty Officer -> plan_flights: RFA7012: same advice as an open draft",
        "10:35:02",
        actor="adk",
    ),
]
REFUSED = [
    _step(30, "POLL", "VA SIGMET (AWC): 2 new or changed record(s)", "10:40:00", detail=POLL),
    _step(31, "EXPOSURE", "RFA1654 (GIA123) is inside the Anak Krakatau cone at FL350", "10:40:01"),
    _step(32, "DUTY", "Duty Officer: 2 item(s) to dispatch (scheduled)", "10:40:02", actor="adk"),
    _step(
        33,
        "DUTY",
        "Duty Officer AI UNAVAILABLE (budget: no calls left); 0 delegation(s) made,"
        " 2 mandatory item(s) to the Desk",
        "10:40:03",
        actor="code",
    ),
]
# an airline's own TEPHRA (batch 2 honesty finding 1): its flights are named by callsign, flight
# number or registration, never RFA; the replay's minute clock gives the whole tick one time
OWN_EXPOSED = (
    "RFB401 (RFB401) is inside the Anak Krakatau cone at FL350",
    "RB555 (PK-RFZ) enters the Anak Krakatau cone in 12 min at FL310 if track and level are held",
    "PK-RFX (PK-RFX) is inside the Anak Krakatau cone at FL120",
)
OWN = [
    _step(50, "POLL", "VA SIGMET (AWC): 2 new or changed record(s)", "10:30:00", detail=POLL),
    *(_step(51 + i, "EXPOSURE", text, "10:30:00") for i, text in enumerate(OWN_EXPOSED)),
    _step(55, "DUTY", "Duty Officer: 1 item(s) to dispatch (scheduled)", "10:30:00", actor="adk"),
    _step(56, "PLANNER", "NO MODEL: MONITOR", "10:30:00", actor="stub"),
    _step(57, "DRAFTER", "DRAFT MONITOR (NO MODEL)", "10:30:00", actor="stub"),
    _step(58, "DESK", "RFB401: DRAFT REROUTE waiting for a dispatcher", "10:30:00"),
    _step(
        59,
        "DUTY",
        "Duty Officer -> plan_flights: RFB401: DRAFT REROUTE for a dispatcher",
        "10:30:00",
        actor="adk",
    ),
]
OWN_RUNS = [
    "RFB401 is inside TEPHRA's area at Anak Krakatau, FL350",
    "PK-RFX is inside TEPHRA's area at Anak Krakatau, FL350",
]
PARTIAL = [
    _step(40, "POLL", "VA SIGMET (AWC): 1 new or changed record(s)", "10:45:00", detail=POLL),
    _step(41, "EXPOSURE", "RFA1654 (GIA123) is inside the Anak Krakatau cone at FL350", "10:45:01"),
]


@pytest.fixture(scope="module")
def out(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    tmp = tmp_path_factory.mktemp("assist")
    (tmp / "wall").mkdir()
    for name in MODULES:
        shutil.copy(WALL / name, tmp / "wall" / name)
    (tmp / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    (tmp / "run.mjs").write_text(RUNNER, encoding="utf-8")
    (tmp / "input.json").write_text(
        json.dumps(
            {
                "rows": ROWS,
                "trace": TRACE,
                "full": FULL,
                "refused": REFUSED,
                "partial": PARTIAL,
                "own": OWN,
                "ownRuns": OWN_RUNS,
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [str(NODE), "run.mjs", "input.json"],
        cwd=tmp,
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return json.loads(result.stdout)


def test_each_row_kind_names_its_step_and_actor_with_no_kind_tag(out: dict[str, Any]) -> None:
    got = [(v["stage"], v["actor"]) for v in out["views"]]
    assert got == [
        ("code", "Code checks"),
        ("ai", "Coordinator"),
        ("ai", "Coordinator"),
        ("ai", "Coordinator"),
        ("ai", "Flight planner"),
        ("ai", "Drafter"),
        ("ai", "Plume reader"),
        ("ai", "Flight planner"),
        ("ai", "Drafter"),  # a draft reaching the Desk: no person acted
        ("feeds", "SIGMET"),
        ("feeds", "Aircraft positions"),
        ("feeds", "Airline positions"),
        ("desk", "A person"),
        ("ai", "TEPHRA Assistant"),
        ("code", "Code"),
    ]
    # the row names its actor only: no "public feed" / "TEPHRA Assistant" tag under it
    assert all("kind" not in v for v in out["views"])
    assert out["noKind"] == "ai"


def test_result_words_follow_what_the_step_says(out: dict[str, Any]) -> None:
    results = [v["result"] for v in out["views"]]
    # a Coordinator run says its outcome in its words, so it carries no "No result" badge too
    assert results == [
        None,
        None,
        None,
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
    # one short line each (owner, 17 Oct: "too much text")
    assert p["follow"]["text"] == "following the clock"
    assert p["catchup"]["text"] == "catching up"
    assert p["catchup"]["lead"] == "Replay"
    assert p["catchup"]["time"] == "10:31:05"
    assert p["follow"]["time"] == "10:32:20"
    assert p["follow"]["valuetext"] == "step at replay clock 10:32:20, the newest step"
    assert p["follow"]["button"] == "Pause the steps"
    # The player moves only the panel's steps: it never claims the replay itself is paused.
    assert p["paused"]["text"] == "paused at 10:31:00, replay clock runs on"
    assert p["paused"]["button"] == "Play the steps from 10:31:00"
    assert p["playing"]["button"] == "Pause the steps"
    assert "Pause the replay" not in json.dumps(p)
    assert p["playing"]["text"] == "playing back from 10:30:00 at 8x"
    assert p["calm"]["text"] == "playing back from 10:30:00 one step at a time"
    assert "recorded" not in json.dumps(p)


def test_live_has_no_player_only_one_line(out: dict[str, Any]) -> None:
    live = out["player"]["live"]
    # LIVE is said once, by the header's pill: the player line has no "Live" lead
    assert live == {"live": True, "lead": "", "text": "new steps appear as they come"}


def test_the_one_status_shows_only_when_not_normal(out: dict[str, Any]) -> None:
    """Owner, 17 Oct: "don't say no model everywhere". The assistant's state is said once, a
    shape and two words in the tab bar, only when it is not working normally; the explanation is
    behind its info button, and the screen-reader words keep the state in every case."""
    stub = out["stub"]
    assert (stub["word"], stub["tone"], stub["why"]) == ("AI off", "off", False)
    assert stub["info"] == (
        "Offline stub: no model is connected. Code checks still run, and code templates write"
        " the drafts."
    )
    assert stub["said"] == "TEPHRA Assistant off: no model is connected."
    assert (out["paused"]["word"], out["paused"]["why"]) == ("AI paused", True)
    assert out["trouble"]["word"] == "AI unavailable"
    assert out["trouble"]["info"].startswith("Flight planner gave no result.")
    assert out["trouble"]["tone"] == "caution"
    # working normally: nothing on screen, the state still said to a screen reader
    assert (out["on"]["word"], out["on"]["info"]) == (None, None)
    assert out["on"]["said"] == "TEPHRA Assistant on."


def test_the_catch_up_plays_the_newest_full_chain_in_pipeline_order(out: dict[str, Any]) -> None:
    full = out["chains"]["full"]
    assert full["full"] is True
    assert full["missing"] == []
    assert full["note"] == ""
    kinds = [(b["kind"], b["node"]) for b in full["beats"]]
    assert kinds == [
        ("feeds", "code"),
        ("code", "code"),
        ("coord", "coord"),
        ("skill", "sk-planner"),
        ("skill", "sk-drafter"),
        ("you", "you"),
    ]
    # the newer run at 10:35 left nothing for a person; the chain is the 10:31 one, real steps only
    assert all(b["at"] < "2026-09-05T10:32:00" for b in full["beats"])
    assert full["beats"][0]["feeds"] == ["sigmet"]
    assert full["beats"][1]["text"] == "Code checks flagged 1 flight"
    assert full["beats"][2]["text"] == "Coordinator handed out 1 job"
    assert full["beats"][-1]["text"] == "1 draft reached the Desk for a person"


def test_a_run_that_did_not_run_passes_must_do_work_and_reaches_no_skill(
    out: dict[str, Any],
) -> None:
    refused = out["chains"]["refused"]
    assert refused["full"] is True
    kinds = [b["kind"] for b in refused["beats"]]
    assert kinds == ["feeds", "code", "coord", "you"]
    assert "skill" not in kinds
    # the hero says the count as it bumps: the beat line names the step,
    # the screen reader hears both
    assert refused["beats"][-1]["text"] == "To You decide"
    assert refused["beats"][-1]["said"] == "Replay, catching up: 2 must-do flights passed to you."


def test_a_part_of_a_chain_plays_as_it_is_and_says_what_is_missing(out: dict[str, Any]) -> None:
    partial = out["chains"]["partial"]
    assert partial["full"] is False
    assert [b["kind"] for b in partial["beats"]] == ["feeds", "code"]
    assert partial["missing"] == ["Coordinator run", "step to You decide"]
    assert partial["note"] == "Showing the latest steps. Earlier ones ran before this page opened."
    empty = out["chains"]["empty"]
    assert empty["beats"] == []
    assert empty["note"] == "No steps held on this page yet to catch up on."


def test_a_feed_read_the_state_reports_feeds_the_chain(out: dict[str, Any]) -> None:
    """A feed's last read (its last_success_at, no POLL step) is a kept step too."""
    beats = out["chains"]["stateRead"]["beats"]
    assert beats[0]["kind"] == "feeds"
    assert beats[0]["feeds"] == ["vaac_darwin"]


def test_the_catch_up_shows_only_what_it_has_played(out: dict[str, Any]) -> None:
    # at the first beat: the feed read, none of the run's later steps
    assert out["shownAtStart"] == ["feed"]


def test_the_catch_up_takes_about_sixteen_seconds(out: dict[str, Any]) -> None:
    pace = out["pace"]
    assert pace["total"] == 16000
    assert 15000 <= pace["six"] * 6 <= 20000
    assert pace["two"] == 3200  # a short chain is never rushed
    assert pace["twenty"] == 1600  # nor a long one too fast to follow
    assert pace["rm"] == pace["rmStep"] == 2200


def test_an_airlines_own_flights_are_flight_steps_and_reach_the_catch_up(
    out: dict[str, Any],
) -> None:
    """In an airline's own TEPHRA the pipeline names a flight by its callsign, flight number or
    registration (geo/fleet.py flight_name), never RFA: the steps are still flight alerts and
    drafts at the Desk, so Code checks counts them and the catch-up finds a whole chain."""
    own = out["own"]
    flights = [e["flight"] for e in own["events"] if e["type"] == "flight"]
    assert flights == ["RFB401", "RB555", "PK-RFX"]
    assert [e["flight"] for e in own["events"] if e["type"] == "desk"] == ["RFB401"]
    assert own["chain"]["full"] is True
    kinds = [b["kind"] for b in own["chain"]["beats"]]
    assert kinds == ["feeds", "code", "coord", "skill", "skill", "you"]
    assert own["chain"]["beats"][1]["text"] == "Code checks flagged 3 flights"
    plain = own["plain"]
    assert plain[1] == "RFB401 is inside TEPHRA's area at Anak Krakatau, FL350"
    assert plain[2].startswith("RB555 enters TEPHRA's area at Anak Krakatau in 12 min")
    assert plain[3] == "PK-RFX is inside TEPHRA's area at Anak Krakatau, FL120"
    assert (
        plain[7] == "RFB401: advisory drafted to reroute around the ash, waiting for a dispatcher"
    )
    assert not any("cone" in line for line in plain)
    # repeated lines fold by flight name, whatever the airline
    assert own["runs"] == ["RFB401 and PK-RFX are inside TEPHRA's area at Anak Krakatau, FL350"]


def test_the_catch_up_log_follows_the_beats_in_play_order(out: dict[str, Any]) -> None:
    """With the replay's minute clock a tick's steps share one time: the log during the catch-up
    still holds only the beats played so far, newest beat first (batch 2 UX finding 3/4)."""
    shown = out["own"]["shown"]
    assert shown[0] == ["VA SIGMETs read: 2 current"]
    assert shown[1][0].startswith("RFB401, RB555 +1")
    # the row's actor ("Coordinator") is said once, beside the text, not again in it
    assert shown[2][0] == "Handed a job to Flight planner"
    assert shown[-1][0] == "Advisory draft for RFB401 reached the Desk"
    assert [len(rows) for rows in shown] == sorted(len(rows) for rows in shown)


def test_each_skill_row_shows_its_state_at_the_beat_playing(out: dict[str, Any]) -> None:
    """In line once the Coordinator's beat handed it a job, running during its own beat, then
    done (batch 2 UX finding 5): the row changes as the beat plays, never the state now."""
    skills = out["own"]["skills"]
    assert skills[0] == {}
    assert skills[1] == {}
    assert skills[2] == {"planner": {"state": "inline", "n": 1}}
    assert skills[3]["planner"]["state"] == "running"
    assert skills[4]["planner"]["state"] == "done"
    assert skills[4]["drafter"]["state"] == "running"
    assert {k: v["state"] for k, v in skills[5].items()} == {"planner": "done", "drafter": "done"}


def test_the_catch_up_is_said_as_the_replay_s_steps(out: dict[str, Any]) -> None:
    """A screen reader hears each beat as the replay catching up, never "New step" for a step from
    the past (batch 2 honesty finding 5)."""
    say = out["own"]["say"]
    assert say[0] == "Replay, catching up: Feed reads: SIGMET."
    assert all(line.startswith("Replay, catching up: ") for line in say)
    assert not any("New step" in line for line in say)
    panel = (WALL / "assist-panel.js").read_text(encoding="utf-8")
    assert 'if (newestKey && P.mode === "follow") say(top);' in panel
    assert "sayNow(sayBeat(b));" in panel


def test_before_the_catch_up_the_player_says_it_is_about_to_catch_up(out: dict[str, Any]) -> None:
    w = out["player"]["waiting"]
    assert (w["lead"], w["text"]) == ("Replay", "about to catch up")
    assert w["time"] is None
