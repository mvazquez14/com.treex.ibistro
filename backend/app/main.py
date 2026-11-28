from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import sentry_sdk
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware

from app.api.deps import SessionDep
from app.api.main import api_router
from app.api.routes import admin, auth, onboarding, public_pages, webhooks
from app.core.config import settings
from app.core.redis import close_redis, get_redis
from app.services.menu_photos import uploads_root
from app.services.onboarding_service import dashboard_destination

FRONTEND_DIR = Path(__file__).parent / "frontend"
_SPA_FALLBACK = (
    '<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">'
    "<title>iBistro</title></head><body>iBistro</body></html>"
)
_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-encoding",
    "content-length",
}


def custom_generate_unique_id(route: APIRoute) -> str:
    tag = route.tags[0] if route.tags else "route"
    return f"{tag}-{route.name}"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    get_redis()
    yield
    await close_redis()


if settings.SENTRY_DSN and settings.FASTAPI_ENV != "development":
    sentry_sdk.init(dsn=str(settings.SENTRY_DSN), enable_tracing=True)

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_HOST],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(
    request: Request, exc: HTTPException
) -> RedirectResponse | JSONResponse:
    if exc.status_code == 401 and request.url.path.startswith("/dashboard"):
        accept = request.headers.get("accept", "")
        if (
            request.headers.get("hx-request")
            or "text/html" in accept
            or "*/*" in accept
        ):
            return RedirectResponse(url="/login", status_code=302)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


app.include_router(auth.router)
app.include_router(webhooks.router)
app.include_router(api_router, prefix=settings.API_V1_STR)
app.include_router(public_pages.router)
app.include_router(admin.router)
app.include_router(onboarding.router)


def _dashboard_file(path: str) -> Response:
    root = FRONTEND_DIR.resolve()
    relative = path.strip("/")
    if relative:
        candidate = (root / relative).resolve()
        if candidate.is_file() and root in candidate.parents:
            return FileResponse(candidate)
    index = root / "index.html"
    if index.is_file():
        return FileResponse(index)
    return HTMLResponse(_SPA_FALLBACK)


async def _proxy_dashboard(request: Request, path: str) -> Response:
    base = settings.VITE_DEV_SERVER.rstrip("/")
    target = f"{base}/dashboard"
    if path:
        target = f"{target}/{path}"
    if request.url.query:
        target = f"{target}?{request.url.query}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            upstream = await client.request(request.method, target)
    except httpx.HTTPError:
        return HTMLResponse(
            "El servidor de Vite no está disponible.",
            status_code=502,
        )
    headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower() not in _HOP_HEADERS
    }
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=headers,
        media_type=upstream.headers.get("content-type"),
    )


def _is_spa_asset(path: str) -> bool:
    return "." in path.rsplit("/", 1)[-1]


@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
async def dashboard_root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard", status_code=302)


@app.api_route("/dashboard", methods=["GET", "HEAD"], include_in_schema=False)
@app.api_route(
    "/dashboard/{path:path}", methods=["GET", "HEAD"], include_in_schema=False
)
async def dashboard_app(
    request: Request, session: SessionDep, path: str = ""
) -> Response:
    if not _is_spa_asset(path):
        destination = await dashboard_destination(request, session)
        if destination:
            return RedirectResponse(url=destination, status_code=302)
    if settings.VITE_DEV_SERVER.strip():
        return await _proxy_dashboard(request, path)
    return _dashboard_file(path)


try:
    app.mount("/uploads", StaticFiles(directory=uploads_root()), name="uploads")
except OSError:
    pass
