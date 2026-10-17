"""Document stores: SQLite on a laptop, Firestore + Cloud Storage on Cloud Run.

Import-light on purpose: ``tephra.store.base`` is imported by low layers, and importing it
runs this file first. The backends are imported inside :func:`open_store`.
"""

import json
import math
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from tephra.store.base import BLOB_KEY_PATTERN, Store

if TYPE_CHECKING:
    from tephra.config import Settings

__all__ = [
    "NAMESPACE_PATTERN",
    "OpHook",
    "billed_count_reads",
    "billed_reads",
    "check_blob_key",
    "check_cas_doc",
    "decode_doc",
    "encode_doc",
    "open_store",
    "tenant_sqlite_path",
]

_BLOB_KEY = re.compile(BLOB_KEY_PATTERN)
NAMESPACE_PATTERN = r"^[A-Z]{3}$"
"""A hosted airline's namespace is its ICAO designator."""
_NAMESPACE = re.compile(NAMESPACE_PATTERN)

OpHook = Callable[[str, int], None]
"""``on_op(kind, n)``: a backend reports ``n`` billed operations of ``kind`` ("reads",
"writes" or "deletes") as it makes them (``tephra.store.metered`` attributes them)."""


def open_store(
    settings: "Settings", *, namespace: str | None = None, shared: Store | None = None
) -> Store:
    """The store selected by ``TEPHRA_STORE`` (Firestore only runs inside Cloud Run).

    ``namespace`` (an airline's ICAO) opens that airline's own documents: Firestore's
    ``tenants/<ICAO>/<collection>`` beside the root collections, on ``shared``'s client when it
    is a Firestore store; SQLite's ``tenants/<ICAO>.sqlite3`` beside ``TEPHRA_SQLITE_PATH``.
    Blobs (public data) stay shared. Open one store per namespace per process: the audit chain,
    decision locks and the meter are kept per store object.
    """
    if namespace is not None and _NAMESPACE.fullmatch(namespace) is None:
        raise ValueError(f"store namespace must be an ICAO designator, got {namespace!r}")
    if settings.store == "firestore":
        from tephra.store.firestore_store import FirestoreStore

        root = getattr(shared, "inner", shared)
        if namespace is not None and isinstance(root, FirestoreStore):
            return root.sibling(namespace)
        if settings.gcp_project is None or settings.gcs_bucket is None:
            message = "TEPHRA_STORE=firestore needs TEPHRA_GCP_PROJECT and TEPHRA_GCS_BUCKET"
            raise ValueError(message)
        return FirestoreStore(
            settings.gcp_project,
            settings.firestore_database,
            settings.gcs_bucket,
            namespace=namespace,
        )

    from tephra.store.sqlite_store import SqliteStore

    path = settings.sqlite_path if namespace is None else tenant_sqlite_path(settings, namespace)
    return SqliteStore(path, settings.cache_dir / "blobs")


def tenant_sqlite_path(settings: "Settings", icao: str) -> Path:
    """An airline's SQLite file: ``<sqlite dir>/tenants/<ICAO>.sqlite3``."""
    if _NAMESPACE.fullmatch(icao) is None:
        raise ValueError(f"not an ICAO designator: {icao!r}")
    return settings.sqlite_path.parent / "tenants" / f"{icao}.sqlite3"


def billed_reads(documents: int) -> int:
    """Reads Firestore bills for a query or get: one per document, at least one."""
    return max(1, documents)


def billed_count_reads(matches: int) -> int:
    """Reads Firestore bills for a count aggregation: one per 1,000 entries, at least one."""
    return max(1, math.ceil(matches / 1000))


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
