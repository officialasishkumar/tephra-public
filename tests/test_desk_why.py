"""The Desk's "Why this advice" page (SPEC T21): a row under "Check before you approve" names the
four skills and opens a page that draws the chain ``wall/chain.js`` renders from
``GET /api/advisories/{id}/chain``; the fetch is kept per advisory and a chain the store does not
serve is said to be not on hand; the Record page links to Why; no quota word reaches the page;
every class the chain emits has a Desk rule. Static reads of the sources, like the inventory test.
"""

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "tephra" / "web"
SKILLS = ("Coordinator", "Plume reader", "Flight planner", "Drafter")
WHY = "Why ›"  # noqa: RUF001  the UI's own "Why" pin, angle quote included
# The quota words that never reach a main view (tests/test_ui_ai_quiet.py, copied: rule 3).
QUOTA_TEXT = re.compile(
    r"quota|used up|closed by google|free ai|next slot|\bspent\b|calls today|calls left"
    r"|share of calls|\bpacing\b|resets? (?:at|once)|reset was due|AI budget",
    re.I,
)
STRING = re.compile(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`")


def _read(rel: str) -> str:
    return (WEB / rel).read_text(encoding="utf-8")


def _function(source: str, name: str) -> str:
    start = source.index(f"function {name}(")
    nxt = re.search(r"\n(?:export )?(?:async )?function ", source[start + 1 :])
    return source[start : start + 1 + nxt.start()] if nxt else source[start:]


def _strings(source: str) -> list[str]:
    return [m.group(0)[1:-1] for m in STRING.finditer(source)]


# ---------------------------------------------------------------- the row and the page


def test_review_has_a_why_page_with_the_four_skills() -> None:
    review = _read("desk/review.js")
    assert "why: 'Why this advice'" in review
    row = "const WHY_SKILLS = 'Coordinator · Plume reader · Flight planner · Drafter';"
    assert row in review
    for skill in SKILLS:
        assert skill in review
    check = _function(review, "checkSection")
    assert "fact('Why', WHY_SKILLS, { page: 'why' })" in check
    assert "why: whyPage" in _function(review, "pageView")
    # the chain comes from the shared view, fetched by the Desk's own HTTP helper
    assert "import { chainView } from '../wall/chain.js';" in review
    assert "api(PATHS.chain(id))" in _function(review, "loadChain")
    assert "chainView(got.chain, { sit: null, mode: 'desk' })" in _function(review, "drawChain")
    assert "chain: (id) => `/api/advisories/${encodeURIComponent(id)}/chain`," in _read(
        "desk/api.js"
    )


def test_the_chain_is_kept_per_advisory_and_a_missing_one_is_said() -> None:
    review = _read("desk/review.js")
    # kept on the sheet, which openSheet makes anew for each advisory
    assert "chain: null," in _function(review, "openSheet")
    load = _function(review, "loadChain")
    assert "sheet.chain = { pending: true };" in load
    assert "if (!sheet || sheet.id !== id) return;" in load
    assert "isChain(res.data, id) ? { chain: res.data } : { missedAt: Date.now() }" in load
    assert "const WHY_MISSING = 'Why is not on hand for this draft.';" in review
    assert "text: WHY_MISSING" in _function(review, "drawChain")
    api = _read("desk/api.js")
    assert "export function isChain(v, id)" in api
    assert "v.advisory_id === id" in _function(api, "isChain")


def test_why_page_uses_no_quota_words() -> None:
    review = _read("desk/review.js")
    for name in ("whyPage", "drawChain", "loadChain"):
        for text in _strings(_function(review, name)):
            assert not QUOTA_TEXT.search(text), (name, text)
    for const in ("WHY_SKILLS", "WHY_MISSING", "WHY_OFFLINE"):
        line = next(ln for ln in review.splitlines() if ln.startswith(f"const {const} = "))
        assert not QUOTA_TEXT.search(line), line
    chain = _read("wall/chain.js")
    for text in _strings(chain):
        assert not QUOTA_TEXT.search(text), text
    # the chain's own code facts the page shows (SPEC T21 strings)
    assert "checks passed" in "".join(_strings(chain)) or '"check")} passed' in chain
    assert "every one from the facts given" in chain


def test_record_page_links_to_why() -> None:
    review = _read("desk/review.js")
    record = _function(review, "recordPage")
    assert "fact('Drafted by', draftedByValue(adv))" in record
    drafted = _function(review, "draftedByValue")
    assert "'data-page': 'why'" in drafted
    assert f"text: '{WHY}'" in drafted
    # every data-page button is routed by the sheet's click handler to goPage
    assert "goPage(target.dataset.page)" in _function(_read("desk/review.js"), "onSheetClick")


# ---------------------------------------------------------------- the Desk's styles


def test_every_chain_class_has_a_desk_rule() -> None:
    chain = _read("wall/chain.js")
    css = _read("desk.css")
    classes = set()
    for m in re.finditer(r'class: "([^"]+)"', chain):
        classes.update(m.group(1).split())
    classes.discard("link-btn")  # the Wall-only estimate link (mode: wall)
    classes.discard("dk-link")
    classes.discard("dk-foot")  # the Wall section's waiting line (chainSection)
    classes.discard("chain__wait")
    classes.discard("icon")
    missing = [c for c in classes if f".{c}" not in css]
    assert not missing, missing
    # the Wall's mark draws its icon with class "icon", the Desk's with "st": both sized
    assert ".ai-mark .icon {" in css
