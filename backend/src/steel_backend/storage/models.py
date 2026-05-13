"""SQLModel table definitions."""
from __future__ import annotations

from datetime import date as date_t
from datetime import datetime

from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True, max_length=64)
    password_hash: str
    role: str = Field(default="user", max_length=16)  # 'admin' | 'user'
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: datetime | None = None


class PriceHistory(SQLModel, table=True):
    __tablename__ = "price_history"

    id: int | None = Field(default=None, primary_key=True)
    slot_key: str = Field(index=True, max_length=64)
    value_date: date_t = Field(index=True)
    value: float | None = None
    unit: str | None = Field(default=None, max_length=16)
    source: str = Field(max_length=32)
    raw_text: str = ""
    source_url: str = ""
    confidence: str = Field(default="high", max_length=8)
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    fetched_by: str = Field(max_length=64)


class CscPriceState(SQLModel, table=True):
    """One row per (group, slot_index) — current state of 中鋼 prices.

    Updates monthly (group='monthly') or quarterly (group='quarterly').
    Admin form overwrites these directly.
    """
    __tablename__ = "csc_price_state"

    id: int | None = Field(default=None, primary_key=True)
    group: str = Field(index=True, max_length=16)           # 'monthly' | 'quarterly'
    slot_index: int = Field(index=True)                      # 0..N-1 within group
    prev_price: int = 0                                       # 上月/上季基價
    change_amount: int = 0                                    # 調整金額 (signed)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    updated_by: str = Field(default="", max_length=64)


class CscAnnouncementMeta(SQLModel, table=True):
    """Header metadata that goes above each 中鋼 table in 八.1 / 八.2."""
    __tablename__ = "csc_announcement_meta"

    group: str = Field(primary_key=True, max_length=16)
    period_label: str = Field(default="", max_length=64)      # "115 年 5 月份"
    announce_date: str = Field(default="", max_length=16)     # "2026/4/15"
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    updated_by: str = Field(default="", max_length=64)


class GenerationRun(SQLModel, table=True):
    __tablename__ = "generation_runs"

    id: int | None = Field(default=None, primary_key=True)
    meeting_date: date_t
    started_by: str = Field(max_length=64)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: datetime | None = None
    status: str = Field(default="running", max_length=16)
    # 'running' | 'success' | 'partial' | 'failed'
    output_path: str | None = None
    notes: str = ""
    # JSON blob: slot_values + confidence + fetched_index (serialised
    # FetchResult dicts). Populated by the background task on completion
    # so the /status endpoint can return full results without re-running
    # the graph. Empty string = task hasn't finished yet.
    result_json: str = Field(default="")
