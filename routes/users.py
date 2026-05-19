from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from database import get_db
from models.user import User
from services.auth_service import hash_password

router = APIRouter()


class UpdateUserRequest(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None


class ResetPasswordRequest(BaseModel):
    new_password: str


def _serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "organization_id": user.organization_id,
        "role": user.role,
        "created_at": user.created_at,
    }


@router.get("/")
def get_all_users(db: Session = Depends(get_db)):
    return [_serialize_user(user) for user in db.query(User).order_by(User.id).all()]


@router.get("/{id}")
def get_user(id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _serialize_user(user)


@router.put("/{id}")
def update_user(id: int, req: UpdateUserRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if req.username:
        user.username = req.username
    if req.email:
        existing = db.query(User).filter(User.email == req.email, User.id != id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already in use")
        user.email = req.email

    db.commit()
    db.refresh(user)
    return _serialize_user(user)


@router.post("/{id}/reset-password")
def reset_password(id: int, req: ResetPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.hashed_password = hash_password(req.new_password)
    db.commit()
    return {"message": "Password reset"}


@router.delete("/{id}")
def delete_user(id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    db.delete(user)
    db.commit()
    return {"message": f"User {user.username} deleted"}
