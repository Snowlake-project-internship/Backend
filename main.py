import logging
import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from database import Base, engine, ensure_metadata_schema
from logs import AuditLog, ErrorLog, ExecutionLog  # noqa: F401
from logs.constants import LogLevel
from logs.service import LoggerService
from logs.utils import error_path_from_exception, exception_type_name, function_name_from_exception, stacktrace_from_exception
from middleware.logging_middleware import LoggingMiddleware
from models import Feedback, ImportFile, User  # noqa: F401
from routes.auth import router as auth_router
from routes.chat import router as chat_router
from routes.dashboard import router as dashboard_router
from routes.imports import router as imports_router
from routes.logfiles import router as logfiles_router
from routes.logs import router as logs_router
from routes.snowflake import router as snowflake_router
from routes.users import router as users_router
from services.snowflake_history_service import run_periodic_snowflake_history_sync

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    history_sync_task = None
    try:
        Base.metadata.create_all(bind=engine)
        ensure_metadata_schema()
        if os.getenv("SNOWFLAKE_HISTORY_SYNC_ENABLED", "true").lower() in {"1", "true", "yes"}:
            history_sync_task = asyncio.create_task(run_periodic_snowflake_history_sync())
    except Exception:
        logger.exception("PostgreSQL metadata tables could not be initialized.")
    try:
        yield
    finally:
        if history_sync_task:
            history_sync_task.cancel()
            try:
                await history_sync_task
            except asyncio.CancelledError:
                pass


app = FastAPI(
    title="Snowflake Excel Import Backend",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(LoggingMiddleware)

app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(users_router, prefix="/api/users", tags=["users"])
app.include_router(imports_router, prefix="/api/imports", tags=["imports"])
app.include_router(dashboard_router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(chat_router, prefix="/api/chat", tags=["chat"])
app.include_router(logs_router, prefix="/api/logs", tags=["logs"])
app.include_router(logfiles_router, prefix="/api/logfiles", tags=["logfiles"])
app.include_router(snowflake_router, prefix="/api/snowflake", tags=["snowflake"])


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_path = error_path_from_exception(exc, f"{request.method} {request.url.path}")
    LoggerService.log_failure(
        operation_type="BACKEND_EXCEPTION",
        service_name="FastAPI",
        error_message=str(exc),
        error_path=error_path,
        details={"query_params": dict(request.query_params)},
    )
    LoggerService.log_error(
        LoggerService.error_from_context(
            level=LogLevel.ERROR,
            operation_type="BACKEND_EXCEPTION",
            service_name="FastAPI",
            api_endpoint=str(request.url.path),
            error_type=exception_type_name(exc),
            exception_type=exception_type_name(exc),
            error_message=str(exc),
            error_path=error_path,
            function_name=function_name_from_exception(exc),
            stacktrace=stacktrace_from_exception(exc),
            details={"query_params": dict(request.query_params)},
        )
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.get("/")
def root():
    return {"message": "Backend OK", "docs": "/docs"}
