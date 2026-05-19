from datetime import datetime

from pydantic import AliasChoices, BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    username: str = Field(validation_alias=AliasChoices("username", "name"), min_length=2)
    email: EmailStr
    password: str
    organization_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: EmailStr
    organization_id: int | None = None
    role: str = "user"
    created_at: datetime
