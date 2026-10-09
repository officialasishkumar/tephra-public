"""SHA-256 helpers for provenance, stable ids and audit input hashes."""

import hashlib
import json
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel
from pydantic_core import to_jsonable_python

__all__ = [
    "SHORT_HASH_LEN",
    "canonical_json",
    "combine_hashes",
    "proxy_flight_number",
    "sha256_bytes",
    "sha256_json",
    "sha256_text",
    "short_hash",
    "stable_id",
]

SHORT_HASH_LEN = 12


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def canonical_json(value: Any) -> bytes:
    """Deterministic JSON bytes (sorted keys, no whitespace) for hashing."""
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    plain = to_jsonable_python(value)
    return json.dumps(plain, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json(value))


def short_hash(digest: str, length: int = SHORT_HASH_LEN) -> str:
    """First ``length`` hex characters of a digest: what the UI and advisory header print."""
    return digest[:length]


def combine_hashes(digests: Iterable[str]) -> str:
    """Order-independent digest of a set of digests (duplicates collapse)."""
    return sha256_text("\n".join(sorted(set(digests))))


def stable_id(prefix: str, *parts: object, length: int = SHORT_HASH_LEN) -> str:
    """``PREFIX-<short sha of parts>``: the same inputs always give the same id."""
    joined = "\x1f".join(str(part) for part in parts)
    return f"{prefix}-{short_hash(sha256_text(joined), length)}"


def proxy_flight_number(hex_id: str) -> str:
    """Fictional Ring of Fire Air flight number for a real ADS-B target, e.g. ``RFA4821``.

    TEPHRA treats every tracked aircraft as if the fictional airline dispatched it; the
    number is derived from the ICAO 24-bit address so it is stable across ticks.
    """
    digest = sha256_text(hex_id.strip().lower())
    return f"RFA{int(digest[:8], 16) % 9000 + 1000}"
