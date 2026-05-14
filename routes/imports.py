from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from database import get_db
from schemas.import_file import (
    ImportAnalyzeResponse,
    ImportConfirmRequest,
    ImportFileResponse,
    ImportUploadResponse,
)
from services.import_service import (
    analyze_excel_import,
    import_cached_session,
    import_excel_to_snowflake,
    list_import_history,
)
from services.snowflake_service import SnowflakeService

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_EXCEL_EXTENSIONS = {".xlsx", ".xls"}


def get_snowflake_service():
    try:
        service = SnowflakeService()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        yield service
    finally:
        service.close()


def _validate_excel_upload(file: UploadFile) -> None:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Excel filename is required.")

    lower_filename = file.filename.lower()
    if not any(lower_filename.endswith(extension) for extension in ALLOWED_EXCEL_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail="Only .xlsx and .xls Excel files are accepted.",
        )


@router.post("/upload", response_model=ImportUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_import(
    file: UploadFile = File(...),
    entreprise_name: str = Form(...),
    user_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    snowflake: SnowflakeService = Depends(get_snowflake_service),
) -> ImportUploadResponse:
    _validate_excel_upload(file)

    if not entreprise_name.strip():
        raise HTTPException(status_code=400, detail="Entreprise name is required.")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded Excel file is empty.")

    try:
        result = await run_in_threadpool(
            import_excel_to_snowflake,
            db=db,
            snowflake=snowflake,
            file_bytes=file_bytes,
            original_filename=file.filename,
            entreprise_name=entreprise_name.strip(),
            user_id=user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.exception("Import runtime error")
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected import error")
        raise HTTPException(
            status_code=500,
            detail="Unexpected error while importing Excel data.",
        ) from exc

    return ImportUploadResponse(
        success=True,
        database=result.database,
        schema_name=result.schema,
        tables_created=result.tables_created,
        rows_inserted=result.rows_inserted,
        import_id=result.import_id,
    )


@router.post("/analyze", response_model=ImportAnalyzeResponse)
async def analyze_import(
    file: UploadFile = File(...),
    entreprise_name: str = Form(...),
    user_id: Optional[int] = Form(None),
) -> ImportAnalyzeResponse:
    _validate_excel_upload(file)

    if not entreprise_name.strip():
        raise HTTPException(status_code=400, detail="Entreprise name is required.")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded Excel file is empty.")

    try:
        result = await run_in_threadpool(
            analyze_excel_import,
            file_bytes=file_bytes,
            original_filename=file.filename,
            entreprise_name=entreprise_name.strip(),
            user_id=user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected analyze error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ImportAnalyzeResponse(**result)


@router.post("/confirm", response_model=ImportUploadResponse, status_code=status.HTTP_201_CREATED)
async def confirm_import(
    request: ImportConfirmRequest,
    db: Session = Depends(get_db),
    snowflake: SnowflakeService = Depends(get_snowflake_service),
) -> ImportUploadResponse:
    try:
        result = await run_in_threadpool(
            import_cached_session,
            db=db,
            snowflake=snowflake,
            session_id=request.session_id,
            user_id=request.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.exception("Import runtime error")
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected import error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ImportUploadResponse(
        success=True,
        database=result.database,
        schema_name=result.schema,
        tables_created=result.tables_created,
        rows_inserted=result.rows_inserted,
        import_id=result.import_id,
    )


@router.get("/history", response_model=list[ImportFileResponse])
def import_history(
    user_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    return list_import_history(db, user_id=user_id)
