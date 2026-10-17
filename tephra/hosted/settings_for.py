"""A hosted airline's runtime settings, its model key's state, and its Assistant tab.

:func:`tenant_settings` builds the settings from the site's own, the tenant record and the
airline's onboarding answers, with ``model_validate`` (nothing is read from the environment).
The site's secrets are cleared (S22d), so a runtime holds no PIN, task token or key secret; its
only model key is the airline's own, or none (then every model step says AI UNAVAILABLE).
"""

import secrets
from typing import Any, Final

from pydantic import SecretStr

from tephra.agents.budget import BudgetView
from tephra.airline.models import AirlineAnswers
from tephra.config import HOSTED_FEATURES, Settings
from tephra.hosted import keys
from tephra.hosted.models import (
    AssistantKeyView,
    AssistantTab,
    HostedRefused,
    ModelChoice,
    TenantAssistant,
    TenantRecord,
)
from tephra.models import RunMode
from tephra.store import tenant_sqlite_path

__all__ = [
    "NO_KEY",
    "NO_MODEL",
    "UNREADABLE",
    "assistant_tab",
    "check_assistant",
    "hosted_models",
    "model_key",
    "tenant_settings",
]

NO_KEY: Final = "no model key is set"
UNREADABLE: Final = keys.UNREADABLE
NO_MODEL: Final = "no model is chosen"
STAGES: Final = frozenset({"setup", "shadow", "live"})


def hosted_models(settings: Settings) -> dict[str, int]:
    """The models an airline may choose, with their free-tier requests a day: TEPHRA's
    free-tier table without the speech model (Ollama is never offered on hosted TEPHRA)."""
    return {
        name: limit.rpd
        for name, limit in settings.model_limits.items()
        if name != settings.model_tts and not name.endswith("-tts") and limit.rpd > 0
    }


def check_assistant(assistant: TenantAssistant, settings: Settings) -> None:
    """Both names in the table, and each daily limit 1..that model's free-tier rpd."""
    table = hosted_models(settings)
    for name in (assistant.model, assistant.model_lite):
        if name not in table:
            raise HostedRefused(422, "model_not_offered", "Choose a model from the list")
    for name, limit in assistant.daily_limits.items():
        if name not in (assistant.model, assistant.model_lite):
            raise HostedRefused(422, "daily_limit", "A daily limit names a model not chosen")
        if not 1 <= limit <= table[name]:
            raise HostedRefused(
                422, "daily_limit", f"The daily limit for {name} is 1 to {table[name]}"
            )


def model_key(record: TenantRecord, settings: Settings) -> tuple[SecretStr | None, str | None]:
    """The airline's key, or None and the reason every model step reports instead."""
    if record.assistant is None:
        return None, NO_MODEL
    if record.model_key is None:
        return None, NO_KEY
    try:
        return keys.unseal(record.icao, record.model_key, settings), None
    except keys.KeyUnreadable:
        return None, UNREADABLE


def tenant_settings(
    base: Settings, record: TenantRecord, answers: AirlineAnswers, key: SecretStr | None
) -> Settings:
    """The runtime settings of a hosted airline (SPEC §3.6 table)."""
    if record.state not in STAGES:
        raise ValueError(f"no runtime settings for an airline in {record.state}")
    if record.region is None:
        raise ValueError("an airline's runtime needs its region (chosen when it starts)")
    airline = answers.airline
    assistant = record.assistant
    model = base.model if assistant is None else assistant.model
    model_lite = base.model_lite if assistant is None else assistant.model_lite
    limits = {} if assistant is None else assistant.daily_limits
    overrides: dict[str, Any] = {
        "mode": RunMode.LIVE,
        "replay_case": None,
        "replay_start": None,
        "replay_end": None,
        "auto_replay": False,
        "local_scheduler": False,
        "llm": "gemini",
        "gemini_api_key": key,
        "model": model,
        "model_lite": model_lite,
        "model_daily_budget": limits.get(model),
        "model_lite_daily_budget": limits.get(model_lite),
        "ai_interactive_share": base.ai_interactive_share
        if assistant is None
        else assistant.reserve_share,
        "sqlite_path": tenant_sqlite_path(base, record.icao),
        "features": HOSTED_FEATURES,
        "visitor_access": "off",
        "region": record.region,
        "fleet_prefixes": frozenset({airline.callsign_prefix, *answers.fleet.extra_prefixes}),
        "fleet_hexes": frozenset(a.hex for a in answers.fleet.aircraft if a.hex is not None),
        "network_airports": frozenset(a.icao for a in answers.network.airports),
        "airline_name": airline.name,
        "airline_icao": airline.icao,
        "airline_iata": airline.iata,
        "airline_schedule": None,
        "airline_fleet": None,
        "recovery_auto": False,
        "science": False,
        "tick_deadline_s": base.hosted_tick_budget_s - 15,
        "desk_pin": None,
        "task_token": None,
        "key_secret": None,
        "session_secret": SecretStr(secrets.token_urlsafe(32)),
        "hosted_tenant": record.icao,
        "hosted_stage": record.state,
    }
    settings = type(base).model_validate({**base.model_dump(), **overrides})
    held = settings.gemini_api_key
    assert held is None if key is None else held == key, "a runtime holds only its airline's key"
    return settings


def assistant_tab(
    record: TenantRecord, settings: Settings, *, budget: BudgetView | None
) -> AssistantTab:
    """The Assistant tab. ``settings`` are the site's (the table and the sealing secret);
    ``budget`` is the airline's ledger (None in setup). Paused: today's calls on every chosen
    model are used."""
    table = hosted_models(settings)
    assistant = record.assistant
    sealed = record.model_key
    readable = None if sealed is None else keys.readable(record.icao, sealed, settings)
    _, unavailable = model_key(record, settings)
    chosen = set() if assistant is None else {assistant.model, assistant.model_lite}
    rows = [] if budget is None else [row for row in budget.models if row.model_id in chosen]
    paused = bool(rows) and all(row.closed or row.remaining <= 0 for row in rows)
    state = "unavailable" if unavailable is not None else "paused" if paused else "on"
    return AssistantTab(
        model=None if assistant is None else assistant.model,
        model_lite=None if assistant is None else assistant.model_lite,
        models=[ModelChoice(name=name, free_rpd=rpd) for name, rpd in table.items()],
        key=AssistantKeyView(
            set=sealed is not None,
            last4=None if sealed is None else sealed.last4,
            set_by=None if sealed is None else sealed.set_by,
            readable=readable,
        ),
        reserve_share=settings.ai_interactive_share
        if assistant is None
        else assistant.reserve_share,
        daily_limits={} if assistant is None else assistant.daily_limits,
        state=state,
        reason=unavailable,
        budget=budget,
    )
