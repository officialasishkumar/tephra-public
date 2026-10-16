"""The HTML pages and their redirects: Home, the demo, the Desk, onboarding and the airline
workspace, the Guide, the privacy notice and the printable documents.

Pages are served whatever ``TEPHRA_FEATURES`` says; a page whose feature is off draws one line
and its API refuses. This module never imports ``tephra.api.server`` (the server imports it).
"""

import asyncio
import re
from pathlib import Path
from typing import Final

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, RedirectResponse, Response

from tephra.airline.sessions import read_claims
from tephra.api import ApiError

__all__ = ["WEB_DIR", "router"]

WEB_DIR: Final = Path(__file__).resolve().parent.parent / "web"
_PRINT_DOC_ID = re.compile(r"(?:DOC-|ho_)[0-9a-f]{12}")
ONBOARD_PAGES: Final = frozenset(
    {
        "airline",
        "policy",
        "fleet",
        "network",
        "schedule",
        "feeds",
        "people",
        "assistant",
        "review",
        "done",
    }
)
WORKSPACE_SECTIONS: Final = frozenset({"answers", "feeds", "assistant", "kit"})

router = APIRouter()


async def _page(filename: str) -> FileResponse:
    path = WEB_DIR / filename
    if not await asyncio.to_thread(path.is_file):
        raise ApiError(404, "not_found", "Page not installed")
    return FileResponse(path, media_type="text/html; charset=utf-8")


def _no_such_page() -> ApiError:
    return ApiError(404, "not_found", "No such page")


@router.get("/", include_in_schema=False)
async def home_page(request: Request) -> Response:
    """Home. An old link to the Wall at ``/?...`` lands on the demo with its query kept byte for
    byte (home-boot.js does the same for a hash, which never reaches the server)."""
    query = request.scope["query_string"].decode("latin-1")
    if query:
        return RedirectResponse(f"/demo?{query}", status_code=307)
    return await _page("home.html")


@router.get("/demo", include_in_schema=False)
async def demo_page() -> FileResponse:
    return await _page("index.html")


@router.get("/assistant", include_in_schema=False)
async def assistant_page() -> FileResponse:
    """The TEPHRA Assistant board as a page of its own: the demo's page, which page-mode.js
    switches to the board."""
    return await _page("index.html")


@router.get("/desk", include_in_schema=False)
async def desk_page() -> FileResponse:
    return await _page("desk.html")


@router.get("/guide", include_in_schema=False)
async def guide_page() -> FileResponse:
    return await _page("guide.html")


@router.get("/privacy", include_in_schema=False)
async def privacy_page() -> FileResponse:
    return await _page("privacy.html")


@router.get("/robots.txt", include_in_schema=False)
async def robots_txt() -> Response:
    """The live ash desk is a demo: no search engine should index or follow it."""
    return Response("User-agent: *\nDisallow: /\n", media_type="text/plain; charset=utf-8")


@router.get("/docs/{doc_id}", include_in_schema=False)
async def doc_page(doc_id: str) -> FileResponse:
    """The printable page for an SRA/VAR draft (DOC-...) or a shift handover (ho_...). The page
    reads the id from the last path segment and fetches the JSON itself."""
    if _PRINT_DOC_ID.fullmatch(doc_id) is None:
        raise ApiError(404, "not_found", "No such document")
    return await _page("doc.html")


@router.get("/connect", include_in_schema=False)
async def connect_page(request: Request) -> RedirectResponse:
    """Connect was folded into onboarding: a signed-in airline lands on its Data feeds."""
    target = "/workspace/feeds" if read_claims(request) is not None else "/onboard"
    return RedirectResponse(target, status_code=307)


@router.get("/onboard", include_in_schema=False)
async def onboard_landing() -> FileResponse:
    return await _page("onboard.html")


@router.get("/onboard/{page}", include_in_schema=False)
async def onboard_page(page: str) -> FileResponse:
    if page not in ONBOARD_PAGES:
        raise _no_such_page()
    return await _page("onboard.html")


@router.get("/signin", include_in_schema=False)
@router.get("/signin/recover", include_in_schema=False)
@router.get("/workspace", include_in_schema=False)
async def workspace_page() -> FileResponse:
    return await _page("workspace.html")


@router.get("/workspace/{section}", include_in_schema=False)
async def workspace_section(section: str) -> FileResponse:
    if section not in WORKSPACE_SECTIONS:
        raise _no_such_page()
    return await _page("workspace.html")
