"""The invite page /join#<token> (SPEC hosted §5.1, D7, S8), ``tephra/web/workspace/join.js``,
under Node with the §4.3 fixtures: the token is read from the fragment and the fragment removed
before any request, the invite card says who, what and until when and that emails are not
checked, a gone link says so, a new account joins with the token in the JSON body, an existing
account signs in here and then accepts, and the token never reaches a path or storage. Also the
sign-in ``?next=`` rule for hosted pages. Skipped without Node."""

from pathlib import Path

from tests.test_golive_web import WEB, fixture, run_node

TOKEN = "Hk2Pq9Lm4Nx7Rt1Vb8Cy3Wz6Ds5Fg0Ja2Qe9Uo4Ii7"
LOOKUP = "POST /api/hosted/invites/lookup"

TAKE = """
const { takeToken } = await import("./workspace/join.js");
const out1 = [];
for (const [path, hash] of DATA.cases) {
  location.pathname = path; location.hash = hash; history.state = [];
  out1.push([takeToken(), location.pathname + location.hash, history.state]);
}
out(out1);
"""


def test_the_token_leaves_the_address_bar_at_once(tmp_path: Path) -> None:
    cases = [
        ["/join", f"#{TOKEN}"],
        ["/join", "#short"],
        ["/join", ""],
        ["/workspace", f"#{TOKEN}"],
    ]
    assert run_node(tmp_path, TAKE, {"cases": cases}) == [
        [TOKEN, "/join", ["/join"]],
        ["", "/join", ["/join"]],
        [None, "/join", []],
        [None, f"/workspace#{TOKEN}", []],
    ]


PAGE = """
const { renderJoin } = await import("./workspace/join.js");
setRoutes(DATA.routes);
const m = main();
await renderJoin(m, { token: DATA.token, signedIn: DATA.signedIn });
const fill = (sel, v) => {
  const n = m.querySelector(sel);
  if (n.type === "checkbox") n.checked = v;
  else n.value = v;
};
for (const [sel, v] of DATA.fill || []) fill(sel, v);
if (DATA.submit) { m.querySelector('button[type="submit"]').click(); await tick(); await tick(); }
out({
  title: document.title,
  text: text(m),
  seen: seen(m),
  infos: infos(m),
  buttons: [...m.querySelectorAll("button")].map(text),
  tabs: [...m.querySelectorAll('[role="tab"]')]
    .map((b) => [text(b), b.getAttribute("aria-selected")]),
  calls: CALLS,
  assigned: location.assigned,
  errors: [...m.querySelectorAll(".err:not([hidden]), .inline-alert:not([hidden])")].map(text),
});
"""


def _page(
    tmp_path: Path,
    *,
    token: str | None = TOKEN,
    signed_in: bool = False,
    lookup: dict | None = None,
    **kw: object,
) -> dict:
    routes = {LOOKUP: lookup or {"status": 200, "body": fixture("workspace", "invite-dispatcher")}}
    routes.update(kw.pop("routes", {}))  # type: ignore[arg-type]
    return run_node(tmp_path, PAGE, {"token": token, "signedIn": signed_in, "routes": routes, **kw})


def test_the_invite_card_says_who_what_until_when_and_that_emails_are_not_checked(
    tmp_path: Path,
) -> None:
    r = _page(tmp_path)
    assert r["title"] == "Join an airline · TEPHRA"
    t = r["text"]
    assert "Join Ring of Fire Charter on TEPHRA" in t
    assert "Airline Ring of Fire Charter (RFB)" in t
    assert "Role Dispatcher" in t
    assert "Invited by Ana Ops" in t
    assert "For d•••@rfb.example" in t
    seen = r["seen"]
    infos = dict(r["infos"])
    # "Emails are not checked" (SPEC hosted §5.1) on screen; the rest behind its (i)
    assert (
        "Anyone with this link can join as Dispatcher until 20 Oct, 14:05 UTC. Emails are not "
        "checked." in seen
    )
    assert "cannot check that the email is yours" in infos["unchecked emails"]
    # what the role does, behind the role's (i); the decision-support tick's words behind its own
    assert infos["the role"].startswith("Dispatchers decide TEPHRA's drafts at the Desk")
    assert "Dispatchers decide" not in seen
    assert infos["decision support"] == "A person decides, and nothing is sent to an aircraft."
    # said once: the card's "For" names the email, the label the password rule (sign-up's words)
    assert "The invite is for" not in seen
    assert "Password · 12+ characters" in seen
    assert "12 characters or more" not in seen
    assert "Members see it" not in seen
    assert "2 to 32 characters" not in seen
    # the not-built email reset is said on the recovery card (and the sign-in tab's Recover page)
    assert "Password reset by email is not built" not in t
    assert r["tabs"] == [["New to TEPHRA", "true"], ["I have an account", "false"]]
    assert r["calls"] == [
        {"method": "POST", "path": "/api/hosted/invites/lookup", "body": {"token": TOKEN}}
    ]


def test_a_gone_or_missing_link_says_ask_for_a_new_one(tmp_path: Path) -> None:
    gone = _page(tmp_path, lookup={"status": 404, "body": {"error": "invite_gone"}})
    assert (
        "This invite link is used, revoked or expired. Ask your ops manager for a new one."
        in gone["text"]
    )
    assert not gone["buttons"]
    bad = _page(tmp_path, token="")
    assert "This invite link is used, revoked or expired." in bad["text"]
    assert bad["calls"] == []
    none = _page(tmp_path, token=None)
    assert "This page needs the whole invite link" in none["text"]
    assert none["calls"] == []


JOIN_FILL = [
    ["#jn-email", "Dee@RFB.example "],
    ["#jn-pw", "a long password 1"],
    ["#jn-name", " Dee  Disp "],
    ["#jn-ack", True],
]
JOIN = "POST /api/hosted/invites/join"


def test_a_new_account_joins_and_lands_on_the_airline(tmp_path: Path) -> None:
    ok = {"status": 200, "body": fixture("workspace", "session-member-only")}
    r = _page(tmp_path, fill=JOIN_FILL, submit=True, routes={JOIN: ok})
    assert r["calls"][1] == {
        "method": "POST",
        "path": "/api/hosted/invites/join",
        "body": {
            "token": TOKEN,
            "email": "dee@rfb.example",
            "password": "a long password 1",
            "display_name": "Dee Disp",
            "acknowledge": True,
        },
    }
    assert r["assigned"] == "/a/RFB/"
    unticked = _page(tmp_path, fill=JOIN_FILL[:3], submit=True, routes={JOIN: ok})
    assert len(unticked["calls"]) == 1
    assert unticked["errors"] == ["Tick to continue"]  # sign-up's terse words


def test_a_new_accounts_recovery_code_is_shown_once_before_the_airline_opens(
    tmp_path: Path,
) -> None:
    """``POST /api/hosted/invites/join`` answers ``Joined``: the session plus the new login's
    recovery code (TEPHRA sends no email, so it is the only way back in after a lost password)."""
    joined = {**fixture("workspace", "session-member-only"), "recovery_code": "K7QW-M2PX-9TRB-4HZD"}
    r = _page(tmp_path, fill=JOIN_FILL, submit=True, routes={JOIN: {"status": 200, "body": joined}})
    assert r["assigned"] is None
    t = r["text"]
    assert "Save your recovery code" in t
    assert "K7QW-M2PX-9TRB-4HZD" in t
    assert "You joined Ring of Fire Charter. Shown once: your way back if you forget your" in t
    assert "Email reset: not built" in t
    assert "Open Ring of Fire Charter" in t
    assert "Join Ring of Fire Charter on TEPHRA" not in t  # the form is gone with the password


def test_join_refusals_are_said_in_place(tmp_path: Path) -> None:
    taken = _page(
        tmp_path,
        fill=JOIN_FILL,
        submit=True,
        routes={JOIN: {"status": 409, "body": {"error": "email_taken"}}},
    )
    assert taken["tabs"] == [["New to TEPHRA", "false"], ["I have an account", "true"]]
    assert "This email has an account already. Sign in with it, then accept." in taken["errors"]
    wrong = _page(
        tmp_path,
        fill=JOIN_FILL,
        submit=True,
        routes={JOIN: {"status": 403, "body": {"error": "wrong_email"}}},
    )
    assert "This invite is for d•••@rfb.example. Use that email." in wrong["errors"]
    name = _page(
        tmp_path,
        fill=JOIN_FILL,
        submit=True,
        routes={JOIN: {"status": 409, "body": {"error": "name_taken"}}},
    )
    assert "Another member uses this name. Choose another." in name["errors"]
    gone = _page(
        tmp_path,
        fill=JOIN_FILL,
        submit=True,
        routes={JOIN: {"status": 404, "body": {"error": "invite_gone"}}},
    )
    assert "This invite link is used, revoked or expired." in gone["text"]


ACCEPT = "POST /api/hosted/invites/accept"


def test_a_signed_in_account_accepts_with_its_name(tmp_path: Path) -> None:
    ok = {"status": 200, "body": fixture("workspace", "membership-dispatcher")}
    r = _page(
        tmp_path, signed_in=True, fill=[["#jn-name", "Dee Disp"]], submit=True, routes={ACCEPT: ok}
    )
    assert "Accept the invite" in r["text"]
    assert "Accept and open Ring of Fire Charter" in r["buttons"]
    assert r["calls"][1] == {
        "method": "POST",
        "path": "/api/hosted/invites/accept",
        "body": {"token": TOKEN, "display_name": "Dee Disp"},
    }
    assert r["assigned"] == "/a/RFB/"
    wrong = _page(
        tmp_path,
        signed_in=True,
        fill=[["#jn-name", "Dee Disp"]],
        submit=True,
        routes={ACCEPT: {"status": 403, "body": {"error": "wrong_email"}}},
    )
    assert wrong["errors"] == [
        "This invite is for d•••@rfb.example. Sign out, then sign in with that email."
    ]
    assert wrong["assigned"] is None


def test_signed_in_the_page_says_as_whom_and_starts_from_the_name_in_use(
    tmp_path: Path,
) -> None:
    invite = fixture("workspace", "invite-dispatcher") | {
        "you": {"email_hint": "d•••@rfb.example", "for_you": True, "name": "Dee Disp"}
    }
    r = _page(tmp_path, signed_in=True, lookup={"status": 200, "body": invite})
    assert "You are signed in as d•••@rfb.example. Not the account this invite is for?" in r["text"]
    assert "Accept and open Ring of Fire Charter" in r["buttons"]
    name = run_node(
        tmp_path,
        PAGE.replace("out({", 'out({ name: m.querySelector("#jn-name").value,'),
        {"token": TOKEN, "signedIn": True, "routes": {LOOKUP: {"status": 200, "body": invite}}},
    )
    assert name["name"] == "Dee Disp"


def test_signed_in_with_another_email_is_told_before_anything_is_tried(tmp_path: Path) -> None:
    invite = fixture("workspace", "invite-dispatcher") | {
        "you": {"email_hint": "s•••@nowhere.example", "for_you": False, "name": None}
    }
    r = _page(tmp_path, signed_in=True, lookup={"status": 200, "body": invite})
    assert r["errors"] == [
        "You are signed in as s•••@nowhere.example. This invite is for d•••@rfb.example. Sign "
        "out, then sign in with that email."
    ]
    assert [b for b in r["buttons"] if b] == ["Sign out"]  # the (i) buttons have no words


SIGNIN = """
const { renderJoin } = await import("./workspace/join.js");
setRoutes(DATA.routes);
const m = main();
await renderJoin(m, { token: DATA.token, signedIn: false });
m.querySelector("#jn-tab-signin").click(); await tick();
m.querySelector("#jn-si-email").value = "dee@rfb.example";
m.querySelector("#jn-si-pw").value = "a long password 1";
m.querySelector('button[type="submit"]').click(); await tick(); await tick();
out({ text: text(m), calls: CALLS.map((c) => c.path) });
"""


def test_an_existing_account_signs_in_here_then_accepts(tmp_path: Path) -> None:
    routes = {
        LOOKUP: {"status": 200, "body": fixture("workspace", "invite-dispatcher")},
        "POST /api/airline/sign-in": {
            "status": 200,
            "body": fixture("workspace", "session-member-only"),
        },
    }
    r = run_node(tmp_path, SIGNIN, {"token": TOKEN, "routes": routes})
    # signed in, the invite is read again: it then says who is signed in
    assert r["calls"] == [
        "/api/hosted/invites/lookup",
        "/api/airline/sign-in",
        "/api/hosted/invites/lookup",
    ]
    assert "Accept the invite" in r["text"]


LEAVE = """
const { renderJoin } = await import("./workspace/join.js");
setRoutes(DATA.routes);
const m = main();
await renderJoin(m, { token: DATA.token, signedIn: false });
const shown = () => m.querySelectorAll(".err:not([hidden])").map(text);
const email = m.querySelector("#jn-email");
const pw = m.querySelector("#jn-pw");
email.dispatchEvent(new Event("blur"));
const untouched = shown();
email.value = "dee@rfb";
email.dispatchEvent(new Event("input"));
email.dispatchEvent(new Event("blur"));
pw.value = "short"; pw.dispatchEvent(new Event("input")); pw.dispatchEvent(new Event("blur"));
const left = shown();
email.value = "dee@rfb.example"; email.dispatchEvent(new Event("input"));
const fixed = shown();
m.querySelector('button[type="submit"]').click(); await tick();
out({ untouched, left, fixed, sent: shown(), focus: document.activeElement?.id });
"""


def test_join_errors_wait_until_a_typed_field_is_left_or_the_form_is_sent(tmp_path: Path) -> None:
    """The owner's form rule (17 Oct 2026), as on sign-up: terse words, shown after blur or
    submit, never before; once shown they follow the typing."""
    routes = {LOOKUP: {"status": 200, "body": fixture("workspace", "invite-dispatcher")}}
    r = run_node(tmp_path, LEAVE, {"token": TOKEN, "routes": routes})
    assert r["untouched"] == []
    assert r["left"] == ["Not an email", "12+ characters"]
    assert r["fixed"] == ["12+ characters"]
    assert r["sent"] == ["12+ characters", "Required", "Tick to continue"]
    assert r["focus"] == "jn-pw"


def test_the_token_goes_only_into_json_bodies() -> None:
    join = (WEB / "workspace" / "join.js").read_text(encoding="utf-8")
    for line in join.splitlines():
        if "call(" in line and "S.token" in line:
            assert "body: {" in line, line
            assert "token: S.token" in line, line
    assert "localStorage" not in join
    assert "sessionStorage" not in join
    assert "history.replaceState" not in join or 'hist.replaceState(null, "", "/join")' in join


NEXT = """
const { safeNext } = await import("./onboard/pages.js");
out(DATA.cases.map((c) => safeNext(c)));
"""


def test_sign_in_follows_next_to_hosted_pages_only(tmp_path: Path) -> None:
    cases = {
        "/a/RFB/": "/a/RFB/",
        "/a/RFB": "/a/RFB",
        "/a/RFB/desk": "/a/RFB/desk",
        "/a/RFB/settings/people": "/a/RFB/settings/people",
        "/a/RFB/docs/SRA-1": "/a/RFB/docs/SRA-1",
        "/join": "/join",
        "/a/rfb/": "/workspace",
        "/a/RFBX/": "/workspace",
        "/a/RFB//evil.example": "/workspace",
        "/a/RFB/../admin": "/workspace",
        "/a/RFB/%2e%2e/x": "/workspace",
        "//a/RFB/": "/workspace",
        "/join#token": "/workspace",
        "/admin": "/workspace",
    }
    assert run_node(tmp_path, NEXT, {"cases": list(cases)}) == list(cases.values())
