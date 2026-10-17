"""Workspace, Go live on TEPHRA (SPEC hosted §5.1), ``tephra/web/workspace/golive.js`` and the
Overview that carries it, drawn under Node on a small DOM with the §4.3 fixtures of
``tests/fixtures/hosted/workspace``: every state (hosting off, Desk-verified and waiting, can set
up, setup with its checklist, region and places, shadow, live, suspended, the limit reached),
buttons only for ops managers, the reason in words when Start cannot run, the Switch to LIVE
dialog's honesty lines, and the Not built line's hosted variant. Skipped without Node.

``run_node`` and ``DOM`` are shared by ``test_join_web.py`` and ``test_admin_web.py``.
"""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "tephra" / "web"
FIX = ROOT / "tests" / "fixtures" / "hosted"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="Node is not installed")

# A DOM just large enough for el(), the forms and the dialogs: elements with attributes, classes,
# dataset, text, events and simple selectors (tag, #id, .class, [attr], [attr="v"], [attr^="v"],
# :not([attr]), descendant and comma lists). fetch answers from ROUTES ("METHOD path" -> {status,
# body, headers}) and records every call in CALLS.
DOM = r"""
const CALLS = [];
let ROUTES = {};
const dataName = (k) => "data-" + String(k).replace(/[A-Z]/g, (c) => "-" + c.toLowerCase());
class Node {
  constructor() {
    this.parentNode = null;
    this.childNodes = [];
  }
  get children() { return this.childNodes.filter((n) => n instanceof Element); }
  get firstChild() { return this.childNodes[0] || null; }
  get lastChild() { return this.childNodes[this.childNodes.length - 1] || null; }
  get textContent() { return this.childNodes.map((n) => n.textContent).join(""); }
  set textContent(v) { this.replaceChildren(new Text(String(v))); }
  _adopt(n) {
    if (n.parentNode) n.parentNode._drop(n);
    n.parentNode = this;
    return n;
  }
  _drop(n) {
    const i = this.childNodes.indexOf(n);
    if (i >= 0) this.childNodes.splice(i, 1);
    n.parentNode = null;
  }
  _wrap(k) { return k instanceof Node ? k : new Text(String(k)); }
  append(...kids) { for (const k of kids) this.childNodes.push(this._adopt(this._wrap(k))); }
  appendChild(k) {
    this.append(k);
    return k;
  }
  prepend(...kids) { this.childNodes.unshift(...kids.map((k) => this._adopt(this._wrap(k)))); }
  replaceChildren(...kids) {
    for (const c of [...this.childNodes]) this._drop(c);
    this.append(...kids);
  }
  remove() { if (this.parentNode) this.parentNode._drop(this); }
  before(...kids) {
    const p = this.parentNode;
    const nodes = kids.map((k) => p._adopt(p._wrap(k)));
    p.childNodes.splice(p.childNodes.indexOf(this), 0, ...nodes);
  }
  contains(n) {
    for (let x = n; x; x = x.parentNode) if (x === this) return true;
    return false;
  }
}
class Text extends Node {
  constructor(t) {
    super();
    this.data = t;
  }
  get textContent() { return this.data; }
  set textContent(v) { this.data = String(v); }
}
const BOOL = ["hidden", "disabled", "checked", "selected", "open"];
class Element extends Node {
  constructor(tag) {
    super();
    this.tagName = tag.toUpperCase();
    this.attributes = new Map();
    this.listeners = {};
    this.value = "";
    const self = this;
    this.dataset = new Proxy({}, {
      get: (_, k) => self.getAttribute(dataName(k)) ?? undefined,
      set: (_, k, v) => {
        self.setAttribute(dataName(k), v);
        return true;
      },
    });
    this.style = { props: {}, setProperty(k, v) { this.props[k] = v; } };
    const names = () => this.className.split(/\s+/).filter(Boolean);
    this.classList = {
      add: (...c) => { this.className = [...new Set([...names(), ...c])].join(" "); },
      remove: (...c) => { this.className = names().filter((x) => !c.includes(x)).join(" "); },
      contains: (c) => names().includes(c),
    };
  }
  setAttribute(k, v) {
    if (k === "value") this.value = String(v);
    this.attributes.set(k, String(v));
  }
  getAttribute(k) { return this.attributes.has(k) ? this.attributes.get(k) : null; }
  hasAttribute(k) { return this.attributes.has(k); }
  removeAttribute(k) { this.attributes.delete(k); }
  get id() { return this.getAttribute("id") || ""; }
  set id(v) { this.setAttribute("id", v); }
  get className() { return this.getAttribute("class") || ""; }
  set className(v) { this.setAttribute("class", v); }
  get tabIndex() { return Number(this.getAttribute("tabindex") ?? -1); }
  set tabIndex(v) { this.setAttribute("tabindex", v); }
  get type() { return this.getAttribute("type") || ""; }
  set type(v) { this.setAttribute("type", v); }
  addEventListener(t, f) { (this.listeners[t] ||= []).push(f); }
  dispatchEvent(e) {
    e.target ||= this;
    for (let n = this; n; n = n.parentNode) {
      e.currentTarget = n;
      for (const f of n.listeners?.[e.type] || []) f(e);
      if (!e.bubbles) break;
    }
    return true;
  }
  click() {
    if (this.disabled) return;
    this.dispatchEvent(new Event("click", { bubbles: true }));
    const form = this.type === "submit" ? this.closest("form") : null;
    if (form) form.dispatchEvent(new Event("submit", { bubbles: true }));
  }
  focus() { document.activeElement = this; }
  select() {}
  showModal() { this.open = true; }
  close() {
    this.open = false;
    this.dispatchEvent(new Event("close"));
  }
  closest(sel) {
    for (let n = this; n instanceof Element; n = n.parentNode) if (matches(n, sel)) return n;
    return null;
  }
  querySelectorAll(sel) {
    const out = [];
    const walk = (n) => {
      for (const c of n.children) {
        if (matches(c, sel)) out.push(c);
        walk(c);
      }
    };
    walk(this);
    return out;
  }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
}
for (const b of BOOL) {
  Object.defineProperty(Element.prototype, b, {
    get() { return this.hasAttribute(b); },
    set(v) { if (v) this.setAttribute(b, ""); else this.removeAttribute(b); },
  });
}
const TOKEN = /[#.][\w-]+|\[[^\]]+\]|:not\(\[[^\]]+\]\)/g;
function one(n, part) {
  const m = part.match(/^([a-zA-Z0-9]*)(.*)$/);
  if (m[2].replace(TOKEN, "")) throw new Error("selector " + part);
  if (m[1] && n.tagName !== m[1].toUpperCase()) return false;
  for (const t of m[2].match(TOKEN) || []) {
    if (t[0] === "#" && n.id !== t.slice(1)) return false;
    if (t[0] === "." && !n.classList.contains(t.slice(1))) return false;
    const neg = t.startsWith(":not(");
    const a = (neg ? t.slice(5, -1) : t).match(/^\[([\w-]+)(?:(\^?=)"([^"]*)")?\]$/);
    if (!a) continue;
    const v = n.getAttribute(a[1]);
    let ok = v != null;
    if (a[2] === "=") ok = v === a[3];
    if (a[2] === "^=") ok = v != null && v.startsWith(a[3]);
    if (ok === neg) return false;
  }
  return true;
}
function matches(n, sel) {
  return sel.split(",").some((s) => {
    const parts = s.trim().split(/\s+/);
    if (!one(n, parts[parts.length - 1])) return false;
    let i = parts.length - 2;
    for (let p = n.parentNode; p instanceof Element && i >= 0; p = p.parentNode) {
      if (one(p, parts[i])) i -= 1;
    }
    return i < 0;
  });
}
class Event {
  constructor(type, o = {}) {
    this.type = type;
    this.bubbles = Boolean(o.bubbles);
    this.defaultPrevented = false;
  }
  preventDefault() { this.defaultPrevented = true; }
}
const html = new Element("html");
const body = new Element("body");
html.append(body);
const document = {
  documentElement: html,
  body,
  activeElement: null,
  title: "",
  createElement: (t) => new Element(t),
  createElementNS: (_, t) => new Element(t),
  createTextNode: (t) => new Text(t),
  getElementById: (id) => html.querySelector("#" + id),
  querySelector: (s) => html.querySelector(s),
  querySelectorAll: (s) => html.querySelectorAll(s),
  addEventListener: () => {},
};
const location = {
  pathname: "/workspace",
  hash: "",
  search: "",
  host: "tephra.example",
  origin: "https://tephra.example",
  assigned: null,
  assign(u) { this.assigned = u; },
  replace(u) { this.assigned = u; },
  reload() { this.assigned = "reload"; },
};
const history = {
  state: [],
  replaceState(_, __, u) {
    this.state.push(u);
    const [p, h] = String(u).split("#");
    location.pathname = p;
    location.hash = h ? "#" + h : "";
  },
  pushState(a, b, u) { this.replaceState(a, b, u); },
};
async function fetch(path, init = {}) {
  const method = init.method || "GET";
  CALLS.push({ method, path, body: init.body ? JSON.parse(init.body) : null });
  const r = ROUTES[`${method} ${path}`] || { status: 404, body: { error: "not_found" } };
  const headers = new Map(Object.entries({ "content-type": "application/json", ...r.headers }));
  return {
    ok: r.status >= 200 && r.status < 300,
    status: r.status,
    headers: { get: (k) => headers.get(k.toLowerCase()) ?? null },
    json: async () => r.body,
    text: async () => JSON.stringify(r.body),
  };
}
const GLOBALS = {
  Node, Element, Text, Event, document, location, history, fetch, CALLS,
  window: globalThis,
  navigator: { clipboard: { writeText: async () => {} } },
  matchMedia: () => ({ matches: false }),
  localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
};
for (const [k, value] of Object.entries(GLOBALS)) {
  Object.defineProperty(globalThis, k, { value, writable: true, configurable: true });
}
globalThis.setRoutes = (r) => { ROUTES = r; };
globalThis.tick = () => new Promise((r) => setTimeout(r, 0));
globalThis.main = () => {
  const m = new Element("main");
  m.id = "main";
  const dlg = new Element("dialog");
  dlg.id = "ob-dlg";
  body.replaceChildren(m, dlg);
  return m;
};
// what a reader gets: element boundaries read as spaces, no space before punctuation
const words = (n) => (n instanceof Text
  ? n.data
  : n.childNodes.map((c) => (c instanceof Text ? c.data : ` ${words(c)} `)).join(""));
globalThis.text = (n) => words(n).replace(/\s+/g, " ").replace(/ ([,.;:)])/g, "$1").trim();
"""


def fixture(area: str, name: str) -> Any:
    return json.loads((FIX / area / f"{name}.json").read_text(encoding="utf-8"))


def run_node(tmp_path: Path, script: str, data: dict[str, Any] | None = None) -> Any:
    """Run `script` (an ES module body, top-level await allowed) after the DOM, with the web tree's
    JS copied beside it and DATA bound; it prints its answer with out(value)."""
    web = tmp_path / "web"
    if not web.exists():
        shutil.copytree(
            WEB,
            web,
            ignore=shutil.ignore_patterns("*.png", "*.svg", "fonts", "data", "kit", "*.woff2"),
        )
        (web / "package.json").write_text('{"type": "module"}', encoding="utf-8")
        (web / "dom.mjs").write_text(DOM, encoding="utf-8")
    (web / "data.json").write_text(json.dumps(data or {}), encoding="utf-8")
    body = (
        'import "./dom.mjs";\nimport { readFileSync } from "node:fs";\n'
        'const DATA = JSON.parse(readFileSync(new URL("./data.json", import.meta.url), "utf8"));\n'
        "const out = (v) => process.stdout.write(JSON.stringify(v));\n" + script
    )
    (web / "run.mjs").write_text(body, encoding="utf-8")
    result = subprocess.run(
        [str(NODE), "run.mjs"], cwd=web, capture_output=True, text=True, timeout=60, check=False
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


# Draws the Overview for DATA.view with view.hosted from loadHosted (fetch answered by DATA.routes),
# and reports what a reader and a screen reader get.
OVERVIEW = """
const { renderOverview } = await import("./workspace/overview.js");
const { loadHosted } = await import("./workspace/golive.js");
setRoutes(DATA.routes);
const view = DATA.view;
view.hosted = DATA.hostedOff ? null : await loadHosted(view.answers.airline.icao);
const m = main();
renderOverview(m, view);
const gl = m.querySelector("#golive");
const start = m.querySelector("#gl-start");
out({
  text: text(m),
  golive: gl ? text(gl) : null,
  buttons: [...m.querySelectorAll("button")].map((b) => text(b)),
  start: start
    ? { disabled: start.disabled, describedby: start.getAttribute("aria-describedby") }
    : null,
  why: m.querySelector("#gl-why") ? text(m.querySelector("#gl-why")) : null,
  links: [...m.querySelectorAll("#golive a")].map((a) => [text(a), a.getAttribute("href")]),
  badges: [...m.querySelectorAll(".sbadge")].map((b) => [b.className, text(b)]),
  calls: CALLS.map((c) => `${c.method} ${c.path}`),
  regionSelect: Boolean(m.querySelector("#gl-region")),
});
"""

ME = "GET /api/hosted/me"
HEADER = "GET /a/RFB/api/tenant/header"
GOLIVE = "GET /a/RFB/api/tenant/golive"


def _ok(body: Any) -> dict[str, Any]:
    return {"status": 200, "body": body}


def _overview(
    tmp_path: Path, me: str | None, header: str | None = None, golive: str | None = None, **kw: Any
) -> Any:
    routes: dict[str, Any] = {}
    if me is not None:
        routes[ME] = _ok(fixture("workspace", f"hosted-me-{me}"))
    else:
        routes[ME] = {"status": 404, "body": {"error": "not_found"}}
    if header:
        routes[HEADER] = _ok(fixture("workspace", header))
    if golive:
        routes[GOLIVE] = _ok(fixture("workspace", golive))
    routes.update(kw.pop("routes", {}))
    data = {"view": fixture("workspace", "airline-view-verified"), "routes": routes, **kw}
    return run_node(tmp_path, OVERVIEW, data)


NOT_BUILT = (
    "This shared site runs the demo only. To check your own flights, run your own TEPHRA with the "
    "setup kit."
)
NOT_BUILT_HOSTED = (
    "TEPHRA runs at most 3 airlines at once on this site. Your own TEPHRA with the setup kit has "
    "no such limit."
)


def test_hosting_off_keeps_today_s_overview(tmp_path: Path) -> None:
    off = _overview(tmp_path, None)
    assert off["golive"] is None
    assert NOT_BUILT in off["text"]
    assert NOT_BUILT_HOSTED not in off["text"]
    assert off["calls"] == [ME]
    skipped = _overview(tmp_path, "setup", hostedOff=True)
    assert skipped["golive"] is None
    assert skipped["calls"] == []


def test_desk_verified_airline_waits_for_the_operators(tmp_path: Path) -> None:
    r = _overview(tmp_path, "waiting")
    assert r["golive"] is None
    assert (
        "TEPHRA's operators approve hosting after verification. This page says when." in r["text"]
    )
    assert "It does not approve your policy or your use of TEPHRA." in r["text"]
    assert NOT_BUILT_HOSTED in r["text"]


def test_an_approved_airline_sets_up_once_with_its_name(tmp_path: Path) -> None:
    r = _overview(tmp_path, "can-set-up")
    assert r["golive"].startswith("Go live on TEPHRA")
    assert "Only the people you invite can sign in to it." in r["golive"]
    assert "Your name on TEPHRA" in r["golive"]
    assert "Set up TEPHRA for Ring of Fire Charter" in r["buttons"]
    # the site's own limit (TEPHRA_HOSTED_MAX_TENANTS=2 in this fixture), never a fixed 3
    assert NOT_BUILT_HOSTED.replace("at most 3", "at most 2") in r["text"]
    assert NOT_BUILT_HOSTED not in r["text"]
    assert NOT_BUILT not in r["text"]


SETUP = """
const { setupCard } = await import("./workspace/golive.js");
setRoutes({ "POST /api/hosted/setup": DATA.answer });
const m = main();
let done = 0;
const onDone = () => { done += 1; };
m.append(setupCard({ icao: "RFB", name: "Ring of Fire Charter" }, { onDone }));
const name = m.querySelector("input");
const go = m.querySelector('button[type="submit"]');
name.value = DATA.name;
go.click();
await tick(); await tick();
const errors = [...m.querySelectorAll(".err:not([hidden]), .inline-alert:not([hidden])")].map(text);
out({ done, calls: CALLS, errors });
"""


def test_set_up_sends_the_display_name_and_says_why_it_was_refused(tmp_path: Path) -> None:
    good = run_node(
        tmp_path,
        SETUP,
        {"name": "  Ana   Ops ", "answer": _ok(fixture("workspace", "header-setup"))},
    )
    assert good["done"] == 1
    assert good["calls"] == [
        {"method": "POST", "path": "/api/hosted/setup", "body": {"display_name": "Ana Ops"}}
    ]
    short = run_node(tmp_path, SETUP, {"name": "A", "answer": _ok({})})
    assert short["calls"] == []
    assert short["done"] == 0
    assert short["errors"] == ["2 to 32 characters."]
    taken = run_node(
        tmp_path,
        SETUP,
        {"name": "Ana Ops", "answer": {"status": 409, "body": {"error": "icao_taken"}}},
    )
    assert taken["done"] == 0
    assert taken["errors"] == [
        "Another airline already has a space with this code. Contact TEPHRA's operators."
    ]


def test_setup_shows_the_checklist_region_places_and_why_start_waits(tmp_path: Path) -> None:
    r = _overview(tmp_path, "setup", "header-setup", "golive-setup-2of4")
    g = r["golive"]
    assert "2 of 4 ready" in g
    for words in (
        "Feeds connected",
        "Model and key set",
        "Policy confirmed",
        "Dispatchers invited",
    ):
        assert words in g
    assert "Done: Model and key set" in g
    assert "To do: Feeds connected" in g
    assert ["Feeds", "/a/RFB/feeds"] in r["links"]
    assert ["Policy", "/a/RFB/settings/policy#versions"] in r["links"]
    assert "Region: Java / Bali · from your network's airports" in g
    assert not r["regionSelect"]
    assert "2 of 3 airline places in use" in g
    assert "Every draft says Shadow · not for use." in g
    assert r["start"] == {"disabled": True, "describedby": "gl-why"}
    assert r["why"] == "Finish the checklist: 2 of 4 still open."
    assert "tephra.example/a/RFB/" in g
    assert r["calls"] == [ME, HEADER, GOLIVE]


def test_start_is_open_at_four_of_four_and_only_for_ops_managers(tmp_path: Path) -> None:
    r = _overview(tmp_path, "setup", "header-setup", "golive-setup-4of4")
    assert "4 of 4 ready" in r["golive"]
    assert r["start"]["disabled"] is False
    assert (
        r["why"]
        == "Ops managers only. You can stop at any time; starting and stopping are in your record."
    )
    viewer = _overview(tmp_path, "setup", "header-setup-dispatcher", "golive-setup-4of4")
    assert viewer["start"] is None
    assert "Start shadow runs" not in viewer["buttons"]
    assert viewer["why"] == "Dispatcher: an ops manager of Ring of Fire Charter starts shadow runs."


def test_a_full_site_and_a_full_memory_say_so(tmp_path: Path) -> None:
    full = _overview(tmp_path, "setup", "header-setup", "golive-limit-reached")
    assert full["start"]["disabled"] is True
    assert (
        full["why"]
        == "All airline places on this site are in use. TEPHRA's operators can see you are ready."
    )
    assert "3 of 3 airline places in use" in full["golive"]
    memory = _overview(tmp_path, "setup", "header-setup", "golive-site-memory")
    assert memory["why"] == "This site's memory is full. TEPHRA's operators can see you are ready."


def test_an_open_checklist_on_a_full_site_says_both(tmp_path: Path) -> None:
    """UX finding 15: the first unmet blocker is the checklist, and the site is full too."""
    g = fixture("workspace", "golive-setup-2of4")
    g["slots"] = {"used": g["slots"]["max"], "max": g["slots"]["max"]}
    r = _overview(tmp_path, "setup", "header-setup", routes={GOLIVE: _ok(g)})
    assert r["why"] == (
        "Finish the checklist: 2 of 4 still open. Every airline place on this site is in use as "
        "well; TEPHRA's operators see when you are ready."
    )


def test_once_set_up_only_the_answers_and_the_kit_stay_beside_go_live(tmp_path: Path) -> None:
    """UX finding 9: the onboarding's Data feeds, Assistant and People cards repeated or
    contradicted the checklist once the airline has its space."""
    r = _overview(tmp_path, "setup", "header-setup", "golive-setup-2of4")
    assert "Your answers" in r["text"]
    assert "will approve advisories in your TEPHRA" not in r["text"]
    assert "Try a file" not in r["text"]
    before = _overview(tmp_path, "can-set-up")
    assert "will approve advisories in your TEPHRA" in before["text"]


def test_an_ambiguous_network_chooses_its_region_and_says_not_built(tmp_path: Path) -> None:
    r = _overview(tmp_path, "setup", "header-setup", "golive-region-choice")
    assert r["regionSelect"]
    assert r["why"] == "Choose a region."
    assert (
        "Not built. Your network is outside these regions: other regions are not built."
        in r["golive"]
    )


START = """
const { setupStateCard } = await import("./workspace/golive.js");
setRoutes({ "POST /a/RFB/api/tenant/start": DATA.answer });
const m = main();
let done = 0;
m.append(setupStateCard("RFB", DATA.header, DATA.golive, { onDone: () => { done += 1; } }));
const sel = m.querySelector("#gl-region");
if (sel && DATA.region) { sel.value = DATA.region; sel.dispatchEvent(new Event("change")); }
const go = m.querySelector("#gl-start");
const before = go.disabled;
go.click();
await tick(); await tick();
const said = [...m.querySelectorAll(".inline-alert:not([hidden])")].map(text);
out({ before, done, calls: CALLS, said });
"""


def test_start_sends_the_region_and_a_refusal_is_said(tmp_path: Path) -> None:
    header = fixture("workspace", "header-setup")
    picked = run_node(
        tmp_path,
        START,
        {
            "header": header,
            "golive": fixture("workspace", "golive-region-choice"),
            "region": "kyushu",
            "answer": _ok(fixture("workspace", "header-shadow")),
        },
    )
    assert picked["before"] is False
    assert picked["done"] == 1
    assert picked["calls"] == [
        {"method": "POST", "path": "/a/RFB/api/tenant/start", "body": {"region": "kyushu"}}
    ]
    refused = run_node(
        tmp_path,
        START,
        {
            "header": header,
            "golive": fixture("workspace", "golive-setup-4of4"),
            "answer": {"status": 409, "body": {"error": "airline_limit_reached"}},
        },
    )
    assert refused["calls"][0]["body"] == {"region": "java_bali"}
    assert refused["done"] == 0
    assert refused["said"] == [
        "All airline places on this site are in use. TEPHRA's operators can see you are ready."
    ]


def test_shadow_and_live_say_since_when_and_give_ops_managers_their_switches(
    tmp_path: Path,
) -> None:
    shadow = _overview(tmp_path, "shadow", "header-shadow")
    assert shadow["golive"].startswith("On TEPHRA")
    assert ["sbadge sbadge--shadow", "SHADOW"] in shadow["badges"]
    assert "Shadow runs since 15 Oct, 10:00 UTC." in shadow["golive"]
    assert ["Open TEPHRA for Ring of Fire Charter ›", "/a/RFB/"] in shadow["links"]  # noqa: RUF001
    assert {"Switch to LIVE…", "Stop shadow runs…"} <= set(shadow["buttons"])
    assert "Back to SHADOW…" not in shadow["buttons"]
    assert shadow["calls"] == [ME, HEADER]
    live = _overview(tmp_path, "live", "header-live")
    assert ["sbadge sbadge--live", "LIVE"] in live["badges"]
    assert "Live since 17 Oct, 14:02 UTC, switched by Ana Ops." in live["golive"]
    assert {"Back to SHADOW…", "Stop TEPHRA…"} <= set(live["buttons"])
    assert "Switch to LIVE…" not in live["buttons"]
    dispatcher = _overview(tmp_path, "shadow", "header-shadow-dispatcher")
    assert not {"Switch to LIVE…", "Stop shadow runs…", "Back to SHADOW…"} & set(
        dispatcher["buttons"]
    )


def test_a_paused_airline_says_so_in_red(tmp_path: Path) -> None:
    r = _overview(tmp_path, "shadow", "header-shadow-paused")
    assert (
        "Paused: Ring of Fire Charter's share of the site's free daily database allowance is used. "
        "Resumes 00:00 Pacific (07:00 UTC)." in r["golive"]
    )


def test_suspended_says_who_when_why_and_the_delete_date(tmp_path: Path) -> None:
    r = _overview(tmp_path, "suspended", "header-suspended")
    assert ["sbadge sbadge--suspended", "SUSPENDED"] in r["badges"]
    assert (
        "TEPHRA's operators suspended Ring of Fire Charter on 17 Oct, 13:40 UTC: Positions pushed "
        "for aircraft outside your fleet. Runs are stopped and pushes are refused. Your settings, "
        "people, keys and record are kept. TEPHRA's operators can delete your data from 24 Oct, "
        "13:40 UTC; nothing deletes it on its own." in r["golive"]
    )
    assert "Contact TEPHRA" in r["golive"]
    assert not {"Switch to LIVE…", "Stop shadow runs…", "Back to SHADOW…", "Stop TEPHRA…"} & set(
        r["buttons"]
    )


def test_a_failed_read_is_said_where_the_card_would_be(tmp_path: Path) -> None:
    r = _overview(
        tmp_path, "setup", routes={HEADER: {"status": 500, "body": {"error": "internal"}}}
    )
    assert r["golive"] == "TEPHRA could not read your airline's hosting: Not done (HTTP 500)."
    assert "Go live on TEPHRA" not in r["text"]


LIVE = """
const { liveDialog } = await import("./workspace/golive.js");
setRoutes({ "POST /a/RFB/api/tenant/live": { status: 200, body: {} } });
const m = main();
let done = 0;
liveDialog("RFB", DATA.header, () => { done += 1; });
const dlg = document.getElementById("ob-dlg");
const shown = { open: dlg.open, text: text(dlg), labelled: dlg.getAttribute("aria-labelledby") };
const typed = dlg.querySelector("#live-icao");
const attest = dlg.querySelector("#live-attest");
const go = dlg.querySelector('button[type="submit"]');
go.click(); await tick();
const unticked = CALLS.length;
attest.checked = true; typed.value = "rfb"; go.click(); await tick();
const lower = CALLS.length;
typed.value = "RFB"; go.click(); await tick(); await tick();
out({ shown, unticked, lower, calls: CALLS, done, open: dlg.open });
"""


def test_switch_to_live_needs_the_attestation_and_the_typed_code(tmp_path: Path) -> None:
    r = run_node(tmp_path, LIVE, {"header": fixture("workspace", "header-shadow")})
    t = r["shown"]["text"]
    assert r["shown"]["open"]
    assert r["shown"]["labelled"] == "live-h"
    assert "Switch Ring of Fire Charter to LIVE?" in t
    assert (
        "Drafts stop saying Shadow · not for use, and your dispatchers may use the advisories "
        "they approve in your operation." in t
    )
    assert (
        "TEPHRA still sends nothing to an aircraft or to any system. An approved advisory goes to "
        "your outbound list; a person passes it on." in t
    )
    assert "Ash policy v2 is ILLUSTRATIVE: its acceptance under your SRA is not recorded." in t
    assert (
        "I am Ring of Fire Charter's ops manager and may put TEPHRA's drafts into our operation."
        in t
    )
    assert "Type RFB to confirm" in t
    assert "Goes into your record Switched to LIVE by Ana Ops (Ops manager)," in t
    assert r["unticked"] == 0
    assert r["lower"] == 0
    assert r["calls"] == [
        {
            "method": "POST",
            "path": "/a/RFB/api/tenant/live",
            "body": {"confirm_icao": "RFB", "attest": True},
        }
    ]
    assert r["done"] == 1
    assert r["open"] is False


REASON = """
const { reasonDialog } = await import("./workspace/golive.js");
setRoutes({ [`POST /a/RFB/api/tenant/${DATA.path}`]: { status: 200, body: {} } });
main();
reasonDialog("RFB", DATA.header, DATA.kind, () => {});
const dlg = document.getElementById("ob-dlg");
const box = dlg.querySelector("textarea");
const go = dlg.querySelector('button[type="submit"]');
box.value = "x"; go.click(); await tick();
const short = CALLS.length;
box.value = "  Fleet maintenance week "; go.click(); await tick();
out({ text: text(dlg), short, calls: CALLS });
"""


def test_back_to_shadow_and_stop_need_a_reason(tmp_path: Path) -> None:
    back = run_node(
        tmp_path,
        REASON,
        {"header": fixture("workspace", "header-live"), "kind": "shadow", "path": "shadow"},
    )
    assert back["short"] == 0
    assert "Put Ring of Fire Charter back to SHADOW?" in back["text"]
    assert back["calls"] == [
        {
            "method": "POST",
            "path": "/a/RFB/api/tenant/shadow",
            "body": {"reason": "Fleet maintenance week"},
        }
    ]
    stop = run_node(
        tmp_path,
        REASON,
        {"header": fixture("workspace", "header-shadow"), "kind": "stop", "path": "stop"},
    )
    assert "Stop shadow runs for Ring of Fire Charter?" in stop["text"]
    assert "the airline place is freed" in stop["text"]
    assert stop["calls"][0]["path"] == "/a/RFB/api/tenant/stop"
    live_stop = run_node(
        tmp_path,
        REASON,
        {"header": fixture("workspace", "header-live"), "kind": "stop", "path": "stop"},
    )
    assert "Stop TEPHRA for Ring of Fire Charter?" in live_stop["text"]


def test_other_airlines_a_record_holder_belongs_to_are_listed(tmp_path: Path) -> None:
    me = fixture("workspace", "hosted-me-shadow")
    me["memberships"].append(
        {"icao": "RFC", "name": "Ring of Fire Cargo", "role": "viewer", "state": "live"}
    )
    r = _overview(tmp_path, None, "header-shadow", routes={ME: _ok(me)})
    assert "Other airlines you belong to" in r["text"]
    assert "Ring of Fire Cargo RFC · Viewer" in r["text"]


def test_workspace_page_wiring() -> None:
    js = (WEB / "workspace.js").read_text(encoding="utf-8")
    assert "S.joinToken = takeToken();\n  inlineSprite();" in js  # before any request or render
    assert 'if (me.status === 404 && errorCode(me) === "no_airline_record")' in js
    assert 'view.status === "verified" && has("hosted")' in js
    html = (WEB / "workspace.html").read_text(encoding="utf-8")
    assert '<link rel="stylesheet" href="/static/tenant.css">' in html
    feeds = (WEB / "workspace" / "feeds.js").read_text(encoding="utf-8")
    assert 'import { mountDryRun } from "../dryrun.js";' in feeds
    assert "segmented" not in feeds  # the dry run's own code now lives in dryrun.js only
