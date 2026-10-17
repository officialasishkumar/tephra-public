"""A hosted airline's runtime settings (SPEC §3.6 table): nothing from the environment, every
override, the site's secrets cleared, the airline's own key or none; the Assistant tab."""

from pathlib import Path

import pytest
from pydantic import SecretStr

from tephra.agents.budget import budget_view, used_tiers
from tephra.agents.llm import StubBackend
from tephra.agents.quota import QuotaLedger
from tephra.airline.models import Stamp
from tephra.config import HOSTED_FEATURES
from tephra.hosted import keys, settings_for
from tephra.hosted.models import HostedRefused, TenantAssistant, TenantRecord
from tephra.models import RunMode
from tephra.store import open_store
from tests.test_hosted_tenants import answers, site, wall

KEY = "AIzaTestKeyRFB0123456789abcdefghijKLMN"


def record(**update: object) -> TenantRecord:
    return TenantRecord(
        icao="RFB",
        airline_id="AL-0123456789ab",
        name="Ring of Fire Charter",
        iata="RB",
        version=4,
        state="shadow",
        state_since=wall(),
        region="java_bali",
        created=Stamp(by="Ana Ops#MB-1a2b3c4d5e", at=wall()),
        ops_managers=["MB-1a2b3c4d5e"],
        assistant=TenantAssistant(
            model="gemini-3.8-flash",
            model_lite="gemini-3.5-flash-lite",
            reserve_share=0.3,
            daily_limits={"gemini-3.5-flash-lite": 200},
        ),
    ).model_copy(update=update)


def test_every_override_and_no_secret_of_the_site(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = site(tmp_path, desk_pin="1234", task_token="t" * 40, key_secret="k" * 40)
    monkeypatch.setenv("TEPHRA_MODEL", "gemma-4-31b-it")
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaTheSitesOwnKey000000000000000000")
    monkeypatch.setenv("TEPHRA_DESK_PIN", "9999")
    monkeypatch.setenv("TEPHRA_FEATURES", "all")
    s = settings_for.tenant_settings(base, record(), answers(), SecretStr(KEY))
    assert s.mode is RunMode.LIVE
    assert (s.replay_case, s.replay_start, s.replay_end, s.auto_replay) == (None, None, None, False)
    assert s.local_scheduler is False
    assert s.llm == "gemini"
    assert s.gemini_api_key is not None
    assert s.gemini_api_key.get_secret_value() == KEY
    assert (s.model, s.model_lite) == ("gemini-3.8-flash", "gemini-3.5-flash-lite")
    assert (s.model_daily_budget, s.model_lite_daily_budget) == (None, 200)
    assert s.daily_budget("gemini-3.5-flash-lite") == 200
    assert s.ai_interactive_share == 0.3
    assert s.sqlite_path == tmp_path / "state" / "tenants" / "RFB.sqlite3"
    assert s.features == HOSTED_FEATURES
    assert s.visitor_access == "off"
    assert s.region == "java_bali"
    assert s.fleet_prefixes == frozenset({"RFB"})
    assert s.fleet_hexes == frozenset({"8a0412", "8a0413"})
    assert s.network_airports == frozenset({"WIII", "WADD"})
    assert (s.airline_name, s.airline_icao, s.airline_iata) == ("Ring of Fire Charter", "RFB", "RB")
    assert (s.airline_schedule, s.airline_fleet) == (None, None)
    assert (s.recovery_auto, s.science) == (False, False)
    assert s.tick_deadline_s == base.hosted_tick_budget_s - 15
    assert (s.desk_pin, s.task_token, s.key_secret) == (None, None, None)
    assert s.session_secret.get_secret_value() != base.session_secret.get_secret_value()
    assert (s.hosted_tenant, s.hosted_stage) == ("RFB", "shadow")
    assert s.airline.shadow is True
    assert s.airline.fictional is False
    assert KEY not in repr(s)


def test_live_is_not_shadow(tmp_path: Path) -> None:
    s = settings_for.tenant_settings(site(tmp_path), record(state="live"), answers(), None)
    assert s.airline.shadow is False
    assert s.gemini_api_key is None


@pytest.mark.parametrize(
    ("update", "reason"),
    [
        ({"assistant": None}, settings_for.NO_MODEL),
        ({}, settings_for.NO_KEY),
        ("unreadable", settings_for.UNREADABLE),
    ],
)
def test_without_a_readable_key_every_model_step_is_unavailable(
    tmp_path: Path, update: object, reason: str
) -> None:
    base = site(tmp_path)
    held = record()
    if update == "unreadable":
        other = site(tmp_path, key_secret="q" * 40)
        held = held.model_copy(
            update={"model_key": keys.seal("RFB", KEY, other, by="Ana Ops#MB-1", at=wall())}
        )
    elif isinstance(update, dict):
        held = held.model_copy(update=update)
    key, unavailable = settings_for.model_key(held, base)
    assert key is None
    assert unavailable == reason


def test_a_readable_key_is_the_airlines_own(tmp_path: Path) -> None:
    base = site(tmp_path)
    held = record(model_key=keys.seal("RFB", KEY, base, by="Ana Ops#MB-1", at=wall()))
    key, unavailable = settings_for.model_key(held, base)
    assert unavailable is None
    assert key is not None
    assert key.get_secret_value() == KEY


def test_a_suspended_airline_gets_no_runtime_settings(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="suspended"):
        settings_for.tenant_settings(site(tmp_path), record(state="suspended"), answers(), None)


def test_only_free_tier_text_models_with_limits_inside_them(tmp_path: Path) -> None:
    base = site(tmp_path)
    table = settings_for.hosted_models(base)
    assert "gemini-3.8-flash-lite-tts" not in table
    assert table["gemini-3.8-flash"] == 20
    for bad, code in (
        ({"model": "gemini-9-ultra"}, "model_not_offered"),
        ({"daily_limits": {"gemini-3.8-flash": 21}}, "daily_limit"),
        ({"daily_limits": {"gemini-3.8-flash": 0}}, "daily_limit"),
        ({"daily_limits": {"gemma-4-31b-it": 5}}, "daily_limit"),
    ):
        chosen = TenantAssistant(
            model="gemini-3.8-flash", model_lite="gemini-3.5-flash-lite"
        ).model_copy(update=bad)
        with pytest.raises(HostedRefused, match=code):
            settings_for.check_assistant(chosen, base)


def test_the_assistant_tab_says_on_or_unavailable_and_never_the_key(tmp_path: Path) -> None:
    base = site(tmp_path)
    tab = settings_for.assistant_tab(record(), base, budget=None)
    assert (tab.state, tab.reason) == ("unavailable", settings_for.NO_KEY)
    assert tab.key.set is False
    held = record(model_key=keys.seal("RFB", KEY, base, by="Ana Ops#MB-1", at=wall()))
    tab = settings_for.assistant_tab(held, base, budget=None)
    assert (tab.state, tab.reason) == ("on", None)
    assert (tab.key.set, tab.key.last4, tab.key.readable) == (True, "KLMN", True)
    assert KEY not in tab.model_dump_json()
    assert tab.reserve_share == 0.3


async def test_today_s_calls_are_the_models_the_airline_runs(tmp_path: Path) -> None:
    """Journey 17 Oct 2026 (41, 43): the speech model showed in a hosted airline's Today's
    calls. A runtime lists the speech model only with voice on (a hosted one never has it), and
    the Assistant tab only the models the airline chose: none until it chooses."""
    base = site(tmp_path)
    voiced = base.model_copy(update={"features": base.features | {"voice"}})
    assert used_tiers(voiced) == ("main", "lite", "tts")
    tenant = settings_for.tenant_settings(voiced, record(), answers(), SecretStr(KEY))
    assert used_tiers(tenant) == ("main", "lite")
    store = open_store(tenant)
    view = await budget_view(tenant, StubBackend(), QuotaLedger(tenant, store))
    assert {m.model_id for m in view.models} == {"gemini-3.8-flash", "gemini-3.5-flash-lite"}
    assert {t.tier for t in view.tiers} == {"main", "lite"}
    # a budget that still held another model (the site's, the speech one): the tab drops it
    wide = await budget_view(voiced, StubBackend(), QuotaLedger(voiced, store))
    assert base.model_tts in {m.model_id for m in wide.models}
    tab = settings_for.assistant_tab(record(), base, budget=wide)
    assert tab.budget is not None
    assert {m.model_id for m in tab.budget.models} == {"gemini-3.8-flash", "gemini-3.5-flash-lite"}
    none = settings_for.assistant_tab(record(assistant=None), base, budget=wide)
    assert none.budget is not None
    assert (none.budget.models, none.budget.tiers) == ([], [])


def test_the_demo_keeps_stream_places_after_every_airline_s_are_held_apart(
    tmp_path: Path,
) -> None:
    """Each airline's event-stream places are held apart from the demo's (M1): the total must
    leave the demo at least one, and with hosting off the demo has them all."""
    from tephra.api.server import demo_stream_places

    settings = site(tmp_path)
    assert demo_stream_places(settings) == settings.max_event_streams - 3 * 10
    off = settings.model_copy(update={"features": frozenset({"connect", "onboard"})})
    assert demo_stream_places(off) == off.max_event_streams
    with pytest.raises(ValueError, match="TEPHRA_MAX_EVENT_STREAMS"):
        site(tmp_path, max_event_streams=30)
