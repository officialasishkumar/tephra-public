"""A hosted airline with no usable model (no model chosen, no key, an unreadable key) is told
AI UNAVAILABLE and that the step did not run: no page says a model was called or "gave no
result" for it (SPEC §0 rule 3, §5.8). The pages' own word tables are run under Node."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tephra.hosted import settings_for

WALL = Path(__file__).resolve().parents[1] / "tephra" / "web" / "wall"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

REASONS = [settings_for.NO_KEY, settings_for.NO_MODEL, settings_for.UNREADABLE]

SCRIPT = """
const x = await import("./x-parts.js");
const d = await import("./duty.js");
const reasons = JSON.parse(process.argv[1]);
const out = reasons.map((r) => {
  const cls = x.reasonClass(r);
  const cause = {
    reasonClass: cls, helper: "Coordinator", steps: 1, items: [{ reason: r }], raw: [r],
  };
  const run = {
    outcome: "MODEL_FAILED", validation_errors: [r], worklist: [], dispatches: [], deferred: [],
    undispatched: [], turns: 0, model_id: "gemini-3.5-flash-lite",
  };
  const coordinator = `Duty Officer AI UNAVAILABLE (${r}); 0 delegation(s) made, `
    + "2 mandatory item(s) to the Desk";
  return {
    cls,
    notRun: x.notRun(cls),
    plainWhy: x.plainWhy(cls),
    home: x.causeShort(cause, { home: true }),
    main: x.causeShort(cause),
    title: x.causeTitle(cause, { home: true }),
    duty: d.outcomeOf(run),
    dutyWords: d.OUTCOME[d.outcomeOf(run)],
    plume: x.plumeOutcome("MODEL_FAILED", `AI UNAVAILABLE: ${r}.`),
    line: x.plainLine(coordinator),
  };
});
const budget = x.reasonClass("budget_exhausted");
const other = x.plumeOutcome("MODEL_FAILED", "no usable model output");
console.log(JSON.stringify({ out, budget, other }));
"""


def run_words() -> dict[str, object]:
    assert NODE is not None
    done = subprocess.run(
        [NODE, "--input-type=module", "-e", SCRIPT, json.dumps(REASONS)],
        cwd=WALL,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return json.loads(done.stdout)


def test_no_usable_model_is_ai_unavailable_and_never_a_model_call() -> None:
    words = run_words()
    for row in words["out"]:  # type: ignore[index]
        assert row["cls"] == "unavailable"
        assert row["notRun"] is True
        assert row["plainWhy"] is None  # a main view says only that it did not run
        assert row["main"] == "Coordinator did not run"
        assert row["home"].startswith("Coordinator did not run (AI UNAVAILABLE: ")
        assert "AI UNAVAILABLE" in row["title"]
        assert row["duty"] == "UNAVAILABLE"
        assert row["dutyWords"][1] == "Not run"
        assert "no model was called" in row["dutyWords"][2]
        assert row["plume"] == "UNAVAILABLE"
        assert row["line"].startswith("Coordinator did not run.")
        for text in (row["main"], row["home"], row["title"], row["dutyWords"][2], row["line"]):
            assert "gave no result" not in text
            assert "was called" not in text.replace("no model was called", "")


def test_a_quota_refusal_and_a_model_that_answered_badly_keep_their_words() -> None:
    words = run_words()
    assert words["budget"] == "budget"
    assert words["other"] == "MODEL_FAILED"  # a model was called: "gave no result" stays true


def test_every_place_that_says_did_not_run_for_a_quota_says_it_for_no_model_too() -> None:
    """No page compares a reason class to "budget" alone to choose "did not run": it asks
    ``notRun``, which also holds for an airline with no usable model."""
    web = WALL.parent
    for path in [*WALL.glob("*.js"), web / "desk" / "failures.js", web / "desk" / "network.js"]:
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if "did not run" in line and ('=== "budget"' in line or "=== 'budget'" in line):
                if "paused" in line or "aiState" in line:
                    continue  # the paused state is the quota's alone
                raise AssertionError(f"{path.name}: {line.strip()}")


STATE_SCRIPT = """
const x = await import("./x-parts.js");
const reason = process.argv[1];
const budget = {
  backend: "gemini", resets_at: "2026-09-06T07:00:00Z", unavailable: reason, waiting: [],
  models: [{ model_id: "gemini-3.5-flash-lite", jobs: "Every other AI step", used: 0, limit: 18,
    remaining: 18, closed: false }],
  tiers: [{ tier: "lite", model_id: "gemini-3.5-flash-lite", used: 0, limit: 18, remaining: 18 }],
};
const why = `DUTY OFFICER AI UNAVAILABLE: ${reason}`;
const plume = "Plume read: Anak Krakatau (sources or aircraft changed): not dispatched";
const errors = [
  { stage: "DUTY", reason: why, at: 1, raw: "r" },
  { stage: "DUTY", reason: plume, at: 2, raw: "p" },
];
const ai = x.aiStateOf({ budget, errors });
const plain = x.aiStateOf({ budget: { ...budget, unavailable: null } });
const stub = x.aiStateOf({ stub: true, budget });
const w = x.aiWords(ai);
const line = x.stateLine(w, { kind: ai.kind, reason: ai.reason });
console.log(JSON.stringify({
  titles: ai.causes.map((c) => x.causeTitle(c, { home: true })),
  kind: ai.kind, trouble: ai.trouble.length, causes: ai.causes.length, line, words: w,
  lead: x.aiLead(ai), main: x.aiLead(ai, { home: false }), block: x.draftBlock(ai),
  bare: x.draftBlock(x.aiStateOf({ budget })), plain: plain.kind, stub: stub.kind,
}));
"""


@pytest.mark.parametrize("reason", REASONS)
def test_an_airline_with_no_usable_model_reads_ai_unavailable_with_its_reason(reason: str) -> None:
    """Merge verify, 17 Oct: a no-key airline's Desk said "TEPHRA Assistant on" and its map's
    Details "On · 1 problem". The budget names the airline's reason (BudgetView.unavailable), and
    that is the one state, "AI unavailable", its (i) giving the reason and where it is set."""
    assert NODE is not None
    done = subprocess.run(
        [NODE, "--input-type=module", "-e", STATE_SCRIPT, reason],
        cwd=WALL,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    r = json.loads(done.stdout)
    assert r["kind"] == "unavailable"
    assert (r["plain"], r["stub"]) == ("on", "off")
    # its own refused steps are the state, not "problems" on top of it; a plume read the
    # Coordinator could not hand out did not run either (no skill was called)
    assert (r["trouble"], r["causes"]) == (0, 2)
    said = reason[0].upper() + reason[1:] + "."
    assert r["line"]["word"] == "AI unavailable"
    assert r["line"]["info"].startswith(f"{said} Fix it in Settings › Assistant.")  # noqa: RUF001
    assert reason in r["line"]["said"]
    assert reason in r["words"]["aria"]
    assert " on." not in r["words"]["aria"]
    assert r["lead"][0]["strong"] == "TEPHRA Assistant is unavailable."
    assert said in r["lead"][0]["text"]
    # a main view says the state and what holds, not the reason (the (i) and the home say it)
    assert said not in r["main"][0]["text"]
    # a place without its draft says the step did not run, never "gave no result"
    assert r["block"]["word"] == "Coordinator did not run"
    assert r["bare"]["word"] == "Drafter did not run"
    assert all("did not run" in title for title in r["titles"])
    for out in (r["line"], r["words"], r["lead"], r["block"], r["titles"]):
        assert "gave no result" not in json.dumps(out)
