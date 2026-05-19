from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import get_db
from logs.constants import ExecutionStatus
from logs.repository import LogRepository
from logs.schemas import ErrorLogResponse, ExecutionLogResponse, PaginatedExecutionLogs
from models.user import User
from services.auth_service import get_current_user, is_organization_admin
from services.snowflake_history_service import SnowflakeHistoryService

router = APIRouter()


def _log_scope(current_user: User, requested_user_id: Optional[int] = None) -> tuple[Optional[int], Optional[int]]:
    if current_user.organization_id is None:
        return current_user.id, None
    if is_organization_admin(current_user):
        return requested_user_id, current_user.organization_id
    return current_user.id, current_user.organization_id


def _logs_to_csv(logs) -> StreamingResponse:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "id",
            "created_at",
            "user_id",
            "organization_id",
            "request_id",
            "operation_type",
            "status",
            "level",
            "api_endpoint",
            "service_name",
            "table_name",
            "duration_ms",
            "rows_affected",
            "snowflake_query_id",
            "message",
            "error_message",
        ]
    )
    for log in logs:
        writer.writerow(
            [
                log.id,
                log.created_at.isoformat() if log.created_at else "",
                log.user_id,
                log.organization_id,
                log.request_id,
                log.operation_type,
                log.status,
                log.level,
                log.api_endpoint,
                log.service_name,
                log.table_name,
                log.duration_ms,
                log.rows_affected,
                log.snowflake_query_id,
                log.message,
                log.error_message,
            ]
        )
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=execution_logs.csv"},
    )


@router.get("", response_model=PaginatedExecutionLogs)
def get_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    status: Optional[str] = None,
    operation_type: Optional[str] = None,
    level: Optional[str] = None,
    user_id: Optional[int] = None,
    request_id: Optional[str] = None,
    session_id: Optional[str] = None,
    table_name: Optional[str] = None,
    service_name: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    search: Optional[str] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    export_csv: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = LogRepository(db)
    scoped_user_id, scoped_organization_id = _log_scope(current_user, user_id)
    items, total = repo.query_execution_logs(
        page=page,
        page_size=page_size,
        status=status,
        operation_type=operation_type,
        level=level,
        user_id=scoped_user_id,
        organization_id=scoped_organization_id,
        request_id=request_id,
        session_id=session_id,
        table_name=table_name,
        service_name=service_name,
        date_from=date_from,
        date_to=date_to,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    if export_csv:
        return _logs_to_csv(items)
    return PaginatedExecutionLogs(items=items, total=total, page=page, page_size=page_size)


@router.get("/errors", response_model=list[ErrorLogResponse])
def get_error_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    user_id: Optional[int] = None,
    operation_type: Optional[str] = None,
    table_name: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = LogRepository(db)
    scoped_user_id, scoped_organization_id = _log_scope(current_user, user_id)
    items, _ = repo.query_error_logs(
        page=page,
        page_size=page_size,
        organization_id=scoped_organization_id,
        user_id=scoped_user_id,
        operation_type=operation_type,
        table_name=table_name,
        date_from=date_from,
        date_to=date_to,
        search=search,
    )
    return items


@router.get("/success", response_model=PaginatedExecutionLogs)
def get_success_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    user_id: Optional[int] = None,
    table_name: Optional[str] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = LogRepository(db)
    scoped_user_id, scoped_organization_id = _log_scope(current_user, user_id)
    items, total = repo.query_execution_logs(
        page=page,
        page_size=page_size,
        status=ExecutionStatus.SUCCESS,
        user_id=scoped_user_id,
        organization_id=scoped_organization_id,
        table_name=table_name,
        search=search,
    )
    return PaginatedExecutionLogs(items=items, total=total, page=page, page_size=page_size)


@router.get("/filters/users")
def get_log_users(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.organization_id is None:
        return [
            {
                "id": current_user.id,
                "username": current_user.username,
                "email": current_user.email,
                "role": current_user.role,
            }
        ]
    query = db.query(User).filter(User.organization_id == current_user.organization_id)
    if not is_organization_admin(current_user):
        query = query.filter(User.id == current_user.id)
    return [
        {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
        }
        for user in query.order_by(User.username.asc()).all()
    ]


@router.post("/sync-snowflake-history")
def sync_snowflake_history(
    minutes: int = Query(60, ge=1, le=1440),
    limit: int = Query(100, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = SnowflakeHistoryService().sync_query_history(
        db,
        user_id=current_user.id,
        organization_id=current_user.organization_id,
        minutes=minutes,
        limit=limit,
    )
    return {
        "success": True,
        "scanned": result.scanned,
        "inserted_execution_logs": result.inserted_execution_logs,
        "inserted_error_logs": result.inserted_error_logs,
        "skipped_existing": result.skipped_existing,
    }


@router.get("/snowflake-history/diagnostics")
def snowflake_history_diagnostics(
    minutes: int = Query(60, ge=1, le=1440),
    current_user: User = Depends(get_current_user),
):
    if not is_organization_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin role required")
    return SnowflakeHistoryService().diagnose_sources(minutes=minutes)


@router.get("/{log_id}", response_model=ExecutionLogResponse)
def get_log(
    log_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scoped_user_id, scoped_organization_id = _log_scope(current_user)
    log = LogRepository(db).get_execution_log(
        log_id,
        organization_id=scoped_organization_id,
        user_id=scoped_user_id,
    )
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")
    return log
