"""The demo's welcome dialog (SPEC-v2 3.4, 5.2.1): ``tephra/web/wall/welcome.js`` run under Node.

Its words come from the state: what plays (a reconstructed, recorded or synthetic replay, or the
live feeds), the fictional airline and decision support only, each said exactly. A link that
skips it (``?intro=0``, a screenshot or recording run, a deep link into Details) and a reader's
"Don't show this again" keep it closed; storage that throws never does. Skipped without Node.
"""

import json
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


def _run(tmp_path: Path, data: dict[str, Any]) -> dict[str, Any]:
    for rel in FILES:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(WEB / rel, tmp_path / rel)
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
    assert w["lede"] == (
        "You will watch these five steps run on a real eruption, step by step, "
        "in the panel on the right."
    )
    assert w["lede_phone"] == (
        "You will watch these five steps run on a real eruption, step by step, in the panel below."
    )
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
    assert w["replay"]["text"] == f"Recorded feeds from the Merapi eruption of 1 Oct 2026. {CLOCK}"
    # a label that does not start with a volcano's name leaves the name out
    w = _words(tmp_path, RECORDED_NO_NAME)
    assert w["eyebrow"] == "10 Oct 2026"
    assert w["replay"]["text"] == f"Recorded feeds from 10 Oct 2026. {CLOCK}"


def test_a_synthetic_replay_says_invented_demo_data(tmp_path: Path) -> None:
    w = _words(tmp_path, SYNTHETIC)
    assert w["pill"] == "Replay"
    assert w["eyebrow"] == "Invented demo data · 14 Oct 2026"
    assert w["lede"] == (
        "You will watch these five steps run on invented demo data, step by step, "
        "in the panel on the right."
    )
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
    assert w["lede"] == (
        "You will watch these five steps run on today's public feeds, in the panel on the right."
    )
    assert w["replay"] == {
        "lead": "Live.",
        "text": "Public feeds as they arrive. The clock shows the time now (UTC).",
    }
    assert w["support"] == SUPPORT


def test_without_a_state_nothing_is_said_about_what_plays(tmp_path: Path) -> None:
    w = _words(tmp_path, None)
    assert w["pill"] is None
    assert w["replay"] is None
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
        'id: "welcome-title", text: "How TEPHRA works, in five steps"',
        'id: "welcome-lede"',
        'id: "welcome-honest", class: "honest-list"',
        'id: "welcome-skip"',
        '"Don\'t show this again"',
        'id: "welcome-start", class: "btn btn--primary", autofocus: true',
        '"Start the demo"',
        'stepsList({ size: "lg" })',
        # the REPLAY words reach a screen reader through the modal's description
        'describeReplay(dialog, state?.mode === "REPLAY" ? replayWords(state.replay).text : "")',
        'dialog.addEventListener("cancel", (e) => { e.preventDefault(); start(dialog); });',
        'document.getElementById("map-pane")',
    ):
        assert needle in source, needle
    assert "innerHTML" not in source
    keys = source.split('dialog.addEventListener("keydown"')[1].split("});")[0]
    assert "checkbox" not in keys  # Enter on "Don't show this again" starts too, as the footer says
    assert '" starts · reopen from How it works"' in source
    css = (WEB / "welcome.css").read_text(encoding="utf-8")
    assert "@media (max-width: 900px)" in css
    assert "@media (prefers-reduced-motion: reduce) { .welcome[open] { animation: none; } }" in css
