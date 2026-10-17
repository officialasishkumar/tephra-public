"""The demo and /assistant, decluttered (owner, 17 Oct 2026: "don't say no model everywhere",
"why are you putting tephra assistant again after assistant tab", "you can hide this in a info
icon", "why you are saying never smaller than official, binding, move it to info").

One short line per item; the explanation one tap away behind the info button (wall/info.js),
never removed: each moved sentence is still in the popover, the screen-reader description, a
tooltip or the full map key. Source checks, plus the code-template text helper under Node.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1] / "tephra" / "web"
WALL = WEB / "wall"
NODE = shutil.which("node")


def _src(rel: str) -> str:
    return (WEB / rel).read_text(encoding="utf-8")


def _function(source: str, name: str) -> str:
    start = source.index(f"function {name}(")
    end = source.find("\n}\n", start)
    return source[start : end + 3]


INDEX = _src("index.html")
CSS = _src("wall.css")
# the info button's look, one stylesheet for the demo, /assistant and the Desk
INFO_CSS = _src("info.css")


# ------------------------------------------------------------------ the info button


def test_the_info_button_is_a_real_button_that_opens_one_popover() -> None:
    """A <button> with aria-expanded and aria-controls, named for its topic, described by the
    same words in sr-only text; a popover in the top layer (never clipped by the map key or the
    side panel); one open at a time; Esc closes it and puts focus back on the button."""
    info = _src("wall/info.js")
    make = _function(info, "infoButton")
    assert (
        'el("button", { type: "button", class: "info__btn", "aria-expanded": "false", '
        '"aria-controls": id,' in make
    )
    assert '"aria-label": label, "aria-describedby": sr.id' in make
    assert 'el("span", { id: `${id}-sr`, class: "sr-only", text: said })' in make
    assert "label = `About ${topic}`" in make
    # the behaviour, shared with an (i) written in a page's HTML (the Desk's sign-in card)
    assert "return wireInfo(" in make
    wire = _function(info, "wireInfo")
    assert 'pop.setAttribute("popover", "auto");' in wire
    assert 'btn.setAttribute("popovertarget", pop.id);' in wire
    # opening one closes any other
    state = _function(info, "setState")
    assert 'btn.setAttribute("aria-expanded", String(open));' in state
    assert "for (const p of [...OPEN]) if (p !== pop) hide(p);" in state
    # Esc: closes, returns focus, and stops the page's own Esc step (a Details section, 3D...)
    assert 'if (e.key === "Escape" && pops.length) {' in info
    assert "e.stopPropagation();" in info
    assert "btn?.focus({ preventScroll: true });" in info
    # keys typed inside a popover never reach the Wall's single-key shortcuts
    assert (
        'if (e.target?.closest?.(".info__pop") && !["Tab", "Enter", " "].includes(e.key)) '
        "e.stopPropagation();" in info
    )
    # never on hover alone
    assert "mouseenter" not in info
    assert "pointerenter" not in info
    # a 44 px hit area around the glyph, theme tokens, no animation under reduced motion
    btn = INFO_CSS[INFO_CSS.index(".info__btn::after") :].split("\n", 1)[0]
    assert "inset: -10px" in btn
    pop = INFO_CSS[
        INFO_CSS.index(".info__pop {") : INFO_CSS.index("}", INFO_CSS.index(".info__pop {"))
    ]
    assert "var(--c-surface-2)" in pop
    assert "max-width: min(320px, calc(100vw - 32px))" in pop
    assert "@media (prefers-reduced-motion: no-preference) {\n  .info__pop:popover-open" in INFO_CSS


def test_the_info_module_is_preloaded() -> None:
    assert '<link rel="modulepreload" href="/static/wall/info.js">' in INDEX
    assert '<link rel="stylesheet" href="/static/info.css">' in INDEX


# ------------------------------------------------------------------ A, C, D: the AI state once


def test_no_tephra_assistant_heading_under_the_assistant_tab() -> None:
    start = INDEX.index('<section id="assist" ')
    tab = INDEX[start : INDEX.index("</section>\n\n", start)]
    assert "TEPHRA Assistant</p>" not in tab
    assert "as-state" not in tab
    assert "NO MODEL" not in INDEX


def test_the_ai_state_is_said_once_on_the_demo() -> None:
    """One status in the tab bar (only when not normal) with its (i); the diagram's gate, the
    Coordinator's row, the map's estimate label and the Details row add no AI-off words; a
    code template's line carries the small "{ }" mark, not "(code only)" words."""
    panels = _src("wall/panels.js")
    chrome = panels[
        panels.index("// TEPHRA Assistant's one status") : panels.index("// Data chip:")
    ]
    assert "stateLine(w, {" in chrome
    assert "chip.hidden = !line.word;" in chrome
    assert 'setText($("ai-state-said"), line.said);' in chrome
    assert (
        'infoButton({ topic: "assistant", label: "About the AI state", text: line.info, '
        "actions: [why] })" in chrome
    )
    # the status words live in one function, for the demo's tab bar and the /assistant board
    assist = _src("wall/assist.js")
    xparts = _src("wall/x-parts.js")
    for word in ("AI off", "AI paused", "AI unavailable"):
        assert xparts.count(f'word: "{word}"') == 1, word
        assert word not in assist, word
    assert (
        "stateLine({ suffix: M.ai.suffix }, { stub: M.stub, kind: M.ai.kind, reason: M.ai.reason })"
        in _src("wall/board-view.js")
    )
    board = _src("wall/board.js")
    assert 'gate = { open: true, kind: "nomodel", name: "", meta: "", title: "" };' in board
    assert '"Code orders the jobs (no model)"' not in board
    assert '"Skills run as code, no model is called"' not in board
    # the map's estimate label and the Details row
    assert 'STUB: "" };' in _src("wall/derive.js")
    assert 'if (ai.kind === "off") return { text: "" };' in _src("wall/details.js")
    # per-item: the "{ }" mark, never "Code only (NO MODEL)" words
    xparts = _src("wall/x-parts.js")
    assert 'export const TEMPLATE = "Written by a code template";' in xparts
    assert "if (no) return codeMark();" in _function(xparts, "aiMark")
    assert "Code only (NO MODEL)" not in panels
    assert "r.code ? codeMark() : null" in _src("wall/assist-panel.js")
    assert "t.code ? codeMark() : null" in _src("wall/board-view.js")


def test_the_status_reads_dashed_when_off_and_never_red() -> None:
    rule = CSS[CSS.index('.side__ai[data-tone="off"] .side__ai-word') :].split("\n", 1)[0]
    assert "dashed" in rule
    side = [line for line in CSS.splitlines() if line.startswith(".side__ai")]
    assert len(side) >= 4
    assert not any("--c-serious" in line for line in side)


# ------------------------------------------------------------------ B: You decide


def test_you_decide_is_one_line_with_its_rule_behind_an_info_button() -> None:
    view = _src("wall/board-view.js")
    inside = _function(view, "mountInside")
    assert (
        'infoButton({ topic: "you-decide", label: "About You decide", text: YOU_DECIDE, '
        "above: true })" in inside
    )
    assert "Nothing leaves TEPHRA until a dispatcher approves." not in inside
    decide = _function(view, "renderDecide")
    # the normal state says the count and "advisories wait for you" only
    assert ': "");' in decide
    assert "Drafts wait at the Desk for a dispatcher." not in decide
    assert "if (who.hidden !== !whoText) who.hidden = !whoText;" in decide
    # the Details foot: "You decide" with the same (i), no second line
    foot = INDEX[
        INDEX.index('id="side-foot"') : INDEX.index("</div>", INDEX.index('id="side-foot"'))
    ]
    assert "side__line" not in foot
    assert "Nothing leaves TEPHRA" not in foot


# ------------------------------------------------------------------ E: the map key


def test_map_key_items_have_one_line_and_the_moved_words_stay_reachable() -> None:
    story = _src("wall/story.js")
    rows = _function(story, "keyRows")
    for label in (
        '"Official ash area"',
        '"TEPHRA\'s estimate"',
        "`${code} flight in or heading in`",
        "`${code} flights close together`",
        "`Forecast area (",
        '"Other aircraft"',
        '"Route"',
    ):
        assert label in rows, label
    # the second words are data for the (i), the tooltip and the full key, never a second line
    for sub in (
        '"binding"',
        '"never smaller than official"',
        '"click to zoom in"',
        '"origin to destination, airport codes at the ends"',
    ):
        assert sub in rows, sub
    key = _function(story, "renderKey")
    assert "key__sub" not in key
    assert (
        'infoButton({ topic: "map-key", label: "About the map key", text: lines, '
        'actions: ui.keyOpen ? [] : [full], cls: "key__info" })' in key
    )
    assert "title: sub ? `${label}: ${sub}` : null" in key
    assert (
        "export const keyInfoLines = (rows) => rows.filter((r) => r[2])"
        '.map(([, label, sub]) => [el("b", { text: label }), `: ${sub}.`]);' in story
    )
    # the full map key (Help, the Guide) keeps every second word
    help_ = _function(_src("wall/controls.js"), "helpContent")
    assert '"Official ash area", "binding"' in help_
    assert "TEPHRA's estimate, never smaller than the official area." in help_
    assert "click to zoom in" in help_
    assert "airport codes" in help_


# ------------------------------------------------------------------ F: the frame


def test_the_status_line_markers_are_words_with_an_info_button() -> None:
    footer = INDEX[INDEX.index("<footer") : INDEX.index("</footer>")]
    assert "title=" not in footer.split('class="stl__keys"')[0]
    status = _function(_src("wall/panels.js"), "renderStatusLine")
    assert 'label: "About the illustrative policy"' in status
    assert (
        '"Illustrative values, not an airline SRA, and not reviewed by an airline dispatcher."'
        in status
    )
    assert "policyBtn.title" not in status


def test_the_replay_clock_says_replay_with_its_explanation_one_tap_away() -> None:
    clock = _function(_src("wall/panels.js"), "renderClock")
    assert "`Replay clock · ${dayMonth(D.now)}`" in clock
    assert '"The clock shows that day\'s time (UTC), not now."' in clock
    assert 'infoButton({ topic: "replay", label: "About replay", text: words })' in clock


@pytest.mark.skipif(NODE is None, reason="Node is not installed")
def test_template_text_drops_the_code_only_words_and_flags_the_line(tmp_path: Path) -> None:
    (tmp_path / "wall").mkdir()
    for name in ("x-parts.js", "util.js"):
        shutil.copy(WALL / name, tmp_path / "wall" / name)
    (tmp_path / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    lines = [
        "Advisory text written by a code template (code only): keep watching",
        "Flight planner (code only) chose: hold at FL176",
        "Coordinator (code only): handed out 2 jobs in urgency order",
        "Code only: built from the official reports only",
        "Safety risk assessment draft for Java / Bali: evidence by code, 4 narrative boxes by a"
        " code template (code only). Not an approved SRA.",
        "Advisory draft for RFA9715 reached the Desk",
    ]
    (tmp_path / "run.mjs").write_text(
        'import { templateText } from "./wall/x-parts.js";\n'
        f"console.log(JSON.stringify({json.dumps(lines)}.map(templateText)));\n",
        encoding="utf-8",
    )
    out = json.loads(
        subprocess.run(
            [str(NODE), "run.mjs"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        ).stdout
    )
    assert out == [
        {"text": "Advisory text: keep watching", "code": True},
        {"text": "Flight planner chose: hold at FL176", "code": True},
        {"text": "Coordinator: handed out 2 jobs in urgency order", "code": True},
        {"text": "Built from the official reports only", "code": True},
        {
            "text": "Safety risk assessment draft for Java / Bali: evidence by code, 4 narrative"
            " boxes. Not an approved SRA.",
            "code": True,
        },
        {"text": "Advisory draft for RFA9715 reached the Desk", "code": False},
    ]
    assert not any(re.search(r"code only|NO MODEL", o["text"]) for o in out)


# ------------------------------------------------------------------ fix pass (verify findings)


def test_inside_the_sections_the_off_state_is_said_once() -> None:
    """Honesty and UX verify, 17 Oct: Details > TEPHRA Assistant said the off state six times
    (pill, title, chip, lead, quota tile, quota note, per-skill "Model" line); the lead says it once
    now, with the tab bar's status. Other Details sections and the /assistant sheets turn their
    "(code only)" lines into the "{ }" mark instead of saying the state again."""
    ext = _src("wall/ext.js")
    for gone in (
        '"Off · code only"',
        "No model (offline stub)",
        "Code does every step, and code templates write the text a model would.",
        "no quota is spent",
        "Code only (assistant off): code follows",
        "Planned by code (code only)",
        "read by a code stub while TEPHRA Assistant is off",
    ):
        assert gone not in ext, gone
    assert 'if (ai.kind === "off") return null;' in _function(ext, "aiPill")
    assert "srTitle: stub" in ext
    assert "stub ? null : budgetTile(stub, ai)" in ext
    panels, story = _src("wall/panels.js"), _src("wall/story.js")
    for gone in (
        "code only, nothing added",
        "Code only (assistant off): official",
        '(code only)."',
    ):
        assert gone not in panels, gone
        assert gone not in story, gone
    duty = _src("wall/duty.js")
    assert '"Code only (assistant off)"' not in duty
    assert 'STUB: ["ok", "Done",' in duty
    # the /assistant sheets: the code mark in place of "(code only)", no footer words with no model,
    # no quote of a code brief that only repeats its line
    view = _src("wall/board-view.js")
    assert "function markedText(text)" in view
    assert 'stepText("ss-result__text", plainCase(x.text))' in view
    assert "...markedText(r.text)" in view
    assert "card?.model?.text ?" in view
    board = _src("wall/board.js")
    assert "No model (offline stub): no calls" not in board
    assert 'run.outcome !== "STUB" && run.llm_backend !== "stub"' in board
    # paused or in trouble, the gate says what waits, never the state again
    assert 'name: "Paused"' not in board
    assert 'name: "AI model · gave no result"' not in board
    # the Guide and the glossary explain the mark the UI shows
    assert "Code only (NO MODEL)" not in _src("wall/glossary.js")
    assert "{ } when a code template wrote it" in _src("guide.html")


def test_the_bare_gate_band_closes_and_targets_are_24_px() -> None:
    """UX verify, 17 Oct: with no model the band between Coordinator and the skills held only a
    lone dash; the replay clock and status-line (i)s were 18 and 22 px."""
    assert 'panel.classList.toggle("is-gate-bare"' in _src("wall/board-view.js")
    assert ".flow-panel.is-gate-bare .flow-gatebar { visibility: hidden; }" in CSS
    assert ".clock__info .info__btn { width: 24px; height: 24px;" in CSS
    assert ".stl .info__btn { width: 24px; height: 24px;" in CSS
    info = _src("wall/info.js")
    assert 'pop.dataset.place === "above"' in info
