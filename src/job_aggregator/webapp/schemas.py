from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator


# ---------- Families ----------

class FamilyCreate(BaseModel):
    slug: str
    display_name: str
    description: str | None = None
    sort_order: int = 0


class FamilyUpdate(BaseModel):
    display_name: str | None = None
    description: str | None = None
    sort_order: int | None = None


class KeywordCreate(BaseModel):
    keyword: str


class KeywordOut(BaseModel):
    id: uuid.UUID
    keyword: str

    model_config = {"from_attributes": True}


class FamilyOut(BaseModel):
    id: uuid.UUID
    slug: str
    display_name: str
    description: str | None
    sort_order: int
    keywords: list[KeywordOut]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------- Regions ----------

class RegionCreate(BaseModel):
    slug: str
    display_name: str
    center_lat: float
    center_lon: float
    department_codes: list[str] | None = None


class RegionUpdate(BaseModel):
    display_name: str | None = None
    center_lat: float | None = None
    center_lon: float | None = None
    department_codes: list[str] | None = None


class RegionOut(BaseModel):
    id: uuid.UUID
    slug: str
    display_name: str
    center_lat: float
    center_lon: float
    department_codes: list[str] | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------- Users ----------

class UserCreate(BaseModel):
    username: str
    email: str | None = None
    password: str
    is_admin: bool = False


class UserUpdate(BaseModel):
    email: str | None = None
    is_admin: bool | None = None
    is_active: bool | None = None
    password: str | None = None  # when set, hashed and stored


class UserOut(BaseModel):
    id: uuid.UUID
    username: str
    email: str | None
    is_admin: bool
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None

    model_config = {"from_attributes": True}


# ---------- Offer views ----------

_VALID_VIEW_STATUSES = {"viewed", "saved", "dismissed"}


class OfferViewCreate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in _VALID_VIEW_STATUSES:
            raise ValueError(f"status must be one of {_VALID_VIEW_STATUSES}")
        return v


class OfferViewOut(BaseModel):
    offer_id: uuid.UUID
    status: str
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------- Offers ----------

class OfferOut(BaseModel):
    id: uuid.UUID
    title: str
    company: str | None
    location: str | None
    department: str | None
    contract_type: str | None
    url: str
    source: str
    relevance_score: int | None
    distance_km: float | None = None
    user_status: str | None = None  # "viewed" | "saved" | "dismissed" | None
    expires_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class OfferListResponse(BaseModel):
    items: list[OfferOut]
    total: int
    limit: int
    offset: int
