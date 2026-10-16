"""Airline passwords (scrypt, standard library) and one-time recovery codes.

A stored hash is ``scrypt$N$r$p$<salt b64url>$<hash b64url>``; a check reads N, r and p from
it, so raising the cost later keeps old hashes valid. Every hash runs in a worker thread behind
one semaphore of two, so a burst of sign-ins queues instead of taking every core and the
thread pool from the tick loop (one semaphore per event loop: one in production, and tests
run several loops).
"""

import asyncio
import base64
import hashlib
import hmac
import secrets
import weakref
from typing import Final

__all__ = [
    "RECOVERY_ALPHABET",
    "check_password",
    "code_sha256",
    "codes_match",
    "dummy_check",
    "hash_password",
    "hashed",
    "new_recovery_code",
    "normalise_code",
    "password_matches",
]

SCRYPT_N: Final = 2**14
SCRYPT_R: Final = 8
SCRYPT_P: Final = 5
"""OWASP's N=2^14, r=8, p=5 row: 16 MiB a hash, about five times p=1's CPU."""
SCRYPT_DKLEN: Final = 32
SALT_BYTES: Final = 16
MAX_MEM: Final = 64 * 1024 * 1024
RECOVERY_ALPHABET: Final = "ABCDEFGHJKMNPQRSTVWXYZ23456789"
"""No 0/O, 1/I/L or U: a code read aloud or copied by hand stays unambiguous."""
RECOVERY_GROUPS: Final = 4
_SCHEME: Final = "scrypt"
_DUMMY_SALT: Final = b"tephra-dummy-salt"
HASHES_AT_ONCE: Final = 2
_HASHING: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore]" = (
    weakref.WeakKeyDictionary()
)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int, dklen: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=dklen, maxmem=MAX_MEM
    )


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    digest = _scrypt(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_DKLEN)
    return f"{_SCHEME}${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def password_matches(password: str, stored: str) -> bool:
    """Recompute with the stored parameters and compare in constant time."""
    parts = stored.split("$")
    if len(parts) != 6 or parts[0] != _SCHEME:
        return False
    try:
        n, r, p = (int(part) for part in parts[1:4])
        salt, expected = _unb64(parts[4]), _unb64(parts[5])
        digest = _scrypt(password, salt, n, r, p, len(expected))
    except ValueError:
        return False
    return hmac.compare_digest(digest, expected)


def dummy_check(password: str) -> None:
    """One scrypt on a fixed salt, so an unknown email costs the same time as a known one."""
    _scrypt(password, _DUMMY_SALT, SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_DKLEN)


def _hashing() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    return _HASHING.setdefault(loop, asyncio.Semaphore(HASHES_AT_ONCE))


async def hashed(password: str) -> str:
    async with _hashing():
        return await asyncio.to_thread(hash_password, password)


async def check_password(password: str, stored: str | None) -> bool:
    """``stored`` None (no such account) still costs one scrypt and answers False."""
    async with _hashing():
        if stored is None:
            await asyncio.to_thread(dummy_check, password)
            return False
        return await asyncio.to_thread(password_matches, password, stored)


def new_recovery_code() -> str:
    """16 characters from a 30-letter alphabet (78 bits), as ``XXXX-XXXX-XXXX-XXXX``."""
    letters = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(4 * RECOVERY_GROUPS))
    return "-".join(letters[i : i + 4] for i in range(0, len(letters), 4))


def normalise_code(text: str) -> str:
    return "".join(ch for ch in text.upper() if ch not in " -")


def code_sha256(code: str) -> str:
    return hashlib.sha256(normalise_code(code).encode("utf-8")).hexdigest()


def codes_match(code: str, stored_sha256: str) -> bool:
    """78 random bits need no slow hash; the comparison is still constant time."""
    return hmac.compare_digest(code_sha256(code), stored_sha256)
