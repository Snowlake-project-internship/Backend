from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from logs.utils import infer_operation_type
from models.user import User
from routes.imports import get_snowflake_service
from services.auth_service import get_optional_current_user
from services.snowflake_service import SnowflakeService

router = APIRouter()


class SnowflakeQueryRequest(BaseModel):
    query: str = Field(min_length=1)
    operation_type: Optional[str] = None
    table_name: Optional[str] = None


class SnowflakeQueryResponse(BaseModel):
    success: bool
    operation_type: str
    rows: list[list[Any]]
    row_count: int


@router.post("/execute", response_model=SnowflakeQueryResponse)
async def execute_snowflake_query(
    request: SnowflakeQueryRequest,
    current_user: User | None = Depends(get_optional_current_user),
    snowflake: SnowflakeService = Depends(get_snowflake_service),
) -> SnowflakeQueryResponse:
    if current_user:
        snowflake.set_actor(
            user_id=current_user.id,
            organization_id=current_user.organization_id,
        )
    try:
        rows = await run_in_threadpool(
            snowflake.execute_query,
            request.query,
            operation_type=request.operation_type,
            table_name=request.table_name,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return SnowflakeQueryResponse(
        success=True,
        operation_type=request.operation_type or infer_operation_type(request.query),
        rows=[list(row) for row in rows],
        row_count=len(rows),
    )
