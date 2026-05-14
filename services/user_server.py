from sqlalchemy.orm import Session

from models.user import User
from schemas.user import RegisterRequest
from services.auth_service import hash_password


def create_user(db: Session, data: RegisterRequest) -> User:
    user = User(
        username=data.username,
        email=data.email,
        hashed_password=hash_password(data.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
