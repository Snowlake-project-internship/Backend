from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ImportFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: Optional[int] = None
    entreprise_name: str
    database_name: str
    schema_name: str
    original_filename: str
    uploaded_at: datetime


class ImportUploadResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    success: bool
    database: str
    schema_name: str = Field(serialization_alias="schema", validation_alias="schema")
    tables_created: List[str]
    rows_inserted: int
    import_id: int


class ImportAnalyzeResponse(BaseModel):
    session_id: str
    org_name: str
    database: str
    schema_name: str = Field(serialization_alias="schema", validation_alias="schema")
    org_exists: bool
    preview: Dict[str, Dict[str, Any]]
    duplicates: Dict[str, Dict[str, Any]]
    has_duplicates: bool
    invalid_values: Dict[str, Dict[str, Any]]
    has_invalid_values: bool
    existing_tables: List[str]
    new_tables: List[str]


class ImportConfirmRequest(BaseModel):
    session_id: str
    user_id: Optional[int] = None
