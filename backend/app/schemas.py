import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    installation_id: uuid.UUID | None = None
    platform: str | None = Field(default=None, pattern="^(android|ios)$")
    device_name: str | None = Field(default=None, min_length=1, max_length=80)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class RegistrationResponse(BaseModel):
    user: UserResponse
    token: TokenResponse
