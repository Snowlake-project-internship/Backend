from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import asc, desc, func, or_
from sqlalchemy.orm import Session

from logs.models import AuditLog, ErrorLog, ExecutionLog
from logs.schemas import AuditLogCreate, ErrorLogCreate, ExecutionLogCreate


class LogRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_execution_log(self, payload: ExecutionLogCreate) -> ExecutionLog:
        log = ExecutionLog(**payload.model_dump())
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        return log

    def create_error_log(self, payload: ErrorLogCreate) -> ErrorLog:
        log = ErrorLog(**payload.model_dump())
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        return log

    def create_audit_log(self, payload: AuditLogCreate) -> AuditLog:
        log = AuditLog(**payload.model_dump())
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        return log

    def get_execution_log(
        self,
        log_id: int,
        *,
        organization_id: Optional[int] = None,
        user_id: Optional[int] = None,
    ) -> Optional[ExecutionLog]:
        query = self.db.query(ExecutionLog).filter(ExecutionLog.id == log_id)
        if organization_id is not None:
            query = query.filter(ExecutionLog.organization_id == organization_id)
        if user_id is not None:
            query = query.filter(ExecutionLog.user_id == user_id)
        return query.first()

    def query_execution_logs(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        status: Optional[str] = None,
        operation_type: Optional[str] = None,
        level: Optional[str] = None,
        user_id: Optional[int] = None,
        organization_id: Optional[int] = None,
        request_id: Optional[str] = None,
        session_id: Optional[str] = None,
        table_name: Optional[str] = None,
        service_name: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        search: Optional[str] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[list[ExecutionLog], int]:
        query = self.db.query(ExecutionLog)
        if organization_id is not None:
            query = query.filter(ExecutionLog.organization_id == organization_id)
        if status:
            query = query.filter(ExecutionLog.status == status)
        if operation_type:
            query = query.filter(ExecutionLog.operation_type == operation_type)
        if level:
            query = query.filter(ExecutionLog.level == level)
        if user_id is not None:
            query = query.filter(ExecutionLog.user_id == user_id)
        if request_id:
            query = query.filter(ExecutionLog.request_id == request_id)
        if session_id:
            query = query.filter(ExecutionLog.session_id == session_id)
        if table_name:
            query = query.filter(ExecutionLog.table_name.ilike(f"%{table_name}%"))
        if service_name:
            query = query.filter(ExecutionLog.service_name == service_name)
        if date_from:
            query = query.filter(ExecutionLog.created_at >= date_from)
        if date_to:
            query = query.filter(ExecutionLog.created_at <= date_to)
        if search:
            pattern = f"%{search}%"
            query = query.filter(
                or_(
                    ExecutionLog.query_text.ilike(pattern),
                    ExecutionLog.error_message.ilike(pattern),
                    ExecutionLog.table_name.ilike(pattern),
                    ExecutionLog.workflow_name.ilike(pattern),
                    ExecutionLog.message.ilike(pattern),
                    ExecutionLog.service_name.ilike(pattern),
                )
            )

        total = query.with_entities(func.count(ExecutionLog.id)).scalar() or 0
        allowed_sort_columns = {
            "created_at",
            "duration_ms",
            "operation_type",
            "status",
            "table_name",
            "user_id",
            "service_name",
        }
        sort_column = getattr(ExecutionLog, sort_by, ExecutionLog.created_at) if sort_by in allowed_sort_columns else ExecutionLog.created_at
        order = asc(sort_column) if sort_order.lower() == "asc" else desc(sort_column)
        items = query.order_by(order).offset((page - 1) * page_size).limit(page_size).all()
        return items, total

    def query_error_logs(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        organization_id: Optional[int] = None,
        user_id: Optional[int] = None,
        status: Optional[str] = None,
        operation_type: Optional[str] = None,
        table_name: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        search: Optional[str] = None,
    ) -> tuple[list[ErrorLog], int]:
        query = self.db.query(ErrorLog)
        if organization_id is not None:
            query = query.filter(ErrorLog.organization_id == organization_id)
        if user_id is not None:
            query = query.filter(ErrorLog.user_id == user_id)
        if operation_type:
            query = query.filter(ErrorLog.operation_type == operation_type)
        if date_from:
            query = query.filter(ErrorLog.created_at >= date_from)
        if date_to:
            query = query.filter(ErrorLog.created_at <= date_to)
        if table_name:
            pattern = f"%{table_name}%"
            query = query.filter(or_(ErrorLog.query_text.ilike(pattern), ErrorLog.error_path.ilike(pattern)))
        if search:
            pattern = f"%{search}%"
            query = query.filter(
                or_(
                    ErrorLog.error_message.ilike(pattern),
                    ErrorLog.error_type.ilike(pattern),
                    ErrorLog.exception_type.ilike(pattern),
                    ErrorLog.query_text.ilike(pattern),
                    ErrorLog.workflow_name.ilike(pattern),
                )
            )
        total = query.with_entities(func.count(ErrorLog.id)).scalar() or 0
        items = query.order_by(desc(ErrorLog.created_at)).offset((page - 1) * page_size).limit(page_size).all()
        return items, total
