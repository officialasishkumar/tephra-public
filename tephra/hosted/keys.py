"""A hosted airline's model key, sealed with AES-256-GCM in its tenant record (D5, S22).

The sealing key and the key id come from two separate HKDF-SHA256 outputs of
``TEPHRA_KEY_SECRET`` (else ``TEPHRA_SESSION_SECRET``), and the AAD binds the airline, the format
version and the key id: a sealed key copied into another airline's record, or sealed under
another secret, does not open. The derived key never leaves this module, no exception carries
the model key, and a page only ever sees its last four characters.
"""

import base64
import os
import re
from datetime import datetime
from typing import Final

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from pydantic import SecretStr

from tephra.config import Settings
from tephra.hosted.models import SealedKey, Stamp

__all__ = [
    "API_KEY",
    "KEY_INFO",
    "KEY_SALT",
    "KID_INFO",
    "UNREADABLE",
    "KeyFormat",
    "KeyUnreadable",
    "key_id",
    "readable",
    "seal",
    "unseal",
]

KEY_INFO: Final = b"tephra hosted model key v1"
KID_INFO: Final = b"tephra hosted model key id v1"
KEY_SALT: Final = b"tephra-hosted"
API_KEY: Final = re.compile(r"^[A-Za-z0-9_-]{30,100}$")
"""An AI Studio key's shape; a value that does not match is refused without being echoed."""
NONCE_BYTES: Final = 12
UNREADABLE: Final = "the model key cannot be read: enter it again in Settings › Assistant"  # noqa: RUF001


class KeyFormat(ValueError):
    def __init__(self) -> None:
        super().__init__("that is not a Google AI Studio key: 30 to 100 letters, digits, - or _")


class KeyUnreadable(Exception):
    """Sealed under another secret, for another airline, or altered."""

    def __init__(self) -> None:
        super().__init__(UNREADABLE)


def _secret(settings: Settings) -> bytes:
    chosen = settings.key_secret if settings.key_secret is not None else settings.session_secret
    return chosen.get_secret_value().encode("utf-8")


def _derive(settings: Settings, info: bytes, length: int) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=KEY_SALT, info=info).derive(
        _secret(settings)
    )


def key_id(settings: Settings) -> str:
    """16 hex digits naming the secret in use: a rotation shows as a kid mismatch."""
    return _derive(settings, KID_INFO, 8).hex()


def _aad(icao: str, kid: str) -> bytes:
    return f"tephra/{icao}/model_key/v1/{kid}".encode("ascii")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def seal(icao: str, api_key: str, settings: Settings, *, by: str, at: datetime) -> SealedKey:
    """Raises :class:`KeyFormat` for anything that is not shaped like a key."""
    if API_KEY.fullmatch(api_key) is None:
        raise KeyFormat()
    kid = key_id(settings)
    nonce = os.urandom(NONCE_BYTES)
    sealed = AESGCM(_derive(settings, KEY_INFO, 32)).encrypt(
        nonce, api_key.encode("ascii"), _aad(icao, kid)
    )
    return SealedKey(
        kid=kid,
        nonce=_b64(nonce),
        ct=_b64(sealed),
        last4=api_key[-4:],
        set_by=Stamp(by=by, at=at),
    )


def unseal(icao: str, sealed: SealedKey, settings: Settings) -> SecretStr:
    """The key, or :class:`KeyUnreadable` (a kid mismatch, another airline's AAD, a bad tag)."""
    if sealed.kid != key_id(settings):
        raise KeyUnreadable()
    try:
        plain = AESGCM(_derive(settings, KEY_INFO, 32)).decrypt(
            _unb64(sealed.nonce), _unb64(sealed.ct), _aad(icao, sealed.kid)
        )
        return SecretStr(plain.decode("ascii"))
    except (InvalidTag, ValueError):
        raise KeyUnreadable() from None


def readable(icao: str, sealed: SealedKey, settings: Settings) -> bool:
    try:
        unseal(icao, sealed, settings)
    except KeyUnreadable:
        return False
    return True
