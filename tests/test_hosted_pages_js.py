"""A hosted airline's Feeds and Settings pages and its Desk marks (SPEC-FINAL 5.4-5.6), rendered
under Node against a small DOM stand-in from the view fixtures (tests/fixtures/hosted/tenant, the
SPEC-FINAL 4.3 shapes H3's models validate): the key is shown once and then only as ••••last4,
ILLUSTRATIVE gives way to the recorded acceptance and comes back for a newer version, the budget
draws the Desk's reserve apart, a viewer gets no decision or edit control, the suspended, paused
and not-updating lines, the setup pages, recovery values "Not built for your network", and the
shadow stamp on a draft. Skipped when Node is not installed."""

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tephra.config import SHADOW_WORDS

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "tephra" / "web"
FIX = ROOT / "tests" / "fixtures" / "hosted" / "tenant"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="Node is not installed")

# A DOM stand-in wide enough for el(), icon(), segmented() and the hosted views: elements with
# classes, attributes, text, children and listeners, serialised for the assertions below.
RUNNER = r"""
import { readFileSync } from "node:fs";
class Node {
  constructor(tag) {
    this.tagName = tag; this.className = ""; this.dataset = {}; this.attrs = {};
    this.kids = []; this._text = null; this.parentElement = null;
    this.style = { setProperty: (k, v) => { this.style[k] = v; } };
  }
  get classList() {
    const n = this;
    const add = (...c) => { n.className = `${n.className} ${c.join(" ")}`.trim(); };
    return { add, remove() {}, toggle() {}, contains: (c) => n.className.split(" ").includes(c) };
  }
  set textContent(t) { this.kids = []; this._text = String(t); }
  get textContent() {
    return this._text != null ? this._text : this.kids.map((k) => k.textContent).join("");
  }
  set hidden(v) { if (v) this.attrs.hidden = ""; else delete this.attrs.hidden; }
  get hidden() { return "hidden" in this.attrs; }
  setAttribute(k, v) { this.attrs[k] = String(v); if (k === "class") this.className = String(v); }
  getAttribute(k) { return this.attrs[k] ?? null; }
  removeAttribute(k) { delete this.attrs[k]; }
  append(...kids) {
    for (const k of kids) {
      if (k == null) throw new Error("null child");
      const n = typeof k === "string" ? new Text(k) : k;
      n.parentElement = this;
      this.kids.push(n);
    }
  }
  prepend(...kids) { this.kids.unshift(...kids); }
  after() {}
  replaceChildren(...kids) { this.kids = []; this.append(...kids); }
  addEventListener() {}
  querySelector() { return null; }
  querySelectorAll() { return []; }
  closest() { return null; }
  get children() { return this.kids.filter((k) => !(k instanceof Text)); }
  toJSON() {
    const { tagName: tag, className: cls, attrs, dataset: data, _text: text, kids } = this;
    return { tag, cls, attrs, data, text, kids };
  }
}
class Text extends Node { constructor(t) { super("#text"); this._text = String(t); } }
globalThis.Node = Node;
globalThis.document = {
  createElement: (t) => new Node(t), createElementNS: (_, t) => new Node(t),
  createTextNode: (t) => new Text(t), getElementById: () => null, querySelector: () => null,
  querySelectorAll: () => [], addEventListener: () => {}, documentElement: { dataset: {} },
};
globalThis.window = {
  matchMedia: () => ({ matches: false, addEventListener() {} }), innerWidth: 1440,
  addEventListener() {}, setTimeout, clearTimeout,
};
const fx = (n) => JSON.parse(readFileSync(`fixtures/${n}.json`, "utf8"));
const F = await import("./hosted/feeds.js");
const P = await import("./hosted/policy.js");
const A = await import("./hosted/assistant.js");
const U = await import("./hosted/people.js");
const R = await import("./hosted/record.js");
const N = await import("./tenant-nav.js");
const D = await import("./desk/ui.js");
const H = await import("./hosted.js");
const box = (...kids) => { const n = new Node("div"); n.append(...kids.flat()); return n; };
const ops = fx("header-shadow"), viewer = fx("header-viewer");
const susp = fx("header-suspended"), setup = fx("header-setup");
const now = Date.parse(ops.wall_now);
const feeds = fx("feeds"), feedsSetup = fx("feeds-setup");
const out = {};
const cardOpts = (v) => ({ now, countedSince: v.counted_since, takenIn: v.taken_in });
const cards = (v) => box(...v.cards.map((c) => F.feedCard(c, cardOpts(v))));
out.cards = cards(feeds);
out.cardsSetup = cards(feedsSetup);
const late = { ...feeds.cards[0], last_received_at: "2026-10-17T13:48:31.000Z" };
const lateOpts = { now, countedSince: "2026-10-17T13:30:00.000Z", takenIn: true };
out.positionsLate = box(F.feedCard(late, lateOpts));
const suspendedOpts = { ...cardOpts(feeds), suspended: true };
out.cardsSuspended = box(...feeds.cards.map((c) => F.feedCard(c, suspendedOpts)));
const undeclared = {
  ...feeds.cards[1], declared: false, last_received_at: null,
  records_last_hour: 0, refused_last_hour: 0, reasons: [],
};
out.undeclared = box(F.feedCard(undeclared, cardOpts(feeds)));
const keyOpts = (editable) => ({
  now, countedSince: feeds.counted_since, editable, onRotate() {}, onRevoke() {},
});
out.keys = F.keysTable(feeds.keys, keyOpts(true));
out.keysRead = F.keysTable(feeds.keys, keyOpts(false));
const secret = "tph_rfb_8Vq2m7KxW4nT9cLp3RzYe6H";
out.once = H.onceBox("New key.", secret, "TEPHRA keeps only its fingerprint.");
out.setupStrip = F.SETUP_STRIP;
out.policy = box(P.render(ops, fx("policy")));
out.policyAccepted = box(P.render(ops, fx("policy-accepted")));
const newer = fx("policy-accepted");
newer.current.version = 4;
newer.versions.unshift({ version: 4, created: newer.current.created, changed: ["fuel.hold_min"] });
newer.label = "ILLUSTRATIVE, not an airline SRA";
out.policyNewer = box(P.render(ops, newer));
out.policyViewer = box(P.render(viewer, fx("policy")));
out.policyValues = P.valuesCard(fx("policy"), { editable: true, onChange() {} });
const versions = P.versionsCard(fx("policy"), { editable: true, onConfirm() {} });
out.versionsId = versions.getAttribute("id");
out.policySuspended = box(P.render(susp, fx("policy")));
out.assistant = box(A.render(ops, fx("assistant")));
out.assistantViewer = box(A.render(viewer, fx("assistant")));
out.assistantUnavailable = box(A.render(ops, fx("assistant-unavailable")));
out.assistantSetup = box(A.render(setup, fx("assistant-setup")));
out.people = box(U.render(ops, fx("people")));
out.peopleViewer = box(U.render(viewer, fx("people-viewer")));
out.inviteWords = U.inviteWords(fx("people").invites[0], "https://tephra.example/join#token").words;
const rec = fx("record");
const recArgs = (v) => ({
  entries: v.entries, filter: "all", onFilter() {}, onOlder() {}, onCheck() {},
  older: null, checkStatus: null,
});
out.record = box(R.render(ops, rec, recArgs(rec)));
out.recordViewer = box(R.render(viewer, rec, recArgs(rec)));
out.recordBroken = box(R.chainLine(fx("record-broken").head));
out.recordDecisions = box(R.entriesTable(rec.entries, "decisions", now));
out.recordWords = [
  { action: "AI_FAILED", note: "DUTY OFFICER AI UNAVAILABLE: no model key is set" },
  { action: "AI_FAILED", note: "Plume read timed out" },
  { action: "SUPERSEDED", note: "REPLACED BY A NEWER DRAFT" },
].map((e) => [
  R.actionWords(e), box(R.entriesTable([{ ...e, at: rec.entries[0].at, seq: 1 }], "all", now)),
]);
out.alarms = {
  susp: N.alarmLines(susp), paused: N.alarmLines(fx("header-paused-airline")),
  site: N.alarmLines(fx("header-paused-site")), stale: N.alarmLines(fx("header-stale")),
};
out.chipStale = N.stateChip(fx("header-stale"), now);
const stamps = [true, false, undefined].map((shadow) => D.shadowStamp({ shadow }));
out.stamp = box(stamps.filter(Boolean));
out.noStamp = [D.shadowStamp({ shadow: false }), D.shadowStamp({}), D.shadowStamp(null)];
out.viewerLine = D.VIEWER_LINE;
const live = fx("header-live");
out.can = [
  H.can(ops, "ops_manager"), H.can(viewer, "dispatcher"), H.can(susp, "ops_manager"),
  H.can(live, "dispatcher"), H.can(live, "ops_manager"),
];
out.terse = {
  keyName: ["", "a", "ops-feed-2"].map(F.keyNameError),
  email: ["", "ana@", "ana@rfb.example"].map(U.emailError),
  modelKey: ["", "short", "A".repeat(39)].map(A.keyError),
  by: ["", "A", "Ana Ops"].map(P.byError),
  day: ["", "2026-10-17"].map(P.dayError),
};
out.uploader = F.uploaderLink();
out.words = {
  feedsLead: F.LEAD.text, notBuilt: F.NOT_BUILT, uploaderInfo: F.UPLOADER_INFO,
  peopleLimits: U.limitsWords(fx("people")), recordLead: R.lead(ops).text,
  newVersion: P.NEW_VERSION, pacing: A.PACING,
};
const where = ["/a/RFB/feeds", "/a/RFB/settings", "/a/RFB/settings/people"];
out.sections = [...where, "/a/RFB/settings/nope", "/a/RFB/"].map((p) => H.sectionOf(p));
process.stdout.write(JSON.stringify(out));
"""


def _text(node: Any) -> str:
    if node is None:
        return ""
    if node.get("text") is not None and not node.get("kids"):
        return node["text"]
    return "".join(_text(k) for k in node.get("kids", []))


def _all(node: Any) -> list[dict[str, Any]]:
    out = [node]
    for k in node.get("kids", []):
        out.extend(_all(k))
    return out


def _tags(node: Any, tag: str) -> list[dict[str, Any]]:
    return [n for n in _all(node) if n.get("tag") == tag]


def _buttons(node: Any) -> list[str]:
    """The named buttons (an (i) is not an action)."""
    return [_text(b) for b in _tags(node, "button") if "info__btn" not in b.get("cls", "")]


def _seen(node: Any) -> str:
    """The words on screen before anything is opened: no (i) popover, no screen-reader text."""
    if node is None or {"info__pop", "sr-only"} & set(str(node.get("cls", "")).split()):
        return ""
    if node.get("text") is not None and not node.get("kids"):
        return node["text"]
    return "".join(_seen(k) for k in node.get("kids", []))


def _pops(node: Any) -> list[str]:
    """The words behind each (i)."""
    return [_text(n) for n in _all(node) if "info__pop" in str(n.get("cls", "")).split()]


@pytest.fixture(scope="module")
def out(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    root = tmp_path_factory.mktemp("hosted")
    for path in WEB.rglob("*.js"):
        dest = root / path.relative_to(WEB)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(path, dest)
    shutil.copytree(FIX, root / "fixtures")
    (root / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    (root / "run.mjs").write_text(RUNNER, encoding="utf-8")
    result = subprocess.run(
        [str(NODE), "run.mjs"], cwd=root, capture_output=True, text=True, timeout=60, check=True
    )
    return json.loads(result.stdout)


def test_feed_cards(out: dict[str, Any]) -> None:
    text = _text(out["cards"])
    assert "PositionsReceiving" in text
    assert "3,412 records" in text
    # refused records: up to three reasons with counts, never the records themselves
    # each reason once, in words, without a record's index or times
    assert "observed_at is older than 300 s9" in text
    assert "positions[" not in text
    assert "Optional. Crews report ash rarely; a quiet hour is normal." in text
    assert "No push yet" in text
    assert "7 min ago" in text
    # counting began less than an hour ago: the card says since when
    assert "Since 13:30Z" in _text(out["positionsLate"])
    # positions missing for more than 10 minutes is a real alarm, in words
    late = _text(out["positionsLate"])
    assert "Not received 14 min" in late
    assert "Your flights are on the map at their last position." in late


def test_a_suspended_airline_s_cards_never_read_as_receiving(out: dict[str, Any]) -> None:
    text = _text(out["cardsSuspended"])
    assert "Receiving" not in text
    assert "Checked" not in text
    assert text.count("Refused while suspended") == 3


def test_a_feed_the_answers_do_not_list_shows_no_empty_numbers(out: dict[str, Any]) -> None:
    text = _text(out["undeclared"])
    assert "Not declared" in text
    assert "Your onboarding answers do not list this feed." in text
    assert "Last received" not in text
    assert "Refused" not in text


def test_setup_feeds_say_checked_not_taken_in(out: dict[str, Any]) -> None:
    text = _text(out["cardsSetup"])
    assert "Checked" in text
    assert "Receiving" not in text
    assert "Not declared" in text
    assert (
        out["setupStrip"] == "Checked, not taken in: TEPHRA starts in SHADOW from your workspace."
    )


def test_push_keys_show_a_key_once_then_its_last_four(out: dict[str, Any]) -> None:
    keys = json.dumps(out["keys"], ensure_ascii=False)
    assert "…k2Q9" in keys
    assert "…7mVb" in keys
    assert "tph_" not in keys
    assert "Has sent (since 09:20Z)" in _text(out["keys"])
    assert "Positions, flight plans" in _text(out["keys"])
    assert "Nothing yet" in _text(out["keys"])
    # a revoked key has no actions; the two live ones have Rotate and Revoke
    assert _buttons(out["keys"]) == ["Rotate…", "Revoke…", "Rotate…", "Revoke…"]
    assert "Revoked 15 Oct" in _text(out["keys"])
    assert _buttons(out["keysRead"]) == []
    once = _text(out["once"])
    assert "tph_rfb_8Vq2m7KxW4nT9cLp3RzYe6H" in once
    assert "TEPHRA keeps only its fingerprint." in once


def test_policy_illustrative_until_accepted_and_again_for_a_newer_version(
    out: dict[str, Any],
) -> None:
    p = _text(out["policy"])
    assert "ILLUSTRATIVE" in p
    assert "Not recorded" in p
    assert "Record acceptance of v3" in _buttons(out["policy"])
    assert "Confirm version 3" in _buttons(out["policy"])
    assert "changed in v3" in p
    assert "changed in v2" in p
    assert "as Policy A" in p
    # recovery values are shown, not edited
    assert "Not built for your network" in p
    assert "Policy B" in p
    assert "Not built" in p
    a = _text(out["policyAccepted"])
    assert "Recorded" in a
    assert (
        "Accepted under Ring of Fire Charter's SRA by Ana Ops, Head of Flight Ops, on 17 Oct 2026"
        " (SRA-VA-2026-03) · recorded by the airline, TEPHRA does not check it" in a
    )
    assert not any(
        c.get("cls", "").startswith("chip chip--illus") for c in _all(out["policyAccepted"])
    )
    assert "Withdraw acceptance…" in _buttons(out["policyAccepted"])
    assert "v3 confirmed" in a
    n = _text(out["policyNewer"])
    assert any(c.get("cls", "") == "chip chip--illus" for c in _all(out["policyNewer"]))
    assert "Version v3 was accepted on 17 Oct 2026; v4 is not." in n
    assert "Record acceptance of v4" in _buttons(out["policyNewer"])


def test_policy_shows_the_key_margins_and_keeps_every_value_one_tap_away(
    out: dict[str, Any],
) -> None:
    """UX finding 8: the margins first, "All n values" under a disclosure, and "Not built for
    your network" said once on a group none of whose values is built."""
    card = out["policyValues"]
    details = [c for c in _all(card) if c.get("tag") == "details"]
    assert len(details) == 1
    full = _text(details[0])
    assert full.startswith("All 8 values")
    assert "Airport plan · Not built for your network" in full
    assert full.count("Not built for your network") == 1
    shown = _text(card).replace(full, "")
    assert "Height margin" in shown
    assert "Airport plan" not in shown
    assert out["versionsId"] == "versions"  # the checklist's Policy link lands on Confirm


def test_policy_is_read_only_for_viewers_and_while_suspended(out: dict[str, Any]) -> None:
    for key in ("policyViewer", "policySuspended"):
        assert _buttons(out[key]) == [], key
        assert not _tags(out[key], "input"), key
        assert "v3 not confirmed" in _text(out[key])


def test_assistant_key_is_write_only_and_shown_as_its_last_four(out: dict[str, Any]) -> None:
    a = _text(out["assistant"])
    assert "••••x9Qa" in a
    assert "Stored encrypted; never shown again or written to a log." in a
    assert "Unpaid-tier data use: Google may use what TEPHRA sends with a free-tier key." in a
    # Ollama is not offered on this site, and no own TEPHRA is offered instead (the kit is dropped)
    assert "Not built: Ollama on this site." in _seen(out["assistant"])
    assert "own TEPHRA" not in a
    assert {"Change…", "Replace…", "Remove…"} <= set(_buttons(out["assistant"]))
    assert "20 calls a day · the free-tier limit for this model" in a
    assert "200 calls a day · the limit you set for your key" in a
    # no key yet: a write-only field, never filled in
    setup = out["assistantSetup"]
    (field,) = [i for i in _tags(setup, "input") if i["attrs"].get("type") == "password"]
    assert field["attrs"]["type"] == "password"
    assert field["attrs"]["autocomplete"] == "off"
    assert "value" not in field["attrs"]
    assert "Today's calls show once TEPHRA runs for Ring of Fire Charter." in _text(setup)
    # the state is said as the map and the Desk say it: "AI unavailable", its reason, its (i)
    assert "AI unavailableNo model key is set." in _seen(setup)
    assert "AI UNAVAILABLE" not in _seen(setup)
    assert "Every model step says it did not run; nothing is put in its place." in _pops(setup)[0]
    # viewers see the model and the key's last four, and change nothing
    assert _buttons(out["assistantViewer"]) == ["gemini-3.5-flash-lite", "gemini-3.8-flash"]
    u = _text(out["assistantUnavailable"])
    assert (
        "AI unavailableThe model key cannot be read: enter it again in Settings › Assistant."  # noqa: RUF001
        in _seen(out["assistantUnavailable"])
    )
    assert "Enter the key again" in u
    assert "No model chosen" not in u
    assert "No model chosen" not in _seen(out["assistantSetup"])


def test_budget_draws_the_desk_reserve_apart(out: dict[str, Any]) -> None:
    a = _text(out["assistant"])
    assert "101 of 200 calls on gemini-3.5-flash-lite" in a
    assert "Held for the Desk." in _seen(out["assistant"])
    # the explanations are one tap away, behind an (i)
    assert any("Routine work cannot take it." in p for p in _pops(out["assistant"]))
    assert "Routine work cannot take it." not in _seen(out["assistant"])
    assert "29of 40 left" in a
    assert "Urgent" in a
    assert "18 / 60" in a
    assert "11 / 40" in a
    assert "72 / 100" in a
    # the 01:00 UTC release is said once, behind the heading's (i)
    assert "01:00 UTC" not in _seen(out["assistant"])
    assert sum(p.count("01:00 UTC") for p in _pops(out["assistant"])) == 1
    assert "quota day ends 07:00 UTC (midnight Pacific)" in a
    reserve = [n for n in _all(out["assistant"]) if n.get("cls") == "reserve"]
    assert len(reserve) == 1


def test_people(out: dict[str, Any]) -> None:
    p = _text(out["people"])
    assert "Names never go to a model." in p
    assert "ana@rfb.example" in p
    assert "Make invite link" in _buttons(out["people"])
    assert _buttons(out["people"]).count("Remove…") == 2
    assert "Revoke" in _buttons(out["people"])
    assert "Leave Ring of Fire Charter…" in _buttons(out["people"])
    words = " ".join(out["inviteWords"])
    assert "Not built: email sending. Send this link yourself." in words
    assert "It joins one person as dispatcher, until 20 Oct, 09:00 UTC." in words
    assert "Emails are not checked." in words
    # the limits and what each role may do are one tap away
    assert "open invites and" not in _seen(out["people"])
    assert any("A link works once, for 72 hours." in p for p in _pops(out["people"]))
    assert [n["tag"] for n in _all(out["people"]) if n.get("cls") == "rolesfold"] == ["details"]
    v = out["peopleViewer"]
    assert "@" not in _text(v)
    assert _buttons(v) == ["Leave Ring of Fire Charter…"]
    assert not _tags(v, "select")


def test_record(out: dict[str, Any]) -> None:
    r = _text(out["record"])
    assert "Chain intact · 212 entries" in r
    assert "checked 14:00Z" in r
    assert "Check the whole chain" in _buttons(out["record"])
    assert "Export (.ndjson)" in r
    assert r.count("SHADOW") == 3
    assert "Dee Disp" in r
    assert "#MB" not in r
    assert "Check the whole chain" not in _buttons(out["recordViewer"])
    assert "Export (.ndjson)" not in _text(out["recordViewer"])
    b = _text(out["recordBroken"])
    assert "Chain broken at entry 203" in b
    assert "TEPHRA's operators see this on their console. Export still works and shows where." in b
    d = _text(out["recordDecisions"])
    assert "Approved advisory" in d
    assert "Push key made" not in d
    # a model step never called "did not run"; one that answered with nothing "gave no result";
    # a replaced draft says it once (merge verify, 17 Oct)
    (unavailable, row), (timed_out, _), (replaced, replaced_row) = out["recordWords"]
    assert unavailable == "Assistant step did not run"
    assert "gave no result" not in _text(row)
    assert "AI UNAVAILABLE: no model key is set" in _text(row)  # the raw reason stays in the record
    assert timed_out == "Assistant gave no result"
    assert replaced == "Draft replaced by a newer draft"
    assert "REPLACED BY" not in _text(replaced_row)


def test_header_lines_for_suspended_paused_and_not_updating(out: dict[str, Any]) -> None:
    a = out["alarms"]
    assert a["susp"][0]["kind"] == "suspended"
    assert a["paused"][0]["lead"].startswith("Paused: Ring of Fire Charter's share")
    assert a["site"][0]["lead"].startswith("Paused: the shared site's")
    assert a["stale"][0]["kind"] == "problem"
    assert out["chipStale"]["stale"] == "not updating since 13:51Z"


def test_desk_marks_and_roles(out: dict[str, Any]) -> None:
    stamp = out["stamp"]
    assert _text(stamp) == SHADOW_WORDS
    assert [k["cls"] for k in stamp["kids"]] == ["stamp--shadow"]
    assert out["noStamp"] == [None, None, None]
    assert out["viewerLine"] == "You can view. Ops managers and dispatchers decide."
    assert out["can"] == [True, False, False, True, False]
    assert [s["section"] for s in out["sections"]] == ["feeds", "settings", "settings", None, None]
    assert out["sections"][1]["tab"] == "policy"
    # the viewer's Desk: the decision bar, the message footer and the paperwork become read-only
    review = (WEB / "desk" / "review.js").read_text("utf-8")
    assert "} else if (isViewer()) {" in review
    assert "put(inner, el('p', { class: 'ah-viewer', text: VIEWER_LINE })" in review
    assert "if (isViewer()) {\n      sheet.setFooter(" in (WEB / "desk" / "messages.js").read_text(
        "utf-8"
    )
    docs = (WEB / "desk" / "docs.js").read_text("utf-8")
    assert "onSign: isViewer() ? null : signLine" in docs
    assert "byId('ask-btn').hidden = isViewer();" in (WEB / "desk.js").read_text("utf-8")
    # the shadow stamp sits above the flight id on the lead card, the rows and the review sheet
    queue = (WEB / "desk" / "queue.js").read_text("utf-8")
    assert "    shadowStamp(adv),\n    el('p', { class: 'lead__top' }" in queue
    assert "    shadowStamp(adv),\n    el('p', { class: 'rv2__who' }" in review
    # an empty Decide on a hosted airline
    assert "New drafts appear here as TEPHRA makes them.${at}" in queue


def test_the_assistant_tab_is_the_only_hosted_page_with_quota_words() -> None:
    quota = re.compile(r"quota|calls today|calls left|\bpacing\b|resets? (?:at|once)", re.I)
    for name in (
        "hosted/feeds.js",
        "hosted/policy.js",
        "hosted/people.js",
        "hosted/record.js",
        "hosted.js",
        "tenant-nav.js",
    ):
        code = [
            line
            for line in (WEB / name).read_text("utf-8").splitlines()
            if not re.match(r"^\s*(//|/\*|\*)", line)
        ]
        assert not any(quota.search(line) for line in code), name
    assert "quota day ends" in (WEB / "hosted" / "assistant.js").read_text("utf-8")


def test_forms_say_what_is_wrong_in_terse_words_after_the_field_is_left() -> None:
    """Owner, 17 Oct: form errors are terse ("Required", "Not an email", "2+ characters"), in the
    caution colour with a triangle (never red), shown after blur or submit (onboard/form.js
    checkOnLeave), as on sign-up."""
    hosted = (WEB / "hosted.js").read_text("utf-8")
    assert "checkOnLeave(control, () => check(control.value.trim()));" in hosted
    css = (WEB / "hosted.css").read_text("utf-8")
    assert "line-height: 1.4; font-weight: 600; color: var(--c-invalid); }" in css
    for rel in ("hosted/feeds.js", "hosted/people.js", "hosted/policy.js", "hosted/assistant.js"):
        assert "checkedField(" in (WEB / rel).read_text("utf-8"), rel


def test_terse_error_words(out: dict[str, Any]) -> None:
    t = out["terse"]
    assert t["keyName"] == ["Required", "2+ characters", None]
    assert t["email"] == ["Required", "Not an email", None]
    assert t["modelKey"] == ["Required", "Not a Google AI Studio key", None]
    assert t["by"] == ["Required", "2+ characters", None]
    assert t["day"] == ["Required", None]
    for words in t.values():
        assert all(w is None or len(w.split()) <= 10 for w in words)  # TEXT-SPEC A1: error 10


def test_the_uploader_is_offered_beside_the_push_keys(out: dict[str, Any]) -> None:
    """FOLLOWUP: push.py on Feeds as "Download uploader", a file from the member-only route."""
    (link,) = _tags(out["uploader"], "a")
    assert link["attrs"]["href"] == "/api/tenant/feeds/uploader"  # under Node: no airline
    assert link["attrs"]["download"] == "push.py"
    assert _seen(out["uploader"]) == "Download uploader"
    assert "--dry-run sends nothing" in _pops(out["uploader"])[0]
    feeds = (WEB / "hosted" / "feeds.js").read_text("utf-8")
    assert 'el("span", { class: "wcard__acts" }, uploaderLink(), ops ? newKey : null)' in feeds


def test_lines_and_explanations_keep_the_text_budgets(out: dict[str, Any]) -> None:
    """TEXT-SPEC A1/A5: a visible line 12 to 15 words at most, an (i) 25 at most."""
    w = {k: len(v.split()) for k, v in out["words"].items()}
    assert w["feedsLead"] <= 10
    assert w["recordLead"] <= 12
    assert w["notBuilt"] <= 15
    for key in ("uploaderInfo", "peopleLimits", "newVersion", "pacing"):
        assert w[key] <= 25, key
