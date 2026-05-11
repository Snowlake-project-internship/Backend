from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models.user import User
from services.auth_service import hash_password
from pydantic import BaseModel

router = APIRouter()

# ─── Schemas ───────────────────────────────────────
class UpdateUserRequest(BaseModel):
    name: str | None = None
    email: str | None = None

class RoleRequest(BaseModel):
    role: str  # "user" ou "admin"

class ResetPasswordRequest(BaseModel):
    new_password: str

# ─── GET tous les users (admin seulement) ──────────
@router.get("/")
def get_all_users(db: Session = Depends(get_db)):
    users = db.query(User).all()
    return [
        {
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "role": u.role,
            "is_active": u.is_active,
            "last_login": u.last_login,
            "created_at": u.created_at
        }
        for u in users
    ]

# ─── GET un seul user ──────────────────────────────
@router.get("/{id}")
def get_user(id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User non trouvé")
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
        "last_login": user.last_login,
        "created_at": user.created_at
    }

# ─── PUT modifier infos ────────────────────────────
@router.put("/{id}")
def update_user(id: int, req: UpdateUserRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User non trouvé")
    if req.name:
        user.name = req.name
    if req.email:
        user.email = req.email
    db.commit()
    return {"message": "User mis à jour"}

# ─── PATCH activer ─────────────────────────────────
@router.patch("/{id}/activate")
def activate_user(id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User non trouvé")
    user.is_active = True
    db.commit()
    return {"message": f"User {user.name} activé"}

# ─── PATCH désactiver ──────────────────────────────
@router.patch("/{id}/deactivate")
def deactivate_user(id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User non trouvé")
    user.is_active = False
    db.commit()
    return {"message": f"User {user.name} désactivé"}

# ─── PATCH changer role ────────────────────────────
@router.patch("/{id}/role")
def change_role(id: int, req: RoleRequest, db: Session = Depends(get_db)):
    if req.role not in ["user", "admin"]:
        raise HTTPException(status_code=400, detail="Role invalide")
    user = db.query(User).filter(User.id == id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User non trouvé")
    user.role = req.role
    db.commit()
    return {"message": f"Role changé en {req.role}"}

# ─── POST reset password ───────────────────────────
@router.post("/{id}/reset-password")
def reset_password(id: int, req: ResetPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User non trouvé")
    user.hashed_password = hash_password(req.new_password)
    db.commit()
    return {"message": "Mot de passe réinitialisé"}

# ─── DELETE supprimer ──────────────────────────────
@router.delete("/{id}")
def delete_user(id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User non trouvé")
    db.delete(user)
    db.commit()
    return {"message": f"User {user.name} supprimé"}