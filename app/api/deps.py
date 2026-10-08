"""Auth dependencies. EVERY protected endpoint declares one of these, so permissions are enforced
on the server regardless of what the frontend shows."""
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import Role, User

_bearer = HTTPBearer(auto_error=False)


def get_optional_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)
) -> User | None:
    """Returns the user if a valid token is present, else None. Used by the AI endpoint, which is
    open to guests (they just can't do account actions)."""
    if creds is None:
        return None
    payload = decode_access_token(creds.credentials)
    if not payload:
        return None
    # Role is re-read from the DB, never trusted from the token alone.
    return db.get(User, int(payload["sub"]))


def get_current_user(user: User | None = Depends(get_optional_user)) -> User:
    if user is None:
        raise UnauthorizedError("Authentication required", code="not_authenticated")
    return user


def require_role(role: Role):
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role != role:
            raise ForbiddenError(f"This action requires the '{role.value}' role")
        return user

    return checker


require_customer = require_role(Role.customer)
require_seller = require_role(Role.seller)
