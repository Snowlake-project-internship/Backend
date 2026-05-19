from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from database import SessionLocal
from logs.context import get_log_context
from logs.repository import LogRepository
from logs.schemas import AuditLogCreate, ErrorLogCreate, ExecutionLogCreate
from models.user import User

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="log-writer")


class LoggerService:
    @staticmethod
    def log_execution(payload: ExecutionLogCreate, *, background: bool = True) -> Optional[int]:
        return LoggerService._submit("execution", payload, background=background)

    @staticmethod
    def log_error(payload: Optional[ErrorLogCreate] = None, *, background: bool = True, **kwargs) -> Optional[int]:
        if payload is None:
            payload = LoggerService.error_from_context(**kwargs)
        return LoggerService._submit("error", payload, background=background)

    @staticmethod
    def log_audit(payload: Optional[AuditLogCreate] = None, *, background: bool = True, **kwargs) -> Optional[int]:
        if payload is None:
            payload = LoggerService.audit_from_context(**kwargs)
        return LoggerService._submit("audit", payload, background=background)

    @staticmethod
    def log_success(
        *,
        operation_type: str,
        user_id: Optional[int] = None,
        organization_id: Optional[int] = None,
        query_text: Optional[str] = None,
        table_name: Optional[str] = None,
        database_name: Optional[str] = None,
        schema_name: Optional[str] = None,
        service_name: Optional[str] = None,
        rows_affected: Optional[int] = None,
        snowflake_query_id: Optional[str] = None,
        duration_ms: Optional[int] = None,
        message: Optional[str] = None,
        details: Optional[dict] = None,
        background: bool = False,
    ) -> Optional[int]:
        return LoggerService.log_execution(
            LoggerService.execution_from_context(
                operation_type=operation_type,
                user_id=user_id,
                organization_id=organization_id,
                status="SUCCESS",
                level="INFO",
                service_name=service_name,
                query_text=query_text,
                table_name=table_name,
                database_name=database_name,
                schema_name=schema_name,
                rows_affected=rows_affected,
                snowflake_query_id=snowflake_query_id,
                duration_ms=duration_ms,
                message=message,
                details=details,
            ),
            background=background,
        )

    @staticmethod
    def log_failure(
        *,
        operation_type: str,
        error_message: str,
        user_id: Optional[int] = None,
        organization_id: Optional[int] = None,
        query_text: Optional[str] = None,
        table_name: Optional[str] = None,
        database_name: Optional[str] = None,
        schema_name: Optional[str] = None,
        service_name: Optional[str] = None,
        snowflake_query_id: Optional[str] = None,
        duration_ms: Optional[int] = None,
        error_path: Optional[str] = None,
        details: Optional[dict] = None,
        background: bool = False,
    ) -> Optional[int]:
        return LoggerService.log_execution(
            LoggerService.execution_from_context(
                operation_type=operation_type,
                user_id=user_id,
                organization_id=organization_id,
                status="FAILED",
                level="ERROR",
                service_name=service_name,
                query_text=query_text,
                table_name=table_name,
                database_name=database_name,
                schema_name=schema_name,
                snowflake_query_id=snowflake_query_id,
                duration_ms=duration_ms,
                error_message=error_message,
                error_path=error_path,
                details=details,
            ),
            background=background,
        )

    @staticmethod
    def execution_from_context(**kwargs) -> ExecutionLogCreate:
        context = {key: value for key, value in get_log_context().items() if value is not None}
        context.update({key: value for key, value in kwargs.items() if value is not None})
        return ExecutionLogCreate(**context)

    @staticmethod
    def error_from_context(**kwargs) -> ErrorLogCreate:
        context = {key: value for key, value in get_log_context().items() if value is not None}
        context.update({key: value for key, value in kwargs.items() if value is not None})
        return ErrorLogCreate(**context)

    @staticmethod
    def audit_from_context(**kwargs) -> AuditLogCreate:
        context = {key: value for key, value in get_log_context().items() if value is not None}
        context.update({key: value for key, value in kwargs.items() if value is not None})
        return AuditLogCreate(**context)

    @staticmethod
    def _submit(kind: str, payload, *, background: bool) -> Optional[int]:
        if background:
            _executor.submit(LoggerService._write, kind, payload)
            return None
        return LoggerService._write(kind, payload)

    @staticmethod
    def _write(kind: str, payload) -> Optional[int]:
        db = SessionLocal()
        try:
            LoggerService._enrich_payload(db, payload)
            repo = LogRepository(db)
            if kind == "execution":
                return repo.create_execution_log(payload).id
            elif kind == "error":
                return repo.create_error_log(payload).id
            elif kind == "audit":
                return repo.create_audit_log(payload).id
            return None
        except Exception:
            db.rollback()
            logger.exception("Failed to persist %s log", kind)
            return None
        finally:
            db.close()

    @staticmethod
    def _enrich_payload(db, payload) -> None:
        if getattr(payload, "organization_id", None) is None and getattr(payload, "user_id", None):
            user = db.query(User).filter(User.id == payload.user_id).first()
            if user:
                payload.organization_id = user.organization_id
