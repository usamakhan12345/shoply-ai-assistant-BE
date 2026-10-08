from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, UnauthorizedError
from app.core.security import create_access_token, hash_password, verify_password
from app.models import Role, User
from app.schemas.auth import RegisterIn


def register(db: Session, data: RegisterIn) -> tuple[User, str]:
    email = data.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise ConflictError("An account with this email already exists", code="email_taken")
    user = User(
        email=email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name.strip(),
        role=data.role,
        store_name=(data.store_name or "").strip() or None if data.role == Role.seller else None,
    )
    db.add(user)
    db.commit()
    return user, create_access_token(user.id, user.role.value)


def login(db: Session, email: str, password: str) -> tuple[User, str]:
    user = db.scalar(select(User).where(User.email == email.lower()))
    # Same message for "no such user" and "wrong password" -> no account enumeration.
    if not user or not verify_password(password, user.hashed_password):
        raise UnauthorizedError("Incorrect email or password", code="invalid_credentials")
    return user, create_access_token(user.id, user.role.value)
