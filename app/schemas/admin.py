from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class AdminUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class AdminRefreshRequest(BaseModel):
    refresh_token: str


class AdminTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    admin: AdminUserOut


class AdminAccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
