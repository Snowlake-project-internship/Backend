from __future__ import annotations

from contextvars import ContextVar
from typing import Optional


request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
session_id_ctx: ContextVar[Optional[str]] = ContextVar("session_id", default=None)
user_id_ctx: ContextVar[Optional[int]] = ContextVar("user_id", default=None)
organization_id_ctx: ContextVar[Optional[int]] = ContextVar("organization_id", default=None)
user_role_ctx: ContextVar[Optional[str]] = ContextVar("user_role", default=None)
endpoint_ctx: ContextVar[Optional[str]] = ContextVar("endpoint", default=None)


def get_log_context() -> dict:
    return {
        "request_id": request_id_ctx.get(),
        "session_id": session_id_ctx.get(),
        "user_id": user_id_ctx.get(),
        "organization_id": organization_id_ctx.get(),
        "api_endpoint": endpoint_ctx.get(),
    }


def get_user_role() -> Optional[str]:
    return user_role_ctx.get()
