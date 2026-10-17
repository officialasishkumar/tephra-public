"""The operator console /admin (SPEC hosted §5.7), ``tephra/web/admin.js``, under Node with the §4.3
fixtures of ``tests/fixtures/hosted/admin``: the tiles (places, waiting, last pass, advisories,
the free-tier tile with the namespaces and RSS), the notes, the filters and their counts, each
row's status shape and actions (Review… for pending and Desk-verified airlines, Suspend… for
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
    assert "2 waiting to be verified" in tiles
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
    assert ["Review…", False] in rfn["buttons"]
    assert rfs["badge"] == "sbadge sbadge--suspended"
    assert ["Resume…", False] in rfs["buttons"]
    assert ["Delete data… From 21 Oct, 13:40 UTC", True] in rfs["buttons"]
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
    assert r["tabs"] == ["All · 6", "To verify · 2", "Running · 2", "Suspended · 1"]
    verify = _console(tmp_path, "admin-list-full", filter="verify")
    assert [x["icao"] for x in verify["rows"]] == ["RFR", "RFN"]
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
    assert "Operator sign-in" in r["text"]
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
    assert "Become an operator of TEPHRA" in r["text"]
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
    assert "This operator link is used or expired. Ask an operator for a new one." in gone["text"]


def test_admin_html_is_the_shared_shell() -> None:
    assert (
        '<nav class="topnav" aria-label="TEPHRA pages"><a href="/demo">Demo</a>'
        '<a href="/desk">Desk</a><a href="/admin" aria-current="page">Admin</a>'
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
    assert "<span>Operators of this site only</span>" in HTML
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
foot.append("Operators of this site only");
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
    assert "Airline? Use the workspace Email reset: not built" in r["seen"]
