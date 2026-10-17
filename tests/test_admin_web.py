"""The TEPHRA staff console /admin (SPEC hosted §5.7), ``tephra/web/admin.js``, under Node with the
§4.3 fixtures of ``tests/fixtures/hosted/admin``: with hosting off (owner, 17 Oct 2026: staff
verify, the demo Desk is RFA's dispatcher only) only the airlines (All, To verify, Verified,
Declined), Review… with the answers and private history, and Delete record… for a declined one;
with hosting on the tiles (places, waiting, last pass, advisories,
the free-tier tile with the namespaces and RSS), the notes, the filters and their counts, each
row's status shape and actions (Review… for pending airlines, Approve hosting… for Desk-verified
ones, Suspend… for
running ones, Resume… disabled at the limit, Delete data… only 7 days after suspension), every
destructive action behind a reason or the airline's code, the operators section, sign-in and the
operator link whose token leaves the address bar. Plus static checks of admin.html. Skipped
without Node (the static checks run anyway)."""

import re
from pathlib import Path

import pytest

from tests.test_golive_web import NODE, WEB, fixture, run_node

needs_node = pytest.mark.skipif(NODE is None, reason="Node is not installed")
HTML = (WEB / "admin.html").read_text(encoding="utf-8")
JS = (WEB / "admin.js").read_text(encoding="utf-8")
CSS = (WEB / "admin.css").read_text(encoding="utf-8")
NOW = "2026-10-17T14:05:12.000Z"

CONSOLE = """
const A = await import("./admin.js");
const list = DATA.list;
const now = Date.parse(DATA.now);
const m = main();
const card = A.airlinesCard(list, DATA.filter || "all", () => {}, now);
m.append(...A.notes(list), A.tiles(list), card);
const rows = [...m.querySelectorAll("tbody tr[data-icao]")].map((tr) => ({
  icao: tr.dataset.icao,
  cells: [...tr.children].map((td) => [td.getAttribute("data-l"), text(td)]),
  buttons: [...tr.querySelectorAll("button")].map((b) => [text(b), b.disabled]),
  badge: tr.querySelector(".sbadge").className,
}));
out({
  text: text(m),
  seen: seen(m),
  tiles: m.querySelector(".acount").children.filter((d) => d.tagName === "DIV")
    .map((d) => [d.className, text(d)]),
  // a note as [class, what is on screen, the words behind its (i) or null]
  notes: [...m.querySelectorAll(".note")].map((n) => [
    n.className, seen(n), n.querySelector(".info") ? text(n.querySelector(".info .sr-only")) : null,
  ]),
  infos: infos(m),
  tabs: [...m.querySelectorAll('[role="tab"]')].map(text),
  over: [...m.querySelectorAll(".mini--over, .is-over")].map(text),
  rows,
});
"""


def _console(tmp_path: Path, name: str, **kw: object) -> dict:
    return run_node(tmp_path, CONSOLE, {"list": fixture("admin", name), "now": NOW, **kw})


def _row(r: dict, icao: str) -> dict:
    return next(x for x in r["rows"] if x["icao"] == icao)


@needs_node
def test_the_tiles_and_the_free_tier(tmp_path: Path) -> None:
    r = _console(tmp_path, "admin-list-full")
    tiles = {t: c for c, t in r["tiles"]}
    assert "2 / 3 places in use (shadow or live)" in tiles
    # what waits for staff is said once, by the To verify and Approve hosting filters
    assert not any("waiting" in t and "staff" in t for t in tiles)
    assert not any("waiting to be verified" in t for t in tiles)
    assert "18.6 s last hosted pass, of 40 s · 14:04:00Z" in tiles
    assert "6 advisories waiting, all airlines" in tiles
    t = r["text"]
    assert "Free tier today Pacific day 17 Oct" in r["seen"]
    for words in (
        "12,000 / 40,000 reads",
        "5,100 / 16,000 writes",
        "300 / 16,000 deletes",
        "310 / 4,000 file uploads in 2026-10",
        "512 / 700 MB memory",
    ):
        assert words in t
    assert "Each airline's own daily allowance: 8,000 reads, 3,200 writes, 3,200 deletes" in t
    assert "Demo 9,000 4,000 250" in t
    assert "RFB 1,900 700 30" in t
    assert r["over"] == []
    assert r["notes"] == [
        [
            "note note--info",
            "4 airlines are still onboarding.",
            "Their answers stay private until they submit.",
        ]
    ]
    # what the bars count, behind the heading's (i), not in hover-only titles
    assert "the demo included" in dict(r["infos"])["the free tier"]
    assert "12,000 / 40,000 reads · airlines" in t


@needs_node
def test_the_demo_past_a_cap_pauses_no_airline_and_the_console_says_so(tmp_path: Path) -> None:
    """Isolation H1: the caps pause the airlines on what the airlines used; a site past a cap
    through the demo's visitors is said as a caution, never as every airline paused."""
    busy = fixture("admin", "admin-list-full")
    busy["meter"]["reads"] = 41_000
    busy["meter"]["by_namespace"]["demo"]["reads"] = 38_000
    r = run_node(tmp_path, CONSOLE, {"list": busy, "now": NOW})
    notes = [t for _, t, _ in r["notes"]]
    assert not any(n.startswith("Every airline is paused.") for n in notes)
    assert [
        "note note--caution",
        "The site is past its free daily cap. Mostly the demo's reads. No airline is paused "
        "for it.",
        "Each airline stops only at its own share.",
    ] in r["notes"]


@needs_node
def test_at_the_limit_and_at_a_cap_the_console_says_so(tmp_path: Path) -> None:
    r = _console(tmp_path, "admin-list-limit-reached")
    tiles = {t: c for c, t in r["tiles"]}
    assert tiles["3 / 3 places in use (shadow or live)"] == "full"
    notes = [t for _, t, _ in r["notes"]]
    assert notes[0] == (
        "Every airline is paused. The airlines together reached today's free writes cap. They "
        "resume at 00:00 Pacific."
    )
    assert r["notes"][0][0] == "note note--serious"
    assert any(n.startswith("Hosted airlines need always-on.") for n in notes)
    # the places tile says 3 / 3; the note says what the limit is, behind its (i)
    assert [
        "note note--caution",
        "Airline limit reached.",
        "This free-tier site runs at most 3 airlines in shadow or live.",
    ] in r["notes"]
    assert any(n.startswith("1 airline's model key cannot be read.") for n in notes)
    assert any(o.startswith("20,000 / 16,000 writes") for o in r["over"])
    assert "3,200" in r["over"]  # RFC at its own writes allowance
    assert "12,800" in r["over"]  # and RFB past its own
    rfc = dict(_row(r, "RFC")["cells"])
    assert "Record chain broken" in rfc["Problem"]
    assert "Paused: site writes allowance used" in rfc["Problem"]


@needs_node
def test_each_status_gets_its_shape_and_its_actions(tmp_path: Path) -> None:
    r = _console(tmp_path, "admin-list-full")
    rfb, rfe, rfr, rfn, rfs = (_row(r, x) for x in ("RFB", "RFE", "RFR", "RFN", "RFS"))
    assert rfb["badge"] == "sbadge sbadge--shadow"
    assert ["Suspend…", False] in rfb["buttons"]
    assert "SHADOW since 15 Oct" in dict(rfb["cells"])["Status"]
    assert "VERIFIED setting up · checklist 2/4" in dict(rfe["cells"])["Status"]
    assert ["Suspend…", False] in rfe["buttons"]
    assert rfr["badge"] == "sbadge sbadge--pending"
    assert ["Review…", False] in rfr["buttons"]
    assert "VERIFIED (DESK)" in dict(rfn["cells"])["Status"]
    # verified already: its action is the approval, in the operator's words (journey 22)
    assert ["Approve hosting…", False] in rfn["buttons"]
    assert ["Review…", False] not in rfn["buttons"]
    assert rfs["badge"] == "sbadge sbadge--suspended"
    assert ["Resume…", False] in rfs["buttons"]
    assert ["Delete data… From 21 Oct, 13:40 UTC", True] in rfs["buttons"]
    # a decided airline's answers and history are one menu item away; a pending one's are Review…
    assert ["Answers and history", False] in rfn["buttons"]
    assert ["Answers and history", False] not in rfr["buttons"]
    assert dict(rfb["cells"])["Feeds"] == "2 of 3 receiving · pilot reports quiet 15 h"
    assert (
        dict(_row(r, "RFC")["cells"])["Feeds"]
        == "1 of 2 not received · positions not received 14 min"
    )
    assert dict(rfs["cells"])["Feeds"] == "Pushes refused"
    # each bar names its model (three unlabelled bars could not be told apart)
    assert (
        dict(_row(r, "RFC")["cells"])["AI use today"]
        == "gemini-3.5-flash-lite: 170 / 200 gemini-3.8-flash: 12 / 20"
    )
    # the row's code is its tile: the line under the name is the contact email alone
    assert "RFC · " not in dict(_row(r, "RFC")["cells"])["Airline"]
    # phone cards: every data cell carries its label
    assert [c for c, _ in rfb["cells"]] == [
        "Airline",
        "Status",
        "Feeds",
        "AI use today",
        "Advisories waiting",
        "Problem",
        None,
    ]


@needs_node
def test_delete_opens_after_seven_days_and_resume_waits_for_a_place(tmp_path: Path) -> None:
    r = _console(tmp_path, "admin-list-limit-reached")
    rfs = _row(r, "RFS")
    assert ["Resume…", True] in rfs["buttons"]
    assert "Airline limit reached: 3 of 3 places in use" in dict(rfs["cells"])[None]
    assert ["Delete data…", False] in rfs["buttons"]


@needs_node
def test_filters_count_what_they_show(tmp_path: Path) -> None:
    r = _console(tmp_path, "admin-list-full")
    # a Desk-verified airline is never "to verify" (journey 17 Oct 2026, 22): its own count
    assert r["tabs"] == [
        "All · 6",
        "To verify · 1",
        "Approve hosting · 1",
        "Running · 2",
        "Suspended · 1",
    ]
    verify = _console(tmp_path, "admin-list-full", filter="verify")
    assert [x["icao"] for x in verify["rows"]] == ["RFR"]
    approve = _console(tmp_path, "admin-list-full", filter="approve")
    assert [x["icao"] for x in approve["rows"]] == ["RFN"]
    assert "VERIFIED (DESK)" in dict(approve["rows"][0]["cells"])["Status"]
    running = _console(tmp_path, "admin-list-full", filter="running")
    assert [x["icao"] for x in running["rows"]] == ["RFB", "RFC"]
    empty = _console(tmp_path, "admin-list-empty")
    assert "No airline here." in empty["text"]
    assert "\u2013 no hosted pass on this instance yet" in [t for _, t in empty["tiles"]]


ACT = """
const A = await import("./admin.js");
setRoutes(DATA.routes);
const m = main();
const dlg = Object.assign(new Element("dialog"), { id: "ad-dlg" });
document.body.append(dlg);
A.act(DATA.kind, DATA.row);
await tick();
const shown = text(dlg);
const look = { seen: seen(dlg), infos: infos(dlg) };
const go = dlg.querySelector('button[type="submit"]');
for (const [sel, v] of DATA.fill || []) dlg.querySelector(sel).value = v;
if (go) { go.click(); await tick(); await tick(); }
const shownErrors = dlg.querySelectorAll(".err:not([hidden]), .inline-alert:not([hidden])");
const errors = [...shownErrors].map(text);
out({ shown, look, calls: CALLS.map((c) => [c.method, c.path, c.body]), errors, open: dlg.open });
"""


def _act(
    tmp_path: Path, kind: str, icao: str, fill: list | None = None, answer: dict | None = None
) -> dict:
    rows = fixture("admin", "admin-list-full")["rows"]
    row = next(r for r in rows if r["icao"] == icao)
    routes = {
        f"POST /api/admin/tenants/{icao}/{p}": answer or {"status": 200, "body": row}
        for p in ("suspend", "resume", "delete-data", "ops-manager-invite")
    }
    routes.update(
        {
            f"POST /api/admin/airlines/{row['airline_id']}/{p}": {"status": 200, "body": row}
            for p in ("approve-hosting",)
        }
    )
    routes["GET /api/admin/airlines"] = {"status": 200, "body": fixture("admin", "admin-list-full")}
    routes["GET /api/admin/operators"] = {"status": 200, "body": fixture("admin", "operators")}
    return run_node(tmp_path, ACT, {"kind": kind, "row": row, "fill": fill or [], "routes": routes})


@needs_node
def test_suspend_needs_a_reason_and_delete_needs_the_code(tmp_path: Path) -> None:
    bare = _act(tmp_path, "suspend", "RFB")
    assert "Suspend Ring of Fire Charter (RFB)?" in bare["shown"]
    # one line on screen; the delete rule and the record behind its (i); who reads the reason
    seen, infos = bare["look"]["seen"], dict(bare["look"]["infos"])
    assert "Runs stop and pushes are refused at once; its members can still read." in seen
    assert "delete its data" not in seen
    assert "It goes into the airline's record." in infos["suspending"]
    assert infos["the reason"] == "The airline reads it in its record."
    assert bare["calls"] == []
    assert bare["errors"] == ["Required"]  # terse (declutter, 17 Oct 2026)
    done = _act(tmp_path, "suspend", "RFB", [["#ad-reason", "Pushed another operator's aircraft"]])
    assert done["calls"][0] == [
        "POST",
        "/api/admin/tenants/RFB/suspend",
        {"reason": "Pushed another operator's aircraft"},
    ]
    wrong = _act(tmp_path, "delete", "RFS", [["#ad-icao", "rfs"]])
    assert "It cannot be undone." in wrong["look"]["seen"]
    assert (
        "A tombstone keeps its code, name and dates"
        in dict(wrong["look"]["infos"])["what is deleted"]
    )
    assert wrong["calls"] == []
    assert wrong["errors"] == ["Type RFS"]
    ok = _act(tmp_path, "delete", "RFS", [["#ad-icao", "RFS"]])
    assert ok["calls"][0] == ["POST", "/api/admin/tenants/RFS/delete-data", {"confirm_icao": "RFS"}]
    soon = _act(
        tmp_path,
        "delete",
        "RFS",
        [["#ad-icao", "RFS"]],
        {"status": 409, "body": {"error": "too_soon"}},
    )
    assert soon["errors"] == ["Its data can be deleted only 7 days after suspension."]


@needs_node
def test_approve_resume_and_the_ops_manager_link(tmp_path: Path) -> None:
    ap = _act(tmp_path, "approve", "RFN")
    assert "Approve hosting for Ring of Fire Nusantara (RFN)?" in ap["shown"]
    assert ap["calls"][0] == [
        "POST",
        "/api/admin/airlines/AL-4d5e6f708192/approve-hosting",
        {"version": 3},
    ]
    rs = _act(tmp_path, "resume", "RFS")
    assert "It resumes in SHADOW, never straight to LIVE" in rs["shown"]
    link = fixture("admin", "ops-manager-link")
    om = _act(tmp_path, "opsinvite", "RFB", answer={"status": 200, "body": link})
    assert om["calls"] == [["POST", "/api/admin/tenants/RFB/ops-manager-invite", {}]]


OPS = """
const A = await import("./admin.js");
setRoutes(DATA.routes);
const m = main();
m.append(A.operatorsCard(DATA.ops, () => {}));
m.querySelector("#op-name").value = "R. Osei";
m.querySelector("#op-email").value = "R.Osei@tephra.example";
m.querySelector('form button[type="submit"]').click(); await tick(); await tick();
const buttons = [...m.querySelectorAll("tbody button")].map(text);
out({ text: text(m), calls: CALLS.map((c) => [c.path, c.body]), buttons });
"""


@needs_node
def test_operators_are_listed_and_an_invite_link_is_shown_once(tmp_path: Path) -> None:
    routes = {
        "POST /api/admin/operators/invites": {
            "status": 200,
            "body": fixture("admin", "operator-link"),
        }
    }
    r = run_node(tmp_path, OPS, {"ops": fixture("admin", "operators"), "routes": routes})
    assert r["calls"] == [
        ["/api/admin/operators/invites", {"name": "R. Osei", "email": "r.osei@tephra.example"}]
    ]
    assert (
        "Shown once. Email sending is not built: send it yourself. It works for "
        "r.osei@tephra.example only, until 18 Oct, 14:05 UTC." in r["text"]
    )
    assert "https://tephra.example/admin/join#" in r["text"]
    assert "Disabled 15 Oct by M. Tan" in r["text"]
    assert r["buttons"] == ["Disable yourself…", "Disable…"]


SIGNIN = """
const A = await import("./admin.js");
setRoutes(DATA.routes);
const m = main();
m.append(A.signinCard());
m.querySelector("#as-email").value = "m.tan@tephra.example";
m.querySelector("#as-pw").value = "wrong-password-1";
m.querySelector('button[type="submit"]').click(); await tick(); await tick();
out({ text: text(m), errors: [...m.querySelectorAll(".inline-alert:not([hidden])")].map(text) });
"""


@needs_node
def test_sign_in_says_the_tries_left(tmp_path: Path) -> None:
    routes = {
        "POST /api/admin/sign-in": {
            "status": 401,
            "body": {"error": "bad_credentials"},
            "headers": {"x-tephra-tries-left": "2"},
        }
    }
    r = run_node(tmp_path, SIGNIN, {"routes": routes})
    assert "TEPHRA staff sign-in" in r["text"]
    assert "Operator" not in r["text"]
    assert r["errors"] == [
        "That email and password don't match. 2 tries left before sign-in waits 15 minutes."
    ]


JOIN = """
const A = await import("./admin.js");
location.pathname = "/admin/join"; location.hash = "#" + DATA.token;
const token = A.takeToken();
const left = location.pathname + location.hash;
setRoutes(DATA.routes);
const m = main();
m.append(await A.joinCard(token));
out({ token, left, text: text(m), calls: CALLS.map((c) => [c.path, c.body]) });
"""


@needs_node
def test_the_operator_link_reads_its_token_once(tmp_path: Path) -> None:
    token = "Zq3v9kN2Lw8xP0aRt5yUcB7mH1sDfG4jE6oQiKlVbYw"
    ok = {
        "POST /api/admin/invite/lookup": {
            "status": 200,
            "body": fixture("admin", "operator-invite"),
        }
    }
    r = run_node(tmp_path, JOIN, {"token": token, "routes": ok})
    assert r["token"] == token
    assert r["left"] == "/admin/join"
    assert r["calls"] == [["/api/admin/invite/lookup", {"token": token}]]
    assert "Join TEPHRA staff" in r["text"]
    assert "operator" not in r["text"].lower()
    assert "For r•••@tephra.example" in r["text"]
    gone = run_node(
        tmp_path,
        JOIN,
        {
            "token": token,
            "routes": {
                "POST /api/admin/invite/lookup": {"status": 404, "body": {"error": "invite_gone"}}
            },
        },
    )
    assert "This staff link is used or expired. Ask TEPHRA staff for a new one." in gone["text"]


def test_admin_html_is_the_shared_shell() -> None:
    assert (
        '<nav class="topnav" aria-label="TEPHRA pages"><a href="/demo">Demo</a>'
        '<a href="/desk">Desk</a><a href="/admin" aria-current="page">Staff</a>'
        '<a href="/guide">Guide</a></nav>' in HTML
    )
    for hook in ('<a class="skip-link" href="#main">', 'id="announcer"', 'id="tn-right"'):
        assert hook in HTML, hook
    assert '<meta name="color-scheme" content="dark light">' in HTML
    assert '<meta name="robots" content="noindex, nofollow">' in HTML
    assert HTML.index('src="/static/theme-boot.js"') < HTML.index('type="module"')
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", HTML, re.I)
    assert not re.search(r"\sstyle=|<style", HTML, re.I)
    for css in ("tokens.css", "topnav.css", "product.css", "tenant.css", "admin.css"):
        assert f'href="/static/{css}"' in HTML
    # one short footer line (no decision-support sentence); admin.js adds its (i)
    assert '<span id="ad-foot" class="pfoot__private">' in HTML
    assert "<span>TEPHRA staff only</span>" in HTML
    assert "perator" not in HTML.split("<body")[1]
    assert "Each action on an airline goes into that airline's record." not in HTML
    assert "Each action on an airline goes into that airline's record." in JS
    assert 'class="product admin-shell"' in HTML
    assert 'id="ad-dlg" class="pdlg"' in HTML


def test_admin_preloads_every_module_it_imports() -> None:
    from tests.test_modulepreload import PRELOAD, _closure

    assert set(PRELOAD.findall(HTML)) == _closure("admin.js")


def test_admin_code_and_style_rules() -> None:
    assert "innerHTML" not in JS
    assert "insertAdjacentHTML" not in JS
    assert "localStorage" not in JS
    assert "sessionStorage" not in JS
    assert not re.search(r"\{\s*style:", JS)
    # the only CSSOM write is a bar's width, a custom property
    assert re.findall(r"\.style\.\w+\(", JS) == [".style.setProperty("]
    assert "@media (max-width: 900px)" in CSS
    assert "td[data-l]::before" in CSS
    for t in re.findall(r"grid-template-columns:\s*([^;]+);", CSS):
        assert "1fr" not in t or "minmax(0" in t, t
    # tokens route in JSON bodies only, never in a path
    for line in JS.splitlines():
        if "call(" in line and "token" in line:
            assert "body: {" in line, line
            assert "token" in line.split("body: {")[1], line


FOOT = """
const A = await import("./admin.js");
const m = main();
const foot = Object.assign(new Element("span"), { id: "ad-foot" });
foot.append("TEPHRA staff only");
m.append(foot, A.signinCard());
A.footInfo(document);
A.footInfo(document);  // once only
out({ seen: seen(m), infos: infos(m) });
"""


@needs_node
def test_the_footer_and_the_sign_in_card_say_each_fact_once(tmp_path: Path) -> None:
    """Owner, 17 Oct 2026: no page-footer sentence, one short line and an (i). The sign-in card
    has no lead repeating the footer; the not-built email reset is a chip."""
    r = run_node(tmp_path, FOOT, {})
    assert r["infos"] == [
        ["the record", "Each action on an airline goes into that airline's record."]
    ]
    assert "For TEPHRA's operators of this site." not in r["seen"]
    assert "Airline? Sign in here Email reset: not built" in r["seen"]


# --- hosting off: the airlines to verify, nothing of hosting -------------------------------------


@needs_node
def test_with_hosting_off_the_console_is_the_airlines_alone(tmp_path: Path) -> None:
    script = """
const A = await import("./admin.js");
const list = A.staffList(DATA.list);
const m = main();
m.append(...A.notes(list), A.airlinesCard(list, DATA.filter, () => {}, Date.parse(DATA.now)));
const rows = [...m.querySelectorAll("tbody tr[data-icao]")].map((tr) => ({
  icao: tr.dataset.icao,
  cells: [...tr.children].map((td) => [td.getAttribute("data-l"), text(td)]),
  buttons: [...tr.querySelectorAll("button")].map((b) => [text(b), b.disabled]),
}));
out({
  text: text(m),
  tabs: [...m.querySelectorAll('[role="tab"]')].map(text),
  heads: [...m.querySelectorAll("thead th")].map(text),
  rows,
  tiles: m.querySelectorAll(".acount").length,
});
"""
    data = {"list": fixture("admin", "staff-list"), "now": NOW, "filter": "all"}
    r = run_node(tmp_path, script, data)
    assert r["tabs"] == ["All · 3", "To verify · 1", "Verified · 1", "Declined · 1"]
    assert r["heads"] == ["Airline", "Status", "Actions"]
    assert r["tiles"] == 0
    for gone in ("Approve hosting", "Suspend", "Feeds", "AI use", "places", "free tier", "Running"):
        assert gone not in r["text"], gone
    assert "2 airlines are still onboarding." in r["text"]
    rows = {x["icao"]: x for x in r["rows"]}
    assert rows["RFR"]["buttons"] == [["Review…", False]]
    assert "submitted 17 Oct · 1 hint" in dict(rows["RFR"]["cells"])["Status"]
    # the same words as with hosting on: "PENDING", and a decided row says since its decision
    assert dict(rows["RFR"]["cells"])["Status"].startswith("PENDING submitted")
    assert dict(rows["RFN"]["cells"])["Status"] == "VERIFIED since 16 Oct"
    assert dict(rows["SPM"]["cells"])["Status"] == "DECLINED since 15 Oct"
    assert ["Answers and history", False] in rows["RFN"]["buttons"]
    assert ["Delete record…", False] in rows["SPM"]["buttons"]
    assert ["Delete record…", False] not in rows["RFN"]["buttons"]
    assert [c for c, _ in rows["RFR"]["cells"]] == ["Airline", "Status", None]


DETAIL = """
const F = await import("./wall/features.js");
F.setFeatures(DATA.features);
const A = await import("./admin.js");
setRoutes(DATA.routes);
main();
const dlg = Object.assign(new Element("dialog"), { id: "ad-dlg" });
document.body.append(dlg);
A.act(DATA.kind, DATA.row);
await tick(); await tick();
const look = { shown: text(dlg), seen: seen(dlg), infos: infos(dlg), wide: dlg.className };
for (const [sel, v] of DATA.fill || []) dlg.querySelector(sel).value = v;
const press = [...dlg.querySelectorAll("button")].find((b) => text(b) === DATA.press);
if (press) { press.click(); await tick(); await tick(); }
out({ ...look, calls: CALLS.map((c) => [c.method, c.path, c.body]),
  history: [...dlg.querySelectorAll(".adet__hist li")].map(text) });
"""


def _detail(tmp_path: Path, name: str, row: dict, **kw: object) -> dict:
    one = fixture("admin", name)
    routes = {
        f"GET /api/admin/airlines/{one['id']}": {"status": 200, "body": one},
        "GET /api/policy": {"status": 404, "body": {}},
        f"POST /api/admin/airlines/{one['id']}/verify": {"status": 200, "body": one},
        f"POST /api/admin/airlines/{one['id']}/decline": {"status": 200, "body": one},
        f"POST /api/admin/airlines/{one['id']}/delete": {"status": 204, "body": None},
        "GET /api/admin/airlines": {"status": 200, "body": fixture("admin", "staff-list")},
        "GET /api/admin/operators": {"status": 200, "body": fixture("admin", "operators")},
    }
    data = {"routes": routes, "row": row, "features": ["onboard"], "kind": "review", **kw}
    return run_node(tmp_path, DETAIL, data)


def _staff_row(icao: str) -> dict:
    script_rows = fixture("admin", "staff-list")["airlines"]
    a = next(x for x in script_rows if x["icao"] == icao)
    return {
        "airline_id": a["id"], "name": a["name"], "icao": a["icao"], "status": a["status"],
        "status_label": a["status_label"], "state_since": a["submitted_at"],
        "ops_email": a["ops_email"], "version": a["version"], "hints": len(a["flags"]),
    }  # fmt: skip


@needs_node
def test_review_shows_the_answers_and_history_then_verifies(tmp_path: Path) -> None:
    r = _detail(
        tmp_path, "airline-detail-pending", _staff_row("RFR"), press="Verify",
        fill=[["#ad-note", "AOC checked"]],
    )  # fmt: skip
    assert "Review Ring of Fire Regional (RFR)" in r["shown"]
    assert "pdlg--wide" in r["wide"]
    assert "Check who they are: write to ops@rfr.example from an address you trust." in r["seen"]
    infos = dict(r["infos"])
    assert "Verifying does not approve their policy and publishes nothing." in infos["verifying"]
    assert "hosting" not in infos["verifying"]  # hosting off: a verify approves no hosting
    assert "1 hint for you" in r["seen"]
    assert "no AOC number given" in r["seen"]
    assert "Answers" in r["seen"]
    assert "Private history" in r["seen"]
    assert r["history"] == [
        "17 Oct, 09:00 UTC Account created · airline",
        "17 Oct, 09:12 UTC Submitted · airline",
    ]
    verify = ["POST", "/api/admin/airlines/AL-0a1b2c3d4e5f/verify"]
    assert [*verify, {"version": 2, "note": "AOC checked"}] in r["calls"]


@needs_node
def test_with_hosting_on_a_verify_says_it_approves_hosting(tmp_path: Path) -> None:
    r = _detail(
        tmp_path, "airline-detail-pending", _staff_row("RFR"), features=["onboard", "hosted"]
    )
    assert "Here it also approves hosting." in dict(r["infos"])["verifying"]


DECLINE = """
const A = await import("./admin.js");
setRoutes(DATA.routes);
main();
const dlg = Object.assign(new Element("dialog"), { id: "ad-dlg" });
document.body.append(dlg);
A.act("review", DATA.row);
await tick(); await tick();
const review = { reason: Boolean(dlg.querySelector("#ad-reason")) };
[...dlg.querySelectorAll("button")].find((b) => text(b) === "Decline…").click();
await tick();
const posts = () => CALLS.filter((c) => c.method === "POST").length;
const step = { seen: seen(dlg), posts: posts() };
dlg.querySelector('button[type="submit"]').click(); await tick();
const empty = { posts: posts(), err: text(dlg.querySelector("#ad-reason-err")) };
dlg.querySelector("#ad-reason").value = DATA.reason;
dlg.querySelector('button[type="submit"]').click(); await tick(); await tick();
out({ review, step, empty, calls: CALLS.map((c) => [c.method, c.path, c.body]) });
"""


@needs_node
def test_decline_asks_again_and_needs_a_reason(tmp_path: Path) -> None:
    """UX check, 17 Oct 2026: "Decline…" promised a second step but declined at once; it now
    asks the question with the reason, as the Desk did."""
    one = fixture("admin", "airline-detail-pending")
    routes = {
        f"GET /api/admin/airlines/{one['id']}": {"status": 200, "body": one},
        "GET /api/policy": {"status": 404, "body": {}},
        f"POST /api/admin/airlines/{one['id']}/decline": {"status": 200, "body": one},
        "GET /api/admin/airlines": {"status": 200, "body": fixture("admin", "staff-list")},
        "GET /api/admin/operators": {"status": 200, "body": fixture("admin", "operators")},
    }
    data = {"routes": routes, "row": _staff_row("RFR"), "reason": "Not an airline we can find"}
    r = run_node(tmp_path, DECLINE, data)
    assert r["review"]["reason"] is False  # the review dialog has no reason box
    assert "Decline Ring of Fire Regional (RFR)?" in r["step"]["seen"]
    assert "The airline reads your reason when it signs in." in r["step"]["seen"]
    assert r["step"]["posts"] == 0
    assert r["empty"] == {"posts": 0, "err": "Required"}
    assert [
        "POST",
        "/api/admin/airlines/AL-0a1b2c3d4e5f/decline",
        {"version": 2, "reason": "Not an airline we can find"},
    ] in r["calls"]


@needs_node
def test_a_decided_airline_shows_its_history_in_staff_words(tmp_path: Path) -> None:
    """Owner, 17 Oct 2026: history labels say "TEPHRA staff"; a Desk decision made before keeps
    its old actor name."""
    r = _detail(tmp_path, "airline-detail-verified", _staff_row("RFN"))
    assert "Ring of Fire Nusantara (RFN)" in r["shown"]
    assert "Review " not in r["shown"]
    assert not any(b in r["shown"] for b in ("Verify", "Decline"))
    assert r["history"][2:] == [
        "16 Oct, 09:30 UTC Verified · Rina Desk · AOC checked by phone",
        "17 Oct, 10:00 UTC Hosting approved · TEPHRA staff (M. Tan)",
    ]


@needs_node
def test_delete_record_is_for_a_declined_airline_and_confirms(tmp_path: Path) -> None:
    script = """
const A = await import("./admin.js");
setRoutes(DATA.routes);
main();
const dlg = Object.assign(new Element("dialog"), { id: "ad-dlg" });
document.body.append(dlg);
A.act("deleterecord", DATA.row);
await tick();
const seenNow = seen(dlg);
dlg.querySelector('button[type="submit"]').click(); await tick(); await tick();
out({ seen: seenNow, calls: CALLS.map((c) => [c.method, c.path, c.body]) });
"""
    row = _staff_row("SPM")
    routes = {
        f"POST /api/admin/airlines/{row['airline_id']}/delete": {"status": 204, "body": None},
        "GET /api/admin/airlines": {"status": 200, "body": fixture("admin", "staff-list")},
        "GET /api/admin/operators": {"status": 200, "body": fixture("admin", "operators")},
    }
    r = run_node(tmp_path, script, {"routes": routes, "row": row})
    assert "Delete Spam Air (SPM)'s record?" in r["seen"]
    assert "It cannot be undone." in r["seen"]
    assert r["calls"][0] == ["POST", "/api/admin/airlines/AL-9a8b7c6d5e4f/delete", {"version": 3}]


FOCUS = """
const A = await import("./admin.js");
setRoutes(DATA.routes);
const m = main();
Object.defineProperty(Element.prototype, "isConnected", { get() {
  let n = this;
  while (n.parentNode) n = n.parentNode;
  return n === document.documentElement;
} });
const dlg = Object.assign(new Element("dialog"), { id: "ad-dlg" });
document.body.append(dlg);
const list = A.staffList(DATA.list);
m.append(A.airlinesCard(list, "all", () => {}, Date.parse(DATA.now)));
const row = m.querySelector('tr[data-icao="RFN"]');
const more = row.querySelector('[aria-haspopup="menu"]');
more.click();
const item = row.querySelector('[data-act="review"]');
item.focus();
item.click();
await tick(); await tick();
const opened = dlg.open;
// Chrome: the hidden item cannot take focus back, so it stays in the closed dialog
document.activeElement = dlg.querySelector("h2");
[...dlg.querySelectorAll("button")].find((x) => text(x) === "Close").click();
out({ opened, back: document.activeElement === more });
"""


@needs_node
def test_closing_answers_and_history_gives_focus_back_to_the_rows_menu_button(
    tmp_path: Path,
) -> None:
    """UX check, 17 Oct 2026: closing a dialog opened from a row's ⋯ menu left focus on <body>."""
    one = fixture("admin", "airline-detail-verified")
    routes = {
        f"GET /api/admin/airlines/{one['id']}": {"status": 200, "body": one},
        "GET /api/policy": {"status": 404, "body": {}},
    }
    data = {"routes": routes, "list": fixture("admin", "staff-list"), "now": NOW}
    r = run_node(tmp_path, FOCUS, data)
    assert r == {"opened": True, "back": True}
