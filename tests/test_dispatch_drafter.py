def test_a_null_cost_note_is_no_note() -> None:
    from tephra.agents.dispatch_drafter import _no_note_as_empty
    from tephra.models import DraftText

    assert _no_note_as_empty(DraftText(body="X", cost_note="null")).cost_note == ""
    assert _no_note_as_empty(DraftText(body="X", cost_note=" None ")).cost_note == ""
    assert (
        _no_note_as_empty(DraftText(body="X", cost_note="HOLD 20 MIN")).cost_note == "HOLD 20 MIN"
    )
    assert _no_note_as_empty(DraftText(body="X", cost_note="EXTRA FUEL: null KG")).cost_note == ""
    assert _no_note_as_empty(None) is None
