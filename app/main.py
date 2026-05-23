import logging
import multiprocessing
import signal
import sys
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse
from fastapi.responses import HTMLResponse
from fastapi.responses import RedirectResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.routes import (
    auth_router,
    businesses_router,
    chat_router,
    documents_router,
    dbview_router,
    health_router,
    rag_router,
    system_config_router,
    ui_router,
    workspace_config_router,
    workspaces_router,
)
from app.core.config import get_settings
from app.core.crash_logger import crash_logger
from app.core.limiter import limiter

settings = get_settings()

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(filename)s:%(lineno)d | %(funcName)s() | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

OPENAPI_TAGS = [
    {
        "name": "Admin Auth",
        "description": "Authentication and account management endpoints for admin and user creation.",
    },
    {
        "name": "Businesses",
        "description": "Create, list, and inspect business tenants used by the RAG system.",
    },
    {
        "name": "Workspaces",
        "description": "Manage workspaces that belong to a business and group related documents and settings.",
    },
    {
        "name": "Workspace Config",
        "description": "Read and update retrieval, embedding, and chat model configuration for a workspace.",
    },
    {
        "name": "Documents",
        "description": "Upload, inspect, reindex, cancel, reset, and browse documents and chunks for a workspace.",
    },
    {
        "name": "RAG Retrieval",
        "description": "Retrieve the most relevant indexed chunks for a user query in a workspace.",
    },
    {
        "name": "Chat",
        "description": "Generate answers, stream responses, and manage chat history for users and admins.",
    },
    {
        "name": "System Config",
        "description": "Read and update global system values such as the OpenAI API key.",
    },
    {
        "name": "Health",
        "description": "Basic health and uptime validation endpoints.",
    },
]


def signal_handler(signum, frame):
    """Handle termination signals and log crash."""
    logger.critical(f"Received signal {signum}, logging crash before exit...")
    try:
        # Create a dummy exception for logging
        class SignalException(Exception):
            pass
        
        exc = SignalException(f"Application terminated by signal {signum}")
        crash_logger.log_crash(
            exc, type(exc), None,
            context={"signal_number": signum, "signal_name": signal.Signals(signum).name},
            additional_info={"frame_info": str(frame)}
        )
    except Exception as log_error:
        logger.error(f"Failed to log crash on signal: {log_error}")
    
    sys.exit(1)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Register signal handlers for crash logging
    if sys.platform != "win32":  # Signal handlers work differently on Windows
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        # Note: SIGKILL cannot be caught
    
    logger.info("Application starting up...")
    # Use spawn for multiprocessing so PDF extraction subprocesses do not inherit parent memory (avoids 4GB spike)
    try:
        multiprocessing.set_start_method("spawn")
    except RuntimeError:
        pass  # already set (e.g. by uvicorn)
    # Ensure crash/progress log dir exists (so ./logs/crashes appears on host volume)
    try:
        crash_logger.log_dir.mkdir(parents=True, exist_ok=True)
        crash_logger.write_progress("app_started", {"event": "startup"})
    except Exception as e:
        logger.warning(f"Could not init log dir: {e}")

    from app.core.seed import ensure_default_user_tenant
    await ensure_default_user_tenant()

    logger.info("Application startup complete")
    yield
    logger.info("Application shutting down...")


app = FastAPI(
    title=settings.app_name,
    description=(
        "MedQuery RAG API for business, workspace, document, retrieval, and chat management. "
        "Use the grouped Swagger sections to explore admin setup, document ingestion, RAG retrieval, and chat generation flows."
    ),
    openapi_tags=OPENAPI_TAGS,
    openapi_url="/openapi.json",
    docs_url=None,
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.get("/", include_in_schema=False)
async def root_redirect() -> RedirectResponse:
    """Redirect root URL to the UI page."""
    return RedirectResponse(url="/ui", status_code=307)


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html() -> HTMLResponse:
    """Serve Swagger UI and pre-fill Bearer auth from localStorage adminToken."""
    response = get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} - Swagger UI",
        swagger_ui_parameters={"persistAuthorization": True},
    )

    html = response.body.decode("utf-8")
    auto_auth_script = """
<script>
(function () {
    function normalizeToken(raw) {
        if (!raw || typeof raw !== "string") return "";
        return raw.startsWith("Bearer ") ? raw.slice(7).trim() : raw.trim();
    }

    function tryAuthorize(attemptsLeft) {
        if (!window.ui || typeof window.ui.preauthorizeApiKey !== "function") {
            if (attemptsLeft > 0) {
                setTimeout(function () { tryAuthorize(attemptsLeft - 1); }, 200);
            }
            return;
        }

        var token = normalizeToken(localStorage.getItem("adminToken"));
        if (!token) {
            console.warn("[Swagger Docs] No adminToken found in localStorage");
            return;
        }

        console.log("[Swagger Docs] Attempting to authorize with token (length=" + token.length + ")");

        // Try HTTPBearer (FastAPI default for HTTPBearer)
        try {
            window.ui.preauthorizeApiKey("HTTPBearer", token);
            console.log("[Swagger Docs] Successfully authorized HTTPBearer scheme");
        } catch (e) {
            console.log("[Swagger Docs] preauthorizeApiKey failed: " + e.message);
        }

        // Also try authActions.authorize as fallback
        try {
            if (window.ui.authActions && typeof window.ui.authActions.authorize === "function") {
                var auth = {
                    "HTTPBearer": {
                        name: "HTTPBearer",
                        schema: { type: "http", scheme: "bearer" },
                        value: token
                    }
                };
                window.ui.authActions.authorize(auth);
                console.log("[Swagger Docs] authActions.authorize succeeded");
            }
        } catch (e) {
            console.log("[Swagger Docs] authActions.authorize failed: " + e.message);
        }
    }

    tryAuthorize(50);
})();
</script>
"""
    html = html.replace("</body>", auto_auth_script + "\n</body>")
    return HTMLResponse(content=html, status_code=response.status_code)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    logger.warning(
        f"HTTPException: {exc.status_code} - {exc.detail} | "
        f"Path: {request.url.path} | Method: {request.method} | "
        f"Headers: {dict(request.headers)}"
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": exc.status_code, "message": exc.detail, "details": {}},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    exc_type = type(exc)
    exc_message = str(exc)
    exc_traceback = exc.__traceback__
    
    # Determine if this is a critical crash
    is_critical = isinstance(exc, (MemoryError, SystemError, KeyboardInterrupt)) or \
                  "out of memory" in exc_message.lower() or \
                  "killed" in exc_message.lower()
    
    # Log with crash logger
    context = {
        "request_path": request.url.path,
        "request_method": request.method,
        "query_params": dict(request.query_params),
        "client_host": request.client.host if request.client else None,
    }
    
    if is_critical:
        crash_log_file = crash_logger.log_crash(
            exc, exc_type, exc_traceback,
            context=context,
            additional_info={
                "request_headers": dict(request.headers),
                "environment": settings.environment,
            }
        )
        logger.critical(f"CRITICAL CRASH LOGGED: {crash_log_file}")
    else:
        crash_logger.log_error(exc, exc_type, exc_traceback, context=context)
    
    exc_traceback_str = "".join(traceback.format_exception(exc_type, exc, exc_traceback))
    
    logger.error(
        f"Unhandled Exception: {exc_type.__name__} - {exc_message} | "
        f"Path: {request.url.path} | Method: {request.method} | "
        f"Query Params: {dict(request.query_params)} | "
        f"Headers: {dict(request.headers)} | "
        f"Traceback:\n{exc_traceback_str}",
        exc_info=True
    )
    
    return JSONResponse(
        status_code=500,
        content={
            "status": 500,
            "message": "Internal server error",
            "details": {
                "exception_type": exc_type.__name__,
                "exception_message": exc_message,
                "traceback": exc_traceback_str if settings.environment == "development" else None,
            },
        },
    )


@app.exception_handler(RateLimitExceeded)
async def rate_limit_exception_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"status": 429, "message": "Too many requests. Please try again later.", "details": {}},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    validation_errors = exc.errors()
    logger.warning(
        f"ValidationError: {len(validation_errors)} validation error(s) | "
        f"Path: {request.url.path} | Method: {request.method} | "
        f"Query Params: {dict(request.query_params)} | "
        f"Errors: {validation_errors}"
    )
    return JSONResponse(
        status_code=422,
        content={"status": 422, "message": "Validation error", "details": validation_errors},
    )


app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(businesses_router, prefix=settings.api_v1_prefix)
app.include_router(workspaces_router, prefix=settings.api_v1_prefix)
app.include_router(workspace_config_router, prefix=settings.api_v1_prefix)
app.include_router(documents_router, prefix=settings.api_v1_prefix)
app.include_router(rag_router, prefix=settings.api_v1_prefix)
app.include_router(chat_router, prefix=settings.api_v1_prefix)
app.include_router(system_config_router, prefix=settings.api_v1_prefix)
app.include_router(dbview_router, prefix=settings.api_v1_prefix)
app.include_router(health_router, prefix=settings.api_v1_prefix)
app.include_router(ui_router)
