"""Shared-contract behaviour: settings from blank env lines, event and hash time format, and
what makes the Plume Reader ask again."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError
from test_discrepancies import SEMERU, SETTINGS, SIGMET_11, VONA_1806, utc

from tephra.config import MIN_SECRET_CHARS, Settings
from tephra.models import RunMode, Situation
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
