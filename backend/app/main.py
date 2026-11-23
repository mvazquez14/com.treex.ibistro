from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import sentry_sdk
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware

from app.api.main import api_router
from app.api.routes import admin, auth, dashboard, public_pages, webhooks
from app.core.config import settings
from app.core.redis import close_redis, get_redis

FRONTEND_DIR = Path(__file__).parent / "frontend"
UPLOADS_DIR = Path("/app/uploads")


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
        if request.headers.get("hx-request") or "text/html" in accept or "*/*" in accept:
            return RedirectResponse(url="/login", status_code=302)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


app.include_router(auth.router)
app.include_router(webhooks.router)
app.include_router(api_router, prefix=settings.API_V1_STR)
app.include_router(public_pages.router)
app.include_router(dashboard.router)
app.include_router(admin.router)
if UPLOADS_DIR.is_dir():
    app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")
if FRONTEND_DIR.is_dir():
    app.frontend("/", directory=FRONTEND_DIR)
