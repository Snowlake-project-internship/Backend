from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from database import Base
from models.user import Organization, User  # noqa: F401


class ExecutionLog(Base):
    __tablename__ = "execution_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    request_id = Column(String(64), nullable=True, index=True)
    session_id = Column(String(64), nullable=True, index=True)
    workflow_name = Column(String(255), nullable=True, index=True)
    iteration_name = Column(String(255), nullable=True, index=True)
    operation_type = Column(String(80), nullable=False, index=True)
    status = Column(String(40), nullable=False, index=True)
    level = Column(String(40), nullable=False, index=True)
    api_endpoint = Column(String(500), nullable=True)
    service_name = Column(String(255), nullable=True, index=True)
    table_name = Column(String(500), nullable=True, index=True)
    database_name = Column(String(255), nullable=True, index=True)
    schema_name = Column(String(255), nullable=True, index=True)
    query_text = Column(Text, nullable=True)
    snowflake_query_id = Column(String(255), nullable=True, index=True)
    rows_affected = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=True, index=True)
    message = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    error_path = Column(String(1000), nullable=True)
    details = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    errors = relationship("ErrorLog", back_populates="execution_log", cascade="all, delete-orphan")
    user = relationship("User", foreign_keys=[user_id])
    organization = relationship("Organization", foreign_keys=[organization_id])


class ErrorLog(Base):
    __tablename__ = "error_logs"

    id = Column(Integer, primary_key=True, index=True)
    execution_log_id = Column(
        Integer,
        ForeignKey("execution_logs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    request_id = Column(String(64), nullable=True, index=True)
    session_id = Column(String(64), nullable=True, index=True)
    level = Column(String(40), nullable=False, index=True)
    operation_type = Column(String(80), nullable=True, index=True)
    api_endpoint = Column(String(500), nullable=True)
    service_name = Column(String(255), nullable=True, index=True)
    error_type = Column(String(255), nullable=True, index=True)
    exception_type = Column(String(255), nullable=True, index=True)
    function_name = Column(String(255), nullable=True, index=True)
    error_message = Column(Text, nullable=False)
    error_path = Column(String(1000), nullable=True)
    stacktrace = Column(Text, nullable=True)
    query_text = Column(Text, nullable=True)
    snowflake_query_id = Column(String(255), nullable=True, index=True)
    workflow_name = Column(String(255), nullable=True, index=True)
    iteration_name = Column(String(255), nullable=True, index=True)
    details = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    execution_log = relationship("ExecutionLog", back_populates="errors")
    user = relationship("User", foreign_keys=[user_id])
    organization = relationship("Organization", foreign_keys=[organization_id])


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    request_id = Column(String(64), nullable=True, index=True)
    session_id = Column(String(64), nullable=True, index=True)
    action = Column(String(120), nullable=False, index=True)
    resource_type = Column(String(120), nullable=True, index=True)
    resource_name = Column(String(500), nullable=True)
    api_endpoint = Column(String(500), nullable=True)
    status = Column(String(40), nullable=False, index=True)
    ip_address = Column(String(80), nullable=True)
    user_agent = Column(String(1000), nullable=True)
    details = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = relationship("User", foreign_keys=[user_id])
    organization = relationship("Organization", foreign_keys=[organization_id])


Index("ix_execution_logs_status_created", ExecutionLog.status, ExecutionLog.created_at)
Index("ix_execution_logs_operation_created", ExecutionLog.operation_type, ExecutionLog.created_at)
Index("ix_execution_logs_user_created", ExecutionLog.user_id, ExecutionLog.created_at)
Index("ix_execution_logs_org_created", ExecutionLog.organization_id, ExecutionLog.created_at)
Index("ix_execution_logs_org_status_created", ExecutionLog.organization_id, ExecutionLog.status, ExecutionLog.created_at)
Index("ix_execution_logs_org_operation_created", ExecutionLog.organization_id, ExecutionLog.operation_type, ExecutionLog.created_at)
Index("ix_error_logs_level_created", ErrorLog.level, ErrorLog.created_at)
Index("ix_error_logs_org_created", ErrorLog.organization_id, ErrorLog.created_at)
Index("ix_audit_logs_action_created", AuditLog.action, AuditLog.created_at)
Index("ix_audit_logs_org_created", AuditLog.organization_id, AuditLog.created_at)
