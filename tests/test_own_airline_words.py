"""An airline's own TEPHRA serves the same pages as the demo (OWNFLIGHTS R5, 16 Oct 2026): the
Wall, the Guide and the Desk name the airline ``/api/state`` gives (``state.airline``) and say
"fictional" only for the demo's Ring of Fire Air. Source checks; the welcome dialog's words run
under Node in test_welcome.py.
"""

from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "tephra" / "web"


def _src(rel: str) -> str:
    return (WEB / rel).read_text(encoding="utf-8")


def test_one_airline_setter_read_from_the_state() -> None:
    util = _src("wall/util.js")
    assert "export function setAirline(a)" in util
    assert 'let AIRLINE = { code: "RFA", name: "Ring of Fire Air", fictional: true };' in util
    wall = _src("wall.js")
    # the first load and every state event
    assert wall.count("airlineWords(data.state.airline);") == 1
    assert wall.count("airlineWords(s.airline);") == 1
    assert "setAirline(state?.airline);" in _src("guide.js")


def test_the_wall_s_flight_words_follow_the_airline() -> None:
    for rel, gone in (
        ("wall/story.js", ['"RFA flight"', '"RFA flights"', "RFA (fictional) flight"]),
        (
            "wall/controls.js",
            ['"RFA flight in or heading in"', '"Other aircraft (not RFA)"', "Amber planes = RFA"],
        ),
        ("wall/panels.js", ["${flights.length} RFA ", "No RFA flight is projected"]),
        ("wall/pick.js", ["${n} RFA "]),
    ):
        source = _src(rel)
        for words in gone:
            assert words not in source, (rel, words)
        assert "airline()" in source, rel


def test_the_fictional_label_stays_for_the_demo() -> None:
    controls = _src("wall/controls.js")
    assert "Ring of Fire Air (RFA) is a fictional airline." in controls
    assert "state?.airline?.fictional === false" in controls
    # the demo's status line: "RFA" with its info button (wall/panels.js renderStatusLine)
    assert "Ring of Fire Air (RFA) is a fictional airline" in _src("wall/panels.js")
    assert 'id="stl-rfa"' in _src("index.html")
    docs = _src("desk/docs.js")
    assert "'DRAFT · not an approved document · fictional airline'" in docs
    assert "app.state?.airline?.fictional === false" in docs
    assert "/FICTIONAL/.test(l)" in _src("desk/docview.js")


def test_the_handover_banner_and_the_document_footer_follow_the_airline() -> None:
    """Batch 2 honesty finding 2: the handover banner says FICTIONAL AIRLINE only for the demo's
    briefs (HandoverBrief.fictional_airline); a document's labels carry it otherwise."""
    view = _src("desk/docview.js")
    assert "b.fictional_airline === false ? '' : ' - FICTIONAL AIRLINE'" in view
    assert "'DRAFT HANDOVER BRIEF - DECISION SUPPORT ONLY - FICTIONAL AIRLINE'" not in view
    # the document page's footer no longer repeats "decision support only" and the fictional
    # airline (owner, 17 Oct: "don't put this everywhere"): the document's own labels say them
    # (regdocs/common.py document_labels, the brief's banner above), and docview.js draws them
    page = _src("doc.html")
    assert "docfoot-fictional" not in page
    assert "decision support only" not in page.split('class="docfoot"')[1]
    assert "...(doc.labels || [])" in view
