"""What the existing pages say inside an airline's space (/a/<ICAO>/), after the hosted UX and
honesty checks: no second "Live" beside the SHADOW chip, the airline's own words from the first
paint, the acceptance qualifier kept, an instruction only for who can follow it, and each fact
once. Helpers run under Node; the wiring is read from the sources."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1] / "tephra" / "web"
NODE = shutil.which("node")


def _src(rel: str) -> str:
    return (WEB / rel).read_text(encoding="utf-8")


def _node(script: str) -> object:
    assert NODE is not None
    done = subprocess.run(
        [NODE, "--input-type=module", "-e", script],
        cwd=WEB,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return json.loads(done.stdout)


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_other_aircraft_on_an_airline_s_map_are_its_own_flights() -> None:
    """D16: an airline's map draws its own fleet only, so the key says "Other RFB flight"."""
    words = _node(
        """
globalThis.location = { pathname: process.argv[1] || "/a/RFB/" };
const u = await import("./wall/util.js");
u.setAirline({ code: "RFB", name: "Ring of Fire Charter", fictional: false });
const hosted = u.otherAircraft();
globalThis.location = { pathname: "/demo" };
u.setAirline({ code: "RFA", name: "Ring of Fire Air", fictional: true });
console.log(JSON.stringify([hosted, u.otherAircraft()]));
"""
    )
    assert words == ["Other RFB flight", "Other aircraft (not RFA)"]


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_a_flight_on_a_desk_card_is_named_once() -> None:
    words = _node(
        """
const f = await import("./desk/format.js");
console.log(JSON.stringify([
  f.flightWho({ proxy_flight: "RFB414", callsign: "RFB414" }),
  f.flightWho({ proxy_flight: "RFA1225", callsign: "GIA417" }),
]));
"""
    )
    assert words == ["RFB414", "RFA1225 · GIA417"]
    for rel in ("desk/queue.js", "desk/review.js", "desk/crew.js"):
        assert "[adv.proxy_flight, adv.callsign].filter(Boolean)" not in _src(rel), rel


def test_the_airline_s_state_chip_is_the_only_live_word_in_its_header() -> None:
    panels = _src("wall/panels.js")
    assert "badge.hidden = replay || Boolean(TENANT);" in panels
    # the time bar names the wall clock under an airline, never a second "Live"
    assert 'TENANT ? el("span", { class: "tl__mode", text: utcTime(D.now) })' in panels


def test_the_status_line_keeps_the_acceptance_qualifier() -> None:
    assert '"accepted under your SRA (recorded by the airline)"' in _src("wall/panels.js")


def test_the_desk_record_gives_an_airline_its_own_policy_label() -> None:
    review = _src("desk/review.js")
    assert "fine(policyNote(adv))" in review
    assert "if (!TENANT) return 'Illustrative values, not an airline SRA" in review
    assert "tenantHeader()?.policy" in review


def test_setup_words_name_the_airline_and_only_an_ops_manager_is_sent_to_go_live() -> None:
    wall = _src("wall.js")
    assert "`${TENANT} flights in or heading in`" in wall
    assert 'h.you?.role === "ops_manager"' in wall
    assert "ops manager starts it from the workspace." in wall
    desk = _src("desk.js")
    assert "h.you?.role === 'ops_manager'" in desk
    assert "ops manager starts it from the workspace." in desk


def test_nothing_says_connecting_while_nothing_runs_for_the_airline() -> None:
    wall = _src("wall.js")
    assert "notRunning(extra.waiting);" in wall
    assert 'notRunning("No access")' in wall
    desk = _src("desk.js")
    assert "runningChips(h.state === 'shadow' || h.state === 'live');" in desk


def test_the_space_s_pages_describe_the_space_not_the_demo() -> None:
    nav = _src("tenant-nav.js")
    assert "a private airline space, behind sign-in. Decision support only." in nav
    assert 'meta[name="description"], meta[property="og:description"]' in nav


def test_the_header_menus_open_and_close_from_the_keyboard() -> None:
    nav = _src("tenant-nav.js")
    assert "setOpen(menu.hidden, { focus: e.detail === 0 })" in nav
    assert 'e.key === "Escape" && !menu.hidden' in nav


def test_the_desk_header_stays_two_rows_on_a_phone() -> None:
    css = _src("tenant.css")
    assert ".is-tenant .dhead__row.ah #budget-chip > :not(svg)" in css
    assert '.conn[data-conn="live"] > span' in css


def test_a_page_drawn_again_after_an_action_keeps_focus() -> None:
    hosted = _src("hosted.js")
    assert "export function refocus(host, prefer = null)" in hosted
    assert "else if (after) refocus(after.host, after.prefer);" in hosted
    for rel, target in (
        ("hosted/feeds.js", '"#keys-h"'),
        ("hosted/people.js", '"#mem-h"'),
        ("hosted/policy.js", '"#v-h"'),
        ("hosted/assistant.js", '"#mod-h"'),
    ):
        assert f"refocus(host, {target})" in _src(rel), rel
    assert "focusRow(row.icao);" in _src("admin.js")
