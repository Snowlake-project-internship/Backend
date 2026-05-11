from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from models.user import User
from schemas.user_schema import UpdateUserRequest, UpdateRoleRequest, ResetPasswordRequest
from services.auth_service import hash_password

# ── Get all users ─────────────────────────────────────────────────
def get_all_users(db: Session):
    return db.query(User).all()

# ── Get user by id ────────────────────────────────────────────────
def get_user_by_id(db: Session, user_id: int):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return user

# ── Update user info ──────────────────────────────────────────────
def update_user(db: Session, user_id: int, data: UpdateUserRequest):
    user = get_user_by_id(db, user_id)

    if data.name:
        user.name = data.name
    if data.email:
        # check email not taken
        existing = db.query(User).filter(
            User.email == data.email,
            User.id != user_id
        ).first()
        if existing:
            raise HTTPException(
                status_code=400,
                detail="Email already in use"
            )
        user.email = data.email

    db.commit()
    db.refresh(user)
    return user

# ── Activate user ─────────────────────────────────────────────────
def activate_user(db: Session, user_id: int):
    user = get_user_by_id(db, user_id)
    user.is_active = True
    db.commit()
    db.refresh(user)
    return user

# ── Deactivate user ───────────────────────────────────────────────
def deactivate_user(db: Session, user_id: int):
    user = get_user_by_id(db, user_id)
    user.is_active = False
    db.commit()
    db.refresh(user)
    return user

# ── Update role ───────────────────────────────────────────────────
def update_role(db: Session, user_id: int, data: UpdateRoleRequest):
    user = get_user_by_id(db, user_id)
    user.role = data.role
    db.commit()
    db.refresh(user)
    return user

# ── Reset password ────────────────────────────────────────────────
def reset_password(db: Session, user_id: int, data: ResetPasswordRequest):
    user = get_user_by_id(db, user_id)
    user.hashed_password = hash_password(data.new_password)
    db.commit()
    return {"message": "Password reset successfully"}

# ── Delete user ───────────────────────────────────────────────────
def delete_user(db: Session, user_id: int):
    user = get_user_by_id(db, user_id)
    db.delete(user)
    db.commit()
    return {"message": "User deleted successfully"}