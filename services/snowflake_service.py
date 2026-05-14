from __future__ import annotations

import logging
import os
from typing import Any, Iterable, Optional

import pandas as pd
import snowflake.connector
from dotenv import load_dotenv
from pandas.api import types as pdt
from snowflake.connector import SnowflakeConnection
from snowflake.connector.pandas_tools import write_pandas

load_dotenv()

logger = logging.getLogger(__name__)


class SnowflakeService:
    def __init__(self) -> None:
        self.connection = self._connect()
        self.current_database: Optional[str] = None
        self.current_schema: Optional[str] = None
        self.viewer_role = os.getenv("SNOWFLAKE_VIEWER_ROLE", "ACCOUNTADMIN")

    def _connect(self) -> SnowflakeConnection:
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

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "SnowflakeService":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    @staticmethod
    def quote_identifier(identifier: str) -> str:
        return f'"{identifier.replace(chr(34), chr(34) + chr(34))}"'

    def execute_query(self, query: str, params: Optional[Iterable[Any] | dict[str, Any]] = None) -> list[tuple[Any, ...]]:
        logger.debug("Executing Snowflake query: %s", query)
        cursor = self.connection.cursor()
        try:
            cursor.execute(query, params)
            if cursor.description:
                return cursor.fetchall()
            return []
        finally:
            cursor.close()

    def create_database(self, database_name: str) -> None:
        self.execute_query(
            f"CREATE DATABASE IF NOT EXISTS {self.quote_identifier(database_name)}"
        )
        self.grant_database_usage(database_name)

    def use_database(self, database_name: str) -> None:
        self.execute_query(f"USE DATABASE {self.quote_identifier(database_name)}")
        self.current_database = database_name

    def create_schema(self, schema_name: str) -> None:
        self.execute_query(
            f"CREATE SCHEMA IF NOT EXISTS {self.quote_identifier(schema_name)}"
        )
        self.grant_schema_usage(schema_name)

    def use_schema(self, schema_name: str) -> None:
        self.execute_query(f"USE SCHEMA {self.quote_identifier(schema_name)}")
        self.current_schema = schema_name

    def schema_exists(self, schema_name: str) -> bool:
        escaped = schema_name.replace("'", "''")
        rows = self.execute_query(f"SHOW SCHEMAS LIKE '{escaped}'")
        return bool(rows)

    def create_unique_schema(self, base_schema_name: str) -> str:
        candidate = base_schema_name
        version = 2

        while self.schema_exists(candidate):
            suffix = f"_V{version}"
            candidate = f"{base_schema_name[:255 - len(suffix)]}{suffix}"
            version += 1

        self.create_schema(candidate)
        return candidate

    def table_exists(self, table_name: str) -> bool:
        escaped = table_name.replace("'", "''")
        rows = self.execute_query(f"SHOW TABLES LIKE '{escaped}'")
        return bool(rows)

    def infer_snowflake_type(self, series: pd.Series) -> str:
        dtype = series.dtype
        if pdt.is_bool_dtype(dtype):
            return "BOOLEAN"
        if pdt.is_integer_dtype(dtype):
            return "NUMBER(38, 0)"
        if pdt.is_float_dtype(dtype):
            return "FLOAT"
        if pdt.is_datetime64_any_dtype(dtype):
            return "TIMESTAMP_NTZ"
        if pdt.is_timedelta64_dtype(dtype):
            return "VARCHAR"
        return "VARCHAR"

    def create_table_from_dataframe(self, table_name: str, dataframe: pd.DataFrame) -> None:
        if len(dataframe.columns) == 0:
            raise ValueError(f"Sheet '{table_name}' has no columns after cleaning.")

        columns_sql = []
        for column in dataframe.columns:
            snowflake_type = self.infer_snowflake_type(dataframe[column])
            columns_sql.append(f"{self.quote_identifier(str(column))} {snowflake_type}")

        self.execute_query(
            f"""
            CREATE TABLE IF NOT EXISTS {self.quote_identifier(table_name)}
            ({", ".join(columns_sql)})
            """
        )
        self.grant_table_select(table_name)

    def grant_database_usage(self, database_name: str) -> None:
        if not self.viewer_role:
            return
        try:
            self.execute_query(
                f"""
                GRANT USAGE ON DATABASE {self.quote_identifier(database_name)}
                TO ROLE {self.quote_identifier(self.viewer_role)}
                """
            )
        except Exception:
            logger.warning("Could not grant database usage to role %s", self.viewer_role, exc_info=True)

    def grant_schema_usage(self, schema_name: str) -> None:
        if not self.viewer_role or not self.current_database:
            return
        try:
            self.execute_query(
                f"""
                GRANT USAGE ON SCHEMA
                {self.quote_identifier(self.current_database)}.{self.quote_identifier(schema_name)}
                TO ROLE {self.quote_identifier(self.viewer_role)}
                """
            )
        except Exception:
            logger.warning("Could not grant schema usage to role %s", self.viewer_role, exc_info=True)

    def grant_table_select(self, table_name: str) -> None:
        if not self.viewer_role or not self.current_database or not self.current_schema:
            return
        try:
            self.execute_query(
                f"""
                GRANT SELECT ON TABLE
                {self.quote_identifier(self.current_database)}.{self.quote_identifier(self.current_schema)}.{self.quote_identifier(table_name)}
                TO ROLE {self.quote_identifier(self.viewer_role)}
                """
            )
        except Exception:
            logger.warning("Could not grant table select to role %s", self.viewer_role, exc_info=True)

    def insert_dataframe(self, table_name: str, dataframe: pd.DataFrame) -> int:
        if dataframe.empty:
            return 0
        if not self.current_database or not self.current_schema:
            raise RuntimeError("Database and schema must be selected before inserting data.")

        prepared = dataframe.copy()
        prepared = prepared.where(pd.notnull(prepared), None)
        for column in prepared.columns:
            if self.infer_snowflake_type(prepared[column]) == "VARCHAR":
                prepared[column] = prepared[column].map(
                    lambda value: None if value is None else str(value)
                )
        success, _, row_count, _ = write_pandas(
            conn=self.connection,
            df=prepared,
            table_name=table_name,
            database=self.current_database,
            schema=self.current_schema,
            quote_identifiers=True,
            auto_create_table=False,
        )
        if not success:
            raise RuntimeError(f"Snowflake failed to insert rows into table {table_name}.")

        return int(row_count)
