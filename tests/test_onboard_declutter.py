"""Onboarding and the workspace say less (owner, 17 Oct 2026: "nobody is going to read so much,
don't overwhelm with infomation"; on the sign-up form: "why so much text after warning sign, keep
it modular ... maybe you can put information in a popup in tick button"; on the setup kit: "drop
it").

- No setup kit: no kit or zip module, no kit page, no kit words, no self-hosting line; the uploader
  (kit/push.py) stays.
- The sign-up card's note is one line, "Private to your airline", with an (i) holding the full
  sentence and the Privacy link.
- The password's rule is in its label ("Password · 12+ characters") and its description; no hint
  line, no "You sign in with it."
- Errors are terse and wait: none while a field is untouched, one once it was typed in and left (or
  on submit), gone when it is right.
- The decision-support tick's (i) sits beside its label, outside it: a tap on it never ticks the
  box; the words still do.
- The Gemini card's (i) holds the unpaid tier's data use, and the radio is described by it, so it is
  heard before the choice.

Node runs the real modules against a small fake DOM. Skipped when Node is not installed.
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
NODE = shutil.which("node")
SOURCES = [
    WEB / "onboard.js",
    WEB / "workspace.js",
    WEB / "onboard.html",
    WEB / "workspace.html",
    *sorted((WEB / "onboard").glob("*.js")),
    *sorted((WEB / "workspace").glob("*.js")),
]

FAKE_DOM = r"""
class FakeNode {
  constructor(tag) {
    this.tag = tag; this.attrs = {}; this.kids = []; this.text = ""; this.parent = null;
    this.dataset = {}; this.listeners = {}; this.checked = false; this._value = null;
  }
  get hidden() { return "hidden" in this.attrs; }
  set hidden(v) { if (v) this.attrs.hidden = ""; else delete this.attrs.hidden; }
  get id() { return this.attrs.id || ""; }
  set id(v) { this.attrs.id = String(v); }
  get className() { return this.attrs.class || ""; }
  set className(v) { this.attrs.class = String(v); }
  get value() { return this._value ?? this.attrs.value ?? ""; }
  set value(v) { this._value = String(v); }
  get type() { return this.attrs.type || ""; }
  set type(v) { this.attrs.type = v; }
  get parentElement() { return this.parent; }
  get firstChild() { return this.kids[0] || null; }
  get lastChild() { return this.kids[this.kids.length - 1] || null; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  hasAttribute(k) { return k in this.attrs; }
  removeAttribute(k) { delete this.attrs[k]; }
  append(...kids) {
    for (const k of kids) {
      const n = typeof k === "string" ? new FakeText(k) : k;
      n.parent = this;
      this.kids.push(n);
    }
  }
  appendChild(k) { this.append(k); return k; }
  replaceChildren(...kids) { this.kids = []; this.append(...kids); }
  set textContent(v) { this.kids = []; this.text = String(v); }
  get textContent() { return this.text + this.kids.map((k) => k.textContent).join(""); }
  get classList() {
    const n = this;
    const set = () => new Set(n.className.split(" ").filter(Boolean));
    return {
      add: (c) => n.classList.toggle(c, true),
      remove: (c) => n.classList.toggle(c, false),
      toggle: (c, on) => {
        const s = set();
        if (on ?? !s.has(c)) s.add(c);
        else s.delete(c);
        n.className = [...s].join(" ");
      },
      contains: (c) => set().has(c),
    };
  }
  get style() { return { setProperty() {}, removeProperty() {} }; }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  fire(type) {
    const e = {
      type, target: this, defaultPrevented: false,
      preventDefault() { this.defaultPrevented = true; },
      stopPropagation() { this.stopped = true; },
    };
    for (let n = this; n && !e.stopped; n = n.parent) {
      for (const fn of n.listeners[type] || []) fn(e);
    }
    return e;
  }
  focus() {}
  matches(sel) { return sel.split(",").some((one) => match(this, one.trim())); }
  closest(sel) {
    for (let n = this; n; n = n.parent) if (n.matches && n.matches(sel)) return n;
    return null;
  }
  *all() {
    for (const k of this.kids) {
      if (k instanceof FakeText) continue;
      yield k;
      yield* k.all();
    }
  }
  querySelectorAll(sel) { return [...this.all()].filter((n) => n.matches(sel)); }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
}
class FakeText extends FakeNode { constructor(t) { super("#text"); this.text = t; } *all() {} }
// ".a", "tag", "#id", "[attr]", ".a.b" and "X > Y" (a direct child)
function one(n, s) {
  const id = s.match(/^#(.+)$/);
  if (id) return n.id === id[1];
  const attr = s.match(/^\[([^\]=]+)\]$/);
  if (attr) return attr[1] in n.attrs;
  const [tag, ...cls] = s.split(".");
  return (!tag || n.tag === tag) && cls.every((c) => n.classList.contains(c));
}
function match(n, sel) {
  const parts = sel.split(/\s*>\s*/);
  if (!one(n, parts.pop())) return false;
  let at = n.parent;
  while (parts.length) { if (!at || !one(at, parts.pop())) return false; at = at.parent; }
  return true;
}
globalThis.Node = FakeNode;
const body = new FakeNode("body");
globalThis.document = {
  body,
  createElement: (t) => new FakeNode(t),
  createElementNS: (_, t) => new FakeNode(t),
  createTextNode: (t) => new FakeText(t),
  getElementById: (id) => [...body.all()].find((n) => n.id === id) || null,
  querySelector: (sel) => body.querySelector(sel),
};
"""

RUNNER = (
    FAKE_DOM
    + r"""
const { accountFields } = await import("./onboard/review.js");
const { modelChoice } = await import("./workspace/assistant.js");
const out = {};
const f = accountFields();
body.append(f.node);
const email = document.getElementById("acct-email");
const pw = document.getElementById("acct-password");
const ack = document.getElementById("acct-ack");
const err = (id) => {
  const e = document.getElementById(`${id}-err`);
  return e.hidden ? null : e.textContent;
};
const shape = (id) => Boolean(document.getElementById(`${id}-err`).querySelector("svg"));
// untouched and left: nothing said
email.fire("blur"); pw.fire("blur");
out.untouched = [err("acct-email"), err("acct-password")];
// typed and left: the terse words, with the caution shape
email.value = "ops.rfa.example"; email.fire("input"); email.fire("blur");
pw.value = "short"; pw.fire("input"); pw.fire("blur");
out.left = [
  err("acct-email"), err("acct-password"), shape("acct-email"), email.getAttribute("aria-invalid"),
];
// once shown, the words follow the typing and go when it is right
email.value = "ops@rfa.example"; email.fire("input");
out.fixed = err("acct-email");
pw.value = "OPS@RFA.EXAMPLE"; pw.fire("input");
out.pwIsEmail = err("acct-password");
// a submit with the tick empty names each field still wrong, in page order
out.problems = f.problems();
// the password's rule: in the label and its description, no hint line
out.labels = f.node.querySelectorAll("label").map((l) => l.textContent);
const textOf = (id) => document.getElementById(id)?.textContent ?? null;
out.pwDescribed = pw.getAttribute("aria-describedby").split(" ").map(textOf);
out.hints = f.node.querySelectorAll(".hint").map((h) => h.textContent);
// the tick's (i): beside the label, never inside it
const info = f.node.querySelectorAll(".info__btn")
  .find((b) => b.dataset.info === "decision support");
out.tickInfo = {
  inLabel: Boolean(info.closest("label")),
  name: info.getAttribute("aria-label"),
  said: textOf(info.getAttribute("aria-describedby")),
};
const tickLabel = ack.closest("label");
out.tickLabel = {
  text: tickLabel.textContent,
  holdsInfo: Boolean(tickLabel.querySelector(".info")),
};
// the model cards: the Gemini card's (i) holds the data use and describes the radio
const a = { provider: null };
const choice = modelChoice(a, { onChange() {} });
body.append(choice);
const radios = choice.querySelectorAll("input").filter((i) => i.type === "radio");
out.cards = radios.map((r) => ({
  value: r.attrs.value,
  name: document.getElementById(r.getAttribute("aria-labelledby")).textContent,
  described: (r.getAttribute("aria-describedby") || "").split(" ").filter(Boolean).map(textOf),
  line: r.closest("label").querySelector(".choice__text")?.querySelector("span")?.textContent,
  privacy: r.closest("label").querySelectorAll("a").map((x) => x.attrs.href),
}));
process.stdout.write(JSON.stringify(out));
"""
)

pytestmark = pytest.mark.skipif(NODE is None, reason="Node is not installed")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def dom(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    # every module the sign-up fields and the model cards import, as the browser has them
    work = tmp_path_factory.mktemp("declutter") / "web"
    shutil.copytree(
        WEB,
        work,
        ignore=shutil.ignore_patterns(
            "*.html",
            "*.css",
            "*.png",
            "*.webp",
            "*.woff2",
            "*.svg",
            "*.py",
            "data",
            "fonts",
            "__pycache__",
        ),
    )
    (work / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    (work / "run.mjs").write_text(RUNNER, encoding="utf-8")
    result = subprocess.run(
        [str(NODE), "run.mjs"], cwd=work, capture_output=True, text=True, timeout=60, check=True
    )
    return json.loads(result.stdout)


def test_no_setup_kit_anywhere_in_the_airline_pages() -> None:
    """The owner (17 Oct 2026): "we still providing setup kit ??", then "drop it"."""
    assert not (WEB / "workspace" / "kit.js").exists()
    assert not (WEB / "workspace" / "zip.js").exists()
    assert (WEB / "kit" / "push.py").is_file()  # the uploader stays
    gone = re.compile(
        r"setup kit|kit\.js|zip\.js|/workspace/kit|run your own TEPHRA|your own TEPHRA|"
        r"made in your browser|(?-i:\bCHECKLIST\b)|airline\.env|Not built yet\.",
        re.I,
    )
    # the kit's CHECKLIST constant is matched by case: hosting's go-live checklist (workspace/
    # golive.js, "Finish the checklist") is not the kit
    for path in SOURCES:
        hit = gone.search(_text(path))
        assert not hit, (path.name, hit and hit.group(0))
    pages = _text(WEB / "onboard" / "pages.js")
    assert (
        'export const NOT_ON_YET = "Running your airline on this site is not switched on yet.";'
        in pages
    )
    assert "NOT_ON_YET" in _text(WEB / "onboard.js")
    assert "NOT_ON_YET" in _text(WEB / "workspace" / "overview.js")
    assert '"Verified."' in _text(WEB / "workspace" / "overview.js")


def test_the_sign_up_note_is_one_line_with_its_info() -> None:
    code = _text(WEB / "onboard.js")
    card = code.split("function signupCard()")[1].split("\nfunction ")[0]
    note = card.split('id: "su-private"')[1]
    assert (
        note.index('icon("i-lock")')
        < note.index('"Private to your airline"')
        < note.index("infoButton(")
    )
    assert 'href: "/privacy", text: "Privacy"' in note
    assert "text: WHO_READS" in note
    pages = _text(WEB / "onboard" / "pages.js")
    assert "Nothing you enter appears on the demo's map or the Desk's picture." in pages
    assert 'class: "hint", text: "Only you' not in card  # no longer a visible paragraph


def test_errors_wait_until_a_typed_field_is_left_and_are_terse(dom: dict[str, Any]) -> None:
    assert dom["untouched"] == [None, None]
    email_err, pw_err, has_shape, invalid = dom["left"]
    assert (email_err, pw_err) == ("Not an email", "12+ characters")
    assert has_shape is True
    assert invalid == "true"
    assert dom["fixed"] is None
    assert dom["pwIsEmail"] == "Not your email"
    assert dom["problems"] == [
        ["acct-password", "Not your email"],
        ["acct-ack", "Tick to continue"],
    ]


def test_the_password_rule_is_in_its_label_and_no_hint_line(dom: dict[str, Any]) -> None:
    assert "Password · 12+ characters" in dom["labels"]
    assert "Work email" in dom["labels"]
    assert "12 characters or more" in dom["pwDescribed"]
    assert dom["hints"] == []
    for path in SOURCES:
        assert "You sign in with it." not in _text(path), path.name


def test_the_ticks_info_never_ticks_the_box(dom: dict[str, Any]) -> None:
    tick = dom["tickInfo"]
    assert tick["inLabel"] is False
    assert tick["name"] == "About decision support"
    assert tick["said"] == "A person decides, and nothing is sent to an aircraft."
    assert dom["tickLabel"] == {
        "text": "I understand TEPHRA is decision support only",
        "holdsInfo": False,
    }


def test_the_gemini_data_use_is_heard_before_the_choice(dom: dict[str, Any]) -> None:
    cards = {c["value"]: c for c in dom["cards"]}
    gemini = cards["gemini"]
    assert gemini["name"] == "Gemini or Gemma (your own key)"
    assert gemini["line"] == "Your key · data use"
    said = " ".join(gemini["described"])
    assert "On Google's unpaid tier, what TEPHRA sends may be used to improve Google's" in said
    assert "this site never stores it" in said
    assert "/privacy" in gemini["privacy"]
    for c in dom["cards"]:
        assert len(c["line"].split()) <= 6, c  # each card: a title and one short line


def test_terse_rule_words(tmp_path: Path) -> None:
    (tmp_path / "onboard").mkdir()
    shutil.copy(WEB / "onboard" / "pages.js", tmp_path / "onboard" / "pages.js")
    (tmp_path / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    (tmp_path / "run.mjs").write_text(
        'import * as P from "./onboard/pages.js";\n'
        "process.stdout.write(JSON.stringify(["
        'P.ruleMessage("acct.email", ""), P.ruleMessage("acct.email", "x"),'
        'P.ruleMessage("acct.password", "short"), P.ruleMessage("airline.name", ""),'
        'P.problemText("fleet", { field: "fleet.aircraft.1.registration", message: "Required" }),'
        'P.problemText("airline", { field: "airline.ops_email", message: "Not an email" })'
        "]));\n",
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
        "Required",
        "Not an email",
        "12+ characters",
        "Required",
        "Fleet · Registration, row 2: Required",
        "Airline · Operations email: Not an email",
    ]


def test_the_explanations_sit_behind_info_buttons() -> None:
    """Every onboarding page says one line under its h1; the paragraphs that explained it are in
    the (i)s of the one info button (wall/info.js), not another component."""
    pages = _text(WEB / "onboard" / "pages.js")
    whys = re.findall(r'why: "([^"]+)"', pages)
    assert len(whys) == 9
    for why in whys:
        assert len(why.split()) <= 10, why
    for rel in ("onboard.js", "onboard/form.js", "onboard/review.js", "workspace/overview.js"):
        assert 'from "./wall/info.js"' in _text(WEB / rel) or 'from "../wall/info.js"' in _text(
            WEB / rel
        ), rel
    for rel in ("onboard.html", "workspace.html"):
        html = _text(WEB / rel)
        assert '<link rel="stylesheet" href="/static/info.css">' in html
    code = _text(WEB / "onboard.js")
    for gone in (
        "Back and Next save your answers to your account.",
        "Your setup kit so far",
        "How to onboard: what you provide",
        "A TEPHRA dispatcher verifies every airline. Until then nothing runs under your name.",
        "What your TEPHRA will check",
    ):
        assert gone not in code, gone
    assert '"What you will provide"' in code


def test_verify_findings_fixed() -> None:
    """The declutter2 verify pass (17 Oct 2026): the (i) stays open on its own words, nothing is
    left alone at a line's end, and each card says what it means."""
    info = _text(WEB / "wall" / "info.js")
    assert 'pop.addEventListener("mousedown"' in info
    assert '.closest?.("a, button")) e.preventDefault()' in info
    overview = _text(WEB / "workspace" / "overview.js")
    assert 'class: "pending__tail"' in overview
    assert "·\\u00a0" in overview
    assert ".pending__tail { white-space: nowrap; }" in _text(WEB / "product.css")
    assert ".checkline > .check { min-height: 0;" in _text(WEB / "product.css")
    assert ".tn-account__code:not([hidden]) + .tn-account__name" in _text(WEB / "topnav.css")
    pages = _text(WEB / "onboard" / "pages.js")
    assert '"Gemini, Ollama or none"' in pages
    assert "AI Studio key, Ollama" not in pages
    assistant = _text(WEB / "workspace" / "assistant.js")
    assert "public ash feeds and the facts code writes about your flights" in assistant
    assert "labelled NO MODEL" not in assistant
    panels = _text(WEB / "wall" / "panels.js")
    assert "nothing is sent anywhere" not in panels
    assert panels.count("never to an aircraft or any real system") == 1
