from pydantic import BaseModel, EmailStr
from enum import Enum
from typing import Optional
from datetime import datetime

class RoleEnum(str, Enum):
    user = "user"
    admin = "admin"

class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    name: str
    user_id: int

class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    role: RoleEnum
    is_active: bool
    last_login: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# ── User Management schemas ───────────────────────────────────────
class UpdateUserRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None

class UpdateRoleRequest(BaseModel):
    role: RoleEnum

class ResetPasswordRequest(BaseModel):
    new_password: str