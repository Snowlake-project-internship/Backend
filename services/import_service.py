from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import pandas as pd
from sqlalchemy.orm import Session

from models.import_file import ImportFile
from services.excel_service import read_excel_file, sanitize_name
from services.snowflake_service import SnowflakeService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImportResult:
    database: str
    schema: str
    tables_created: list[str]
    rows_inserted: int
    import_id: int


IMPORT_SESSION_CACHE: dict[str, dict[str, Any]] = {}
IMPORT_SESSION_TTL = timedelta(minutes=30)


def _unique_table_names(sheets: Dict[str, pd.DataFrame]) -> dict[str, str]:
    seen: dict[str, int] = {}
    table_names: dict[str, str] = {}

    for sheet_name in sheets:
        base_name = sanitize_name(sheet_name, fallback="SHEET")
        count = seen.get(base_name, 0) + 1
        seen[base_name] = count
        if count == 1:
            table_names[sheet_name] = base_name
            continue

        suffix = f"_{count}"
        table_names[sheet_name] = f"{base_name[:255 - len(suffix)]}{suffix}"

    return table_names


def _cleanup_import_sessions() -> None:
    expires_before = datetime.utcnow() - IMPORT_SESSION_TTL
    expired = [
        session_id
        for session_id, payload in IMPORT_SESSION_CACHE.items()
        if payload["created_at"] < expires_before
    ]
    for session_id in expired:
        IMPORT_SESSION_CACHE.pop(session_id, None)


def analyze_excel_import(
    *,
    file_bytes: bytes,
    original_filename: str,
    entreprise_name: str,
    user_id: Optional[int] = None,
) -> dict[str, Any]:
    _cleanup_import_sessions()
    sheets = read_excel_file(file_bytes)
    if not sheets:
        raise ValueError("The Excel file does not contain readable sheets.")

    table_names = _unique_table_names(sheets)
    preview: dict[str, Any] = {}
    duplicates: dict[str, Any] = {}
    invalid_values: dict[str, Any] = {}

    for sheet_name, dataframe in sheets.items():
        table_name = table_names[sheet_name]
        preview[sheet_name] = {
            "rows": int(len(dataframe)),
            "columns": [str(column) for column in dataframe.columns],
            "table_name": table_name,
            "action": "CREATE",
            "warnings": [],
        }

        duplicate_count = int(dataframe.attrs.get("duplicate_count", 0))
        if duplicate_count:
            duplicates[sheet_name] = {"count": duplicate_count, "examples": []}

        invalid_count = int(dataframe.attrs.get("invalid_count", 0))
        if invalid_count:
            invalid_values[sheet_name] = {
                "count": invalid_count,
                "examples": dataframe.attrs.get("invalid_examples", []),
            }

    session_id = str(uuid.uuid4())
    IMPORT_SESSION_CACHE[session_id] = {
        "file_bytes": file_bytes,
        "original_filename": original_filename,
        "entreprise_name": entreprise_name,
        "user_id": user_id,
        "created_at": datetime.utcnow(),
    }

    return {
        "session_id": session_id,
        "org_name": entreprise_name,
        "database": sanitize_name(entreprise_name, fallback="ENTREPRISE"),
        "schema": sanitize_name(original_filename, fallback="IMPORT"),
        "org_exists": False,
        "preview": preview,
        "duplicates": duplicates,
        "has_duplicates": bool(duplicates),
        "invalid_values": invalid_values,
        "has_invalid_values": bool(invalid_values),
        "existing_tables": [],
        "new_tables": list(table_names.values()),
    }


def import_cached_session(
    *,
    db: Session,
    snowflake: SnowflakeService,
    session_id: str,
    user_id: Optional[int] = None,
) -> ImportResult:
    _cleanup_import_sessions()
    payload = IMPORT_SESSION_CACHE.get(session_id)
    if not payload:
        raise ValueError("Import session expired. Upload the Excel file again.")

    result = import_excel_to_snowflake(
        db=db,
        snowflake=snowflake,
        file_bytes=payload["file_bytes"],
        original_filename=payload["original_filename"],
        entreprise_name=payload["entreprise_name"],
        user_id=user_id if user_id is not None else payload.get("user_id"),
    )
    IMPORT_SESSION_CACHE.pop(session_id, None)
    return result


def import_excel_to_snowflake(
    *,
    db: Session,
    snowflake: SnowflakeService,
    file_bytes: bytes,
    original_filename: str,
    entreprise_name: str,
    user_id: Optional[int] = None,
) -> ImportResult:
    sheets = read_excel_file(file_bytes)
    if not sheets:
        raise ValueError("The Excel file does not contain readable sheets.")

    database_name = sanitize_name(entreprise_name, fallback="ENTREPRISE")
    base_schema_name = sanitize_name(original_filename, fallback="IMPORT")
    table_names = _unique_table_names(sheets)

    try:
        # Entreprise = database. Reuse existing database if it is already present.
        snowflake.create_database(database_name)
        snowflake.use_database(database_name)

        # Uploaded file = schema. If the filename schema already exists, version it.
        schema_name = snowflake.create_unique_schema(base_schema_name)
        snowflake.use_schema(schema_name)

        tables_created: list[str] = []
        rows_inserted = 0
        for sheet_name, dataframe in sheets.items():
            table_name = table_names[sheet_name]
            snowflake.create_table_from_dataframe(table_name, dataframe)
            rows_inserted += snowflake.insert_dataframe(table_name, dataframe)
            tables_created.append(table_name)

        metadata = ImportFile(
            user_id=user_id,
            entreprise_name=entreprise_name,
            database_name=database_name,
            schema_name=schema_name,
            original_filename=original_filename,
        )
        db.add(metadata)
        db.commit()
        db.refresh(metadata)

        return ImportResult(
            database=database_name,
            schema=schema_name,
            tables_created=tables_created,
            rows_inserted=rows_inserted,
            import_id=metadata.id,
        )
    except Exception:
        db.rollback()
        logger.exception("Excel import failed for file %s", original_filename)
        raise


def list_import_history(db: Session, user_id: Optional[int] = None) -> list[ImportFile]:
    query = db.query(ImportFile)
    if user_id is not None:
        query = query.filter(ImportFile.user_id == user_id)
    return query.order_by(ImportFile.uploaded_at.desc()).limit(100).all()
