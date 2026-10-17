"""Every hosted fixture the web packages test against (``tests/fixtures/hosted/**``) is a
valid answer of its §4.3 model, with no key the model does not have: the pages' fixtures
cannot drift from what the API returns."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter

from tephra.airline.models import AirlineSessionView, AirlineView
from tephra.hosted.models import (
    AdminContact,
    AdminList,
    AssistantTab,
    FeedsView,
    GoLive,
    HostedMe,
    InviteView,
    LinkView,
    Membership,
    OperatorInviteView,
    OperatorView,
    PeopleTab,
    PolicyTab,
    RecordTab,
    TenantHeader,
)

FIXTURES = Path(__file__).parent / "fixtures" / "hosted"
MODELS: dict[str, Any] = {
    "admin-list-": AdminList,
    "contact-": AdminContact,
    "operator-invite": OperatorInviteView,
    "operator-link": LinkView,
    "ops-manager-link": LinkView,
    "operator-me": OperatorView,
    "operators": list[OperatorView],
    "header-": TenantHeader,
    "feeds": FeedsView,
    "policy": PolicyTab,
    "assistant": AssistantTab,
    "people": PeopleTab,
    "record": RecordTab,
    "golive-": GoLive,
    "hosted-me-": HostedMe,
    "invite-": InviteView,
    "membership-": Membership,
    "session-": AirlineSessionView,
    "airline-view-": AirlineView,
}
"""File name prefix -> the model of the answer it stands for."""


def model_for(path: Path) -> Any:
    matches = [prefix for prefix in MODELS if path.stem.startswith(prefix)]
    assert matches, f"{path.relative_to(FIXTURES)}: no model for this fixture name"
    return MODELS[max(matches, key=len)]


def drift(raw: Any, dumped: Any, where: str = "$") -> list[str]:
    """Keys in the fixture that the model's own answer does not have."""
    if isinstance(raw, dict) and isinstance(dumped, dict):
        found = [f"{where}.{key}" for key in raw if key not in dumped]
        for key in raw.keys() & dumped.keys():
            found += drift(raw[key], dumped[key], f"{where}.{key}")
        return found
    if isinstance(raw, list) and isinstance(dumped, list):
        return [
            p
            for i, (a, b) in enumerate(zip(raw, dumped, strict=False))
            for p in drift(a, b, f"{where}[{i}]")
        ]
    return []


FILES = sorted(FIXTURES.rglob("*.json"))


def test_there_are_fixtures_for_every_web_package() -> None:
    assert {path.parent.name for path in FILES} == {"admin", "tenant", "workspace"}


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(FIXTURES)))
def test_each_fixture_is_its_models_answer(path: Path) -> None:
    raw = json.loads(path.read_text())
    adapter = TypeAdapter(model_for(path))
    parsed = adapter.validate_python(raw)
    dumped = adapter.dump_python(parsed, mode="json")
    assert drift(raw, dumped) == []


def test_every_model_name_matches_a_fixture() -> None:
    used = {prefix for path in FILES for prefix in MODELS if path.stem.startswith(prefix)}
    assert set(MODELS) - used == set()
