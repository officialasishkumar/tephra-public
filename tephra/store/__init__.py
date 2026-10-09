"""Document stores: SQLite on a laptop, Firestore + Cloud Storage on Cloud Run.

Import-light on purpose: ``tephra.store.base`` is imported by low layers, and importing it
runs this file first. The backends are imported inside :func:`open_store`.
"""

import json
import math
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from tephra.store.base import BLOB_KEY_PATTERN, Store

if TYPE_CHECKING:
    from tephra.config import Settings

__all__ = ["check_blob_key", "check_cas_doc", "decode_doc", "encode_doc", "open_store"]

_BLOB_KEY = re.compile(BLOB_KEY_PATTERN)


def open_store(settings: "Settings") -> Store:
    """The store selected by ``TEPHRA_STORE`` (Firestore only runs inside Cloud Run)."""
    if settings.store == "firestore":
        from tephra.store.firestore_store import FirestoreStore

        if settings.gcp_project is None or settings.gcs_bucket is None:
            message = "TEPHRA_STORE=firestore needs TEPHRA_GCP_PROJECT and TEPHRA_GCS_BUCKET"
            raise ValueError(message)
        return FirestoreStore(
            settings.gcp_project, settings.firestore_database, settings.gcs_bucket
        )

    from tephra.store.sqlite_store import SqliteStore

    return SqliteStore(settings.sqlite_path, settings.cache_dir / "blobs")


def encode_doc(doc: Mapping[str, Any]) -> str:
    """Compact JSON for a stored document; NaN and infinities become null.

    Strict JSON keeps SQLite's json_extract and Firestore readers working when a numeric
    statistic (a BTD median over zero pixels, say) is not finite.
    """
    return json.dumps(
        _finite(dict(doc)), ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )


def decode_doc(text: str) -> dict[str, Any]:
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("stored document is not a JSON object")
    return value


def check_cas_doc(expected_version: int, doc: Mapping[str, Any]) -> None:
    """Shared precondition of ``Store.compare_and_set_advisory``."""
    if expected_version < 0:
        raise ValueError("expected_version must be >= 0")
    if doc.get("version") != expected_version + 1:
        raise ValueError(
            f"advisory version must be {expected_version + 1}, got {doc.get('version')!r}"
        )


def check_blob_key(key: str) -> None:
    if _BLOB_KEY.fullmatch(key) is None:
        raise ValueError(f"blob key {key!r} does not match {BLOB_KEY_PATTERN}")


def _finite(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return {str(key): _finite(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_finite(item) for item in value]
    return value
