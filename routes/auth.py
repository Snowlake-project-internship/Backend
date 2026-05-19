from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from logs.constants import ExecutionStatus
from logs.service import LoggerService
from models.user import Organization, User
from schemas.user import LoginRequest, RegisterRequest
from services.auth_service import create_token, hash_password, is_legacy_password_hash, verify_password

router = APIRouter()


@router.post("/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == req.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already in use")

    organization_name = (req.organization_name or "Default Organization").strip() or "Default Organization"
    organization = db.query(Organization).filter(Organization.name == organization_name).first()
    if not organization:
        organization = Organization(name=organization_name)
        db.add(organization)
        db.flush()

    user = User(
        username=req.username,
        email=req.email,
        hashed_password=hash_password(req.password),
        organization_id=organization.id,
        role="user",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    LoggerService.log_audit(
        LoggerService.audit_from_context(
            user_id=user.id,
            organization_id=user.organization_id,
            action="REGISTER",
            resource_type="USER",
            resource_name=user.email,
            status=ExecutionStatus.SUCCESS,
            details={"username": user.username},
        )
    )
    return {"message": "Account created", "user_id": user.id}


@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if is_legacy_password_hash(user.hashed_password):
        user.hashed_password = hash_password(req.password)
        db.commit()

    token = create_token(
        {
            "sub": str(user.id),
            "name": user.username,
            "organization_id": user.organization_id,
            "role": user.role,
        }
    )
    LoggerService.log_audit(
        LoggerService.audit_from_context(
            user_id=user.id,
            organization_id=user.organization_id,
            action="LOGIN",
            resource_type="USER",
            resource_name=user.email,
            status=ExecutionStatus.SUCCESS,
        )
    )

    return {
        "id": str(user.id),
        "access_token": token,
        "token_type": "bearer",
        "role": user.role,
        "organization_id": user.organization_id,
        "name": user.username,
        "user_id": user.id,
    }
