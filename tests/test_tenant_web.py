"""A hosted airline's own space on the existing pages (SPEC-FINAL 5.2, 5.9): ``tephra/web/base.js``
maps every API call and in-app link into /a/<ICAO>/, the map, Desk and document scripts keep no
root ``/api/`` literal and no root Desk link, every root-relative link of the three page shells has
its tenant target, the shadow words equal Python's, and the airline header (``tenant-nav.js``)
gives each state its shape, word and title. The JavaScript runs under Node (skipped without it);
the rest is a static read of the sources."""

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

# The scripts whose API calls and in-app links moved behind base.js. The Desk keeps its path tables
# (older tests pin them): its one fetch wrapper and its stream ask them of the space (tenantPath).
CONVERTED = [WEB / "wall.js", WEB / "doc.js", *sorted((WEB / "wall").glob("*.js"))]
DESK = [WEB / "desk.js", *sorted((WEB / "desk").glob("*.js"))]
STRING_API = re.compile(r"""["'`]/api/""")
DESK_LINK = re.compile(r"""href:\s*["'`]/desk""")
COMMENT = re.compile(r"^\s*(//|/\*|\*)")
# Root paths a hosted airline's pages never reach, pinned by older tests: the /assistant board's
# Desk button (the board is the demo's) and the demo-only deep link from that page into Details.
ROOT_ONLY = ('el("a", { class: "flow-cta", href: "/desk",', "location.assign(`/demo#details-")
STRING = re.compile(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`")

# Every root-relative <a href> in the three shells and where it points under /a/RFB/.
SHELL_LINKS = {
    "/": "/",
    "/demo": "/a/RFB/",
    "/desk": "/a/RFB/desk",
    "/onboard": "/onboard",
    "/guide": "/guide",
    "/guide#policy": "/guide#policy",
    "/guide#about-credits": "/guide#about-credits",
    "/guide#read": "/guide#read",
    "/assistant": "/assistant",
    "/privacy": "/privacy",
}

RUNNER = """
import { readFileSync } from "node:fs";
const B = await import("./base.js");
const N = await import("./tenant-nav.js");
const input = JSON.parse(readFileSync("input.json", "utf8"));
const out = { map: {}, apis: {}, tenantOf: {}, chips: {}, alarms: {}, titles: {}, same: {} };
const rfb = B.baseFor("/a/RFB/settings/people");
const root = B.baseFor("/demo");
for (const p of input.pages) out.map[p] = [rfb.page(p), root.page(p)];
for (const p of input.apis) out.apis[p] = [rfb.api(p), root.api(p)];
for (const p of input.paths) out.tenantOf[p] = B.tenantOf(p);
out.shadow = B.SHADOW_WORDS;
out.module = [B.TENANT, B.PAGE_BASE, B.api("/state"), B.page("/desk")];
const drafts = "/api/desk/advisories?status=DRAFT&limit=100";
const asked = ["/api/state", drafts, "/static/icons.svg", "/apix"];
out.paths = asked.map((p) => [rfb.tenantPath(p), root.tenantPath(p)]);
for (const [name, h] of Object.entries(input.headers)) {
  out.chips[name] = N.stateChip(h, Date.parse(h.wall_now));
  out.alarms[name] = N.alarmLines(h);
  out.titles[name] = [N.titleFor(h, "Map"), N.titleFor(h, "Desk")];
}
for (const [icao, path, section] of input.same) {
  out.same[`${icao}${path}|${section}`] = N.sameSection(icao, path, section);
}
out.names = input.names.map((n) => N.personName(n));
out.footer = N.footerWords(input.headers["header-shadow"]);
process.stdout.write(JSON.stringify(out));
"""


def _shell_hrefs(name: str) -> list[str]:
    text = (WEB / name).read_text("utf-8")
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    return re.findall(r"<a\b[^>]*\bhref=\"(/[^\"]*)\"", text)


def _strings(path: Path) -> list[str]:
    return [line for line in path.read_text("utf-8").splitlines() if not COMMENT.match(line)]


def test_no_root_api_literal_or_desk_link_left() -> None:
    for path in CONVERTED:
        for line in _strings(path):
            if any(ok in line for ok in ROOT_ONLY):
                continue
            assert not STRING_API.search(line), (path.name, line.strip()[:120])
            assert not DESK_LINK.search(line), (path.name, line.strip()[:120])


def test_every_desk_request_is_asked_of_the_space() -> None:
    fetches = [
        (p.name, line.strip())
        for p in DESK
        for line in _strings(p)
        if re.search(r"\bfetch\(|new EventSource\(", line)
    ]
    assert sorted(fetches) == sorted(
        [
            ("api.js", "response = await fetch(tenantPath(path), init);"),
            ("dom.js", "const res = await fetch(SPRITE, { cache: 'force-cache' });"),
            ("desk.js", "const source = new EventSource(tenantPath(PATHS.events));"),
        ]
    )
    for path in DESK:
        for line in _strings(path):
            assert not DESK_LINK.search(line), (path.name, line.strip()[:120])


def test_every_shell_link_has_its_tenant_target() -> None:
    hrefs = {h for name in ("index.html", "desk.html", "doc.html") for h in _shell_hrefs(name)}
    assert hrefs <= set(SHELL_LINKS), sorted(hrefs - set(SHELL_LINKS))


def test_the_shells_are_not_forked() -> None:
    """The demo's shells only preload the new modules: the space's stylesheet comes from
    tenant-nav.js, and the pages mount the header themselves."""
    for name in ("index.html", "desk.html", "doc.html"):
        text = (WEB / name).read_text("utf-8")
        assert "tenant.css" not in text, name
        assert re.findall(r"<[^>]*tenant-nav\.js[^>]*>", text) == [
            '<link rel="modulepreload" href="/static/tenant-nav.js">'
        ], name
    assert 'for (const css of ["/static/info.css", "/static/tenant.css"])' in (
        WEB / "tenant-nav.js"
    ).read_text("utf-8")


@pytest.fixture(scope="module")
def ran(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    if NODE is None:
        pytest.skip("Node is not installed")
    root = tmp_path_factory.mktemp("tenant")
    for path in WEB.rglob("*.js"):
        dest = root / path.relative_to(WEB)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(path, dest)
    (root / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    (root / "run.mjs").write_text(RUNNER, encoding="utf-8")
    headers = {p.stem: json.loads(p.read_text("utf-8")) for p in FIX.glob("header-*.json")}
    data = {
        "pages": [
            *SHELL_LINKS,
            "/desk#review/adv_0123456789ab",
            "/desk#crew-report",
            "/demo#details-ai",
            "/demo#track-record",
            "/docs/DOC-0123456789ab",
            "/desktop",
            "/privacy",
            "https://example.org/desk",
        ],
        "apis": ["/state", "/tenant/header", "/desk/advisories?status=DRAFT&limit=100"],
        "paths": ["/a/RFB/", "/a/RFB", "/a/RFB/desk", "/a/rfb/", "/a/RFBX/", "/demo", "/a/"],
        "headers": headers,
        "same": [
            ["RFC", "/a/RFB/settings/people", "settings"],
            ["RFC", "/a/RFB/", "map"],
            ["RFC", "/a/RFB/docs/DOC-0123456789ab", "doc"],
        ],
        "names": [
            "desk:Ana Ops#MB-1a2b3c4d5e",
            "Ana Ops#MB-1a2b3c4d5e",
            "operator:M. Tan#0a1b2c3d",
            "Dee Disp",
        ],
    }
    (root / "input.json").write_text(json.dumps(data), encoding="utf-8")
    result = subprocess.run(
        [str(NODE), "run.mjs"], cwd=root, capture_output=True, text=True, timeout=60, check=True
    )
    return json.loads(result.stdout)


def test_base_maps_pages_into_the_space(ran: dict[str, Any]) -> None:
    m = ran["map"]
    for href, target in SHELL_LINKS.items():
        assert m[href] == [target, href], href
    assert m["/desk#review/adv_0123456789ab"][0] == "/a/RFB/desk#review/adv_0123456789ab"
    assert m["/desk#crew-report"][0] == "/a/RFB/desk#crew-report"
    assert m["/demo#details-ai"][0] == "/a/RFB/#details-ai"
    assert m["/docs/DOC-0123456789ab"][0] == "/a/RFB/docs/DOC-0123456789ab"
    for unchanged in ("/desktop", "/privacy", "https://example.org/desk"):
        assert m[unchanged] == [unchanged, unchanged]
    # outside a space nothing changes
    assert all(root == href for href, (_, root) in m.items())


def test_base_maps_the_api(ran: dict[str, Any]) -> None:
    a = ran["apis"]
    assert a["/state"] == ["/a/RFB/api/state", "/api/state"]
    assert a["/tenant/header"] == ["/a/RFB/api/tenant/header", "/api/tenant/header"]
    assert (
        a["/desk/advisories?status=DRAFT&limit=100"][0]
        == "/a/RFB/api/desk/advisories?status=DRAFT&limit=100"
    )
    assert ran["tenantOf"] == {
        "/a/RFB/": "RFB",
        "/a/RFB": "RFB",
        "/a/RFB/desk": "RFB",
        "/a/rfb/": None,
        "/a/RFBX/": None,
        "/demo": None,
        "/a/": None,
    }
    assert ran["paths"] == [
        ["/a/RFB/api/state", "/api/state"],
        [
            "/a/RFB/api/desk/advisories?status=DRAFT&limit=100",
            "/api/desk/advisories?status=DRAFT&limit=100",
        ],
        ["/static/icons.svg", "/static/icons.svg"],
        ["/apix", "/apix"],
    ]
    # under Node there is no location: the module reads as the demo
    assert ran["module"] == [None, "", "/api/state", "/desk"]


def test_shadow_words_equal_python(ran: dict[str, Any]) -> None:
    assert ran["shadow"] == SHADOW_WORDS


def test_state_chip_shapes_words_and_clock(ran: dict[str, Any]) -> None:
    c = ran["chips"]
    assert c["header-shadow"]["cls"] == "ah-state ah-state--shadow"
    assert (c["header-shadow"]["word"], c["header-shadow"]["clock"]) == ("SHADOW", "14:02Z")
    # the chip's (i) (no tooltip-only words): what a draft is, once; the decision-support sentence
    # is not page chrome (owner, 17 Oct: "don't put this everywhere")
    assert c["header-shadow"]["info"] == (
        "TEPHRA runs on your real flights; every draft says Shadow · not for use."
        " Nothing is sent to aircraft."
    )
    assert "Decision support only" not in c["header-shadow"]["info"]
    live = c["header-live"]
    assert (live["cls"], live["word"], live["clock"]) == (
        "ah-state ah-state--live",
        "LIVE",
        "14:02Z",
    )
    assert (
        live["info"]
        == "Switched to LIVE on 17 Oct, 11:30 UTC by Rin Ops. Nothing is sent to aircraft."
    )
    assert "#MB" not in live["info"]
    setup = c["header-setup"]
    assert (setup["cls"], setup["word"], setup["clock"]) == (
        "ah-state ah-state--setup",
        "Not started",
        "",
    )
    # Not started and suspended get no (i): the chip and the red line say it all
    assert setup["info"] is None
    susp = c["header-suspended"]
    assert (susp["cls"], susp["word"], susp["sub"], susp["clock"]) == (
        "ah-state ah-state--suspended",
        "SUSPENDED",
        "since",
        "13:40Z",
    )
    assert susp["info"] is None
    # S17: not updating is said in the chip, with the time of the last run, and no clock
    stale = c["header-stale"]
    assert stale["cls"] == "ah-state ah-state--shadow ah-state--stale"
    assert (stale["stale"], stale["clock"]) == ("not updating since 13:51Z", "")
    assert "13:51Z" not in stale["info"]  # said once, in the chip


def test_red_line_says_real_alarms_only(ran: dict[str, Any]) -> None:
    a = ran["alarms"]
    assert a["header-shadow"] == []
    assert a["header-live"] == []
    assert a["header-setup"] == []
    assert a["header-paused-airline"] == [
        {
            "kind": "paused",
            "lead": "Paused: Ring of Fire Charter's share of the site's free daily database"
            " allowance is used.",
            "text": "Resumes 00:00 Pacific (07:00 UTC).",
        }
    ]
    assert (
        a["header-paused-site"][0]["lead"]
        == "Paused: the shared site's free daily database allowance is used."
    )
    assert a["header-stale"] == [
        {
            "kind": "problem",
            "lead": "TEPHRA stopped for Ring of Fire Charter at 13:52Z: TimeoutError."
            " TEPHRA retries at 14:07Z.",
            "text": "",
        }
    ]
    (s,) = a["header-suspended"]
    assert s["lead"] == "TEPHRA staff suspended Ring of Fire Charter on 17 Oct, 13:40 UTC."
    assert (
        "Runs are stopped and pushes are refused. Your settings, people, keys and record are kept"
        in s["text"]
    )
    assert (
        "TEPHRA staff can delete your data from 24 Oct 2026; nothing deletes it on its own."
        in s["text"]
    )


def test_titles_switcher_names_and_footer(ran: dict[str, Any]) -> None:
    t = ran["titles"]
    assert t["header-shadow"] == ["SHADOW · Map · RFB · TEPHRA", "SHADOW · Desk · RFB · TEPHRA"]
    assert t["header-live"] == ["Map · RFC · TEPHRA", "Desk · RFC · TEPHRA"]
    assert t["header-suspended"][0] == "Map · RFB · TEPHRA"
    assert ran["same"] == {
        "RFC/a/RFB/settings/people|settings": "/a/RFC/settings/people",
        "RFC/a/RFB/|map": "/a/RFC/",
        "RFC/a/RFB/docs/DOC-0123456789ab|doc": "/a/RFC/desk",
    }
    assert ran["names"] == ["Ana Ops", "Ana Ops", "M. Tan", "Dee Disp"]
    # who sees the space; the decision-support sentence left the footer (owner, 17 Oct 2026:
    # "don't put this everywhere"; tests/test_footer_said_once.py)
    assert ran["footer"] == "Private to Ring of Fire Charter and TEPHRA staff."


def test_header_markup_and_aria() -> None:
    src = (WEB / "tenant-nav.js").read_text("utf-8")
    # the switcher and the account are menu buttons; the airlines are radio items, the current
    # one checked
    assert (
        '"aria-haspopup": "menu", "aria-expanded": "false", "aria-controls": "ah-air-menu"' in src
    )
    assert 'role: "menuitemradio", "aria-checked": here ? "true" : "false"' in src
    assert '"aria-controls": "ah-account-menu"' in src
    assert 'role: "menu", "aria-label": "Your airlines"' in src
    # the four pages, the current one marked; never hidden at any width (tenant.css)
    assert '"aria-current": s.key === section ? "page" : null' in src
    css = (WEB / "tenant.css").read_text("utf-8")
    assert ".tn-bar.ah .topnav.ah-nav a { display: inline-flex; }" in css
    assert "grid-template-columns: repeat(4, minmax(0, 1fr))" in css
    # the red line is an alert; the chip's words are its (i) (wall/info.js: a real button whose
    # words a screen reader hears on focus), kept beside the chip and only reworded on a redraw
    assert 'role: "alert", hidden: true' in src
    assert 'el("span", { class: "ah-statewrap" }, chip, stateInfo)' in src
    assert "if (c.info) setInfo(S.parts.stateInfo, c.info);" in src
    assert "title:" not in src.split("function chipNode")[1].split("\n}")[0]
    # sign-out signs out on every device (S26)
    assert '"Sign out on every device"' in src
    assert 'call("/api/airline/sign-out", { method: "POST", body: {} })' in src


def test_no_inline_style_or_script_in_the_space() -> None:
    html = (WEB / "hosted.html").read_text("utf-8")
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html)
    assert not re.search(r"\sstyle=|<style", html)
    assert '<meta name="robots" content="noindex">' in html
    for path in [
        WEB / "tenant-nav.js",
        WEB / "base.js",
        WEB / "hosted.js",
        WEB / "dryrun.js",
        *sorted((WEB / "hosted").glob("*.js")),
    ]:
        text = path.read_text("utf-8")
        assert "innerHTML" not in text, path.name
        assert not re.search(r"\{\s*style:", text), path.name
        # pages say "airline", never "tenant" (SPEC-FINAL 0.7); paths and ids may
        for literal in (lit for line in _strings(path) for lit in STRING.findall(line)):
            words = re.sub(r"\$\{[^}]*\}|/tenant/|tenant\.css|tenant-nav|is-tenant", "", literal)
            assert not re.search(r"\btenant\b", words, re.I), (path.name, literal[:80])


def test_the_desk_asks_an_airline_for_at_most_50_a_page() -> None:
    """An airline's API refuses ``limit`` above 50 (422 ``limit_too_large``, SPEC §4.1 step 7):
    every list the Desk asks under ``/a/<ICAO>/`` stays within it (the demo keeps its 100)."""
    src = (WEB / "desk" / "api.js").read_text("utf-8")
    assert "drafts: `/api/desk/advisories?status=DRAFT&limit=${TENANT ? 50 : 100}`" in src
    fixed = [int(n) for n in re.findall(r"limit=(\d+)", src)]
    assert fixed
    assert max(fixed) <= 50, fixed


def test_the_merge_verify_findings_stay_fixed_in_the_page_sources() -> None:
    """Merge verify, 17 Oct (static checks of the sources the hosted pages run):
    the Desk's AI (i) moves with its chip into the airline bar; Paperwork stamps SHADOW drafts on
    their rows; an airline's pages never name the demo's RFA (not even as hidden text); a form
    error inside a card keeps the invalid colour."""
    desk = (WEB / "desk.js").read_text(encoding="utf-8")
    assert "chips: [byId('ai-status'), byId('ask-btn'), byId('conn')]" in desk
    assert "for (const id of ['ai-status', 'conn'])" in desk
    docs = (WEB / "desk" / "docs.js").read_text(encoding="utf-8")
    assert "shadowStamp(d), el('span', { class: 'drow__t'" in docs
    assert "shadowStamp(handover), el('span', { class: 'drow__t'" in docs
    assert "no RFA flight" not in docs
    assert "const code = app.state?.airline?.code || 'RFA';" in docs
    assert '$("stl-rfa")?.remove();' in (WEB / "wall.js").read_text(encoding="utf-8")
    util = (WEB / "wall" / "util.js").read_text(encoding="utf-8")
    assert "if (SPACE_ICAO) AIRLINE = { code: SPACE_ICAO, name: SPACE_ICAO," in util
    css = (WEB / "product.css").read_text(encoding="utf-8")
    assert ".wcard .err { font-size: 13px; line-height: 1.4; color: var(--c-invalid); }" in css
    assert ".drow__what > .stamp--shadow" in (WEB / "tenant.css").read_text(encoding="utf-8")
