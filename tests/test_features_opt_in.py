"""The hosted feature is opt-in: never in "all" or the default, and only with onboard and an
explicitly set secret."""

import pytest
from pydantic import ValidationError

from tephra.config import ALL_FEATURES, OPT_IN_FEATURES, Settings

SECRET = "s" * 40


def test_all_and_the_default_never_include_hosted() -> None:
    assert {"hosted"} == OPT_IN_FEATURES
    assert "hosted" not in ALL_FEATURES
    assert "hosted" not in Settings(_env_file=None).features
    assert "hosted" not in Settings(_env_file=None, features="all").features
    assert Settings(_env_file=None, features="hero").features == frozenset()


def test_a_comma_list_turns_hosted_on() -> None:
    settings = Settings(_env_file=None, features="connect,onboard,hosted", session_secret=SECRET)
    assert settings.features == {"connect", "onboard", "hosted"}


def test_hosted_needs_onboard() -> None:
    with pytest.raises(ValidationError, match="hosted needs onboard"):
        Settings(_env_file=None, features="hosted", session_secret=SECRET)


def test_hosted_needs_an_explicit_secret() -> None:
    with pytest.raises(ValidationError, match="TEPHRA_SESSION_SECRET or TEPHRA_KEY_SECRET"):
        Settings(_env_file=None, features="onboard,hosted")
    keyed = Settings(_env_file=None, features="onboard,hosted", key_secret="k" * 32)
    assert keyed.key_secret is not None


def test_a_secret_from_the_environment_counts_and_a_blank_one_does_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEPHRA_FEATURES", "onboard,hosted")
    monkeypatch.setenv("TEPHRA_SESSION_SECRET", "")
    with pytest.raises(ValidationError, match="TEPHRA_SESSION_SECRET or TEPHRA_KEY_SECRET"):
        Settings(_env_file=None)
    monkeypatch.setenv("TEPHRA_SESSION_SECRET", SECRET)
    assert "hosted" in Settings(_env_file=None).features


def test_unknown_features_are_still_refused() -> None:
    with pytest.raises(ValidationError, match="unknown feature"):
        Settings(_env_file=None, features="hosted,tenants")
