"""Request / response DTOs.

Kept separate from the SQLModel tables so DB rows never leak directly into
HTTP responses and so we can version-evolve the API without DB migrations.
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class UserResponse(BaseModel):
    id: int
    username: str
    role: str


class LoginResponse(BaseModel):
    user: UserResponse


class GenerationStartRequest(BaseModel):
    meeting_date: date
    fengxing_open_date: date | None = None  # defaults to meeting_date on backend


class SlotValueDto(BaseModel):
    slot_key: str
    label: str
    value: str | None
    raw_value: float | None = None
    unit: str | None = None
    confidence: str = "high"
    source: str | None = None
    source_url: str | None = None


class GenerationStatusResponse(BaseModel):
    run_id: int
    status: str
    meeting_date: date
    slots: list[SlotValueDto] = Field(default_factory=list)
    has_output: bool = False
    # Populated when status == "failed". Frontend surfaces this as the
    # toast message so users see the actual cause from the backend log.
    notes: str | None = None


class InternalDataRequest(BaseModel):
    """Step 4 form payload. Keys must match slot_schema INTERNAL slot keys."""

    data: dict[str, str] = Field(default_factory=dict)
    meeting_time: str | None = None
