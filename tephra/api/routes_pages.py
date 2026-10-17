"""The HTML pages and their redirects: Home, the demo, the Desk, onboarding and the airline
workspace, the Guide, the privacy notice and the printable documents.

Pages are served whatever ``TEPHRA_FEATURES`` says; a page whose feature is off draws one line
and its API refuses. The hosted pages (an airline's ``/a/<ICAO>/...``, ``/join``, ``/admin``)
are the exception: with ``hosted`` off their router is not included at all. An airline's pages
are the site's own shells, the same for every ICAO: whether the reader is a member is the API's
answer.
This module never imports ``tephra.api.server`` (the server imports it).
"""

import asyncio
import re
from pathlib import Path
from typing import Final
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, RedirectResponse, Response

from tephra.airline.sessions import read_claims
from tephra.api import ApiError

__all__ = ["WEB_DIR", "hosted_router", "router"]

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
WORKSPACE_SECTIONS: Final = frozenset({"answers", "feeds", "assistant"})
SETTINGS_TABS: Final = frozenset({"policy", "assistant", "people", "record"})
_TENANT_ICAO: Final = re.compile(r"[A-Z]{3}")
NOINDEX: Final = {"X-Robots-Tag": "noindex"}

router = APIRouter()
hosted_router = APIRouter()
"""The hosted pages, included only with ``hosted`` on (else no route answers them: 404)."""


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


# The privacy notice's hosted-only parts (a fold and a clause), between ``<!-- hosted -->`` and
# ``<!-- /hosted -->`` in the file (a comment, so the markup and its styles stay as they are).
_HOSTED_ONLY: Final = re.compile(r"[ \t]*<!-- hosted -->.*?<!-- /hosted -->\n?", re.S)


def without_hosted(html: str) -> str:
    """A page with its hosted-only parts cut, as it is served with ``hosted`` off."""
    return _HOSTED_ONLY.sub("", html)


@router.get("/privacy", include_in_schema=False)
async def privacy_page(request: Request) -> Response:
    """With ``hosted`` off the notice says nothing of hosted airlines: its hosted-only parts are
    cut before it is served."""
    if "hosted" in request.app.state.settings.features:
        return await _page("privacy.html")
    path = WEB_DIR / "privacy.html"
    if not await asyncio.to_thread(path.is_file):
        raise ApiError(404, "not_found", "Page not installed")
    text = await asyncio.to_thread(path.read_text, encoding="utf-8")
    return Response(without_hosted(text), media_type="text/html; charset=utf-8")


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


# --- hosted airlines (feature "hosted") --------------------------------------------------


def _tenant_guard(request: Request, icao: str) -> RedirectResponse | None:
    """404 unless ``icao`` is three capital letters the path middleware accepted; a reader
    without a valid airline cookie goes to sign-in and comes back."""
    if _TENANT_ICAO.fullmatch(icao) is None or request.scope.get("tephra.tenant_page") != icao:
        raise _no_such_page()
    if read_claims(request) is None:
        target = f"/signin?next={quote(request.url.path, safe='/')}"
        return RedirectResponse(target, status_code=303, headers=NOINDEX)
    return None


async def _tenant_page(request: Request, icao: str, filename: str) -> Response:
    redirect = _tenant_guard(request, icao)
    if redirect is not None:
        return redirect
    response = await _page(filename)
    response.headers.update(NOINDEX)
    return response


@hosted_router.get("/a/{icao}", include_in_schema=False)
async def tenant_root(request: Request, icao: str) -> Response:
    redirect = _tenant_guard(request, icao)
    if redirect is not None:
        return redirect
    return RedirectResponse(f"/a/{icao}/", status_code=308, headers=NOINDEX)


@hosted_router.get("/a/{icao}/", include_in_schema=False)
async def tenant_map(request: Request, icao: str) -> Response:
    return await _tenant_page(request, icao, "index.html")


@hosted_router.get("/a/{icao}/desk", include_in_schema=False)
async def tenant_desk(request: Request, icao: str) -> Response:
    return await _tenant_page(request, icao, "desk.html")


@hosted_router.get("/a/{icao}/feeds", include_in_schema=False)
@hosted_router.get("/a/{icao}/settings", include_in_schema=False)
async def tenant_hosted(request: Request, icao: str) -> Response:
    return await _tenant_page(request, icao, "hosted.html")


@hosted_router.get("/a/{icao}/settings/{tab}", include_in_schema=False)
async def tenant_settings_tab(request: Request, icao: str, tab: str) -> Response:
    if tab not in SETTINGS_TABS:
        _tenant_guard(request, icao)
        raise _no_such_page()
    return await _tenant_page(request, icao, "hosted.html")


@hosted_router.get("/a/{icao}/docs/{doc_id}", include_in_schema=False)
async def tenant_doc(request: Request, icao: str, doc_id: str) -> Response:
    if _PRINT_DOC_ID.fullmatch(doc_id) is None:
        _tenant_guard(request, icao)
        raise ApiError(404, "not_found", "No such document")
    return await _tenant_page(request, icao, "doc.html")


@hosted_router.get("/admin", include_in_schema=False)
@hosted_router.get("/admin/join", include_in_schema=False)
async def admin_page() -> Response:
    """The operators' console; ``/admin/join#<token>`` keeps its token in the fragment."""
    response = await _page("admin.html")
    response.headers.update(NOINDEX)
    return response


@hosted_router.get("/static/kit/{rest:path}", include_in_schema=False)
@hosted_router.head("/static/kit/{rest:path}", include_in_schema=False)
async def kit_files(rest: str) -> Response:
    """With ``hosted`` on, the uploader (``kit/push.py``) is an airline member's download
    (``/a/<ICAO>/api/tenant/feeds/uploader``), never a public static file. Included before the
    ``/static`` mount, so it answers first."""
    raise ApiError(404, "not_found", "No such file")


@hosted_router.get("/join", include_in_schema=False)
async def join_page() -> Response:
    """An invite link, ``/join#<token>``: the workspace page reads the fragment."""
    response = await _page("workspace.html")
    response.headers.update(NOINDEX)
    return response
