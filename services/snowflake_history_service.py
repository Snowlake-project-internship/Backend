from __future__ import annotations

import logging
import os
import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

import snowflake.connector
from dotenv import load_dotenv
from snowflake.connector import DictCursor
from sqlalchemy.orm import Session

from logs.constants import ExecutionStatus, LogLevel
from logs.models import ExecutionLog
from logs.repository import LogRepository
from logs.schemas import ErrorLogCreate, ExecutionLogCreate
from logs.utils import infer_operation_type, infer_table_name
from database import SessionLocal

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SnowflakeHistorySyncResult:
    scanned: int
    inserted_execution_logs: int
    inserted_error_logs: int
    skipped_existing: int


class SnowflakeHistoryService:
    """
    Imports Snowflake Query History into PostgreSQL logs.

    This is the only way to observe queries executed directly in the Snowflake UI,
    because those queries never pass through FastAPI/SnowflakeService.
    """

    def __init__(self) -> None:
        self.history_database = os.getenv("SNOWFLAKE_HISTORY_DATABASE", "IDRISSI")

    def _connect(self):
        required = {
            "user": os.getenv("SNOWFLAKE_USER"),
            "password": os.getenv("SNOWFLAKE_PASSWORD"),
            "account": os.getenv("SNOWFLAKE_ACCOUNT"),
            "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE"),
            "role": os.getenv("SNOWFLAKE_ROLE"),
        }
        missing = [key.upper() for key, value in required.items() if not value]
        if missing:
            raise RuntimeError(f"Missing Snowflake environment variables: {', '.join(missing)}")
        return snowflake.connector.connect(**required)

    def sync_query_history(
        self,
        db: Session,
        *,
        user_id: Optional[int],
        organization_id: Optional[int],
        minutes: int = 60,
        limit: int = 100,
    ) -> SnowflakeHistorySyncResult:
        minutes = max(1, min(minutes, 24 * 60))
        limit = max(1, min(limit, 1000))
        rows = self._fetch_history(minutes=minutes, limit=limit)
        repo = LogRepository(db)

        inserted_execution_logs = 0
        inserted_error_logs = 0
        skipped_existing = 0

        for row in rows:
            query_id = row.get("QUERY_ID")
            if not query_id:
                continue
            exists = (
                db.query(ExecutionLog.id)
                .filter(ExecutionLog.snowflake_query_id == query_id)
                .first()
            )
            if exists:
                skipped_existing += 1
                continue

            query_text = row.get("QUERY_TEXT") or ""
            status = self._map_status(row.get("EXECUTION_STATUS"))
            operation_type = self._map_operation(row.get("QUERY_TYPE"), query_text)
            table_name = infer_table_name(query_text)
            created_at = self._as_naive_datetime(row.get("START_TIME"))
            duration_ms = self._as_int(row.get("TOTAL_ELAPSED_TIME"))
            error_message = row.get("ERROR_MESSAGE")

            execution_log = repo.create_execution_log(
                ExecutionLogCreate(
                    user_id=user_id,
                    organization_id=organization_id,
                    operation_type=operation_type,
                    status=status,
                    level=LogLevel.ERROR if status == ExecutionStatus.FAILED else LogLevel.INFO,
                    service_name="SnowflakeQueryHistory",
                    api_endpoint="SNOWFLAKE_UI",
                    database_name=row.get("DATABASE_NAME"),
                    schema_name=row.get("SCHEMA_NAME"),
                    table_name=table_name,
                    query_text=query_text,
                    snowflake_query_id=query_id,
                    rows_affected=self._as_int(row.get("ROWS_PRODUCED")),
                    duration_ms=duration_ms,
                    error_message=error_message if status == ExecutionStatus.FAILED else None,
                    error_path="SNOWFLAKE_UI -> QUERY_HISTORY",
                    details={
                        "snowflake_user": row.get("USER_NAME"),
                        "snowflake_role": row.get("ROLE_NAME"),
                        "query_type": row.get("QUERY_TYPE"),
                        "execution_status": row.get("EXECUTION_STATUS"),
                        "source": "snowflake_query_history",
                    },
                    created_at=created_at,
                )
            )
            inserted_execution_logs += 1

            if status == ExecutionStatus.FAILED:
                safe_error_message = error_message or "Snowflake query failed; Snowflake did not expose a detailed error message in query history."
                repo.create_error_log(
                    ErrorLogCreate(
                        execution_log_id=execution_log.id,
                        user_id=user_id,
                        organization_id=organization_id,
                        operation_type=operation_type,
                        level=LogLevel.ERROR,
                        service_name="SnowflakeQueryHistory",
                        api_endpoint="SNOWFLAKE_UI",
                        error_type="SnowflakeQueryHistoryError",
                        exception_type="SnowflakeSQLExecutionError",
                        function_name="sync_query_history",
                        error_message=safe_error_message,
                        error_path="SNOWFLAKE_UI -> QUERY_HISTORY",
                        query_text=query_text,
                        snowflake_query_id=query_id,
                        details={
                            "error_code": row.get("ERROR_CODE"),
                            "snowflake_user": row.get("USER_NAME"),
                            "snowflake_role": row.get("ROLE_NAME"),
                        },
                        created_at=created_at,
                    )
                )
                inserted_error_logs += 1

        return SnowflakeHistorySyncResult(
            scanned=len(rows),
            inserted_execution_logs=inserted_execution_logs,
            inserted_error_logs=inserted_error_logs,
            skipped_existing=skipped_existing,
        )

    def _fetch_history(self, *, minutes: int, limit: int) -> list[dict[str, Any]]:
        try:
            account_usage_rows = self._fetch_account_usage_history(minutes=minutes, limit=limit)
        except Exception:
            logger.warning(
                "Could not read SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY. "
                "Grant imported privileges on SNOWFLAKE database to the backend role.",
                exc_info=True,
            )
            account_usage_rows = []

        information_schema_rows = self._fetch_information_schema_history(minutes=minutes, limit=limit)
        merged: dict[str, dict[str, Any]] = {}
        for row in account_usage_rows + information_schema_rows:
            query_id = row.get("QUERY_ID")
            if query_id:
                merged[str(query_id)] = row
        return list(merged.values())

    def _fetch_information_schema_history(self, *, minutes: int, limit: int) -> list[dict[str, Any]]:
        sql = f"""
        SELECT
            QUERY_ID,
            QUERY_TEXT,
            DATABASE_NAME,
            SCHEMA_NAME,
            QUERY_TYPE,
            USER_NAME,
            ROLE_NAME,
            EXECUTION_STATUS,
            ERROR_CODE,
            ERROR_MESSAGE,
            START_TIME,
            TOTAL_ELAPSED_TIME,
            ROWS_PRODUCED
        FROM TABLE({self._quote_identifier(self.history_database)}.INFORMATION_SCHEMA.QUERY_HISTORY(
            END_TIME_RANGE_START => DATEADD('minute', -{minutes}, CURRENT_TIMESTAMP()),
            RESULT_LIMIT => {limit}
        ))
        WHERE QUERY_TEXT NOT ILIKE '%QUERY_HISTORY%'
        ORDER BY START_TIME DESC
        """
        return self._execute_history_sql(sql)

    def _fetch_account_usage_history(self, *, minutes: int, limit: int) -> list[dict[str, Any]]:
        sql = f"""
        SELECT
            QUERY_ID,
            QUERY_TEXT,
            DATABASE_NAME,
            SCHEMA_NAME,
            QUERY_TYPE,
            USER_NAME,
            ROLE_NAME,
            EXECUTION_STATUS,
            ERROR_CODE,
            ERROR_MESSAGE,
            START_TIME,
            TOTAL_ELAPSED_TIME,
            ROWS_PRODUCED
        FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
        WHERE START_TIME >= DATEADD('minute', -{minutes}, CURRENT_TIMESTAMP())
          AND QUERY_TEXT NOT ILIKE '%QUERY_HISTORY%'
        ORDER BY START_TIME DESC
        LIMIT {limit}
        """
        return self._execute_history_sql(sql)

    def diagnose_sources(self, *, minutes: int = 60, limit: int = 5) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for source_name, fetcher in {
            "information_schema": self._fetch_information_schema_history,
            "account_usage": self._fetch_account_usage_history,
        }.items():
            try:
                rows = fetcher(minutes=minutes, limit=limit)
                result[source_name] = {
                    "ok": True,
                    "rows": len(rows),
                    "examples": [
                        {
                            "start_time": str(row.get("START_TIME")),
                            "user_name": row.get("USER_NAME"),
                            "role_name": row.get("ROLE_NAME"),
                            "database_name": row.get("DATABASE_NAME"),
                            "query_type": row.get("QUERY_TYPE"),
                            "execution_status": row.get("EXECUTION_STATUS"),
                            "query_text": (row.get("QUERY_TEXT") or "").replace("\n", " ")[:160],
                        }
                        for row in rows[:limit]
                    ],
                }
            except Exception as exc:
                result[source_name] = {
                    "ok": False,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                }
        return result

    def _execute_history_sql(self, sql: str) -> list[dict[str, Any]]:
        connection = self._connect()
        try:
            cursor = connection.cursor(DictCursor)
            try:
                cursor.execute(sql)
                return list(cursor.fetchall())
            finally:
                cursor.close()
        finally:
            connection.close()

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        return f'"{identifier.replace(chr(34), chr(34) + chr(34))}"'

    @staticmethod
    def _map_operation(query_type: Any, query_text: str) -> str:
        query_type_text = str(query_type or "").upper()
        if query_type_text in {"CREATE_TABLE", "INSERT", "UPDATE", "DELETE", "DROP", "SELECT", "MERGE", "COPY"}:
            return "COPY_INTO" if query_type_text == "COPY" else query_type_text
        return infer_operation_type(query_text)

    @staticmethod
    def _map_status(status: Any) -> str:
        status_text = str(status or "").upper()
        if status_text == "SUCCESS":
            return ExecutionStatus.SUCCESS
        if status_text in {"RUNNING", "RESUMING_WAREHOUSE"}:
            return ExecutionStatus.RUNNING
        if status_text in {"ABORTING", "CANCELED", "CANCELLED"}:
            return ExecutionStatus.CANCELLED
        return ExecutionStatus.FAILED

    @staticmethod
    def _as_int(value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _as_naive_datetime(value: Any) -> Optional[datetime]:
        if not isinstance(value, datetime):
            return None
        return value.replace(tzinfo=None)


def _optional_int_env(name: str) -> Optional[int]:
    value = os.getenv(name)
    if value and value.isdigit():
        return int(value)
    return None


async def run_periodic_snowflake_history_sync() -> None:
    """
    Optional background poller for Snowflake UI queries.

    It is intentionally separate from SnowflakeService automatic logging:
    - SnowflakeService logs backend executions instantly.
    - This poller imports direct Snowflake UI query history after the fact.
    """

    interval_seconds = max(30, int(os.getenv("SNOWFLAKE_HISTORY_SYNC_INTERVAL_SECONDS", "60")))
    minutes = max(1, int(os.getenv("SNOWFLAKE_HISTORY_SYNC_LOOKBACK_MINUTES", "180")))
    limit = max(1, min(int(os.getenv("SNOWFLAKE_HISTORY_SYNC_LIMIT", "200")), 1000))
    user_id = _optional_int_env("SNOWFLAKE_HISTORY_SYNC_USER_ID")
    organization_id = _optional_int_env("SNOWFLAKE_HISTORY_SYNC_ORGANIZATION_ID") or 1
    service = SnowflakeHistoryService()

    while True:
        try:
            await asyncio.to_thread(
                _sync_once,
                service,
                user_id,
                organization_id,
                minutes,
                limit,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Snowflake query history background sync failed")
        await asyncio.sleep(interval_seconds)


def _sync_once(
    service: SnowflakeHistoryService,
    user_id: Optional[int],
    organization_id: Optional[int],
    minutes: int,
    limit: int,
) -> None:
    db = SessionLocal()
    try:
        result = service.sync_query_history(
            db,
            user_id=user_id,
            organization_id=organization_id,
            minutes=minutes,
            limit=limit,
        )
        if result.inserted_execution_logs or result.inserted_error_logs:
            logger.info(
                "Synced Snowflake query history: scanned=%s inserted=%s errors=%s skipped=%s",
                result.scanned,
                result.inserted_execution_logs,
                result.inserted_error_logs,
                result.skipped_existing,
            )
    finally:
        db.close()
