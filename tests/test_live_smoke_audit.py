"""scripts/live_smoke.sh on the audit chain: intact passes; not intact warns by default (the
stored record's state, which a deploy carrying a fix must not be blocked on) and fails with
EXPECT_AUDIT_INTACT=1 (once the record is repaired, a new fork fails the gate)."""

import json
import re

from test_scripts import _CLOUD_STATE, _OK_ROUTES, _line, _smoke_against

ROUTES = {**_OK_ROUTES, "/api/audit/verify": [200], "/api/evals": [404]}
FORKED = {
    "intact": False,
    "entries": 32300,
    "problems": ["fork at seq 5664-5668", "fork at seq 14370"],
}


def _body(chain: dict[str, object]) -> dict[str, bytes]:
    return {"/api/audit/verify": json.dumps(chain).encode()}


def _failed(out: str) -> int:
    """The run's failed checks (the fake answers 404 to the pages, which fail on their own)."""
    match = re.search(r"(\d+) failed check", out.splitlines()[-1])
    assert match is not None
    return int(match.group(1))


def test_an_intact_chain_passes() -> None:
    body = _body({"intact": True, "entries": 32300, "problems": []})
    out = _smoke_against(ROUTES, {}, _CLOUD_STATE, body)
    assert _line(out, "audit-chain") == "PASS audit-chain: intact, 32300 entries"


def test_a_chain_that_is_not_intact_warns_by_default() -> None:
    out = _smoke_against(ROUTES, {}, _CLOUD_STATE, _body(FORKED))
    assert _line(out, "audit-chain") == (
        "WARN audit-chain: not intact: fork at seq 5664-5668; fork at seq 14370"
    )
    assert _failed(out) == _failed(
        _smoke_against(ROUTES, {}, _CLOUD_STATE, _body({"intact": True}))
    )


def test_a_chain_that_is_not_intact_fails_when_expected_intact() -> None:
    out = _smoke_against(ROUTES, {"EXPECT_AUDIT_INTACT": "1"}, _CLOUD_STATE, _body(FORKED))
    assert _line(out, "audit-chain").startswith("FAIL audit-chain: not intact: fork at seq 5664")
    assert _failed(out) == _failed(_smoke_against(ROUTES, {}, _CLOUD_STATE, _body(FORKED))) + 1
