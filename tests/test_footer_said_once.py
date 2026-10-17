"""The decision-support sentence is not page chrome (owner, 17 Oct 2026, on the footer "Decision
support only. Not for operational use.": "don't put this everywhere"). No page's body says it in a
footer, a strip or a chip; it stays once where it matters: the demo's welcome dialog (its facts
line), About > Safety limits (wall/controls.js, the Guide's About), the sign-up checkbox's (i) and
Home's line ("a dispatcher approves"). Link previews (meta, og.svg), generated documents and their
labels (doc.html, desk/docview.js, the advisory headers) keep their own wording. Source checks."""

import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1] / "tephra" / "web"
PAGES = [
    "home.html",
    "guide.html",
    "privacy.html",
    "index.html",
    "desk.html",
    "onboard.html",
    "workspace.html",
]
PHRASE = re.compile(r"decision support only|not for operational use", re.I)
# where the sentence lives on purpose: the welcome facts, About, the sign-up checkbox, a document
HOMES = {"wall/welcome.js", "wall/controls.js", "onboard/review.js", "desk/docview.js"}


def _body(page: str) -> str:
    html = (WEB / page).read_text(encoding="utf-8")
    body = html.split("</head>", 1)[1]
    return re.sub(r"<!--.*?-->", "", body, flags=re.S)


@pytest.mark.parametrize("page", PAGES)
def test_no_page_s_chrome_carries_the_decision_support_sentence(page: str) -> None:
    body = _body(page)
    assert not PHRASE.search(body), (page, PHRASE.search(body))
    assert "a person approves every advisory, and nothing is sent" not in body.lower(), page
    for gone in ("home__honest", "pfoot__honest"):
        assert gone not in body, (page, gone)


def test_no_script_outside_its_homes_writes_it_into_a_page() -> None:
    hits = []
    for path in sorted(WEB.rglob("*.js")):
        rel = path.relative_to(WEB).as_posix()
        if rel in HOMES:
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("//"):
                continue
            if PHRASE.search(line):
                hits.append(f"{rel}:{n}")
    assert not hits, hits


def test_the_sentence_still_lives_in_the_welcome_facts_and_about() -> None:
    welcome = (WEB / "wall" / "welcome.js").read_text(encoding="utf-8")
    assert (
        'const SUPPORT = { lead: "Decision support only.", text: "A person approves every '
        'advisory, and nothing is sent to an aircraft." };' in welcome
    )
    controls = (WEB / "wall" / "controls.js").read_text(encoding="utf-8")
    about = controls[controls.index("export function aboutContent") :]
    assert 'el("li", { text: "Decision support only. Not for operational use." })' in about
    assert "Nothing is sent to an aircraft or any real system." in about
    # Home's line says who decides; the Guide's chips link to About's safety limits
    assert "<em>a dispatcher approves</em>" in (WEB / "home.html").read_text(encoding="utf-8")
    assert 'href="#what-is-real">What is real?</a>' in (WEB / "guide.html").read_text(
        encoding="utf-8"
    )
