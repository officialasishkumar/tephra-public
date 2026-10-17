"""The hosted contract additions: they change no demo document, hash or answer.

The pinned hashes were computed from the same models at bc3fac9, before the hosted fields
existed: a new field that reached a demo document would change them.
"""

from datetime import UTC, datetime
from typing import get_args

import pytest

from tephra.config import (
    ALL_FEATURES,
    DEMO_AIRLINE,
    HOSTED_FEATURES,
    SHADOW_LINE,
    SHADOW_WORDS,
    Settings,
)
from tephra.models import (
    ActionKind,
    Advisory,
    AdvisoryStatus,
    AuditAction,
    OutboundMessage,
    PlumeMode,
    PushedDot,
    PushSummary,
    SessionInfo,
    SessionRole,
)
from tephra.store.base import Collection
from tephra.store.firestore_store import INDEXED_ONLY, index_fields
from tephra.util.hashing import sha256_json

AT = datetime(2026, 10, 17, 14, 2, tzinfo=UTC)


def advisory(**overrides: object) -> Advisory:
    fields: dict[str, object] = {
        "id": "adv_0123456789ab",
        "version": 1,
        "status": AdvisoryStatus.DRAFT,
        "created_at": AT,
        "updated_at": AT,
        "replay": False,
        "volcano_id": "263300",
        "volcano_name": "Semeru",
        "flight_id": "8a0123:263300",
        "proxy_flight": "RFA0123",
        "callsign": "RFA417",
        "hex": "8a0123",
        "action": ActionKind.HOLD,
        "hold_fl": 350,
        "minutes_to_entry": 14,
        "inside_now": False,
        "fuel_line": "HOLD 20 MIN",
        "plume_mode": PlumeMode.OFFICIAL,
        "confidence": 1.0,
        "cone_id": "CONE-0123456789ab",
        "assessment_id": "PA-0123456789ab",
        "plan_id": "PLAN-0123456789ab",
        "header": "TEPHRA COMPANY ADVISORY",
        "body": "HOLD FL350.",
        "cost_note": "HOLD 20 MIN",
        "sources": [],
        "input_hash": "0" * 64,
        "llm_backend": "stub",
        "model_id": "stub",
        "prompt_hashes": {"drafter": "c" * 64},
        "dedupe_key": "DD-0123456789ab",
    }
    return Advisory.model_validate(fields | overrides)


def outbound(**overrides: object) -> OutboundMessage:
    fields: dict[str, object] = {
        "id": "out_1",
        "advisory_id": "adv_0123456789ab",
        "advisory_version": 2,
        "queued_at": AT,
        "proxy_flight": "RFA0123",
        "status": AdvisoryStatus.APPROVED,
        "approved_by": "desk:Ana",
        "text": "HOLD",
    }
    return OutboundMessage.model_validate(fields | overrides)


def push(**overrides: object) -> PushSummary:
    dot = PushedDot(
        hex="8a0123",
        callsign="RFB417",
        lat=-7.5,
        lon=110.4,
        alt_baro_ft=35000,
        track_deg=90.0,
        in_ash=False,
    )
    fields: dict[str, object] = {
        "connection_id": "CN-1",
        "name": "ops",
        "sample": False,
        "at": AT,
        "wall_at": AT,
        "accepted": 3,
        "rejected": 1,
        "reasons": ["positions[4]: too old"],
        "dots": [dot],
    }
    return PushSummary.model_validate(fields | overrides)


@pytest.mark.parametrize(
    ("model", "pinned"),
    [
        (advisory(), "ed1761db9bbb9699e89cde66265f533512659ab0cc69c0849564ad86b94b78f7"),
        (outbound(), "934974ed771a5033f4e2772819343fcb3ee0c98a3bbbf75df0775b6fa67d9580"),
        (push(), "885b58583d1427f4375c9b80ecc1622273f1472bc21a0e9c1be8bccc9f1d987e"),
        (DEMO_AIRLINE, "f3b9f74df78b94a2c78e815d4ecbefe9d9f42e49899800b6a0d6a15e344a3032"),
    ],
    ids=["advisory", "outbound", "push", "airline"],
)
def test_demo_documents_and_hashes_are_unchanged(model: object, pinned: str) -> None:
    assert sha256_json(model.model_dump(mode="json")) == pinned  # type: ignore[attr-defined]


def test_new_fields_are_left_out_at_their_defaults_and_written_when_set() -> None:
    assert "shadow" not in advisory().model_dump()
    assert "shadow" not in advisory().model_dump_json()
    assert advisory(shadow=True).model_dump(mode="json")["shadow"] is True
    assert Advisory.model_validate(advisory().model_dump(mode="json")).shadow is False
    assert "shadow" not in outbound().model_dump(mode="json")
    assert outbound(shadow=True).model_dump(mode="json")["shadow"] is True
    assert "rejected_by_section" not in push().model_dump(mode="json")
    assert push(rejected_by_section={"positions": 3}).model_dump(mode="json")[
        "rejected_by_section"
    ] == {"positions": 3}
    assert "shadow" not in DEMO_AIRLINE.model_dump(mode="json")


def test_shadow_words_and_hosted_features() -> None:
    assert SHADOW_LINE == "SHADOW - NOT FOR USE"
    assert SHADOW_WORDS == "Shadow · not for use"
    assert {"connect", "crew", "notices"} == HOSTED_FEATURES
    assert HOSTED_FEATURES <= ALL_FEATURES


def test_the_airline_carries_the_shadow_stage() -> None:
    def own(stage: str | None) -> Settings:
        return Settings(
            _env_file=None,
            fleet_prefixes="RFB",
            airline_name="Ring of Fire Charter",
            airline_icao="RFB",
            airline_iata="RB",
            hosted_tenant=None if stage is None else "RFB",
            hosted_stage=stage,
        )

    shadow = own("shadow").airline
    assert shadow.shadow
    assert shadow.stamp == SHADOW_LINE
    assert own("live").airline.stamp is None
    assert own("setup").airline.stamp is None
    assert own(None).airline.stamp is None
    assert DEMO_AIRLINE.stamp is None


def test_viewer_is_a_session_role_and_operators_are_not() -> None:
    assert set(get_args(SessionRole)) == {"dispatcher", "visitor", "viewer"}
    assert SessionInfo(name="Dee", expires_at=AT, role="viewer").role == "viewer"


def test_hosted_audit_actions() -> None:
    hosted = {
        "HOSTED_SETUP",
        "HOSTED_SHADOW",
        "HOSTED_LIVE",
        "HOSTED_STOPPED",
        "HOSTED_SUSPENDED",
        "HOSTED_RESUMED",
        "POLICY_CHANGED",
        "POLICY_CONFIRMED",
        "SRA_RECORDED",
        "SRA_WITHDRAWN",
        "MODEL_KEY_SET",
        "MODEL_KEY_REMOVED",
        "ASSISTANT_CHANGED",
        "MEMBER_INVITED",
        "MEMBER_JOINED",
        "MEMBER_ROLE_CHANGED",
        "MEMBER_REMOVED",
        "INVITE_REVOKED",
        "OPS_MANAGER_RESTORED",
        "CHAIN_CHECKED",
    }
    assert hosted <= {action.value for action in AuditAction}
    assert AuditAction.CONNECTION_CREATED == "CONNECTION_CREATED"  # push keys reuse these


def test_hosted_collections_and_their_indexed_fields() -> None:
    assert {
        member: member.value
        for member in Collection
        if member.value.startswith(("hosted_", "operator", "policy_versions"))
    } == {
        Collection.HOSTED_TENANTS: "hosted_tenants",
        Collection.HOSTED_MEMBERS: "hosted_members",
        Collection.HOSTED_INVITES: "hosted_invites",
        Collection.HOSTED_SLOTS: "hosted_slots",
        Collection.HOSTED_METER: "hosted_meter",
        Collection.OPERATORS: "operators",
        Collection.OPERATOR_INVITES: "operator_invites",
        Collection.POLICY_VERSIONS: "policy_versions",
    }
    member = {"icao": "RFB", "login_key": "k", "email": "ana@rfb.example", "role": "viewer"}
    assert index_fields(member, Collection.HOSTED_MEMBERS) == {"icao": "RFB", "login_key": "k"}
    assert index_fields({"state": "live", "name": "x"}, Collection.HOSTED_TENANTS) == {
        "state": "live"
    }
    for name in (
        Collection.OPERATORS,
        Collection.OPERATOR_INVITES,
        Collection.HOSTED_SLOTS,
        Collection.HOSTED_METER,
    ):
        assert INDEXED_ONLY[name] == frozenset()
    assert INDEXED_ONLY[Collection.HOSTED_INVITES] == {"icao", "expires_at"}


def test_hosted_settings_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.hosted_max_tenants == 3
    assert settings.key_secret is None
    assert settings.hosted_tick_budget_s == 40
    assert (settings.hosted_reads_cap, settings.hosted_writes_cap) == (40_000, 16_000)
    assert settings.hosted_deletes_cap == 16_000
    assert settings.hosted_tenant_share == 0.6
    assert settings.hosted_blob_puts_cap == 4_000
    assert settings.hosted_rss_limit_mb == 700
    assert settings.hosted_push_gap_s == 10
    assert settings.hosted_streams_per_tenant == 10
    assert (settings.hosted_tenant, settings.hosted_stage) == (None, None)


@pytest.mark.parametrize(
    "overrides",
    [
        {"hosted_max_tenants": 4},
        {"hosted_tick_budget_s": 34},
        {"hosted_tick_budget_s": 46},
        {"hosted_tenant_share": 0},
        {"hosted_rss_limit_mb": 199},
        {"hosted_streams_per_tenant": 51},
        {"hosted_tenant": "rfb", "hosted_stage": "live"},
        {"hosted_tenant": "RFB"},
        {"hosted_stage": "live"},
        {"key_secret": "short"},
    ],
)
def test_hosted_settings_are_bounded(overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError):  # noqa: PT011 (pydantic's ValidationError, any message)
        Settings(_env_file=None, **overrides)
