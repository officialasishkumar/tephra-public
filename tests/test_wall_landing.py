"""The Wall's first minute (redesign A4, A10, A12, A13, B08): the assistant as the only gap is one
quiet line, the one filled call to action needs a draft to decide, the counts have one source,
Decisions rows open a read-only preview with the code's check line, the footer carries the audit
chain once, and the pinned honesty strings stay. A static check of the page sources.
"""

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "tephra" / "web"


def _read(rel: str) -> str:
    return (WEB / rel).read_text(encoding="utf-8")


def _function(source: str, name: str) -> str:
    start = source.index(f"function {name}(")
    pattern = r"\n(?:export )?(?:async )?function |\nconst [A-Za-z_]+ = \("
    nxt = re.search(pattern, source[start + 1 :])
    return source[start : start + 1 + nxt.start()] if nxt else source[start:]


STORY = _read("wall/story.js")
PANELS = _read("wall/panels.js")
DERIVE = _read("wall/derive.js")
CSS = _read("wall.css")
INDEX = _read("index.html")


def test_the_assistant_as_the_only_gap_is_one_quiet_line() -> None:
    model = _function(STORY, "storyModel")
    assert "if (draftsGap && !undone && !pf) {" in model
    assert "`${ASSISTANT} · paused · no advisory drafts for the ${nf}`" in model
    assert "`Waiting in line for ${ASSISTANT} · drafts for the ${nf} come next`" in model
    assert "`${block.word} · no advisory drafts for the ${nf}`" in model
    assert "quiet: true" in model
    # the caution box stays for a missing airport plan and must-do flights
    assert "} else if (draftsGap || undone || pf) {" in model
    notice = _function(STORY, "noticeNode")
    assert 'class: "notice notice--quiet"' in notice
    assert 'icon("ta-waiting", "icon notice__icon")' in notice
    assert ".notice--quiet {" in CSS
    assert "border: 0" in CSS.split(".notice--quiet {", 1)[1].split("\n", 1)[0]


def test_the_filled_call_to_action_needs_a_draft_to_decide() -> None:
    actions = _function(STORY, "renderActions")
    assert actions.count("primary = true") == 1
    assert "if (a.urgent) {" in actions.split("primary = true", 1)[0].rsplit("\n", 1)[1]
    assert 'class: "cta__sub"' in actions
    assert "to plan by hand" in actions
    assert '"Open the Desk →"' in actions
    assert ".cta__sub {" in CSS


def test_the_advisories_tile_is_drawn_only_with_something_to_count() -> None:
    model = _function(STORY, "storyModel")
    assert "if (a.drafts || a.decided || a.unknown) {" in model
    assert "if (n > 0 || a.drafts" not in model
    # the zero KPI stays in the DOM, hidden; its id is kept
    assert '$("kpi-drafts").closest(".kpi").hidden = !!D && s.draft_count === 0' in STORY
    for ident in ("kpi-exposed", "kpi-active", "kpi-drafts"):
        assert f'id="{ident}"' in INDEX, ident


def test_the_counts_have_one_source() -> None:
    assert "const counts = { aircraft: aircraft.length, exposed: mine.length" in DERIVE
    assert "counts, exposures:" in DERIVE
    model = _function(STORY, "storyModel")
    assert "const n = D.counts.exposed;" in model
    assert "D.counts.inside" in model
    assert "D.counts.heading" in model
    assert "sit.exposed_count" not in model
    # the story's "All volcanoes" line and the demo's slim strip read the same three numbers
    assert "export function allCounts(D) {" in STORY
    assert "const { active, exposed, drafts } = allCounts(D);" in _function(STORY, "renderAll")
    assert "const { active, exposed, drafts } = allCounts(D);" in _function(STORY, "renderRail")


def test_the_decider_keeps_a_name_and_a_role() -> None:
    assert 'replace(/^(desk|visitor):/, "")' in DERIVE
    assert "export const deciderRole = (a) =>" in DERIVE
    assert '"visitor" : "dispatcher"' in DERIVE
    rows = _function(PANELS, "decisionsSection")
    assert "by ${deciderName(a)} · ${deciderRole(a)}" in rows


def test_decisions_rows_open_a_read_only_preview() -> None:
    preview = _function(PANELS, "draftPreview")
    checked = (
        "Checked by code: action allowed · every number and place from the facts · no clock time"
        " · header, sources, times and hashes by code"
    )
    assert f'export const CHECKED = "{checked}";' in PANELS
    assert "text: CHECKED" in preview
    assert 'text: "Code only (NO MODEL)"' in preview
    assert "aiMark(a.model_id, MARK.written)" in preview
    assert "text: a.header" in preview
    assert "a.edited_body ?? a.body" in preview
    assert '"Decide on the Desk ›"' in preview  # noqa: RUF001  the UI's own chevron
    assert "a.fuel_line" in preview
    assert "a.policy_hash" in preview
    section = _function(PANELS, "decisionsSection")
    assert 'dkChip("Read-only preview · decide on the Desk"' in section
    assert 'el("details", { class: `dk-row dk-dec' in section
    assert "ui.details.vid === a.id : a.id === urgent?.id" in section
    assert "previewOpen.set(a.flight_id, d.open)" in section
    # the draft to decide first leads the waiting list, as on the Desk
    assert "draft.sort((a, b) => (b.id === urgent.id) - (a.id === urgent.id))" in section
    # the preview never reads as a decision made here
    assert "Approve" not in preview
    assert "Reject" not in preview


def test_the_footer_carries_the_audit_chain_once() -> None:
    assert PANELS.count("Audit chain intact") == 1
    words = _function(PANELS, "auditWords")
    assert "if (!head) return null;" in words
    assert '"Audit chain: checking"' in words
    assert '`Audit chain: ${plural(problems.length, "problem")}`' in words
    assert 'tone: "serious"' in words
    assert "not yet walked" in words
    status = _function(PANELS, "renderStatusLine")
    assert "auditWords(s.audit)" in status
    assert 'id="stl-audit"' in INDEX


def test_the_footer_keys_are_all_there_and_the_left_part_is_short() -> None:
    """The owner kept the full key row (15 Oct): each key is a visible button that runs it."""
    footer = INDEX[INDEX.index("<footer") : INDEX.index("</footer>")]
    for key in (
        "<kbd>?</kbd>Guide",
        "<kbd>W</kbd>How it works",
        "<kbd>E</kbd>Story",
        "<kbd>A</kbd>Assistant",
        "<kbd>[ ]</kbd>Volcano",
        "<kbd>F</kbd>Fit map",
        "<kbd>D</kbd>3D",
        "<kbd>S</kbd>Compare",
        "<kbd>Esc</kbd>Back",
    ):
        assert key in footer, key
    status = _function(PANELS, "renderStatusLine")
    assert "Flat map" not in status
    assert "official ash area" not in status
    # the fictional airline stays said in the status line's tooltip (CLAUDE.md, How the UI talks)
    assert (
        'class="stl__line honesty__airline" title="Ring of Fire Air (RFA) is a fictional airline'
        in footer
    )


def test_the_data_chip_says_all_working_and_leaves_off_feeds_out() -> None:
    chrome = _function(PANELS, "renderChrome")
    assert 'for (const k of ["ERROR", "STALE", "OK", "NEVER"])' in chrome
    assert "DISABLED" not in chrome.split("const by = {};", 1)[1].split("renderStatusLine", 1)[0]
    assert "allOk ? `all ${w}`" in chrome


def test_timeline_marks_of_one_kind_close_together_group() -> None:
    assert "export function groupMarks(events, span) {" in PANELS
    timeline = _function(PANELS, "renderTimeline")
    assert "groupMarks(list, 0.009 * (t1 - t0))" in timeline
    assert "tl__mark--group" in timeline
    assert 'class: "tl__count"' in timeline
    assert "${hhmmz(first.t)}–${hhmmz(last.t)}" in timeline  # noqa: RUF001  the UI's own en dash
    assert '"flights heading in"' in PANELS
    # "% played" leaves the bar's text and stays in the progress bar's aria-valuetext
    assert "text: utcTime(D.now), title:" in timeline
    assert '"aria-valuetext": `${pctText} of the recording' in timeline
    assert ".tl__mark--group" in CSS
    assert ".tl__count" in CSS


def test_the_plane_card_says_what_a_waiting_draft_proposes() -> None:
    pick = _read("wall/pick.js")
    assert 'adv.status === "DRAFT" ? ` · ${actionWords(adv)}`' in pick


def test_the_pinned_honesty_strings_stay() -> None:
    """The strings other tests grep (SPEC §1 rule 5) stay where they are: the trust line in the
    story, the fictional airline on the page, every Why link, the Desk's paste-notice id (a Desk
    file, read here and never edited by this task) and the REPLAY title prefix."""
    assert "never smaller than the official area" in STORY
    assert "RFA" in INDEX
    assert "fictional" in INDEX
    assert 'text: "Why ›"' in STORY  # noqa: RUF001  the UI's own chevron
    assert 'id="paste-notice"' in _read("desk.html")
    assert '`${replay ? "REPLAY - " : ""}TEPHRA ${' in PANELS


def test_the_case_strip_sits_under_the_eyebrow_and_reads_its_colour() -> None:
    assert 'import { caseStrip, caseOf, loadCases } from "./case.js";' in STORY
    eyebrow = _function(STORY, "eyebrow")
    assert "caseStory?.eyebrow ||" in eyebrow
    story = _function(STORY, "renderStory")
    assert "replay.volcano_ids.includes(sit.volcano_id)" in story
    assert "renderCase(caseStrip(caseStory, { mode: D?.mode, open: ui.caseOpen }))" in story
    assert ".case__what { display: none; }" in CSS.split('.story[data-fit="3"] .case__what', 1)[1]
