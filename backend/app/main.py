import asyncio
from contextlib import asynccontextmanager
import logging

from fastapi import APIRouter, FastAPI, Request

from app.api import ai, analytics, auth, automation, collab, reminders, conversations, email_accounts, workspace
from app.automation.scheduler import tick as automation_tick
from app.services.ai_triage import process_pending_task
from app.core.config import get_settings
from app.core.errors import error_response, register_error_handlers
from app.services.email_sync import import_pending_history, sync_all_active_accounts

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    stop_event = asyncio.Event()

    async def _sync_loop():
        await asyncio.sleep(2)
        while not stop_event.is_set():
            try:
                await asyncio.to_thread(sync_all_active_accounts, limit_per_account=30)
            except Exception as e:
                logger.warning("Background email sync loop error: %s", e)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=60)
            except asyncio.TimeoutError:
                pass

    async def _import_loop():
        # Older mail comes in page after page; when every mailbox is complete, look again every 30 seconds.
        await asyncio.sleep(4)
        while not stop_event.is_set():
            more = False
            try:
                more = await asyncio.to_thread(import_pending_history)
            except Exception as e:
                logger.warning("Background import loop error: %s", e)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=3 if more else 30)
            except asyncio.TimeoutError:
                pass

    async def _automation_loop():
        # Rules that failed are tried again here; new mail runs its rules straight after it is stored.
        await asyncio.sleep(6)
        while not stop_event.is_set():
            try:
                await asyncio.to_thread(automation_tick)
            except Exception as e:
                logger.warning("Automation retry loop error: %s", e)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=30)
            except asyncio.TimeoutError:
                pass

    async def _ai_loop():
        # Emails waiting to be analysed live in the database, so nothing is lost across a restart.
        await asyncio.sleep(8)
        while not stop_event.is_set():
            try:
                await asyncio.to_thread(process_pending_task)
            except Exception as e:
                logger.warning("AI loop error: %s", e)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=20)
            except asyncio.TimeoutError:
                pass

    tasks = [asyncio.create_task(_sync_loop()), asyncio.create_task(_import_loop()), asyncio.create_task(_automation_loop()), asyncio.create_task(_ai_loop())]
    try:
        yield
    finally:
        stop_event.set()
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass


MAX_REQUEST_BYTES = 30 * 1024 * 1024


def create_app() -> FastAPI:
    settings = get_settings()
    logging.getLogger("app").setLevel(settings.log_level.upper())

    docs = None if settings.is_production else "/api/docs"
    app = FastAPI(
        title="Email Management API",
        docs_url=docs,
        redoc_url=None,
        openapi_url=None if settings.is_production else "/api/openapi.json",
        lifespan=lifespan,
    )
    register_error_handlers(app)

    @app.middleware("http")
    async def same_origin_only(request: Request, call_next):
        # The session lives in a cookie, so a request that changes something must come
        # from our own web app. Browsers always send Origin on such requests.
        origin = request.headers.get("origin")
        if request.method in UNSAFE_METHODS:
            if origin and origin.rstrip("/") not in settings.allowed_origins:
                return error_response(403, "ORIGIN_NOT_ALLOWED", "This request did not come from the app.")
            # A second, independent signal browsers send: the request was started by another site.
            if request.headers.get("sec-fetch-site") == "cross-site":
                return error_response(403, "ORIGIN_NOT_ALLOWED", "This request did not come from the app.")
            # Nothing this API accepts is anywhere near this size (attachments are capped at 18 MB).
            declared = request.headers.get("content-length", "")
            if declared.isdigit() and int(declared) > MAX_REQUEST_BYTES:
                return error_response(413, "REQUEST_TOO_LARGE", "That request is too large.")
        response = await call_next(request)
        # Told to every browser: do not guess file types, do not show us inside another site's frame,
        # do not pass our addresses on (a password-reset link carries its token in the address).
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")
        if settings.is_production:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
            response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        return response

    @app.get("/api/healthz", tags=["health"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    v1 = APIRouter(prefix="/api/v1")
    v1.include_router(auth.router)
    v1.include_router(workspace.router)
    v1.include_router(email_accounts.router)
    v1.include_router(conversations.router)
    v1.include_router(collab.router)
    v1.include_router(automation.router)
    v1.include_router(ai.router)
    v1.include_router(reminders.router)
    v1.include_router(analytics.router)
    app.include_router(v1)
    return app


app = create_app()
