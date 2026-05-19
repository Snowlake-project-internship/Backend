from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class ExecutionLogCreate(BaseModel):
    user_id: Optional[int] = None
    organization_id: Optional[int] = None
    request_id: Optional[str] = None
    session_id: Optional[str] = None
    workflow_name: Optional[str] = None
    iteration_name: Optional[str] = None
    operation_type: str
    status: str
    level: str = "INFO"
    api_endpoint: Optional[str] = None
    service_name: Optional[str] = None
    table_name: Optional[str] = None
    database_name: Optional[str] = None
    schema_name: Optional[str] = None
    query_text: Optional[str] = None
    snowflake_query_id: Optional[str] = None
    rows_affected: Optional[int] = None
    duration_ms: Optional[int] = None
    message: Optional[str] = None
    error_message: Optional[str] = None
    error_path: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None


class ErrorLogCreate(BaseModel):
    execution_log_id: Optional[int] = None
    user_id: Optional[int] = None
    organization_id: Optional[int] = None
    request_id: Optional[str] = None
    session_id: Optional[str] = None
    level: str = "ERROR"
    operation_type: Optional[str] = None
    api_endpoint: Optional[str] = None
    service_name: Optional[str] = None
    error_type: Optional[str] = None
    exception_type: Optional[str] = None
    function_name: Optional[str] = None
    error_message: str
    error_path: Optional[str] = None
    stacktrace: Optional[str] = None
    query_text: Optional[str] = None
    snowflake_query_id: Optional[str] = None
    workflow_name: Optional[str] = None
    iteration_name: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None


class AuditLogCreate(BaseModel):
    user_id: Optional[int] = None
    organization_id: Optional[int] = None
    request_id: Optional[str] = None
    session_id: Optional[str] = None
    action: str
    resource_type: Optional[str] = None
    resource_name: Optional[str] = None
    api_endpoint: Optional[str] = None
    status: str
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None


class ExecutionLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: Optional[int] = None
    organization_id: Optional[int] = None
    request_id: Optional[str] = None
    session_id: Optional[str] = None
    workflow_name: Optional[str] = None
    iteration_name: Optional[str] = None
    operation_type: str
    status: str
    level: str
    api_endpoint: Optional[str] = None
    service_name: Optional[str] = None
    table_name: Optional[str] = None
    database_name: Optional[str] = None
    schema_name: Optional[str] = None
    query_text: Optional[str] = None
    snowflake_query_id: Optional[str] = None
    rows_affected: Optional[int] = None
    duration_ms: Optional[int] = None
    message: Optional[str] = None
    error_message: Optional[str] = None
    error_path: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    created_at: datetime


class ErrorLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    execution_log_id: Optional[int] = None
    user_id: Optional[int] = None
    organization_id: Optional[int] = None
    request_id: Optional[str] = None
    session_id: Optional[str] = None
    level: str
    operation_type: Optional[str] = None
    api_endpoint: Optional[str] = None
    service_name: Optional[str] = None
    error_type: Optional[str] = None
    exception_type: Optional[str] = None
    function_name: Optional[str] = None
    error_message: str
    error_path: Optional[str] = None
    stacktrace: Optional[str] = None
    query_text: Optional[str] = None
    snowflake_query_id: Optional[str] = None
    workflow_name: Optional[str] = None
    iteration_name: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    created_at: datetime


class PaginatedExecutionLogs(BaseModel):
    items: List[ExecutionLogResponse]
    total: int
    page: int
    page_size: int
