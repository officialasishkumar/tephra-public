"""Regulator paperwork routes: SRA and VAR drafts, their listing and their sign-off.

``router`` is mounted under ``/api`` by the app factory. Reading is public like advisories;
drafting and signing need a desk session, and a POST needs the CSRF guard. A draft goes
nowhere outside TEPHRA: signing records who signed and when, and that is all.
"""

import re
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import Field

from tephra.api import ApiError
from tephra.api.auth import require_csrf
from tephra.api.server import DeskSession, RuntimeDep, _json
from tephra.models import TephraModel
from tephra.regdocs.evidence import NoActiveVolcano, UnknownRegion
from tephra.regdocs.models import DocKind, DocModel, DocSummary, SignRole, SraDraft, VarDraft
from tephra.regdocs.narrative import AiUnavailable
from tephra.regdocs.registry import (
    AlreadySigned,
    DocNotFound,
    InvalidSignature,
    get_doc,
    list_docs,
    sign_doc,
)
from tephra.regdocs.sra import draft_sra
from tephra.regdocs.var import FlightNotExposed, draft_var

__all__ = ["router"]

_DOC_ID = re.compile(r"DOC-[0-9a-f]{12}")
Limit = Annotated[int, Query(ge=1, le=200)]

router = APIRouter()


class SraRequest(TephraModel):
    region: str = Field(pattern=r"^[a-z_]{1,32}$", description="A region key, e.g. 'java_bali'")


class VarRequest(TephraModel):
    flight_id: str = Field(pattern=r"^[0-9a-f]{6}:[0-9]{1,10}$", description="'<hex>:<volcano_id>'")


class SignRequest(TephraModel):
    name: str = Field(max_length=200, description="Who signs, as they want it printed")
    role: SignRole


class DocList(TephraModel):
    docs: list[DocSummary]


def _check_doc_id(doc_id: str) -> None:
    if _DOC_ID.fullmatch(doc_id) is None:
        raise ApiError(404, "not_found", "No such document")


@router.get("/docs", response_model=DocList)
async def get_docs(runtime: RuntimeDep, kind: DocKind | None = None, limit: Limit = 50) -> Response:
    docs = await list_docs(runtime.store, kind=kind, limit=limit)
    return _json(DocList(docs=[DocSummary.of(doc) for doc in docs]))


@router.get("/docs/{doc_id}", response_model=DocModel)
async def get_one_doc(doc_id: str, runtime: RuntimeDep) -> Response:
    _check_doc_id(doc_id)
    doc = await get_doc(runtime.store, doc_id)
    if doc is None:
        raise ApiError(404, "not_found", "No such document")
    return _json(doc)


@router.post("/desk/docs/sra", response_model=SraDraft, dependencies=[Depends(require_csrf)])
async def draft_sra_route(body: SraRequest, session: DeskSession, runtime: RuntimeDep) -> Response:
    try:
        doc = await draft_sra(runtime, body.region, actor=f"desk:{session.name}")
    except UnknownRegion:
        raise ApiError(404, "not_found", "No such region") from None
    except NoActiveVolcano:
        raise ApiError(
            409, "no_active_volcano", "No volcano of this region is in the current picture"
        ) from None
    except AiUnavailable as exc:
        raise ApiError(503, "ai_unavailable", str(exc)) from None
    return _json(doc)


@router.post("/desk/docs/var", response_model=VarDraft, dependencies=[Depends(require_csrf)])
async def draft_var_route(body: VarRequest, session: DeskSession, runtime: RuntimeDep) -> Response:
    try:
        doc = await draft_var(runtime, body.flight_id, actor=f"desk:{session.name}")
    except FlightNotExposed:
        raise ApiError(404, "not_found", "That flight is not in the current exposure set") from None
    return _json(doc)


@router.post(
    "/desk/docs/{doc_id}/sign",
    response_model=DocModel,
    dependencies=[Depends(require_csrf)],
)
async def sign_route(
    doc_id: str, body: SignRequest, session: DeskSession, runtime: RuntimeDep
) -> Response:
    _check_doc_id(doc_id)
    try:
        doc = await sign_doc(
            runtime.store,
            runtime.bus,
            doc_id,
            role=body.role,
            name=body.name,
            actor=f"desk:{session.name}",
        )
    except DocNotFound:
        raise ApiError(404, "not_found", "No such document") from None
    except AlreadySigned as exc:
        raise ApiError(409, "invalid_transition", str(exc), problems=exc.problems) from None
    except InvalidSignature as exc:
        raise ApiError(
            422, "validation_failed", "Signature rejected", problems=exc.problems
        ) from None
    return _json(doc)
