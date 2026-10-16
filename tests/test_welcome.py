"""The demo's welcome dialog (SPEC-v2 3.4, 5.2.1): ``tephra/web/wall/welcome.js`` run under Node.

Its words come from the state: what plays (a reconstructed, recorded or synthetic replay, or the
live feeds), the fictional airline and decision support only, each said exactly. The card shows
the steps by name only and one short honesty line; the full sentences are its screen-reader
description. A link that
skips it (``?intro=0``, a screenshot or recording run, a deep link into Details) and a reader's
"Don't show again" keep it closed; storage that throws never does. Skipped without Node.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "tephra" / "web"
FILES = (
    "five-steps.js",
    "replay-words.js",
    "wall/welcome.js",
    "wall/util.js",
    "wall/x-parts.js",
)
NODE = shutil.which("node")
SHIPPED = json.loads(
    (ROOT / "data/replay/anak-krakatau-20260905/manifest.json").read_text(encoding="utf-8")
)

RUNNER = """
import { readFileSync } from "node:fs";
const input = JSON.parse(readFileSync(process.argv[2], "utf8"));
const store = new Map(Object.entries(input.storage || {}));
globalThis.localStorage = input.storageThrows
  ? { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); } }
  : { getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, v) };
const welcome = await import("./wall/welcome.js");
const { welcomeWords, shouldOpenWelcome, welcomeSkipped, WELCOME_KEY } = welcome;
const out = {
  key: WELCOME_KEY,
  skipped: welcomeSkipped(),
  words: input.states.map((s) => welcomeWords(s)),
  opens: input.links.map(([query, hash]) => shouldOpenWelcome(new URLSearchParams(query), hash)),
};
process.stdout.write(JSON.stringify(out));
"""

# A DOM just big enough for el() and icon(): the dialog's built tree, read back as plain data.
FAKE_DOM = """
class FakeNode {
  constructor(tag) {
    this.tag = tag; this.kids = []; this.attrs = {}; this.className = ""; this.dataset = {};
    this.text = "";
  }
  setAttribute(k, v) { this.attrs[k] = String(v); if (k === "class") this.className = String(v); }
  append(...kids) { this.kids.push(...kids); }
  get children() { return this.kids.filter((k) => k instanceof FakeNode); }
  set textContent(v) { this.text = String(v); this.kids = []; }
  get textContent() { return this.text + this.kids.map((k) => k.textContent).join(""); }
  get classList() {
    const n = this;
    const toggle = (c, on) => {
      const s = new Set(n.className.split(" ").filter(Boolean));
      if (on) s.add(c);
      else s.delete(c);
      n.className = [...s].join(" ");
    };
    return { toggle };
  }
  removeAttribute(k) { delete this.attrs[k]; }
  get style() { return {}; }
}
class FakeText extends FakeNode { constructor(t) { super("#text"); this.text = t; } }
globalThis.Node = FakeNode;
globalThis.document = {
  createElement: (t) => new FakeNode(t),
  createElementNS: (_, t) => new FakeNode(t),
  createTextNode: (t) => new FakeText(t),
};
const walk = (n) => ({
  tag: n.tag, cls: n.className || n.attrs.class || "", id: n.attrs.id || null,
  hidden: n.attrs["aria-hidden"] || null, text: n.tag === "#text" || !n.kids.length ? n.text : "",
  kids: n.kids.map(walk),
});
"""

DOM_RUNNER = (
    FAKE_DOM
    + """
import { readFileSync } from "node:fs";
const input = JSON.parse(readFileSync(process.argv[2], "utf8"));
globalThis.localStorage = { getItem: () => null, setItem() {} };
const { welcomeContent } = await import("./wall/welcome.js");
const { stepsList } = await import("./five-steps.js");
process.stdout.write(JSON.stringify({
  dialog: input.states.map((s) => welcomeContent(s).map(walk)),
  guide: walk(stepsList()),
}));
"""
)

pytestmark = pytest.mark.skipif(NODE is None, reason="Node is not installed")

REGION = {"key": "java_bali", "name": "Java / Bali"}
RECONSTRUCTED = {
    "mode": "REPLAY",
    "region": REGION,
    "replay": {
        "case_id": SHIPPED["case_id"],
        "label": SHIPPED["label"],
        "recorded_from": SHIPPED["recorded_from"],
        "window_from": "2026-09-05T10:30:00.000Z",
        "synthetic": False,
    },
}
RECORDED = {
    "mode": "REPLAY",
    "region": REGION,
    "replay": {
        "label": "Merapi: dome collapse ash, 1-2 Oct 2026",
        "recorded_from": "2026-10-01T03:00:00.000Z",
        "window_from": None,
        "synthetic": False,
    },
}
RECORDED_NO_NAME = {
    "mode": "REPLAY",
    "region": REGION,
    "replay": {
        "label": "Java and Bali, live public feeds from 10 Oct 2026 06:00Z (13:00 WIB): traffic",
        "recorded_from": "2026-10-10T06:00:00.000Z",
        "synthetic": False,
    },
}
SYNTHETIC = {
    "mode": "REPLAY",
    "region": REGION,
    "replay": {
        "label": "SYNTHETIC DEMO: Agung ash closes Bali, 14 Oct 2026 (invented data)",
        "recorded_from": "2026-10-14T00:00:00.000Z",
        "synthetic": True,
    },
}
LIVE = {"mode": "LIVE", "region": REGION, "replay": None}
CLOCK = "The replay clock shows that day's time, not now."
AIRLINE = "Ring of Fire Air (RFA) is a fictional airline."
SUPPORT = {
    "lead": "Decision support only.",
    "text": "A person approves every advisory, and nothing is sent to an aircraft.",
}


def _run(tmp_path: Path, data: dict[str, Any], runner: str = RUNNER) -> dict[str, Any]:
    for rel in FILES:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(WEB / rel, tmp_path / rel)
    (tmp_path / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    (tmp_path / "run.mjs").write_text(runner, encoding="utf-8")
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


def _words(tmp_path: Path, state: dict[str, Any] | None) -> dict[str, Any]:
    return _run(tmp_path, {"states": [state], "links": []})["words"][0]


def test_the_shipped_case_is_labelled_reconstructed() -> None:
    # the welcome dialog words a case from its label; a relabelled case must not switch silently
    assert SHIPPED["label"].endswith("(reconstructed)")
    assert SHIPPED["label"].startswith("Anak Krakatau: ")


def test_a_reconstructed_replay_says_it_was_rebuilt_from_archives(tmp_path: Path) -> None:
    w = _words(tmp_path, RECONSTRUCTED)
    assert w["pill"] == "Replay"
    # the day is the window's start: the part that plays
    assert w["eyebrow"] == "Anak Krakatau · 5 Sep 2026"
    assert w["title"] == "Watch TEPHRA work a real eruption"
    assert [f["text"] for f in w["facts"]] == [
        "Rebuilt from archives",
        "RFA is a fictional airline",
        "A person approves every advisory",
    ]
    assert w["replay"] == {
        "lead": "Replay.",
        "text": "Public feeds from the Anak Krakatau eruption of 5 Sep 2026, rebuilt from "
        f"archives and played back. {CLOCK}",
    }
    assert w["airline"] == {
        "lead": AIRLINE,
        "text": "Its flight numbers stand in for real aircraft.",
    }
    assert w["support"] == SUPPORT


def test_a_recorded_replay_says_recorded_feeds_and_its_first_day(tmp_path: Path) -> None:
    w = _words(tmp_path, RECORDED)
    assert w["eyebrow"] == "Merapi · 1 Oct 2026"
    assert w["title"] == "Watch TEPHRA work a real eruption"
    assert w["facts"][0]["text"] == "Recorded feeds"
    assert w["replay"]["text"] == f"Recorded feeds from the Merapi eruption of 1 Oct 2026. {CLOCK}"
    # a label that does not start with a volcano's name leaves the name out
    w = _words(tmp_path, RECORDED_NO_NAME)
    assert w["eyebrow"] == "10 Oct 2026"
    assert w["title"] == "Watch TEPHRA work a recorded day"
    assert w["replay"]["text"] == f"Recorded feeds from 10 Oct 2026. {CLOCK}"


def test_a_synthetic_replay_says_invented_demo_data(tmp_path: Path) -> None:
    w = _words(tmp_path, SYNTHETIC)
    assert w["pill"] == "Replay"
    # "invented demo data" is said once, on the honesty line; the chip row keeps the day
    assert w["eyebrow"] == "14 Oct 2026"
    assert w["title"] == "Watch TEPHRA work a demo eruption"
    assert w["facts"][0]["text"] == "Invented demo data"
    assert w["replay"] == {
        "lead": "Replay.",
        "text": "Invented demo data, played back. The replay clock shows the demo's time, not now.",
    }
    assert w["airline"]["text"] == "Its flight numbers stand in for demo aircraft."
    assert "real eruption" not in json.dumps(w)


def test_live_says_live_and_the_time_now(tmp_path: Path) -> None:
    w = _words(tmp_path, LIVE)
    assert w["pill"] == "Live"
    assert w["eyebrow"] == "Java / Bali"
    assert w["title"] == "Watch TEPHRA work today's feeds"
    assert w["facts"][0] == {"icon": "i-live", "text": "Feeds as they arrive", "replay": True}
    assert w["replay"] == {
        "lead": "Live.",
        "text": "Public feeds as they arrive. The clock shows the time now (UTC).",
    }
    assert w["support"] == SUPPORT


def test_an_airlines_own_tephra_names_its_airline_and_never_calls_it_fictional(
    tmp_path: Path,
) -> None:
    # /api/state's airline (OWNFLIGHTS, 16 Oct 2026): fictional only for the demo's RFA
    own = {**LIVE, "airline": {"code": "RFB", "name": "Ring of Fire Air", "fictional": False}}
    w = _words(tmp_path, own)
    assert [f["text"] for f in w["facts"]][1] == "Only RFB flights are checked"
    assert w["airline"] == {
        "lead": "This TEPHRA checks only Ring of Fire Air's own flights (RFB).",
        "text": "Each is named by its callsign, schedule or registration.",
    }
    assert "fictional" not in json.dumps(w)
    demo = {**LIVE, "airline": {"code": "RFA", "name": "Ring of Fire Air", "fictional": True}}
    assert _words(tmp_path, demo)["airline"]["lead"] == AIRLINE


def test_without_a_state_nothing_is_said_about_what_plays(tmp_path: Path) -> None:
    w = _words(tmp_path, None)
    assert w["pill"] is None
    assert w["replay"] is None
    assert w["title"] == "Watch TEPHRA work"
    assert [f["icon"] for f in w["facts"]] == ["i-aircraft", "i-hand"]
    assert w["airline"]["lead"] == AIRLINE
    assert w["support"] == SUPPORT


LINKS = [
    ("", ""),
    ("intro=0", ""),
    ("shots=1", ""),
    ("present=1", ""),
    ("", "#details-sources"),
    ("", "#track-record"),
    ("", "#ai-at-work"),
    ("", "#foo"),
    ("intro=1", "#details"),
]


def test_links_that_skip_the_dialog(tmp_path: Path) -> None:
    out = _run(tmp_path, {"states": [], "links": LINKS})
    assert out["key"] == "tephra.demo.welcome"
    assert out["skipped"] is False
    assert out["opens"] == [True, False, False, False, False, False, False, True, True]


def test_dont_show_again_keeps_it_closed(tmp_path: Path) -> None:
    skip = {"tephra.demo.welcome": "skip"}
    out = _run(tmp_path, {"states": [], "links": LINKS[:1], "storage": skip})
    assert out["skipped"] is True
    assert out["opens"] == [False]


def test_storage_that_throws_opens_the_dialog(tmp_path: Path) -> None:
    out = _run(tmp_path, {"states": [], "links": LINKS[:1], "storageThrows": True})
    assert out["skipped"] is False
    assert out["opens"] == [True]


def test_the_dialog_s_parts_and_keys() -> None:
    source = (WEB / "wall/welcome.js").read_text(encoding="utf-8")
    for needle in (
        'id: "welcome-title", text: w.title',
        'id: "welcome-more", class: "sr-only"',
        'id: "welcome-skip"',
        '"Don\'t show again"',
        'id: "welcome-start", class: "btn btn--primary", autofocus: true',
        '"Start the demo"',
        'stepsList({ size: "lg", lines: false })',
        # the REPLAY words reach a screen reader through the modal's description
        'describeReplay(dialog, state?.mode === "REPLAY" ? replayWords(state.replay).text : "")',
        'dialog.addEventListener("cancel", (e) => { e.preventDefault(); start(dialog); });',
        'document.getElementById("map-pane")',
    ):
        assert needle in source, needle
    assert "innerHTML" not in source
    keys = source.split('dialog.addEventListener("keydown"')[1].split("});")[0]
    assert "checkbox" not in keys  # Enter on "Don't show again" starts too
    # the card shows no keyboard hint: Enter and Esc still start, How it works reopens it
    assert "<kbd" not in source
    assert '"kbd"' not in source
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert (
        '<dialog id="welcome" class="welcome" aria-labelledby="welcome-title" '
        'aria-describedby="welcome-more"></dialog>'
    ) in html
    css = (WEB / "welcome.css").read_text(encoding="utf-8")
    assert "@media (max-width: 900px)" in css
    assert "@media (prefers-reduced-motion: reduce) { .welcome[open] { animation: none; } }" in css
    # the phone sheet keeps source order, so Tab and a screen reader meet the parts as they are seen
    assert not re.search(r"(?<![-\w])order\s*:", css)


def _find(node: dict[str, Any], test: Any) -> list[dict[str, Any]]:
    hits = [node] if test(node) else []
    for kid in node["kids"]:
        hits += _find(kid, test)
    return hits


def _has(cls: str) -> Any:
    return lambda n: cls in n["cls"].split()


def _text(node: dict[str, Any]) -> str:
    return node["text"] + "".join(_text(k) for k in node["kids"])


def test_the_card_shows_step_names_only_and_one_honesty_line(tmp_path: Path) -> None:
    states = [RECONSTRUCTED, SYNTHETIC, LIVE, None]
    out = _run(tmp_path, {"states": states}, DOM_RUNNER)
    for state, (body, foot) in zip(states, out["dialog"], strict=True):
        steps = _find(body, _has("steps5"))
        assert len(steps) == 1
        assert "steps5--names" in steps[0]["cls"].split()
        assert len(_find(steps[0], _has("steps5__n"))) == 5
        assert _find(body, _has("steps5__line")) == []  # no per-step description in the dialog
        lines = _find(body, _has("welcome__facts"))
        assert len(lines) == 1  # the three facts on one quiet line
        assert len(_find(lines[0], _has("welcome__fact"))) == (3 if state else 2)
        assert lines[0]["hidden"] == "true"  # a screen reader hears the full sentences instead
        more = _find(body, lambda n: n["id"] == "welcome-more")
        assert len(more) == 1
        assert "sr-only" in more[0]["cls"]
        assert AIRLINE in more[0]["text"]
        assert f"{SUPPORT['lead']} {SUPPORT['text']}" in more[0]["text"]
        assert "Don't show again" in _text(foot)
        assert "Start the demo" in _text(foot)
        assert "Enter" not in _text(foot)
    sr = _find(out["dialog"][0][0], lambda n: n["id"] == "welcome-more")[0]["text"]
    assert sr.startswith("Replay. Public feeds from the Anak Krakatau eruption of 5 Sep 2026")
    assert CLOCK in sr
    assert "Its flight numbers stand in for real aircraft." in sr


def test_the_guide_keeps_each_step_s_line(tmp_path: Path) -> None:
    guide = _run(tmp_path, {"states": []}, DOM_RUNNER)["guide"]
    assert "steps5--names" not in guide["cls"]
    assert len(_find(guide, _has("steps5__line"))) == 5
