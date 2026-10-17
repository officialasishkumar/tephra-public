"""The Why chain behind an advisory (redesign T22): Decisions rows offer it, ``wall/chain.js``
renders four steps whose model-written text each sits under a mark, the chain says no quota word,
nulls read "not on hand", and the widened-estimate map pill quotes code words only. The view is
run under Node against a small DOM stand-in; the rest is a static read of the sources."""

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

WEB = Path(__file__).resolve().parents[1] / "tephra" / "web"
NODE = shutil.which("node")

# The quota words that never reach a main view (tests/test_ui_ai_quiet.py, copied: rule 3).
QUOTA_TEXT = re.compile(
    r"quota|used up|closed by google|free ai|next slot|\bspent\b|calls today|calls left"
    r"|share of calls|\bpacing\b|resets? (?:at|once)|reset was due|AI budget",
    re.I,
)
STRING = re.compile(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`")
COMMENT = re.compile(r"^\s*(//|/\*|\*)")

# Sentinels for every model-written field of the chain record: each must be found under a mark.
MODEL_TEXT = {
    "coordinator.why": "Zq1 the flight enters first and the hold burns little",
    "plume.reading": "Zq2 the observatory saw the ash drift east",
    "plume.why": "Zq3 the newer report is the observer's own",
    "plume.rationale": "Zq4 widened along the observed drift",
    "plume.uncertainty": "Zq5 night: the satellite is blind",
    "plan.reasoning": "Zq6 a climb clears the band with margin",
}

CHAIN: dict[str, Any] = {
    "advisory_id": "adv_0123456789ab",
    "flight": "RFA123",
    "volcano_name": "Anak Krakatau",
    "coordinator": {
        "run_id": "duty_1",
        "decided_at": "2026-09-05T11:00:00.000Z",
        "outcome": "ACCEPTED",
        "rank": 2,
        "of": 24,
        "why": MODEL_TEXT["coordinator.why"],
    },
    "plume": {
        "assessment_id": "asm_1",
        "model_id": "gemini-x",
        "outcome": "REPAIRED",
        "attempts": 2,
        "mode": "WIDENED",
        "base_fl": 0,
        "top_fl": 500,
        "sources_used": ["vaac:darwin:1", "vona:krakatau:1"],
        "leaned_on": [
            {
                "discrepancy_id": "dis_1",
                "which_source_we_lean_on": "vona:krakatau:1",
                "reading": MODEL_TEXT["plume.reading"],
                "why": MODEL_TEXT["plume.why"],
            }
        ],
        "rationale": MODEL_TEXT["plume.rationale"],
        "uncertainty_notes": MODEL_TEXT["plume.uncertainty"],
        "latency_ms": 2300,
        "input_tokens": 100,
        "output_tokens": 50,
        "checks": ["citations", "times", "numbers", "mode", "geometry", "hypothesis", "narrowing"],
    },
    "plan": {
        "plan_id": "plan_1",
        "model_id": "gemini-x",
        "outcome": "REPAIRED",
        "repaired": True,
        "tool_calls": [
            {"name": "exposure", "args": {}, "result_summary": "inside in 12 min"},
            {"name": "level_bands", "args": {}, "result_summary": "FL280-FL300 clear"},
        ],
        "reasoning": MODEL_TEXT["plan.reasoning"],
        "reasoning_checks": ["clock words"],
        "action": "CHANGE_LEVEL",
        "target": "FL280-FL300",
        "input_tokens": 100,
        "output_tokens": 50,
        "checks": ["allowed action", "level band clear of the hazard", "reasoning"],
    },
    "draft": {
        "model_id": "gemini-x",
        "outcome": "REPAIRED",
        "repaired": True,
        "numbers_in_body": 7,
        "validation_notes": ["a number not in the facts"],
        "drafted_at": "2026-09-05T11:02:00.000Z",
        "checks": ["allowed action", "numbers from facts", "no clock times"],
    },
}
SIT = {
    "volcano_id": "krakatau",
    "cards": [
        {"source_id": "vona:krakatau:1", "title": "VONA 2026KRA12"},
        {"source_id": "vaac:darwin:1", "title": "VAA Darwin 05/1030Z"},
    ],
    "discrepancies": [{"id": "dis_1", "values": {"vaac:darwin:1": "E", "vona:krakatau:1": "ENE"}}],
}
STUB_CHAIN = json.loads(json.dumps(CHAIN))
for part in ("plume", "plan", "draft"):
    STUB_CHAIN[part]["model_id"] = "stub"
    STUB_CHAIN[part]["outcome"] = "STUB"
STUB_CHAIN["coordinator"]["outcome"] = "STUB"
STUB_CHAIN["coordinator"]["why"] = "NO MODEL: urgency order"
STUB_CHAIN["plume"]["leaned_on"] = []
STUB_CHAIN["plan"]["tool_calls"] = []
NULL_CHAIN = {**CHAIN, "coordinator": None, "plume": None, "plan": None}

# A DOM stand-in just wide enough for el(), icon() and the Details kit: a tree of elements with
# class names, data attributes and text, serialised for the assertions below.
RUNNER = """
class Node {
  constructor(tag) {
    this.tagName = tag; this.className = ""; this.dataset = {}; this.attrs = {};
    this.kids = []; this.style = {}; this._text = null; this.parentElement = null;
  }
  get classList() {
    const n = this;
    return { add: (c) => { n.className = `${n.className} ${c}`.trim(); } };
  }
  set textContent(t) { this.kids = []; this._text = String(t); }
  get textContent() {
    return this._text != null ? this._text : this.kids.map((k) => k.textContent).join("");
  }
  setAttribute(k, v) { this.attrs[k] = String(v); if (k === "class") this.className = String(v); }
  getAttribute(k) { return this.attrs[k] ?? null; }
  append(...kids) { for (const k of kids) { k.parentElement = this; this.kids.push(k); } }
  prepend(...kids) { for (const k of kids) { k.parentElement = this; this.kids.unshift(k); } }
  replaceChildren(...kids) { this.kids = []; this.append(...kids); }
  remove() {}
  querySelector() { return null; }
  querySelectorAll() { return []; }
  addEventListener() {}
  toJSON() {
    const { tagName: tag, className: cls, dataset: data, attrs, _text: text, kids } = this;
    return { tag, cls, data, attrs, text, kids };
  }
}
class Text extends Node { constructor(t) { super("#text"); this._text = String(t); } }
globalThis.Node = Node;
globalThis.document = {
  createElement: (t) => new Node(t), createElementNS: (_, t) => new Node(t),
  createTextNode: (t) => new Text(t), getElementById: () => null,
};
globalThis.window = { matchMedia: () => ({ matches: false }), innerWidth: 1440 };
const { chainView, chainSection } = await import("./wall/chain.js");
const input = JSON.parse(process.argv[2]);
const out = {};
for (const [name, c] of Object.entries(input.chains)) {
  out[name] = {
    wall: chainView(c, { sit: input.sit, mode: "wall" }),
    desk: chainView(c, { sit: null, mode: "desk" }),
  };
}
const host = new Node("div");
const adv = {
  id: "adv_0123456789ab", proxy_flight: "RFA123", volcano_id: "krakatau",
  action: "CHANGE_LEVEL", change_level_fl_min: 280, change_level_fl_max: 300,
};
globalThis.fetch = async () => ({ ok: false, status: 404 });
const ui = { details: { sec: "chain", vid: adv.id } };
chainSection({ sits: [input.sit] }, { advisories: [adv] }, ui, host);
out.sectionFirst = JSON.parse(JSON.stringify(host));
await new Promise((r) => setTimeout(r, 20));
out.sectionMissed = JSON.parse(JSON.stringify(host));
process.stdout.write(JSON.stringify(out));
"""

pytestmark = pytest.mark.skipif(NODE is None, reason="Node is not installed")


def _read(rel: str) -> str:
    return (WEB / rel).read_text(encoding="utf-8")


def _function(source: str, name: str) -> str:
    start = source.index(f"function {name}(")
    pattern = r"\n(?:export )?(?:async )?function |\nconst [A-Za-z_]+ = \("
    nxt = re.search(pattern, source[start + 1 :])
    return source[start : start + 1 + nxt.start()] if nxt else source[start:]


@pytest.fixture(scope="module")
def rendered(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    root = tmp_path_factory.mktemp("chain")
    (root / "wall").mkdir()
    for name in ("chain.js", "util.js", "x-parts.js", "dk.js", "derive.js"):
        shutil.copy(WEB / "wall" / name, root / "wall" / name)
    (root / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    (root / "run.mjs").write_text(RUNNER, encoding="utf-8")
    payload = json.dumps(
        {"chains": {"model": CHAIN, "stub": STUB_CHAIN, "nulls": NULL_CHAIN}, "sit": SIT}
    )
    result = subprocess.run(
        [str(NODE), "run.mjs", payload],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return json.loads(result.stdout)


def _text(node: dict[str, Any]) -> str:
    if node["text"] is not None:
        return node["text"]
    return "".join(_text(k) for k in node["kids"])


def _walk(node: dict[str, Any], path: tuple[dict[str, Any], ...] = ()):
    here = (*path, node)
    yield here
    for kid in node["kids"]:
        yield from _walk(kid, here)


def _has_class(node: dict[str, Any], cls: str) -> bool:
    return cls in node["cls"].split()


def _find(node: dict[str, Any], cls: str) -> list[dict[str, Any]]:
    return [p[-1] for p in _walk(node) if _has_class(p[-1], cls)]


def _marks(node: dict[str, Any]) -> list[str]:
    return [m["attrs"].get("aria-label", "") for m in _find(node, "ai-mark")]


# ---------------------------------------------------------------- the row and the hook


def test_decisions_rows_offer_why() -> None:
    preview = _function(_read("wall/panels.js"), "draftPreview")
    assert 'dataset: { act: "chain", vid: a.id' in preview
    assert 'text: "Why ›"' in preview  # noqa: RUF001  the UI's own chevron
    assert 'class: "dk-dec__links"' in preview
    assert ".dk-dec__links {" in _read("wall.css")
    # the click reaches the chain section in the flight host (wall.js and details.js, wall-shell's)
    assert 'else if (act === "chain") openDetails("chain", { vid: t.dataset.vid' in _read("wall.js")
    assert '{ key: "chain", title: "Why this advice", host: "flights", hidden: true }' in _read(
        "wall/details.js"
    )


# ---------------------------------------------------------------- the four steps


def test_chain_view_names_each_skill_once_in_order(rendered: dict[str, Any]) -> None:
    for surface in ("wall", "desk"):
        view = rendered["model"][surface]
        steps = _find(view, "chain__step")
        assert [s["data"]["step"] for s in steps] == ["coordinator", "plume", "plan", "draft"]
        skills = [_text(n) for n in _find(view, "chain__skill")]
        assert skills == ["Coordinator", "Plume reader", "Flight planner", "Drafter"]
        lines = " ".join(_text(n) for n in _find(view, "chain__line"))
        for name in skills:
            assert name not in lines  # the line never repeats the step's title


def test_chain_view_marks_every_model_text(rendered: dict[str, Any]) -> None:
    for surface in ("wall", "desk"):
        view = rendered["model"][surface]
        wanted = dict(MODEL_TEXT)
        if surface == "wall":  # the rationale lives under TEPHRA's estimate, linked
            del wanted["plume.rationale"]
            del wanted["plume.uncertainty"]
            assert "Zq4" not in _text(view)
            assert any(
                n["data"].get("sec") == "estimate" and _text(n) == "TEPHRA's estimate ›"  # noqa: RUF001
                for n in _find(view, "dk-link")
            )
        for field, sentinel in wanted.items():
            hits = [p for p in _walk(view) if p[-1]["text"] and sentinel in p[-1]["text"]]
            assert hits, (surface, field)
            path = hits[0]
            step = next(n for n in path if _has_class(n, "chain__step"))
            marks = _marks(step)
            assert marks, (surface, field)
            assert all(m.startswith(("Chosen by", "Read by", "Drafted by")) for m in marks), marks
            if field == "plan.reasoning":
                # only under "More", beside its own mark, never on the one-line summary
                assert any(_has_class(n, "chain__more") for n in path)
                block = next(n for n in path if _has_class(n, "chain__reasoning"))
                assert _marks(block) == ["Chosen by TEPHRA Assistant (gemini-x)"]
                head = next(n for n in _find(step, "chain__head"))
                assert sentinel not in _text(head)


def test_chain_view_lines_hold_code_words(rendered: dict[str, Any]) -> None:
    view = rendered["model"]["wall"]
    lines = {
        s["data"]["step"]: _text(_find(s, "chain__line")[0]) for s in _find(view, "chain__step")
    }
    assert lines["coordinator"] == f"Planned 2 of 24 · {MODEL_TEXT['coordinator.why']}"
    assert (
        lines["plume"]
        == "Wider than official FL000-FL500 · leaned on VONA 2026KRA12 over VAA Darwin 05/1030Z"
    )
    assert lines["plan"] == "CHANGE LEVEL FL280-FL300 after 2 tool calls: exposure, level_bands"
    assert lines["draft"] == (
        "Checked by code: action allowed · every number and place from the facts · no clock time"
        " · 7 numbers in the text, every one from the facts given · 1 repair"
    )
    feet = {
        s["data"]["step"]: [_text(f) for f in _find(s, "chain__foot")]
        for s in _find(view, "chain__step")
    }
    assert feet["plume"] == ["7 checks passed · 1 repair · 2.3 s"]
    assert feet["plan"] == ["reasoning checked for clock words only · rejected once, then accepted"]
    # the Desk names a source by its id's first parts when no situation is on hand
    desk_plume = _text(_find(rendered["model"]["desk"], "chain__line")[1])
    assert desk_plume == "Wider than official FL000-FL500 · leaned on vona krakatau 1"
    # the rejected body's note and the tool results sit one tap in
    more = _text(view)
    assert "rejected once: a number not in the facts" in more
    assert "inside in 12 min" in more


def test_chain_view_says_no_model_in_stub_and_not_on_hand_for_nulls(
    rendered: dict[str, Any],
) -> None:
    stub = rendered["stub"]["wall"]
    marks = _marks(stub)
    assert marks
    # the small "{ }" mark (owner, 17 Oct: "don't say no model everywhere"), its words for a
    # screen reader and the tooltip
    assert all(m == "Written by a code template" for m in marks)
    assert "NO MODEL:" not in _text(stub)  # the mark says it; the words are not repeated
    lines = [_text(n) for n in _find(stub, "chain__line")]
    assert lines[0] == "Planned 2 of 24 · urgency order"
    assert lines[2] == "CHANGE LEVEL FL280-FL300 after 0 tool calls"
    nulls = rendered["nulls"]["wall"]
    assert [_text(n) for n in _find(nulls, "chain__line")][:3] == ["not on hand"] * 3
    assert len(_marks(nulls)) == 1  # the draft's alone


def test_chain_view_uses_no_quota_words(rendered: dict[str, Any]) -> None:
    for name in ("model", "stub", "nulls"):
        for surface in ("wall", "desk"):
            text = _text(rendered[name][surface])
            assert not QUOTA_TEXT.search(text), (name, surface)
            for path in _walk(rendered[name][surface]):
                for v in path[-1]["attrs"].values():
                    assert not QUOTA_TEXT.search(v), (name, surface, v)
    for line in _read("wall/chain.js").splitlines():
        if COMMENT.match(line):
            continue
        for text in STRING.findall(line):
            assert not QUOTA_TEXT.search(text), line.strip()[:140]


def test_the_wall_section_fetches_once_and_says_not_on_hand(rendered: dict[str, Any]) -> None:
    first = _text(rendered["sectionFirst"])
    assert "RFA123 · CHANGE LEVEL FL280–FL300" in first  # noqa: RUF001  the UI's own dash
    assert "Fetching the chain…" in first
    missed = rendered["sectionMissed"]
    assert "The reasoning chain for this draft is not on hand." in _text(missed)
    assert "Nothing stands in for it." in _text(missed)
    assert any(n["data"].get("sec") == "decisions" for n in _find(missed, "link-btn"))


# ---------------------------------------------------------------- the map pill (A11)


def test_the_map_pill_quotes_no_model_prose() -> None:
    pills = "\n".join(
        line
        for line in _function(_read("wall/panels.js"), "mapPills").splitlines()
        if not COMMENT.match(line)
    )
    assert "text: `Widened · leans on ${cardName(D.sit, lean)}`" in pills
    assert 'actionText: "Why ›"' in pills  # noqa: RUF001  the UI's own chevron
    assert 'sec: "estimate"' in pills
    for field in ("reading", "rationale", "uncertainty_notes", ".why"):
        assert field not in pills
    assert ".map-pill--tephra {" in _read("wall.css")
