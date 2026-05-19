from __future__ import annotations

import uuid

from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from services.auth_service import ALGORITHM, SECRET_KEY
from logs.constants import ExecutionStatus, LogLevel, OperationType
from logs.context import endpoint_ctx, organization_id_ctx, request_id_ctx, session_id_ctx, user_id_ctx, user_role_ctx
from logs.service import LoggerService
from logs.utils import (
    duration_ms,
    error_path_from_exception,
    exception_type_name,
    function_name_from_exception,
    now_ms,
    stacktrace_from_exception,
)


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        session_id = request.headers.get("X-Session-ID")
        identity = self._resolve_identity(request)
        user_id = identity.get("user_id")
        organization_id = identity.get("organization_id")
        user_role = identity.get("role")

        request.state.request_id = request_id
        request.state.user_id = user_id
        request.state.organization_id = organization_id
        request_id_token = request_id_ctx.set(request_id)
        session_id_token = session_id_ctx.set(session_id)
        user_id_token = user_id_ctx.set(user_id)
        organization_id_token = organization_id_ctx.set(organization_id)
        user_role_token = user_role_ctx.set(user_role)
        endpoint_token = endpoint_ctx.set(str(request.url.path))
        start = now_ms()

        try:
            response = await call_next(request)
            status = ExecutionStatus.SUCCESS if response.status_code < 400 else ExecutionStatus.FAILED
            level = LogLevel.INFO if response.status_code < 400 else LogLevel.ERROR
            response.headers["X-Request-ID"] = request_id
            LoggerService.log_execution(
                LoggerService.execution_from_context(
                    operation_type=OperationType.API_REQUEST,
                    status=status,
                    level=level,
                    api_endpoint=str(request.url.path),
                    service_name="FastAPI",
                    duration_ms=duration_ms(start),
                    message=f"{request.method} {request.url.path} returned {response.status_code}",
                    details={
                        "method": request.method,
                        "status_code": response.status_code,
                        "client": request.client.host if request.client else None,
                    },
                )
            )
            return response
        except Exception as exc:
            elapsed_ms = duration_ms(start)
            LoggerService.log_execution(
                LoggerService.execution_from_context(
                    operation_type=OperationType.API_REQUEST,
                    status=ExecutionStatus.FAILED,
                    level=LogLevel.ERROR,
                    api_endpoint=str(request.url.path),
                    service_name="FastAPI",
                    duration_ms=elapsed_ms,
                    error_message=str(exc),
                    error_path=error_path_from_exception(exc, f"{request.method} {request.url.path}"),
                    details={
                        "method": request.method,
                        "client": request.client.host if request.client else None,
                    },
                )
            )
            LoggerService.log_error(
                LoggerService.error_from_context(
                    operation_type=OperationType.API_REQUEST,
                    level=LogLevel.ERROR,
                    api_endpoint=str(request.url.path),
                    service_name="FastAPI",
                    error_type=exception_type_name(exc),
                    exception_type=exception_type_name(exc),
                    error_message=str(exc),
                    error_path=error_path_from_exception(exc, f"{request.method} {request.url.path}"),
                    function_name=function_name_from_exception(exc),
                    stacktrace=stacktrace_from_exception(exc),
                )
            )
            raise
        finally:
            request_id_ctx.reset(request_id_token)
            session_id_ctx.reset(session_id_token)
            user_id_ctx.reset(user_id_token)
            organization_id_ctx.reset(organization_id_token)
            user_role_ctx.reset(user_role_token)
            endpoint_ctx.reset(endpoint_token)

    @staticmethod
    def _resolve_identity(request: Request) -> dict:
        user_id_header = request.headers.get("X-User-ID")
        identity = {"user_id": int(user_id_header) if user_id_header and user_id_header.isdigit() else None}

        organization_id_header = request.headers.get("X-Organization-ID")
        if organization_id_header and organization_id_header.isdigit():
            identity["organization_id"] = int(organization_id_header)
        role_header = request.headers.get("X-User-Role")
        if role_header:
            identity["role"] = role_header

        if user_id_header and user_id_header.isdigit():
            identity["user_id"] = int(user_id_header)

        authorization = request.headers.get("Authorization", "")
        if not authorization.lower().startswith("bearer "):
            return identity

        token = authorization.split(" ", 1)[1].strip()
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        except JWTError:
            return identity

        subject = payload.get("sub")
        if isinstance(subject, str) and subject.isdigit():
            identity["user_id"] = int(subject)
        organization_id = payload.get("organization_id")
        if isinstance(organization_id, int):
            identity["organization_id"] = organization_id
        elif isinstance(organization_id, str) and organization_id.isdigit():
            identity["organization_id"] = int(organization_id)
        role = payload.get("role")
        if isinstance(role, str):
            identity["role"] = role
        return identity
