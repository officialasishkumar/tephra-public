"""Storing, listing and signing documents.

Documents live in the ``docs`` collection next to other work packages' records (the shift
handover brief), so a stored document of another kind is never returned here. Every signature
is an audit entry and a ``doc`` event. Nothing is queued to ``outbound``: an SRA or a VAR goes
to an authority only through the operator's own channels, outside TEPHRA.
"""

import asyncio
import logging
import weakref
from collections.abc import Sequence
from typing import Any, Final

from pydantic import ValidationError

from tephra.desk import audit
from tephra.models import AuditAction, SseEvent
from tephra.regdocs.models import (
    DocKind,
    DocStatus,
    DocSummary,
    RegDocAdapter,
    SignRole,
    SraDraft,
    VarDraft,
)
from tephra.store.base import Collection, Store, Where
from tephra.util import timeutil
from tephra.util.events import EventBus

__all__ = [
    "MAX_SIGN_NAME_CHARS",
    "AlreadySigned",
    "DocNotFound",
    "InvalidSignature",
    "get_doc",
    "list_docs",
    "record_new_doc",
    "sign_doc",
]

MAX_SIGN_NAME_CHARS: Final = 60
MIN_SIGN_NAME_CHARS: Final = 2
_KINDS: Final = [kind.value for kind in DocKind]
_locks: "weakref.WeakKeyDictionary[Store, asyncio.Lock]" = weakref.WeakKeyDictionary()
logger = logging.getLogger(__name__)


class DocNotFound(Exception): ...


class InvalidSignature(Exception):
    """The role has no line on this document, the line is signed, or the name is unusable."""

    def __init__(self, problems: Sequence[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = list(problems)


class AlreadySigned(InvalidSignature):
    """The role's signature line is already filled."""


async def record_new_doc(
    store: Store,
    bus: EventBus,
    doc: SraDraft | VarDraft,
    *,
    actor: str,
    model_id: str | None = None,
    prompt_hash: str | None = None,
) -> None:
    """Store a new draft, audit ``DOC_DRAFTED`` and announce it."""
    await _put(store, doc)
    await audit.record(
        store,
        actor=actor,
        action=AuditAction.DOC_DRAFTED,
        after=_audit_view(doc),
        input_hashes=[doc.input_hash],
        model_id=model_id,
        prompt_hash=prompt_hash,
        note=f"{doc.kind} draft {doc.id}",
    )
    bus.publish(SseEvent.DOC, DocSummary.of(doc))


async def _put(store: Store, doc: SraDraft | VarDraft) -> None:
    await store.put(Collection.DOCS, doc.id, doc.model_dump(mode="json"))


async def get_doc(store: Store, doc_id: str) -> SraDraft | VarDraft | None:
    return _parse(await store.get(Collection.DOCS, doc_id))


async def list_docs(
    store: Store, *, kind: DocKind | None = None, limit: int = 50
) -> list[SraDraft | VarDraft]:
    """Newest first."""
    kinds = _KINDS if kind is None else [kind.value]
    docs = await store.query(
        Collection.DOCS,
        [Where("kind", "in", kinds)],
        order_by="created_at",
        descending=True,
        limit=limit,
    )
    parsed = (_parse(doc) for doc in docs)
    return [doc for doc in parsed if doc is not None]


async def sign_doc(
    store: Store,
    bus: EventBus,
    doc_id: str,
    *,
    role: SignRole,
    name: str,
    actor: str,
) -> SraDraft | VarDraft:
    """Fill one signature line. The line's role must be on the document and still blank."""
    cleaned = " ".join(name.split())
    if not MIN_SIGN_NAME_CHARS <= len(cleaned) <= MAX_SIGN_NAME_CHARS or not cleaned.isprintable():
        raise InvalidSignature(
            [f"name: {MIN_SIGN_NAME_CHARS} to {MAX_SIGN_NAME_CHARS} printable characters"]
        )
    async with _lock(store):
        current = await get_doc(store, doc_id)
        if current is None:
            raise DocNotFound(doc_id)
        line = next((item for item in current.signatures if item.role is role), None)
        if line is None:
            raise InvalidSignature([f"role: {role.value} has no signature line on this document"])
        if line.signed_at is not None:
            raise AlreadySigned([f"role: {role.value} has already signed this document"])
        at = timeutil.now()
        lines = [
            item.model_copy(update={"signed_name": cleaned, "signed_at": at, "recorded_by": actor})
            if item.role is role
            else item
            for item in current.signatures
        ]
        complete = all(item.signed_at is not None for item in lines)
        signed = current.model_copy(
            update={
                "signatures": lines,
                "version": current.version + 1,
                "updated_at": at,
                "status": DocStatus.SIGNED if complete else DocStatus.DRAFT,
            }
        )
        await _put(store, signed)
        await audit.record(
            store,
            actor=actor,
            action=AuditAction.DOC_SIGNED,
            before=_audit_view(current),
            after={**_audit_view(signed), "role": role.value, "signed_name": cleaned},
            input_hashes=[signed.input_hash],
            note=f"{signed.kind} {signed.id} signed as {role.value}",
        )
    bus.publish(SseEvent.DOC, DocSummary.of(signed))
    return signed


def _audit_view(doc: SraDraft | VarDraft) -> dict[str, Any]:
    subject = (
        {"region": doc.region_key} if isinstance(doc, SraDraft) else {"flight_id": doc.flight_id}
    )
    return {
        "doc_id": doc.id,
        "kind": doc.kind,
        "status": doc.status.value,
        "version": doc.version,
        "signed_roles": [role.value for role in doc.signed_roles()],
        **subject,
    }


def _parse(stored: dict[str, Any] | None) -> SraDraft | VarDraft | None:
    if stored is None or stored.get("kind") not in _KINDS:
        return None
    try:
        return RegDocAdapter.validate_python(stored)
    except ValidationError:
        logger.warning("stored document %s does not match its model", stored.get("id"))
        return None


def _lock(store: Store) -> asyncio.Lock:
    lock = _locks.get(store)
    if lock is None:
        lock = _locks[store] = asyncio.Lock()
    return lock
