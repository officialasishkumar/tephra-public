"""A hosted airline's model key: sealed with AES-256-GCM under an HKDF key, its kid from a
separate HKDF output, the AAD binding the airline and the kid (D5, S22); never echoed."""

import base64
import logging

import pytest

from tephra.config import Settings
from tephra.hosted import keys
from tephra.hosted.models import SealedKey
from tests.test_hosted_tenants import SECRET, wall

KEY = "AIzaTestKeyRFB0123456789abcdefghijKLMN"


def settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, session_secret=SECRET, **overrides)  # type: ignore[arg-type]


def test_a_sealed_key_opens_for_its_airline_only() -> None:
    sealed = keys.seal("RFB", KEY, settings(), by="Ana Ops#MB-1a2b3c4d5e", at=wall())
    assert sealed.last4 == KEY[-4:]
    assert sealed.v == 1
    assert len(sealed.kid) == 16
    assert keys.unseal("RFB", sealed, settings()).get_secret_value() == KEY
    with pytest.raises(keys.KeyUnreadable):
        keys.unseal("RFC", sealed, settings())
    assert not keys.readable("RFC", sealed, settings())


def test_another_secret_is_a_kid_mismatch() -> None:
    sealed = keys.seal("RFB", KEY, settings(), by="Ana Ops#MB-1", at=wall())
    rotated = settings(key_secret="k" * 40)
    assert keys.key_id(rotated) != sealed.kid
    with pytest.raises(keys.KeyUnreadable, match="enter it again"):
        keys.unseal("RFB", sealed, rotated)


def test_the_key_secret_wins_over_the_session_secret() -> None:
    one = settings(key_secret="k" * 40)
    other = Settings(_env_file=None, session_secret="z" * 40, key_secret="k" * 40)
    sealed = keys.seal("RFB", KEY, one, by="Ana Ops#MB-1", at=wall())
    assert keys.unseal("RFB", sealed, other).get_secret_value() == KEY


def test_an_altered_ciphertext_or_a_forged_kid_does_not_open() -> None:
    sealed = keys.seal("RFB", KEY, settings(), by="Ana Ops#MB-1", at=wall())
    raw = bytearray(base64.urlsafe_b64decode(sealed.ct + "=" * (-len(sealed.ct) % 4)))
    raw[0] ^= 1
    bent = sealed.model_copy(
        update={"ct": base64.urlsafe_b64encode(bytes(raw)).rstrip(b"=").decode()}
    )
    with pytest.raises(keys.KeyUnreadable):
        keys.unseal("RFB", bent, settings())
    other = keys.seal("RFB", KEY, settings(key_secret="q" * 40), by="Ana Ops#MB-1", at=wall())
    forged = other.model_copy(update={"kid": sealed.kid})
    with pytest.raises(keys.KeyUnreadable):
        keys.unseal("RFB", forged, settings())


def test_the_kid_and_the_sealing_key_are_separate_outputs() -> None:
    s = settings()
    assert keys._derive(s, keys.KID_INFO, 8).hex() == keys.key_id(s)
    assert not keys._derive(s, keys.KEY_INFO, 32).startswith(keys._derive(s, keys.KID_INFO, 8))


def test_a_bad_key_is_refused_without_being_echoed(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    typed = "not a key but a secret sentence 4242"
    with pytest.raises(keys.KeyFormat) as refused:
        keys.seal("RFB", typed, settings(), by="Ana Ops#MB-1", at=wall())
    assert typed not in str(refused.value)
    assert typed not in repr(refused.value)
    assert "4242" not in caplog.text


def test_no_key_in_an_error_a_repr_or_the_record() -> None:
    sealed = keys.seal("RFB", KEY, settings(), by="Ana Ops#MB-1", at=wall())
    stored = sealed.model_dump_json()
    assert KEY not in stored
    assert KEY[:8] not in stored
    assert KEY not in repr(sealed)
    opened = keys.unseal("RFB", sealed, settings())
    assert KEY not in repr(opened)
    assert KEY not in str(opened)
    with pytest.raises(keys.KeyUnreadable) as refused:
        keys.unseal("RFC", sealed, settings())
    assert KEY not in str(refused.value)
    assert refused.value.__cause__ is None
    assert refused.value.__suppress_context__
    assert SealedKey.model_validate_json(stored).model_dump_json() == stored
