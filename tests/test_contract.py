"""Shared-contract behaviour: settings from blank env lines, event and hash time format, and
what makes the Plume Reader ask again."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError
from test_discrepancies import SEMERU, SETTINGS, SIGMET_11, VONA_1806, utc

from tephra.config import (
    ALL_FEATURES,
    HERO_FEATURES,
    MIN_SECRET_CHARS,
    MOVED_TO_POLICY,
    Settings,
)
from tephra.models import (
    Advisory,
    AuditAction,
    AuditEntry,
    ChainHead,
    CloudInfo,
    DutyRun,
    ReplayRecord,
    RunMode,
    SessionInfo,
    Situation,
    SystemState,
)
from tephra.reconcile.discrepancies import build_situation
from tephra.util import timeutil
from tephra.util.events import EventBus
from tephra.util.hashing import canonical_json

AT = utc(2026, 10, 9, 19, 40)
LONG = "x" * MIN_SECRET_CHARS


def situation(**changes: object) -> Situation:
    sigmet = SIGMET_11.model_copy(update=changes)
    return build_situation(
        SEMERU,
        active_reasons=["test"],
        sigmets=[sigmet],
        vonas=[VONA_1806],
        vaas=[],
        winds=[],
        frames=[],
        btd=None,
        at=AT,
        mode=RunMode.REPLAY,
        settings=SETTINGS,
    )


def test_blank_lines_copied_from_env_example_mean_unset(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "TEPHRA_DESK_PIN=\nTEPHRA_SESSION_SECRET=\nTEPHRA_TASK_TOKEN=\nGEMINI_API_KEY=\n"
    )
    settings = Settings(_env_file=env)
    assert settings.desk_pin is None
    assert settings.task_token is None
    assert settings.gemini_api_key is None
    assert len(settings.session_secret.get_secret_value()) >= MIN_SECRET_CHARS


def test_blank_environment_variables_mean_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEPHRA_TASK_TOKEN", "")
    monkeypatch.setenv("TEPHRA_SESSION_SECRET", "")
    settings = Settings(_env_file=None)
    assert settings.task_token is None
    assert len(settings.session_secret.get_secret_value()) >= MIN_SECRET_CHARS


@pytest.mark.parametrize("name", ["session_secret", "task_token"])
def test_short_secrets_are_refused(name: str) -> None:
    with pytest.raises(ValidationError, match=f"at least {MIN_SECRET_CHARS} characters"):
        Settings(_env_file=None, **{name: "too-short"})
    assert Settings(_env_file=None, **{name: LONG})


@pytest.mark.parametrize("name", sorted(MOVED_TO_POLICY))
def test_settings_moved_to_the_policy_file_are_refused(
    name: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Settings ignores unknown keys, so without the check the value would silently not apply.
    monkeypatch.setenv(name, "3000")
    with pytest.raises(ValidationError, match=r"policy_a\.json"):
        Settings(_env_file=None)
    monkeypatch.delenv(name)
    env = tmp_path / ".env"
    env.write_text(f"{name}=3000\n")
    with pytest.raises(ValidationError, match=r"policy_a\.json"):
        Settings(_env_file=env)
    env.write_text(f"{name}=\n")  # a blank line copied from .env.example means unset
    assert Settings(_env_file=env)


def test_subscriptions_must_be_bounded() -> None:
    with pytest.raises(ValueError, match="bounded"):
        EventBus().subscribe(maxsize=0)


class Stamped(BaseModel):
    detail: dict[str, object]


@pytest.mark.parametrize(
    ("at", "expected"),
    [
        (datetime(2026, 10, 7, 10, 32, tzinfo=UTC), "2026-10-07T10:32:00.000Z"),
        (datetime(2026, 10, 7, 10, 32, 5, 123456, tzinfo=UTC), "2026-10-07T10:32:05.123Z"),
    ],
)
def test_hashes_and_events_write_fixed_width_times(at: datetime, expected: str) -> None:
    assert f'"{expected}"'.encode() in canonical_json({"at": at, "list": [at]})
    assert f'"{expected}"'.encode() in canonical_json(Stamped(detail={"at": at}))
    event = EventBus().publish("trace", Stamped(detail={"at": at}))
    assert event.data == {"detail": {"at": expected}}
    assert EventBus().publish("trace", {"at": (at,)}).data == {"at": [expected]}


def test_model_times_keep_their_format_through_events() -> None:
    payload = situation()
    event = EventBus().publish("situation", payload)
    assert event.data["as_of"] == timeutil.to_iso(payload.as_of)
    assert event.data == payload.model_dump(mode="json")


def test_input_hash_follows_the_record_text_not_the_response_hash() -> None:
    base = situation()
    other_response = SIGMET_11.provenance.model_copy(update={"sha256": "0" * 64})
    assert situation(provenance=other_response).input_hash == base.input_hash
    changed_text = SIGMET_11.raw_text.replace("MOV SE", "MOV E")
    assert changed_text != SIGMET_11.raw_text
    assert situation(raw_text=changed_text).input_hash != base.input_hash


@pytest.mark.parametrize(
    ("begin", "expected"),
    [
        (datetime(2026, 9, 25, 15, 0, tzinfo=UTC), datetime(2026, 9, 25, 15, 0, tzinfo=UTC)),
        (datetime(2026, 9, 1, 0, 0, tzinfo=UTC), datetime(2026, 9, 23, 12, 0, tzinfo=UTC)),
        (datetime(2026, 10, 1, 0, 0, tzinfo=UTC), datetime(2026, 9, 27, 6, 0, tzinfo=UTC)),
        (None, datetime(2026, 9, 23, 12, 0, tzinfo=UTC)),
    ],
)
def test_replay_clock_starts_where_asked_inside_the_window(
    begin: datetime | None, expected: datetime
) -> None:
    start, end = datetime(2026, 9, 23, 12, 0, tzinfo=UTC), datetime(2026, 9, 27, 6, 0, tzinfo=UTC)
    clock = timeutil.ReplayClock(start, end, speed=1.0, loop=False, begin=begin)
    assert abs((clock.now() - expected).total_seconds()) < 5


# --- 15 Oct 2026 contract: features, cloud, visitor, replay minute ----------------------


def test_features_setting_parses_all_hero_and_lists() -> None:
    assert Settings(_env_file=None, features="all").features == ALL_FEATURES
    assert Settings(_env_file=None, features="hero").features == HERO_FEATURES == frozenset()
    assert Settings(_env_file=None, features="").features == HERO_FEATURES
    assert Settings(_env_file=None, features="connect,btd").features == frozenset(
        {"connect", "btd"}
    )
    assert Settings(_env_file=None, features=frozenset({"crew"})).features == frozenset({"crew"})
    with pytest.raises(ValidationError, match=r"unknown feature\(s\): nope"):
        Settings(_env_file=None, features="nope")


def test_features_setting_reads_the_environment_as_words(monkeypatch: pytest.MonkeyPatch) -> None:
    # A frozenset field would otherwise be read as JSON and refuse "all".
    monkeypatch.setenv("TEPHRA_FEATURES", "all")
    assert Settings(_env_file=None).features == ALL_FEATURES
    monkeypatch.setenv("TEPHRA_FEATURES", "voice, present")
    assert Settings(_env_file=None).features == frozenset({"voice", "present"})


def test_cloud_info_and_chain_head_shapes() -> None:
    cloud = CloudInfo(
        platform="cloud-run",
        service="tephra",
        revision="tephra-00123-abc",
        region="asia-southeast1",
        store="firestore",
        scheduler="cloud-scheduler",
        secrets="secret-manager",
        model_access="gemini-api",
    )
    assert cloud.instances == "one"
    local = CloudInfo(
        platform="local",
        store="sqlite",
        scheduler="in-process",
        secrets="environment",
        model_access="none",
    )
    assert (local.service, local.revision, local.region) == (None, None, None)
    with pytest.raises(ValidationError):
        CloudInfo(
            platform="laptop",
            store="sqlite",
            scheduler="in-process",
            secrets="environment",
            model_access="none",
        )
    head = ChainHead(seq=1204, sha256="a" * 64, checked_at=AT, entries=1204, intact=True)
    assert head.problems == []
    assert head.model_dump(mode="json")["checked_at"] == timeutil.to_iso(AT)
    state_fields = SystemState.model_fields
    assert state_fields["cloud"].default is None
    assert state_fields["audit"].default is None
    assert state_fields["visitor_access"].default is False
    assert state_fields["features"].default_factory is not None


def test_session_role_defaults_to_dispatcher() -> None:
    session = SessionInfo(name="Mira", expires_at=AT)
    assert session.role == "dispatcher"
    assert session.sid is None
    visitor = SessionInfo(name="Mira", expires_at=AT, role="visitor", sid="s1")
    assert visitor.role == "visitor"
    with pytest.raises(ValidationError):
        SessionInfo(name="Mira", expires_at=AT, role="observer")
    assert AuditAction.VISITOR_ENTERED == "VISITOR_ENTERED"
    assert AuditAction.REPLAY_RESTARTED == "REPLAY_RESTARTED"


def test_new_model_fields_are_optional_and_default_to_todays_shape() -> None:
    entry = AuditEntry(id="a1", at=AT, actor="system", action=AuditAction.DRAFT_CREATED)
    assert (entry.seq, entry.prev_sha256, entry.sha256) == (None, None, None)
    record = ReplayRecord(
        feed="vona",
        url="https://example.invalid/vona",
        fetched_at=AT,
        sha256="0" * 64,
        path="raw/vona/1.html",
        status_code=200,
    )
    assert record.reconstructed is False
    for model, names in (
        (Advisory, ("plan_key", "input_tokens", "output_tokens")),
        (DutyRun, ("input_tokens", "output_tokens")),
    ):
        for name in names:
            assert model.model_fields[name].default is None, (model.__name__, name)


class _Wall:
    """Fake wall and monotonic clocks the quantised replay clock is read against."""

    def __init__(self, monotonic: float, wall: float) -> None:
        self.monotonic = monotonic
        self.wall = wall

    def advance(self, seconds: float) -> None:
        self.monotonic += seconds
        self.wall += seconds


REPLAY_START = datetime(2026, 9, 5, 10, 30, tzinfo=UTC)
REPLAY_END = datetime(2026, 9, 5, 19, 30, tzinfo=UTC)


def _quantised_clock(
    monkeypatch: pytest.MonkeyPatch, *, wall_second: int, quantum_s: int
) -> tuple[timeutil.ReplayClock, _Wall]:
    wall = _Wall(monotonic=500.0, wall=1_700_000_000.0 - (1_700_000_000.0 % 60) + wall_second)
    monkeypatch.setattr(timeutil.time, "monotonic", lambda: wall.monotonic)
    monkeypatch.setattr(timeutil.time, "time", lambda: wall.wall)
    clock = timeutil.ReplayClock(REPLAY_START, REPLAY_END, quantum_s=quantum_s)
    return clock, wall


def test_a_quantised_replay_clock_ticks_the_same_minute_whatever_the_wall_second(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock, wall = _quantised_clock(monkeypatch, wall_second=20, quantum_s=60)
    first, first_exact = clock.now(), clock.now_exact()
    wall.advance(20)
    second, second_exact = clock.now(), clock.now_exact()
    assert first == second == REPLAY_START
    assert (second_exact - first_exact).total_seconds() == 20
    assert (first_exact - first).total_seconds() == 20
    # The replay minute turns when the wall minute does, never in between.
    wall.advance(19)
    assert clock.now() == REPLAY_START
    wall.advance(1)
    assert clock.now() == REPLAY_START + timedelta(minutes=1)
    assert clock.quantum_s == 60
    with timeutil.use_clock(clock):
        assert timeutil.now() == REPLAY_START + timedelta(minutes=1)
        assert timeutil.now_exact() == REPLAY_START + timedelta(minutes=1)

    exact, exact_wall = _quantised_clock(monkeypatch, wall_second=20, quantum_s=0)
    assert exact.now() == exact.now_exact() == REPLAY_START
    exact_wall.advance(20)
    assert exact.now() == exact.now_exact() == REPLAY_START + timedelta(seconds=20)
    with pytest.raises(ValueError, match="quantum"):
        timeutil.ReplayClock(REPLAY_START, REPLAY_END, quantum_s=-1)


def test_now_exact_on_a_plain_clock_is_now() -> None:
    with timeutil.use_clock(timeutil.FixedClock(AT)):
        assert timeutil.now_exact() == timeutil.now() == AT


def test_every_new_setting_defaults_to_todays_behaviour() -> None:
    settings = Settings(_env_file=None)
    assert settings.features == ALL_FEATURES
    assert settings.replay_quantum_s == 0
    assert settings.visitor_access == "off"
    assert settings.secrets_source == "environment"
    assert settings.cloud_region is None
    assert settings.ai_answer_replay_keep_h == 2160.0
    assert settings.visitor_session_ttl_h == 2.0
    assert settings.visitor_decision_cap == 40
    assert settings.visitor_ask_cap == 3
    assert settings.tick_deadline_s == 100
    with pytest.raises(ValidationError):
        Settings(_env_file=None, replay_quantum_s=301)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, tick_deadline_s=19)
