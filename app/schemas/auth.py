from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.models.user import Role
from app.schemas.common import ORM


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    full_name: str = Field(min_length=1, max_length=120)
    role: Role = Role.customer
    store_name: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def seller_needs_store(self):
        if self.role == Role.seller and not (self.store_name or "").strip():
            raise ValueError("store_name is required for sellers")
        return self


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(ORM):
    id: int
    email: EmailStr
    full_name: str
    role: Role
    store_name: str | None
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    store_name: str | None = Field(default=None, max_length=120)
